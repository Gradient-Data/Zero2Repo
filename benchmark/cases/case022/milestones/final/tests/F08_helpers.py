# feature: F08
"""Media collection fixtures and observations through public loading entries."""
import csv
import functools
import io
import json
from pathlib import Path
import tarfile

from PIL import Image as PILImage
import pyarrow as pa
import pyarrow.parquet as pq
from velnora import load_dataset

from _helpers import run_python


def collection_source_test(function):
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
from F08_collections import TEST_FUNCTION
TEST_FUNCTION.__wrapped__(Path(sys.argv[2]))
""".replace('TEST_FUNCTION', function.__name__)
        result = run_python(source, timeout=180,
                            args=(str(Path(__file__).parent), str(tmp_path)))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def collection_image(root, relative, color):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.new('RGB', (3, 2), color).save(path)
    return path


def collection_metadata(root, extension, rows):
    root.mkdir(parents=True, exist_ok=True)
    path = root / ('metadata.' + extension)
    if extension == 'jsonl':
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    elif extension == 'csv':
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    elif extension == 'parquet':
        pq.write_table(pa.Table.from_pylist(rows), path)
    else:
        raise ValueError('Unsupported metadata format')
    return path


def load_collection(root, reader='imagefolder', **kwargs):
    return load_dataset(reader, data_dir=str(root), split='train', **kwargs)


def collection_bytes(value):
    if value['bytes'] is not None:
        return value['bytes']
    return Path(value['path']).read_bytes()


def collection_tar(path, entries):
    with tarfile.open(path, 'w') as archive:
        for name, content in entries:
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    return path
