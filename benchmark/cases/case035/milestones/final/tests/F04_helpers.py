# feature: F04
"""Real distributions, loopback indexes and installed-environment observations."""
from contextlib import contextmanager
from F00_transport import ClientDisconnects
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading

from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.markers import Marker

from _helpers import parse_json, read_toml, run_cli
from F01_helpers import (BUILD_SYSTEM, project_cli, project_environment, succeeded,
                         wheel_observation, write_project)


class DistributionFactory:
    """Build executable packages through the public build command, once per input."""
    def __init__(self, root):
        self.root = root
        self.env = project_environment(root / "builder-environment")
        self.packages = {}

    def create(self, name, version="1.0", *, dependencies=(), extras=None):
        key = (name, version, tuple(dependencies), json.dumps(extras, sort_keys=True))
        if key not in self.packages:
            module = canonicalize_name(name).replace("-", "_")
            document = ('[project]\nname=' + json.dumps(name) + '\nversion=' + json.dumps(version)
                        + '\nrequires-python=">=3.9"\ndependencies=' + json.dumps(list(dependencies)) + '\n')
            if extras:
                document += '[project.optional-dependencies]\n'
                document += ''.join(json.dumps(k) + '=' + json.dumps(v) + '\n' for k, v in extras.items())
            source = write_project(self.root / ("package-" + str(len(self.packages))),
                                   document + BUILD_SYSTEM, module=module)
            (source / module / "__init__.py").write_text(
                'def value():\n    return ' + repr(name + ":" + version) + '\n', encoding="utf-8")
            wheel_observation(source, self.env)
            wheel, = (source / "dist").glob("*.whl")
            self.packages[key] = (source, wheel)
        return self.packages[key]


@contextmanager
def distribution_index(root, wheels):
    """Serve actual artifacts through an ordinary PEP 503 HTML index."""
    root.mkdir(parents=True)
    artifacts = root / "files"
    artifacts.mkdir()
    links = {}
    backend = Path(__file__).with_name("F04_assets") / "F04_poetry_core-2.5.0-py3-none-any.whl"
    for wheel in [*wheels, backend]:
        filename = wheel.name.removeprefix("F04_") if wheel == backend else wheel.name
        name, _, _, _ = parse_wheel_filename(filename)
        target = artifacts / filename
        if target.exists():
            # One filename names one artifact; the first listed wins, so a later
            # copy can never replace bytes whose digest is already linked.
            continue
        shutil.copyfile(wheel, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        links.setdefault(name, []).append(f'<a href="/files/{filename}#sha256={digest}">{filename}</a>')
    for name, members in links.items():
        directory = root / "simple" / name
        directory.mkdir(parents=True)
        (directory / "index.html").write_text('\n'.join(members), encoding="utf-8")

    class Handler(ClientDisconnects, SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        def handle_error(self, request, address):
            errors.append(sys.exception())

    errors = []
    server = Server(("127.0.0.1", 0), partial(Handler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "Index did not stop"
        assert not errors, errors


def dependency_project(path, index, *, standard=(), extra="", legacy="", name="sample-project"):
    document = ('[project]\nname=' + json.dumps(name) + '\nversion="1.0"\nrequires-python=">=3.9"\n'
                + 'dependencies=' + json.dumps(list(standard)) + '\n' + extra)
    if legacy:
        document += '\n[tool.<legacy>.dependencies]\n' + legacy + '\n'
    document += ('\n[[tool.<legacy>.source]]\nname="acceptance"\nurl="' + index
                 + '/simple/"\npriority="primary"\n' + BUILD_SYSTEM)
    return write_project(path, document)


def dependency_lock(path, env):
    succeeded(project_cli(path, env, "lock"))
    return read_toml(path / "velnora.lock")["package"]


def locked_by_name(records):
    result = {}
    for record in records:
        name = canonicalize_name(record["name"])
        assert name not in result, records
        result[name] = record
    return result


def lock_marker_applies(record, target, *, group='main'):
    """Evaluate either documented marker carrier; omission is unconditional."""
    markers = record.get('markers', '')
    expression = markers.get(group, '') if isinstance(markers, dict) else markers
    return not expression or Marker(expression).evaluate(target)


def installed_values(path, env, names):
    """Query metadata and import actual dependency code in the selected environment."""
    # The target environment need not contain packaging: normalize distribution
    # identities in the test process, not by importing a test dependency there.
    source = '''import importlib, importlib.metadata as m, json, sys
print(json.dumps({"installed": {d.metadata["Name"]: d.version for d in m.distributions()},
                  "values": {name: importlib.import_module(name.replace("-", "_")).value()
                             for name in json.loads(sys.argv[1])}}))
'''
    result = succeeded(project_cli(path, env, "run", "python", "-B", "-c", source, json.dumps(list(names))))
    observation = parse_json(result.stdout)
    observation["installed"] = {canonicalize_name(k): v for k, v in observation["installed"].items()}
    return observation


def inspect_names(path, env, *options):
    result = succeeded(project_cli(path, env, "show", "--format=json", *options))
    records = parse_json(result.stdout)
    names = [canonicalize_name(record["name"]) for record in records]
    assert len(names) == len(set(names)), records
    return set(names)


def git_command(path, env, *args):
    return succeeded(run_cli(("git",), args, cwd=path, env=env, timeout=30)).stdout.strip()
