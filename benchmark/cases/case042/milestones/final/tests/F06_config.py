# feature: F06
"""Acceptance of configuration precedence, scope, reload and provider selection."""
from F06_helpers import run_config_script


def test_f06_t01():
    run_config_script('''
assert config.get('default_zarr_format') == 2
observe_configured_array(2)
config.set({'default_zarr_format': 3})
assert config.get('default_zarr_format') == 3
observe_configured_array(3)
with config.set({'default_zarr_format': 2}):
    assert config.get('default_zarr_format') == 2
    observe_configured_array(2)
    with config.set({'default_zarr_format': 3}):
        observe_configured_array(3)
    assert config.get('default_zarr_format') == 2
    observe_configured_array(2)
assert config.get('default_zarr_format') == 3
observe_configured_array(3)
class ScopeFailure(Exception):
    pass
with pytest.raises(ScopeFailure):
    with config.set({'default_zarr_format': 2}):
        observe_configured_array(2)
        raise ScopeFailure('Scope interrupted')
assert config.get('default_zarr_format') == 3
observe_configured_array(3)
config.reset()
assert config.get('default_zarr_format') == 2
observe_configured_array(2)
config.set({'default_zarr_format': 2})
os.environ['VELNORA_DEFAULT_ZARR_FORMAT'] = '3'
config.reset()
assert config.get('default_zarr_format') == 3
observe_configured_array(3)
''', environment={'VELNORA_DEFAULT_ZARR_FORMAT': '2'})


def test_f06_t02():
    run_config_script('''
assert config.get('default_zarr_format') == 3
assert config.get('array.order') == 'F'
observe_configured_array(3)
a = velnora.create_array({}, shape=(2, 3), chunks=(2, 3), dtype='int32', compressors=None)
assert a.order == 'F'
a[:] = [[1, 4, 9], [16, 25, 36]]
np.testing.assert_array_equal(velnora.open_array(a.store)[:], [[1, 4, 9], [16, 25, 36]])
del os.environ['VELNORA_DEFAULT_ZARR_FORMAT']
config.reset()
assert config.get('default_zarr_format') == 2
observe_configured_array(2)
document_path.write_text(yaml.safe_dump({'default_zarr_format': 3}), encoding='utf-8')
config.reset()
assert config.get('default_zarr_format') == 3
observe_configured_array(3)
document_path.write_text('{}', encoding='utf-8')
config.reset()
assert config.get('default_zarr_format') == 3
observe_configured_array(3)
os.environ['VELNORA_DEFAULT_ZARR_FORMAT'] = '2'
config.reset()
assert config.get('default_zarr_format') == 2
observe_configured_array(2)
''', document={'default_zarr_format': 2, 'array': {'order': 'F'}},
        environment={'VELNORA_DEFAULT_ZARR_FORMAT': '3'})


def test_f06_t03():
    run_config_script('''
assert config.get('default_zarr_format') == 3
observe_configured_array(3)
with config.set({'default_zarr_format': 2}):
    observe_configured_array(2)
observe_configured_array(3)
''')


def test_f06_t04():
    run_config_script('''
import gzip
from F06_helpers import ConfiguredGzip, ReverseGzip, SelectedArray, SelectedNDBuffer, SelectedBuffer
from velnora.registry import (register_codec, register_buffer, register_ndbuffer,
                           fully_qualified_name)
from velnora.core.config import BadConfigError
from velnora.core.buffer import default_buffer_prototype
from _helpers import invoke

name = ConfiguredGzip.encoding_name
register_codec(name, ConfiguredGzip)
register_codec(name, ReverseGzip)
register_buffer(SelectedBuffer)
register_ndbuffer(SelectedNDBuffer)
data = np.array([37, -901, 2048, 73, -2, 19], dtype='int32')
raw = data.astype('<i4').tobytes()
for provider, expected in ((ConfiguredGzip, raw), (ReverseGzip, raw[::-1])):
    with config.set({'codecs.' + name: fully_qualified_name(provider),
                     'buffer': fully_qualified_name(SelectedBuffer),
                     'ndbuffer': fully_qualified_name(SelectedNDBuffer)}):
        a = encoding_array(data, serializer=velnora.codecs.BytesCodec(endian='little'),
                           compressors=[{'name': name, 'configuration': {'level': 2}}])
        a[:] = data
        assert gzip.decompress(chunk_payload(a)) == expected
        value = reopened_values(a)
        assert isinstance(value, SelectedArray)
        np.testing.assert_array_equal(value, data)
        buffer = invoke(a.store.get, 'c/0',
                        call_kwargs={'prototype': default_buffer_prototype()}).value
        assert isinstance(buffer, SelectedBuffer)
        assert gzip.decompress(buffer.to_bytes()) == expected
        # Independently supplied bytes also travel through the configured decoder.
        from F05_helpers import replace_payload
        other = np.array([-17, 41, 999, -73, 4, 120], dtype='<i4')
        decoded_bytes = other.tobytes()
        encoded_bytes = decoded_bytes if provider is ConfiguredGzip else decoded_bytes[::-1]
        replace_payload(a, gzip.compress(encoded_bytes, compresslevel=2))
        result = reopened_values(a)
        assert isinstance(result, SelectedArray)
        np.testing.assert_array_equal(result, other)

for key in ('codecs.' + name, 'buffer', 'ndbuffer'):
    with config.set({key: 'acceptance.unregistered.Provider'}):
        with pytest.raises(BadConfigError):
            a = encoding_array(data, compressors=[{'name': name, 'configuration': {'level': 2}}])
            a[:] = data
            reopened_values(a)
''')
