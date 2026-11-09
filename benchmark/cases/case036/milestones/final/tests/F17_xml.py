# feature: F17
"""Public XML keywords exercised through real Velun execution."""
from _helpers import temporary_workspace, write_file, read_xml
from F17_helpers import XMLWorkflow


def test_parse_sources_and_input_errors():
    with temporary_workspace() as directory:
        text = '<catalog><!--discard--><?inspect data?><item code="a">café</item></catalog>'
        path = write_file(directory / 'input.xml', text)
        w = XMLWorkflow(directory)
        for source in (str(path), text, text.encode('utf-8')):
            root = w.call('Parse Xml', source)
            selected = w.call('Get Element', root)
            w.inspect('($' + selected.name + '.tag, [(e.tag, e.text, dict(e.attrib)) for e in $' + selected.name + '])',
                      ('catalog', [('item', 'café', {'code': 'a'})]))
        # A DTD constraint is deliberately unmet: ordinary parsing is not validation.
        root = w.call('Parse Xml', '<!DOCTYPE root [<!ELEMENT root (required)><!ELEMENT required EMPTY>]><root><other/></root>')
        w.inspect('[(e.tag) for e in $' + root.name + ']', ['other'])
        w.reject('Parse Xml', '<catalog><item></catalog>')
        w.reject('Parse Xml', str(directory / 'missing.xml'))
        w.run_and_verify()


def test_selection_order_predicates_and_cardinality():
    xml = '<r><group><item id="b">B</item><item id="a">A</item><other>O</other></group><item id="c">C</item></r>'
    with temporary_workspace() as directory:
        w = XMLWorkflow(directory)
        for path, expected in [('group/item', ['B', 'A']), ('.//item', ['B', 'A', 'C']),
                               ('group/*', ['B', 'A', 'O']), (".//item[@id='a']", ['A']),
                               ('group/item[2]', ['A']), ('absent', [])]:
            nodes = w.call('Get Elements', xml, path)
            w.inspect('[e.text for e in $' + nodes.name + ']', expected)
            w.check(w.call('Get Element Count', xml, path), len(expected))
        children = w.call('Get Child Elements', xml, 'group')
        w.inspect('[e.tag for e in $' + children.name + ']', ['item', 'item', 'other'])
        one = w.call('Get Element', xml, "group/item[@id='a']")
        w.inspect('$' + one.name + '.text', 'A')
        w.call('Element Should Exist', xml, './/item')
        w.call('Element Should Not Exist', xml, 'absent')
        w.reject('Get Element', xml, 'absent', identifies=('absent',))
        w.reject('Get Element', xml, './/item', identifies=('.//item',))
        w.reject('Get Element Text', xml, 'group/item', identifies=('group/item',))
        w.reject('Element Should Exist', xml, 'absent', identifies=('absent',))
        w.reject('Element Should Not Exist', xml, './/item', identifies=('.//item',))
        w.run_and_verify()


def test_content_and_comparison_options():
    xml = '<r><p code="ab7" extra="kept">Hello <b>bold<i>!</i></b> end</p>OUTSIDE<empty/></r>'
    with temporary_workspace() as directory:
        w = XMLWorkflow(directory)
        p = w.call('Get Element', xml, 'p')
        w.inspect('$' + p.name + '.tag', 'p')
        w.check(w.call('Get Element Text', p), 'Hello bold! end')
        w.check(w.call('Get Elements Texts', xml, '*'), ['Hello bold! end', ''])
        w.check(w.call('Get Element Attributes', p), {'code': 'ab7', 'extra': 'kept'})
        w.check(w.call('Get Element Attribute', p, 'code'), 'ab7')
        w.check(w.call('Get Element Attribute', p, 'missing'), None)
        w.check(w.call('Get Element Attribute', p, 'missing', default=['caller', 8]), ['caller', 8])
        w.check(w.call('Get Element Text', '<p>  alpha\n beta\t gamma  </p>', normalize_whitespace=True), 'alpha beta gamma')
        w.check(w.call('Get Element Text', '<p>  alpha\n beta\t gamma  </p>'), '  alpha\n beta\t gamma  ')
        w.call('Element Text Should Be', p, 'Hello bold! end')
        w.call('Element Text Should Match', p, 'Hello *[!?] end')
        w.call('Element Attribute Should Be', p, 'code', 'ab7')
        w.call('Element Attribute Should Match', p, 'code', 'a?[0-9]')
        w.call('Element Should Not Have Attribute', p, 'missing')
        w.call('Elements Should Be Equal', p, '<p extra="kept" code="ab7">Hello <b>bold<i>!</i></b> end</p>')
        w.call('Elements Should Match', p, '<p code="a?[0-9]" extra="*">Hello <b>b*<i>?</i></b>*</p>')
        # Excluding children skips child content and count, but not the root's own tag, attributes or text.
        w.call('Elements Should Be Equal', '<r k="v">A<x/><y/></r>', '<r k="v">A<different/></r>', exclude_children=True)
        w.call('Elements Should Be Equal', '<r> a\n b <x> c </x> d </r>', '<r>a b<x>c</x>d</r>', normalize_whitespace=True)
        # Both sides are unsorted, so ordering only one of them is not enough.
        w.call('Elements Should Be Equal', '<r><z/><a>first</a><a>second</a></r>', '<r><a>first</a><z/><a>second</a></r>', sort_children=True)
        for keyword, args, kwargs, identifies in [
            ('Element Text Should Be', (xml, 'wrong'), {'xpath': 'p'}, ('wrong',)),
            ('Element Text Should Match', (xml, 'absent*'), {'xpath': 'p'}, ('absent',)),
            ('Element Attribute Should Be', (xml, 'missing', 'value'), {'xpath': 'p'}, ('value',)),
            ('Element Attribute Should Match', (xml, 'missing', '*'), {'xpath': 'p'}, ('missing',)),
            ('Element Attribute Should Be', (xml, 'code', 'wrong'), {'xpath': 'p'}, ('wrong',)),
            ('Element Attribute Should Match', (xml, 'code', 'z*'), {'xpath': 'p'}, ('z*',)),
            ('Element Should Not Have Attribute', (xml, 'code'), {'xpath': 'p'}, ('code',)),
            ('Elements Should Be Equal', ('<r/>', '<other/>'), {}, ('other',)),
            ('Elements Should Be Equal', ('<r a="x"/>', '<r a="y"/>'), {}, ('a',)),
            ('Elements Should Be Equal', ('<r a="x"/>', '<r a="x" b="y"/>'), {}, ('b',)),
            ('Elements Should Be Equal', ('<r><a><b>actual</b></a></r>', '<r><a><b>expected</b></a></r>'), {}, ('expected',)),
            ('Elements Should Be Equal', ('<r k="v">actual<x/></r>', '<r k="v">expected<x/></r>'), {'exclude_children': True}, ('expected',)),
            ('Elements Should Be Equal', ('<r k="v">A<x/></r>', '<r k="w">A<x/></r>'), {'exclude_children': True}, ('k',)),
            ('Elements Should Be Equal', ('<r>actual</r>', '<r>expected</r>'), {}, ('expected',)),
            ('Elements Should Be Equal', ('<r><a/>actual</r>', '<r><a/>expected</r>'), {}, ('expected',)),
            ('Elements Should Be Equal', ('<r><a/><b/></r>', '<r><b/><a/></r>'), {}, ()),
            ('Elements Should Be Equal', ('<r> a  b </r>', '<r>a b</r>'), {}, ()),
            ('Elements Should Be Equal', ('<r><a>first</a><a>second</a></r>', '<r><a>second</a><a>first</a></r>'), {'sort_children': True}, ()),
            ('Elements Should Match', ('<r a="x">text</r>', '<r a="z*">*</r>'), {}, ('a',)),
            ('Elements Should Match', ('<r>text</r>', '<r>z*</r>'), {}, ()),
        ]:
            w.reject(keyword, *args, identifies=identifies, **kwargs)
        w.run_and_verify()


def test_edit_returned_document_and_explicit_save():
    with temporary_workspace() as directory:
        original = '<r><old a="1">before</old>tail<gone/><clear a="x">text<child/></clear></r>'
        path = write_file(directory / 'document.xml', original)
        w = XMLWorkflow(directory)
        root = w.call('Set Element Tag', str(path), 'new', xpath='old')
        root = w.call('Set Element Text', root, 'café & tea', tail='AFTER', xpath='new')
        root = w.call('Set Element Attribute', root, 'id', 'edited', xpath='new')
        root = w.call('Remove Element Attribute', root, 'a', xpath='new')
        root = w.call('Add Element', root, '<added k="v">saved</added>')
        root = w.call('Remove Element', root, 'gone')
        root = w.call('Clear Element', root, 'clear')
        w.inspect('[(e.tag, e.text, e.tail, dict(e.attrib), len(e)) for e in $' + root.name + ']',
                  [('new', 'café & tea', 'AFTER', {'id': 'edited'}, 0), ('clear', None, None, {}, 0), ('added', 'saved', None, {'k': 'v'}, 0)])
        w.inspect('pathlib.Path(' + repr(str(path)) + ').read_text()', original, modules='pathlib')
        serialized = w.call('Element To String', root)
        w.inspect('[(e.tag, e.text, e.tail, dict(e.attrib)) for e in xml.etree.ElementTree.fromstring($' + serialized.name + ')]',
                  [('new', 'café & tea', 'AFTER', {'id': 'edited'}), ('clear', None, None, {}), ('added', 'saved', None, {'k': 'v'})], modules='xml.etree.ElementTree')
        w.call('Save XML', root, str(path))
        w.run_and_verify()
        saved = read_xml(path).getroot()
        assert saved.tag == 'r'
        assert [(e.tag, e.text, e.tail, dict(e.attrib), len(e)) for e in saved] == [
            ('new', 'café & tea', 'AFTER', {'id': 'edited'}, 0), ('clear', None, None, {}, 0), ('added', 'saved', None, {'k': 'v'}, 0)]


def test_namespace_selection_and_saved_content():
    xml = '<r xmlns:a="urn:alpha" xmlns:b="urn:beta"><a:item>A</a:item><b:item>B</b:item></r>'
    with temporary_workspace() as directory:
        w = XMLWorkflow(directory)
        for label, options, tags in [
            ('default', {}, ['item', 'item']),
            ('qualified', {'keep_clark_notation': True}, ['{urn:alpha}item', '{urn:beta}item']),
            ('removed', {'strip_namespaces': True}, ['item', 'item']),
            ('both', {'keep_clark_notation': True, 'strip_namespaces': True}, ['{urn:alpha}item', '{urn:beta}item']),
        ]:
            root = w.call('Parse Xml', xml, **options)
            w.inspect('[e.tag for e in $' + root.name + ']', tags)
            if options.get('keep_clark_notation'):
                for uri, text in [('urn:alpha', 'A'), ('urn:beta', 'B')]:
                    w.check(w.call('Get Element Text', root, '{' + uri + '}item'), text)
            else:
                w.check(w.call('Get Elements Texts', root, 'item'), ['A', 'B'])
            w.call('Save XML', root, str(directory / (label + '.xml')))
        w.run_and_verify()
        for label in ('default', 'qualified', 'both', 'removed'):
            saved = read_xml(directory / (label + '.xml')).getroot()
            assert [(e.tag, e.text) for e in saved] == (
                [('item', 'A'), ('item', 'B')] if label == 'removed' else
                [('{urn:alpha}item', 'A'), ('{urn:beta}item', 'B')])


def test_full_xpath_results_and_context():
    # Independent XPath 1.0 oracle: the caller's document fixes node order,
    # sums, string conversion, axes, and context position without a product round trip.
    xml = '<r><group><item n="2">red</item><item n="7">blue</item></group><item n="5">green</item></r>'
    with temporary_workspace() as directory:
        w = XMLWorkflow(directory, full_xpath=True)
        root = w.call('Parse Xml', xml)
        for expression, context, expected in [
            ('count(.//item)', '.', 3.0), ('sum(.//item/@n)', '.', 14.0),
            ('string(item[last()])', 'group', 'blue'),
            ('boolean(preceding-sibling::item[@n="2"])', 'group/item[2]', True),
            ('boolean(following-sibling::item)', 'group/item[2]', False),
            ('concat(name(..), ":", string(@n))', 'group/item[2]', 'group:7'),
            ('item/@n', 'group', ['2', '7']), ('item/text()', 'group', ['red', 'blue']),
        ]:
            value = w.call('Evaluate Xpath', root, expression, context=context)
            # XPath scalar strings may be string subclasses; compare their value.
            if isinstance(expected, str):
                w.inspect('str($' + value.name + ')', expected)
            elif isinstance(expected, list):
                w.inspect('[str(v) for v in $' + value.name + ']', expected)
            else:
                w.check(value, expected)
        nodes = w.call('Evaluate Xpath', root, './/item[@n > 2]')
        w.inspect('[(e.tag, e.text, e.get("n")) for e in $' + nodes.name + ']', [('item', 'blue', '7'), ('item', 'green', '5')])
        w.run_and_verify()


def test_tree_positions_copy_isolation_and_tail_controls():
    with temporary_workspace() as directory:
        w = XMLWorkflow(directory)
        root = w.call('Parse Xml', '<r><first/><last/></r>')
        original = w.call('Parse Xml', '<branch a="x"><leaf>original</leaf></branch>')
        copy = w.call('Copy Element', original)
        w.call('Add Element', root, original)
        w.call('Add Element', root, '<inserted/>', index=1)
        w.inspect('[e.tag for e in $' + root.name + ']', ['first', 'inserted', 'last', 'branch'])
        w.call('Set Element Text', original, 'changed', xpath='leaf')
        w.check(w.call('Get Element Text', copy, 'leaf'), 'original')
        w.check(w.call('Get Element Text', root, 'branch/leaf'), 'original')
        w.call('Set Element Text', copy, 'copy only', xpath='leaf')
        w.check(w.call('Get Element Text', original, 'leaf'), 'changed')
        for remove_tail in (False, True):
            # 'last' follows a sibling: its kept tail must stay after that sibling's content.
            for path, expected in [('drop', 'ABCDEF' if not remove_tail else 'ACDEF'),
                                   ('keep/drop', 'ABCDEF' if not remove_tail else 'ABCEF'),
                                   ('last', 'ABCDEF' if not remove_tail else 'ABCDE')]:
                source = '<r>A<drop/>B<keep>C<drop/>D</keep>E<last/>F</r>'
                changed = w.call('Remove Element', source, path, **({'remove_tail': True} if remove_tail else {}))
                w.check(w.call('Get Element Text', changed), expected)
            changed = w.call('Remove Elements', '<r>A<x/>B<x/>C<y/>D</r>', 'x', **({'remove_tail': True} if remove_tail else {}))
            w.inspect('[e.tag for e in $' + changed.name + ']', ['y'])
            w.check(w.call('Get Element Text', changed), 'ABCD' if not remove_tail else 'AD')
            cleared = w.call('Clear Element', '<r>A<target a="x">inside<leaf/></target>TAIL<end/></r>', 'target', **({'clear_tail': True} if remove_tail else {}))
            w.inspect('[(e.tag, dict(e.attrib), e.text, len(e)) for e in $' + cleared.name + ']', [('target', {}, None, 0), ('end', {}, None, 0)])
            w.check(w.call('Get Element Text', cleared), 'ATAIL' if not remove_tail else 'A')
        w.reject('Remove Element', '<r><child/></r>', '.')
        w.run_and_verify()
