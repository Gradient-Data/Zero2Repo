# feature: F06
"""Control-structure execution through the existing native workflow driver."""
from _helpers import write_file
from F01_helpers import execute_source
from F03_helpers import library_outcomes
from F04_helpers import TRACE_LIBRARY, workflow_events
from F05_helpers import lifecycle_cases


def control_run(directory, cases, expected, *, variables='', keywords=''):
    source = ('*** Settings ***\nLibrary    Trace.py\n'
              '*** Variables ***\n' + variables + '\n*** Test Cases ***\n' + cases +
              '\n*** Keywords ***\n' + keywords)
    write_file(directory / 'Trace.py', TRACE_LIBRARY)
    path = write_file(directory / 'case.velun', source)
    process, root = execute_source(path, directory)
    library_outcomes(process, root, expected)
    return root


def control_events(root, expected):
    for name, events in expected.items():
        assert workflow_events(root, name) == events, (name, workflow_events(root, name), events)


def failure_reason(root, name):
    case = lifecycle_cases(root)[name]
    assert case.find('status').attrib['status'] == 'FAIL'
    reason = case.find('status').text
    assert reason, name
    return reason
