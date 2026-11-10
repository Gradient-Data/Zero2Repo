# feature: F08
"""Caller-owned selection fixtures and bounded concurrent operations."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json

import numpy as np
import velnora

from F03_helpers import put_bytes, read_bytes


def selection_array():
    """Return a real multi-chunk array and its caller-owned dense input."""
    import velnora

    data = (np.arange(35, dtype='int32').reshape(5, 7) * 3) - 41
    array = velnora.create_array({}, data=data, chunks=(2, 3), compressors=None)
    return array, data.copy()


def legacy_selection_store(version, *, inner=None):
    """Store real array metadata with a legacy zero outer chunk extent."""
    array = velnora.create_array({}, shape=(6,), chunks=(inner or 1,),
                              shards=(inner,) if inner else None,
                              dtype='int16', fill_value=0, zarr_format=version)
    key = '.zarray' if version == 2 else 'zarr.json'
    document = json.loads(read_bytes(array.store, key))
    if version == 2:
        document['chunks'] = [0]
    else:
        document['chunk_grid']['configuration']['chunk_shape'] = [0]
    put_bytes(array.store, key, json.dumps(document).encode())
    return array.store, key


def concurrent_calls(calls):
    """Start independent public calls together and propagate every failure."""
    gate = Barrier(len(calls))

    def run(call):
        gate.wait(timeout=15)
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(run, call) for call in calls]
        return [future.result(timeout=30) for future in futures]
