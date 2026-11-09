# feature: F17
"""Declarative typing through checked calls and CLI diagnostics."""
import ast
import sys
from textwrap import dedent

from _helpers import environment_info, workspace
from F01_helpers import assert_source_column
from F02_helpers import config_file, check_configured
from F17_helpers import check_evaluated_source


def test_conditional_declarations():
    check_evaluated_source('''
        from typing import assert_type
        from velnora.extensions import evaluated, is_of_type, show_error
        @evaluated
        def choose(value: int | str):
            if is_of_type(value, int):
                return bytes
            return float
        def choose(value: int | str) -> object: raise NotImplementedError
        @evaluated
        def nonempty(value: str):
            if value == '':
                show_error('A nonempty value is required', argument=value)
            return int
        def nonempty(value: str) -> object: raise NotImplementedError
        def use(value: int | str):
            assert_type(choose(4), bytes)
            assert_type(choose('abc'), float)
            assert_type(choose(value), bytes | float)
            choose(b'bad')  # E: incompatible_argument
            assert_type(nonempty('ok'), int)
            nonempty('')  # E: incompatible_call
            assert_type(choose(4), float)  # E: inference_failure
    ''')
    files = {
        'library.py': 'def choose(value): raise NotImplementedError\n',
        'stubs/velnora/__init__.pyi': '',
        'stubs/velnora/extensions.pyi': (
            'from typing import Any, Callable\n'
            'def evaluated(func: Callable[..., Any]) -> Callable[..., Any]: ...\n'
        ),
        'stubs/library/__init__.pyi': dedent('''\
            from velnora.extensions import evaluated, is_of_type, show_error
            @evaluated
            def choose(value: int | str):
                if is_of_type(value, int):
                    return bytes
                if value == '':
                    show_error('A nonempty value is required', argument=value)
                return float
        '''),
        'subject.py': dedent('''\
            from library import choose
            from typing import assert_type
            def use(value: int | str):
                assert_type(choose(4), bytes)
                assert_type(choose('abc'), float)
                assert_type(choose(value), bytes | float)
                choose(b'bad')
                choose('')
                assert_type(choose(4), float)
        '''),
    }
    with workspace(files) as root:
        config = config_file(root, 'import_paths = ["."]\nstub_path = ["stubs"]\n')
        check_configured(root, config, [root / 'subject.py'], expected=[
            ('subject.py', 7, 'incompatible_argument'),
            ('subject.py', 8, 'incompatible_call'),
            ('subject.py', 9, 'inference_failure'),
        ])


def test_conditions_and_environment():
    check_evaluated_source('''
        from typing import Any, Literal, assert_type
        from velnora.extensions import evaluated, is_provided, is_positional, is_keyword, is_of_type
        @evaluated
        def kind(value: int = 0):
            if is_positional(value):
                return bytes
            if is_keyword(value):
                return str
            if is_provided(value):
                return bool
            return float
        def kind(*args, **kwargs): raise NotImplementedError
        @evaluated
        def provided(value: int = 0):
            if is_provided(value):
                return bytes
            return str
        def provided(*args, **kwargs): raise NotImplementedError
        @evaluated
        def logic(value: int | None, label: str):
            if value is not None and (label == 'go' or label == 'run'):
                if not is_of_type(value, Literal[0]):
                    return bytes
            return str
        def logic(value, label): raise NotImplementedError
        @evaluated
        def unequal(value: int):
            if value != 3:
                return bytes
            return str
        def unequal(value): raise NotImplementedError
        @evaluated
        def identity(value: bool):
            if value is True:
                return bytes
            return str
        def identity(value): raise NotImplementedError
        def use(args: Any, kwargs: Any):
            assert_type(kind(), float)
            assert_type(kind(0), bytes)
            assert_type(kind(value=0), str)
            assert_type(kind(*args), float)
            assert_type(kind(**kwargs), float)
            assert_type(provided(), str)
            assert_type(provided(0), bytes)
            assert_type(provided(value=0), bytes)
            assert_type(provided(*args), str)
            assert_type(provided(**kwargs), str)
            assert_type(logic(2, 'go'), bytes)
            assert_type(logic(2, 'run'), bytes)
            assert_type(logic(0, 'go'), str)
            assert_type(logic(None, 'go'), str)
            assert_type(logic(2, 'stop'), str)
            assert_type(unequal(3), str)
            assert_type(unequal(4), bytes)
            assert_type(identity(True), bytes)
            assert_type(identity(False), str)
            assert_type(kind(0), str)  # E: inference_failure
            assert_type(provided(), bytes)  # E: inference_failure
            assert_type(logic(2, 'go'), str)  # E: inference_failure
            assert_type(unequal(3), bytes)  # E: inference_failure
            assert_type(identity(False), bytes)  # E: inference_failure
    ''')
    info = environment_info()
    version = info['version'][:3]
    implementation_version = tuple(sys.implementation.version)
    # Each supported comparison gets both outcomes, without assuming the host.
    conditions = [
        (f'sys.version_info >= {version!r}', True),
        (f'sys.version_info < {version!r}', False),
        (f'sys.version_info == {info["version"]!r}', True),
        ('sys.version_info == (0, 0)', False),
        (f'sys.implementation.version >= {implementation_version!r}', True),
        (f'sys.implementation.version < {implementation_version!r}', False),
        (f'sys.implementation.version == {implementation_version!r}', True),
        ('sys.implementation.version == (0, 0)', False),
        (f'sys.platform == {info["platform"]!r}', True),
        ("sys.platform == 'not-a-platform'", False),
        (f'sys.platform in ({info["platform"]!r},)', True),
        ("sys.platform in ('not-a-platform',)", False),
        (f'sys.platform.startswith({info["platform"][:2]!r})', True),
        ("sys.platform.startswith('not-a-platform')", False),
        (f'sys.implementation.name == {info["implementation"]!r}', True),
        ("sys.implementation.name == 'not-an-interpreter'", False),
        (f'sys.implementation.name in ({info["implementation"]!r},)', True),
        ("sys.implementation.name in ('not-an-interpreter',)", False),
    ]
    source = 'import sys\nfrom typing import assert_type\nfrom velnora.extensions import evaluated\n'
    for index, (condition, outcome) in enumerate(conditions):
        source += (f'@evaluated\ndef environment_{index}():\n'
                   f'    if {condition}:\n        return bytes\n    return str\n'
                   f'def environment_{index}(): raise NotImplementedError\n')
    source += 'def use():\n'
    for index, (_, outcome) in enumerate(conditions):
        source += f'    assert_type(environment_{index}(), {"bytes" if outcome else "str"})\n'
    check_evaluated_source(source)


def test_declaration_validation_and_revelation():
    findings = check_evaluated_source('''
        from typing import assert_type
        from velnora.extensions import evaluated, is_of_type, is_provided, show_error, reveal_type
        @evaluated
        def valid(value: int):
            if is_of_type(value, int):
                pass
            reveal_type(value)
            show_error('Declaration explanation')
            return bytes
        def valid(value): raise NotImplementedError
        def use(number: int):
            result = valid(number)  # E: incompatible_call, incompatible_call|reveal_type
            assert_type(result, bytes)
        @evaluated
        def invalid(value: int):
            value = 2  # E: bad_evaluator
            print(value)  # E: bad_evaluator
            if value > 1:  # E: bad_evaluator
                return bytes
            if is_provided(other):  # E: bad_evaluator
                return str
            reveal_type(other)  # E: bad_evaluator
            return int
        def invalid(value): raise NotImplementedError
    ''')
    descriptions = [f['description'] for f in findings if f['code'] in ('incompatible_call', 'reveal_type')]
    reveals = [text.partition('Type of value is ')[2] for text in descriptions
               if 'Type of value is ' in text]
    assert len(reveals) == 1, descriptions
    assert ast.literal_eval(reveals[0]) == 'int', descriptions
    assert any('Declaration explanation' in text for text in descriptions), descriptions


def test_defaults_and_fallthrough():
    check_evaluated_source('''
        from typing import Any, Literal, assert_type
        from velnora.extensions import evaluated, is_of_type, show_error
        @evaluated
        def concrete(value: int = 7):
            if is_of_type(value, Literal[7]):
                return bytes
            return str
        def concrete(value=7): raise NotImplementedError
        @evaluated
        def unspecified(value: int = ...):
            if is_of_type(value, Literal[7]):
                return bytes
            return str
        def unspecified(value=7): raise NotImplementedError
        @evaluated
        def annotated(value: bool) -> float:
            if value is True:
                return bytes
            pass
        def annotated(value): raise NotImplementedError
        @evaluated
        def unrestricted(value: bool):
            if value is True:
                return bytes
            pass
        def unrestricted(value): raise NotImplementedError
        @evaluated
        def continues(value: int):
            show_error('Continue after this diagnostic', argument=value)
            return bytes
        def continues(value): raise NotImplementedError
        def use():
            assert_type(concrete(), bytes)
            assert_type(concrete(8), str)
            assert_type(unspecified(), str)
            assert_type(unspecified(7), bytes)
            assert_type(annotated(True), bytes)
            assert_type(annotated(False), float)
            assert_type(unrestricted(True), bytes)
            assert_type(unrestricted(False), Any)
            result = continues(1)  # E: incompatible_call
            assert_type(result, bytes)
            wrong: str = result  # E: incompatible_assignment
    ''')


def test_custom_diagnostic_attribution():
    info = environment_info()
    source = dedent(f'''
        import sys
        from velnora.extensions import evaluated, is_provided, show_error
        @evaluated
        def restricted(first: int, second: int = 0):
            if is_provided(second):
                show_error('Restriction explanation', argument=second)
            return int
        def restricted(first, second=0): raise NotImplementedError
        @evaluated
        def environmental(first: int, second: int = 0):
            if sys.platform == {info['platform']!r}:
                show_error('Restriction explanation')
            return int
        def environmental(first, second=0): raise NotImplementedError
        def use():
            restricted(11)
            restricted(11, 22)  # E: incompatible_call
            restricted(11, second=33)  # E: incompatible_call
            environmental(11, 22)  # E: incompatible_call
    ''').lstrip('\n')
    findings = check_evaluated_source(source)
    by_line = {f['lineno']: f for f in findings}
    lines = source.splitlines()
    for line, text in enumerate(lines, 1):
        if '# E:' not in text:
            continue
        finding = by_line[line]
        assert 'Restriction explanation' in finding['description'], finding
        indent = len(text) - len(text.lstrip())
        call = ast.parse(text.lstrip()).body[0].value
        if 'environmental(' in text:
            assert_source_column(finding['col_offset'], text,
                                 start=indent + call.col_offset, end=indent + call.end_col_offset)
            assert any(part.lstrip().startswith('Platform (')
                       for part in finding['concise_message'].splitlines()), finding
        else:
            argument = call.keywords[0].value if call.keywords else call.args[1]
            assert_source_column(finding['col_offset'], text,
                                 start=indent + argument.col_offset, end=indent + argument.end_col_offset)
            assert any(part.lstrip().startswith('Argument second ')
                       for part in finding['concise_message'].splitlines()), finding


def test_unrestricted_compatibility():
    check_evaluated_source('''
        from typing import Any, Sequence, assert_type
        from velnora.extensions import evaluated, is_of_type
        @evaluated
        def strict(value: object):
            if is_of_type(value, int):
                return bytes
            return str
        def strict(value): raise NotImplementedError
        @evaluated
        def gradual(value: object):
            if is_of_type(value, int, exclude_any=False):
                return bytes
            return str
        def gradual(value): raise NotImplementedError
        @evaluated
        def nested(value: object):
            if is_of_type(value, Sequence[int]):
                return bytes
            return str
        def nested(value): raise NotImplementedError
        @evaluated
        def nested_gradual(value: object):
            if is_of_type(value, Sequence[int], exclude_any=False):
                return bytes
            return str
        def nested_gradual(value): raise NotImplementedError
        @evaluated
        def any_target(value: object):
            if is_of_type(value, Any):
                return bytes
            return str
        def any_target(value): raise NotImplementedError
        @evaluated
        def any_target_gradual(value: object):
            if is_of_type(value, Any, exclude_any=False):
                return bytes
            return str
        def any_target_gradual(value): raise NotImplementedError
        @evaluated
        def universal_target(value: object):
            if is_of_type(value, object):
                return bytes
            return str
        def universal_target(value): raise NotImplementedError
        def use(unknown: Any, nested_unknown: Sequence[Any], integers: Sequence[int]):
            assert_type(strict(1), bytes)
            assert_type(strict('x'), str)
            assert_type(strict(unknown), str)
            assert_type(gradual(unknown), bytes)
            assert_type(gradual('x'), str)
            assert_type(nested(integers), bytes)
            assert_type(nested(nested_unknown), str)
            assert_type(nested(unknown), str)
            assert_type(nested_gradual(nested_unknown), bytes)
            assert_type(nested_gradual(unknown), bytes)
            assert_type(any_target(unknown), bytes)
            assert_type(any_target(nested_unknown), str)
            assert_type(any_target('x'), str)
            assert_type(any_target_gradual(unknown), bytes)
            assert_type(any_target_gradual(nested_unknown), bytes)
            assert_type(any_target_gradual(1), bytes)
            assert_type(universal_target(unknown), bytes)
            assert_type(universal_target(nested_unknown), bytes)
            assert_type(universal_target(1), bytes)
            assert_type(strict(unknown), bytes)  # E: inference_failure
            assert_type(gradual(unknown), str)  # E: inference_failure
            assert_type(nested(integers), str)  # E: inference_failure
            assert_type(any_target('x'), bytes)  # E: inference_failure
    ''')
