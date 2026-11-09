# feature: F17
"""Real history workloads and public command/screen observations."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import velnora
from velnora import File, task
from velnora.cli import VelnoraClient
from _helpers import execute_client, read_log_json, run_process
from F06_helpers import history_scheduler


@task(namespace="f17.alpha", name="adjust", version="edition-one", tags=[("f17.task.selection", "left")])
def adjust_left(number):
    return number + 6


@task(namespace="f17.beta", name="adjust", version="edition-two", tags=[("f17.task.selection", "right")])
def adjust_right(number):
    return number * 5


@task(namespace="f17.history")
def pair(number):
    return [adjust_left(number), adjust_right(number)]


@task(namespace="f17.files", version="file-edition")
def produce(path, text):
    file = File(path)
    file.write(text)
    return file


@task(namespace="f17.files")
def consume(file):
    return file.read().upper() + "!"


@task(namespace="f17.files")
def file_flow(path, text):
    return consume(produce(path, text))


@task(namespace="f17.live", cache=False)
def wait_for_release(marker, release):
    Path(marker).write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + 40
    while not Path(release).exists():
        if time.monotonic() > deadline:
            raise TimeoutError("Release signal was not received")
        time.sleep(0.05)
    return 37


def history_log(directory, *options, json_output=True):
    """Read the selected carrier directly; command failures never mean absence."""
    output = io.StringIO()
    argv = ["velnora", "--config", str(directory), "log", "--no-pager"]
    if json_output:
        argv += ["--format", "json"]
    result = execute_client(VelnoraClient(stdout=output), argv + list(options))
    assert result.exception is None, result
    return read_log_json(output.getvalue()) if json_output else output.getvalue()


def record_key(row):
    return row["id"] if row["_type"] in ("Job", "Execution") else row["value_hash"]


@contextlib.contextmanager
def running_history(directory):
    """Keep a real CLI execution in progress while a separate client queries it."""
    marker, release = directory / "started", directory / "release"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(Path(__file__).parent),
        str(Path(velnora.__file__).resolve().parent.parent), env.get("PYTHONPATH", "")])
    process = subprocess.Popen([sys.executable, "-c", "from velnora.cli import main; main()", "--config", str(directory),
        "run", __file__, "f17.live.wait_for_release", "--marker", str(marker),
        "--release", str(release)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env)
    try:
        deadline = time.monotonic() + 25
        while not marker.exists():
            if process.poll() is not None:
                out, err = process.communicate()
                raise AssertionError((process.returncode, out, err))
            assert time.monotonic() < deadline, "Live task did not start"
            time.sleep(0.05)
        yield
    finally:
        release.write_text("release", encoding="utf-8")
        try:
            out, err = process.communicate(timeout=15)
            assert process.returncode == 0, (out, err)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


def screen_text(app):
    """Read rendered terminal text via the public SVG screenshot export."""
    root = ET.fromstring(app.export_screenshot())
    lines = {}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "text":
            lines.setdefault(node.attrib["y"], []).append(
                "".join(node.itertext()).replace("\xa0", " "))
    return "\n".join("".join(parts) for parts in lines.values())


def history_console(directory, route=()):
    """Construct the product's public terminal application on the real repository."""
    from argparse import Namespace
    from velnora.console.app import VelnoraApp
    return VelnoraApp(history_scheduler(directory), Namespace(), list(route), ["velnora", "console"])


def inspection_process(argv, **options):
    """Keep the fresh inspector on the same product tree as the query client."""
    return run_process(argv, env={"PYTHONPATH": os.pathsep.join([
        str(Path(__file__).parent), str(Path(velnora.__file__).resolve().parent.parent),
        os.environ.get("PYTHONPATH", "")])}, **options)
