# feature: F02
"""The nine planned acceptance checks for durability and restart recovery."""

import struct

from F02_helpers import (
    compile_persistence_caller, log_record, read_log_state, run_persistence_caller,
)


def test_application_encodings_and_unicode(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        int phase = Integer.parseInt(args[1]);
        for (int form = 0; form < 3; form++) {
            Path dir = root.resolve("custom-" + form).resolve("nested");
            try (VelqoraMap<Integer,String> map = form == 0 ? new VelqoraMap<>(dir, KEYS, VALUES)
                    : form == 1 ? VelqoraMap.open(dir, KEYS, VALUES)
                    : VelqoraMap.open(dir.toString(), KEYS, VALUES)) {
                if (phase == 0) {
                    contents(Map.of(), map);
                    map.putAll(Map.of(-19,"café 水 🌱", 730,"", 5,"discard"));
                    map.flush();
                    map.put(-19,"updated Ω\u0000🧭");
                    map.remove(5);
                    map.flush();
                } else {
                    contents(Map.of(-19,"updated Ω\u0000🧭", 730,""), map);
                }
            }
        }
        for (int form = 0; form < 2; form++) {
            Path dir = root.resolve("unicode-" + form);
            try (VelqoraMap<String,String> map = form == 0 ? VelqoraMap.strings(dir)
                    : VelqoraMap.strings(dir.toString())) {
                Map<String,String> expected = Map.of("clé 水🧭", "line\nΩ\u0000🌱", "", "空", "é", "");
                if (phase == 0) { map.putAll(expected); map.flush(); }
                contents(expected, map);
            }
        }
        if (phase == 1) {
            try (VelqoraMap<Integer,String> map = VelqoraMap.open(root.resolve("independent"), KEYS, VALUES)) {
                contents(Map.of(81,"restored 独立", -2,""), map);
            }
        }
    ''')
    root = tmp_path / 'stores'
    run_persistence_caller(caller, tmp_path, root, 0)
    expected = {
        b'K' + struct.pack('<i', -19): b'V\0' + 'updated Ω\0🧭'.encode('utf-16le'),
        b'K' + struct.pack('<i', 730): b'V\0',
    }
    for form in range(3):
        assert read_log_state(root / f'custom-{form}' / 'nested' / 'velqoramap.log') == expected
    unicode = {'clé 水🧭': 'line\nΩ\0🌱', '': '空', 'é': ''}
    for form in range(2):
        assert read_log_state(root / f'unicode-{form}' / 'velqoramap.log') == {
            k.encode('utf-8'): v.encode('utf-8') for k, v in unicode.items()
        }
    independent = root / 'independent'
    independent.mkdir()
    independent.joinpath('velqoramap.log').write_bytes(b''.join([
        log_record(b'K' + struct.pack('<i', 81), b'V\0' + 'old'.encode('utf-16le')),
        log_record(b'K' + struct.pack('<i', 9), b'V\0' + 'deleted'.encode('utf-16le')),
        log_record(b'K' + struct.pack('<i', 81), b'V\0' + 'restored 独立'.encode('utf-16le')),
        log_record(b'K' + struct.pack('<i', 9), None),
        log_record(b'K' + struct.pack('<i', -2), b'V\0'),
    ]))
    run_persistence_caller(caller, tmp_path, root, 1)


def test_checkpoints_recover_all_mutation_families(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        int phase = Integer.parseInt(args[1]);
        List<Map<String,String>> states = List.of(
            Map.of(),
            Map.ofEntries(Map.entry("put","old"), Map.entry("replace","r"), Map.entry("cas","c"),
                Map.entry("remove","d"), Map.entry("conditional","d"), Map.entry("compute","5"),
                Map.entry("present","7"), Map.entry("merge","9"), Map.entry("compute-delete","x"),
                Map.entry("present-delete","x"), Map.entry("merge-delete","x"), Map.entry("keep","safe")),
            Map.ofEntries(Map.entry("put","new"), Map.entry("replace","rr"), Map.entry("cas","cc"),
                Map.entry("compute","15"), Map.entry("present","70"), Map.entry("merge","94"),
                Map.entry("keep","safe"), Map.entry("insert","i"), Map.entry("absent","a"),
                Map.entry("merge-new","m"), Map.entry("compute-new","n")),
            Map.ofEntries(Map.entry("put","new!"), Map.entry("replace","rr!"), Map.entry("cas","cc!"),
                Map.entry("compute","15!"), Map.entry("present","70!"), Map.entry("merge","94!"),
                Map.entry("keep","safe!"), Map.entry("insert","i!"), Map.entry("absent","a!"),
                Map.entry("merge-new","m!"), Map.entry("compute-new","n!")),
            Map.ofEntries(Map.entry("put","new!"), Map.entry("cas","cc!"), Map.entry("compute","15!"),
                Map.entry("present","70!"), Map.entry("merge","94!"), Map.entry("keep","safe!"),
                Map.entry("absent","a!"), Map.entry("merge-new","m!"), Map.entry("compute-new","n!"),
                Map.entry("batch","b"), Map.entry("second","s")),
            Map.of(), Map.of("after-clear","survives"));
        VelqoraMap<String,String> map = new VelqoraMap<>(Path.of(args[0]), TEXT, TEXT);
        contents(states.get(phase), map);
        switch (phase) {
            case 0 -> map.putAll(states.get(1));
            case 1 -> {
                map.put("put","new");
                map.putIfAbsent("insert","i"); map.putIfAbsent("keep","wrong");
                map.replace("replace","rr"); map.replace("cas","c","cc");
                map.replace("keep","wrong","wrong"); map.replace("missing","wrong");
                map.remove("remove"); map.remove("conditional","d"); map.remove("keep","wrong");
                map.compute("compute",(k,v)->Integer.toString(Integer.parseInt(v)*3));
                map.compute("compute-new",(k,v)->"n");
                map.compute("compute-delete",(k,v)->null);
                map.computeIfAbsent("absent",k->"a"); map.computeIfAbsent("keep",k->"wrong");
                map.computeIfPresent("present",(k,v)->v+"0");
                map.computeIfPresent("present-delete",(k,v)->null);
                map.merge("merge","4",String::concat); map.merge("merge-new","m",String::concat);
                map.merge("merge-delete","unused",(a,b)->null);
            }
            case 2 -> map.replaceAll((k,v)->v+"!");
            case 3 -> {
                map.removeAll(List.of("replace","insert","missing"));
                map.putAll(Map.of("batch","b","second","s"));
            }
            case 4 -> map.clear();
            case 5 -> map.put("after-clear","survives");
            case 6 -> { }
            default -> throw new AssertionError("Unknown phase");
        }
        checkpointExit(map);
    ''')
    for phase in range(7):
        run_persistence_caller(caller, tmp_path, tmp_path / 'store', phase)


def test_close_saves_and_repeated_close_needs_no_application_action(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        Path dir = Path.of(args[0]);
        if (args[1].equals("write")) {
            try (var seed = new VelqoraMap<>(dir,TEXT,TEXT)) {
                seed.putAll(Map.ofEntries(Map.entry("replace","old"), Map.entry("cas","old"),
                    Map.entry("delete","old"), Map.entry("conditional-delete","old"),
                    Map.entry("computed","old"), Map.entry("present","old"),
                    Map.entry("combined","old"), Map.entry("compute-delete","old"),
                    Map.entry("merge-delete","old"), Map.entry("bulk-delete","old"),
                    Map.entry("bulk-keep","old")));
            }
            // One application encoder serves keys and values; it waits until the
            // application releases its resource. Encoding may start at mutation time
            // or only once close is requested: both schedules are permitted.
            GatedText codec = new GatedText();
            VelqoraMap<String,String> map = new VelqoraMap<>(dir, codec, codec);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                Future<?> writes = pool.submit(() -> {
                    map.put("closed","pending Ω");
                    map.putIfAbsent("inserted","new");
                    map.replace("replace","replacement"); map.replace("cas","old","conditional");
                    map.remove("delete"); map.remove("conditional-delete","old");
                    map.compute("computed",(k,v)->v+"-computed");
                    map.compute("compute-delete",(k,v)->null);
                    map.computeIfAbsent("absent",k->"created");
                    map.computeIfPresent("present",(k,v)->v+"-present");
                    map.merge("combined","-combined",String::concat);
                    map.merge("merge-delete","unused",(a,b)->null);
                    map.putAll(Map.of("batch-a","a","batch-b","b"));
                    map.removeAll(List.of("bulk-delete","missing"));
                    map.replaceAll((k,v)->"saved:"+v);
                    return null;
                });
                // Ordinary mutations complete even if an encoder is already waiting.
                writes.get(10, TimeUnit.SECONDS);
                CountDownLatch closing = new CountDownLatch(1);
                Future<?> close = pool.submit(() -> { closing.countDown(); map.close(); return null; });
                awaitGate(closing);
                // Saving requires the application encoder; by now it must be waiting.
                awaitGate(codec.entered);
                pending(close);
                codec.release.countDown();
                close.get(20, TimeUnit.SECONDS);
                codec.forbidden.set(true);
                int completedActions = codec.invocations.get();
                map.close();
                map.close();
                eq(completedActions,codec.invocations.get());
            } finally { codec.release.countDown(); stopPool(pool); }
            Path clearDir = dir.resolveSibling("cleared");
            try (var seed = new VelqoraMap<>(clearDir,TEXT,TEXT)) {
                seed.putAll(Map.of("one","old","two","old"));
            }
            try (var clearing = new VelqoraMap<>(clearDir,TEXT,TEXT)) { clearing.clear(); }
        } else {
            try (VelqoraMap<String,String> map = new VelqoraMap<>(dir, TEXT, TEXT)) {
                contents(Map.ofEntries(Map.entry("closed","saved:pending Ω"),
                    Map.entry("replace","saved:replacement"), Map.entry("cas","saved:conditional"),
                    Map.entry("computed","saved:old-computed"), Map.entry("present","saved:old-present"),
                    Map.entry("combined","saved:old-combined"), Map.entry("bulk-keep","saved:old"),
                    Map.entry("inserted","saved:new"), Map.entry("absent","saved:created"),
                    Map.entry("batch-a","saved:a"), Map.entry("batch-b","saved:b")), map);
            }
            try (var cleared = new VelqoraMap<>(dir.resolveSibling("cleared"),TEXT,TEXT)) {
                contents(Map.of(),cleared);
            }
        }
    ''')
    run_persistence_caller(caller, tmp_path, tmp_path / 'store', 'write')
    run_persistence_caller(caller, tmp_path, tmp_path / 'store', 'read')


def test_waiting_encoder_leaves_local_access_available_but_blocks_checkpoint(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        Path dir = Path.of(args[0]);
        if (args[1].equals("write")) {
            // One application encoder serves keys and values. Encoding may begin at
            // the mutation or only once durability is requested; both are permitted.
            GatedText codec = new GatedText();
            VelqoraMap<String,String> map = new VelqoraMap<>(dir, codec, codec);
            ExecutorService pool = Executors.newFixedThreadPool(3);
            try {
                pool.submit(() -> map.put("first","one")).get(10, TimeUnit.SECONDS);
                CountDownLatch checkpointing = new CountDownLatch(1);
                Future<?> flush = pool.submit(() -> { checkpointing.countDown(); map.flush(); return null; });
                awaitGate(checkpointing);
                // The requested checkpoint needs encoding, so the encoder is now waiting.
                awaitGate(codec.entered);
                Future<?> access = pool.submit(() -> {
                    eq("one",map.get("first"));
                    eq("fallback",map.getOrDefault("missing","fallback"));
                    for (int i=0; i<200; i++) eq(null,map.put("wait-"+i,"w"+i));
                    eq(null,map.putIfAbsent("absent","a"));
                    eq("w0",map.replace("wait-0","r"));
                    eq(true,map.replace("wait-1","w1","cas"));
                    eq("w2",map.remove("wait-2"));
                    eq(true,map.remove("wait-3","w3"));
                    eq("w4c",map.compute("wait-4",(k,v)->v+"c"));
                    eq("x",map.computeIfAbsent("created",k->"x"));
                    eq("w5p",map.computeIfPresent("wait-5",(k,v)->v+"p"));
                    eq("w6m",map.merge("wait-6","m",String::concat));
                    Map<String,String> batch = new HashMap<>();
                    for (int i=0; i<100; i++) batch.put("batch-"+i,"b"+i);
                    map.putAll(batch);
                    eq(true,map.removeAll(List.of("batch-0","wait-7","missing")));
                    map.put("removed","transient"); map.remove("removed");
                    contents(waited(),map);
                    return null;
                });
                access.get(10, TimeUnit.SECONDS);
                pending(flush);
                codec.release.countDown();
                flush.get(20, TimeUnit.SECONDS);
                checkpointExit(map);
            } finally { codec.release.countDown(); stopPool(pool); }
        } else {
            try (VelqoraMap<String,String> map = new VelqoraMap<>(dir,TEXT,TEXT)) {
                contents(waited(),map);
            }
        }
    ''', members=r'''
        static Map<String,String> waited() {
            // Independent oracle: the FP-01 rules applied to the operations above.
            Map<String,String> expected = new HashMap<>();
            expected.put("first","one");
            for (int i=0; i<200; i++) expected.put("wait-"+i,"w"+i);
            expected.put("wait-0","r"); expected.put("wait-1","cas");
            expected.remove("wait-2"); expected.remove("wait-3");
            expected.put("wait-4","w4c"); expected.put("wait-5","w5p"); expected.put("wait-6","w6m");
            expected.remove("wait-7");
            expected.put("absent","a"); expected.put("created","x");
            for (int i=1; i<100; i++) expected.put("batch-"+i,"b"+i);
            return expected;
        }
    ''')
    run_persistence_caller(caller, tmp_path, tmp_path / 'store', 'write')
    run_persistence_caller(caller, tmp_path, tmp_path / 'store', 'read')


def test_incomplete_tail_preserves_prefix_and_future_writes(tmp_path):
    # Every byte boundary covers partial length headers as well as key/value data.
    # This is one recovery obligation, not separately scored parameter cases.
    prefix = (log_record(b'alive', b'old') + log_record(b'deleted', b'gone') +
              log_record(b'alive', b'latest') + log_record(b'deleted', None))
    tail = log_record(b'unfinished', b'payload')
    for cut in range(1, len(tail)):
        directory = tmp_path / f'cut-{cut}'
        directory.mkdir()
        (directory / 'velqoramap.log').write_bytes(prefix + tail[:cut])
    caller = compile_persistence_caller(tmp_path, r'''
        for (int cut=1; cut<Integer.parseInt(args[1]); cut++) {
            Path dir = Path.of(args[0]).resolve("cut-"+cut);
            try (VelqoraMap<String,String> map = new VelqoraMap<>(dir,TEXT,TEXT)) {
                if (args[2].equals("repair")) {
                    contents(Map.of("alive","latest"),map);
                    map.put("new","after recovery");
                    map.flush();
                } else contents(Map.of("alive","latest","new","after recovery"),map);
            }
        }
    ''')
    run_persistence_caller(caller, tmp_path, tmp_path, len(tail), 'repair')
    run_persistence_caller(caller, tmp_path, tmp_path, len(tail), 'read')


def test_field_length_bounds_and_corruption_precedence(tmp_path):
    limit = 256 * 1024 * 1024
    prefix = log_record(b'valid', b'kept')
    invalid = []
    for field in ('key', 'value'):
        for length in (-2, -1, limit + 1, 2**31 - 1):
            if field == 'value' and length == -1:
                continue  # This is the recognized deletion marker, checked below.
            tail = struct.pack('>i', length)
            if field == 'value':
                tail = struct.pack('>i', 1) + b'k' + tail
            directory = tmp_path / f'invalid-{len(invalid)}'
            directory.mkdir()
            (directory / 'velqoramap.log').write_bytes(prefix + tail)
            invalid.append(directory)
    for field in ('key', 'value'):
        directory = tmp_path / f'partial-{field}'
        directory.mkdir()
        tail = struct.pack('>i', limit)
        if field == 'value':
            tail = struct.pack('>i', 1) + b'k' + tail
        (directory / 'velqoramap.log').write_bytes(prefix + tail)
    legal = tmp_path / 'legal'
    legal.mkdir()
    # Sparse zero-filled fields are complete real input, without keeping a second
    # 512 MiB copy in the Python process. The application decoder checks all bytes.
    with (legal / 'velqoramap.log').open('wb') as stream:
        for key_size, value_size in ((limit, 3), (2, limit), (0, 0), (4, 5)):
            stream.write(struct.pack('>i', key_size))
            stream.seek(key_size, 1)
            stream.write(struct.pack('>i', value_size))
            stream.seek(value_size, 1)
        stream.write(log_record(b'\0' * 4, None))
    caller = compile_persistence_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        for (int n=0; n<Integer.parseInt(args[1]); n++) {
            Path dir = root.resolve("invalid-"+n);
            rejects(IOException.class, () -> { try (var map = new VelqoraMap<>(dir,TEXT,TEXT)) { } });
        }
        for (String field : List.of("key","value")) {
            try (var map = new VelqoraMap<>(root.resolve("partial-"+field),TEXT,TEXT)) {
                contents(Map.of("valid","kept"),map);
            }
        }
        Codec<Integer> lengths = new Codec<>() {
            public byte[] encode(Integer value) { return new byte[value]; }
            public Integer decode(byte[] bytes) throws IOException {
                for (byte b : bytes) if (b != 0) throw new IOException("Unexpected field contents");
                return bytes.length;
            }
        };
        try (var map = new VelqoraMap<>(root.resolve("legal"),lengths,lengths)) {
            contents(Map.of(268435456,3, 2,268435456, 0,0),map);
        }
    ''')
    # Two legal 256 MiB fields: the heap leaves room for any reading strategy, so the
    # verdict rests on the declared-length rules alone.
    run_persistence_caller(caller, tmp_path, tmp_path, len(invalid), heap='2g')


def test_unusable_storage_is_reported_at_open(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        Path good = root.resolve("good/nested");
        try (var map = VelqoraMap.strings(good)) { map.put("works","persisted"); map.flush(); }
        try (var map = new VelqoraMap<>(good,TEXT,TEXT)) { contents(Map.of("works","persisted"),map); }
        Path file = Files.writeString(root.resolve("ordinary-file"),"not a directory");
        Path badLog = Files.createDirectories(root.resolve("log-is-directory"));
        Files.createDirectory(badLog.resolve("velqoramap.log"));
        for (Path bad : List.of(file, file.resolve("child"), badLog)) {
            rejects(IOException.class, () -> { try (var map = new VelqoraMap<>(bad,TEXT,TEXT)) { } });
            rejects(UncheckedIOException.class, () -> { try (var map = VelqoraMap.open(bad,TEXT,TEXT)) { } });
            rejects(UncheckedIOException.class, () -> { try (var map = VelqoraMap.strings(bad.toString())) { } });
        }
    ''')
    run_persistence_caller(caller, tmp_path, tmp_path)


def test_encoder_and_real_io_failures_remain_visible(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        if (args[1].equals("io")) {
            VelqoraMap<String,String> map = new VelqoraMap<>(root,TEXT,TEXT);
            map.putAll(BASE); map.flush();
            contents(BASE,map);
            failedPersistence(map, () -> map.put("overflow","z".repeat(131072)));
        } else {
            // "deletion": the key encoder fails while the removal is being saved.
            for (String kind : List.of("key","value","runtime","deletion")) {
                AtomicBoolean failing = new AtomicBoolean();
                Codec<String> codec = new Codec<>() {
                    public byte[] encode(String text) throws IOException {
                        if (failing.get()) {
                            if (kind.equals("runtime")) throw new IllegalArgumentException("Application encoding failed");
                            throw new IOException("Application resource unavailable");
                        }
                        return TEXT.encode(text);
                    }
                    public String decode(byte[] bytes) throws IOException { return TEXT.decode(bytes); }
                };
                boolean keyFailure = kind.equals("key") || kind.equals("deletion");
                VelqoraMap<String,String> map = new VelqoraMap<>(root.resolve(kind),
                    keyFailure ? codec : TEXT, keyFailure ? TEXT : codec);
                map.putAll(BASE); map.flush();
                contents(BASE,map);
                failing.set(true);
                failedPersistence(map, kind.equals("deletion") ? () -> map.remove("doomed")
                    : () -> map.put("next","cannot encode"));
            }
            // No checkpoint before close: the failure may first arise while close
            // saves, and close must still not report success.
            Codec<String> refusing = new Codec<>() {
                public byte[] encode(String text) throws IOException {
                    if (text.equals("unsaveable")) throw new IOException("Application resource unavailable");
                    return TEXT.encode(text);
                }
                public String decode(byte[] bytes) throws IOException { return TEXT.decode(bytes); }
            };
            VelqoraMap<String,String> closing = new VelqoraMap<>(root.resolve("close-only"),TEXT,refusing);
            try { closing.put("last","unsaveable"); }
            catch (UncheckedIOException immediate) { /* immediate delivery is also permitted */ }
            rejects(IOException.class,closing::close);
        }
    ''', members=r'''
        static final Map<String,String> BASE = Map.of("baseline","saved","doomed","saved",
            "swap","old","cas","old","cond","old","present","old","merge","old");
        static void failedPersistence(VelqoraMap<String,String> map, Action trigger) throws Exception {
            UncheckedIOException immediate = null;
            try { trigger.run(); }
            catch (UncheckedIOException failure) { immediate = failure; }
            // Immediate or deferred delivery is acceptable; both must retain the
            // failure for every subsequent durability request. Preserve an early
            // report in the diagnostics if any of those observations fail.
            try {
                rejects(IOException.class,map::flush);
                rejects(IOException.class,map::flush);
                rejects(UncheckedIOException.class,()->map.put("later","value"));
                rejects(UncheckedIOException.class,()->map.putAll(Map.of("batch","value")));
                rejects(UncheckedIOException.class,()->map.remove("baseline"));
                // Conditional and computed mutations whose conditions are met are
                // attempts to record mutations too (FP-01.02/01.03 forms).
                rejects(UncheckedIOException.class,()->map.putIfAbsent("fresh-1","v"));
                rejects(UncheckedIOException.class,()->map.replace("swap","new"));
                rejects(UncheckedIOException.class,()->map.replace("cas","old","new"));
                rejects(UncheckedIOException.class,()->map.remove("cond","old"));
                rejects(UncheckedIOException.class,()->map.computeIfAbsent("fresh-2",k->"v"));
                rejects(UncheckedIOException.class,()->map.computeIfPresent("present",(k,v)->v+"!"));
                rejects(UncheckedIOException.class,()->map.compute("fresh-3",(k,v)->"v"));
                rejects(UncheckedIOException.class,()->map.merge("merge","!",String::concat));
                rejects(UncheckedIOException.class,()->map.replaceAll((k,v)->v+"?"));
                rejects(UncheckedIOException.class,map::clear);
                rejects(IOException.class,map::flush);
                rejects(IOException.class,map::close);
            } catch (Exception | AssertionError failure) {
                if (immediate != null) failure.addSuppressed(immediate);
                throw failure;
            }
        }
    ''')
    run_persistence_caller(caller, tmp_path, tmp_path / 'encoders', 'encode')
    run_persistence_caller(caller, tmp_path, tmp_path / 'limited', 'io', file_limit=65536)


def test_convenience_maps_save_during_ordinary_shutdown(tmp_path):
    caller = compile_persistence_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        if (args[1].equals("write")) {
            CountDownLatch shuttingDown = new CountDownLatch(1);
            Runtime.getRuntime().addShutdownHook(new Thread(shuttingDown::countDown));
            Codec<String> delayed = new Codec<>() {
                public byte[] encode(String value) throws IOException {
                    awaitGate(shuttingDown);
                    try { Thread.sleep(300); }
                    catch (InterruptedException failure) { throw new IOException(failure); }
                    return TEXT.encode(value);
                }
                public String decode(byte[] bytes) throws IOException { return TEXT.decode(bytes); }
            };
            VelqoraMap<String,String> first = VelqoraMap.open(root.resolve("custom-path"),TEXT,delayed);
            VelqoraMap<String,String> second = VelqoraMap.open(root.resolve("custom-text").toString(),TEXT,delayed);
            first.put("pending","shutdown Ω"); second.put("other","shutdown 🧭");
            // Two convenience maps with equal contents: closing one must not
            // withdraw the other, still-pending one from shutdown saving.
            VelqoraMap<String,String> twinClosed = VelqoraMap.open(root.resolve("twin-closed"),TEXT,TEXT);
            // Its encoder finishes well after the other maps' shutdown saving, so
            // only shutdown handling that still includes this map can save it.
            Codec<String> slower = new Codec<>() {
                public byte[] encode(String value) throws IOException {
                    awaitGate(shuttingDown);
                    try { Thread.sleep(2000); }
                    catch (InterruptedException failure) { throw new IOException(failure); }
                    return TEXT.encode(value);
                }
                public String decode(byte[] bytes) throws IOException { return TEXT.decode(bytes); }
            };
            VelqoraMap<String,String> twinLive = VelqoraMap.open(root.resolve("twin-live"),TEXT,slower);
            twinClosed.put("twin","equal 水"); twinLive.put("twin","equal 水");
            eq(twinClosed, twinLive);
            twinClosed.close();
            VelqoraMap<String,String> strings = VelqoraMap.strings(root.resolve("strings"));
            for (int i=0; i<256; i++) strings.put("key-"+i,"value-"+i+" 水");
            // Return normally: no explicit durability/close, and encoding remains
            // unfinished until JVM shutdown begins. The application hook only
            // releases its own resource; it never waits for or saves product data.
        } else {
            try (var first = VelqoraMap.strings(root.resolve("custom-path"));
                 var second = VelqoraMap.strings(root.resolve("custom-text"));
                 var strings = VelqoraMap.strings(root.resolve("strings"))) {
                contents(Map.of("pending","shutdown Ω"),first);
                contents(Map.of("other","shutdown 🧭"),second);
                Map<String,String> expected = new HashMap<>();
                for (int i=0; i<256; i++) expected.put("key-"+i,"value-"+i+" 水");
                contents(expected,strings);
            }
            for (String twin : List.of("twin-closed","twin-live")) {
                try (var map = VelqoraMap.strings(root.resolve(twin))) {
                    contents(Map.of("twin","equal 水"),map);
                }
            }
        }
    ''')
    run_persistence_caller(caller, tmp_path, tmp_path / 'stores', 'write')
    run_persistence_caller(caller, tmp_path, tmp_path / 'stores', 'read')
