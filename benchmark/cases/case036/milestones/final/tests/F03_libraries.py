# feature: F03
"""Acceptance of externally supplied library operations through public entries."""
import datetime
import socket

from velun.velunexdocs import LibraryDocumentation
from _helpers import write_file, call_public, keyword_calls
from F01_helpers import execute_source
from F02_helpers import WITNESS, rejection_cases, rejected_names
from F03_helpers import library_run, library_outcomes, keyword_service, TYPED_LIBRARY


def test_library_import_locations_initializers_and_aliases(tmp_path):
    source = '''from pathlib import Path
class Provider:
    def __init__(self, label, path, suffix='!'):
        self.label = label + suffix
        self.path = Path(path)
    def deliver(self, value):
        self.path.write_text(self.label + ':' + value)
        return self.label + ':' + value
'''
    write_file(tmp_path / 'Provider.py', source)
    write_file(tmp_path / 'NamedProvider.py', source.replace('Provider', 'NamedProvider'))
    search = tmp_path / 'search'
    write_file(search / 'SearchProvider.py', source.replace('Provider', 'SearchProvider'))
    # An equally named provider on the search path must not shadow the local one.
    write_file(search / 'Provider.py', source.replace("label + suffix", "'wrong provider'"))
    write_file(tmp_path / 'nested' / 'Absolute.py', source.replace('Provider', 'Absolute'))
    libraries = (f'Library    Provider.py    relative    {tmp_path / "relative.txt"}    WITH NAME    Relative\n'
                 f'Library    NamedProvider    named    {tmp_path / "named.txt"}    suffix=?    WITH NAME    Named\n'
                 f'Library    SearchProvider    searched    {tmp_path / "search.txt"}    WITH NAME    Searched\n'
                 f'Library    {tmp_path / "nested" / "Absolute.py"}    absolute    {tmp_path / "absolute.txt"}    WITH NAME    Located\n')
    body = ''
    for alias, label, filename in [('Relative', 'relative!', 'relative'), ('Named', 'named?', 'named'),
                                    ('Searched', 'searched!', 'search'), ('Located', 'absolute!', 'absolute')]:
        body += f'    ${{v}}=    {alias}.Deliver    payload\n    Check    ${{v}}    {repr(label + ":payload")}\n'
    library_run(tmp_path, body, libraries=libraries, options=['--pythonpath', str(search), '--pythonpath', str(tmp_path)])
    for filename, expected in [('relative', 'relative!'), ('named', 'named?'), ('search', 'searched!'), ('absolute', 'absolute!')]:
        assert (tmp_path / (filename + '.txt')).read_text() == expected + ':payload'


def test_library_import_and_initialization_errors(tmp_path):
    write_file(tmp_path / 'Broken.py', "class Broken:\n    def __init__(self):\n        raise ValueError('Initialization refused by provider.')\n")
    write_file(tmp_path / 'SyntaxBroken.py', 'def invalid(:\n')
    process, root = library_run(tmp_path, "    Check    ${17}    17\n", libraries='''Library    MissingF03Provider
Library    Broken.py
Library    SyntaxBroken.py
''', extra_tests='''Unavailable Keyword
    MissingF03Provider.Deliver
''', failures=['Unavailable Keyword'])
    errors = root.findall('./errors/msg')
    assert errors and all(m.attrib['level'] == 'ERROR' for m in errors)
    for identity in ['MissingF03Provider', 'Broken.py', 'SyntaxBroken.py']:
        assert any(identity in (m.text or '') for m in errors), (identity, [m.text for m in errors])
        assert identity.encode() in process.stderr


def test_static_hybrid_dynamic_discovery_and_metadata(tmp_path):
    static = '''from velun.api.deco import keyword, not_keyword
class Static:
    VELUN_AUTO_KEYWORDS = False
    @keyword('Exposed', tags=['library-tag'])
    def operation(self, value: int=7):
        """Provider documentation."""
        return value + 1
    @not_keyword
    def hidden(self): return 'hidden operation executed'
    def ordinary(self): return 'undecorated operation executed'
'''
    hybrid = '''class Hybrid:
    def get_keyword_names(self): return ['Exposed']
    def Exposed(self, value: int=7):
        """Provider documentation."""
        return value + 1
    Exposed.velun_tags = ['library-tag']
    def hidden(self): return 'hidden operation executed'
'''
    dynamic = '''class Dynamic:
    def get_keyword_names(self): return ['Exposed']
    def get_keyword_arguments(self, name): return ['value=7']
    def get_keyword_documentation(self, name): return 'Provider documentation.'
    def get_keyword_tags(self, name): return ['library-tag']
    def get_keyword_types(self, name): return {'value': int}
    def run_keyword(self, name, args, kwargs):
        assert name == 'Exposed'
        value = args[0] if args else kwargs.get('value', 7)
        assert type(value) is int
        return value + 1
    def hidden(self): return 'hidden operation executed'
'''
    # Hidden operations return normally, so only refusal (not a raising call) fails their cases.
    # Automatic exposure is on here, so only the explicit marker can hide 'concealed'.
    plain = '''from velun.api.deco import not_keyword
def visible(): return 'visible'
@not_keyword
def concealed(): return 'hidden operation executed'
'''
    libraries = f'Library    {write_file(tmp_path / "Plain.py", plain)}\n'
    body = "    ${v}=    Plain.Visible\n    Check    ${v}    'visible'\n"
    bad = ['Plain.Concealed', 'Dynamic.Exposed    1    2']
    for name, source in [('Static', static), ('Hybrid', hybrid), ('Dynamic', dynamic)]:
        path = write_file(tmp_path / (name + '.py'), source)
        libraries += f'Library    {path}\n'
        body += (f'    ${{v}}=    {name}.Exposed    12\n    Check    ${{v}}    13\n    ${{v}}=    {name}.Exposed\n    Check    ${{v}}    8\n'
                 f'    ${{v}}=    {name}.Exposed    value=20\n    Check    ${{v}}    21\n')
        bad.append(f'{name}.Hidden')
        doc = call_public(LibraryDocumentation, str(path)).value
        assert {k.name for k in doc.keywords} == {'Exposed'}
        keyword = doc.keywords[0]
        assert keyword.doc == 'Provider documentation.'
        assert set(keyword.tags) == {'library-tag'}
        args = list(keyword.args)
        assert len(args) == 1 and args[0].name == 'value'
        assert args[0].default_repr == '7'
        assert args[0].type.name == 'int'
    bad.append('Static.Ordinary')
    library_run(tmp_path, body, libraries=libraries, extra_tests=rejection_cases(bad), failures=rejected_names(bad))


def test_declared_argument_binding_and_errors(tmp_path):
    write_file(tmp_path / 'Binding.py', '''from velun.api.deco import keyword
@keyword(types=None)
def bind(first, /, second='default', *rest, required, optional='opt', **extra):
    return [first, second, list(rest), required, optional, extra]
@keyword(types=None)
def strict(first, second='default'): return [first, second]
@keyword(types=None)
def narrow(first, *, required): return [first, required]
@keyword(types=None)
def gap(a='A', b='B', c='C'): return [a, b, c]
''')
    bad = ['Bind    x', 'Strict', 'Strict    a    b    first=c', 'Strict    a    b    c', 'Strict    a    first=c',
           'Narrow    a    required=b    other=c',
           'Strict    first=a    b', 'Strict    a    second=b    unknown=c',
           'Strict    first=a    SECOND=b', 'Strict    first=a    sec ond=b',
           'Bind    @{EMPTY}    required=y']
    library_run(tmp_path, '''    ${v}=    Bind    one    required=need
    Check    ${v}    ['one', 'default', [], 'need', 'opt', {}]
    ${v}=    Bind    one    two    three    four    required=need    optional=chosen    custom=value
    Check    ${v}    ['one', 'two', ['three', 'four'], 'need', 'chosen', {'custom': 'value'}]
    ${v}=    Bind    one    second=two    required=need
    Check    ${v}    ['one', 'two', [], 'need', 'opt', {}]
    ${v}=    Bind    first=x    required=need
    Check    ${v}    ['first=x', 'default', [], 'need', 'opt', {}]
    ${v}=    Strict    unmatched=value
    Check    ${v}    ['unmatched=value', 'default']
    ${v}=    Strict    first=chosen    second=tail
    Check    ${v}    ['chosen', 'tail']
    ${v}=    Strict    a    second=x=y
    Check    ${v}    ['a', 'x=y']
    ${v}=    Narrow    a    required=b
    Check    ${v}    ['a', 'b']
    ${v}=    Gap    c=z
    Check    ${v}    ['A', 'B', 'z']
''', libraries='Library    Binding.py\n', extra_tests=rejection_cases(bad), failures=rejected_names(bad))


def test_explicit_types_nested_members_typed_dict_and_custom(tmp_path):
    specs = [('int', '23', '23'), ('float', '2.5', '2.5'), ('Decimal', '2.50', "Decimal('2.50')"),
             ('bool', 'yes', 'True'), ('str', '${23}', "'23'"), ('bytes', 'Aÿ', 'bytes([65, 255])'),
             ('bytearray', 'ab', "bytearray(b'ab')"), ('list[int]', "['2', 3]", '[2, 3]'),
             ('tuple[int, str]', "['2', 3]", "(2, '3')"), ('Sequence[int]', "['2', 3]", '[2, 3]'),
             ('set[int]', "['2', 3]", '{2, 3}'), ('frozenset[int]', "['2', 3]", 'frozenset({2, 3})'),
             ('dict[int, list[float]]', "{'2': ['3.5']}", '{2: [3.5]}'),
             ('Mapping[str, int]', "{'key': '2'}", "{'key': 2}"),
             ('Path', 'folder/file', "Path('folder/file')"), ('date', '2025-04-06', 'date(2025, 4, 6)'),
             ('datetime', '2025-04-06 07:08:09', 'datetime(2025, 4, 6, 7, 8, 9)'),
             ('timedelta', '2 minutes', 'timedelta(seconds=120)'), ('None', 'none', 'None'),
             ('int | float', '2.5', '2.5'), ('int | float', '23', '23'), ('bool', 'off', 'False'), ("Literal['red', 'blue']", 'BLUE', "'blue'")]
    source = TYPED_LIBRARY
    body = ''
    for i, (kind, value, expected) in enumerate(specs):
        source += f'\n@keyword\ndef convert_{i}(value: {kind}): return value\n'
        body += f'    ${{v}}=    Convert {i}    {value}\n    Check    ${{v}}    {expected}\n'
    write_file(tmp_path / 'Typed.py', source)
    body += '''    ${v}=    Typed Options    {'count': '3', 'label': 17}
    Check    ${v}    {'count': 3, 'label': '17'}
    ${v}=    Typed Options    {'count': '4'}
    Check    ${v}    {'count': 4}
    ${v}=    Token Value    token:accepted
    Check    ${v}    'accepted'
    ${original}=    Evaluate    object()
    ${v}=    Arbitrary    ${original}
    Same    ${v}    ${original}
    ${v}=    Anything    ${original}
    Same    ${v}    ${original}
'''
    bad = ['Convert 0    invalid', 'Convert 1    invalid', "Convert 7    ['bad']", "Convert 12    {'key': ['bad']}",
           "Typed Options    {'label': 'missing'}", "Typed Options    {'count': 2, 'unknown': 3}",
           'Token Value    invalid']
    library_run(tmp_path, body, libraries='Library    Typed.py\n', extra_tests=rejection_cases(bad), failures=rejected_names(bad))


def test_inferred_alternative_disabled_and_preserved_conversion(tmp_path):
    write_file(tmp_path / 'Typed.py', TYPED_LIBRARY)
    bad = ['Numeric Alternative    not-numeric']
    library_run(tmp_path, '''    ${original}=    Evaluate    [1, 2]
    ${v}=    Retained    ${original}
    Same    ${v}    ${original}
    ${v}=    Inferred    3.25
    Check    ${v}    3.25
    ${v}=    Inferred    7
    Check    ${v}    7
    ${v}=    Inferred    not-numeric
    Check    ${v}    'not-numeric'
    ${v}=    Alternative    true
    Check    ${v}    True
    ${v}=    Numeric Alternative    3.25
    Check    ${v}    3.25
    ${v}=    Alternative    9
    Check    ${v}    9
    ${v}=    Disabled    12
    Check    ${v}    '12'
    ${v}=    Inferred
    Check    ${v}    1
''', libraries='Library    Typed.py\n', extra_tests=rejection_cases(bad), failures=rejected_names(bad))


def test_library_state_scopes_and_initialized_aliases(tmp_path):
    tree = tmp_path / 'tree'
    for name, scope in [('Isolated', ''), ('SuiteState', 'SUITE'), ('GlobalState', 'GLOBAL')]:
        declaration = f"    VELUN_LIBRARY_SCOPE = '{scope}'\n" if scope else ''
        write_file(tree / (name + '.py'), 'class ' + name + ':\n' + declaration + '''    def __init__(self, initial=0): self.value = int(initial)
    def advance(self):
        self.value += 1
        return self.value
''')
    write_file(tree / 'ModuleState.py', 'value = 0\ndef advance():\n    global value\n    value += 1\n    return value\n')
    write_file(tree / 'Witness.py', WITNESS)
    for suite_index in range(2):
        text = '''*** Settings ***
Library    Witness.py
Library    Isolated
Library    SuiteState
Library    GlobalState
Library    ModuleState
Library    SuiteState    30    WITH NAME    Other
Library    Isolated    50    WITH NAME    Fifty
*** Test Cases ***
'''
        for test_index in range(2):
            text += f'Case {suite_index} {test_index}\n'
            for alias, value in [('Isolated', 1), ('SuiteState', test_index + 1),
                                 ('GlobalState', suite_index * 2 + test_index + 1),
                                 ('ModuleState', suite_index * 2 + test_index + 1), ('Other', test_index + 31),
                                 ('Fifty', 51)]:
                text += f'    ${{v}}=    {alias}.Advance\n    Check    ${{v}}    {value}\n'
        write_file(tree / f'{suite_index}.velun', text)
    process, root = execute_source(tree, tmp_path, '--pythonpath', str(tree))
    library_outcomes(process, root, {f'Case {i} {j}': 'PASS' for i in range(2) for j in range(2)})
    from _helpers import json_messages
    assert json_messages([m.text or '' for m in root.findall('.//msg')], prefix='F02_CHECK:') == [{'checked': True}] * 24


def test_remote_discovery_execution_logs_and_outcomes(tmp_path):
    with keyword_service() as (service, uri):
        # Declared discovery metadata must govern the call, not a catch-all signature.
        information = service.get_library_information
        service.get_library_information = lambda: {**information(), 'Mapping': {'args': ['first', 'second=fallback'], 'doc': 'Declared.'}}
        write_file(tmp_path / 'Witness.py', WITNESS)
        source = write_file(tmp_path / 'remote.velun', f'''*** Settings ***
Library    Remote    {uri}    WITH NAME    Service
Library    Witness.py
*** Test Cases ***
Working
    ${{v}}=    Service.Combine    left-    suffix=right
    Check    ${{v}}    'left-right'
    Service.Echo    when=${{{{datetime.date(2025, 4, 6)}}}}    empty=${{None}}    span=${{{{datetime.timedelta(seconds=1.5)}}}}
    Service.Mapping    one    two
Declared Too Few
    Service.Mapping
Declared Too Many
    Service.Mapping    one    two    three
Ordinary
    Service.Ordinary
    Log    ordinary tail
Continuable
    Service.Continuable
    Log    continuable tail
Fatal
    Service.Fatal
    Log    fatal tail
After Fatal
    Service.Combine    forbidden    suffix=tail
''')
        process, root = execute_source(source, tmp_path)
        library_outcomes(process, root, {'Working': 'PASS', 'Declared Too Few': 'FAIL', 'Declared Too Many': 'FAIL', 'Ordinary': 'FAIL', 'Continuable': 'FAIL', 'Fatal': 'FAIL', 'After Fatal': 'FAIL'})
        cases = {c.attrib['name']: c for c in root.findall('.//test')}
        for name, tail in [('Ordinary', 'NOT RUN'), ('Continuable', 'PASS'), ('Fatal', 'NOT RUN')]:
            assert keyword_calls(cases[name], 'Log')[0].find('status').attrib['status'] == tail
            assert 'service failure: ' + name in cases[name].find('status').text
        assert service.calls == [('Combine', ['left-'], {'suffix': 'right'}),
                                 ('Echo', [], {'when': datetime.datetime(2025, 4, 6), 'empty': '', 'span': 1.5}),
                                 ('Mapping', ['one', 'two'], {}), ('Ordinary', [], {}),
                                 ('Continuable', [], {}), ('Fatal', [], {})]
        assert 'service executed Combine' in [m.text for m in root.findall('.//msg')]
        assert keyword_calls(cases['Working'], 'Check')[0].find('status').attrib['status'] == 'PASS'


def test_remote_timeouts_unavailable_and_malformed_results(tmp_path):
    import pytest
    import time
    from threading import Event
    from velun.libraries.Remote import Remote
    with keyword_service() as (service, uri):
        client = call_public(Remote, uri, '3 seconds').value
        assert set(call_public(client.get_keyword_names).value) == set(service.get_library_information())
        assert call_public(client.run_keyword, 'Delay', ['0.8'], {}).value == 'completed delayed operation'
        for explicit in (True, False):
            old = socket.getdefaulttimeout()
            try:
                socket.setdefaulttimeout(.15 if not explicit else None)
                client = call_public(Remote, uri, '.15 seconds' if explicit else None).value
                call_public(client.get_keyword_names)
                entered, release = Event(), Event()
                service.delay_gate = entered, release
                try:
                    started = time.monotonic()
                    with pytest.raises(RuntimeError):
                        call_public(client.run_keyword, 'Delay', ['0.8'], {})
                    elapsed = time.monotonic() - started
                    assert entered.wait(10), 'The peer must receive the timed operation.'
                    assert elapsed >= .12
                finally:
                    release.set()
                    service.delay_gate = None
            finally:
                socket.setdefaulttimeout(old)
        # A caller-selected timeout is not displaced by a shorter host default.
        old = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(.15)
            client = call_public(Remote, uri, '3 seconds').value
            assert call_public(client.run_keyword, 'Delay', ['0.8'], {}).value == 'completed delayed operation'
        finally:
            socket.setdefaulttimeout(old)
        assert [c[0] for c in service.calls] == ['Delay'] * 4
        client = call_public(Remote, uri).value
        for shape in ([], ['missing-status']):
            with pytest.raises(RuntimeError):
                call_public(client.run_keyword, 'Malformed', shape, {})
        library_run(tmp_path / 'malformed', "    Check    ${1}    1\n", libraries=f'Library    Remote    {uri}\n',
                    extra_tests='Malformed\n    Remote.Malformed\n', failures=['Malformed'])
        with socket.socket() as unavailable:
            unavailable.bind(('127.0.0.1', 0))
            address = 'http://127.0.0.1:' + str(unavailable.getsockname()[1])
            process, root = library_run(tmp_path / 'unavailable', '    Check    ${1}    1\n',
                libraries=f'Library    Remote    {address}    timeout=.15 seconds\n',
                extra_tests='Unavailable\n    Remote.Echo    value\n', failures=['Unavailable'])
            assert any(m.attrib['level'] == 'ERROR' and address in (m.text or '') for m in root.findall('./errors/msg'))
            assert address.encode() in process.stderr


def test_remote_transport_value_kinds_and_integer_bounds(tmp_path):
    write_file(tmp_path / 'Values.py', '''from datetime import date, datetime, timedelta
class TextObject:
    def __str__(self): return 'object-as-text'
def values():
    return ['plain text', -2147483648, 2147483647, 1.25, True, False,
            b'\\x00\\xff', bytearray(b'ab'), datetime(2025, 4, 6, 7, 8, 9),
            date(2025, 4, 6), timedelta(seconds=62.5), None, (1, None),
            {7: [None, (2, 3)]}, TextObject(), range(2), {5},
            [date(2025, 4, 6), timedelta(seconds=1.5), TextObject()],
            {'when': date(2025, 4, 6), 'span': timedelta(seconds=1.5), 'object': TextObject()}]
''')
    with keyword_service() as (service, uri):
        bad = ['Remote.Echo    ${2147483648}', 'Remote.Echo    ${-2147483649}', 'Remote.Echo    ${{[2147483648]}}',
               "Remote.Echo    ${{{'key': -2147483649}}}", 'Remote.Echo    named=${2147483648}']
        library_run(tmp_path, '''    ${values}=    Values.Values
    ${returned}=    Remote.Echo    @{values}
    Check    ${returned}[0]    'plain text'
    Check    ${returned}[1]    -2147483648
    Check    ${returned}[2]    2147483647
    Check    ${returned}[3]    1.25
    Check    ${returned}[4]    True
    Check    ${returned}[5]    False
    Check    ${returned}[6]    bytes([0, 255])
    Check    ${returned}[7]    b'ab'
    Check    ${returned}[8]    datetime(2025, 4, 6, 7, 8, 9)
    Check    ${returned}[9]    datetime(2025, 4, 6)
    Check    ${returned}[10]    62.5
    Check    ${returned}[11]    ''
    Check    ${returned}[12]    [1, '']
    Check    ${returned}[13]    {'7': ['', [2, 3]]}
    Check    ${returned}[14]    'object-as-text'
    Check    ${returned}[15]    [0, 1]
    Check    ${returned}[16]    [5]
    Check    ${returned}[17]    [datetime(2025, 4, 6), 1.5, 'object-as-text']
    Check    ${returned}[18]    {'when': datetime(2025, 4, 6), 'span': 1.5, 'object': 'object-as-text'}
''', libraries=f'Library    Values.py\nLibrary    Remote    {uri}\n',
                    extra_tests=rejection_cases(bad), failures=rejected_names(bad))
        expected = ['plain text', -2147483648, 2147483647, 1.25, True, False, bytes([0, 255]), b'ab',
                    datetime.datetime(2025, 4, 6, 7, 8, 9), datetime.datetime(2025, 4, 6),
                    62.5, '', [1, ''], {'7': ['', [2, 3]]}, 'object-as-text', [0, 1], [5],
                    [datetime.datetime(2025, 4, 6), 1.5, 'object-as-text'],
                    {'when': datetime.datetime(2025, 4, 6), 'span': 1.5, 'object': 'object-as-text'}]
        assert len(service.calls) == 1
        assert service.calls[0][0] == 'Echo' and service.calls[0][2] == {}
        actual = service.calls[0][1]
        assert len(actual) == len(expected)
        for got, wanted in zip(actual, expected):
            assert type(got) is type(wanted) and got == wanted, (got, wanted)


def test_remote_control_text_binary_and_mapping_access(tmp_path):
    write_file(tmp_path / 'Controls.py', '''def controls():
    return ['x' + chr(n) + 'ÿ' for n in range(32) if n not in (9, 10, 13)]
def text(): return 'text' + chr(9) + 'line' + chr(10) + 'return' + chr(127) + chr(150) + chr(8364)
def carriage(): return 'a' + chr(13) + 'b'
''')
    with keyword_service() as (service, uri):
        bad = ['Remote.Echo    ${{chr(0) + chr(8364)}}', "Remote.Echo    ${{{chr(0): 'value'}}}"]
        library_run(tmp_path, '''    ${values}=    Controls.Controls
    ${v}=    Remote.Echo    @{values}
    ${binary}=    Remote.Binary
    Check    ${binary}    bytes([0, 65, 255])
    ${mapping}=    Remote.Mapping
    Check    ${mapping}[outer][data]    bytes([0, 255])
    Check    ${mapping.outer.data}    bytes([0, 255])
    Check    ${mapping}[records][0][value]    7
    Check    ${mapping.records[0].value}    7
    ${plain}=    Controls.Text
    ${v}=    Remote.Echo    ${plain}
    Check    ${v}    ['text' + chr(9) + 'line' + chr(10) + 'return' + chr(127) + chr(150) + chr(8364)]
    ${v}=    Remote.Echo    ${{['x' + chr(1) + 'y']}}    ${{{'key': 'x' + chr(2) + 'y'}}}
    ${carriage}=    Controls.Carriage
    ${v}=    Remote.Echo    ${carriage}
''', libraries=f'Library    Controls.py\nLibrary    Remote    {uri}\n',
                    extra_tests=rejection_cases(bad), failures=rejected_names(bad))
        assert [c[0] for c in service.calls] == ['Echo', 'Binary', 'Mapping', 'Echo', 'Echo', 'Echo']
        expected = [bytes([120, n, 255]) for n in range(32) if n not in (9, 10, 13)]
        assert service.calls[0][1] == expected
        assert all(type(v) is bytes for v in service.calls[0][1])
        # Only ordinals 0-31 (other than tab, line feed, carriage return) select binary transport.
        assert service.calls[3][1] == ['text\tline\nreturn\x7f\x96\u20ac']
        assert type(service.calls[3][1][0]) is str
        # Collection members and mapping values undergo the same classification.
        assert service.calls[4][1] == [[b'x\x01y'], {'key': b'x\x02y'}]
        assert type(service.calls[4][1][0][0]) is bytes and type(service.calls[4][1][1]['key']) is bytes
        # A carriage return does not select binary; XML transport may normalize its line ending.
        assert type(service.calls[5][1][0]) is str


def test_enum_literal_secret_binding_and_ambiguity(tmp_path):
    write_file(tmp_path / 'Typed.py', TYPED_LIBRARY)
    body = '''    ${v}=    Enum Value    Exact
    Check    ${v}    'Exact'
    ${v}=    Enum Value    EXACT
    Check    ${v}    'EXACT'
    ${v}=    Enum Value    bLuE-sKy
    Check    ${v}    'Blue_Sky'
    ${member}=    Enum Member
    ${v}=    Enum Value    ${member}
    Check    ${v}    'Blue_Sky'
    ${v}=    Integer Enum    ${4}
    Check    ${v}    'LOW'
    ${v}=    Integer Enum    high
    Check    ${v}    'HIGH'
    ${v}=    Integer Enum    9
    Check    ${v}    'HIGH'
    ${v}=    Literal Value    Exact
    Check    ${v}    'Exact'
    ${v}=    Literal Value    EXACT
    Check    ${v}    'EXACT'
    ${v}=    Literal Value    blue sky
    Check    ${v}    'Blue_Sky'
    ${v}=    Literal Value    4
    Check    ${v}    4
    ${v}=    Literal Value    ${False}
    Check    ${v}    False
    ${v}=    Ambiguous Literal    1
    Check    ${v}    '1'
    ${v}=    Ambiguous Literal    ${1}
    Check    ${v}    1
    ${secret}=    Make Secret    protected value
    ${v}=    Secret Value    ${secret}
    Check    ${v}    'protected value'
'''
    bad = ['Enum Value    eXaCt', 'Enum Value    missing', 'Enum Value    1', 'Integer Enum    ${3}',
           'Literal Value    eXaCt', 'Literal Value    missing', 'Secret Value    protected value']
    library_run(tmp_path, body, libraries='Library    Typed.py\n', extra_tests=rejection_cases(bad), failures=rejected_names(bad))


def test_refresh_keywords_arguments_documentation_by_name_and_object(tmp_path):
    write_file(tmp_path / 'Changing.py', '''class Changing:
    VELUN_LIBRARY_SCOPE = 'GLOBAL'
    def __init__(self): self.changed = False
    def get_keyword_names(self):
        return ['Change', 'Current', 'Added'] if self.changed else ['Change', 'Current', 'Removed']
    def get_keyword_arguments(self, name):
        return ['first', 'second'] if name == 'Current' and self.changed else (['first'] if name == 'Current' else [])
    def get_keyword_documentation(self, name):
        return 'Updated provider documentation.' if self.changed else 'Original provider documentation.'
    def run_keyword(self, name, args):
        if name == 'Change': self.changed = True
        elif name == 'Current': return list(args)
        elif name == 'Added': return 'new operation'
        elif name == 'Removed': return 'old operation'
        else: raise ValueError(name)
''')
    for by_object in (False, True):
        directory = tmp_path / str(by_object)
        write_file(directory / 'Changing.py', (tmp_path / 'Changing.py').read_text())
        selector = '${instance}' if by_object else 'Changing'
        body = '''    ${v}=    Current    old
    Check    ${v}    ['old']
    ${v}=    Removed
    Check    ${v}    'old operation'
    ${instance}=    Get Library Instance    Changing
    Change
    Reload Library    SELECTOR
    ${v}=    Current    new    declaration
    Check    ${v}    ['new', 'declaration']
    ${v}=    Added
    Check    ${v}    'new operation'
'''.replace('SELECTOR', selector)
        bad = ['Current    too-few', 'Removed', 'Reload Library    MissingF03Library']
        process, root = library_run(directory, body, libraries='Library    Changing.py\n',
            extra_tests=rejection_cases(bad), failures=rejected_names(bad))
        current = keyword_calls(root.find(".//test[@name='Working']"), 'Current')
        assert [k.find('doc').text for k in current] == ['Original provider documentation.', 'Updated provider documentation.']
        assert 'MissingF03Library' in root.find(".//test[@name='Invalid 2']/status").text
