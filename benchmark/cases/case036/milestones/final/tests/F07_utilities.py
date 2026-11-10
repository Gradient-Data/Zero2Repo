# feature: F07
"""Acceptance tests for automatically available standard utilities."""
import re
from _helpers import temporary_workspace, write_file, require_python
from F04_helpers import workflow_events
from F05_helpers import lifecycle_cases
from F06_helpers import failure_reason
from F07_helpers import utility_run, effect_rows


def test_standard_assertion_families():
    pairs = [
        ('Should Be True', '3 > 1', '3 < 1'),
        ('Should Not Be True', '${0}', '${1}'),
        ('Should Be Equal', 'cedar    cedar', 'cedar    maple'),
        ('Should Not Be Equal', 'cedar    maple', 'cedar    cedar'),
        ('Should Be Equal As Integers', '0x19    25', '25    26'),
        ('Should Be Equal As Strings', '${17}    17', 'cedar    maple'),
        ('Should Be Empty', '${EMPTY}', 'cedar'),
        ('Should Not Be Empty', 'cedar', '${EMPTY}'),
        ('Length Should Be', 'cedar    5', 'cedar    3'),
        ('Should Contain', 'cedar    ed', 'cedar    zz'),
        ('Should Not Contain', 'cedar    zz', 'cedar    ed'),
        ('Should Contain Any', 'cedar    zz    ed', 'cedar    zz    xx'),
        ('Should Not Contain Any', 'cedar    zz    xx', 'cedar    zz    ed'),
        ('Should Contain X Times', 'banana    an    2', 'banana    an    3'),
        ('Should Start With', 'cedar    ce', 'cedar    ar'),
        ('Should Not Start With', 'cedar    ar', 'cedar    ce'),
        ('Should End With', 'cedar    ar', 'cedar    ce'),
        ('Should Not End With', 'cedar    ce', 'cedar    ar'),
        ('Should Match', 'cedar    c?d[ae]r', 'cedar    d*'),
        ('Should Not Match', 'cedar    d*', 'cedar    c*'),
        ('Should Match Regexp', 'cedar    ed[a-z]', 'cedar    ^maple$'),
        ('Should Not Match Regexp', 'cedar    ^maple$', 'cedar    ed[a-z]'),
    ]
    # Caller values that an unsatisfied assertion's reason must make identifiable
    # (PRD: compared values and unmet condition identifiable); no wording is fixed.
    shown = [['3 < 1'], [], ['cedar', 'maple'], ['cedar'], ['25', '26'], ['cedar', 'maple'],
             ['cedar'], [], ['3', '5'], ['cedar', 'zz'], ['cedar', 'ed'], ['cedar', 'zz', 'xx'],
             ['cedar', 'ed'], ['banana', 'an'], ['cedar', 'ar'], ['cedar', 'ce'], ['cedar', 'ce'],
             ['cedar', 'ar'], ['cedar', 'd*'], ['cedar', 'c*'], ['cedar', '^maple$'], ['cedar', 'ed[a-z]']]
    # Opposite-side bounds: fewer occurrences / longer length than actual also fail.
    pairs += [('Should Contain X Times', 'banana    an    2', 'banana    an    1'),
              ('Length Should Be', 'cedar    5', 'cedar    7')]
    shown += [['banana', 'an'], ['5', '7']]
    cases = 'Satisfied\n' + ''.join(f'    {kw}    {good}\n' for kw, good, bad in pairs)
    expected = {'Satisfied': 'PASS'}
    for i, (kw, good, bad) in enumerate(pairs):
        name = f'Unsatisfied {i}'
        cases += f'{name}\n    {kw}    {bad}\n'
        expected[name] = 'FAIL'
    cases += '''Compared Values
    Should Be Equal    caller-left    caller-right
Custom Message
    Should Be Equal    a    b    msg=caller supplied reason    values=False
'''
    expected.update({'Compared Values': 'FAIL', 'Custom Message': 'FAIL'})
    with temporary_workspace() as d:
        root = utility_run(d, cases, expected)
        reason = failure_reason(root, 'Compared Values')
        assert 'caller-left' in reason and 'caller-right' in reason
        assert failure_reason(root, 'Custom Message') == 'caller supplied reason'
        for i, tokens in enumerate(shown):
            reason = failure_reason(root, f'Unsatisfied {i}')
            assert all(token in reason for token in tokens), (pairs[i], reason)


def test_precision_normalization_and_equality_conversion():
    with temporary_workspace() as d:
        utility_run(d, r'''Working
    Should Be Equal As Numbers    1.1234561    1.1234564
    Should Be Equal As Numbers    1.234    1.233    precision=2
    Should Be Equal    Straße    STRASSE    ignore_case=True
    Should Be Equal    ${SPACE}Alpha${SPACE}    Alpha    strip_spaces=True
    Should Be Equal    ${SPACE}Alpha    Alpha    strip_spaces=LEADING
    Should Be Equal    Alpha${SPACE}    Alpha    strip_spaces=TRAILING
    Should Be Equal    a${SPACE}${SPACE}b    a b    collapse_spaces=True
    ${left}=    Evaluate    [[' A' + chr(32)*2 + 'B '], {'key': 'Straße'}]
    ${right}=    Evaluate    [['a b'], {'key': 'STRASSE'}]
    Should Be Equal    ${left}    ${right}    ignore_case=True    strip_spaces=True    collapse_spaces=True
    Should Be Equal    ${23}    23    type=int
    Should Be Equal    ${23}    23    type=AUTO
    Should Be Equal    023    23    types=int
Precision
    Should Be Equal As Numbers    1.1234561    1.1234571
Explicit Precision
    Should Be Equal As Numbers    1.234    1.233    precision=3
Default Case
    Should Be Equal    Alpha    alpha
Default Strip
    Should Be Equal    ${SPACE}Alpha    Alpha
Default Collapse
    Should Be Equal    a${SPACE}${SPACE}b    a b
Nested Default
    ${left}=    Create List    Alpha
    ${right}=    Create List    alpha
    Should Be Equal    ${left}    ${right}
Nested Different
    ${left}=    Create List    Alpha
    ${right}=    Create List    Beta
    Should Be Equal    ${left}    ${right}    ignore_case=True
Invalid First Type
    Should Be Equal    23    23    type=int
Mutually Exclusive
    Should Be Equal    ${23}    23    type=int    types=int
Rounded Apart
    Should Be Equal As Numbers    1.0000004    1.0000006
Leading Only
    Should Be Equal    Alpha${SPACE}    Alpha    strip_spaces=LEADING
Trailing Only
    Should Be Equal    ${SPACE}Alpha    Alpha    strip_spaces=TRAILING
Collapse Keeps Space
    Should Be Equal    a${SPACE}${SPACE}b    ab    collapse_spaces=True
''', {name: ('PASS' if name == 'Working' else 'FAIL') for name in (
            'Working', 'Precision', 'Explicit Precision', 'Default Case', 'Default Strip',
            'Default Collapse', 'Nested Default', 'Nested Different', 'Invalid First Type', 'Mutually Exclusive',
            'Rounded Apart', 'Leading Only', 'Trailing Only', 'Collapse Keeps Space')})


def test_scalar_bytes_and_collection_conversions():
    operations = [
        ('Convert To Integer    ${-12.9}', '-12'),
        ('Convert To Integer    10 0_1', '1001'),
        ('Convert To Integer    0b10101', '21'),
        ('Convert To Integer    0o31', '25'),
        ('Convert To Integer    0x2F', '47'),
        ('Convert To Integer    31    base=8', '25'),
        ('Convert To Number    2.5    precision=0', '2.0'),
        ('Convert To Number    3.5    precision=0', '4.0'),
        ('Convert To Number    1 2_3.125', '123.125'),
        ('Convert To Binary    13', "'1101'"),
        ('Convert To Octal    27', "'33'"),
        ('Convert To Hex    137', "'89'"),
        ('Convert To String    ${42}', "'42'"),
        ('Convert To Boolean    FaLsE', 'False'),
        ('Convert To Boolean    no', 'True'),
        ('Convert To Boolean    ${EMPTY}', 'False'),
        ('Convert To Boolean    ${0}', 'False'),
        ('Convert To Boolean    ${-2}', 'True'),
        ('Convert To Bytes    Aÿ', "bytes([65,255])"),
        ('Convert To Bytes    0 65 255    int', "bytes([0,65,255])"),
        ('Convert To Bytes    00 41 ff    hex', "bytes([0,65,255])"),
        ('Convert To Bytes    00000000 01000001 11111111    bin', "bytes([0,65,255])"),
        ('Create List    oak    ${3}    ${False}', "['oak',3,False]"),
        ('Create Dictionary    key=old    key=new    n=${4}', "{'key':'new','n':4}"),
    ]
    cases = 'Working\n'
    for call, expected in operations:
        cases += f'    ${{v}}=    {call}\n    Check    ${{v}}    {expected}\n'
    cases += '''    ${v}=    Convert To Bytes    41 ff    hex
    ${v}=    Convert To String    ${v}
    Check    ${v}    'Aÿ'
'''
    failures = {'Bad Integer': 'Convert To Integer    xyz', 'Bad Number': 'Convert To Number    twelve',
                'Bad Byte Range': 'Convert To Bytes    256    int', 'Bad Byte Text': 'Convert To Bytes    Ā',
                'Bad Byte Hex': 'Convert To Bytes    gg    hex', 'Bad Byte Binary': 'Convert To Bytes    00000002    bin'}
    for name, call in failures.items():
        cases += f'{name}\n    {call}\n'
    with temporary_workspace() as d:
        utility_run(d, cases, {'Working': 'PASS', **dict.fromkeys(failures, 'FAIL')})


def test_expression_and_object_operations():
    require_python((3, 13))
    with temporary_workspace() as d:
        utility_run(d, r'''Working
    ${n}=    Set Variable    ${7}
    ${v}=    Evaluate    [i*i + $n for i in range(4)]
    Check    ${v}    [7,8,11,16]
    ${v}=    Evaluate    math.isqrt(82)    modules=math
    Check    ${v}    9
    ${ns}=    Create Dictionary    offset=${11}
    ${v}=    Evaluate    offset + 4    namespace=${ns}
    Check    ${v}    15
    ${obj}=    Fresh Object
    ${v}=    Call Method    ${obj}    append    caller-value
    Check    ${v}    None
    Check    ${obj}    ['caller-value']
    ${v}=    Call Method    ${obj}    pop
    Check    ${v}    'caller-value'
    Check    ${obj}    []
Bad Expression
    Evaluate    1 +
Missing Method
    ${obj}=    Fresh Object
    Call Method    ${obj}    no_such_operation
Method Failure
    ${obj}=    Fresh Object
    Call Method    ${obj}    pop
''', {'Working': 'PASS', 'Bad Expression': 'FAIL', 'Missing Method': 'FAIL', 'Method Failure': 'FAIL'})


def test_dynamic_execution_and_failure_handling():
    with temporary_workspace() as d:
        root = utility_run(d, r'''Working
    ${name}=    Set Variable    Store
    ${v}=    Run Keyword    ${name}    dynamic
    Check    ${v}    ['dynamic']
    ${v}=    Run Keyword And Return Status    Store    status
    Check    ${v}    True
    ${v}=    Run Keyword And Return Status    Fail    ordinary reason
    Check    ${v}    False
    ${v}=    Run Keyword And Ignore Error    Store    ignored
    Check    ${v}    ('PASS',['dynamic','status','ignored'])
    ${v}=    Run Keyword And Ignore Error    Fail    ordinary reason
    Check    ${v}    ('FAIL','ordinary reason')
    Run Keyword And Warn On Failure    Fail    warning reason
    Mark    after-warning
    ${v}=    Run Keyword And Expect Error    prefix * tail    Fail    prefix middle tail
    Check    ${v}    'prefix middle tail'
    ${v}=    Run Keyword And Expect Error    EQUALS: literal *    Fail    literal *
    Check    ${v}    'literal *'
    ${v}=    Run Keyword And Expect Error    STARTS: prefix    Fail    prefix rest
    Check    ${v}    'prefix rest'
    ${v}=    Run Keyword And Expect Error    REGEXP: item [0-9]+    Fail    item 271
    Check    ${v}    'item 271'
Continue
    Run Keyword And Continue On Failure    Fail    continued reason
    Mark    after-continue
Unexpected Success
    Run Keyword And Expect Error    *    No Operation
Mismatch
    Run Keyword And Expect Error    exact    Fail    prefix exact suffix
Prefix Mismatch
    Run Keyword And Expect Error    STARTS: prefix    Fail    before prefix rest
Exact Mismatch
    Run Keyword And Expect Error    EQUALS: literal *    Fail    literal anything
Case Sensitive
    Run Keyword And Expect Error    EQUALS: Mixed    Fail    mixed
Wildcard Case Sensitive
    Run Keyword And Expect Error    Prefix * tail    Fail    prefix middle tail
Regexp Whole Message
    Run Keyword And Expect Error    REGEXP: item [0-9]+    Fail    before item 271 after
Syntax
    Run Keyword And Ignore Error    Needs Argument
Timeout
    [Timeout]    50 milliseconds
    Run Keyword And Ignore Error    Sleep    200 milliseconds
Fatal
    Run Keyword And Ignore Error    Fatal Error    fatal reason
''', {'Working': 'PASS', **dict.fromkeys(('Continue', 'Unexpected Success', 'Mismatch', 'Case Sensitive', 'Wildcard Case Sensitive',
                                       'Prefix Mismatch', 'Exact Mismatch', 'Regexp Whole Message', 'Syntax', 'Timeout', 'Fatal'), 'FAIL')},
            keywords='Needs Argument\n    FOR    ${x}    IN    empty-body\n    END\n')
        assert workflow_events(root, 'Working') == [['after-warning']]
        assert workflow_events(root, 'Continue') == [['after-continue']]
        assert any(m.attrib['level'] == 'WARN' and 'warning reason' in (m.text or '') for m in root.findall('.//msg'))
        assert 'continued reason' in failure_reason(root, 'Continue')


def test_count_and_duration_repetition():
    with temporary_workspace() as d:
        path = d / 'effects.jsonl'
        cases = f'''Working
    Repeat Keyword    3 times    Effect    {path}    count
    Repeat Keyword    0    Effect    {path}    forbidden
    Repeat Keyword    -2    Effect    {path}    forbidden
    Repeat Keyword    0 seconds    Effect    {path}    forbidden
    Repeat Keyword    -1 seconds    Effect    {path}    forbidden
    Repeat Keyword    280 milliseconds    Effect    {path}    duration    0.12
Bad Count
    Repeat Keyword    bad times    No Operation
Bad Duration
    Repeat Keyword    nonsense seconds    No Operation
Failure Stops
    Repeat Keyword    4    Effect    {d / 'failed.jsonl'}    failing    0    9
'''
        utility_run(d, cases, {'Working': 'PASS', 'Bad Count': 'FAIL', 'Bad Duration': 'FAIL', 'Failure Stops': 'FAIL'})
        rows = effect_rows(path)
        assert [r[:2] for r in rows[:6]] == [[phase, 'count'] for _ in range(3) for phase in ('start', 'end')]
        duration = rows[6:]
        assert len(duration) >= 2 and len(duration) % 2 == 0
        assert [r[:2] for r in duration] == [[phase, 'duration'] for _ in range(len(duration)//2) for phase in ('start', 'end')]
        assert duration[-1][2] - duration[0][2] >= .26
        assert duration[-1][2] - duration[-2][2] >= .10
        # No call starts after the 280 ms allowance is exhausted (calls take 120 ms).
        assert duration[-2][2] - duration[0][2] < .33, duration
        assert [r[:2] for r in effect_rows(d / 'failed.jsonl')] == [['start', 'failing'], ['end', 'failing']]


def test_retry_results_intervals_and_configuration():
    with temporary_workspace() as d:
        cases = ''
        for name, interval in [('Default', '2 seconds'), ('Strict', 'strict: 2 seconds'),
                               ('Overrun', 'strict: 800 milliseconds')]:
            delay = 1
            cases += f'''{name}
    ${{v}}=    Wait Until Keyword Succeeds    4x    {interval}    Effect    {d / (name + '.jsonl')}    {name}    {delay}    3
    Check    ${{v}}    '{name}:done'
'''
        cases += f'''Deadline Success
    ${{v}}=    Wait Until Keyword Succeeds    2 seconds    0    Effect    {d / 'deadline.jsonl'}    deadline    0    1
    Check    ${{v}}    'deadline:done'
Exhausted
    Wait Until Keyword Succeeds    2x    0    Effect    {d / 'exhausted.jsonl'}    exhausted    0    8
Deadline Exhausted
    Wait Until Keyword Succeeds    40 milliseconds    0    Effect    {d / 'elapsed.jsonl'}    elapsed    0.1    99
'''
        invalid = {'Zero': ('0x', '0'), 'Negative': ('-2x', '0'), 'Bad Count': ('bad times', '0'),
                   'Bad Duration': ('bad seconds', '0'), 'Bad Interval': ('2x', 'bad interval')}
        for name, (retry, interval) in invalid.items():
            cases += f'{name}\n    Wait Until Keyword Succeeds    {retry}    {interval}    Effect    {d / "invalid.jsonl"}    invalid\n'
        cases += '''Syntax
    Wait Until Keyword Succeeds    3x    0    Stop With Syntax
Skip
    Wait Until Keyword Succeeds    3x    0    Stop With Skip
Timeout
    [Timeout]    50 milliseconds
    Wait Until Keyword Succeeds    3x    0    Stop With Timeout
Fatal
    Wait Until Keyword Succeeds    3x    0    Stop With Fatal
'''
        root = utility_run(d, cases, {**dict.fromkeys(('Default', 'Strict', 'Overrun', 'Deadline Success'), 'PASS'),
            **dict.fromkeys(('Exhausted', 'Deadline Exhausted', *invalid, 'Syntax', 'Timeout', 'Fatal'), 'FAIL'), 'Skip': 'SKIP'},
            keywords=f'''Stop With Syntax
    Effect    {d / 'syntax.jsonl'}    stop
    FOR    ${{x}}    IN    empty-body
    END
Stop With Skip
    Effect    {d / 'skip.jsonl'}    stop
    Skip    stop retry
Stop With Timeout
    Effect    {d / 'timeout.jsonl'}    stop
    Sleep    200 milliseconds
Stop With Fatal
    Effect    {d / 'fatal.jsonl'}    stop
    Fatal Error    stop retry
''')
        for kind in ('syntax', 'skip', 'timeout', 'fatal'):
            assert [r[:2] for r in effect_rows(d / (kind + '.jsonl'))] == [['start', 'stop'], ['end', 'stop']]
        for name in ('Default', 'Strict', 'Overrun'):
            rows = effect_rows(d / (name + '.jsonl'))
            assert [r[:2] for r in rows] == [[phase, name] for _ in range(4) for phase in ('start', 'end')]
            gaps = [rows[i + 1][2] - rows[i][2] for i in (1, 3, 5)]
            print(f'{name} observed retry gaps: {gaps}', flush=True)
            # Original observation (seconds): default best 2.001, strict best 0.992,
            # overrun best 0.001; upper margins leave 0.708 and 0.649 seconds.
            # Repeated attempts separate interval semantics with ample scheduler reserve.
            # Only the best observation supplies an upper bound; every gap supplies the lower bound.
            if name == 'Default':
                assert min(gaps) >= 1.95
            elif name == 'Strict':
                durations = [rows[i][2] - rows[i - 1][2] for i in (1, 3, 5)]
                assert all(gap >= max(0, 2 - duration) - .05
                           for gap, duration in zip(gaps, durations)), (gaps, durations)
                assert min(gaps) < 1.7, gaps
            else:
                assert min(gaps) < .65, gaps
        assert 'attempt-2' in failure_reason(root, 'Exhausted')
        assert 'attempt-1' in failure_reason(root, 'Deadline Exhausted')
        assert len(effect_rows(d / 'exhausted.jsonl')) == 4
        assert len(effect_rows(d / 'deadline.jsonl')) == 4
        assert len(effect_rows(d / 'elapsed.jsonl')) == 2
        assert not (d / 'invalid.jsonl').exists()


def test_runtime_variables_imports_and_metadata():
    with temporary_workspace() as d:
        write_file(d / 'Other.py', "def choice(): return 'other-choice'\n")
        write_file(d / 'values.py', "IMPORTED_VALUE = ['imported', 17]\n")
        write_file(d / 'extra.resource', '*** Keywords ***\nResource Operation\n    RETURN    resource-result\n')
        root = utility_run(d, r'''Working
    [Teardown]    Mark    ${TEST MESSAGE}
    [Documentation]    initial test doc
    [Tags]    initial-tag    other-initial
    Variable Should Exist    ${declared}
    Variable Should Not Exist    \${absent}
    ${v}=    Get Variable Value    \${declared}
    Check    ${v}    'initial'
    ${v}=    Get Variable Value    \${absent}    chosen-default
    Check    ${v}    'chosen-default'
    Set Test Variable    \${runtime}    changed
    ${v}=    Get Variables
    Check    ${v}[\${runtime}]    'changed'
    Variable Should Exist    \${runtime}
    Import Library    ${CURDIR}/Other.py
    Set Library Search Order    Active    Other
    ${v}=    Choice
    Check    ${v}    'utility-choice'
    Set Library Search Order    Other    Active
    ${v}=    Choice
    Check    ${v}    'other-choice'
    Import Resource    ${CURDIR}/extra.resource
    ${v}=    Resource Operation
    Check    ${v}    'resource-result'
    Import Variables    ${CURDIR}/values.py
    Check    ${IMPORTED_VALUE}    ['imported',17]
    Set Test Documentation    changed test doc
    Check    ${TEST DOCUMENTATION}    'changed test doc'
    Set Suite Documentation    changed suite doc
    Check    ${SUITE DOCUMENTATION}    'changed suite doc'
    Set Suite Metadata    Owner    changed owner
    Check    ${SUITE METADATA}[Owner]    'changed owner'
    Set Tags    changed-tag    extra-tag
    Remove Tags    initial-tag    other-initial
    Check Members    ${TEST TAGS}    ['changed-tag','extra-tag']
    Set Test Message    changed message
Missing Required
    Variable Should Exist    \${absent}
Unexpected Present
    Variable Should Not Exist    \${declared}
''', {'Working': 'PASS', 'Missing Required': 'FAIL', 'Unexpected Present': 'FAIL'},
            variables='${declared}    initial\n', settings='Documentation    initial suite doc\nMetadata    Owner    initial owner\n',
            keywords='')
        case = lifecycle_cases(root)['Working']
        assert workflow_events(root, 'Working') == [['changed message']]
        assert case.findtext('doc') == 'changed test doc'
        assert case.findtext('status') == 'changed message'
        assert {t.text for t in case.findall('tag')} == {'changed-tag', 'extra-tag'}
        assert root.findtext('./suite/doc') == 'changed suite doc'
        assert {m.attrib['name']: m.text for m in root.findall('./suite/meta')}['Owner'] == 'changed owner'


def test_wildcards_regular_expressions_and_literal_patterns():
    require_python((3, 13))
    with temporary_workspace() as d:
        root = utility_run(d, r'''Working
    Should Match    ab7xy    a?*[xy]
    Should Not Match    zab7xyz    ab7xy
    ${v}=    Should Match Regexp    prefix AB-271 suffix    ([a-z]+)-([0-9]+)    flags=IGNORECASE
    Mark    ${v}
    ${escaped}=    Regexp Escape    a+b[2].(x)?^$|{z}
    Mark    ${escaped}
Wildcard Whole
    Should Match    prefix ab7xy suffix    ab7xy
Single Character
    Should Match    cedar    ce?dar
Character Set
    Should Match    cedar    c[xy]dar
Regexp Anchors
    Should Match Regexp    prefix ab7xy suffix    ^ab7xy$
Regexp Missing
    Should Match Regexp    ordinary    [0-9]+
''', {'Working': 'PASS', 'Wildcard Whole': 'FAIL', 'Single Character': 'FAIL', 'Character Set': 'FAIL',
          'Regexp Anchors': 'FAIL', 'Regexp Missing': 'FAIL'})
        events = workflow_events(root, 'Working')
        match = re.search(r'([a-z]+)-([0-9]+)', 'prefix AB-271 suffix', re.IGNORECASE)
        assert events[0] == [[match.group(0), *match.groups()]]
        assert len(events) == 2 and len(events[1]) == 1
        pattern = events[1][0]
        literal = 'a+b[2].(x)?^$|{z}'
        assert re.fullmatch(pattern, literal)
        assert re.fullmatch(pattern, 'aaab2.x') is None
        assert re.fullmatch(pattern, literal + 'extra') is None


def test_pause_join_and_explicit_execution_control():
    with temporary_workspace() as d:
        path = d / 'control.jsonl'
        root = utility_run(d, f'''Working
    ${{v}}=    Catenate    oak    pine    elm
    Check    ${{v}}    'oak pine elm'
    ${{v}}=    Catenate    SEPARATOR=::    oak    pine
    Check    ${{v}}    'oak::pine'
    Effect    {path}    before-positive
    Sleep    150 milliseconds
    Effect    {path}    after-positive
    Sleep    -10 seconds
    Effect    {path}    after-negative
Early
    [Teardown]    Effect    {path}    early-cleanup
    Pass Execution    finished early
    Effect    {path}    forbidden
Accumulated
    [Teardown]    Effect    {path}    failure-cleanup
    Run Keyword And Continue On Failure    Fail    retained failure
    Pass Execution    early after failure
Explicit Failure
    [Teardown]    Effect    {path}    explicit-cleanup
    Fail    explicit reason
Explicit Skip
    [Teardown]    Effect    {path}    skip-cleanup
    Skip    skip reason
''', {'Working': 'PASS', 'Early': 'PASS', 'Accumulated': 'FAIL', 'Explicit Failure': 'FAIL', 'Explicit Skip': 'SKIP'})
        rows = effect_rows(path)
        assert [r[1] for r in rows if r[0] == 'start'] == ['before-positive', 'after-positive', 'after-negative',
                'early-cleanup', 'failure-cleanup', 'explicit-cleanup', 'skip-cleanup']
        assert all(rows[i][0] == 'start' and rows[i + 1][0] == 'end' for i in range(0, len(rows), 2))
        assert rows[2][2] - rows[1][2] >= .13
        assert rows[4][2] - rows[3][2] < 5
        assert 'retained failure' in failure_reason(root, 'Accumulated')


def test_length_and_occurrence_measurements():
    with temporary_workspace() as d:
        utility_run(d, r'''Working
    ${text}=    Set Variable    banana
    ${bytes}=    Convert To Bytes    00 ff 41    hex
    ${list}=    Create List    ${1}    ${True}    ${2}    ${1}
    ${mapping}=    Create Dictionary    one=1    two=2
    ${v}=    Get Length    ${text}
    Check    ${v}    6
    ${v}=    Get Length    ${bytes}
    Check    ${v}    3
    ${v}=    Get Length    ${list}
    Check    ${v}    4
    ${v}=    Get Length    ${mapping}
    Check    ${v}    2
    ${v}=    Get Count    aaaaa    aa
    Check    ${v}    2
    ${v}=    Get Count    ${list}    ${1}
    Check    ${v}    3
    ${v}=    Get Count    ${list}    missing
    Check    ${v}    0
Bad Length
    Get Length    ${42}
Bad Count
    Get Count    ${42}    a
''', {'Working': 'PASS', 'Bad Length': 'FAIL', 'Bad Count': 'FAIL'})


def test_keyword_inspection_and_active_library_objects():
    with temporary_workspace() as d:
        write_file(d / 'Other.py', "def choice(): return 'other-choice'\n")
        path = d / 'inspection.jsonl'
        root = utility_run(d, f'''Working
    Keyword Should Exist    Side Effect
    Keyword Should Exist    BuiltIn.No Operation
    ${{v}}=    Store    first
    Check    ${{v}}    ['first']
    ${{lib}}=    Get Library Instance    Active
    ${{v}}=    Call Method    ${{lib}}    store    second
    Check    ${{v}}    ['first','second']
    ${{v}}=    Store    third
    Check    ${{v}}    ['first','second','third']
    ${{all}}=    Get Library Instance    all=True
    ${{names}}=    Library Names    ${{all}}
    Mark    ${{names}}
    Same    ${{all}}[Active]    ${{lib}}
    ${{v}}=    Call Method    ${{all}}[Active]    store    fourth
    Check    ${{v}}    ['first','second','third','fourth']
    Side Effect
Missing Keyword
    Keyword Should Exist    Absent Operation
Ambiguous Keyword
    Keyword Should Exist    Choice
Invalid Keyword
    Keyword Should Exist    Invalid Definition
Missing Library
    Get Library Instance    AbsentLibrary
''', {'Working': 'PASS', 'Missing Keyword': 'FAIL', 'Ambiguous Keyword': 'FAIL',
                 'Invalid Keyword': 'FAIL', 'Missing Library': 'FAIL'}, settings='Library    Other.py\n',
            keywords=f'''Side Effect
    Effect    {path}    invoked
Invalid Definition
    [Arguments]    ${{x}}=default    ${{required}}
    No Operation
''')
        assert [r[:2] for r in effect_rows(path)] == [['start', 'invoked'], ['end', 'invoked']]
        assert {'Active', 'BuiltIn', 'Witness', 'Trace', 'Other'} <= set(workflow_events(root, 'Working')[0][0])
