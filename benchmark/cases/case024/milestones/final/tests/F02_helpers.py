# feature: F02
"""Authored value protocols and observations for extensible workflow values."""
import hashlib
import json
from pathlib import Path

from velnora.value import ProxyValue, Value, get_type_registry
from _helpers import run_workflow


def restored_value(value):
    """Save and restore through the public registry without inspecting bytes."""
    registry = get_type_registry()
    return registry.deserialize(registry.get_type_name(type(value)), registry.serialize(value))


def run_value_workflow(scheduler, expression):
    """Run against the caller's repository, preserving captured failures."""
    result = run_workflow(scheduler, expression)
    if result.exception is not None:
        raise result.exception
    return result.value


class Amount(Value):
    """An author equates different decimal spellings of the same amount."""
    type_name = "f02.Amount"

    def __init__(self, spelling):
        self.spelling = spelling

    @property
    def number(self):
        return int(self.spelling)

    def get_hash(self, data=None):
        return hashlib.sha1(str(self.number).encode()).hexdigest()

    def serialize(self):
        return json.dumps(self.number).encode()

    @classmethod
    def deserialize(cls, raw_type, data):
        return cls(str(json.loads(data)))


class RawAmount:
    """An existing class whose storage is supplied by an adaptation."""
    def __init__(self, spelling):
        self.spelling = spelling

    @property
    def number(self):
        return int(self.spelling)

    def __getstate__(self):
        raise TypeError("RawAmount requires its registered serialization protocol")


class AmountAdapter(ProxyValue):
    type = RawAmount
    type_name = "f02.RawAmount"

    def get_hash(self, data=None):
        return hashlib.sha1(str(self.instance.number).encode()).hexdigest()

    def serialize(self):
        return json.dumps(self.instance.number).encode()

    @classmethod
    def deserialize(cls, raw_type, data):
        return RawAmount(str(json.loads(data)))


class Snapshot(Value):
    """Author-defined validity based on the actual contents of a local file."""
    type_name = "f02.Snapshot"

    def __init__(self, path, text):
        self.path = path
        self.text = text

    def serialize(self):
        return json.dumps([self.path, self.text]).encode()

    @classmethod
    def deserialize(cls, raw_type, data):
        return cls(*json.loads(data))

    def get_hash(self, data=None):
        return hashlib.sha1(self.serialize()).hexdigest()

    def is_valid(self):
        path = Path(self.path)
        return path.is_file() and path.read_text(encoding="utf-8") == self.text


class Interval(Value):
    type_name = "f02.Interval"

    def __init__(self, start, stop):
        self.start = start
        self.stop = stop

    @classmethod
    def parse_arg(cls, raw_type, arg):
        start, stop = map(int, arg.split(":"))
        if start >= stop:
            raise ValueError("Interval endpoints must increase")
        return cls(start, stop)

    def serialize(self):
        return json.dumps([self.start, self.stop]).encode()

    @classmethod
    def deserialize(cls, raw_type, data):
        return cls(*json.loads(data))

    def get_hash(self, data=None):
        return hashlib.sha1(self.serialize()).hexdigest()


class BoundaryAmount(Amount):
    type_name = "f02.BoundaryAmount"

    def __getstate__(self):
        return {"spelling": self.spelling}

    def __setstate__(self, state):
        self.spelling = state["spelling"]

    def preprocess(self, preprocess_args):
        return BoundaryAmount(str(self.number + 3))

    def postprocess(self, postprocess_args):
        return BoundaryAmount(str(self.number * 5))


def affine(value):
    """Ordinary importable function used as workflow data."""
    return 4 * value - 7


def halve(value):
    """A second importable function with a different meaning from affine."""
    return value / 2


def restored_in_fresh_process(value, directory):
    """Save here, restore and save again in a new interpreter, restore here.

    Only public registry methods exchange the type name and bytes, so a value
    kept alive in this process's memory cannot stand in for saved data.
    """
    import os
    import velnora
    from _helpers import run_python
    registry = get_type_registry()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    type_name = registry.get_type_name(type(value))
    source, target = directory / "saved.bin", directory / "resaved.bin"
    source.write_bytes(registry.serialize(value))
    if target.exists():
        target.unlink()
    result = run_python(
        "import sys, pathlib\n"
        "import F01_helpers, F02_helpers\n"
        "from velnora.value import get_type_registry\n"
        "registry = get_type_registry()\n"
        "value = registry.deserialize(sys.argv[1], pathlib.Path(sys.argv[2]).read_bytes())\n"
        "pathlib.Path(sys.argv[3]).write_bytes(registry.serialize(value))\n",
        cwd=directory, args=[type_name, str(source), str(target)], timeout=90,
        env={"PYTHONPATH": os.pathsep.join([
            str(Path(__file__).parent), str(Path(velnora.__file__).resolve().parent.parent),
            os.environ.get("PYTHONPATH", "")])})
    assert result.returncode == 0, result
    return registry.deserialize(type_name, target.read_bytes())
