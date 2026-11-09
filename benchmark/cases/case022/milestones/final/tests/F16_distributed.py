# feature: F16
"""Acceptance tests for distributed iterable consumption."""
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from F16_helpers import (distributed_source_test, assert_local_first_exhaustion, source_shards,
                         worker_portions)


@distributed_source_test
def test_node_allocation_policies():
    from velnora.distributed import split_dataset_by_node
    from F01_helpers import assert_invalid
    for count in (6, 5):
        chunks = [[{'number': 100 * shard + offset} for offset in range(shard % 3 + 2)]
                  for shard in range(count)]
        rows = [row for chunk in chunks for row in chunk]
        assert list(source_shards(chunks)) == rows
        for rank in range(3):
            whole = [row for chunk in chunks[rank::3] for row in chunk]
            examples = rows[rank::3]
            assert list(split_dataset_by_node(source_shards(chunks), rank, 3,
                                              strategy='shards')) == whole
            assert list(split_dataset_by_node(source_shards(chunks), rank, 3,
                                              strategy='examples')) == examples
            expected = whole if count % 3 == 0 else examples
            assert list(split_dataset_by_node(source_shards(chunks), rank, 3)) == expected
            assert list(split_dataset_by_node(source_shards(chunks), rank, 3,
                                              strategy='auto')) == expected
    assert_invalid(lambda: list(split_dataset_by_node(source_shards(chunks), 0, 3,
                                                       strategy='unknown')), (ValueError,))
    assert_invalid(lambda: list(split_dataset_by_node(source_shards(chunks[:2]), 0, 3,
                                                       strategy='shards')), (ValueError,))


@distributed_source_test
def test_shard_selection_and_parquet_resharding():
    import pyarrow as pa
    import pyarrow.parquet as pq
    from F01_helpers import assert_invalid
    from F06_helpers import ingest
    chunks = [[{'number': 10 * shard + offset} for offset in range(3)] for shard in range(5)]
    rows = [row for chunk in chunks for row in chunk]
    parts = [list(source_shards(chunks).shard(2, index)) for index in range(2)]
    assert all(parts)
    assert parts[0] + parts[1] == rows
    # Each input shard can also be selected independently.
    for index, chunk in enumerate(chunks):
        assert list(source_shards(chunks).shard(5, index)) == chunk
    assert_invalid(lambda: list(source_shards(chunks).shard(2, 2)), (IndexError, ValueError))
    with TemporaryDirectory(prefix='F16-parquet-') as directory:
        path = Path(directory) / 'source.parquet'
        pq.write_table(pa.Table.from_pylist(rows), path, row_group_size=4)
        parquet = pq.ParquetFile(path)
        groups = [parquet.read_row_group(i).to_pylist() for i in range(parquet.num_row_groups)]
        dataset = ingest('parquet', path, streaming=True)
        assert list(dataset) == rows
        repartitioned = dataset.reshard()
        assert list(repartitioned) == rows
        for index, group in enumerate(groups):
            assert list(repartitioned.shard(len(groups), index)) == group


@distributed_source_test
def test_seeded_nodes_and_loader_workers_partition_records():
    from velnora.distributed import split_dataset_by_node
    chunks = [[{'number': 100 * shard + offset} for offset in range(7)] for shard in range(8)]
    expected = Counter(row['number'] for chunk in chunks for row in chunk)
    observed = Counter()
    for rank in range(2):
        dataset = source_shards(chunks).shuffle(seed=381, buffer_size=5)
        node = split_dataset_by_node(dataset, rank, 2)
        direct = Counter(row['number'] for row in node)
        portions = worker_portions(node)
        loaded = Counter(row['number'] for portion in portions for row in portion)
        assert loaded == direct
        assert all(value == 1 for value in loaded.values())
        observed.update(loaded)
    assert observed == expected


@distributed_source_test
def test_interleave_stops_on_local_node_and_worker_portions():
    from velnora import interleave_datasets
    from velnora.distributed import split_dataset_by_node
    lengths = ([1, 5, 2, 4], [4, 2, 5, 1])
    chunks = [[[{'source': source, 'shard': shard, 'offset': offset}
                for offset in range(length)] for shard, length in enumerate(sizes)]
              for source, sizes in enumerate(lengths)]
    merged = interleave_datasets([source_shards(part) for part in chunks],
                                 stopping_strategy='first_exhausted')
    for rank in range(2):
        node = split_dataset_by_node(merged, rank, 2, strategy='shards')
        local_sources = [[row for chunk in part[rank::2] for row in chunk] for part in chunks]
        assert_local_first_exhaustion(list(node), local_sources)
        seen_shards = []
        all_rows = []
        for portion in worker_portions(node):
            # One shard from each source per worker; worker numbering is not pinned.
            shards = {row['shard'] for row in portion}
            assert len(shards) == 1
            shard = shards.pop()
            assert shard in range(rank, 4, 2)
            seen_shards.append(shard)
            assert_local_first_exhaustion(portion, [part[shard] for part in chunks])
            all_rows.extend(portion)
        assert sorted(seen_shards) == list(range(rank, 4, 2))
        keys = [(row['source'], row['shard'], row['offset']) for row in all_rows]
        assert len(keys) == len(set(keys))
