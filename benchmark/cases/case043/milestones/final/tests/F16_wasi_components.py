# feature: F16
"""Seven planned public WASI 0.2 acceptance measurements."""
from collections import Counter
import math
import os
import struct
import time

from F01_helpers import f01_driver
from F08_helpers import f08_driver
from F11_helpers import f11_driver, f11_failure
from F16_helpers import f16_driver, F16Guest, f16_load, f16_success, f16_open


def test_command_context_io_and_outcomes(f16_driver, f11_driver):
    # F16.T01. Guest serializes lists as count followed by length-prefixed bytes.
    g = F16Guest()
    g.add('env', 'wasi:cli/environment')
    for name, result in [('args','(list string)'), ('env','(list (tuple string string))')]:
        g.bind(name,'env','get-arguments' if name=='args' else 'get-environment',[],result,'i')
        ret = g.result(name,size=8)
        g.emit(ret+4,4)
        stride = 8 if name=='args' else 16
        g.body.append(f'''(local.set $i (i32.const 0))
(block $done (loop $next (br_if $done (i32.ge_u (local.get $i) {f16_load(ret+4)}))
(local.set $p (i32.add {f16_load(ret)} (i32.mul (local.get $i) (i32.const {stride}))))''')
        for offset in range(0,stride,8):
            g.body.append(f'''(call $emit (i32.add (local.get $p) (i32.const {offset+4})) (i32.const 4))
(call $emit (i32.load offset={offset} (local.get $p)) (i32.load offset={offset+4} (local.get $p)))''')
        g.body.append('(local.set $i (i32.add (local.get $i) (i32.const 1))) (br $next)))')
    g.body.append('(local.set $s (call $getstdin))')
    for size in (1,)*9:
        ret = g.result('readin','(local.get $s)',size)
        g.body.append(f'(if (i32.load8_u (i32.const {ret})) (then unreachable))')
        g.emit(ret+8,4)
        g.emit(f16_load(ret+4),f16_load(ret+8))
    eof = g.result('readin','(local.get $s)',1)
    g.emit(eof,1); g.emit(eof+4,1)
    p = g.alloc(b'error-channel\x00\xff')
    g.body.append(g.call('writeout','(call $getstderr)',p,15,128))
    source = g.source()
    def decode(payload):
        pos = 0
        def integer():
            nonlocal pos
            n, = struct.unpack_from('<I',payload,pos); pos += 4
            return n
        def blob():
            nonlocal pos
            n = integer(); b = payload[pos:pos+n]; pos += n
            assert len(b)==n
            return b
        args = [blob() for _ in range(integer())]
        env = [(blob(),blob()) for _ in range(integer())]
        reads = [blob() for _ in range(9)]
        assert payload[pos:] == bytes([1, 1])  # error(stream-error.closed)
        pos += 2
        assert pos == len(payload)
        return args,env,reads
    for args,env in [(None,{}), (['command','猫','', 'two words'],{'MODE':'active','EMPTY':''})]:
        config = {'stdin':'abcdefghi','keys':list(env),'values':list(env.values())}
        if args is not None: config['args']=args
        result = f16_driver.observe(source,**config)
        got = decode(f16_success(result))
        assert got[0] == ([] if args is None else [s.encode() for s in args])
        assert dict(got[1]) == {k.encode():v.encode() for k,v in env.items()}
        assert got[2] == [bytes([b]) for b in b'abcdefghi']
        assert result['stderr'] == b'error-channel\x00\xff'
    path = f16_driver.guest(source)
    result = f11_driver.command(['run','--env','MODE=cli',path,'alpha','猫'],stdin=b'abcdefghi')
    assert result.returncode == 0, result.stderr
    args,env,reads = decode(result.stdout)
    assert args[0] in (path.name.encode(), str(path).encode())
    assert args[1:] == [b'alpha','猫'.encode()]
    assert dict(env)=={b'MODE':b'cli'}
    assert reads == [bytes([b]) for b in b'abcdefghi']
    assert result.stderr == b'error-channel\x00\xff'
    # Both result variants travel through the actual command entry.
    for status in (0,1):
        command = F16Guest(); p=command.alloc(b'ran') ; command.emit(p,3)
        source = command.source(status=status)
        observed = f16_driver.observe(source)
        assert observed['stdout']==b'ran'
        assert observed['err'] is None
        assert observed['exit_code'] in ((None, 0) if status == 0 else (1,))
        cli = f11_driver.command(['run',f16_driver.guest(source)])
        assert cli.returncode == status
        assert cli.stdout == b'ran'

    for status in (0, 1):
        command = F16Guest(); command.add('exit', 'wasi:cli/exit')
        command.bind('exit', 'exit', 'exit', [('status', '(result)')], None, 'i')
        p = command.alloc(b'beforeafter'); command.emit(p, 6)
        command.body.append(command.call('exit', status)); command.emit(p + 6, 5)
        source = command.source()
        observed = f16_driver.observe(source)
        assert observed['stdout'] == b'before' and observed['err'] is None, observed
        assert observed['exit_code'] == status, observed
        cli = f11_driver.command(['run', f16_driver.guest(source)])
        assert cli.returncode == status and cli.stdout == b'before', cli.stderr


def test_filesystem_operations_and_metadata(f16_driver, tmp_path):
    # F16.T02. All paths and data are caller inputs; no directory ordering pin.
    g = F16Guest(); g.filesystem()
    f16_open(g,'written',flags=9)
    payload=b'alpha\x00beta!'
    p=g.alloc(payload)
    write=g.alloc(bytes(32))
    g.body.append('(local.set $i (i32.const 0)) (block $done (loop $again')
    g.body.append(f'(br_if $done (i32.eq (local.get $i) (i32.const {len(payload)})))')
    g.body.append(g.call('write','(local.get $file)',f'(i32.add (i32.const {p}) (local.get $i))',
                         f'(i32.sub (i32.const {len(payload)}) (local.get $i))',
                         '(i64.extend_i32_u (i32.add (local.get $i) (i32.const 3)))',write))
    g.body.append(f'''(if (i32.load8_u (i32.const {write})) (then unreachable))
(if (i64.eqz {f16_load(write+8,'i64')}) (then unreachable))
(if (i64.gt_u {f16_load(write+8,'i64')} (i64.extend_i32_u (i32.sub (i32.const {len(payload)}) (local.get $i)))) (then unreachable))
(local.set $i (i32.add (local.get $i) (i32.wrap_i64 {f16_load(write+8,'i64')}))) (br $again)))
(i64.store (i32.const {write+8}) (i64.extend_i32_u (local.get $i)))''')
    checks=[write]
    for op in ('sync','syncdata','type'):
        ret=g.result(op,'(local.get $file)'); checks.append(ret)
        if op=='type': typ=ret
    # One-byte reads exercise offsets without requiring the host to fill a
    # multi-byte request. A separate read beyond the end establishes EOF.
    reads=[]
    for offset in range(1,3+len(payload)):
        ret=g.result('read','(local.get $file)',1,offset); checks.append(ret); reads.append(ret)
    end=g.result('read','(local.get $file)',1,3+len(payload)); checks.append(end)
    stat=g.result('stat','(local.get $file)',size=104); checks.append(stat)
    name=g.alloc(b'written')
    statat=g.result('statat','(local.get $dir)',1,name,7,size=104); checks.append(statat)
    for ret in checks: g.emit(ret,1)
    g.emit(write+8,8); g.emit(typ+1,1)
    for ret in reads:
        g.emit(ret+8,4); g.emit(f16_load(ret+4),f16_load(ret+8))
    g.emit(end+8,4); g.emit(end+12,1)
    # Canonical record fields, excluding unspecified padding.
    for ret in (stat,statat):
        g.emit(ret+8,1); g.emit(ret+24,8)
        for off in (32,56,80):
            g.emit(ret+off,1); g.emit(ret+off+8,12)
    names={s:g.alloc(s.encode()) for s in ('written','renamed','hard','sym','folder','gone')}
    operations=[('rename',names['written'],7,'(local.get $dir)',names['renamed'],7),
                ('link',1,names['renamed'],7,'(local.get $dir)',names['hard'],4),
                ('symlink',names['renamed'],7,names['sym'],3),
                ('mkdir',names['folder'],6),('mkdir',names['gone'],4),('rmdir',names['gone'],4)]
    for op,*args in operations:
        ret=g.result(op,'(local.get $dir)',*args); g.emit(ret,1)
    link=g.result('readlink','(local.get $dir)',names['sym'],3)
    g.emit(link,1); g.emit(link+8,4); g.emit(f16_load(link+4),f16_load(link+8))
    listing=g.result('listing','(local.get $dir)')
    g.emit(listing,1)
    g.body.append(f'(local.set $s {f16_load(listing+4)})')
    # Bounded enumeration: four entries plus the end marker, no unbounded probe.
    for _ in range(5):
        entry=g.result('entry','(local.get $s)')
        g.emit(entry,1); g.emit(entry+4,1)
        g.body.append(f'(if (i32.load8_u (i32.const {entry+4})) (then')
        g.emit(entry+8,1); g.emit(entry+16,4); g.emit(f16_load(entry+12),f16_load(entry+16))
        g.body.append('))')
    ret=g.result('unlink','(local.get $dir)',names['renamed'],7); g.emit(ret,1)
    result=f16_driver.observe(g.source(),directory=str(tmp_path))
    raw=f16_success(result); pos=0
    def take(n):
        nonlocal pos
        x=raw[pos:pos+n]; pos+=n; assert len(x)==n; return x
    assert take(len(checks))==bytes(len(checks))
    assert struct.unpack('<Q',take(8))[0]==len(payload)
    assert take(1)==b'\x06'
    received=bytearray()
    for _ in reads:
        size=struct.unpack('<I',take(4))[0]
        assert size==1
        received.extend(take(size))
    assert received==b'\0\0'+payload
    assert struct.unpack('<I',take(4))[0]==0
    assert take(1)==b'\x01' 
    metadata=[]
    for _ in range(2):
        kind=take(1); length=struct.unpack('<Q',take(8))[0]
        stamps=[]
        for _ in range(3):
            assert take(1)==b'\x01'
            seconds,nanos=struct.unpack('<QI',take(12)); assert nanos<1_000_000_000
            stamps.append(seconds*1_000_000_000+nanos)
        metadata.append((kind,length,stamps))
    assert metadata[0]==metadata[1]
    assert metadata[0][:2]==(b'\x06',3+len(payload))
    assert take(6)==bytes(6)
    assert take(1)==b'\0'
    size=struct.unpack('<I',take(4))[0]; assert take(size)==b'renamed'
    assert take(1)==b'\0'
    entries={}
    for _ in range(5):
        assert take(1)==b'\0'
        present=take(1)
        assert present in (b'\0',b'\1')
        if present==b'\1':
            kind=take(1)[0]; n=struct.unpack('<I',take(4))[0]; name=take(n).decode()
            assert name not in entries; entries[name]=kind
    assert entries=={'renamed':6,'hard':6,'sym':5,'folder':3}
    assert take(1)==b'\0' and pos==len(raw)
    assert {p.name for p in tmp_path.iterdir()}=={'hard','sym','folder'}
    assert (tmp_path/'hard').read_bytes()==b'\0\0\0'+payload
    assert os.readlink(tmp_path/'sym')=='renamed'
    assert (tmp_path/'folder').is_dir()

    # Opening flags and link metadata are part of this filesystem measurement.
    (tmp_path / 'truncate').write_bytes(b'old contents')
    g = F16Guest(); g.filesystem()
    f16_open(g, 'truncate', flags=8)
    stat = g.result('stat', '(local.get $file)', size=104)
    g.body.append(f'(if (i32.load8_u (i32.const {stat})) (then unreachable))')
    g.emit(stat + 24, 8)
    raw = f16_success(f16_driver.observe(g.source(), directory=str(tmp_path)))
    assert struct.unpack('<Q', raw)[0] == 0
    assert (tmp_path / 'truncate').read_bytes() == b''

    (tmp_path / 'target').write_bytes(b'x')
    os.symlink('target', tmp_path / 'link')
    h = F16Guest(); h.filesystem()
    p = h.alloc(b'link')
    followed = h.result('statat', '(local.get $dir)', 1, p, 4, size=104)
    direct = h.result('statat', '(local.get $dir)', 0, p, 4, size=104)
    for result in (followed, direct):
        h.body.append(f'(if (i32.load8_u (i32.const {result})) (then unreachable))')
    h.emit(followed + 8, 1); h.emit(direct + 8, 1)
    out = f16_success(f16_driver.observe(h.source(), directory=str(tmp_path)))
    assert out == b'\x06\x05'


def test_file_identity_across_paths_descriptors_and_links(f16_driver, tmp_path):
    # F16.T03. Equal content is intentional: identity must identify the object.
    for name in ('one','two'): (tmp_path/name).write_bytes(b'identical content')
    os.link(tmp_path/'one',tmp_path/'alias')
    g=F16Guest(); g.filesystem()
    for name in ('one','alias','two'):
        f16_open(g,name)
        ret=g.result('hash','(local.get $file)'); g.emit(ret,1); g.emit(ret+8,16)
        p=g.alloc(name.encode())
        ret=g.result('hashat','(local.get $dir)',1,p,len(name)); g.emit(ret,1); g.emit(ret+8,16)
    for op in ('stat','statat'):
        args=['(local.get $file)'] if op=='stat' else ['(local.get $dir)',1,g.alloc(b'two'),3]
        ret=g.result(op,*args,size=104); g.emit(ret,1); g.emit(ret+8,1); g.emit(ret+24,8)
        for off in (32,56,80): g.emit(ret+off,1); g.emit(ret+off+8,12)
    raw=f16_success(f16_driver.observe(g.source(),directory=str(tmp_path)))
    identities=[]
    for i in range(6):
        assert raw[17*i]==0
        identities.append(raw[17*i+1:17*i+17])
    assert identities[0]==identities[1]==identities[2]==identities[3]
    assert identities[4]==identities[5] and identities[0]!=identities[4]
    a,b=raw[102:151],raw[151:200]
    assert len(raw)==200 and a==b
    assert a[:2]==b'\0\6' and struct.unpack_from('<Q',a,2)[0]==len(b'identical content')
    native=(tmp_path/'two').stat()
    for i,expected in enumerate((native.st_atime_ns,native.st_mtime_ns,native.st_ctime_ns)):
        off=10+i*13; assert a[off]==1
        sec,nsec=struct.unpack_from('<QI',a,off+1)
        assert sec*1_000_000_000+nsec==expected


def test_random_bytes_and_stable_instance_seed(f16_driver):
    # F16.T05. Bernstein + union bound over both APIs and four count families
    # bounds false rejection by 1e-9 for independent uniform bytes.
    g=F16Guest()
    for key,interface,method in [('secure','random','get-random-bytes'),('insecure','insecure','get-insecure-random-bytes')]:
        g.add(key,'wasi:random/'+interface)
        g.bind(key,key,method,[('len','u64')],'(list u8)','qi')
    g.add('seed','wasi:random/insecure-seed')
    g.bind('seed','seed','insecure-seed',[],'(tuple u64 u64)','i')
    lengths=[0,1,31,257]+[1024]*40
    for key in ('secure','insecure'):
        for n in lengths:
            ret=g.result(key,n,size=8); g.emit(ret+4,4); g.emit(f16_load(ret),f16_load(ret+4))
    for _ in range(4):
        ret=g.result('seed',size=16); g.emit(ret,16)
    executions=[]
    for _ in range(2):
        raw=f16_success(f16_driver.observe(g.source())); pos=0; groups=[]
        for key in ('secure','insecure'):
            blocks=[]
            for n in lengths:
                length,=struct.unpack_from('<I',raw,pos); pos+=4
                assert length==n
                block=raw[pos:pos+length]; pos+=length; assert len(block)==length
                blocks.append(block)
            groups.append(blocks[4:])
        assert len(raw)==pos+64
        assert raw[pos:pos+16]==raw[pos+16:pos+32]==raw[pos+32:pos+48]==raw[pos+48:]
        executions.append(groups)
    assert any(a != b for a, b in zip(executions[0][0][0], executions[0][0][1]))
    t=math.log(2*2*5*256/1e-9)
    for api in range(2):
        blocks=executions[0][api]+executions[1][api]; raw=b''.join(blocks)
        adjacent=bytes(raw[i]^raw[i+1] for i in range(0,len(raw),2))
        across=bytes(x^y for i in range(0,len(blocks),2) for x,y in zip(blocks[i],blocks[i+1],strict=True))
        restarted=bytes(x^y for x,y in zip(b''.join(executions[0][api]),b''.join(executions[1][api]),strict=True))
        separated=bytes(x^y for block in blocks for x,y in zip(block[:512],block[512:],strict=True))
        for label,sample in [('halves',separated),('bytes',raw),('adjacent',adjacent),('requests',across),('executions',restarted)]:
            counts=Counter(sample); mean=len(sample)/256
            margin=math.sqrt(2*mean*t)+2*t/3
            assert all(abs(counts[b]-mean)<=margin for b in range(256)),(api,label,counts)


def test_filesystem_errors_invalid_poll_and_memory(f16_driver, tmp_path):
    # F16.T06. Standard filesystem error discriminants are observed directly.
    (tmp_path/'existing').write_bytes(b'unchanged')
    g=F16Guest(); g.filesystem(); f16_open(g,'existing')
    for path,flags in [('missing',0),('existing',5)]:
        p=g.alloc(path.encode()); ret=g.result('open','(local.get $dir)',0,p,len(path),flags,1)
        g.emit(ret,1); g.emit(ret+4,1)
    assert f16_success(f16_driver.observe(g.source(),directory=str(tmp_path)))==bytes([1,20,1,7])
    assert (tmp_path/'existing').read_bytes()==b'unchanged'
    # The same write entry works with valid memory before its invalid variant.
    for ptr in (4096,16*65536-2):
        g=F16Guest(); g.alloc(b'valid')
        g.body.append(g.call('writeout','(call $getstdout)',ptr,5,128))
        result=f16_driver.observe(g.source())
        if ptr==4096: assert f16_success(result)==b'valid'
        else: assert result['err']=='OutOfBoundsLoad',result
    from F16_helpers import f16_poll_services
    g=F16Guest(); f16_poll_services(g)
    p=g.alloc(bytes(4))
    g.body.append(f'(i32.store (i32.const {p}) (call $ready (call $duration (i64.const 0))))')
    g.emit(p,4)
    g.body.append('(drop (call $ready (call $getstdout)))')
    result=f16_driver.observe(g.source())
    assert result['stdout']==struct.pack('<I',1)
    assert result['err'] in ('Unreachable', 'TypeMismatch'),result


def test_cli_rejects_component_limits_and_disabled_support(f16_driver, f11_driver):
    # F16.T07. A live command precedes every refused configuration.
    g=F16Guest(); p=g.alloc(b'component executed'); g.emit(p,18)
    path=f16_driver.guest(g.source())
    baseline=f11_driver.command(['run',path])
    assert baseline.returncode==0 and baseline.stdout==b'component executed'
    for flag,value in [('--fuel','100000'),('--timeout','1000'),('--max-memory','1048576'),('--max-table-elements','100')]:
        rejected=f11_driver.command(['run',flag,value,path])
        f11_failure(rejected, status=2)
        assert rejected.stdout==b''
    disabled=f11_driver.build(wasi='p1')[0]
    rejected=f11_driver.command(['run',path],cli=disabled)
    f11_failure(rejected, status=2)
    assert rejected.stdout==b''


def test_clocks_polling_and_terminal_detection(f16_driver, f11_driver):
    # F16.T04. Wall time is bracketed independently; monotonic epoch is free.
    from F16_helpers import f16_poll_services, f16_terminal_command
    g=F16Guest(); f16_poll_services(g)
    g.add('wall','wasi:clocks/wall-clock','(type $dt0 (record (field "seconds" u64) (field "nanoseconds" u32))) (export "datetime" (type $dt (eq $dt0)))')
    g.bind('wall','wall','now',[],'$dt','i')
    wall=g.result('wall',size=16); g.emit(wall,12)
    for expr in ('(call $now)','(call $now)'):
        p=g.alloc(bytes(8)); g.body.append(f'(i64.store (i32.const {p}) {expr})'); g.emit(p,8)
    subscriptions=g.alloc(bytes(16))
    for i,expr in enumerate(['(call $duration (i64.const 0))','(call $inputsub (call $getstdin))',
                              '(call $outputsub (call $getstdout))','(call $instant (call $now))']):
        g.body.append(f'(i32.store (i32.const {subscriptions+i*4}) {expr})')
    ret=g.result('poll',subscriptions,4,size=8)
    g.emit(ret+4,4); g.emit(f16_load(ret),f'(i32.mul {f16_load(ret+4)} (i32.const 4))')
    for i in range(4):
        p=g.alloc(bytes(4)); g.body.append(f'(i32.store (i32.const {p}) (call $ready {f16_load(subscriptions+i*4)}))'); g.emit(p,4)
    f16_driver.program(); source=g.source(); observations=[]
    for _ in range(2):
        before=time.time_ns(); mono_before=time.monotonic_ns()
        raw=f16_success(f16_driver.observe(source,stdin='ready'))
        mono_after=time.monotonic_ns(); after=time.time_ns()
        sec,nano,first,last=struct.unpack_from('<QIQQ',raw)
        assert before<=sec*1_000_000_000+nano<=after
        assert nano<1_000_000_000 and first<=last
        n,=struct.unpack_from('<I',raw,28)
        assert 1 <= n <= 4
        indices = struct.unpack_from('<'+'I'*n, raw, 32)
        assert len(set(indices)) == n and set(indices) <= {0,1,2,3}
        assert struct.unpack_from('<4I',raw,32+4*n)==(1,1,1,1) and len(raw)==48+4*n
        observations.append((mono_before,mono_after,first,last))
        time.sleep(0.04)
    # Instants from different instances have no shared epoch. Measure elapsed
    # time across a real blocked input read within one instance instead.
    from F16_helpers import f16_clock_interval
    clock = F16Guest(); f16_poll_services(clock)
    for i in range(2):
        if i: clock.result('readin', '(call $getstdin)', 1)
        p = clock.alloc(bytes(8))
        clock.body.append(f'(i64.store (i32.const {p}) (call $now))'); clock.emit(p, 8)
    lower, upper, first, last = f16_clock_interval(f11_driver.build()[0], f16_driver.guest(clock.source()))
    assert lower <= last-first <= upper
    # Only queued input differs. Output is ready in both arms, so poll cannot
    # block while the empty input pipe remains open.
    from F16_helpers import f16_pipe_readiness
    pipe=F16Guest(); f16_poll_services(pipe)
    subs=pipe.alloc(bytes(8))
    pipe.body.append(f'(i32.store (i32.const {subs}) (call $inputsub (call $getstdin)))')
    pipe.body.append(f'(i32.store (i32.const {subs+4}) (call $outputsub (call $getstdout)))')
    ret=pipe.result('poll',subs,2,size=8)
    pipe.emit(ret+4,4); pipe.emit(f16_load(ret),f'(i32.mul {f16_load(ret+4)} (i32.const 4))')
    p=pipe.alloc(bytes(4))
    pipe.body.append(f'(i32.store (i32.const {p}) (call $ready {f16_load(subs)}))'); pipe.emit(p,4)
    path=f16_driver.guest(pipe.source())
    for incoming,expected in [(b'',{1}),(b'queued',{0,1})]:
        raw=f16_pipe_readiness(f11_driver.build()[0],path,incoming=incoming)
        n,=struct.unpack_from('<I',raw)
        assert len(raw)==8+4*n
        indices=struct.unpack_from('<'+'I'*n,raw,4)
        assert n > 0 and len(set(indices))==n and set(indices)<=expected
        assert struct.unpack_from('<I',raw,4+4*n)[0] == bool(incoming)
    terminal=F16Guest()
    for stream in ('stdin','stdout','stderr'):
        key='term'+stream
        resource='terminal-input' if stream=='stdin' else 'terminal-output'
        terminal.add(key,'wasi:cli/terminal-'+stream, f'(export "{resource}" (type $term (sub resource)))')
        terminal.bind(key,key,'get-terminal-'+stream,[], '(option (own $term))','i')
        ret=terminal.result(key,size=8); terminal.emit(ret,1)
    source=terminal.source()
    assert f16_success(f16_driver.observe(source,stdin='bytes'))==b'\0\0\0'
    path=f16_driver.guest(source)
    result=f11_driver.command(['run',path],stdin=b'bytes')
    assert result.returncode==0 and result.stdout==b'\0\0\0'
    for terminals in ((True, True, True), (True, False, False), (False, True, False), (False, False, True)):
        assert f16_terminal_command(f11_driver.build()[0],path,terminals)==bytes(terminals)
