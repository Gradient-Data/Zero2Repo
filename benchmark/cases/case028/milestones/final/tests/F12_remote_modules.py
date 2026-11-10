# feature: F12
"""Acceptance of remote modules through real proxy traffic and evaluation."""

from urllib.parse import urlsplit

from F12_helpers import (F12Proxy, f12_tools, f12_evaluate, f12_downloaded,
                         f12_unavailable, f01_success, f01_value)


def test_latest_modules_and_transitive_packages(f12_tools, tmp_path):
    session, _ = f12_tools
    proxy = F12Proxy(tmp_path / "proxy")
    for version, amount in (("v1.0.0", 2), ("v1.6.2", 31)):
        proxy.publish("remote.test/base", version, {
            "numbers/numbers.go": f"package numbers\nfunc Scale(n int) int {{ return n*{amount} }}\n",
        })
    for version, offset in (("v1.0.0", 3), ("v1.3.4", 17)):
        proxy.publish("remote.test/front", version, {
            "go.mod": "module remote.test/front\n\ngo 1.26\nrequire remote.test/base v1.0.0\n",
            "calc/calc.go": 'package calc\nimport "remote.test/base/numbers"\n'
                             f'func Compute(n int) int {{ return numbers.Scale(n)+{offset} }}\n',
        })
    with proxy.serving(), session(proxy.url) as command:
        for argument, expected in ((4, 141), (9, 296)):
            value = f12_evaluate(command, "remote.test/front/calc", f"calc.Compute({argument})")
            f01_value(value, "int", expected)
        f12_downloaded(proxy, "remote.test/front", "v1.3.4")
        f12_downloaded(proxy, "remote.test/base", "v1.6.2")


def test_shortest_containing_module_and_longer_prefix(f12_tools, tmp_path):
    session, _ = f12_tools
    proxy = F12Proxy(tmp_path / "proxy")
    proxy.publish("remote.test/choice", "v1.1.0", {
        "branch/calc/calc.go": 'package calc\nfunc Result() string { return "short root" }\n',
    })
    proxy.publish("remote.test/choice/branch", "v1.9.0", {
        "calc/calc.go": 'package calc\nfunc Result() string { return "long root" }\n',
    })
    proxy.publish("remote.test/extended", "v1.2.0", {
        "other/other.go": "package other\nvar Answer = 5\n",
    })
    nested_source = "package calc\nfunc Compute(n int) int { return 13*n+7 }\n"
    proxy.publish("remote.test/extended/branch/v2", "v2.4.0", {
        "calc/calc.go": nested_source,
    })
    with proxy.serving(), session(proxy.url) as command:
        value = f12_evaluate(command, "remote.test/choice/branch/calc", "calc.Result()")
        f01_value(value, "string", "short root")
        value = f12_evaluate(command, "remote.test/extended/branch/v2/calc", "calc.Compute(6)")
        f01_value(value, "int", 85)
        content = command("read", Path="remote.test/extended/branch/v2/calc/calc.go")
        f01_success([content])
        assert content["content"] == nested_source
        f12_downloaded(proxy, "remote.test/choice", "v1.1.0")
        f12_downloaded(proxy, "remote.test/extended/branch/v2", "v2.4.0")


def test_default_first_proxy_and_disabled_network(f12_tools, tmp_path):
    session, run_cli = f12_tools
    first, second = F12Proxy(tmp_path / "first"), F12Proxy(tmp_path / "second")
    for proxy, number in ((first, 19), (second, 43)):
        proxy.publish("remote.test/tool", "v1.2.0", {
            "main.go": f'package main\nfunc main() {{ println("selected", {number}) }}\n',
        })
        proxy.publish("remote.test/library", "v1.0.0", {
            "value.go": f'package library\nfunc Value() int {{ return {number} }}\n',
        })
    with first.serving(), second.serving():
        # The client observes the default destination but forwards real HTTP
        # to the local service, so the test needs no public network access.
        with session(redirect=first.url) as command:
            value = f12_evaluate(command, "remote.test/library", "library.Value()")
            f01_value(value, "int", 19)
            assert value["urls"], value
            assert all((urlsplit(url).scheme, urlsplit(url).netloc) ==
                       ("https", "proxy.golang.org") for url in value["urls"]), value

        for proxy, expected in ((first, b"selected 19\n"), (second, b"selected 43\n")):
            result = run_cli(proxy.url, "remote.test/tool")
            assert result.returncode == 0, result
            assert result.stdout == expected, result
            f12_downloaded(proxy, "remote.test/tool", "v1.2.0")

        for separator in (",", "|"):
            second.requests.clear()
            result = run_cli(",|" + first.url + separator + second.url, "remote.test/tool")
            assert result.returncode == 0, result
            assert result.stdout == b"selected 19\n", result
            assert not second.requests, second.requests

        first.unavailable = True
        first.requests.clear()
        second.requests.clear()
        result = run_cli(first.url + "," + second.url, "remote.test/tool")
        assert result.returncode != 0, result
        assert result.stderr, result
        assert any(r["status"] == 503 for r in first.requests), first.requests
        assert not second.requests, second.requests
        first.unavailable = False

        # Baselines above prove both services and their source packages work.
        # Fresh CLI environments prohibit saved modules from masking retrieval.
        for mode in ("off", "direct"):
            first.requests.clear()
            second.requests.clear()
            result = run_cli(mode + "," + first.url + "," + second.url, "remote.test/tool")
            assert result.returncode != 0, result
            assert result.stderr, result
            assert not first.requests and not second.requests, (first.requests, second.requests)
        first.requests.clear()
        with session(first.url, offline=True) as command:
            f12_unavailable(f12_evaluate(command, "remote.test/library", "library.Value()"))
            assert not first.requests, first.requests
            assert command("read", Path="remote.test/library/value.go")["not_exist"] is True


def test_unavailable_import_and_recovery_in_same_resolver(f12_tools, tmp_path):
    session, _ = f12_tools
    proxy = F12Proxy(tmp_path / "proxy")
    source = "package calc\nfunc Compute(n int) int { return 11*n-4 }\n"
    proxy.publish("remote.test/recover", "v1.7.0", {"calc/calc.go": source})
    with proxy.serving(), session(proxy.url) as command:
        # A healthy resolver reports both an absent module and an absent package.
        f01_value(f12_evaluate(command, "remote.test/recover/calc", "calc.Compute(5)"), "int", 51)
        f12_unavailable(f12_evaluate(command, "remote.test/absent", "absent.Value()"))
        f12_unavailable(f12_evaluate(command, "remote.test/recover/missing", "missing.Value()"))
    # Keep this resolver alive across the outage. Interpreters are fresh so the
    # assertion does not add an interpreter-rollback promise to module retry.
    with proxy.serving(), session(proxy.url) as command:
        proxy.unavailable = True
        failed = command("read", Path="remote.test/recover/calc/calc.go")
        assert failed["error"] is not None and failed["not_exist"] is True, failed
        f12_unavailable(f12_evaluate(command, "remote.test/recover/calc", "calc.Compute(8)"))
        assert any(r["status"] == 503 for r in proxy.requests), proxy.requests
        proxy.unavailable = False
        restored = command("read", Path="remote.test/recover/calc/calc.go")
        f01_success([restored])
        assert restored["content"] == source
        directory = command("directory", Path="remote.test/recover/calc")
        f01_success([directory])
        assert "calc.go" in directory["entries"], directory
        f01_value(f12_evaluate(command, "remote.test/recover/calc", "calc.Compute(8)"), "int", 84)
