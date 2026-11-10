# feature: F12
"""Real saved-result production and explicit post-processing observations."""
from _helpers import run_module, read_xml
from F10_helpers import artifact_run, statistic_counts


def saved_run(directory, cases, *, settings='', keywords='', options=(), section='Test Cases'):
    source = (f'*** Settings ***\n{settings}\n*** {section} ***\n{cases}'
              f'\n*** Keywords ***\n{keywords}')
    process = artifact_run(directory, source, ['--log', 'NONE', '--report', 'NONE', *options])
    root = read_xml(directory / 'output.xml').getroot()
    statuses = [s.attrib['status'] for s in root.findall('.//test/status')]
    assert statuses, process.stderr
    if 'FAIL' in statuses:
        assert 1 <= process.returncode <= 250, process.stderr
    else:
        assert process.returncode == 0, process.stderr
    return directory / 'output.xml'


def postprocess(directory, inputs, options=(), *, expected=0):
    directory.mkdir(parents=True, exist_ok=True)
    process = run_module('velun.velunexmerge', ['--outputdir', str(directory), '--output', 'output.xml',
                         '--log', 'NONE', '--report', 'NONE', *options, *map(str, inputs)])
    if 0 < expected < 251:
        assert 1 <= process.returncode <= 250, (process.stdout, process.stderr)
    else:
        assert process.returncode == expected, (process.stdout, process.stderr)
    if expected == 252:
        assert process.stderr, 'Rejected input must be reported on stderr.'
        return process
    return read_xml(directory / 'output.xml').getroot()


def result_signature(root):
    return ({t.attrib['name']: t.find('status').attrib['status'] for t in root.findall('.//test')},
            statistic_counts(root.find('./statistics/total/stat')))


DETAIL_CASES = '''Clean
    Selected
    Untouched
Warning
    Guarded
Broken
    Fail    final failure
Loops
    FOR    ${i}    IN    first    middle    last
        Log    for-${i}
        IF    $i == 'middle'    Log    loop-warning    WARN
    END
    ${n}=    Set Variable    ${0}
    WHILE    $n < 3
        Log    while-${n}
        ${n}=    Evaluate    $n + 1
    END
Retry
    Wait Until Keyword Succeeds    4x    0s    Eventually
'''
DETAIL_KEYWORDS = '''Selected
    [Tags]    reduce
    Inner    selected-payload
Untouched
    Inner    untouched-payload
Guarded
    [Tags]    reduce
    Log    warning-payload    WARN
    Inner    guarded-payload
Inner
    [Arguments]    ${text}
    Log    ${text}
Eventually
    ${count}=    Get Variable Value    ${ATTEMPTS}    ${0}
    ${count}=    Evaluate    $count + 1
    Set Suite Variable    ${ATTEMPTS}    ${count}
    Log    attempt-${count}
    IF    $count == 2    Log    retry-warning    WARN
    Should Be True    $count == 4
'''
