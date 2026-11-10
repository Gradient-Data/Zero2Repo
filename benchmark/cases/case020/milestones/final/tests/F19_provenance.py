# feature: F19
"""Dependency provenance acceptance through public recipe and CLI entries."""
from F01_helpers import cli_success, named_node
from F02_helpers import recipe_client, recipe_file
from F03_helpers import exported_reference
from F05_helpers import dependency_recipe
from F19_helpers import (sbom_consumer, sbom_documents, sbom_components, sbom_revision,
                         sbom_edges, comparison_inputs, comparison_report, difference_lines,
                         comparison_client)


def test_cyclonedx_identity_metadata_and_relationships(tmp_path):
    client = recipe_client(tmp_path)
    leaf = dependency_recipe(client, tmp_path / 'leaf', 'leaf', '2.4',
                            '    license = ("MIT", "Apache-2.0")\n'
                            '    description = "Numerical leaf library"\n', create=True)
    parent = dependency_recipe(client, tmp_path / 'parent', 'parent', '5.1',
                              '    requires = "leaf/2.4"\n'
                              '    license = "BSD-3-Clause"\n'
                              '    description = "Parent library"\n', create=True)
    variants = [('bill14.json', '1.4', {}), ('bill16.json', '1.6', {})]
    root = sbom_consumer(tmp_path / 'consumer', '    requires = "parent/5.1"\n', variants)
    _, documents = sbom_documents(client, root, variants)
    for filename, version, _ in variants:
        document = documents[filename]
        assert document['bomFormat'] == 'CycloneDX'
        assert document['specVersion'] == version
        components = sbom_components(document)
        assert set(components) == {'leaf', 'parent'}
        for name, reference, description, licenses in (
            ('leaf', leaf, 'Numerical leaf library', {'MIT', 'Apache-2.0'}),
            ('parent', parent, 'Parent library', {'BSD-3-Clause'}),
        ):
            row = components[name]
            assert row['version'] == reference.split('#')[0].split('/')[1]
            assert row['purl'] == 'pkg:velmora/' + name + '@' + row['version']
            assert sbom_revision(row) == reference.split('#')[1]
            assert row['description'] == description
            assert {item['license']['id'] for item in row['licenses']} == licenses
        assert sbom_edges(document) == {'$root': {'parent'}, 'parent': {'leaf'}, 'leaf': set()}


def test_build_and_test_dependency_selection(tmp_path):
    client = recipe_client(tmp_path)
    for name in ('regular', 'tool', 'testing'):
        dependency_recipe(client, tmp_path / name, name, create=True)
    selections = [('default', {}, {'regular'}),
                  ('build', {'add_build': True}, {'regular', 'tool'}),
                  ('test', {'add_tests': True}, {'regular', 'testing'}),
                  ('both', {'add_build': True, 'add_tests': True}, {'regular', 'tool', 'testing'})]
    variants = [(f'{label}{version}.json', version, options)
                for label, options, _ in selections for version in ('1.4', '1.6')]
    root = sbom_consumer(tmp_path / 'consumer',
                        '    requires = "regular/1.0"\n'
                        '    tool_requires = "tool/1.0"\n'
                        '    test_requires = "testing/1.0"\n', variants)
    _, documents = sbom_documents(client, root, variants)
    for label, _, expected in selections:
        for version in ('1.4', '1.6'):
            document = documents[f'{label}{version}.json']
            assert document['specVersion'] == version
            assert set(sbom_components(document)) == expected
            assert sbom_edges(document) == {
                '$root': expected, **{name: set() for name in expected}}


def test_unnecessary_binaries_and_component_augmentation(tmp_path):
    client = recipe_client(tmp_path)
    leaf = dependency_recipe(client, tmp_path / 'leaf', 'unusedbinary', create=True)
    dependency_recipe(client, tmp_path / 'tool', 'runner',
                      body='    package_type = "application"\n'
                           '    requires = "unusedbinary/1.0"\n', create=True)
    variants = [('bill14.json', '1.4', {'add_build': True}),
                ('bill16.json', '1.6', {'add_build': True}),
                ('unselected.json', '1.6', {})]
    root = sbom_consumer(tmp_path / 'consumer', '    tool_requires = "runner/1.0"\n', variants,
                        extra_info={'unusedbinary': {'description': 'Caller annotation',
                                                     'supplier': {'name': 'Research team'}}})
    report, documents = sbom_documents(client, root, variants)
    assert named_node(report, 'unusedbinary', 'build')['binary'] == 'Skip'
    for filename in ('bill14.json', 'bill16.json'):
        rows = sbom_components(documents[filename])
        assert set(rows) == {'runner', 'unusedbinary'}
        assert sbom_revision(rows['unusedbinary']) == leaf.split('#')[1]
        assert rows['unusedbinary']['description'] == 'Caller annotation'
        assert rows['unusedbinary']['supplier'] == {'name': 'Research team'}
        # Caller information reaches only the component it names.
        assert rows['runner'].get('description') != 'Caller annotation'
        assert rows['runner'].get('supplier') != {'name': 'Research team'}
        assert sbom_edges(documents[filename]) == {
            '$root': {'runner'}, 'runner': {'unusedbinary'}, 'unusedbinary': set()}
    # An unnecessary binary still follows its category's selection.
    assert not sbom_components(documents['unselected.json'])


def test_recipe_export_patch_and_acquired_source_differences(tmp_path):
    with comparison_client(tmp_path) as client:
        old = comparison_inputs(tmp_path / 'old', '1.0', 'copper', removed=True)
        new = comparison_inputs(tmp_path / 'new', '2.0', 'indigo')
        old_ref = exported_reference(client, old)
        new_ref = exported_reference(client, new)
        # A later revision of the same version: an exact revision is not the latest one.
        revised = comparison_inputs(tmp_path / 'revised', '2.0', 'ochre')
        revised_ref = exported_reference(client, revised)
        # Local locations hold recipes that differ from every exported revision.
        local_old = comparison_inputs(tmp_path / 'local-old', '1.0', 'amber', removed=True)
        local_new = comparison_inputs(tmp_path / 'local-new', '2.0', 'violet')
        for paths, first, second, references in (
            ((local_old, local_new), 'amber', 'violet', ('compare/1.0', 'compare/2.0')),
            (None, 'copper', 'indigo', (old_ref, new_ref)),
        ):
            report = comparison_report(client, *references, paths=paths)
            recipe = difference_lines(report, 'e/velmorafile.py')
            assert f"-    description = '{first}'" in recipe
            assert f"+    description = '{second}'" in recipe
            for path, before, after in (
                ('e/material.txt', first + ' exported', second + ' exported'),
                ('es/header.h', first + ' header', second + ' header'),
                ('es/patches/change.patch', '+' + first + ' patched', '+' + second + ' patched'),
                ('s/acquired.txt', first + ' source', second + ' source'),
                ('s/patched.txt', first + ' patched', second + ' patched'),
            ):
                lines = difference_lines(report, path)
                assert '-' + before in lines, (path, lines)
                assert '+' + after in lines, (path, lines)
            for category, extension, content in [('e', 'txt', 'export'), ('es', 'h', 'header'),
                                                  ('s', 'c', 'source')]:
                removed = difference_lines(report, category + '/retired.' + extension)
                added = difference_lines(report, category + '/introduced.' + extension)
                assert '+++ /dev/null' in removed
                assert '-' + first + ' unique ' + content in removed
                assert '--- /dev/null' in added
                assert '+' + second + ' unique ' + content in added
        report = comparison_report(client, new_ref, revised_ref)
        for path, before, after in (('e/material.txt', 'indigo exported', 'ochre exported'),
                                    ('s/acquired.txt', 'indigo source', 'ochre source')):
            lines = difference_lines(report, path)
            assert '-' + before in lines, (path, lines)
            assert '+' + after in lines, (path, lines)


def test_comparison_failure_is_not_an_empty_difference(tmp_path):
    with comparison_client(tmp_path) as client:
        valid = comparison_inputs(tmp_path / 'valid', '1.0', 'copper', removed=True)
        reference = exported_reference(client, valid)
        assert comparison_report(client, reference, reference) == {}
        comparison_report(client, reference, 'unavailable/4.0', rejected=True)
        comparison_report(client, 'unavailable/4.0', reference, rejected=True)
        comparison_report(client, reference, reference.split('#')[0] + '#' + '0' * 32, rejected=True)
        broken = recipe_file(tmp_path / 'broken',
                             '    def source(self):\n'
                             '        raise RuntimeError("source acquisition failed")\n',
                             name='compare', version='2.0').parent
        broken_ref = exported_reference(client, broken)
        comparison_report(client, reference, broken_ref, rejected=True)
        comparison_report(client, broken_ref, reference, rejected=True)
