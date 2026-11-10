# feature: F04
"""Selection metadata adapter, extending the existing native SQL client."""
from F02_helpers import SCALAR_CLIENT, utc_instant
from _helpers import run_command, parse_json

# Reuse the complete value/error transport; retain metadata and cells together.
SELECTION_CLIENT = SCALAR_CLIENT.replace('fn main() {', 'fn scalar_main() {') + r'''
fn main() {
    if std::env::args().nth(1).as_deref() != Some("columns") {
        scalar_main();
        return;
    }
    let db = Database::open_in_memory().unwrap();
    let statements: Vec<String> = io::stdin().lock().lines()
        .map(|line| unhex(&line.unwrap())).collect();
    for sql in &statements[..statements.len()-1] { db.execute(sql, ()).unwrap(); }
    let observation = db.query(statements.last().unwrap(), ()).and_then(|rows| {
        let columns = rows.columns().to_vec();
        rows.collect_vec().map(|values| (columns, values))
    });
    match observation {
        Ok((columns, rows)) => {
            println!("COLUMNS\t{}", columns.len());
            for column in columns { println!("{}", hex(&column)); }
            println!("ROWS\t{}", rows.len());
            for row in rows {
                println!("{}", (0..row.len()).map(|i| encode(row.get_value(i).unwrap()))
                    .collect::<Vec<_>>().join("\t"));
            }
        },
        Err(error) => panic!("Metadata query failed: {error}"),
    }
}
'''


def selection_columns(binary, setup, query):
    return selection_result(binary, setup, query)['columns']


def selection_result(binary, setup, query):
    """Read names and fully consumed values from one public Rows instance."""
    wire = ''.join(sql.encode().hex() + '\n' for sql in [*setup, query])
    result = run_command([binary, 'columns'], cwd=binary.parent, timeout=120,
                         input_bytes=wire.encode())
    assert result.returncode == 0, (result.stdout, result.stderr)
    lines = iter(result.stdout.decode().splitlines())
    label, count = next(lines).split('\t')
    assert label == 'COLUMNS', label
    columns = [bytes.fromhex(next(lines)).decode() for _ in range(int(count))]
    label, count = next(lines).split('\t')
    assert label == 'ROWS', label
    rows = []
    for _ in range(int(count)):
        row = []
        for cell in next(lines).split('\t'):
            tag, raw = cell[0], cell[1:]
            if tag == 'n':
                assert raw == '', cell
                value = None
            elif tag == 'i': value = int(raw)
            elif tag == 'f': value = float(raw)
            elif tag == 'b':
                assert raw in ('true', 'false'), cell
                value = raw == 'true'
            else:
                assert tag in ('s', 't', 'j'), cell
                value = bytes.fromhex(raw).decode()
            row.append((tag, value))
        assert len(row) == len(columns), (columns, row)
        rows.append(row)
    assert list(lines) == [], 'Unexpected client output'
    return {'columns': columns, 'rows': rows}


def selection_json_array(observation):
    rows = observation['rows']
    assert len(rows) == 1 and len(rows[0]) == 1, observation
    tag, text = rows[0][0]
    assert tag == 's', observation
    array = parse_json(text)
    assert isinstance(array, list), array
    return array


def selection_instants(observation):
    rows = observation['rows']
    assert all(len(row) == 1 and row[0][0] == 't' for row in rows), observation
    return [utc_instant(row[0][1]) for row in rows]
