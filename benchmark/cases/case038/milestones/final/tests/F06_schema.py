# feature: F06
"""Schema integration through real XML Schema processor inputs.

Expected values follow XML Schema 1.0/1.1 and XPath 2.0/3.0/3.1 rules,
independently of the product's conversion implementation.
"""
from decimal import Decimal
from xml.etree import ElementTree as ET
from velunara import XPath2Parser, XPathSchemaContext, select
from velunara.xpath30 import XPath30Parser
from velunara.xpath31 import XPath31Parser
from velunara import VelunaraValueError, VelunaraTypeError, VelunaraError, XPathContext
from _helpers import observe
from F02_helpers import datatype_failure, datatype_rejection
from F04_helpers import context_results
from F06_helpers import (SCHEMA_NS, SCHEMA_NAMESPACES, schema_document,
                         typed_schema, schema_value, AcceptanceSchemaProxy)


def test_schema_atomization_and_type_tests():
    schema = typed_schema()
    root = ET.XML('<s:root xmlns:s="urn:acceptance:schema" s:level="7.5" count="0042" enabled="true">'
                  '<s:detail weight="2.5" s:level="3"><s:when>2001-02-03</s:when></s:detail>'
                  '<s:amount>003.25</s:amount><s:amount>11</s:amount></s:root>')
    for parser_class in (XPath2Parser, XPath30Parser, XPath31Parser):
        def value(expression):
            return schema_value(schema, root, expression, parser_class=parser_class)
        assert value('data(s:amount)') == [Decimal('3.25'), 11]
        assert value('data(@s:level)') == [Decimal('7.5')]
        assert value('data(@count)') == [42]
        assert value('data(@count) instance of xs:int') is True
        assert value('data(@enabled)') == [True]
        assert value('data(@enabled) instance of xs:boolean') is True
        assert value('sum(s:amount) + @s:level') == Decimal('21.75')
        assert value('every $v in data(s:amount) satisfies $v instance of xs:decimal') is True
        assert value('data(@s:level) instance of xs:decimal') is True
        assert value('data(s:amount[1]) instance of xs:untypedAtomic') is False
        # Nested local declarations and a strict attribute wildcard resolved to
        # the global declaration are annotated too, not only top-level ones.
        assert value('data(s:detail/s:when) instance of xs:date') is True
        assert value('year-from-date(s:detail/s:when)') == 2001
        assert value('data(s:detail/@weight)') == [2.5]
        assert value('data(s:detail/@weight) instance of xs:double') is True
        assert value('data(s:detail/@s:level)') == [Decimal('3')]
        assert value('data(s:detail/@s:level) instance of xs:decimal') is True


def test_schema_tests_constructors_and_casts():
    schema = typed_schema()
    root = ET.XML('<s:root xmlns:s="urn:acceptance:schema" s:level="6">'
                  '<s:detail><s:when>2001-02-03</s:when></s:detail>'
                  '<s:amount>9</s:amount></s:root>')
    assert schema_value(schema, root, 'count(schema-element(s:amount))') == 1
    # The test selects the declared name, not merely the first child element.
    assert schema_value(schema, root, 'local-name(schema-element(s:amount))') == 'amount'
    assert schema_value(schema, root, 'data(schema-element(s:amount))') == [9]
    assert schema_value(schema, root, 'count(attribute::schema-attribute(s:level))') == 1
    # Both inclusive edges and a fractional interior value are distinct rules.
    for lexical in ('2', '8.5', '12'):
        for expression in (f's:Small("{lexical}")', f'"{lexical}" cast as s:Small'):
            assert schema_value(schema, root, expression) == Decimal(lexical)
        assert schema_value(schema, root, f'"{lexical}" castable as s:Small') is True
    assert schema_value(schema, root, 's:Small("8") instance of s:Small') is True
    # Castability honours both facets just outside each inclusive edge.
    for lexical in ('1', '1.99', '12.01', '13'):
        assert schema_value(schema, root, f'"{lexical}" castable as s:Small') is False
    # A value outside the facets is not an instance of the restricted type.
    assert schema_value(schema, root, '13 instance of s:Small') is False
    # Empty-sequence rules of constructor functions and optional casts.
    assert schema_value(schema, root, 'count(s:Small(()))') == 0
    assert schema_value(schema, root, 'count(() cast as s:Small?)') == 0
    assert schema_value(schema, root, '() castable as s:Small?') is True
    assert schema_value(schema, root, '() castable as s:Small') is False
    parser = XPath2Parser(namespaces=SCHEMA_NAMESPACES, schema=AcceptanceSchemaProxy(schema))
    # Undeclared names in schema node tests are static errors (XPST0008).
    for expression in ('count(schema-element(s:absent))',
                       'count(attribute::schema-attribute(s:absent))'):
        datatype_failure(expression, VelunaraError, 'XPST0008', parser=parser,
                         context=XPathContext(root, namespaces=SCHEMA_NAMESPACES,
                                              schema=AcceptanceSchemaProxy(schema)))
    datatype_failure('s:Small("13")', VelunaraValueError, 'FORG0001', parser=parser)
    datatype_failure('"1" cast as s:Small', VelunaraValueError, 'FORG0001', parser=parser)
    # Exercise construction and enumeration constraints through schema binding.
    # Namespace-carrying NOTATION results are a recorded baseline limitation.
    assert schema_value(schema, root, 's:Image("s:image") instance of s:Image') is True
    datatype_failure('s:Image("s:other")', VelunaraValueError, 'FORG0001', parser=parser)


def test_schema_proxy_declarations_conversions_and_failures():
    schema = typed_schema()
    proxy = AcceptanceSchemaProxy(schema)
    for lookup, name, expected in ((proxy.get_type, 'Small', schema.types['Small']),
                                   (proxy.get_element, 'amount', schema.elements['amount']),
                                   (proxy.get_attribute, 'level', schema.attributes['level'])):
        assert lookup('{' + SCHEMA_NS + '}' + name) is expected
        assert lookup('{' + SCHEMA_NS + '}absent') is None
        # Same local name in another namespace is a different declaration.
        assert lookup('{urn:acceptance:other}' + name) is None
    # Each lookup is restricted to its own global declaration kind.
    for lookup, name in ((proxy.get_type, 'amount'), (proxy.get_type, 'level'),
                         (proxy.get_element, 'Small'), (proxy.get_element, 'level'),
                         (proxy.get_attribute, 'amount'), (proxy.get_attribute, 'Small'),
                         (proxy.get_element, 'detail')):
        assert lookup('{' + SCHEMA_NS + '}' + name) is None
    name = '{' + SCHEMA_NS + '}Small'
    assert proxy.is_instance(8, name) is True
    assert proxy.is_instance(13, name) is False
    assert proxy.is_instance('not-a-number', name) is False
    assert proxy.cast_as('008', name) == 8
    # Missing type and invalid value must remain distinguishable.
    datatype_rejection(proxy.cast_as, '8', '{' + SCHEMA_NS + '}absent', error_class=KeyError)
    outcome = observe(proxy.cast_as, '13', name, exceptions=(ValueError, TypeError))
    assert isinstance(outcome.error, (ValueError, TypeError)), outcome
    datatype_rejection(XPath2Parser, schema=ET.XML('<schema/>'), error_class=TypeError)
    datatype_rejection(XPath2Parser, schema='schema', error_class=TypeError)
    for invalid in (ET.XML('<schema/>'), 'schema'):
        datatype_rejection(XPathContext, ET.XML('<root/>'), schema=invalid,
                           error_class=VelunaraTypeError)


def test_schema_component_tree_selection():
    schema = typed_schema()
    parser = XPath2Parser(namespaces=SCHEMA_NAMESPACES)
    context = XPathSchemaContext(schema)
    assert context_results('s:root', parser=parser, context=context) == [schema.elements['root']]
    content = list(schema.elements['root'].type.content)
    assert context_results('s:root/s:amount', parser=parser, context=context) == content[1:]
    assert context_results('s:root/s:detail', parser=parser, context=context) == content[:1]
    assert context_results('s:root/*', parser=parser, context=context) == content
    assert context_results('s:root/s:detail/s:when', parser=parser,
                           context=context) == list(content[0].type.content)
    assert context_results('s:amount', parser=parser, context=context) == [schema.elements['amount']]
    assert context_results('for $e in s:root/s:amount return namespace-uri($e)',
                           parser=parser, context=context) == [SCHEMA_NS]
    assert context_results('for $e in s:root/s:amount return local-name($e)',
                           parser=parser, context=context) == ['amount']


def test_schema_substitution_and_derivation():
    schema = schema_document('''
      <xs:complexType name="Base"><xs:simpleContent><xs:extension base="xs:decimal"/>
      </xs:simpleContent></xs:complexType>
      <xs:complexType name="Extended"><xs:simpleContent><xs:extension base="s:Base">
        <xs:attribute name="rank" type="xs:decimal"/>
      </xs:extension></xs:simpleContent></xs:complexType>
      <xs:element name="head" type="s:Base"/>
      <xs:element name="member" type="s:Extended" substitutionGroup="s:head"/>
      <xs:element name="root"><xs:complexType><xs:sequence>
        <xs:element ref="s:head" maxOccurs="unbounded"/>
      </xs:sequence></xs:complexType></xs:element>''')
    root = ET.XML('<s:root xmlns:s="urn:acceptance:schema" '
                  'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                  '<s:member rank="4">17</s:member>'
                  '<s:head xsi:type="s:Extended" rank="6">23</s:head></s:root>')
    assert schema_value(schema, root, 'data(*)') == [17, 23]
    assert schema_value(schema, root, 'every $v in data(*) satisfies $v instance of xs:decimal') is True
    assert schema_value(schema, root, 'data(*/@rank)') == [4, 6]
    for expression in ('s:member', 's:head'):
        selected = schema_value(schema, root, expression)
        assert len(selected) == 1
        assert selected[0].type_name == '{' + SCHEMA_NS + '}Extended'
    assert schema_value(schema, root, 'every $a in */@rank satisfies data($a) instance of xs:decimal') is True


def test_schema_defaults_fixed_values_and_identifiers():
    schema = schema_document('''
      <xs:element name="defaulted" type="xs:decimal" default="31"/>
      <xs:element name="fixed" type="xs:decimal" fixed="47"/>
      <xs:element name="entry"><xs:complexType>
        <xs:attribute name="key" type="xs:ID"/>
        <xs:attribute name="link" type="xs:IDREF"/>
        <xs:attribute name="links" type="xs:IDREFS"/>
        <xs:attribute name="plain" type="xs:string"/>
        <xs:attribute name="defaulted" type="xs:decimal" default="59"/>
        <xs:attribute name="fixed" type="xs:decimal" fixed="61"/>
      </xs:complexType></xs:element>
      <xs:element name="root"><xs:complexType><xs:sequence>
        <xs:element ref="s:defaulted" maxOccurs="unbounded"/>
        <xs:element ref="s:fixed"/><xs:element ref="s:entry" maxOccurs="unbounded"/>
        <xs:element name="code" type="xs:ID"/><xs:element name="note" type="xs:string"/>
      </xs:sequence></xs:complexType></xs:element>''')
    root = ET.XML('<s:root xmlns:s="urn:acceptance:schema">'
                  '<s:defaulted/><s:defaulted>37</s:defaulted><s:fixed/>'
                  '<s:entry key="target" plain="decoy"/>'
                  '<s:entry key="source" link="target" links="target source" defaulted="5"/>'
                  '<s:code>gamma</s:code><s:note>delta</s:note></s:root>')
    assert schema_value(schema, root, 'data(s:defaulted)') == [31, 37]
    assert schema_value(schema, root, 'data(s:fixed)') == [47]
    # The attribute default fills only the absent attribute; 5 is explicit.
    assert schema_value(schema, root, 'data(s:entry/@defaulted)') == [59, 5]
    assert schema_value(schema, root, 'data(s:entry/@fixed)') == [61, 61]
    assert schema_value(schema, root,
                        'every $v in data((s:defaulted, s:fixed, s:entry/@defaulted, '
                        's:entry/@fixed)) satisfies $v instance of xs:decimal') is True
    # Read source elements through the public result conversion, not wrappers.
    options = dict(namespaces=SCHEMA_NAMESPACES, schema=AcceptanceSchemaProxy(schema))
    assert select(root, 'id("target")', **options) == [root[3]]
    assert select(root, 'id("decoy")', **options) == []
    # Every whitespace-separated IDREF is resolved, results in document order;
    # an element whose type is xs:ID is identified by its own content.
    assert select(root, 'id("source target")', **options) == [root[3], root[4]]
    assert select(root, 'id("gamma")', **options) == [root[5]]
    assert select(root, 'id("delta")', **options) == []
    assert select(root, 'id(("gamma", "absent", "target"))', **options) == [root[3], root[5]]
    assert schema_value(schema, root, 'data(s:entry[2]/@links)') == ['target', 'source']
    assert schema_value(schema, root, 'data(s:entry[2]/@link) instance of xs:IDREF') is True


def test_schema_version_overrides_parser_datatype_version():
    # Year zero is excluded by XSD 1.0 and included by XSD 1.1.
    root = ET.XML('<s:date xmlns:s="urn:acceptance:schema">2001-02-03</s:date>')
    for version, other, accepted in (('1.0', '1.1', False), ('1.1', '1.0', True)):
        schema = typed_schema(version=version)
        assert schema_value(schema, root, '"0000-01-01" castable as xs:date',
                            xsd_version=other) is accepted
        assert schema_value(schema, root, 'year-from-date(xs:date("2001-02-03"))',
                            xsd_version=other) == 2001
        assert schema_value(schema, root, 'data(.) instance of xs:date',
                            xsd_version=other) is True
