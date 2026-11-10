# feature: F06
"""Acceptance checks for local tabular and text source ingestion."""
import bz2
import gzip
import io
import json
import lzma
from pathlib import Path
import sqlite3
import tarfile
import zipfile

from F06_helpers import distributed_runtime, ingest, ingest_rows, source_product_test, write_binary_table

import pyarrow as pa
from velnora import Dataset, load_dataset
from velnora.features import Features, List, Value
from velnora.download import DownloadConfig, DownloadManager
from velnora.exceptions import DatasetGenerationError

from F01_helpers import assert_invalid
from F05_helpers import write_records


@source_product_test
def test_delimited_defaults_and_overrides(tmp_path):
    expected = [{'id': 7, 'word': '雪'}, {'id': -3, 'word': 'oak'}]
    for suffix, delimiter in [('csv', ','), ('tsv', '\t')]:
        root = tmp_path / suffix
        root.mkdir()
        path = root / ('part.' + suffix)
        path.write_text(f'id{delimiter}word\n7{delimiter}雪\n-3{delimiter}oak\n', encoding='utf-8')
        assert list(load_dataset(str(root), split='train')) == expected
    path = tmp_path / 'custom.csv'
    path.write_text('007;yes\n023;no\n', encoding='utf-8')
    features = Features({'code': Value('string'), 'answer': Value('string')})
    dataset = ingest('csv', path, delimiter=';', header=None, names=['code', 'answer'], features=features)
    assert list(dataset) == [{'code': '007', 'answer': 'yes'}, {'code': '023', 'answer': 'no'}]
    assert dataset.features == features


@source_product_test
def test_json_record_forms(tmp_path):
    rows = [{'value': 8}, {'value': -5}, {'value': 31}]
    line_path = write_records(tmp_path, 'lines.jsonl', [8, -5, 31])
    assert ingest_rows('json', line_path) == rows
    # The named field sits between other record arrays, so only the name selects it.
    container = {'other': [{'value': 99}], 'records': rows, 'tail': [{'value': -1}, {'value': 0}]}
    for name, content, kwargs in [('array', rows, {}),
                                  ('container', container, {'field': 'records'})]:
        path = tmp_path / (name + '.json')
        path.write_text(json.dumps(content), encoding='utf-8')
        assert ingest_rows('json', path, **kwargs) == rows


@source_product_test
def test_malformed_and_incompatible_data(tmp_path):
    valid = tmp_path / 'valid.jsonl'
    valid.write_text('{"id": 8}\n{"id": -2}\n', encoding='utf-8')
    schema = Features({'id': Value('int32')})
    assert ingest_rows('json', valid, features=schema) == [{'id': 8}, {'id': -2}]
    malformed = tmp_path / 'broken.jsonl'
    malformed.write_text('{"id": 8}\n{"id":\n', encoding='utf-8')
    incompatible = tmp_path / 'wrong.csv'
    incompatible.write_text('id\n8\nnot-an-integer\n', encoding='utf-8')
    for format_name, path, kwargs in [('json', malformed, {}), ('csv', incompatible, {'features': schema})]:
        assert_invalid(lambda: list(ingest(format_name, path, **kwargs)), (DatasetGenerationError,))


@source_product_test
def test_text_grouping_and_xml(tmp_path):
    content = 'first\nsecond\n\nthird\n\nfourth'
    path = tmp_path / 'source.txt'
    path.write_text(content, encoding='utf-8')
    for kwargs, expected in [({}, ['first', 'second', '', 'third', '', 'fourth']),
                              ({'keep_linebreaks': True}, ['first\n', 'second\n', '\n', 'third\n', '\n', 'fourth']),
                              ({'sample_by': 'paragraph'}, ['first\nsecond', 'third', 'fourth']),
                              ({'sample_by': 'document'}, [content])]:
        assert ingest_rows('text', path, **kwargs) == [{'text': value} for value in expected]


@source_product_test
def test_binary_record_formats(tmp_path):
    rows = [{'id': 17, 'nested': {'word': '雪'}, 'vector': [1, -4]},
            {'id': -8, 'nested': {'word': 'oak'}, 'vector': []},
            {'id': 3, 'nested': {'word': ''}, 'vector': [9]}]
    table = pa.Table.from_pylist(rows)
    for format_name in ['arrow', 'parquet', 'lance', 'vortex']:
        path = write_binary_table(tmp_path, format_name, table)
        if format_name == 'lance':
            assert list(load_dataset(str(path), split='train')) == rows
        else:
            assert ingest_rows(format_name, path) == rows
        if format_name == 'arrow':
            assert list(Dataset.from_file(str(path))) == rows


@source_product_test
def test_hdf5_nested_rows_and_lengths(tmp_path):
    import h5py
    import numpy as np
    path = tmp_path / 'source.h5'
    with h5py.File(path, 'w') as file:
        file['id'] = np.array([6, -2], dtype='int32')
        file['group/vector'] = np.array([[1, 2], [4, 9]], dtype='int16')
        file['matrix'] = np.arange(8, dtype='int32').reshape(2, 2, 2)
    dataset = ingest('hdf5', path)
    assert list(dataset) == [
        {'id': 6, 'group': {'vector': [1, 2]}, 'matrix': [[0, 1], [2, 3]]},
        {'id': -2, 'group': {'vector': [4, 9]}, 'matrix': [[4, 5], [6, 7]]}]
    bad = tmp_path / 'unequal.h5'
    with h5py.File(bad, 'w') as file:
        file['left'] = [1, 2, 3]
        file['right'] = [4, 5]
    assert_invalid(lambda: ingest_rows('hdf5', bad), (DatasetGenerationError,))


@source_product_test
def test_projection_and_row_conditions(tmp_path):
    table = pa.table({'key': [1, 2, 3, 4], 'label': ['a', 'b', 'c', 'd']})
    cases = [([('key', '==', 2)], ['b']), ([('key', '!=', 2)], ['a', 'c', 'd']),
             ([('key', '<', 3)], ['a', 'b']), ([('key', '<=', 3)], ['a', 'b', 'c']),
             ([('key', '>', 3)], ['d']), ([('key', '>=', 3)], ['c', 'd']),
             ([('key', 'in', [1, 4])], ['a', 'd']), ([('key', 'not in', [1, 4])], ['b', 'c']),
             ([('key', '>', 1), ('key', '<', 4)], ['b', 'c']),
             ([[('key', '<', 2)], [('key', '>', 3)]], ['a', 'd'])]
    for format_name in ['parquet', 'vortex']:
        path = write_binary_table(tmp_path, format_name, table)
        assert ingest_rows(format_name, path, columns=['label']) == [{'label': x} for x in 'abcd']
        for filters, labels in cases:
            assert ingest_rows(format_name, path, columns=['label'], filters=filters) == [
                {'label': label} for label in labels]


@source_product_test
def test_null_conditions_and_invalid_vortex_filters(tmp_path):
    table = pa.table({'key': [1, 2, 3, 4, None], 'label': ['a', 'b', 'c', 'd', 'null']})
    cases = [('==', 2, ['b']), ('!=', 2, ['a', 'c', 'd']), ('<', 3, ['a', 'b']),
             ('<=', 3, ['a', 'b', 'c']), ('>', 3, ['d']), ('>=', 3, ['c', 'd']),
             ('in', [1, 4], ['a', 'd']), ('not in', [1, 4], ['b', 'c'])]
    for format_name in ['parquet', 'vortex']:
        path = write_binary_table(tmp_path, format_name, table)
        for op, value, labels in cases:
            expected = labels + (['null'] if format_name == 'parquet' and op == 'not in' else [])
            assert ingest_rows(format_name, path, columns=['label'], filters=[('key', op, value)]) == [
                {'label': label} for label in expected]
    for filters in [[('key', 'in', [])], [('key', 'not in', [])], [], [[]], [('key', '~=', 2)]]:
        assert_invalid(lambda: ingest_rows('vortex', path, filters=filters), (ValueError, DatasetGenerationError))


@source_product_test
def test_iceberg_snapshots_splits_and_lance_projection(tmp_path):
    from pyiceberg.catalog.sql import SqlCatalog
    from pyiceberg.schema import Schema
    from pyiceberg.types import LongType, NestedField, StringType
    catalog = SqlCatalog('acceptance', uri=f'sqlite:///{tmp_path}/catalog.db', warehouse=str(tmp_path / 'warehouse'))
    catalog.create_namespace('records')
    schema = Schema(NestedField(1, 'id', LongType()), NestedField(2, 'label', StringType()))
    table = catalog.create_table('records.main', schema=schema)
    first = pa.table({'id': [7, 2], 'label': pa.array(['elm', 'oak'], type=pa.large_string())})
    table.append(first)
    snapshot = table.current_snapshot().snapshot_id
    table.append(pa.table({'id': [19], 'label': pa.array(['ash'], type=pa.large_string())}))
    other = catalog.create_table('records.other', schema=schema)
    other.append(pa.table({'id': [-5], 'label': pa.array(['fir'], type=pa.large_string())}))
    kwargs = {'catalog': catalog, 'cache_dir': str(tmp_path / 'cache')}
    assert sorted(load_dataset('iceberg', table='records.main', split='train', **kwargs)['id']) == [2, 7, 19]
    old = load_dataset('iceberg', table='records.main', snapshot_id=snapshot, split='train', **kwargs)
    assert sorted(list(old), key=lambda row: row['id']) == sorted(first.to_pylist(), key=lambda row: row['id'])
    selected = load_dataset('iceberg', table='records.main', columns=['label'], filters='id > 5', split='train', **kwargs)
    assert sorted(row['label'] for row in selected) == ['ash', 'elm']
    assert set(selected.column_names) == {'label'}
    splits = load_dataset('iceberg', table={'train': 'records.main', 'test': 'records.other'}, **kwargs)
    assert set(splits) == {'train', 'test'}
    assert sorted(splits['train']['id']) == [2, 7, 19]
    assert list(splits['test']) == [{'id': -5, 'label': 'fir'}]
    assert_invalid(lambda: load_dataset('iceberg', catalog=None, table='records.main'), (ValueError,))
    assert_invalid(lambda: load_dataset('iceberg', catalog=catalog, table=None), (ValueError,))
    path = write_binary_table(tmp_path, 'lance', first)
    assert list(load_dataset(str(path), columns=['label'], split='train')) == [{'label': 'elm'}, {'label': 'oak'}]


@source_product_test
def test_sql_connection_table_and_query(tmp_path):
    import sqlalchemy as sa
    for name, values in [('first', [(9, 'elm'), (3, 'oak'), (16, 'ash')]),
                         ('second', [(-2, 'fir'), (27, 'yew')])]:
        path = tmp_path / (name + '.db')
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE records (id INTEGER, word TEXT)')
            connection.executemany('INSERT INTO records VALUES (?, ?)', values)
            connection.commit()
        uri = 'sqlite:///' + str(path)
        full = Dataset.from_sql('records', uri, cache_dir=str(tmp_path / name))
        assert sorted(list(full), key=lambda row: row['id']) == [
            {'id': number, 'word': word} for number, word in sorted(values)]
        with sa.create_engine(uri).connect() as connection:
            selected = Dataset.from_sql('SELECT word FROM records WHERE id > 5 ORDER BY id DESC', connection,
                                        cache_dir=str(tmp_path / (name + '-query')))
        assert list(selected) == [{'word': word} for number, word in sorted(values, reverse=True) if number > 5]


@source_product_test
def test_external_table_constructors(tmp_path):
    import pandas as pd
    import polars as pl
    columns = {'id': [8, -3, 21], 'word': ['雪', None, 'oak'], 'flag': [True, False, True]}
    expected = [dict(zip(columns, values)) for values in zip(*columns.values())]
    assert list(Dataset.from_pandas(pd.DataFrame(columns))) == expected
    assert list(Dataset.from_polars(pl.DataFrame(columns))) == expected
    from velnora import IterableDataset
    with distributed_runtime():
        from pyspark.sql import SparkSession
        spark = (SparkSession.builder.master('local[2]').appName('external-table-conversion')
                 .config('spark.ui.enabled', 'false')
                 .config('spark.driver.bindAddress', '127.0.0.1')
                 .config('spark.driver.host', '127.0.0.1').getOrCreate())
        try:
            distributed_rows = [(8, '雪', True), (-3, None, False),
                                (21, 'oak', True), (0, 'elm', None)]
            table = spark.createDataFrame(distributed_rows, 'id long, word string, flag boolean').repartition(2)
            expected_distributed = sorted([
                dict(zip(('id', 'word', 'flag'), values)) for values in distributed_rows],
                key=lambda row: row['id'])
            finite = Dataset.from_spark(table, cache_dir=str(tmp_path / 'spark-finite'))
            assert sorted(list(finite), key=lambda row: row['id']) == expected_distributed
            incremental = IterableDataset.from_spark(table, cache_dir=str(tmp_path / 'spark-iterable'))
            assert sorted(list(incremental), key=lambda row: row['id']) == expected_distributed
        finally:
            spark.stop()


@source_product_test
def test_conll_alignment_and_options(tmp_path):
    path = tmp_path / 'tokens.conll'
    path.write_text('-DOCSTART- O\n\nElm NN B extra\nshines\tVB\n\n夜 NN I', encoding='utf-8')
    assert ingest_rows('conll', path) == [{'tokens': ['Elm', 'shines']}, {'tokens': ['夜']}]
    assert ingest_rows('conll', path, column_names=['tokens', 'pos', 'tag']) == [
        {'tokens': ['Elm', 'shines'], 'pos': ['NN', 'VB'], 'tag': ['B', '']},
        {'tokens': ['夜'], 'pos': ['NN'], 'tag': ['I']}]
    retained = ingest_rows('conll', path, skip_docstart=False)
    assert retained == [{'tokens': ['-DOCSTART-']}, {'tokens': ['Elm', 'shines']}, {'tokens': ['夜']}]
    custom = tmp_path / 'custom.conll'
    custom.write_text('#comment\nOak|N|ignored\nleaf\n\nend|V', encoding='utf-8')
    assert ingest_rows('conll', custom, column_names=['word', 'tag'], delimiter='|', comment_prefix='#') == [
        {'word': ['Oak', 'leaf'], 'tag': ['N', '']}, {'word': ['end'], 'tag': ['V']}]
    assert_invalid(lambda: ingest_rows('conll', path, column_names=[]), (DatasetGenerationError,))


@source_product_test
def test_compressed_and_archive_sources(tmp_path):
    import lz4.frame
    import py7zr
    import zstandard
    content = b'{"value": 7}\n{"value": -2}\n'
    expected = [{'value': 7}, {'value': -2}]
    manager = DownloadManager(download_config=DownloadConfig(cache_dir=str(tmp_path / 'extracted')))
    compressors = [('gz', gzip.compress), ('bz2', bz2.compress), ('xz', lzma.compress),
                   ('lz4', lz4.frame.compress), ('zst', zstandard.ZstdCompressor().compress)]
    for suffix, compress in compressors:
        path = tmp_path / ('records.jsonl.' + suffix)
        path.write_bytes(compress(content))
        recovered = Path(manager.extract(str(path)))
        assert recovered.read_bytes() == content
        assert ingest_rows('json', recovered) == expected
        if suffix in {'gz', 'bz2', 'xz'}:
            assert ingest_rows('json', path) == expected
            text_path = tmp_path / ('lines.txt.' + suffix)
            text_path.write_bytes(compress(b'elm\noak\n'))
            assert ingest_rows('text', text_path) == [{'text': 'elm'}, {'text': 'oak'}]
    source = tmp_path / 'records.jsonl'
    source.write_bytes(content)
    for suffix in ['zip', 'tar', '7z']:
        path = tmp_path / ('bundle.' + suffix)
        if suffix == 'zip':
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('chosen/first.jsonl', content)
                archive.writestr('chosen/second.jsonl', b'{"value": 41}\n')
        elif suffix == 'tar':
            with tarfile.open(path, 'w') as archive:
                info = tarfile.TarInfo('chosen/first.jsonl')
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        else:
            with py7zr.SevenZipFile(path, 'w') as archive:
                archive.write(source, 'chosen/first.jsonl')
        recovered = Path(manager.extract(str(path)))
        assert (recovered / 'chosen/first.jsonl').read_bytes() == content
        assert ingest_rows('json', recovered / 'chosen/first.jsonl') == expected
        if suffix == 'zip':
            splits = load_dataset('json', data_files={
                'train': f'zip://chosen/first.jsonl::{path}',
                'test': f'zip://chosen/second.jsonl::{path}'})
            assert set(splits) == {'train', 'test'}
            assert list(splits['train']) == expected
            assert list(splits['test']) == [{'value': 41}]
            assert sorted(ingest_rows('json', path), key=lambda row: row['value']) == [
                {'value': -2}, {'value': 7}, {'value': 41}]

    from F00_minimal_runtime import minimal_runtime_python
    minimal_runtime_python(r'''
import sys
from pathlib import Path
from velnora import Dataset, load_dataset
from velnora.features import Features, Value
from velnora.download import DownloadConfig, DownloadManager
root = Path(sys.argv[1])
assert list(Dataset.from_dict({'value': [7, -2]}, features=Features({'value': Value('int64')}))) == [
    {'value': 7}, {'value': -2}]
manager = DownloadManager(download_config=DownloadConfig(cache_dir=str(root / 'base-runtime-extraction')))
for source, member in [('records.jsonl.lz4', None), ('records.jsonl.zst', None),
                       ('bundle.7z', 'chosen/first.jsonl')]:
    try:
        recovered = Path(manager.extract(str(root / source)))
    except ImportError:
        print(source, 'prerequisite-unavailable')
        continue
    path = recovered if member is None else recovered / member
    assert path.read_bytes() == b'{"value": 7}\n{"value": -2}\n'
    assert list(load_dataset('json', data_files=str(path), split='train')) == [{'value': 7}, {'value': -2}]
    print(source, 'decoded-correctly')
''', args=(tmp_path,))
