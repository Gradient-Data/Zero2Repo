# feature: F13
"""Public offline source access, persistence, and secondary-source selection."""

import base64
from pathlib import Path

from _helpers import isolated_workspace, write_files
from F13_helpers import (F12Proxy, f01_success, f01_value, f12_downloaded,
                         f12_unavailable, f13_tools, f13_injection,
                         f13_expression, f13_go_download, f13_snapshot,
                         f13_cli_value, f13_cli_missing)


def test_injected_archive_files_directories_and_evaluation(f13_tools, tmp_path):
    observe, _ = f13_tools
    proxy = F12Proxy(tmp_path / "proxy")
    module, version = "offline.test/supplied", "v1.4.2"
    source = "package calc\nfunc Compute(n int) int { return 7*n+13 }\n"
    data = b"\x00archive bytes\xff\n"
    proxy.publish(module, version, {"calc/calc.go": source, "calc/data/value.bin": data})
    with proxy.serving(), isolated_workspace() as work:
        rows = observe(work, [
            f13_injection(proxy, module, version),
            {"Op": "read", "Path": module + "/calc/calc.go"},
            {"Op": "read", "Path": module + "/calc/data/value.bin"},
            {"Op": "directory", "Path": module + "/calc"},
            f13_expression(module + "/calc", "calc.Compute(6)"),
            f13_expression(module + "/calc", "calc.Compute(11)"),
            {"Op": "inject", "Archive": {"Module": "offline.test/invalid", "Version": version,
                                           "Data": base64.b64encode(b"not a zip archive").decode()}},
        ], Proxy=proxy.url, Offline=True)
        f01_success(rows[:6])
        assert base64.b64decode(rows[1]["data"], validate=True) == source.encode()
        assert base64.b64decode(rows[2]["data"], validate=True) == data
        assert rows[3]["entries"] == {"calc.go": False, "data": True}
        f01_value(rows[4], "int", 55)
        f01_value(rows[5], "int", 90)
        assert rows[6]["error"] is not None, rows[6]
        assert not proxy.requests, proxy.requests


def test_cli_persistence_location_and_disabled_storage(f13_tools, tmp_path):
    observe, cli_run = f13_tools
    proxy = F12Proxy(tmp_path / "proxy")
    module, version = "offline.test/persist", "v1.3.7"
    source = "package main\nfunc main() { println(6*9+5) }\n"
    proxy.publish(module, version, {"main.go": source})
    with proxy.serving():
        for location in ("default", "custom"):
            with isolated_workspace() as work:
                default = Path(work.env["XDG_CACHE_HOME"]) / "zelviro/download"
                cache = None if location == "default" else work.root / "chosen-storage"
                storage = default if cache is None else cache
                proxy.requests.clear()
                f13_cli_value(cli_run(work, proxy.url, module, cache=cache), b"59\n")
                f12_downloaded(proxy, module, version)
                assert f13_snapshot(storage), "Successful download did not persist any files"
                if cache is not None:
                    assert not f13_snapshot(default), "Custom storage wrote to the default location"
                # A separate CLI process and an independent reader consume the saved source.
                proxy.requests.clear()
                f13_cli_value(cli_run(work, "off," + proxy.url, module, cache=cache), b"59\n")
                rows = observe(work, [{"Op": "read", "Path": module + "/main.go"}],
                               Proxy=proxy.url, Offline=True, CacheDir=str(storage))
                f01_success(rows)
                assert base64.b64decode(rows[0]["data"], validate=True) == source.encode()
                assert not proxy.requests, proxy.requests

        with isolated_workspace() as work:
            watched = [Path(work.env[key]) for key in ("XDG_CACHE_HOME", "GOMODCACHE", "GOPATH")]
            before = [f13_snapshot(path) for path in watched]
            proxy.requests.clear()
            f13_cli_value(cli_run(work, proxy.url, module, cache="off"), b"59\n")
            f12_downloaded(proxy, module, version)
            assert [f13_snapshot(path) for path in watched] == before
            f13_cli_missing(cli_run(work, "off," + proxy.url, module, cache="off"))
            # A real Go download is usable when storage is enabled, but not when disabled.
            f13_go_download(work, proxy, module, [version])
            proxy.requests.clear()
            f13_cli_value(cli_run(work, "off," + proxy.url, module), b"59\n")
            # Enabled reuse may populate product storage. Only the disabled
            # invocation promises not to write module downloads.
            before = [f13_snapshot(path) for path in watched]
            f13_cli_missing(cli_run(work, "off," + proxy.url, module, cache="off"))
            assert [f13_snapshot(path) for path in watched] == before
            assert not proxy.requests, proxy.requests


def test_go_download_versions_saved_choice_and_proxy_precedence(f13_tools, tmp_path):
    _, cli_run = f13_tools
    proxy = F12Proxy(tmp_path / "proxy")
    # Each group isolates one promised ordering component; no prerelease policy
    # is assumed. Versions are downloaded in the listed order, with the highest
    # in the middle, so neither the first nor the last download is the answer.
    choices = [
        ("major", ("v0.99.99", "v1.0.0", "v0.100.0")),
        ("minor", ("v1.9.99", "v1.10.0", "v1.2.0")),
        ("patch", ("v1.10.9", "v1.10.12", "v1.10.2")),
    ]
    with proxy.serving():
        for part, versions in choices:
            module = "offline.test/" + part
            for version, result in zip(versions, (31, 78, 64)):
                proxy.publish(module, version, {
                    "main.go": f"package main\nfunc main() {{ println({result}) }}\n",
                })
            with isolated_workspace() as work:
                f13_go_download(work, proxy, module, versions)
                proxy.requests.clear()
                f13_cli_value(cli_run(work, "off," + proxy.url, module), b"78\n")
                assert not proxy.requests, proxy.requests

        module = "offline.test/precedence"
        for version, result in (("v1.2.0", 42), ("v1.8.0", 96)):
            proxy.publish(module, version, {
                "main.go": f"package main\nfunc main() {{ println({result}) }}\n",
            }, latest=(version == "v1.2.0"))
        with isolated_workspace() as work:
            f13_go_download(work, proxy, module, ["v1.8.0"])
            proxy.requests.clear()
            # Successful proxy lookup wins even over a newer downloaded release.
            saved = work.root / "saved"
            f13_cli_value(cli_run(work, proxy.url, module, cache=saved), b"42\n")
            f12_downloaded(proxy, module, "v1.2.0")
            proxy.requests.clear()
            f13_cli_value(cli_run(work, "off," + proxy.url, module, cache=saved), b"42\n")
            assert not proxy.requests, proxy.requests
            # The saved choice survives a newly published version as well.
            (proxy.root / module / "@latest").write_bytes(
                (proxy.root / module / "@v/v1.8.0.info").read_bytes())
            f13_cli_value(cli_run(work, proxy.url, module, cache=saved), b"42\n")

        with isolated_workspace() as work:
            f13_go_download(work, proxy, module, ["v1.2.0", "v1.8.0"])
            proxy.requests.clear()
            proxy.unavailable = True
            try:
                f13_cli_value(cli_run(work, proxy.url, module), b"96\n")
                assert any(r["status"] == 503 for r in proxy.requests), proxy.requests
            finally:
                proxy.unavailable = False


def test_offline_sources_and_missing_packages_without_requests(f13_tools, tmp_path):
    observe, cli_run = f13_tools
    proxy = F12Proxy(tmp_path / "proxy")
    module, version = "offline.test/available", "v1.5.1"
    source = "package calc\nfunc Compute(n int) int { return n*n-3 }\n"
    proxy.publish(module, version, {"calc/calc.go": source})
    with proxy.serving(), isolated_workspace() as work:
        storage = work.root / "saved"
        # Live baseline demonstrates that the service and saved source both work.
        rows = observe(work, [f13_expression(module + "/calc", "calc.Compute(8)")],
                       Proxy=proxy.url, CacheDir=str(storage))
        f01_value(rows[0], "int", 61)
        f12_downloaded(proxy, module, version)
        proxy.requests.clear()
        rows = observe(work, [
            f13_expression("cmp", "cmp.Compare(23, 7)"),
            f13_expression(module + "/calc", "calc.Compute(9)"),
            f13_injection(proxy, module, version),
            f13_expression(module + "/calc", "calc.Compute(5)"),
            f13_expression(module + "/missing", "missing.Value()"),
            f13_expression("offline.test/absent", "absent.Value()"),
            {"Op": "read", "Path": "offline.test/absent/value.go"},
        ], Proxy=proxy.url, Offline=True, Bundled=True, CacheDir=str(storage))
        f01_value(rows[0], "int", 1)
        f01_value(rows[1], "int", 78)
        f01_success([rows[2]])
        f01_value(rows[3], "int", 22)
        f12_unavailable(rows[4])
        f12_unavailable(rows[5])
        assert rows[6]["error"] is not None and rows[6]["not_exist"] is True, rows[6]
        assert not proxy.requests, proxy.requests

        write_files(work.cwd, {"offline.go": 'package main\nimport "cmp"\n'
                               f'import "{module}/calc"\n'
                               'func main() { println(cmp.Compare(3, 12), calc.Compute(7)) }\n'})
        f13_cli_value(cli_run(work, "off," + proxy.url, "offline.go", cache=storage), b"-1 46\n")
        f13_cli_missing(cli_run(work, "off," + proxy.url, "offline.test/absent", cache=storage))
        assert not proxy.requests, proxy.requests
