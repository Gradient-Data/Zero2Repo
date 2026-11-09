# feature: F10
"""Real buffer inputs and independent Python buffer consumers."""
BUFFER_DRIVER = '''
from array import array
from itertools import product
from math import prod
import struct

def int_buffer(shape, values=None):
    if values is None:
        values = range(prod(shape))
    storage = array('i', values)
    return memoryview(storage).cast('B').cast('i', shape=shape)

def check_layout(value, shape, order):
    consumer = memoryview(value)
    assert consumer.shape == tuple(shape)
    assert consumer.format == 'i' and not consumer.readonly
    assert consumer.itemsize == struct.calcsize('@i')
    strides = [0] * len(shape)
    stride = consumer.itemsize
    axes = range(len(shape) - 1, -1, -1) if order == 'c' else range(len(shape))
    for axis in axes:
        strides[axis] = stride
        stride *= shape[axis]
    assert consumer.strides == tuple(strides)
    assert tuple(value.shape) == consumer.shape
    assert tuple(value.strides) == consumer.strides
    assert value.itemsize == consumer.itemsize
    return consumer
'''

# An actual owning exporter with a pointer table and separately addressed rows.
# It supplies data, not canned observations of the memoryview implementation.
ROW_EXPORTER = '''
from cpython.buffer cimport Py_buffer
cdef class RowBuffer:
    cdef int storage[3][4]
    cdef int* rows[3]
    cdef Py_ssize_t shape[2]
    cdef Py_ssize_t strides[2]
    cdef Py_ssize_t suboffsets[2]
    def __cinit__(self):
        cdef int i, j
        for i in range(3):
            self.rows[i] = &self.storage[i][0]
            for j in range(4):
                self.storage[i][j] = 10 * i + j
        self.shape[0], self.shape[1] = 3, 4
        self.strides[0], self.strides[1] = sizeof(int*), sizeof(int)
        self.suboffsets[0], self.suboffsets[1] = 0, -1
    def __getbuffer__(self, Py_buffer* output, int flags):
        output.buf = <void*> self.rows
        output.obj = self
        output.len = 12 * sizeof(int)
        output.itemsize = sizeof(int)
        output.readonly = False
        output.ndim = 2
        output.format = 'i'
        output.shape = self.shape
        output.strides = self.strides
        output.suboffsets = self.suboffsets
        output.internal = NULL
    def snapshot(self):
        return [[self.storage[i][j] for j in range(4)] for i in range(3)]
'''
