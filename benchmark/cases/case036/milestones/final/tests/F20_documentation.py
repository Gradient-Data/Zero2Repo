# feature: F20
"""Acceptance checks for non-executing suite documentation."""
from velun.velunexplan import velunexplan as generate_test_document
from _helpers import call_public, run_module, temporary_workspace, index_by_identity
from F01_helpers import execute_source
from F20_helpers import documentation_sources, generate_overview, overview_page


def test_hierarchical_overview_without_execution():
    with temporary_workspace() as directory:
        root, extra, markers = documentation_sources(directory)
        for source in (root, extra):
            process, result = execute_source(source, directory)
            assert process.returncode == 0, (process.stdout, process.stderr)
            assert result.find('suite/status').attrib['status'] == 'PASS'
        for marker, text in markers.values():
            assert marker.read_text() == text
            marker.unlink()
        for mode in ('cli', 'api'):
            target = directory / (mode + '.html')
            if mode == 'cli':
                generate_overview([root, extra], target, '--name', 'Voyage Catalogue')
            else:
                call_public(generate_test_document, str(root), str(extra), str(target),
                            name='Voyage Catalogue')
            page = overview_page(directory, target)
            assert page['title'] == page['heading'] == 'Voyage Catalogue'
            top = page['suite']
            assert top['name'] == 'Voyage Catalogue'
            sources = index_by_identity(top['suites'], lambda item: item['name'])
            assert set(sources) == {'Fleet', 'Extra'}
            fleet = sources['Fleet']
            assert fleet['fields']['Documentation:'] == 'Fleet overview.'
            assert fleet['fields']['Owner:'] == 'Marine team'
            assert fleet['fields']['Region:'] == 'Coast'
            leaves = index_by_identity(fleet['suites'], lambda item: item['name'])
            assert set(leaves) == {'Alpha', 'Beta'}
            leaves['Extra'] = sources['Extra']
            for suite_name, name, tag in [('Alpha', 'Harbour Check', 'smoke'),
                                           ('Beta', 'Ocean Check', 'slow'),
                                           ('Extra', 'Island Check', 'smoke')]:
                leaf = leaves[suite_name]
                text = suite_name.lower()
                assert leaf['fields']['Documentation:'] == text + ' suite notes.'
                assert leaf['fields']['Area:'] == text
                assert [t['name'] for t in leaf['tests']] == [name]
                test = leaf['tests'][0]
                assert test['fields']['Documentation:'] == text + ' test notes.'
                assert set(test['fields']['Tags:'].split(', ')) == {tag, 'voyage'}
                assert test['calls'] == [
                    {'name': 'Record Body', 'args': f'{markers[name][0]}, {text}'},
                    {'name': 'No Operation', 'args': ''}]
            assert all(not marker.exists() for marker, _ in markers.values())


def test_selection_overrides_and_title():
    with temporary_workspace() as directory:
        root, extra, _ = documentation_sources(directory)
        baseline = directory / 'baseline.html'
        generate_overview([root], baseline)
        page = overview_page(directory, baseline)
        assert page['title'] == page['heading'] == page['suite']['name'] == 'Fleet'
        assert {s['tests'][0]['name'] for s in page['suite']['suites']} == {'Harbour Check', 'Ocean Check'}
        # Each selection has a surviving and a rejected member in the same source.
        for option, pattern, expected in [('--suite', 'Alpha', 'Harbour Check'),
                                          ('--test', 'Ocean Check', 'Ocean Check'),
                                          ('--include', 'smoke', 'Harbour Check'),
                                          ('--exclude', 'smoke', 'Ocean Check')]:
            target = directory / 'selected.html'
            generate_overview([root], target, option, pattern,
                              '--name', 'Selected Voyages', '--doc', 'Reviewed journeys.',
                              '--metadata', 'Owner:Review team', '--metadata', 'Stage:Ready',
                              '--settag', 'reviewed', '--title', 'Journey Manual')
            selected = overview_page(directory, target)
            assert selected['title'] == selected['heading'] == 'Journey Manual'
            top = selected['suite']
            assert top['name'] == 'Selected Voyages'
            assert top['fields']['Documentation:'] == 'Reviewed journeys.'
            assert top['fields']['Owner:'] == 'Review team'
            assert top['fields']['Stage:'] == 'Ready'
            assert top['fields']['Region:'] == 'Coast'
            tests = [t for suite in top['suites'] for t in suite['tests']]
            assert [t['name'] for t in tests] == [expected]
            original_tag = 'smoke' if expected == 'Harbour Check' else 'slow'
            assert set(tests[0]['fields']['Tags:'].split(', ')) == {original_tag, 'voyage', 'reviewed'}


def test_input_errors_and_imported_calls_without_execution():
    with temporary_workspace() as directory:
        root, extra, markers = documentation_sources(directory)
        process, result = execute_source(extra, directory)
        assert process.returncode == 0, (process.stdout, process.stderr)
        marker, text = markers['Island Check']
        assert marker.read_text() == text
        marker.unlink()
        target = directory / 'imported.html'
        generate_overview([extra], target)
        page = overview_page(directory, target)
        assert page['suite']['tests'][0]['name'] == 'Island Check'
        assert page['suite']['tests'][0]['calls'] == [
            {'name': 'Record Body', 'args': f'{marker}, extra'},
            {'name': 'No Operation', 'args': ''}]
        assert not marker.exists()
        for args in ([str(directory / 'absent.velun'), str(directory / 'bad.html')],
                     ['--not-a-velunexplan-option', str(extra), str(directory / 'bad.html')],
                     [str(extra)],
                     ['--include', 'unmatched', str(root), str(directory / 'bad.html')]):
            rejected = run_module('velun.velunexplan', args)
            assert rejected.returncode == 252, (args, rejected.stdout, rejected.stderr)
            assert rejected.stdout.strip(), (args, rejected.stderr)
