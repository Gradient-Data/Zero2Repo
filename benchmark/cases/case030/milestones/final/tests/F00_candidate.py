# feature: F00
"""Candidate package installation and import isolation for public test entries."""
import shutil
import sys
import sysconfig
import hashlib
import tempfile
from pathlib import Path

PRODUCT_ROOT = Path.cwd()
_CANDIDATES = {}


def _tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.digest()


def materialize_candidate(directory, *, fortran_containers=False):
    """Reuse a verified candidate copy while keeping worker processes isolated.

    Source comes from the mounted candidate; generated resources come from the
    candidate installation supplied by the harness. Missing resources are errors.
    """
    key = bool(fortran_containers)
    cached = _CANDIDATES.get(key)
    if cached is not None:
        root, expected_digest = cached
        if _tree_digest(root / "zelvori") != expected_digest:
            raise RuntimeError("The shared candidate installation changed during the test run")
        return root

    root = Path(tempfile.mkdtemp(prefix="zelvori-candidate-"))
    package = root / "zelvori"
    # Interpreter bytecode is rebuildable and may belong to the build user.
    # Only source and required package resources cross into the worker copy.
    ignore_bytecode = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(PRODUCT_ROOT / "zelvori", package, copy_function=shutil.copyfile,
                    ignore=ignore_bytecode)
    if fortran_containers:
        installed = Path(sysconfig.get_path('purelib')) / 'zelvori/extensions/gftl_install'
        shutil.copytree(installed, package / 'extensions/gftl_install',
                        copy_function=shutil.copyfile, dirs_exist_ok=True,
                        ignore=ignore_bytecode)
    expected_digest = _tree_digest(package)
    _CANDIDATES[key] = (root, expected_digest)
    return root


def activate_candidate(candidate):
    """Select the candidate in a worker whose parent has no product imports.

    Product-backed oracles run in their own workers, so state and locks never
    cross a process boundary. Detect contamination instead of using a cached
    installation or attempting to rebuild another package's global registries.
    """
    inherited = [name for name in sys.modules
                 if name == 'zelvori' or name.startswith('zelvori.')]
    if inherited:
        raise RuntimeError("Product imports must be isolated from the test parent: " + repr(inherited))
    sys.path.insert(0, str(candidate))


# Native delivery observations. The product translates typed Python into C or
# Fortran and delivers the compiled translation: a script executable is a
# native program, an extension computes with the compiled code, and a translated
# callable does not run the submitted Python body in the interpreter.

import os as _os
import re as _re
import subprocess as _subprocess

_EXECUTION_API = _re.compile(
    r"^(PyRun_\w+|Py_CompileString\w*|PyEval_EvalCode\w*|PyImport_ExecCodeModule\w*"
    r"|Py_Initialize\w*|Py_Main|Py_BytesMain|Py_RunMain)$")


def _elf_symbols(path):
    path = Path(path)
    with open(path, "rb") as handle:
        assert handle.read(4) == b"\x7fELF", f"{path} is not a compiled native file"
    names = set()
    for command in (["nm", "-D", str(path)], ["nm", str(path)]):
        listed = _subprocess.run(command, capture_output=True, text=True)
        for line in listed.stdout.splitlines():
            fields = line.split()
            if fields:
                names.add(fields[-1].split("@")[0])
    dynamic = _subprocess.run(["readelf", "-d", str(path)], capture_output=True, text=True)
    assert dynamic.returncode == 0, dynamic.stderr
    needed = _re.findall(r"\(NEEDED\)\s+Shared library: \[(.+?)\]", dynamic.stdout)
    return names, needed


def require_native_program(path):
    """A delivered script executable is a native program: it carries no Python runtime."""
    names, needed = _elf_symbols(path)
    runtime = [name for name in needed if name.startswith("libpython")]
    assert not runtime, f"{path} needs a Python runtime: {runtime}"
    python = sorted(name for name in names if _re.match(r"_?Py[A-Z_]", name))
    assert not python, f"{path} carries Python runtime symbols: {python[:8]}"


def require_native_extension(path):
    """A delivered extension computes natively; it does not execute Python source."""
    names, _ = _elf_symbols(path)
    executing = sorted(name for name in names if _EXECUTION_API.match(name))
    assert not executing, f"{path} executes Python code at run time: {executing}"


def _inside(filename, roots):
    return filename.startswith("<frozen") or any(filename.startswith(root) for root in roots)



def require_compiled(value, language):
    """A C or Fortran translation delivers compiled callables, not Python functions."""
    if language == "python":
        return value
    import inspect
    import types

    def python_code(obj):
        # Behaviour implemented by Python bytecode: a function or method, or an
        # instance whose call is a Python method (a wrapper object).
        if isinstance(obj, (types.FunctionType, types.MethodType)):
            return True
        if inspect.isclass(obj) or isinstance(obj, types.ModuleType):
            return False
        call = getattr(type(obj), "__call__", None)
        return callable(obj) and isinstance(call, types.FunctionType)

    found = []

    def visit(obj, label, depth):
        if python_code(obj):
            found.append(label)
            return
        if depth == 0:
            return
        if inspect.isclass(obj):
            members = vars(obj).items()
        elif isinstance(obj, types.ModuleType) or hasattr(obj, "__dict__"):
            members = ((k, v) for k, v in vars(obj).items() if not k.startswith("__"))
        else:
            return
        for name, member in list(members):
            if inspect.isclass(member) or python_code(member):
                visit(member, f"{label}.{name}", depth - 1)

    visit(value, getattr(value, "__name__", type(value).__name__), 2)
    assert not found, f"the {language} translation delivered Python functions: {found[:8]}"
    return value


def _checked(translate):
    def call(*args, **kwargs):
        return require_compiled(translate(*args, **kwargs), kwargs.get("language", "fortran"))
    return call


def without_interpretation(consume):
    """Apply consume(value) while watching how translated callables compute.

    Once a translation request has returned, code from outside the product, the
    tests and the Python installation (the submitted source) must not run with
    product Python code beneath it on the call stack. Native translations call
    no such code; an implementation that runs the submitted body in the
    interpreter does. Product code below a translation request (ezelvori,
    lambdify) is exempt: translation may read the submitted source.
    """
    import sysconfig
    import zelvori

    product = str(Path(zelvori.__file__).resolve().parent) + _os.sep
    allowed = [product, str(Path(__file__).resolve().parent) + _os.sep]
    allowed += [str(Path(sysconfig.get_path(key)).resolve()) + _os.sep
                for key in ("stdlib", "platstdlib", "purelib", "platlib")]
    entries = set()
    for name in ("ezelvori", "lambdify"):
        code = getattr(getattr(zelvori, name, None), "__code__", None)
        if code is not None:
            entries.add(code)
    seen = []

    def profile(frame, event, arg):
        if event != "call" or _inside(frame.f_code.co_filename, allowed):
            return
        below = frame.f_back
        under_product = False
        while below is not None:
            if below.f_code in entries:
                return
            if below.f_code.co_filename.startswith(product):
                under_product = True
            below = below.f_back
        if under_product and len(seen) < 5:
            seen.append(f"{frame.f_code.co_name} ({frame.f_code.co_filename}:{frame.f_code.co_firstlineno})")

    def run(value):
        saved = {name: getattr(zelvori, name) for name in ("ezelvori", "lambdify") if hasattr(zelvori, name)}
        for name, translate in saved.items():
            setattr(zelvori, name, _checked(translate))
        if any(value is translate for translate in saved.values()):
            value = _checked(value)
        sys.setprofile(profile)
        try:
            result = consume(value)
        finally:
            sys.setprofile(None)
            for name, translate in saved.items():
                setattr(zelvori, name, translate)
        assert not seen, "translated callables ran submitted Python code in the interpreter: " + "; ".join(seen)
        return result
    return run
