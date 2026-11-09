# feature: F05
"""Public array and store observations for encoding acceptance."""
import numpy as np
import velnora
from _helpers import invoke
from velnora.core.buffer import default_buffer_prototype


def encoding_array(data, **options):
    data = np.asarray(data)
    args = dict(store={}, shape=data.shape, chunks=data.shape, dtype=data.dtype,
                zarr_format=3, compressors=None, fill_value=0)
    args.update(options)
    return invoke(velnora.create_array, call_kwargs=args).value


def payload_key(array):
    coordinates = ['0'] * len(array.chunks)
    return '/'.join(['c', *coordinates]) if array.metadata.zarr_format == 3 else '.'.join(coordinates)


def chunk_payload(array):
    value = invoke(array.store.get, payload_key(array)).value
    assert value is not None, 'Written chunk must exist'
    return value.to_bytes()


def replace_payload(array, value):
    buffer = default_buffer_prototype().buffer.from_bytes(value)
    invoke(array.store.set, payload_key(array), buffer)


def reopened_values(array):
    return invoke(lambda: velnora.open_array(array.store, mode='r')[:]).value


def check_encoded(data, filters, encoded, encoded_dtype, *, decoded=None, **options):
    array = encoding_array(data, filters=filters,
                           serializer=velnora.codecs.BytesCodec(endian='little'), **options)
    array[:] = data
    actual = np.frombuffer(chunk_payload(array), dtype=np.dtype(encoded_dtype).newbyteorder('<'))
    np.testing.assert_array_equal(actual, np.asarray(encoded).ravel())
    np.testing.assert_array_equal(reopened_values(array), data if decoded is None else decoded)
    return array


class RegisteredGzip(velnora.codecs.GzipCodec):
    """Real compression registered under a caller-defined encoding name."""

    encoding_name = 'acceptance.registered_gzip'

    @classmethod
    def from_dict(cls, data):
        return cls(**data['configuration'])

    def to_dict(self):
        return {'name': self.encoding_name, 'configuration': {'level': self.level}}


def check_missing_conversion_support():
    """Remove a declared optional provider from a real isolated import tree.

    Built-in implementations need no external dependency and have no missing-
    provider obligation. Nothing patches imports or fabricates provider results.
    """
    import importlib.metadata
    from pathlib import Path
    import json
    import zipfile
    import sys
    import tempfile
    from _helpers import effective_import_paths, make_env, run_command

    requirements = importlib.metadata.requires('velnora') or []
    if not any(r.lower().startswith('cast-value-rs') for r in requirements):
        return
    provider = importlib.metadata.distribution('cast-value-rs')
    excluded = {Path(f).parts[0] for f in provider.files if '..' not in Path(f).parts}
    with tempfile.TemporaryDirectory(prefix='f05-no-provider-') as directory:
        root = Path(directory)
        # Preserve root order and namespace-package portions instead of merging
        # distinct roots. Never put an unfiltered root on the isolated path.
        filtered = []
        for index, source in enumerate(effective_import_paths()):
            source = Path(source)
            if not source.exists():
                continue
            target = root / str(index)
            target.mkdir()
            if source.is_dir():
                for child in source.iterdir():
                    if child.name not in excluded:
                        (target / child.name).symlink_to(child, target_is_directory=child.is_dir())
            else:
                # Python also accepts zip archives as import roots.
                with zipfile.ZipFile(source) as archive:
                    for member in archive.infolist():
                        parts = Path(member.filename).parts
                        assert not Path(member.filename).is_absolute() and '..' not in parts
                        if parts and parts[0] not in excluded:
                            archive.extract(member, target)
            filtered.append(str(target))
        source = '''
import sys
import json
sys.path[:] = json.loads(sys.argv[1])
import importlib.util
assert importlib.util.find_spec('cast_value_rs') is None
import velnora
from importlib.metadata import distribution
assert distribution('velnora').metadata['Name'].lower() == 'velnora'
import numpy as np
try:
    a = velnora.create_array({}, shape=(2,), chunks=(2,), dtype='float64',
                          filters=[velnora.codecs.CastValue(data_type='int16')], compressors=None)
    a[:] = [1.5, -2.5]
    result = velnora.open_array(a.store, mode='r')[:]
except ImportError:
    pass
else:
    np.testing.assert_array_equal(result, [2, -2])
'''
        result = run_command([sys.executable, '-S', '-c', source, json.dumps(filtered)],
                             env=make_env({'PYTHONPATH': None}))
        assert result.returncode == 0, result.stdout + result.stderr
