# feature: F06
"""One acceptance function per planned F06 entry, through public C APIs.

Core arithmetic and state semantics follow the published WebAssembly Core
Specification. Mode queries are public outcomes, not evidence of a private
execution technique. Current execution evidence is recorded separately.
"""
from F06_helpers import (
    F06_CORE, F06_ENTITIES, f01_driver, f06_driver,
    f02_arg, f02_values, f06_check_mode,
)


def test_auto_selection_preserves_computation_and_each_host_entity(f06_driver):
    # The import-free input is independently checked against the MVP feature
    # set, so post-1.0 instructions cannot accidentally narrow the promise.
    calls = [('run', [f02_arg(0, x), f02_arg(0, y)], 1)
             for x, y in [(9, 5), (-7, -3)]]
    got = f06_driver.run(F06_CORE, calls, features='mvp')
    f06_check_mode(got, 1)
    assert got['calls'] == [f02_values((0, 76)), f02_values((0, 52))], got
    local_memory = f06_driver.run(F06_CORE.replace('(module','(module (memory 1)'), calls, features='mvp')
    f06_check_mode(local_memory, 1)
    assert local_memory['calls'] == [f02_values((0,76)),f02_values((0,52))], local_memory
    empty = f06_driver.run('(module)', features='mvp')
    f06_check_mode(empty, 1)

    # Each listed entity is the sole import in its module: a memory import
    # cannot conceal a broken selection rule for tables or globals.
    for kind, guest in F06_ENTITIES.items():
        got = f06_driver.run(guest, [('write', [f02_arg(0, 91)], 0)], action=kind)
        f06_check_mode(got, 2)
        assert got['calls'] == [f02_values()], got
        if kind == 'memory':
            assert got['initial_host'] == 11, got
            assert got['initial_guest'] == f02_values((0, 11)), got
            assert got['host_write'] == f02_values((0, 37)), got
            assert got['final_guest'] == f02_values((0, 91)), got
            assert got['final_host'] == 91, got
        elif kind == 'global':
            assert got['initial_host'] == f02_values((0, 7))['values'][0], got
            assert got['initial_guest'] == f02_values((0, 7)), got
            assert got['host_write'] == f02_values((0, -19)), got
            assert got['final_guest'] == f02_values((0, 91)), got
            assert got['final_host'] == f02_values((0, 91))['values'][0], got
        else:
            assert got['initial_host'] == {'first': False, 'second': False}, got
            assert got['initial_guest'] == f02_values((0, 1)), got
            assert got['host_write'] == f02_values((0, 0)), got
            assert got['final_guest'] == f02_values((0, 0)), got
            # The guest copied a pre-existing second host reference; merely
            # retaining non-nullness or returning an arbitrary ref cannot pass.
            assert got['final_host'] == {'first': False, 'second': True}, got


def test_explicit_modes_report_selection_or_jit_refusal(f06_driver):
    calls = [('run', [f02_arg(0, x), f02_arg(0, y)], 1)
             for x, y in [(9, 5), (-7, -3)]]
    for mode in (2, 1):
        got = f06_driver.run(F06_CORE, calls, mode=mode, features='mvp', action='coexisting')
        assert got['loaded'] is True, got
        if mode == 1 and not got['created']:
            # A declined explicit JIT request has a NULL instance; its trap is optional.
            # The PRD permits refusal; it never permits a successful downgrade.
            assert got['created'] is False, got
        else:
            f06_check_mode(got, mode)
            assert got['retained'] == {'ok':True,'selected':mode}, got
            assert got['other'] == {'ok':True,'selected':3-mode}, got
            assert got['calls'] == [f02_values((0, 76)), f02_values((0, 52))], got

    # A valid binding that the reference JIT declines exercises its actual
    # refusal carrier. A future implementation that supports it is also valid.
    got = f06_driver.run(F06_ENTITIES['memory'], mode=1, action='memory',
                        calls=[('write', [f02_arg(0, 91)], 0)])
    assert got['loaded'] is True, got
    if got['created']:
        f06_check_mode(got, 1)
        assert got['initial_guest'] == f02_values((0, 11)), got
        assert got['host_write'] == f02_values((0, 37)), got
        assert got['calls'] == [f02_values()], got
        assert got['final_guest'] == f02_values((0, 91)), got
        assert got['final_host'] == 91, got
    else:
        assert got['created'] is False, got


def test_auto_rejects_invalid_and_never_repeats_failed_invocations(f06_driver):
    # Both the front-end and instantiation-time validation surfaces are valid
    # rejection points. Do not require the reference's division of validation.
    invalid = [
        '(module (func (result i32) f32.const 1))',
        '(module (func $f (param i32)) (start $f))',
        '(module (func $f) (export "a" (func $f)) (export "a" (func $f)))',
    ]
    for guest in invalid:
        got = f06_driver.run(guest, valid=False)
        if got['loaded']:
            assert got['created'] is False, got
            assert got['trap'] in (-1,19), got
        else:
            # The observed NULL module is the public loading-refusal carrier.
            assert got['loaded'] is False, got

    # The external recorder survives any replacement/reset of the instance.
    # Read the guest's accumulated state after every call as well: preserving
    # callback multiplicity alone does not prove that writes were not replayed.
    # Both memory arrangements run the same successful and failing calls.
    for imported in (False, True):
        memory = ('(import "env" "memory" (memory 1 4))' if imported
                  else '(memory 1 4)')
        guest = f'''(module
          (import "env" "observe" (func $observe (param i32))) {memory}
          (func (export "void-fault")
            i32.const 0 i32.const 113 i32.store i32.const 113 call $observe unreachable)
          (func (export "state") (result i32) i32.const 0 i32.load)
          (func (export "run") (param i32 i32) (result i32)
            i32.const 0 i32.const 0 i32.load local.get 1 i32.add i32.store
            local.get 1 call $observe i32.const 84 local.get 0 i32.div_s))'''
        calls = [('state', [], 1)]
        for divisor, token in [(2, 17), (0, 31), (4, 59), (0, -11)]:
            calls.extend([('run', [f02_arg(0, divisor), f02_arg(0, token)], 1),
                          ('state', [], 1)])
        calls += [('void-fault',[],0),('state',[],1)]
        got = f06_driver.run(guest, calls)
        assert got['loaded'] is True and got['created'] is True, got
        assert got['trap'] == -1, got
        # Function-only imports have no mandatory AUTO mode; externally bound
        # memory does. Do not impose an unspecified mode-stability requirement
        # on the function-only case: the promised outcome is no replay.
        for field in ('before', 'after'):
            assert got[field]['ok'] is True, got
            assert got[field]['selected'] in ((2,) if imported else (1, 2)), got
        assert got['calls'] == [
            f02_values((0, 0)),
            f02_values((0, 42)), f02_values((0, 17)),
            {'trap': 2}, f02_values((0, 48)),
            f02_values((0, 21)), f02_values((0, 107)),
            {'trap': 2}, f02_values((0, 96)), {'trap':1}, f02_values((0,113)),
        ], got
        assert got['events'] == [17, 31, 59, -11, 113], got
