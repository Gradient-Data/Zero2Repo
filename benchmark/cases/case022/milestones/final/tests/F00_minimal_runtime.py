# feature: F00
"""Execute with genuine base dependencies and no optional package installation."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from _helpers import run_command


def minimal_runtime_python(source, *, args=(), timeout=90):
    """Construct a separate dependency inventory without altering any imports.

    The image's installed base distribution supplies the runtime prerequisites.
    Optional extras are not selected. Files are unmodified links to genuine
    installed distributions; no availability flags or import hooks are patched.
    A product with a bundled decoder can still return the correct decoded data.
    """
    pending = ['velnora']
    seen = set()
    packages = {}
    while pending:
        name = canonicalize_name(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        distribution = importlib.metadata.distribution(name)
        for declaration in distribution.requires or ():
            requirement = Requirement(declaration)
            if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                pending.append(requirement.name)
        if name == 'velnora':
            continue
        for relative in distribution.files or ():
            first = relative.parts[0]
            if first == '..':
                continue
            location = Path(distribution.locate_file(first)).resolve()
            if first in packages:
                assert packages[first] == location, ('Dependency namespace collision', first)
            packages[first] = location
    with tempfile.TemporaryDirectory(prefix='F00-base-runtime-') as temporary:
        # A standard site-packages name also preserves third-party serializers'
        # classification of installed dependencies as importable references.
        site = Path(temporary) / 'site-packages'
        site.mkdir()
        for name, location in packages.items():
            (site / name).symlink_to(location, target_is_directory=location.is_dir())
        bootstrap = '''
import sys
sys.path[:0] = ['/app/src', sys.argv.pop(1)]
'''
        result = run_command([sys.executable, '-I', '-S', '-c', bootstrap + source,
                              str(site), *map(str, args)], timeout=timeout,
                             env=dict(os.environ, PYTHONNOUSERSITE='1'))
        assert result.returncode == 0, result.stdout + result.stderr
        print(json.dumps({'base_runtime_distributions': sorted(seen),
                          'observation': result.stdout}), flush=True)
        return result
