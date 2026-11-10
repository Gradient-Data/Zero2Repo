# feature: F08
"""Acceptance observations through real Collections keywords in Velun workflows."""
from _helpers import temporary_workspace, require_python
from F06_helpers import failure_reason
from F08_helpers import collection_run


def test_list_transformations_and_mutation():
    with temporary_workspace() as d:
        collection_run(d, r'''Working
    ${source}=    Evaluate    ('pear', 'apple', 'pear')
    ${a}=    Convert To List    ${source}
    Check    ${a}    ['pear','apple','pear']
    ${alias}=    Set Variable    ${a}
    ${v}=    Append To List    ${a}    plum    lime
    Check    ${v}    ['pear','apple','pear','plum','lime']
    Check    ${alias}    ['pear','apple','pear','plum','lime']
    ${v}=    Insert Into List    ${a}    1    fig
    Check    ${v}    ['pear','fig','apple','pear','plum','lime']
    Check    ${alias}    ['pear','fig','apple','pear','plum','lime']
    ${v}=    Set List Value    ${a}    2    fig
    Check    ${v}    ['pear','fig','fig','pear','plum','lime']
    Check    ${alias}    ['pear','fig','fig','pear','plum','lime']
    ${v}=    Combine Lists    ${a}    ${source}
    Check    ${v}    ['pear','fig','fig','pear','plum','lime','pear','apple','pear']
    Check    ${a}    ['pear','fig','fig','pear','plum','lime']
    Check    ${source}    ('pear','apple','pear')
    ${v}=    Remove Values From List    ${a}    pear    absent
    Check    ${v}    ['fig','fig','plum','lime']
    Check    ${alias}    ['fig','fig','plum','lime']
    ${v}=    Remove From List    ${a}    2
    Check    ${v}    'plum'
    Check    ${alias}    ['fig','fig','lime']
    ${duplicates}=    Evaluate    ['lime','fig','lime','ash','fig']
    ${v}=    Remove Duplicates    ${duplicates}
    Check    ${v}    ['lime','fig','ash']
    Check    ${duplicates}    ['lime','fig','lime','ash','fig']
    Check    ${a}    ['fig','fig','lime']
    ${v}=    Reverse List    ${a}
    Check    ${v}    ['lime','fig','fig']
    Check    ${alias}    ['lime','fig','fig']
    ${v}=    Sort List    ${a}
    Check    ${v}    ['fig','fig','lime']
    Check    ${alias}    ['fig','fig','lime']
    ${numbers}=    Evaluate    [12,-3,2,12]
    Sort List    ${numbers}
    Check    ${numbers}    [-3,2,12,12]
''')


def test_list_reads_searches_and_copy_isolation():
    with temporary_workspace() as d:
        collection_run(d, r'''Working
    ${a}=    Evaluate    ['oak','elm','oak','ash','oak']
    ${v}=    Get From List    ${a}    1
    Check    ${v}    'elm'
    ${v}=    Get Slice From List    ${a}    1    -1
    Check    ${v}    ['elm','oak','ash']
    ${v}=    Get Index From List    ${a}    oak    1    4
    Check    ${v}    2
    ${v}=    Get Index From List    ${a}    oak    -2
    Check    ${v}    4
    ${v}=    Get Index From List    ${a}    absent
    Check    ${v}    -1
    ${v}=    Get Index From List    ${a}    oak    1    2
    Check    ${v}    -1
    ${v}=    Count Values In List    ${a}    oak
    Check    ${v}    3
    ${v}=    Count Values In List    ${a}    oak    1    -1
    Check    ${v}    1
    ${v}=    Count Values In List    ${a}    absent
    Check    ${v}    0
    Check    ${a}    ['oak','elm','oak','ash','oak']
    ${nested}=    Evaluate    [['seed'], 'outer']
    ${shallow}=    Copy List    ${nested}
    ${deep}=    Copy List    ${nested}    deepcopy=True
    Append To List    ${shallow}    extra
    Append To List    ${shallow}[0]    grown
    Check    ${nested}    [['seed','grown'],'outer']
    Check    ${shallow}    [['seed','grown'],'outer','extra']
    Check    ${deep}    [['seed'],'outer']
    Append To List    ${deep}[0]    isolated
    Check    ${nested}    [['seed','grown'],'outer']
Unsortable
    ${a}=    Evaluate    [1, 'two']
    Sort List    ${a}
''', failures=('Unsortable',))


def test_dictionary_reads_edits_and_missing_data():
    with temporary_workspace() as d:
        collection_run(d, r'''Working
    ${a}=    Evaluate    {'oak':1,'elm':2,'ash':3}
    ${alias}=    Set Variable    ${a}
    ${v}=    Get From Dictionary    ${a}    elm
    Check    ${v}    2
    ${v}=    Get From Dictionary    ${a}    absent    default=chosen
    Check    ${v}    'chosen'
    ${v}=    Get From Dictionary    ${a}    oak    default=unused
    Check    ${v}    1
    ${v}=    Set To Dictionary    ${a}    oak    ${9}    fir    ${4}
    Check    ${v}    {'oak':9,'elm':2,'ash':3,'fir':4}
    Check    ${alias}    {'oak':9,'elm':2,'ash':3,'fir':4}
    ${later}=    Evaluate    {'oak':11,'pine':5}
    ${v}=    Create Dictionary    &{a}    &{later}
    Check    ${v}    {'oak':11,'elm':2,'ash':3,'fir':4,'pine':5}
    Check    ${a}    {'oak':9,'elm':2,'ash':3,'fir':4}
    ${v}=    Remove From Dictionary    ${a}    elm    missing
    Check    ${v}    {'oak':9,'ash':3,'fir':4}
    Check    ${alias}    {'oak':9,'ash':3,'fir':4}
    ${v}=    Pop From Dictionary    ${a}    ash
    Check    ${v}    3
    Check    ${alias}    {'oak':9,'fir':4}
    ${v}=    Pop From Dictionary    ${a}    missing    default=${None}
    Check    ${v}    None
    ${v}=    Keep In Dictionary    ${a}    oak    absent
    Check    ${v}    {'oak':9}
    Check    ${alias}    {'oak':9}
Missing Read
    ${a}=    Evaluate    {'oak':1}
    Get From Dictionary    ${a}    missing-read-key
Missing Pop
    ${a}=    Evaluate    {'oak':1}
    Pop From Dictionary    ${a}    missing-pop-key
''', failures=('Missing Read','Missing Pop'))


def test_dictionary_enumeration_and_copy_isolation():
    with temporary_workspace() as d:
        cases = 'Working\n    ${a}=    Evaluate    {"z":1,"a":3,"m":2}\n'
        for keyword, sorted_value, original in (
            ('Keys', "['a','m','z']", "['z','a','m']"),
            ('Values', '[3,2,1]', '[1,3,2]'),
            ('Items', "['a',3,'m',2,'z',1]", "['z',1,'a',3,'m',2]")):
            cases += f'    ${{v}}=    Get Dictionary {keyword}    ${{a}}\n    Check    ${{v}}    {sorted_value}\n'
            cases += f'    ${{v}}=    Get Dictionary {keyword}    ${{a}}    sort_keys=False\n    Check    ${{v}}    {original}\n'
        cases += '''    Check    ${a}    {'z':1,'a':3,'m':2}
    ${a}=    Evaluate    {'z':3, 4:'four', 'a':1}
'''
        for keyword, expected in (('Keys', "['z',4,'a']"), ('Values', "[3,'four',1]"),
                                  ('Items', "['z',3,4,'four','a',1]")):
            cases += f'    ${{v}}=    Get Dictionary {keyword}    ${{a}}\n    Check    ${{v}}    {expected}\n'
        cases += '''    ${a}=    Evaluate    {'nested':['seed'],'value':1}
    ${shallow}=    Copy Dictionary    ${a}
    ${deep}=    Copy Dictionary    ${a}    deepcopy=True
    Set To Dictionary    ${shallow}    value    ${2}
    Append To List    ${shallow}[nested]    grown
    Check    ${a}    {'nested':['seed','grown'],'value':1}
    Check    ${shallow}    {'nested':['seed','grown'],'value':2}
    Check    ${deep}    {'nested':['seed'],'value':1}
    Append To List    ${deep}[nested]    isolated
    Check    ${a}    {'nested':['seed','grown'],'value':1}
'''
        collection_run(d, cases)


def test_collection_relationship_assertions():
    with temporary_workspace() as d:
        cases = r'''Working
    ${a}=    Evaluate    ['oak','elm','oak']
    ${tuple}=    Evaluate    ('oak','elm','oak')
    Lists Should Be Equal    ${a}    ${tuple}
    Lists Should Be Equal    ${a}    ['elm','oak','oak']    ignore_order=True
    List Should Contain Sub List    ${a}    ['elm','elm','oak']
    List Should Contain Value    ${a}    elm
    List Should Not Contain Value    ${a}    ash
    List Should Not Contain Duplicates    ['oak','elm']
    Lists Should Be Equal    [{'Branch':['LEAF']}]    [{'branch':['leaf']}]    ignore_case=True
    ${a}=    Evaluate    {'name':'Oak','nested':{'LEAF':['Green']},'skip':1}
    ${b}=    Evaluate    {'NAME':'oak','NESTED':{'leaf':['green']},'skip':99}
    Dictionaries Should Be Equal    ${a}    ${b}    ignore_case=True    ignore_keys=['skip']
    Dictionaries Should Be Equal    {'Name':'Oak'}    {'name':'Oak'}    ignore_case=KEYS
    Dictionaries Should Be Equal    {'Name':'Oak'}    {'Name':'oak'}    ignore_case=VALUES
    Dictionary Should Contain Sub Dictionary    ${a}    {'name':'Oak'}
    Dictionary Should Contain Key    ${a}    name
    Dictionary Should Not Contain Key    ${a}    absent
    Dictionary Should Contain Item    ${a}    name    Oak
    Dictionary Should Contain Value    ${a}    Oak
    Dictionary Should Not Contain Value    ${a}    Ash
'''
        rejected = {
            'Positions': "Lists Should Be Equal    ['oak','elm']    ['elm','oak']",
            'Occurrences': "Lists Should Be Equal    ['oak','oak','elm']    ['oak','elm','elm']    ignore_order=True",
            'List Missing': "List Should Contain Sub List    ['oak']    ['elm']",
            'Later Missing': "List Should Contain Sub List    ['oak','elm']    ['elm','ash']",
            'List Case': "Lists Should Be Equal    ['Oak']    ['oak']",
            'Duplicates': "List Should Not Contain Duplicates    ['oak','oak']",
            'Contains': "List Should Contain Value    ['oak']    elm",
            'Not Contains': "List Should Not Contain Value    ['oak']    oak",
            'Dict Missing': "Dictionary Should Contain Key    {'oak':1}    elm",
            'Dict Extra': "Dictionary Should Not Contain Key    {'oak':1}    oak",
            'Item': "Dictionary Should Contain Item    {'oak':1}    oak    ${2}",
            'Value': "Dictionary Should Contain Value    {'oak':1}    ${2}",
            'Not Value': "Dictionary Should Not Contain Value    {'oak':1}    ${1}",
            'Dict Keys': "Dictionaries Should Be Equal    {'oak':1}    {'elm':1}",
            'Dict Values': "Dictionaries Should Be Equal    {'oak':'old-value'}    {'oak':'new-value'}",
            'Dict Subset': "Dictionary Should Contain Sub Dictionary    {'oak':1}    {'oak':2}",
            'Subset Missing': "Dictionary Should Contain Sub Dictionary    {'oak':1}    {'oak':1,'elm':1}",
            'Dict Case': "Dictionaries Should Be Equal    {'Name':'Oak'}    {'name':'Oak'}",
            'Excluded Only': "Dictionaries Should Be Equal    {'oak':1,'skip':1}    {'oak':2,'skip':2}    ignore_keys=['skip']",
            'Ambiguous': "Dictionaries Should Be Equal    {'oak':1,'OAK':2}    {'oak':1}    ignore_case=KEYS",
            'Keys Only': "Dictionaries Should Be Equal    {'Name':'Oak'}    {'name':'oak'}    ignore_case=KEYS",
            'Values Only': "Dictionaries Should Be Equal    {'Name':'Oak'}    {'name':'oak'}    ignore_case=VALUES",
        }
        cases += ''.join(f'{name}\n    {statement}\n' for name, statement in rejected.items())
        root = collection_run(d, cases, failures=tuple(rejected))
        for name, tokens in {'Positions':['oak','elm'], 'List Missing':['elm'], 'Later Missing':['ash'],
                             'Subset Missing':['elm'],
                             'Dict Keys':['oak','elm'], 'Dict Values':['oak','old-value','new-value'],
                             'Dict Missing':['elm'], 'Ambiguous':['oak']}.items():
            reason = failure_reason(root, name)
            for token in tokens:
                assert token in reason, (name, reason)


def test_collection_pattern_selection_and_assertions():
    require_python((3, 13))
    with temporary_workspace() as d:
        collection_run(d, r'''Working
    ${a}=    Evaluate    ['ab7 tail','xab7','ab7','AB7','a b7',17,None,'ab7']
    ${v}=    Get Matches    ${a}    ab?
    Check    ${v}    ['ab7','ab7']
    ${v}=    Get Matches    ${a}    regexp=ab[0-9]
    Check    ${v}    ['ab7 tail','ab7','ab7']
    ${v}=    Get Match Count    ${a}    ab?
    Check    ${v}    2
    ${v}=    Get Match Count    ${a}    regexp=ab[0-9]
    Check    ${v}    3
    ${v}=    Get Matches    ${a}    ab?    ignore_case=True
    Check    ${v}    ['ab7','AB7','ab7']
    ${v}=    Get Matches    ${a}    ab?    ignore_whitespace=True
    Check    ${v}    ['ab7','a b7','ab7']
    ${v}=    Get Matches    ${a}    ab?    ignore_case=True    ignore_whitespace=True
    Check    ${v}    ['ab7','AB7','a b7','ab7']
    ${v}=    Get Matches    ${a}    regexp=ab[0-9]    ignore_case=True
    Check    ${v}    ['ab7 tail','ab7','AB7','ab7']
    Should Contain Match    ${a}    a?7
    Should Not Contain Match    ['AB7']    ab?
    ${v}=    Get Matches    ${a}    *
    Check    ${v}    ['ab7 tail','xab7','ab7','AB7','a b7','ab7']
    ${v}=    Get Matches    ${a}    absent*
    Check    ${v}    []
    ${v}=    Get Match Count    ${a}    absent*
    Check    ${v}    0
    Should Contain Match    ${a}    regexp=ab[0-9]
    Should Not Contain Match    ${a}    absent*
    Check    ${a}    ['ab7 tail','xab7','ab7','AB7','a b7',17,None,'ab7']
No Match
    Should Contain Match    ['xab7']    regexp=ab[0-9]
Unexpected Match
    Should Not Contain Match    ['ab7']    ab?
Case Significant
    Should Contain Match    ['AB7','a b7']    ab?
Nontext
    Should Contain Match    [17,None]    *
''', failures=('No Match','Unexpected Match','Case Significant','Nontext'))


def test_boundaries_immutable_inputs_and_invalid_operations():
    with temporary_workspace() as d:
        cases = r'''Working
    ${a}=    Evaluate    ['a','b','c']
    ${v}=    Get From List    ${a}    -1
    Check    ${v}    'c'
    ${v}=    Get From List    ${a}    -3
    Check    ${v}    'a'
    Insert Into List    ${a}    99    end
    Insert Into List    ${a}    -99    start
    Check    ${a}    ['start','a','b','c','end']
    Set List Value    ${a}    -2    changed
    ${v}=    Remove From List    ${a}    -1
    Check    ${v}    'end'
    Check    ${a}    ['start','a','b','changed']
'''
        for statement, expected in (
            ('Append To List    ${immutable}    d', "['c','a','b','d']"),
            ('Insert Into List    ${immutable}    -1    d', "['c','a','d','b']"),
            ('Set List Value    ${immutable}    -1    d', "['c','a','d']"),
            ('Remove Values From List    ${immutable}    a', "['c','b']"),
            ('Reverse List    ${immutable}', "['b','a','c']"),
            ('Sort List    ${immutable}', "['a','b','c']")):
            cases += '    ${immutable}=    Evaluate    ("c","a","b")\n'
            cases += f'    ${{v}}=    {statement}\n    Check    ${{v}}    {expected}\n'
            cases += '    Check    ${immutable}    ("c","a","b")\n    Append To List    ${v}    mutable\n'
        cases += '''    ${immutable}=    Evaluate    ('c','a','b')
    ${v}=    Remove From List    ${immutable}    -1
    Check    ${v}    'b'
    Check    ${immutable}    ('c','a','b')
    ${immutable}=    Evaluate    types.MappingProxyType({'a':1,'b':2})    modules=types
    ${v}=    Pop From Dictionary    ${immutable}    a
    Check    ${v}    1
    Check    ${immutable}    {'a':1,'b':2}
'''
        for statement, expected in (
            ('Set To Dictionary    ${immutable}    a    ${9}', "{'a':9,'b':2}"),
            ('Remove From Dictionary    ${immutable}    a', "{'b':2}"),
            ('Keep In Dictionary    ${immutable}    a', "{'a':1}")):
            cases += "    ${immutable}=    Evaluate    types.MappingProxyType({'a':1,'b':2})    modules=types\n"
            cases += f'    ${{v}}=    {statement}\n    Check    ${{v}}    {expected}\n'
            cases += "    Check    ${immutable}    {'a':1,'b':2}\n    Set To Dictionary    ${v}    mutable    yes\n"
        invalid = {
            'Read Right': "Get From List    ['a','b']    2",
            'Read Left': "Get From List    ['a','b']    -3",
            'Replace Range': "Set List Value    ['a','b']    2    x",
            'Remove Range': "Remove From List    ['a','b']    -3",
            'Bad Index': "Get From List    ['a']    not-an-index",
            'Bad List': "Append To List    ${42}    x",
            'Bad Mapping': "Get From Dictionary    ${42}    x",
        }
        cases += ''.join(f'{name}\n    {statement}\n' for name, statement in invalid.items())
        collection_run(d, cases, failures=tuple(invalid))
