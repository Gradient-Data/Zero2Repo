# feature: F09
"""Acceptance of supplied native C++ semantics through compiled bindings."""
import pytest
from _helpers import temporary_project
from F01_helpers import translate_source, source_diagnostics
from F03_helpers import REJECTIONS
from F06_helpers import run_cooperating_application
from F09_helpers import build_cpp_binding


HEADER = r'''
#include <string>
#include <stdexcept>
#include <new>
#include <typeinfo>
#include <ios>
#include <cstdio>
struct Number {
    int value;
    Number(): value(0) {}
    Number(int x): value(x) {}
    int choose(int x) { value += x; return value * 3; }
    double choose(double x) { return value + x / 2; }
    Number operator+(const Number& other) const { return Number(value-other.value); }
};
struct Base {
    virtual int read() { return 5; }
    virtual ~Base() {}
};
struct Derived: Base {
    int value;
    Derived(int x): value(x) {}
    int read() override { return value * 4; }
};
template<class T> struct Box {
    T value;
    Box(): value() {}
    Box(T x): value(x) {}
    T apply(T x) { value = value * 2 + x; return value; }
};
struct Resource {
    FILE* stream;
    Resource(): stream(nullptr) {}
    Resource(const std::string& path): stream(nullptr) { open(path); }
    void open(const std::string& path) {
        stream = std::fopen(path.c_str(), "w");
        if (!stream) throw std::runtime_error("resource open failed");
        std::fputs("open\n", stream); std::fflush(stream);
    }
    void use(int x) { std::fprintf(stream, "%d\n", x); std::fflush(stream); }
    ~Resource() { if (stream) { std::fputs("closed\n", stream); std::fclose(stream); } }
};
inline int native_call(int kind, int value) {
    switch(kind) {
        case 0: return value * 3 + 1;
        case 1: throw std::bad_alloc();
        case 2: throw std::invalid_argument("authored invalid argument");
        case 3: throw std::domain_error("authored domain error");
        case 4: throw std::out_of_range("authored range error");
        case 5: throw std::overflow_error("authored overflow error");
        case 6: throw std::range_error("authored arithmetic range error");
        case 7: throw std::underflow_error("authored underflow error");
        case 8: throw std::bad_cast();
        case 9: throw std::ios_base::failure("authored io error");
        default: throw std::runtime_error("authored runtime explanation");
    }
}
'''

SOURCE = '''
from libcpp.string cimport string
from libcpp.vector cimport vector
from libcpp.list cimport list as cpp_list
from libcpp.set cimport set as cpp_set
from libcpp.unordered_set cimport unordered_set
from libcpp.map cimport map as cpp_map
from libcpp.unordered_map cimport unordered_map
from libcpp.utility cimport pair
from libcpp.complex cimport complex as cpp_complex
from libcpp.deque cimport deque

cdef int custom_translation() except *:
    raise LookupError("author selected failure")

cdef extern from "native.hpp":
    cppclass Number:
        Number() except +
        Number(int) except +
        int value
        int choose(int)
        double choose(double)
        Number operator+(Number)
    cppclass Base:
        int read()
    cppclass Derived(Base):
        Derived(int) except +
    cppclass Box[T]:
        Box() except +
        Box(T) except +
        T value
        T apply(T)
    cppclass Resource:
        Resource() except +
        Resource(string) except +
        void open(string) except +
        void use(int)
    int native_call(int, int) except +
    int customized "native_call"(int, int) except +custom_translation

def objects(int x, int y, double fraction):
    cdef Number a = Number(x)
    cdef Number b = Number(y)
    cdef Number c = a + b
    cdef Derived* child = new Derived(x)
    cdef Base* parent = child
    cdef Box[int] ints = Box[int](y)
    cdef Box[double] floats = Box[double](fraction)
    try:
        initial = a.value
        chosen_int = a.choose(y)
        chosen_double = a.choose(fraction)
        a.value += 1
        return (initial, c.value, chosen_int, chosen_double, a.value,
                parent.read(), ints.apply(x), floats.apply(fraction))
    finally:
        del child

def strings(value):
    cdef string native = value
    native.append(string(b"!\\x00?", 3))
    return native

def vectors(value):
    cdef vector[int] native = value
    native.push_back(17)
    return native

def lists(value):
    cdef cpp_list[int] native = value
    native.push_front(19)
    return native

def sets(value):
    cdef cpp_set[int] native = value
    native.insert(23)
    return native

def unordered_sets(value):
    cdef unordered_set[int] native = value
    native.insert(29)
    return native

def maps(value):
    cdef cpp_map[string, int] native = value
    native[string(b"native")] = 31
    return native

def unordered_maps(value):
    cdef unordered_map[string, int] native = value
    native[string(b"native")] = 37
    return native

def pairs(value):
    cdef pair[int, double] native = value
    native.first += 7
    native.second *= 2
    return native

def complexes(value):
    cdef cpp_complex[double] native = value
    return native * cpp_complex[double](2, -1)

def nested(source, mutate):
    cdef cpp_map[string, vector[vector[int]]] native = source
    mutate()
    native[string(b"rows")][0].push_back(41)
    first = <object>native
    native[string(b"rows")][1].push_back(43)
    return first, <object>native

cdef class Owner:
    cdef Resource resource
    def __init__(self, path):
        self.resource.open(path)
    def use(self, int x):
        self.resource.use(x)

def explicit(path, int x):
    cdef Resource* item = new Resource(path)
    try:
        item.use(x)
    finally:
        del item

def iterate():
    cdef vector[int] v = [4, -3, 8]
    cdef cpp_list[int] l = [6, 2, -5]
    cdef cpp_set[int] s = [9, 3, 9]
    cdef unordered_set[int] u = [12, -4, 12]
    cdef cpp_map[int, int] m = {2: 7, -1: 5}
    cdef unordered_map[int, int] n = {6: 4, 1: 9}
    cdef deque[int] d
    d.push_back(13)
    d.push_front(-2)
    return ([x * 2 for x in v], [x + 1 for x in l],
            {x * 3 for x in s}, {x - 1 for x in u},
            {x.first: x.second * 2 for x in m},
            {x.first: x.second + 3 for x in n}, [x for x in d])

def failure(int kind, int value=0):
    return native_call(kind, value)

def custom(int kind, int value=0):
    return customized(kind, value)
'''


@pytest.fixture(scope='module')
def cpp_project():
    with temporary_project() as project:
        project.write('native.hpp', HEADER)
        build_cpp_binding(project, 'cpp_subject', SOURCE)
        yield project


def test_f09_t01(cpp_project):
    run_cooperating_application(cpp_project, '''
        import cpp_subject as s
        assert s.objects(6, 2, 1.5) == (6, 4, 24, 8.75, 9, 24, 10, 4.5)
        assert s.objects(-3, 5, -2.0) == (-3, -8, 6, 1.0, 3, -12, 7, -6.0)
    ''')
    path = cpp_project.write('c_mode.pyx', '''
cdef extern from "native.hpp":
    cppclass Number:
        Number() except +
cdef Number* value = new Number()
''')
    result = translate_source(cpp_project, path)
    assert result.returncode != 0
    assert source_diagnostics(result, path), result.text('stderr')


def test_f09_t02(cpp_project):
    run_cooperating_application(cpp_project, '''
        import cpp_subject as s
        assert s.strings(b"a\\x00bc") == b"a\\x00bc!\\x00?"
        assert s.strings(b"") == b"!\\x00?"
        assert s.vectors(iter([5, -2, 5])) == [5, -2, 5, 17]
        assert s.lists((5, -2, 5)) == [19, 5, -2, 5]
        assert s.sets([5, -2, 5]) == {5, -2, 23}
        assert s.unordered_sets([5, -2, 5]) == {5, -2, 29}
        assert s.maps({b"first": 8, b"second": -4}) == {b"first": 8, b"second": -4, b"native": 31}
        assert s.unordered_maps({b"first": 8, b"second": -4}) == {b"first": 8, b"second": -4, b"native": 37}
        assert s.pairs(iter([4, 2.5])) == (11, 5.0)
        assert s.complexes(3+4j) == 10+5j
        assert s.vectors([]) == [17]
        assert s.maps({}) == {b"native": 31}
        assert type(s.strings(b"x")) is bytes
        assert type(s.vectors([])) is list
        assert type(s.lists([])) is list
        assert type(s.sets([])) is set
        assert type(s.unordered_sets([])) is set
        assert type(s.maps({})) is dict
        assert type(s.unordered_maps({})) is dict
        assert type(s.pairs([0, 0])) is tuple
        assert type(s.complexes(0j)) is complex
    ''')


def test_f09_t03(cpp_project):
    run_cooperating_application(cpp_project, REJECTIONS + '''
import cpp_subject as s
source = {b"rows": [[2, -5], [7]], b"other": [[11]]}
def mutate():
    source[b"rows"][0].append(99)
    source[b"other"].clear()
    source[b"added"] = [[13]]
first, second = s.nested(source, mutate)
assert first == {b"rows": [[2, -5, 41], [7]], b"other": [[11]]}
assert second == {b"rows": [[2, -5, 41], [7, 43]], b"other": [[11]]}
first[b"rows"][0].append(101)
assert second[b"rows"][0] == [2, -5, 41]
assert source == {b"rows": [[2, -5, 99], [7]], b"other": [], b"added": [[13]]}
bad = object()
for call in (s.vectors, s.lists, s.sets, s.unordered_sets):
    rejects(TypeError, call, [1, bad])
for call in (s.maps, s.unordered_maps):
    rejects(TypeError, call, {bad: 1})
    rejects(TypeError, call, {b"key": bad})
rejects(TypeError, s.nested, {b"rows": [[bad], [1]]}, lambda: None)
rejects(TypeError, s.pairs, [1, bad])
rejects(ValueError, s.pairs, [1])
rejects(ValueError, s.pairs, [1, 2, 3])
''')


def test_f09_t04(cpp_project):
    run_cooperating_application(cpp_project, '''
        import cpp_subject as s
        from pathlib import Path
        import tempfile
        assert s.iterate() == ([8, -6, 16], [7, 3, -4], {27, 9}, {11, -5},
                               {2: 14, -1: 10}, {6: 7, 1: 12}, [-2, 13])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.txt'
            owner = s.Owner(bytes(path))
            assert path.read_text() == 'open\\n'
            owner.use(47)
            assert path.read_text() == 'open\\n47\\n'
            owner.use(-8)
            assert path.read_text() == 'open\\n47\\n-8\\n'
            del owner
            assert path.read_text() == 'open\\n47\\n-8\\nclosed\\n'
            path = Path(directory) / 'explicit.txt'
            s.explicit(bytes(path), 53)
            assert path.read_text() == 'open\\n53\\nclosed\\n'
    ''')


def test_f09_t05(cpp_project):
    run_cooperating_application(cpp_project, REJECTIONS + '''
import cpp_subject as s
assert s.failure(0, 7) == 22
assert s.failure(0, -4) == -11
for kind, error in [(1, MemoryError), (2, ValueError), (3, ValueError),
                    (4, IndexError), (5, OverflowError), (6, ArithmeticError),
                    (7, ArithmeticError), (8, TypeError), (9, OSError)]:
    rejects(error, s.failure, kind)
try:
    s.failure(10)
except RuntimeError as error:
    assert str(error) == 'authored runtime explanation'
else:
    raise AssertionError('Native failure was returned as a value')
''')


def test_f09_t06(cpp_project):
    run_cooperating_application(cpp_project, '''
        import cpp_subject as s
        assert s.custom(0, 9) == 28
        assert s.custom(0, -2) == -5
        for kind in (2, 4, 10):
            try:
                s.custom(kind)
            except LookupError as error:
                assert type(error) is LookupError
                assert str(error) == 'author selected failure'
            else:
                raise AssertionError('Custom translator was ignored')
    ''')
