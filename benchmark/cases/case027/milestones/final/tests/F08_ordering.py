# feature: F08
from _helpers import lf_lines
import os
import time
from _helpers import make_tree, run_trisift

# F08.T01 regression — FP-08.01, FP-03.16
def test_listing_timestamp_sorting(tmp_path):
    root = make_tree(tmp_path / "w", {"a.txt": "a\n", "b.txt": "b\n", "c.txt": "c\n"})
    order = ["c.txt", "a.txt", "b.txt"]
    now = time.time()
    for i, p in enumerate(order):
        os.utime(root / p, (now + 1000 + i * 10, now - 1000 + i * 10))
    for key in ("modified", "accessed"):
        for flag, names in (("--sort", order), ("--sortr", order[::-1])):
            r = run_trisift(["--files", "--no-index", flag, key, "."], cwd=root)
            assert r.code == 0 and lf_lines(r.out) == ["./" + p for p in names]
