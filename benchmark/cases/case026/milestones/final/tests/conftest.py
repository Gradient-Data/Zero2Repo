# feature: F00
"""Keep assertion outcomes separate from observations of conditional branches.

The standard pytest reports retain their real passed/failed/skipped outcomes.
Uncovered branches also appear in report properties, a per-test JSON artifact,
and the terminal summary. An uncovered skip is neither a pass nor a rejection;
a partial observation retains all executed assertions without claiming the
unobserved branch. No failed report is reclassified.
"""

import json

import pytest


@pytest.fixture
def coverage_observation(request, tmp_path):
    observations = []

    def record(requirement, branch, *, observed, reason, evidence=None):
        observation = {
            'requirement': requirement,
            'branch': branch,
            'status': 'observed' if observed else 'uncovered',
            'reason': reason,
        }
        if evidence is not None:
            observation['evidence'] = evidence
        observations.append(observation)
        request.node.user_properties.append(
            ('branch_observation', json.dumps(observation, sort_keys=True)))
        (tmp_path / 'coverage-observations.json').write_text(
            json.dumps(observations, indent=2) + '\n', encoding='utf-8')

    return record


_observation_ledger = pytest.StashKey[dict]()


def pytest_configure(config):
    config.stash[_observation_ledger] = {}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    ledger = item.config.stash[_observation_ledger]
    for name, value in report.user_properties:
        if name == 'branch_observation':
            observation = json.loads(value)
            if observation['status'] == 'uncovered':
                # Properties persist across phases; show each observation once.
                ledger[(report.nodeid, value)] = {
                    'test': report.nodeid, **observation}


def pytest_terminal_summary(terminalreporter):
    ledger = terminalreporter.config.stash[_observation_ledger]
    if ledger:
        terminalreporter.section('uncovered branches (not capability passes or failures)')
    for observation in ledger.values():
        terminalreporter.write_line(json.dumps(observation, sort_keys=True))
