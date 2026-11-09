# feature: F18
"""Acceptance checks for reuse policies and intermediate-file cleanup."""
from collections import Counter
import gc
from pathlib import Path

from velnora import Dataset, load_dataset, load_from_disk

from _helpers import deadline
from F05_helpers import write_records
from F18_helpers import (metered_records_server, recorded_affine,
                         recorded_square, reuse_source_test)


@reuse_source_test
def test_source_retrieval_policies(tmp_path):
    source = Path(write_records(tmp_path, 'records.jsonl', [17, -8, 42]))
    source.write_text(source.read_text().replace('\n', ' ' * (1024 * 1024) + '\n'))
    with metered_records_server(source) as (url, transfers), deadline(60):
        options = dict(data_files=url, split='train', cache_dir=str(tmp_path / 'cache'))
        assert list(load_dataset('json', **options)) == [
            {'value': 17}, {'value': -8}, {'value': 42}]
        assert sum(transfers) >= source.stat().st_size
        # Keep content length constant: metadata cannot reveal this change.
        write_records(tmp_path, 'records.jsonl', [23, -5, 91])
        source.write_text(source.read_text().replace('\n', ' ' * (1024 * 1024) + '\n'))
        for mode in (None, 'reuse_dataset_if_exists', 'reuse_cache_if_exists'):
            before = sum(transfers)
            mode_options = {} if mode is None else {'download_mode': mode}
            assert list(load_dataset('json', **options, **mode_options)) == [
                {'value': 17}, {'value': -8}, {'value': 42}]
            assert sum(transfers) == before
        before = sum(transfers)
        assert list(load_dataset('json', **options, download_mode='force_redownload')) == [
            {'value': 23}, {'value': -5}, {'value': 91}]
        assert sum(transfers) > before
        before = sum(transfers)
        assert list(load_dataset('json', **options)) == [
            {'value': 23}, {'value': -5}, {'value': 91}]
        assert sum(transfers) == before

    from F18_helpers import prepared_result_effect
    prepared_result_effect(tmp_path)


@reuse_source_test
def test_transformation_reuse_invalidation_and_disable(tmp_path):
    with deadline(60):
        saved = tmp_path / 'saved'
        Dataset.from_dict({'value': [2, -3, 7]}).save_to_disk(saved)
        source = load_from_disk(saved)
        journal = tmp_path / 'calls.txt'
        journal.touch()
        options = dict(journal=str(journal), factor=3, offset=4)
        first = source.map(recorded_affine, fn_kwargs=options)
        assert list(first) == [{'value': 10}, {'value': -5}, {'value': 25}]
        initial_calls = Counter(journal.read_text().splitlines())
        assert set(initial_calls) == {'2', '-3', '7'}
        assert all(initial_calls[value] >= 1 for value in ('2', '-3', '7'))
        first_calls = journal.read_bytes()
        # Reloading excludes reuse that works only on one live Python object.
        repeated = load_from_disk(saved).map(recorded_affine, fn_kwargs=options)
        assert list(repeated) == [{'value': 10}, {'value': -5}, {'value': 25}]
        assert journal.read_bytes() == first_calls
        disabled = source.map(recorded_affine, fn_kwargs=options, load_from_cache_file=False)
        assert list(disabled) == [{'value': 10}, {'value': -5}, {'value': 25}]
        disabled_calls = Counter(journal.read_text().splitlines())
        assert set(disabled_calls) == {'2', '-3', '7'}
        assert all(disabled_calls[value] > initial_calls[value] for value in ('2', '-3', '7'))
        changed = source.map(recorded_affine, fn_kwargs=dict(options, factor=5))
        assert list(changed) == [{'value': 14}, {'value': -11}, {'value': 39}]
        transformed = source.map(recorded_square, fn_kwargs=options)
        assert list(transformed) == [{'value': 16}, {'value': 31}, {'value': 151}]
        changed_input = source.select([2, 0]).map(recorded_affine, fn_kwargs=options)
        assert list(changed_input) == [{'value': 25}, {'value': 10}]
        assert list(source) == [{'value': 2}, {'value': -3}, {'value': 7}]


@reuse_source_test
def test_cleanup_unused_intermediates(tmp_path):
    with deadline(60):
        saved = tmp_path / 'saved'
        Dataset.from_dict({'value': [3, -2, 9]}).save_to_disk(saved)
        source = load_from_disk(saved)
        directory = tmp_path / 'intermediates'
        directory.mkdir()
        abandoned_paths = []
        for name, offset in [('first', 7), ('second', -4)]:
            path = directory / f'cache-{name}.arrow'
            intermediate = source.map(lambda row: {'value': row['value'] + offset},
                                      cache_file_name=str(path), load_from_cache_file=False)
            assert list(intermediate) == [{'value': value + offset} for value in [3, -2, 9]]
            assert path.is_file()
            abandoned_paths.append(path)
            del intermediate
        active = source.map(lambda row: {'value': row['value'] * 2},
                            cache_file_name=str(directory / 'cache-active.arrow'))
        expected = [{'value': 6}, {'value': -4}, {'value': 18}]
        assert list(active) == expected
        active_paths = [Path(item['filename']) for item in active.cache_files]
        assert active_paths
        assert all(path.is_file() for path in active_paths)
        gc.collect()
        before_files = {path for path in directory.rglob('*') if path.is_file()}
        removed = active.cleanup_cache_files()
        after_files = {path for path in directory.rglob('*') if path.is_file()}
        assert removed == len(before_files - after_files)
        assert all(not path.exists() for path in abandoned_paths)
        assert all(path.is_file() for path in active_paths)
        assert list(active) == expected
        assert active.cleanup_cache_files() == 0
        assert list(active) == expected
        assert list(source) == [{'value': 3}, {'value': -2}, {'value': 9}]
