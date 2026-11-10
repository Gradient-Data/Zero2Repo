# feature: F19
"""Remote file publication observed through an independent storage client."""
from pathlib import Path
from tempfile import TemporaryDirectory

from F15_helpers import framework_source_test
from F17_helpers import authenticated_ftp, csv_values, export_records, export_sources


@framework_source_test
def test_remote_file_publication_and_authorization():
    import csv
    import ftplib
    import io
    import json
    import pyarrow.parquet as pq
    from F01_helpers import assert_invalid

    records = export_records()
    with TemporaryDirectory() as directory:
        with authenticated_ftp(Path(directory)) as (endpoint, options, client):
            for index, source in enumerate(export_sources(records)):
                for format_name in ('csv', 'json', 'parquet'):
                    path = f'/published-{index}.{format_name}'
                    getattr(source, 'to_' + format_name)(
                        endpoint + path, storage_options=options, batch_size=3)
                    content = io.BytesIO()
                    client.retrbinary('RETR ' + path, content.write)
                    if format_name == 'csv':
                        actual = list(csv.DictReader(io.StringIO(content.getvalue().decode('utf-8'))))
                        assert csv_values(actual) == records
                    elif format_name == 'json':
                        assert [json.loads(line) for line in content.getvalue().decode('utf-8').splitlines()] == records
                    else:
                        content.seek(0)
                        assert pq.read_table(content).to_pylist() == records
            refused = dict(options, password=options['password'] + '-invalid')
            for source in export_sources(records):
                for format_name in ('csv', 'json', 'parquet'):
                    # A live service rejects these credentials; no simulated error.
                    assert_invalid(lambda: getattr(source, 'to_' + format_name)(
                        endpoint + '/refused.' + format_name, storage_options=refused),
                        errors=(ftplib.error_perm,))
