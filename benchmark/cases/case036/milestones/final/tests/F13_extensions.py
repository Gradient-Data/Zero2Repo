# feature: F13
"""Acceptance tests for caller-provided execution and result extensions."""
import json
from collections import Counter
from velun.api import ExecutionResult, ResultVisitor
from _helpers import write_file, read_xml, call_public
from _helpers import keyword_calls
from F01_helpers import native_case
from F03_helpers import library_outcomes
from F10_helpers import rendered_probe
from F11_helpers import configured_run, configured_result, configuration_error
from F12_helpers import postprocess
from F13_helpers import extension_bank, extension_records, extension_errors


def test_listener_notifications_nesting_and_priority(tmp_path):
    extension_bank(tmp_path)
    trace, order = tmp_path/'trace.jsonl', tmp_path/'order.jsonl'
    source = write_file(tmp_path/'tree'/'child.velun', f'''*** Settings ***
Library    HookBank.LibraryOrder    {order}
*** Test Cases ***
Observed
    Present
    FOR    ${{item}}    IN    alpha    beta
        IF    True
            Log    nested-${{item}}
        END
    END
    WHILE    False
        No Operation
    END
    TRY
        No Operation
    FINALLY
        No Operation
    END
    GROUP    named block
        No Operation
    END
''')
    write_file(source.parent/'__init__.velun', '*** Settings ***\nName    Tree\n')
    options = ['--pythonpath',str(tmp_path),'--listener',f'HookBank.Trace:{trace}',
               '--log','log.html','--report','report.html']
    for label, priority in [('low','-4'),('default',None),('zero','0'),('high','7.5'),('second-zero','0')]:
        options += ['--listener', f'HookBank.Partial:{order}:{label}' + (f':{priority}' if priority is not None else '')]
    directory = tmp_path/'run'
    process = configured_run(directory,[source.parent],options)
    library_outcomes(process,configured_result(directory),{'Observed':'PASS'})
    assert b'[ ERROR ]' not in process.stderr, process.stderr
    # Numeric priority orders across command-line and library listeners: library 10 precedes CLI 7.5.
    priority_order = ['library-ten','high','default','zero','second-zero','library-default','library-zero','low']
    assert extension_records(order) == (
        [[label,'start_test','Observed'] for label in priority_order] +
        [[label,'end_test','Observed','PASS'] for label in priority_order])
    events = extension_records(trace)
    stack, seen = [], set()
    for event, *values in events:
        if event.startswith('start_'):
            kind = event[6:]
            stack.append((kind, values[:2]))
            seen.add(kind)
        elif event.startswith('end_'):
            assert stack.pop() == (event[4:], values[:2])
            assert values[2] in ('PASS','NOT RUN'), values
    assert not stack
    assert {'suite','test','keyword','for','for_iteration','if','if_branch','while','try','try_branch','group'} <= seen
    assert any(e[:3] == ['start_suite','SUITE','Tree'] for e in events)
    assert ['end_test','TEST','Observed','PASS'] in events
    assert ['message','INFO','nested-alpha'] in events
    assert ['message','INFO','nested-beta'] in events
    for kind in ('output','log','report'):
        filename = 'output.xml' if kind == 'output' else kind+'.html'
        assert ['artifact',kind,str(directory/filename)] in events
        assert (directory/filename).is_file()


def test_legacy_observation_and_current_listener_edits(tmp_path):
    extension_bank(tmp_path)
    trace = tmp_path/'legacy.jsonl'
    source = write_file(tmp_path/'suite.velun', '''*** Test Cases ***
Rewritten
    [Tags]    original
    Fail    would fail without editing
Override
    No Operation
''')
    directory = tmp_path/'run'
    process = configured_run(directory,[source],['--pythonpath',str(tmp_path),
        '--listener',f'HookBank.Legacy:{trace}','--listener','HookBank.Edit'])
    root = configured_result(directory)
    library_outcomes(process,root,{'Rewritten':'PASS','Override':'FAIL'})
    assert b'[ ERROR ]' not in process.stderr, process.stderr
    records = extension_records(trace)
    assert ['legacy-start','Rewritten',['original']] in records
    assert ['legacy-end','Rewritten','PASS'] in records
    assert ['legacy-log','INFO','rewritten-call'] in records
    assert root.find("./suite/meta[@name='Review']").text == 'listener-edit'
    rewritten = root.find(".//test[@name='Rewritten']")
    assert keyword_calls(rewritten, 'Log')[0].find('msg').text == 'rewritten-call'
    for test in root.findall('.//test'):
        assert 'reviewed' in [t.text for t in test.findall('tag')]
        assert test.find("meta[@name='Decision']").text == 'edited'
    assert root.find(".//test[@name='Override']/status").text == 'caller outcome'


def test_listener_scope_and_registration_callback_errors(tmp_path):
    extension_bank(tmp_path)
    scoped, global_events = tmp_path/'scoped.jsonl', tmp_path/'global.jsonl'
    active = write_file(tmp_path/'tree'/'active.velun',f'''*** Settings ***
Library    HookBank.Scoped    {scoped}
*** Test Cases ***
Active
    ${{value}}=    Present
    Should Be Equal    ${{value}}    active
''')
    write_file(active.parent/'other.velun',native_case('Outside'))
    directory = tmp_path/'scope'
    process = configured_run(directory,[active.parent],['--pythonpath',str(tmp_path),
        '--listener',f'HookBank.Partial:{global_events}:global'])
    library_outcomes(process,configured_result(directory),{'Active':'PASS','Outside':'PASS'})
    assert b'[ ERROR ]' not in process.stderr, process.stderr
    assert extension_records(scoped) == [['scoped','Active']]
    assert Counter(map(tuple, extension_records(global_events))) == Counter([
        ('global','start_test','Active'),('global','end_test','Active','PASS'),
        ('global','start_test','Outside'),('global','end_test','Outside','PASS')])
    for error in ('BadVersion','BrokenCallback'):
        directory = tmp_path/error
        process = configured_run(directory,[active],['--pythonpath',str(tmp_path),'--listener','HookBank.'+error])
        root = configured_result(directory)
        library_outcomes(process,root,{'Active':'PASS'})
        extension_errors(process,root)

    bad_library = write_file(tmp_path/'bad-library.velun',
        '*** Settings ***\nLibrary    HookBank.BadLibrary\n' + native_case('After Registration Error'))
    directory = tmp_path/'library-error'
    process = configured_run(directory,[bad_library],['--pythonpath',str(tmp_path)])
    root = configured_result(directory)
    library_outcomes(process,root,{'After Registration Error':'PASS'})
    extension_errors(process,root)


def test_ordered_prerun_modifiers_edit_before_selection(tmp_path):
    extension_bank(tmp_path)
    source = write_file(tmp_path/'tree'/'nested.velun','''*** Settings ***
Name    Nested
*** Test Cases ***
Original
    Log    original
    Fail    deleted statement must not execute
Remove
    Fail    removed body must not execute
Unselected
    Fail    filtered body must not execute
''')
    write_file(source.parent/'__init__.velun', '*** Settings ***\nName    Tree\n')
    write_file(source.parent/'discard.velun','*** Settings ***\nName    Discard\n' + native_case('Discarded'))
    directory = tmp_path/'modified'
    process = configured_run(directory,[source.parent],['--pythonpath',str(tmp_path),
        '--prerunmodifier','HookBank.First','--prerunmodifier','HookBank.Second',
        '--include','selected','--test','Renamed','--test','Added','--test','Remove','--test','Suite Added'])
    root = configured_result(directory)
    library_outcomes(process,root,{'Suite Added':'PASS','Added':'PASS','Renamed':'PASS'})
    assert b'[ ERROR ]' not in process.stderr, process.stderr
    assert [t.attrib['name'] for t in root.findall('.//test')] == ['Suite Added','Added','Renamed']
    assert [s.attrib['name'] for s in root.findall('./suite/suite')] == ['Inserted','Nested']
    assert root.find(".//test[@name='Suite Added']/kw/msg").text == 'suite-added-effect'
    assert keyword_calls(root.find(".//test[@name='Renamed']"), 'Log')[0].find('msg').text == 'first-second'
    assert root.find(".//test[@name='Added']/kw/msg").text == 'added-effect'
    assert root.find("./suite/suite[@name='Nested']/meta[@name='Sequence']").text == 'first-second'
    for modifier in ('HookBank.Absent','HookBank.BrokenModifier'):
        directory = tmp_path/modifier
        process = configured_run(directory,[source],['--pythonpath',str(tmp_path),'--prerunmodifier',modifier])
        root = configured_result(directory)
        library_outcomes(process,root,{'Original':'FAIL','Remove':'FAIL','Unselected':'FAIL'})
        extension_errors(process,root)


def test_public_result_traversal_and_prevelunexmerge_artifacts(tmp_path):
    bank = extension_bank(tmp_path)
    source = write_file(tmp_path/'tree'/'deep.velun','''*** Settings ***
Name    Deep
*** Test Cases ***
Chosen
    Fail    original rejection
Untouched
    No Operation
''')
    directory = tmp_path/'original'
    process = configured_run(directory,[source.parent])
    library_outcomes(process,configured_result(directory),{'Chosen':'FAIL','Untouched':'PASS'})
    original = directory/'output.xml'
    before = original.read_bytes()
    result = call_public(ExecutionResult,str(original)).value
    class Select(ResultVisitor):
        def __init__(self): self.selected = []
        def visit_test(self, test):
            if test.name == 'Chosen':
                test.doc = 'public descendant edit'
                self.selected.append(test)
    visitor = Select()
    call_public(result.visit,visitor)
    assert len(visitor.selected) == 1
    assert result.suite.suites[0].tests[0].doc == 'public descendant edit'
    saved = tmp_path/'visited.xml'
    call_public(result.save,str(saved))
    assert read_xml(saved).find(".//test[@name='Chosen']/doc").text == 'public descendant edit'
    output = tmp_path/'reviewed'
    root = postprocess(output,[original],['--pythonpath',str(bank.parent),
        '--prevelunexmergemodifier','HookBank.ResultEdit','--log','log.html','--report','report.html'])
    assert original.read_bytes() == before
    assert {t.attrib['name']:t.find('status').attrib['status'] for t in root.findall('.//test')} == {'Chosen':'PASS','Untouched':'PASS'}
    test = root.find(".//test[@name='Chosen']")
    assert test.find('status').text == 'review accepted'
    assert test.find('doc').text == 'edited descendant documentation'
    assert 'result-reviewed' in [t.text for t in test.findall('tag')]
    assert [m.text for m in test.findall('.//msg')] == ['replacement-content']
    assert root.find("./suite/suite/meta[@name='Review']").text == 'result-edit'
    visible = rendered_probe(output,output/'report.html','''
const doc=frame.contentDocument;
doc.querySelector('a[href="#totals"]').click(); await pause();
return Array.from(doc.querySelectorAll('#test-details tbody tr')).map(row=>[resultTestName(row),row.querySelector('.details-col-status').textContent.trim()]);
''')
    assert dict(visible) == {'Chosen':'PASS','Untouched':'PASS'}
    content = rendered_probe(output,output/'log.html','''
const doc=frame.contentDocument;
for (const header of doc.querySelectorAll('.suite > .element-header')) header.click();
await pause();
for (const header of doc.querySelectorAll('.test > .element-header')) header.click();
await pause();
const chosen=Array.from(doc.querySelectorAll('.test')).find(test=>
    test.querySelector('.element-header > .name').textContent.trim()==='Chosen');
return {messages:Array.from(chosen.querySelectorAll('.messages td.message')).map(e=>e.textContent),
        docs:Array.from(chosen.querySelectorAll('.metadata td.doc')).map(e=>e.textContent)};
''')
    assert content['messages'] == ['replacement-content']
    assert content['docs'] == ['edited descendant documentation']


def test_custom_parser_defaults_override_and_source_errors(tmp_path):
    extension_bank(tmp_path)
    init = {'name':'Custom Root','origin':'initialization','tags':['inherited'],
            'timeout':'19 seconds','setup':'inherited setup','teardown':'inherited teardown'}
    write_file(tmp_path/'sources'/'__init__.spec',json.dumps(init))
    source_data = {'name':'Parsed Content','tests':[{'name':'Generated',
        'calls':[['Log',['custom-source-payload']],['Should Be Equal',['actual','actual']]]}]}
    source = write_file(tmp_path/'sources'/'child.spec',json.dumps(source_data))
    options = ['--pythonpath',str(tmp_path),'--parser','HookBank.SourceParser']
    directory = tmp_path/'parsed'
    process = configured_run(directory,[source.parent],options)
    root = configured_result(directory)
    library_outcomes(process,root,{'Generated':'PASS'})
    assert b'[ ERROR ]' not in process.stderr, process.stderr
    assert root.find('./suite').attrib['name'] == 'Custom Root'
    assert root.find("./suite/meta[@name='Origin']").text == 'initialization'
    test = root.find('.//test')
    assert [t.text for t in test.findall('tag')] == ['inherited']
    assert test.find('timeout').attrib['value'] == '19 seconds'
    assert test.find("kw[@type='SETUP']/msg").text == 'inherited setup'
    assert test.find("kw[@type='TEARDOWN']/msg").text == 'inherited teardown'
    assert 'custom-source-payload' in [m.text for m in test.findall('kw/msg')]
    override = write_file(tmp_path/'override.velun',json.dumps(source_data))
    directory = tmp_path/'override'
    process = configured_run(directory,[override],['--pythonpath',str(tmp_path),
        '--parser','HookBank.SourceParser:velun'])
    root = configured_result(directory)
    library_outcomes(process,root,{'Generated':'PASS'})
    assert root.find('./suite').attrib['name'] == 'Parsed Content'
    assert keyword_calls(root.find('.//test'), 'Log')[0].find('msg').text == 'custom-source-payload'
    for mode in ('raise','invalid'):
        process = configured_run(tmp_path/mode,[source],['--pythonpath',str(tmp_path),
            '--parser','HookBank.SourceParser:spec:'+mode])
        configuration_error(process)


def test_custom_console_replaces_presentation_and_load_failure(tmp_path):
    extension_bank(tmp_path)
    source = write_file(tmp_path/'console.velun','*** Settings ***\nName    Console\n' + native_case('Console Live')+'Console Failed\n    Fail    deliberate failure\n')
    baseline = configured_run(tmp_path/'baseline',[source],['--console','verbose'])
    library_outcomes(baseline,configured_result(tmp_path/'baseline'),{'Console Live':'PASS','Console Failed':'FAIL'})
    assert b'Console Live' in baseline.stdout and b'Console Failed' in baseline.stdout
    directory = tmp_path/'custom'
    process = configured_run(directory,[source],['--pythonpath',str(tmp_path),
        '--console','HookBank.Console','--log','log.html','--report','report.html'])
    library_outcomes(process,configured_result(directory),{'Console Live':'PASS','Console Failed':'FAIL'})
    assert b'[ ERROR ]' not in process.stderr, process.stderr
    records = [json.loads(line) for line in process.stdout.splitlines()]
    assert Counter(map(tuple, records)) == Counter([('suite','Console'),
        ('test','Console Live','PASS'),('test','Console Failed','FAIL'),
        ('output',str(directory/'output.xml')),('log',str(directory/'log.html')),
        ('report',str(directory/'report.html')),('closed',)])
    configuration_error(configured_run(tmp_path/'invalid',[source],['--pythonpath',str(tmp_path),
        '--console','HookBank.NoSuchConsole']))
