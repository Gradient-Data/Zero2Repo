# feature: F05
"""Acceptance tests for lexical bindings and reachable control-flow results."""
from textwrap import dedent
from collections import Counter
from _helpers import environment_info, workspace, read_json
from F01_helpers import check_source
from F03_helpers import check_types


def test_lexical_bindings():
    check_types('''
        from typing import assert_type, Literal
        shared = 'outer'
        class Box:
            shared = 12
            copy = shared
            assert_type(copy, Literal[12])
            def method(self):
                assert_type(shared, Literal['outer'])
        def outer(value: int, flag: bool):
            def closure():
                assert_type(value, int)
                size: int = len('abc')
                print(size)
            local = 'inner'
            assert_type(local, Literal['inner'])
            assert_type(local, int)  # E: inference_failure
            if flag:
                conditional = 1
            print(conditional)  # E: possibly_undefined_name
            print(missing)  # E: undefined_name
            values = [item + value for item in range(3)]
            print(item)  # E: undefined_name
            print(values)
            return closure
        def separate():
            print(local)  # E: undefined_name
    ''')


def test_branch_and_cleanup_merges():
    check_types('''
        from typing import assert_type, Literal, NoReturn
        def stop() -> NoReturn:
            raise RuntimeError()
        def merged(flag: bool, i: int, s: str):
            if flag:
                value = i
            else:
                value = s
            assert_type(value, int | str)
            assert_type(value, int)  # E: inference_failure
        def terminated(mode: int, i: int):
            if mode == 0:
                value = 'return'
                print(value)
                return
            elif mode == 1:
                value = 'raise'
                print(value)
                raise ValueError()
            elif mode == 2:
                value = 'stop'
                print(value)
                stop()
            else:
                value = i
            assert_type(value, int)
        def handled(i: int, s: str):
            try:
                value = i
            except ValueError:
                value = s
            assert_type(value, int | str)
            try:
                other = i
                print(other)
            finally:
                other = s
            assert_type(other, str)
        def cleanup(flag: bool):
            try:
                if flag:
                    partial = 1
            finally:
                print(partial)  # E: possibly_undefined_name
    ''')


def test_scope_declarations():
    check_types('''
        from typing import assert_type, Literal
        shared = 1
        def global_write():
            global shared
            shared = 'changed'
            assert_type(shared, Literal['changed'])
            assert_type(shared, int)  # E: inference_failure
        def outer():
            cell = 1
            def write():
                nonlocal cell
                cell = 'updated'
                assert_type(cell, Literal['updated'])
                assert_type(cell, int)  # E: inference_failure
            return write
    ''')
    # Invalid declarations can be refused at compilation or during checking.
    for source in ('def f():\n    nonlocal absent\n',
                   'def f():\n    global clash\n    nonlocal clash\n'):
        with workspace() as root:
            result = check_source(root, ['--code', source])
            assert result.returncode == 1, result
            assert result.stderr.strip(), result


def test_exception_operations():
    check_types('''
        from typing import assert_type
        def raising():
            raise 23  # E: bad_exception
        def valid():
            raise ValueError('reason')
        def handlers():
            try:
                raise ValueError()
            except ValueError as error:
                assert_type(error, ValueError)
                assert_type(error, int)  # E: inference_failure
            try:
                raise TypeError()
            except int:  # E: bad_except_handler
                pass
    ''')
    if environment_info()['version'][:2] >= (3, 11):
        check_types('''
            from typing import assert_type
            def groups():
                try:
                    raise ExceptionGroup('errors', [ValueError()])
                except* ValueError as errors:
                    assert_type(errors, ExceptionGroup[ValueError])
                    assert_type(errors, ValueError)  # E: inference_failure
                try:
                    raise BaseExceptionGroup('errors', [KeyboardInterrupt()])
                except* KeyboardInterrupt as errors:
                    assert_type(errors, BaseExceptionGroup[KeyboardInterrupt])
                try:
                    raise ExceptionGroup('errors', [ValueError()])
                except* ExceptionGroup:  # E: bad_except_handler
                    pass
        ''')


def test_environment_branches():
    env = environment_info()
    # Each environment comparison selects its branch in both directions, so a
    # checker that always takes (or always skips) the guarded branch fails.
    conditions = [(f"sys.version_info >= {env['version'][:2]!r}", True),
                  (f"sys.version_info < {env['version'][:2]!r}", False),
                  (f"sys.platform == {env['platform']!r}", True),
                  ("sys.platform == 'not-a-platform'", False),
                  ("sys.platform != 'not-a-platform'", True),
                  (f"sys.implementation.name == {env['implementation']!r}", True),
                  ("sys.implementation.name == 'not-an-interpreter'", False),
                  ('TYPE_CHECKING', True)]
    selected = ['        value = 17']
    excluded = ['        excluded_name', "        1 + 'invalid'", "        value = 'x'"]
    for condition, outcome in conditions:
        first, second = (selected, excluded) if outcome else (excluded, selected)
        check_types('\n'.join([
            'import sys',
            'from typing import TYPE_CHECKING, assert_type, Literal',
            'def selected():',
            f'    if {condition}:', *first,
            '    else:', *second,
            '    assert_type(value, Literal[17])',
            '    assert_type(value, str)  # E: inference_failure',
        ]))


def test_optional_unreachable_reporting():
    source = dedent('''\
        from typing import NoReturn
        def stop() -> NoReturn:
            raise RuntimeError()
        def live():
            unknown_live_name
        def after_return():
            return
            print('first')
            print('second')
        def after_raise():
            raise ValueError()
            print('third')
        def after_stop():
            stop()
            print('fourth')
        def excluded(flag: bool):
            print('reachable')
            if False:
                print('fifth')
                print('sixth')
            if flag:
                print('also reachable')
    ''')
    for enabled in (False, True):
        with workspace() as root:
            path = root / 'report.json'
            args = ['--disable', 'value_always_true', '--json-output', str(path), '--code', source]
            if enabled:
                args = ['--enable', 'unreachable', *args]
            result = check_source(root, args)
            findings = read_json(path, result=result)
            expected = Counter({(8, 'unreachable'): 1, (12, 'unreachable'): 1,
                                (15, 'unreachable'): 1, (19, 'unreachable'): 1}) if enabled else Counter()
            expected[(5, 'undefined_name')] = 1
            assert Counter((f['lineno'], f['code']) for f in findings) == expected, findings
            assert result.returncode == 1, result
            assert result.stderr.strip(), result


def test_loop_bindings_and_completion():
    check_types('''
        from typing import assert_type, Literal
        def maybe_empty(items: list[int]):
            for item in items:
                last = item
            print(last)  # E: possibly_undefined_name
        def completion(items: list[int], flag: bool):
            value = 'initial'
            for item in items:
                value = item
            assert_type(value, Literal['initial'] | int)
            assert_type(value, int)  # E: inference_failure
            outcome = 'initial'
            for item in items:
                if flag:
                    outcome = item
                    break
            else:
                outcome = 'complete'
            accepted: int | str = outcome
            rejected: bytes = outcome  # E: incompatible_assignment
            normal = 'finished'
            print(normal)
            for item in items:
                normal = item
            else:
                normal = 'finished'
            completed: int | str = normal
            wrong: bytes = normal  # E: incompatible_assignment
            while flag:
                only_in_loop = 1
                break
            print(only_in_loop)  # E: possibly_undefined_name
    ''')
