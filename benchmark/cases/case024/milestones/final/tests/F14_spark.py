# feature: F14
"""Read actual transformed rows and SQL results from real Spark execution."""
from velnora.glue import sql_query, udf

from F14_helpers import spark_tables


def test_f14_t06():
    from pyspark.sql.types import ArrayType, IntegerType

    def numbers(left, right):
        return [int(left) + 3, int(right) * 2]

    def greeting(text):
        return text + "!"

    # Exercise the same authored functions before any Spark session exists.
    ordinary = udf(return_type=ArrayType(IntegerType()))(numbers)
    ordinary_text = udf(greeting)
    assert ordinary("-4", "7") == [-1, 14]
    assert ordinary("0", "-2") == [3, -4]
    assert ordinary_text("pear") == "pear!"

    with spark_tables() as session:
        distributed = udf(return_type=ArrayType(IntegerType()))(numbers)
        distributed_text = udf(greeting)
        source = session.createDataFrame(
            [("pear", "-4", "7"), ("plum", "0", "-2"), ("fig", "8", "0")],
            ["name", "left", "right"],
        ).repartition(2)
        result = source.select(
            "name", distributed(source.left, source.right).alias("numbers"),
            distributed_text(source.name).alias("greeting"),
        )
        assert result.schema["numbers"].dataType == ArrayType(IntegerType())
        assert sorted((row["name"], row["numbers"], row["greeting"])
                      for row in result.collect()) == [
            ("fig", [11, 0], "fig!"),
            ("pear", [-1, 14], "pear!"),
            ("plum", [3, -4], "plum!"),
        ]


def test_f14_t07():
    with spark_tables() as session:
        source = session.createDataFrame(
            [("oak", 4), ("elm", 9), ("oak", 7), ("ash", -2)],
            ["kind", "amount"],
        ).repartition(2)
        # Projection, filtering and aggregation must all affect the delivered rows.
        result = sql_query(
            source,
            "SELECT kind, SUM(amount) AS total FROM woodland "
            "WHERE amount > 0 GROUP BY kind",
            dataset_alias="woodland",
        )
        assert sorted((row["kind"], row["total"]) for row in result.collect()) == [
            ("elm", 9), ("oak", 11),
        ]
        # A second alias/query rejects implementations that return a canned result
        # or use a fixed view name rather than the caller's alias.
        selected = sql_query(
            source, "SELECT amount * 3 AS scaled FROM grove WHERE kind = 'ash'",
            dataset_alias="grove",
        )
        assert [row["scaled"] for row in selected.collect()] == [-6]


def test_f14_t08(tmp_path):
    """Real Glue reads S3 rows and persists derived rows for independent readers."""
    import os
    from pathlib import Path
    import velnora
    from _helpers import run_python

    # A fresh interpreter gives the JVM its region before startup and prevents
    # sessions from other tests from supplying a cached runtime configuration.
    source = '''
import json
import os
from velnora import ShardedS3Dataset
from F03_services import object_store, service_environment
from F14_helpers import spark_tables

environment = service_environment()
os.environ["AWS_REGION"] = environment["AWS_DEFAULT_REGION"]
os.environ["AWS_DEFAULT_REGION"] = environment["AWS_DEFAULT_REGION"]
config = {"spark.hadoop." + name: value for name, value in {
    "fs.s3.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
    "fs.s3a.endpoint": environment["AWS_ENDPOINT_URL_S3"],
    "fs.s3a.path.style.access": "true",
    "fs.s3a.connection.ssl.enabled": "false",
    "fs.s3a.access.key": environment["AWS_ACCESS_KEY_ID"],
    "fs.s3a.secret.key": environment["AWS_SECRET_ACCESS_KEY"],
    "fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
}.items()}

def rows(table):
    return sorted((row["name"], row["amount"]) for row in table.collect())

with spark_tables(config) as session:
    with object_store("s3") as store:
        inputs = [[("willow", 6), ("beech", -3)], [("cedar", 11), ("willow", 2)]]
        for index, shard in enumerate(inputs):
            payload = "".join(json.dumps({"name": name, "amount": amount}) + "\\n"
                              for name, amount in shard)
            store.write("source/part-{}.json".format(index), payload.encode("utf-8"))
        source = ShardedS3Dataset(store.url("source"), format="json")
        loaded = source.load_spark()
        assert rows(loaded) == sorted(row for shard in inputs for row in shard)
        transformed = loaded.selectExpr("name", "amount * 5 - 4 AS amount")
        expected = sorted((name, amount * 5 - 4) for shard in inputs for name, amount in shard)
        target = ShardedS3Dataset(store.url("derived"), format="json")
        assert store.keys("derived/") == []
        target.save_spark(transformed)
        # No shard count, basename, extension, or row order is prescribed.
        assert store.keys("derived/")
        # This reader bypasses the product to prove that real objects contain
        # the computed rows, rather than accepting an in-memory saved result.
        assert rows(session.read.json(target.path)) == expected
        reopened = ShardedS3Dataset(target.path, format="json")
        assert rows(reopened.load_spark()) == expected
'''
    python_path = os.pathsep.join([str(Path(__file__).resolve().parent),
                                  str(Path(velnora.__file__).resolve().parent.parent)])
    result = run_python(source, cwd=tmp_path, timeout=180,
                        env={"PYTHONPATH": python_path, "AWS_ACCESS_KEY_ID": None,
                             "AWS_SECRET_ACCESS_KEY": None, "AWS_SESSION_TOKEN": None})
    assert result.returncode == 0, result.stdout + result.stderr
