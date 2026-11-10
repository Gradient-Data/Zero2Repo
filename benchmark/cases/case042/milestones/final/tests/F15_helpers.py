# feature: F15
"""Real migration fixtures and observations through public entries."""
import velnora
from pathlib import Path
import numpy as np
from _helpers import run_python, temporary_directory
from F07_helpers import array_storage_bytes, assert_array_definition
from F14_helpers import assert_saved_values


METADATA_NAMES = {'.zarray', '.zgroup', '.zattrs', '.zmetadata', 'zarr.json'}


def migration_cli(*args):
    # Use the installed command declaration, independent of pip's install layout.
    with temporary_directory() as directory:
        ready = directory / 'entry-loaded'
        result = run_python("""
import sys
from pathlib import Path
from importlib.metadata import distribution
ready = Path(sys.argv.pop(1))
command, = (entry for entry in distribution('velnora').entry_points
            if entry.group == 'console_scripts' and entry.name == 'velnora')
entry = command.load()
ready.write_text('loaded', encoding='utf-8')
sys.argv[0] = 'velnora'
try:
    entry()
except ImportError:
    ready.unlink()
    raise
""", args=[str(ready), *map(str, args)])
        # Import/discovery failures must not masquerade as a CLI refusal.
        # Other failures retain the public exit-status/stderr contract.
        assert ready.exists(), result.stdout + result.stderr
        return result


def require_cli(result, success=True):
    assert result.returncode == (0 if success else 1), result.stdout + result.stderr
    if not success:
        assert result.stderr.strip(), 'A failed command must report its error on stderr'


def metadata_keys(snapshot, version):
    names = {'zarr.json'} if version == 3 else METADATA_NAMES - {'zarr.json'}
    return {key for key in snapshot if key.rsplit('/', 1)[-1] in names}


def payloads(snapshot):
    return {key: value for key, value in snapshot.items()
            if key.rsplit('/', 1)[-1] not in METADATA_NAMES}


def migration_hierarchy(location):
    root = velnora.create_group(location, zarr_format=2, attributes={'project': ['migration', 9]})
    branch = root.create_group('branch', attributes={'stage': 2})
    branch.create_group('empty', attributes={'note': 'kept'})
    expected = {}
    for parent, name, dtype, order, separator in [
        (root, 'direct', '<i2', 'C', '.'),
        (branch, 'deep', '>i4', 'F', '/'),
    ]:
        array = parent.create_array(name, shape=(5, 7), chunks=(3, 4), dtype=dtype,
                                    fill_value=-13, compressors=None, order=order,
                                    chunk_key_encoding={'name': 'v2', 'separator': separator},
                                    attributes={'units': 'count', 'labels': [name, 4]})
        values = np.full((5, 7), -13, dtype=dtype)
        values[:3, :4] = np.arange(12).reshape(3, 4) * 7 - 9
        array[:3, :4] = values[:3, :4]
        expected[array.path] = (values, dict(array.attrs))
    return root.store, expected


def check_migrated_hierarchy(store, expected, *, with_values=True):
    group = velnora.open_group(store, mode='r', zarr_format=3, use_consolidated=False)
    assert dict(group.attrs) == {'project': ['migration', 9]}
    assert dict(group['branch'].attrs) == {'stage': 2}
    assert dict(group['branch/empty'].attrs) == {'note': 'kept'}
    assert set(dict(group.members())) == {'direct', 'branch'}
    assert set(dict(group['branch'].members())) == {'deep', 'empty'}
    for path, (values, attributes) in expected.items():
        array = group[path]
        assert_array_definition(array, shape=(5, 7), dtype=values.dtype,
                                chunks=(3, 4), fill_value=-13, version=3)
        assert dict(array.attrs) == attributes
        if with_values:
            assert_saved_values(array, values)
    assert metadata_keys(array_storage_bytes(store), 3) == {
        'zarr.json', 'direct/zarr.json', 'branch/zarr.json',
        'branch/deep/zarr.json', 'branch/empty/zarr.json'}


def reported_local_paths(lines):
    """Read the local-target carrier without interpreting report sentences."""
    from pathlib import Path

    paths = set()
    for line in lines:
        _, marker, target = line.partition('file://')
        if marker:
            assert 'file://' not in target, 'Multiple local targets on one report line'
            assert Path(target).is_absolute(), 'Reported target is not absolute'
            paths.add(Path(target))
    return paths
