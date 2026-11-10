# feature: F11
"""Public serialization behavior, read with independent XML and JSON parsers."""
from velunara import VelunaraTypeError, VelunaraValueError, MissingContextError
from velunara.xpath30 import XPath30Parser
from velunara.xpath31 import XPath31Parser
from _helpers import read_xml, read_json
from F02_helpers import datatype_failure
from F11_helpers import (serialization_context, xml_parameter_element, serialization_text,
                         xml_fragment_content)


def test_default_xml_preserves_document_and_element_content():
    xml = ('<p:record xmlns:p="urn:record" xmlns:q="urn:detail" q:key="K&amp;7" plain="v">'
           '<q:title>A &amp; B<q:em>deep</q:em>end</q:title><p:empty/></p:record>')
    for expression in ('serialize(/)', 'serialize(/*)'):
        root = read_xml(serialization_text(expression, context=serialization_context(xml)))
        assert root.tag == '{urn:record}record'
        assert root.attrib == {'{urn:detail}key': 'K&7', 'plain': 'v'}
        assert [child.tag for child in root] == ['{urn:detail}title', '{urn:record}empty']
        assert root[0].text == 'A & B'
        assert len(root[0]) == 1
        assert root[0][0].tag == '{urn:detail}em'
        assert root[0][0].text == 'deep'
        assert root[0][0].tail == 'end'
        assert len(root[1]) == 0


def test_xml_refuses_missing_context_and_nonserializable_items():
    assert serialization_text('serialize((3, "ok"))') == '3 ok'
    datatype_failure('serialize(1)', MissingContextError, 'XPDY0002', parser=XPath30Parser())
    for item in ('/r/@flag', '/r/namespace::*', 'abs#1'):
        datatype_failure('serialize(' + item + ')', VelunaraTypeError, 'SENR0001',
                         parser=XPath30Parser(), context=serialization_context())
    # The refusal also holds for members reached through array flattening and in
    # either position of a mixed sequence, and for the map-option form of the call.
    for item in ('[/r/@flag]', '(1, [/r/@flag])', '[abs#1]', '(/r/a, /r/@flag)'):
        datatype_failure('serialize(' + item + ')', VelunaraTypeError, 'SENR0001',
                         parser=XPath31Parser(), context=serialization_context())
    datatype_failure('serialize(1, map{"method":"json"})', MissingContextError, 'XPDY0002',
                     parser=XPath31Parser())


def test_xml_options_and_sequence_normalization():
    # Each option form must carry the same user-visible controls.
    forms = (
        (XPath30Parser, '$options', xml_parameter_element('')),
        (XPath31Parser, 'map{}', None),
        (XPath31Parser, 'map{"method":"xml"}', None),
    )
    for parser_factory, options, xml_options in forms:
        text = serialization_text('serialize(/r, ' + options + ')',
                                  parser=parser_factory(),
                                  context=serialization_context(options=xml_options))
        assert not text.lstrip().startswith('<?xml')
        assert read_xml(text).tag == 'r'
    for parser_factory in (XPath30Parser, XPath31Parser):
        text = serialization_text('serialize(/r)', parser=parser_factory())
        assert not text.lstrip().startswith('<?xml')
        assert read_xml(text).tag == 'r'
    # XML is the method whether defaulted or named, and it keeps the option semantics.
    assert serialization_text('serialize((2,3), map{"method":"xml"})') == '2 3'
    assert serialization_text('serialize((2,3), map{"method":"xml","item-separator":"+"})') == '2+3'
    assert serialization_text('serialize(())') == ''
    # Only adjacent atomics take the default space: no separator is invented around nodes.
    for item, expected in (('(/r/a,/r/b)', '<a>one</a><b>two</b>'),
                           ('(1,/r/a,2,3)', '1<a>one</a>2 3'),
                           ('(/r/a,[/r/b,5,6])', '<a>one</a><b>two</b>5 6')):
        actual = serialization_text('serialize(' + item + ')')
        assert xml_fragment_content(actual) == xml_fragment_content(expected), item
    assert read_xml(serialization_text('serialize([/])')).tag == 'r'
    for parser_factory, options, xml_options, declared in (
        (XPath30Parser, '$options', xml_parameter_element('<omit-xml-declaration value="no"/>'), True),
        (XPath30Parser, '$options', xml_parameter_element('<omit-xml-declaration value="yes"/>'), False),
        (XPath31Parser, 'map{"omit-xml-declaration":false()}', None, True),
        (XPath31Parser, 'map{"omit-xml-declaration":true()}', None, False),
    ):
        text = serialization_text('serialize(/r, ' + options + ')', parser=parser_factory(),
                                  context=serialization_context(options=xml_options))
        assert text.lstrip().startswith('<?xml ') is declared
        assert read_xml(text).attrib == {'flag': 'yes'}
    assert serialization_text('serialize((4,true(),"end"))') == '4 true end'
    assert serialization_text('serialize([4,[true(),(),["end"]]])') == '4 true end'
    for parser_factory, options, xml_options in (
        (XPath30Parser, '$options', xml_parameter_element('<item-separator value="|~|"/>')),
        (XPath31Parser, 'map{"item-separator":"|~|"}', None),
    ):
        ctx = serialization_context(options=xml_options)
        assert serialization_text('serialize((4,true(),"end"), ' + options + ')',
                                  parser=parser_factory(), context=ctx) == '4|~|true|~|end'
        text = serialization_text('serialize((/r/a,/r/b), ' + options + ')',
                                  parser=parser_factory(), context=serialization_context(options=xml_options))
        parts = text.split('|~|')
        assert len(parts) == 2
        assert [(read_xml(part).tag, read_xml(part).text) for part in parts] == [('a', 'one'), ('b', 'two')]
        text = serialization_text('serialize((/,"end"), ' + options + ')',
                                  parser=parser_factory(), context=serialization_context(options=xml_options))
        parts = text.split('|~|')
        assert len(parts) == 2 and parts[1] == 'end'
        root = read_xml(parts[0])
        assert root.tag == 'r'
        assert [(child.tag, child.text) for child in root] == [('a', 'one'), ('b', 'two')]
        # The supplied separator also stands between atomic and node items, not around a lone item.
        text = serialization_text('serialize((1,/r/a,2,3), ' + options + ')', parser=parser_factory(),
                                  context=serialization_context(options=xml_options))
        parts = text.split('|~|')
        assert len(parts) == 4 and parts[0] == '1' and parts[2:] == ['2', '3']
        assert xml_fragment_content(parts[1]) == xml_fragment_content('<a>one</a>')
        text = serialization_text('serialize(/r/a, ' + options + ')', parser=parser_factory(),
                                  context=serialization_context(options=xml_options))
        assert xml_fragment_content(text) == xml_fragment_content('<a>one</a>')
    # A supplied empty separator is still a supplied separator.
    for parser_factory, options, xml_options in (
        (XPath30Parser, '$options', xml_parameter_element('<item-separator value=""/>')),
        (XPath31Parser, 'map{"item-separator":""}', None),
    ):
        assert serialization_text('serialize((2,3), ' + options + ')', parser=parser_factory(),
                                  context=serialization_context(options=xml_options)) == '23'
    assert serialization_text('serialize([4,[true(),(),["end"]]], map{"item-separator":"|~|"})') == '4|~|true|~|end'


def test_character_maps_replace_serialized_output_in_both_option_forms():
    xml = '<r code="?">why?</r>'
    for parser_factory, options, xml_options in (
        (XPath30Parser, '$options', xml_parameter_element(
            '<use-character-maps><character-map character="&lt;" map-string="["/>'
            '<character-map character="?" map-string="!"/></use-character-maps>')),
        (XPath31Parser, 'map{"use-character-maps":map{"<":"[", "?":"!"}}', None),
    ):
        baseline = serialization_text('serialize(/r)', parser=parser_factory(),
                                      context=serialization_context(xml))
        root = read_xml(baseline)
        assert root.tag == 'r' and root.attrib == {'code': '?'} and root.text == 'why?'
        replaced = serialization_text('serialize(/r, ' + options + ')', parser=parser_factory(),
                                      context=serialization_context(xml, options=xml_options))
        # Every literal source character must be replaced, including markup.
        # Reverse the disjoint replacements to read the complete original content,
        # without requiring separate serializations to choose identical XML syntax.
        assert '<' not in replaced and '?' not in replaced and '[' in replaced
        restored = replaced.replace('[', '<').replace('!', '?')
        assert xml_fragment_content(restored) == xml_fragment_content(xml)
        # Character references are valid XML spellings too; a replacement acts
        # on literal serialized characters, wherever they occur in the result.
        atomic = serialization_text('serialize("why?", ' + options + ')', parser=parser_factory(),
                                    context=serialization_context(xml, options=xml_options))
        assert '?' not in atomic
        assert xml_fragment_content(atomic.replace('!', '?')) == xml_fragment_content('why?')


def test_invalid_serialization_parameters_are_refused():
    assert serialization_text('serialize((2,3), map{"item-separator":"/"})') == '2/3'
    for body, code in (
        ('<item-separator value="a"/><item-separator value="b"/>', 'SEPM0019'),
        ('<omit-xml-declaration value="maybe"/>', 'SEPM0017'),
        ('<omit-xml-declaration/>', 'SEPM0017'),
        ('<item-separator/>', 'SEPM0017'),
        ('<use-character-maps bad="yes"/>', 'SEPM0017'),
        ('<use-character-maps><character-map character="ab" map-string="x"/></use-character-maps>', 'SEPM0017'),
        ('<use-character-maps><character-map character="" map-string="x"/></use-character-maps>', 'SEPM0017'),
        ('<omit-xml-declaration value="yes"/><omit-xml-declaration value="yes"/>', 'SEPM0019'),
    ):
        datatype_failure('serialize(/r, $options)', VelunaraValueError, code,
                         parser=XPath30Parser(),
                         context=serialization_context(options=xml_parameter_element(body)))
    for options, code, error_class in (
        ('map{"omit-xml-declaration":"yes"}', 'XPTY0004', VelunaraTypeError),
        ('map{"item-separator":7}', 'XPTY0004', VelunaraTypeError),
        ('map{"use-character-maps":"wrong"}', 'XPTY0004', VelunaraTypeError),
        ('map{"use-character-maps":map{3:"x"}}', 'XPTY0004', VelunaraTypeError),
        ('map{"use-character-maps":map{"a":3}}', 'XPTY0004', VelunaraTypeError),
        ('map{"use-character-maps":map{"ab":"x"}}', 'SEPM0016', VelunaraValueError),
        ('map{"use-character-maps":map{"":"x"}}', 'SEPM0016', VelunaraValueError),
    ):
        datatype_failure('serialize(/r, ' + options + ')', error_class, code,
                         parser=XPath31Parser(), context=serialization_context())


def test_json_preserves_atomic_collection_and_empty_values():
    cases = (
        ("'snow 雪 / line\nquote\"'", 'snow 雪 / line\nquote"'),
        ('concat("back", codepoints-to-string(92), "slash", codepoints-to-string(9), "tab")', 'back\\slash\ttab'),
        ('true()', True), ('false()', False), ('-17', -17), ('2.5e0', 2.5), ('12.34', 12.34),
        ('0', 0), ('""', ''),
        ('()', None), ('map{}', {}), ('[]', []),
        ('[(),false(),[7,"v"]]', [None, False, [7, 'v']]),
        # Falsy members are values: only an empty sequence member becomes null.
        ('[[],map{},0,"",false()]', [[], {}, 0, '', False]),
        ('[[()],[[]]]', [[None], [[]]]),
        ('map{"z":0,"e":"","f":false(),"a":[],"m":map{}}', {'z': 0, 'e': '', 'f': False, 'a': [], 'm': {}}),
        ('map{"m":map{"k":[1,map{"d":"x"}]},"s":"y"}', {'m': {'k': [1, {'d': 'x'}]}, 's': 'y'}),
        ('[map{"e":()}]', [{'e': []}]),
        ('map{"x":[()]}', {'x': [None]}),
    )
    for item, expected in cases:
        actual = read_json(serialization_text('serialize(' + item + ', map{"method":"json"})'))
        assert actual == expected, item
        if isinstance(expected, bool) or expected is None:
            assert actual is expected, item
        elif isinstance(expected, (int, float)):
            assert type(actual) in (int, float), item
    actual = read_json(serialization_text(
        'serialize(map{"title":"雪","n":7,"ok":true(),"empty":(),"items":[(),2,"x"]}, '
        'map{"method":"json"})'))
    assert isinstance(actual, dict)
    assert set(actual) == {'title', 'n', 'ok', 'empty', 'items'}
    assert actual['empty'] == []
    assert {key: value for key, value in actual.items() if key != 'empty'} == {
        'title': '雪', 'n': 7, 'ok': True, 'items': [None, 2, 'x']}


def test_json_nodes_contain_parseable_xml_content():
    xml = '<p:r xmlns:p="urn:json-node" key="A&amp;B"><p:c>snow 雪 &amp; sun</p:c></p:r>'
    for item in ('/', '/*'):
        value = read_json(serialization_text('serialize(' + item + ', map{"method":"json"})',
                                             context=serialization_context(xml)))
        assert isinstance(value, str)
        root = read_xml(value)
        assert root.tag == '{urn:json-node}r'
        assert root.attrib == {'key': 'A&B'}
        assert len(root) == 1
        assert root[0].tag == '{urn:json-node}c'
        assert root[0].text == 'snow 雪 & sun'


def test_json_refuses_multiple_items_nonfinite_numbers_and_functions():
    assert read_json(serialization_text('serialize(17, map{"method":"json"})')) == 17
    for item, code in (
        ('(1,2)', 'SERE0023'),
        ('([1],[2])', 'SERE0023'),
        ('(map{},1)', 'SERE0023'),
        ('[xs:double("INF")]', 'SERE0020'),
        ('[1,[xs:double("NaN")]]', 'SERE0020'),
        ('map{"a":[xs:double("-INF")]}', 'SERE0020'),
        ('map{"a":xs:double("NaN")}', 'SERE0020'),
        ('[abs#1]', 'SERE0021'),
        ('map{"f":abs#1}', 'SERE0021'),
        ('map{"k":[1,abs#1]}', 'SERE0021'),
        ('xs:double("NaN")', 'SERE0020'),
        ('xs:double("INF")', 'SERE0020'),
        ('xs:double("-INF")', 'SERE0020'),
        ('abs#1', 'SERE0021'),
    ):
        datatype_failure('serialize(' + item + ', map{"method":"json"})',
                         VelunaraTypeError, code, parser=XPath31Parser(),
                         context=serialization_context())
