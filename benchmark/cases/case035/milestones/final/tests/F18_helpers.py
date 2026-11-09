# feature: F18
"""Persistent loopback publication destination and real distribution observations."""
from contextlib import contextmanager
from F00_transport import ClientDisconnects
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import sys
import threading

from packaging.utils import canonicalize_name
from packaging.version import Version

from F01_helpers import project_cli, succeeded
from F03_helpers import save_setting
from F10_helpers import archive_files, archive_metadata, build_archives, build_project


def publishing_target(project, env, repository, *, name="private", endpoint="/legacy/"):
    save_setting(project, env, "repositories." + name, repository["url"] + endpoint)


def publish_call(project, env, *options):
    return project_cli(project, env, "publish", "--no-interaction", *options)


def received_artifacts(repository, artifacts, *, start=0):
    expected = {artifact.name: artifact.read_bytes() for artifact in artifacts}
    received = repository["uploads"][start:]
    assert len(received) == len(expected), [name for name, _ in received]
    assert dict(received) == expected


def distribution_identity(artifact):
    fmt = "wheel" if artifact.suffix == ".whl" else "sdist"
    metadata = archive_metadata(archive_files(artifact), fmt)
    return canonicalize_name(metadata["Name"]), Version(metadata["Version"])


def versioned_artifacts(root, env, destination, version, *, name="build-subject"):
    project = build_project(root, header='[project]\nname = "' + name +
        '"\nversion = "' + version + '"\nrequires-python = ">=3.9,<4"\n')
    if name != "build-subject":
        (project / "build_subject").rename(project / name.replace("-", "_"))
    artifacts = build_archives(project, env)
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for artifact in artifacts.values():
        target = destination / artifact.name
        shutil.copyfile(artifact, target)
        copied.append(target)
    return copied


@contextmanager
def publication_store(root):
    """Store multipart artifacts on disk; reject overwrites and read-only paths."""
    root.mkdir()
    state = {"attempts": [], "errors": []}

    class Handler(ClientDisconnects, BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            message = BytesParser(policy=default).parsebytes(
                ("Content-Type: " + self.headers["Content-Type"] + "\r\n\r\n").encode() + body)
            assert message.is_multipart(), self.headers
            files = [(part.get_filename(), part.get_payload(decode=True))
                     for part in message.iter_parts() if part.get_filename() is not None]
            assert len(files) == 1, files
            name, content = files[0]
            assert Path(name).name == name
            state["attempts"].append((self.path, name))
            if self.path != "/legacy/":
                status = 405
            elif (root / name).exists():
                status = 409
            else:
                (root / name).write_bytes(content)
                status = 201
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, address):
            state["errors"].append(sys.exception())

    server = Server(("127.0.0.1", 0), Handler)
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "Publication destination did not stop"
        assert not state["errors"], state["errors"]
