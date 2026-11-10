# feature: F18
"""Real array sources with controllable access and delegating readers."""
from F16_helpers import assert_coordinate_mapping, coordinate_points
from velnora_indexing import basic_reader


class F18Source:
    """Read real NumPy data, optionally denying access to its values."""

    def __init__(self, data, *, readable=True):
        self.data = data
        self.shape = data.shape
        self.dtype = data.dtype
        self.readable = readable

    def __getitem__(self, key):
        if not self.readable:
            raise PermissionError("Source values are currently inaccessible")
        return self.data[key]


class F18ReaderFailure(RuntimeError):
    """An application reader's public failure."""


class F18DelegatingReader:
    """Execute actual reads through the public conservative reader."""

    def __init__(self):
        self.fail = False

    def read_into(self, source, context, out, /):
        if self.fail:
            raise F18ReaderFailure("Application reader failed")
        basic_reader.read_into(source, context, out)
