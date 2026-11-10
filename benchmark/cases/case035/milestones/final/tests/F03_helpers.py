# feature: F03
"""Scoped configuration and real loopback package repositories."""
from contextlib import contextmanager
from F00_transport import ClientDisconnects
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import hashlib
import json
from pathlib import Path
import ssl
import sys
import threading

from _helpers import make_environment, parse_json, probe_python, read_toml, run_cli
from F01_helpers import (
    BUILD_SYSTEM, project_cli, project_environment, refused, succeeded, write_project,
)


def configuration_environment(root):
    return make_environment(project_environment(root),
        remove=("VELNORA_CACHE_DIR", "VELNORA_VIRTUALENVS_IN_PROJECT",
                "VELNORA_KEYRING_ENABLED", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
                "SSL_CERT_FILE"),
        updates={"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})


def configuration_call(path, env, *args, stdin=""):
    return run_cli(("velnora",), ("--no-ansi", "config", *args),
                   cwd=path, env=env, stdin=stdin, timeout=60)


def save_setting(path, env, key, *values, local=False):
    return succeeded(configuration_call(path, env, *(('--local',) if local else ()),
                                        key, *values))


def query_setting(path, env, key, *, structured=False):
    output = succeeded(configuration_call(path, env, key)).stdout.strip()
    return parse_json(output) if structured else output


def listed_settings(path, env):
    result = succeeded(configuration_call(path, env, "--list"))
    fields = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(" = ")
        assert separator and key not in fields, result.stdout
        fields[key] = value
    return fields, result


def stored_value(document, key):
    for component in key.split("."):
        document = document[component]
    return document


def repository_wheel(root, env):
    path = write_project(root / "package", '''[project]
name = "access-addon"
version = "1.2.3"
requires-python = ">=3.9"
''' + BUILD_SYSTEM, module="access_addon")
    (path / "access_addon" / "__init__.py").write_text(
        'def value():\n    return "downloaded repository contents"\n', encoding="utf-8")
    succeeded(project_cli(path, env, "build", "--format", "wheel"))
    wheels = list((path / "dist").glob("*.whl"))
    assert len(wheels) == 1, wheels
    return path, wheels[0]


@contextmanager
def package_repository(wheel, *, tls=None, proxy_host=None):
    """Serve an actual wheel and accept multipart uploads with optional Basic auth."""
    payload = wheel.read_bytes()
    state = {"credentials": None, "requests": [], "uploads": [], "errors": [], "tunnels": []}

    class Handler(ClientDisconnects, BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def respond(self, status, content=b"", content_type="text/html"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def authorize(self, body=b""):
            authorization = self.headers.get("Authorization")
            peer = self.connection.getpeercert() if tls else None
            pair = state["credentials"]
            expected = None if pair is None else "Basic " + base64.b64encode(
                (pair[0] + ":" + pair[1]).encode()).decode()
            accepted = pair is None or authorization == expected
            state["requests"].append({"method": self.command, "path": self.path,
                "authorization": authorization, "accepted": accepted,
                "peer": peer, "body": body})
            if not accepted:
                self.respond(403, b"Repository access denied")
            return accepted

        def do_CONNECT(self):
            assert proxy_host and self.path == proxy_host + ':443', self.path
            assert tls is not None
            state['tunnels'].append(self.path)
            self.send_response(200)
            self.end_headers()
            self.connection = tls.wrap_socket(self.connection, server_side=True)
            self.rfile = self.connection.makefile('rb')
            self.wfile = self.connection.makefile('wb')
            self.close_connection = True
            self.handle_one_request()

        def do_GET(self):
            if not self.authorize():
                return
            if self.path == "/simple/access-addon/":
                digest = hashlib.sha256(payload).hexdigest()
                content = (f'<a href="/files/{wheel.name}#sha256={digest}">{wheel.name}</a>').encode()
                self.respond(200, content)
            elif self.path == "/files/" + wheel.name:
                self.respond(200, payload, "application/octet-stream")
            else:
                self.respond(404, b"Not found")

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if not self.authorize(body):
                return
            message = BytesParser(policy=default).parsebytes(
                ("Content-Type: " + self.headers["Content-Type"] + "\r\n\r\n").encode() + body)
            assert message.is_multipart(), self.headers
            files = [(part.get_filename(), part.get_payload(decode=True))
                     for part in message.iter_parts() if part.get_filename() is not None]
            assert files, "Upload contained no artifact"
            state["uploads"].extend(files)
            self.respond(201, b"Created")

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, address):
            state["errors"].append(sys.exception())

    server = Server(("127.0.0.1", 0), Handler)
    if tls and not proxy_host:
        server.socket = tls.wrap_socket(server.socket, server_side=True)
    state["url"] = ("https" if tls and not proxy_host else "http") + f"://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "Repository did not stop"
        assert not state["errors"], state["errors"]


def repository_consumer(path, env, repository, *, name="private"):
    write_project(path, '''[project]
name = "access-consumer"
version = "1.0.0"
requires-python = ">=3.9"
[tool.<legacy>.dependencies]
access-addon = {version = "1.2.3", source = "''' + name + '''"}
[[tool.<legacy>.source]]
name = "''' + name + '''"
url = "''' + repository["url"] + '''/simple/"
priority = "primary"
''')
    # Keep environment state out of each authentication/trust comparison.
    (path / "velnora.toml").write_text('[virtualenvs]\nin-project = true\n', encoding="utf-8")
    return path


def fetch_repository(path, env, repository, *, name="private", accepted=True):
    repository_consumer(path, env, repository, name=name)
    result = project_cli(path, env, "--no-cache", "install", "--no-root")
    if not accepted:
        return refused(result)
    succeeded(result)
    executable = succeeded(project_cli(path, env, "env", "info", "--executable")).stdout.strip()
    observation = probe_python(executable, cwd=path, env=env,
        application_source="import access_addon\nreturn access_addon.value()")
    assert observation["application"] == "downloaded repository contents"
    return result


def publish_repository(path, env, repository, wheel, *, name="private", accepted=True):
    before = len(repository["uploads"])
    result = project_cli(path, env, "publish", "--repository", name, "--no-interaction")
    if not accepted:
        refused(result)
        assert len(repository["uploads"]) == before
        return result
    succeeded(result)
    assert repository["uploads"][before:] == [(wheel.name, wheel.read_bytes())]
    return result


def certificate_material(root, env, *, server_names=()):
    root.mkdir()
    def openssl(*args):
        succeeded(run_cli(("openssl",), args, cwd=root, env=env, timeout=30))

    for authority in ("trusted", "other"):
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                "-subj", "/CN=" + authority, "-keyout", authority + ".key",
                "-out", authority + ".pem", "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    for role, extensions in (("server", "subjectAltName=IP:127.0.0.1" + "".join(",DNS:" + name for name in server_names) + "\nextendedKeyUsage=serverAuth\n"),
                              ("client", "extendedKeyUsage=clientAuth\n")):
        openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=" + role,
                "-keyout", role + ".key", "-out", role + ".csr")
        (root / (role + ".ext")).write_text(extensions, encoding="utf-8")
        openssl("x509", "-req", "-in", role + ".csr", "-CA", "trusted.pem",
                "-CAkey", "trusted.key", "-CAcreateserial", "-days", "2",
                "-extfile", role + ".ext", "-out", role + ".pem")
    (root / "client-combined.pem").write_bytes(
        (root / "client.pem").read_bytes() + (root / "client.key").read_bytes())
    return root


def repository_tls(material, *, client_required=False):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(material / "server.pem", material / "server.key")
    if client_required:
        context.load_verify_locations(material / "trusted.pem")
        context.verify_mode = ssl.CERT_REQUIRED
    return context


_SECRET_SNAPSHOT = '''import json
import secretstorage
import time

connection = secretstorage.dbus_init()
for attempt in range(100):
    if secretstorage.check_service_availability(connection):
        break
    time.sleep(0.05)
else:
    raise AssertionError("The isolated Secret Service did not become available")

items = {}
for collection in secretstorage.get_all_collections(connection):
    assert not collection.is_locked(), "The isolated collection is locked"
    for item in collection.get_all_items():
        assert not item.is_locked(), "A stored secret is locked"
        assert item.item_path not in items, "Duplicate Secret Service item path"
        items[item.item_path] = item.get_secret().decode("utf-8")
connection.close()
print(json.dumps(items))
'''


def keyring_snapshot(path, env):
    """Enumerate and consume every secret in a separate, independent client."""
    result = succeeded(run_cli((sys.executable,), ("-B", "-c", _SECRET_SNAPSHOT),
                               cwd=path, env=env, timeout=15))
    return parse_json(result.stdout)


@contextmanager
def isolated_keyring(env):
    """Run the packaged, unmodified GNOME Secret Service on a private session bus."""
    import subprocess
    import tempfile
    import time

    assets = Path(__file__).with_name("F03_assets")
    manifest = json.loads((assets / "F03_manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="f03-secret-") as directory:
        root = Path(directory)
        provider = root / "provider"
        for package in manifest["packages"]:
            archive = assets / package["asset"]
            assert hashlib.sha256(archive.read_bytes()).hexdigest() == package["sha256"], archive
            succeeded(run_cli(("dpkg-deb",), ("--extract", str(archive), str(provider)),
                               cwd=root, env=env, timeout=30))
        for name in ("runtime", "data", "control"):
            (root / name).mkdir(mode=0o700)
        Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
        active = make_environment(env, remove=("PYTHON_KEYRING_BACKEND", "GNOME_KEYRING_CONTROL"), updates={
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(root / "bus"),
            "XDG_RUNTIME_DIR": str(root / "runtime"),
            "XDG_DATA_HOME": str(root / "data"),
        })
        processes = []
        with (root / "service.log").open("w+b") as log:
            try:
                bus = subprocess.Popen(("dbus-daemon", "--session", "--nofork", "--nopidfile",
                    "--address=" + active["DBUS_SESSION_BUS_ADDRESS"]),
                    env=active, cwd=root, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT)
                processes.append(bus)
                deadline = time.monotonic() + 10
                while not (root / "bus").exists():
                    assert bus.poll() is None, ("Session bus exited", (root / "service.log").read_text())
                    assert time.monotonic() < deadline, "Session bus socket did not appear"
                    time.sleep(0.05)
                daemon_env = make_environment(active, updates={
                    "LD_LIBRARY_PATH": str(provider / "usr/lib/x86_64-linux-gnu")})
                daemon = subprocess.Popen((str(provider / "usr/bin/gnome-keyring-daemon"),
                    "--foreground", "--components=secrets", "--unlock",
                    "--control-directory=" + str(root / "control")),
                    env=daemon_env, cwd=root, stdin=subprocess.PIPE,
                    stdout=log, stderr=subprocess.STDOUT)
                processes.append(daemon)
                daemon.stdin.write(b"acceptance-keyring-unlock\n")
                daemon.stdin.close()
                keyring_snapshot(root, active)
                assert daemon.poll() is None, ("Secret Service exited", (root / "service.log").read_text())
                yield active
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
