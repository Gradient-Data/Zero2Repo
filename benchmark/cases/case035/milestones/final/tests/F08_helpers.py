# feature: F08
"""Real standalone releases served offline through an explicit HTTPS proxy."""
from contextlib import contextmanager
from F00_transport import ClientDisconnects
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import html
import re
from pathlib import Path
import shutil
import ssl
import sys
import threading
from urllib.parse import urlsplit, unquote

from _helpers import make_environment, parse_json, run_python, run_cli
from F01_helpers import project_cli, succeeded
from F03_helpers import configuration_environment, save_setting


ASSETS = Path(__file__).with_name("F08_assets")


def standalone_releases():
    records = json.loads((ASSETS / "F08_manifest.json").read_text())
    for record in records:
        artifact = ASSETS / record["asset"]
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == record["sha256"], artifact
    return records


def interpreter_identity(executable, path, env):
    source = '''import json, platform, sys, sysconfig
print(json.dumps({"version": platform.python_version(),
                  "implementation": platform.python_implementation(),
                  "free_threaded": bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
                  "executable": sys.executable}))
'''
    return parse_json(succeeded(run_python(str(executable), source, cwd=path, env=env)).stdout)


def python_rows(path, env, *options):
    """Read the named, left-aligned compact table columns, including whole paths."""
    result = succeeded(project_cli(path, env, "python", "list", *options))
    if not re.match(r"\s*Version\s+Implementation\s+Manager\s+Path\s*\n", result.stdout):
        assert result.stdout.strip(), result
        return []
    lines = result.stdout.splitlines()
    assert lines, result
    header = lines[0]
    labels = ("Version", "Implementation", "Manager", "Path")
    starts = [header.index(label) for label in labels]
    assert starts == sorted(starts), header
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        values = [line[a:b].strip() for a, b in zip(starts, starts[1:] + [len(line)])]
        assert all(values), (header, line)
        rows.append(dict(zip(labels, values)))
    return sorted(rows, key=lambda row: tuple(row[label] for label in labels))


@contextmanager
def standalone_proxy(root, env, releases):
    """Serve genuine releases and a catalogue, with redirects for equivalent builds."""
    root.mkdir()
    cert = root / "proxy.pem"
    key = root / "proxy.key"
    succeeded(run_cli(("openssl",), ("req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-days", "2", "-subj", "/CN=Offline release cache", "-keyout", str(key),
        "-out", str(cert), "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "subjectAltName=DNS:github.com,DNS:api.github.com,DNS:downloads.python.org,DNS:www.python.org"),
        cwd=root, env=env, timeout=30))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    by_url = {record["url"]: ASSETS / record["asset"] for record in releases}
    state = {"requests": [], "catalogue_requests": [], "redirects": [], "fail": False, "errors": []}
    providers = {'github.com', 'api.github.com', 'downloads.python.org', 'www.python.org'}
    catalogue = []
    for record in releases:
        if record['implementation'] != 'cpython':
            continue
        parsed = urlsplit(record['url'])
        tag = parsed.path.split('/download/')[1].split('/')[0]
        group = next((r for r in catalogue if r['tag_name'] == tag), None)
        if group is None:
            group = {'tag_name': tag, 'assets': []}
            catalogue.append(group)
        group['assets'].append({'name': unquote(parsed.path.rsplit('/', 1)[1]),
            'browser_download_url': record['url'],
            'size': (ASSETS / record['asset']).stat().st_size,
            'digest': 'sha256:' + record['sha256']})

    def equivalent_release(url):
        # Provider filenames identify release and variant independently of build revision.
        filename = unquote(urlsplit(url).path.rsplit('/', 1)[-1])
        match = re.fullmatch(r'cpython-(\d+\.\d+\.\d+)(?:\+[^-]+)?-(.+)\.tar\.(gz|zst)', filename)
        if match:
            return next((r for r in releases if r['implementation'] == 'cpython'
                         and r['version'] == match[1]
                         and r['free_threaded'] == ('freethreaded' in match[2])
                         and r['asset'].endswith('.tar.' + match[3])), None)
        # PyPy's provider filenames state the Python minor series and PyPy release.
        match = re.fullmatch(r'pypy(\d+\.\d+)-v[^-]+-linux64\.tar\.gz', filename)
        if match:
            return next((r for r in releases if r['implementation'] == 'pypy'
                         and r['version'].startswith(match[1] + '.')), None)
        return None

    class Handler(ClientDisconnects, BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_CONNECT(self):
            host, separator, port = self.path.partition(":")
            assert separator and port == "443", self.path
            assert host in providers, self.path
            self.send_response(200)
            self.end_headers()
            self.connection = context.wrap_socket(self.connection, server_side=True)
            self.rfile = self.connection.makefile("rb")
            self.wfile = self.connection.makefile("wb")
            self.close_connection = True
            self.handle_one_request()

        def respond(self, status, payload, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            url = 'https://' + self.headers['Host'] + self.path
            if url in by_url:
                state['requests'].append(url)
                if state['fail']:
                    self.send_error(503, 'Offline release cache unavailable')
                    return
                artifact = by_url[url]
                self.send_response(200)
                self.send_header('Content-Length', str(artifact.stat().st_size))
                self.send_header('Content-Type', 'application/octet-stream')
                self.end_headers()
                with artifact.open('rb') as source:
                    shutil.copyfileobj(source, self.wfile)
                return
            if self.path.split('?', 1)[0].endswith(('.tar.gz', '.tar.zst')):
                record = equivalent_release(url)
                if record is None:
                    self.send_error(404, 'Release unavailable in offline repository')
                    return
                state['redirects'].append((url, record['url']))
                self.send_response(302)
                self.send_header('Location', record['url'])
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            state['catalogue_requests'].append(url)
            path = urlsplit(self.path).path
            if self.headers['Host'] == 'api.github.com' and '/releases' in path:
                tail = path.split('/releases', 1)[1].strip('/')
                if not tail:
                    result = catalogue
                elif tail == 'latest':
                    result = max(catalogue, key=lambda r: r['tag_name'])
                elif tail.startswith('tags/'):
                    result = next((r for r in catalogue if r['tag_name'] == tail[5:]), None)
                    if result is None:
                        self.send_error(404, 'Release unavailable in offline repository')
                        return
                else:
                    self.send_error(404, 'Catalogue route unavailable')
                    return
                self.respond(200, json.dumps(result).encode(), 'application/json')
            elif path.endswith('/versions.json') and self.headers['Host'] in {'downloads.python.org', 'www.python.org'}:
                result = [{'python_version': r['version'], 'version': unquote(urlsplit(r['url']).path).split('-v')[1].split('-')[0],
                           'stable': True, 'files': [{'download_url': r['url'], 'filename': unquote(urlsplit(r['url']).path.rsplit('/', 1)[1]),
                           'arch': 'x64', 'platform': 'linux'}]} for r in releases if r['implementation'] == 'pypy']
                self.respond(200, json.dumps(result).encode(), 'application/json')
            else:
                links = '\n'.join('<a href="' + html.escape(r['url']) + '">' +
                                  html.escape(unquote(urlsplit(r['url']).path.rsplit('/', 1)[1])) + '</a>' for r in releases)
                self.respond(200, links.encode(), 'text/html')

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        def handle_error(self, request, address):
            state["errors"].append(sys.exception())

    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    active = make_environment(env, remove=("ALL_PROXY", "all_proxy", "http_proxy", "https_proxy"),
        updates={"HTTPS_PROXY": f"http://127.0.0.1:{server.server_port}",
                 "HTTP_PROXY": f"http://127.0.0.1:{server.server_port}",
                 "SSL_CERT_FILE": str(cert), "REQUESTS_CA_BUNDLE": str(cert),
                 "NO_PROXY": "127.0.0.1,localhost"})
    try:
        yield active, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "Release cache did not stop"
        assert not state["errors"], state["errors"]


def python_environment(root):
    env = configuration_environment(root / "environment")
    storage = root / "managed interpreters"
    save_setting(root, env, "python.installation-dir", str(storage))
    return env, storage


def install_release(path, env, record, *, explicit=True):
    options = ["--implementation", record["implementation"]] if explicit else []
    if record["free_threaded"]:
        options.append("--free-threaded")
    succeeded(project_cli(path, env, "python", "install", record["version"], *options))
    rows = python_rows(path, env, record["version"], "--managed")
    matches = [row for row in rows if row["Implementation"].lower() == record["implementation"]
               and row["Version"].endswith("t") == record["free_threaded"]]
    assert matches, rows
    for row in matches:
        actual = interpreter_identity(row["Path"], path, env)
        assert actual["version"] == record["version"], actual
        assert actual["implementation"].lower() == record["implementation"], actual
        assert actual["free_threaded"] == record["free_threaded"], actual
        assert row["Manager"] == "Velnora", row
    return Path(matches[0]["Path"])
