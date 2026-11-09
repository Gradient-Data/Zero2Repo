# feature: F10
"""Four planned measurements of real WASI snapshot-01 host services.

ABI discriminants and structure offsets are from WASI snapshot-01 witx.
The reference observations and deliberate-defect runs are recorded separately.
"""
from collections import Counter
import math
import struct

from F08_helpers import f08_driver
from F09_helpers import f01_driver, f09_statuses, f09_uint, F09_FILE_RIGHTS
from F10_helpers import (
    f10_driver, F10Guest, f10_fd, f10_timer, f10_events, f10_run, f10_capture_memory,
    f10_run_configured_io, f10_samples,
)


def test_clock_values_and_resolutions(f10_driver):
    # F10.T01. The monotonic epoch is deliberately not fixed. Differences are
    # bracketed by independent native observations, not another guest clock.
    guest = F10Guest()
    resolutions = [guest.clock(f'resolution-{i}', i, resolution=True) for i in range(4)]
    readings = [[guest.clock(f'clock-{i}-{j}', i) for j in range(8)] for i in (0, 1)]
    cpu_before = [guest.clock(f'cpu-before-{i}', i) for i in (2, 3)]
    # Real guest work makes constant CPU readings distinguishable. No speed
    # threshold is imposed: the native CPU clocks provide the independent bounds.
    guest.locals.add('work')
    guest.body.append('i32.const 1000000 local.set $work loop $busy '
                      'local.get $work i32.const 1 i32.sub local.tee $work br_if $busy end')
    cpu_after = [guest.clock(f'cpu-after-{i}', i) for i in (2, 3)]
    elapsed_after = [guest.clock(f'elapsed-after-{i}', i) for i in (0, 1)]
    for engine in ('interp', 'jit'):
      observations = []
      for mem, before, after in f10_samples(f10_driver, guest, engine=engine):
        f09_statuses(guest, mem)
        actual_res = [f09_uint(mem, p, 64) for p in resolutions]
        assert all(r > 0 for r in actual_res)
        for i, start, stop in zip((2, 3), cpu_before, cpu_after, strict=True):
            first, last = f09_uint(mem, start, 64), f09_uint(mem, stop, 64)
            assert before[i] - actual_res[i] <= first <= last <= after[i] + actual_res[i]
        wall, mono = [[f09_uint(mem, p, 64) for p in group] for group in readings]
        assert all(before[0] - actual_res[0] <= x <= after[0] + actual_res[0] for x in wall)
        assert mono == sorted(mono)
        assert f09_uint(mem, elapsed_after[0], 64) >= wall[-1]
        assert f09_uint(mem, elapsed_after[1], 64) >= mono[-1]
        observations.append((before, after, mono, actual_res[1]))
      for previous, current in zip(observations, observations[1:]):
          pb, pa, pm, pr = previous
          cb, ca, cm, cr = current
          delta = cm[0] - pm[-1]
          tolerance = pr + cr
          assert cb[1] - pa[1] - tolerance <= delta <= ca[1] - pb[1] + tolerance

    # A real absent host service is reachable through the public optional I/O
    # configuration. This does not simulate an OS rejecting a particular clock.
    configured = F10Guest()
    configured_res = [configured.clock(f'resolution-{i}', i, resolution=True) for i in range(4)]
    for i in range(4):
        configured.clock(f'clock-{i}', i)
    completed = configured.alloc(4)
    configured.body.append(f'i32.const {completed} i32.const 37 i32.const 5 i32.mul i32.store')
    control = f10_run_configured_io(f10_driver, configured, enabled=True)
    f09_statuses(configured, control)
    assert all(f09_uint(control, p, 64) > 0 for p in configured_res)
    assert f09_uint(control, completed) == 37 * 5
    unavailable = f10_run_configured_io(f10_driver, configured, enabled=False)
    for label, offset in configured.statuses.items():
        # Both unavailable-service (nosys) and unsupported-clock (notsup)
        # are declared failure forms; success and unrelated errors are not.
        assert f09_uint(unavailable, offset) in (52, 58), label
    assert f09_uint(unavailable, completed) == 37 * 5


def test_random_extent_empty_request_and_independent_uniform_bytes(f10_driver):
    # F10.T02. Five families of 256 binomial counts: byte frequencies,
    # non-overlapping adjacent XORs, and corresponding bytes across disjoint
    # request pairs, and matching bytes in independent executions. The last
    # family detects a generator that restarts the same stream in each process.
    # Bernstein + union bound gives total false rejection <=
    # 1e-9. Samples inside each family are independent under the promised law.
    guest = F10Guest()
    regions = []
    guard = bytes(range(16, 32))
    for i, size in enumerate([1, 31, 257] + [1024] * 40):
        ptr = guest.alloc(size + 32, guard + b'\xa5' * size + guard)
        guest.service(f'random-{i}', 'random_get', ptr + 16, size)
        regions.append((ptr, size))
    empty = guest.alloc(64, bytes(range(64)))
    guest.service('empty', 'random_get', empty + 29, 0)
    tails = []
    for i in range(16):
        ptr = guest.alloc(9, b'\xa5' * 9)
        guest.service(f'tail-{i}', 'random_get', ptr, 9)
        tails.append(ptr + 8)
    executions = []
    blocks = []
    for _ in range(2):
        mem, _, _ = f10_run(f10_driver, guest)
        f09_statuses(guest, mem)
        assert mem[empty:empty+64] == bytes(range(64))
        for ptr, size in regions:
            assert mem[ptr:ptr+16] == guard
            assert mem[ptr+16+size:ptr+32+size] == guard
        current = [mem[p+16:p+16+n] for p, n in regions[3:]]
        # Independent final bytes: false rejection probability is 256**-16.
        assert any(mem[p] != 0xa5 for p in tails)
        blocks.extend(current)
        executions.append(b''.join(current))
    raw = b''.join(blocks)
    adjacent = bytes(raw[i] ^ raw[i+1] for i in range(0, len(raw), 2))
    across = bytes(a ^ b for i in range(0, len(blocks), 2)
                   for a, b in zip(blocks[i], blocks[i+1], strict=True))
    restarted = bytes(a ^ b for a, b in zip(*executions, strict=True))
    separated = bytes(a ^ b for block in blocks
                      for a, b in zip(block[:512], block[512:], strict=True))
    t = math.log(2 * 5 * 256 / 1e-9)
    for label, sample in [('bytes', raw), ('adjacent-xor', adjacent),
                          ('request-xor', across), ('execution-xor', restarted),
                          ('half-xor', separated)]:
        counts = Counter(sample)
        mean = len(sample) / 256
        margin = math.sqrt(2 * mean * t) + 2 * t / 3
        assert all(abs(counts[b] - mean) <= margin for b in range(256)), (label, counts)


def test_poll_resource_state_and_timer_completion(f10_driver, f08_driver, tmp_path):
    # F10.T03. Read counts and EOF are checked on the same resources after
    # real reads; writes have no fixed capacity promise beyond being writable.
    incoming = b'input\x00payload!'
    stdin_guest = F10Guest()
    stdin_guest.body.append('i32.const 0 local.set $file')
    initial = stdin_guest.poll('stdin-initial', [f10_fd(0x100000065, 1, 0)])
    prefix, prefix_n = stdin_guest.io('stdin-prefix', 'fd_read', 4)
    partial = stdin_guest.poll('stdin-partial', [f10_fd(0x100000066, 1, 0)])
    tail, tail_n = stdin_guest.io('stdin-tail', 'fd_read', 64)
    empty = stdin_guest.poll('stdin-eof', [f10_fd(0x100000067, 1, 0)])
    mem = f10_capture_memory(f08_driver, stdin_guest, incoming)
    f09_statuses(stdin_guest, mem)
    for region, user, count in [(initial, 0x100000065, len(incoming)),
                                (partial, 0x100000066, len(incoming)-4),
                                (empty, 0x100000067, 0)]:
        assert f10_events(mem, region) == {user: {'error': 0, 'kind': 1, 'nbytes': count}}
    assert f09_uint(mem, prefix_n) == 4 and mem[prefix:prefix+4] == incoming[:4]
    assert f09_uint(mem, tail_n) == len(incoming)-4 and mem[tail:tail+len(incoming)-4] == incoming[4:]

    root = tmp_path / 'poll-files'
    root.mkdir()
    content = b'file-readiness\x00data'
    (root / 'data').write_bytes(content)
    guest = F10Guest()
    guest.grant()
    guest.open('file-open', 'data', rights=F09_FILE_RIGHTS | (1 << 27))
    # Subscription fd is obtained from path_open, never assumed from ordering.
    file_regions = []
    for label in ('file-initial', 'file-partial', 'file-eof', 'file-beyond-eof', 'file-write'):
        kind = 2 if label == 'file-write' else 1
        sub = guest.alloc(48, f10_fd(0x1000000c9, kind, 0))
        guest.body.append(f'i32.const {sub+16} local.get $file i32.store')
        out, count = guest.alloc(32), guest.alloc(4)
        guest.service(label, 'poll_oneoff', sub, out, 1, count)
        file_regions.append((out, count, 1))
        if label == 'file-initial':
            first, first_n = guest.io('file-prefix', 'fd_read', 3)
        if label == 'file-partial':
            rest, rest_n = guest.io('file-rest', 'fd_read', 128)
        if label == 'file-eof':
            position = guest.alloc(8)
            guest.call('seek-beyond-eof', 'fd_seek', '(local.get $file)', len(content) + 19, 0, position)
    sinks = [guest.poll(f'output-{fd}', [f10_fd(0x10000012c+fd, 2, fd)]) for fd in (1, 2)]
    mem, _, _ = f10_run(f10_driver, guest, [(root, '/sandbox')])
    f09_statuses(guest, mem)
    for region, remaining in zip(file_regions[:4], (len(content), len(content)-3, 0, 0), strict=True):
        assert f10_events(mem, region) == {0x1000000c9: {'error': 0, 'kind': 1, 'nbytes': remaining}}
    for region, user in [(file_regions[4], 0x1000000c9), (sinks[0], 0x10000012d), (sinks[1], 0x10000012e)]:
        events = f10_events(mem, region)
        assert set(events) == {user}
        assert events[user]['error'] == 0 and events[user]['kind'] == 2
        assert events[user]['nbytes'] > 0
    assert f09_uint(mem, first_n) == 3 and mem[first:first+3] == content[:3]
    assert f09_uint(mem, rest_n) == len(content)-3 and mem[rest:rest+len(content)-3] == content[3:]

    # These durations are timer inputs, not machine performance thresholds.
    # The later deadline leaves seconds of scheduling reserve for the earliest
    # event. Repeat to allow outliers; startup and instantiation are outside each bracket.
    short_ns, later_ns = 60_000_000, 5_000_000_000
    for clock_id in (0, 1):
        durations = {'relative': [], 'absolute': [], 'ready': []}
        for mode in durations:
            for _ in range(3):
                timer = F10Guest()
                if mode == 'absolute':
                    now = timer.clock('now', clock_id)
                    sub = timer.alloc(96, f10_timer(402, 0, clock=clock_id, absolute=True)
                                      + f10_timer(401, 0, clock=clock_id, absolute=True))
                    for offset, delay in ((24, later_ns), (72, short_ns)):
                        timer.body.append(f'i32.const {sub+offset} i32.const {now} i64.load i64.const {delay} i64.add i64.store')
                    out, count = timer.alloc(64), timer.alloc(4)
                    timer.service('wait', 'poll_oneoff', sub, out, 2, count)
                    region = (out, count, 2)
                elif mode == 'relative':
                    region = timer.poll('wait', [f10_timer(402, later_ns, clock=clock_id), f10_timer(401, short_ns, clock=clock_id)])
                else:
                    region = timer.poll('wait', [f10_timer(402, later_ns, clock=clock_id), f10_fd(403, 2, 1)])
                mem, before, after = f10_run(f10_driver, timer)
                f09_statuses(timer, mem)
                elapsed = after[1] - before[1]
                durations[mode].append(elapsed)
                events = f10_events(mem, region)
                if mode == 'ready':
                    assert 403 in events and events[403]['kind'] == 2 and events[403]['error'] == 0
                    assert events[403]['nbytes'] > 0
                else:
                    assert 401 in events and events[401] == {'error': 0, 'kind': 0}
                    assert elapsed >= short_ns
                assert set(events) <= ({401, 402} if mode != 'ready' else {402, 403})
                if 402 in events:
                    assert elapsed >= later_ns and events[402] == {'error': 0, 'kind': 0}
            assert min(durations[mode]) < later_ns, (mode, durations[mode])
        print('poll execution brackets (ns):', durations)


def test_distinguishable_clock_poll_and_memory_failures(f10_driver):
    # F10.T04. Every failure is a preview1 errno returned by the real import.
    # No assertion depends on diagnostic prose or internal exception classes.
    guest = F10Guest()
    guest.clock('clock-baseline', 0)
    guest.clock('resolution-baseline', 1, resolution=True)
    baseline = guest.poll('poll-baseline', [f10_fd(501, 2, 1)])
    scratch = guest.alloc(32)
    guest.service('random-baseline', 'random_get', scratch, 32)
    guest.service('clock-invalid', 'clock_time_get', 17, 1, scratch)
    guest.service('resolution-invalid', 'clock_res_get', 17, scratch)
    guest.poll('subscription-invalid', [f10_fd(502, 9, 1)])
    missing = guest.poll('descriptor-missing', [f10_fd(503, 1, 999)])
    guest.poll('clock-subscription-invalid', [f10_timer(504, 1, clock=17, absolute=True)])
    guest.service('clock-output-fault', 'clock_time_get', 0, 1, 65532)
    guest.service('resolution-output-fault', 'clock_res_get', 1, 65532)
    guest.service('random-output-fault', 'random_get', 65532, 8)
    sub = guest.alloc(48, f10_fd(505, 2, 1))
    count = guest.alloc(4)
    guest.service('poll-output-fault', 'poll_oneoff', sub, 65520, 1, count)
    guest.service('poll-count-fault', 'poll_oneoff', sub, scratch, 1, 65534)
    guest.call('reduce-poll-right', 'fd_fdstat_set_rights', 1, 0, 0)
    denied = guest.poll('poll-right-denied', [f10_fd(506, 2, 1)])
    mem, _, _ = f10_run(f10_driver, guest)
    for label, info, identity, kind, errno in [('descriptor-missing', missing, 503, 1, 8),
                                               ('poll-right-denied', denied, 506, 2, 76)]:
        status = struct.unpack_from('<I', mem, guest.statuses[label])[0]
        assert status in (0, errno), (label, status)
        if status == 0:
            events = f10_events(mem, info)
            assert set(events) == {identity}
            assert events[identity]['error'] == errno and events[identity]['kind'] == kind
    f09_statuses(guest, mem, {
        'descriptor-missing': struct.unpack_from('<I',mem,guest.statuses['descriptor-missing'])[0],
        'poll-right-denied': struct.unpack_from('<I',mem,guest.statuses['poll-right-denied'])[0],
        'clock-invalid': 28, 'resolution-invalid': 28, 'subscription-invalid': 28,
        'clock-subscription-invalid': 28, 'clock-output-fault': 21,
        'resolution-output-fault': 21, 'random-output-fault': 21,
        'poll-output-fault': 21, 'poll-count-fault': 21,
    })
    events = f10_events(mem, baseline)
    assert set(events) == {501}
    assert events[501]['error'] == 0 and events[501]['kind'] == 2 and events[501]['nbytes'] > 0
