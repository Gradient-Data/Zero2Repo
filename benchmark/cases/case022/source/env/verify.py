"""Verify pinned distributions and imports in the judge and fresh interpreters."""
import importlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys


def verify():
    prefix = Path('/opt/conda').resolve()
    if Path(sys.prefix).resolve() != prefix:
        raise RuntimeError(f'Unexpected runtime prefix: {sys.prefix}')
    packages = json.loads(Path(__file__).with_name('packages.json').read_text())
    for package in packages:
        if 'name' in package:
            distribution = importlib.metadata.distribution(package['name'])
        else:
            # Source archives are identified by pip's recorded installation URL.
            matches = []
            for candidate in importlib.metadata.distributions():
                direct = candidate.read_text('direct_url.json')
                if direct and json.loads(direct)['url'] == (
                    Path('/opt/wheelhouse') / package['filename']
                ).as_uri():
                    matches.append(candidate)
            if len(matches) != 1:
                raise RuntimeError(f'Expected one installed archive, found {len(matches)}')
            distribution = matches[0]
        if distribution.version != package['version']:
            raise RuntimeError(
                f"Version mismatch for {distribution.metadata['Name']}: "
                f"expected {package['version']}, got {distribution.version}"
            )
        location = Path(distribution.locate_file('')).resolve()
        if not location.is_relative_to(prefix):
            raise RuntimeError(f'Distribution outside judge runtime: {location}')
        print(f"Verified distribution {distribution.metadata['Name']}=={distribution.version}", flush=True)
    for module in (
        'fsspec', 'numpy', 'pyarrow', 'faiss', 'yaml', 'PIL', 'pandas', 'dill',
        'multiprocess', 'aiohttp', 'xxhash', 'pytest', 'torch', 'torchcodec',
        'tensorflow', 'jax', 'jaxlib', 'soundfile', 'scipy', 'h5py', 'lance',
        'pyiceberg', 'vortex', 'polars', 'sqlalchemy', 'trimesh', 'pdfplumber',
        'Bio', 'nibabel', 'ipyniivue', 'lz4', 'py7zr', 'rarfile', 'zstandard',
    ):
        imported = importlib.import_module(module)
        location = Path(imported.__file__).resolve()
        if not location.is_relative_to(prefix):
            raise RuntimeError(f'Import outside judge runtime: {module}: {location}')
        print(f'Verified import {module}: {location}', flush=True)
    print(f'Verified interpreter: {sys.executable}', flush=True)


if __name__ == '__main__':
    verify()
    if len(sys.argv) == 1:
        for executable in (sys.executable, 'python', 'python3'):
            subprocess.run([executable, __file__, '--child'], check=True)
