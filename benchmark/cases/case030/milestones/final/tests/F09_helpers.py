# feature: F09
"""Source programs for object acceptance through public translation entries."""

OBJECT_SOURCE = '''
import numpy as np

class State:
    def __init__(self, value: int, size: int):
        self.value = value
        self.data = np.full(size, value, dtype=int)
        self.initialize(value)

    def initialize(self, value: int):
        self.extra = value * 3 + 1

    def update(self, amount: int):
        self.value += amount
        self.data[:] += amount
        self.extra -= amount

    @property
    def total(self):
        return self.value + self.extra
'''

REFERENCE_SOURCE = '''
class Buffer:
    def __init__(self, data: 'float[:]'):
        self.data = data
        self.edits = 0

    def change(self, index: int, value: float):
        self.data[index] = value
        self.edits += 1

class Holder:
    def __init__(self, item: Buffer):
        self.item = item

    def get(self):
        return self.item

    def change(self, index: int, value: float):
        self.item.change(index, value)

def identity(item: Buffer):
    return item

def change(item: Buffer, index: int, value: float):
    item.change(index, value)

def make(data: 'float[:]'):
    return Buffer(data)
'''

# This is user input generation, not a model of the translator. Python executes
# the same class definitions independently to supply the behavioral oracle.
OPERATOR_SPECS = (
    ('add', '+'), ('sub', '-'), ('mul', '*'), ('truediv', '/'),
    ('pow', '**'), ('lshift', '<<'), ('rshift', '>>'),
    ('and', '&'), ('or', '|'),
)


def operator_program():
    source = '''
class Number:
    def __init__(self, value: int):
        self.value = value

    def __len__(self):
        return self.value + 2

    def __getitem__(self, index: int):
        return self.value * 3 - index * 2

    def __contains__(self, item: int):
        return item == self.value + 1
'''
    for name, symbol in OPERATOR_SPECS:
        source += f'''
    def __{name}__(self, other: int):
        return Number(int(self.value {symbol} other) + 3)

    def __r{name}__(self, other: int):
        return Number(int(other {symbol} self.value) + 5)

    def __i{name}__(self, other: int):
        self.value = int(self.value {symbol} other) + 7
        return self
'''
    # The original omits power syntax dispatch and does not visit custom
    # indexing arguments. Explicit calls preserve the method behavior checks;
    # the unsupported syntax obligations are recorded in the feature ledger.
    for name, symbol in OPERATOR_SPECS:
        direct = 'obj.__pow__(other)' if name == 'pow' else f'obj {symbol} other'
        reflected = 'obj.__rpow__(other)' if name == 'pow' else f'other {symbol} obj'
        update = 'obj.__ipow__(other)' if name == 'pow' else f'obj {symbol}= other'
        source += f'''
def direct_{name}(value: int, other: int):
    obj = Number(value)
    result = {direct}
    return result.value

def reflected_{name}(value: int, other: int):
    obj = Number(value)
    result = {reflected}
    return result.value

def inplace_{name}(value: int, other: int):
    obj = Number(value)
    {update}
    return obj.value
'''
    source += '''
def collection(value: int, index: int, item: int):
    obj = Number(value)
    selected = obj.__getitem__(index)
    return len(obj), selected, item in obj
'''
    return source
