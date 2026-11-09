# feature: F06
"""Callable acceptance through source checking and public type assertions."""
from textwrap import dedent
from _helpers import workspace
from F03_helpers import check_types
from F02_helpers import config_file, check_configured


def test_call_binding():
    check_types('''
        def target(a: int, /, b: str, *items: int, flag: bool, **extras: str) -> str:
            return b
        class Worker:
            def method(self, value: int) -> int: return value
            def __call__(self, value: str) -> str: return value
        def use(w: Worker):
            target(1, 'x', 2, flag=True, note='ok')
            target(*(1, 'x'), **{'flag': True})
            target(1, flag=True)  # E: incompatible_call
            target(1, 'x', b='y', flag=True)  # E: incompatible_call
            target(a=1, b='x', flag=True)  # E: incompatible_call
            target(1, 'x', True)  # E: incompatible_call
            target('bad', 'x', flag=True)  # E: incompatible_argument
            target(1, 'x', 'bad', flag=True)  # E: incompatible_argument
            target(1, 'x', flag=True, note=3)  # E: incompatible_argument
            w.method(2)
            w.method('bad')  # E: incompatible_argument
            w('ok')
            w(2)  # E: incompatible_argument
            w.method(1, 2)  # E: incompatible_call
            value = 42
            value()  # E: not_callable
    ''')


def test_higher_order_contracts():
    check_types('''
        from typing import Callable, ParamSpec, TypeVar, Concatenate, assert_type
        P = ParamSpec('P')
        R = TypeVar('R')
        def preserve(f: Callable[P, R]) -> Callable[P, R]: return f
        def bind(f: Callable[P, R]) -> Callable[Concatenate[int, P], R]:
            def wrapped(count: int, /, *args: P.args, **kwargs: P.kwargs) -> R:
                return f(*args, **kwargs)
            return wrapped
        def broad(x: object) -> str: return str(x)
        def narrow(x: str) -> object: return x
        def use():
            good: Callable[[str], object] = broad
            bad: Callable[[object], str] = narrow  # E: incompatible_assignment
            good('ok')
        @preserve
        def original(x: int, *, label: str) -> bytes: return b'x'
        def original_bound(text: str, *, enabled: bool) -> str: return text
        def calls():
            bound = bind(original_bound)
            assert_type(original(1, label='a'), bytes)
            original('bad', label='a')  # E: incompatible_argument
            original(1)  # E: incompatible_call
            assert_type(bound(1, 'a', enabled=True), str)
            bound(text='a', enabled=True)  # E: incompatible_call
            bound(1, 'a', enabled=1)  # E: incompatible_argument
    ''')


def test_concrete_overload_selection():
    check_types('''
        from typing import overload, assert_type
        @overload
        def choose(x: bool) -> bytes: ...
        @overload
        def choose(x: int) -> int: ...
        @overload
        def choose(x: str, *, repeat: int) -> str: ...
        def choose(x, **kwargs): return x
        def use(i: int, s: str, b: bool):
            assert_type(choose(b), bytes)
            assert_type(choose(i), int)
            assert_type(choose(s, repeat=2), str)
            choose(s)  # E: incompatible_argument
            choose(b'x')  # E: incompatible_argument
    ''')


def test_defaults_and_returns():
    check_types('''
        from abc import ABC, abstractmethod
        from typing import NoReturn, overload
        def default(x: int = 'wrong') -> int:  # E: incompatible_default
            return x
        def wrong() -> int:
            return 'wrong'  # E: incompatible_return_value
        def partial(flag: bool) -> int:  # E: missing_return
            if flag: return 1
        def complete(flag: bool) -> int:
            if flag: return 1
            raise ValueError()
        def nullable(flag: bool) -> int | None:
            if flag: return 1
        def never() -> NoReturn:
            return None  # E: no_return_may_return
        class Abstract(ABC):
            @abstractmethod
            def empty(self) -> int: ...
        @overload
        def stub(x: int) -> int: ...
        @overload
        def stub(x: str) -> str: ...
        def stub(x): return x
    ''')


def test_return_inference():
    check_types('''
        from typing import Any, Callable, assert_type
        def inferred(flag: bool, i: int, s: str):
            if flag: return i
            return s
        def partial(flag: bool, i: int):
            if flag: return i
            return
        def implicit():
            pass
        def declared() -> bytes: return b'x'
        def identity(x: bytes) -> bytes: return x
        def use(flag: bool, i: int, s: str, unknown: Callable):
            assert_type(inferred(flag, i, s), int | str)
            assert_type(partial(flag, i), int | None)
            assert_type(implicit(), type(None))
            result = declared()
            assert_type(identity(result), bytes)
            assert_type(result, str)  # E: inference_failure
            assert_type(unknown(1, key='x'), Any)
    ''')


def test_optional_annotation_checks():
    source = '''
        def ordinary(self):
            return self
        def generic(items: list) -> None:
            pass
        class Owner:
            def instance(receiver, value: int) -> int: return value
            @classmethod
            def factory(receiver, value: int) -> int: return value
    '''
    with workspace({'subject.py': dedent(source).lstrip('\n')}) as root:
        config = config_file(root)
        check_configured(root, config, [root / 'subject.py'])
        check_configured(root, config, [root / 'subject.py'], flags=(
            '--enable', 'missing_parameter_annotation', '--enable', 'missing_return_annotation',
            '--enable', 'missing_generic_parameters'), expected=[
                ('subject.py', 1, 'missing_parameter_annotation'),
                ('subject.py', 1, 'missing_return_annotation'),
                ('subject.py', 3, 'missing_generic_parameters')])


def test_unpacked_overload_preference():
    check_types('''
        from typing import overload, assert_type
        @overload
        def positional(x: int, /) -> int: ...
        @overload
        def positional(*x: int) -> str: ...
        def positional(*x: int) -> int | str: return ''
        @overload
        def keyword(*, x: int) -> int: ...
        @overload
        def keyword(**x: int) -> str: ...
        def keyword(**x: int) -> int | str: return ''
        def use(xs: tuple[int, ...], kw: dict[str, int]):
            assert_type(positional(*xs), str)
            assert_type(keyword(**kw), str)
            assert_type(positional(1), int)
            assert_type(keyword(x=1), int)
            assert_type(positional(*xs), int)  # E: inference_failure
    ''')


def test_imported_stub_contracts():
    files = {
        'library.py': 'def convert(*args, **kwargs): return None\n',
        'stubs/library/__init__.pyi': dedent('''
            from typing import overload
            @overload
            def convert(value: int, count: int = ...) -> bytes: ...
            @overload
            def convert(value: str, *, upper: bool) -> str: ...
        '''),
        'subject.py': dedent('''\
            from library import convert
            from typing import assert_type
            def use():
                assert_type(convert(2), bytes)
                assert_type(convert(2, 3), bytes)
                assert_type(convert('a', upper=True), str)
                convert('a')
                convert(2, 'bad')
                value: int = convert(2)
        '''),
    }
    with workspace(files) as root:
        config = config_file(root, 'import_paths = ["."]\nstub_path = ["stubs"]\n')
        check_configured(root, config, [root / 'subject.py'], flags=('--disable', 'unused_variable'),
                         expected=[('subject.py', 7, 'incompatible_argument'),
                                   ('subject.py', 8, 'incompatible_argument'),
                                   ('subject.py', 9, 'incompatible_assignment')])


def test_callable_intersections():
    check_types('''
        from typing import Callable, assert_type
        from velnora.extensions import Intersection
        class A: pass
        class B: pass
        class C: pass
        def use(f: Intersection[Callable[[int], A], Callable[[object], B]],
                g: Intersection[Callable[[int], A], Callable[[str], C]],
                value: int | str, uncovered: int | bytes):
            assert_type(f(1), Intersection[A, B])
            assert_type(g(value), A | C)
            g(uncovered)  # E: incompatible_call|incompatible_argument
    ''')


def test_constructor_contracts():
    check_types('''
        from typing import Generic, TypeVar, Any, Never, Self, assert_type
        T = TypeVar('T')
        class Box(Generic[T]):
            def __init__(self, value: T) -> None: self.value = value
        class Empty: pass
        class Proxy:
            def __new__(cls, name: str) -> str: return name
            def __init__(self, count: int) -> None: pass
        class Dynamic:
            def __new__(cls) -> Any: return object.__new__(cls)
            def __init__(self, count: int) -> None: pass
        class Stop:
            def __new__(cls) -> Never: raise RuntimeError()
            def __init__(self, count: int) -> None: pass
        class Meta(type):
            def __call__(cls, value: str) -> bytes: return value.encode()
        class Special(metaclass=Meta):
            def __init__(self, count: int) -> None: pass
        def use():
            assert_type(Box[int](1), Box[int])
            Box[int]('bad')  # E: incompatible_argument
            Empty()
            Empty(1)  # E: incompatible_call
            assert_type(Proxy('name'), str)
            Proxy(1)  # E: incompatible_argument
            assert_type(Dynamic(), Any)
            Dynamic(1)  # E: incompatible_call
            assert_type(Special('name'), bytes)
            Special(1)  # E: incompatible_argument
        def stopped():
            assert_type(Stop(), Never)
        def invalid_stop():
            Stop(1)  # E: incompatible_call
    ''')


def test_union_and_unknown_overloads():
    check_types('''
        from typing import Any, overload, assert_type
        @overload
        def choose(x: int) -> bytes: ...
        @overload
        def choose(x: str) -> float: ...
        def choose(x): return x
        def use(value: int | str, uncovered: int | bytes, unknown: Any):
            assert_type(choose(value), bytes | float)
            choose(uncovered)  # E: incompatible_argument
            assert_type(choose(unknown), Any)
    ''')


def test_overload_implementation_consistency():
    check_types('''
        from typing import overload
        @overload
        def good(x: int) -> int: ...
        @overload
        def good(x: str) -> str: ...
        def good(x: int | str) -> int | str: return x
        @overload
        def bad_parameter(x: int) -> int: ...
        @overload
        def bad_parameter(x: str) -> str: ...  # E+1: inconsistent_overload
        def bad_parameter(x: int) -> int | str: return x
        @overload
        def bad_return(x: int) -> int: ...
        @overload
        def bad_return(x: str) -> str: ...  # E+1: inconsistent_overload
        def bad_return(x: int | str) -> int: return 1
    ''')
