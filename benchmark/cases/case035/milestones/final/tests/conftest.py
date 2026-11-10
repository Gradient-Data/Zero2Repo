"""Session configuration for the isolated end-to-end suite."""

import json

import pytest


# Keep phase timings on the controller as well as on xdist workers. These are
# observations only: they never change selection, assertions or exit status.
_PHASE_REPORTS = []


def pytest_runtest_logreport(report):
    _PHASE_REPORTS.append({
        "nodeid": report.nodeid, "phase": report.when,
        "outcome": report.outcome, "seconds": report.duration,
    })


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_sep("-", "suite phase timings (worker seconds, not wall time)")
    terminalreporter.write_line(json.dumps(_PHASE_REPORTS, sort_keys=True))


@pytest.fixture(scope="session")
def product_runtime(tmp_path_factory, request):
    from F01_helpers import prepare_product_runtime

    base = tmp_path_factory.getbasetemp()
    if hasattr(request.config, "workerinput"):
        base = base.parent
    return prepare_product_runtime(tmp_path_factory.mktemp("product") / "prepared",
                                   base / "current-product")


@pytest.fixture(scope="session", autouse=True)
def bind_product_environment(product_runtime):
    from F01_helpers import bind_product_runtime

    bind_product_runtime(product_runtime)
    yield
    bind_product_runtime(None)


@pytest.fixture(scope="session")
def current_product_wheel(product_runtime):
    return product_runtime["wheel"]
