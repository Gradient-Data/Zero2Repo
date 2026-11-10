# feature: F10
"""Acceptance coverage for execution results, reporting, and logging."""
from datetime import datetime
import pytest
from velun.api import ExecutionResult, ResultWriter
from velun.errors import DataError
from _helpers import read_xml, read_json, write_file, call_public, keyword_calls
from F03_helpers import library_outcomes
from F10_helpers import (ARTIFACT_CASES, artifact_run, artifact_cases, timed_artifacts,
                         check_recorded_interval, rendered_probe, statistic_counts, public_result_messages)

EXPECTED = {'Accepted': 'PASS', 'Rejected': 'FAIL', 'Omitted': 'SKIP'}


def test_default_artifacts_and_real_timings(tmp_path):
    process, before, after, interval = timed_artifacts(tmp_path)
    root = read_xml(tmp_path / 'output.xml').getroot()
    library_outcomes(process, root, EXPECTED)
    suite = root.find('suite')
    assert suite.find('doc').text == 'Artifact suite documentation'
    assert suite.find("meta[@name='Owner']").text == 'Acceptance team'
    cases = artifact_cases(tmp_path)
    assert cases['Accepted'].find('doc').text == 'Accepted documentation'
    assert {x.text for x in cases['Accepted'].findall('tag')} == {'red', 'common'}
    assert cases['Rejected'].find('status').text == 'deliberate rejection'
    assert cases['Omitted'].find('status').text == 'deliberate omission'
    assert cases['Accepted'].find(".//msg[.='nested payload']") is not None
    assert cases['Accepted'].find('.//if/branch/kw') is not None
    assert {(m.attrib['level'], m.text) for m in root.findall('./errors/msg')} == {
        ('WARN', 'execution warning'), ('ERROR', 'execution error')}
    controlled = keyword_calls(cases['Accepted'], 'Controlled Operation')[0]
    for node in (controlled, cases['Accepted'], suite):
        status = node.find('status')
        check_recorded_interval(datetime.fromisoformat(status.attrib['start']),
                                float(status.attrib['elapsed']), process, before, after, interval)
    for name in ('log.html', 'report.html'):
        assert (tmp_path / name).stat().st_size > 0


def test_rendered_log_report_and_navigation(tmp_path):
    artifact_run(tmp_path, expected=EXPECTED)
    result = rendered_probe(tmp_path, tmp_path / 'report.html', '''
const doc = frame.contentDocument;
doc.querySelector('a[href="#totals"]').click();
await pause();
const totals=Array.from(doc.querySelectorAll('#total-stats tbody tr td.stats-col-stat')).map(e=>Number(e.textContent));
const tagRows=doc.querySelectorAll('#tag-stats tbody tr').length;
const suiteRows=doc.querySelectorAll('#suite-stats tbody tr').length;
const rows = Array.from(doc.querySelectorAll('#test-details tbody tr')).map(row => ({
name: resultTestName(row),
status: row.querySelector('.details-col-status').textContent.trim()}));
const link = Array.from(doc.querySelectorAll('#test-details a')).find(a => a.textContent.includes('Accepted'));
const href = link.href;
frame.src = href;
await new Promise(resolve => frame.onload = resolve);
await pause();
const log = frame.contentDocument;
const test = Array.from(log.querySelectorAll('.test')).find(e => e.querySelector('.name').textContent.includes('Accepted'));
const fragment = decodeURIComponent(new URL(href).hash.slice(1));
const addressed = log.getElementById(fragment);
const addressedTest = addressed ? addressed.closest('.test') : null;
const linkTarget = addressedTest ? addressedTest.querySelector('.element-header > .name').textContent.trim() : null;
test.querySelector('a.expand').click();
await pause();
return {rows, totals, tagRows, suiteRows, href, linkTarget, title:log.title, text:test.innerText,
keywordNames:Array.from(test.querySelectorAll('.keyword > .element-header > .name')).map(e=>e.textContent.trim()),
labels:Array.from(test.querySelectorAll('.keyword > .element-header > .label')).map(e=>e.textContent),
suiteFailed:log.querySelector('.suite > .element-header > .label').classList.contains('fail')};
''')
    assert {row['name']: row['status'] for row in result['rows']} == EXPECTED
    assert result['totals'] == [3, 1, 1, 1]
    assert result['tagRows'] == 3 and result['suiteRows'] == 1
    assert 'log.html#' in result['href']
    # The report entry's fragment addresses the detailed log element of that same test.
    assert result['linkTarget'] == 'Accepted'
    assert 'Log' in result['title']
    assert 'nested payload' in result['text']
    assert 'Nested' in result['keywordNames']
    assert 'IF' in result['labels']
    assert result['suiteFailed']


def test_severity_thresholds_and_execution_issues(tmp_path):
    source = '*** Test Cases ***\nMessages\n' + ''.join(
        f'    Log    severity-{level}    {level}\n' for level in ('TRACE','DEBUG','INFO','WARN','ERROR'))
    levels = ('TRACE','DEBUG','INFO','WARN','ERROR')
    for threshold in (None, *levels, 'NONE'):
        directory = tmp_path / str(threshold)
        options = [] if threshold is None else ['--loglevel', threshold]
        artifact_run(directory, source, options, {'Messages': 'PASS'})
        root = read_xml(directory / 'output.xml').getroot()
        actual = {(m.attrib['level'], m.text) for m in root.findall('./suite/test/kw/msg')
                  if (m.text or '').startswith('severity-')}
        visible = levels[levels.index(threshold or 'INFO'):] if threshold != 'NONE' else ()
        assert actual == {(level, 'severity-' + level) for level in visible}
        assert {(m.attrib['level'], m.text) for m in root.findall('./errors/msg')} == {
            ('WARN','severity-WARN'), ('ERROR','severity-ERROR')}


def test_library_stream_association_and_console_modes(tmp_path):
    library = write_file(tmp_path / 'Streams.py', '''import sys
from velun.api import logger

def emit(token):
    logger.info('library-' + token)
    print('stdout-' + token)
    print('stderr-' + token, file=sys.stderr)
    logger.console('console-' + token)
    logger.warn('warning-' + token)
''')
    source = f'*** Settings ***\nLibrary    {library}\n*** Test Cases ***\nFirst\n    Emit    first\nSecond\n    Emit    second\n'
    for mode in (None, 'dotted', 'quiet', 'none'):
        directory = tmp_path / str(mode)
        options = [] if mode is None else ['--console', mode]
        process = artifact_run(directory, source, options, {'First':'PASS','Second':'PASS'})
        cases = artifact_cases(directory)
        for name, token in (('First','first'), ('Second','second')):
            messages = [m.text for call in keyword_calls(cases[name], 'Emit') for m in call.findall('msg')]
            assert 'library-' + token in messages
            assert 'stdout-' + token in messages
            assert 'stderr-' + token in messages
            assert 'console-' + token not in messages
            assert ('console-' + token).encode() in process.stdout
            if mode != 'none':
                assert ('warning-' + token).encode() in process.stderr
            else:
                assert ('warning-' + token).encode() not in process.stderr
        console = process.stdout.decode()
        if mode is None:
            assert 'First' in console and 'Second' in console and '| PASS |' in console
        if mode in (None, 'dotted'):
            assert '2 tests, 2 passed, 0 failed' in console
        else:
            assert console.splitlines() == ['console-first', 'console-second']
    compact = artifact_run(tmp_path / 'progress', options=['--console','dotted'], expected=EXPECTED)
    compact_lines = compact.stdout.decode().splitlines()
    assert '.Fs' in compact_lines
    # Final totals follow the declared outcomes (3 tests: 1 passed, 1 failed, 1 skipped).
    assert any(line.startswith('3 tests, 1 passed, 1 failed') for line in compact_lines), compact_lines


def test_statistics_groups_and_presentation_selection(tmp_path):
    source = tmp_path / 'tree'
    write_file(source / 'child' / 'leaf.velun', ARTIFACT_CASES)
    from _helpers import run_module
    for label, options in [('all', []), ('selected', ['--suitestatlevel','1','--tagstatinclude','*e*',
            '--tagstatexclude','b*','--tagstatcombine','redANDcommon:Intersection',
            '--tagstatcombine','redORblue:Union','--tagdoc','red:Red documentation',
            '--tagstatlink','red:https://example.invalid/red:Red reference'])]:
        directory = tmp_path / label
        directory.mkdir()
        process = run_module('velun', ['--outputdir',str(directory), *options, str(source)])
        root = read_xml(directory / 'output.xml').getroot()
        library_outcomes(process, root, EXPECTED)
        assert statistic_counts(root.find('./statistics/total/stat')) == (1,1,1)
        tags = {s.text:s for s in root.findall('./statistics/tag/stat')}
        if label == 'all':
            assert {k:statistic_counts(v) for k,v in tags.items()} == {'red':(1,0,1),'blue':(0,1,0),'common':(1,1,0)}
            # Every suite level contains the single leaf file's three tests.
            assert [statistic_counts(s) for s in root.findall('./statistics/suite/stat')] == [(1,1,1)] * 3
        else:
            assert {k:statistic_counts(v) for k,v in tags.items()} == {'red':(1,0,1),'Intersection':(1,0,0),'Union':(1,1,1)}
            assert [statistic_counts(s) for s in root.findall('./statistics/suite/stat')] == [(1,1,1)]
            assert tags['red'].attrib['doc'] == 'Red documentation'
            assert 'https://example.invalid/red' in tags['red'].attrib['links']
            rendered = rendered_probe(directory, directory / 'report.html', '''
const doc=frame.contentDocument;
const row=Array.from(doc.querySelectorAll('tr')).find(r => r.querySelector('td[title="Red documentation"]'));
return {text:row.innerText, links:Array.from(row.querySelectorAll('a')).map(a=>({text:a.textContent,href:a.href}))};''')
            assert 'red' in rendered['text']
            assert {'text':'Red reference','href':'https://example.invalid/red'} in rendered['links']


def test_public_result_readers_and_invalid_input(tmp_path):
    for extension in ('xml','json'):
        directory = tmp_path / extension
        directory.mkdir()
        process, before, after, interval = timed_artifacts(directory, output='output.' + extension)
        path = directory / ('output.' + extension)
        result = call_public(ExecutionResult, path).value
        suite = result.suite
        assert suite.doc == 'Artifact suite documentation'
        assert suite.metadata['Owner'] == 'Acceptance team'
        assert {t.name:t.status for t in suite.tests} == EXPECTED
        assert suite.tests[1].message == 'deliberate rejection'
        assert suite.tests[2].message == 'deliberate omission'
        assert set(suite.tests[0].tags) == {'red','common'}
        assert suite.tests[0].doc == 'Accepted documentation'
        assert ('INFO', 'nested payload') in public_result_messages(result)
        assert {(m.level, m.message) for m in result.errors} == {('WARN','execution warning'), ('ERROR','execution error')}
        assert (result.statistics.total.passed, result.statistics.total.failed, result.statistics.total.skipped) == (1,1,1)
        for item in (suite, suite.tests[0], suite.tests[0].body[0]):
            check_recorded_interval(item.start_time, item.elapsed_time.total_seconds(), process, before, after, interval)
        if extension == 'xml':
            raw = read_xml(path).getroot().find('suite')
            assert raw.attrib['name'] == suite.name
            assert [t.attrib['name'] for t in raw.findall('test')] == [t.name for t in suite.tests]
        else:
            raw = read_json(path)['suite']
            assert raw['name'] == suite.name
            assert [t['name'] for t in raw['tests']] == [t.name for t in suite.tests]
    for name, content in [('bad.xml','<velun><suite>'),('bad.json','{"suite":'),('empty.xml','')]:
        path = write_file(tmp_path / name, content)
        with pytest.raises(DataError):
            call_public(ExecutionResult, path)
    with pytest.raises(DataError):
        call_public(ExecutionResult, tmp_path / 'missing.xml')


def test_edit_save_and_regenerate_reports(tmp_path):
    artifact_run(tmp_path, expected=EXPECTED)
    result = call_public(ExecutionResult, tmp_path / 'output.xml').value
    result.suite.name = 'Revised suite'
    result.suite.doc = 'Revised documentation'
    result.suite.metadata['Owner'] = 'Revised owner'
    case = result.suite.tests[1]
    case.name, case.status, case.message = 'Repaired', 'PASS', 'resolved by reviewer'
    case.tags = ['revised']
    for extension in ('xml','json'):
        target = tmp_path / ('revised.' + extension)
        call_public(result.save, target)
        loaded = call_public(ExecutionResult, target).value
        assert loaded.suite.name == 'Revised suite'
        assert loaded.suite.doc == 'Revised documentation'
        assert loaded.suite.metadata['Owner'] == 'Revised owner'
        assert {t.name:t.status for t in loaded.suite.tests} == {'Accepted':'PASS','Repaired':'PASS','Omitted':'SKIP'}
        assert loaded.suite.tests[1].message == 'resolved by reviewer'
        assert list(loaded.suite.tests[1].tags) == ['revised']
        assert (loaded.statistics.total.passed,loaded.statistics.total.failed,loaded.statistics.total.skipped) == (2,0,1)
    call_public(ResultWriter(result).write_results, outputdir=str(tmp_path / 'rewritten'), log='log.html', report='report.html')
    rendered = rendered_probe(tmp_path, tmp_path / 'rewritten' / 'report.html', '''
const doc=frame.contentDocument;
doc.querySelector('a[href="#totals"]').click(); await pause();
return {totals:Array.from(doc.querySelectorAll('#total-stats tbody tr td.stats-col-stat')).map(e=>Number(e.textContent)),title:doc.title, rows:Array.from(doc.querySelectorAll('#test-details tbody tr')).map(r=>({name:resultTestName(r),status:r.querySelector('.details-col-status').textContent.trim()}))};''')
    assert 'Revised suite' in rendered['title']
    assert rendered['totals'] == [3,2,0,1]
    assert {r['name']:r['status'] for r in rendered['rows']} == {'Accepted':'PASS','Repaired':'PASS','Omitted':'SKIP'}


def test_runtime_threshold_change_restore_and_invalid_level(tmp_path):
    source = '''*** Test Cases ***
Changes
    ${old}=    Set Log Level    TRACE
    Should Be Equal    ${old}    DEBUG
    Log    trace-enabled    TRACE
    ${old}=    Set Log Level    ERROR
    Should Be Equal    ${old}    TRACE
    Log    info-suppressed    INFO
    Log    error-enabled    ERROR
    ${old}=    Set Log Level    NONE
    Should Be Equal    ${old}    ERROR
    Log    error-suppressed    ERROR
    ${old}=    Reset Log Level
    Should Be Equal    ${old}    NONE
    Log    debug-restored    DEBUG
    Log    trace-suppressed    TRACE
Invalid
    Set Log Level    unsupported-severity
'''
    process = artifact_run(tmp_path, source, ['--loglevel','DEBUG'], {'Changes':'PASS','Invalid':'FAIL'})
    root = read_xml(tmp_path / 'output.xml').getroot()
    messages = {m.text for m in root.findall('./suite/test/kw/msg')}
    assert {'trace-enabled','error-enabled','debug-restored'} <= messages
    assert not {'info-suppressed','error-suppressed','trace-suppressed'} & messages
    assert artifact_cases(tmp_path)['Invalid'].find('status').text


def test_optional_formats_and_independent_artifact_disabling(tmp_path):
    options = ['--xunit','summary.xml','--debugfile','debug.txt']
    artifact_run(tmp_path / 'all', options=options, expected=EXPECTED)
    unit = read_xml(tmp_path / 'all' / 'summary.xml').getroot()
    assert (int(unit.attrib['tests']),int(unit.attrib['failures']),int(unit.attrib['skipped'])) == (3,1,1)
    assert {c.attrib['name'] for c in unit.findall('testcase')} == set(EXPECTED)
    assert unit.find("testcase[@name='Rejected']/failure") is not None
    assert unit.find("testcase[@name='Omitted']/skipped") is not None
    debug = (tmp_path / 'all' / 'debug.txt').read_text()
    debug_lines = debug.splitlines()
    for name in ('Accepted', 'Rejected', 'Omitted'):
        assert any(line.endswith('START TEST: ' + name) for line in debug_lines)
    assert any(' START KEYWORD: Nested [' in line for line in debug_lines)
    artifact_run(tmp_path / 'json', options=['--output','output.json'])
    raw = read_json(tmp_path / 'json' / 'output.json')
    assert {t['name']:t['status'] for t in raw['suite']['tests']} == EXPECTED
    artifact_run(tmp_path / 'legacy', options=['--legacyoutput'], expected=EXPECTED)
    legacy = read_xml(tmp_path / 'legacy' / 'output.xml').getroot()
    assert legacy.find('./suite/test/status').attrib['starttime']
    assert legacy.find('./suite/test/status').attrib['endtime']
    assert {t.attrib['name']:t.find('status').attrib['status'] for t in legacy.findall('./suite/test')} == EXPECTED
    assert legacy.find(".//msg[.='nested payload']") is not None
    files = {'output':'output.xml','log':'log.html','report':'report.html','xunit':'summary.xml','debugfile':'debug.txt'}
    for disabled, filename in files.items():
        directory = tmp_path / disabled
        process = artifact_run(directory, options=[*options, '--'+disabled,'NONE'])
        assert 0 < process.returncode < 251, process.stderr
        assert not (directory / filename).exists()
        if disabled != 'output':
            library_outcomes(process, read_xml(directory / 'output.xml').getroot(), EXPECTED)
        else:
            summary = read_xml(directory / 'summary.xml').getroot()
            assert (int(summary.attrib['tests']), int(summary.attrib['failures']), int(summary.attrib['skipped'])) == (3,1,1)
        if disabled == 'output':
            assert not (directory / 'log.html').exists()
            assert b'[ ERROR ]' in process.stderr
        for other, otherfile in files.items():
            if other != disabled and not (disabled == 'output' and other == 'log'):
                assert (directory / otherfile).stat().st_size > 0
