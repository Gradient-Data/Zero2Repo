# feature: F06
"""Isolated configuration exercises and real registered providers."""
import os
from pathlib import Path

from _helpers import make_env, run_python, temporary_directory
from F05_helpers import RegisteredGzip
import gzip
import numpy as np
from velnora.buffer import cpu


def run_config_script(source, *, document=None, environment=None):
    """Execute public configuration calls with a fresh external YAML document."""
    import yaml

    with temporary_directory() as directory:
        path = directory / 'velnora.yaml'
        path.write_text(yaml.safe_dump({} if document is None else document), encoding='utf-8')
        env = make_env(base={k: v for k, v in os.environ.items()
                             if not k.startswith('VELNORA_')})
        env.update({'VELNORA_CONFIG': str(path), 'VELNORA_ROOT_CONFIG': str(directory / 'root')})
        env.update({} if environment is None else environment)
        prelude = '''
import os
from pathlib import Path
import numpy as np
import pytest
import yaml
import velnora
from F05_helpers import chunk_payload, encoding_array, reopened_values
from F06_helpers import observe_configured_array
config = velnora.config
document_path = Path(os.environ['VELNORA_CONFIG'])
'''
        result = run_python(prelude + source, env=env, cwd=Path(__file__).parent, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr


def observe_configured_array(expected_format):
    """Check newly created and reopened data without an explicit format argument."""
    import velnora

    data = np.array([[13, -29, 48], [107, 6, -52]], dtype='int32')
    array = velnora.create(store={}, shape=data.shape, chunks=data.shape, dtype=data.dtype)
    assert array.metadata.zarr_format == expected_format
    array[:] = data
    reopened = velnora.open_array(array.store, mode='r')
    assert reopened.metadata.zarr_format == expected_format
    np.testing.assert_array_equal(reopened[:], data)


class ConfiguredGzip(RegisteredGzip):
    """Reuse the earlier real codec with a flat configuration key."""

    encoding_name = 'acceptance_gzip'


class ReverseGzip(ConfiguredGzip):
    """An alternate caller-defined encoding: reverse bytes before compression."""

    def _encode_sync(self, chunk_bytes, chunk_spec):
        return chunk_spec.prototype.buffer.from_bytes(
            gzip.compress(chunk_bytes.to_bytes()[::-1], compresslevel=self.level))

    def _decode_sync(self, chunk_bytes, chunk_spec):
        return chunk_spec.prototype.buffer.from_bytes(
            gzip.decompress(chunk_bytes.to_bytes())[::-1])


class SelectedArray(np.ndarray):
    """Caller-owned array type exposed by the selected ND-buffer provider."""


class SelectedNDBuffer(cpu.NDBuffer):
    @classmethod
    def create(cls, *, shape, dtype, order='C', fill_value=None):
        value = np.empty(shape, dtype=dtype, order=order).view(SelectedArray)
        if fill_value is not None:
            value.fill(fill_value)
        return cls(value)

    @classmethod
    def empty(cls, shape, dtype, order='C'):
        return cls.create(shape=shape, dtype=dtype, order=order)


class SelectedBuffer(cpu.Buffer):
    """A real CPU byte buffer with a caller-owned observable type."""
