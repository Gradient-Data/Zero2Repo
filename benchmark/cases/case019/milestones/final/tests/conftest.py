# feature: F00
"""Bind acceptance execution to the mounted submission before collection."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

# The public environment recipe prepares dependencies here. Executable symlink
# resolution is not an environment identity: a venv can share its base binary.
_ENVIRONMENT = Path('/opt/venv')
_PROJECT = Path('/app')


def _outside_project(entry):
    # A launcher may expose an earlier build below the mounted project. Keeping
    # it alongside this installation duplicates distribution entry points.
    return not Path(entry).resolve().is_relative_to(_PROJECT)


def pytest_configure(config):
    """Align the interpreter and install the submission before test imports."""
    global _INSTALLATION
    python = _ENVIRONMENT / 'bin' / 'python'
    os.environ.pop('PYTHONHOME', None)
    os.environ['VIRTUAL_ENV'] = str(_ENVIRONMENT)
    os.environ['PATH'] = os.pathsep.join(
        (str(_ENVIRONMENT / 'bin'), os.environ.get('PATH', '')))
    if Path(sys.prefix) != _ENVIRONMENT:
        # Restart the original entry, including -I, the judge launcher/audit
        # plugin, selections and all pytest arguments. exec preserves its status.
        if os.environ.get('_SUITE_ENV_REEXEC'):
            raise RuntimeError('Prepared execution environment prerequisite failed: '
                               f'{python} started with prefix {sys.prefix!r}')
        os.environ['_SUITE_ENV_REEXEC'] = '1'
        # During conftest import pytest redirects the OS descriptors to temporary
        # capture files. Restore them before exec so the restarted judge retains
        # its real stdout/stderr, including the collection audit and diagnostics.
        config.pluginmanager.get_plugin('capturemanager').suspend_global_capture(in_=True)
        try:
            os.execv(str(python), [str(python), *sys.orig_argv[1:]])
        except OSError as error:
            raise RuntimeError('Prepared execution environment prerequisite failed: '
                               f'cannot execute {python}') from error

    if not (_PROJECT / 'src' / 'talvo').is_dir():
        raise RuntimeError('The submitted product source is missing at /app/src/talvo')

    # Keep the installation alive until pytest and its child processes exit.
    # A fresh target cannot reuse a reference installation or a prior build.
    _INSTALLATION = tempfile.TemporaryDirectory(prefix='suite-product-')
    target = Path(_INSTALLATION.name) / 'installed'
    command = (sys.executable, '-m', 'pip', '--isolated', 'install',
               '--no-index', '--no-deps', '--no-build-isolation', '--no-cache-dir',
               '--target', str(target), str(_PROJECT))
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(
            'Offline product installation prerequisite failed (exit {}): {!r}\n'
            'stdout:\n{}\nstderr:\n{}'.format(
                result.returncode, command,
                result.stdout.decode('utf-8', errors='backslashreplace'),
                result.stderr.decode('utf-8', errors='backslashreplace')))

    # Use the generated package, resources and distribution registrations in
    # collection and fresh Python/CLI/Sphinx processes.
    sys.path[:] = [str(target), *filter(_outside_project, sys.path)]
    os.environ['PATH'] = os.pathsep.join(
        (str(target / 'bin'), os.environ['PATH']))
    os.environ['PYTHONPATH'] = os.pathsep.join(
        (str(target), *(entry for entry in
                       os.environ.get('PYTHONPATH', '').split(os.pathsep)
                       if entry and _outside_project(entry))))
