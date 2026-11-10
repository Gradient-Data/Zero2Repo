# feature: F16
"""Author workflows and complete CLI invocations for lifecycle acceptance."""
import os
import velnora
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from velnora import Dir, File, task
from velnora.cli import VelnoraClient
from _helpers import candidate_cli_environment, execute_client, run_process


class Shade(Enum):
    amber = 3
    violet = 8


def transform(number):
    return number * 5 - 2


@task(namespace="f16")
def combine(first: int, second: int = 4, third: int = 9):
    return first * 100 + second * 10 + third


@task(namespace="f16")
def child(first: int):
    return first * 3


@task(namespace="f16")
def parent(first: int, second: int = 4, third: int = 9):
    return child(first) + second * 10 + third


@task(namespace="f16")
def scalars(raw, text: str, integer: int, real: float, flag: bool,
            shade: Shade, file: File, directory: Dir, when: datetime, func: Callable):
    return (raw + text, integer + 7, real / 2, not flag, shade.value,
            file.read(), sorted(p.name for p in Path(directory.path).iterdir()),
            when.isoformat(), func(integer))


@task(namespace="f16")
def sequences(numbers: List[int], flags: List[bool], shades: List[Shade],
              words: List, maybe: Optional[int] = None, scale: int = 3):
    return ([n * scale for n in numbers], [not f for f in flags],
            [s.value for s in shades], [w.upper() for w in words],
            None if maybe is None else maybe + 11)


@task(namespace="f16")
def unseen(value: int):
    return value + 1


@task(namespace="f16")
def dynamic(value: int, effect: str):
    with open(effect, "a") as stream:
        stream.write(str(value) + "\n")
    return unseen(value)


def lifecycle_call(directory, *arguments):
    return execute_client(VelnoraClient(),
                          ["velnora", "-c", str(directory), *map(str, arguments)],
                          cwd=directory.parent)


def lifecycle_run(directory, task_name, *arguments):
    return lifecycle_call(directory, "run", __file__, "f16." + task_name, *arguments)


def lifecycle_value(result):
    assert result.exception is None, result
    return result.value


def invalid_arguments(result):
    assert isinstance(result.exception, SystemExit), result
    assert result.exit_code == 2, result
    assert result.stderr.strip(), result


def lifecycle_process(argv, *, cwd, env=None):
    """Run the CLI against the same product tree as in-process observations."""
    environment = dict(env or {})
    environment["PYTHONPATH"] = os.pathsep.join([
        str(Path(velnora.__file__).resolve().parent.parent),
        os.environ.get("PYTHONPATH", "")])
    with candidate_cli_environment() as cli_env:
        return run_process(argv, cwd=cwd, env={**environment, **cli_env})
