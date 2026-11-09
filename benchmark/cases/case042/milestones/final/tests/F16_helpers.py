# feature: F16
"""Finite coordinate observations and independent ndsel conformance vectors."""
from importlib.metadata import version
from itertools import product
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import pytest
from _helpers import invoke, make_env, run_command


# The root distribution does not install this independently published package.
# Always build the current product, never an image's preinstalled implementation.
# Keep the installation alive for this Python process; build failures propagate.
_coordinate_installation = TemporaryDirectory(prefix="f16-coordinate-package-")
_coordinate_package_source = Path.cwd() / "packages" / "velnora-indexing"
_coordinate_build = run_command(
    [sys.executable, "-m", "pip", "install", "--no-index", "--no-deps",
     "--no-build-isolation", "--no-cache-dir", "--target",
     _coordinate_installation.name, str(_coordinate_package_source)],
    env=make_env({"SETUPTOOLS_SCM_PRETEND_VERSION": version("velnora")}),
    timeout=120,
)
_coordinate_build.check_returncode()
sys.path.insert(0, _coordinate_installation.name)

from velnora_indexing import IndexTransform, NdselError, normalize_ndsel


def coordinate_points(lower, upper):
    """Enumerate a caller-specified finite rectangle, including scalar rank."""
    return list(product(*(range(lo, hi) for lo, hi in zip(lower, upper, strict=True))))


def assert_coordinate_mapping(transform, lower, upper, expected):
    """Check public bounds and every mapped coordinate against caller data."""
    assert transform.domain.inclusive_min == tuple(lower)
    assert transform.domain.exclusive_max == tuple(upper)
    assert transform.domain.shape == tuple(b-a for a, b in zip(lower, upper, strict=True))
    points = coordinate_points(lower, upper)
    assert len(points) == len(expected)
    actual = [invoke(transform.apply, point).value for point in points]
    assert actual == [tuple(point) for point in expected]


def executable_message(message):
    """Normalize and lower through public message and exchange entries."""
    return IndexTransform.from_json(invoke(normalize_ndsel, message).value)


def ndsel_refused(entry, message, reason):
    """Require the public failure carrier and its structured reason code."""
    with pytest.raises(NdselError) as error:
        invoke(entry, message)
    assert error.value.reason in ({reason} if isinstance(reason, str) else set(reason)), error.value.reason


# Independent source: zarr-developers/ndsel, conformance/slice.json at
# 49b9e1db1ca93c55f320b025a666367de87a9014 (1.0-draft.2 section 5.3).
# Vendored provenance is packages/velnora-indexing/tests/conformance/PROVENANCE.md.
# Columns: start, stop, step, input lower, input upper, source coordinates.
# These are fixed standard vectors, not outputs computed by the tested product.
NDSEL_SLICE_VECTORS = (
    (5, 10, 1, 5, 10, (5, 6, 7, 8, 9)),
    (4, 10, 2, 2, 5, (4, 6, 8)),
    (5, 10, 2, 2, 5, (5, 7, 9)),
    (-9, 5, 2, -4, 3, (-9, -7, -5, -3, -1, 1, 3)),
    (15, 5, -2, -7, -2, (15, 13, 11, 9, 7)),
    (15, 5, -4, -3, 0, (15, 11, 7)),
    (-2, -9, -3, 0, 3, (-2, -5, -8)),
    (5, 5, -1, -5, -5, ()),
)
