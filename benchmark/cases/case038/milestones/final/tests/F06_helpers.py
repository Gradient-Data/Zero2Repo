# feature: F06
"""Real schema inputs and public schema-bound evaluation."""
import xmlschema
from velunara import XPath2Parser, XPathContext, AbstractSchemaProxy
from xmlschema.xpath import XMLSchemaProxy
from F02_helpers import datatype_expression


class AcceptanceSchemaProxy(XMLSchemaProxy):
    """Bind real processor declarations through the public product methods.

    Membership, conversion and atomic-type enumeration are supplied by the
    real processor; parser registration and declaration lookup are exercised
    through the product's public base implementation.
    """
    bind_parser = AbstractSchemaProxy.bind_parser
    # Exercise the product's public lookup implementations, while the real
    # processor continues to provide type membership and conversion.
    get_type = AbstractSchemaProxy.get_type
    get_element = AbstractSchemaProxy.get_element
    get_attribute = AbstractSchemaProxy.get_attribute


SCHEMA_NS = 'urn:acceptance:schema'
SCHEMA_NAMESPACES = {'s': SCHEMA_NS}


def schema_document(body, *, version='1.0'):
    factory = {'1.0': xmlschema.XMLSchema10, '1.1': xmlschema.XMLSchema11}[version]
    return factory('''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
        xmlns:s="urn:acceptance:schema" targetNamespace="urn:acceptance:schema"
        elementFormDefault="qualified">''' + body + '</xs:schema>')


def typed_schema(*, version='1.0'):
    return schema_document('''
      <xs:simpleType name="Small"><xs:restriction base="xs:decimal">
        <xs:minInclusive value="2"/><xs:maxInclusive value="12"/>
      </xs:restriction></xs:simpleType>
      <xs:notation name="image" public="image-format"/>
      <xs:simpleType name="Image"><xs:restriction base="xs:NOTATION">
        <xs:enumeration value="s:image"/>
      </xs:restriction></xs:simpleType>
      <xs:attribute name="level" type="s:Small"/>
      <xs:element name="amount" type="s:Small"/>
      <xs:element name="date" type="xs:date"/>
      <xs:element name="root"><xs:complexType><xs:sequence>
        <xs:element name="detail" minOccurs="0"><xs:complexType><xs:sequence>
          <xs:element name="when" type="xs:date"/>
        </xs:sequence><xs:attribute name="weight" type="xs:double"/>
          <xs:anyAttribute namespace="##targetNamespace" processContents="strict"/>
        </xs:complexType></xs:element>
        <xs:element ref="s:amount" maxOccurs="unbounded"/>
      </xs:sequence><xs:attribute ref="s:level"/>
        <xs:attribute name="count" type="xs:int"/>
        <xs:attribute name="enabled" type="xs:boolean"/>
      </xs:complexType></xs:element>
    ''', version=version)


def schema_value(schema, root, expression, *, parser_class=XPath2Parser,
                 xsd_version=None):
    proxy = AcceptanceSchemaProxy(schema)
    options = dict(namespaces=SCHEMA_NAMESPACES, schema=proxy)
    if xsd_version is not None:
        options['xsd_version'] = xsd_version
    parser = parser_class(**options)
    context = XPathContext(root, namespaces=SCHEMA_NAMESPACES, schema=proxy)
    return datatype_expression(expression, parser=parser, context=context)
