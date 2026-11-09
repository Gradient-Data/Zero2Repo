# feature: F17
"""Durable logical datasets, self-contained media and independent export readers."""
from pathlib import Path
from tempfile import TemporaryDirectory

from F15_helpers import framework_source_test
from F17_helpers import persistence_session, export_records, export_sources, csv_values
from F04_helpers import group_columns


@framework_source_test
def test_saved_dataset_and_splits_fresh_session():
    from velnora import Dataset, DatasetDict, DatasetInfo
    from velnora.features import Features, Value, ClassLabel
    features = Features({'id': Value('int32'), 'label': ClassLabel(names=['north', 'south'])})
    metadata = dict(description='Survey records', citation='Field notebook',
                    homepage='https://example.org/survey', license='CC0')
    rows = [{'id': 9, 'label': 0}, {'id': 4, 'label': 1}, {'id': 18, 'label': 0}]
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = Dataset.from_list(rows, features=features, info=DatasetInfo(features=features, **metadata), split='train')
        view = data.select([2, 0, 2])
        view.save_to_disk(root / 'single')
        DatasetDict({'train': view, 'validation': data.select([1])}).save_to_disk(root / 'splits')
        (root / 'not-saved').mkdir()
        (root / 'not-saved' / 'ordinary.txt').write_text('Not a dataset', encoding='utf-8')
        persistence_session('''
from pathlib import Path
from velnora import load_from_disk
from velnora.features import Features, Value, ClassLabel
from F01_helpers import assert_invalid
root = Path(sys.argv[2])
expected_features = Features({'id': Value('int32'), 'label': ClassLabel(names=['north', 'south'])})
expected = [{'id': 18, 'label': 0}, {'id': 9, 'label': 0}, {'id': 18, 'label': 0}]
single = load_from_disk(root / 'single')
assert list(single) == expected
assert single.features == expected_features
assert str(single.split) == 'train'
for name, value in dict(description='Survey records', citation='Field notebook', homepage='https://example.org/survey', license='CC0').items():
    assert getattr(single.info, name) == value
splits = load_from_disk(root / 'splits')
assert set(splits) == {'train', 'validation'}
assert list(splits['train']) == expected
assert list(splits['validation']) == [{'id': 4, 'label': 1}]
for name in splits:
    assert splits[name].features == expected_features
    assert str(splits[name].split) == 'train'
    for field, value in dict(description='Survey records', citation='Field notebook', homepage='https://example.org/survey', license='CC0').items():
        assert getattr(splits[name].info, field) == value
for path in (root / 'missing', root / 'not-saved'):
    assert_invalid(lambda: list(load_from_disk(path)), errors=(FileNotFoundError,))
''', root)


@framework_source_test
def test_media_survives_source_removal_and_overwrite_refused():
    import numpy as np
    from PIL import Image as PILImage
    from velnora import Dataset, load_from_disk
    from velnora.features import Features, Image, Audio, Value
    from F07_helpers import audio_source
    from F01_helpers import assert_invalid
    with TemporaryDirectory() as directory:
        root = Path(directory)
        image = root / 'picture.png'
        pixels = np.array([[4, 210, 19], [255, 37, 88]], dtype=np.uint8)
        PILImage.fromarray(pixels).save(image)
        audio, expected, rate = audio_source(root)
        features = Features({'id': Value('int64'), 'image': Image(), 'audio': Audio()})
        data = Dataset.from_dict({'id': [42], 'image': [str(image)], 'audio': [str(audio)]}, features=features)
        data.save_to_disk(root / 'saved')
        image.unlink()
        audio.unlink()
        # Independent source expectations are passed to the fresh reader, never
        # obtained by decoding the dataset under test.
        np.savez(root / 'expected.npz', audio=expected, rate=rate)
        persistence_session('''
from pathlib import Path
import numpy as np
from velnora import load_from_disk
row = load_from_disk(Path(sys.argv[2]) / 'saved')[0]
assert row['id'] == 42
np.testing.assert_array_equal(np.asarray(row['image']), [[4, 210, 19], [255, 37, 88]])
samples = row['audio'].get_all_samples()
with np.load(Path(sys.argv[2]) / 'expected.npz') as expected:
    assert samples.sample_rate == int(expected['rate'])
    np.testing.assert_allclose(np.asarray(samples.data), expected['audio'], atol=1e-4, rtol=0)
''', root)
        active = load_from_disk(root / 'saved')
        assert_invalid(lambda: active.save_to_disk(root / 'saved'), errors=(PermissionError,))
        persistence_session('''
from pathlib import Path
import numpy as np
from velnora import load_from_disk
row = load_from_disk(Path(sys.argv[2]) / 'saved')[0]
assert row['id'] == 42
np.testing.assert_array_equal(np.asarray(row['image']), [[4, 210, 19], [255, 37, 88]])
samples = row['audio'].get_all_samples()
with np.load(Path(sys.argv[2]) / 'expected.npz') as expected:
    assert samples.sample_rate == int(expected['rate'])
    np.testing.assert_allclose(np.asarray(samples.data), expected['audio'], atol=1e-4, rtol=0)
''', root)


@framework_source_test
def test_file_exports_preserve_records_and_order():
    import csv
    import json
    import pyarrow.parquet as pq
    records = export_records()
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for index, source in enumerate(export_sources(records)):
            csv_path, json_path, parquet_path = [root / f'{index}.{suffix}' for suffix in ('csv', 'jsonl', 'parquet')]
            source.to_csv(csv_path, batch_size=3)
            with csv_path.open(newline='', encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            assert csv_values(rows) == records
            source.to_json(json_path, batch_size=3)
            with json_path.open(encoding='utf-8') as stream:
                assert [json.loads(line) for line in stream] == records
            source.to_parquet(parquet_path, batch_size=3)
            assert pq.read_table(parquet_path).to_pylist() == records


@framework_source_test
def test_sql_conflict_replace_and_append():
    import sqlite3
    from F01_helpers import assert_invalid
    records = export_records()
    with TemporaryDirectory() as directory:
        for index, source in enumerate(export_sources(records)):
            with sqlite3.connect(str(Path(directory) / f'{index}.db')) as connection:
                connection.execute('CREATE TABLE observations (id INTEGER, text TEXT, value REAL)')
                connection.execute('INSERT INTO observations VALUES (?, ?, ?)', (99, 'prior', -10.0))
                connection.commit()
                assert_invalid(lambda: source.to_sql('observations', connection, batch_size=3), errors=(ValueError,))
                assert connection.execute('SELECT id, text, value FROM observations').fetchall() == [(99, 'prior', -10.0)]
                source.to_sql('observations', connection, batch_size=3, if_exists='replace')
                expected = [(row['id'], row['text'], row['value']) for row in records]
                assert sorted(connection.execute('SELECT id, text, value FROM observations').fetchall()) == sorted(expected)
                source.to_sql('observations', connection, batch_size=3, if_exists='append')
                assert sorted(connection.execute('SELECT id, text, value FROM observations').fetchall()) == sorted(expected * 2)
                source.to_sql('new_table', connection, batch_size=3)
                assert sorted(connection.execute('SELECT id, text, value FROM new_table').fetchall()) == sorted(expected)


@framework_source_test
def test_record_column_and_table_exports():
    import pandas as pd
    import polars as pl
    records = export_records()
    for source in export_sources(records):
        # Partly consume an independent iterator first: exports still represent
        # the complete restartable collection, not the remaining iterator tail.
        iterator = iter(source)
        assert next(iterator) == records[0]
        assert source.to_list() == records
        assert source.to_dict() == group_columns(records)
        pandas_table = source.to_pandas()
        assert isinstance(pandas_table, pd.DataFrame)
        assert pandas_table.to_dict(orient='records') == records
        polars_table = source.to_polars()
        assert isinstance(polars_table, pl.DataFrame)
        assert polars_table.to_dicts() == records


@framework_source_test
def test_remote_storage_options_and_failures():
    import csv
    import ftplib
    import io
    import json
    import pyarrow.parquet as pq
    from F01_helpers import assert_invalid
    from F17_helpers import authenticated_ftp
    records = export_records()
    with TemporaryDirectory() as directory:
        with authenticated_ftp(Path(directory)) as (endpoint, options, client):
            finite, _ = export_sources(records)
            finite.save_to_disk(endpoint + '/single', storage_options=options)
            persistence_session('''
import json
from velnora import load_from_disk
from F17_helpers import export_records
endpoint, options = sys.argv[2], json.loads(sys.argv[3])
assert list(load_from_disk(endpoint + '/single', storage_options=options)) == export_records()
''', endpoint, json.dumps(options))
            for index, source in enumerate(export_sources(records)):
                for format_name in ('csv', 'json', 'parquet'):
                    path = f'/export-{index}.{format_name}'
                    getattr(source, 'to_' + format_name)(endpoint + path, storage_options=options, batch_size=3)
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
            # This is an actual authentication refusal from a live service.
            assert_invalid(lambda: finite.save_to_disk(endpoint + '/denied', storage_options=refused),
                           errors=(ftplib.error_perm,))
            persistence_session('''
import ftplib
import json
from velnora import load_from_disk
from F01_helpers import assert_invalid
options = json.loads(sys.argv[3])
assert_invalid(lambda: list(load_from_disk(sys.argv[2] + '/single', storage_options=options)), errors=(ftplib.error_perm,))
''', endpoint, json.dumps(refused))
            for source in export_sources(records):
                for format_name in ('csv', 'json', 'parquet'):
                    assert_invalid(lambda: getattr(source, 'to_' + format_name)(
                        endpoint + '/refused.' + format_name, storage_options=refused), errors=(ftplib.error_perm,))


@framework_source_test
def test_disk_access_memory_growth():
    import json
    import statistics
    from F17_helpers import prepare_memory_dataset, measure_disk_reader
    # The same schema, one storage shard, three four-row slices and external
    # resident budget are used throughout. Preparation is outside measurement.
    counts = (32_000, 256_000)
    budget = 512 * 1024**2
    with TemporaryDirectory() as directory:
        paths = [prepare_memory_dataset(Path(directory), count) for count in counts]
        assert counts[-1] * 8200 > budget, 'Stored record content must exceed the reader budget'
        measurements = [[], []]
        for repeat in range(3):
            for index in (repeat % 2, 1 - repeat % 2):
                measurements[index].append(measure_disk_reader(paths[index], counts[index], budget))
        growth = [statistics.median(sample['growth'] for sample in group) for group in measurements]
        print(json.dumps({'rows': counts, 'resident_budget': budget, 'measurements': measurements,
                          'median_growth': growth}), flush=True)
        # A constant allowance absorbs interpreter/allocator noise; the repeated
        # comparison permits substantial growth while excluding proportional RAM.
        assert growth[1] <= 3 * growth[0] + 24 * 1024**2, measurements

        # A dense-record companion observes anonymous resident memory: reclaimable
        # mapped pages are not an allocated per-row index. This distinguishes a
        # row index without letting file-page readahead dictate the verdict.
        dense_counts = (1_000_000, 8_000_000)
        dense_paths = [prepare_memory_dataset(Path(directory), count, payload_size=8)
                       for count in dense_counts]
        dense = [[measure_disk_reader(path, count, budget, payload_size=8) for _ in range(3)]
                 for path, count in zip(dense_paths, dense_counts)]
        anonymous = [statistics.median(sample['anonymous_growth'] for sample in group) for group in dense]
        print(json.dumps({'dense_rows': dense_counts, 'measurements': dense,
                          'median_anonymous_growth': anonymous}), flush=True)
        assert anonymous[1] <= 3 * anonymous[0] + 16 * 1024**2, dense
