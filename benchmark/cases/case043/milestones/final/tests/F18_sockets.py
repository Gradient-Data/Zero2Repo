# feature: F18
"""Acceptance of socket effects through real WASI components and OS peers."""
import ipaddress
import socket
import struct
from pathlib import Path
from collections import Counter
from F01_helpers import f01_driver
from F16_helpers import f16_driver, f16_load
from F17_helpers import f17_driver, f17_completed_copy
from F18_helpers import (F18Guest,F18Reader,F18_TYPES,f18_peer,f18_worker,f18_recv_exact,f18_p2_exchange,F18P2Guest,f18_streaming_driver,f18_host_resolve,f18_p2_operation,f18_flat,f18_p2_streaming_driver)


# F18.T01: FP-18.01, FP-18.02, FP-18.03, FP-18.05
def test_tcp_client_exchange(f17_driver,f16_driver):
    f17_driver.program()
    for family in (socket.AF_INET,socket.AF_INET6):
        with f18_peer(family) as server:
            sent=b'out\x00\xff7'; incoming=b'in\xff\x001234'
            g=F18Guest(); h=g.create(int(family==socket.AF_INET6))
            g.record(g.call('get-address-family',h))
            g.address_call('bind',h,(server.getsockname()[0],0))
            g.endpoint('get-local-address',h)
            g.address_call('connect',h,server.getsockname())
            g.endpoint('get-local-address',h); g.endpoint('get-remote-address',h)
            g.tcp_exchange(h,sent,len(incoming))
            def serve():
                peer,addr=server.accept()
                with peer:
                    peer.settimeout(12)
                    data=f18_recv_exact(peer,len(sent))
                    peer.sendall(incoming[:3]); peer.sendall(incoming[3:])
                    peer.shutdown(socket.SHUT_WR)
                    return data,addr[:2]
            with f18_worker(serve) as task:
                r=F18Reader(f17_driver.observe(g.source()))
                observed,remote=task.result(timeout=15)
            r.status(); assert r.u32()==int(family==socket.AF_INET6)
            r.status(); r.status(); local=r.endpoint()
            assert local[0]==server.getsockname()[0] and 0<local[1]<=65535
            r.status(); r.status(); assert r.endpoint()==local==remote
            r.status(); assert r.endpoint()==server.getsockname()[:2]
            r.copies(len(sent)); assert r.u32()==0; r.status()
            r.closed_content(incoming)
            assert r.u32()==0; r.status(); r.end()
            assert observed==sent

    f18_p2_exchange(f16_driver,False)

# F18.T02: FP-18.01, FP-18.02, FP-18.03, FP-18.05
def test_tcp_listener_exchange(f18_streaming_driver,f16_driver,f18_p2_streaming_driver):
    driver=f18_streaming_driver; driver.program()
    for family in (socket.AF_INET,socket.AF_INET6):
        host='127.0.0.1' if family==socket.AF_INET else '::1'
        g=F18Guest(); h=g.create(int(family==socket.AF_INET6))
        g.record(g.call('get-is-listening',h))
        g.address_call('bind',h,(host,0))
        result=g.result('listen',h); g.status(result)
        g.record(g.call('get-is-listening',h)); g.endpoint('get-local-address',h)
        accepted=g.alloc(bytes(4))
        f17_completed_copy(g,'acceptread',f16_load(result+4),accepted,1)
        child=f16_load(accepted)
        g.endpoint('get-local-address',child); g.endpoint('get-remote-address',child)
        sent=b'accepted\x00\xfe'; incoming=b'client\x01\xff'
        g.tcp_exchange(child,sent,len(incoming))
        def connect(prefix):
            ready=F18Reader(prefix)
            ready.status(); assert ready.u32()==0; ready.status(); ready.status()
            assert ready.u32()==1; ready.status(); address=ready.endpoint(); ready.end()
            assert address[0]==host and 0<address[1]<=65535
            with socket.socket(family,socket.SOCK_STREAM) as peer:
                peer.settimeout(12); peer.connect(address)
                peer.sendall(incoming); peer.shutdown(socket.SHUT_WR)
                return f18_recv_exact(peer,len(sent)),peer.getsockname()[:2],address
        observed,(received,remote,address)=driver.interact(g.source(),44,connect)
        r=F18Reader(observed)
        r.status(); assert r.u32()==0; r.status(); r.status()
        assert r.u32()==1; r.status(); assert r.endpoint()==address
        r.copies(1); r.status(); assert r.endpoint()==address
        r.status(); assert r.endpoint()==remote
        r.copies(len(sent)); assert r.u32()==0; r.status()
        r.closed_content(incoming)
        assert r.u32()==0; r.status(); r.end()
        assert received==sent
    f18_p2_exchange(f18_p2_streaming_driver,True)
    # Port zero asks the OS to choose a concrete port; the listener query must
    # expose that endpoint rather than echoing the unresolved bind request.
    g=F18P2Guest(); h=g.create(0)
    g.address_call('start-bind',h,('127.0.0.1',0))
    g.status(g.complete('finish-bind',h))
    g.status(g.result('start-listen',h))
    g.status(g.complete('finish-listen',h))
    g.endpoint('local-address',h)
    r=F18Reader(f16_driver.observe(g.source()))
    for _ in range(6): r.status()
    address=r.endpoint(); r.end()
    assert address[0]=='127.0.0.1' and 0<address[1]<=65535


# F18.T03: FP-18.01, FP-18.04, FP-18.05
def test_udp_datagrams_and_peer_removal(f17_driver):
    f17_driver.program()
    for family in (socket.AF_INET,socket.AF_INET6):
        with f18_peer(family,socket.SOCK_DGRAM) as peer:
            g=F18Guest('udp'); h=g.create(int(family==socket.AF_INET6))
            g.record(g.call('get-address-family',h))
            g.address_call('bind',h,(peer.getsockname()[0],0))
            g.endpoint('get-local-address',h)
            g.address_call('connect',h,peer.getsockname())
            g.endpoint('get-remote-address',h)
            outgoing=[b'first\x00\xff',bytes((i * 37) % 256 for i in range(4097))]; incoming=[b'other\x01',b'\x00\xfflonger']
            for data in outgoing: g.udp_send(h,data)
            for _ in incoming: g.udp_receive(h)
            g.status(g.result('disconnect',h))
            g.status(g.result('get-remote-address',h,size=40))
            g.udp_send(h,b'after',peer.getsockname())
            def exchange():
                received=[]; addresses=[]
                for _ in outgoing:
                    data,addr=peer.recvfrom(65536); received.append(data); addresses.append(addr[:2])
                for data in incoming: peer.sendto(data,addresses[0])
                data,addr=peer.recvfrom(65536); received.append(data); addresses.append(addr[:2])
                return received,addresses
            with f18_worker(exchange) as task:
                r=F18Reader(f17_driver.observe(g.source())); received,addresses=task.result(timeout=15)
            r.status(); assert r.u32()==int(family==socket.AF_INET6)
            r.status(); r.status(); local=r.endpoint()
            assert all(a==local for a in addresses)
            r.status(); r.status(); assert r.endpoint()==peer.getsockname()[:2]
            for _ in outgoing: r.status()
            delivered=[]
            for _ in incoming:
                r.status(); delivered.append(r.take(r.u32()))
                assert r.endpoint()==peer.getsockname()[:2]
            r.status(); r.status(5); r.status(); r.end()
            # UDP preserves whole datagrams, but does not promise arrival order.
            assert Counter(delivered)==Counter(incoming)
            assert Counter(received)==Counter(outgoing+[b'after'])

        # A datagram socket may acquire its local endpoint as part of connect.
        with f18_peer(family, socket.SOCK_DGRAM) as peer:
            g = F18Guest('udp'); h = g.create(int(family == socket.AF_INET6))
            g.address_call('connect', h, peer.getsockname())
            g.endpoint('get-local-address', h)
            g.udp_send(h, b'auto-bound')
            with f18_worker(lambda: peer.recvfrom(128)) as task:
                r = F18Reader(f17_driver.observe(g.source()))
                payload, source = task.result(timeout=15)
            r.status(); r.status(); r.status(); local = r.endpoint(); r.status(); r.end()
            assert local[1] != 0 and payload == b'auto-bound'
            assert source[1] == local[1]


# F18.T04: FP-18.06, FP-18.08
def test_name_resolution(f17_driver):
    # Use real configured loopback aliases of either address family. IPv6
    # aliases are part of the case image's OS configuration; the runtime
    # hostname need not itself be resolvable. Native lookup is the control.
    aliases=set()
    for line in Path('/etc/hosts').read_text().splitlines():
        fields=line.split('#',1)[0].split()
        if not fields:
            continue
        if ipaddress.ip_address(fields[0]).is_loopback:
            aliases.update(name for name in fields[1:] if name.lower() != 'localhost')
    assert aliases, 'The case environment needs a configured non-localhost loopback hostname'
    names=['192.0.2.37','2001:db8::19','localhost',*sorted(aliases)]
    g=F18Guest('udp')
    g.add('lookup','wasi:sockets/ip-name-lookup',F18_TYPES+'''(type $error-def (variant
     (case "access-denied") (case "invalid-name") (case "name-unresolvable")
     (case "temporary-resolver-failure") (case "permanent-resolver-failure") (case "other" (option string)))) (export "error-code" (type $error (eq $error-def)))''')
    g.bind('resolve','lookup','resolve-addresses',[('name','string')], '(result (list $ip) (error $error))','iii','i')
    g.groups['lookup'][2][-1]=g.groups['lookup'][2][-1].replace('(func ','(func async ')
    g.async_names.add('resolve')
    missing='unresolvable-f18.invalid.'
    answers=f18_host_resolve(names+[missing])
    assert all(a['error'] is None for a in answers[:-1]), answers
    assert answers[-1]['error'] is not None, answers[-1]
    expected=[{str(ipaddress.ip_address(x)) for x in a['addresses']} for a in answers[:-1]]
    for name in names+['invalid name',missing]:
        p=g.alloc(name.encode()); result=g.async_result('resolve',p,len(name))
        g.status(result)
        if name in names:
            g.emit(result+8,4); g.emit(f16_load(result+4),f'(i32.mul {f16_load(result+8)} (i32.const 18))')
    r=F18Reader(f17_driver.observe(g.source()))
    for name,allowed in zip(names,expected):
        r.status(); count=r.u32(); assert count>0
        observed=set()
        for _ in range(count):
            data=r.take(18); assert data[0] in (0,1)
            raw=data[2:6] if data[0]==0 else struct.pack('!8H',*struct.unpack_from('<8H',data,2))
            observed.add(str(ipaddress.ip_address(raw)))
        assert observed <= allowed
        if name in names[:2]: assert observed=={str(ipaddress.ip_address(name))}
    r.status(1)
    assert r.take(1)==b'\x01'
    assert r.take(1)[0] in (2,3,4,5)
    r.end()


# F18.T05: FP-18.07, FP-18.08
def test_socket_failures(f17_driver,f16_driver):
    with f18_peer(socket.AF_INET) as occupied, socket.socket() as closed:
        closed.bind(('127.0.0.1',0))
        closed_address=closed.getsockname()
        # A bound non-listening TCP socket reliably refuses local connections.
        g=F18Guest(); a=g.create(0)
        g.address_call('bind',a,('127.0.0.1',0)); g.endpoint('get-local-address',a)
        g.address_call('connect',a,occupied.getsockname())
        b=g.create(0); g.address_call('connect',b,closed_address)
        c=g.create(0); g.address_call('bind',c,occupied.getsockname())
        d=g.create(0); g.status(g.result('get-remote-address',d,size=40))
        e=g.create(0); g.address_call('bind',e,('::1',0))
        f=g.create(0); g.address_call('connect',f,('0.0.0.0',0))
        r=F18Reader(f17_driver.observe(g.source()))
        accepted,_=occupied.accept(); accepted.close()
        r.status(); r.status(); r.status(); endpoint=r.endpoint()
        assert endpoint[0]=='127.0.0.1' and 0<endpoint[1]<=65535
        r.status()
        r.status(); r.status(9); r.status(); r.status(7)
        r.status(); r.status(5); r.status(); r.status(2); r.status(); r.status(2); r.end()
        g=F18Guest('udp'); h=g.create(0)
        g.status(g.async_result('receive',h,size=48))
        g.status(g.result('get-remote-address',h,size=40))
        g.address_call('bind',h,('::1',0))
        g.address_call('connect',h,('0.0.0.0',0))
        g.address_call('bind',h,('127.0.0.1',0))
        r=F18Reader(f17_driver.observe(g.source()))
        r.status(); r.status(5); r.status(5); r.status(2); r.status(2); r.status(); r.end()

        g=F18P2Guest(); ready=g.create(0)
        f18_p2_operation(g,[
            ('start-connect',(ready,'(call $network)',*f18_flat(occupied.getsockname())),1),
            ('finish-connect',(ready,),4)])
        h=g.create(0)
        g.status(g.result('accept',h),4)
        g.status(g.result('remote-address',h,size=40),4)
        f18_p2_operation(g,[
            ('start-bind',(h,'(call $network)',*f18_flat(('::1',0))),1),
            ('finish-bind',(h,),1)])
        f18_p2_operation(g,[
            ('start-connect',(h,'(call $network)',*f18_flat(closed_address)),1),
            ('finish-connect',(h,),4)])
        h=g.create(0)
        f18_p2_operation(g,[
            ('start-bind',(h,'(call $network)',*f18_flat(occupied.getsockname())),1),
            ('finish-bind',(h,),1),('start-listen',(h,),1),('finish-listen',(h,),1)])
        r=F18Reader(f16_driver.observe(g.source()))
        accepted,_=occupied.accept(); accepted.close()
        r.status(); r.status()
        r.status(); r.status((0,9)); r.status((0,9)); r.status(3)
        r.status(14); r.status(); r.status(12); r.end()
