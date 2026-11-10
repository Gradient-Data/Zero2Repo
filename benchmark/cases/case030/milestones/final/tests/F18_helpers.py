# feature: F18
"""Real cleanup inputs and exact filesystem observations."""
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import run_command, write_text
from F01_helpers import translate_and_observe
from F03_helpers import require_success
from F04_helpers import (delivery_source, call_delivered, run_delivered_program,
                         delivered_extension, target_source)


def cleanup_seed(root, session, *, interactive=False):
    """Build and exercise native artifacts before making independent arms."""
    root.mkdir()
    source = delivery_source(root)
    require_success(session.command('compile', source, '--language', 'c', cwd=root))
    call_delivered(root, session)
    run_delivered_program(root, session)
    build = target_source(root, 'c').parent
    assert build.is_dir()
    # A saved translation is an input to cleanup, not a serialization oracle.
    saved = root / 'saved_translation.zelvori'
    shutil.copyfile(target_source(root, 'c'), saved)
    artifact_dirs = [build.name]
    if interactive:
        work = root.parent / 'interactive_build'
        def exercise(module):
            assert module.calculate(6) == 41
        translate_and_observe('def calculate(x: int):\n    return x*x + 5\n',
                              'c', work, exercise)
        dirname = '__ezelvori__' + os.environ.get('PYTEST_XDIST_WORKER', '')
        assert (work / dirname).is_dir()
        shutil.copytree(work / dirname, root / dirname)
        artifact_dirs.append(dirname)
    extension = delivered_extension(root)
    # Extension libraries need not be executable. Distinguish the two options.
    extension.chmod(0o600)
    executable_library = root / ('executable_copy' + extension.name[len('submitted'):])
    shutil.copyfile(extension, executable_library)
    executable_library.chmod(0o700)
    external = write_text(root, 'external_tool', '#!/bin/sh\nprintf "external-tool-ok\\n"\n')
    external.chmod(0o700)
    result = run_command([external], cwd=root)
    require_success(result)
    assert result.stdout == 'external-tool-ok\n'
    # Same content without execute permission must survive program cleanup.
    nonprogram = root / 'tool_text'
    shutil.copyfile(external, nonprogram)
    nonprogram.chmod(0o600)
    return artifact_dirs, [saved.name], [extension.name, executable_library.name], [
        'submitted', external.name, executable_library.name]


def cleanup_layout(seed, root):
    """Repeat the same proven artifacts at each selected traversal depth."""
    shutil.copytree(seed, root)
    shutil.copytree(seed, root / 'child')
    shutil.copytree(seed, root / 'child' / 'grandchild')


def cleanup_snapshot(root):
    """Read every file's content and permissions; observation errors propagate."""
    return {p.relative_to(root).as_posix():
            ('directory', p.stat().st_mode & 0o777) if p.is_dir() else
            ('file', p.stat().st_mode & 0o777, p.read_bytes())
            for p in root.rglob('*')}


def require_cleanup_state(root, before, removed):
    """Demand the exact remaining tree, including unchanged retained content."""
    def selected(name):
        return any(name == entry or name.startswith(entry + '/') for entry in removed)
    assert all(entry in before for entry in removed), removed
    expected = {name: value for name, value in before.items() if not selected(name)}
    assert cleanup_snapshot(root) == expected
