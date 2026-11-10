# feature: F10
"""The eleven planned live HTTP acceptance checks."""

from _helpers import parse_json
from F02_helpers import read_log_state, compile_persistence_caller, run_persistence_caller
from F10_helpers import compile_http_caller, run_http_caller, run_http_scenario, read_rows_wire


# Application-side request variants on one HTTP/1.1 client, which keeps connections
# alive between requests. A streamed body has unknown length (chunked), so the
# service cannot learn its size from a declared Content-Length.
APPLICATION_REQUESTS = r'''
    static final HttpClient KEPT_ALIVE = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(5)).build();
    static HttpResponse<byte[]> keptAlive(VelqoraMapHttpServer<?,?> server, String method, String path,
                                          HttpRequest.BodyPublisher body, int expected,
                                          String... headers) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+server.port()+path))
            .timeout(Duration.ofSeconds(40)).method(method,body);
        if (headers.length != 0) builder.headers(headers);
        var response = KEPT_ALIVE.send(builder.build(),HttpResponse.BodyHandlers.ofByteArray());
        if (expected != response.statusCode())
            throw new AssertionError(method+" "+path+": expected "+expected+", got "+response.statusCode());
        return response;
    }
    static HttpResponse<byte[]> keptAlive(VelqoraMapHttpServer<?,?> server, String method, String path,
                                          byte[] body, int expected, String... headers) throws Exception {
        return keptAlive(server,method,path,HttpRequest.BodyPublishers.ofByteArray(body),expected,headers);
    }
    static HttpResponse<byte[]> streamed(VelqoraMapHttpServer<?,?> server, String method, String path,
                                         byte[] body, int expected) throws Exception {
        var publisher = HttpRequest.BodyPublishers.ofInputStream(()->new ByteArrayInputStream(body));
        if (publisher.contentLength() >= 0)
            throw new AssertionError("Streamed request unexpectedly declares its length");
        return keptAlive(server,method,path,publisher,expected);
    }
    // A raw HTTP/1.1 exchange whose body is written concurrently with reading the reply,
    // so an early reply (before the body was consumed) and a late one are both observed;
    // write failures after the service stops reading are expected and ignored.
    record RawReply(int status, Map<String,String> headers) {}
    static RawReply raw(VelqoraMapHttpServer<?,?> server, String method, String path, int length) throws Exception {
        try (var socket = new Socket("127.0.0.1",server.port())) {
            socket.setSoTimeout(60000);
            var out = socket.getOutputStream();
            Thread writer = new Thread(() -> {
                try {
                    out.write(utf(method+" "+path+" HTTP/1.1\r\nHost: 127.0.0.1:"+server.port()
                        +"\r\nContent-Length: "+length+"\r\nConnection: close\r\n\r\n"));
                    byte[] chunk = new byte[1<<20]; Arrays.fill(chunk,(byte)'!');
                    for (int sent=0; sent<length; sent+=chunk.length)
                        out.write(chunk,0,Math.min(chunk.length,length-sent));
                    out.flush();
                } catch (IOException ignored) { /* the service may stop reading early */ }
            });
            writer.setDaemon(true); writer.start();
            var in = new BufferedReader(new InputStreamReader(socket.getInputStream(),StandardCharsets.ISO_8859_1));
            String statusLine = in.readLine();
            if (statusLine == null) throw new AssertionError("No reply to "+method+" "+path);
            String[] parts = statusLine.split(" ");
            Map<String,String> headers = new HashMap<>();
            for (String line = in.readLine(); line != null && !line.isEmpty(); line = in.readLine()) {
                int colon = line.indexOf(':');
                if (colon > 0) headers.put(line.substring(0,colon).trim().toLowerCase(Locale.ROOT),line.substring(colon+1).trim());
            }
            socket.close(); writer.join(30000);
            return new RawReply(Integer.parseInt(parts[1]),headers);
        }
    }
'''


def test_entry_routes_and_map_isolation(tmp_path):
    run_http_scenario(tmp_path, r'''
        try (var root = VelqoraMap.<String,String>memory();
             var numbers = VelqoraMap.<Integer,String>memory();
             var other = VelqoraMap.<String,String>memory();
             var server = VelqoraMapHttpServer.builder(root,TEXT,TEXT)
                 .map("numbers",numbers,KEYS,VALUES).map("other",other,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
            root.put("shared","root-only"); other.put("shared","other-only");
            String key = "clé/水 ?\u0000Ω";
            String route = path("",utf(key));
            status(server,"PUT",route,utf("value\n🧭"),204);
            bytes(utf("value\n🧭"),status(server,"GET",route,new byte[0],200).body());
            contents(Map.of("shared","root-only",key,"value\n🧭"),root);
            String numberRoute = path("/maps/numbers",KEYS.encode(-79));
            status(server,"PUT",numberRoute,VALUES.encode("different 水"),204);
            bytes(VALUES.encode("different 水"),status(server,"GET",numberRoute,new byte[0],200).body());
            contents(Map.of(-79,"different 水"),numbers);
            String otherRoute = path("/maps/other",utf("shared"));
            status(server,"PUT",otherRoute,utf("replacement"),204);
            bytes(utf("replacement"),status(server,"GET",otherRoute,new byte[0],200).body());
            contents(Map.of("shared","replacement"),other);
            contents(Map.of("shared","root-only",key,"value\n🧭"),root);
            status(server,"DELETE",numberRoute,new byte[0],204);
            status(server,"DELETE",route,new byte[0],204);
            contents(Map.of(),numbers); contents(Map.of("shared","root-only"),root);
            contents(Map.of("shared","replacement"),other);
            for (String missing : List.of(route,numberRoute,path("/maps/other",utf("absent")))) {
                error(server,"GET",missing,new byte[0],404);
                error(server,"DELETE",missing,new byte[0],404);
            }
            for (String missing : List.of("/missing", "/maps/unknown/entries/aA", "/maps/other/missing"))
                error(server,"GET",missing,new byte[0],404);
        }
        try (var map = VelqoraMap.<String,String>memory();
             var server = VelqoraMapHttpServer.builder().map("only",map,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
            String route = path("/maps/only",utf("standalone"));
            status(server,"PUT",route,utf("named"),204);
            bytes(utf("named"),status(server,"GET",route,new byte[0],200).body());
            error(server,"GET",path("",utf("standalone")),new byte[0],404);
            contents(Map.of("standalone","named"),map);
        }
    ''')


def test_binary_batches_apply_every_entry(tmp_path):
    run_http_scenario(tmp_path, r'''
        try (var root = VelqoraMap.<Integer,String>memory();
             var other = VelqoraMap.<Integer,String>memory();
             var server = VelqoraMapHttpServer.builder(root,KEYS,VALUES)
                 .map("other",other,KEYS,VALUES).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
            var codec = new BinaryBatchCodec<Integer,String>(KEYS,VALUES);
            Map<Integer,String> entries = new LinkedHashMap<>();
            entries.put(-9,"first\u0000水"); entries.put(700,"Ω🌱"); entries.put(2,"");
            byte[] independent = fields(KEYS.encode(-9),VALUES.encode("first\u0000水"),
                KEYS.encode(700),VALUES.encode("Ω🌱"),KEYS.encode(2),VALUES.encode(""));
            eq(entries,codec.decodeEntries(independent));
            // Parse the public encoder's output independently; order is not judged.
            var input = new DataInputStream(new ByteArrayInputStream(codec.encodeEntries(entries)));
            Map<Integer,String> decoded = new HashMap<>();
            while (input.available() != 0) {
                int ks = input.readInt(); byte[] kb = input.readNBytes(ks); eq(ks,kb.length);
                int vs = input.readInt(); byte[] vb = input.readNBytes(vs); eq(vs,vb.length);
                decoded.put(KEYS.decode(kb),VALUES.decode(vb));
            }
            eq(entries,decoded);
            var receivedKeys = codec.decodeKeys(fields(KEYS.encode(-9),KEYS.encode(999),KEYS.encode(700)));
            eq(Set.of(-9,999,700),new HashSet<>(receivedKeys)); eq(3,receivedKeys.size());
            input = new DataInputStream(new ByteArrayInputStream(codec.encodeKeys(List.of(-9,999,700))));
            List<Integer> decodedKeys = new ArrayList<>();
            while (input.available() != 0) {
                int length = input.readInt(); byte[] key = input.readNBytes(length); eq(length,key.length);
                decodedKeys.add(KEYS.decode(key));
            }
            eq(Set.of(-9,999,700),new HashSet<>(decodedKeys));
            eq(3,decodedKeys.size());
            // Zero-byte application encodings are valid contents and must round trip.
            var text = new BinaryBatchCodec<String,String>(TEXT,TEXT);
            Map<String,String> empties = new LinkedHashMap<>();
            empties.put("","value-for-empty-key"); empties.put("k","");
            input = new DataInputStream(new ByteArrayInputStream(text.encodeEntries(empties)));
            Map<String,String> decodedText = new HashMap<>();
            while (input.available() != 0) {
                int ks = input.readInt(); byte[] kb = input.readNBytes(ks); eq(ks,kb.length);
                int vs = input.readInt(); byte[] vb = input.readNBytes(vs); eq(vs,vb.length);
                decodedText.put(TEXT.decode(kb),TEXT.decode(vb));
            }
            eq(empties,decodedText);
            eq(empties,text.decodeEntries(text.encodeEntries(empties)));
            byte[] emptyKeys = text.encodeKeys(List.of("","k"));
            input = new DataInputStream(new ByteArrayInputStream(emptyKeys));
            List<String> decodedTextKeys = new ArrayList<>();
            while (input.available() != 0) {
                int length = input.readInt(); byte[] key = input.readNBytes(length); eq(length,key.length);
                decodedTextKeys.add(TEXT.decode(key));
            }
            eq(Set.of("","k"),new HashSet<>(decodedTextKeys)); eq(2,decodedTextKeys.size());
            eq(Set.of("","k"),new HashSet<>(text.decodeKeys(emptyKeys)));
            for (String prefix : List.of("","/maps/other")) {
                var target = prefix.isEmpty() ? root : other;
                var untouched = prefix.isEmpty() ? other : root;
                Map<Integer,String> beforeUntouched = new HashMap<>(untouched);
                target.put(2,"old"); target.put(10,"keep");
                status(server,"PUT",prefix+"/entries",independent,204);
                contents(Map.of(-9,"first\u0000水",700,"Ω🌱",2,"",10,"keep"),target);
                contents(beforeUntouched,untouched);
                for (var entry : entries.entrySet())
                    bytes(VALUES.encode(entry.getValue()),status(server,"GET",
                        path(prefix,KEYS.encode(entry.getKey())),new byte[0],200).body());
                status(server,"PUT",prefix+"/entries",new byte[0],204);
                status(server,"DELETE",prefix+"/entries",new byte[0],204);
                contents(Map.of(-9,"first\u0000水",700,"Ω🌱",2,"",10,"keep"),target);
                contents(beforeUntouched,untouched);
                status(server,"DELETE",prefix+"/entries",fields(KEYS.encode(-9),KEYS.encode(999),KEYS.encode(700)),204);
                contents(Map.of(2,"",10,"keep"),target);
                contents(beforeUntouched,untouched);
                error(server,"GET",path(prefix,KEYS.encode(-9)),new byte[0],404);
                error(server,"GET",path(prefix,KEYS.encode(700)),new byte[0],404);
            }
        }
    ''')


def test_malformed_mutations_are_atomic(tmp_path):
    run_http_scenario(tmp_path, r'''
        try (var map = VelqoraMap.<Integer,String>memory();
             var server = VelqoraMapHttpServer.builder(map,KEYS,VALUES).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
            Map<Integer,String> initial = Map.of(1,"original",2,"keep");
            map.putAll(initial);
            byte[] valid = fields(KEYS.encode(1),VALUES.encode("changed"));
            List<byte[]> badEntries = List.of(
                new byte[]{0}, join(integer(5),new byte[]{75}), fields(KEYS.encode(7)),
                integer(-1),integer(256*1024*1024+1),
                join(fields(KEYS.encode(7)),integer(-1)),
                join(fields(KEYS.encode(7)),integer(256*1024*1024+1)),
                join(fields(KEYS.encode(7)),join(integer(6),new byte[]{86,0})),
                fields(new byte[]{42},VALUES.encode("value")),fields(KEYS.encode(7),new byte[]{42}));
            for (byte[] bad : badEntries) {
                error(server,"PUT","/entries",join(valid,bad),400);
                contents(initial,map);
            }
            for (byte[] bad : List.of(new byte[]{0},join(integer(5),new byte[]{75}),
                                      integer(-1),integer(256*1024*1024+1),fields(new byte[]{42}))) {
                error(server,"DELETE","/entries",join(fields(KEYS.encode(1)),bad),400);
                contents(initial,map);
            }
            error(server,"PUT",path("",KEYS.encode(1)),new byte[]{42},400);
            error(server,"PUT",path("",new byte[]{42}),VALUES.encode("changed"),400);
            contents(initial,map);
            bytes(VALUES.encode("original"),status(server,"GET",path("",KEYS.encode(1)),new byte[0],200).body());
        }
    ''')


def test_complete_body_size_bound_on_enabled_routes(tmp_path):
    observations = run_http_scenario(tmp_path, members=APPLICATION_REQUESTS, body=r'''
        final int limit = 64*1024*1024;
        try (var map = VelqoraMap.<String,String>memory()) {
            map.put("small","visible");
            var queries = textEngine(map);
            try (var server = VelqoraMapHttpServer.builder(map,TEXT,TEXT).queries(queries)
                    .clusterQueries(queries).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                byte[] large = new byte[limit]; Arrays.fill(large,(byte)'x');
                String route = path("",utf("large"));
                status(server,"PUT",route,large,204);
                bytes(large,status(server,"GET",route,new byte[0],200).body());
                map.remove("large");
                byte[] value = new byte[limit-9]; Arrays.fill(value,(byte)'b');
                byte[] batch = fields(utf("b"),value); eq(limit,batch.length);
                status(server,"PUT","/entries",batch,204);
                bytes(value,status(server,"GET",path("",utf("b")),new byte[0],200).body());
                map.remove("b");
                String longKey = "k".repeat(limit-4);
                map.put(longKey,"remove-me");
                byte[] keys = fields(utf(longKey)); eq(limit,keys.length);
                status(server,"DELETE","/entries",keys,204);
                contents(Map.of("small","visible"),map);
                byte[] sql = new byte[limit]; Arrays.fill(sql,(byte)' ');
                byte[] statement = utf("SELECT value AS result FROM items");
                System.arraycopy(statement,0,sql,0,statement.length);
                report("query",status(server,"POST","/query",sql,200));
                report("rows",status(server,"POST","/cluster/stream",sql,200));
                byte[] scalar = scalarText("q".repeat(limit-5)); eq(limit,scalar.length);
                report("empty_rows",status(server,"POST","/cluster/lookup?table=items&alias=i",scalar,200));
                // Valid oversized bodies distinguish size refusal from ordinary parse refusal.
                error(server,"PUT",route,Arrays.copyOf(large,limit+1),400);
                batch = fields(utf("b"),Arrays.copyOf(value,value.length+1));
                eq(limit+1,batch.length); error(server,"PUT","/entries",batch,400);
                keys = fields(utf("k".repeat(limit-3)));
                eq(limit+1,keys.length); error(server,"DELETE","/entries",keys,400);
                sql = Arrays.copyOf(sql,limit+1); sql[limit]=(byte)' ';
                error(server,"POST","/query",sql,400);
                error(server,"POST","/cluster/stream",sql,400);
                scalar = scalarText("q".repeat(limit-4));
                eq(limit+1,scalar.length);
                error(server,"POST","/cluster/lookup?table=items&alias=i",scalar,400);
                contents(Map.of("small","visible"),map);
                byte[] over = new byte[limit+1]; Arrays.fill(over,(byte)'!');
                for (String endpoint : List.of(route,"/entries","/query","/cluster/stream",
                                               "/cluster/lookup?table=items&alias=i")) {
                    String method = endpoint.equals(route)||endpoint.equals("/entries") ? "PUT":"POST";
                    error(server,method,endpoint,over,400);
                    contents(Map.of("small","visible"),map);
                }
                error(server,"DELETE","/entries",over,400);
                contents(Map.of("small","visible"),map);
                // The bound measures the complete body, not a declared length: a streamed
                // (chunked, no Content-Length) body is held to the same limit.
                streamed(server,"PUT",route,large,204);
                bytes(large,status(server,"GET",route,new byte[0],200).body());
                map.remove("large");
                report("error",streamed(server,"PUT",route,Arrays.copyOf(large,limit+1),400));
                batch = fields(utf("b"),Arrays.copyOf(value,value.length+1));
                report("error",streamed(server,"PUT","/entries",batch,400));
                report("error",streamed(server,"POST","/query",sql,400));
                contents(Map.of("small","visible"),map);
                // Method and route resolution precede the size bound (FP-10.04, FP-10.01).
                for (String endpoint : List.of(route,"/entries","/query","/health")) {
                    var reply = raw(server,"PATCH",endpoint,limit+1);
                    eq(405,reply.status());
                    if (!reply.headers().containsKey("allow"))
                        throw new AssertionError("Method error without Allow: "+endpoint);
                }
                eq(404,raw(server,"POST","/no-such-route",limit+1).status());
                eq(404,raw(server,"PUT","/maps/unknown/entries/aA",limit+1).status());
                eq(400,raw(server,"PUT","/entries",limit+1).status());
                contents(Map.of("small","visible"),map);
            }
        }
    ''')
    for item in observations:
        if item['tag'] == 'query':
            assert parse_json(item['body'])['rows'] == [{'result': 'visible'}]
        elif item['tag'] == 'rows':
            assert read_rows_wire(item['body']) == [{'result': 'visible'}]
        elif item['tag'] == 'empty_rows':
            assert read_rows_wire(item['body']) == []


def test_method_errors_and_key_decoding_precedence(tmp_path):
    run_http_scenario(tmp_path, r'''
        try (var map = VelqoraMap.<Integer,String>memory(); var queryMap = VelqoraMap.<String,String>memory()) {
            map.put(5,"unchanged");
            var queries = textEngine(queryMap);
            try (var server = VelqoraMapHttpServer.builder(map,KEYS,VALUES).queries(queries)
                    .clusterQueries(queries).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                Map<String,Set<String>> methods = Map.of(
                    path("",KEYS.encode(5)),Set.of("GET","PUT","DELETE"),
                    "/entries",Set.of("PUT","DELETE"),"/health",Set.of("GET"),
                    "/flush",Set.of("POST"),"/compact",Set.of("POST"),"/query",Set.of("POST"),
                    "/cluster/stream",Set.of("POST"),"/cluster/scan?table=items&alias=i",Set.of("GET"),
                    "/cluster/lookup?table=items&alias=i",Set.of("POST"));
                for (var entry : methods.entrySet()) {
                    var response = status(server,"PATCH",entry.getKey(),new byte[]{42},405);
                    report("error",response);
                    Set<String> allowed = new HashSet<>();
                    for (String method : response.headers().firstValue("Allow").orElseThrow().split(","))
                        allowed.add(method.trim());
                    eq(entry.getValue(),allowed);
                }
                error(server,"PATCH",path("",new byte[]{42}),new byte[0],400);
                contents(Map.of(5,"unchanged"),map);
            }
        }
    ''')


def test_health_counts_current_maps(tmp_path):
    observations = run_http_scenario(tmp_path, r'''
        try (var root = VelqoraMap.<String,String>memory();
             var first = VelqoraMap.<String,String>memory();
             var second = VelqoraMap.<String,String>memory()) {
            try (var server = VelqoraMapHttpServer.builder(root,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                report("single0",status(server,"GET","/health",new byte[0],200));
                status(server,"PUT","/entries",fields(utf("a"),utf("one"),utf("b"),utf("two")),204);
                report("single2",status(server,"GET","/health",new byte[0],200));
                status(server,"PUT",path("",utf("a")),utf("replacement"),204);
                status(server,"DELETE",path("",utf("b")),new byte[0],204);
                report("single1",status(server,"GET","/health",new byte[0],200));
            }
            try (var server = VelqoraMapHttpServer.builder(root,TEXT,TEXT).map("first",first,TEXT,TEXT)
                     .map("second",second,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                first.putAll(Map.of("a","1","b","2")); second.putAll(Map.of("a","3","b","4","c","5"));
                report("multi6",status(server,"GET","/health",new byte[0],200));
                status(server,"DELETE",path("/maps/first",utf("a")),new byte[0],204);
                second.clear();
                report("multi2",status(server,"GET","/health",new byte[0],200));
            }
            try (var server = VelqoraMapHttpServer.builder().map("first",first,TEXT,TEXT)
                     .map("second",second,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                report("named1",status(server,"GET","/health",new byte[0],200));
            }
        }
    ''')
    expected = {'single0': (0, None), 'single2': (2, None), 'single1': (1, None),
                'multi6': (6, 3), 'multi2': (2, 3), 'named1': (1, 2)}
    for item in observations:
        size, maps = expected[item['tag']]
        data = parse_json(item['body'])
        assert data['size'] == size
        if maps is not None:
            assert data['maps'] == maps


def test_remote_maintenance_completion_and_recovery(tmp_path, coverage_observation):
    caller = compile_http_caller(tmp_path, r'''
        Path root = Path.of(args[0]);
        GatedText gate = new GatedText();
        AtomicReference<GatedText> activeGate = new AtomicReference<>(gate);
        Codec<String> controlled = new Codec<>() {
            public byte[] encode(String value) throws IOException { return activeGate.get().encode(value); }
            public String decode(byte[] value) throws IOException { return TEXT.decode(value); }
        };
        var disk = new VelqoraMap<String,String>(root.resolve("disk"),TEXT,controlled);
        var other = new VelqoraMap<String,String>(root.resolve("other"),TEXT,TEXT);
        other.put("untouched","other-map"); other.flush();
        byte[] otherBefore = Files.readAllBytes(root.resolve("other/velqoramap.log"));
        try (var server = VelqoraMapHttpServer.builder(other,TEXT,TEXT)
                .map("disk",disk,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
            disk.put("kept","pending");
            ExecutorService pool = Executors.newSingleThreadExecutor();
            CountDownLatch sent = new CountDownLatch(1);
            AtomicLong released = new AtomicLong(Long.MAX_VALUE);
            try {
                // Encoding may begin before or after the checkpoint request; only the
                // checkpoint's completion is ordered after the application's encoder.
                Future<Long> flush = pool.submit(() -> {
                    sent.countDown(); status(server,"POST","/maps/disk/flush",new byte[0],204);
                    return System.nanoTime();
                });
                awaitGate(sent); awaitGate(gate.entered); pending(flush);
                released.set(System.nanoTime()); gate.release.countDown();
                long completed = flush.get(20,TimeUnit.SECONDS);
                if (completed < released.get()) throw new AssertionError("HTTP completion preceded required work release");
                Files.copy(root.resolve("disk/velqoramap.log"),root.resolve("checkpoint.log"));
            } finally { gate.release.countDown(); stopPool(pool); }
            eq(durableState(otherBefore),durableState(Files.readAllBytes(root.resolve("other/velqoramap.log"))));
            // Checkpoint every version so the log really holds earlier overwritten/deleted versions.
            for (int i=0;i<30;i++) { disk.put("kept","version-"+i); disk.flush(); }
            disk.put("removed","discard"); disk.flush(); disk.remove("removed"); disk.flush();
            disk.put("kept","final");
            status(server,"POST","/maps/disk/flush",new byte[0],204);
            // Arm only after all history and current state have been checkpointed.
            // This gate is independent of the permanently released flush gate.
            AtomicLong encodingEntered = new AtomicLong(Long.MAX_VALUE);
            GatedText compactGate = new GatedText() {
                public byte[] encode(String value) throws IOException {
                    encodingEntered.compareAndSet(Long.MAX_VALUE,System.nanoTime());
                    return super.encode(value);
                }
            };
            activeGate.set(compactGate);
            AtomicLong compactReleased = new AtomicLong(Long.MAX_VALUE);
            AtomicLong responded = new AtomicLong(Long.MAX_VALUE);
            ExecutorService compactPool = Executors.newSingleThreadExecutor();
            try {
                Future<HttpResponse<byte[]>> compact = compactPool.submit(() -> {
                    var response = request(server,"POST","/maps/disk/compact",new byte[0]);
                    // Record at the receiving caller, never when the controller later reads the future.
                    responded.set(System.nanoTime());
                    eq(204,response.statusCode());
                    Files.copy(root.resolve("disk/velqoramap.log"),root.resolve("compacted.log"));
                    return response;
                });
                long deadline = System.nanoTime()+TimeUnit.SECONDS.toNanos(15);
                while (compactGate.entered.getCount()!=0 && !compact.isDone()) {
                    if (System.nanoTime() >= deadline)
                        throw new AssertionError("Neither compaction response nor encoder entry observed");
                    compactGate.entered.await(10,TimeUnit.MILLISECONDS);
                }
                if (compactGate.entered.getCount()==0) {
                    // Bounded observation window, not a product latency requirement.
                    try {
                        compact.get(300,TimeUnit.MILLISECONDS);
                        throw new AssertionError("HTTP compaction succeeded before required encoding release");
                    } catch (TimeoutException held) { /* release below permits completion */ }
                }
                compactReleased.set(System.nanoTime());
                compactGate.release.countDown();
                var response = compact.get(20,TimeUnit.SECONDS);
                boolean encoded = encodingEntered.get()!=Long.MAX_VALUE;
                if (encoded && responded.get() < compactReleased.get())
                    throw new AssertionError("HTTP compaction succeeded before required encoding release");
                report(encoded ? "compaction-encoded" : "compaction-reused",response);
            } finally {
                compactGate.release.countDown();
                stopPool(compactPool);
                activeGate.set(gate);
            }
            contents(Map.of("kept","final"),disk);
            // FP-03.01 through FP-10.06: same encodings and live state, far fewer earlier
            // versions, compacted embedded; the remote result must not be larger.
            try (var baseline = new VelqoraMap<String,String>(root.resolve("baseline"),TEXT,TEXT)) {
                baseline.put("kept","version-0"); baseline.flush();
                baseline.put("removed","discard"); baseline.flush();
                baseline.remove("removed"); baseline.flush();
                baseline.put("kept","final"); baseline.flush(); baseline.compact();
                contents(Map.of("kept","final"),baseline);
                long remote = Files.size(root.resolve("compacted.log"));
                long fewer = Files.size(root.resolve("baseline/velqoramap.log"));
                if (remote > fewer)
                    throw new AssertionError("Remote compaction kept history: "+remote+" > "+fewer);
            }
            eq(durableState(otherBefore),durableState(Files.readAllBytes(root.resolve("other/velqoramap.log"))));
            disk.clear(); status(server,"POST","/maps/disk/compact",new byte[0],204);
            eq(0L,Files.size(root.resolve("disk/velqoramap.log")));
            disk.put("restart","durable"); status(server,"POST","/maps/disk/flush",new byte[0],204);
            other.put("root-operation","saved"); status(server,"POST","/flush",new byte[0],204);
            status(server,"POST","/compact",new byte[0],204);
        }
        AtomicBoolean fail = new AtomicBoolean();
        Codec<String> failing = new Codec<>() {
            public byte[] encode(String value) throws IOException {
                if (fail.get()) throw new IOException("Application encoder unavailable");
                return TEXT.encode(value);
            }
            public String decode(byte[] value) throws IOException { return TEXT.decode(value); }
        };
        var broken = new VelqoraMap<String,String>(root.resolve("broken"),TEXT,failing);
        try (var server = VelqoraMapHttpServer.builder(broken,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
            broken.put("safe","saved"); status(server,"POST","/flush",new byte[0],204);
            fail.set(true);
            try { broken.put("pending","cannot-save"); }
            catch (UncheckedIOException immediate) { /* The triggering write may report immediately. */ }
            rejects(IOException.class,()->broken.flush());
            error(server,"POST","/flush",new byte[0],500);
            error(server,"POST","/compact",new byte[0],500);
            rejects(IOException.class,()->broken.close());
        }
        // Independent recovery must not be repaired by map.close or shutdown hooks.
        System.out.println("["+String.join(",",reports)+"]"); System.out.flush();
        Runtime.getRuntime().halt(0);
    ''')
    stores = tmp_path / 'stores'
    stores.mkdir()
    observations = run_http_caller(caller, tmp_path, stores)
    assert read_log_state(stores / 'checkpoint.log') == {b'kept': b'pending'}
    assert read_log_state(stores / 'compacted.log') == {b'kept': b'final'}
    assert read_log_state(stores / 'disk/velqoramap.log') == {b'restart': b'durable'}
    # Reopen the response-time snapshot, isolated from later maintenance and close.
    snapshot = stores / 'snapshot'
    snapshot.mkdir()
    (snapshot / 'velqoramap.log').write_bytes((stores / 'compacted.log').read_bytes())
    # Fresh JVM, using the existing feature's independent recovery machinery.
    recovery_dir = tmp_path / 'recovery'
    recovery = compile_persistence_caller(recovery_dir, r'''
        Path root = Path.of(args[0]);
        try (var snapshot = VelqoraMap.strings(root.resolve("snapshot"));
             var disk = VelqoraMap.strings(root.resolve("disk"));
             var other = VelqoraMap.strings(root.resolve("other"));
             var broken = VelqoraMap.strings(root.resolve("broken"))) {
            contents(Map.of("kept","final"),snapshot);
            contents(Map.of("restart","durable"),disk);
            contents(Map.of("untouched","other-map","root-operation","saved"),other);
            contents(Map.of("safe","saved"),broken);
        }
    ''')
    run_persistence_caller(recovery, recovery_dir, stores)
    encoded = [item['tag'] for item in observations if item['tag'].startswith('compaction-')]
    assert len(encoded) == 1, observations
    coverage_observation('FP-10.06', 'remote compaction response while required work is unfinished',
        observed=encoded == ['compaction-encoded'],
        reason=('Application encoding entered a fresh held gate; caller release preceded HTTP success.'
                if encoded == ['compaction-encoded'] else
                'No application encoding was observed; completion was checked by immediate history '
                'reclamation and independent recovery of the response-time snapshot.'),
        evidence=encoded)



def test_service_close_preserves_persistent_map_lifecycle(tmp_path):
    caller = compile_http_caller(tmp_path, r'''
        Path dir = Path.of(args[0]);
        try (var map = VelqoraMap.strings(dir)) {
            var server = VelqoraMapHttpServer.builder(map,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0)).build().start();
            String existing = path("",utf("existing"));
            try {
                status(server,"PUT",existing,utf("initial"),204);
                bytes(utf("initial"),status(server,"GET",existing,new byte[0],200).body());
                status(server,"POST","/flush",new byte[0],204);
            } finally { server.close(); }
            for (String method : List.of("GET","PUT","DELETE")) {
                try {
                    var response = request(server,method,existing,utf("remote-change"));
                    if (response.statusCode()<400 || response.statusCode()>599)
                        throw new AssertionError("Closed service still accepts requests: "+response.statusCode());
                } catch (HttpTimeoutException failure) { throw failure;
                } catch (IOException failure) {
                    boolean terminated = false;
                    for (Throwable cause=failure;cause!=null;cause=cause.getCause())
                        if (cause instanceof ConnectException || cause instanceof java.net.SocketException
                            || cause instanceof EOFException) terminated = true;
                    if (!terminated) throw failure;
                }
                contents(Map.of("existing","initial"),map);
            }
            map.put("embedded","after-close"); map.remove("existing"); map.flush();
            contents(Map.of("embedded","after-close"),map);
            map.put("separate-close","saved");
        }
    ''')
    store = tmp_path / 'store'
    run_http_caller(caller, tmp_path, store)
    recovery_dir = tmp_path / 'recovery'
    recovery = compile_persistence_caller(recovery_dir, r'''
        try (var map = VelqoraMap.strings(Path.of(args[0]))) {
            contents(Map.of("embedded","after-close","separate-close","saved"),map);
        }
    ''')
    run_persistence_caller(recovery, recovery_dir, store)


def test_authorization_outcomes_and_application_effects(tmp_path, coverage_observation):
    observations = run_http_scenario(tmp_path, members=APPLICATION_REQUESTS, body=r'''
        record Operation(String method,String path,byte[] body,int success,Map<String,String> state,boolean query) {}
        String existing = path("",utf("present"));
        List<Operation> operations = List.of(
            new Operation("GET",existing,new byte[0],200,Map.of("present","value"),false),
            new Operation("PUT",existing,utf("changed"),204,Map.of("present","changed"),false),
            new Operation("DELETE",existing,new byte[0],204,Map.of(),false),
            new Operation("PUT","/entries",fields(utf("added"),utf("batch")),204,Map.of("present","value","added","batch"),false),
            new Operation("DELETE","/entries",fields(utf("present")),204,Map.of(),false),
            new Operation("POST","/flush",new byte[0],204,Map.of("present","value"),false),
            new Operation("POST","/compact",new byte[0],204,Map.of("present","value"),false),
            new Operation("GET","/health",new byte[0],200,Map.of("present","value"),false),
            new Operation("POST","/query",utf("SELECT value AS result FROM items"),200,Map.of("present","value"),true),
            new Operation("POST","/cluster/stream",utf("SELECT value AS result FROM items"),200,Map.of("present","value"),true),
            new Operation("GET","/cluster/scan?table=items&alias=i",new byte[0],200,Map.of("present","value"),true),
            new Operation("POST","/cluster/lookup?table=items&alias=i",scalarText("present"),200,Map.of("present","value"),true),
            new Operation("GET","/unknown",new byte[0],404,Map.of("present","value"),false),
            new Operation("PATCH","/health",new byte[0],405,Map.of("present","value"),false),
            new Operation("PUT","/entries/!",new byte[]{42},400,Map.of("present","value"),false));
        for (Operation op : operations) {
            // Same initial map, schema, request and policy; only the authorization header differs.
            for (String mode : List.of("allow","deny","io")) {
                try (var map = VelqoraMap.<String,String>memory()) {
                    map.put("present","value");
                    var schema = Schema.<String>builder().column("value",value->value).build();
                    var queries = new QueryEngine(new Catalog().add("items",map,schema));
                    try (var server = VelqoraMapHttpServer.builder(map,TEXT,TEXT).queries(queries).clusterQueries(queries)
                        .authorize(exchange->{
                            String supplied = exchange.getRequestHeaders().getFirst("X-Application-Access");
                            if ("io".equals(supplied)) throw new IOException("Application policy unavailable");
                            return "allow".equals(supplied);
                        }).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                        int expected = mode.equals("allow") ? op.success() : mode.equals("deny") ? 401:500;
                        var response = status(server,op.method(),op.path(),op.body(),expected,"X-Application-Access",mode);
                        if (expected>=400) report("error",response);
                        if (mode.equals("deny")) eq("VelqoraMap",response.headers().firstValue("WWW-Authenticate").orElseThrow());
                        contents(mode.equals("allow") ? op.state():Map.of("present","value"),map);
                        if (mode.equals("allow") && op.query()) {
                            report(op.path().equals("/query") ? "query":op.path().equals("/cluster/stream") ? "rows":"qualified_rows",response);
                        }
                        // Reader evaluation timing is not a public promise. The ledger
                        // records the missing portable observation of denied query work.
                        if (mode.equals("allow") && op.method().equals("GET") && op.path().equals(existing))
                            bytes(utf("value"),response.body());
                    }
                }
            }
        }
        // Named-map dispatch uses the same policy, with real successful mutations as its baseline.
        for (String mode : List.of("allow","deny","io")) {
            try (var map = VelqoraMap.<String,String>memory();
                 var server = VelqoraMapHttpServer.builder().map("named",map,TEXT,TEXT)
                     .authorize(exchange->{
                         if (mode.equals("io")) throw new IOException("Application policy unavailable");
                         return mode.equals("allow");
                     }).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                var response = status(server,"PUT",path("/maps/named",utf("key")),utf("value"),
                    mode.equals("allow")?204:mode.equals("deny")?401:500);
                if (!mode.equals("allow")) report("error",response);
                if (mode.equals("deny")) eq("VelqoraMap",response.headers().firstValue("WWW-Authenticate").orElseThrow());
                contents(mode.equals("allow")?Map.of("key","value"):Map.of(),map);
            }
        }
        // One long-lived service and one keep-alive client: each request is decided by
        // its own header, whatever was decided earlier on the same connection.
        Path stores = Files.createTempDirectory(Path.of("").toAbsolutePath(),"authorized-stores");
        AtomicInteger readerCalls = new AtomicInteger();
        GatedText gate = new GatedText();
        try (var disk = new VelqoraMap<String,String>(stores.resolve("disk"),TEXT,TEXT);
             var gated = new VelqoraMap<String,String>(stores.resolve("gated"),TEXT,gate)) {
            var counted = Schema.<String>builder().column("value",value->{
                readerCalls.incrementAndGet(); return value; }).build();
            var queries = new QueryEngine(new Catalog().add("items",disk,counted));
            try (var server = VelqoraMapHttpServer.builder(disk,TEXT,TEXT).map("gated",gated,TEXT,TEXT)
                    .queries(queries).authorize(exchange->{
                        String supplied = exchange.getRequestHeaders().getFirst("X-Application-Access");
                        if ("io".equals(supplied)) throw new IOException("Application policy unavailable");
                        return "allow".equals(supplied);
                    }).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                String entry = path("",utf("present"));
                int changes = 0;
                for (String mode : List.of("allow","deny","allow","io","deny","allow","deny")) {
                    String value = "value-"+(changes++);
                    int expected = mode.equals("allow") ? 204 : mode.equals("deny") ? 401 : 500;
                    var before = new HashMap<>(disk);
                    var response = keptAlive(server,"PUT",entry,utf(value),expected,"X-Application-Access",mode);
                    if (expected>=400) report("error",response);
                    if (mode.equals("deny")) eq("VelqoraMap",response.headers().firstValue("WWW-Authenticate").orElseThrow());
                    contents(mode.equals("allow") ? Map.of("present",value) : before,disk);
                    response = keptAlive(server,"GET",entry,new byte[0],
                        mode.equals("allow") ? 200 : expected,"X-Application-Access",mode);
                    if (mode.equals("allow")) bytes(utf(value),response.body()); else report("error",response);
                }
                // Refused maintenance preserves durable entries, independently of history reclamation.
                for (int i=0;i<40;i++) { disk.put("present","history-"+i); disk.flush(); }
                byte[] history = Files.readAllBytes(stores.resolve("disk/velqoramap.log"));
                report("error",keptAlive(server,"POST","/compact",new byte[0],401,"X-Application-Access","deny"));
                eq(durableState(history),durableState(Files.readAllBytes(stores.resolve("disk/velqoramap.log"))));
                report("error",keptAlive(server,"POST","/compact",new byte[0],500,"X-Application-Access","io"));
                eq(durableState(history),durableState(Files.readAllBytes(stores.resolve("disk/velqoramap.log"))));
                // A refused query performs no query work: no application column reader runs.
                // (Readers may run earlier, e.g. on changes, but there are no changes here.)
                String wanted = "SELECT _key AS id, value AS result FROM items WHERE value = :wanted";
                report("authorized_query",keptAlive(server,"POST","/query?wanted=history-39",utf(wanted),200,
                    "X-Application-Access","allow"));
                int readsBefore = readerCalls.get();
                if (readsBefore == 0) throw new AssertionError("Authorized query consulted no reader");
                report("error",keptAlive(server,"POST","/query?wanted=history-39",utf(wanted),401,
                    "X-Application-Access","deny"));
                eq(readsBefore,readerCalls.get());
                report("error",keptAlive(server,"POST","/query?wanted=history-39",utf(wanted),500,
                    "X-Application-Access","io"));
                report("authorized_query",keptAlive(server,"POST","/query?wanted=history-39",utf(wanted),200,
                    "X-Application-Access","allow"));
                keptAlive(server,"POST","/compact",new byte[0],204,"X-Application-Access","allow");
                eq(durableState(history),durableState(Files.readAllBytes(stores.resolve("disk/velqoramap.log"))));
                // Compare identical current data with no earlier versions. An implementation
                // may already have reclaimed history before the explicit request.
                try (var fresh = new VelqoraMap<String,String>(stores.resolve("fresh"),TEXT,TEXT)) {
                    fresh.putAll(new HashMap<>(disk)); fresh.flush(); fresh.compact();
                    if (Files.size(stores.resolve("disk/velqoramap.log")) > Files.size(stores.resolve("fresh/velqoramap.log")))
                        throw new AssertionError("Compacted log still depends on earlier history");
                }
                // A refused checkpoint does not wait for, or run, the map's pending encoding.
                ExecutorService pool = Executors.newSingleThreadExecutor();
                try {
                    gated.put("pending","held");
                    Future<?> refused = pool.submit(() -> {
                        report("error",keptAlive(server,"POST","/maps/gated/flush",new byte[0],401,
                            "X-Application-Access","deny"));
                        return null;
                    });
                    refused.get(10,TimeUnit.SECONDS); // the encoder is still held here
                    Future<?> allowed = pool.submit(() -> {
                        keptAlive(server,"POST","/maps/gated/flush",new byte[0],204,
                            "X-Application-Access","allow");
                        return null;
                    });
                    awaitGate(gate.entered); pending(allowed);
                    gate.release.countDown();
                    allowed.get(20,TimeUnit.SECONDS);
                } finally { gate.release.countDown(); stopPool(pool); }
            }
        }
    ''')
    for item in observations:
        if item['tag'] == 'query':
            assert parse_json(item['body'])['rows'] == [{'result': 'value'}]
        elif item['tag'] == 'rows':
            assert read_rows_wire(item['body']) == [{'result': 'value'}]
        elif item['tag'] == 'qualified_rows':
            assert read_rows_wire(item['body']) == [{'i._key': 'present', 'i.value': 'value'}]
        elif item['tag'] == 'authorized_query':
            assert parse_json(item['body'])['rows'] == [{'id': 'present', 'result': 'history-39'}]
    assert sum(item['tag'] == 'authorized_query' for item in observations) == 2
    coverage_observation('FP-10.07', 'denied query internal non-execution', observed=True,
        reason='On one unchanged table, an authorized query consults its application column '
               'reader; refused queries in between leave the reader invocation count unchanged.')
    coverage_observation('FP-10.07', 'denied maintenance internal non-execution', observed=True,
        reason='A refused compaction preserves independently decoded durable associations, '
               'while authorized compaction meets the history-independent size relation; a refused checkpoint answers while the '
               "map's encoder is held, whereas the authorized checkpoint waits for it.")


def test_application_filter_changes_reach_client(tmp_path):
    run_http_scenario(tmp_path, r'''
        try (var map = VelqoraMap.<String,String>memory();
             var server = VelqoraMapHttpServer.builder(map,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0)).build()
                 .addFilter(new Filter() {
                     public String description() { return "Application request annotation"; }
                     public void doFilter(HttpExchange exchange,Chain chain) throws IOException {
                         String trace = exchange.getRequestHeaders().getFirst("X-Trace-Input");
                         exchange.getResponseHeaders().set("X-Application-Trace",
                             exchange.getRequestMethod()+":"+exchange.getRequestURI().getPath()+":"+trace);
                         chain.doFilter(exchange);
                     }
                 }).start()) {
            map.put("entry","actual-data");
            String route = path("",utf("entry"));
            for (String trace : List.of("first","second")) {
                var response = status(server,"GET",route,new byte[0],200,"X-Trace-Input",trace);
                bytes(utf("actual-data"),response.body());
                eq("GET:"+route+":"+trace,response.headers().firstValue("X-Application-Trace").orElseThrow());
            }
            var response = status(server,"GET","/health",new byte[0],200,"X-Trace-Input","health");
            eq("GET:/health:health",response.headers().firstValue("X-Application-Trace").orElseThrow());
        }
    ''')


def test_service_registration_validation(tmp_path):
    run_http_scenario(tmp_path, r'''
        rejects(IllegalStateException.class,()->VelqoraMapHttpServer.builder().port(0).build());
        try (var map = VelqoraMap.<String,String>memory()) {
            for (String name : List.of("","has space","slash/name","colon:name","question?","percent%","中文",
                    "~tilde","plus+name","bang!","at@name","star*","quote'name","comma,name","semi;name",
                    "equals=name","dollar$","amp&name","paren(name)","bracket[0]","brace{x}","pipe|name",
                    "caret^name","back`tick","hash#name","tab\tname","new\nline","back\\slash","quote\"name"))
                rejects(IllegalArgumentException.class,()->VelqoraMapHttpServer.builder().map(name,map,TEXT,TEXT));
            var duplicate = VelqoraMapHttpServer.builder().map("same",map,TEXT,TEXT);
            rejects(IllegalArgumentException.class,()->duplicate.map("same",map,TEXT,TEXT));
            map.put("key","registered");
            var builder = VelqoraMapHttpServer.builder();
            List<String> valid = List.of("Alpha","digits09","dot.name","under_score","hyphen-name",
                "9lives","0",".leading","_leading","-leading","trailing.","A-Z_a.z-0_9","x");
            for (String name : valid) builder.map(name,map,TEXT,TEXT);
            try (var server = builder.address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                for (String name : valid)
                    bytes(utf("registered"),status(server,"GET",path("/maps/"+name,utf("key")),new byte[0],200).body());
            }
        }
    ''')
