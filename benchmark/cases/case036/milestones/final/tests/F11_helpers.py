# feature: F11
"""CLI configuration observations with explicit XML and error carriers."""
from _helpers import run_module, read_xml, write_file
from F01_helpers import native_case
from F03_helpers import library_outcomes


def configured_run(directory, sources, options=(), defaults=None):
    directory.mkdir(parents=True, exist_ok=True)
    return run_module('velun', ['--outputdir', str(directory), '--log', 'NONE',
                      '--report', 'NONE', *map(str, options), *map(str, sources)],
                      env_overrides={'VELUN_OPTIONS': defaults})


def configured_result(directory):
    return read_xml(directory / 'output.xml').getroot()


def selected_cases(process, directory, expected):
    root = configured_result(directory)
    assert sorted(t.attrib['name'] for t in root.findall('.//test')) == sorted(expected)
    library_outcomes(process, root, {name:'PASS' for name in expected})
    return root


def configuration_error(process):
    assert process.returncode == 252, process
    assert b'[ ERROR ]' in process.stderr, process.stderr


def selection_tree(directory):
    write_file(directory / '__init__.velun', '*** Settings ***\nName    Catalog\n')
    for suite, cases in [('north_wing', [('Alpha One', 'red    ready'),
                ('Beta Two', 'blue    ready'), ('Gamma Three', 'red    blocked')]),
                ('south_wing', [('Delta Four', 'green'), ('Alpha One Extra', 'blue')])]:
        text = '*** Settings ***\nName    ' + suite.replace('_', ' ').title() + '\n*** Test Cases ***\n'
        for name, tags in cases:
            text += f'{name}\n    [Tags]    {tags}\n    No Operation\n'
        write_file(directory / (suite + '.velun'), text)
    return directory
