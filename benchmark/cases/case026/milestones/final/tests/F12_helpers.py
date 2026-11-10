# feature: F12
"""Public cluster callers, real application stores and independently owned JVMs."""

from contextlib import contextmanager, ExitStack

from _helpers import compile_java, run_java, start_java
from F10_helpers import compile_http_caller


CLUSTER_SUPPORT = r'''
import dev.velqoramap.VelqoraMap;
import dev.velqoramap.cluster.*;
import dev.velqoramap.codec.Codec;
import dev.velqoramap.http.*;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;

public class F12ClusterCheck extends F10HttpCheck {
    static final Codec<String> B64_KEY = new Codec<>() {
        public byte[] encode(String key) { return Base64.getDecoder().decode(key); }
        public String decode(byte[] value) { return Base64.getEncoder().encodeToString(value); }
    };
    static final Codec<byte[]> RAW_KEY = new Codec<>() {
        public byte[] encode(byte[] key) { return key.clone(); }
        public byte[] decode(byte[] value) { return value.clone(); }
    };
    static List<ClusterNode> nodes(String[] args) {
        List<ClusterNode> result = new ArrayList<>();
        for (int i=0; i<args.length; i++) result.add(new ClusterNode("owner-"+i,URI.create(args[i])));
        return result;
    }
    static List<ClusterNode> configNodes() {
        return List.of(new ClusterNode("Az.0_-",URI.create("http://127.0.0.1:1")),
            new ClusterNode("second",URI.create("http://127.0.0.1:2")),
            new ClusterNode("third",URI.create("http://127.0.0.1:3")));
    }
    static void balanced(ClusterTopology topology, List<ClusterNode> nodes, int partitions) {
        eq(partitions,topology.partitions()); eq(partitions,topology.owners().size());
        eq(new HashSet<>(nodes),new HashSet<>(topology.nodes()));
        Map<String,Integer> counts = new HashMap<>();
        for (var node:nodes) counts.put(node.name(),0);
        for (int p=0; p<partitions; p++) {
            String owner=topology.owners().get(p);
            if (!counts.containsKey(owner)) throw new AssertionError("Unknown owner: "+owner);
            eq(owner,topology.owner(p).name());
            counts.put(owner,counts.get(owner)+1);
        }
        if (Collections.max(counts.values())-Collections.min(counts.values())>1)
            throw new AssertionError("Unbalanced partition counts: "+counts);
    }
    // This is a real application-supplied transport backed by independent VelqoraMaps.
    // It performs every operation; it does not supply canned results or replace product code.
    static class ApplicationStores implements ClusterTransport<String,String>, AutoCloseable {
        final Map<String,Map<String,VelqoraMap<String,String>>> stores = new HashMap<>();
        ApplicationStores(List<ClusterNode> nodes) {
            for (var node:nodes) stores.put(node.name(),Map.of(
                "records",VelqoraMap.<String,String>memory(),"other",VelqoraMap.<String,String>memory()));
        }
        VelqoraMap<String,String> store(ClusterNode node,String map) { return stores.get(node.name()).get(map); }
        public String get(ClusterNode n,String m,String k) { return store(n,m).get(k); }
        public void put(ClusterNode n,String m,String k,String v) { store(n,m).put(k,v); }
        public boolean remove(ClusterNode n,String m,String k) { return store(n,m).remove(k)!=null; }
        public void putAll(ClusterNode n,String m,Map<String,String> entries) { store(n,m).putAll(entries); }
        public void removeAll(ClusterNode n,String m,Collection<String> keys) { store(n,m).removeAll(keys); }
        public void close() throws IOException { for(var maps:stores.values()) for(var map:maps.values()) map.close(); }
    }
    static HttpClusterTransport<String,String> httpTransport() {
        return new HttpClusterTransport<>(CLIENT,B64_KEY,TEXT,Map.of("X-Application-Route","accepted"));
    }
    static ClusterMap<String,String> routed(ClusterTopology topology,ClusterTransport<String,String> transport) {
        return new ClusterMap<>("records",B64_KEY,topology,transport);
    }
    static String randomKey(Random random) {
        byte[] raw=new byte[16]; random.nextBytes(raw); return Base64.getEncoder().encodeToString(raw);
    }
    static Map<String,List<String>> ownerKeys(ClusterMap<String,String> map,List<ClusterNode> nodes) {
        Map<String,List<String>> selected=new LinkedHashMap<>();
        for(var node:nodes) selected.put(node.name(),new ArrayList<>());
        Random random=new Random(0x12C0FFEE);
        for(int i=0;i<8192;i++) {
            String key=randomKey(random);
            var keys=selected.get(map.owner(key).name());
            if(keys==null) throw new AssertionError("Owner outside membership");
            if(keys.size()<3) keys.add(key);
            if(selected.values().stream().allMatch(v->v.size()==3)) return selected;
        }
        throw new AssertionError("Uniform encoded samples did not reach all configured owners");
    }
    // Observe the node's public HTTP entry directly, bypassing ClusterMap routing.
    static void remoteValue(ClusterNode node,String map,String key,String expected) throws Exception {
        var req=HttpRequest.newBuilder(URI.create(node.address()+path("/maps/"+map,B64_KEY.encode(key))))
            .timeout(Duration.ofSeconds(15)).header("X-Application-Route","accepted").GET().build();
        var response=CLIENT.send(req,HttpResponse.BodyHandlers.ofByteArray());
        eq(expected==null?404:200,response.statusCode());
        if(expected!=null) bytes(TEXT.encode(expected),response.body());
    }
    interface StoreObserver { void check(ClusterNode node,String map,String key,String expected) throws Exception; }
    static void soleStorage(ClusterMap<String,String> map,List<ClusterNode> nodes,List<String> keys,
                            Map<String,String> expected,StoreObserver observer) throws Exception {
        for(String key:keys) {
            eq(expected.get(key),map.get(key));
            for(var node:nodes) {
                observer.check(node,"records",key,node.equals(map.owner(key))?expected.get(key):null);
                observer.check(node,"other",key,null);
            }
        }
    }
    static void exerciseRouting(ClusterTopology topology,ClusterTransport<String,String> transport,
                                StoreObserver observer) throws Exception {
        var map=routed(topology,transport); var nodes=topology.nodes();
        var selected=ownerKeys(map,nodes);
        List<String> keys=new ArrayList<>(); selected.values().forEach(keys::addAll);
        Map<String,String> expected=new LinkedHashMap<>();
        for(String key:keys) { eq(null,map.get(key)); eq(false,map.remove(key)); }
        for(var owner:selected.entrySet()) {
            String key=owner.getValue().get(0), value="single-"+owner.getKey()+" 水";
            map.put(key,value); expected.put(key,value);
        }
        soleStorage(map,nodes,keys,expected,observer);
        for(String key:keys) expected.put(key,"batch-"+keys.indexOf(key)+" Ω");
        expected.put(keys.get(0),"");
        map.putAll(expected); map.putAll(Map.of());
        soleStorage(map,nodes,keys,expected,observer);
        for(var group:selected.values()) {
            eq(true,map.remove(group.get(0))); eq(false,map.remove(group.get(0)));
            expected.remove(group.get(0));
        }
        soleStorage(map,nodes,keys,expected,observer);
        List<String> deleting=new ArrayList<>();
        for(var group:selected.values()) { deleting.add(group.get(0)); deleting.add(group.get(1)); expected.remove(group.get(1)); }
        map.removeAll(deleting); map.removeAll(List.of());
        soleStorage(map,nodes,keys,expected,observer);
    }
    static void ownerFailure(String owner,Action action) throws Exception { ownerFailure(owner,List.of(),action); }
    // The diagnostic must identify the unavailable owner: it includes that owner's name and
    // may include additional context. Its prose, prefix and address text are not pinned.
    static void ownerFailure(String owner,List<ClusterNode> members,Action action) throws Exception {
        try { action.run(); }
        catch(UncheckedIOException failure) {
            String message=failure.getMessage();
            if(message==null || !message.contains(owner)) throw new AssertionError("Failure lacks owner identity",failure);
            return;
        }
        throw new AssertionError("Unavailable owner operation returned normally: "+owner);
    }
    static void awaitGo() throws IOException {
        // Application-owned step signal from the Python driver; not a product protocol.
        String line=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8)).readLine();
        if(!"go".equals(line)) throw new AssertionError("Driver did not signal the next step");
    }
    static void serveNode() throws Exception {
        try(var records=VelqoraMap.<String,String>memory(); var other=VelqoraMap.<String,String>memory();
            var server=VelqoraMapHttpServer.builder().map("records",records,B64_KEY,TEXT)
                .map("other",other,B64_KEY,TEXT).address(new InetSocketAddress("127.0.0.1",0))
                .authorize(exchange->"accepted".equals(exchange.getRequestHeaders().getFirst("X-Application-Route")))
                .build().start()) {
            System.out.println("{\"port\":"+server.port()+"}"); System.out.flush();
            // EOF is an application-owned shutdown signal, not a product protocol.
            while(System.in.read()!=-1) {}
        }
    }
'''


def compile_cluster_caller(tmp_path, body):
    classpath = compile_http_caller(tmp_path, '')
    source = tmp_path / 'F12ClusterCheck.java'
    source.write_text(CLUSTER_SUPPORT + '\npublic static void main(String[] args) throws Exception {\n'
                      'if(args.length==1 && args[0].equals("serve")) { serveNode(); return; }\n'
                      + body + '\n}\n}\n', encoding='utf-8')
    compile_java([source], javac='javac', classpath=classpath, output_dir=classpath[0],
                 cwd=tmp_path, timeout=60, options=['--release', '17'])
    return classpath


def run_cluster_caller(classpath, tmp_path, *args):
    return run_java('F12ClusterCheck', java='java', classpath=classpath, cwd=tmp_path,
                    args=args, jvm_args=['-Xmx512m'], timeout=120, check=True)


SCENARIO_COMPLETED = 'F12 scenario completed'


def run_cluster_scenario(tmp_path, body):
    """Run a caller body and require that it reached its end, not just exit status 0."""
    completed = body + '\nSystem.err.println("' + SCENARIO_COMPLETED + '"); System.err.flush();\n'
    result = run_cluster_caller(compile_cluster_caller(tmp_path, completed), tmp_path)
    assert result.returncode == 0, result
    assert SCENARIO_COMPLETED.encode() in result.stderr.splitlines(), result
    return result


@contextmanager
def cluster_nodes(classpath, tmp_path, count=3):
    """Start only registered child JVMs and retain failure output on every probe."""
    with ExitStack() as stack:
        processes, addresses = [], []
        for _ in range(count):
            process = stack.enter_context(start_java(
                'F12ClusterCheck', java='java', classpath=classpath, cwd=tmp_path,
                args=['serve'], jvm_args=['-Xmx256m']))
            ready = process.read_json_line(channel='stdout', timeout=20)
            assert isinstance(ready['port'], int) and 0 < ready['port'] < 65536, ready
            processes.append(process)
            addresses.append(f"http://127.0.0.1:{ready['port']}")
        yield processes, addresses
