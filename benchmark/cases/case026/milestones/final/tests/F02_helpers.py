# feature: F02
"""Public persistence callers and independent readers of the persistence shell."""

from pathlib import Path
import struct
import sys

from _helpers import compile_java, java_command, run_command, run_java
from F01_helpers import MAP_CHECK_SUPPORT


PERSISTENCE_SUPPORT = r'''
import dev.velqoramap.VelqoraMap;
import dev.velqoramap.codec.Codec;
import dev.velqoramap.codec.Utf8StringCodec;
import java.io.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class F02PersistenceCheck extends F01MapCheck {
    static final Codec<String> TEXT = Utf8StringCodec.INSTANCE;
    static final Codec<Integer> KEYS = new Codec<>() {
        public byte[] encode(Integer value) {
            return ByteBuffer.allocate(5).order(ByteOrder.LITTLE_ENDIAN)
                .put((byte) 75).putInt(value).array();
        }
        public Integer decode(byte[] bytes) throws IOException {
            if (bytes.length != 5 || bytes[0] != 75) throw new IOException("Invalid application key");
            return ByteBuffer.wrap(bytes, 1, 4).order(ByteOrder.LITTLE_ENDIAN).getInt();
        }
    };
    static final Codec<String> VALUES = new Codec<>() {
        public byte[] encode(String value) {
            byte[] text = value.getBytes(StandardCharsets.UTF_16LE);
            return ByteBuffer.allocate(text.length + 2).put((byte)86).put((byte)0).put(text).array();
        }
        public String decode(byte[] bytes) throws IOException {
            if (bytes.length < 2 || bytes[0] != 86 || bytes[1] != 0 || bytes.length % 2 != 0)
                throw new IOException("Invalid application value");
            return new String(bytes, 2, bytes.length - 2, StandardCharsets.UTF_16LE);
        }
    };
    static void awaitGate(CountDownLatch gate) throws IOException {
        try {
            if (!gate.await(20, TimeUnit.SECONDS)) throw new IOException("Application gate timed out");
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            throw new IOException("Application gate interrupted", failure);
        }
    }
    static class GatedText implements Codec<String> {
        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final AtomicBoolean forbidden = new AtomicBoolean();
        final AtomicInteger invocations = new AtomicInteger();
        public byte[] encode(String value) throws IOException {
            invocations.incrementAndGet();
            if (forbidden.get()) throw new IOException("Repeated application action after close");
            entered.countDown();
            awaitGate(release);
            return TEXT.encode(value);
        }
        public String decode(byte[] bytes) throws IOException { return TEXT.decode(bytes); }
    }
    static void pending(Future<?> future) throws Exception {
        try {
            future.get(300, TimeUnit.MILLISECONDS);
            throw new AssertionError("Durability completed before required encoding");
        } catch (TimeoutException expected) {
            // The application still owns the closed gate; completion is forbidden.
        }
    }
    static void stopPool(ExecutorService pool) throws Exception {
        pool.shutdownNow();
        if (!pool.awaitTermination(10, TimeUnit.SECONDS))
            throw new AssertionError("Application tasks did not terminate");
    }
    static void checkpointExit(VelqoraMap<?,?> map) throws Exception {
        map.flush();
        System.out.println("F02 checks completed");
        System.out.flush();
        Runtime.getRuntime().halt(0); // No close or JVM shutdown hooks can repair this checkpoint.
    }
'''


def compile_persistence_caller(tmp_path, body, *, members=''):
    """Compile a public-API application, inheriting the earlier feature's assertions."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    product = Path('/app/target/classes')
    assert product.is_dir(), 'Harness product classes are missing at /app/target/classes'
    parent = tmp_path / 'F01MapCheck.java'
    parent.write_text(MAP_CHECK_SUPPORT + '\n}\n}\n', encoding='utf-8')
    source = tmp_path / 'F02PersistenceCheck.java'
    source.write_text(PERSISTENCE_SUPPORT + members +
                      '\npublic static void main(String[] args) throws Exception {\n' + body +
                      '\nSystem.out.println("F02 checks completed");\n}\n}\n', encoding='utf-8')
    classes = tmp_path / 'classes'
    compile_java([parent, source], javac='javac', classpath=[product], output_dir=classes,
                 cwd=tmp_path, timeout=60, options=['--release', '17'])
    return classes, product


def run_persistence_caller(classpath, tmp_path, *args, file_limit=None, heap='768m'):
    """Run one isolated JVM, preserving compiler, process and product failures."""
    options = ['-Xmx' + heap, '-XX:-UsePerfData']
    if file_limit is None:
        result = run_java('F02PersistenceCheck', java='java', classpath=classpath,
                          cwd=tmp_path, args=[str(a) for a in args], jvm_args=options,
                          timeout=100, check=True)
    else:
        # An OS-enforced write limit creates a real I/O failure, confined to this
        # child. Ignoring SIGXFSZ makes write(2) return EFBIG instead of killing it.
        command = java_command('F02PersistenceCheck', java='java', classpath=classpath,
                               args=[str(a) for a in args], jvm_args=options)
        launcher = ('import os,resource,signal,sys; '
                    'limit=int(sys.argv[1]); '
                    'resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit)); '
                    'signal.signal(signal.SIGXFSZ,signal.SIG_IGN); '
                    'os.execvp(sys.argv[2],sys.argv[2:])')
        result = run_command([sys.executable, '-c', launcher, str(file_limit), *command],
                             cwd=tmp_path, timeout=100, check=True)
    assert result.stdout == b'F02 checks completed\n', result
    return result


def log_record(key, value):
    """Encode the public log framing, using caller-supplied encoded field bytes."""
    return (struct.pack('>i', len(key)) + key +
            (struct.pack('>i', -1) if value is None else struct.pack('>i', len(value)) + value))


def read_log_state(path):
    """Read complete records; any incomplete/malformed observation fails loudly.

    Return final encoded key/value associations, not a record-count or order pin.
    This is only used on logs after successful durability, never to classify a
    deliberately interrupted input. It does not invoke the product's own decoder.
    """
    data = Path(path).read_bytes()
    offset = 0
    state = {}
    while offset < len(data):
        assert offset + 4 <= len(data), 'Incomplete durable key length'
        size, = struct.unpack_from('>i', data, offset)
        offset += 4
        assert 0 <= size <= 256 * 1024 * 1024, 'Invalid durable key length'
        assert offset + size + 4 <= len(data), 'Incomplete durable key or value length'
        key = data[offset:offset + size]
        offset += size
        size, = struct.unpack_from('>i', data, offset)
        offset += 4
        assert -1 <= size <= 256 * 1024 * 1024, 'Invalid durable value length'
        if size == -1:
            state.pop(key, None)
        else:
            assert offset + size <= len(data), 'Incomplete durable value'
            state[key] = data[offset:offset + size]
            offset += size
    return state
