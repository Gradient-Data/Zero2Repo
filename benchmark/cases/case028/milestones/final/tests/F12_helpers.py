# feature: F12
"""Real local module-protocol service and public remote-filesystem observer."""

import contextlib
import http.server
import io
import json
from pathlib import Path
import threading
import zipfile

import pytest

from _helpers import (Process, build_go, isolated_workspace, parse_json,
                      run_process, write_files)
from F01_helpers import f01_success, f01_value


F12_OBSERVER = r'''package main
import (
    "bytes"
    "encoding/json"
    "errors"
    "io"
    "io/fs"
    "net/http"
    "net/url"
    "os"
    "strings"
    "time"
    "github.com/zelviro-sh/zelviro/goparser"
    "github.com/zelviro-sh/zelviro/interp"
    "github.com/zelviro-sh/zelviro/lang/golang"
    "github.com/zelviro-sh/zelviro/modfs"
)
type Command struct {
    Op, Proxy, Redirect, Path string
    Offline bool
    Sources []string
}
type Observation struct {
    Error *string `json:"error"`
    MissingPackage bool `json:"missing_package"`
    NotExist bool `json:"not_exist"`
    Valid bool `json:"valid"`
    Type string `json:"type"`
    Value any `json:"value"`
    Content string `json:"content"`
    Entries []string `json:"entries"`
    Output string `json:"output"`
    Diagnostic string `json:"diagnostic"`
    URLs []string `json:"urls"`
}
// Preserve the requested URL as evidence, then deliver the request to a real
// local HTTP service. Used only to observe the default without external access.
type transport struct { target *url.URL; urls []string }
func (t *transport) RoundTrip(r *http.Request) (*http.Response, error) {
    t.urls = append(t.urls, r.URL.String())
    copy := r.Clone(r.Context())
    if t.target != nil {
        copy.URL.Scheme, copy.URL.Host = t.target.Scheme, t.target.Host
        copy.Host = t.target.Host
    }
    return http.DefaultTransport.RoundTrip(copy)
}
func main() {
    decoder, encoder := json.NewDecoder(os.Stdin), json.NewEncoder(os.Stdout)
    var remote *modfs.FS
    var network *transport
    for {
        var c Command
        if err := decoder.Decode(&c); err == io.EOF { return } else if err != nil { panic(err) }
        o := Observation{}
        var err error
        switch c.Op {
        case "new":
            network = &transport{}
            if c.Redirect != "" {
                network.target, err = url.Parse(c.Redirect); if err != nil { panic(err) }
            }
            remote = modfs.New(modfs.Options{Proxy:c.Proxy, Offline:c.Offline,
                Client:&http.Client{Transport:network, Timeout:10*time.Second}})
            defer remote.CloseIdleConnections()
        case "read":
            var data []byte
            data, err = fs.ReadFile(remote, c.Path)
            o.Content = string(data)
            o.NotExist = errors.Is(err, fs.ErrNotExist)
        case "directory":
            var entries []fs.DirEntry
            entries, err = remote.ReadDir(c.Path)
            o.NotExist = errors.Is(err, fs.ErrNotExist)
            for _, entry := range entries { o.Entries = append(o.Entries, entry.Name()) }
        case "eval":
            engine := interp.NewInterpreter(golang.GoSpec)
            engine.SetPkgfs(".")
            engine.SetStdlibFS(os.DirFS("."))
            engine.SetRemoteFS(remote)
            var output, diagnostic bytes.Buffer
            engine.SetIO(strings.NewReader(""), &output, &diagnostic)
            for _, source := range c.Sources {
                v, evalErr := engine.Eval("remote.go", source)
                err = evalErr
                if err != nil { break }
                o.Valid = v.IsValid()
                if o.Valid { o.Type, o.Value = v.Type().String(), v.Interface() }
            }
            o.MissingPackage = errors.Is(err, goparser.ErrPkgNotFound)
            o.Output, o.Diagnostic = output.String(), diagnostic.String()
            engine.Close()
        default: panic("unknown observation operation")
        }
        if err != nil { message := err.Error(); o.Error = &message }
        o.URLs = network.urls
        if err := encoder.Encode(o); err != nil { panic(err) }
    }
}
'''


class F12Proxy:
    """Serve actual module archives; a controlled outage returns HTTP 503."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir()
        self.requests = []
        self.unavailable = False

    def publish(self, module, version, files, *, latest=True):
        contents = dict(files)
        contents.setdefault("go.mod", f"module {module}\n\ngo 1.26\n")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            for name, content in contents.items():
                output.writestr(f"{module}@{version}/{name}", content)
        info = json.dumps({"Version": version, "Time": "2026-01-01T00:00:00Z"})
        write_files(self.root, {
            f"{module}/@v/{version}.zip": archive.getvalue(),
            f"{module}/@v/{version}.mod": contents["go.mod"],
            f"{module}/@v/{version}.info": info,
        })
        if latest:
            (self.root / module / "@latest").write_text(info)

    @contextlib.contextmanager
    def serving(self):
        owner, errors = self, []

        class Handler(http.server.BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(10)
                super().setup()

            def do_GET(self):
                path = (owner.root / self.path.lstrip("/")).resolve()
                if owner.unavailable:
                    status, content = 503, b"Service unavailable\n"
                elif not path.is_relative_to(owner.root) or not path.is_file():
                    status, content = 404, b"Module resource not found\n"
                else:
                    status, content = 200, path.read_bytes()
                owner.requests.append({"method": "GET", "path": self.path, "status": status})
                self.send_response(status)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, *args):
                pass  # Request records above carry every response status.

        class Server(http.server.HTTPServer):
            def handle_error(self, request, address):
                import sys
                errors.append(sys.exc_info()[1])

        server = Server(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{server.server_port}"
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        thread.start()
        try:
            yield self
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=15)
            assert not thread.is_alive(), "Module service did not stop"
            assert not errors, errors


@pytest.fixture(scope="module")
def f12_tools():
    product = Path.cwd()
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIROCACHE": "off",
                                       "ZELVIRO_DEBUG": None, "ZELVIRO_TRACE": None}) as workspace:
        source = write_files(workspace.root, {"observer.go": F12_OBSERVER})["observer.go"]
        observer = build_go(["go"], source, cwd=product, env=workspace.env,
                            output=workspace.root / "observer", timeout=240).artifact
        cli = build_go(["go"], ".", cwd=product, env=workspace.env,
                       output=workspace.root / "cli", flags=("-buildvcs=false",),
                       timeout=240).artifact

        @contextlib.contextmanager
        def session(proxy="", *, offline=False, redirect=""):
            with Process([observer], cwd=workspace.cwd, env=workspace.env, timeout=90) as process:
                offset = 0

                def command(op, **fields):
                    nonlocal offset
                    process.send(json.dumps(dict(Op=op, **fields)) + "\n")
                    line = process.read_until(b"\n", start=offset)
                    offset += len(line)
                    return parse_json(line)

                f01_success([command("new", Proxy=proxy, Offline=offline, Redirect=redirect)])
                yield command
                result = process.finish()
                assert result.returncode == 0, result

        def run_cli(proxy, target, files=None):
            # Every arm has fresh local sources and caches; no earlier download
            # can make a later offline or failed-proxy invocation succeed.
            with isolated_workspace(base_env=workspace.env,
                                    overrides={"GOPROXY": proxy, "ZELVIROCACHE": "off"}) as run:
                if files:
                    write_files(run.cwd, files)
                return run_process([cli, "run", target], cwd=run.cwd, env=run.env, timeout=45)

        yield session, run_cli


def f12_evaluate(command, package, expression):
    return command("eval", Sources=[f'import "{package}"', expression])


def f12_downloaded(proxy, module, version):
    observed = {(r["path"], r["status"]) for r in proxy.requests}
    assert (f"/{module}/@latest", 200) in observed, proxy.requests
    assert (f"/{module}/@v/{version}.zip", 200) in observed, proxy.requests


def f12_unavailable(observation):
    assert observation["error"] is not None, observation
    assert observation["missing_package"] is True, observation
