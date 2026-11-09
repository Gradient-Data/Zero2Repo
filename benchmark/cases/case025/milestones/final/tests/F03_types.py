# feature: F03
"""Acceptance tests for annotation meanings and generic specialization."""
import ast
from _helpers import workspace
from F03_helpers import check_types, expression_type, literal_display_value


def test_annotation_compatibility():
    check_types('''
        from typing import Any, Callable, Optional, Union, Literal, assert_type
        def f(i: int, s: str, u: Union[int, str], a: Any,
              li: list[int], se: set[str], ma: dict[str, int], cb: Callable[[int], str]):
            x: Union[int, str] = i
            y: Union[int, str] = s
            z: int = u  # E: incompatible_assignment
            optional: Optional[int] = None
            optional2: Optional[int] = i
            unrestricted: int = a
            anything: Any = s
            good_list: list[int] = li
            bad_list: list[str] = li  # E: incompatible_assignment
            good_set: set[str] = se
            bad_set: set[int] = se  # E: incompatible_assignment
            good_map: dict[str, int] = ma
            bad_key: dict[int, int] = ma  # E: incompatible_assignment
            bad_value: dict[str, str] = ma  # E: incompatible_assignment
            good_call: Callable[[int], str] = cb
            bad_call: Callable[[str], str] = cb  # E: incompatible_assignment
            bad_result: Callable[[int], int] = cb  # E: incompatible_assignment
            scalar: str = i  # E: incompatible_assignment
            assert_type(cb(i), str)
    ''')


def test_subtypes_numeric_and_nominal():
    check_types('''
        from typing import NewType
        class Parent: pass
        class Child(Parent): pass
        User = NewType('User', int)
        Group = NewType('Group', int)
        def f(p: Parent, c: Child, pc: type[Parent], cc: type[Child],
              i: int, r: float, z: complex, user: User, group: Group):
            a: Parent = c
            b: Child = p  # E: incompatible_assignment
            ac: type[Parent] = cc
            bc: type[Child] = pc  # E: incompatible_assignment
            real: float = i
            complex_i: complex = i
            complex_r: complex = r
            narrow_i: int = r  # E: incompatible_assignment
            narrow_r: float = z  # E: incompatible_assignment
            underlying: int = user
            same: User = user
            wrong_base: User = i  # E: incompatible_assignment
            wrong_wrapper: User = group  # E: incompatible_assignment
    ''')


def test_forward_annotations_and_invalid_aliases():
    check_types('''
        from typing import TypeAlias, Union, assert_type
        Alias = list[int]
        def f(x: 'Later', items: 'Alias'):
            assert_type(x, Later)
            assert_type(items, list[int])
            wrong: list[str] = items  # E: incompatible_assignment
            malformed: 123 = 1  # E: invalid_annotation
        class Later: pass
        Cycle: TypeAlias = Union['Cycle', int]  # E: invalid_type_alias
    ''')


def test_generic_inference_and_specialization():
    check_types('''
        from typing import Generic, TypeVar, assert_type
        T = TypeVar('T')
        B = TypeVar('B', bound=int)
        C = TypeVar('C', int, str)
        class Box(Generic[T]):
            def __init__(self, value: T): self.value = value
        type Bounded[B: int] = list[B]
        type Constrained[C: (int, str)] = list[C]
        def identity(value: T) -> T: return value
        def f(i: int, s: str):
            assert_type(identity(i), int)
            assert_type(identity(s), str)
            assert_type(Box(i), Box[int])
            assert_type(Box[str](s), Box[str])
            Box[int](s)  # E: incompatible_argument
            a: Bounded[int]
            b: Bounded[str]  # E: invalid_specialization
            c: Constrained[bytes]  # E: invalid_specialization
            d: Box[int, str]  # E: invalid_specialization
            e: Box[42]  # E: invalid_annotation
    ''')


def test_generic_defaults():
    check_types('''
        from typing import Generic, assert_type
        from typing_extensions import TypeVar
        T = TypeVar('T', default=int)
        U = TypeVar('U', default=list[T])
        class Pair(Generic[T, U]): pass
        def f():
            assert_type(Pair(), Pair[int, list[int]])
            assert_type(Pair[str](), Pair[str, list[str]])
            assert_type(Pair[str, bytes](), Pair[str, bytes])
        class BadBound[T: str = int]: pass  # E: invalid_type_parameter_default
        class BadConstraint[T: (int, str) = bytes]: pass  # E: invalid_type_parameter_default
        Later = TypeVar('Later')
        Early = TypeVar('Early', default=list[Later])
        def declarations():
            class Forward(Generic[Early, Later]): pass  # E: invalid_type_parameter_default
            class Required(Generic[T, Later]): pass  # E: invalid_type_parameter_default
    ''')


def test_declared_variance_and_parameter_identity():
    check_types('''
        from typing import Generic, TypeVar, assert_type
        Co = TypeVar('Co', covariant=True)
        Contra = TypeVar('Contra', contravariant=True)
        Inv = TypeVar('Inv')
        class Producer(Generic[Co]): pass
        class Consumer(Generic[Contra]): pass
        class Cell(Generic[Inv]): pass
        def f(pn: Producer[int], pw: Producer[float], cn: Consumer[int], cw: Consumer[float],
              n: Cell[int], w: Cell[float]):
            p: Producer[float] = pn
            bad_p: Producer[int] = pw  # E: incompatible_assignment
            c: Consumer[int] = cw
            bad_c: Consumer[float] = cn  # E: incompatible_assignment
            a: Cell[float] = n  # E: incompatible_assignment
            b: Cell[int] = w  # E: incompatible_assignment
        class First[T]:
            def get(self) -> T: raise NotImplementedError
        class Second[T]:
            def get(self) -> T: raise NotImplementedError
        def combine[A, B](a: First[A], b: Second[B]) -> tuple[A, B]:
            return a.get(), b.get()
        def first[T](x: T) -> T: return x
        def second[T](x: T) -> T: return first(x)
        def independent(i: int, s: str):
            assert_type(first(i), int)
            assert_type(second(s), str)
            assert_type(first(s), str)
            assert_type(second(i), int)
            assert_type(combine(First[int](), Second[str]()), tuple[int, str])
            assert_type(combine(First[str](), Second[int]()), tuple[str, int])
    ''')


def test_generic_parameter_scope():
    check_types('''
        from typing import TypeVar, Generic, assert_type
        T = TypeVar('T')
        def legacy(x: T) -> T: return x
        def inline[S](x: S) -> S: return x
        def good(i: int):
            assert_type(legacy(i), int)
            assert_type(inline(i), int)
        def bad():
            unbound: T  # E: invalid_annotation
        class Outer(Generic[T]):
            class Inner:
                value: list[T]  # E: invalid_annotation
            type Alias = T  # E: invalid_type_alias
    ''')


def test_reveals_and_type_assertions():
    findings = check_types('''
        from typing import Literal, assert_type, reveal_type
        from velnora.extensions import reveal_locals
        def f(union: int | str, sequence: list[str]):
            literal = 37
            assert_type(literal, Literal[37])
            assert_type(union, int | str)
            assert_type(sequence, list[str])
            assert_type(literal, str)  # E: inference_failure
            reveal_type(literal)  # E: reveal_type
            reveal_type(sequence)  # E: reveal_type
            reveal_type(union)  # E: reveal_type
            reveal_locals()  # E: reveal_type
    ''')
    by_line = {f['lineno']: f for f in findings}
    literal = by_line[9]['description']
    prefix = "Revealed type is '"
    assert literal.startswith(prefix) and literal.endswith("'"), literal
    value = literal_display_value(literal[len(prefix):-1])
    assert type(value) is int and value == 37
    assert by_line[10]['description'] == "Revealed type is 'list[str]'"
    prefix = "Revealed type is '"
    union = by_line[11]['description']
    assert union.startswith(prefix), union
    assert union.endswith("'"), union
    assert set(union[len(prefix):-1].split(' | ')) == {'int', 'str'}
    local_message = by_line[12]['message']
    local_types = {}
    label = 'Revealed local types are: (code: reveal_type)\n'
    assert label in local_message, local_message
    block = local_message.split(label, 1)[1].split('\n\n', 1)[0]
    for line in block.splitlines():
        assert line.startswith('    '), line
        name, display = line[4:].split(': ', 1)
        local_types[name] = display
    value = literal_display_value(local_types['literal'])
    assert type(value) is int and value == 37
    assert local_types['sequence'] == 'list[str]'
    assert set(local_types['union'].split(' | ')) == {'int', 'str'}


def test_type_expression_values():
    check_types('''
        from typing import TypeVar, cast, assert_type
        from typing_extensions import TypeForm
        T = TypeVar('T')
        def accepts(value: TypeForm[int]): pass
        def convert(target: TypeForm[T], value: object) -> T:
            return cast(target, value)
        def f(obj: object):
            accepts(int)
            accepts(bool)
            accepts(str)  # E: incompatible_argument
            accepts(3)  # E: incompatible_argument
            assert_type(convert(int, obj), int)
            assert_type(convert(list[str], obj), list[str])
            assert_type(convert(int | str, obj), int | str)
    ''')


def test_literals_tuples_and_container_variance():
    check_types('''
        from typing import Literal, Sequence, Iterable
        def signature(x: int) -> str: return str(x)
        def equivalent(x: int) -> str: return str(x + 1)
        def different(x: str) -> int: return len(x)
        def f(i: int, n: list[int], s: set[int], d: dict[str, int],
              fixed: tuple[int, str], many: tuple[int, ...]):
            callable_ok: Literal[signature] = equivalent
            callable_bad: Literal[signature] = different  # E: incompatible_assignment
            literal: Literal[1] = 1
            wrong_value: Literal[1] = 2  # E: incompatible_assignment
            wrong_kind: Literal[1] = True  # E: incompatible_assignment
            optional: int | None = None
            optional_i: int | None = i
            optional_bad: int | None = 'x'  # E: incompatible_assignment
            same: tuple[int, str] = fixed
            wrong_order: tuple[str, int] = fixed  # E: incompatible_assignment
            wrong_length: tuple[int] = fixed  # E: incompatible_assignment
            repeated: tuple[int, ...] = (1, 2, 3)
            repeated_bad: tuple[int, ...] = fixed  # E: incompatible_assignment
            fixed_bad: tuple[int, int] = many  # E: incompatible_assignment
            list_wide: list[float] = n  # E: incompatible_assignment
            set_wide: set[float] = s  # E: incompatible_assignment
            dict_wide: dict[str, float] = d  # E: incompatible_assignment
            readonly: Sequence[float] = n
            iterable: Iterable[float] = s
    ''')


def test_bounds_constraints_and_omitted_arguments():
    check_types('''
        from typing import Any, TypeVar, Generic, assert_type
        class Base: pass
        class Child(Base): pass
        B = TypeVar('B', bound=Base)
        C = TypeVar('C', Base, str)
        T = TypeVar('T')
        U = TypeVar('U')
        def bounded(x: B) -> B: return x
        def constrained(x: C, y: C) -> C: return x
        class Pair(Generic[T, U]): pass
        def f(child: Child, base: Base, text: str):
            assert_type(bounded(child), Child)
            assert_type(bounded(base), Base)
            bounded(text)  # E: incompatible_argument
            assert_type(constrained(child, base), Base)
            constrained(child, text)  # E: incompatible_call|incompatible_argument
            assert_type(Pair(), Pair[Any, Any])
            incomplete: Pair[int]  # E: invalid_specialization
    ''')

    check_types('''
        from typing import assert_type
        class Numeric[T: int]:
            def __init__(self, value: T): self.value = value
        def use(number: int, flag: bool, text: str):
            assert_type(Numeric(number).value, int)
            assert_type(Numeric(flag).value, bool)
            Numeric(text)  # E: incompatible_argument
    ''')


def test_cast_controls_later_checks():
    check_types('''
        from typing import cast, assert_type
        def f(text: str, number: int):
            converted = cast(int, text)
            assert_type(converted, int)
            good: int = converted
            bad: str = converted  # E: incompatible_assignment
            other = cast(list[str], number)
            assert_type(other, list[str])
            bad_target = cast(19, text)  # E: invalid_annotation
    ''')


def test_empty_type_and_exhaustiveness():
    check_types('''
        from typing import Never, NoReturn, assert_never
        def stop() -> Never: raise RuntimeError()
        def stop2() -> NoReturn: raise RuntimeError()
        def complete(x: int | str) -> int:
            if isinstance(x, int): return x
            if isinstance(x, str): return len(x)
            assert_never(x)
        def incomplete(x: int | str):
            if isinstance(x, int): return
            assert_never(x)  # E: incompatible_argument
        def never_finishes(flag: bool) -> int:
            if flag: stop()
            else: stop2()
        def invalid(x: int):
            empty: Never = x  # E: incompatible_assignment
    ''')


def test_programmatic_expression_types():
    from velnora.ast_annotator import annotate_code, annotate_file
    source = ('number = 23\ntext = "leaf"\n'
              'class Record:\n    def __init__(self):\n        self.count = 11\n'
              'record = Record()\nnumber\ntext\nrecord.count\n')
    with workspace({'expressions.py': source}) as root:
        for tree in (annotate_code(source), annotate_file(root / 'expressions.py')):
            value = literal_display_value(expression_type(tree, ast.Constant, 1, 9))
            assert type(value) is int and value == 23
            value = literal_display_value(expression_type(tree, ast.Constant, 2, 7))
            assert type(value) is str and value == 'leaf'
            value = literal_display_value(expression_type(tree, ast.Name, 7, 0))
            assert type(value) is int and value == 23
            value = literal_display_value(expression_type(tree, ast.Name, 8, 0))
            assert type(value) is str and value == 'leaf'
            value = literal_display_value(expression_type(tree, ast.Attribute, 9, 0))
            assert type(value) is int and value == 11


def test_singleton_sentinel_alternatives():
    check_types('''
        from typing_extensions import Sentinel, assert_type
        MISSING = Sentinel('MISSING')
        EMPTY = Sentinel('EMPTY')
        def f(x: int | MISSING):
            same: MISSING = MISSING
            other: MISSING = EMPTY  # E: incompatible_assignment
            ordinary: MISSING = 0  # E: incompatible_assignment
            if x is MISSING:
                assert_type(x, MISSING)
            else:
                assert_type(x, int)
    ''')


def test_inferred_variance():
    check_types('''
        from typing import Callable, Generic
        from typing_extensions import TypeVar
        T = TypeVar('T', infer_variance=True)
        class RuntimeOutput(Generic[T]):
            def get(self) -> T: raise NotImplementedError
        class Output[T]:
            def get(self) -> T: raise NotImplementedError
        class Input[T]:
            def put(self, value: T): pass
        class Both[T]:
            def get(self) -> T: raise NotImplementedError
            def put(self, value: T): pass
        class Writable[T]:
            value: T
        class CallbackInput[T]:
            def put(self, callback: Callable[[T], int]): pass
        class CallbackOutput[T]:
            def get(self) -> Callable[[T], int]: raise NotImplementedError
        def f():
            ro: RuntimeOutput[float] = RuntimeOutput[int]()
            rb: RuntimeOutput[int] = RuntimeOutput[float]()  # E: incompatible_assignment
            o: Output[float] = Output[int]()
            ob: Output[int] = Output[float]()  # E: incompatible_assignment
            i: Input[int] = Input[float]()
            ib: Input[float] = Input[int]()  # E: incompatible_assignment
            b1: Both[float] = Both[int]()  # E: incompatible_assignment
            b2: Both[int] = Both[float]()  # E: incompatible_assignment
            w1: Writable[float] = Writable[int]()  # E: incompatible_assignment
            w2: Writable[int] = Writable[float]()  # E: incompatible_assignment
            ci: CallbackInput[float] = CallbackInput[int]()
            cib: CallbackInput[int] = CallbackInput[float]()  # E: incompatible_assignment
            co: CallbackOutput[int] = CallbackOutput[float]()
            cob: CallbackOutput[float] = CallbackOutput[int]()  # E: incompatible_assignment
    ''')


def test_recursive_alias_specialization():
    check_types('''
        from typing import TypeAlias, Union
        Tree: TypeAlias = Union[int, list['Tree']]
        type Branch[T] = T | list[Branch[T]]
        def f():
            tree: Tree = [1, [2, [3]]]
            bad_tree: Tree = [1, ['leaf']]  # E: incompatible_assignment
            ints: Branch[int] = [1, [2]]
            texts: Branch[str] = ['a', ['b']]
            bad_ints: Branch[int] = [1, ['leaf']]  # E: incompatible_assignment
            bad_texts: Branch[str] = ['a', [2]]  # E: incompatible_assignment
    ''')


def test_callable_and_variadic_parameters():
    check_types('''
        from typing import Callable, Generic, ParamSpec, TypeVar, TypeVarTuple, Unpack, assert_type
        P = ParamSpec('P')
        R = TypeVar('R')
        Ts = TypeVarTuple('Ts')
        def preserve(fn: Callable[P, R]) -> Callable[P, R]: return fn
        def target(count: int, *, label: str) -> bytes: return b''
        class Row(Generic[Unpack[Ts]]):
            def __init__(self, *items: Unpack[Ts]): pass
        def f(i: int, s: str):
            wrapped = preserve(target)
            assert_type(wrapped(i, label=s), bytes)
            wrapped(s, label=s)  # E: incompatible_argument
            wrapped(i, s)  # E: incompatible_call
            assert_type(Row(i, s), Row[int, str])
            assert_type(Row(s, i), Row[str, int])
            assert_type(Row(i), Row[int])
            assert_type(Row[int, str](i, s), Row[int, str])
            Row[int, str](s, i)  # E: incompatible_argument
        type Capture[R, **P] = Callable[P, R]
        def invalid():
            valid: Capture[bytes, [int, str]]
            wrong: Capture[bytes, int]  # E: invalid_annotation
    ''')
