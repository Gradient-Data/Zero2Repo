# feature: F12
"""The five planned AOT acceptance entries, observed through real CLI runs."""
import struct

from F01_helpers import f01_driver
from F08_helpers import f08_driver
from F05_helpers import F05_WORK
from F11_helpers import (
    f11_driver, f11_values, f11_failure, f11_fuel_completion, f11_files_guest,
    F11_SCALARS, F11_CONTEXT, F11_IO, F11_MEMORY, F11_TABLE, F11_INITIAL_TABLES,
)
from F12_helpers import f12_compile, f12_artifact_variants, F12_STATE


def test_artifact_survives_source_removal_with_ordered_state_results(f11_driver, tmp_path):
    # F12.T01. Core arithmetic, memory and indirect calls give independent
    # semantic expectations; a source/artifact closed loop alone is insufficient.
    source = f11_driver.wasi.guest(F12_STATE)
    artifact = f12_compile(f11_driver, source, tmp_path / 'compiled.cwasm')
    # Start adds 5 to global 11 and 7 to memory 23. The indirect and direct
    # calls then add n + (n + 1) and 3*n + 3*(n + 1), respectively.
    # Each fresh instance must apply the start effects exactly once.
    vectors = [('evolve=7', [31, 75]), ('evolve=-4', [9, 9])]
    for invocation, expected in vectors:
        f11_values(f11_driver.command(['run', '--engine', 'jit', '--invoke', invocation, source]), expected)
    source.unlink()
    for invocation, expected in vectors:
        # Every command is a new OS process using the production executable.
        f11_values(f11_driver.command(['run', '--invoke', invocation, artifact]), expected)


def test_artifact_preserves_named_calls_wasi_context_io_and_files(f11_driver, tmp_path):
    # F12.T02. The equal basename makes argv[0] identical in both arms.
    mixed = '''(func (export "mixed") (param i32 i64 f32 f64) (result i64)
      local.get 0 i64.extend_i32_s local.get 1 i64.add
      local.get 2 i64.trunc_f32_s i64.add local.get 3 i64.trunc_f64_s i64.sub)'''
    source = f11_driver.wasi.guest(F11_SCALARS[:-1] + mixed + ')')
    artifact = f12_compile(f11_driver, source, tmp_path / source.name)
    vectors = [('int32=-13', [-18]), ('int64=4294967311', [4294967318]),
               ('float32=1.25', [('f32', '2.5')]), ('float64=-3.5', ['-3.375']),
               ('pair=-5,19', [38, -8]), ('mixed=19,1099511627783,3.5,-7.25', [1099511627812])]
    for invocation, expected in vectors:
        f11_values(f11_driver.command(['run', '--engine', 'jit', '--invoke', invocation, source]), expected)
    source.unlink()
    for invocation, expected in vectors:
        f11_values(f11_driver.command(['run', '--invoke', invocation, artifact]), expected)

    source = f11_driver.wasi.guest(F11_CONTEXT)
    artifact = f12_compile(f11_driver, source, tmp_path / source.name)
    args = ['', 'two words', '--literal', 'λ']
    env_options = ['--env', 'MODE=two words', '--env', 'EMPTY=', '--env', 'EQUAL=a=b']
    for path, engine in ((source, ['--engine', 'jit']), (artifact, [])):
        result = f11_driver.command(['run', *engine, *env_options, path, *args])
        assert result.returncode == 0, result.stderr
        assert result.stdout == b'\0'.join([source.name.encode(), *(a.encode() for a in args)]) + b'\0'
        assert result.stderr.endswith(b'\0'), result.stderr
        assert sorted(result.stderr[:-1].split(b'\0')) == [b'EMPTY=', b'EQUAL=a=b', b'MODE=two words']
        if path == source:
            source.unlink()

    source = f11_driver.wasi.guest(F11_IO)
    artifact = f12_compile(f11_driver, source, tmp_path / source.name)
    for path, engine in ((source, ['--engine', 'jit']), (artifact, [])):
        for payload in (b'', b'first\x00\xff\nsecond\r\n'):
            result = f11_driver.command(['run', *engine, path], stdin=payload)
            assert result.returncode == 23, (result.returncode, result.stderr)
            assert result.stdout == payload
            assert result.stderr == b'\x7f' + payload
        if path == source:
            source.unlink()

    payload = b'file\x00payload\xff\n'
    source = f11_driver.wasi.guest(f11_files_guest(len(payload)))
    artifact = f12_compile(f11_driver, source, tmp_path / source.name)
    folder = tmp_path / 'host'
    folder.mkdir()
    second = tmp_path / 'second'
    second.mkdir()
    for path, engine in ((source, ['--engine', 'jit']), (artifact, [])):
        # Reconstruct the same initial host state at the same granted path.
        (folder / 'input.bin').write_bytes(payload)
        assert not (folder / 'output.bin').exists()
        result = f11_driver.command(['run', *engine, '--invoke', 'run',
                                    '--dir', str(folder) + ':/granted',
                                    '--dir', str(second) + ':/second', path])
        assert result.returncode == 0, result.stderr
        assert result.stdout == struct.pack('<II', 2, 8)
        assert (folder / 'input.bin').read_bytes() == payload
        assert (folder / 'output.bin').read_bytes() == payload
        (folder / 'output.bin').unlink()
        (folder / 'input.bin').unlink()
        if path == source:
            source.unlink()


def test_artifact_preserves_execution_limits_and_fuel_outcomes(f11_driver, tmp_path):
    # F12.T03. Compare completion/exhaustion without fixing a fuel-cost model.
    source = f11_driver.wasi.guest(F05_WORK)
    artifact = f12_compile(f11_driver, source, tmp_path / source.name)
    options = ['--engine', 'jit', '--invoke', 'work=200']
    high, completed = f11_fuel_completion(f11_driver, source, options)
    f11_values(completed, [20100])

    def compare(budget):
        observations = []
        for path in (source, artifact):
            result = f11_driver.command(['run', *options, '--fuel', str(budget), path])
            if result.returncode == 0:
                f11_values(result, [20100])
            else:
                f11_failure(result, trap='out_of_fuel')
            observations.append(result.returncode)
        assert observations[0] == observations[1], (budget, observations)
        return observations[0] == 0

    assert not compare(0)
    assert compare(high)
    # Locate the completion boundary without pinning either charging units
    # or the reference's chosen amount. Every search probe checks both arms.
    low = 0
    while high - low > 1:
        middle = (low + high) // 2
        if compare(middle):
            high = middle
        else:
            low = middle
    assert not compare(low)
    assert compare(high)
    assert compare(2 * high)
    for path in (source, artifact):
        f11_values(f11_driver.command(['run', *options, '--timeout', '10000', path]), [20100])
        for control, value, kind in (('--fuel', '100', 'out_of_fuel'),
                                     ('--timeout', '20', 'interrupted')):
            f11_failure(f11_driver.command(['run', '--engine', 'jit', '--invoke', 'spin',
                                           control, value, path]), trap=kind)

    for guest, flag, cases in (
        (F11_MEMORY, '--max-memory', [(None, [2, 4]), (3 * 65536, [-1, 2]), (4 * 65536, [2, 4])]),
        (F11_TABLE, '--max-table-elements', [(None, [2, 4]), (3, [-1, 2]), (4, [2, 4])]),
    ):
        source = f11_driver.wasi.guest(guest)
        artifact = f12_compile(f11_driver, source, tmp_path / source.name)
        for path in (source, artifact):
            for limit, expected in cases:
                extra = [] if limit is None else [flag, str(limit)]
                f11_values(f11_driver.command(['run', '--engine', 'jit', '--invoke', 'grow', *extra, path]), expected)
    source = f11_driver.wasi.guest(F11_INITIAL_TABLES)
    artifact = f12_compile(f11_driver, source, tmp_path / source.name)
    for path in (source, artifact):
        f11_values(f11_driver.command(['run', '--engine', 'jit', '--max-table-elements', '7', path]), [71])
        f11_failure(f11_driver.command(['run', '--engine', 'jit', '--max-table-elements', '6', path]))


def test_compile_and_artifact_input_failures(f11_driver, tmp_path):
    # F12.T04. Shell-envelope mutations never decode or alter machine code.
    source = f11_driver.wasi.guest(F12_STATE)
    artifact = f12_compile(f11_driver, source, tmp_path / 'valid.cwasm')
    f11_values(f11_driver.command(['run', '--invoke', 'evolve=7', artifact]), [31, 75])
    missing = tmp_path / 'missing.wasm'
    assert not missing.exists()
    f11_failure(f11_driver.command(['compile', missing, '-o', tmp_path / 'missing.cwasm']))
    # A directory is an unwritable file destination even when run as root.
    f11_failure(f11_driver.command(['compile', source, '-o', tmp_path]))
    invalid = tmp_path / 'invalid.wasm'
    # Both a truncated binary and a well-formed but ill-typed Core module.
    for data in (b'\x00asm\x01\x00\x00\x00\x01\x05\x01',
                 f11_driver.wasi.compiler.wat('(module (func (result i32) f64.const 1))')):
        invalid.write_bytes(data)
        f11_failure(f11_driver.command(['compile', invalid, '-o', tmp_path / 'invalid.cwasm']))
    for kind, data in f12_artifact_variants(artifact.read_bytes()).items():
        path = tmp_path / (kind + '.cwasm')
        path.write_bytes(data)
        f11_failure(f11_driver.command(['run', '--invoke', 'evolve=7', path]))


def test_artifact_rejects_forced_interpreter(f11_driver, tmp_path):
    # F12.T05. The same live artifact and invocation differ only in mode.
    source = f11_driver.wasi.guest(F12_STATE)
    artifact = f12_compile(f11_driver, source, tmp_path / 'program.cwasm')
    source.unlink()
    f11_values(f11_driver.command(['run', '--engine', 'jit', '--invoke', 'evolve=-4', artifact]), [9, 9])
    f11_failure(f11_driver.command(['run', '--engine', 'interp', '--invoke', 'evolve=-4', artifact]), status=2)
