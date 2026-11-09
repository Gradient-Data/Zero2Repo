# feature: F07
"""Public array observations reusable by later features."""
from F02_helpers import assert_dtype_meaning
from F03_helpers import listed, read_bytes


def array_properties(array):
    """Read the public definition without text rendering or private info objects."""
    return dict(shape=array.shape, ndim=array.ndim, dtype=array.dtype,
                chunks=array.chunks, shards=array.shards, fill_value=array.metadata.fill_value,
                zarr_format=array.metadata.zarr_format, filters=array.filters,
                serializer=array.serializer, compressors=array.compressors,
                dimension_names=(array.metadata.dimension_names
                                 if array.metadata.zarr_format == 3 else None))


def assert_array_definition(array, *, shape, dtype, chunks, fill_value, version):
    properties = array_properties(array)
    assert properties['shape'] == shape
    assert properties['ndim'] == len(shape)
    assert_dtype_meaning(properties['dtype'], dtype)
    assert properties['chunks'] == chunks
    assert properties['fill_value'] == fill_value
    assert properties['zarr_format'] == version


def array_storage_bytes(store):
    """Measure every actual object in a dedicated array store via public reads."""
    return {key: read_bytes(store, key) for key in listed(store.list)}


def array_data_keys(store, version):
    """Separate metadata from data using the published default key layouts."""
    keys = listed(store.list)
    metadata = {'zarr.json'} if version == 3 else {'.zarray', '.zattrs'}
    return keys - metadata
