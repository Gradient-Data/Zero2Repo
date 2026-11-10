# feature: F11
"""Serialization inputs and bounded calls through public XPath evaluation."""
import xml.etree.ElementTree as ET
from velunara import XPathContext
from velunara.xpath31 import XPath31Parser
from F02_helpers import datatype_expression
from _helpers import read_xml


def serialization_context(xml='<r flag="yes"><a>one</a><b>two</b></r>', *, options=None):
    variables = {} if options is None else {'options': options}
    return XPathContext(ET.ElementTree(ET.fromstring(xml)), variables=variables)


def xml_parameter_element(body):
    return ET.fromstring(
        '<serialization-parameters xmlns="http://www.w3.org/2010/xslt-xquery-serialization">'
        + body + '</serialization-parameters>')


def serialization_text(expression, *, parser=None, context=None):
    value = datatype_expression(
        expression, parser=XPath31Parser() if parser is None else parser,
        context=serialization_context() if context is None else context)
    assert isinstance(value, str), value
    return value


def xml_fragment_content(text):
    """Parse XML fragment content independently, retaining names and mixed text.

    A temporary wrapper permits multiple top-level elements and atomic text.
    Parsing failures propagate. Lexical choices such as quote style, character
    references and namespace prefixes do not affect the returned content tree.
    """
    def content(element):
        return (element.tag, dict(element.attrib), element.text or '',
                [(content(child), child.tail or '') for child in element])

    return content(read_xml('<fragment>' + text + '</fragment>'))
