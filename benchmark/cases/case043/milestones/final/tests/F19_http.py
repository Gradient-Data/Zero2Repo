# feature: F19
"""HTTP resource and exchange acceptance through WASI 0.3 imports."""
import socket
from F01_helpers import f01_driver
from F17_helpers import f17_driver
from F16_helpers import f16_load
from F18_helpers import f18_peer, f18_worker
from F19_helpers import (F19Guest, F19Reader, F19_METHODS, F19_TIMEOUTS,
                         f19_immutable_probe, f19_immutable_check, f19_http_exchange)


def test_headers_order_mutation_and_copies(f17_driver):
    """F19.T01: FP-19.01, FP-19.02, FP-19.03, FP-19.04."""
    g=F19Guest()
    fresh=g.fields(); g.lookup(fresh,'absent')
    g.change('append',fresh,'X-Run',b'first'); g.lookup(fresh,'x-RUN')
    h=g.fields([('X-Repeat',b'one'),('Unrelated',b'keep'),('x-repeat',b'two')])
    g.lookup(h,'X-REPEAT'); g.lookup(h,'missing')
    copy=g.handle('clone',h); g.lookup(copy,'x-repeat')
    g.change('set',copy,'X-RePeAt',[b'replaced',b'ordered'])
    g.change('append',copy,'x-repeat',b'last'); g.lookup(copy,'X-REPEAT')
    g.lookup(h,'x-repeat'); g.lookup(copy,'unrelated')
    g.change('get-and-delete',copy,'x-REPEAT')
    for name in ('X-Repeat','x-repeat','X-REPEAT'): g.lookup(copy,name)
    g.lookup(copy,'UNRELATED')
    g.change('delete',h,'x-RePeAt')
    for name in ('X-Repeat','x-repeat','X-REPEAT'): g.lookup(h,name)
    g.lookup(h,'unrelated')
    g.change('set',fresh,'x-run',[b'new']); g.lookup(fresh,'X-RUN')
    g.change('set',fresh,'x-run',[]); g.lookup(fresh,'X-Run')
    r=F19Reader(f17_driver.observe(g.source()))
    r.lookup([]); r.status(); r.lookup([b'first']); r.status()
    r.lookup([b'one',b'two']); r.lookup([]); r.lookup([b'one',b'two'])
    r.status(); r.status(); r.lookup([b'replaced',b'ordered',b'last'])
    r.lookup([b'one',b'two']); r.lookup([b'keep'])
    r.status(); assert r.values()==[b'replaced',b'ordered',b'last']
    for _ in range(3): r.lookup([])
    r.lookup([b'keep']); r.status()
    for _ in range(3): r.lookup([])
    r.lookup([b'keep']); r.status(); r.lookup([b'new']); r.status(); r.lookup([]); r.end()


def test_header_rfc_alphabets(f17_driver):
    """F19.T02: FP-19.10; RFC 9110 sections 5.1, 5.5 and 5.6.2."""
    # RFC 9110 sections 5.1 and 5.5: token punctuation, visible ASCII,
    # interior HTAB/SP and obs-text; no requirement on edge whitespace.
    token="Az09!#$%&'*+-.^_`|~"
    value=b'A\t B!~\x80\xffZ'
    invalid_names=['','bad name','bad:name','bad\tname','bad\x7fname','bad\x01name','bad/name','bad(name)','caf\u00e9']
    invalid_values=[b'a\x00b',b'a\x01b',b'a\nb',b'a\rb',b'a\x7fb']
    g=F19Guest(); h=g.fields([(token,value)]); g.lookup(h,token.swapcase())
    g.change('set',h,token,[b'new',value]); g.lookup(h,token)
    g.change('append',h,token,b'next'); g.lookup(h,token)
    for name in invalid_names:
        g.fields([(name,b'value')])
        g.change('set',h,name,[b'value']); g.change('append',h,name,b'value')
    for bad in invalid_values:
        g.fields([('Valid',bad)])
        g.change('set',h,token,[b'valid-first',bad]); g.change('append',h,token,bad)
        g.lookup(h,token)
    r=F19Reader(f17_driver.observe(g.source()))
    for expected in ([value], [b'new', value], [b'new', value, b'next']):
        assert r.take(1) == b'\x00'  # result.ok
        assert r.u32() == 1  # fields.has
        assert r.values() == expected
    for _ in invalid_names:
        for _ in range(3):
            assert r.take(2) == b'\x01\x00'  # result.err(invalid-syntax)
    for _ in invalid_values:
        for _ in range(3):
            assert r.take(2) == b'\x01\x00'
        assert r.u32() == 1
        assert r.values() == [b'new', value, b'next']
    r.end()


def test_request_response_metadata_and_bodies(f17_driver,tmp_path):
    """F19.T03: FP-19.05, FP-19.06, FP-19.13, FP-19.14."""
    g=F19Guest(); req,_=g.resource('request')
    methods=list(F19_METHODS)+["X-Sync!#$%&'*+-.^_`|~",'lowercase']
    for method in methods: g.assign(req,'method',method); g.metadata(req,'method')
    bad_methods=['','BAD METHOD','GET\n','GET/','m\u00e9thod']
    for method in bad_methods: g.assign(req,'method',method); g.metadata(req,'method')
    schemes=['http','https','git+ssh','A9.-x',None,'https']
    for scheme in schemes: g.assign(req,'scheme',scheme); g.metadata(req,'scheme')
    bad_schemes=['','1http','a b','a:','a/','\u00e9']
    for scheme in bad_schemes: g.assign(req,'scheme',scheme); g.metadata(req,'scheme')
    authorities=['example.test:8123','localhost',None,'example.test:80']
    for value in authorities: g.assign(req,'authority',value); g.metadata(req,'authority')
    for value in ['', 'example.test:', 'example.test:ab', 'example.test:8x']:
        g.assign(req,'authority',value)
    paths=['/first?a=1&b=%20','/next','',None,'/final?q=ok']
    for path in paths: g.assign(req,'path-with-query',path); g.metadata(req,'path-with-query')
    for path in ['/a b','/?q=a b','/\x00','/\t','/\r','/\n','/\x7f']:
        g.assign(req,'path-with-query',path)
    resp,_=g.resource('response')
    statuses=[100,201,418,599,204]
    for status in statuses: g.assign(resp,'status',status); g.metadata(resp,'status')
    for status in [0,99,600,65535]: g.assign(resp,'status',status); g.metadata(resp,'status')
    for kind in ('request','response'):
        headers=g.fields([('X-Content',b'one'),('x-content',b'two')])
        h,_=g.resource(kind,headers=headers)
        unrelated=g.fields([('X-Content',b'unrelated')])
        g.lookup(g.handle(kind+'-headers',h),'X-CONTENT')
        g.consume(kind,h,0)
    r=F19Reader(f17_driver.observe(g.source()))
    for method in methods: assert r.u32()==0; assert r.metadata('method')==method
    for _ in bad_methods: assert r.u32()==1; assert r.metadata('method')==methods[-1]
    for scheme in schemes: assert r.u32()==0; assert r.metadata('scheme')==scheme
    for _ in bad_schemes: assert r.u32()==1; assert r.metadata('scheme')==schemes[-1]
    for value in authorities: assert r.u32()==0; assert r.metadata('authority')==value
    for _ in range(4): assert r.u32()==1
    for path in paths: assert r.u32()==0; assert r.metadata('path-with-query')==('/' if path=='' else path)
    for _ in range(7): assert r.u32()==1
    for status in statuses: assert r.u32()==0; assert r.metadata('status')==status
    for _ in range(4): assert r.u32()==1; assert r.metadata('status')==statuses[-1]
    for _ in range(2): r.status(); r.status(); r.lookup([b'one',b'two']); r.content(b'')
    r.end()
    data=b'body\x00\xff-19'
    (tmp_path/'body.bin').write_bytes(data)
    for kind in ('request','response'):
        g=F19Guest(filesystem=True)
        file=g.open('body.bin')
        g.bind('readfile','fs','[method]descriptor.read-via-stream',
               [('self','(borrow $desc)'),('offset','u64')],
               '(tuple (stream u8) (future (result (error $error))))','iqi')
        stream=g.result('readfile',file,0)
        headers=g.fields([('X-Content',b'one'),('x-content',b'two')])
        h,_=g.resource(kind,headers=headers,body=f16_load(stream))
        g.lookup(g.handle(kind+'-headers',h),'X-CONTENT')
        g.consume(kind,h,len(data))
        r=F19Reader(f17_driver.observe(g.source(),directory=str(tmp_path)))
        assert r.take(1)==b'\x00'; r.status(); r.lookup([b'one',b'two']); r.content(data); r.end()


def test_request_options_independence_and_ownership(f17_driver):
    """F19.T04: FP-19.07, FP-19.12."""
    g=F19Guest(); opts=g.handle('options-new')
    assigned=[0,2**63+123456789,2**64-8]
    expected=[]
    # Clear explicitly before observing: no incidental constructor default is pinned.
    for name in F19_TIMEOUTS: g.timeout_set(opts,name,None)
    g.timeouts(opts); expected.append([None,None,None])
    for i,(name,value) in enumerate(zip(F19_TIMEOUTS,assigned)):
        g.timeout_set(opts,name,value); g.timeouts(opts)
        expected.append(assigned[:i+1]+[None]*(2-i))
    clone=g.handle('options-clone',opts); g.timeouts(clone)
    for name in F19_TIMEOUTS: g.timeout_set(clone,name,None)
    g.timeouts(clone); g.timeouts(opts)
    req,_=g.resource('request',options=opts)
    p=g.result('get-options',req); g.emit(p,1); view=f16_load(p+4); g.timeouts(view)
    for name in F19_TIMEOUTS:
        g.timeout_set(view,name,777); g.timeouts(view)
        g.timeout_set(view,name,None); g.timeouts(view)
    independent=g.handle('options-clone',view); g.timeouts(independent)
    for i,name in enumerate(F19_TIMEOUTS): g.timeout_set(independent,name,assigned[i]+7)
    g.timeouts(independent); g.timeouts(view)
    r=F19Reader(f17_driver.observe(g.source()))
    for _ in range(3): r.status()
    assert r.timeouts()==expected[0]
    for values in expected[1:]: r.status(); assert r.timeouts()==values
    assert r.timeouts()==assigned
    for _ in range(3): r.status()
    assert r.timeouts()==[None,None,None]; assert r.timeouts()==assigned
    assert r.take(1)==b'\x01'; assert r.timeouts()==assigned
    for _ in range(6): r.status(1); assert r.timeouts()==assigned
    assert r.timeouts()==assigned
    for _ in range(3): r.status()
    assert r.timeouts()==[v+7 for v in assigned]; assert r.timeouts()==assigned; r.end()


def test_header_views_are_immutable(f17_driver):
    """F19.T05: FP-19.04, FP-19.11; guest-owned and HTTP peer header views."""
    g=F19Guest()
    for kind in ('request','response'):
        headers=g.fields([('X-Retained',b'first'),('X-Retained',b'second')])
        resource,_=g.resource(kind,headers=headers)
        view=g.handle(kind+'-headers',resource); f19_immutable_probe(g,view)
    r=F19Reader(f17_driver.observe(g.source()))
    for _ in range(2): r.status(); f19_immutable_check(r)
    r.end()
    with f18_peer(socket.AF_INET) as server:
        g=F19Guest(); g.client(); req,_=g.resource('request')
        g.assign(req,'method','POST'); g.assign(req,'scheme','http')
        g.assign(req,'authority','127.0.0.1:'+str(server.getsockname()[1]))
        g.assign(req,'path-with-query','/owned')
        response=g.send(req)
        view=g.handle('response-headers',response); f19_immutable_probe(g,view)
        g.consume('response',response,0)
        with f18_worker(lambda: f19_http_exchange(server,b'')) as task:
            r=F19Reader(f17_driver.observe(g.source())); task.result(timeout=15)
        for _ in range(4): assert r.u32()==0
        assert r.take(1)==b'\x00'; f19_immutable_check(r); r.content(b''); r.end()


def test_http_client_methods_bodies_and_failures(f17_driver):
    """F19.T06: FP-19.01, FP-19.08, FP-19.15; method gaps are in the ledger."""
    f17_driver.program()
    # Exercise the supported transport methods and independent HTTP framing forms.
    for method,framing in [('POST','length'),('PUT','chunked'),('PATCH','close')]:
        with f18_peer(socket.AF_INET) as server:
            authority='localhost:'+str(server.getsockname()[1])
            path='/items/'+method.lower()+'?q=%20&n=19'
            sent=b'guest\x00\xff-'+method.encode()
            incoming=bytes((i*29+7)%256 for i in range(10007))+method.encode()
            status=207
            g=F19Guest(); g.client()
            headers=g.fields([('X-Guest',b'alpha'),('X-Guest',b'beta')])
            req,pair=g.resource('request',headers=headers,body=bool(sent))
            for name,value in [('method',method),('scheme','http'),('authority',authority),('path-with-query',path)]: g.assign(req,name,value)
            response=g.send(req,pair,sent)
            g.metadata(response,'status')
            view=g.handle('response-headers',response); g.lookup(view,'x-retained')
            expected_body=incoming
            g.consume('response',response,len(expected_body))
            with f18_worker(lambda: f19_http_exchange(server,incoming,status,framing)) as task:
                r=F19Reader(f17_driver.observe(g.source())); wire=task.result(timeout=15)
            r.status()
            for _ in range(4): assert r.u32()==0
            r.sent(len(sent)); assert r.take(1)==b'\x00'
            assert r.metadata('status')==status
            r.lookup([b'first',b'second']); r.content(expected_body); r.end()
            assert wire=={'method':method,'target':path,
                          'authority':authority,'values':['alpha','beta'],'body':sent}
    # A bound but non-listening endpoint cannot accept a connection and cannot
    # be claimed by another process between choosing its port and the request.
    with socket.socket() as unavailable:
        unavailable.bind(('127.0.0.1',0))
        g=F19Guest(); g.client()
        failure_body=b'guest\x00\xff-POST'
        for authority in (None,'127.0.0.1:'+str(unavailable.getsockname()[1])):
            headers=g.fields([('X-Guest',b'alpha'),('X-Guest',b'beta')])
            req,pair=g.resource('request',headers=headers,body=True)
            g.assign(req,'method','POST'); g.assign(req,'scheme','http')
            g.assign(req,'authority',authority)
            g.assign(req,'path-with-query','/items/post?q=%20&n=19')
            g.send(req,pair,failure_body)
        r=F19Reader(f17_driver.observe(g.source()))
        for _ in range(2):
            r.status()
            for _ in range(4): assert r.u32()==0
            r.sent(len(failure_body),may_close=True)
            assert r.take(1)==b'\x01'  # The public failed-request result variant.
        r.end()
