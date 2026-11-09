# feature: F09
"""Public resource, XML and environment acceptance tests.

Expected content comes from the real supplied files, XML and host environment.
Error categories follow the W3C F&O editions named in FP-09; diagnostic prose
and implementation-specific caches are not inspected.
"""
import os
import xml.etree.ElementTree as ET

from velunara import (XPath2Parser, XPathContext, VelunaraTypeError,
                         VelunaraValueError, MissingContextError)
from velunara.xpath3 import XPath30Parser, XPath31Parser
from velunara.exceptions import XMLResourceForbidden
from _helpers import observe, evaluate_expression
from F02_helpers import datatype_failure
from F04_helpers import context_results
from F09_helpers import xpath_string, http_files, ftp_files


def test_bound_documents_relative_resolution_types_and_no_download(tmp_path):
    (tmp_path / 'unbound.xml').write_text('<external>downloadable</external>', encoding='utf-8')
    document = ET.ElementTree(ET.fromstring('<catalog><item>bound</item></catalog>'))
    with http_files(tmp_path) as (base, requests):
        parser = XPath2Parser(base_uri=base)
        context = XPathContext(ET.Element('r'), documents={base + 'bound.xml': document})
        assert context_results("doc('bound.xml')", parser=parser, context=context) == [document]
        assert context_results("doc('bound.xml')/catalog/item/string()", parser=parser,
                               context=context) == ['bound']
        assert context_results("doc-available('bound.xml')", parser=parser, context=context) == [True]
        assert context_results("doc(())", parser=parser, context=context) == []
        assert context_results("doc-available(())", parser=parser, context=context) == [False]
        # Prove the unregistered URL really serves a document before querying doc().
        assert context_results("unparsed-text('unbound.xml')",
                               parser=XPath30Parser(base_uri=base, allow_external_resources=True),
                               context=XPathContext(ET.Element('r'))) == ['<external>downloadable</external>']
        requests.clear()
        datatype_failure("doc('unbound.xml')", VelunaraValueError, 'FODC0002',
                         parser=parser, context=context)
        assert context_results("doc-available('unbound.xml')", parser=parser, context=context) == [False]
        assert requests == []
        wrong_type = XPath2Parser(base_uri=base, document_types={base + 'bound.xml': 'element()'})
        for function in ('doc', 'doc-available'):
            datatype_failure(function + "('bound.xml')", VelunaraTypeError, 'XPDY0050',
                             parser=wrong_type, context=context)
        outcome = observe(XPath2Parser, document_types={base + 'bound.xml': 'invalid()'},
                          exceptions=(VelunaraValueError,))
        assert isinstance(outcome.error, VelunaraValueError)


def test_bound_collections_order_defaults_types_and_no_directory_scan(tmp_path):
    first = ET.fromstring('<a>first</a>')
    second = ET.fromstring('<b>second</b>')
    (tmp_path / 'discoverable.xml').write_text('<scan/>', encoding='utf-8')
    (tmp_path / 'subdir').mkdir()
    base = tmp_path.as_uri() + '/'
    context = XPathContext(ET.Element('r'), collections={base + 'set': [second, first]},
                           default_collection=[first, second])
    parser = XPath2Parser(base_uri=base, collection_types={base + 'set': 'node()*'})
    assert context_results("collection('set')", parser=parser, context=context) == [second, first]
    assert context_results("collection('set')/string()", parser=parser, context=context) == ['second', 'first']
    assert context_results('collection()', parser=parser, context=context) == [first, second]
    assert context_results('collection(())', parser=parser, context=context) == [first, second]
    datatype_failure("collection('missing')", VelunaraValueError, 'FODC0002', parser=parser, context=context)
    datatype_failure('collection()', VelunaraValueError, 'FODC0002', parser=parser,
                     context=XPathContext(ET.Element('r')))
    # A supplied empty default collection is present, not absent.
    assert context_results('collection()', parser=parser,
                           context=XPathContext(ET.Element('r'), default_collection=[])) == []
    for directory in (base, tmp_path.as_uri(), 'subdir'):
        datatype_failure('collection(' + xpath_string(directory) + ')', VelunaraValueError, 'FODC0004',
                         parser=parser, context=context)
    datatype_failure("collection('absent-dir/')", VelunaraValueError, 'FODC0002', parser=parser, context=context)
    for expression, options in (("collection('set')", {'collection_types': {base + 'set': 'node()'}}),
                                ('collection()', {'default_collection_type': 'node()'})):
        datatype_failure(expression, VelunaraTypeError, 'XPDY0050',
                         parser=XPath2Parser(base_uri=base, **options), context=context)
    outcome = observe(XPath2Parser, collection_types={'set': 'invalid()'}, exceptions=(VelunaraValueError,))
    assert isinstance(outcome.error, VelunaraValueError)


def test_local_text_lines_encodings_and_bom(tmp_path):
    # Only CR LF, CR and LF end lines; NEL and LINE SEPARATOR are ordinary characters.
    # Only the final line ending is ignored, so the trailing empty line remains.
    text = 'alpha café\r\nbeta\x85same\r\n\ngamma\rdelta\u2028same\n\r\n'
    lines = ['alpha café', 'beta\x85same', '', 'gamma', 'delta\u2028same', '']
    latin = text.replace('\u2028', ' ')
    files = (('utf8.txt', text, text.encode('utf-8'), None),
             ('latin.txt', latin, latin.encode('iso-8859-1'), 'iso-8859-1'),
             ('utf16.txt', text, text.encode('utf-16'), None),
             ('utf16le.txt', text, b'\xff\xfe' + text.encode('utf-16-le'), None),
             ('utf16be.txt', text, b'\xfe\xff' + text.encode('utf-16-be'), None))
    parser = XPath30Parser(base_uri=tmp_path.as_uri() + '/', allow_external_resources=True)
    for name, content, data, encoding in files:
        (tmp_path / name).write_bytes(data)
        arguments = xpath_string(name) + (', ' + xpath_string(encoding) if encoding else '')
        for function, expected in (('unparsed-text', [content]),
                                    ('unparsed-text-lines', [x.replace('\u2028', ' ') for x in lines]
                                     if encoding else lines),
                                    ('unparsed-text-available', [True])):
            assert context_results(function + '(' + arguments + ')', parser=parser,
                                   context=XPathContext(ET.Element('r'))) == expected
    for function, expected in (('unparsed-text', []), ('unparsed-text-lines', []),
                                ('unparsed-text-available', [False])):
        assert context_results(function + '(())', parser=parser) == expected


def test_real_http_ftp_text_and_relative_references(tmp_path):
    (tmp_path / 'texts').mkdir()
    (tmp_path / 'texts' / 'resource.txt').write_bytes('network café\nnext\n'.encode('utf-8'))
    with http_files(tmp_path) as (http_base, requests), ftp_files(tmp_path) as ftp_base:
        for base, (static_base, reference) in ((b, r) for b in (http_base, ftp_base) for r in (
                ('texts/', 'resource.txt'), ('other/index.html', '../texts/resource.txt'))):
            parser = XPath30Parser(base_uri=base + static_base, allow_external_resources=True)
            for function, expected in (('unparsed-text', ['network café\nnext\n']),
                                        ('unparsed-text-lines', ['network café', 'next']),
                                        ('unparsed-text-available', [True])):
                assert context_results(function + '(' + xpath_string(reference) + ')', parser=parser,
                                       context=XPathContext(ET.Element('r'))) == expected
        assert '/texts/resource.txt' in requests


def test_external_permissions_normalized_prefixes_and_missing_resources(tmp_path):
    (tmp_path / 'allowed').mkdir()
    (tmp_path / 'other').mkdir()
    (tmp_path / 'allowed' / 'live.txt').write_text('allowed content', encoding='utf-8')
    (tmp_path / 'other' / 'secret.txt').write_text('outside content', encoding='utf-8')
    (tmp_path / 'allowed-sibling').mkdir()
    (tmp_path / 'allowed-sibling' / 'secret.txt').write_text('sibling content', encoding='utf-8')
    with http_files(tmp_path) as (base, requests), http_files(tmp_path) as (other_origin, other_requests):
        # Each arm uses a new context: prior reads cannot turn into bound text.
        for uri_base in (base, tmp_path.as_uri() + '/'):
            live = uri_base + 'allowed/live.txt'
            outside = uri_base + 'other/secret.txt'
            # Every listed prefix grants access, not only the first or last entry.
            allowed = XPath30Parser(allow_external_resources=[uri_base + 'first-unused/', uri_base + 'allowed/',
                                                              uri_base + 'last-unused/'])
            # The permission applies to the resolved reference, not to the static base URI.
            based = XPath30Parser(base_uri=uri_base + 'allowed/', allow_external_resources=[uri_base + 'allowed/'])
            opened = XPath30Parser(allow_external_resources=True)
            assert context_results('unparsed-text(' + xpath_string(outside) + ')', parser=opened,
                                   context=XPathContext(ET.Element('r'))) == ['outside content']
            for parser, href, permitted in ((XPath30Parser(), live, False),
                                            (XPath30Parser(allow_external_resources=False), live, False),
                                            (opened, live, True), (allowed, live, True),
                                            (allowed, uri_base + 'allowed/../other/secret.txt', False),
                                            (allowed, uri_base + 'other/../allowed/live.txt', True),
                                            (based, 'live.txt', True), (based, '../other/secret.txt', False),
                                            (allowed, uri_base + 'allowed/x/../../other/secret.txt', False),
                                            (allowed, uri_base + 'allowed-sibling/secret.txt', False),
                                            (allowed, outside, False)) + (
                                            # Same path on another origin is outside the permitted prefix.
                                            ((allowed, other_origin + 'allowed/live.txt', False),)
                                            if uri_base == base else ()):
                before = len(requests)
                if permitted:
                    assert context_results('unparsed-text(' + xpath_string(href) + ')', parser=parser,
                                           context=XPathContext(ET.Element('r'))) == ['allowed content']
                else:
                    datatype_failure('unparsed-text(' + xpath_string(href) + ')', VelunaraValueError,
                                     'FOUT1170', parser=parser, context=XPathContext(ET.Element('r')))
                assert context_results('unparsed-text-available(' + xpath_string(href) + ')', parser=parser,
                                       context=XPathContext(ET.Element('r'))) == [permitted]
                if not permitted:
                    assert len(requests) == before
                    assert other_requests == []
            missing = uri_base + 'allowed/missing.txt'
            assert context_results('unparsed-text-available(' + xpath_string(missing) + ')', parser=allowed,
                                   context=XPathContext(ET.Element('r'))) == [False]
            datatype_failure('unparsed-text(' + xpath_string(missing) + ')', VelunaraValueError,
                             'FOUT1170', parser=allowed, context=XPathContext(ET.Element('r')))


def test_explicit_text_binding_precedence_and_availability_permission(tmp_path):
    (tmp_path / 'same.txt').write_text('external content', encoding='utf-8')
    with http_files(tmp_path) as (base, requests):
        uri = base + 'same.txt'
        for permitted, parser_base, reference in ((True, None, uri), (False, None, uri),
                                                  (True, base, 'same.txt'), (False, base, 'same.txt')):
            parser = XPath30Parser(base_uri=parser_base, allow_external_resources=permitted)
            context = XPathContext(ET.Element('r'), text_resources={uri: 'bound\ntext\n'},
                                   variables={'uri': reference})
            before = len(requests)
            assert context_results('unparsed-text($uri)', parser=parser,
                                   context=context) == ['bound\ntext\n']
            assert context_results('unparsed-text-lines($uri)', parser=parser,
                                   context=context) == ['bound', 'text']
            assert len(requests) == before
            assert context_results('unparsed-text-available($uri)', parser=parser,
                                   context=context) == [permitted]
            if not permitted:
                assert len(requests) == before
        assert context_results('unparsed-text(' + xpath_string(uri) + ')',
                               parser=XPath30Parser(allow_external_resources=True),
                               context=XPathContext(ET.Element('r'))) == ['external content']


def test_uri_collections_order_default_and_unconfigured_states():
    base = 'http://resources.example.test/'
    uris = [base + 'second', base + 'first', base + 'second', base + 'third']
    parser = XPath30Parser(base_uri=base)
    context = XPathContext(ET.Element('r'), resource_collections={base + 'named': uris},
                           default_resource_collection=base + 'default')
    assert [str(x) for x in context_results("uri-collection('named')", parser=parser, context=context)] == uris
    assert [str(x) for x in context_results('uri-collection()', parser=parser, context=context)] == [base + 'default']
    assert [str(x) for x in context_results('uri-collection(())', parser=parser, context=context)] == [base + 'default']
    for expression in ("uri-collection('named') instance of xs:anyURI+", 'uri-collection() instance of xs:anyURI'):
        assert context_results(expression, parser=parser, context=context) == [True]
    datatype_failure("uri-collection('missing')", VelunaraValueError, 'FODC0002', parser=parser, context=context)
    empty = XPathContext(ET.Element('r'))
    assert context_results("uri-collection('missing')", parser=parser, context=empty) == []
    datatype_failure('uri-collection()', VelunaraValueError, 'FODC0002', parser=parser, context=empty)


def test_text_resource_uri_encoding_decode_and_xml_character_failures(tmp_path):
    (tmp_path / 'valid.txt').write_bytes(b'valid text')
    (tmp_path / 'invalid.txt').write_bytes(b'\xff\xfe\xfd')
    (tmp_path / 'control.txt').write_bytes(b'bad\x00text')
    parser = XPath30Parser(base_uri=tmp_path.as_uri() + '/', allow_external_resources=True)
    assert context_results("unparsed-text('valid.txt')", parser=parser) == ['valid text']
    for arguments, code in (("'valid.txt#fragment'", 'FOUT1170'),
                             ("'valid.txt', 'no-such-encoding'", 'FOUT1190'),
                             ("'invalid.txt', 'UTF-8'", 'FOUT1190'),
                             ("'control.txt'", 'FOUT1190')):
        for function in ('unparsed-text', 'unparsed-text-lines'):
            datatype_failure(function + '(' + arguments + ')', VelunaraValueError, code, parser=parser)
        assert context_results('unparsed-text-available(' + arguments + ')', parser=parser) == [False]


def test_parse_xml_document_fragment_empty_malformed_and_context():
    parser = XPath30Parser()
    context = XPathContext(ET.Element('r'))
    document = xpath_string('<r a="7">lead<c>inside</c>tail</r>')
    fragment = xpath_string('lead<a>one</a>between<b/>tail')
    for expression, expected in (
        ('parse-xml(' + document + ') instance of document-node()', [True]),
        ('parse-xml(' + document + ')/r/@a/string()', ['7']),
        ('parse-xml(' + document + ')/r/node()/string()', ['lead', 'inside', 'tail']),
        ('parse-xml-fragment(' + fragment + ') instance of document-node()', [True]),
        ('parse-xml-fragment(' + fragment + ')/node()/string()', ['lead', 'one', 'between', '', 'tail']),
        ('parse-xml-fragment(' + fragment + ')/*/name()', ['a', 'b']),
    ):
        assert context_results(expression, parser=parser, context=context) == expected
    for function in ('parse-xml', 'parse-xml-fragment'):
        assert context_results(function + '(())', parser=parser, context=context) == []
        datatype_failure(function + "('<r>')", VelunaraValueError, 'FODC0006', parser=parser, context=context)
        datatype_failure(function + "('<r/>')", MissingContextError, 'XPDY0002', parser=parser)
    # A complete document has exactly one root element and no top-level text.
    for not_document in ('<a/><b/>', 'lead<a/>', '<a/>tail'):
        datatype_failure('parse-xml(' + xpath_string(not_document) + ')', VelunaraValueError, 'FODC0006',
                         parser=parser, context=context)


def test_parse_xml_entity_protection_default_and_disabled():
    context = XPathContext(ET.Element('r'))
    xml = xpath_string('<!DOCTYPE r [<!ENTITY word "trusted content">]><r>&word;</r>')
    expression = 'parse-xml(' + xml + ')/r/string()'
    parameter = 'parse-xml(' + xpath_string('<!DOCTYPE r [<!ENTITY % p "x">]><r/>') + ')/r/string()'
    # Declaration-like text inside character data is not an entity declaration.
    harmless = (('<r><![CDATA[<!DOCTYPE r [<!ENTITY word "x">]>]]></r>', '<!DOCTYPE r [<!ENTITY word "x">]>'),)
    for parser in (XPath30Parser(), XPath30Parser(defuse_xml=True)):
        assert context_results("parse-xml('<r>normal</r>')/r/string()", parser=parser,
                               context=context) == ['normal']
        for source, value in harmless:
            assert context_results('parse-xml(' + xpath_string(source) + ')/r/string()', parser=parser,
                                   context=context) == [value]
        for forbidden in (expression, parameter):
            outcome = observe(evaluate_expression, parser, forbidden, context=context,
                              result_method='select_results', consume=True,
                              exceptions=(XMLResourceForbidden,))
            assert isinstance(outcome.error, XMLResourceForbidden)
    assert context_results(expression, parser=XPath30Parser(defuse_xml=False),
                           context=context) == ['trusted content']


def test_environment_default_all_exact_prefix_and_missing(monkeypatch):
    names = {'F09_SCOPE_ONE': 'first actual value', 'F09_SCOPE_TWO': 'second actual value',
             'F09_EXACT': 'exact value', 'F09_EXACT_SUFFIX': 'not exact', 'F09_DENIED': 'hidden',
             'X_F09_SCOPE_INNER': 'not a prefix match', 'f09_exact': 'different case', 'F09_EMPTY': ''}
    for name, value in names.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('F09_ABSENT', raising=False)
    for options, allowed in (({}, set()), ({'allow_environment': False}, set()),
                              ({'allow_environment': True}, set(os.environ)),
                              ({'allow_environment': ['F09_EXACT']}, {'F09_EXACT'}),
                              ({'allow_environment': ['F09_SCOPE_*', 'F09_EXACT', 'F09_ABSENT', 'F09_EMPTY']},
                               {n for n in os.environ if n.startswith('F09_SCOPE_')} | {'F09_EXACT', 'F09_EMPTY'})):
        parser = XPath30Parser(**options)
        assert set(context_results('available-environment-variables()', parser=parser)) == allowed
        for name, value in names.items():
            assert context_results('environment-variable(' + xpath_string(name) + ')', parser=parser) == (
                [value] if name in allowed else [])
        assert context_results("environment-variable('F09_ABSENT')", parser=parser) == []


def test_policy_configuration_types_and_effects_in_both_versions(tmp_path, monkeypatch):
    path = tmp_path / 'resource.txt'
    path.write_text('policy content', encoding='utf-8')
    json_path = tmp_path / 'resource.json'
    json_path.write_text('{"v": 5}', encoding='utf-8')
    monkeypatch.setenv('F09_POLICY', 'policy value')
    for factory in (XPath30Parser, XPath31Parser):
        for setting, permitted in ((True, True), (False, False), ([path.parent.as_uri() + '/'], True),
                                   ([path.parent.as_uri() + '/elsewhere/'], False), ([], False)):
            parser = factory(allow_external_resources=setting)
            expressions = {'unparsed-text(' + xpath_string(path.as_uri()) + ')': ['policy content']}
            if factory is XPath31Parser:
                expressions['json-doc(' + xpath_string(json_path.as_uri()) + ')?v'] = [5]
            for expression, expected in expressions.items():
                if permitted:
                    assert context_results(expression, parser=parser) == expected
                else:
                    datatype_failure(expression, VelunaraValueError, 'FOUT1170', parser=parser)
        for setting in (True, False, ['F09_POLICY'], []):
            assert context_results("environment-variable('F09_POLICY')",
                                   parser=factory(allow_environment=setting)) == (['policy value'] if setting else [])
        for option in ('allow_environment', 'allow_external_resources'):
            for invalid in (1, 'yes', {'permission': True}, None):
                outcome = observe(factory, **{option: invalid}, exceptions=(VelunaraTypeError,))
                assert isinstance(outcome.error, VelunaraTypeError), outcome
