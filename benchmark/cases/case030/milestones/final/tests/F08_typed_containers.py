# feature: F08
"""Typed container semantics observed through public translation entries."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from F01_helpers import compile_source, require_source_error
from F08_helpers import translate_containers
from F02_helpers import python_namespace


def test_tuple_operations_and_boundaries(tmp_path):
    source = '''
def local(x: int):
    a = (x, x + 3, x - 2)
    b = tuple(a)
    c = b + (x + 9,)
    d = c * 2
    u, v, w = a
    mixed = (x, 2.5, True)
    return len(d), d[0], d[3], d[-1], u, v, w, mixed[0], mixed[1], mixed[2]

def argument(a: 'tuple[int,...]'):
    total = 0
    for i in range(len(a)):
        total += (i + 1) * a[i]
    return len(a), total
'''
    reference = python_namespace(source)
    def exercise(module):
        for x in (-7, 12):
            assert module.local(x) == reference['local'](x)
        for a in ((9,), (3, -8, 3, 17), (5, 2)):
            assert module.argument(a) == reference['argument'](a)
    for language in ('c', 'fortran'):
        translate_containers(source, language, tmp_path / language, exercise)
    returned = '''
def returned(x: int) -> 'tuple[int,...]':
    return (x - 4, x + 7, x, x - 4)
'''
    def returned_check(module):
        for x in (-3, 8):
            assert tuple(module.returned(x)) == python_namespace(returned)['returned'](x)
    translate_containers(returned, 'fortran', tmp_path / 'returned', returned_check)


def test_heterogeneous_tuple_index_rejection(tmp_path):
    template = '''
def select(i: int):
    a = (4, 2.5, True)
    return a[INDEX]
'''
    for language in ('c', 'fortran'):
        good, _ = compile_source(tmp_path / language / 'good', template.replace('INDEX', '1'), language=language)
        assert good.returncode == 0, (good.stdout, good.stderr)
        bad, path = compile_source(tmp_path / language / 'bad', template.replace('INDEX', 'i'), language=language)
        require_source_error(bad, path, 'semantic', {4})


def test_list_operations_and_readonly_boundary(tmp_path):
    source = '''
from typing import Final

def operations(x: int):
    a = [x, 3, x, -6]
    a[1] = 8
    a.append(11)
    a.insert(1, x + 2)
    a.extend([14, -3])
    removed = a.pop(2)
    last = a.pop()
    a.reverse()
    return a, removed, last, len(a), x in a, 97 in a

def cleared(x: float):
    a = [x, 2.5]
    a.clear()
    return a

def repeated(n: int):
    b = [3, -2, 3] * n
    return b

def sliced(a: Final[list[int]]):
    b = [0] * len(a)
    b[:] = a[-1::-1]
    return b

def readonly(a: Final[list[int]], b: Final[list[int]]):
    total = 0
    for i in range(len(a)):
        total += (i + 1) * a[i]
    return total, a == b
'''
    reference = python_namespace(source)
    def exercise(module):
        for x in (-9, 6):
            assert module.operations(x) == reference['operations'](x)
        assert module.cleared(3.5) == []
        for n in (0, 3):
            assert module.repeated(n) == reference['repeated'](n)
        for a, b in (([7, -2, 7, 4], [7, -2, 7, 4]), ([7, -2, 7, 4], [7, 7, -2, 4]), ([2], [2, 2])):
            assert module.readonly(a, b) == reference['readonly'](a, b)
            assert module.sliced(a) == reference['sliced'](a)
    for language in ('c', 'fortran'):
        translate_containers(source, language, tmp_path / language, exercise)


def test_c_list_mutation_and_nested_sharing(tmp_path):
    source = '''
def mutate(a: 'list[int]', n: int):
    a[0] += n
    a.append(n - 3)
    a.insert(1, n + 5)
    return a.pop(-2)

def nested(n: int):
    a = [1, 4]
    b = [8, 2]
    outer = [a, b, a]
    indexed = outer[0]
    removed = outer.pop()
    indexed[0] += n
    removed.append(n + 7)
    outer[0][1] -= n
    return a[0], a[1], len(a), outer[0][0], outer[0][-1], b[0], b[1], removed[0], removed[-1], len(outer)
'''
    reference = python_namespace(source)
    def exercise(module):
        for n in (-5, 13):
            a, b = [3, 7, -8, 3], [3, 7, -8, 3]
            assert module.mutate(a, n) == reference['mutate'](b, n)
            assert a == b
            assert module.nested(n) == reference['nested'](n)
    translate_containers(source, 'c', tmp_path / 'c', exercise)


def test_set_operations_and_boundaries(tmp_path):
    source = '''
from typing import Final

def operations(x: int):
    a = {x, 3, 7, 3}
    a.add(11)
    a.add(3)
    a.remove(7)
    a.discard(97)
    a.discard(11)
    b = a.copy()
    b.add(19)
    c = {3, 13}
    union = a.union(c)
    intersection = a.intersection(c)
    difference = a.difference(c)
    return a, b, union, intersection, difference, a.isdisjoint(c), a.isdisjoint({31}), len(a), x in a, 97 in a

def updated():
    a = {2, 5}
    a.update({5, 9})
    b = a.copy()
    b.intersection_update({5, 9, 13})
    c = a.copy()
    c.difference_update({2, 9})
    return a, b, c

def popped():
    a = {2, 5, 9}
    p = a.pop()
    return p, a

def cleared():
    a = {1.5, 4.5}
    a.clear()
    return a

def readonly(a: Final[set[int]]):
    total = 0
    for v in a:
        total += v
    return total, len(a), 5 in a
'''
    reference = python_namespace(source)
    def exercise(module):
        for x in (-4, 17):
            assert module.operations(x) == reference['operations'](x)
        assert module.updated() == reference['updated']()
        p, remaining = module.popped()
        original = {2, 5, 9}
        assert p in original
        assert remaining == original - {p}
        assert module.cleared() == set()
        for a in ({5, -2, 11}, {3, 8}):
            assert module.readonly(a) == reference['readonly'](a)
    for language in ('c', 'fortran'):
        translate_containers(source, language, tmp_path / language, exercise)
    mutable = '''
def mutate(a: 'set[int]', x: int):
    a.add(x)
    a.discard(5)
    return len(a)
'''
    def mutation_check(module):
        for x in (-3, 14):
            a, b = {5, 9, 12}, {5, 9, 12}
            assert module.mutate(a, x) == python_namespace(mutable)['mutate'](b, x)
            assert a == b
    translate_containers(mutable, 'c', tmp_path / 'mutable', mutation_check)


def test_dictionary_operations_and_target_limits(tmp_path):
    source = '''
def operations(x: int):
    a = {2: x, 7: 13}
    a[2] = x + 5
    before = a[2]
    removed = a.pop(7)
    default = a.pop(97, -11)
    return a, before, removed, default, len(a), 2 in a, 7 in a

def empty():
    a: dict[int, int] = {}
    return a

def iterated(x: int):
    a = {2: x, 7: 13, -3: 5}
    keys = 0
    values = 0
    pairs = 0
    for k in a.keys():
        keys += k
    for v in a.values():
        values += v
    for k, v in a.items():
        pairs += k * v
    return keys, values, pairs

def popped():
    a = {2: 8, 7: 13, -3: 5}
    k, v = a.popitem()
    return k, v, a

def cleared():
    a = {2: 8, 7: 13}
    a.clear()
    return a
'''
    reference = python_namespace(source)
    def exercise(module):
        for x in (-4, 17):
            assert module.operations(x) == reference['operations'](x)
            assert module.iterated(x) == reference['iterated'](x)
        k, v, remaining = module.popped()
        original = {2: 8, 7: 13, -3: 5}
        assert k in original and v == original[k]
        del original[k]
        assert remaining == original
        assert module.cleared() == {}
        assert module.empty() == {}
    for language in ('c', 'fortran'):
        translate_containers(source, language, tmp_path / language, exercise)
    strings = '''
def strings(x: int):
    a = {'red': x, 'blue': 7, 'green': 0}
    a['green'] = x + 4
    return a, a.get('red', -8), a.get('missing', -8)
'''
    def string_check(module):
        for x in (-5, 12):
            assert module.strings(x) == python_namespace(strings)['strings'](x)
    translate_containers(strings, 'c', tmp_path / 'strings', string_check)


def test_comprehensions_and_generator_sums(tmp_path):
    source = '''
from typing import Final

def constructed(n: int):
    a = [3 * i - 7 for i in range(n)]
    b = [10 * i + j for i in range(n) for j in range(3)]
    return a, b, sum(i * i - 2 for i in range(n)), sum(i - 3 * j for i in range(n) for j in range(4))

def sequence(a: Final[list[int]]):
    b = [2 * v + 1 for v in a]
    return b, sum(v * v for v in a)
'''
    reference = python_namespace(source)
    def exercise(module):
        for n in (1, 5):
            assert module.constructed(n) == reference['constructed'](n)
        for a in ([7, -3, 2, 7], [-2, 9]):
            assert module.sequence(a) == reference['sequence'](a)
    for language in ('c', 'fortran'):
        translate_containers(source, language, tmp_path / language, exercise)


def test_scalar_and_fortran_generator_extrema(tmp_path):
    source = '''
def two(a: int, b: int):
    return min(a, b), max(a, b)
'''
    def exercise(module):
        for a, b in ((-9, 5), (12, -3), (4, 4)):
            assert module.two(a, b) == (min(a, b), max(a, b))
    for language in ('c', 'fortran'):
        translate_containers(source, language, tmp_path / language, exercise)
    extended = '''
def many(a: int, b: int, c: int):
    return min(a, b, c), max(a, b, c)

def generated(n: int):
    return min((i - 3) ** 2 for i in range(n)), max(7 - i * i for i in range(n))
'''
    reference = python_namespace(extended)
    def extended_check(module):
        for a in ((-5, 9, 3), (8, -11, 2), (4, 7, -9)):
            assert module.many(*a) == reference['many'](*a)
        for n in (2, 7):
            assert module.generated(n) == reference['generated'](n)
    translate_containers(extended, 'fortran', tmp_path / 'extended', extended_check)


def test_enumeration_zip_map_and_products(tmp_path):
    source = '''
from typing import Final
from itertools import product

def transform(x: int):
    return 3 * x - 2

def fixed(x: int):
    a = (x, 3, -4)
    b = (7, -2)
    result: list[int] = []
    for i, v in enumerate(a):
        result.append(10 * i + v)
    for u, v in zip(a, b):
        result.append(10 * u + v)
    for v in map(transform, a):
        result.append(v)
    for u, v in product(a, b):
        result.append(10 * u + v)
    return result

def dynamic(a: Final[list[int]], b: Final[list[int]]):
    result: list[int] = []
    for i, v in enumerate(a):
        result.append(10 * i + v)
    for u, v in zip(a, b):
        result.append(10 * u + v)
    for v in map(transform, a):
        result.append(v)
    for u, v in product(a, b):
        result.append(10 * u + v)
    return result

def arrays(a: 'int[:]', b: 'int[:]'):
    result: list[int] = []
    for i, v in enumerate(a):
        a[i] = v + i
    for u, v in zip(a, b):
        result.append(10 * u + v)
    for v in map(transform, a):
        result.append(v)
    for u, v in product(a, b):
        result.append(10 * u + v)
    return result

def sets(x: int):
    a = {x, 3, -4}
    b = {7, -2}
    result: list[int] = []
    for v in a:
        result.append(v)
    for u, v in product(a, b):
        result.append(10 * u + v)
    return result
'''
    reference = python_namespace(source)
    def exercise(module):
        from F00_oracle import host_numpy as np
        for x in (-7, 11):
            assert module.fixed(x) == reference['fixed'](x)
            assert sorted(module.sets(x)) == sorted(reference['sets'](x))
        for a, b in (([5, -3, 9], [2, 7]), ([4], [-2, 6, 8])):
            assert module.dynamic(a, b) == reference['dynamic'](a, b)
            actual, expected = np.array(a, dtype=int), np.array(a, dtype=int)
            other = np.array(b, dtype=int)
            assert module.arrays(actual, other) == reference['arrays'](expected, other)
            np.testing.assert_array_equal(actual, expected)
    for language in ('c', 'fortran'):
        translate_containers(source, language, tmp_path / language, exercise)
