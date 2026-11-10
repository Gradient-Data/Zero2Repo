# feature: F07
"""Pure Python declarations measured at compiled and interpreted call boundaries."""
import textwrap
from _helpers import temporary_project
from F01_helpers import translate_source, source_diagnostics
from F03_helpers import REJECTIONS
from F07_helpers import build_pure_module, run_pure_application


def test_f07_t01():
    with temporary_project() as project:
        path = build_pure_module(project, 'pure_declarations', '''
            import velora
            @velora.cfunc
            def multiply(value: velora.int) -> velora.int:
                return value * 3
            @velora.ccall
            @velora.locals(total=velora.int)
            def calculate(value: velora.int) -> velora.int:
                total = multiply(value) + 2
                return total
            @velora.cclass
            class Counter:
                count: velora.int
                def __init__(self, value): self.count = value
                @velora.ccall
                def advance(self, step: velora.int) -> velora.int:
                    self.count += step
                    return self.count
            def inspect(item: Counter): return item.count
        ''')
        common = textwrap.dedent('''
            assert subject.calculate(7) == 23
            assert subject.calculate(-4) == -10
            item = subject.Counter(9)
            assert item.advance(5) == 14
            assert item.advance(-8) == 6
            assert subject.inspect(item) == 6
        ''')
        run_pure_application(project, path.stem, common, interpreted=True)
        path.unlink()  # Native execution must not depend on the Python implementation file.
        run_pure_application(project, path.stem, common + REJECTIONS + '''
rejects(AttributeError, getattr, subject, 'multiply')
rejects(AttributeError, getattr, item, 'count')
rejects(TypeError, subject.calculate, '7')
rejects(TypeError, item.advance, None)
rejects(TypeError, subject.inspect, object())
assert subject.calculate(3.75) == 11
''')


def test_f07_t02():
    with temporary_project() as project:
        source = '''
            def hidden(value): return value * 4
            def exposed(value): return hidden(value) - 3
            class Reading:
                def __init__(self, value): self.value = value
                def update(self, delta):
                    self.value += delta
                    return self.value
        '''
        path = build_pure_module(project, 'augmented', source, companion='''
            cdef int hidden(int value)
            cpdef int exposed(int value)
            cdef class Reading:
                cdef readonly int value
                cpdef int update(self, int delta)
        ''')
        run_pure_application(project, path.stem, '''
            assert subject.exposed(6) == 21
            item = subject.Reading(12)
            assert item.update(-5) == 7
            assert item.value == 7
        ''', interpreted=True)
        path.unlink()
        run_pure_application(project, path.stem, REJECTIONS + '''
assert subject.exposed(6.75) == 21
assert subject.exposed(-2) == -11
rejects(TypeError, subject.exposed, '6')
rejects(AttributeError, getattr, subject, 'hidden')
item = subject.Reading(12.75)
assert item.value == 12
assert item.update(-5.5) == 7
assert item.value == 7
rejects(AttributeError, setattr, item, 'value', 99)
rejects(TypeError, item.update, None)
''')
        project.write('incompatible.pxd', 'cpdef int exposed(int value, int extra)\n')
        invalid = project.write('incompatible.py', 'def exposed(value): return value + 1\n')
        result = translate_source(project, invalid, options=('-3',))
        assert result.returncode == 1, result.text('stderr')
        assert source_diagnostics(result, invalid), result.text('stderr')


def test_f07_t03():
    with temporary_project() as project:
        path = build_pure_module(project, 'mode_status', '''
            import velora
            def status(): return velora.compiled
            def choose(value):
                if velora.compiled:
                    return value * 5 + 1
                return value - 8
        ''')
        run_pure_application(project, path.stem, '''
            assert subject.status() is False
            assert subject.choose(4) == -4
            assert subject.choose(-3) == -11
        ''', interpreted=True)
        path.unlink()
        run_pure_application(project, path.stem, '''
            assert subject.status() is True
            assert subject.choose(4) == 21
            assert subject.choose(-3) == -14
        ''')


def test_f07_t04():
    with temporary_project() as project:
        path = build_pure_module(project, 'numeric_annotations', '''
            def boolean(value: bool): return value
            def integer(value: int): return value
            def real(value: float): return value
            def imaginary(value: complex): return value
        ''')
        run_pure_application(project, path.stem, REJECTIONS + '''
for value, expected in ((None, False), ([], False), ([0], True), ('', False), ('0', True), (-3, True)):
    result = subject.boolean(value)
    assert result is expected
for value, expected in ((2**173 + 19, 2**173 + 19), (-2**161 - 7, -2**161 - 7), (7.875, 7), (-7.875, -7)):
    result = subject.integer(value)
    assert type(result) is int and result == expected
class IntegerValue:
    def __int__(self): return 37
assert subject.integer(IntegerValue()) == 37
class RealValue:
    def __float__(self): return 1.125
class ComplexValue:
    def __complex__(self): return 2.25 - 3.5j
for value, expected in ((7, 7.0), (-3.125, -3.125), (1.0000000000000002, 1.0000000000000002), (RealValue(), 1.125)):
    result = subject.real(value)
    assert type(result) is float and result == expected
for value, expected in ((7, 7+0j), (-3.125, -3.125+0j), (1.0000000000000002-2.5j, 1.0000000000000002-2.5j), (ComplexValue(), 2.25-3.5j)):
    result = subject.imaginary(value)
    assert type(result) is complex and result == expected
for call in (subject.integer, subject.real, subject.imaginary):
    for value in (None, '12', b'12', object()):
        rejects(TypeError, call, value)
''')


def test_f07_t05():
    with temporary_project() as project:
        path = build_pure_module(project, 'argument_annotations', '''
            import velora
            from typing import Optional
            @velora.cclass
            class Item:
                pass
            def item(value: Item): return value
            def optional(value: Optional[Item]): return value
            def defaulted(value: Item = None): return value
            def elements(value: list[int]): return value
            def mapping(value: dict[str, int]): return value
            def text(value: str): return value
            def immutable_bytes(value: bytes): return value
            def mutable_bytes(value: bytearray): return value
            def sequence(value: tuple[int, ...]): return value
            def mutable_set(value: set[int]): return value
            def immutable_set(value: frozenset[int]): return value
            @velora.annotation_typing(False)
            def unrestricted(value: list[int], count: int, real: float, thing: Item):
                return value, count, real, thing
        ''')
        run_pure_application(project, path.stem, REJECTIONS + '''
for call, value in ((subject.elements, ['text', None, 2.5]),
                    (subject.mapping, {3: 'text', None: object()}),
                    (subject.text, 'hello'), (subject.immutable_bytes, b'hello'),
                    (subject.mutable_bytes, bytearray(b'hello')), (subject.sequence, (None, 'x')),
                    (subject.mutable_set, {1, 'x'}), (subject.immutable_set, frozenset({1, 'x'}))):
    assert call(value) is value
    rejects(TypeError, call, None)
    rejects(TypeError, call, 17)
    derived = type('Derived', (type(value),), {})
    rejects(TypeError, call, derived(value))
item = subject.Item()
class DerivedItem(subject.Item): pass
child = DerivedItem()
assert subject.item(item) is item
assert subject.item(child) is child
rejects(TypeError, subject.item, None)
rejects(TypeError, subject.item, object())
assert subject.optional(None) is None
assert subject.optional(child) is child
assert subject.defaulted() is None
assert subject.defaulted(None) is None
assert subject.defaulted(item) is item
for values in ((None, 'not integer', b'not real', object()), (('tuple',), 2.5, None, 'not item')):
    result = subject.unrestricted(*values)
    assert all(actual is expected for actual, expected in zip(result, values))
''')
