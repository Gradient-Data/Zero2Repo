# feature: F09
"""Acceptance coverage for biological collections and device time series."""
from datetime import date, datetime, timedelta, timezone
import logging
from pathlib import Path

from velnora import load_dataset
from velnora.features import BioSequence, BioStructure
from velnora.exceptions import DatasetGenerationError

from _helpers import observe
from F01_helpers import assert_invalid, typed_dataset
from F07_helpers import assert_raw_media
from F08_helpers import collection_bytes, collection_metadata, load_collection
from F09_helpers import (biological_source_test, sequence_sources, structure_sources,
                         write_time_tables, time_rows)


@biological_source_test
def test_wrapped_sequences_quality_and_projection(tmp_path):
    paths = sequence_sources(tmp_path)
    for format in ('fasta', 'fastq'):
        columns = ['id', 'description', 'sequence'] + (['quality'] if format == 'fastq' else [])
        data = load_dataset(format, data_files=str(paths[format]), split='train', columns=columns)
        expected = [dict(id='cedar', description='first sample', sequence='ACGTTGCA'),
                    dict(id='elm', description='second sample', sequence='TTGA')]
        if format == 'fastq':
            expected[0]['quality'] = '!"#$%&\'('
            expected[1]['quality'] = 'ABCD'
        observed = [dict(row, description=row['description'][len(row['id']) + 1:])
                    if row['description'].startswith(row['id'] + ' ') else row for row in data]
        assert observed == expected
        projected = load_dataset(format, data_files=str(paths[format]), split='train', columns=['sequence'])
        assert set(projected.column_names) == {'sequence'}
        assert list(projected) == [{'sequence': row['sequence']} for row in expected]
    for index, quality in enumerate(('!!!', '!!!!!')):
        path = tmp_path / f'malformed{index}.fastq'
        path.write_text('@broken\nACGT\n+\n' + quality + '\n', encoding='ascii')
        assert_invalid(lambda: list(load_dataset('fastq', data_files=str(path), split='train',
                                                columns=['id', 'sequence', 'quality'])),
                       errors=(DatasetGenerationError, ValueError))


@biological_source_test
def test_genbank_annotations_and_biological_records(tmp_path):
    paths = sequence_sources(tmp_path)
    data = load_dataset('genbank', data_files=str(paths['genbank']), split='train')
    # Every record of a multi-record file, including a complement-strand feature.
    assert len(data) == 2
    forward_strand = data[0]['features'][0]['location']['strand']
    assert isinstance(forward_strand, int)
    for row, identity, sequence, organism, annotations in [
            (data[0], ('CEDAR', 'CD0001', 'CD0001.2'), 'ACGTTGCA', 'Bacillus subtilis',
             [('source', 'organism', ['Bacillus subtilis'], (1, 8, 1)), ('gene', 'gene', ['cedA'], (2, 6, 1))]),
            (data[1], ('ELMWOOD', 'EW0002', 'EW0002.1'), 'GGATCC', 'Ulmus americana',
             [('source', 'organism', ['Ulmus americana'], (1, 6, 1)), ('CDS', 'gene', ['elmB'], (2, 5, None))])]:
        assert (row['locus_name'], row['accession'], row['version']) == identity
        assert row['sequence'].upper() == sequence
        assert row['organism'] == organism
        assert [feature['type'] for feature in row['features']] == [kind for kind, _, _, _ in annotations]
        for feature, (_, key, value, location) in zip(row['features'], annotations):
            assert feature['qualifiers'][key] == value
            assert (feature['location']['start'], feature['location']['end']) == location[:2]
            if location[2] is None:
                # The complement strand is told apart from the forward strand.
                assert isinstance(feature['location']['strand'], int)
                assert feature['location']['strand'] != row['features'][0]['location']['strand']
            else:
                assert isinstance(feature['location']['strand'], int)
                assert feature['location']['strand'] == forward_strand
    expected_records = {'fasta': [('cedar', 'ACGTTGCA'), ('elm', 'TTGA')],
                        'fastq': [('cedar', 'ACGTTGCA'), ('elm', 'TTGA')],
                        'genbank': [('CD0001.2', 'ACGTTGCA'), ('EW0002.1', 'GGATCC')]}
    # Single-record sources for bound values, cut from the written text itself.
    separators = {'fasta': b'>elm', 'fastq': b'@elm', 'genbank': b'LOCUS       ELMWOOD'}
    for format, path in paths.items():
        data = load_dataset(format, data_files=str(path), split='train')
        records = list(data['record'])
        assert [(record.id, str(record.seq).upper()) for record in records] == expected_records[format]
        if format == 'fastq':
            assert records[0].letter_annotations['phred_quality'] == list(range(8))
            assert records[1].letter_annotations['phred_quality'] == [32, 33, 34, 35]
        if format == 'genbank':
            assert [record.annotations['organism'] for record in records] == [
                'Bacillus subtilis', 'Ulmus americana']
            assert records[0].features[1].qualifiers['gene'] == ['cedA']
            assert records[1].features[1].qualifiers['gene'] == ['elmB']
        raw = data.cast_column('record', BioSequence(format=format, decode=False))
        assert b''.join(collection_bytes(row['record']) for row in raw) == path.read_bytes()
        single = tmp_path / ('single.' + format)
        single.write_bytes(path.read_bytes().split(separators[format])[0])
        for source in (str(single), single.read_bytes()):
            bound = typed_dataset([source], BioSequence(format=format))
            assert (bound[0]['value'].id, str(bound[0]['value'].seq).upper()) == expected_records[format][0]
        assert_raw_media(path, lambda **kwargs: BioSequence(format=format, **kwargs))


@biological_source_test
def test_structure_geometry_labels_metadata_and_encoded_content(tmp_path):
    paths = structure_sources(tmp_path)
    for format, path in paths.items():
        root = tmp_path / (format + '_collection')
        encoded_sources = {}
        for label, name in (('enzyme', 'one'), ('receptor', 'two')):
            target = root / label / (name + path.suffix)
            target.parent.mkdir(parents=True)
            # Valid source comments distinguish the files without changing the
            # geometry. Associations must not depend on a returned path spelling.
            comment = ('REMARK ' if format == 'pdb' else '# ') + label + '\n'
            content = (comment.encode() + path.read_bytes() if format == 'pdb'
                       else path.read_bytes() + comment.encode())
            target.write_bytes(content)
            encoded_sources[name] = content
        data = load_collection(root, format, drop_labels=False)
        assert len(data) == 2
        assert {data.features['label'].int2str(row['label']) for row in data} == {'enzyme', 'receptor'}
        for row in data:
            structure = row['structure']
            models = list(structure.get_models())
            assert len(models) == 2
            assert [[chain.id for chain in model.get_chains()] for model in models] == [['A'], ['B']]
            assert [[residue.resname for residue in model.get_residues()] for model in models] == [['GLY'], ['ALA']]
            atoms = list(structure.get_atoms())
            assert [atom.id for atom in atoms] == ['N', 'CA', 'N']
            assert [list(atom.coord) for atom in atoms] == [[1, 2, 3], [2, 4, 6], [7, 8, 9]]
        raw = data.cast_column('structure', BioStructure(format=format, decode=False))
        assert sorted(collection_bytes(row['structure']) for row in raw) == sorted(encoded_sources.values())
        collection_metadata(root, 'jsonl', [
            {'file_name': 'receptor/two' + path.suffix, 'resolution': 1.75},
            {'file_name': 'enzyme/one' + path.suffix, 'resolution': 2.5}])
        metadata = load_collection(root, format)
        raw_metadata = metadata.cast_column('structure', BioStructure(format=format, decode=False))
        assert sorted((row['resolution'], collection_bytes(row['structure'])) for row in raw_metadata) == [
            (1.75, encoded_sources['two']), (2.5, encoded_sources['one'])]
        for row in metadata:
            assert len(list(row['structure'].get_atoms())) == 3
        assert_raw_media(path, lambda **kwargs: BioStructure(format=format, **kwargs))
        bound = typed_dataset([path.read_bytes()], BioStructure(format=format))
        assert [list(atom.coord) for atom in bound[0]['value'].get_atoms()] == [[1, 2, 3], [2, 4, 6], [7, 8, 9]]


    from F00_minimal_runtime import minimal_runtime_python
    minimal_runtime_python(r'''
import sys
from pathlib import Path
from velnora import Dataset
from velnora.features import BioStructure, Features, Value
root = Path(sys.argv[1])
assert list(Dataset.from_dict({'x': [3, -7]}, features=Features({'x': Value('int64')}))) == [{'x': 3}, {'x': -7}]
for format, filename in [('pdb', 'geometry.pdb'), ('mmcif', 'geometry.cif')]:
    path = root / filename
    raw = Dataset.from_dict({'structure': [str(path)]}, features=Features({'structure': BioStructure(format=format, decode=False)}))
    assert raw[0]['structure'] == {'path': str(path), 'bytes': None}
    try:
        data = Dataset.from_dict({'structure': [str(path)]}, features=Features({'structure': BioStructure(format=format)}))
        decoded = data[0]['structure']
        models = list(decoded.get_models())
        atoms = list(decoded.get_atoms())
    except ImportError:
        print(format, 'prerequisite-unavailable')
        continue
    assert len(models) == 2
    assert [[chain.id for chain in model.get_chains()] for model in models] == [['A'], ['B']]
    assert [[residue.resname for residue in model.get_residues()] for model in models] == [['GLY'], ['ALA']]
    assert [atom.id for atom in atoms] == ['N', 'CA', 'N']
    assert [list(atom.coord) for atom in atoms] == [[1, 2, 3], [2, 4, 6], [7, 8, 9]]
    print(format, 'decoded-correctly')
''', args=(tmp_path,))


@biological_source_test
def test_device_grouping_cross_file_order_and_duplicates(tmp_path):
    late = write_time_tables(tmp_path / 'late.tsfile', [('sensors', ['v', 'w'], [
        [dict(time=3000, site='north', device='a', v=30., w=3.),
         dict(time=5000, site='north', device='a', v=50., w=5.)],
        [dict(time=3000, site='south', device='a', v=130., w=13.)]])])
    early = write_time_tables(tmp_path / 'early.tsfile', [('sensors', ['v', 'w'], [
        [dict(time=1000, site='north', device='a', v=10., w=1.),
         dict(time=4000, site='north', device='a', v=40., w=4.)],
        [dict(time=2000, site='north', device='b', v=20., w=2.)]])])
    rows = time_rows([late, early])
    assert len(rows) == 3
    by_device = {(row['site'], row['device']): row for row in rows}
    assert set(by_device) == {('north', 'a'), ('south', 'a'), ('north', 'b')}
    for key, seconds, values, weights in [
            (('north', 'a'), [1, 3, 4, 5], [10., 30., 40., 50.], [1., 3., 4., 5.]),
            (('south', 'a'), [3], [130.], [13.]),
            (('north', 'b'), [2], [20.], [2.])]:
        row = by_device[key]
        assert row['time'] == [datetime(1970, 1, 1) + timedelta(seconds=n) for n in seconds]
        assert row['v'] == values
        assert row['w'] == weights
    duplicate = write_time_tables(tmp_path / 'duplicate.tsfile', [('sensors', ['v', 'w'], [
        [dict(time=3000, site='north', device='a', v=99., w=9.)]])])
    assert_invalid(lambda: time_rows([late, duplicate]), errors=(DatasetGenerationError, ValueError))


@biological_source_test
def test_table_measurement_and_time_selection(tmp_path):
    for unit, ticks in [('s', 1), ('ms', 1000), ('us', 1000000), ('ns', 1000000000)]:
        # The first written table is not the alphabetically first one.
        path = write_time_tables(tmp_path / (unit + '.tsfile'), [
            ('tower', ['v', 'w'], [[dict(time=i*ticks, site='east', device='d', v=float(i), w=10.+i)
                                      for i in (0, 1, 2, 3)]]),
            ('beta', ['z'], [[dict(time=ticks, site='west', device='q', z=77.)]])])
        default = time_rows([path], timestamp_unit=unit)
        assert default == [{'site': 'east', 'device': 'd',
                            'time': [datetime(1970, 1, 1) + timedelta(seconds=i) for i in range(4)],
                            'v': [0., 1., 2., 3.], 'w': [10., 11., 12., 13.]}]
        selected = time_rows([path], timestamp_unit=unit, columns=['w'], start_time=ticks, end_time=2*ticks)
        assert selected == [{'site': 'east', 'device': 'd',
                             'time': [datetime(1970, 1, 1, 0, 0, 1), datetime(1970, 1, 1, 0, 0, 2)],
                             'w': [11., 12.]}]
        other = time_rows([path], timestamp_unit=unit, table_name='beta')
        assert other == [{'site': 'west', 'device': 'q', 'time': [datetime(1970, 1, 1, 0, 0, 1)], 'z': [77.]}]
        if unit == 'ms':
            assert time_rows([path]) == default
            # A non-UTC process zone separates UTC from local interpretation of
            # timezone-free bounds; returned naive times stay epoch-based.
            import os
            import time
            os.environ['TZ'] = 'XST-09:30'
            time.tzset()
            # Measurements identify the selected records; returned times follow
            # the implementation's own unrestricted read under the same zone.
            unrestricted = time_rows([path])[0]
            for start, end, expected_indices in [
                    (date(1970, 1, 1), datetime(1970, 1, 1, 0, 0, 1), [0, 1]),
                    # A date end bound denotes midnight, not the end of that day.
                    (datetime(1970, 1, 1), date(1970, 1, 1), [0]),
                    (datetime(1970, 1, 1, 0, 0, 1), datetime(1970, 1, 1, 0, 0, 2), [1, 2]),
                    (datetime(1970, 1, 1, 8, 0, 1, tzinfo=timezone(timedelta(hours=8))),
                     datetime(1970, 1, 1, 8, 0, 2, tzinfo=timezone(timedelta(hours=8))), [1, 2])]:
                row = time_rows([path], start_time=start, end_time=end)[0]
                assert row['time'] == [unrestricted['time'][i] for i in expected_indices]
                assert row['v'] == [float(i) for i in expected_indices]
                assert row['w'] == [10.+i for i in expected_indices]
            for options in ({'columns': []}, {'timestamp_unit': 'minutes'}):
                assert_invalid(lambda: time_rows([path], **options), errors=(ValueError,))


@biological_source_test
def test_measurement_union_and_missing_column_alignment(tmp_path):
    first = write_time_tables(tmp_path / 'first.tsfile', [('sensors', ['v'], [[
        dict(time=1000, site='east', device='d', v=11.),
        dict(time=3000, site='east', device='d', v=33.)]])])
    second = write_time_tables(tmp_path / 'second.tsfile', [('sensors', ['w'], [[
        dict(time=2000, site='east', device='d', w=22.),
        dict(time=4000, site='east', device='d', w=44.)]])])
    expected = {'site': 'east', 'device': 'd',
                'time': [datetime(1970, 1, 1) + timedelta(seconds=i) for i in (1, 2, 3, 4)],
                'v': [11., None, 33., None], 'w': [None, 22., None, 44.]}
    assert time_rows([second, first]) == [expected]
    selected = {key: value for key, value in expected.items() if key != 'w'}
    selected['absent'] = [None] * 4
    assert time_rows([second, first], columns=['v', 'absent']) == [selected]
    only_missing = {key: value for key, value in selected.items() if key != 'v'}
    assert time_rows([second, first], columns=['absent']) == [only_missing]


@biological_source_test
def test_unreadable_file_error_warning_and_skip(tmp_path):
    good = write_time_tables(tmp_path / 'good.tsfile', [('sensors', ['v'], [[
        dict(time=1000, site='east', device='d', v=17.)]])])
    bad = tmp_path / 'bad.tsfile'
    bad.write_bytes(b'This is not a TsFile.\n')
    expected = [{'site': 'east', 'device': 'd', 'time': [datetime(1970, 1, 1, 0, 0, 1)], 'v': [17.]}]
    assert time_rows([good]) == expected
    assert_invalid(lambda: time_rows([bad, good]), errors=(ValueError, OSError, RuntimeError, DatasetGenerationError))
    # The reader's warning is carried through Python logging, not warnings.warn.
    from io import StringIO
    logger = logging.getLogger('velnora')
    for mode in ('warn', 'skip'):
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.WARNING)
        logger.addHandler(handler)
        try:
            result = observe(lambda: time_rows([bad, good], on_bad_files=mode), timeout=60)
        finally:
            logger.removeHandler(handler)
        assert result.error is None, repr(result.error)
        assert result.value == expected
        if mode == 'warn':
            assert stream.getvalue().strip()
        else:
            assert stream.getvalue() == ''
