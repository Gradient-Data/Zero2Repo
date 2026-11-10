# feature: F10
"""Typed memoryviews measured through compiled applications and real buffers."""
from _helpers import temporary_project
from F01_helpers import translate_source, source_diagnostics
from F02_helpers import check_python_execution
from F03_helpers import REJECTIONS
from F10_helpers import BUFFER_DRIVER, ROW_EXPORTER


def test_f10_t01():
    source = ''
    for rank in range(1, 8):
        declaration = ','.join(':' for _ in range(rank))
        index = ','.join(f'index[{axis}]' for axis in range(rank))
        source += f'''
def read_{rank}(int[{declaration}] value, index):
    return value[{index}]
def native_{rank}(index):
    cdef int storage{'[2]' * rank}
    cdef int* flat = <int*> storage
    cdef int i
    for i in range({2 ** rank}):
        flat[i] = 3 * i - 19
    cdef int[{declaration}] value = storage
    return value[{index}]
'''
    check_python_execution(source, BUFFER_DRIVER + REJECTIONS + '''
def exercise(s):
    for rank in range(1, 8):
        values = [3 * i - 19 for i in range(2 ** rank)]
        data = int_buffer((2,) * rank, values)
        reader = getattr(s, 'read_' + str(rank))
        native = getattr(s, 'native_' + str(rank))
        for index, expected in zip(product(range(2), repeat=rank), values):
            assert reader(data, index) == expected
            assert native(index) == expected
        wrong_rank = int_buffer((2,) * (rank + 1))
        rejects(ValueError, reader, wrong_rank, (0,) * rank)
    rejects(ValueError, s.read_1, array('d', [1.0, 2.0]), (0,))
''', reference=False)
    with temporary_project() as project:
        path = project.write('too_many.pyx', 'def read(int[:,:,:,:,:,:,:,:] value):\n    return 0\n')
        result = translate_source(project, path)
        assert result.returncode != 0
        assert source_diagnostics(result, path), result.text('stderr')


def test_f10_t02():
    check_python_execution('''
        def derive(int[:, :] value):
            return value[1:, ::2], value[::-1, ::-1], value.T, value[None, :, 1:]
    ''', BUFFER_DRIVER + '''
def exercise(s):
    original = int_buffer((3, 4))
    sliced, reversed_view, transposed, expanded = s.derive(original)
    assert memoryview(sliced).tolist() == [[4, 6], [8, 10]]
    assert memoryview(reversed_view).tolist() == [[11, 10, 9, 8], [7, 6, 5, 4], [3, 2, 1, 0]]
    assert memoryview(transposed).tolist() == [[0, 4, 8], [1, 5, 9], [2, 6, 10], [3, 7, 11]]
    assert memoryview(expanded).tolist() == [[[1, 2, 3], [5, 6, 7], [9, 10, 11]]]
    sliced[1, 1] = -31
    assert original[2, 2] == -31
    reversed_view[2, 0] = 42
    assert original[0, 3] == 42
    transposed[1, 1] = 57
    assert original[1, 1] == 57
    expanded[0, 0, 1] = 68
    assert original[0, 2] == 68
    original[2, 2] = 93
    assert sliced[1, 1] == reversed_view[0, 1] == transposed[2, 2] == expanded[0, 2, 1] == 93
''', reference=False)


def test_f10_t03():
    check_python_execution('''
        def derive(int[:] value):
            return value[::-2]
    ''', BUFFER_DRIVER + '''
import gc
import weakref

def exercise(s):
    owner = array('i', [5, 8, 13, 21, 34, 55])
    reference = weakref.ref(owner)
    derived = s.derive(owner)
    sibling = derived[1:]
    del owner
    gc.collect()
    assert reference() is not None
    assert list(derived) == [55, 21, 8]
    del derived
    gc.collect()
    assert reference() is not None
    assert list(sibling) == [21, 8]
    sibling[0] = -17
    assert reference()[3] == -17
    reference()[1] = 76
    assert list(sibling) == [-17, 76]
''', reference=False)


def test_f10_t04():
    source = ROW_EXPORTER + '''
from velora cimport view

def direct(int[:, :] value): return value[2, 1]
def c_order(int[:, ::1] value): return value[2, 1]
def f_order(int[::1, :] value): return value[2, 1]
def row_contiguous(int[:, ::view.contiguous] value): return value[1, 1]
def indirect(int[::view.indirect, :] value):
    value[2, 1] += 7
    return value[2, 1]
def indirect_contiguous(int[::view.indirect_contiguous, ::view.contiguous] value):
    return value[1, 2]
def generic(int[::view.generic, ::view.generic] value): return value[2, 1]
def transpose(int[:, :] value): return value.T
'''
    check_python_execution(source, BUFFER_DRIVER + REJECTIONS + '''
def exercise(s):
    direct = int_buffer((3, 4))
    assert s.direct(direct) == s.c_order(direct) == s.generic(direct) == 9
    transposed = s.transpose(int_buffer((4, 3)))
    assert s.f_order(transposed) == s.direct(transposed) == 5
    rejects((ValueError, BufferError), s.f_order, direct)
    rejects((ValueError, BufferError), s.c_order, transposed)
    strided = s.transpose(int_buffer((4, 6)))[::2, ::2]
    assert s.direct(strided) == 16
    rejects((ValueError, BufferError), s.c_order, strided)
    rejects((ValueError, BufferError), s.f_order, strided)
    rows = direct[::2]
    assert s.row_contiguous(rows) == 9
    # Row contiguity does not imply whole-array C contiguity.
    rejects((ValueError, BufferError), s.c_order, rows)
    rejects((ValueError, BufferError), s.row_contiguous, strided)
    indirect = s.RowBuffer()
    assert memoryview(indirect).tolist() == [[0, 1, 2, 3], [10, 11, 12, 13], [20, 21, 22, 23]]
    assert s.generic(indirect) == 21
    assert s.indirect_contiguous(indirect) == 12
    assert s.indirect(indirect) == 28
    assert indirect.snapshot()[2][1] == 28
    rejects((ValueError, BufferError), s.direct, indirect)
    rejects((ValueError, BufferError), s.indirect, direct)
''', reference=False)
    with temporary_project() as project:
        path = project.write('pointer_elements.pyx', 'cdef int*[:] value\n')
        result = translate_source(project, path)
        assert result.returncode != 0
        assert source_diagnostics(result, path), result.text('stderr')


def test_f10_t05():
    check_python_execution('''
        def read(const unsigned char[:] value): return [value[i] for i in range(value.shape[0])]
        def write(unsigned char[:] value, unsigned char replacement):
            value[1] = replacement
            return value[1]
    ''', REJECTIONS + '''
def exercise(s):
    writable = bytearray([3, 17, 29])
    readonly = bytes(writable)
    assert s.read(writable) == s.read(readonly) == [3, 17, 29]
    assert s.write(writable, 71) == 71
    assert writable == bytearray([3, 71, 29])
    rejects(BufferError, s.write, readonly, 71)
''', reference=False)
    with temporary_project() as project:
        path = project.write('const_write.pyx', 'def write(const int[:] value):\n    value[0] = 7\n')
        result = translate_source(project, path)
        assert result.returncode != 0
        assert source_diagnostics(result, path), result.text('stderr')


def test_f10_t06():
    check_python_execution('''
        cimport velora
        def read(int[:] value, Py_ssize_t index): return value[index]
        def uninitialised():
            cdef int[:] value
            return value[0]
        @velora.boundscheck(False)
        @velora.wraparound(False)
        @velora.initializedcheck(False)
        def unchecked(int[:] value, Py_ssize_t index): return value[index]
    ''', BUFFER_DRIVER + REJECTIONS + '''
def exercise(s):
    data = array('i', [4, -8, 15, 16])
    for index, expected in ((0, 4), (2, 15), (-1, 16), (-4, 4)):
        assert s.read(data, index) == expected
    for index in (-5, 4, 19):
        rejects(IndexError, s.read, data, index)
    rejects(UnboundLocalError, s.uninitialised)
    for index, expected in enumerate(data):
        assert s.unchecked(data, index) == expected
''', reference=False)


def test_f10_t07():
    check_python_execution('''
        def fill(int[:, :] target, int value): target[::2, 1::2] = value
        def assign(int[:, :] target, int[:, :] source): target[:, :] = source
        def assign_row(int[:, :] target, int[:] source): target[:, :] = source
    ''', BUFFER_DRIVER + REJECTIONS + '''
def exercise(s):
    target = int_buffer((3, 4))
    s.fill(target, -23)
    assert target.tolist() == [[0, -23, 2, -23], [4, 5, 6, 7], [8, -23, 10, -23]]
    s.assign_row(target, array('i', [9, 3, -5, 11]))
    assert target.tolist() == [[9, 3, -5, 11]] * 3
    s.assign(target, int_buffer((3, 1), [8, -2, 19]))
    assert target.tolist() == [[8] * 4, [-2] * 4, [19] * 4]
    s.assign(target, int_buffer((1, 4), [6, 1, 7, 2]))
    assert target.tolist() == [[6, 1, 7, 2]] * 3
    s.assign(target, int_buffer((3, 4), range(20, 32)))
    assert target.tolist() == [[20, 21, 22, 23], [24, 25, 26, 27], [28, 29, 30, 31]]
    rejects(ValueError, s.assign, target, int_buffer((2, 4)))
    rejects(ValueError, s.assign_row, target, array('i', [1, 2, 3]))
''', reference=False)


def test_f10_t08():
    check_python_execution('''
        def overlap(int[:] value, int direction):
            if direction == 0: value[1:] = value[:-1]
            elif direction == 1: value[:-1] = value[1:]
            else: value[:] = value[::-1]
        def copies(int[:, :] value):
            return value[::2, ::-1].copy(), value[::2, ::-1].copy_fortran()
    ''', BUFFER_DRIVER + '''
def exercise(s):
    for direction, expected in enumerate(([2, 2, 5, 9, 14], [5, 9, 14, 20, 20], [20, 14, 9, 5, 2])):
        data = array('i', [2, 5, 9, 14, 20])
        s.overlap(data, direction)
        assert list(data) == expected
    original = int_buffer((4, 4))
    c_copy, f_copy = s.copies(original)
    expected = [[3, 2, 1, 0], [11, 10, 9, 8]]
    for copy, order in ((c_copy, 'c'), (f_copy, 'fortran')):
        consumer = check_layout(copy, (2, 4), order)
        assert consumer.tolist() == expected
    original[0, 3] = 97
    assert c_copy[0, 0] == f_copy[0, 0] == 3
    c_copy[1, 2] = -41
    assert original[2, 1] == f_copy[1, 2] == 9
    f_copy[1, 3] = -53
    assert original[2, 0] == c_copy[1, 3] == 8
''', reference=False)


def test_f10_t09():
    check_python_execution('''
        def select(int[:, :] value): return value[1::2, ::-2]
    ''', BUFFER_DRIVER + '''
def exercise(s):
    original = int_buffer((5, 6))
    selected = s.select(original)
    consumer = memoryview(selected)
    assert tuple(selected.shape) == consumer.shape == (2, 3)
    assert tuple(selected.strides) == consumer.strides == (original.strides[0] * 2, original.strides[1] * -2)
    assert selected.itemsize == consumer.itemsize == original.itemsize
    assert selected.size == 6
    assert selected.nbytes == consumer.nbytes == 6 * original.itemsize
    assert selected.base is original
    assert consumer.format == original.format and not consumer.readonly
    assert consumer.tolist() == [[11, 9, 7], [23, 21, 19]]
    consumer[1, 1] = -67
    assert original[3, 3] == selected[1, 1] == -67
    original[1, 1] = 82
    assert consumer[0, 2] == selected[0, 2] == 82
''', reference=False)


def test_f10_t10():
    check_python_execution('''
        from velora.view cimport array
        def allocate(shape, itemsize, mode=None):
            if mode is None:
                return array(shape=shape, itemsize=itemsize, format='i')
            return array(shape=shape, itemsize=itemsize, format='i', mode=mode)
        def initialise(int[:, :] value):
            cdef Py_ssize_t i, j
            for i in range(value.shape[0]):
                for j in range(value.shape[1]):
                    value[i, j] = 10 * i - 3 * j
            return value[:, :]
    ''', BUFFER_DRIVER + REJECTIONS + '''
import sys
import importlib.abc

class NoNumpy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'numpy' or fullname.startswith('numpy.'):
            raise ImportError('NumPy is unavailable in this application')

def exercise(s):
    assert 'numpy' not in sys.modules
    sys.meta_path.insert(0, NoNumpy())
    itemsize = struct.calcsize('@i')
    for mode in (None, 'c', 'fortran'):
        owner = s.allocate((3, 4), itemsize, mode)
        typed = s.initialise(owner)
        consumer = memoryview(owner)
        assert consumer.tolist() == [[0, -3, -6, -9], [10, 7, 4, 1], [20, 17, 14, 11]]
        check_layout(typed, (3, 4), 'fortran' if mode == 'fortran' else 'c')
        consumer[1, 2] = 83
        assert typed[1, 2] == 83
        typed[2, 1] = -45
        assert consumer[2, 1] == -45
    for shape, size, mode in (((), itemsize, 'c'), ((0, 4), itemsize, 'c'), ((3, -1), itemsize, 'c'), ((3, 4), 0, 'c'), ((3, 4), -1, 'c'), ((3, 4), itemsize, 'diagonal')):
        rejects(ValueError, s.allocate, shape, size, mode)
    assert 'numpy' not in sys.modules
''', reference=False)
