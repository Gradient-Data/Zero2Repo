# feature: F14
"""Loopback S3 dataset objects, genuine table shards and a real local Spark session."""
from contextlib import contextmanager

from F03_services import object_store


@contextmanager
def dataset_objects():
    """Yield (location, put, delete) over a fresh bucket of the loopback S3 service.

    put(relative, content) stores an object through an independent S3 client and
    returns its s3:// URL; delete(relative) removes one object this test stored.
    The product reaches the same service through the standard AWS SDK settings.
    """
    with object_store("s3") as store:
        location = store.url("dataset")
        allocated = set()

        def put(relative, content):
            allocated.add(relative)
            store.write("dataset/" + relative, content)
            return location + "/" + relative

        def delete(relative):
            if relative not in allocated:
                raise ValueError("Cannot delete an object not allocated by this test")
            store.remove("dataset/" + relative)

        yield location, put, delete


JSON_TABLE_LAYOUTS = (
    {},  # one object keyed by column, then by row position
    {"orient": "records"},  # one array of row objects
    {"orient": "records", "lines": True},  # one row object per line
)


def json_shard_bytes(layout, rows):
    """One standard JSON table layout; the documents do not fix which one a shard uses."""
    import pandas as pd

    return pd.DataFrame(rows, columns=["name", "amount"]).to_json(**layout).encode("utf-8")


def table_shard_bytes(format, rows):
    """Create genuine table files with the independent table libraries."""
    from io import BytesIO
    import pandas as pd

    frame = pd.DataFrame(rows, columns=["name", "amount"])
    if format == "csv":
        return frame.to_csv(index=False).encode("utf-8")
    if format == "json":
        return frame.to_json().encode("utf-8")
    output = BytesIO()
    if format == "parquet":
        frame.to_parquet(output, index=False)
    elif format == "orc":
        frame.to_orc(output, index=False)
    else:
        raise ValueError("Unsupported acceptance input format")
    return output.getvalue()


@contextmanager
def spark_tables(config=None):
    """Execute through Spark itself; startup and collection errors propagate."""
    from pyspark.sql import SparkSession

    # The offline container hostname is not resolvable. Bind the real local
    # engine explicitly to loopback; no external service is being substituted.
    import os
    previous = os.environ.get("SPARK_LOCAL_IP")
    os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
    try:
        builder = (SparkSession.builder.master("local[2]")
                   .appName("velnora-dataset-acceptance")
                   .config("spark.ui.enabled", "false")
                   .config("spark.sql.shuffle.partitions", "2"))
        for name, value in (config or {}).items():
            builder = builder.config(name, value)
        session = builder.getOrCreate()
        try:
            yield session
        finally:
            session.stop()
    finally:
        if previous is None:
            del os.environ["SPARK_LOCAL_IP"]
        else:
            os.environ["SPARK_LOCAL_IP"] = previous
