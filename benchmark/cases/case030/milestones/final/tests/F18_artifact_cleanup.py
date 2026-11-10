# feature: F18
"""Scoped artifact cleanup through the public command line."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from F03_helpers import ConfigurationSession, require_success
from F18_helpers import (cleanup_seed, cleanup_layout, cleanup_snapshot,
                         require_cleanup_state)


def test_default_selected_and_nonrecursive_cleanup(tmp_path):
    session = ConfigurationSession(tmp_path / 'commands')
    directories, saved, _, _ = cleanup_seed(tmp_path / 'seed', session, interactive=True)
    # Each arm starts with identical live artifacts; only selection/traversal changes.
    for mode in ('default', 'explicit', 'nonrecursive'):
        sandbox = tmp_path / mode
        sandbox.mkdir()
        for name in ('first', 'second', 'outside'):
            cleanup_layout(tmp_path / 'seed', sandbox / name)
        before = cleanup_snapshot(sandbox)
        if mode == 'default':
            selected = ('first',)
            result = session.command('clean', cwd=sandbox / 'first')
        else:
            selected = ('first', 'second')
            options = ['--not-recursive'] if mode == 'nonrecursive' else []
            result = session.command('clean', *options,
                                     sandbox / 'first', sandbox / 'second', cwd=sandbox)
        require_success(result)
        depths = ('',) if mode == 'nonrecursive' else ('', 'child/', 'child/grandchild/')
        removed = [f'{name}/{depth}{artifact}' for name in selected for depth in depths
                   for artifact in directories + saved]
        require_cleanup_state(sandbox, before, removed)


def test_optional_library_and_program_cleanup(tmp_path):
    session = ConfigurationSession(tmp_path / 'commands')
    directories, saved, libraries, programs = cleanup_seed(tmp_path / 'seed', session)
    # The shallow library arm isolates optional cleanup from traversal.
    modes = [([], False, False, True),
             (['--remove-libs'], True, False, True),
             (['--remove-programs'], False, True, True),
             (['--remove-libs', '--remove-programs'], True, True, True),
             (['--remove-libs', '--not-recursive'], True, False, False)]
    for index, (options, libs, progs, recursive) in enumerate(modes):
        sandbox = tmp_path / f'arm_{index}'
        sandbox.mkdir()
        cleanup_layout(tmp_path / 'seed', sandbox / 'selected')
        cleanup_layout(tmp_path / 'seed', sandbox / 'outside')
        before = cleanup_snapshot(sandbox)
        require_success(session.command('clean', *options, sandbox / 'selected', cwd=sandbox))
        categories = set(directories + saved + (libraries if libs else []) +
                         (programs if progs else []))
        depths = ('', 'child/', 'child/grandchild/') if recursive else ('',)
        removed = [f'selected/{depth}{artifact}' for depth in depths for artifact in categories]
        require_cleanup_state(sandbox, before, removed)


def test_nonrecursive_program_cleanup_without_descendants(tmp_path):
    import shutil

    session = ConfigurationSession(tmp_path / 'commands')
    directories, saved, _, programs = cleanup_seed(tmp_path / 'seed', session)
    sandbox = tmp_path / 'scope'
    sandbox.mkdir()
    # Copy the proven seed once, without creating ordinary child directories.
    for name in ('selected', 'outside'):
        shutil.copytree(tmp_path / 'seed', sandbox / name)
    before = cleanup_snapshot(sandbox)
    require_success(session.command('clean', '--not-recursive', '--remove-programs',
                                    sandbox / 'selected', cwd=sandbox))
    removed = [f'selected/{artifact}' for artifact in set(directories + saved + programs)]
    require_cleanup_state(sandbox, before, removed)
