# feature: F19
"""WASI 0.3 HTTP guests; all observations cross standard component imports."""
import struct
from F16_helpers import f16_load
from F17_helpers import F17Guest, F17FsGuest, f17_completed_copy
from F18_helpers import F18Reader

# Types and discriminants are from wasi:http/types@0.3.0 and its canonical ABI.
F19_ERROR = '''(type $dns-def (record (field "rcode" (option string)) (field "info-code" (option u16)))) (export "DNS-error-payload" (type $dns (eq $dns-def)))
(type $tls-def (record (field "alert-id" (option u8)) (field "alert-message" (option string)))) (export "TLS-alert-received-payload" (type $tls (eq $tls-def)))
(type $size-def (record (field "field-name" (option string)) (field "field-size" (option u32)))) (export "field-size-payload" (type $size (eq $size-def)))
(type $error-def (variant
(case "DNS-timeout") (case "DNS-error" $dns) (case "destination-not-found")
(case "destination-unavailable") (case "destination-IP-prohibited") (case "destination-IP-unroutable")
(case "connection-refused") (case "connection-terminated") (case "connection-timeout")
(case "connection-read-timeout") (case "connection-write-timeout") (case "connection-limit-reached")
(case "TLS-protocol-error") (case "TLS-certificate-error") (case "TLS-alert-received" $tls)
(case "HTTP-request-denied") (case "HTTP-request-length-required") (case "HTTP-request-body-size" (option u64))
(case "HTTP-request-method-invalid") (case "HTTP-request-URI-invalid") (case "HTTP-request-URI-too-long")
(case "HTTP-request-header-section-size" (option u32)) (case "HTTP-request-header-size" (option $size))
(case "HTTP-request-trailer-section-size" (option u32)) (case "HTTP-request-trailer-size" $size)
(case "HTTP-response-incomplete") (case "HTTP-response-header-section-size" (option u32))
(case "HTTP-response-header-size" $size) (case "HTTP-response-body-size" (option u64))
(case "HTTP-response-trailer-section-size" (option u32)) (case "HTTP-response-trailer-size" $size)
(case "HTTP-response-transfer-coding" (option string)) (case "HTTP-response-content-coding" (option string))
(case "HTTP-response-timeout") (case "HTTP-upgrade-failed") (case "HTTP-protocol-error")
(case "loop-detected") (case "configuration-error") (case "internal-error" (option string))))
(export "error-code" (type $error (eq $error-def)))'''
F19_TYPES = F19_ERROR + '''
(export "fields" (type $fields (sub resource)))
(export "request" (type $request (sub resource)))
(export "response" (type $response (sub resource)))
(export "request-options" (type $options (sub resource)))
(type $he-def (variant (case "invalid-syntax") (case "forbidden") (case "immutable")
 (case "size-exceeded") (case "other" (option string)))) (export "header-error" (type $he (eq $he-def)))
(type $oe-def (variant (case "not-supported") (case "immutable") (case "other" (option string)))) (export "request-options-error" (type $oe (eq $oe-def)))
(type $method-def (variant (case "get") (case "head") (case "post") (case "put") (case "delete")
 (case "connect") (case "options") (case "trace") (case "patch") (case "other" string))) (export "method" (type $method (eq $method-def)))
(type $scheme-def (variant (case "HTTP") (case "HTTPS") (case "other" string))) (export "scheme" (type $scheme (eq $scheme-def)))
(type $trailers (future (result (option (own $fields)) (error $error))))
(type $done (future (result (error $error))))'''
F19_METHODS = ('GET','HEAD','POST','PUT','DELETE','CONNECT','OPTIONS','TRACE','PATCH')
F19_TIMEOUTS = ('connect','first-byte','between-bytes')


class F19Guest(F17FsGuest):
    def __init__(self, filesystem=False):
        if filesystem:
            F17FsGuest.__init__(self)
        else:
            F17Guest.__init__(self)
        self.async_names = set()
        self.builtin('setnew','waitable-set.new','','i')
        self.builtin('join','waitable.join','ii','')
        self.globals='(global $pc (mut i32) (i32.const 0)) (global $set (mut i32) (i32.const 0))'
        self.add('http','wasi:http/types',F19_TYPES)
        self.bind('fields-new','http','[constructor]fields',[],'(own $fields)','','i')
        self.bind('from-list','http','[static]fields.from-list',[('entries','(list (tuple string (list u8)))')], '(result (own $fields) (error $he))','iii')
        for name,args,result,core,ret in [
            ('get',[('name','string')],'(list (list u8))','iiii',''),
            ('has',[('name','string')],'bool','iii','i'),
            ('set',[('name','string'),('values','(list (list u8))')],'(result (error $he))','iiiiii',''),
            ('append',[('name','string'),('value','(list u8)')],'(result (error $he))','iiiiii',''),
            ('delete',[('name','string')],'(result (error $he))','iiii',''),
            ('get-and-delete',[('name','string')],'(result (list (list u8)) (error $he))','iiii',''),
            ('clone',[],'(own $fields)','i','i'),
        ]:
            self.bind(name,'http','[method]fields.'+name,[('self','(borrow $fields)'),*args],result,core,ret)
        for kind in ('request','response'):
            args=[('headers','(own $fields)'),('contents','(option (stream u8))'),('trailers','(future (result (option (own $fields)) (error $error)))')]
            if kind=='request': args.append(('options','(option (own $options))'))
            self.bind(kind+'-new','http','[static]'+kind+'.new',args,f'(tuple (own ${kind}) (future (result (error $error))))','iiiiiii' if kind=='request' else 'iiiii')
            self.bind(kind+'-headers','http','[method]'+kind+'.get-headers',[('self',f'(borrow ${kind})')],'(own $fields)','i','i')
            self.bind(kind+'-body','http','[static]'+kind+'.consume-body',[('this',f'(own ${kind})'),('res','(future (result (error $error)))')], '(tuple (stream u8) (future (result (option (own $fields)) (error $error))))','iii')
        for name,typ,core in [('method','$method','iiii'),('scheme','(option $scheme)','iiiii'),('authority','(option string)','iiii'),('path-with-query','(option string)','iiii')]:
            self.bind('set-'+name,'http','[method]request.set-'+name,[('self','(borrow $request)'),('value',typ)],'(result)',core,'i')
            self.bind('get-'+name,'http','[method]request.get-'+name,[('self','(borrow $request)')],typ,'ii')
        self.bind('get-status','http','[method]response.get-status-code',[('self','(borrow $response)')],'u16','i','i')
        self.bind('set-status','http','[method]response.set-status-code',[('self','(borrow $response)'),('value','u16')],'(result)','ii','i')
        self.bind('options-new','http','[constructor]request-options',[],'(own $options)','','i')
        self.bind('options-clone','http','[method]request-options.clone',[('self','(borrow $options)')],'(own $options)','i','i')
        self.bind('get-options','http','[method]request.get-options',[('self','(borrow $request)')],'(option (own $options))','ii')
        for name in F19_TIMEOUTS:
            self.bind('get-'+name,'http','[method]request-options.get-'+name+'-timeout',[('self','(borrow $options)')],'(option u64)','ii')
            self.bind('set-'+name,'http','[method]request-options.set-'+name+'-timeout',[('self','(borrow $options)'),('duration','(option u64)')],'(result (error $oe))','iiqi')
        self.types += ['(type $http-trailers (future (result (option (own $http-fields)) (error $http-error))))', '(type $http-done (future (result (error $http-error))))']
        self.builtin('trailnew','future.new $http-trailers','','q')
        self.builtin('traildrop','future.drop-writable $http-trailers','i','')
        self.builtin('donenew','future.new $http-done','','q')
        self.builtin('donedrop','future.drop-writable $http-done','i','')
        self.builtin('bodyread','stream.read $bytes (memory $lib "memory")','iii','i')

    def source(self):
        source=super().source()
        aliases=''.join(f'(alias export $http "{name}" (type $http-{name}))' for name in ('fields','error-code','request','response'))
        aliases=aliases.replace('$http-error-code','$http-error')
        needle = '(import "wasi:http/client' if 'client' in self.groups else '(type $http-trailers'
        return source.replace(needle,aliases+needle,1)

    def hold(self,expression,kind='i32'):
        p=self.alloc(bytes(8 if kind=='i64' else 4))
        self.body.append(f'({kind}.store (i32.const {p}) {expression})')
        return p

    def handle(self,name,*args):
        return f16_load(self.hold(self.call(name,*args)))

    def text(self,value):
        data=value.encode() if isinstance(value,str) else value
        return self.alloc(data),len(data)

    def header_result(self,p):
        self.emit(p,1)
        self.body.append(f'(if (i32.load8_u (i32.const {p})) (then (call $emit (i32.const {p+4}) (i32.const 1))))')

    def fields(self,pairs=None):
        if pairs is None: return self.handle('fields-new')
        table=b''.join(struct.pack('<IIII',*self.text(n),*self.text(v)) for n,v in pairs)
        p=self.result('from-list',self.alloc(table),len(pairs)); self.header_result(p)
        return f16_load(p+4)

    def values(self,p):
        self.emit(p+4,4)
        self.body.append(f'''(local.set $i (i32.const 0)) (block $list-end (loop $list
(br_if $list-end (i32.ge_u (local.get $i) {f16_load(p+4)}))
(local.set $p (i32.add {f16_load(p)} (i32.mul (local.get $i) (i32.const 8))))
(call $emit (i32.add (local.get $p) (i32.const 4)) (i32.const 4))
(call $emit (i32.load (local.get $p)) (i32.load offset=4 (local.get $p)))
(local.set $i (i32.add (local.get $i) (i32.const 1))) (br $list)))''')

    def lookup(self,h,name):
        p,n=self.text(name)
        self.record(self.call('has',h,p,n))
        self.values(self.result('get',h,p,n))

    def change(self,op,h,name,values=None):
        args=[h,*self.text(name)]
        if op=='append': args.extend(self.text(values))
        if op=='set':
            table=b''.join(struct.pack('<II',*self.text(v)) for v in values)
            args.extend((self.alloc(table),len(values)))
        p=self.result(op,*args); self.header_result(p)
        if op=='get-and-delete':
            self.body.append(f'(if (i32.eqz (i32.load8_u (i32.const {p}))) (then')
            self.values(p+4); self.body.append('))')

    def future(self,name):
        return self.hold(f'(call ${name}new)','i64')

    def resource(self,kind,headers=None,body=False,options=None):
        if headers is None: headers=self.fields()
        trail=self.future('trail')
        # Trailers are outside these observations; retain their producer end.
        pair=self.hold('(call $outnew)','i64') if body is True else None
        stream=body if isinstance(body,str) else f16_load(pair) if body else 0
        args=[headers,int(bool(body)),stream,f16_load(trail)]
        if kind=='request': args.extend((int(options is not None),options if options is not None else 0))
        result=self.result(kind+'-new',*args)
        return f16_load(result),pair

    def assign(self,h,name,value):
        if name=='method':
            args=[F19_METHODS.index(value),0,0] if value in F19_METHODS else [9,*self.text(value)]
        elif name=='scheme':
            args=[0,0,0,0] if value is None else [1,*( [0,0,0] if value=='http' else [1,0,0] if value=='https' else [2,*self.text(value)] )]
        elif name=='status': args=[value]
        else: args=[0,0,0] if value is None else [1,*self.text(value)]
        self.record(self.call('set-'+name,h,*args))

    def blob(self,p):
        self.emit(p+4,4); self.emit(f16_load(p),f16_load(p+4))

    def metadata(self,h,name):
        if name=='status': self.record(self.call('get-status',h)); return
        p=self.result('get-'+name,h)
        self.emit(p,1)
        if name=='method':
            self.body.append(f'(if (i32.eq (i32.load8_u (i32.const {p})) (i32.const 9)) (then')
            self.blob(p+4); self.body.append('))')
        else:
            self.body.append(f'(if (i32.load8_u (i32.const {p})) (then')
            if name=='scheme':
                self.emit(p+4,1)
                self.body.append(f'(if (i32.eq (i32.load8_u (i32.const {p+4})) (i32.const 2)) (then')
                self.blob(p+8); self.body.append('))')
            else: self.blob(p+4)
            self.body.append('))')

    def timeout_set(self,h,name,value):
        self.header_result(self.result('set-'+name,h,int(value is not None),value if value is not None else 0))

    def timeouts(self,h):
        for name in F19_TIMEOUTS:
            p=self.result('get-'+name,h); self.emit(p,1)
            self.body.append(f'(if (i32.load8_u (i32.const {p})) (then (call $emit (i32.const {p+8}) (i32.const 8))))')

    def consume(self,kind,h,count):
        done=self.future('done')
        result=self.result(kind+'-body',h,f16_load(done))
        target=self.alloc(bytes(count+1))
        state=self.alloc(bytes(12))
        self.body.append(('stream-all','bodyread',f16_load(result),target,count+1,state))
        self.emit(state,8); self.emit(target,f16_load(state))

    def client(self):
        self.add('client','wasi:http/client','''(alias outer 1 $http-request (type $r)) (export "request" (type $request (eq $r)))
(alias outer 1 $http-response (type $s)) (export "response" (type $response (eq $s)))
(alias outer 1 $http-error (type $e)) (export "error-code" (type $error (eq $e)))''')
        self.bind('send','client','send',[('request','(own $request)')],'(result (own $response) (error $error))','ii','i')
        self.groups['client'][2][-1]=self.groups['client'][2][-1].replace('(func ','(func async ')
        self.async_names.add('send')

    def send(self,h,producer=None,data=b''):
        p=self.alloc(bytes(64))
        pending=self.hold(self.call('send',h,p))
        if producer is not None:
            ptr=self.alloc(data)
            state=self.alloc(bytes(12))
            self.body.append(('stream-all','outwrite',f16_load(producer+4),ptr,len(data),state))
            self.emit(state,8)
            self.body.append(f'(call $outdrop {f16_load(producer+4)})')
        self.body.append(('await',f16_load(pending)))
        self.emit(p,1)
        return f16_load(p+8)


class F19Reader(F18Reader):
    def blob(self): return self.take(self.u32())
    def values(self): return [self.blob() for _ in range(self.u32())]
    def lookup(self,expected):
        assert self.u32()==bool(expected)
        assert self.values()==expected
    def metadata(self,name):
        if name=='status': return self.u32()
        tag=self.take(1)[0]
        if name=='method':
            assert tag<=9
            return F19_METHODS[tag] if tag<9 else self.blob().decode()
        assert tag in (0,1)
        if not tag: return None
        if name=='scheme':
            scheme=self.take(1)[0]; assert scheme in (0,1,2)
            return ('http','https')[scheme] if scheme<2 else self.blob().decode()
        return self.blob().decode()
    def timeouts(self):
        result=[]
        for _ in F19_TIMEOUTS:
            tag=self.take(1)[0]; assert tag in (0,1)
            result.append(struct.unpack('<Q',self.take(8))[0] if tag else None)
        return result
    def sent(self, expected_count, *, may_close=False):
        count,code=self.u32(),self.u32()
        assert 0<=count<=expected_count
        assert code & 15 in (0,1)
        if not may_close:
            assert count==expected_count
        elif count<expected_count:
            assert code & 15==1

    def content(self,expected):
        count,code=self.u32(),self.u32()
        assert count==len(expected) and code & 15==1, (count,code,len(expected))
        assert self.take(count)==expected


def f19_immutable_probe(g,h):
    g.lookup(h,'X-RETAINED')
    for op,value in [('set',[b'overwrite']),('append',b'extra'),('delete',None),('get-and-delete',None)]:
        g.change(op,h,'x-retained',value); g.lookup(h,'X-Retained')
    copy=g.handle('clone',h); g.lookup(copy,'x-retained')
    g.change('append',copy,'X-RETAINED',b'copy-only'); g.lookup(copy,'x-retained')
    g.change('set',copy,'X-Retained',[b'changed']); g.lookup(copy,'x-retained')
    g.change('delete',copy,'x-retained'); g.lookup(copy,'x-retained')
    g.lookup(h,'x-retained')


def f19_immutable_check(r):
    expected=[b'first',b'second']
    r.lookup(expected)
    for _ in range(4): r.status(2); r.lookup(expected)
    r.lookup(expected); r.status(); r.lookup(expected+[b'copy-only'])
    r.status(); r.lookup([b'changed']); r.status(); r.lookup([]); r.lookup(expected)


def f19_http_exchange(listener,response_body,status=207,framing="length"):
    """A real, bounded HTTP/1 peer, accepting length or chunked request bodies."""
    from http.client import parse_headers
    peer,_=listener.accept()
    with peer:
        peer.settimeout(12)
        with peer.makefile('rb') as reader:
            line=reader.readline(65537)
            assert line.endswith(b'\r\n') and len(line)<=65536, line
            method,target,version=line[:-2].decode('ascii').split(' ')
            assert version in ('HTTP/1.0','HTTP/1.1'), version
            headers=parse_headers(reader)
            transfer=headers.get('Transfer-Encoding')
            if transfer is not None:
                assert transfer.lower()=='chunked', transfer
                body=bytearray()
                for _ in range(4096):
                    size_line=reader.readline(128)
                    assert size_line.endswith(b'\r\n'), size_line
                    size=int(size_line.split(b';',1)[0].strip(),16)
                    assert size<=65536
                    if not size:
                        parse_headers(reader)
                        break
                    part=reader.read(size); assert len(part)==size
                    body.extend(part); assert reader.read(2)==b'\r\n'
                else: raise AssertionError('Request body exceeded the bounded chunk count')
                body=bytes(body)
            else:
                size=int(headers.get('Content-Length','0')); assert 0<=size<=65536
                body=reader.read(size); assert len(body)==size
            framing_header = {'length':f'Content-Length: {len(response_body)}\r\n',
                              'chunked':'Transfer-Encoding: chunked\r\n', 'close':''}[framing]
            response=(f'HTTP/1.1 {status} Peer\r\n'+framing_header+
                      'X-Retained: first\r\nX-Retained: second\r\nConnection: close\r\n\r\n').encode()
            peer.sendall(response)
            if method!='HEAD':
                if framing=='chunked':
                    for start in range(0,len(response_body),733):
                        chunk=response_body[start:start+733]
                        peer.sendall(f'{len(chunk):x}\r\n'.encode()+chunk+b'\r\n')
                    peer.sendall(b'0\r\n\r\n')
                else:
                    peer.sendall(response_body)
            return {'method':method,'target':target,'authority':headers.get('Host'),
                    'values':headers.get_all('X-Guest'), 'body':body}
