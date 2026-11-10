# feature: F02
"""Acceptance evidence for variables through native suite execution."""
import os
import tempfile
from pathlib import Path
from _helpers import environment, write_file
from F01_helpers import execute_source
from F02_helpers import (WITNESS, variable_run, document, rejection_cases,
                         rejected_names, variable_tree_run)


def test_scalar_interpolation_and_expansion(tmp_path):
    bad = ['Arguments    @{text}', 'Arguments    &{items}']
    variable_run(tmp_path, document('''    ${alias}=    Give    ${items}
    Same    ${alias}    ${items}
    Check    ${items}    ['red', 'blue']
    Check    ${mapping}    {'left': 'L', 'right': 'R'}
    Check    before:${text}:after    'before:hello:after'
    Check    list=${items}    "list=['red', 'blue']"
    ${bound}=    Arguments    prefix    @{items}    &{mapping}
    Check    ${bound}    [['prefix', 'red', 'blue'], {'left': 'L', 'right': 'R'}]
''', variables='''${text}    hello
@{items}    red    blue
&{mapping}    left=L    right=R
''', extra_tests=rejection_cases(bad)), failures=rejected_names(bad))


def test_variable_sources_and_environment(tmp_path):
    write_file(tmp_path / 'dynamic.py', "def get_variables(prefix, suffix):\n    return {'dynamic': prefix + '/' + suffix}\n")
    write_file(tmp_path / 'data.yaml', 'yaml_value:\n  - apple\n  - pear\n')
    write_file(tmp_path / 'data.json', '{"json_value": {"count": 7}}')
    with environment({'F02_PRESENT': 'from environment', 'F02_ABSENT': None}):
        variable_run(tmp_path, document('''    Check    ${data}    'declared'
    Check    ${execution}    'cli'
    Check    ${dynamic}    'north/south'
    Check    ${yaml_value}    ['apple', 'pear']
    Check    ${json_value}    {'count': 7}
    Check    %{F02_PRESENT}    'from environment'
    Check    %{F02_ABSENT=replacement}    'replacement'
    Check    %{F02_PRESENT=unused}    'from environment'
''', variables='${data}    declared\n', settings='''Variables    dynamic.py    north    south
Variables    data.yaml
Variables    data.json
''', extra_tests='Missing Environment\n    Give    %{F02_ABSENT}\n'),
            options=['--variable', 'execution:cli'], failures=['Missing Environment'])


def test_invalid_providers_and_unresolved_values(tmp_path):
    write_file(tmp_path / 'good.json', '{"known": "live"}')
    write_file(tmp_path / 'broken.json', '{not valid JSON')
    for index, provider in enumerate(('good.json', 'absent.json', 'broken.json')):
        directory = tmp_path / str(index)
        bad = [] if index == 0 else ['Check    ${known}    \'live\'']
        text = document('    Check    ${1}    1\n' + ('    Check    ${known}    \'live\'\n' if not bad else ''),
                        settings=f'Variables    {tmp_path / provider}\n',
                        extra_tests=rejection_cases(bad + ['Give    ${unresolved_f02}']))
        _, root = variable_run(directory, text, failures=rejected_names(bad + ['Give    ${unresolved_f02}']),
                               checks=2 if index == 0 else 1)
        errors = root.findall('./errors/msg[@level="ERROR"]')
        if index:
            assert errors and any(provider in (m.text or '') for m in errors)
        else:
            assert errors == []


def test_normalized_names_and_precedence(tmp_path):
    write_file(tmp_path / 'first.py', "priority='first file'\nfile_only='first file'\n")
    write_file(tmp_path / 'second.py', "priority='second file'\nfile_only='second file'\n")
    write_file(tmp_path / 'inner.resource', '*** Variables ***\n${resource_own}    imported\n${from_resource}    imported\n')
    write_file(tmp_path / 'outer.resource', '*** Settings ***\nResource    inner.resource\n*** Variables ***\n${resource_own}    own declaration\n${priority}    resource\n')
    write_file(tmp_path / 'execution.py', "priority='execution file'\n")
    write_file(tmp_path / 'later.py', "priority='later execution file'\n")
    base = document('''    Check    ${MiXeD n a m e}    'normalized'
    Check    ${priority}    ${expected}
    Check    ${file_only}    'first file'
    Check    ${resource_own}    'own declaration'
    Check    ${from_resource}    'imported'
''', settings='''Resource    outer.resource
Variables    first.py
Variables    second.py
''', variables='${mixed_name}    normalized\n${priority}    suite\n')
    for index, (options, expected) in enumerate([
        ([], 'suite'),
        (['--variablefile', str(tmp_path / 'execution.py')], 'execution file'),
        (['--variablefile', str(tmp_path / 'execution.py'), '--variablefile', str(tmp_path / 'later.py')], 'execution file'),
        (['--variablefile', str(tmp_path / 'execution.py'), '--variable', 'priority:early', '--variable', 'PRIOR_ITY:late'], 'late')]):
        # Keep import locations explicit when rebuilding each independent arm.
        text = base.replace('outer.resource', str(tmp_path / 'outer.resource')).replace('first.py', str(tmp_path / 'first.py')).replace('second.py', str(tmp_path / 'second.py'))
        variable_run(tmp_path / str(index), text, options=[*options, '--variable', f'expected:{expected!r}'])


def test_local_test_suite_global_scopes(tmp_path):
    text = document('''    VAR    ${shared}    old    scope=TEST
    Local Setter
    Check    ${shared}    'old'
    Test Reader
    Suite Setter
    Check    ${shared}    'suite replacement'
    VAR    ${world}    test value    scope=TEST
    Global Setter
    Check    ${world}    'across suites'
''', keywords='''Global Setter
    VAR    ${world}    across suites    scope=GLOBAL
Local Setter
    ${shared}=    Give    local
    Check    ${shared}    'local'
Test Reader
    Check    ${shared}    'old'
Suite Setter
    VAR    ${shared}    suite replacement    scope=SUITE
''', extra_tests='''Next
    Check    ${shared}    'suite replacement'
    Check    ${world}    'across suites'
    Give    ${local_only}
''')
    # A local return target in a keyword must not survive that call.
    text = text.replace("    Check    ${shared}    'local'", "    Check    ${shared}    'local'\n    ${local_only}=    Give    confined")
    variable_run(tmp_path / 'single', text, failures=['Next'])
    task_text = text.replace('*** Test Cases ***', '*** Tasks ***').replace('scope=TEST', 'scope=TASK')
    variable_run(tmp_path / 'tasks', task_text, failures=['Next'])
    tree = tmp_path / 'tree'
    write_file(tree / '__init__.velun', '''*** Settings ***
Suite Setup    Initialize
*** Keywords ***
Initialize
    Set Suite Variable    $private    root only
    Set Suite Variable    $inherited    child value    children=True
    Set Global Variable    $global_value    everywhere
''')
    write_file(tree / 'a.velun', '''*** Settings ***
Library    Witness.py
*** Test Cases ***
First
    Check    ${inherited}    'child value'
    Check    ${global_value}    'everywhere'
    Set Suite Variable    $private_child    child only
No Parent Inheritance
    Give    ${private}
''')
    write_file(tree / 'b.velun', '''*** Settings ***
Library    Witness.py
*** Test Cases ***
Sibling
    Check    ${inherited}    'child value'
    Check    ${global_value}    'everywhere'
No Sibling Inheritance
    Give    ${private_child}
''')
    variable_tree_run(tree, tmp_path, passed=['First', 'Sibling'],
                      failures=['No Parent Inheritance', 'No Sibling Inheritance'], checks=4)


def test_suite_fixture_test_scope_isolation(tmp_path):
    variable_run(tmp_path, document('''    Give    ${fixture_value}
''', settings='Suite Setup    Open Suite\nSuite Teardown    Close Suite\n',
        keywords='''Open Suite
    Set Test Variable    $fixture_value    setup value
    Check    ${fixture_value}    'setup value'
Close Suite
    Check    ${fixture_value}    'setup value'
    Set Test Variable    $cleanup_value    cleanup only
    Check    ${cleanup_value}    'cleanup only'
''', extra_tests='''Independent
    Give    ${cleanup_value}
'''), failures=['Working', 'Independent'])

    tree = tmp_path / 'tree'
    write_file(tree / '__init__.velun', """*** Settings ***
Library    Witness.py
Suite Setup    Open Suite
Suite Teardown    Close Suite
*** Keywords ***
Open Suite
    Set Test Variable    $fixture_value    parent setup
    Check    ${fixture_value}    'parent setup'
Close Suite
    Check    ${fixture_value}    'parent setup'
    Set Test Variable    $cleanup_value    parent cleanup
    Check    ${cleanup_value}    'parent cleanup'
""")
    write_file(tree / 'child.velun', """*** Settings ***
Library    Witness.py
*** Test Cases ***
Live Child
    Check    ${1}    1
Parent Setup Is Isolated
    Give    ${fixture_value}
Parent Cleanup Is Isolated
    Give    ${cleanup_value}
""")
    variable_tree_run(tree, tmp_path, passed=['Live Child'],
                      failures=['Parent Setup Is Isolated', 'Parent Cleanup Is Isolated'], checks=4)


def test_nested_extended_and_indexed_access(tmp_path):
    bad = ['Give    ${value_${missing_inner}}', 'Give    ${obj.missing}',
           'Give    ${items}[20]', 'Give    ${items}[invalid]', 'Give    ${obj.value +}']
    variable_run(tmp_path, document('''    ${obj}=    Evaluate    types.SimpleNamespace(value=6)    modules=types
    VAR    ${obj.value}    full name
    Check    ${obj.value}    'full name'
    Check    ${obj.value * 3}    18
    Check    ${value_${selector}}    'nested value'
    Check    ${items}[1]    'b'
    Check    ${items}[::-1]    ['c', 'b', 'a']
    Check    ${mapping}[key][1]    5
''', variables='''${selector}    picked
${value_picked}    nested value
${value_}    empty inner
@{items}    a    b    c
${mapping}    ${{{'key': [4, 5]}}}
${obj}    ${{type('Item', (), {'value': 6})()}}
''', extra_tests=rejection_cases(bad)), failures=rejected_names(bad))


def test_return_assignment_and_unpacking(tmp_path):
    bad = ['${a}    ${b}=    Give    ${items}', '${a}    ${b}=    Give    scalar',
           '${a}    ${b}    ${c}    ${d}=    Give    ${items}']
    variable_run(tmp_path, document('''    ${whole}=    Give    ${items}
    Same    ${whole}    ${items}
    ${a}    ${b}    ${c}=    Give    ${items}
    Check    ${a}    'a'
    Check    ${b}    'b'
    Check    ${c}    'c'
    ${head}    @{middle}    ${tail}=    Give    ${items}
    Check    ${head}    'a'
    Check    ${middle}    ['b']
    Check    ${tail}    'c'
''', variables='@{items}    a    b    c\n', extra_tests=rejection_cases(bad)), failures=rejected_names(bad))


def test_automatic_context_values(tmp_path):
    resource = tmp_path / 'nested' / 'context.resource'
    write_file(resource, '*** Variables ***\n${resource_dir}    ${CURDIR}\n')
    text = document('''    [Documentation]    Test documentation
    [Tags]    alpha    beta
    Check    ${CURDIR}    SOURCE
    Check    ${resource_dir}    RESOURCE
    Check    ${EXECDIR}    EXECUTION
    Check    ${TEMPDIR}    TEMPORARY
    Check    ${/}    '/'
    Check    ${:}    ':'
    Check    ${\\n}    chr(10)
    Check    ${EMPTY}    ''
    ${empty_args}=    Arguments    @{EMPTY}    &{EMPTY}
    Check    ${empty_args}    [[], {}]
    Check    ${SPACE}    ' '
    Check    ${True}    True
    Check    ${False}    False
    Check    ${None}    None
    Check    ${42}    42
    Check    ${TEST NAME}    'Working'
    Check    ${TEST DOCUMENTATION}    'Test documentation'
    Check Members    ${TEST TAGS}    ['alpha', 'beta']
    Check    ${SUITE NAME}    'Context'
    Check    ${SUITE DOCUMENTATION}    'Suite documentation'
    Check    ${SUITE METADATA}    {'Owner': 'QA'}
    Check    ${OUTPUT DIR}    OUTPUTDIR
    Check    ${OUTPUT FILE}    OUTPUTFILE
    VAR    ${TEST NAME}    overridden
    Check    ${TEST NAME}    'overridden'
''', settings=f'''Documentation    Suite documentation
Metadata    Owner    QA
Resource    {resource}
Test Teardown    Test Outcome
Suite Teardown    Suite Outcome
''', variables='${TEST NAME}    static must lose\n', keywords='''Test Outcome
    Check    ${TEST STATUS}    'PASS'
    Check    ${TEST MESSAGE}    ''
Failure Outcome
    Check    ${TEST STATUS}    'FAIL'
    Check    ${TEST MESSAGE}    'deliberate failure'
Suite Outcome
    Check    ${SUITE STATUS}    'FAIL'
    Text Value    ${SUITE MESSAGE}
''', extra_tests='''Previous
    Check    ${PREV TEST NAME}    'Working'
    Check    ${PREV TEST STATUS}    'PASS'
    Check    ${PREV TEST MESSAGE}    ''
    Fail    deliberate failure
    [Teardown]    Failure Outcome
After Failure
    Check    ${PREV TEST NAME}    'Previous'
    Check    ${PREV TEST STATUS}    'FAIL'
    Check    ${PREV TEST MESSAGE}    'deliberate failure'
''')
    replacements = {'SOURCE': str(tmp_path), 'RESOURCE': str(resource.parent),
                    'EXECUTION': os.getcwd(), 'TEMPORARY': tempfile.gettempdir(),
                    'OUTPUTDIR': os.getcwd(), 'OUTPUTFILE': str(tmp_path / 'result.xml')}
    for key, value in replacements.items():
        text = text.replace('    ' + key + '\n', '    ' + repr(value) + '\n')
    variable_run(tmp_path, text, checks=37, passed=('Working', 'After Failure'),
                 failures=['Previous'], options=['--name', 'Context'])


def test_supported_variable_type_families(tmp_path):
    specs = [('int', '19', '19'), ('float', '2.75', '2.75'),
             ('Decimal', '2.50', "Decimal('2.50')"), ('bool', 'yes', 'True'),
             ('str', '${23}', "'23'"), ('bytes', 'abc', "b'abc'"),
             ('bytearray', 'ab', "bytearray(b'ab')"),
             ('list[int]', "['1', 2]", '[1, 2]'),
             ('tuple[int, str]', "['3', 4]", "(3, '4')"),
             ('set[int]', "['1', 2]", '{1, 2}'),
             ('frozenset[int]', "['1', 2]", 'frozenset({1, 2})'),
             ('dict[int, list[float]]', "{'2': ['1.5']}", '{2: [1.5]}'),
             ('date', '2025-06-07', 'date(2025, 6, 7)'),
             ('datetime', '2025-06-07 08:09:10', 'datetime(2025, 6, 7, 8, 9, 10)'),
             ('timedelta', '2 minutes', 'timedelta(seconds=120)'),
             ('Path', '/var/data/example', "Path('/var/data/example')"),
             ('None', 'none', 'None')]
    body = ''.join(f'    VAR    ${{v: {kind}}}    {value}\n    Check    ${{v}}    {expected}\n' for kind, value, expected in specs)
    body += '''    Check    ${declared_int}    31
    Check    ${declared_nested}    {2: [3, 4]}
    ${obj}=    Evaluate    object()
    VAR    ${retained: object}    ${obj}
    Same    ${retained}    ${obj}
    VAR    ${retained: Any}    ${obj}
    Same    ${retained}    ${obj}
'''
    bad = ['VAR    ${v: int}    not numeric', 'VAR    ${v: Enum}    one',
           'VAR    ${v: TypedDict}    {}', 'VAR    ${v: Custom}    custom']
    variable_run(tmp_path, document(body, variables="${declared_int: int}    31\n${declared_nested: dict[int, list[int]]}    {'2': ['3', 4]}\n", extra_tests=rejection_cases(bad)), failures=rejected_names(bad))


def test_union_precedence_for_variables_and_arguments(tmp_path):
    body = ''
    for kind, source, expected in [
        ('int | float', '${2.5}', '2.5'), ('float | int', '${2}', '2'),
        ('int | float', '4', '4'), ('float | int', '4', '4.0'),
        ('int | Any', '4', "'4'"), ('Any | int', '4', "'4'"),
        ('int | object', '4', '4'), ('int | object', 'abc', "'abc'"),
        ('object | int', '4', "'4'"),
        ('list[int] | list[str]', "${{['1', '2']}}", "['1', '2']"),
        ('list[int] | list[str]', "['1', '2']", '[1, 2]')]:
        body += f'    VAR    ${{v: {kind}}}    {source}\n    Check    ${{v}}    {expected}\n'
    for keyword, source, expected in [('Number', '${2.5}', '2.5'), ('Reverse Number', '${2}', '2'),
        ('Number', '4', '4'), ('Reverse Number', '4', '4.0'),
        ('Unrestricted', '4', "'4'"), ('Unrestricted First', '4', "'4'"),
        ('General', '4', '4'), ('General', 'abc', "'abc'"), ('General First', '4', "'4'"),
        ('Collection Union', "${{['1', '2']}}", "['1', '2']")]:
        body += f'    ${{v}}=    {keyword}    {source}\n    Check    ${{v}}    {expected}\n'
    body += '''    ${original}=    Evaluate    [1, 2]
    VAR    ${retained: list[int] | list[str]}    ${original}
    Same    ${retained}    ${original}
    ${retained}=    Collection Union    ${original}
    Same    ${retained}    ${original}
'''
    bad = ['VAR    ${v: int | float}    invalid', 'Number    invalid']
    variable_run(tmp_path, document(body, extra_tests=rejection_cases(bad)), failures=rejected_names(bad))


def test_secret_delivery_concealment_and_extraction(tmp_path):
    private = 'private-value-8361'
    with environment({'F02_PRIVATE': private}):
        text = document('''    VAR    ${secret: Secret}    %{F02_PRIVATE}
    Accept Secret    ${secret}
    VAR    ${copy: Secret}    ${secret}
    Accept Secret    ${copy}
    Log    wrapped:${secret}
''', extra_tests='''Bare Literal
    VAR    ${bad: Secret}    literal-secret
''')
        process, root = variable_run(tmp_path / 'hidden', text, options=['--loglevel', 'TRACE'], failures=['Bare Literal'])
        assert private not in (tmp_path / 'hidden' / 'result.xml').read_text()
        assert private.encode() not in process.stdout + process.stderr
        process, root = variable_run(tmp_path / 'extracted', document('''    VAR    ${secret: Secret}    %{F02_PRIVATE}
    ${plain}=    Give    ${secret.value}
    Check    ${plain}    EXPECTED
    Log    ${plain}
'''.replace('EXPECTED', repr(private))))
        assert private in [m.text for m in root.findall('.//msg')]


def test_numeric_conversion_rules(tmp_path):
    specs = [('int', '+1_024', '1024'), ('int', '-0b101', '-5'),
             ('int', '0o17', '15'), ('int', '0x2A', '42'),
             ('int', '12.0', '12'), ('int', '2e3', '2000'),
             ('int', '1 000', '1000'), ('int', '${4.0}', '4'),
             ('Decimal', '1 234.5', "Decimal('1234.5')"),
             ('float', '-1_234.5e-1', '-123.45'), ('float', '1 234.5', '1234.5'),
             ('float', '${17}', '17.0'), ('Decimal', '${17}', "Decimal('17')"),
             ('Decimal', '1_234.50', "Decimal('1234.50')"),
             ('Decimal', '${1.5}', "Decimal('1.5')")]
    body = ''.join(f'    VAR    ${{v: {k}}}    {v}\n    Check    ${{v}}    {e}\n' for k, v, e in specs)
    body += '''    ${v}=    Number    1_024
    Check    ${v}    1024
    ${v}=    Number    -2.75e1
    Check    ${v}    -27.5
'''
    bad = ['VAR    ${v: int}    1.25', 'VAR    ${v: int}    ${1.25}']
    variable_run(tmp_path, document(body, extra_tests=rejection_cases(bad)), failures=rejected_names(bad))


def test_boolean_text_bytes_and_absence(tmp_path):
    specs = [('bool', word, expected) for word, expected in [
        ('TrUe', 'True'), ('YeS', 'True'), ('oN', 'True'), ('1', 'True'),
        ('FaLsE', 'False'), ('nO', 'False'), ('OfF', 'False'), ('0', 'False'),
        ('${EMPTY}', 'False'), ('NoNe', 'None'), ('other', "'other'"),
        ('${2}', '2'), ('${None}', 'None'), ('真', 'True'), ('假', 'False')]]
    specs += [('str', '${{bytes([65, 255])}}', "'Aÿ'"),
              ('bytes', 'Aÿ', "bytes([65, 255])"),
              ('bytes', '${{[0, 65, 255]}}', 'bytes([0, 65, 255])'),
              ('bytearray', '${{[0, 255]}}', 'bytearray([0, 255])'),
              ('None', '${EMPTY}', 'None'), ('None', 'NoNe', 'None')]
    body = ''.join(f'    VAR    ${{v: {k}}}    {v}\n    Check    ${{v}}    {e}\n' for k, v, e in specs)
    bad = ['VAR    ${v: bytes}    €', 'VAR    ${v: bytes}    ${{[256]}}',
           'VAR    ${v: bytes}    ${{[-1]}}', 'VAR    ${v: None}    something',
           'VAR    ${s: Secret}    %{F02_PRIVATE}\n    Accept Secret    ${s}\n    VAR    ${v: str}    ${s}']
    with environment({'F02_PRIVATE': 'conversion-secret'}):
        variable_run(tmp_path, document(body, extra_tests=rejection_cases(bad)),
                     options=['--language', 'zh-CN'], failures=rejected_names(bad))


def test_collection_literals_and_member_conversion(tmp_path):
    specs = [('list[int]', "('2', '3')", '[2, 3]'),
             ('tuple[int, str]', "['2', 3]", "(2, '3')"),
             ('tuple[int, ...]', "['2', '3', '4']", '(2, 3, 4)'),
             ('set[int]', "['2', '2', 3]", '{2, 3}'),
             ('frozenset[int]', "{'2', '3'}", 'frozenset({2, 3})'),
             ('dict[int, float]', "{'2': '3.5'}", '{2: 3.5}'),
             ('list[int]', "${{('4', '5')}}", '[4, 5]')]
    body = ''.join(f'    VAR    ${{v: {k}}}    {v}\n    Check    ${{v}}    {e}\n' for k, v, e in specs)
    bad = ['VAR    ${v: list}    [x for x in range(3)]',
           'VAR    ${v: list}    list((1, 2))',
           'VAR    ${v: tuple[int, int]}    [1]',
           'VAR    ${v: tuple[int, int]}    [1, 2, 3]',
           'VAR    ${v: dict[int, int]}    {"bad": 2}']
    variable_run(tmp_path, document(body, extra_tests=rejection_cases(bad)), failures=rejected_names(bad))


def test_path_calendar_and_duration_declarations(tmp_path):
    bad = ['VAR    ${v: date}    2025-06-07 01:00:00',
           'VAR    ${v: date}    ${{datetime.datetime(2025,6,7,10).timestamp()}}',
           'VAR    ${v: datetime}    not-a-date', 'VAR    ${v: timedelta}    not-a-duration']
    variable_run(tmp_path, document('''    VAR    ${v: Path}    folder/file.txt
    Check    ${v}    Path('folder/file.txt')
    ${path}=    Evaluate    pathlib.Path('another/file')    modules=pathlib
    VAR    ${v: Path}    ${path}
    Check    ${v}    Path('another/file')
    VAR    ${v: date}    2025-06-07 00:00:00
    Check    ${v}    date(2025, 6, 7)
    ${before}=    Calendar Boundary
    VAR    ${v: date}    ToDaY
    Date Is Current    ${v}    ${before}
    ${before}=    Calendar Boundary
    VAR    ${v: date}    NoW
    Date Is Current    ${v}    ${before}
    VAR    ${v: datetime}    2025-06-07 08:09:10.125
    Check    ${v}    datetime(2025, 6, 7, 8, 9, 10, 125000)
    VAR    ${v: timedelta}    1 minute 2 seconds
    Check    ${v}    timedelta(seconds=62)
    VAR    ${v: timedelta}    01:02:03
    Check    ${v}    timedelta(seconds=3723)
    VAR    ${v: timedelta}    ${1.5}
    Check    ${v}    timedelta(seconds=1.5)
''', extra_tests=rejection_cases(bad)), failures=rejected_names(bad))


def test_numeric_references_and_optional_lookup(tmp_path):
    variable_run(tmp_path, document('''    Check    ${-17}    -17
    Check    ${0b101}    5
    Check    ${0o17}    15
    Check    ${0x2a}    42
    Check    ${+3.5}    3.5
    VAR    ${17}    shadow
    Check    ${17}    'shadow'
    ${present}=    Get Variable Value    $present_f02    fallback
    Check    ${present}    'here'
    ${absent}=    Get Variable Value    $missing_f02
    Check    ${absent}    None
    ${replacement}=    Get Variable Value    $missing_f02    supplied
    Check    ${replacement}    'supplied'
''', variables='${present_f02}    here\n', extra_tests='''Direct Missing
    Give    ${missing_f02}
'''), failures=['Direct Missing'])


def test_indexed_assignment_mutates_shared_objects(tmp_path):
    variable_run(tmp_path, document('''    ${items}=    Evaluate    [1, 2, 3, 4]
    ${alias}=    Give    ${items}
    ${items}[1]=    Give    ${9}
    Check    ${alias}    [1, 9, 3, 4]
    ${items}[1:3]=    Give    ${replacement}
    Check    ${alias}    [1, 7, 8, 10, 4]
    ${mapping}=    Evaluate    {'old': 1}
    ${other}=    Give    ${mapping}
    ${mapping}[old]=    Give    ${2}
    ${mapping}[new]=    Give    ${3}
    Check    ${other}    {'old': 2, 'new': 3}
    Same    ${items}    ${alias}
    Same    ${mapping}    ${other}
''', variables='${replacement}    ${{[7, 8, 10]}}\n'))


def test_attribute_assignment_precedence_and_refusal(tmp_path):
    bad = ['${immutable}[0]=    Give    changed', '${items}[99]=    Give    changed',
           '${locked.real}=    Give    ${7}']
    variable_run(tmp_path, document('''    ${obj}=    Evaluate    types.SimpleNamespace(value=1)    modules=types
    ${alias}=    Give    ${obj}
    ${obj.value}=    Give    ${7}
    Check    ${alias.value}    7
    VAR    ${missing.value}    complete
    ${missing.value}=    Give    replaced
    Check    ${missing.value}    'replaced'
    Check    ${alias.value}    7
    ${absent.attr}=    Give    local value
    Check    ${absent.attr}    'local value'
    VAR    ${text}    text
    ${text.attr}=    Give    text attribute
    Check    ${text.attr}    'text attribute'
    VAR    ${integer}    ${3}
    ${integer.attr}=    Give    int attribute
    Check    ${integer.attr}    'int attribute'
    VAR    ${floating}    ${3.5}
    ${floating.attr}=    Give    float attribute
    Check    ${floating.attr}    'float attribute'
''', variables='''${immutable}    ${{(1, 2)}}
${items}    ${{[1, 2]}}
${locked}    ${{1+2j}}
''', extra_tests=rejection_cases(bad)), failures=rejected_names(bad))
