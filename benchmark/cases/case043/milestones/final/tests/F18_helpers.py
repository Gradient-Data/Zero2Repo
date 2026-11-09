# feature: F18
"""Real loopback peers and WASI socket command guests.

Guest bytes are canonical-ABI observations, not implementation state. Padding
and resource identities are never compared. All network waits are bounded.
"""
import ipaddress
import socket
import struct
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from F16_helpers import F16Guest, f16_load, f16_success
from F17_helpers import F17Guest, F17FsGuest, f17_completed_copy

F18_ERRORS = 'access-denied not-supported invalid-argument out-of-memory timeout invalid-state address-not-bindable address-in-use remote-unreachable connection-refused connection-broken connection-reset connection-aborted datagram-too-large'
F18_TYPES = '\n'.join(
    f'(type ${key}-def {value}) (export "{name}" (type ${key} (eq ${key}-def)))'
    for key,name,value in [
        ('family','ip-address-family','(enum "ipv4" "ipv6")'),
        ('v4','ipv4-address','(tuple u8 u8 u8 u8)'),
        ('v6','ipv6-address','(tuple u16 u16 u16 u16 u16 u16 u16 u16)'),
        ('a4','ipv4-socket-address','(record (field "port" u16) (field "address" $v4))'),
        ('a6','ipv6-socket-address','(record (field "port" u16) (field "flow-info" u32) (field "address" $v6) (field "scope-id" u32))'),
        ('addr','ip-socket-address','(variant (case "ipv4" $a4) (case "ipv6" $a6))'),
        ('ip','ip-address','(variant (case "ipv4" $v4) (case "ipv6" $v6))'),
    ])
F18_ERROR_TYPE = '(type $error-def (variant '+''.join(f'(case "{s}")' for s in F18_ERRORS.split())+'(case "other" (option string)))) (export "error-code" (type $error (eq $error-def)))'


def f18_flat(address):
    host, port = address[:2]
    ip = ipaddress.ip_address(host)
    if ip.version == 4:
        return [0, port, *ip.packed, *([0]*6)]
    return [1, port, 0, *struct.unpack('!8H', ip.packed), 0]


def f18_address_bytes(address):
    flat = f18_flat(address)
    data = bytearray(32)
    data[0] = flat[0]
    struct.pack_into('<H', data, 4, flat[1])
    if flat[0] == 0:
        data[6:10] = bytes(flat[2:6])
    else:
        struct.pack_into('<8H', data, 12, *flat[3:11])
    return bytes(data)


class F18Guest(F17FsGuest):
    def __init__(self, protocol='tcp'):
        F17Guest.__init__(self)
        self.async_names = set()
        self.builtin('setnew','waitable-set.new','','i')
        self.builtin('join','waitable.join','ii','')
        self.globals='(global $pc (mut i32) (i32.const 0)) (global $set (mut i32) (i32.const 0))'
        self.protocol = protocol
        self.add('sock', 'wasi:sockets/types', F18_TYPES + F18_ERROR_TYPE + f'(export "{protocol}-socket" (type $socket (sub resource)))')
        self.bind('create','sock',f'[static]{protocol}-socket.create',[('family','$family')], '(result (own $socket) (error $error))','ii')
        for name in ('bind','connect'):
            self.method(name,[('address','$addr')], '(result (error $error))', 'i'*14, asynchronous=(protocol=='tcp' and name=='connect'))
        for name in ('get-local-address','get-remote-address'):
            self.method(name,[], '(result $addr (error $error))','ii')
        self.method('get-address-family',[], '$family','i','i')
        if protocol == 'udp':
            self.method('disconnect',[], '(result (error $error))','ii')
            self.method('send',[('data','(list u8)'),('remote','(option $addr)')], '(result (error $error))','ii',asynchronous=True)
            self.method('receive',[], '(result (tuple (list u8) $addr) (error $error))','ii',asynchronous=True)
        else:
            self.groups['sock'][1] += '(type $incoming (stream (own $socket)))'
            self.method('get-is-listening',[], 'bool','i','i')
            self.method('listen',[], '(result $incoming (error $error))','ii')
            self.method('send',[('data','(stream u8)')], '(future (result (error $error)))','ii','i')
            self.method('receive',[], '(tuple (stream u8) (future (result (error $error))))','ii')
            self.types += ['(type $accepted (stream (own $socket)))', '(type $completion (future (result (error $socket-error))))']
            self.builtin('acceptread','stream.read $accepted (memory $lib "memory")','iii','i')
            self.builtin('netread','stream.read $bytes (memory $lib "memory")','iii','i')
            self.builtin('done','future.read $completion (memory $lib "memory") (realloc $realloc)','ii','i')

    def method(self,name,params,result,core,returns='',asynchronous=False):
        if asynchronous:
            core='ii'
            returns='i'
        self.bind(name,'sock',f'[method]{self.protocol}-socket.{name}', [('self','(borrow $socket)'),*params],result,core,returns)
        if asynchronous:
            self.groups['sock'][2][-1]=self.groups['sock'][2][-1].replace('(func ','(func async ')
            self.async_names.add(name)

    def source(self):
        source=super().source()
        # Resource and error type aliases tie stream element identities to imports.
        needle='\n(core module $lib'
        aliases=f'\n(alias export $sock "{self.protocol}-socket" (type $socket))'
        # The completion error type is structurally identical to the WIT type.
        aliases+='\n'+F18_ERROR_TYPE.split(' (export ')[0].replace('$error-def','$socket-error')
        return source.replace('(type $accepted', aliases+'\n(type $accepted',1) if self.protocol=='tcp' else source

    def status(self,ptr):
        self.emit(ptr,1)
        self.body.append(f'(if (i32.load8_u (i32.const {ptr})) (then (call $emit (i32.const {ptr+4}) (i32.const 1))))')

    def create(self,family):
        p=self.result('create',family)
        self.status(p)
        return f16_load(p+4)

    def address_call(self,name,handle,address):
        if name in self.async_names:
            p=self.alloc(bytes(4)+f18_address_bytes(address))
            self.body.append(f'(i32.store (i32.const {p}) {handle})')
            ret=self.async_result(name,p)
        else:
            ret=self.result(name,handle,*f18_flat(address))
        self.status(ret)
        return ret

    def endpoint(self,name,handle):
        p=self.result(name,handle,size=40)
        self.status(p)
        self.emit(p+4,32)

    def udp_send(self,handle,data,address=None):
        p=self.alloc(data)
        args=self.alloc(struct.pack('<III',0,p,len(data)) + bytes([address is not None,0,0,0]) + (f18_address_bytes(address) if address is not None else bytes(32)))
        self.body.append(f'(i32.store (i32.const {args}) {handle})')
        self.status(self.async_result('send',args))

    def udp_receive(self,handle):
        p=self.async_result('receive',handle,size=48)
        self.status(p)
        self.emit(p+8,4)
        self.emit(f16_load(p+4),f16_load(p+8))
        self.emit(p+12,32)

    def tcp_exchange(self,handle,data,receive_size):
        p=self.alloc(data)
        pair=self.alloc(bytes(8))
        self.body += [f'(i64.store (i32.const {pair}) (call $outnew))']
        future=self.alloc(bytes(4))
        self.body.append(f'(i32.store (i32.const {future}) (call $send {handle} {f16_load(pair)}))')
        # Copy completion counts are observed; chunks are not presumed atomic.
        self.copy_all('outwrite',f16_load(pair+4),p,len(data))
        self.body.append(f'(call $outdrop {f16_load(pair+4)})')
        done=self.alloc(bytes(16))
        f17_completed_copy(self,'done',f16_load(future),done)
        self.status(done)
        streams=self.result('receive',handle,size=8)
        target=self.alloc(bytes(receive_size+1)); state=self.alloc(bytes(12))
        self.body.append(('stream-all','netread',f16_load(streams),target,receive_size+1,state))
        self.emit(state,8); self.emit(target,f16_load(state))
        f17_completed_copy(self,'done',f16_load(streams+4),done)
        self.status(done)

    def copy_all(self,name,handle,ptr,count):
        # One-byte transfers avoid any assumption about TCP packet boundaries or
        # stream capacity, while every byte and completion remains observable.
        for i in range(count):
            f17_completed_copy(self,name,handle,ptr+i,1)


class F18Reader:
    def __init__(self,observed):
        self.data=observed if isinstance(observed,bytes) else bytes(f16_success(observed)); self.pos=0
    def take(self,n):
        assert self.pos+n <= len(self.data), (self.pos,n,self.data)
        value=self.data[self.pos:self.pos+n]; self.pos+=n
        return value
    def u32(self): return struct.unpack('<I',self.take(4))[0]
    def status(self,error=None):
        tag=self.take(1)[0]
        assert tag == (error is not None), (tag,error,self.data)
        if error is not None:
            actual = self.take(1)[0]
            assert actual in (error if isinstance(error, tuple) else (error,)), (actual, error)
    def endpoint(self):
        d=self.take(32); family=d[0]
        assert family in (0,1)
        port=struct.unpack_from('<H',d,4)[0]
        raw=d[6:10] if family==0 else struct.pack('!8H',*struct.unpack_from('<8H',d,12))
        return str(ipaddress.ip_address(raw)),port
    def end(self): assert self.pos==len(self.data), self.data[self.pos:]
    def copies(self,n):
        for _ in range(n): assert self.u32()==16
    def closed_content(self,expected):
        count,code=self.u32(),self.u32()
        assert count==len(expected) and code & 15==1, (count,code)
        assert self.take(count)==expected


@contextmanager
def f18_peer(family,kind=socket.SOCK_STREAM):
    with socket.socket(family,kind) as s:
        s.settimeout(12)
        s.bind(('127.0.0.1' if family==socket.AF_INET else '::1',0))
        if kind==socket.SOCK_STREAM: s.listen(1)
        yield s


@contextmanager
def f18_worker(function):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(function)
        try:
            yield future
        except Exception as original:
            try:
                future.result(timeout=15)
            except Exception as peer_error:
                raise ExceptionGroup('Guest and peer observations failed', [original,peer_error])
            raise
        else:
            future.result(timeout=15)


def f18_recv_exact(peer,n):
    result=bytearray()
    while len(result)<n:
        chunk=peer.recv(n-len(result))
        assert chunk, (len(result),n)
        result.extend(chunk)
    return bytes(result)

F18_P2_ERRORS='unknown access-denied not-supported invalid-argument out-of-memory timeout concurrency-conflict not-in-progress would-block invalid-state new-socket-limit address-not-bindable address-in-use remote-unreachable connection-refused connection-reset connection-aborted datagram-too-large name-unresolvable temporary-resolver-failure permanent-resolver-failure'

class F18P2Guest(F16Guest):
    def __init__(self):
        super().__init__()
        self.add('network','wasi:sockets/network','(export "network" (type $network (sub resource)))')
        self.add('instance','wasi:sockets/instance-network','(alias outer 1 $network (type $n)) (export "network" (type $network (eq $n)))')
        self.bind('network','instance','instance-network',[],'(own $network)','','i')
        self.add('poll','wasi:io/poll','(export "pollable" (type $pollable (sub resource)))')
        self.bind('block','poll','[method]pollable.block',[('self','(borrow $pollable)')],None,'i')
        self.add('tcp','wasi:sockets/tcp', F18_TYPES+'(type $error-def (enum '+ ' '.join('"'+x+'"' for x in F18_P2_ERRORS.split())+''')) (export "error-code" (type $error (eq $error-def)))
(export "tcp-socket" (type $socket (sub resource)))
(alias outer 1 $network (type $n)) (export "network" (type $network (eq $n)))
(alias outer 1 $ins (type $in)) (export "input-stream" (type $input (eq $in)))
(alias outer 1 $os (type $out)) (export "output-stream" (type $output (eq $out)))
(alias outer 1 $pollable (type $p)) (export "pollable" (type $pollable (eq $p)))''')
        self.add('create','wasi:sockets/tcp-create-socket','''(alias outer 1 $socket (type $s))
(export "tcp-socket" (type $socket (eq $s))) (type $family-def (enum "ipv4" "ipv6")) (export "ip-address-family" (type $family (eq $family-def)))
(type $error-def (enum '''+' '.join('"'+x+'"' for x in F18_P2_ERRORS.split())+')) (export "error-code" (type $error (eq $error-def)))')
        self.bind('create','create','create-tcp-socket',[('family','$family')],'(result (own $socket) (error $error))','ii')
        for op in ('start-bind','start-connect'):
            self.bind(op,'tcp','[method]tcp-socket.'+op,[('self','(borrow $socket)'),('network','(borrow $network)'),('address','$addr')],'(result (error $error))','i'*15)
        for op in ('finish-bind','start-listen','finish-listen'):
            self.bind(op,'tcp','[method]tcp-socket.'+op,[('self','(borrow $socket)')],'(result (error $error))','ii')
        for op in ('local-address','remote-address'):
            self.bind(op,'tcp','[method]tcp-socket.'+op,[('self','(borrow $socket)')],'(result $addr (error $error))','ii')
        self.bind('is-listening','tcp','[method]tcp-socket.is-listening',[('self','(borrow $socket)')],'bool','i','i')
        self.bind('subscribe','tcp','[method]tcp-socket.subscribe',[('self','(borrow $socket)')],'(own $pollable)','i','i')
        self.bind('finish-connect','tcp','[method]tcp-socket.finish-connect',[('self','(borrow $socket)')],'(result (tuple (own $input) (own $output)) (error $error))','ii')
        self.bind('accept','tcp','[method]tcp-socket.accept',[('self','(borrow $socket)')],'(result (tuple (own $socket) (own $input) (own $output)) (error $error))','ii')

    def source(self):
        source=super().source()
        source=source.replace('(import "wasi:sockets/instance-network', '(alias export $network "network" (type $network))\n(import "wasi:sockets/instance-network')
        source=source.replace('(import "wasi:sockets/tcp-create-socket', '(alias export $tcp "tcp-socket" (type $socket))\n(import "wasi:sockets/tcp-create-socket')
        return source

    def status(self,ptr,error_offset=1):
        self.emit(ptr,1)
        self.body.append(f'(if (i32.load8_u (i32.const {ptr})) (then (call $emit (i32.const {ptr+error_offset}) (i32.const 1))))')

    def create(self,family):
        p=self.result('create',family); self.status(p,4); return f16_load(p+4)

    def address_call(self,name,handle,address):
        p=self.result(name,handle,'(call $network)',*f18_flat(address)); self.status(p); return p

    def endpoint(self,name,handle):
        p=self.result(name,handle,size=40); self.status(p,4); self.emit(p+4,32)

    record = F17Guest.record

    def complete(self,name,handle,size=32):
        """Wait through the standard pending outcome of a completion operation."""
        assert name in ('finish-bind','finish-listen','finish-connect','accept')
        error_offset=4 if name in ('finish-connect','accept') else 1
        self.body.append('(loop $socket-completion')
        result=self.result(name,handle,size=size)
        self.body.append(f'''(if (i32.and (i32.load8_u (i32.const {result}))
          (i32.eq (i32.load8_u (i32.const {result+error_offset})) (i32.const 8))) (then
          {self.call('block',self.call('subscribe',handle))}
          (br $socket-completion))))''')
        return result

    def exchange(self,input_handle,output_handle,data,size):
        p=self.alloc(data); result=self.result('writeout',output_handle,p,len(data)); self.status(result,4)
        # A blocking read may return a short list; request one byte and expose
        # both the result variant and the returned list length for every read.
        for _ in range(size):
            ret=self.result('readin',input_handle,1)
            self.status(ret,4); self.emit(ret+8,4); self.emit(f16_load(ret+4),f16_load(ret+8))
        ret=self.result('readin',input_handle,1); self.status(ret,4)


def f18_p2_exchange(driver,listener):
    """Exercise preview2 with a live peer and the listener's actual endpoint."""
    driver.program()
    for family in (socket.AF_INET,socket.AF_INET6):
        with f18_peer(family) as server:
            host=server.getsockname()[0]
            g=F18P2Guest(); h=g.create(int(family==socket.AF_INET6))
            if listener:
                g.record(g.call('is-listening',h))
                g.address_call('start-bind',h,(host,0))
                g.status(g.complete('finish-bind',h))
                g.status(g.result('start-listen',h))
                g.status(g.complete('finish-listen',h))
                g.record(g.call('is-listening',h))
                g.endpoint('local-address',h)
                result=g.complete('accept',h); g.status(result,4)
                h=f16_load(result+4); input_handle=f16_load(result+8); output_handle=f16_load(result+12)
            else:
                g.address_call('start-connect',h,server.getsockname())
                result=g.complete('finish-connect',h); g.status(result,4)
                input_handle=f16_load(result+4); output_handle=f16_load(result+8)
            g.endpoint('local-address',h); g.endpoint('remote-address',h)
            sent=b'p2\x00\xff-send'; incoming=b'reply\xff\x01'
            g.exchange(input_handle,output_handle,sent,len(incoming))
            source=g.source()
            def transfer(prefix=None):
                if listener:
                    ready=F18Reader(prefix)
                    ready.status(); assert ready.u32()==0
                    for _ in range(4): ready.status()
                    assert ready.u32()==1; ready.status()
                    address=ready.endpoint(); ready.end()
                    assert address[0]==host and 0<address[1]<=65535
                    peer=socket.socket(family,socket.SOCK_STREAM)
                    peer.settimeout(12)
                    try: peer.connect(address)
                    except BaseException: peer.close(); raise
                else:
                    address=None
                    peer,_=server.accept(); peer.settimeout(12)
                with peer:
                    local=peer.getsockname()[:2]; remote=peer.getpeername()[:2]
                    got=f18_recv_exact(peer,len(sent))
                    peer.sendall(incoming); peer.shutdown(socket.SHUT_WR)
                    return got,local,remote,address
            if listener:
                observed,peer_result=driver.interact(source,46,transfer)
                r=F18Reader(observed)
            else:
                with f18_worker(transfer) as task:
                    r=F18Reader(driver.observe(source)); peer_result=task.result(timeout=15)
            got,peer_local,peer_remote,address=peer_result
            r.status()
            if listener:
                assert r.u32()==0
                for _ in range(4): r.status()
                assert r.u32()==1; r.status(); assert r.endpoint()==address
                r.status()
            else: r.status(); r.status()
            r.status(); assert r.endpoint()==peer_remote
            r.status(); assert r.endpoint()==peer_local
            r.status()
            received=bytearray()
            for _ in incoming:
                r.status(); assert r.u32()==1; received.extend(r.take(1))
            r.status(1); r.end()
            assert bytes(received)==incoming and got==sent

from F17_helpers import F17Driver
from F16_helpers import F16_ZIG
from _helpers import parse_json, trace_consumer_execution
import json
import os
import selectors
import subprocess
import time
import pytest

class F18StreamingDriver(F17Driver):
    """Public consumer exposing guest stdout while a socket guest is running."""
    consumer_name = "F18_streaming"
    program_source = (F16_ZIG.replace('runWasiP2Main','runWasiP3Main')
        .replace('extern fn printf([*:0]const u8, ...) c_int;',
                 'extern fn fprintf(?*anyopaque, [*:0]const u8, ...) c_int;\nextern var stderr: ?*anyopaque;')
        .replace('host.stdout_buffer = &out;', '')
        .replace('_ = printf("%.*s",','_ = fprintf(stderr, "%.*s",'))

    @trace_consumer_execution
    def interact(self,source,ready_bytes,peer):
        path=self.guest(source); request=path.with_suffix('.json'); request.write_text('{}')
        child=subprocess.Popen([self.program(),path,request],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        prefix=bytearray(); deadline=time.monotonic()+15
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout,selectors.EVENT_READ)
                while len(prefix)<ready_bytes:
                    remaining=deadline-time.monotonic()
                    assert remaining>0 and selector.select(remaining), 'Guest readiness output timed out'
                    data=os.read(child.stdout.fileno(),ready_bytes-len(prefix))
                    assert data, 'Guest exited before its readiness output'
                    prefix.extend(data)
            with f18_worker(lambda: peer(bytes(prefix))) as future:
                stdout,stderr=child.communicate(timeout=15)
                peer_result=future.result(timeout=15)
            assert child.returncode==0, stderr
            result=parse_json(stderr)
            result['stdout']=bytes(prefix)+stdout
            return result,peer_result
        finally:
            if child.poll() is None: child.kill()
            child.communicate(timeout=5)

@pytest.fixture(scope='session')
def f18_streaming_driver(f01_driver,tmp_path_factory):
    return F18StreamingDriver(f01_driver,tmp_path_factory.mktemp('f18-streaming'))

from _helpers import run_json_adapter
import sys


def f18_host_resolve(names):
    """Bounded independent host-resolver observation; errors stay classified."""
    source='''import json,socket,sys
answers=[]
for name in json.loads(sys.argv[1]):
 try:
  addresses=socket.getaddrinfo(name,None,type=socket.SOCK_STREAM)
  answers.append({'addresses':[a[4][0] for a in addresses], 'error':None})
 except socket.gaierror as exc:
  answers.append({'addresses':None, 'error':exc.errno})
print(json.dumps(answers))
'''
    return run_json_adapter([sys.executable,'-c',source,json.dumps(names)],timeout=20).value


def f18_p2_operation(guest,steps):
    """Expose the first failure, or final result, of a staged WASI operation.

    A conforming host can report failure at initiation or completion. Every
    invoked result is inspected, and no unsuccessful result is discarded.
    """
    guest.body.append('(block $operation')
    for index,(name,args,error_offset) in enumerate(steps):
        result=(guest.complete(name,*args) if name in ('finish-bind','finish-connect','finish-listen')
                else guest.result(name,*args))
        if index < len(steps)-1:
            guest.body.append(f'(if (i32.load8_u (i32.const {result})) (then')
            guest.status(result,error_offset)
            guest.body.append('(br $operation)))')
        else:
            guest.status(result,error_offset)
    guest.body.append(')')


class F18P2StreamingDriver(F18StreamingDriver):
    consumer_name = "F18_p2_streaming"
    program_source = F18StreamingDriver.program_source.replace('runWasiP3Main','runWasiP2Main')


@pytest.fixture(scope='session')
def f18_p2_streaming_driver(f01_driver,tmp_path_factory):
    return F18P2StreamingDriver(f01_driver,tmp_path_factory.mktemp('f18-p2-streaming'))


def consumer_sources():
    return {driver.consumer_name: (driver.program_source, '/* Public streaming consumer. */\n', ('v3_0',))
            for driver in (F18StreamingDriver, F18P2StreamingDriver)}
