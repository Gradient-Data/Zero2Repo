# feature: F20
"""Generate bindings, compile consumers, and observe the public maps and Eval."""

import json
from pathlib import Path

import pytest

from _helpers import build_go, isolated_workspace, parse_json, run_process, write_files


F20_NATIVE = '''package native

type Measure int64
const Level Measure = 37
const Greeting = "cedar"
const Large = 0xc96c5795d7870f42
var Text = "initial"
type Parcel struct { Count int; Label string }
var Current = Parcel{3, "first"}
func Pair(n int, s string) (string, int) { return s+s, n*3 }
func Sum(base int, xs ...int) int { for _, x := range xs { base += x }; return base }
func Rename(p *Parcel, s string) { p.Label = s; p.Count++ }
func Echo(p Parcel) Parcel { return p }
const hiddenConst = 6
var hiddenVar = 2
type hiddenType int
func hiddenFunc() {}
func Identity[T any](x T) T { return x }
type Box[T any] struct { Value T }
'''

F20_MEMBERS = {
    ('const', 'Level'), ('const', 'Greeting'), ('const', 'Large'),
    ('var', 'Text'), ('var', 'Current'), ('type', 'Measure'), ('type', 'Parcel'),
    ('func', 'Pair'), ('func', 'Sum'), ('func', 'Rename'), ('func', 'Echo'),
}


class F20Project:
    def __init__(self, workspace, root, extractor):
        self.workspace, self.root, self.extractor = workspace, root, extractor
        self.serial = 0

    def extract(self, arguments, *, cwd=None):
        return run_process([self.extractor, *arguments], cwd=cwd or self.root,
                           env=self.workspace.env, timeout=90)

    def generate(self, arguments, destination, *, cwd=None):
        result = self.extract(arguments, cwd=cwd)
        assert result.returncode == 0, result
        write_files(self.root, {destination: result.stdout})
        return result

    def inventory(self, arguments):
        result = self.extract(['-list', *arguments])
        assert result.returncode == 0, result
        records = []
        for line in result.stdout.decode().splitlines():
            fields = line.split()
            assert len(fields) == 2, (line, result)
            kind, name = fields
            assert kind in {'const', 'var', 'type', 'func'}, (line, result)
            records.append((kind, name))
        assert len(records) == len(set(records)), records
        return set(records)

    def observe(self, directory, source, *, target=None):
        self.serial += 1
        write_files(self.root, {f'{directory}/main.go': source})
        env = dict(self.workspace.env)
        if target:
            env.update(GOOS=target[0], GOARCH=target[1], CGO_ENABLED='0')
        binary = build_go(['go'], './' + directory, cwd=self.root,
                          output=self.root / f'observer-{self.serial}', env=env,
                          flags=['-buildvcs=false'], timeout=240).artifact
        if target:
            return binary  # Cross-build only; never claim a target binary ran.
        result = run_process([binary], cwd=self.root, env=env, timeout=45)
        assert result.returncode == 0, result
        return parse_json(result.stdout)


@pytest.fixture(scope='module')
def f20_projects():
    product = Path.cwd()
    with isolated_workspace(overrides={'GOPROXY': 'off', 'ZELVIRO_DEBUG': None,
                                       'ZELVIRO_TRACE': None}) as workspace:
        extractor = build_go(['go'], './cmd/extract', cwd=product,
                             output=workspace.root / 'extract', env=workspace.env,
                             flags=['-buildvcs=false'], timeout=240).artifact
        serial = 0

        def create(files):
            nonlocal serial
            serial += 1
            root = workspace.cwd / f'project-{serial}'
            write_files(root, {
                'go.mod': 'module binding.test/check\n\ngo 1.26\n'
                          'require github.com/zelviro-sh/zelviro v0.0.0\n'
                          f'replace github.com/zelviro-sh/zelviro => {json.dumps(str(product))}\n',
                **files,
            })
            return F20Project(workspace, root, extractor)

        yield create


F20_MAP_OBSERVER = '''package main
import ("encoding/json"; "os"; "sort")
func main() {
    result := map[string][]string{}
    for path, members := range nativeValues {
        names := []string{}
        for name := range members { names = append(names, name) }
        sort.Strings(names)
        result[path] = names
    }
    if err := json.NewEncoder(os.Stdout).Encode(result); err != nil { panic(err) }
}
'''
