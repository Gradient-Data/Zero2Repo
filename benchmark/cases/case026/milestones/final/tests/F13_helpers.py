# feature: F13
"""Independent wire construction and public interchange observations."""

import io
import struct

from F10_helpers import run_http_scenario


def scalar_wire(tag, value):
    """Construct the public tagged scalar shell, independently of the product."""
    if tag == 0:
        return b'\0'
    if tag in (1, 9, 10):
        data = value if tag == 9 else value.encode('utf-8')
        return bytes([tag]) + struct.pack('>i', len(data)) + data
    forms = {2: '>?', 3: '>b', 4: '>h', 5: '>i', 6: '>q', 7: '>f', 8: '>d'}
    return bytes([tag]) + struct.pack(forms[tag], value)


def rows_wire(rows):
    """Rows contain (name, scalar tag, value) triples; no field order is required."""
    output = bytearray()
    for row in rows:
        output.extend(b'\1' + struct.pack('>i', len(row)))
        for name, tag, value in row:
            name_bytes = name.encode('utf-8')
            output.extend(struct.pack('>i', len(name_bytes)) + name_bytes)
            output.extend(scalar_wire(tag, value))
    output.append(0)
    return bytes(output)


def _typed_take(stream, size):
    assert size >= 0, 'Negative wire field length'
    value = stream.read(size)
    assert len(value) == size, 'Incomplete wire observation'
    return value


def read_typed_scalar(stream):
    """Read one public tagged scalar as (tag, value), so integer widths, booleans
    and floating widths stay distinguishable (Python equates 1, 1.0 and True)."""
    tag = _typed_take(stream, 1)[0]
    if tag == 0:
        return (0, None)
    if tag in (1, 9, 10):
        data = _typed_take(stream, struct.unpack('>i', _typed_take(stream, 4))[0])
        return (tag, data if tag == 9 else data.decode('utf-8'))
    forms = {2: '>?', 3: '>b', 4: '>h', 5: '>i', 6: '>q', 7: '>f', 8: '>d'}
    assert tag in forms, f'Unknown scalar tag: {tag}'
    return (tag, struct.unpack(forms[tag], _typed_take(stream, struct.calcsize(forms[tag])))[0])


def read_typed_rows(data):
    """Consume a complete public row stream into dicts of field -> (tag, value)."""
    stream = io.BytesIO(data)
    rows = []
    while True:
        marker = _typed_take(stream, 1)[0]
        if marker == 0:
            assert stream.read() == b'', 'Trailing row-stream bytes'
            return rows
        assert marker == 1, 'Invalid row frame'
        count = struct.unpack('>i', _typed_take(stream, 4))[0]
        assert count >= 0, 'Negative field count'
        row = {}
        for _ in range(count):
            name = _typed_take(stream, struct.unpack('>i', _typed_take(stream, 4))[0]).decode('utf-8')
            assert name not in row, 'Duplicate field name'
            row[name] = read_typed_scalar(stream)
        rows.append(row)


def java_wire(data):
    return 'HexFormat.of().parseHex("' + data.hex() + '")'


INTERCHANGE_SUPPORT = r'''
    static void wireReport(String tag, byte[] data) {
        reports.add("{\"tag\":\""+tag+"\",\"body\":\""
            +Base64.getEncoder().encodeToString(data)+"\"}");
    }
    static void scalarEqual(Object expected, Object actual) {
        if (expected == null) { eq(null,actual); return; }
        if (actual == null) throw new AssertionError("Scalar unexpectedly null");
        eq(expected.getClass(),actual.getClass());
        if (expected instanceof byte[] data) bytes(data,(byte[])actual);
        else eq(expected,actual);
    }
    static List<Map<String,Object>> consumeRows(byte[] data) {
        List<Map<String,Object>> result = new ArrayList<>();
        for (var row : new BinaryRowStream().read(new ByteArrayInputStream(data))) result.add(row);
        return result;
    }
    static void rowSequenceEqual(List<Map<String,Object>> expected, List<Map<String,Object>> actual) {
        eq(expected.size(),actual.size());
        for (int i=0;i<expected.size();i++) {
            eq(expected.get(i).keySet(),actual.get(i).keySet());
            for (var field : expected.get(i).entrySet())
                scalarEqual(field.getValue(),actual.get(i).get(field.getKey()));
        }
    }
    static void rowReadFailure(byte[] data, boolean incomplete) throws Exception {
        // Capture creation and full consumption together, allowing eager or lazy failures.
        try { consumeRows(data); }
        catch (UncheckedIOException failure) {
            if (incomplete != (failure.getCause() instanceof EOFException))
                throw new AssertionError("Incorrect row failure category",failure);
            return;
        }
        throw new AssertionError("Invalid row stream completed successfully");
    }
    static void scalarReadFailure(byte[] data, boolean incomplete) throws Exception {
        try { BinaryScalar.decode(data); }
        catch (IOException failure) {
            if (incomplete != (failure instanceof EOFException))
                throw new AssertionError("Incorrect scalar failure category",failure);
            return;
        }
        throw new AssertionError("Invalid scalar completed successfully");
    }
'''


def run_interchange(tmp_path, body):
    """The inherited runner grants 1536 MiB heap for the direct 256 MiB check."""
    observations = run_http_scenario(tmp_path, body, members=INTERCHANGE_SUPPORT)
    # Completion is evidenced by the report array the caller prints after its body.
    assert isinstance(observations, list), observations
    return observations


SCAN_OBSERVATIONS = r'''
    static Map<String,Object> typedRow(Map<String,Object> row) {
        if (row == null) return null;
        Map<String,Object> result = new HashMap<>();
        row.forEach((field,value) -> result.put(field, value instanceof byte[] bytes
            ? java.nio.ByteBuffer.wrap(bytes.clone()).asReadOnlyBuffer() : value));
        return result;
    }
    static Map<Map<String,Object>,Integer> typedBag(Iterable<Map<String,Object>> rows) {
        Map<Map<String,Object>,Integer> result = new HashMap<>();
        for (var row : rows) result.merge(typedRow(row),1,Integer::sum);
        return result;
    }
'''
