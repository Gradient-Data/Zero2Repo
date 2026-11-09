# feature: F16
"""Sandbox runs using application model inputs and real local workspaces."""
import base64
import io

from _helpers import bounded
from F01_helpers import RecordingModel, function_call
from velmora import RunConfig, Runner
from velmora.sandbox import SandboxAgent, SandboxRunConfig
from openai.types.responses.response_custom_tool_call import ResponseCustomToolCall


async def sandbox_run(agent, input='Work in the workspace.', **options):
    return await bounded(Runner.run(agent, input, run_config=RunConfig(
        tracing_disabled=True, sandbox=SandboxRunConfig(**options))))


def shell_call(command, identity='shell'):
    return function_call('exec_command', {'cmd': command, 'login': False}, identity)


def patch_call(patch, identity='patch'):
    return ResponseCustomToolCall(type='custom_tool_call', name='apply_patch',
                                  call_id=identity, input=patch)


def tool_outputs(model, request=-1):
    return {item['call_id']: item['output'] for item in model.requests[request]['input']
            if item.get('type') in ('function_call_output', 'custom_tool_call_output')}


def shell_output(text):
    """Read the published status line and Output section, ignoring timing metadata."""
    header, separator, output = text.partition('\nOutput:\n')
    assert separator, text
    statuses = [line.removeprefix('Process exited with code ')
                for line in header.splitlines() if line.startswith('Process exited with code ')]
    assert len(statuses) == 1, text
    return int(statuses[0]), output


# Valid small raster files generated with Pillow; no runtime encoder dependency.
_RASTERS = {
    'PNG': 'iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAIAAAASFvFNAAAAFUlEQVR4nGOUCOtjYGBgYGBgYoABABF+AQCg0PQ1AAAAAElFTkSuQmCC',
    'JPEG': '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAACAAMDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDiaKKK+iPnz//Z',
    'GIF': 'R0lGODdhAwACAIEAABhWjgAAAAAAAAAAACwAAAAAAwACAAAIBgABCBwYEAA7',
    'WEBP': 'UklGRjgAAABXRUJQVlA4ICwAAADQAQCdASoDAAIAAUAmJaACdLoB+AADsAD+9Bi3/kpr/G3Xn/8guWF1xGAAAA==',
    'BMP': 'Qk1OAAAAAAAAADYAAAAoAAAAAwAAAAIAAAABABgAAAAAABgAAADEDgAAxA4AAAAAAAAAAAAAjlYYjlYYjlYYAAAAjlYYjlYYjlYYAAAA',
    'TIFF': 'SUkqAAgAAAAKAAABBAABAAAAAwAAAAEBBAABAAAAAgAAAAIBAwADAAAAhgAAAAMBAwABAAAAAQAAAAYBAwABAAAAAgAAABEBBAABAAAAjAAAABUBAwABAAAAAwAAABYBBAABAAAAAgAAABcBBAABAAAAEgAAABwBAwABAAAAAQAAAAAAAAAIAAgACAAYVo4YVo4YVo4YVo4YVo4YVo4=',
}

def raster_bytes(format):
    return base64.b64decode(_RASTERS[format], validate=True)

def image_payload(output, mime=None):
    assert isinstance(output, list) and len(output) == 1, output
    part = output[0]
    assert part['type'] == 'input_image', output
    prefix, encoded = part['image_url'].split(',', 1)
    assert prefix.startswith('data:image/') and prefix.endswith(';base64'), prefix
    if mime is not None:
        # Media types are the registered IANA names of the recognised content formats.
        assert prefix.removeprefix('data:').removesuffix(';base64').lower() in mime, prefix
    return base64.b64decode(encoded, validate=True)


IMAGE_MIME = {'PNG': {'image/png'}, 'JPEG': {'image/jpeg'}, 'GIF': {'image/gif'},
              'WEBP': {'image/webp'}, 'BMP': {'image/bmp'}, 'TIFF': {'image/tiff'},
              'SVG': {'image/svg+xml'}}


from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import threading


class HttpSnapshotStorage:
    """Application storage adapter transferring actual snapshot bytes over HTTP."""
    def __init__(self, url):
        self.url = url

    def upload(self, identity, data):
        with urlopen(Request(self.url + '/' + identity, data=data.read(), method='PUT'), timeout=10) as response:
            assert response.status == 201

    def download(self, identity):
        with urlopen(self.url + '/' + identity, timeout=10) as response:
            return io.BytesIO(response.read())

    def exists(self, identity):
        try:
            with urlopen(Request(self.url + '/' + identity, method='HEAD'), timeout=10) as response:
                return response.status == 200
        except HTTPError as error:
            if error.code != 404:
                raise
            return False


@contextmanager
def snapshot_storage(directory):
    """Serve a filesystem-backed application snapshot store on loopback."""
    directory.mkdir()

    class Handler(BaseHTTPRequestHandler):
        def target(self):
            from pathlib import Path
            name = self.path.removeprefix('/')
            assert name and Path(name).name == name
            return directory / name

        def do_PUT(self):
            self.target().write_bytes(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(201)
            self.end_headers()

        def do_HEAD(self):
            self.send_response(200 if self.target().is_file() else 404)
            self.end_headers()

        def do_GET(self):
            path = self.target()
            if not path.is_file():
                self.send_response(404)
                self.end_headers()
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield HttpSnapshotStorage(f'http://127.0.0.1:{server.server_port}')
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        assert not worker.is_alive(), 'Snapshot storage server failed to stop.'
