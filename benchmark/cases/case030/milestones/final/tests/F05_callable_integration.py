# feature: F05
"""Acceptance of interactive Python calls, binding, and higher-order code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _helpers import write_text
from F01_helpers import translate_and_observe
from F02_helpers import python_namespace
from F05_helpers import interactive_session, load_session_module, require_exception


# Reference measurement (original, C and Fortran): the interpreter took
# 13 to 14 times as long as the translated callable for 200000 iterations.
SPEED_ITERATIONS = 200000
SPEED_SOURCE = '''
def churn(n: int, seed: int):
    total = seed
    for i in range(n):
        total = (total * 31 + i) % 1000003
    return total
'''


def test_interactive_inputs_and_context(tmp_path):
    for language in ('c', 'fortran'):
        root = tmp_path / language
        root.mkdir()
        path = write_text(root, 'context_input.py', '''
import numpy as np

def plain(x: int):
    return x * x - 3

def make_context():
    offset = 13
    T = int
    def contextual(x: T) -> T:
        return x * offset + int(np.floor(2.75))
    return contextual

def unresolved(x: int):
    return external_object.value + x
''')

        def exercise(ezelvori):
            from zelvori.errors.errors import ZelvoriSemanticError
            module = load_session_module(path)
            plain = ezelvori(module.plain, language=language, folder='function')
            for x in (-4, 7):
                assert plain(x) == module.plain(x)
            contextual = module.make_context()
            compiled = ezelvori(contextual, language=language, folder='context')
            for x in (-3, 8):
                assert compiled(x) == contextual(x)
            # A separate source-backed module exercises the module input form.
            simple_path = write_text(Path.cwd(), 'module_input.py',
                                    'def evaluate(x: int):\n    return 5 * x - 2\n')
            simple = load_session_module(simple_path)
            delivered = ezelvori(simple, language=language, folder='module')
            text = ezelvori(simple_path.read_text(), language=language, folder='text')
            for x in (-2, 9):
                assert delivered.evaluate(x) == simple.evaluate(x)
                assert text.evaluate(x) == simple.evaluate(x)
            # A second request with the same names in the same folder delivers
            # its own computation; earlier deliveries keep theirs.
            changed = ezelvori(simple_path.read_text().replace('5 * x - 2', '7 * x + 4'),
                              language=language, folder='text')
            for x in (-2, 9):
                assert changed.evaluate(x) == 7 * x + 4
                assert text.evaluate(x) == simple.evaluate(x)
            with require_exception(ZelvoriSemanticError):
                ezelvori(module.unresolved, language=language, folder='unresolved')
            # A translated callable must outrun the interpreter on the same
            # loop-dominated call (FP-05.01). Calls alternate and vary their
            # seed; the best of seven calls on each side is compared.
            import time
            speed = load_session_module(write_text(Path.cwd(), 'speed_input.py', SPEED_SOURCE))
            native = ezelvori(speed.churn, language=language, folder='speed')
            native_times, python_times = [], []
            for seed in range(7):
                started = time.perf_counter()
                observed = native(SPEED_ITERATIONS, seed)
                native_times.append(time.perf_counter() - started)
                started = time.perf_counter()
                expected = speed.churn(SPEED_ITERATIONS, seed)
                python_times.append(time.perf_counter() - started)
                assert observed == expected
            assert min(python_times) >= 3 * min(native_times), (native_times, python_times)

        interactive_session(root / 'session', exercise)


BINDING_SOURCE = '''
def bind(a: int, b: int, c: int = 7):
    return 100 * a + 10 * b + c

def positional(a: int, /, b: int = 4):
    return 10 * a - b

def keyword(a: int, *, b: int = 2, c: int = 3):
    return 100 * a - 10 * b + c

def optional(a: int, b: int = None):
    if b is None:
        return a - 11
    return a + 2 * b
'''


def test_argument_binding_and_defaults(tmp_path):
    reference = python_namespace(BINDING_SOURCE)

    def exercise(module):
        calls = [
            ('bind', (2, 5), {}), ('bind', (), {'c': 9, 'b': 3, 'a': -1}),
            ('bind', (4,), {'b': -2}), ('bind', (1, 2, 3), {}),
            ('positional', (6,), {}), ('positional', (-3,), {'b': 8}),
            ('keyword', (4,), {}), ('keyword', (4,), {'b': 5}),
            ('keyword', (), {'c': 8, 'b': -1, 'a': 3}),
            ('optional', (8,), {}), ('optional', (8, None), {}),
            ('optional', (8, 0), {}), ('optional', (-2,), {'b': 9}),
        ]
        for name, args, kwargs in calls:
            assert getattr(module, name)(*args, **kwargs) == reference[name](*args, **kwargs)

    for language in ('c', 'fortran'):
        translate_and_observe(BINDING_SOURCE, language, tmp_path / language, exercise)


def test_invalid_argument_bindings(tmp_path):
    def exercise(module):
        assert module.bind(2, 5) == 257
        assert module.positional(6, b=8) == 52
        assert module.keyword(4, b=2) == 383
        invalid = [
            ('bind', (2,), {}), ('bind', (2, 5), {'a': 3}),
            ('bind', (2, 5), {'unknown': 3}), ('bind', (2.5, 5), {}),
            ('bind', (2, 5, 7, 9), {}),
            ('positional', (), {'a': 6, 'b': 8}),
            ('keyword', (4, 2), {}),
        ]
        for name, args, kwargs in invalid:
            with require_exception(TypeError):
                getattr(module, name)(*args, **kwargs)
        assert module.bind(-1, 3, 9) == -61

    for language in ('c', 'fortran'):
        translate_and_observe(BINDING_SOURCE, language, tmp_path / language, exercise)


def test_results_and_private_visibility(tmp_path):
    source = '''
from zelvori.decorators import private

@private
def hidden(x: int):
    return 3 * x + 7

def scalar(x: int):
    return hidden(x) - 2

def multiple(x: int, y: int):
    return hidden(x), x - y, y > x

def no_result(a: 'int[:]'):
    a[0] += 9
'''
    def exercise(module):
        from F00_oracle import host_numpy as np
        for x, y in ((2, 5), (-4, -7)):
            assert module.scalar(x) == 3 * x + 5
            assert module.multiple(x, y) == (3 * x + 7, x - y, y > x)
        values = np.array([5, -2], dtype=int)
        assert module.no_result(values) is None
        assert values.tolist() == [14, -2]
        with require_exception(AttributeError):
            getattr(module, 'hidden')

    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_translated_calls_and_recursion(tmp_path):
    source = '''
def transform(x: int, scale: int = 3):
    return scale * x - 2

def recursive(n: int) -> int:
    if n <= 0:
        return 2
    return recursive(n - 1) + transform(n)

def outer(n: int):
    return transform(recursive(n), scale=2) + transform(n)
'''
    reference = python_namespace(source)

    def exercise(module):
        for n in (-2, 0, 1, 5, 9):
            assert module.recursive(n) == reference['recursive'](n)
            assert module.outer(n) == reference['outer'](n)

    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


HIGHER_ORDER_SOURCE = '''
def increase(x: int):
    return x + 5

def decrease(x: int):
    return 2 * x - 3

def apply(x: int, function: '(int)(int)' = increase):
    return function(x)

def choose(x: int, alternate: bool):
    if alternate:
        return apply(x, decrease)
    return apply(x)

def explicit_default(x: int):
    return apply(x, increase)
'''


def test_typed_callable_arguments(tmp_path):
    def exercise(module):
        for x in (-7, 0, 11):
            assert module.choose(x, False) == x + 5
            assert module.choose(x, True) == 2 * x - 3
            assert module.explicit_default(x) == x + 5

    for language in ('c', 'fortran'):
        translate_and_observe(HIGHER_ORDER_SOURCE, language, tmp_path / language, exercise)

    def reject(ezelvori):
        from zelvori.errors.errors import ZelvoriSemanticError
        # The refusal matters; either published compilation error carrier is
        # accepted, without requiring a particular validation phase.
        for name, declaration, expression in (
            ('argument', 'float', 'int(x)'),
            ('result', 'int', 'float(x)'),
        ):
            source = HIGHER_ORDER_SOURCE + f'''
def incompatible(x: {declaration}):
    return {expression}

def invalid(x: int):
    return apply(x, incompatible)
'''
            try:
                ezelvori(source, language='fortran', folder=name)
            except (ZelvoriSemanticError, RuntimeError):
                pass
            else:
                raise AssertionError('Incompatible callable declaration was accepted')

    interactive_session(tmp_path / 'fortran_invalid', reject)


def test_local_anonymous_functions(tmp_path):
    source = '''
def evaluate(a: int, b: int):
    first = lambda x: x * x + 1
    second = lambda x, y: first(y) - 3 * x
    return second(a, b), second(b, a)
'''
    reference = python_namespace(source)

    def exercise(module):
        for a, b in ((2, 5), (-3, 4), (0, -2), (7, 1)):
            assert module.evaluate(a, b) == reference['evaluate'](a, b)

    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)
