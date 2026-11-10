# feature: F01
"""Acceptance observations for source parsing and executable suite construction."""
import ast
import json
import re
from io import StringIO

import pytest
from velun.api import TestSuite as Suite, TestSuiteBuilder as Builder
from velun.api.parsing import get_model, get_init_model, get_tokens, Token, ModelVisitor, TestCase as SyntaxTestCase
from velun.errors import DataError

from _helpers import call_public, write_file, run_module
from F01_helpers import (syntax_errors, execute_suite, execute_source, leaf_suites,
                         native_case, LANGUAGE_INPUTS)


def _reports_location(stderr, path, line):
    """Some [ ERROR ] line names the source path and, apart from it, the line number."""
    for text in stderr.decode(errors="replace").splitlines():
        if "[ ERROR ]" in text and str(path) in text:
            if re.search(rf"(?<!\d){line}(?!\d)", text.replace(str(path), " ")):
                return True
    return False


def test_supported_source_formats(tmp_path):
    text = '''*** Settings ***
Documentation    A transport document
Metadata    Owner    Research
Test Tags    transport
*** Tasks ***
Carry parcel
    [Documentation]    A declared task
    [Tags]    fragile
    Deliver    blue crate
*** Keywords ***
Deliver
    [Arguments]    ${item}
    Should Be Equal    ${item}    blue crate
'''
    # JSON is independent caller-created suite data, not an encode/decode oracle.
    data = {"name": "Parcel", "doc": "A transport document", "rpa": True,
            "metadata": {"Owner": "Research"},
            "tests": [{"name": "Carry parcel", "doc": "A declared task",
                       "tags": ["transport", "fragile"],
                       "body": [{"name": "Deliver", "args": ["blue crate"]}]}],
            "resource": {"keywords": [{"name": "Deliver", "args": ["${item}"],
                         "body": [{"name": "Should Be Equal",
                                   "args": ["${item}", "blue crate"]}]}]}}
    # Embedded documents split the data over two automation blocks separated by
    # prose and followed by a non-automation code block whose rows must not count.
    head, tail = text.split("*** Keywords ***\n")
    tail = "*** Keywords ***\n" + tail
    foreign = "Prose Keyword\n    Fail    prose executed\n"

    def rst_block(language, body):
        return f".. code:: {language}\n\n" + ''.join('    ' + line + '\n'
                                                     for line in body.splitlines()) + "\n"

    sources = {"parcel.velun": text,
               "parcel.velun.rst": "Prose outside the block.\n\n" + rst_block("velunexsuite", head) +
               "Prose between blocks.\n\n" + rst_block("velunexsuite", tail) +
               rst_block("python", foreign) + 'More prose.\n',
               "parcel.velun.md": "# Narrative\n\n```velunexsuite\n" + head +
               "```\n\nProse between blocks.\n\n```velunexsuite\n" + tail +
               "```\n\n```python\n" + foreign + "```\n\nThis is not a keyword call.\n",
               "parcel.rbt": json.dumps(data)}
    for filename, content in sources.items():
        suite = Suite.from_file_system(write_file(tmp_path / filename, content))
        assert suite.rpa is True
        assert suite.doc == "A transport document"
        assert dict(suite.metadata) == {"Owner": "Research"}
        assert [t.name for t in suite.tests] == ["Carry parcel"]
        test = suite.tests[0]
        assert test.doc == "A declared task"
        assert set(test.tags) == {"transport", "fragile"}
        assert [(k.name, tuple(k.args)) for k in test.body] == [("Deliver", ("blue crate",))]
        assert [k.name for k in suite.resource.keywords] == ["Deliver"]
        assert [(k.name, tuple(k.args)) for k in suite.resource.keywords[0].body] == [
            ("Should Be Equal", ("${item}", "blue crate"))]
        assert execute_suite(suite).tests[0].status == "PASS"


def test_table_separation_escaping_continuation_comments(tmp_path):
    text = r'''*** Test Cases ***
Spaces
    # Fail    comments must not execute
    Should Be Equal    one two    one two    # trailing comment
    Should Be Equal    first\ second
    ...    first second
    Should Be Equal    \#literal    \#literal
    Should Be Equal    a\\b    a\\b
| Pipes |
| | Should Be Equal | a\|b | a\|b | # ignored |
| | Should Be Equal | two  spaces | two  spaces |
'''
    library = write_file(tmp_path / "LiteralWitness.py", r'''def literal_hash(value):
    assert value == "#literal", repr(value)
def literal_slash(value):
    assert value == "a\\b", repr(value)
def literal_pipe(value):
    assert value == "a|b", repr(value)
''')
    text += r"| | Literal Pipe | a\|b |" + "\n"
    text = "*** Settings ***\nLibrary    " + str(library) + "\n" + text
    text = text.replace(r"    Should Be Equal    \#literal    \#literal",
                        r"    Literal Hash    \#literal")
    text = text.replace(r"    Should Be Equal    a\\b    a\\b",
                        r"    Literal Slash    a\\b")
    model = get_model(StringIO(text))
    assert syntax_errors(model) == []
    suite = Suite.from_model(model)
    assert [t.name for t in suite.tests] == ["Spaces", "Pipes"]
    assert [tuple(k.args) for k in suite.tests[0].body] == [
        ("one two", "one two"), (r"first\ second", "first second"),
        (r"\#literal",), (r"a\\b",)]
    assert [tuple(k.args) for k in suite.tests[1].body] == [
        (r"a\|b", r"a\|b"), ("two  spaces", "two  spaces"), (r"a\|b",)]
    assert [t.status for t in execute_suite(suite).tests] == ["PASS", "PASS"]


def test_discovery_selection_and_hierarchy(tmp_path):
    root = tmp_path / "collection"
    write_file(root / "__init__.velun", "*** Settings ***\nDocumentation    Directory description\n")
    write_file(root / "alpha.velun", native_case("Alpha"))
    write_file(root / "nested" / "beta.velun.md", "```velunexsuite\n" + native_case("Beta") + "```\n")
    write_file(root / "gamma.velun.rst", ".. code:: velunexsuite\n\n" + ''.join(
        '    ' + line + '\n' for line in native_case("Gamma").splitlines()))
    write_file(root / "delta.rbt", json.dumps({"name": "Delta", "tests": [
        {"name": "Delta", "body": [{"name": "No Operation"}]}]}))
    for name in (".secret.velun", "_private.velun", ".hidden/inside.velun", "_skip/inside.velun"):
        write_file(root / name, native_case("Excluded"))
    write_file(root / "empty.velun", "*** Settings ***\nDocumentation    No tests\n")
    write_file(root / "extra.txt", native_case("Extended"))
    write_file(root / "custom.parcel", "Custom delivery")

    class ParcelParser:
        extension = "parcel"

        def parse(self, source, defaults):
            suite = Suite(name="Custom")
            suite.tests.create(name=source.read_text()).body.create_keyword("No Operation")
            return suite

    suite = Builder(custom_parsers=[ParcelParser()]).build(root)
    assert suite.doc == "Directory description"
    assert {t.name for s in leaf_suites(suite) for t in s.tests} == {
        "Alpha", "Beta", "Gamma", "Delta", "Custom delivery"}
    def every_suite(node):
        yield node
        for child in node.suites:
            yield from every_suite(child)
    # Sources without tests or tasks (empty.velun) are omitted, not kept as empty leaves.
    assert all(s.tests or s.suites for s in every_suite(suite))
    assert len(suite.suites) == 5
    nested = next(s for s in suite.suites
                  if any(t.name == "Beta" for leaf in leaf_suites(s) for t in leaf.tests))
    assert [t.name for t in nested.suites[0].tests] == ["Beta"]
    restricted = Builder(included_extensions=["velun"]).build(root)
    assert [t.name for s in leaf_suites(restricted) for t in s.tests] == ["Alpha"]
    extended = Builder(included_extensions=["velun", "txt"]).build(root)
    assert {t.name for s in leaf_suites(extended) for t in s.tests} == {"Alpha", "Extended"}
    explicit = Builder().build(root / ".secret.velun")
    assert [t.name for t in explicit.tests] == ["Excluded"]
    multi = Builder().build(root / "alpha.velun", root / "nested" / "beta.velun.md")
    assert len(multi.suites) == 2
    assert {t.name for s in multi.suites for t in s.tests} == {"Alpha", "Beta"}


def test_directory_defaults_and_scope(tmp_path):
    root = tmp_path / "tree"
    write_file(root / "__init__.velun", '''*** Settings ***
Documentation    Root description
Metadata    Team    Root team
Suite Setup    Log    root-open
Suite Teardown    Log    root-close
Test Setup    Log    inherited-open
Test Teardown    Log    inherited-close
Test Timeout    2 minutes
Test Tags    root-tag    removable
*** Variables ***
${PRIVATE_VALUE}    root-only
*** Keywords ***
Private Action
    No Operation
''')
    write_file(root / "direct.velun", native_case("Inherited"))
    write_file(root / "branch" / "__init__.velun", '''*** Settings ***
Test Setup    Log    branch-open
Test Teardown    NONE
Test Timeout    3 minutes
Test Tags    branch-tag
''')
    write_file(root / "branch" / "child.velun", '''*** Test Cases ***
Overridden
    [Tags]    -removable    own
    No Operation
Disabled
    [Setup]    NONE
    No Operation
Private variable
    Log    ${PRIVATE_VALUE}
Private keyword
    Private Action
''')
    # Inheritance across more than one directory level: a directory without own
    # defaults keeps the root ones; a grandchild accumulates tags of every level and
    # keeps the nearest overriding setup, disabled teardown and replacing timeout.
    write_file(root / "plain" / "inner" / "leaf.velun", native_case("Deep default"))
    write_file(root / "branch" / "deeper" / "__init__.velun",
               "*** Settings ***\nTest Tags    deeper-tag\n")
    write_file(root / "branch" / "deeper" / "grand.velun", native_case("Grandchild"))
    suite = Builder().build(root)
    assert suite.doc == "Root description"
    assert dict(suite.metadata) == {"Team": "Root team"}
    observed = {t.name: t for s in leaf_suites(suite) for t in s.tests}
    assert observed["Inherited"].setup.args == ("inherited-open",)
    assert observed["Inherited"].teardown.args == ("inherited-close",)
    assert observed["Inherited"].timeout == "2 minutes"
    assert observed["Overridden"].setup.args == ("branch-open",)
    assert observed["Overridden"].timeout == "3 minutes"
    assert set(observed["Overridden"].tags) == {"root-tag", "branch-tag", "own"}
    assert set(observed["Inherited"].tags) == {"root-tag", "removable"}
    assert observed["Deep default"].setup.args == ("inherited-open",)
    assert observed["Deep default"].teardown.args == ("inherited-close",)
    assert observed["Deep default"].timeout == "2 minutes"
    assert set(observed["Deep default"].tags) == {"root-tag", "removable"}
    assert observed["Grandchild"].setup.args == ("branch-open",)
    assert observed["Grandchild"].timeout == "3 minutes"
    assert set(observed["Grandchild"].tags) == {"root-tag", "removable", "branch-tag",
                                                "deeper-tag"}
    process, xml = execute_source(root, tmp_path)
    assert process.returncode == 2, process.stderr
    results = {t.attrib["name"]: t for t in xml.findall('.//test')}
    assert {n: t.find('status').attrib['status'] for n, t in results.items()} == {
        "Inherited": "PASS", "Overridden": "PASS", "Disabled": "PASS",
        "Private variable": "FAIL", "Private keyword": "FAIL",
        "Deep default": "PASS", "Grandchild": "PASS"}
    assert results["Deep default"].find('./kw[@type="SETUP"]/msg').text == "inherited-open"
    assert results["Grandchild"].find('./kw[@type="SETUP"]/msg').text == "branch-open"
    assert results["Grandchild"].find('./kw[@type="TEARDOWN"]') is None
    assert results["Disabled"].find('./kw[@type="SETUP"]') is None
    assert results["Overridden"].find('./kw[@type="TEARDOWN"]') is None
    assert xml.find('./suite/kw[@type="SETUP"]/arg').text == "root-open"
    assert xml.find('./suite/kw[@type="TEARDOWN"]/arg').text == "root-close"
    assert results["Overridden"].find('./kw[@type="SETUP"]/arg').text == "branch-open"
    assert results["Inherited"].find('./kw[@type="TEARDOWN"]/arg').text == "inherited-close"
    assert xml.find('./suite/kw[@type="SETUP"]/msg').text == "root-open"
    assert xml.find('./suite/kw[@type="TEARDOWN"]/msg').text == "root-close"
    assert results["Overridden"].find('./kw[@type="SETUP"]/msg').text == "branch-open"
    assert results["Inherited"].find('./kw[@type="SETUP"]/msg').text == "inherited-open"
    assert results["Inherited"].find('./kw[@type="TEARDOWN"]/msg').text == "inherited-close"
    assert "PRIVATE_VALUE" in results["Private variable"].find('status').text
    assert "Private Action" in results["Private keyword"].find('status').text


def test_initialization_rejects_forbidden_declarations(tmp_path):
    root = tmp_path / "initialization"
    path = write_file(root / "__init__.velun", '''*** Settings ***
Documentation    Still readable
Test Template    Forbidden
Default Tags    forbidden
*** Test Cases ***
Forbidden test
    No Operation
''')
    errors = syntax_errors(get_init_model(path))
    assert {line for line, messages in errors} >= {3, 4, 5}
    assert all(messages and all(messages) for _, messages in errors)
    for line, construct in [(3, 'Test Template'), (4, 'Default Tags'), (5, 'Test Cases')]:
        assert any(construct in message for n, messages in errors if n == line
                   for message in messages)
    write_file(root / "child.velun", native_case("Legal"))
    built = call_public(Builder().build, root)
    assert built.value.doc == "Still readable"
    assert [t.name for s in leaf_suites(built.value) for t in s.tests] == ["Legal"]
    process, xml = execute_source(root, tmp_path)
    assert process.returncode == 0, process.stderr
    assert b"[ ERROR ]" in process.stderr
    assert str(path).encode() in process.stderr
    for line in (3, 4, 5):
        assert _reports_location(process.stderr, path, line), process.stderr
    assert xml.find('./suite/suite/test/status').attrib['status'] == 'PASS'
    assert set(built.value.suites[0].tests[0].tags) == set()
    assert built.value.suites[0].tests[0].template is None


def test_located_diagnostics_preserve_valid_content(tmp_path):
    cases = [
        ("*** Unknown Section ***\nvalue\n", 1),
        ("*** Settings ***\nUnknown Setting    value\n", 2),
        ("*** Test Cases ***\nBroken\n    IF\n        No Operation\n    END\n", 3),
        ("*** Tasks ***\nA task\n    No Operation\n", 4),
    ]
    for index, (prefix, line) in enumerate(cases):
        # Mixing tasks follows a test section; the other faults precede it.
        content = native_case("Kept") + prefix if index == 3 else prefix + native_case("Kept")
        path = write_file(tmp_path / f"bad{index}.velun", content)
        model = get_model(path)
        errors = syntax_errors(model)
        if index == 3:
            # The syntax retains both declarations; construction rejects the mode conflict.
            names = [n.name for n in ast.walk(model)
                     if isinstance(n, SyntaxTestCase)]
            assert names == ["Kept", "A task"]
            with pytest.raises(DataError):
                Suite.from_model(model)
            # The conflict is independent of which section comes first.
            with pytest.raises(DataError):
                Suite.from_string(prefix + native_case("Kept"))
            # Each section alone is a valid suite (the rejection is about mixing).
            assert Suite.from_string(prefix).rpa is True
            assert Suite.from_string(native_case("Kept")).rpa is False
            continue
        assert line in {n for n, messages in errors}, errors
        assert str(model.source) == str(path)
        assert all(messages and all(messages) for _, messages in errors)
        construct = ["Unknown Section", "Unknown Setting", "IF"][index]
        assert any(construct in message for n, messages in errors if n == line
                   for message in messages)
        observed = call_public(Suite.from_model, model)
        assert "Kept" in [t.name for t in observed.value.tests]
        assert observed.value.tests[[t.name for t in observed.value.tests].index("Kept")].body[0].name == "No Operation"
        process, xml = execute_source(path, tmp_path)
        assert process.returncode == (1 if index == 2 else 0), process.stderr
        kept = next(t for t in xml.findall('./suite/test') if t.attrib['name'] == 'Kept')
        assert kept.find('status').attrib['status'] == 'PASS'
        if index != 2:
            assert b"[ ERROR ]" in process.stderr
            assert str(path).encode() in process.stderr
            assert _reports_location(process.stderr, path, line), process.stderr
        else:
            broken = next(t for t in xml.findall('./suite/test') if t.attrib['name'] == 'Broken')
            assert broken.find('status').attrib['status'] == 'FAIL'
            assert broken.find('status').text


def test_tokens_edit_and_save(tmp_path):
    text = '*** Test Cases ***\nFirst\n    Log    original\nSecond\n    No Operation\n'
    path = write_file(tmp_path / "editable.velun", text)
    tokens = list(get_tokens(path))
    assert [(t.value, t.lineno, t.col_offset) for t in tokens if t.type == Token.KEYWORD] == [
        ("Log", 3, 4), ("No Operation", 5, 4)]
    assert [(t.value, t.lineno, t.col_offset) for t in tokens if t.type == Token.ARGUMENT] == [
        ("original", 3, 11)]
    model = get_model(path)
    assert syntax_errors(model) == []

    class Editor(ModelVisitor):
        def visit_KeywordCall(self, node):
            if node.keyword == "Log":
                node.get_token(Token.ARGUMENT).value = "changed payload"

    Editor().visit(model)
    saved = tmp_path / "saved.velun"
    model.save(saved)
    suite = Suite.from_file_system(saved)
    assert [t.name for t in suite.tests] == ["First", "Second"]
    assert suite.tests[0].body[0].args == ("changed payload",)
    assert suite.tests[1].body[0].name == "No Operation"
    assert [t.status for t in execute_suite(suite).tests] == ["PASS", "PASS"]


def test_suite_construction_and_structured_exchange(tmp_path):
    text = '''*** Settings ***
Documentation    Constructed document
Metadata    Purpose    Exchange
*** Test Cases ***
Constructed
    [Documentation]    Exchanged test
    [Tags]    transfer
    [Setup]    Log    exchange-open
    [Timeout]    1 minute
    Local Check    declared value
*** Keywords ***
Local Check
    [Arguments]    ${value}
    Should Be Equal    ${value}    declared value
'''
    path = write_file(tmp_path / "source.velun", text)
    caller = Suite(name="Caller", doc="Constructed document", metadata={"Purpose": "Exchange"})
    test = caller.tests.create(name="Constructed", tags=["transfer"])
    test.body.create_keyword("Local Check", args=["declared value"])
    keyword = caller.resource.keywords.create(name="Local Check", args=["${value}"])
    keyword.body.create_keyword("Should Be Equal", args=["${value}", "declared value"])
    suites = [Suite.from_string(text), Suite.from_model(get_model(path)),
              Suite.from_file_system(path), caller]
    parent = Suite(name="Parent")
    parent.suites.append(caller)
    # The parsed suite also carries test documentation, setup and timeout that the
    # exchange must keep.
    parent.suites.append(Suite.from_file_system(path))
    data_path = tmp_path / "exchange.rbt"
    parent.to_json(data_path)
    restored = Suite.from_json(data_path)
    assert restored.name == "Parent"
    assert len(restored.suites) == 2
    copied = Suite.from_dict(parent.to_dict())
    declared = [suites[0], suites[1], suites[2], restored.suites[1], copied.suites[1]]
    suites.extend([restored.suites[0], copied.suites[0], restored.suites[1], copied.suites[1]])
    for suite in declared:
        assert suite.tests[0].doc == "Exchanged test"
        assert (suite.tests[0].setup.name, tuple(suite.tests[0].setup.args)) == (
            "Log", ("exchange-open",))
        assert suite.tests[0].timeout == "1 minute"
    for suite in suites:
        assert suite.doc == "Constructed document"
        assert dict(suite.metadata) == {"Purpose": "Exchange"}
        assert [t.name for t in suite.tests] == ["Constructed"]
        assert list(suite.tests[0].tags) == ["transfer"]
        assert [(k.name, tuple(k.args)) for k in suite.tests[0].body] == [
            ("Local Check", ("declared value",))]
        assert [k.name for k in suite.resource.keywords] == ["Local Check"]
        assert [(k.name, tuple(k.args)) for k in suite.resource.keywords[0].body] == [
            ("Should Be Equal", ("${value}", "declared value"))]
        assert execute_suite(suite).tests[0].status == "PASS"


def test_all_builtin_languages(tmp_path):
    library = write_file(tmp_path / "BooleanWitness.py", '''def require_boolean(value: bool, expected: str):
    assert type(value) is bool, repr(value)
    assert value is (expected == "true"), repr(value)
''')
    for language, words in LANGUAGE_INPUTS:
        lines = [f'*** {words["settings_header"]} ***',
                 f'{words["documentation_setting"]}    Local document',
                 f'Library    {library}', f'*** {words["test_cases_header"]} ***',
                 'Localized', f'    [{words["tags_setting"]}]    locale',
                 '    Local Action', '    No Operation']
        for family in ('given_prefixes', 'when_prefixes', 'then_prefixes', 'and_prefixes', 'but_prefixes'):
            lines.extend(f'    {prefix} Local Action' for prefix in words[family])
        for value in words['true_strings']:
            lines.append(f'    Require Boolean    {value}    true')
        for value in words['false_strings']:
            lines.append(f'    Require Boolean    {value}    false')
        lines += [f'*** {words["keywords_header"]} ***', 'Local Action',
                  '    No Operation', '*** Test Cases ***', 'English', '    No Operation']
        text = '\n'.join(lines) + '\n'
        model = get_model(StringIO(text), lang=language)
        assert syntax_errors(model) == [], language
        suite = Suite.from_string(text, lang=language)
        assert suite.doc == 'Local document', language
        assert [t.name for t in suite.tests] == ['Localized', 'English'], language
        assert list(suite.tests[0].tags) == ['locale'], language
        # CLI activation also supplies translated BDD and Boolean vocabulary at runtime.
        source = write_file(tmp_path / 'localized.velun', text)
        process, xml = execute_source(source, tmp_path, '--language', language)
        assert process.returncode == 0, (language, process.stderr, process.stdout)
        assert [t.find('status').attrib['status'] for t in xml.findall('./suite/test')] == ['PASS', 'PASS']
        task = Suite.from_string(f'*** {words["tasks_header"]} ***\nLocalized task\n    No Operation\n', lang=language)
        assert task.rpa is True and task.tests[0].name == 'Localized task', language


def test_custom_language_and_unknown_language(tmp_path):
    language = write_file(tmp_path / 'ParcelLanguage.py', '''from velun.api import Language
class ParcelLanguage(Language):
    settings_header = "Parcel Settings"
    test_cases_header = "Deliveries"
    documentation_setting = "Manifest"
    tags_setting = "Labels"
    given_prefixes = ["Assuming"]
    true_strings = ["affirmed"]
    false_strings = ["denied"]
''')
    library = write_file(tmp_path / 'CustomWitness.py', '''def verify(value: bool, expected: str):
    assert type(value) is bool
    assert value is (expected == 'true')
''')
    source = write_file(tmp_path / 'custom.velun', f'''*** Parcel Settings ***
Manifest    Custom document
Library    {library}
*** Deliveries ***
Delivery
    [Labels]    custom
    Assuming No Operation
    Verify    affirmed    true
    Verify    denied    false
*** Test Cases ***
English still works
    No Operation
''')
    process, xml = execute_source(source, tmp_path, '--language', str(language))
    assert process.returncode == 0, (process.stdout, process.stderr)
    assert xml.find('./suite/doc').text == 'Custom document'
    assert [t.attrib['name'] for t in xml.findall('./suite/test')] == ['Delivery', 'English still works']
    assert [t.find('status').attrib['status'] for t in xml.findall('./suite/test')] == ['PASS', 'PASS']
    unknown = run_module('velun', ['--language', 'UnavailableParcelLanguage', str(source)])
    assert unknown.returncode == 252
    assert b'[ ERROR ]' in unknown.stderr
    assert b'UnavailableParcelLanguage' in unknown.stderr


def test_declarations_overrides_tags_and_empty_body(tmp_path):
    write_file(tmp_path / 'values.py', 'IMPORTED = "from variables"\n')
    write_file(tmp_path / 'actions.resource', '*** Keywords ***\nResource Action\n    No Operation\n')
    source = write_file(tmp_path / 'declarations.velun', '''*** Settings ***
Name    Declared identity
Documentation    Suite document
Metadata    Team    Data team
Library    Collections
Resource    actions.resource
Variables    values.py
Suite Setup    Log    suite-open
Suite Teardown    Log    suite-close
Test Setup    Log    default-open
Test Teardown    Log    default-close
Test Timeout    1 minute
Test Template    Check Pair
Test Tags    Common_Tag    common tag    COMMON_TAG
Default Tags    default-only
*** Variables ***
${LOCAL}    from data
*** Test Cases ***
Defaulted
    same    same
Own settings
    [Documentation]    Test document
    [Tags]    own    -common_tag
    [Setup]    Log    own-open
    [Teardown]    Log    own-close
    [Timeout]    2 minutes
    [Template]    NONE
    Should Be Equal    ${IMPORTED}    from variables
    Should Be Equal    ${LOCAL}    from data
    Resource Action
    ${items}=    Create List    a    b
    Length Should Be    ${items}    2
Empty
    [Template]    NONE
*** Keywords ***
Check Pair
    [Arguments]    ${left}    ${right}
    Should Be Equal    ${left}    ${right}
''')
    suite = Suite.from_file_system(source)
    assert suite.name == 'Declared identity'
    assert suite.doc == 'Suite document'
    assert dict(suite.metadata) == {'Team': 'Data team'}
    assert [i.type for i in suite.resource.imports] == ['LIBRARY', 'RESOURCE', 'VARIABLES']
    assert [i.name for i in suite.resource.imports] == ['Collections', 'actions.resource', 'values.py']
    assert suite.resource.variables[0].name == '${LOCAL}'
    assert tuple(suite.resource.variables[0].value) == ('from data',)
    assert [k.name for k in suite.resource.keywords] == ['Check Pair']
    defaulted, own, empty = suite.tests
    assert len(defaulted.tags) == 2 and 'common tag' in defaulted.tags and 'default-only' in defaulted.tags
    assert list(own.tags) == ['own']
    assert defaulted.setup.args == ('default-open',)
    assert defaulted.teardown.args == ('default-close',)
    assert defaulted.timeout == '1 minute'
    assert defaulted.template == 'Check Pair'
    assert own.doc == 'Test document'
    assert own.setup.args == ('own-open',) and own.teardown.args == ('own-close',)
    assert own.timeout == '2 minutes' and own.template is None
    process, xml = execute_source(source, tmp_path)
    assert process.returncode == 1, (process.stdout, process.stderr)
    results = {t.attrib['name']: t for t in xml.findall('./suite/test')}
    assert {n: t.find('status').attrib['status'] for n, t in results.items()} == {
        'Defaulted': 'PASS', 'Own settings': 'PASS', 'Empty': 'FAIL'}
    assert results['Empty'].find('status').text
    for test_name, opening, closing in [('Defaulted', 'default-open', 'default-close'),
                                        ('Own settings', 'own-open', 'own-close')]:
        assert results[test_name].find('./kw[@type="SETUP"]/msg').text == opening
        assert results[test_name].find('./kw[@type="TEARDOWN"]/msg').text == closing
    assert xml.find('./suite/kw[@type="SETUP"]/msg').text == 'suite-open'
    assert xml.find('./suite/kw[@type="TEARDOWN"]/msg').text == 'suite-close' 
