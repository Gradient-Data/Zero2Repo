# feature: F05
"""Acceptance tests for execution order, lifecycle and termination."""
import os
import signal
import subprocess
import sys

from _helpers import write_file, run_module, read_xml, wait_until, call_public, keyword_calls
from velun.api import ExecutionResult
from F01_helpers import execute_source
from F03_helpers import library_outcomes
from F05_helpers import (lifecycle_source, lifecycle_run, lifecycle_records,
                         lifecycle_cases, suite_outcome)


def test_declared_order_hierarchy_and_descriptions(tmp_path):
    tree = tmp_path / 'ordered'
    for filename, names in [('b_second.velun', ['Zebra', 'Apple']), ('a_first.velun', ['Later', 'Earlier'])]:
        cases = ''.join(f'{name}\n    [Documentation]    Description of {name}\n'
                        f'    [Tags]    lifecycle    {name}\n'
                        f'    ${{value}}=    Joined    {name}\n'
                        f'    Record    ${{EVENTS}}    ${{value}}\n' for name in names)
        text = lifecycle_source(tmp_path, cases,
                                settings='Documentation    Suite description\nMetadata    Owner    Automation\n')
        write_file(tree / filename, text)
    process, root = execute_source(tree, tmp_path)
    library_outcomes(process, root, {n: 'PASS' for n in ['Later', 'Earlier', 'Zebra', 'Apple']})
    assert lifecycle_records(tmp_path) == [[n + ':processed'] for n in ['Later', 'Earlier', 'Zebra', 'Apple']]
    suites = root.findall('./suite/suite')
    assert [s.attrib['source'] for s in suites] == [str(tree / name) for name in ['a_first.velun', 'b_second.velun']]
    assert [[c.attrib['name'] for c in s.findall('test')] for s in suites] == [['Later', 'Earlier'], ['Zebra', 'Apple']]
    for suite in suites:
        assert suite.find('doc').text == 'Suite description'
        assert {m.attrib['name']: m.text for m in suite.findall('meta')} == {'Owner': 'Automation'}
        for case in suite.findall('test'):
            name = case.attrib['name']
            assert case.find('doc').text == 'Description of ' + name
            assert {t.text for t in case.findall('tag')} == {'lifecycle', name}
    suite_outcome(root, 'PASS')


def test_fixture_order_failures_and_cleanup_continuation(tmp_path):
    cases = 'First\n    Record    ${EVENTS}    first body\nSecond\n    Record    ${EVENTS}    second body\n'
    fixture = '''Fixture
    [Arguments]    ${label}
    Record    ${EVENTS}    ${label}
    Fail    fixture rejection
Cleanup
    Record    ${EVENTS}    cleanup before
    Fail    cleanup rejection
    Record    ${EVENTS}    cleanup after
Fatal Cleanup
    Record    ${EVENTS}    fatal before
    Fatal Error    cleanup termination
    Record    ${EVENTS}    fatal after
Syntax Cleanup
    Record    ${EVENTS}    syntax before
    IF    True
        No Operation
    ELSE IF
        No Operation
    END
    Record    ${EVENTS}    syntax after
'''
    scenarios = [
        # Unlike ordinary failures, fatal failures and invalid syntax stop the cleanup.
        ('fatal_cleanup', 'Test Teardown    Fatal Cleanup\n', 'FAIL', ['first body', 'fatal before']),
        ('syntax_cleanup', 'Test Teardown    Syntax Cleanup\n', 'FAIL', ['first body', 'syntax before', 'second body', 'syntax before']),
        ('normal', 'Suite Setup    Record    ${EVENTS}    suite setup\nSuite Teardown    Record    ${EVENTS}    suite cleanup\nTest Setup    Record    ${EVENTS}    test setup\nTest Teardown    Record    ${EVENTS}    test cleanup\n', 'PASS',
         ['suite setup', 'test setup', 'first body', 'test cleanup', 'test setup', 'second body', 'test cleanup', 'suite cleanup']),
        ('test_setup', 'Test Setup    Fixture    test setup\nTest Teardown    Record    ${EVENTS}    test cleanup\n', 'FAIL',
         ['test setup', 'test cleanup', 'test setup', 'test cleanup']),
        ('suite_setup', 'Suite Setup    Fixture    suite setup\nSuite Teardown    Record    ${EVENTS}    suite cleanup\n', 'FAIL', ['suite setup', 'suite cleanup']),
        ('suite_cleanup', 'Suite Teardown    Cleanup\n', 'FAIL', ['first body', 'second body', 'cleanup before', 'cleanup after']),
        ('test_cleanup', 'Test Teardown    Cleanup\n', 'FAIL', ['first body', 'cleanup before', 'cleanup after', 'second body', 'cleanup before', 'cleanup after'])]
    for label, settings, status, events in scenarios:
        directory = tmp_path / label
        if label == 'suite_cleanup':
            source = write_file(directory / 'case.velun', lifecycle_source(directory, cases, settings=settings, keywords=fixture))
            process, root = execute_source(source, directory)
            assert 0 < process.returncode < 251, process.stderr
            result = call_public(ExecutionResult, str(directory / 'result.xml')).value
            assert {c.name: c.status for c in result.suite.tests} == {'First': 'FAIL', 'Second': 'FAIL'}
        else:
            _, root = lifecycle_run(directory, cases, {'First': status, 'Second': status}, settings=settings, keywords=fixture)
        assert lifecycle_records(directory) == [[v] for v in events]
        suite_outcome(root, status)
    # A parent fixture failure also reaches tests in descendant suites.
    for phase in ['Setup', 'Teardown']:
        directory = tmp_path / ('descendant_' + phase)
        source = lifecycle_source(directory, 'Child\n    Record    ${EVENTS}    child body\n')
        write_file(directory / 'tree' / 'child.velun', source)
        settings = f'Suite {phase}    Fixture    parent {phase}\n'
        if phase == 'Setup':
            settings += 'Suite Teardown    Record    ${EVENTS}    parent cleanup\n'
        init = lifecycle_source(directory, '', settings=settings, keywords=fixture)
        write_file(directory / 'tree' / '__init__.velun', init.split('*** Test Cases ***')[0] + '*** Keywords ***\n' + fixture)
        process, root = execute_source(directory / 'tree', directory)
        assert 0 < process.returncode < 251, process.stderr
        result = call_public(ExecutionResult, str(directory / 'result.xml')).value
        child = result.suite.suites[0]
        assert {c.name: c.status for c in child.tests} == {'Child': 'FAIL'}
        expected = [['parent Setup'], ['parent cleanup']] if phase == 'Setup' else [['child body'], ['parent Teardown']]
        assert lifecycle_records(directory) == expected
        suite_outcome(root, 'FAIL')


def test_ordinary_and_explicit_continuable_failures(tmp_path):
    cases = '''Ordinary
    Record    ${EVENTS}    ordinary before
    Fail    ordinary rejection
    Record    ${EVENTS}    ordinary after
Continuable
    Record    ${EVENTS}    continuable before
    Run Keyword And Continue On Failure    Fail    continuable rejection
    Record    ${EVENTS}    continuable after
Later
    Record    ${EVENTS}    later body
'''
    _, root = lifecycle_run(tmp_path, cases, {'Ordinary': 'FAIL', 'Continuable': 'FAIL', 'Later': 'PASS'})
    assert lifecycle_records(tmp_path) == [[v] for v in ['ordinary before', 'continuable before', 'continuable after', 'later body']]
    suite_outcome(root, 'FAIL')


def test_local_recursive_and_overridden_failure_policies(tmp_path):
    keywords = '''Outer
    Inner
    Record    ${EVENTS}    outer after
Inner
    Fail    nested rejection
    Record    ${EVENTS}    inner after
Local Stop
    [Tags]    velun:stop-on-failure
    Inner
    Record    ${EVENTS}    stop after
Local Continue
    [Tags]    velun:continue-on-failure
    Inner
    Record    ${EVENTS}    continue after
Explicit
    [Tags]    velun:stop-on-failure
    Run Keyword And Continue On Failure    Fail    explicit rejection
    Record    ${EVENTS}    explicit after
'''
    scenarios = [
        ('local', 'velun:continue-on-failure', 'Outer', ['test after']),
        ('recursive', 'velun:recursive-continue-on-failure', 'Outer', ['inner after', 'outer after', 'test after']),
        ('override_stop', 'velun:recursive-continue-on-failure', 'Local Stop', ['inner after', 'test after']),
        ('override_continue', 'velun:recursive-stop-on-failure', 'Local Continue', ['continue after']),
        ('explicit', 'velun:recursive-stop-on-failure', 'Explicit', ['explicit after', 'test after'])]
    for label, tag, call, events in scenarios:
        directory = tmp_path / label
        cases = f'Policy\n    [Tags]    {tag}\n    Record    ${{EVENTS}}    started\n    {call}\n    Record    ${{EVENTS}}    test after\n'
        _, root = lifecycle_run(directory, cases, {'Policy': 'FAIL'}, keywords=keywords)
        assert lifecycle_records(directory) == [['started']] + [[v] for v in events]
        suite_outcome(root, 'FAIL')


def test_skip_mechanisms_and_suite_aggregation(tmp_path):
    cases = '''Passing
    Record    ${EVENTS}    pass body
Requested
    Record    ${EVENTS}    requested before
    Skip    caller skip reason
    Record    ${EVENTS}    requested after
Tagged
    [Tags]    omitted
    Record    ${EVENTS}    tagged body
Converted
    [Tags]    converted
    Record    ${EVENTS}    converted before
    Fail    converted rejection
    Record    ${EVENTS}    converted after
'''
    settings = 'Test Teardown    Record    ${EVENTS}    cleanup    ${TEST NAME}\n'
    options = ['--skip', 'omitted', '--skiponfailure', 'converted']
    expected = {'Passing': 'PASS', 'Requested': 'SKIP', 'Tagged': 'SKIP', 'Converted': 'SKIP'}
    _, root = lifecycle_run(tmp_path / 'mixed', cases, expected, settings=settings, options=options)
    assert lifecycle_records(tmp_path / 'mixed') == [['pass body'], ['cleanup', 'Passing'], ['requested before'], ['cleanup', 'Requested'], ['converted before'], ['cleanup', 'Converted']]
    suite_outcome(root, 'PASS')
    _, root = lifecycle_run(tmp_path / 'all_skipped', cases, {**expected, 'Passing': 'SKIP'}, settings=settings, options=[*options, '--skip', '*', '--settag', 'all'])
    suite_outcome(root, 'SKIP')
    _, root = lifecycle_run(tmp_path / 'failed', cases + 'Rejected\n    Fail    retained rejection\n', {**expected, 'Rejected': 'FAIL'}, settings=settings, options=options)
    suite_outcome(root, 'FAIL')


def test_timeout_scopes_overlap_and_cleanup(tmp_path):
    keywords = '''Slow Keyword
    [Arguments]    ${limit}
    [Timeout]    ${limit}
    Pause    2
    Record    ${EVENTS}    keyword finished
Setup Keyword
    [Timeout]    200 milliseconds
    [Setup]    Pause    2
    Record    ${EVENTS}    keyword setup finished
Cleanup Keyword
    [Timeout]    200 milliseconds
    [Teardown]    Slow Cleanup
    Record    ${EVENTS}    keyword body
Slow Cleanup
    Record    ${EVENTS}    keyword cleanup started
    Pause    2
    Record    ${EVENTS}    keyword cleanup finished
Test Cleanup
    Pause    0.3
    Record    ${EVENTS}    test cleanup finished
'''
    cases = '''Body Timeout
    [Timeout]    200 milliseconds
    Pause    2
    Record    ${EVENTS}    forbidden body
Setup Timeout
    [Timeout]    200 milliseconds
    [Setup]    Pause    2
    Record    ${EVENTS}    forbidden setup body
Keyword Body
    Slow Keyword    200 milliseconds
Keyword Setup
    Setup Keyword
Keyword Cleanup
    Cleanup Keyword
Earlier Test
    [Timeout]    200 milliseconds
    Slow Keyword    5 seconds
Earlier Keyword
    [Timeout]    5 seconds
    Slow Keyword    200 milliseconds
Ordinary Failure
    Fail    assertion sentinel
Cleanup Uninterrupted
    [Timeout]    200 milliseconds
    Record    ${EVENTS}    quick body
    [Teardown]    Test Cleanup
'''
    names = ['Body Timeout', 'Setup Timeout', 'Keyword Body', 'Keyword Setup', 'Keyword Cleanup', 'Earlier Test', 'Earlier Keyword', 'Ordinary Failure', 'Cleanup Uninterrupted']
    cases += 'Within Limit\n    [Timeout]    5 seconds\n    Slow Keyword    5 seconds\n'
    _, root = lifecycle_run(tmp_path, cases, {**dict.fromkeys(names, 'FAIL'), 'Within Limit': 'PASS'}, keywords=keywords,
                            settings='Test Teardown    Record    ${EVENTS}    cleanup    ${TEST NAME}\n')
    expected = [['cleanup', n] for n in names[:4]]
    expected += [['keyword body'], ['keyword cleanup started'], ['keyword cleanup finished'], ['cleanup', 'Keyword Cleanup']]
    expected += [['cleanup', n] for n in names[5:8]]
    expected += [['quick body'], ['test cleanup finished'], ['keyword finished'], ['cleanup', 'Within Limit']]
    assert lifecycle_records(tmp_path) == expected
    import json
    timings = [json.loads(line) for line in (tmp_path / 'timings.jsonl').read_text().splitlines()]
    # The supplied operation measures actual time spent waiting, including interruption.
    # Cleanup and the live baseline complete; the other waits are cut short.
    assert len(timings) == 9, timings
    for index in [0, 1, 2, 3, 5, 6]:
        requested, elapsed = timings[index]
        assert 0 <= elapsed < requested, timings
    for index in [4, 7, 8]:
        requested, elapsed = timings[index]
        assert elapsed >= requested, timings
    observed = lifecycle_cases(root)
    # Timeout category labels are shell; duration formatting and prose are not pinned.
    for name in names:
        message = observed[name].find('status').text
        if name == 'Ordinary Failure':
            assert message == 'assertion sentinel'
        else:
            category = 'Keyword timeout ' if name.startswith('Keyword') or name == 'Earlier Keyword' else 'Test timeout '
            assert category in message, (name, message)
    suite_outcome(root, 'FAIL')
    # The earliest expiry governs, not the shortest declared duration: the test deadline
    # started first, so it expires before the shorter keyword deadline started later.
    # An outer test deadline also leaves a keyword cleanup running to completion.
    directory = tmp_path / 'expiry'
    _, root = lifecycle_run(directory, '''Earlier Expiry
    [Timeout]    1 second
    Pause    0.6
    Slow Keyword    0.8 seconds
Outer Deadline
    [Timeout]    200 milliseconds
    Plain Cleanup Keyword
''', {'Earlier Expiry': 'FAIL', 'Outer Deadline': 'FAIL'}, keywords=keywords + '''Plain Cleanup Keyword
    Record    ${EVENTS}    outer body
    [Teardown]    Outer Cleanup
Outer Cleanup
    Record    ${EVENTS}    outer cleanup started
    Pause    0.6
    Record    ${EVENTS}    outer cleanup finished
''')
    assert lifecycle_records(directory) == [['outer body'], ['outer cleanup started'], ['outer cleanup finished']]
    observed = lifecycle_cases(root)
    assert 'Test timeout ' in observed['Earlier Expiry'].find('status').text
    assert 'Test timeout ' in observed['Outer Deadline'].find('status').text


def test_disabled_and_invalid_timeout_declarations(tmp_path):
    declarations = [('Omitted', None), ('Empty', ''), ('Disabled', 'NONE'), ('Zero', '0'), ('Negative', '-1 second')]
    cases = ''
    keywords = ''
    for name, declaration in declarations:
        setting = '' if declaration is None else f'    [Timeout]    {declaration}\n'
        cases += f'{name}\n{setting}    Pause    0.05\n    Keyword {name}\n    Record    ${{EVENTS}}    {name}\n'
        keywords += f'Keyword {name}\n{setting}    Pause    0.05\n'
    cases += '''Bad Test
    [Timeout]    not-a-duration
    Record    ${EVENTS}    invalid test body
Bad Keyword
    Invalid Keyword
'''
    keywords += '''Invalid Keyword
    [Timeout]    not-a-duration
    Record    ${EVENTS}    invalid keyword body
'''
    _, root = lifecycle_run(tmp_path, cases, {**dict.fromkeys([n for n, _ in declarations], 'PASS'), 'Bad Test': 'FAIL', 'Bad Keyword': 'FAIL'}, keywords=keywords)
    assert lifecycle_records(tmp_path) == [[n] for n, _ in declarations]
    observed = lifecycle_cases(root)
    for name in ('Bad Test', 'Bad Keyword'):
        reason = observed[name].find('status').text
        assert 'not-a-duration' in reason
    keyword = keyword_calls(observed['Bad Keyword'], 'Invalid Keyword')[0]
    assert keyword.find('status').attrib['status'] == 'FAIL'
    assert 'not-a-duration' in keyword.find('status').text
    # A direct disabling declaration also disables a suite-level default timeout,
    # while an undeclared test keeps the default (live baseline).
    directory = tmp_path / 'suite_default'
    cases = 'Inherited\n    Pause    0.4\n    Record    ${EVENTS}    Inherited\n'
    for name, declaration in declarations[1:]:
        cases += f'{name}\n    [Timeout]    {declaration}\n    Pause    0.4\n    Record    ${{EVENTS}}    {name}\n'
    _, root = lifecycle_run(directory, cases, {'Inherited': 'FAIL', **dict.fromkeys([n for n, _ in declarations[1:]], 'PASS')},
                            settings='Test Timeout    100 milliseconds\n')
    assert lifecycle_records(directory) == [[n] for n, _ in declarations[1:]]
    assert 'Test timeout ' in lifecycle_cases(root)['Inherited'].find('status').text


def test_fatal_and_stop_on_failure_terminate_remaining_tests(tmp_path):
    for label, operation, options in [('fatal', 'Fatal Error', []), ('stop', 'Fail', ['--exitonfailure'])]:
        directory = tmp_path / label
        cases = f'''Completed
    Record    ${{EVENTS}}    completed body
Stopping
    Record    ${{EVENTS}}    stopping before
    {operation}    caller termination reason
    Record    ${{EVENTS}}    stopping after
Remaining
    Record    ${{EVENTS}}    remaining body
'''
        _, root = lifecycle_run(directory, cases, {'Completed': 'PASS', 'Stopping': 'FAIL', 'Remaining': 'FAIL'}, settings='Test Teardown    Record    ${EVENTS}    cleanup    ${TEST NAME}\nSuite Teardown    Record    ${EVENTS}    suite cleanup\n', options=options)
        assert lifecycle_records(directory) == [['completed body'], ['cleanup', 'Completed'], ['stopping before'], ['cleanup', 'Stopping'], ['suite cleanup']]
        remaining = lifecycle_cases(root)['Remaining']
        assert 'velun:exit' in {t.text for t in remaining.findall('tag')}
        suite_outcome(root, 'FAIL')
        # Termination also reaches tests of a later suite in the same execution.
        nested = directory / 'nested'
        write_file(nested / 'tree' / 'a_first.velun', lifecycle_source(nested, cases, settings='Suite Teardown    Record    ${EVENTS}    suite cleanup\n'))
        write_file(nested / 'tree' / 'b_later.velun', lifecycle_source(nested, 'Later Suite\n    Record    ${EVENTS}    later suite body\n'))
        process, root = execute_source(nested / 'tree', nested, *options)
        library_outcomes(process, root, {'Completed': 'PASS', 'Stopping': 'FAIL', 'Remaining': 'FAIL', 'Later Suite': 'FAIL'})
        assert lifecycle_records(nested) == [['completed body'], ['stopping before'], ['suite cleanup']]
        assert 'velun:exit' in {t.text for t in lifecycle_cases(root)['Later Suite'].findall('tag')}
        suite_outcome(root, 'FAIL')


def test_cleanup_can_be_disabled_after_termination(tmp_path):
    cases = '''Stopping
    Record    ${EVENTS}    started
    Fatal Error    caller termination reason
Remaining
    Record    ${EVENTS}    forbidden
'''
    settings = 'Test Teardown    Record    ${EVENTS}    test cleanup\nSuite Teardown    Record    ${EVENTS}    suite cleanup\n'
    for label, options, events in [('baseline', [], ['started', 'test cleanup', 'suite cleanup']), ('disabled', ['--skipteardownonexit'], ['started'])]:
        directory = tmp_path / label
        _, root = lifecycle_run(directory, cases, {'Stopping': 'FAIL', 'Remaining': 'FAIL'}, settings=settings, options=options)
        assert lifecycle_records(directory) == [[v] for v in events]
        assert 'velun:exit' in {t.text for t in lifecycle_cases(root)['Remaining'].findall('tag')}
        suite_outcome(root, 'FAIL')


def test_first_external_interrupt_preserves_results_and_cleanup(tmp_path):
    cases = '''Completed
    Record    ${EVENTS}    completed
Interrupted
    Record    ${EVENTS}    waiting
    Pause    30
    Record    ${EVENTS}    forbidden completion
Remaining
    Record    ${EVENTS}    forbidden remaining
'''
    source = write_file(tmp_path / 'case.velun', lifecycle_source(tmp_path, cases, settings='Test Teardown    Record    ${EVENTS}    cleanup    ${TEST NAME}\nSuite Teardown    Record    ${EVENTS}    suite cleanup\n'))
    output = tmp_path / 'result.xml'
    process = subprocess.Popen([sys.executable, '-m', 'velun', '--output', str(output), '--log', 'NONE', '--report', 'NONE', str(source)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        def ready():
            if process.poll() is not None:
                raise AssertionError('Product exited before interruption synchronization.')
            path = tmp_path / 'events.jsonl'
            return path.exists() and ['waiting'] in lifecycle_records(tmp_path)
        wait_until(ready, timeout=15)
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=15)
        root = read_xml(output).getroot()
        # Use the same completed-process carrier as the shared outcome checker.
        from types import SimpleNamespace
        result = SimpleNamespace(returncode=process.returncode, stdout=stdout, stderr=stderr)
        library_outcomes(result, root, {'Completed': 'PASS', 'Interrupted': 'FAIL', 'Remaining': 'FAIL'})
        assert lifecycle_records(tmp_path) == [['completed'], ['cleanup', 'Completed'], ['waiting'], ['cleanup', 'Interrupted'], ['suite cleanup']]
        assert 'velun:exit' in {t.text for t in lifecycle_cases(root)['Remaining'].findall('tag')}
        suite_outcome(root, 'FAIL')
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)


def test_task_mode_automatic_explicit_and_mixed_source_rejection(tmp_path):
    cases = '''Work
    Record    ${EVENTS}    executed task
Rejected Work
    Record    ${EVENTS}    failing task
    Fail    task rejection
    Record    ${EVENTS}    forbidden task continuation
Skipped Work
    Record    ${EVENTS}    skipping task
    Skip    task skip reason
    Record    ${EVENTS}    forbidden skipped continuation
Later Work
    Record    ${EVENTS}    later task
'''
    for label, section, options, mode in [('automatic', 'Tasks', [], 'true'), ('explicit', 'Test Cases', ['--rpa'], 'true'), ('test_mode', 'Tasks', ['--norpa'], 'false')]:
        directory = tmp_path / label
        process, root = lifecycle_run(directory, cases, {'Work': 'PASS', 'Rejected Work': 'FAIL', 'Skipped Work': 'SKIP', 'Later Work': 'PASS'}, section=section, options=options, settings='Test Setup    Record    ${EVENTS}    setup    ${TEST NAME}\nTest Teardown    Record    ${EVENTS}    cleanup    ${TEST NAME}\n')
        events = []
        for name, body in [('Work', 'executed task'), ('Rejected Work', 'failing task'), ('Skipped Work', 'skipping task'), ('Later Work', 'later task')]:
            events += [['setup', name], [body], ['cleanup', name]]
        assert lifecycle_records(directory) == events
        assert root.attrib['rpa'] == mode
        # Console aggregate uses a public fixed singular/plural terminology label.
        assert (b'4 tasks, ' if mode == 'true' else b'4 tests, ') in process.stdout
        suite_outcome(root, 'FAIL')
    directory = tmp_path / 'mixed'
    test = write_file(directory / 'tests.velun', lifecycle_source(directory, 'Test Work\n    Record    ${EVENTS}    test\n'))
    task = write_file(directory / 'tasks.velun', lifecycle_source(directory, 'Task Work\n    Record    ${EVENTS}    task\n', section='Tasks'))
    process = run_module('velun', ['--outputdir', str(directory), '--log', 'NONE', '--report', 'NONE', str(test), str(task)])
    assert process.returncode == 252
    assert b'[ ERROR ]' in process.stderr
    # An explicit mode resolves the same mixed source configuration.
    process, root = execute_source(directory, directory, '--rpa')
    library_outcomes(process, root, {'Test Work': 'PASS', 'Task Work': 'PASS'})
    assert sorted(lifecycle_records(directory)) == [['task'], ['test']]
    assert root.attrib['rpa'] == 'true'
