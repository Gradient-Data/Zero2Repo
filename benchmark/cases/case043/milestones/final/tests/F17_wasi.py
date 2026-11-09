# feature: F17
"""WASI 0.3 services observed through real callback-form commands."""
from collections import Counter
import math
import os
import struct
import time
from F01_helpers import f01_driver
from F08_helpers import f08_driver
from F11_helpers import f11_driver
from F17_helpers import F17Guest, F17FsGuest, f17_completed_copy, f17_driver
from F16_helpers import f16_load, f16_success, f16_open


def test_command_context_stream_io_and_outcomes(f17_driver,f11_driver):
    # F17.T05 (FP-17.01, FP-17.06). The guest serializes the standard lists, then consumes stdin.
    g=F17FsGuest(); g.add('env','wasi:cli/environment')
    for name,result in [('args','(list string)'),('env','(list (tuple string string))')]:
        g.bind(name,'env','get-arguments' if name=='args' else 'get-environment',[],result,'i')
        ret=g.result(name,size=8); g.emit(ret+4,4)
        stride=8 if name=='args' else 16
        g.body.append(f'''(local.set $i (i32.const 0))
(block $done (loop $next (br_if $done (i32.ge_u (local.get $i) {f16_load(ret+4)}))
(local.set $p (i32.add {f16_load(ret)} (i32.mul (local.get $i) (i32.const {stride}))))''')
        for off in range(0,stride,8):
            g.body.append(f'''(call $emit (i32.add (local.get $p) (i32.const {off+4})) (i32.const 4))
(call $emit (i32.load offset={off} (local.get $p)) (i32.load offset={off+4} (local.get $p)))''')
        g.body.append('(local.set $i (i32.add (local.get $i) (i32.const 1))) (br $next)))')
    g.add('stdin','wasi:cli/stdin', '(type $ec0 (enum "io" "illegal-byte-sequence" "pipe")) (export "error-code" (type $ec (eq $ec0)))')
    g.bind('input','stdin','read-via-stream',[], '(tuple (stream u8) (future (result (error $ec))))','i')
    g.builtin('inread','stream.read $bytes (memory $lib "memory")','iii','i')
    ret=g.result('input',size=8)
    incoming='A\x00é水Z'.encode()
    for _ in incoming:
        f17_completed_copy(g, 'inread', f16_load(ret), 512, 1)
        g.emit(512,1)
    err=b'other-channel\x00\xff'; p=g.alloc(err)
    pair=g.alloc(bytes(8))
    g.body += [f'(i64.store (i32.const {pair}) (call $outnew))',
               f'(drop (call $stderr {f16_load(pair)}))']
    for offset in range(len(err)):
        code=g.alloc(bytes(4))
        g.body.append(('copy',f'(call $outwrite {f16_load(pair+4)} (i32.const {p+offset}) (i32.const 1))',f16_load(pair+4),code,3))
        g.body.append(f'(if (i32.ne {f16_load(code)} (i32.const 16)) (then unreachable))')
    source=g.source()
    def decode(raw):
        pos=0
        def number():
            nonlocal pos
            n,=struct.unpack_from('<I',raw,pos); pos+=4; return n
        def blob():
            nonlocal pos
            n=number(); data=raw[pos:pos+n]; pos+=n; assert len(data)==n; return data
        args=[blob() for _ in range(number())]
        env=[(blob(),blob()) for _ in range(number())]
        data=bytearray()
        for index in range(len(incoming)):
            assert number() in ((16,17) if index==len(incoming)-1 else (16,))
            data.extend(raw[pos:pos+1]); pos+=1
        assert pos==len(raw)
        assert data==incoming
        return args,env
    for args,env in [([],{}),(['app','猫','','two words'],{'MODE':'p3','EMPTY':''})]:
        got=f17_driver.observe(source,args=args,keys=list(env),values=list(env.values()),stdin=incoming.decode())
        actual_args,actual_env=decode(f16_success(got))
        assert actual_args==[s.encode() for s in args]
        assert len(actual_env)==len(env) and dict(actual_env)=={k.encode():v.encode() for k,v in env.items()}
        assert got['stderr']==err
    path=f17_driver.guest(source)
    got=f11_driver.command(['run','--env','MODE=cli',path,'α','z'],stdin=incoming)
    assert got.returncode==0,got.stderr
    args,env=decode(got.stdout)
    assert args[0] in (path.name.encode(), str(path).encode())
    assert args[1:]==['α'.encode(),b'z'] and env==[(b'MODE',b'cli')]
    assert got.stderr==err
    for status in (0,1):
        command=F17Guest()
        command.builtin('complete','task.return (result (result))','i','')
        p=command.alloc(b'executed'); command.emit(p,8)
        command.body.append(f'(call $complete (i32.const {status}))')
        source=command.source().replace('(func $run async (canon lift','(func $run async (result (result)) (canon lift')
        source=source.replace('(func $f async))','(func $f async (result (result))))')
        result=f17_driver.observe(source)
        assert result['err'] is None and result['exit_code'] in ((None,0) if status==0 else (1,)) and result['stdout']==b'executed',result
        path=f17_driver.guest(source); cli=f11_driver.command(['run',path])
        assert cli.returncode==status and cli.stdout==b'executed'


def test_clocks_relative_and_absolute_waits(f17_driver):
    # F17.T06 (FP-17.07, FP-17.10). No upper runtime bound; the requested wait is a semantic duration.
    g=F17Guest()
    for key,scalar in [('wall','u64'),('system','s64')]:
        g.add(key,'wasi:clocks/'+('wall-clock' if key=='wall' else 'system-clock'),
              f'(type $t0 (record (field "seconds" {scalar}) (field "nanoseconds" u32))) (export "'+('datetime' if key=='wall' else 'instant')+'" (type $t (eq $t0)))')
        g.bind(key,key,'now',[],'$t','i')
        ret=g.result(key,size=16); g.emit(ret,12)
    g.add('mono','wasi:clocks/monotonic-clock')
    g.bind('now','mono','now',[],'u64','','q')
    for key in ('system','mono'):
        g.bind(key+'res',key,'get-resolution',[],'u64','','q')
        g.record('(call $'+key+'res)','i64')
    for key in ('relative','absolute'):
        g.bind(key,'mono','wait-for' if key=='relative' else 'wait-until',[('when','u64')],None,'q')
        # The WIT function is async; lowering synchronously still waits for it.
        g.groups['mono'][2][-1]=g.groups['mono'][2][-1].replace('(func ','(func async ')
        before=g.record('(call $now)','i64')
        requested=35_000_000
        g.body.append(g.call(key, requested if key=='relative' else f'(i64.add {f16_load(before,"i64")} (i64.const {requested}))'))
        g.record('(call $now)','i64')
    f17_driver.program()
    before=time.time_ns(); start=time.monotonic_ns()
    raw=f16_success(f17_driver.observe(g.source()))
    end=time.monotonic_ns(); after=time.time_ns()
    assert len(raw)==72
    systemres,monores,a,b,c,d=struct.unpack_from('<6Q',raw,24)
    assert systemres > 0 and monores > 0
    for offset in (0,12):
        sec,nano=struct.unpack_from('<QI',raw,offset)
        assert nano<1_000_000_000 and before-systemres<=sec*1_000_000_000+nano<=after+systemres
    assert a<=b<=c<=d and b-a+monores>=requested and d-c+monores>=requested
    assert end-start+monores>=2*requested
    from F17_helpers import F17FsGuest
    g=F17FsGuest(); g.add('mono','wasi:clocks/monotonic-clock')
    g.bind('resolution','mono','get-resolution',[],'u64','','q')
    g.record('(call $resolution)','i64')
    g.bind('now','mono','now',[],'u64','','q')
    for key in ('relative','absolute'):
        g.bind(key,'mono','wait-for' if key=='relative' else 'wait-until',[('when','u64')],None,'q','i')
        g.groups['mono'][2][-1]=g.groups['mono'][2][-1].replace('(func ','(func async ')
        g.async_names.add(key)
        before=g.record('(call $now)','i64')
        request=requested if key=='relative' else f'(i64.add {f16_load(before,"i64")} (i64.const {requested}))'
        g.body.append(('await',g.call(key,request)))
        g.record('(call $now)','i64')
    start=time.monotonic_ns()
    resolution,a,b,c,d=struct.unpack('<5Q',f16_success(f17_driver.observe(g.source())))
    assert resolution > 0
    assert time.monotonic_ns()-start+resolution>=2*requested
    assert a<=b<=c<=d and b-a+resolution>=requested and d-c+resolution>=requested


def test_random_bytes_and_stable_seed(f17_driver):
    # F17.T09 (FP-17.11). Bernstein + union bound over 2 APIs * 4 families * 256 bins
    # gives false rejection probability below 1e-9 for independent uniform bytes.
    g=F17Guest()
    for key,interface,method in [('secure','random','get-random-bytes'),('insecure','insecure','get-insecure-random-bytes')]:
        g.add(key,'wasi:random/'+interface)
        g.bind(key,key,method,[('len','u64')],'(list u8)','qi')
    g.add('seed','wasi:random/insecure-seed'); g.bind('seed','seed','insecure-seed',[],'(tuple u64 u64)','i')
    lengths=[0,1,31,257]+[1024]*40
    for key in ('secure','insecure'):
        for n in lengths:
            ret=g.result(key,n,size=8); g.emit(ret+4,4); g.emit(f16_load(ret),f16_load(ret+4))
    for _ in range(4):
        ret=g.result('seed',size=16); g.emit(ret,16)
    executions=[]
    for _ in range(2):
        raw=f16_success(f17_driver.observe(g.source())); pos=0; groups=[]
        for key in ('secure','insecure'):
            blocks=[]
            for n in lengths:
                actual,=struct.unpack_from('<I',raw,pos); pos+=4; assert actual==n
                block=raw[pos:pos+n]; pos+=n; assert len(block)==n; blocks.append(block)
            groups.append(blocks[4:])
        assert len(raw)==pos+64
        assert raw[pos:pos+16]==raw[pos+16:pos+32]==raw[pos+32:pos+48]==raw[pos+48:]
        executions.append(groups)
    t=math.log(2*2*4*256/1e-9)
    for api in range(2):
        blocks=executions[0][api]+executions[1][api]; raw=b''.join(blocks)
        adjacent=bytes(raw[i]^raw[i+1] for i in range(0,len(raw),2))
        across=bytes(x^y for i in range(0,len(blocks),2) for x,y in zip(blocks[i],blocks[i+1],strict=True))
        restarted=bytes(x^y for x,y in zip(b''.join(executions[0][api]),b''.join(executions[1][api]),strict=True))
        for sample in (raw,adjacent,across,restarted):
            counts=Counter(sample); mean=len(sample)/256
            margin=math.sqrt(2*mean*t)+2*t/3
            assert all(abs(counts[b]-mean)<=margin for b in range(256))


def test_file_identity_descriptors_paths_and_hardlinks(f17_driver,tmp_path):
    # F17.T08 (FP-17.09). Equal bytes deliberately do not imply equal objects.
    from F17_helpers import F17FsGuest
    for name in ('one','two'): (tmp_path/name).write_bytes(b'equal bytes')
    os.link(tmp_path/'one',tmp_path/'alias')
    g=F17FsGuest()
    g.async_bind('hash','metadata-hash',[('self','(borrow $desc)')],'(result $hash (error $error))','ii')
    g.async_bind('hashat','metadata-hash-at',[('self','(borrow $desc)'),('pf','$pf'),('path','string')],'(result $hash (error $error))','iiiii')
    g.async_bind('same','is-same-object',[('self','(borrow $desc)'),('other','(borrow $desc)')],'bool','iii')
    handles=[]
    for name in ('one','one','alias','two'):
        handle=g.open(name); handles.append(handle)
        r=g.async_result('hash',handle); g.emit(r,1); g.emit(r+8,16)
        p=g.alloc(name.encode()); r=g.async_result('hashat',g.directory_handle,1,p,len(name)); g.emit(r,1); g.emit(r+8,16)
    for handle in handles:
        r=g.async_result('same',handles[0],handle); g.emit(r,1)
    p=g.alloc(b'absent'); r=g.async_result('hashat',g.directory_handle,0,p,6); g.emit(r,1); g.emit(r+8,1)
    raw=f16_success(f17_driver.observe(g.source(),directory=str(tmp_path)))
    ids=[]; pos=0
    for _ in handles:
        assert raw[pos]==0; pos+=1
        pair=[]
        for _ in range(2):
            assert raw[pos]==0; pair.append(raw[pos+1:pos+17]); pos+=17
        assert pair[0]==pair[1]; ids.append(pair[0])
    assert ids[0]==ids[1]==ids[2] and ids[0]!=ids[3]
    assert raw[pos:]==bytes([1,1,1,0,1,19])


def test_filesystem_streams_metadata_and_mutations(f17_driver,tmp_path):
    # F17.T07 (FP-17.08). Observe the real filesystem and each standard result discriminant.
    from F17_helpers import F17FsGuest, f17_completed_copy
    g=F17FsGuest()
    g.types += ['(type $done (future (result (error $fs-error))))', '(type $entries (stream $fs-entry))']
    g.builtin('completion','future.read $done (memory $lib "memory") (realloc $realloc)','ii','i')
    g.builtin('readbytes','stream.read $bytes (memory $lib "memory")','iii','i')
    g.builtin('readentry','stream.read $entries (memory $lib "memory") (realloc $realloc)','iii','i')
    g.bind('writefile','fs','[method]descriptor.write-via-stream',[('self','(borrow $desc)'),('data','(stream u8)'),('offset','u64')],'(future (result (error $error)))','iiq','i')
    g.bind('appendfile','fs','[method]descriptor.append-via-stream',[('self','(borrow $desc)'),('data','(stream u8)')],'(future (result (error $error)))','ii','i')
    g.bind('readfile','fs','[method]descriptor.read-via-stream',[('self','(borrow $desc)'),('offset','u64')],'(tuple (stream u8) (future (result (error $error))))','iqi')
    g.bind('listing','fs','[method]descriptor.read-directory',[('self','(borrow $desc)')],'(tuple (stream $entry) (future (result (error $error))))','ii')
    for name,params,result,core in [
        ('sync',[('self','(borrow $desc)')],'(result (error $error))','ii'),
        ('sync-data',[('self','(borrow $desc)')],'(result (error $error))','ii'),
        ('set-size',[('self','(borrow $desc)'),('size','u64')],'(result (error $error))','iqi'),
        ('get-flags',[('self','(borrow $desc)')],'(result $df (error $error))','ii'),
        ('get-type',[('self','(borrow $desc)')],'(result $dt (error $error))','ii'),
        ('stat',[('self','(borrow $desc)')],'(result $stat (error $error))','ii'),
        ('set-times',[('self','(borrow $desc)'),('atime','$newtime'),('mtime','$newtime')],'(result (error $error))','ii'),
        ('rename-at',[('self','(borrow $desc)'),('old','string'),('dest','(borrow $desc)'),('new','string')],'(result (error $error))','ii'),
        ('link-at',[('self','(borrow $desc)'),('flags','$pf'),('old','string'),('dest','(borrow $desc)'),('new','string')],'(result (error $error))','ii'),
        ('symlink-at',[('self','(borrow $desc)'),('old','string'),('new','string')],'(result (error $error))','ii'),
        ('readlink-at',[('self','(borrow $desc)'),('path','string')],'(result string (error $error))','iiii'),
        *[(n,[('self','(borrow $desc)'),('path','string')],'(result (error $error))','iiii') for n in ('create-directory-at','remove-directory-at','unlink-file-at')],
    ]: g.async_bind(name,name,params,result,core)
    ret=g.preopen_result; g.emit(ret+4,4)
    g.emit(f'(i32.load offset=4 {f16_load(ret)})',f'(i32.load offset=8 {f16_load(ret)})')
    handle=g.open('original',flags=1)
    for method,data in [('writefile',b'Q\x00\xffabc'),('appendfile',b'XYZ')]:
        p=g.alloc(data)
        g.body += ['(local.set $h (call $outnew))']
        args=[handle,'(i32.wrap_i64 (local.get $h))']+([2] if method=='writefile' else [])
        future=g.alloc(bytes(4))
        g.body.append(f'(i32.store (i32.const {future}) {g.call(method,*args)})')
        writable=g.alloc(bytes(4))
        g.body.append(f'(i32.store (i32.const {writable}) (i32.wrap_i64 (i64.shr_u (local.get $h) (i64.const 32))))')
        for offset in range(len(data)):
            f17_completed_copy(g,'outwrite',f16_load(writable),p+offset,1)
        g.body.append(f'(call $outdrop {f16_load(writable)})')
        # The returned handle itself is opaque and is not an assertion target.
        result=g.alloc(bytes(20)); f17_completed_copy(g,'completion',f16_load(future),result); g.emit(result,1)
    # Accumulate to closure, accepting a final completion that also carries data.
    ret=g.result('readfile',handle,2,size=8)
    contents=g.alloc(bytes(10)); read_state=g.alloc(bytes(12))
    g.body.append(('stream-all','readbytes',f16_load(ret),contents,10,read_state))
    g.emit(read_state,8); g.emit(contents,f16_load(read_state))
    done=g.alloc(bytes(20)); f17_completed_copy(g,'completion',f16_load(ret+4),done); g.emit(done,1)
    for op in ('sync','sync-data'):
        r=g.async_result(op,handle); g.emit(r,1)
    readonly=g.open('original',rights=1)
    r=g.async_result('get-flags',readonly); g.emit(r,1); g.emit(r+4,1)
    r=g.async_result('get-flags',handle); g.emit(r,1); g.emit(r+4,1)
    r=g.async_result('get-type',handle); g.emit(r,1); g.emit(r+4,1)
    r=g.async_result('set-size',handle,5); g.emit(r,1)
    stamps=(1_600_000_003_123456789,1_600_000_007_987654321)
    control=tmp_path.parent / (tmp_path.name+'-timestamp-control')
    control.write_bytes(b'time')
    os.utime(control,ns=stamps)
    expected_stamps=(control.stat().st_atime_ns,control.stat().st_mtime_ns)
    args=g.alloc(bytes(56)); g.body.append(f'(i32.store (i32.const {args}) {handle})')
    for off,stamp in zip((8,32),stamps):
        g.body += [f'(i32.store8 (i32.const {args+off}) (i32.const 2))',
                   f'(i64.store (i32.const {args+off+8}) (i64.const {stamp//1_000_000_000}))',
                   f'(i32.store (i32.const {args+off+16}) (i32.const {stamp%1_000_000_000}))']
    r=g.async_result('set-times',args); g.emit(r,1)
    r=g.async_result('stat',handle,size=112); g.emit(r,1); g.emit(r+8,1); g.emit(r+24,8); g.emit(r+32,8)
    for off in (40,64,88): g.emit(r+off,1); g.emit(r+off+8,12)
    names={s:g.alloc(s.encode()) for s in ('original','renamed','hard','sym','folder','gone')}
    for op in ('rename-at','link-at','symlink-at'):
        arg=g.alloc(bytes(32)); g.body.append(f'(i32.store (i32.const {arg}) {g.directory_handle})')
        if op=='rename-at': fields=[(4,names['original']),(8,8),(12,g.directory_handle),(16,names['renamed']),(20,7)]
        elif op=='link-at': fields=[(4,1),(8,names['renamed']),(12,7),(16,g.directory_handle),(20,names['hard']),(24,4)]
        else: fields=[(4,names['renamed']),(8,7),(12,names['sym']),(16,3)]
        for off,v in fields:
            expr=v if isinstance(v,str) else f'(i32.const {v})'
            g.body.append(f'(i32.store (i32.const {arg+off}) {expr})')
        r=g.async_result(op,arg); g.emit(r,1)
    for op,name in [('create-directory-at','folder'),('create-directory-at','gone'),('remove-directory-at','gone')]:
        r=g.async_result(op,g.directory_handle,names[name],len(name)); g.emit(r,1)
    directory=g.open('folder',flags=2,rights=1)
    r=g.async_result('get-type',directory); g.emit(r,1); g.emit(r+4,1)
    r=g.async_result('readlink-at',g.directory_handle,names['sym'],3)
    g.emit(r,1); g.emit(r+8,4); g.emit(f16_load(r+4),f16_load(r+8))
    r=g.result('listing',g.directory_handle,size=8)
    entries_buffer=g.alloc(bytes(5*24)); listing_state=g.alloc(bytes(12))
    g.body.append(('stream-all','readentry',f16_load(r),entries_buffer,5,listing_state,24))
    g.emit(listing_state,8)
    g.body.append(f'''(local.set $i (i32.const 0)) (block $entries-done (loop $entries
      (br_if $entries-done (i32.ge_u (local.get $i) {f16_load(listing_state)}))
      (local.set $p (i32.add (i32.const {entries_buffer}) (i32.mul (local.get $i) (i32.const 24))))''')
    g.emit('(local.get $p)',1)
    g.emit('(i32.add (local.get $p) (i32.const 20))',4)
    g.emit('(i32.load offset=16 (local.get $p))','(i32.load offset=20 (local.get $p))')
    g.body.append('(local.set $i (i32.add (local.get $i) (i32.const 1))) (br $entries)))')
    # A directory is a valid descriptor but cannot supply file bytes.
    r=g.result('readfile',directory,0,size=8)
    f17_completed_copy(g,'readbytes',f16_load(r),512,1)
    done=g.alloc(bytes(20)); f17_completed_copy(g,'completion',f16_load(r+4),done); g.emit(done,1); g.emit(done+4,1)
    r=g.async_result('unlink-file-at',g.directory_handle,names['renamed'],7); g.emit(r,1)
    before=time.time_ns()
    raw=f16_success(f17_driver.observe(g.source(),directory=str(tmp_path))); pos=0
    after=time.time_ns()
    def take(n):
        nonlocal pos
        data=raw[pos:pos+n]; pos+=n; assert len(data)==n; return data
    def u32(): return struct.unpack('<I',take(4))[0]
    assert u32()==1 and take(8)==b'/sandbox'
    assert take(1)==b'\0'
    for size in (6,3):
        for _ in range(size): assert u32()==16
        assert u32()==0 and take(1)==b'\0'
    assert u32()==9 and u32() & 15 == 1
    assert take(9)==b'Q\0\xffabcXYZ'
    assert u32()==0 and take(1)==b'\0'
    assert take(2)==b'\0\0'
    assert take(3)==bytes([0,0,1])
    assert take(4)==bytes([0,3,0,5])
    assert take(2)==b'\0\0'
    assert take(2)==bytes([0,5]) and struct.unpack('<QQ',take(16))==(1,5)
    for stamp in expected_stamps:
        assert take(1)==b'\1'; sec,nano=struct.unpack('<qI',take(12)); assert sec*1_000_000_000+nano==stamp
    assert take(1)==b'\1'; sec,nano=struct.unpack('<qI',take(12)); assert before<=sec*1_000_000_000+nano<=after
    assert take(6)==bytes(6)
    assert take(3)==bytes([0,0,2])
    assert take(1)==b'\0'; n=u32(); assert take(n)==b'renamed'
    entries={}
    assert u32()==4 and u32() & 15 == 1
    for _ in range(4):
        kind=take(1)[0]; n=u32(); name=take(n).decode(); assert name not in entries; entries[name]=kind
    assert entries=={'renamed':5,'hard':5,'sym':4,'folder':2}
    assert u32()==1 and u32()==0 and take(2)==bytes([1,13])
    assert take(1)==b'\0' and pos==len(raw)
    assert {p.name for p in tmp_path.iterdir()}=={'hard','sym','folder'}
    stat=(tmp_path/'hard').stat(); assert (stat.st_atime_ns,stat.st_mtime_ns)==expected_stamps
    assert (tmp_path/'hard').read_bytes()==b'\0\0Q\0\xff'
    assert os.readlink(tmp_path/'sym')=='renamed' and (tmp_path/'folder').is_dir()


    target=tmp_path/'current-time'; target.write_bytes(b'timestamp')
    stale=1_500_000_000_000_000_000; os.utime(target,ns=(stale,stale))
    g=F17FsGuest(); handle=g.open('current-time')
    g.async_bind('set-times','set-times',[('self','(borrow $desc)'),('atime','$newtime'),('mtime','$newtime')],'(result (error $error))','ii')
    args=g.alloc(bytes(56)); g.body.append(f'(i32.store (i32.const {args}) {handle})')
    for off in (8,32): g.body.append(f'(i32.store8 (i32.const {args+off}) (i32.const 1))')
    result=g.async_result('set-times',args); g.emit(result,1)
    before=time.time_ns(); raw=f16_success(f17_driver.observe(g.source(),directory=str(tmp_path))); after=time.time_ns()
    assert raw==b'\0\0'
    actual=target.stat()
    assert before<=actual.st_atime_ns<=after and before<=actual.st_mtime_ns<=after
