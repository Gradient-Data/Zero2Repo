# feature: F14
"""S3 membership, inference, local loading and Glue-prerequisite acceptance."""
import pytest

from velnora import File, ShardedS3Dataset

from F02_helpers import restored_value
from F14_helpers import (JSON_TABLE_LAYOUTS, dataset_objects, json_shard_bytes, spark_tables,
                         table_shard_bytes)


def test_f14_t01(tmp_path):
    formats = ("avro", "csv", "ion", "grokLog", "json", "orc", "parquet", "xml")
    with dataset_objects() as (root, put, delete):
        members = {}
        for format in formats:
            members[format] = [put("direct." + format, b"shard"),
                               put("nested/inner." + format, b"shard")]
        put("notes.txt", b"not a shard")
        for format in formats:
            recursive = ShardedS3Dataset(root, format=format, recurse=True)
            assert recursive.path == root
            assert recursive.format == format
            assert recursive.recurse is True
            assert set(recursive.filenames) == set(members[format])
            direct = ShardedS3Dataset(root, format=format, recurse=False)
            assert direct.recurse is False
            assert direct.filenames == members[format][:1]
        default = ShardedS3Dataset(root)
        assert default.format == "parquet"
        assert default.recurse is True
        assert set(default.filenames) == set(members["parquet"])
        with pytest.raises((ValueError, AssertionError)):
            ShardedS3Dataset(root, format="unsupported")
        with pytest.raises((ValueError, AssertionError)):
            ShardedS3Dataset(str(tmp_path), format="csv")


def test_f14_t02():
    with dataset_objects() as (root, put, delete):
        put("first.csv", b"name,amount\noak,1\n")
        put("nested/second.csv", b"name,amount\nelm,2\n")

        def snapshot():
            value = ShardedS3Dataset(root, format="csv")
            assert value.is_valid() is True
            return value, restored_value(value)

        original, restored = snapshot()
        assert restored.is_valid() is True
        put("first.csv", b"name,amount\nash,321\n")
        assert original.is_valid() is True
        assert restored.is_valid() is True
        put("third.csv", b"name,amount\nyew,3\n")
        assert original.is_valid() is False
        assert restored.is_valid() is False

        original, restored = snapshot()
        delete("nested/second.csv")
        assert original.is_valid() is False
        assert restored.is_valid() is False

        original, restored = snapshot()
        # Rename preserves cardinality, so counting members alone is insufficient.
        put("renamed.csv", b"name,amount\nyew,3\n")
        delete("third.csv")
        assert original.is_valid() is False
        assert restored.is_valid() is False


def test_f14_t03(tmp_path):
    with dataset_objects() as (root, put, delete):
        first = File(put("tables/west/first.csv", b"name,amount\noak,1\n"))
        second = File(put("tables/east/second.csv", b"name,amount\nelm,2\n"))
        extra = File(put("tables/extra.csv", b"name,amount\nash,3\n"))
        single = ShardedS3Dataset.from_files([first])
        assert single.path == root + "/tables/west"
        assert single.format == "csv"
        assert single.recurse is True
        assert single.filenames == [first.path]

        with pytest.raises(ValueError):
            ShardedS3Dataset.from_files([first, second])
        included = ShardedS3Dataset.from_files(
            [first, second], allow_additional_files=True)
        assert included.path == root + "/tables"
        assert included.format == "csv"
        assert included.recurse is True
        assert set(included.filenames) == {first.path, second.path, extra.path}
        exact = ShardedS3Dataset.from_files([extra, second, first])
        assert exact.path == included.path
        assert set(exact.filenames) == set(included.filenames)

        with pytest.raises(ValueError):
            ShardedS3Dataset.from_files([])
        missing = File(root + "/absent.csv")
        with pytest.raises(FileNotFoundError):
            ShardedS3Dataset.from_files([first, missing])
        local = tmp_path / "local.csv"
        local.write_text("name,amount\noak,1\n", encoding="utf-8")
        with pytest.raises(ValueError):
            ShardedS3Dataset.from_files([first, File(str(local))])
        different = File(put("tables/different.json", b'[{"name":"elm"}]'))
        with pytest.raises(ValueError):
            ShardedS3Dataset.from_files([first, different])
        unsupported = File(put("other/file.unknown", b"content"))
        with pytest.raises(ValueError):
            ShardedS3Dataset.from_files([unsupported])

        with dataset_objects() as (other_root, other_put, other_delete):
            other = File(other_put("tables/west/part.csv", b"name,amount\nyew,5\n"))
            assert ShardedS3Dataset.from_files([other]).filenames == [other.path]
            # One bucket is required, but the original has no deliberate check: the
            # common path degenerates and an SDK validation error escapes. Only
            # "this does not produce a dataset" is dependable, so the class is open.
            with pytest.raises(Exception):
                ShardedS3Dataset.from_files([first, other])


def assert_ordered_shard_loading(root, put, prefix, format, encode):
    # Creation order differs from lexical selection order.
    put(prefix + "/z-last." + format, encode([("ash", -2)]))
    put(prefix + "/a-first." + format, encode([("oak", 4), ("elm", 9)]))
    put(prefix + "/m-middle." + format, encode([("yew", 12)]))
    dataset = ShardedS3Dataset(root + "/" + prefix, format=format)
    shards = dataset.load_pandas_shards()
    assert [list(table.itertuples(index=False, name=None)) for table in shards] == [
        [("oak", 4), ("elm", 9)], [("yew", 12)], [("ash", -2)],
    ]
    assert list(dataset.load_pandas().itertuples(index=False, name=None)) == [
        ("oak", 4), ("elm", 9), ("yew", 12), ("ash", -2),
    ]
    limited = dataset.load_pandas_shards(max_shards=1)
    assert [list(table.itertuples(index=False, name=None)) for table in limited] == [
        [("oak", 4), ("elm", 9)],
    ]
    assert list(dataset.load_pandas(max_shards=1).itertuples(
        index=False, name=None)) == [("oak", 4), ("elm", 9)]
    for limit, expected in (
        (2, [[("oak", 4), ("elm", 9)], [("yew", 12)]]),
        (5, [[("oak", 4), ("elm", 9)], [("yew", 12)], [("ash", -2)]]),
    ):
        selected = dataset.load_pandas_shards(max_shards=limit)
        assert [list(table.itertuples(index=False, name=None))
                for table in selected] == expected
        assert list(dataset.load_pandas(max_shards=limit).itertuples(
            index=False, name=None)) == [row for shard in expected for row in shard]


def test_f14_t04():
    with dataset_objects() as (root, put, delete):
        for format in ("csv", "parquet", "orc"):
            assert_ordered_shard_loading(root, put, format, format,
                                         lambda rows: table_shard_bytes(format, rows))
        # The whole behaviour must hold on at least one standard JSON table layout.
        failures = []
        for number, layout in enumerate(JSON_TABLE_LAYOUTS):
            try:
                assert_ordered_shard_loading(root, put, "json-" + str(number), "json",
                                             lambda rows: json_shard_bytes(layout, rows))
                break
            except Exception as error:
                failures.append((layout, repr(error)))
        else:
            raise AssertionError(("No standard JSON table layout was read", failures))
        for format in ("avro", "ion", "grokLog", "xml"):
            put(format + "/part." + format, b"shard")
            dataset = ShardedS3Dataset(root + "/" + format, format=format)
            with pytest.raises(ValueError):
                dataset.load_pandas_shards()
            with pytest.raises(ValueError):
                dataset.load_pandas()


def test_f14_t05():
    # Construct the declared input with a real engine, then stop that engine.
    # This deliberately leaves no active execution context, whether or not
    # the runtime has the Glue library installed.
    with spark_tables() as session:
        table = session.createDataFrame([("oak", 4)], ["name", "amount"])
    with dataset_objects() as (root, put, delete):
        put("input/part.csv", table_shard_bytes("csv", [("oak", 4), ("elm", 9)]))
        source = ShardedS3Dataset(root + "/input", format="csv")
        target = ShardedS3Dataset(root + "/output", format="parquet")
        # The dataset itself works, so the refusals below are about the missing context.
        assert list(source.load_pandas().itertuples(index=False, name=None)) == [
            ("oak", 4), ("elm", 9)]
        with pytest.raises(ValueError):
            source.load_spark()
        # The input retains its declared distributed-table type; it cannot be
        # used until the missing execution prerequisite is available.
        with pytest.raises(ValueError):
            target.save_spark(table)
        # A refused save leaves nothing behind at the target location.
        assert ShardedS3Dataset(root + "/output", format="parquet").filenames == []
