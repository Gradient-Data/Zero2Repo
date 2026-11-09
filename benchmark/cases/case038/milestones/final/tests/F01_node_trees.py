# feature: F01
"""Acceptance coverage of public XPath node-tree construction and accessors."""

import xml.etree.ElementTree as ET

from lxml import etree as LE

from velunara import VelunaraTypeError, XPath1Parser, XPath2Parser, XPathContext, \
    get_node_tree, select
from _helpers import evaluate_expression, observe, read_xml, result_items


def test_supported_tree_inputs_and_reuse():
    for module in (ET, LE):
        source = module.fromstring('<inventory><item code="a">first</item>'
                                   '<item code="b">second</item>'
                                   '<item code="a">first</item></inventory>')
        document = module.ElementTree(source)
        for supplied, kind, original in ((source, 'element', source),
                                         (document, 'document', document)):
            tree = get_node_tree(supplied)
            assert tree.node_kind == kind
            assert tree.value is original
            reused = get_node_tree(tree)
            assert reused.node_kind == kind
            assert reused.value is original
            for root in (supplied, tree, reused):
                selected = select(root, '//item')
                assert len(selected) == 3
                assert selected[0] is source[0]
                assert selected[1] is source[1]
                assert selected[2] is source[2]
                assert selected[0] is not selected[2]
                assert select(root, '//item/@code') == ['a', 'b', 'a']
                assert select(root, '//item/text()') == ['first', 'second', 'first']


def test_invalid_tree_roots_are_refused():
    assert result_items(select(get_node_tree(ET.fromstring('<r><a>live</a></r>')),
                               'a/text()')) == ['live']
    invalid = [None, 7, '<r/>', {}, [], object()]
    for module in (ET, LE):
        invalid.extend([module.Comment('note'), module.ProcessingInstruction('go', 'data')])
    for root in invalid:
        outcome = observe(get_node_tree, root, exceptions=(VelunaraTypeError,))
        assert isinstance(outcome.error, VelunaraTypeError)


def test_node_kinds_content_relationships_and_order():
    xml = ('<r xmlns="urn:tree" xmlns:p="urn:prop" p:code="Q" plain="v">'
           'lead<a>inside</a>middle<!--note-->after-comment'
           '<?go data?>after-pi<b/>end</r>')
    for source in (read_xml(xml), LE.fromstring(xml)):
        module = LE if hasattr(source, 'xpath') else ET
        document = module.ElementTree(source)
        tree = get_node_tree(document, namespaces={'p': 'urn:prop'})
        assert tree.node_kind == 'document'
        assert tree.value is document
        assert tree.parent is None
        assert len(tree.children) == 1
        root = tree.children[0]
        assert root.node_kind == 'element'
        assert root.name == '{urn:tree}r'
        assert root.value is source
        assert root.parent is tree
        expected = [('text', None, 'lead'), ('element', '{urn:tree}a', 'inside'),
                    ('text', None, 'middle'), ('comment', None, 'note'),
                    ('text', None, 'after-comment'),
                    ('processing-instruction', 'go', 'data'),
                    ('text', None, 'after-pi'), ('element', '{urn:tree}b', ''),
                    ('text', None, 'end')]
        assert [(n.node_kind, n.name, n.string_value) for n in root.children] == expected
        assert all(n.parent is root for n in root.children)
        for index, source_index in ((1, 0), (3, 1), (5, 2), (7, 3)):
            assert root.children[index].value is source[source_index]
        assert root.children[1] is not root.children[7]
        assert root.children[1].children[0].parent is root.children[1]
        assert root.children[1].children[0].string_value == 'inside'
        attributes = root.attributes
        assert {n.name: (n.node_kind, n.value, n.string_value) for n in attributes} == {
            '{urn:prop}code': ('attribute', 'Q', 'Q'),
            'plain': ('attribute', 'v', 'v')}
        assert all(n.parent is root for n in attributes)
        namespaces = root.namespace_nodes
        assert all(n.node_kind == 'namespace' and n.parent is root for n in namespaces)
        assert all(n.string_value == n.value for n in namespaces)
        assert {n.name: n.value for n in namespaces}['p'] == 'urn:prop'
        # XPath union must return source elements once, in document order.
        chosen = select(tree, '/*/*[2] | /*/*[1] | /*/*[1]')
        assert len(chosen) == 2
        assert chosen[0] is source[0] and chosen[1] is source[3]
        # XDM document order places an element's attributes before its children.
        ordered = module.fromstring('<r a="1">x<s b="2">y<u c="3"/>k</s>z</r>')
        for expression in ('//text() | //@*', '//@* | //text()'):
            assert select(ordered, expression) == ['1', 'x', '2', 'y', '3', 'k', 'z']

        # Aggregate string values are checked without the baseline's known
        # comment/PI-tail omission; the independent text nodes above remain checked.
        clean = module.fromstring('<r>north<a>inner</a>south<!--note--><?go data?><b/>end</r>')
        clean_tree = get_node_tree(module.ElementTree(clean))
        assert clean_tree.string_value == 'northinnersouthend'
        assert clean_tree.children[0].string_value == 'northinnersouthend'

    discarded = get_node_tree(ET.fromstring(xml))
    assert [(n.node_kind, n.string_value) for n in discarded.children] == [
        ('text', 'lead'), ('element', 'inside'),
        ('text', 'middleafter-commentafter-pi'), ('element', ''), ('text', 'end')]


def test_namespace_sources_and_implicit_xml_binding():
    xml_uri = 'http://www.w3.org/XML/1998/namespace'
    source = LE.fromstring('<r xmlns="urn:default" xmlns:p="urn:outer">'
                           '<p:a xmlns:p="urn:inner" xmlns:q="urn:extra"/></r>')
    root = get_node_tree(source, namespaces={'wrong': 'urn:ignored'})
    assert {n.name: n.value for n in root.namespace_nodes} == {
        'xml': xml_uri, None: 'urn:default', 'p': 'urn:outer'}
    assert {n.name: n.value for n in root.children[0].namespace_nodes} == {
        'xml': xml_uri, None: 'urn:default', 'p': 'urn:inner', 'q': 'urn:extra'}
    standard = ET.fromstring('<r xmlns:p="urn:source"><p:a/></r>')
    root = get_node_tree(standard, namespaces={'p': 'urn:source', 'z': 'urn:caller'})
    for node in (root, root.children[0]):
        assert {n.name: n.value for n in node.namespace_nodes} == {
            'xml': xml_uri, 'p': 'urn:source', 'z': 'urn:caller'}
    assert {n.name: n.value for n in get_node_tree(ET.fromstring('<r/>')).namespace_nodes} == {
        'xml': xml_uri}
    # Caller bindings supplied through selection also provide the standard tree's
    # namespace nodes (XPath 1.0 namespace axis).
    assert result_items(select(standard, 'string(p:a/namespace::z)', parser=XPath1Parser,
                               namespaces={'p': 'urn:source', 'z': 'urn:caller'})) == ['urn:caller']
    for module in (ET, LE):
        # The xml prefix needs no explicit binding in expressions either.
        assert select(module.fromstring('<r xml:lang="en"><a xml:lang="fr"/></r>'),
                      '(@xml:lang, a/@xml:lang)') == ['en', 'fr']


def test_base_and_document_uri_resolution():
    uri = 'https://example.org/catalog/doc.xml'
    for module in (ET, LE):
        plain = get_node_tree(module.ElementTree(module.fromstring('<r><a/></r>')), uri=uri)
        assert plain.base_uri == uri
        assert plain.children[0].base_uri == uri
        assert result_items(select(plain, 'base-uri(/*)')) == [uri]
        images = 'https://example.org/catalog/images/'
        parse = read_xml if module is ET else LE.fromstring
        source = parse('<r xml:base="assets/"><a xml:base="../images/">'
                       '<b k="1">tx<!--c--><?p d?></b></a><c/></r>')
        tree = get_node_tree(module.ElementTree(source), uri=uri)
        root = tree.children[0]
        assert tree.base_uri == uri
        assert tree.document_uri == uri
        assert root.base_uri == 'https://example.org/catalog/assets/'
        assert root.children[0].base_uri == images
        leaf = root.children[0].children[0]
        assert leaf.base_uri == images
        # Attribute, text, comment and PI nodes take the parent element's base URI.
        assert [n.base_uri for n in leaf.attributes] == [images]
        assert [(n.node_kind, n.base_uri) for n in leaf.children] == [
            ('text', images), ('comment', images), ('processing-instruction', images)]
        assert root.children[1].base_uri == 'https://example.org/catalog/assets/'
        assert result_items(select(tree, 'base-uri(/*/a/b)')) == [images]
        for node in ('@k', 'text()', 'comment()', 'processing-instruction()'):
            assert result_items(select(tree, 'string(base-uri(/*/a/b/%s))' % node)) == [images]
        assert result_items(select(tree, 'base-uri(/*/c)')) == ['https://example.org/catalog/assets/']
        assert result_items(select(tree, 'document-uri(/)')) == [uri]
        # A URI supplied with a document root through the dynamic context.
        context = XPathContext(module.ElementTree(module.fromstring('<r/>')), uri=uri)
        assert observe(evaluate_expression, XPath2Parser(),
                       '(string(base-uri(/*)), string(document-uri(/)))',
                       context=context).value == [uri, uri]
        absolute = get_node_tree(module.fromstring(
            '<r xml:base="https://example.net/base/"><a xml:base="child"/></r>'))
        assert absolute.base_uri == 'https://example.net/base/'
        assert absolute.children[0].base_uri == 'https://example.net/base/child'


def test_default_fragment_and_document_root_treatment():
    for module in (ET, LE):
        source = module.fromstring('<r><a>live</a></r>')
        document = module.ElementTree(source)
        assert get_node_tree(source).node_kind == 'element'
        assert get_node_tree(document).node_kind == 'document'
        for supplied in (source, document):
            fragment = get_node_tree(supplied, fragment=True)
            assert fragment.node_kind == 'element'
            assert fragment.value is source
            assert fragment.parent is None
            assert select(supplied, 'a', fragment=True)[0] is source[0]
            forced = get_node_tree(supplied, fragment=False)
            assert forced.node_kind == 'document'
            assert len(forced.children) == 1
            assert forced.children[0].value is source
            assert forced.children[0].parent is forced
            assert select(supplied, 'r/a', fragment=False)[0] is source[0]
        # Explicit treatment also applies when an existing XPath tree is supplied.
        for existing in (get_node_tree(source), get_node_tree(document)):
            fragment = get_node_tree(existing, fragment=True)
            assert fragment.node_kind == 'element' and fragment.value is source
            assert select(existing, 'a', fragment=True)[0] is source[0]
            forced = get_node_tree(existing, fragment=False)
            assert forced.node_kind == 'document' and forced.children[0].value is source
            assert select(existing, 'r/a', fragment=False)[0] is source[0]
        addressed = get_node_tree(get_node_tree(module.ElementTree(module.fromstring('<r/>'))),
                                  uri='https://example.org/reused.xml')
        assert addressed.base_uri == 'https://example.org/reused.xml'
        selected_document = select(document, '/')
        assert len(selected_document) == 1 and selected_document[0] is document
        # Default element processing can use an auxiliary document internally,
        # but must not return it as though supplied by the caller.
        assert select(source, '/') == []
        assert select(source, '/r/a')[0] is source[0]

    source = LE.fromstring(b'<!--before--><?start x?><r><a/></r><?finish y?><!--after-->')
    expected = [('comment', None, 'before'), ('processing-instruction', 'start', 'x'),
                ('element', 'r', ''), ('processing-instruction', 'finish', 'y'),
                ('comment', None, 'after')]
    for supplied in (source, LE.ElementTree(source)):
        tree = get_node_tree(supplied)
        assert tree.node_kind == 'document'
        assert [(n.node_kind, n.name, n.string_value) for n in tree.children] == expected
        originals = [source.getprevious().getprevious(), source.getprevious(), source,
                     source.getnext(), source.getnext().getnext()]
        assert all(n.value is value and n.parent is tree
                   for n, value in zip(tree.children, originals))
        results = select(supplied, '/node()')
        assert len(results) == len(originals)
        assert all(actual is original for actual, original in zip(results, originals))
        fragment = get_node_tree(supplied, fragment=True)
        assert fragment.node_kind == 'element' and fragment.value is source
        assert fragment.parent is None
        assert len(fragment.children) == 1 and fragment.children[0].value is source[0]
        results = select(supplied, 'a', fragment=True)
        assert len(results) == 1 and results[0] is source[0]

    # Document-level siblings on only one side still require a document root.
    for text, kinds in ((b'<r><a/></r><!--after-->', ['element', 'comment']),
                        (b'<?start x?><r><a/></r>', ['processing-instruction', 'element'])):
        source = LE.fromstring(text)
        tree = get_node_tree(source)
        assert tree.node_kind == 'document'
        assert [n.node_kind for n in tree.children] == kinds
        assert any(n.value is source for n in tree.children)
        assert len(select(source, '/node()')) == 2
