# feature: F06
"""Acceptance observations for native branches, iteration and failure handling."""
from _helpers import temporary_workspace
from F04_helpers import workflow_events
from F05_helpers import lifecycle_run, lifecycle_records, lifecycle_cases
from F06_helpers import control_run, control_events, failure_reason


def test_conditional_branches_and_inline_assignment():
    with temporary_workspace() as d:
        root = control_run(d, r'''Branches
    ${text}=    Set Variable    False or True
    IF    ${text}
        Mark    substituted
    ELSE IF    True
        Mark    wrong
    END
    IF    $text == 'False or True'
        Mark    object
    END
    ${zero}=    Set Variable    0
    IF    ${zero}
        Mark    wrong
    ELSE
        Mark    substituted false
    END
    IF    $zero
        Mark    object true
    END
    IF    False
        Mark    wrong
    ELSE IF    2 < 3
        Mark    first
    ELSE IF    True
        Mark    wrong
    ELSE
        Mark    wrong
    END
    IF    False
        Mark    wrong
    ELSE
        Mark    alternative
    END
    ${a}=    IF    False    Set Variable    wrong    ELSE IF    True    Set Variable    chosen    ELSE    Set Variable    wrong
    ${b}=    IF    False    Set Variable    wrong
    Mark    ${a}    ${b}
Invalid
    IF    1 +
        Mark    wrong
    END
''', {'Branches': 'PASS', 'Invalid': 'FAIL'})
        control_events(root, {'Branches': [['substituted'], ['object'], ['substituted false'], ['object true'], ['first'], ['alternative'], ['chosen', None]], 'Invalid': []})
        failure_reason(root, 'Invalid')


def test_ordered_range_enumeration_and_dictionary_loops():
    with temporary_workspace() as d:
        root = control_run(d, r'''Values
    FOR    ${a}    ${b}    IN    red    2    blue    5
        Mark    ${a}    ${b}
    END
    FOR    ${n}    IN RANGE    3
        Mark    default    ${n}
    END
    FOR    ${n}    IN RANGE    2    5
        Mark    span    ${n}
    END
    FOR    ${n}    IN RANGE    5    -1    -2
        Mark    step    ${n}
    END
    FOR    ${i}    ${v}    IN ENUMERATE    oak    pine
        Mark    enum    ${i}    ${v}
    END
    FOR    ${i}    ${v}    IN ENUMERATE    elm    ash    start=4
        Mark    offset    ${i}    ${v}
    END
    &{mapping}=    Create Dictionary    z=last    a=first
    FOR    ${key}    IN    @{mapping}
        Mark    key    ${key}
    END
    FOR    ${key}    ${value}    IN    &{mapping}
        Mark    pair    ${key}    ${value}
    END
    FOR    ${pair}    IN    &{mapping}
        ${key}    ${value}=    Set Variable    ${pair}
        Mark    tuple    ${key}    ${value}
    END
Zero Step
    FOR    ${n}    IN RANGE    0    5    0
        Mark    wrong
    END
Bad Group
    FOR    ${a}    ${b}    IN    one    two    three
        Mark    wrong
    END
''', {'Values': 'PASS', 'Zero Step': 'FAIL', 'Bad Group': 'FAIL'})
        control_events(root, {'Values': [['red', '2'], ['blue', '5']] +
            [['default', n] for n in (0, 1, 2)] + [['span', n] for n in (2, 3, 4)] + [['step', n] for n in (5, 3, 1)] +
            [['enum', 0, 'oak'], ['enum', 1, 'pine'], ['offset', 4, 'elm'], ['offset', 5, 'ash']] +
            [['key', 'z'], ['key', 'a']] + [[kind, k, v] for kind in ('pair', 'tuple') for k, v in (('z', 'last'), ('a', 'first'))],
            'Zero Step': [], 'Bad Group': []})


def test_parallel_iteration_modes_and_fill():
    with temporary_workspace() as d:
        cases = ''
        expected = {}
        for name, options in [('Default', ''), ('Shortest', '    mode=SHORTEST'), ('Strict', '    mode=STRICT'), ('Longest', '    mode=LONGEST'), ('Filled', '    mode=LONGEST    fill=missing')]:
            cases += f'''{name}
    @{{left}}=    Create List    A    B
    @{{right}}=    Create List    x    y    z
    FOR    ${{a}}    ${{b}}    IN ZIP    ${{left}}    ${{right}}{options}
        Mark    ${{a}}    ${{b}}
    END
'''
            expected[name] = 'FAIL' if name == 'Strict' else 'PASS'
        cases += '''Equal
    ${a}=    Create List    A    B
    ${b}=    Create List    x    y
    FOR    ${x}    ${y}    IN ZIP    ${a}    ${b}    mode=STRICT
        Mark    ${x}    ${y}
    END
'''
        expected['Equal'] = 'PASS'
        root = control_run(d, cases, expected)
        rows = [['A', 'x'], ['B', 'y']]
        control_events(root, {'Default': rows, 'Shortest': rows, 'Equal': rows,
                              'Longest': rows + [[None, 'z']], 'Filled': rows + [['missing', 'z']]})
        failure_reason(root, 'Strict')


def test_while_conditions_counts_and_limit_policy():
    with temporary_workspace() as d:
        root = control_run(d, r'''Condition
    ${i}=    Set Variable    ${0}
    WHILE    $i < 3
        Mark    ${i}
        ${i}=    Evaluate    $i + 1
    END
Default One
    Count Default
Default Two
    Count Default
Exact Limit
    ${i}=    Set Variable    ${0}
    WHILE    $i < 3    limit=3
        ${i}=    Evaluate    $i + 1
        Mark    exact    ${i}
    END
    Mark    after
Explicit
    WHILE    limit=3
        Mark    counted
    END
Successful
    WHILE    limit=2    on_limit=pass
        Mark    counted
    END
    Mark    after
''', {'Condition': 'PASS', 'Default One': 'FAIL', 'Default Two': 'FAIL', 'Exact Limit': 'PASS', 'Explicit': 'FAIL', 'Successful': 'PASS'}, keywords=r'''Count Default
    ${i}=    Set Variable    ${0}
    TRY
        WHILE
            ${i}=    Evaluate    $i + 1
        END
    FINALLY
        Mark    ${i}
    END
''')
        control_events(root, {'Condition': [[0], [1], [2]], 'Default One': [[10000]], 'Default Two': [[10000]],
                              'Exact Limit': [['exact', n] for n in (1, 2, 3)] + [['after']], 'Explicit': [['counted']] * 3, 'Successful': [['counted']] * 2 + [['after']]})


def test_elapsed_limit_finishes_keyword_and_unlimited_loop():
    with temporary_workspace() as d:
        process, root = lifecycle_run(d, '''Timed
    Record    ${EVENTS}    begin
    WHILE    limit=0.1 seconds
        Slow Effect
    END
Unlimited
    ${i}=    Set Variable    ${0}
    WHILE    limit=NONE
        ${i}=    Evaluate    $i + 1
        IF    $i == 10002    BREAK
    END
    Record    ${EVENTS}    unlimited    ${i}
''', {'Timed': 'FAIL', 'Unlimited': 'PASS'}, keywords='''Slow Effect
    Pause    0.3
    Record    ${EVENTS}    completed
''')
        assert lifecycle_records(d) == [['begin'], ['completed'], ['unlimited', 10002]]
        failure_reason(root, 'Timed')


def test_continue_break_and_control_placement():
    with temporary_workspace() as d:
        cases = r'''Nested
    FOR    ${i}    IN RANGE    5
        TRY
            IF    $i == 1    CONTINUE
            IF    $i == 3    BREAK
            Mark    ${i}
        FINALLY
            Mark    cleanup    ${i}
        END
        Mark    tail    ${i}
    END
    Mark    after
While
    ${i}=    Set Variable    ${0}
    WHILE    $i < 8
        ${i}=    Evaluate    $i + 1
        IF    $i == 1    CONTINUE
        IF    $i == 3    BREAK
        Mark    ${i}
    END
    Mark    after
'''
        expected = {'Nested': 'PASS', 'While': 'PASS'}
        for word in ('BREAK', 'CONTINUE'):
            cases += f'''Outside {word}
    {word}
Called {word}
    FOR    ${{i}}    IN RANGE    2
        Called {word}
    END
'''
            expected.update({f'Outside {word}': 'FAIL', f'Called {word}': 'FAIL'})
        root = control_run(d, cases, expected, keywords='Called BREAK\n    BREAK\nCalled CONTINUE\n    CONTINUE\n')
        control_events(root, {'Nested': [[0], ['cleanup', 0], ['tail', 0], ['cleanup', 1], [2], ['cleanup', 2], ['tail', 2], ['cleanup', 3], ['after']],
                              'While': [[2], ['after']]})


def test_handlers_selection_propagation_else_and_finally():
    with temporary_workspace() as d:
        root = control_run(d, r'''Handled
    TRY
        Fail    selected cause
    EXCEPT    other
        Mark    wrong
    EXCEPT    selected cause    AS    ${cause}
        Mark    handler    ${cause}
    EXCEPT
        Mark    wrong
    ELSE
        Mark    wrong
    FINALLY
        Mark    cleanup
    END
    Mark    after
Catch All
    TRY
        Fail    ordinary cause
    EXCEPT    different
        Mark    wrong
    EXCEPT    AS    ${cause}
        Mark    catchall    ${cause}
    FINALLY
        Mark    cleanup
    END
Success
    TRY
        Mark    body
    EXCEPT
        Mark    wrong
    ELSE
        Mark    success
    FINALLY
        Mark    cleanup
    END
Unmatched
    TRY
        Fail    unhandled cause
    EXCEPT    different
        Mark    wrong
    ELSE
        Mark    wrong
    FINALLY
        Mark    cleanup
    END
''', {'Handled': 'PASS', 'Catch All': 'PASS', 'Success': 'PASS', 'Unmatched': 'FAIL'})
        control_events(root, {'Handled': [['handler', 'selected cause'], ['cleanup'], ['after']],
                              'Catch All': [['catchall', 'ordinary cause'], ['cleanup']],
                              'Success': [['body'], ['success'], ['cleanup']], 'Unmatched': [['cleanup']]})
        assert failure_reason(root, 'Unmatched') == 'unhandled cause'


def test_handler_matching_modes_and_multiple_patterns():
    # Expected selections follow the documented matching rules, not a product round trip.
    scenarios = [('Exact', 'Alpha 42 tail', 'Alpha 42 tail', '', True),
                 ('Exact Case', 'Alpha', 'alpha', '', False),
                 ('Exact Full', 'Alpha tail', 'Alpha', '', False),
                 ('Exact Literal', 'Alpha tail', 'Alpha *', '', False),
                 ('Prefix', 'Alpha tail', 'Alpha', 'START', True),
                 ('Prefix Case', 'Alpha tail', 'alpha', 'START', False),
                 ('Glob', 'Alpha 42 tail', 'Alpha ?? tail', 'GLOB', True),
                 ('Glob Full', 'before Alpha tail', 'Alpha*', 'GLOB', False),
                 ('Regex', 'Alpha 42 tail', 'Alpha [0-9]+ tail', 'REGEXP', True),
                 ('Regex Full', 'before Alpha 42 tail', 'Alpha [0-9]+ tail', 'REGEXP', False),
                 ('Regex End', 'Alpha 42 tail after', 'Alpha [0-9]+ tail', 'REGEXP', False),
                 ('Any Pattern', 'Alpha', 'wrong    Alpha    later', '', True)]
    with temporary_workspace() as d:
        cases = ''
        for name, message, patterns, mode, matches in scenarios:
            option = f'    type={mode}' if mode else ''
            cases += f'''{name}
    TRY
        Fail    {message}
    EXCEPT    {patterns}{option}    AS    ${{cause}}
        Mark    selected    ${{cause}}
    EXCEPT    AS    ${{cause}}
        Mark    alternative    ${{cause}}
    END
'''
        root = control_run(d, cases, {s[0]: 'PASS' for s in scenarios})
        control_events(root, {name: [['selected' if matches else 'alternative', message]]
                              for name, message, patterns, mode, matches in scenarios})


def test_groups_scope_nesting_status_and_invalid_syntax():
    with temporary_workspace() as d:
        root = control_run(d, r'''Scope
    ${value}=    Set Variable    outer
    GROUP    named
        ${value}=    Set Variable    changed
        FOR    ${n}    IN RANGE    2
            GROUP
                Mark    ${n}
            END
        END
    END
    Mark    ${value}
Failed
    GROUP    failed
        Fail    group cause
        Mark    wrong
    END
    GROUP    unexecuted
        Mark    wrong
    END
Skipped
    GROUP    skipped
        Skip    intentional
        Mark    wrong
    END
Missing End
    GROUP    broken
        Mark    wrong
Missing Loop End
    FOR    ${n}    IN    one
        Mark    wrong
Missing If End
    IF    True
        Mark    wrong
Misplaced
    GROUP    broken
    ELSE
        Mark    wrong
    END
''', {'Scope': 'PASS', 'Failed': 'FAIL', 'Skipped': 'SKIP', 'Missing End': 'FAIL', 'Missing Loop End': 'FAIL', 'Missing If End': 'FAIL', 'Misplaced': 'FAIL'})
        control_events(root, {'Scope': [[0], [1], ['changed']], 'Failed': [], 'Missing End': [], 'Missing Loop End': [], 'Missing If End': [], 'Misplaced': []})
        cases = lifecycle_cases(root)
        assert cases['Scope'].find("group[@name='named']/status").attrib['status'] == 'PASS'
        assert len(cases['Scope'].findall('.//group')) == 3
        assert cases['Failed'].find("group[@name='failed']/status").attrib['status'] == 'FAIL'
        assert cases['Failed'].find("group[@name='unexecuted']/status").attrib['status'] == 'NOT RUN'
        assert cases['Skipped'].find("group[@name='skipped']/status").attrib['status'] == 'SKIP'


def test_nonordinary_failures_and_cleanup_failure():
    with temporary_workspace() as d:
        cases = '''Success Cleanup
    TRY
        Mark    body
    EXCEPT
        Mark    wrong
    FINALLY
        Fail    cleanup cause
    END
Handled Cleanup
    TRY
        Fail    ordinary
    EXCEPT
        Mark    handled
    FINALLY
        Fail    cleanup cause
    END
Syntax
    TRY
        IF    True
            No Operation
        ELSE IF
            No Operation
        END
    EXCEPT
        Mark    wrong
    END
Timeout
    [Timeout]    0.1 seconds
    TRY
        Sleep    0.4 seconds
    EXCEPT
        Mark    wrong
    END
'''
        root = control_run(d, cases, {name: 'FAIL' for name in ('Success Cleanup', 'Handled Cleanup', 'Syntax', 'Timeout')})
        control_events(root, {'Success Cleanup': [['body']], 'Handled Cleanup': [['handled']], 'Syntax': [], 'Timeout': []})
        for name in ('Success Cleanup', 'Handled Cleanup'):
            assert failure_reason(root, name) == 'cleanup cause'
        # The uncaught test timeout remains the outcome (stated category marker).
        assert 'Test timeout ' in failure_reason(root, 'Timeout')
