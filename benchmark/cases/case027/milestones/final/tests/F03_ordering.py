# feature: F03
"""Ordering through every public answering path."""
from _helpers import lf_lines
import os
import time
from contextlib import nullcontext
import pytest
from _helpers import make_tree, run_trisift
from F06_helpers import build_index
from F00_observations import birthtime_ns
from F07_helpers import NoWatchServer


# F03.T20 regression — FP-03.16, FP-08.01
@pytest.mark.parametrize("mode", ["scan", "local", "server"])
def test_timestamp_and_reverse_sorting(tmp_path, mode):
    root = tmp_path / "w"
    creation = ["c.txt", "a.txt", "b.txt"]
    for name in creation:
        make_tree(root, {name: "needle\n"})
    created = {name: birthtime_ns(root / name) for name in creation}
    now = time.time()
    modified = ["b.txt", "c.txt", "a.txt"]
    accessed = ["a.txt", "b.txt", "c.txt"]
    for name in creation:
        os.utime(root / name, (now + 10000 + accessed.index(name) * 10,
                              now - 10000 + modified.index(name) * 10))
    if mode != "scan":
        build_index(root)
    with NoWatchServer(root) if mode == "server" else nullcontext():
        for key, order in (("created", creation), ("modified", modified), ("accessed", accessed)):
            for opt, expected in (("--sort", order), ("--sortr", list(reversed(order)))):
                for command in (["-l", "needle"], ["--files"]):
                    args = (["--no-index"] if mode == "scan" else []) + [opt, key, *command, "."]
                    r = run_trisift(args, cwd=root)
                    assert r.code == 0, r.describe()
                    rows = lf_lines(r.out)
                    if key == "created":
                        assert sorted(rows) == sorted("./" + p for p in creation), r.describe()
                        values = [created[p[2:]] for p in rows]
                        assert values == sorted(values, reverse=opt == "--sortr"), r.describe()
                    else:
                        assert rows == ["./" + p for p in expected], r.describe()
