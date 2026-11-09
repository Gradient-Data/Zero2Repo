# feature: F03
"""Manual history reclamation through the public persistent-map API.

Conditional observations are explicitly uncovered when a conforming strategy
does not produce overlap or invoke encoding. Their branch records preserve the
observations; an uncovered skip is not a pass or product nonconformance.
"""

import struct

import pytest

from _helpers import read_json_file
from F02_helpers import compile_persistence_caller, read_log_state, run_persistence_caller
from F03_helpers import COMPACTION_SUPPORT


def test_compaction_reclaims_history_and_preserves_state(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        Map<String,String> expected = Map.of(
            "first", "latest 水", "second", "still present", "third", "Ω");
        if (args[1].equals("write")) {
            for (String name : List.of("short", "long", "empty")) {
                VelqoraMap<String,String> map = new VelqoraMap<>(root.resolve(name),TEXT,TEXT);
                int rounds = name.equals("short") ? 4 : 48;
                for (int i=0; i<rounds; i++) {
                    map.put("first", "obsolete-"+i+"x".repeat(256));
                    map.put("removed-"+i, "deleted-"+i+"y".repeat(128));
                    map.flush();
                    map.remove("removed-"+i);
                    map.flush();
                }
                map.putAll(expected);
                if (name.equals("empty")) map.clear();
                map.flush();
                contents(name.equals("empty") ? Map.of() : expected, map);
                long before = Files.size(root.resolve(name).resolve("velqoramap.log"));
                map.compact();
                contents(name.equals("empty") ? Map.of() : expected, map);
                long after = Files.size(root.resolve(name).resolve("velqoramap.log"));
                Files.writeString(root.resolve(name+".json"),
                    "{\"before\":"+before+",\"after\":"+after+"}");
            }
            // Zero earlier versions: the same live entries written once.
            VelqoraMap<String,String> fresh = new VelqoraMap<>(root.resolve("fresh"),TEXT,TEXT);
            fresh.putAll(expected);
            fresh.flush();
            fresh.compact();
            contents(expected, fresh);
            // Every manual compaction reclaims history, including history written
            // after an earlier compaction of a different state.
            VelqoraMap<String,String> repeat = new VelqoraMap<>(root.resolve("repeat"),TEXT,TEXT);
            repeat.putAll(Map.of("first","before 1st compaction","second","still present",
                "stale","removed after 1st compaction"));
            repeat.flush();
            repeat.compact();
            for (int i=0; i<48; i++) {
                repeat.put("first", "again-"+i+"z".repeat(256));
                repeat.put("later-"+i, "deleted-"+i);
                repeat.flush();
                repeat.remove("later-"+i);
                repeat.flush();
            }
            repeat.remove("stale");
            repeat.remove("second");
            repeat.flush();
            repeat.putAll(expected);
            repeat.flush();
            contents(expected, repeat);
            repeat.compact();
            contents(expected, repeat);
            Files.writeString(root.resolve("sizes.json"),
                "{\"fresh\":"+Files.size(root.resolve("fresh").resolve("velqoramap.log"))+
                ",\"repeat\":"+Files.size(root.resolve("repeat").resolve("velqoramap.log"))+"}");
            // Application key and value encodings that are not UTF-8 text.
            VelqoraMap<Integer,String> coded = new VelqoraMap<>(root.resolve("coded"),KEYS,VALUES);
            for (int i=0; i<8; i++) {
                coded.put(-7, "obsolete-"+i);
                coded.put(1000+i, "deleted");
                coded.flush();
                coded.remove(1000+i);
            }
            coded.putAll(CODED);
            coded.flush();
            coded.compact();
            contents(CODED, coded);
            // Current entries not yet requested durable when compaction is called.
            VelqoraMap<String,String> unflushed = new VelqoraMap<>(root.resolve("unflushed"),TEXT,TEXT);
            for (int round=0; round<3; round++) {
                for (int i=0; i<UNFLUSHED; i++) unflushed.put("u-"+i, "old-"+round);
                unflushed.flush();
                for (int i=0; i<UNFLUSHED; i++) {
                    if (i % 7 == 0) unflushed.remove("u-"+i);
                    else unflushed.put("u-"+i, "new-"+round);
                }
                unflushed.compact();
                unflushed.flush();
                contents(unflushedState(round), unflushed);
            }
            compactionExit();
        } else {
            for (String name : List.of("short", "long", "empty", "fresh", "repeat")) {
                try (var map = new VelqoraMap<>(root.resolve(name),TEXT,TEXT)) {
                    contents(name.equals("empty") ? Map.of() : expected, map);
                }
            }
            try (var map = new VelqoraMap<>(root.resolve("coded"),KEYS,VALUES)) {
                contents(CODED, map);
            }
            try (var map = new VelqoraMap<>(root.resolve("unflushed"),TEXT,TEXT)) {
                contents(unflushedState(2), map);
            }
        }
    ''', members=COMPACTION_SUPPORT + r'''
        static final Map<Integer,String> CODED = Map.of(-7,"latest 水", 42,"", 2147483647,"Ω🧭");
        static final int UNFLUSHED = 6000;
        static Map<String,String> unflushedState(int round) {
            Map<String,String> state = new HashMap<>();
            for (int i=0; i<UNFLUSHED; i++) if (i % 7 != 0) state.put("u-"+i, "new-"+round);
            return state;
        }
    ''')
    run_persistence_caller(caller, tmp_path, tmp_path, 'write')
    run_persistence_caller(caller, tmp_path, tmp_path, 'read')
    short = read_json_file(tmp_path / 'short.json')
    long = read_json_file(tmp_path / 'long.json')
    empty = read_json_file(tmp_path / 'empty.json')
    # No fixed bytes-per-entry, order, compression ratio, or requirement that
    # history was retained until this call: proactive reclamation is legitimate.
    assert long['after'] <= short['after'], (short, long)
    assert empty['after'] == 0, empty
    # Same live entries and encodings: no compacted log may exceed the one with
    # zero earlier versions (a relation between product outputs, not a size pin).
    sizes = read_json_file(tmp_path / 'sizes.json')
    for name, after in (('short', short['after']), ('long', long['after']),
                        ('repeat', sizes['repeat'])):
        assert after <= sizes['fresh'], (name, after, sizes)
    # Independent reading of the compacted application-encoded log.
    assert read_log_state(tmp_path / 'coded' / 'velqoramap.log') == {
        b'K' + struct.pack('<i', key): b'V\0' + value.encode('utf-16le')
        for key, value in {-7: 'latest 水', 42: '', 2147483647: 'Ω🧭'}.items()
    }


def test_completed_overlapping_mutations_survive_compaction(tmp_path, coverage_observation):
    caller = compile_persistence_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        Map<String,String> expected = new HashMap<>();
        for (int i=0; i<256; i++) expected.put("stable-"+i,"payload-"+i);
        for (int i=0; i<64; i++) {
            expected.put("update-"+i,"new-"+i);
            expected.put("insert-"+i,"added-"+i);
        }
        expected.put("held","held-v3");
        if (args[1].equals("read")) {
            try (var map = new VelqoraMap<>(root.resolve("store"),TEXT,TEXT)) {
                contents(expected,map);
            }
        } else {
            AtomicBoolean armed = new AtomicBoolean();
            CountDownLatch encoding = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            // A second, optional application gate holds the first encoding of
            // "held-v1" (by whichever component saves it), so that "held" can
            // change again and compaction can be requested while that earlier
            // change may still be unsaved. Its invocation is never required.
            AtomicBoolean heldOnce = new AtomicBoolean();
            CountDownLatch heldEntered = new CountDownLatch(1);
            CountDownLatch heldRelease = new CountDownLatch(1);
            Codec<String> codec = new Codec<>() {
                public byte[] encode(String value) throws IOException {
                    if (value.equals("held-v1") && heldOnce.compareAndSet(false, true)) {
                        heldEntered.countDown();
                        awaitGate(heldRelease);
                    } else if (armed.get()) {
                        encoding.countDown();
                        awaitGate(release);
                    }
                    return TEXT.encode(value);
                }
                public String decode(byte[] bytes) throws IOException { return TEXT.decode(bytes); }
            };
            VelqoraMap<String,String> map = new VelqoraMap<>(root.resolve("store"),TEXT,codec);
            for (int i=0; i<256; i++) map.put("stable-"+i,"payload-"+i);
            for (int i=0; i<64; i++) {
                map.put("update-"+i,"old-"+i);
                map.put("remove-"+i,"delete-"+i);
            }
            map.flush();
            armed.set(true);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            CountDownLatch invoked = new CountDownLatch(1);
            CountDownLatch mutationsDone = new CountDownLatch(1);
            long[] compactInterval = new long[2];
            long[][] intervals = new long[192][2];
            try {
                map.put("held","held-v1");
                heldEntered.await(2,TimeUnit.SECONDS);
                map.put("held","held-v2");
                Future<?> compact = pool.submit(() -> {
                    compactInterval[0] = System.nanoTime();
                    invoked.countDown();
                    try { map.compact(); }
                    finally { compactInterval[1] = System.nanoTime(); }
                    return null;
                });
                awaitGate(invoked);
                // Coordination only: let the compaction request get under way
                // before the held encoding is allowed to finish.
                Thread.sleep(150);
                heldRelease.countDown();
                Future<?> mutations = pool.submit(() -> {
                    awaitGate(invoked);
                    // The optional application gate improves repeatability on
                    // encoders that run here; its invocation is never required.
                    encoding.await(300,TimeUnit.MILLISECONDS);
                    try {
                        for (int i=0; i<64; i++) {
                            intervals[3*i][0] = System.nanoTime();
                            map.put("insert-"+i,"added-"+i);
                            intervals[3*i][1] = System.nanoTime();
                            intervals[3*i+1][0] = System.nanoTime();
                            map.put("update-"+i,"new-"+i);
                            intervals[3*i+1][1] = System.nanoTime();
                            intervals[3*i+2][0] = System.nanoTime();
                            map.remove("remove-"+i);
                            intervals[3*i+2][1] = System.nanoTime();
                        }
                        map.put("held","held-v3");
                    } finally { mutationsDone.countDown(); }
                    return null;
                });
                // Release even if mutations serialize behind compaction. This
                // deadline is coordination only, not a performance assertion.
                mutationsDone.await(1,TimeUnit.SECONDS);
                release.countDown();
                compact.get(30,TimeUnit.SECONDS);
                mutations.get(30,TimeUnit.SECONDS);
            } finally {
                heldRelease.countDown();
                release.countDown();
                stopPool(pool);
            }
            contents(expected,map);
            map.flush();
            StringJoiner recorded = new StringJoiner(",","[","]");
            for (long[] interval : intervals)
                recorded.add("["+interval[0]+","+interval[1]+"]");
            Files.writeString(root.resolve("overlap.json"),
                "{\"compact\":["+compactInterval[0]+","+compactInterval[1]+
                "],\"mutations\":"+recorded+"}");
            compactionExit();
        }
    ''', members=COMPACTION_SUPPORT)
    run_persistence_caller(caller, tmp_path, tmp_path, 'write')
    run_persistence_caller(caller, tmp_path, tmp_path, 'read')
    report = read_json_file(tmp_path / 'overlap.json')
    begin, end = report['compact']
    observed = [
        any(begin <= a <= b <= end for a, b in report['mutations'][kind::3])
        for kind in range(3)
    ]
    coverage_observation('FP-02.02', 'completed insertion, replacement and deletion during compaction',
        observed=all(observed),
        reason='Independent recovery passed; only mutations inside the recorded compaction interval '
               'establish the overlap antecedent. Serialization and encoded-byte reuse are permitted.',
        evidence={'observed_mutation_kinds': observed, 'intervals': report})
    if not all(observed):
        pytest.skip('UNCOVERED F03.T02: completed insertion, replacement and deletion '
                    f'overlap not all observed; observed={observed}; see coverage-observations.json')


def test_compaction_encoding_failure_preserves_durable_log(tmp_path, coverage_observation):
    caller = compile_persistence_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        Map<String,String> expected = new HashMap<>();
        for (int i=0; i<12; i++) expected.put("key-"+i,"current-"+i);
        if (args[1].equals("read")) {
            try (var map = new VelqoraMap<>(root.resolve("store"),TEXT,TEXT)) {
                contents(expected,map);
            }
        } else {
            AtomicBoolean armed = new AtomicBoolean();
            AtomicBoolean triggered = new AtomicBoolean();
            AtomicInteger encodings = new AtomicInteger();
            Codec<String> codec = new Codec<>() {
                public byte[] encode(String value) throws IOException {
                    if (armed.get() && encodings.incrementAndGet() >= 3) {
                        triggered.set(true);
                        throw new IOException("Application encoding resource unavailable");
                    }
                    return TEXT.encode(value);
                }
                public String decode(byte[] bytes) throws IOException { return TEXT.decode(bytes); }
            };
            VelqoraMap<String,String> map = new VelqoraMap<>(root.resolve("store"),TEXT,codec);
            for (int i=0; i<12; i++) map.put("key-"+i,"old-"+i);
            map.put("deleted","must not return");
            map.flush();
            map.putAll(expected);
            map.remove("deleted");
            map.flush();
            contents(expected,map);
            armed.set(true);
            IOException reported = null;
            try { map.compact(); }
            catch (IOException failure) { reported = failure; }
            if (triggered.get()) {
                if (reported == null) throw new AssertionError("Compaction swallowed encoding failure");
            } else if (reported != null) {
                throw reported;
            }
            Files.writeString(root.resolve("failure.json"),
                "{\"triggered\":"+triggered.get()+",\"reported\":"+(reported!=null)+"}");
            // Do not disarm the encoder, flush, close, or run shutdown hooks:
            // the fresh JVM must recover the durable state left at this point.
            compactionExit();
        }
    ''', members=COMPACTION_SUPPORT)
    run_persistence_caller(caller, tmp_path, tmp_path, 'write')
    run_persistence_caller(caller, tmp_path, tmp_path, 'read')
    report = read_json_file(tmp_path / 'failure.json')
    coverage_observation('FP-03.03', 'compaction encoding failure and durable recovery',
        observed=report['triggered'],
        reason='Independent recovery passed; the failure branch is observed only if the '
               'application encoder actually failed. Encoded-byte reuse is permitted.',
        evidence=report)
    if not report['triggered']:
        pytest.skip('UNCOVERED F03.T03: compaction did not trigger encoding failure; '
                    'encoded-byte reuse is permitted; see coverage-observations.json')
    assert report['reported'], report
