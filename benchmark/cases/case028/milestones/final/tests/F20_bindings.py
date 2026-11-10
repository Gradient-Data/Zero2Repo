# feature: F20
"""Public native binding generation, resolution, discovery and diagnostics."""

from _helpers import parse_json, read_bytes, run_process, write_files
from F02_helpers import F02_CAPTURE
from F20_helpers import (
    F20_MAP_OBSERVER, F20_MEMBERS, F20_NATIVE, f20_projects,
)


def test_generated_bindings_preserve_native_behavior(f20_projects):
    project = f20_projects({'odd-path/native.go': F20_NATIVE})
    project.generate(['binding.test/check/odd-path'], 'consumer/bindings.go')
    observed = project.observe('consumer', r'''package main
import ("encoding/json"; "os"; "reflect";
"binding.test/check/odd-path";
"github.com/zelviro-sh/zelviro/interp"; "github.com/zelviro-sh/zelviro/lang/golang")
''' + F02_CAPTURE + r'''
func main() {
    bindings := nativeValues["binding.test/check/odd-path"]
    // Compare complete reflect.Type objects with the actual native package.
    originals := map[string]any{
        "Level": native.Level, "Greeting": native.Greeting, "Large": uint64(native.Large),
        "Text": &native.Text, "Current": &native.Current,
        "Measure": (*native.Measure)(nil), "Parcel": (*native.Parcel)(nil),
        "Pair": native.Pair, "Sum": native.Sum, "Rename": native.Rename, "Echo": native.Echo,
    }
    if len(bindings) != len(originals) { panic("wrong export membership") }
    for name, original := range originals {
        v, ok := bindings[name]
        if !ok || !v.IsValid() || v.Type() != reflect.TypeOf(original) {
            panic("native type or signature lost: " + name)
        }
    }
    for _, name := range []string{"Level", "Greeting", "Large", "Text", "Current"} {
        if bindings[name].Interface() != originals[name] { panic("native value or storage lost: " + name) }
    }
    engine := interp.NewInterpreter(golang.GoSpec)
    defer engine.Close()
    engine.ImportPackageValues(nativeValues)
    eval := func(source string) reflect.Value {
        v, err := engine.Eval("binding.go", source)
        if err != nil { panic(err) }; return v
    }
    eval(`import native "binding.test/check/odd-path"`)
    values := []scalar{}
    values = append(values, capture(eval(`native.Text`)))
    values = append(values, capture(eval(`native.Greeting`)))
    values = append(values, capture(eval(`native.Level`)))
    values = append(values, capture(eval(`native.Large`)))
    p := eval(`native.Echo(native.Parcel{Count: 9, Label: "local"})`)
    if p.Type() != reflect.TypeOf(native.Parcel{}) { panic("interpreted native type identity lost") }
    values = append(values, capture(p))
    eval(`s, n := native.Pair(7, "go"); native.Text = s; native.Current.Count += 4`)
    values = append(values, capture(eval(`n`)), capture(reflect.ValueOf(native.Text)), capture(reflect.ValueOf(native.Current.Count)))
    native.Text = "host-update"
    native.Current.Label = "host-side"
    values = append(values, capture(eval(`native.Text`)), capture(eval(`native.Current.Label`)))
    values = append(values, capture(eval(`native.Sum(5, 2, -4, 9)`)), capture(eval(`native.Sum(5)`)))
    eval(`native.Rename(&native.Current, "shared")`)
    values = append(values, capture(reflect.ValueOf(native.Current)))
    emit(values)
}
''')
    assert observed == [
        {'Type': kind, 'Value': value} for kind, value in [
            ('string', 'initial'), ('string', 'cedar'), ('native.Measure', 37),
            ('uint64', 14514072000185962306),
            ('native.Parcel', {'Count': 9, 'Label': 'local'}),
            ('int', 21), ('string', 'gogo'), ('int', 7),
            ('string', 'host-update'), ('string', 'host-side'), ('int', 12), ('int', 5),
            ('native.Parcel', {'Count': 8, 'Label': 'shared'}),
        ]
    ]


def test_selection_identity_and_output_options(f20_projects):
    project = f20_projects({
        'versioned/v2/native.go': 'package native // declared name differs from directory\nconst Message = "birch"\n',
        'versioned/v2/generate.go': '//go:build ignore\n\npackage main\nfunc main() {}\n',
    })
    identity = 'binding.test/check/versioned/v2'
    selections = [
        ([identity], project.root),
        (['./versioned/v2'], project.root),
        (['.'], project.root / 'versioned/v2'),
        ([identity, str(project.root / 'versioned/v2')], project.workspace.root),
    ]
    for index, (arguments, cwd) in enumerate(selections):
        directory = f'consumer{index}'
        output = project.root / directory / 'bindings.go'
        output.parent.mkdir()
        process = project.extract(['-o', str(output), '-pkg', 'bridge', *arguments], cwd=cwd)
        assert process.returncode == 0, process
        assert read_bytes(output), process
        # The generated package is imported by a separate native consumer.
        write_files(project.root, {directory + '/export.go': '''package bridge
import "reflect"
func Values() map[string]map[string]reflect.Value { return nativeValues }
'''})
        observed = project.observe(f'runner{index}', '''package main
import ("encoding/json"; "os"; "github.com/zelviro-sh/zelviro/interp";
"github.com/zelviro-sh/zelviro/lang/golang"; "binding.test/check/''' + directory + '''")
func main() {
    values := bridge.Values()
    if len(values) != 1 || len(values["''' + identity + '''"]) != 1 { panic("incorrect package identity") }
    engine := interp.NewInterpreter(golang.GoSpec); defer engine.Close()
    engine.ImportPackageValues(values)
    if _, err := engine.Eval("import.go", `import native "''' + identity + '''"`); err != nil { panic(err) }
    v, err := engine.Eval("use.go", "native.Message"); if err != nil { panic(err) }
    if err := json.NewEncoder(os.Stdout).Encode(v.Interface()); err != nil { panic(err) }
}
''')
        assert observed == 'birch'


def test_export_filtering_targets_and_empty_bindings(f20_projects):
    project = f20_projects({
        'native/base.go': 'package native\nconst Common = "base"\nvar hidden = 1\nfunc Identity[T any](x T) T { return x }\ntype Box[T any] struct { Value T }\n',
        'native/os_linux.go': 'package native\nconst Linux = "linux"\n',
        'native/os_windows.go': 'package native\nconst Windows = "windows"\n',
        'native/arch_amd64.go': 'package native\nconst AMD64 = "amd64"\n',
        'native/arch_arm64.go': 'package native\nconst ARM64 = "arm64"\n',
        'native/constraint.go': '//go:build linux && arm64\n\npackage native\nconst Constrained = "selected"\n',
        'native/ignored.go': '//go:build ignore\n\npackage native\nconst Ignored = "excluded"\n',
        'empty/native.go': 'package native\nvar hidden = 1\nfunc Identity[T any](x T) T { return x }\ntype Box[T any] struct { Value T }\n',
    })
    # Three targets separate OS, architecture, and their build-expression interaction.
    targets = [
        ('linux', 'amd64', {'Common', 'Linux', 'AMD64'}),
        ('linux', 'arm64', {'Common', 'Linux', 'ARM64', 'Constrained'}),
        ('windows', 'amd64', {'Common', 'Windows', 'AMD64'}),
    ]
    for index, (os_name, arch, names) in enumerate(targets):
        options = ['-goos', os_name, '-goarch', arch]
        assert project.inventory([*options, 'native']) == {('const', name) for name in names}
        project.generate([*options, 'binding.test/check/native'], f'target{index}/bindings.go')
        project.observe(f'target{index}', F20_MAP_OBSERVER, target=(os_name, arch))
    # Also execute host-selected bindings, rather than relying on compilation alone.
    project.generate(['binding.test/check/native'], 'host/bindings.go')
    observed = project.observe('host', F20_MAP_OBSERVER)
    # Host values are selected independently by Go's toolchain environment.
    environment = run_process(['go', 'env', '-json', 'GOOS', 'GOARCH'], cwd=project.root,
                              env=project.workspace.env, timeout=30)
    assert environment.returncode == 0, environment
    target = parse_json(environment.stdout)
    expected = {'Common'}
    expected.update({'linux': {'Linux'}, 'windows': {'Windows'}}.get(target['GOOS'], set()))
    expected.update({'amd64': {'AMD64'}, 'arm64': {'ARM64'}}.get(target['GOARCH'], set()))
    if (target['GOOS'], target['GOARCH']) == ('linux', 'arm64'):
        expected.add('Constrained')
    assert observed == {'binding.test/check/native': sorted(expected)}
    assert project.inventory(['empty']) == set()
    project.generate(['binding.test/check/empty'], 'emptyconsumer/bindings.go')
    assert project.observe('emptyconsumer', F20_MAP_OBSERVER) == {'binding.test/check/empty': []}


def test_inventory_and_selection_output_failures(f20_projects):
    project = f20_projects({'odd-path/native.go': F20_NATIVE,
                           'second/native.go': 'package second\nconst Other = 4\n'})
    assert project.inventory(['odd-path']) == F20_MEMBERS
    project.generate(['binding.test/check/odd-path'], 'consumer/bindings.go')
    assert project.observe('consumer', F20_MAP_OBSERVER) == {
        'binding.test/check/odd-path': sorted(name for _, name in F20_MEMBERS),
    }
    output = project.root / 'inventory.txt'
    process = project.extract(['-list', '-o', str(output), 'odd-path'])
    assert process.returncode == 0, process
    records = [tuple(line.split()) for line in read_bytes(output).decode().splitlines()]
    assert len(records) == len(F20_MEMBERS) and set(records) == F20_MEMBERS
    # Use a real unwritable destination, not permissions that root could bypass.
    blocked = project.root / 'output-directory'
    blocked.mkdir()
    for arguments, subject in [
        ([], None),
        (['./...'], './...'),
        (['binding.test/check/absent'], 'binding.test/check/absent'),
        (['-o', str(blocked), 'binding.test/check/odd-path'], str(blocked)),
    ]:
        result = project.extract(arguments)
        assert result.returncode == 1, result
        errors = [line.removeprefix('error: ') for line in result.stderr.decode().splitlines()
                  if line.startswith('error: ')]
        assert len(errors) == 1 and errors[0].strip(), result
        if subject is not None:
            assert subject in errors[0], result
