# feature: F04
"""Acceptance of reusable workflows through the Velun command entry."""
from _helpers import write_file
from F02_helpers import document, rejection_cases, rejected_names
from F04_helpers import workflow_run, workflow_events


def test_transitive_resources_and_import_locations(tmp_path):
    write_file(tmp_path / 'pkg' / 'outer.resource', '''*** Settings ***
Resource    inner.resource
*** Keywords ***
Compose
    ${v}=    Build Value    ${SHARED}
    RETURN    ${v}
''')
    write_file(tmp_path / 'pkg' / 'inner.resource', '''*** Settings ***
Library    Joiner.py
*** Variables ***
${SHARED}    local
*** Keywords ***
Build Value
    [Arguments]    ${value}
    ${v}=    Join Value    ${value}
    RETURN    ${v}
''')
    write_file(tmp_path / 'pkg' / 'Joiner.py', "def join_value(value):\n    return value + ':joined'\n")
    write_file(tmp_path / 'search' / 'inner.resource', '''*** Variables ***
${SHARED}    wrong
*** Keywords ***
Build Value
    Fail    Search path must not shadow the importing directory.
''')
    write_file(tmp_path / 'search' / 'fallback.resource', '''*** Keywords ***
Fallback Value
    RETURN    from-search
''')
    source = document('''    ${v}=    Compose
    Check    ${v}    'local:joined'
    ${v}=    Fallback Value
    Check    ${v}    'from-search'
    Check    ${SHARED}    'local'
    ${v}=    Join Value    direct
    Check    ${v}    'direct:joined'
''', settings='Resource    pkg/outer.resource\nResource    fallback.resource\nResource    absent-workflow.resource\n')
    process, root = workflow_run(tmp_path, source, checks=4,
                                options=['--pythonpath', str(tmp_path / 'search')])
    errors = root.findall('./errors/msg')
    assert any(m.attrib['level'] == 'ERROR' and 'absent-workflow.resource' in (m.text or '') for m in errors)
    assert b'absent-workflow.resource' in process.stderr


def test_user_argument_binding_conversion_and_local_scope(tmp_path):
    keywords = '''Bind
    [Arguments]    ${first}    ${copy}=${first}    @{rest}    ${named}    &{extra}
    Check    ${copy}    'seed'
    Check    ${rest}    ['tail', 'end']
    Check    ${named}    'only'
    Check    ${extra}    {'color': 'blue'}
    RETURN    ${first}
Default
    [Arguments]    ${first}    ${copy}=${first}
    RETURN    ${copy}
Typed
    [Arguments]    ${count: int}    ${enabled: bool}
    RETURN    ${count}    ${enabled}
Fixed
    [Arguments]    ${required}    ${optional}=default    @{}    ${named}
    RETURN    ${optional}
Caller
    ${caller_only}=    Set Variable    private
    Read Local
Read Local
    Check    ${caller_only}    'private'
'''
    bad = ['Fixed    named=n', 'Fixed    x    named=n    surprise=v',
           'Fixed    x    required=y    named=n', 'Fixed    x',
           'Fixed    x    a    b    named=n', 'Typed    not-an-integer    yes', 'Caller']
    source = document('''    ${caller_only}=    Set Variable    private
    ${v}=    Bind    seed    seed    tail    end    named=only    color=blue
    Check    ${v}    'seed'
    ${v}=    Default    seed
    Check    ${v}    'seed'
    ${v}=    Default    other
    Check    ${v}    'other'
    ${v}=    Default    seed    copy=changed
    Check    ${v}    'changed'
    ${v}=    Typed    12    yes
    Check    ${v}    [12, True]
    ${v}=    Fixed    x    named=n
    Check    ${v}    'default'
''', keywords=keywords, extra_tests=rejection_cases(bad) + '''Test Local
    ${caller_only}=    Set Variable    private
    Read Local
''')
    workflow_run(tmp_path, source, failures=rejected_names(bad) + ['Test Local'], checks=10)


def test_provider_resolution_priorities_and_errors(tmp_path):
    write_file(tmp_path / 'External.py', '''def no_operation(): return 'external'
def pick(): return 'external-pick'
def library_only(): return 'external-only'
''')
    write_file(tmp_path / 'Rival.py', "def shared(): return 'rival'\n")
    write_file(tmp_path / 'Holder.py', "def shared(): return 'holder'\n")
    write_file(tmp_path / 'A.resource', '''*** Keywords ***
Pick
    RETURN    resource-a
Other Choice
    [Tags]    velun:private
    RETURN    private-a
Resource Only
    RETURN    resource-only
Local Caller
    ${v}=    Pick
    RETURN    ${v}
Public Choice
    RETURN    public-a
Ambiguous
    RETURN    a
''')
    write_file(tmp_path / 'B.resource', '''*** Keywords ***
Pick
    RETURN    resource-b
Second Caller
    ${v}=    Pick
    RETURN    ${v}
Other Choice
    RETURN    public-b
Public Choice
    [Tags]    velun:private
    RETURN    private-b
Ambiguous
    RETURN    b
''')
    source = document('''    ${v}=    s_u_i_t_e_p_i_c_k
    Check    ${v}    'suite'
    ${v}=    nO_oPeRaTiOn
    Check    ${v}    'resource-shadow'
    ${v}=    r_E_sOuRcE oNlY
    Check    ${v}    'resource-only'
    ${v}=    l_I_bRaRy oNlY
    Check    ${v}    'external-only'
    ${v}=    A.Local Caller
    Check    ${v}    'resource-a'
    ${v}=    B.Second Caller
    Check    ${v}    'resource-b'
    ${v}=    Public Choice
    Check    ${v}    'public-a'
    ${v}=    Other Choice
    Check    ${v}    'public-b'
    ${v}=    B.Pick
    Check    ${v}    'resource-b'
    ${v}=    B.Ambiguous
    Check    ${v}    'b'
    Set Library Search Order    B    A
    ${v}=    Pick
    Check    ${v}    'resource-b'
    Set Library Search Order    A    B
    ${v}=    Pick
    Check    ${v}    'resource-a'
    Set Library Search Order    C
    ${v}=    nO_oPeRaTiOn
    Check    ${v}    'resource-shadow'
    Set Library Search Order    C    Rival    Holder
    ${v}=    Shared
    Check    ${v}    'rival'
    Set Library Search Order    Holder    Rival
    ${v}=    Shared
    Check    ${v}    'holder'
    Set Library Search Order
    BuiltIn.No Operation
''', settings='Resource    A.resource\nResource    B.resource\nLibrary    External.py\nLibrary    Rival.py\nLibrary    Holder.py\n',
        keywords='''Suite Pick
    RETURN    suite
No Operation
    RETURN    resource-shadow
''', extra_tests='''Ambiguous Call
    Ambiguous
Unknown Call
    Unavailable Workflow Operation
Cleared Order Call
    Set Library Search Order    B    A
    Set Library Search Order
    Pick
Library Collision
    Shared
''')
    # Resource-over-library and library-over-standard use separate declarations.
    write_file(tmp_path / 'C.resource', '''*** Keywords ***
No Operation
    RETURN    resource-over-library
''')
    source = source.replace('Resource    A.resource\n', 'Resource    A.resource\nResource    C.resource\n')
    marker = '    ${v}=    l_I_bRaRy oNlY'
    assert source.count(marker) == 1
    source = source.replace(marker, '''    ${v}=    C.No Operation
    Check    ${v}    'resource-over-library'
    ${v}=    External.No Operation
    Check    ${v}    'external'
''' + marker)
    workflow_run(tmp_path, source, failures=['Ambiguous Call', 'Unknown Call', 'Cleared Order Call', 'Library Collision'], checks=17)
    # Remove the suite declaration to observe the resource precedence, then the library precedence.
    # Naming the library in the search order does not lift it over a resource: nothing is ambiguous across layers.
    for label, imports, expected in [('resource', 'Resource    C.resource\nLibrary    External.py\n', 'resource-over-library'),
                                     ('library', 'Library    External.py\n', 'external')]:
        workflow_run(tmp_path / label, document(f"    Set Library Search Order    External\n    ${{v}}=    No Operation\n    Check    ${{v}}    {expected!r}\n",
                     settings=imports.replace('C.resource', str(tmp_path / 'C.resource')).replace('External.py', str(tmp_path / 'External.py'))), checks=1)


def test_bdd_english_translated_prefixes_and_full_name_fallback(tmp_path):
    body = ''
    keywords = '''Action
    [Arguments]    ${value}
    RETURN    stripped:${value}
Given Action
    [Arguments]    ${value}
    RETURN    full:${value}
Oletetaan Action
    [Arguments]    ${value}
    RETURN    translated-full:${value}
Given Unique
    RETURN    full-only
Oletetaan Unique
    RETURN    translated-only
'''
    for prefix, expected in [('Given', 'stripped'), ('When', 'stripped'), ('Then', 'stripped'),
                             ('And', 'stripped'), ('But', 'stripped'), ('Oletetaan', 'stripped'),
                             ('Kun', 'stripped'), ('Niin', 'stripped'), ('Ja', 'stripped'), ('Mutta', 'stripped')]:
        body += f'    ${{v}}=    {prefix} Action    payload\n    Check    ${{v}}    {expected + ":payload"!r}\n'
    body += '''    ${v}=    Given Unique
    Check    ${v}    'full-only'
    ${v}=    Oletetaan Unique
    Check    ${v}    'translated-only'
'''
    workflow_run(tmp_path, document(body, keywords=keywords), checks=12, options=['--language', 'fi'])
    # Without activation the translated word is not a prefix; the English ones remain.
    inactive = document('''    ${v}=    Given Action    payload
    Check    ${v}    'stripped:payload'
''', keywords=keywords, extra_tests='''Inactive Prefix
    Oletetaan Plain
''') + '''Plain
    RETURN    plain
'''
    workflow_run(tmp_path / 'inactive', inactive, failures=['Inactive Prefix'], checks=1)


def test_embedded_binding_restrictions_and_candidate_selection(tmp_path):
    write_file(tmp_path / 'Preferred.resource', '''*** Keywords ***
Choose ${value}
    RETURN    preferred:${value}
Choose pear
    RETURN    preferred-ordinary
Internal
    ${v}=    Choose apple
    RETURN    ${v}
''')
    write_file(tmp_path / 'Other.resource', '''*** Keywords ***
Choose apple
    RETURN    ordinary-other
Paint blue wall
    RETURN    resource-ordinary
''')
    keywords = r'''Paint ${general_item_with_a_long_declared_name}
    RETURN    general:${general_item_with_a_long_declared_name}
Paint red ${item}
    RETURN    specific:${item}
Paint red door
    RETURN    ordinary
Code ${value:[0-9]+}
    RETURN    code:${value}
Keep_space ${value}
    RETURN    kept:${value}
Pair ${a} with item
    RETURN    first
Pair item with ${b}
    RETURN    second
Wash ${shade} car
    RETURN    shade:${shade}
Wash red ${vehicle_with_a_long_name}
    RETURN    vehicle:${vehicle_with_a_long_name}
Move ${what} to ${where}
    RETURN    ${what}>${where}
'''
    body = '''    ${v}=    Paint red door
    Check    ${v}    'ordinary'
    ${v}=    Paint red wall
    Check    ${v}    'specific:wall'
    ${v}=    Paint blue wall
    Check    ${v}    'general:blue wall'
    ${v}=    cOdE 731
    Check    ${v}    'code:731'
    ${v}=    kEEP_space value
    Check    ${v}    'kept:value'
    ${v}=    Choose apple
    Check    ${v}    'ordinary-other'
    ${v}=    Preferred.Choose apple
    Check    ${v}    'preferred:apple'
    ${v}=    Preferred.Choose pear
    Check    ${v}    'preferred-ordinary'
    ${v}=    Pair red with item
    Check    ${v}    'first'
    ${v}=    Pair item with blue
    Check    ${v}    'second'
    ${v}=    Wash blue car
    Check    ${v}    'shade:blue'
    ${v}=    Wash red bike
    Check    ${v}    'vehicle:bike'
    ${v}=    Move box to shelf
    Check    ${v}    'box>shelf'
    Set Library Search Order    Preferred
    ${v}=    Choose apple
    Check    ${v}    'preferred:apple'
    Set Library Search Order
    ${v}=    Preferred.Internal
    Check    ${v}    'preferred:apple'
'''
    bad = ['Code letters', 'Code 731x', 'Keep space value', 'Keep__space value', 'Keep_spacevalue', 'Pair item with item', 'Wash red car']
    workflow_run(tmp_path, document(body, settings='Resource    Preferred.resource\nResource    Other.resource\n',
                 keywords=keywords, extra_tests=rejection_cases(bad)), failures=rejected_names(bad), checks=15)


def test_return_values_and_nested_early_return(tmp_path):
    keywords = '''Empty Return
    RETURN
Single Return
    [Arguments]    ${value}
    RETURN    ${value}
Many Return
    RETURN    alpha    beta    gamma
Collection Return
    ${items}=    Create List    red    green
    RETURN    ${items}
Early Return
    FOR    ${i}    IN RANGE    4
        IF    ${i} == 2
            RETURN    ${i}    finished
        END
        Mark    visited    ${i}
    END
    Mark    unreachable
    Fail    Return failed to exit the workflow.
'''
    body = '''    ${v}=    Empty Return
    Check    ${v}    None
    ${v}=    Single Return    payload
    Check    ${v}    'payload'
    ${v}=    Many Return
    Check    ${v}    ['alpha', 'beta', 'gamma']
    ${first}    @{rest}=    Many Return
    Check    ${first}    'alpha'
    Check    ${rest}    ['beta', 'gamma']
    ${v}=    Collection Return
    Check    ${v}    ['red', 'green']
    ${v}=    Early Return
    Check    ${v}    [2, 'finished']
    Mark    caller continued
'''
    _, root = workflow_run(tmp_path, document(body, settings='Library    Trace.py\n', keywords=keywords), checks=7)
    assert workflow_events(root, 'Working') == [['visited', 0], ['visited', 1], ['caller continued']]


def test_keyword_setup_body_cleanup_and_empty_body(tmp_path):
    keywords = '''Normal
    [Setup]    Mark    setup
    [Teardown]    Mark    cleanup
    Mark    body
Setup Failure
    [Setup]    Fail    Setup rejected.
    [Teardown]    Mark    cleanup
    Mark    forbidden body
Body Failure
    [Setup]    Mark    setup
    [Teardown]    Mark    cleanup
    Mark    body
    Fail    Body rejected.
Cleanup Failure
    [Setup]    Mark    setup
    [Teardown]    Fail    Cleanup rejected.
    Mark    body
Empty Body
    [Documentation]    Documentation does not make an executable body.
Returning
    [Teardown]    Mark    cleanup
    Mark    body
    RETURN    returned
    Mark    forbidden after return
'''
    source = document("    Normal\n    ${v}=    Returning\n    Check    ${v}    'returned'\n", settings='Library    Trace.py\n', keywords=keywords,
                      extra_tests='''Setup Rejection
    Setup Failure
Body Rejection
    Body Failure
Cleanup Rejection
    Cleanup Failure
Empty Rejection
    Empty Body
''')
    _, root = workflow_run(tmp_path, source, failures=['Setup Rejection', 'Body Rejection', 'Cleanup Rejection', 'Empty Rejection'], checks=1)
    for name, events in [('Working', [['setup'], ['body'], ['cleanup'], ['body'], ['cleanup']]),
                         ('Setup Rejection', [['cleanup']]),
                         ('Body Rejection', [['setup'], ['body'], ['cleanup']]),
                         ('Cleanup Rejection', [['setup'], ['body']]), ('Empty Rejection', [])]:
        assert workflow_events(root, name) == events
    assert ['forbidden body'] not in workflow_events(root, 'Setup Rejection')


def test_templates_rows_overrides_loops_and_stopping_conditions(tmp_path):
    keywords = '''Default Row
    [Arguments]    ${value}    ${kind}
    Mark    default    ${value}    ${kind}
    IF    $kind == 'fail'
        Fail    Ordinary row failure.
    END
    IF    $kind == 'fatal'
        Fatal Error    Fatal row failure.
    END
    IF    $kind == 'slow'
        Sleep    2 seconds
    END
Alternate Row
    [Arguments]    ${value}
    Mark    alternate    ${value}
Syntax Row
    [Arguments]    ${value}
    Mark    syntax    ${value}
    IF    $value == 'bad'
        Invalid Body
    END
Invalid Body
    IF    True
        Mark    invalid
'''
    text = '''*** Settings ***
Library    Trace.py
Test Template    Default Row
*** Test Cases ***
Rows
    first    pass
    second    fail
    third    pass
Loop Rows
    FOR    ${v}    IN    one    two
        ${v}    pass
    END
Loop Failure
    FOR    ${v}    IN    one    two
        ${v}    fail
    END
Override
    [Template]    Alternate Row
    custom
Disabled
    [Template]    NONE
    Mark    ordinary
Syntax Stop
    [Template]    Syntax Row
    first
    bad
    forbidden
Timeout Stop
    [Timeout]    200 milliseconds
    waiting    slow
    forbidden    pass
Fatal Stop
    last    fatal
    forbidden    pass
*** Keywords ***
'''+keywords
    _, root = workflow_run(tmp_path, text, passed=['Loop Rows', 'Override', 'Disabled'],
                           failures=['Rows', 'Loop Failure', 'Syntax Stop', 'Timeout Stop', 'Fatal Stop'])
    expected = {'Rows': [['default', 'first', 'pass'], ['default', 'second', 'fail'], ['default', 'third', 'pass']],
                'Loop Rows': [['default', 'one', 'pass'], ['default', 'two', 'pass']],
                'Override': [['alternate', 'custom']], 'Disabled': [['ordinary']],
                'Loop Failure': [['default', 'one', 'fail'], ['default', 'two', 'fail']],
                'Syntax Stop': [['syntax', 'first'], ['syntax', 'bad']],
                'Timeout Stop': [['default', 'waiting', 'slow']], 'Fatal Stop': [['default', 'last', 'fatal']]}
    for name, events in expected.items():
        assert workflow_events(root, name) == events


def test_private_keywords_callable_with_external_warning(tmp_path):
    write_file(tmp_path / 'Vault.resource', '''*** Keywords ***
Hidden
    [Tags]    velun:private
    RETURN    secret-result
Public Wrapper
    ${v}=    Hidden
    RETURN    ${v}
''')
    write_file(tmp_path / 'Outsider.resource', '''*** Keywords ***
Outside Caller
    ${v}=    Hidden
    RETURN    ${v}
''')
    source = document('''    ${v}=    Vault.Public Wrapper
    Check    ${v}    'secret-result'
''', settings='Resource    Vault.resource\nResource    Outsider.resource\n', extra_tests='''External
    ${v}=    Vault.Hidden
    Check    ${v}    'secret-result'
Other Resource
    ${v}=    Outside Caller
    Check    ${v}    'secret-result'
''')
    _, root = workflow_run(tmp_path, source, passed=['Working', 'External', 'Other Resource'], checks=3)
    cases = {c.attrib['name']: c for c in root.findall('.//test')}
    assert not cases['Working'].findall('.//msg[@level="WARN"]')
    for name in ('External', 'Other Resource'):
        warnings = cases[name].findall('.//msg[@level="WARN"]')
        assert warnings and all(m.text for m in warnings)
