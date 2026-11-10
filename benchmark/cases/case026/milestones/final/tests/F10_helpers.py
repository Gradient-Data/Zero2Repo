# feature: F10
"""Live public HTTP callers and independent readers of their wire formats."""

import base64
import io
import struct
from pathlib import Path

from _helpers import compile_java, parse_json, run_java
from F02_helpers import compile_persistence_caller


HTTP_SUPPORT = r'''
import dev.velqoramap.VelqoraMap;
import dev.velqoramap.codec.Codec;
import dev.velqoramap.http.*;
import dev.velqoramap.query.*;
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpExchange;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class F10HttpCheck extends F02PersistenceCheck {
    static final HttpClient CLIENT = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5)).build();
    static final List<String> reports = new ArrayList<>();
    static byte[] utf(String value) { return value.getBytes(StandardCharsets.UTF_8); }
    static String path(String prefix, byte[] key) {
        return prefix + "/entries/" + Base64.getUrlEncoder().withoutPadding().encodeToString(key);
    }
    static HttpResponse<byte[]> request(VelqoraMapHttpServer<?,?> server, String method,
                                        String path, byte[] body, String... headers) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+server.port()+path))
            .timeout(Duration.ofSeconds(40)).method(method,HttpRequest.BodyPublishers.ofByteArray(body));
        if (headers.length != 0) builder.headers(headers);
        return CLIENT.send(builder.build(),HttpResponse.BodyHandlers.ofByteArray());
    }
    static HttpResponse<byte[]> status(VelqoraMapHttpServer<?,?> server, String method,
                                       String path, byte[] body, int expected, String... headers) throws Exception {
        var response = request(server,method,path,body,headers);
        if (expected != response.statusCode())
            throw new AssertionError(method+" "+path+": expected "+expected+", got "+response.statusCode()
                +" body="+new String(response.body(),StandardCharsets.UTF_8));
        return response;
    }
    static void report(String tag, HttpResponse<byte[]> response) {
        // Tags are application-owned scenario names, not inferred product messages.
        reports.add("{\"tag\":\""+tag+"\",\"status\":"+response.statusCode()
            +",\"body\":\""+Base64.getEncoder().encodeToString(response.body())+"\"}");
    }
    static void error(VelqoraMapHttpServer<?,?> server, String method, String path,
                       byte[] body, int expected, String... headers) throws Exception {
        report("error",status(server,method,path,body,expected,headers));
    }
    static void bytes(byte[] expected, byte[] actual) {
        if (!Arrays.equals(expected,actual)) throw new AssertionError("HTTP byte contents differ");
    }
    static Map<ByteBuffer,ByteBuffer> durableState(byte[] log) throws IOException {
        var state = new HashMap<ByteBuffer,ByteBuffer>();
        var input = new DataInputStream(new ByteArrayInputStream(log));
        while (input.available() != 0) {
            int keySize = input.readInt();
            if (keySize < 0 || keySize > 256*1024*1024) throw new IOException("Invalid durable key length");
            byte[] keyBytes = input.readNBytes(keySize);
            if (keyBytes.length != keySize) throw new EOFException("Incomplete durable key");
            var key = ByteBuffer.wrap(keyBytes);
            int valueSize = input.readInt();
            if (valueSize == -1) state.remove(key);
            else {
                if (valueSize < 0 || valueSize > 256*1024*1024) throw new IOException("Invalid durable value length");
                byte[] value = input.readNBytes(valueSize);
                if (value.length != valueSize) throw new EOFException("Incomplete durable value");
                state.put(key,ByteBuffer.wrap(value));
            }
        }
        return state;
    }
    static byte[] fields(byte[]... fields) throws IOException {
        var buffer = new ByteArrayOutputStream();
        var output = new DataOutputStream(buffer);
        for (byte[] field : fields) { output.writeInt(field.length); output.write(field); }
        return buffer.toByteArray();
    }
    static byte[] join(byte[] a, byte[] b) {
        byte[] result = Arrays.copyOf(a,a.length+b.length);
        System.arraycopy(b,0,result,a.length,b.length);
        return result;
    }
    static byte[] integer(int value) { return ByteBuffer.allocate(4).putInt(value).array(); }
    static byte[] scalarText(String value) throws IOException { return join(new byte[]{1},fields(utf(value))); }
    static QueryEngine textEngine(VelqoraMap<String,String> map) {
        return new QueryEngine(new Catalog().add("items",map,
            Schema.<String>builder().column("value",v->v).build()));
    }
'''


def compile_http_caller(tmp_path, body, *, members=''):
    """Reuse persistence codecs/assertions; compile only application-side callers."""
    classes, product = compile_persistence_caller(tmp_path, '')
    source = tmp_path / 'F10HttpCheck.java'
    source.write_text(HTTP_SUPPORT + members +
                      '\npublic static void main(String[] args) throws Exception {\n' + body +
                      '\nSystem.out.println("["+String.join(",",reports)+"]");\n}\n}\n',
                      encoding='utf-8')
    compile_java([source], javac='javac', classpath=[classes, product],
                 output_dir=classes, cwd=tmp_path, timeout=60, options=['--release', '17'])
    return classes, product


def run_http_caller(classpath, tmp_path, *args):
    result = run_java('F10HttpCheck', java='java', classpath=classpath, cwd=tmp_path,
                      args=[str(a) for a in args], jvm_args=['-Xmx1536m'], timeout=240, check=True)
    observations = result.json(channel='stdout')
    for item in observations:
        item['body'] = base64.b64decode(item['body'], validate=True)
        if item['tag'] == 'error':
            # Diagnostic prose is intentionally not used to infer an error category.
            payload = parse_json(item['body'])
            assert isinstance(payload['error'], str) and payload['error'], item
    return observations


def run_http_scenario(tmp_path, body, *, members=''):
    observations = run_http_caller(compile_http_caller(tmp_path, body, members=members), tmp_path)
    # The report array is printed only after the whole caller body ran; an early
    # successful JVM exit leaves no array and cannot pass as a completed scenario.
    assert isinstance(observations, list), observations
    assert all(isinstance(item.get('tag'), str) for item in observations), observations
    return observations


def _wire_read(stream, size):
    assert size >= 0, 'Negative wire field length'
    value = stream.read(size)
    assert len(value) == size, 'Incomplete wire observation'
    return value


def _wire_unpack(stream, form):
    return struct.unpack(form, _wire_read(stream, struct.calcsize(form)))[0]


def read_scalar_wire(stream):
    """Read a scalar from an independent stream; malformed observations raise."""
    tag = _wire_unpack(stream, '>B')
    if tag == 0:
        return None
    if tag in (1, 9, 10):
        value = _wire_read(stream, _wire_unpack(stream, '>i'))
        return value if tag == 9 else value.decode('utf-8')
    forms = {2: '>?', 3: '>b', 4: '>h', 5: '>i', 6: '>q', 7: '>f', 8: '>d'}
    assert tag in forms, f'Unknown scalar tag: {tag}'
    return _wire_unpack(stream, forms[tag])


def read_rows_wire(data):
    """Consume complete framed rows, including the terminator and EOF."""
    stream = io.BytesIO(data)
    rows = []
    while True:
        marker = _wire_unpack(stream, '>B')
        if marker == 0:
            assert stream.read() == b'', 'Trailing row-stream bytes'
            return rows
        assert marker == 1, 'Invalid row frame'
        count = _wire_unpack(stream, '>i')
        assert count >= 0, 'Negative column count'
        row = {}
        for _ in range(count):
            name = _wire_read(stream, _wire_unpack(stream, '>i')).decode('utf-8')
            assert name not in row, 'Duplicate column name'
            row[name] = read_scalar_wire(stream)
        rows.append(row)


def read_batch_fields(data):
    """Independent length-prefixed batch reader; no product round-trip oracle."""
    stream = io.BytesIO(data)
    fields = []
    while stream.tell() < len(data):
        fields.append(_wire_read(stream, _wire_unpack(stream, '>i')))
    return fields
