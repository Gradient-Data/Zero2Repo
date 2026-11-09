# feature: F12
"""Acceptance coverage for saved-result post-processing."""
from lxml import html
from _helpers import keyword_calls, read_xml, read_json, write_file
from F05_helpers import lifecycle_cases
from F10_helpers import rendered_probe, statistic_counts
from F12_helpers import saved_run, postprocess, result_signature, DETAIL_CASES, DETAIL_KEYWORDS


def test_saved_formats_reports_and_modes(tmp_path):
    witness = tmp_path / 'body.txt'
    library = write_file(tmp_path / 'Witness.py', '''from pathlib import Path

def touch(path):
    with Path(path).open('a') as stream:
        stream.write('executed\\n')
''')
    inputs = []
    for suffix in ('xml', 'json'):
        from F10_helpers import artifact_run
        section = 'Test Cases' if suffix == 'xml' else 'Tasks'
        process = artifact_run(tmp_path / suffix,
            f'*** Settings ***\nLibrary    {library}\n*** {section} ***\nKept\n    Touch    {witness}\nRejected\n    Fail    recorded rejection\nOmitted\n    Skip    recorded omission\n',
            ['--output', f'output.{suffix}', '--log', 'NONE', '--report', 'NONE'])
        assert 1 <= process.returncode <= 250, process.stderr
        path = tmp_path / suffix / f'output.{suffix}'
        if suffix == 'json':
            assert read_json(path)['rpa'] is True
        inputs.append(path)
        before = witness.read_bytes()
        library.unlink()
        output = tmp_path / ('new-' + suffix)
        root = postprocess(output, [path], ['--log', 'log.html', '--report', 'report.html', '--xunit', 'summary.xml'], expected=1)
        assert root.attrib['rpa'] == ('false' if suffix == 'xml' else 'true')
        assert result_signature(root) == ({'Kept': 'PASS', 'Rejected': 'FAIL', 'Omitted': 'SKIP'}, (1, 1, 1))
        summary = read_xml(output / 'summary.xml').getroot()
        assert {t.attrib['name']: (t.find('failure') is not None, t.find('skipped') is not None)
                for t in summary.findall('.//testcase')} == {
                    'Kept': (False, False), 'Rejected': (True, False), 'Omitted': (False, True)}
        visible = rendered_probe(output, output / 'report.html', '''
const doc=frame.contentDocument;
doc.querySelector('a[href="#totals"]').click(); await pause();
return {rows:Array.from(doc.querySelectorAll('#test-details tbody tr')).map(row=>({name:resultTestName(row),status:row.querySelector('.details-col-status').textContent.trim()})),
link:doc.querySelector('a[href="log.html"]').getAttribute('href')};
''')
        assert {row['name']:row['status'] for row in visible['rows']} == {
            'Kept': 'PASS', 'Rejected': 'FAIL', 'Omitted': 'SKIP'}
        assert visible['link'] == 'log.html'
        log_names = rendered_probe(output, output / 'log.html', '''
return Array.from(frame.contentDocument.querySelectorAll('.test > .element-header > .name')).map(e=>e.textContent.trim());
''')
        assert set(log_names) == {'Kept', 'Rejected', 'Omitted'}
        assert witness.read_bytes() == before
        write_file(library, 'from pathlib import Path\ndef touch(path):\n    with Path(path).open("a") as stream:\n        stream.write("executed\\n")\n')
    postprocess(tmp_path / 'mixed', inputs, expected=252)
    overridden = postprocess(tmp_path / 'override', inputs, ['--rpa'], expected=2)
    assert overridden.attrib['rpa'] == 'true'
    assert len(overridden.findall('./suite/suite/test')) == 6
    bad = write_file(tmp_path / 'unreadable.xml', '<broken>')
    postprocess(tmp_path / 'bad', [bad], expected=252)


def test_combine_filter_overrides_and_statistics(tmp_path):
    cases = 'Keep\n    [Tags]    red\n    No Operation\nDrop\n    [Tags]    blue\n    Fail    rejected\n'
    second_cases = cases.replace('    No Operation', '    Fail    second rejection').replace('    Fail    rejected', '    No Operation')
    inputs = [saved_run(tmp_path / str(i), text, settings='Metadata    Owner    original', options=['--name', 'Same'])
              for i, text in enumerate((cases, second_cases))]
    original = [p.read_bytes() for p in inputs]
    root = postprocess(tmp_path / 'combined', inputs, expected=2)
    children = root.findall('./suite/suite')
    assert [s.attrib['name'] for s in children] == ['Same', 'Same']
    assert [[t.attrib['name'] for t in s.findall('test')] for s in children] == [['Keep', 'Drop']] * 2
    assert [[t.find('status').attrib['status'] for t in child.findall('test')] for child in children] == [
        ['PASS', 'FAIL'], ['FAIL', 'PASS']]
    assert statistic_counts(root.find('./statistics/total/stat')) == (2, 2, 0)
    # Distinct names make input order observable independently of identical executions.
    other = saved_run(tmp_path / 'other', 'Other\n    No Operation\n', options=['--name', 'Other suite'])
    ordered = postprocess(tmp_path / 'order', [other, inputs[0]], expected=1)
    assert [s.attrib['name'] for s in ordered.findall('./suite/suite')] == ['Other suite', 'Same']
    filtered = postprocess(tmp_path / 'filtered', [other, inputs[0]],
        ['--suite', 'Same', '--test', 'K*', '--include', 'red', '--name', 'Chosen',
         '--doc', 'new documentation', '--metadata', 'Owner:replacement', '--tagstatinclude', 'red'])
    assert result_signature(filtered) == ({'Keep': 'PASS'}, (1, 0, 0))
    assert filtered.find('./suite').attrib['name'] == 'Chosen'
    assert filtered.find('./suite/doc').text == 'new documentation'
    assert filtered.find("./suite/meta[@name='Owner']").text == 'replacement'
    assert [s.text for s in filtered.findall('./statistics/tag/stat')] == ['red']
    for label, options, names, counts in [
        ('suite', ['--suite', 'Other suite'], {'Other': 'PASS'}, (1, 0, 0)),
        ('test', ['--test', 'Drop'], {'Drop': 'FAIL'}, (0, 1, 0)),
        ('tag', ['--include', 'blue'], {'Drop': 'FAIL'}, (0, 1, 0))]:
        selected = postprocess(tmp_path / label, [other, inputs[0]], options, expected=counts[1])
        assert result_signature(selected) == (names, counts)
    stats = postprocess(tmp_path / 'stats', [inputs[0]], ['--tagstatinclude', 'red'], expected=1)
    assert [s.text for s in stats.findall('./statistics/tag/stat')] == ['red']
    assert [p.read_bytes() for p in inputs] == original


def test_merge_replacement_skip_additions_and_root_refusal(tmp_path):
    first = saved_run(tmp_path / 'first', 'Changed\n    Fail    prior reason\nPreserved\n    Fail    preserved reason\nRegressed\n    No Operation\n', options=['--name', 'Root'])
    later = saved_run(tmp_path / 'later', 'Changed\n    No Operation\nPreserved\n    Skip    later omission\nAdded\n    No Operation\nRegressed\n    Fail    later regression\n', options=['--name', 'Root'])
    root = postprocess(tmp_path / 'merged', [first, later], ['--merge'], expected=2)
    # A later non-skipped result replaces the earlier one in both directions (FAIL->PASS, PASS->FAIL).
    assert result_signature(root) == ({'Changed': 'PASS', 'Preserved': 'FAIL', 'Added': 'PASS', 'Regressed': 'FAIL'}, (2, 2, 0))
    cases = lifecycle_cases(root)
    message = html.fragment_fromstring(cases['Changed'].find('status').text.removeprefix('*HTML*'), create_parent=True)
    label = message.xpath('.//*[@class="old-status"]')
    assert len(label) == 1
    assert label[0].getnext().text_content() == 'FAIL'
    assert 'prior reason' in message.text_content()
    assert 'preserved reason' in cases['Preserved'].find('status').text
    # New child suites are also carried into a merge.
    child_dir = tmp_path / 'tree'
    write_file(child_dir / 'child.velun', '*** Settings ***\nName    Child\n*** Test Cases ***\nChild test\n    No Operation\n')
    from F01_helpers import execute_source
    process, _ = execute_source(child_dir, tmp_path / 'child-output', '--name', 'Root')
    assert process.returncode == 0, process.stderr
    extended = postprocess(tmp_path / 'extended', [first, tmp_path / 'child-output/result.xml'], ['--merge'], expected=2)
    assert extended.find("./suite/suite[@name='Child']/test[@name='Child test']") is not None
    wrong = saved_run(tmp_path / 'wrong', 'Valid\n    No Operation\n', options=['--name', 'Different'])
    postprocess(tmp_path / 'refused', [first, wrong], ['--merge'], expected=252)


def test_merge_last_suite_information_and_recomputed_totals(tmp_path):
    inputs = []
    for i, action in enumerate(('Fail    obsolete failure', 'Skip    omitted rerun', 'No Operation')):
        settings = (f'Documentation    documentation-{i}\nSuite Setup    Log    setup-{i}\n'
                    f'Suite Teardown    Log    teardown-{i}\nMetadata    Shared    value-{i}\nMetadata    Unique{i}    retained-{i}')
        inputs.append(saved_run(tmp_path / str(i), f'Repeated\n    {action}\n', settings=settings, options=['--name', 'Root']))
    root = postprocess(tmp_path / 'merged', inputs, ['--merge'])
    assert result_signature(root) == ({'Repeated': 'PASS'}, (1, 0, 0))
    suite = root.find('suite')
    assert suite.find('status').attrib['status'] == 'PASS'
    assert suite.find('doc').text == 'documentation-2'
    assert {m.attrib['name']: m.text for m in suite.findall('meta')} == {
        'Shared': 'value-2', **{f'Unique{i}': f'retained-{i}' for i in range(3)}}
    assert suite.find("kw[@type='SETUP']/arg").text == 'setup-2'
    assert suite.find("kw[@type='TEARDOWN']/arg").text == 'teardown-2'


def test_keyword_detail_removal_selections(tmp_path):
    source = saved_run(tmp_path / 'input', DETAIL_CASES, keywords=DETAIL_KEYWORDS)
    baseline = read_xml(source).getroot()
    base_cases = lifecycle_cases(baseline)
    assert base_cases['Clean'].find('.//kw/kw/msg').text == 'selected-payload'
    assert len(base_cases['Loops'].findall('for/iter')) == 3
    assert len(base_cases['Retry'].findall('kw/kw')) == 4
    for selection in ('all', 'passed', 'for', 'while', 'wuks', 'name:Sel*ted', 'tag:reduce'):
        root = postprocess(tmp_path / selection.replace(':', '-'), [source], ['--removekeywords', selection], expected=1)
        assert result_signature(root) == result_signature(baseline)
        cases = lifecycle_cases(root)
        if selection == 'all':
            assert not root.findall('./suite/test//msg')
            assert not root.findall('./suite/test/*//kw')
            assert not root.findall('./suite/test/*//iter')
            continue
        # Warnings survive every selection except 'all', including inside removable
        # loop iterations and earlier retry attempts.
        assert sorted(m.text for m in root.findall("./suite/test//msg[@level='WARN']")) == [
            'loop-warning', 'retry-warning', 'warning-payload']
        if selection in ('passed', 'name:Sel*ted', 'tag:reduce'):
            assert keyword_calls(cases['Clean'], 'Selected')[0].find('kw') is None
            assert cases['Broken'].find('.//msg').text == 'final failure'
            if selection != 'passed':
                assert keyword_calls(cases['Clean'], 'Untouched')[0].find('kw') is not None
        elif selection in ('for', 'while'):
            loop = cases['Loops'].find(selection)
            assert len(loop.findall('iter')) < len(base_cases['Loops'].findall(selection + '/iter'))
            other = 'while' if selection == 'for' else 'for'
            assert len(cases['Loops'].findall(other + '/iter')) == len(base_cases['Loops'].findall(other + '/iter'))
        else:
            attempts = cases['Retry'].findall('kw/kw')
            assert 0 < len(attempts) < 4
            assert attempts[-1].find('status').attrib['status'] == 'PASS'
            assert keyword_calls(cases['Clean'], 'Selected')[0].find('kw') is not None


def test_flatten_loops_iterations_and_selected_keywords(tmp_path):
    source = saved_run(tmp_path / 'input', DETAIL_CASES, keywords=DETAIL_KEYWORDS)
    baseline = read_xml(source).getroot()
    for selection, path in [('for', './suite/test/for'), ('while', './suite/test/while'),
                            ('iteration', './suite/test/for/iter'), ('name:Selected', None),
                            ('tag:reduce', None)]:
        before = baseline.findall(path) if path is not None else keyword_calls(baseline, 'Selected', recursive=True)
        assert before and all(n.find('kw') is not None or n.find('iter') is not None for n in before)
        root = postprocess(tmp_path / selection.replace(':', '-'), [source], ['--flattenkeywords', selection], expected=1)
        assert result_signature(root) == result_signature(baseline)
        after = root.findall(path) if path is not None else keyword_calls(root, 'Selected', recursive=True)
        if selection == 'iteration':
            before += baseline.findall('./suite/test/while/iter')
            after += root.findall('./suite/test/while/iter')
        assert len(after) == len(before)
        for old, new in zip(before, after):
            messages = [(m.attrib['level'], m.text) for m in old.findall('.//msg')]
            assert messages
            assert [(m.attrib['level'], m.text) for m in new.findall('msg')] == messages
            assert not new.findall('kw') and not new.findall('iter') and not new.findall('if')
        assert keyword_calls(root, 'Untouched', recursive=True)[0].find('kw') is not None
