# feature: F05
"""Extension instances observed through compiled callers and Python operations."""
from F02_helpers import check_python_execution
from F03_helpers import REJECTIONS


def test_f05_t01():
    check_python_execution('''
        cdef class Record:
            cdef int hidden
            cdef public int number
            cdef readonly object label
            cdef object payload
            cdef int* pointer
            def __call__(self, value):
                return self.hidden + self.number + value
        def state(Record item):
            return item.hidden, item.number, item.label, item.payload, item.pointer == NULL
        def update(Record item, int value, payload):
            item.hidden = value
            item.number = value * 2
            item.label = payload
            item.payload = payload
    ''', REJECTIONS + '''
def exercise(s):
    item = s.Record()
    assert s.state(item) == (0, 0, None, None, True)
    assert item.number == 0 and item.label is None
    rejects(AttributeError, getattr, item, 'hidden')
    rejects(AttributeError, setattr, item, 'hidden', 5)
    rejects(AttributeError, getattr, item, 'payload')
    for value in (7, -4):
        payload = [value]
        s.update(item, value, payload)
        assert s.state(item) == (value, value * 2, payload, payload, True)
        assert item.label is payload
        assert item(9) == value * 3 + 9
        item.number = value + 1
        assert s.state(item)[1] == value + 1
        rejects(AttributeError, setattr, item, 'label', 'forbidden')
        assert item.label is payload
''', reference=False)


def test_f05_t02():
    check_python_execution('''
        cdef class Fixed:
            cdef public int value
        cdef class Dynamic:
            cdef dict __dict__
            cdef public int value
    ''', REJECTIONS + '''
def exercise(s):
    fixed = s.Fixed()
    fixed.value = 17
    assert fixed.value == 17
    rejects(AttributeError, setattr, fixed, 'extra', [3])
    class Child(s.Fixed):
        pass
    for item in (s.Dynamic(), Child()):
        for name, value in (('extra', [3]), ('other', {'x': 8})):
            setattr(item, name, value)
            assert getattr(item, name) is value
        item.value = -9
        assert item.value == -9
''', reference=False)


def test_f05_t03():
    check_python_execution('''
        cdef class Managed:
            cdef object stored
            cdef public object events
            def __init__(self):
                self.stored = 4
                self.events = []
            property value:
                def __get__(self):
                    self.events.append('read')
                    return self.stored * 3
                def __set__(self, value):
                    self.events.append(('write', value))
                    self.stored = value + 2
                def __del__(self):
                    self.events.append('delete')
                    self.stored = -1
            property read_only:
                def __get__(self):
                    return self.stored
            property write_only:
                def __set__(self, value):
                    self.stored = value
    ''', REJECTIONS + '''
def exercise(s):
    item = s.Managed()
    assert item.value == 12
    item.value = 5
    assert item.value == 21 and item.read_only == 7
    del item.value
    assert item.value == -3
    assert item.events == ['read', ('write', 5), 'read', 'delete', 'read']
    rejects(AttributeError, setattr, item, 'read_only', 4)
    rejects(AttributeError, delattr, item, 'read_only')
    rejects(AttributeError, getattr, item, 'write_only')
    rejects((AttributeError, NotImplementedError), delattr, item, 'write_only')
    item.write_only = 13
    assert item.read_only == 13
''', reference=False)


def test_f05_t04():
    check_python_execution('''
        cdef class Base:
            cdef public int number
            def __init__(self, number):
                self.number = number
            cdef int native(self, int x):
                return self.number + x
            cpdef dual(self, x):
                return self.number - x
        cdef class Derived(Base):
            cdef int native(self, int x):
                return self.number * x
            cpdef dual(self, x):
                return self.number + 2 * x
        def invoke(Base item, int x):
            return item.native(x), item.dual(x)
    ''', '''
def exercise(s):
    class Child(s.Derived):
        def dual(self, x):
            return self.number - 3 * x
    for number, x in ((7, 4), (-5, 3)):
        base, derived, child = s.Base(number), s.Derived(number), Child(number)
        assert base.dual(x) == number - x
        assert derived.dual(x) == number + 2 * x
        assert child.dual(x) == number - 3 * x
        assert s.invoke(base, x) == (number + x, number - x)
        assert s.invoke(derived, x) == (number * x, number + 2 * x)
        assert s.invoke(child, x) == (number * x, number - 3 * x)
''', reference=False)


def test_f05_t05():
    # The actual Python type-definition entry is allowed to reject the layout.
    check_python_execution('''
        cdef class Left:
            cdef public int left
        cdef class Right:
            cdef public double right
    ''', REJECTIONS + '''
def exercise(s):
    class Mixin:
        def read(self):
            return self.left + 6
    class Valid(s.Left, Mixin):
        pass
    item = Valid()
    item.left = 11
    assert item.read() == 17
    def incompatible():
        class Invalid(s.Left, s.Right):
            pass
        return Invalid()
    rejects(TypeError, incompatible)
''', reference=False)


def test_f05_t06():
    check_python_execution('''
        cdef class Protocols:
            cdef public object values
            cdef public object events
            def __init__(self, values):
                self.values = list(values)
                self.events = []
            def __sub__(self, other):
                return self.values[0] - other
            def __rsub__(self, other):
                return other - self.values[0]
            def __richcmp__(self, other, int op):
                if op == 0: return self.values[0] < other
                if op == 1: return self.values[0] <= other
                if op == 2: return self.values[0] == other
                if op == 3: return self.values[0] != other
                if op == 4: return self.values[0] > other
                if op == 5: return self.values[0] >= other
            def __int__(self): return self.values[0]
            def __float__(self): return self.values[0] / 2.0
            def __bool__(self): return bool(self.values)
            def __len__(self): return len(self.values)
            def __iter__(self): return iter(self.values)
            def __getitem__(self, key): return self.values[key]
            def __setitem__(self, key, value): self.values[key] = value
            def __delitem__(self, key): del self.values[key]
            def __enter__(self):
                self.events.append('enter')
                return self.values
            def __exit__(self, kind, value, tb):
                self.events.append((kind, value.args if value is not None else None))
                return False
    ''', REJECTIONS + '''
def exercise(s):
    for number in (9, -6):
        item = s.Protocols([number, 4, 7])
        assert item - 2 == number - 2
        assert 2 - item == 2 - number
        for other in (number - 1, number, number + 1):
            assert (item < other, item <= other, item == other,
                    item != other, item > other, item >= other) == (
                        number < other, number <= other, number == other,
                        number != other, number > other, number >= other)
        assert int(item) == number and float(item) == number / 2.0
        assert bool(item) and len(item) == 3
        assert list(item) == [number, 4, 7]
        assert item[1:] == [4, 7]
        item[1] = 12
        del item[2]
        assert list(item) == [number, 12]
        with item as values:
            assert values is item.values
            values.append(18)
        def fail():
            with item:
                raise LookupError('payload')
        rejects(LookupError, fail)
        assert item.events == ['enter', (None, None), 'enter', (LookupError, ('payload',))]
        assert list(item) == [number, 12, 18]
    assert not s.Protocols([])
''', reference=False)


def test_f05_t07():
    check_python_execution('''
        from libc.stdio cimport FILE, fopen, fclose
        from posix.stdio cimport fileno
        cdef class Resource:
            cdef FILE* handle
            cdef public object events
            def __cinit__(self, path, events):
                self.events = events
                self.handle = fopen(path, "wb")
                if self.handle == NULL:
                    raise OSError("Unable to open resource")
                events.append('native')
            def __init__(self, path, events):
                events.append('python')
            def descriptor(self):
                return fileno(self.handle)
            def __dealloc__(self):
                if self.handle != NULL:
                    fclose(self.handle)
    ''', '''
import os
import tempfile

def exercise(s):
    with tempfile.TemporaryDirectory() as directory:
        path = os.fsencode(os.path.join(directory, 'resource'))
        for bypass in (False, True):
            events = []
            if bypass:
                item = s.Resource.__new__(s.Resource, path, events)
            else:
                item = s.Resource(path, events)
            assert events == (['native'] if bypass else ['native', 'python'])
            descriptor = item.descriptor()
            os.fstat(descriptor)
            del item
            try:
                os.fstat(descriptor)
            except OSError as error:
                import errno
                assert error.errno == errno.EBADF
            else:
                raise AssertionError('Native cleanup left the resource open')
''', reference=False)


def test_f05_t08():
    check_python_execution('''
        cdef class Owner:
            cdef object held
            def __init__(self, value): self.held = value
            def get(self): return self.held
    ''', '''
import gc
import weakref

def exercise(s):
    class Payload:
        def __init__(self, number): self.number = number
        def compute(self, x): return self.number + x
    for cyclic in (False, True):
        payload = Payload(23)
        reference = weakref.ref(payload)
        owner = s.Owner(payload)
        if cyclic:
            payload.owner = owner
        del payload
        gc.collect()
        assert reference() is not None
        assert owner.get() is reference()
        assert owner.get().compute(8) == 31
        owner.get().number = -9
        assert owner.get().compute(8) == -1
        if cyclic:
            assert owner.get().owner is owner
        # Keep the cycle intact: removing its link would only test refcounting.
        del owner
        gc.collect()
        assert reference() is None, 'Unreachable owned payload was retained'
''', reference=False)


def test_f05_t09():
    check_python_execution('''
        from typing import Optional
        cdef class Target:
            pass
        cdef class Derived(Target):
            pass
        cdef class Other:
            pass
        def argument(Target value): return value
        def nonnull(Target value not None): return value
        def assignment(value):
            cdef Target item = value
            return item
        def checked(value): return <Target?>value
        def annotated(value: Target): return value
        def optional(value: Optional[Target]): return value
        def defaulted(value: Target = None): return value
    ''', REJECTIONS + '''
def exercise(s):
    class Child(s.Target): pass
    entries = (s.argument, s.nonnull, s.assignment, s.checked, s.annotated, s.optional, s.defaulted)
    for value in (s.Target(), s.Derived(), Child()):
        for entry in entries:
            assert entry(value) is value
    for value in (s.Other(), object(), 17):
        for entry in entries:
            rejects(TypeError, entry, value)
    for entry in (s.argument, s.assignment, s.optional, s.defaulted):
        assert entry(None) is None
    for entry in (s.nonnull, s.annotated, s.checked):
        rejects(TypeError, entry, None)
    assert s.defaulted() is None
''', reference=False)


def test_f05_t10():
    check_python_execution('''
        from cpython.buffer cimport Py_buffer
        cdef class Exporter:
            cdef int storage[6]
            cdef Py_ssize_t shape[1]
            cdef Py_ssize_t strides[1]
            cdef public object events
            cdef public bint readonly, refuse
            def __init__(self, values, readonly=False):
                self.storage[:] = values
                self.shape[0] = 3
                self.strides[0] = 2 * sizeof(int)
                self.events = []
                self.readonly = readonly
            def snapshot(self): return list(self.storage)
            def put(self, int index, int value): self.storage[index] = value
            def __getbuffer__(self, Py_buffer* view, int flags):
                if self.refuse:
                    raise BufferError("Acquisition refused")
                self.events.append('acquire')
                view.buf = <void*> self.storage
                view.obj = self
                view.len = 3 * sizeof(int)
                view.itemsize = sizeof(int)
                view.readonly = self.readonly
                view.ndim = 1
                view.format = "i"
                view.shape = self.shape
                view.strides = self.strides
                view.suboffsets = NULL
                view.internal = NULL
            def __releasebuffer__(self, Py_buffer* view):
                self.events.append('release')
    ''', REJECTIONS + '''
import struct

def exercise(s):
    for readonly in (False, True):
        item = s.Exporter([2, 90, 5, 91, 8, 92], readonly)
        view = memoryview(item)
        assert view.format == 'i'
        assert view.itemsize == struct.calcsize('@i')
        assert view.shape == (3,) and view.strides == (2 * view.itemsize,)
        assert view.readonly == readonly
        assert view.tolist() == [2, 5, 8]
        assert item.events == ['acquire']
        item.put(2, -11)
        assert view[1] == -11
        if readonly:
            rejects(TypeError, view.__setitem__, 1, 17)
            assert item.snapshot() == [2, 90, -11, 91, 8, 92]
        else:
            view[2] = 37
            assert item.snapshot() == [2, 90, -11, 91, 37, 92]
        view.release()
        assert item.events == ['acquire', 'release']
        item.refuse = True
        rejects(BufferError, memoryview, item)
''', reference=False)
