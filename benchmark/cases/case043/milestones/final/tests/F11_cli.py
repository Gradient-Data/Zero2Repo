# feature: F11
"""Six planned CLI acceptance entries, with external process observations."""
import struct

from _helpers import run_process
from F01_helpers import f01_driver
from F08_helpers import f08_driver
from F05_helpers import F05_WORK
from F11_helpers import (
    f11_driver, f11_values, f11_failure, f11_identity, f11_files_guest,
    f11_fuel_completion, F11_SCALARS, F11_CONTEXT, F11_IO,
    F11_MEMORY, F11_TABLE, F11_INITIAL_TABLES, F11_SIMD,
)


def test_default_entry_selection_and_exit_status(f11_driver):
    # F11.T01. Values are Core scalar constants, not process exit requests.
    both = '''(module
      (func (export "main") (result i32) i32.const 27)
      (func (export "_start") (result i32) i32.const -19)
      (func (export "chosen") (result i32) i32.const 83))'''
    main = '(module (func (export "main") (result i32) i32.const 27))'
    for mode in ('interp', 'jit'):
        options = ['--engine', mode]
        path = f11_driver.wasi.guest(both)
        f11_values(f11_driver.command(['run', *options, path]), [-19])
        f11_values(f11_driver.command(['run', *options, '--invoke', 'main', path]), [27])
        f11_values(f11_driver.command(['run', *options, '--invoke', 'chosen', path]), [83])
        _, result = f11_driver.run(main, options=options)
        f11_values(result, [27])
        for status in (0, 37, 197):
            termination = f'''(module
              (import "wasi_snapshot_preview1" "proc_exit" (func $exit (param i32)))
              (func (export "_start") i32.const {status} call $exit unreachable))'''
            _, result = f11_driver.run(termination, options=options)
            assert result.returncode == status, result.stderr
            assert result.stdout == b'' and result.stderr == b'', result


def test_declared_scalar_arguments_and_ordered_results(f11_driver):
    # F11.T02. Exactly representable operands avoid implementation-specific
    # decimal rounding; the signed and wide integers expose wrong carriers.
    vectors = [
        ('int32=-13', [-18]), ('int32=2147483647', [2147483642]),
        ('int64=4294967311', [4294967318]), ('int64=-4294967321', [-4294967314]),
        ('int64=9007199254740994', [9007199254741001]),
        ('float32=1.25', [('f32', '2.5')]), ('float32=-6.25e-1', [('f32', '-1.25')]),
        ('float64=-3.5', ['-3.375']), ('float64=1.00000000023283064365386962890625',
                                         ['1.12500000023283064365386962890625']),
        ('pair=13,-7', [-14, 10]), ('pair=-5,19', [38, -8]), ('nothing', []),
    ]
    path = f11_driver.wasi.guest(F11_SCALARS)
    for mode in ('interp', 'jit'):
        for invoke, values in vectors:
            f11_values(f11_driver.command(['run', '--engine', mode, '--invoke', invoke, path]), values)
        ordered = f11_driver.wasi.guest('''(module
          (func (export "ordered") (result i32 i32 i32)
            i32.const 11 i32.const 11 i32.const 3 i32.add
            i32.const 11 i32.const 5 i32.mul))''')
        f11_values(f11_driver.command(['run', '--engine', mode, '--invoke', 'ordered', ordered]),
                   [11, 14, 55])
    # The reference supports mixed four-result signatures on the interpreter.
    # Other supported result shapes above exercise both selected modes.
    f11_values(f11_driver.command(['run', '--engine', 'interp', '--invoke',
                                  'mix=-13,4294967311,1.25,-3.5', path]),
               ['-3.375', -18, ('f32', '2.5'), 4294967318])


def test_cli_refusals_and_usage_vs_guest_failure(f11_driver):
    # F11.T03. Missing uniform error categories are an explicit plan request;
    # status/channel, empty results and the published trap field are readable.
    only_named = '(module (func (export "chosen") (result i32) i32.const 67))'
    shape = '''(module
      (func (export "_start") (param i32))
      (func (export "main") (result i32) i32.const 29))'''
    scalar_path = f11_driver.wasi.guest(F11_SCALARS)
    for mode in ('interp', 'jit'):
        options = ['--engine', mode]
        path = f11_driver.wasi.guest(only_named)
        f11_values(f11_driver.command(['run', *options, '--invoke', 'chosen', path]), [67])
        f11_failure(f11_driver.command(['run', *options, path]))
        path = f11_driver.wasi.guest(shape)
        f11_values(f11_driver.command(['run', *options, '--invoke', 'main', path]), [29])
        f11_failure(f11_driver.command(['run', *options, path]))
        main_with_argument = f11_driver.wasi.guest('''(module
          (func (export "main") (param i32) (result i32)
            local.get 0 i32.const 2 i32.mul))''')
        f11_values(f11_driver.command(['run', *options, '--invoke', 'main=7', main_with_argument]), [14])
        f11_failure(f11_driver.command(['run', *options, main_with_argument]))
        f11_values(f11_driver.command(['run', *options, '--invoke', 'int32=19', scalar_path]), [14])
        for invocation in ('absent', 'int32', 'int32=1,2', 'int32=not-an-int',
                           'int64=not-an-int', 'float32=not-a-float', 'float64=not-a-float',
                           'int32=4294967296', 'int32=-2147483649'):
            f11_failure(f11_driver.command(['run', *options, '--invoke', invocation, scalar_path]))
        _, result = f11_driver.run('(module (func (export "main") unreachable))', options=options)
        f11_failure(result, trap='unreachable_')
        missing = f11_driver.directory / 'uncreated.wasm'
        assert not missing.exists()
        f11_failure(f11_driver.command(['run', *options, missing]))
        invalid = f11_driver.directory / 'invalid.wasm'
        invalid.write_bytes(b'not a WebAssembly module')
        f11_failure(f11_driver.command(['run', *options, invalid]))
    for request in (['not-a-command'], ['run'], ['run', '--engine', 'unknown', scalar_path],
                    ['run', '--fuel', 'not-a-number', scalar_path], ['run', '--invoke']):
        f11_failure(f11_driver.command(request), status=2)


def test_cli_wasi_configuration_io_and_directory_effects(f11_driver, tmp_path):
    # F11.T04. These are real WASI imports, pipes and granted host files.
    context = f11_driver.wasi.guest(F11_CONTEXT)
    for mode in ('interp', 'jit'):
        options = ['--engine', mode]
        baseline = f11_driver.command(['run', *options, context])
        assert baseline.returncode == 0, baseline.stderr
        assert baseline.stdout == context.name.encode() + b'\0'
        assert baseline.stderr == b''
        args = ['', 'two words', '--literal', 'λ']
        result = f11_driver.command(['run', *options, '--env', 'MODE=two words',
                                    '--env', 'EMPTY=', '--env', 'EQUAL=a=b', context, *args])
        assert result.returncode == 0, result.stderr
        assert result.stdout == b'\0'.join([context.name.encode(), *(x.encode() for x in args)]) + b'\0'
        assert result.stderr.endswith(b'\0'), result.stderr
        assert sorted(result.stderr[:-1].split(b'\0')) == [b'EMPTY=', b'EQUAL=a=b', b'MODE=two words']
        named = f11_driver.command(['run', *options, '--invoke', '_start', context, *args])
        assert named.returncode == 0, named.stderr
        assert named.stdout == b'\0'.join([context.name.encode(), *(x.encode() for x in args)]) + b'\0'
        assert named.stderr == b''
        payload = b'first\x00\xff\nsecond\r\n'
        for stdin in (b'', payload):
            _, result = f11_driver.run(F11_IO, options=options, stdin=stdin)
            assert result.returncode == 23, (result.returncode, result.stderr)
            assert result.stdout == stdin and result.stderr == b'\x7f' + stdin, result
        folder = tmp_path / mode
        folder.mkdir()
        original = b'file\x00payload\xff\n'
        (folder / 'input.bin').write_bytes(original)
        guest = f11_driver.wasi.guest(f11_files_guest(len(original)))
        baseline = f11_driver.command(['run', *options, '--invoke', 'run', guest])
        assert baseline.returncode == 0, baseline.stderr
        assert baseline.stdout == struct.pack('<II', 0, 8)
        assert sorted(x.name for x in folder.iterdir()) == ['input.bin']
        result = f11_driver.command(['run', *options, '--invoke', 'run',
                                    '--dir', str(folder) + ':/granted', guest])
        assert result.returncode == 0, result.stderr
        assert result.stdout == struct.pack('<II', 1, 8)
        assert (folder / 'input.bin').read_bytes() == original
        assert (folder / 'output.bin').read_bytes() == original


def test_cli_mode_selection_and_execution_limits(f11_driver):
    # F11.T05. A scalar-boundary SIMD result proves mode forwarding without
    # inspecting implementation techniques or accepting a printed mode claim.
    simd = f11_driver.wasi.guest(F11_SIMD)
    for mode in ('interp', 'jit'):
        f11_values(f11_driver.command(['run', '--engine', mode, '--invoke', 'scalar=-9', simd]), [-27])
    f11_values(f11_driver.command(['run', '--engine', 'jit', '--invoke', 'simd=-9', simd]), [2])
    f11_failure(f11_driver.command(['run', '--engine', 'interp', '--invoke', 'simd=-9', simd]))
    for options in ([], ['--engine', 'auto']):
        f11_values(f11_driver.command(['run', *options, '--invoke', 'scalar=7', simd]), [21])

    work = f11_driver.wasi.guest(F05_WORK)
    memory = f11_driver.wasi.guest(F11_MEMORY)
    for mode in ('interp', 'jit'):
        options = ['--engine', mode, '--invoke', 'work=200']
        f11_values(f11_driver.command(['run', *options, work]), [20100])
        budget, completed = f11_fuel_completion(f11_driver, work, options)
        f11_values(completed, [20100])
        f11_values(f11_driver.command(['run', *options, '--fuel', str(budget), work]), [20100])
        f11_values(f11_driver.command(['run', *options, '--fuel', str(2*budget), work]), [20100])
        f11_failure(f11_driver.command(['run', *options, '--fuel', '0', work]), trap='out_of_fuel')
        f11_failure(f11_driver.command(['run', '--engine', mode, '--invoke', 'spin',
                                       '--fuel', '100', work]), trap='out_of_fuel')
        f11_values(f11_driver.command(['run', *options, '--timeout', '10000', work]), [20100])
        f11_failure(f11_driver.command(['run', '--engine', mode, '--invoke', 'spin',
                                       '--timeout', '20', work]), trap='interrupted')
        for limit, expected in ((None, [2, 4]), (3*65536, [-1, 2]), (4*65536, [2, 4])):
            extra = [] if limit is None else ['--max-memory', str(limit)]
            f11_values(f11_driver.command(['run', '--engine', mode, '--invoke', 'grow', *extra, memory]), expected)
    table = f11_driver.wasi.guest(F11_TABLE)
    for limit, expected in ((None, [2, 4]), (3, [-1, 2]), (4, [2, 4])):
        extra = [] if limit is None else ['--max-table-elements', str(limit)]
        f11_values(f11_driver.command(['run', '--engine', 'jit', '--invoke', 'grow', *extra, table]), expected)
    tables = f11_driver.wasi.guest(F11_INITIAL_TABLES)
    f11_values(f11_driver.command(['run', '--engine', 'jit', '--max-table-elements', '7', tables]), [71])
    f11_failure(f11_driver.command(['run', '--engine', 'jit', '--max-table-elements', '6', tables]))


def test_help_and_cli_library_build_identity(f11_driver):
    # F11.T06. Preserve the planned function identity; help prose and layout
    # are outside this feature's promised build-identity behavior.
    versions = []
    configs = [dict(wasm='v3_0', wasi='p3', engine='both', optimize='ReleaseSafe'),
               dict(wasm='v1_0', wasi='none', engine='interp', optimize='ReleaseFast')]
    for config in configs:
        cli, library_query = f11_driver.build(**config)
        identity = f11_identity(f11_driver.command(['--version'], cli=cli))
        assert identity[1:] == tuple(config.values()), identity
        release = identity[0]
        versions.append(release)
        # Build mode is a field of the version request; the no-command banner
        # carries the release and enabled capability levels.
        assert f11_identity(f11_driver.command(cli=cli), banner=True) == identity[:4]
        queried = run_process([library_query])
        assert queried.returncode == 0, queried.stderr
        assert queried.stdout == release.encode() + b'\n'
    assert versions[0] == versions[1]
