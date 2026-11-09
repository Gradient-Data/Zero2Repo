# feature: F15
"""Acceptance of real local commands through Velun's Process keywords."""
from pathlib import Path
from _helpers import temporary_workspace, write_file
from F15_helpers import process_run


def test_foreground_background_configuration_and_shell():
    with temporary_workspace() as d:
        (d / 'work').mkdir()
        process_run(d, r'''Working
    ${r}=    Run Process    @PY@    @ROOT@/child.py    config    @ROOT@/sync-effect    two words    ${42}    $F15_PARENT
    Check    ${r.rc}    0
    ${v}=    Decoded Json    ${r.stdout}
    Check    ${v}    {'args':['two words','42','$F15_PARENT'],'cwd':'@CWD@','env':{'F15_PARENT':'inherited','F15_EXTRA':None,'F15_ONLY':None}}
    ${v}=    Disk Bytes    @ROOT@/sync-effect
    Check    ${v}    b'executed'
    ${r}=    Run Process    @PY@    @ROOT@/child.py    config    @ROOT@/sync-config    ${7}    cwd=@ROOT@/work    env:F15_EXTRA=only
    Check    ${r.rc}    0
    ${v}=    Decoded Json    ${r.stdout}
    Check    ${v}    {'args':['7'],'cwd':'@ROOT@/work','env':{'F15_PARENT':'inherited','F15_EXTRA':'only','F15_ONLY':None}}
    ${env}=    Evaluate    {'F15_ONLY':'replacement','F15_EXTRA':'before'}
    ${p}=    Start Process    @PY@    @ROOT@/child.py    config    @ROOT@/async-effect    next arg    cwd=@ROOT@/work    env=${env}    env:F15_EXTRA=after
    ${r}=    Wait For Process    ${p}
    Check    ${r.rc}    0
    ${v}=    Decoded Json    ${r.stdout}
    Check    ${v}    {'args':['next arg'],'cwd':'@ROOT@/work','env':{'F15_PARENT':None,'F15_EXTRA':'after','F15_ONLY':'replacement'}}
    ${v}=    Disk Bytes    @ROOT@/async-effect
    Check    ${v}    b'executed'
    ${r}=    Run Process    /bin/echo    $F15_PARENT
    Check    ${r.stdout}    '$F15_PARENT'
    ${r}=    Run Process    /bin/echo    $F15_PARENT    shell=True
    Check    ${r.stdout}    'inherited'
'''.replace('@CWD@', str(Path.cwd())))


def test_stdin_capture_redirection_encoding_and_exit():
    with temporary_workspace() as d:
        write_file(d / 'input.txt', 'file input\nsecond line')
        cases = r'''Working
    ${r}=    Run Process    @PY@    @ROOT@/child.py    input
    ${v}=    Decoded Json    ${r.stdout}
    Check    ${v}    'parent input\\n'
    ${r}=    Run Process    @PY@    @ROOT@/child.py    input    stdin=literal input
    ${v}=    Decoded Json    ${r.stdout}
    Check    ${v}    'literal input'
    ${r}=    Run Process    @PY@    @ROOT@/child.py    input    stdin=@ROOT@/input.txt
    ${v}=    Decoded Json    ${r.stdout}
    Check    ${v}    'file input\\nsecond line'
    ${stream}=    Input Stream    @ROOT@/input.txt
    ${r}=    Run Process    @PY@    @ROOT@/child.py    input    stdin=${stream}
    ${v}=    Decoded Json    ${r.stdout}
    Check    ${v}    'file input\\nsecond line'
    ${r}=    Run Process    @PY@    @ROOT@/child.py    emit    636166e90d0a6c696e650d0a0d0a    6572726f720d0a    7    output_encoding=latin-1
    Check    ${r.rc}    7
    Check    ${r.stdout}    'café\\nline\\n'
    Check    ${r.stderr}    'error'
    ${hex}=    Console Encoded    café Ω
    ${r}=    Run Process    @PY@    @ROOT@/child.py    emit    ${hex}    657272    0
    Check    ${r.stdout}    'café Ω'
    Check    ${r.stderr}    'err'
    ${r}=    Run Process    @PY@    @ROOT@/child.py    emit    6f75740a    6572720a    0    stderr=STDOUT
    Check    ${r.stdout}    'out\\nerr'
    Check    ${r.stderr}    ''
    ${r}=    Run Process    @PY@    @ROOT@/child.py    emit    6f75740a    6572720a    0    stdout=@ROOT@/out    stderr=@ROOT@/err
    Check    ${r.stdout}    'out'
    Check    ${r.stderr}    'err'
    ${v}=    Disk Bytes    @ROOT@/out
    Check    ${v}    b'out\\n'
    ${v}=    Disk Bytes    @ROOT@/err
    Check    ${v}    b'err\\n'
    ${r}=    Run Process    @PY@    @ROOT@/child.py    emit    6f75740a    6572720a    0    stdout=DEVNULL    stderr=DEVNULL
    Check    ${r.rc}    0
    Check    ${r.stdout}    ''
    Check    ${r.stderr}    ''
'''
        process_run(d, cases)


def test_references_aliases_active_selection_and_pid():
    with temporary_workspace() as d:
        process_run(d, r'''No Active
    Get Process Id
Working
    ${a}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/first    normal    alias=first
    ${ap}=    Ready    @ROOT@/first
    ${b}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/second    normal    alias=second
    ${bp}=    Ready    @ROOT@/second
    Should Not Be Equal    ${ap}    ${bp}
    ${v}=    Get Process Id
    Should Be Equal    ${v}    ${bp}
    ${r}=    Run Process    @PY@    @ROOT@/child.py    emit    73796e63    00    0
    Check    ${r.stdout}    'sync'
    ${v}=    Get Process Id
    Should Be Equal    ${v}    ${bp}
    Switch Process    first
    ${v}=    Get Process Id
    Should Be Equal    ${v}    ${ap}
    ${v}=    Get Process Id    ${b}
    Should Be Equal    ${v}    ${bp}
    ${v}=    Is Process Running
    Check    ${v}    True
    Process Should Be Running    ${b}
    OS Alive    ${ap}
    OS Alive    ${bp}
    Release Child    @ROOT@/second
    ${r}=    Wait For Process    second
    Check    ${r.stdout}    'second'
    Process Should Be Stopped    ${b}
    ${v}=    Is Process Running    ${b}
    Check    ${v}    False
    OS Stopped    ${bp}
    Release Child    @ROOT@/first
    ${r}=    Wait For Process    ${a}
    Check    ${r.stdout}    'first'
    ${r}=    Get Process Result    first
    Check    ${r.rc}    0
    Check    ${r.stdout}    'first'
Not Running
    ${p}=    Start Process    @PY@    @ROOT@/child.py    emit    6f6b    6f6b    0
    ${r}=    Wait For Process    ${p}
    Check    ${r.stdout}    'ok'
    Process Should Be Running    ${p}
Not Stopped
    ${p}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/third    normal
    ${pid}=    Ready    @ROOT@/third
    Process Should Be Stopped    ${p}
Unknown Alias
    Get Process Id    not-registered
Unknown Reference
    Get Process Id    ${123456}
''', failures=('No Active', 'Not Running', 'Not Stopped', 'Unknown Alias', 'Unknown Reference'))


def test_wait_default_timeout_continue_terminate_and_kill():
    with temporary_workspace() as d:
        process_run(d, r'''Working
    ${p}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/kept    normal
    ${pid}=    Ready    @ROOT@/kept
    ${start}=    Clock Now
    ${r}=    Wait For Process    ${p}    timeout=0.3 seconds
    Check    ${r}    None
    Elapsed At Least    ${start}    0.3
    Elapsed At Most    ${start}    10
    OS Alive    ${pid}
    Process Should Be Running    ${p}
    ${event}=    Begin Event    @ROOT@/kept/release    create    2
    ${r}=    Wait For Process    ${p}
    Event Completed    ${event}    @ROOT@/kept/release    create
    Check    ${r.rc}    0
    Check    ${r.stdout}    'kept'
    OS Stopped    ${pid}
    Events Are    @ROOT@/kept    ["completed"]
    ${p}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/terminated    normal
    ${pid}=    Ready    @ROOT@/terminated
    ${r}=    Wait For Process    ${p}    timeout=0.2 seconds    on_timeout=terminate
    Check    ${r.rc}    0
    OS Stopped    ${pid}
    Events Are    @ROOT@/terminated    ["TERM","graceful"]
    ${p}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/killed    stubborn
    ${pid}=    Ready    @ROOT@/killed
    ${start}=    Clock Now
    ${r}=    Wait For Process    ${p}    timeout=0.2 seconds    on_timeout=kill
    Elapsed At Most    ${start}    15
    Should Not Be Equal    ${r.rc}    ${None}
    OS Stopped    ${pid}
    Process Should Be Stopped    ${p}
''')


def test_signals_termination_and_killing_select_real_target():
    with temporary_workspace() as d:
        process_run(d, r'''Working
    ${a}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/target    normal    alias=target
    ${ap}=    Ready    @ROOT@/target
    ${b}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/other    stubborn
    ${bp}=    Ready    @ROOT@/other
    Send Signal To Process    USR1    target
    Await Event    @ROOT@/target    USR1
    OS Alive    ${ap}
    OS Alive    ${bp}
    ${r}=    Terminate Process    target
    Check    ${r.rc}    0
    Events Are    @ROOT@/target    ["USR1","TERM","graceful"]
    OS Stopped    ${ap}
    OS Alive    ${bp}
    ${start}=    Clock Now
    ${r}=    Terminate Process    ${b}    kill=True
    Elapsed At Most    ${start}    15
    Should Not Be Equal    ${r.rc}    ${None}
    OS Stopped    ${bp}
    ${r}=    Get Process Result    ${b}
    Should Not Be Equal    ${r.rc}    ${None}
''')


def test_real_grace_period_process_tree_and_bulk_ownership():
    with temporary_workspace() as d:
        process_run(d, r'''Working
    ${control}=    Start Control    @ROOT@/child.py    @ROOT@/control
    ${cp}=    Ready    @ROOT@/control
    ${p}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/stubborn    stubborn
    ${pid}=    Ready    @ROOT@/stubborn
    ${start}=    Clock Now
    ${r}=    Terminate Process    ${p}
    Elapsed At Least    ${start}    30
    Elapsed At Most    ${start}    45
    OS Stopped    ${pid}
    Events Are    @ROOT@/stubborn    ["TERM"]
    OS Alive    ${cp}
    ${p}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/tree    tree
    ${pid}=    Ready    @ROOT@/tree
    ${child}=    Ready    @ROOT@/tree/child
    ${q}=    Start Process    @PY@    @ROOT@/child.py    managed    @ROOT@/another    normal
    ${qp}=    Ready    @ROOT@/another
    Terminate All Processes
    OS Stopped    ${pid}
    OS Stopped    ${child}
    OS Stopped    ${qp}
    Events Are    @ROOT@/tree    ["TERM","graceful"]
    Events Are    @ROOT@/tree/child    ["TERM","graceful"]
    Events Are    @ROOT@/another    ["TERM","graceful"]
    OS Alive    ${cp}
    Release Child    @ROOT@/control
    OS Stopped    ${cp}
    Events Are    @ROOT@/control    ["completed"]
''')


def test_command_line_splitting_joining_and_bad_quotes():
    with temporary_workspace() as d:
        process_run(d, r'''Working
    ${v}=    Split Command Line    tool "two words" 'third part' tail
    Check    ${v}    ['tool','two words','third part','tail']
    ${v}=    Split Command Line    one\\ two
    Check    ${v}    ['one\\\\','two']
    ${v}=    Split Command Line    one\\ two    escaping=True
    Check    ${v}    ['one two']
    ${line}=    Join Command Line    tool    two words    a"quote    final
    ${v}=    Parse Joined    ${line}
    Check    ${v}    ['tool','two words','a"quote','final']
Malformed
    Split Command Line    tool "unterminated
''', failures=('Malformed',))


def test_relative_redirection_and_unknown_configuration():
    with temporary_workspace() as d:
        (d / 'child-cwd').mkdir()
        process_run(d, r'''Working
    ${r}=    Run Process    @PY@    @ROOT@/child.py    emit    6f75740a    6572720a    0    cwd=@ROOT@/child-cwd    stdout=out.txt    stderr=err.txt
    Check    ${r.rc}    0
    Check    ${r.stdout}    'out'
    Check    ${r.stderr}    'err'
    ${v}=    Disk Bytes    @ROOT@/child-cwd/out.txt
    Check    ${v}    b'out\\n'
    ${v}=    Disk Bytes    @ROOT@/child-cwd/err.txt
    Check    ${v}    b'err\\n'
Unknown Configuration
    Run Process    @PY@    @ROOT@/child.py    config    @ROOT@/should-not-run    wrong_option=value
''', failures=('Unknown Configuration',))
        assert not (d / 'should-not-run').exists()


def test_start_failures_are_distinct_from_nonzero_child_exit():
    with temporary_workspace() as d:
        process_run(d, r'''Working
    ${r}=    Run Process    @PY@    @ROOT@/child.py    emit    646f6e65    646961676e6f73746963    23
    Check    ${r.rc}    23
    Check    ${r.stdout}    'done'
    Check    ${r.stderr}    'diagnostic'
Missing Executable
    Start Process    @ROOT@/nonexistent-executable
Invalid Directory
    Start Process    @PY@    @ROOT@/child.py    config    @ROOT@/not-started    cwd=@ROOT@/missing-directory
''', failures=('Missing Executable', 'Invalid Directory'))
        assert not (d / 'not-started').exists()
