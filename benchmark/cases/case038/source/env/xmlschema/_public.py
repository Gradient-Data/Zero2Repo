"""Bind to the public package declared by the current product's build backend.

Source imports need no installed distribution. Installed imports must be owned
by the current project's metadata on the actual interpreter search path.
Nothing is persisted across builds or package renaming.
"""
import importlib
import importlib.metadata
import importlib.util
from pathlib import Path
import re

from setuptools.config.pyprojecttoml import read_configuration


def normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def resolve_public_api():
    manifest = Path('pyproject.toml').resolve(strict=True)
    configuration = read_configuration(str(manifest), expand=True)
    project = configuration['project']['name']
    packaging = configuration['tool']['setuptools']
    packages = sorted({name.split('.')[0] for name in packaging['packages']})
    if len(packages) != 1 or not packages[0].isidentifier():
        raise ValueError(
            f'Expected one declared public caller package for {project!r}; '
            f'found {packages!r}')
    name = packages[0]
    directories = packaging['package-dir']
    source = (manifest.parent / directories.get(name, directories.get('', '')))
    if name not in directories:
        source /= name
    source = (source / '__init__.py').resolve(strict=True)
    spec = importlib.util.find_spec(name)
    if spec is None or spec.origin is None:
        raise ModuleNotFoundError(f'The declared public caller {name!r} is not importable')
    origin = Path(spec.origin).resolve(strict=True)
    evidence = {'project': project, 'package': name, 'origin': str(origin),
                'declared_source': str(source)}
    if origin == source:
        evidence['identity'] = 'declared source package'
    else:
        owners = []
        for distribution in importlib.metadata.distributions():
            if normalized(distribution.metadata['Name']) != normalized(project):
                continue
            files = distribution.files
            if files is None:
                raise ValueError(f'Caller distribution {project!r} has no file ownership metadata')
            if any(Path(distribution.locate_file(file)).resolve() == origin for file in files):
                owners.append(distribution)
        if len(owners) != 1:
            raise ValueError(
                f'Expected one distribution owning imported caller {name!r} at '
                f'{str(origin)!r} for {project!r}; found {len(owners)}')
        evidence['identity'] = 'distribution file ownership'
        evidence['distribution_root'] = str(owners[0].locate_file(''))
    module = importlib.import_module(name)
    if Path(module.__file__).resolve(strict=True) != origin:
        raise ValueError(f'Public caller {name!r} changed origin during import')
    return module, evidence


api, binding = resolve_public_api()
