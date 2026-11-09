# feature: F14
"""Distributed public callers, real HTTP sources, and coordinator observations."""

from contextlib import contextmanager
from pathlib import Path
import time

from _helpers import compile_java, run_java, start_java
from F05_helpers import QUERY_SUPPORT
from F08_helpers import AGGREGATE_SUPPORT
from F10_helpers import compile_http_caller


DISTRIBUTED_SUPPORT = r'''
import dev.velqoramap.VelqoraMap;
import dev.velqoramap.codec.Utf8StringCodec;
import dev.velqoramap.http.VelqoraMapHttpServer;
import dev.velqoramap.query.*;
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpExchange;
import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class F14DistributedCheck extends F05QueryCheck {
    record Item(String label, Object link, Object value, String bucket, boolean included) {}
    static Schema<Item> itemSchema() {
        return Schema.<Item>builder().column("label",Item::label).column("link",Item::link)
            .column("value",Item::value).column("bucket",Item::bucket)
            .column("included",Item::included).build();
    }
    static Map<String,Item> itemData(Item... values) {
        Map<String,Item> data=new LinkedHashMap<>();
        for(int i=0;i<values.length;i++) data.put("key"+i,values[i]);
        return data;
    }
    static Catalog itemCatalog(Item... values) {
        return new Catalog().add("items",itemData(values),itemSchema());
    }
    static final class QueryNode implements AutoCloseable {
        final VelqoraMap<String,String> route=VelqoraMap.memory();
        final VelqoraMapHttpServer<String,String> server;
        QueryNode(Catalog catalog) throws Exception {
            server=VelqoraMapHttpServer.builder(route,Utf8StringCodec.INSTANCE,Utf8StringCodec.INSTANCE)
                .address(new InetSocketAddress("127.0.0.1",0)).clusterQueries(new QueryEngine(catalog))
                .authorize(e->"allowed".equals(e.getRequestHeaders().getFirst("X-Query-Application")))
                .build().start();
        }
        URI uri() { return URI.create("http://127.0.0.1:"+server.port()); }
        public void close() throws Exception { server.close(); route.close(); }
    }
    static DistributedQueryEngine.Builder distributed(Path directory,int allowance) {
        return DistributedQueryEngine.builder().header("X-Query-Application","allowed")
            .maxRowsInMemory(allowance).spillDirectory(directory);
    }
    static List<Map<String,Object>> distributedRows(DistributedQueryEngine engine,String sql,Map<String,?> params) {
        try(var result=engine.query(sql,params)) {
            List<Map<String,Object>> rows=new ArrayList<>();
            for(var row:result) rows.add(row);
            eq((long)rows.size(),result.size());
            return rows;
        }
    }
    @SafeVarargs
    static void distributedBag(DistributedQueryEngine engine,String sql,Map<String,?> params,
                               Map<String,Object>... expected) {
        eq(rowBag(Arrays.asList(expected)),rowBag(distributedRows(engine,sql,params)));
    }
    @SafeVarargs
    static void distributedSummary(DistributedQueryEngine engine,String sql,Map<String,Object>... expected) {
        var actual=distributedRows(engine,sql,Map.of());
        eq(expected.length,actual.size());
        for(var wanted:expected) {
            int match=-1;
            for(int i=0;i<actual.size();i++) if(aggregateMatch(wanted,actual.get(i))) { match=i; break; }
            if(match<0) throw new AssertionError(sql+"; expected "+wanted+"; remaining "+actual);
            actual.remove(match);
        }
    }
    static void subBag(List<Map<String,Object>> universe,List<Map<String,Object>> rows,int size) {
        // A limited unordered result: exactly `size` rows drawn from the full result's multiset.
        eq(size,rows.size());
        var all=rowBag(universe);
        for(var entry:rowBag(rows).entrySet())
            if(entry.getValue()>all.getOrDefault(entry.getKey(),0))
                throw new AssertionError("Limited rows are not a multiplicity-preserving subset: "+rows);
    }
    static void missingBinding(boolean embeddedOnly,Action action) throws Exception {
        // Embedded catalogs refuse locally; with a remote node either the coordinator's local
        // refusal or the node request failure is an admitted carrier of the refusal.
        try { action.run(); }
        catch(IllegalArgumentException refused) { return; }
        catch(UncheckedIOException remote) { if(!embeddedOnly) return; throw new AssertionError(remote); }
        throw new AssertionError("Omitted binding was not refused");
    }
    static Set<String> filesOutside(Path root,Path owned) throws IOException {
        // Regular files under root, excluding the caller-supplied temporary-storage location.
        Set<String> result=new HashSet<>();
        for(String name:remainingFiles(root))
            if(!root.resolve(name).normalize().startsWith(owned.normalize())) result.add(name);
        return result;
    }
    static Set<String> remainingFiles(Path directory) throws IOException {
        try { Files.readAttributes(directory,java.nio.file.attribute.BasicFileAttributes.class); }
        catch(NoSuchFileException absent) { return Set.of(); }
        Set<String> result=new HashSet<>();
        try(var paths=Files.walk(directory)) {
            var iterator=paths.iterator();
            while(iterator.hasNext()) {
                Path path=iterator.next();
                if(Files.readAttributes(path,java.nio.file.attribute.BasicFileAttributes.class).isRegularFile())
                    result.add(directory.relativize(path).toString());
            }
        }
        return result;
    }
    static void consumeImmutableValues(Iterator<Map<String,Object>> iterator,int count) throws Exception {
        consumeImmutableValues(iterator,count,count);
    }
    static void consumeImmutableValues(Iterator<Map<String,Object>> iterator,int count,int bound) throws Exception {
        // `count` distinct values drawn from 0..bound-1, each row refusing modification.
        BitSet seen=new BitSet(bound);
        while(iterator.hasNext()) {
            var row=iterator.next();eq(Set.of("value"),row.keySet());
            int value=((Number)row.get("value")).intValue();
            if(value<0 || value>=bound || seen.get(value)) throw new AssertionError("Unexpected row");
            seen.set(value);
            rejects(UnsupportedOperationException.class,()->row.put("value",-1));
            rejects(UnsupportedOperationException.class,()->row.remove("value"));
            rejects(UnsupportedOperationException.class,()->row.entrySet().iterator().next().setValue(-1));
            eq(resultValue(value),resultValue(row.get("value")));
        }
        eq(count,seen.cardinality());
    }
    static void remoteSource(String[] args) throws Exception {
        int count=Integer.parseInt(args[1]), width=Integer.parseInt(args[2]);
        Path arm=Path.of(args[3]), reached=Path.of(args[4]);
        try(var data=VelqoraMap.<String,String>memory()) {
            for(int i=0;i<count;i++) {
                char[] chars=new char[width];
                String prefix=String.format(java.util.Locale.ROOT,"%08d",i);
                prefix.getChars(0,8,chars,0);
                for(int j=8;j<width;j++) chars[j]=(char)('A'+(i*31+j*17)%26);
                data.put("row"+i,new String(chars));
            }
            var schema=Schema.<String>builder().column("payload",value->value).build();
            try(var node=new QueryNode(new Catalog().add("items",data,schema))) {
                // Gate the real HTTP exchange, independently of when column readers run.
                node.server.addFilter(new Filter() {
                    public String description() { return "Application request coordination"; }
                    public void doFilter(HttpExchange exchange,Chain chain) throws IOException {
                        if(Files.exists(arm)) {
                            // Publish only a complete signal to the controller process.
                            Path pending=Files.createTempFile(reached.getParent(),"query-request-",".pending");
                            try {
                                Files.writeString(pending,"request");
                                Files.move(pending,reached,StandardCopyOption.ATOMIC_MOVE);
                            } finally { Files.deleteIfExists(pending); }
                            try {
                                if(!new CountDownLatch(1).await(30,TimeUnit.SECONDS))
                                    throw new AssertionError("Node-loss controller did not stop the source");
                            } catch(InterruptedException e) {
                                Thread.currentThread().interrupt();
                                throw new IOException("Application request coordination interrupted",e);
                            }
                        }
                        chain.doFilter(exchange);
                    }
                });
                System.out.println("{\"port\":"+node.server.port()+"}"); System.out.flush();
                while(System.in.read()!=-1) {}
            }
        }
    }
    static void measureCoordinator(String[] args) throws Exception {
        URI address=URI.create(args[1]); int count=Integer.parseInt(args[2]),width=Integer.parseInt(args[3]);
        int allowance=Integer.parseInt(args[4]); Path directory=Path.of(args[5]);
        long heap=Runtime.getRuntime().maxMemory();
        if(count<=allowance || (long)allowance*width>heap/8)
            throw new AssertionError("Memory workload preconditions failed");
        if(Files.getFileStore(directory).getUsableSpace()<(long)count*width*3)
            throw new AssertionError("Insufficient temporary disk space");
        AtomicBoolean sampling=new AtomicBoolean(true); AtomicLong peak=new AtomicLong();
        Runnable sample=()->peak.accumulateAndGet(Runtime.getRuntime().totalMemory()
            -Runtime.getRuntime().freeMemory(),Math::max);
        Thread sampler=new Thread(()->{ while(sampling.get()) {
            sample.run(); java.util.concurrent.locks.LockSupport.parkNanos(1_000_000);
        }});
        // Sampling includes builder/query preparation, execution, and complete consumption.
        sample.run(); sampler.start(); long seen=0;
        try {
            var engine=distributed(directory,allowance).node("remote",address).build();
            BitSet ids=new BitSet(count);
            try(var result=engine.query("SELECT payload AS payload FROM items")) {
                eq((long)count,result.size());
                for(var row:result) {
                    eq(Set.of("payload"),row.keySet());
                    String payload=(String)row.get("payload"); eq(width,payload.length());
                    int id=Integer.parseInt(payload.substring(0,8));
                    if(id<0 || id>=count || ids.get(id)) throw new AssertionError("Missing or repeated source identity");
                    ids.set(id);
                    for(int j=8;j<width;j++) if(payload.charAt(j)!='A'+(id*31+j*17)%26)
                        throw new AssertionError("Corrupt projected content");
                    seen++; sample.run();
                }
                eq((long)count,seen); eq(count,ids.cardinality());
            }
        } finally { sample.run(); sampling.set(false); sampler.join(); }
        System.out.println("{\"peak\":"+peak.get()+",\"heap\":"+heap+",\"rows\":"+seen+"}");
    }
    static void nodeLossCoordinator(String[] args) throws Exception {
        URI address=URI.create(args[1]); Path directory=Path.of(args[2]);
        String sql="SELECT payload AS payload FROM items"+(args[3].equals("ordered")?" ORDER BY payload":"");
        var schema=Schema.<String>builder().column("payload",v->v).build();
        Map<String,String> data=new LinkedHashMap<>();
        for(int i=0;i<40;i++) data.put("local"+i,"local payload "+i);
        var engine=distributed(directory,2).node("local",new Catalog().add("items",data,schema))
            .node("remote",address).build();
        var baseline=remainingFiles(directory);
        if(args[4].equals("live")) {
            var rows=distributedRows(engine,sql,Map.of());
            eq(440,rows.size());
            for(int i=0;i<40;i++) if(!rows.contains(queryRow("payload","local payload "+i)))
                throw new AssertionError("Local row missing");
            // Remote full content is independently validated by the measuring caller.
        } else {
            rejects(UncheckedIOException.class,()->distributedRows(engine,sql,Map.of()));
        }
        eq(baseline,remainingFiles(directory));
        System.out.println("{\"completed\":true}");
    }
'''


def compile_distributed_caller(tmp_path, body=''):
    classpath = compile_http_caller(tmp_path, '')
    parent = tmp_path / 'F05QueryCheck.java'
    parent.write_text(QUERY_SUPPORT + AGGREGATE_SUPPORT + '\n}\n', encoding='utf-8')
    source = tmp_path / 'F14DistributedCheck.java'
    source.write_text(DISTRIBUTED_SUPPORT + r'''
    public static void main(String[] args) throws Exception {
        if(args.length>0) {
            switch(args[0]) {
                case "source": remoteSource(args); return;
                case "measure": measureCoordinator(args); return;
                case "loss": nodeLossCoordinator(args); return;
                default: throw new AssertionError("Unknown driver command");
            }
        }
''' + body + '\n}\n}\n', encoding='utf-8')
    compile_java([parent, source], javac='javac', classpath=classpath,
                 output_dir=classpath[0], cwd=tmp_path, timeout=60, options=['--release', '17'])
    return classpath


def run_distributed_caller(classpath, tmp_path, *args, heap='512m', jvm_args=()):
    return run_java('F14DistributedCheck', java='java', classpath=classpath,
                    cwd=tmp_path, args=args, jvm_args=['-Xmx'+heap, *jvm_args], timeout=240, check=True)


SCENARIO_COMPLETED = 'F14 scenario completed'


def run_distributed_scenario(tmp_path, body, jvm_args=()):
    """Run a caller body and require that it reached its end, not just exit status 0."""
    completed = body + '\nSystem.err.println("' + SCENARIO_COMPLETED + '"); System.err.flush();\n'
    result = run_distributed_caller(compile_distributed_caller(tmp_path, completed), tmp_path,
                                    jvm_args=jvm_args)
    assert result.returncode == 0, result
    assert SCENARIO_COMPLETED.encode() in result.stderr.splitlines(), result
    return result


@contextmanager
def query_source(classpath, tmp_path, count, width, arm, reached):
    with start_java('F14DistributedCheck', java='java', classpath=classpath, cwd=tmp_path,
                    args=['source', str(count), str(width), str(arm), str(reached)],
                    jvm_args=['-Xmx768m']) as process:
        ready = process.read_json_line(channel='stdout', timeout=60)
        assert isinstance(ready['port'], int) and 0 < ready['port'] < 65536, ready
        yield process, f"http://127.0.0.1:{ready['port']}"


def wait_for_query_request(process, coordinator, reached):
    deadline = time.monotonic() + 20
    while not reached.exists():
        assert process.poll() is None, process.snapshot()
        assert coordinator.poll() is None, coordinator.snapshot()
        assert time.monotonic() < deadline, 'Remote query did not reach the application HTTP filter'
        time.sleep(0.01)
    assert reached.read_text() == 'request'
