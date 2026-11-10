# feature: F09
"""Run Windows activation in a real Windows Python and command shell under Wine."""
from F00_documents import legacy_document
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PureWindowsPath
import shutil
import zipfile

from _helpers import make_environment, parse_json, run_cli
from F01_helpers import succeeded


def windows_path(path):
    return 'Z:' + str(path.resolve()).replace('/', '\\')


@contextmanager
def windows_runtime(root, env, product_wheel):
    root.mkdir()
    assets = Path(__file__).with_name('F09_windows_assets')
    python = root / 'python'
    python.mkdir()
    for record in json.loads((assets / 'F09_manifest.json').read_text()):
        artifact = assets / record['asset']
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == record['sha256'], artifact
        if record['kind'] == 'deb':
            succeeded(run_cli(('dpkg-deb',), ('-x', str(artifact), str(root)), cwd=root, env=env))
        else:
            with zipfile.ZipFile(artifact) as archive:
                archive.extractall(python)
    # Relocate the distribution's Unix/PE libraries without changing their content.
    library = root / 'usr/lib/wine'
    for directory in ('x86_64-unix', 'x86_64-windows'):
        source = root / 'usr/lib/x86_64-linux-gnu/wine' / directory
        (library / directory).symlink_to(source, target_is_directory=True)
        for path in source.iterdir():
            link = library / path.name
            if not link.exists():
                link.symlink_to(path)
    server = library / 'wineserver'
    server.unlink()
    server.symlink_to('wineserver64')
    prefix = root / 'prefix'
    system32 = prefix / 'drive_c/windows/system32'
    system32.mkdir(parents=True)
    shutil.copyfile(root / 'usr/x86_64-w64-mingw32/lib/zlib1.dll', system32 / 'zlib1.dll')
    shutil.copyfile(root / 'usr/x86_64-w64-mingw32/lib/zlib1.dll',
                    root / 'usr/lib/x86_64-linux-gnu/wine/x86_64-windows/zlib1.dll')
    # Extract the current session's genuine product build into this private runtime.
    product = product_wheel
    with zipfile.ZipFile(product) as archive:
        archive.extractall(python)
    (python / 'python312._pth').write_text('python312.zip\n.\nimport site\n')
    executable = library / 'wine64'
    active = make_environment(env, remove=('PYTHONPATH', 'VIRTUAL_ENV', 'CONDA_PREFIX',
        'CONDA_DEFAULT_ENV', 'PYTHONHOME'), updates={
        'WINEPREFIX': str(prefix), 'WINELOADER': str(executable),
        'WINESERVER': str(library / 'wineserver64'), 'WINEDLLPATH': str(library),
        'WINEDLLOVERRIDES': 'mscoree,mshtml,winemenubuilder.exe,explorer.exe=', 'WINEDEBUG': '-all',
        'LD_LIBRARY_PATH': str(root / 'usr/lib/x86_64-linux-gnu'),
        'PATH': str(library) + ':' + env['PATH'], 'WINEPATH': windows_path(python),
        'VELNORA_CONFIG_DIR': windows_path(root / 'config'),
        'VELNORA_CACHE_DIR': windows_path(root / 'cache'), 'VELNORA_NO_INTERACTION': '1'})
    try:
        # Initialize Windows before running product processes, retaining bootstrap logs.
        import subprocess
        with (root / 'wine-bootstrap.log').open('w') as log:
            boot = subprocess.run((str(executable), 'wineboot', '--init'), cwd=root, env=active,
                                  stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=120)
        assert boot.returncode == 0, (root / 'wine-bootstrap.log').read_text()
        system32 = prefix / 'drive_c/windows/system32'
        shutil.copyfile(root / 'usr/x86_64-w64-mingw32/lib/zlib1.dll', system32 / 'zlib1.dll')
        yield executable, python, active
    finally:
        # This server belongs only to this fixture's unique WINEPREFIX.
        succeeded(run_cli((str(library / 'wineserver64'),), ('-k',), cwd=root, env=active))
        succeeded(run_cli((str(library / 'wineserver64'),), ('-w',), cwd=root, env=active))


def windows_activation(root, env, product_wheel):
    with windows_runtime(root, env, product_wheel) as (wine, python, active):
        project = root / 'project with spaces'
        project.mkdir()
        (project / 'pyproject.toml').write_text(legacy_document('[project]\nname="windows-activation"\n'
            'version="1.0"\nrequires-python=">=3.12"\n[tool.<legacy>]\npackage-mode=false\n'))
        (project / 'velnora.toml').write_text('[virtualenvs]\nin-project=true\n')
        selected = project / '.venv'
        succeeded(run_cli((str(wine),), (str(python / 'python.exe'), '-m', 'virtualenv',
            '--no-seed', windows_path(selected)), cwd=project, env=active, timeout=120))
        probe = 'import sys,json,os; print(json.dumps({"prefix":sys.prefix,"os":os.name}))'
        (project / 'probe.py').write_text(probe)
        batch = '@echo off\nset "PATH=' + windows_path(python) + ';%PATH%"\n' + '''python probe.py > before.json
if errorlevel 1 exit /b 90
python -m velnora --no-ansi env activate > activation-command
if errorlevel 1 exit /b 91
python probe.py > after-query.json
if errorlevel 1 exit /b 92
for /f "usebackq delims=" %%A in ("activation-command") do call %%A
if errorlevel 1 exit /b 93
python probe.py > after-activation.json
'''
        (project / 'exercise.bat').write_text(batch)
        succeeded(run_cli((str(wine),), ('cmd', '/d', '/c', 'exercise.bat'),
            cwd=project, env=active, timeout=120))
        before = parse_json((project / 'before.json').read_text())
        queried = parse_json((project / 'after-query.json').read_text())
        activated = parse_json((project / 'after-activation.json').read_text())
        assert before == queried and before['os'] == activated['os'] == 'nt'
        assert PureWindowsPath(before['prefix']) == PureWindowsPath(windows_path(python))
        assert PureWindowsPath(activated['prefix']) == PureWindowsPath(windows_path(selected))
        (selected / 'Scripts/activate.bat').unlink()
        failure = '@echo off\n"' + windows_path(python / 'python.exe') + '" -m velnora --no-ansi env activate 2> activation-error.txt\nexit /b %ERRORLEVEL%\n'
        (project / 'missing.bat').write_text(failure)
        rejected = run_cli((str(wine),), ('cmd', '/d', '/c', 'missing.bat'),
            cwd=project, env=active, timeout=120)
        assert rejected.returncode == 1, (rejected.args, rejected.stdout, rejected.stderr)
        # Redirect inside cmd so Wine's own Unix stderr cannot stand in for diagnostics.
        assert (project / 'activation-error.txt').read_text().strip()
