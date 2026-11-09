# feature: F15
"""Command execution through local files, scripts, inline input and packages."""

import re

from _helpers import parse_json
from F12_helpers import F12Proxy
from F14_helpers import f14_diagnostic
from F15_helpers import f10_cli, f15_run, f15_output


def test_local_files_shared_declarations_and_arguments(f15_run):
    single = '''package main
import ("encoding/json"; "os")
func main() {
    if err := json.NewEncoder(os.Stdout).Encode(os.Args[1:]); err != nil { panic(err) }
}
'''
    arguments = ["zeta", "two words", "", "-flag", "alpha", "雪"]
    result = f15_run(["run", "single.go", *arguments], files={"single.go": single})
    assert result.returncode == 0, result
    assert parse_json(result.stdout) == arguments, result

    files = {
        "entry.go": '''package main
import ("encoding/json"; "os")
func main() {
    result := map[string]any{"value": compute(seed), "arguments": os.Args[1:]}
    if err := json.NewEncoder(os.Stdout).Encode(result); err != nil { panic(err) }
}
''',
        "data.go": "package main\nvar seed = 13\n",
        "operation.go": "package main\nfunc compute(n int) int { return n*7-2 }\n",
    }
    # Both permutations require declarations from every supplied file.
    for names in (("entry.go", "data.go", "operation.go"),
                  ("operation.go", "data.go", "entry.go")):
        result = f15_run(["run", *names, *arguments], files=files)
        assert result.returncode == 0, result
        assert parse_json(result.stdout) == {"value": 89, "arguments": arguments}, result


def test_scripts_optional_wrappers_and_initialization(f15_run):
    # Each wrapper combination is a separate promised accepted source form.
    # Shebang coverage is combined with those forms without a second matrix.
    for package, main, shebang in ((True, True, True), (False, True, False),
                                   (True, False, False), (False, False, True)):
        source = "#!/usr/bin/env zelviro\n" if shebang else ""
        if package:
            source += "package main\n"
        source += '''var state = seed()
func seed() int { println("seed"); return 4 }
'''
        body = 'println("first", state); state *= 3; println("second", state)'
        if main:
            source += 'func init() { state += 6; println("init", state) }\n'
            source += "func main() { " + body + " }\n"
        else:
            # The original contradicts its docs about init versus top-level
            # statement ordering. That obligation remains unresolved in the
            # ledger. Measure execution of both, without requiring either order
            # or treating the original's reversed order as the specification.
            source += 'var initialized int\n'
            source += 'func init() { initialized = 17; println("init", initialized) }\n'
            source += body + "\n"
        result = f15_run(["run", "script"], files={"script": source})
        if main:
            f15_output(result, b"seed\ninit 10\nfirst 10\nsecond 30\n")
        else:
            assert result.returncode == 0, result
            lines = result.stdout.splitlines()
            assert sorted(lines) == sorted([b"seed", b"init 17", b"first 4", b"second 12"]), result
            assert lines.index(b"seed") < lines.index(b"first 4") < lines.index(b"second 12"), result
            assert lines.index(b"seed") < lines.index(b"init 17"), result


def test_inline_single_value_and_no_extra_display(f15_run):
    # Every suppression arm has an executed side effect, not just empty output.
    cases = [
        ("7*8-3", b"53\n"),
        ('len("seasons")', b"7\n"),
        ('n:=9; println("effect", n); n+5', b"effect 9\n14\n"),
        ('func mark() int { println("declaration"); return 17 }; var n=mark()',
         b"declaration\n"),
        ('func mark() int { println("definition"); return 19 }; n:=mark()',
         b"definition\n"),
        ('n:=2; println("assignment", n); n=8', b"assignment 2\n"),
        ('f:=func(){println("void")}; f()', b"void\n"),
        ('func pair()(int,int){println("pair");return 3,8}; pair()', b"pair\n"),
        ('fmt.Println("formatted")', b"formatted\n"),
    ]
    for source, expected in cases:
        f15_output(f15_run(["run", "-e", source]), expected)


def test_import_path_entry_arguments_and_no_main_report(f15_run, tmp_path):
    proxy = F12Proxy(tmp_path / "proxy")
    proxy.publish("launch.test/program", "v1.0.0", {
        "cmd/main.go": '''package main
import ("encoding/json"; "os")
var value = 5
func init() { value *= 7 }
func main() {
    if err := json.NewEncoder(os.Stdout).Encode(map[string]any{
        "value": value+4, "arguments": os.Args[1:],
    }); err != nil { panic(err) }
}
''',
        "initonly/init.go": '''package main
var value = 9
func init() { value += 14; println("initialized", value) }
''',
    })
    with proxy.serving():
        arguments = ["omega", "two words", "", "-option", "beta"]
        result = f15_run(["run", "launch.test/program/cmd", *arguments], proxy=proxy.url)
        assert result.returncode == 0, result
        assert parse_json(result.stdout) == {"value": 39, "arguments": arguments}, result
        # A program whose entry function ran carries no no-entry report.
        assert not any(line.startswith(b"zelviro run: launch.test/program/cmd ")
                       for line in result.stderr.splitlines()), result
        target = "launch.test/program/initonly"
        result = f15_run(["run", target], proxy=proxy.url)
        f15_output(result, b"initialized 23\n")
        # The original has a labeled, target-bearing stderr report, not JSON
        # events. Read that carrier without requiring its explanatory prose.
        prefix = b"zelviro run: " + target.encode() + b" "
        reports = [line[len(prefix):] for line in result.stderr.splitlines()
                   if line.startswith(prefix)]
        assert len(reports) == 1 and reports[0].strip(), result


def test_command_failures_and_requested_exit_status(f15_run):
    f15_output(f15_run(["run", "healthy.go"], files={
        "healthy.go": 'package main\nfunc main(){println("healthy")}\n',
    }), b"healthy\n")
    rejected = [
        (["run", "missing.go"], {}, ()),
        (["run", "denied.go"], {"denied.go": 'println("must not execute")'}, ("denied.go",)),
        (["run", "invalid.go"], {"invalid.go": "package main\nfunc main(){ absent() }\n"}, ()),
        (["run", "syntax.go"], {"syntax.go": "package main\nfunc main( {\n"}, ()),
        (["run", "imports.go"], {"imports.go": 'package main\nimport "absent.test/module"\n'
          'func main(){module.Run()}\n'}, ()),
    ]
    for arguments, files, unreadable in rejected:
        result = f15_run(arguments, files=files, unreadable=unreadable)
        assert result.returncode == 1, result
        assert result.stderr.strip(), result

    result = f15_run(["run", "panic.go"], files={
        "panic.go": 'package main\nfunc main(){println("entered");panic("execution-stopped")}\n',
    })
    assert result.returncode == 1, result
    assert result.stdout == b"entered\n", result
    diagnostic = f14_diagnostic(result.stderr.decode())
    assert diagnostic["cause"] == "execution-stopped", diagnostic

    for status in (0, 7, 29):
        source = ('package main\nimport "os"\nfunc main(){println("before exit");'
                  f'os.Exit({status});println("after exit")' + '}\n')
        result = f15_run(["run", "exit.go"], files={"exit.go": source})
        assert result.returncode == status, result
        assert result.stdout == b"before exit\n", result


def test_execution_mode_precedence_and_interactive_default(f15_run, tmp_path):
    proxy = F12Proxy(tmp_path / "proxy")
    target = "choice.test/launch"
    proxy.publish(target, "v1.0.0", {
        "main.go": 'package main\nfunc main(){println("remote", 43)}\n',
    })
    local = {target: 'println("local", 31)\n'}
    with proxy.serving():
        # Each invocation has fresh caches and files. The remote control proves
        # that the competing interpretation is both resolvable and executable.
        f15_output(f15_run([target], proxy=proxy.url), b"remote 43\n")
        assert any(r["status"] == 200 for r in proxy.requests), proxy.requests
        proxy.requests.clear()
        f15_output(f15_run([target], files=local, proxy=proxy.url), b"local 31\n")
        assert not proxy.requests, proxy.requests

        for entry in ([], ["run"]):
            for inline, expected in (("", b"local 31\n"), ('println("inline", 59)', b"inline 59\n")):
                result = f15_run([*entry, "-e", inline, target], files=local, proxy=proxy.url)
                f15_output(result, expected)
                assert not proxy.requests, proxy.requests

    # Both dispatch entries must open a working REPL, not just print a prompt.
    for entry in ([], ["run"]):
        result = f15_run(entry, input="6*9\n")
        assert result.returncode == 0, result
        match = re.fullmatch(rb"> : +(-?\d+)\n> ", result.stdout)
        assert match is not None, result
        assert int(match.group(1)) == 54, result
