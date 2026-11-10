# feature: F10
"""Real build inputs, archive observations and independent wheel execution."""
import json
from pathlib import Path
import shutil
import sys

from _helpers import (make_environment, parse_json, parse_metadata, read_tar,
                      read_zip, run_cli, run_python)
from F01_helpers import BUILD_SYSTEM, project_cli, succeeded, write_project


BUILD_PROJECT = '''[project]
name = "build-subject"
version = "2.3.1"
requires-python = ">=3.9,<4"
'''


def build_project(path, extra="", *, header=BUILD_PROJECT, backend=BUILD_SYSTEM):
    return write_project(path, header + extra + backend, module="build_subject")


def put_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_archives(path, env, *options, output=None, formats=("sdist", "wheel")):
    succeeded(project_cli(path, env, "build", *options))
    destination = output if output is not None else path / "dist"
    artifacts = {}
    for fmt, pattern in (("sdist", "*.tar.gz"), ("wheel", "*.whl")):
        files = list(destination.glob(pattern))
        assert len(files) == (1 if fmt in formats else 0), (fmt, files)
        if files:
            artifacts[fmt] = files[0]
    return artifacts


def archive_files(artifact):
    if artifact.suffix == ".whl":
        return read_zip(artifact)
    records = read_tar(artifact)
    roots = {name.split("/", 1)[0] for name in records}
    assert len(roots) == 1, roots
    root, = roots
    return {name.removeprefix(root + "/"): value
            for name, (kind, value) in records.items() if kind == "file"}


def archive_metadata(files, fmt):
    if fmt == "sdist":
        return parse_metadata(files["PKG-INFO"])
    names = [name for name in files if name.endswith(".dist-info/METADATA")]
    assert len(names) == 1, names
    return parse_metadata(files[names[0]])


def installed_wheel_result(wheel, root, env, source):
    """Install offline, then execute outside the source tree with isolated imports."""
    root.mkdir(parents=True)
    target = root / "site"
    succeeded(run_cli((sys.executable, "-m", "pip"),
        ("install", "--no-index", "--no-deps", "--no-compile", "--target", str(target), str(wheel)),
        cwd=root, env=env, timeout=120))
    clean = make_environment(env, remove=("PYTHONPATH",))
    result = succeeded(run_python(sys.executable,
        'import sys\nsys.path.insert(0, ' + repr(str(target)) + ')\n' + source,
        cwd=root, env=clean))
    return parse_json(result.stdout)


def core_requirement(root):
    source = Path(__file__).with_name("F04_assets") / "F04_poetry_core-2.5.0-py3-none-any.whl"
    destination = root / source.name.removeprefix("F04_")
    shutil.copyfile(source, destination)
    return "poetry-core @ " + destination.as_uri()


def backend_project(path, requirements, source):
    backend = '\n[build-system]\nrequires = ' + json.dumps(requirements) + '''
build-backend = "custom_backend"
backend-path = ["."]
'''
    project = build_project(path, backend=backend)
    put_file(project / "custom_backend.py", source)
    return project


CUSTOM_BACKEND = '''from pathlib import Path
from poetry.core.masonry import api
import build_seed

def get_requires_for_build_wheel(config_settings=None):
    return EXTRA_REQUIREMENTS

def get_requires_for_build_sdist(config_settings=None):
    return EXTRA_REQUIREMENTS

def prepare(config_settings):
    import build_extra
    settings = config_settings or {}
    if settings.get("fail"):
        raise RuntimeError("Requested custom build failure")
    values = [build_seed.value(), build_extra.value(), settings["flavour"]]
    Path("build_subject/generated.py").write_text("VALUES = " + repr(values) + "\\n")

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    prepare(config_settings)
    return api.build_wheel(wheel_directory, config_settings, metadata_directory)

def build_sdist(sdist_directory, config_settings=None):
    prepare(config_settings)
    return api.build_sdist(sdist_directory, config_settings)
'''

NATIVE_BACKEND = '''from pathlib import Path
from poetry.core.masonry import api
import shlex
import subprocess
import sysconfig

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    output = "build_subject/_arithmetic" + sysconfig.get_config_var("EXT_SUFFIX")
    command = shlex.split(sysconfig.get_config_var("LDSHARED"))
    command += ["-fPIC", "-I" + sysconfig.get_path("include"), "arithmetic.c", "-o", output]
    subprocess.run(command, check=True)
    return api.build_wheel(wheel_directory, config_settings, metadata_directory)

def build_sdist(sdist_directory, config_settings=None):
    return api.build_sdist(sdist_directory, config_settings)
'''

NATIVE_SOURCE = r'''#include <Python.h>
static PyObject *multiply(PyObject *self, PyObject *args) {
    long a, b;
    if (!PyArg_ParseTuple(args, "ll", &a, &b)) return NULL;
    return PyLong_FromLong(a * b);
}
static PyMethodDef methods[] = {
    {"multiply", multiply, METH_VARARGS, "Multiply two integers."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_arithmetic", NULL, -1, methods};
PyMODINIT_FUNC PyInit__arithmetic(void) { return PyModule_Create(&module); }
'''
