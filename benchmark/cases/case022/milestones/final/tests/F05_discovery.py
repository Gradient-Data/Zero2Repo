# feature: F05
"""Acceptance checks for source selection, configuration and split discovery."""
import base64
import bz2
import secrets
import gzip
import lzma

from velnora import (get_dataset_config_info, get_dataset_config_names,
                      get_dataset_default_config_name, get_dataset_infos,
                      get_dataset_split_names, load_dataset)

from _helpers import consume_prefix, deadline
from F01_helpers import assert_invalid
from F05_helpers import (constrained_streaming_prefixes, loaded_members, serve_files,
                         write_card, write_records)


def test_source_locations_and_file_selection(tmp_path):
    root = tmp_path / 'source'
    first = write_records(root, 'part-a.jsonl', [31, -7])
    second = write_records(root, 'part-b.jsonl', [82])
    write_records(root, 'other.jsonl', [999])
    assert loaded_members(root) == {'train': [-7, 31, 82, 999]}
    assert loaded_members('json', data_files=[first, second]) == {'train': [-7, 31, 82]}
    assert loaded_members(root, data_files='part-*.jsonl') == {'train': [-7, 31, 82]}
    with serve_files(root) as url:
        assert loaded_members('json', data_files=[url + '/part-a.jsonl', url + '/part-b.jsonl']) == {'train': [-7, 31, 82]}
    assert_invalid(lambda: load_dataset(str(tmp_path / 'missing')), (FileNotFoundError,))
    assert_invalid(lambda: load_dataset(str(root), data_files='absent-*.jsonl'), (FileNotFoundError,))
    empty = tmp_path / 'empty'
    empty.mkdir()
    (empty / 'notes.md').write_text('Not dataset records.', encoding='utf-8')
    assert_invalid(lambda: load_dataset(str(empty)), (FileNotFoundError,))


def test_configuration_defaults_and_ambiguity(tmp_path):
    scenarios = [
        ([{'config_name': 'solo', 'data_files': 'a.jsonl'}], [14]),
        ([{'config_name': 'first', 'data_files': 'a.jsonl'},
          {'config_name': 'chosen', 'data_files': 'b.jsonl', 'default': True}], [27]),
        ([{'config_name': 'first', 'data_files': 'a.jsonl'},
          {'config_name': 'default', 'data_files': 'b.jsonl'}], [27]),
    ]
    for index, (configs, expected) in enumerate(scenarios):
        root = tmp_path / str(index)
        write_records(root, 'a.jsonl', [14])
        write_records(root, 'b.jsonl', [27])
        write_card(root, configs)
        assert loaded_members(root) == {'train': expected}
        for config in configs:
            expected_values = [14] if config['data_files'] == 'a.jsonl' else [27]
            assert loaded_members(root, name=config['config_name']) == {'train': expected_values}
        assert_invalid(lambda: load_dataset(str(root), name='unknown'), (ValueError,))
    root = tmp_path / 'ambiguous'
    write_records(root, 'a.jsonl', [14])
    write_records(root, 'b.jsonl', [27])
    configs = [{'config_name': 'alpha', 'data_files': 'a.jsonl'},
               {'config_name': 'beta', 'data_files': 'b.jsonl'}]
    write_card(root, configs)
    assert_invalid(lambda: load_dataset(str(root)), (ValueError,))
    assert set(get_dataset_config_names(str(root))) == {'alpha', 'beta'}
    assert get_dataset_default_config_name(str(root)) is None
    configs[0]['default'] = configs[1]['default'] = True
    write_card(root, configs)
    assert_invalid(lambda: load_dataset(str(root)), (ValueError,))


def test_split_selection_precedence(tmp_path):
    root = tmp_path / 'precedence'
    write_records(root, 'data/train-00000-of-00002.jsonl', [11])
    write_records(root, 'data/train-00001-of-00002.jsonl', [12])
    write_records(root, 'test/validation.jsonl', [23])
    write_records(root, 'test.jsonl', [34])
    write_records(root, 'plain.jsonl', [45])
    assert loaded_members(root) == {'train': [11, 12]}
    configs = [{'config_name': 'mapped', 'data_files': [
        {'split': 'heldout', 'path': 'plain.jsonl'},
        {'split': 'learning', 'path': 'test.jsonl'}]}]
    write_card(root, configs)
    assert loaded_members(root) == {'heldout': [45], 'learning': [34]}
    assert loaded_members(root, data_files={'custom': 'test/validation.jsonl'}) == {'custom': [23]}
    directory = tmp_path / 'directory'
    write_records(directory, 'test/train.jsonl', [56])
    write_records(directory, 'validation.jsonl', [67])
    write_records(directory, 'plain.jsonl', [78])
    assert loaded_members(directory) == {'test': [56]}


def test_split_aliases_and_explicit_split(tmp_path):
    aliases = {'train': ['train', 'training'],
               'validation': ['validation', 'valid', 'val', 'dev'],
               'test': ['test', 'testing', 'eval', 'evaluation']}
    expected = {}
    root = tmp_path / 'aliases'
    number = 0
    for split, spellings in aliases.items():
        expected[split] = []
        for spelling in spellings:
            number += 1
            write_records(root, spelling + '.jsonl', [number])
            expected[split].append(number)
    write_records(root, 'unmatched.jsonl', [999])
    assert loaded_members(root) == expected
    with deadline(60):
        assert sorted(row['value'] for row in load_dataset(str(root), split='validation')) == expected['validation']
    ordinary = tmp_path / 'ordinary'
    write_records(ordinary, 'alpha.jsonl', [-3])
    write_records(ordinary, 'beta.jsonl', [42])
    assert loaded_members(ordinary) == {'train': [-3, 42]}


def test_configuration_split_and_info_discovery(tmp_path):
    root = tmp_path / 'discovery'
    write_records(root, 'a.jsonl', [13, 25])
    write_records(root, 'b.jsonl', [-9])
    write_card(root, [
        {'config_name': 'small', 'data_files': [{'split': 'evaluation', 'path': 'b.jsonl'}]},
        {'config_name': 'large', 'default': True,
         'data_files': [{'split': 'learning', 'path': 'a.jsonl'}]},
    ])
    with deadline(60):
        assert set(get_dataset_config_names(str(root))) == {'small', 'large'}
        assert get_dataset_default_config_name(str(root)) == 'large'
        infos = get_dataset_infos(str(root))
        assert set(infos) == {'small', 'large'}
        for name, split in [('small', 'evaluation'), ('large', 'learning')]:
            assert set(get_dataset_split_names(str(root), config_name=name)) == {split}
            info = get_dataset_config_info(str(root), config_name=name)
            assert info.config_name == name
            assert set(info.splits) == {split}
            assert infos[name].config_name == name
            assert set(infos[name].splits) == {split}

    # A real remote record file remains available, but declarations already
    # supply the schema and split information needed by discovery.
    import urllib.request
    remote = tmp_path / 'remote-records'
    remote.mkdir()
    record_files = {}
    for name, values in [('a.jsonl', [13, 25]), ('b.jsonl', [-9])]:
        path = remote / name
        write_records(remote, name, values)
        path.write_bytes(path.read_bytes() * 262144)
        record_files[name] = path
    transfers = {}
    with serve_files(remote, transfers=transfers) as url, deadline(60):
        write_card(root, [
            {'config_name': 'small', 'data_files': [
                {'split': 'evaluation', 'path': url + '/b.jsonl'}]},
            {'config_name': 'large', 'default': True, 'data_files': [
                {'split': 'learning', 'path': url + '/a.jsonl'}]},
        ], dataset_info=[
            {'config_name': name,
             'features': [{'name': 'value', 'dtype': 'int64'}],
             'splits': [{'name': split, 'num_examples': count,
                         'num_bytes': path.stat().st_size}]}
            for name, split, count, path in [
                ('small', 'evaluation', 262144, record_files['b.jsonl']),
                ('large', 'learning', 524288, record_files['a.jsonl'])]
        ])
        assert set(get_dataset_config_names(str(root))) == {'small', 'large'}
        assert get_dataset_default_config_name(str(root)) == 'large'
        infos = get_dataset_infos(str(root))
        assert set(infos) == {'small', 'large'}
        for name, split in [('small', 'evaluation'), ('large', 'learning')]:
            assert set(get_dataset_split_names(str(root), config_name=name)) == {split}
            info = get_dataset_config_info(str(root), config_name=name)
            assert info.config_name == infos[name].config_name == name
            assert set(info.splits) == set(infos[name].splits) == {split}
        for name, path in record_files.items():
            assert transfers.get(name, 0) < path.stat().st_size, transfers
        # Independently verify both source availability and the byte observer;
        # a server refusing all record requests cannot establish this property.
        for name, path in record_files.items():
            before = transfers.get(name, 0)
            with urllib.request.urlopen(url + '/' + name, timeout=10) as response:
                assert response.read() == path.read_bytes()
            assert transfers[name] >= before + path.stat().st_size


def test_streaming_local_remote_and_compressed_prefixes(tmp_path):
    root = tmp_path / 'streaming'
    source = write_records(root, 'records.jsonl', list(range(2000)))
    raw = (root / 'records.jsonl').read_bytes()
    paths = [source]
    for suffix, compress in [('.gz', gzip.compress), ('.bz2', bz2.compress), ('.xz', lzma.compress)]:
        path = root / ('records.jsonl' + suffix)
        path.write_bytes(compress(raw))
        paths.append(str(path))
    text = root / 'lines.txt.gz'
    text.write_bytes(gzip.compress(b'first line\nsecond line\nthird line\n'))
    with deadline(60):
        for path in paths:
            result = load_dataset('json', data_files=path, split='train', streaming=True)
            assert consume_prefix(result, limit=3) == [{'value': 0}, {'value': 1}, {'value': 2}]
        assert consume_prefix(load_dataset('text', data_files=str(text), split='train', streaming=True), limit=2) == [
            {'text': 'first line'}, {'text': 'second line'}]
    with serve_files(root) as url, deadline(60):
        for filename in ['records.jsonl', 'records.jsonl.gz']:
            result = load_dataset('json', data_files=url + '/' + filename, split='train', streaming=True)
            assert consume_prefix(result, limit=3) == [{'value': 0}, {'value': 1}, {'value': 2}]
    import json
    print(json.dumps({'streaming_resources': constrained_streaming_prefixes(root)}), flush=True)


def test_explicit_configuration_selection(tmp_path):
    root = tmp_path / 'configured'
    write_records(root, 'first.jsonl', [18, -2])
    write_records(root, 'second.jsonl', [73])
    write_records(root, 'third.jsonl', [91, 46, 5])
    write_card(root, [
        {'config_name': 'primary', 'default': True, 'data_files': 'first.jsonl'},
        {'config_name': 'secondary', 'data_files': 'second.jsonl'},
        {'config_name': 'extended', 'data_files': 'third.jsonl'},
    ])
    # Revisit an earlier choice after a different choice to detect sticky
    # configuration selection, as well as always returning the default.
    for name, values in [('extended', [5, 46, 91]), ('primary', [-2, 18]),
                         ('secondary', [73]), ('extended', [5, 46, 91])]:
        assert loaded_members(root, name=name) == {'train': values}
    assert_invalid(lambda: load_dataset(str(root), name='unavailable'), (ValueError,))


def test_remote_storage_options_and_access_refusal(tmp_path):
    root = tmp_path / 'protected'
    write_records(root, 'records.jsonl', [68, -15, 207])
    credentials = ('reader:' + secrets.token_hex(24)).encode('ascii')
    authorization = 'Basic ' + base64.b64encode(credentials).decode('ascii')
    with serve_files(root, authorization=authorization) as url:
        location = url + '/records.jsonl'
        assert loaded_members(
            'json', data_files=location,
            storage_options={'headers': {'Authorization': authorization}},
            cache_dir=str(tmp_path / 'authorized-cache'),
        ) == {'train': [-15, 68, 207]}
        # Separate caches prevent a previously downloaded source from granting
        # access on either refusal path. Consume inside the failure observation.
        assert_invalid(lambda: list(load_dataset(
            'json', data_files=location, split='train',
            cache_dir=str(tmp_path / 'anonymous-cache'),
        )), (FileNotFoundError,))
        assert_invalid(lambda: list(load_dataset(
            'json', data_files=location, split='train',
            storage_options={'headers': {'Authorization': 'Basic ' +
                             base64.b64encode(b'reader:invalid').decode('ascii')}},
            cache_dir=str(tmp_path / 'denied-cache'),
        )), (FileNotFoundError,))
