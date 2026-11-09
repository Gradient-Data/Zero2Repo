# feature: F06
"""Local format fixtures and fully consumed public ingestion calls."""
import functools
import contextlib
from pathlib import Path

from _helpers import run_python


def source_product_test(function):
    """Run each observation in a fresh interpreter against the mounted source.

    The build container's installed wheel is not retained by the test container.
    Binding before imports also avoids another feature's collection imports
    choosing the image's preinstalled baseline for this feature.
    """
    @functools.wraps(function)
    def execute(tmp_path):
        source = """
import sys
from pathlib import Path
source = Path('/app/src')
if not (source / 'velnora/__init__.py').is_file():
    raise RuntimeError('Mounted product source is missing')
sys.path.insert(0, str(source))
sys.path.insert(0, sys.argv[1])
from F06_ingestion import TEST_FUNCTION
TEST_FUNCTION.__wrapped__(Path(sys.argv[2]))
""".replace('TEST_FUNCTION', function.__name__)
        result = run_python(source, timeout=120,
                            args=(str(Path(__file__).parent), str(tmp_path)))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


import pyarrow as pa
import pyarrow.parquet as pq
from velnora import load_dataset


def ingest(format_name, path, **kwargs):
    return load_dataset(format_name, data_files=str(path), split='train', **kwargs)


def ingest_rows(format_name, path, **kwargs):
    return list(ingest(format_name, path, **kwargs))


def write_binary_table(root, format_name, table):
    path = root / ('records.' + format_name)
    if format_name == 'parquet':
        pq.write_table(table, path)
    elif format_name == 'arrow':
        with pa.OSFile(str(path), 'wb') as sink:
            with pa.ipc.new_stream(sink, table.schema) as writer:
                writer.write_table(table)
    elif format_name == 'lance':
        import lance
        lance.write_dataset(table, path)
    elif format_name == 'vortex':
        import vortex
        vortex.io.write(vortex.array(table), str(path))
    else:
        raise ValueError('Unsupported fixture format')
    return path


@contextlib.contextmanager
def distributed_runtime():
    """Expose genuine, hash-verified offline Spark and Java distributions."""
    import hashlib
    import json
    import os
    import subprocess
    import sys
    import tarfile
    import tempfile
    import zipfile
    assets = Path(__file__).parent / 'resources' / 'F06'
    manifest = json.loads((assets / 'F06_runtime.json').read_text())
    with tempfile.TemporaryDirectory(prefix='F06-runtime-') as temporary:
        root = Path(temporary)
        for item in manifest['assets']:
            asset = assets / item['file']
            with asset.open('rb') as source:
                assert hashlib.file_digest(source, 'sha256').hexdigest() == item['sha256']
            if item['format'] == 'zip':
                with zipfile.ZipFile(asset) as archive:
                    for member in archive.infolist():
                        archive.extract(member, root / 'site')
                        mode = member.external_attr >> 16
                        if mode:
                            os.chmod(root / 'site' / member.filename, mode)
            elif item['format'] == 'deb':
                unpacked = root / 'deb'
                subprocess.run(('dpkg-deb', '-x', str(asset), str(unpacked)), check=True)
                # Absolute links (configuration under /etc) resolve inside the
                # unpacked package, never into the host system.
                for link in [entry for entry in unpacked.rglob('*') if entry.is_symlink()]:
                    target = os.readlink(link)
                    if target.startswith('/'):
                        link.unlink()
                        link.symlink_to(os.path.relpath(unpacked / target.lstrip('/'), link.parent))
            else:
                assert item['format'] == 'tar.gz'
                with tarfile.open(asset) as archive:
                    archive.extractall(root, filter='data')
        source = root / 'pyspark-4.0.1'
        paths = [str(root / 'site'), str(source)]
        previous_path = list(sys.path)
        keys = ['JAVA_HOME', 'SPARK_HOME', 'SPARK_LOCAL_IP', 'PYSPARK_PYTHON',
                'PYSPARK_DRIVER_PYTHON', 'PYTHONPATH']
        previous_environment = {name: os.environ.get(name) for name in keys}
        sys.path[:0] = paths
        os.environ.update(JAVA_HOME=str(root / 'deb' / 'usr' / 'lib' / 'jvm' / 'java-21-openjdk-amd64'),
                          SPARK_HOME=str(source / 'deps'), SPARK_LOCAL_IP='127.0.0.1',
                          PYSPARK_PYTHON=sys.executable, PYSPARK_DRIVER_PYTHON=sys.executable,
                          PYTHONPATH=os.pathsep.join(paths + [os.environ.get('PYTHONPATH', '')]))
        try:
            yield
        finally:
            sys.path[:] = previous_path
            for name, value in previous_environment.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
