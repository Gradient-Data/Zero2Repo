# feature: F01
"""Compile and execute application-owned checks against the public map API."""

from pathlib import Path

from _helpers import compile_java, run_java


MAP_CHECK_SUPPORT = r'''
import dev.velqoramap.VelqoraMap;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.*;

public class F01MapCheck {
    static void eq(Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError("Expected " + expected + ", got " + actual);
        }
    }
    static <K,V> void contents(Map<K,V> expected, VelqoraMap<K,V> actual) {
        eq(expected, new HashMap<>(actual));
        eq(expected.size(), actual.size());
        eq(expected.isEmpty(), actual.isEmpty());
        for (var entry : expected.entrySet()) {
            eq(entry.getValue(), actual.get(entry.getKey()));
        }
    }
    interface Action { void run() throws Exception; }
    static void rejects(Class<? extends Throwable> type, Action action) throws Exception {
        try {
            action.run();
        } catch (Throwable failure) {
            if (type.isInstance(failure)) return;
            throw new AssertionError("Expected " + type.getName(), failure);
        }
        throw new AssertionError("Expected " + type.getName() + " to be thrown");
    }
    static <T> List<T> contend(int workers, IntFunction<T> action) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<T>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < workers; i++) {
                final int worker = i;
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(20, TimeUnit.SECONDS))
                        throw new AssertionError("Start gate did not open");
                    return action.apply(worker);
                }));
            }
            if (!ready.await(20, TimeUnit.SECONDS))
                throw new AssertionError("Workers did not reach the start gate");
            start.countDown();
            List<T> results = new ArrayList<>();
            for (Future<T> future : futures) results.add(future.get(40, TimeUnit.SECONDS));
            return results;
        } finally {
            start.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS))
                throw new AssertionError("Workers did not terminate");
        }
    }
    static void align(CyclicBarrier barrier) {
        // Bounded rendezvous so contending callers overlap on one key at a time.
        try {
            barrier.await(20, TimeUnit.SECONDS);
        } catch (Exception failure) {
            throw new AssertionError("Contending callers did not align", failure);
        }
    }
    static void notified(VelqoraMap<String,Integer> map, List<String> first,
                         List<String> second, Set<String> affected,
                         Map<String,Integer> expected, Action action) throws Exception {
        first.clear();
        second.clear();
        action.run();
        eq(affected, new HashSet<>(first));
        eq(affected, new HashSet<>(second));
        contents(expected, map);
    }
    public static void main(String[] args) throws Exception {
'''


def run_map_scenario(tmp_path, body):
    """Run a real Java caller; compile errors and all unexpected failures propagate.

    The case harness builds the selected product at /app. The driver and its
    classes live only in pytest's writable temporary directory. No product source
    is read or compiled by this helper.
    """
    product_classes = Path('/app/target/classes')
    assert product_classes.is_dir(), 'Harness product classes are missing at /app/target/classes'
    source = tmp_path / 'F01MapCheck.java'
    source.write_text(
        MAP_CHECK_SUPPORT + body + '\nSystem.out.println("F01 checks completed");\n}\n}\n',
        encoding='utf-8',
    )
    classes = tmp_path / 'classes'
    compile_java([source], javac='javac', classpath=[product_classes],
                 output_dir=classes, cwd=tmp_path, timeout=60, options=['--release', '17'])
    result = run_java('F01MapCheck', java='java', classpath=[classes, product_classes],
                      cwd=tmp_path, timeout=100, check=True)
    assert result.stdout == b'F01 checks completed\n', result
