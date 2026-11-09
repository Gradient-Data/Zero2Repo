# feature: F04
"""Public evaluation and context acceptance tests.

Expected values use the supplied XML and the XPath Recommendations cited in
FP-04, not agreement between different product evaluation paths.
"""
import datetime as dt
import time
from decimal import Decimal
import xml.etree.ElementTree as ET

from lxml import etree as LE

from velunara import (
    select, iter_select, Selector, XPathContext, XPath1Parser, XPath2Parser,
    VelunaraError, VelunaraTypeError, VelunaraValueError,
    VelunaraNameError, VelunaraSyntaxError, MissingContextError,
)
from velunara.xpath3 import XPath30Parser, XPath31Parser
from _helpers import observe, result_items
from F04_helpers import context_results
from F02_helpers import datatype_expression, datatype_failure, datatype_rejection


def test_complete_iterative_and_prepared_results():
    root = ET.fromstring('<r><v n="2">red</v><v n="5">blue</v><v n="8">gold</v></r>')
    for expression, expected in (
        ('v[@n > 3]', [root[1], root[2]]),
        ('v[@n > 3]/text()', ['blue', 'gold']),
        ('sum(v/@n)', [15]),
        ('v[@n > 20]', []),
    ):
        prepared = Selector(expression)
        complete = [select(root, expression), prepared.select(root)]
        for value in complete:
            items = result_items(value)
            assert items == expected
            if expression == 'v[@n > 3]':
                assert all(a is b for a, b in zip(items, expected))
        for call, args in ((iter_select, (root, expression)),
                           (prepared.iter_select, (root,))):
            outcome = observe(call, *args, consume=True)
            assert outcome.value == expected
            if expression == 'v[@n > 3]':
                assert all(a is b for a, b in zip(outcome.value, expected))
    # Item-at-a-time consumption: the returned objects are iterators.
    for lazy in (iter_select(root, 'v[@n > 3]'), Selector('v[@n > 3]').iter_select(root)):
        assert next(lazy) is root[1]
        assert next(lazy) is root[2]
        assert next(lazy, None) is None


def test_prepared_expression_uses_current_tree_and_bindings():
    first = ET.fromstring('<r><v n="1"/><v n="4"/></r>')
    second = ET.fromstring('<r><v n="7"/><v n="9"/></r>')
    prepared = Selector('v[@n > $limit]')
    for root, limit, expected in ((first, 2, [first[1]]),
                                   (second, 8, [second[1]]),
                                   (second, 6, list(second)),
                                   (first, 9, [])):
        value = prepared.select(root, variables={'limit': limit})
        assert value == expected
        assert all(a is b for a, b in zip(value, expected))
        outcome = observe(prepared.iter_select, root, variables={'limit': limit}, consume=True)
        assert outcome.value == expected
        assert all(a is b for a, b in zip(outcome.value, expected))
    for call, consume in ((prepared.select, False), (prepared.iter_select, True)):
        outcome = observe(call, second, exceptions=(VelunaraError,), consume=consume)
        assert isinstance(outcome.error, VelunaraNameError)
        assert outcome.error.code == 'err:XPST0008'
    # Current data: the same tree object and binding mapping, changed between uses.
    third = ET.fromstring('<r><v n="7"/><v n="9"/></r>')
    bindings = {'limit': 8}
    assert prepared.select(third, variables=bindings) == [third[1]]
    assert observe(prepared.iter_select, third, variables=bindings,
                   consume=True).value == [third[1]]
    third.append(ET.Element('v', n='10'))
    bindings['limit'] = 6
    for value in (prepared.select(third, variables=bindings),
                  observe(prepared.iter_select, third, variables=bindings, consume=True).value):
        assert value == list(third)
        assert all(a is b for a, b in zip(value, third))


def test_language_modes_and_default():
    root = ET.fromstring('<r/>')
    # Version-specific syntax supplies positive evidence for every mode.
    for factory, expression, expected in (
        (XPath1Parser, '7 div 2', [3.5]),
        (XPath2Parser, 'for $x in 2 to 4 return $x * 3', [6, 9, 12]),
        (XPath30Parser, '(function($x) {$x + 4})(6)', [10]),
        (XPath31Parser, 'map {"answer": 13}?answer', [13]),
    ):
        assert result_items(select(root, expression, parser=factory)) == expected
        assert context_results(expression, parser=factory(), context=XPathContext(root)) == expected
    assert result_items(select(root, 'for $x in 2 to 3 return $x')) == [2, 3]
    # The default applies to every public selection entry point.
    assert observe(iter_select, root, 'for $x in 2 to 3 return $x', consume=True).value == [2, 3]
    default_prepared = Selector('for $x in 2 to 3 return $x')
    assert result_items(default_prepared.select(root)) == [2, 3]
    assert observe(default_prepared.iter_select, root, consume=True).value == [2, 3]
    for call in (lambda: iter_select(root, '(function($x) {$x})(1)'),
                 lambda: Selector('(function($x) {$x})(1)').iter_select(root)):
        outcome = observe(call, exceptions=(VelunaraError,), consume=True)
        assert isinstance(outcome.error, (VelunaraSyntaxError, VelunaraTypeError))
        assert outcome.error.code in ('err:XPST0003', 'err:XPST0017')
    for factory, expression in ((XPath1Parser, '1 to 3'),
                                (XPath2Parser, '(function($x) {$x})(1)'),
                                (XPath30Parser, 'map {"x": 1}')):
        outcome = observe(select, root, expression, parser=factory,
                          exceptions=(VelunaraError,))
        assert isinstance(outcome.error, (VelunaraSyntaxError, VelunaraTypeError))
        assert outcome.error.code in ('err:XPST0003', 'err:XPST0017')
    outcome = observe(select, root, '(function($x) {$x})(1)',
                      exceptions=(VelunaraError,))
    assert isinstance(outcome.error, (VelunaraSyntaxError, VelunaraTypeError))
    assert outcome.error.code in ('err:XPST0003', 'err:XPST0017')


def test_rootless_static_atomic_and_missing_context():
    assert datatype_expression('6 * 7') == 42
    assert datatype_expression('. + 5', context=XPathContext(item=12)) == 17
    assert result_items(select(None, '. + 5', item=12)) == [17]
    element = ET.fromstring('<r><a k="1">t</a></r>')
    assert result_items(select(None, 'a/text()', item=element)) == ['t']
    assert result_items(select(None, 'a/@k', item=element)) == ['1']
    datatype_rejection(XPathContext, error_class=VelunaraTypeError)
    for expression in ('.', 'position()', '/r', '..', 'parent::*', 'v', '@a'):
        datatype_failure(expression, MissingContextError, 'XPDY0002')


def test_focus_tree_boundary_position_and_size():
    for module in (ET, LE):
        root = module.fromstring('<r><group><leaf>inside</leaf></group>'
                                 '<other>outside</other></r>')
        for context, expression, expected in (
            (XPathContext(root), 'name(.)', ['r']),
            (XPathContext(root), '(position(), last())', [1, 1]),
            (XPathContext(root, position=3, size=7), '(position(), last())', [3, 7]),
            (XPathContext(root, item=root[0], position=3, size=7),
             '(name(.), position(), last(), leaf/text())', ['group', 3, 7, 'inside']),
            (XPathContext(root, item=root[0]), '/r/other/text()', ['outside']),
            (XPathContext(root[0]), '/r/other/text()', []),
            (XPathContext(root[0]), 'leaf/text()', ['inside']),
            (XPathContext(root, item=root[0]), '../other/text()', ['outside']),
            (XPathContext(root[0]), '../other/text()', []),
        ):
            assert context_results(expression, context=context) == expected
        # Public selection entry points apply the same focus defaults and choices.
        prepared = Selector('(position(), last())')
        assert select(root, '(position(), last())') == [1, 1]
        assert observe(iter_select, root, '(position(), last())', consume=True).value == [1, 1]
        assert prepared.select(root) == [1, 1]
        assert observe(prepared.iter_select, root, consume=True).value == [1, 1]
        assert select(root, '(name(.), position(), last())', item=root[0],
                      position=2, size=5) == ['group', 2, 5]
        assert result_items(select(root, '/r/other/text()', item=root[0])) == ['outside']
        assert select(root[0], '/r/other/text()') == []


def test_variable_atomic_node_sequence_and_namespace_binding():
    root = ET.fromstring('<r><v>red</v><v>blue</v></r>')
    bindings = {'a': 11, 'node': root[1], 'seq': [2, 5, 9],
                '{urn:left}x': 17, '{urn:right}x': 23}
    context = XPathContext(root, variables=bindings)
    parser = XPath2Parser(namespaces={'l': 'urn:left', 'r': 'urn:right'})
    assert datatype_expression('($a + 3, $seq, $l:x, $r:x)',
                               parser=parser, context=context) == [14, 2, 5, 9, 17, 23]
    outcome = observe(lambda: parser.parse('$node').select_results(context), consume=True)
    assert len(outcome.value) == 1
    assert outcome.value[0] is root[1]
    assert context_results('$node/text()', parser=parser, context=context) == ['blue']
    assert datatype_expression('$empty', context=XPathContext(root, variables={'empty': []})) == []
    datatype_failure('$missing', VelunaraNameError, 'XPST0008', context=context)
    datatype_failure('$unbound:x', VelunaraNameError, 'XPST0081', context=context)


def test_static_namespaces_and_base_uri_are_used():
    root = ET.fromstring('<r xmlns:a="urn:one" xmlns:b="urn:two">'
                         '<a:v>first</a:v><b:v>second</b:v></r>')
    for uri, expected in (('urn:one', ['first']), ('urn:two', ['second'])):
        parser = XPath2Parser(namespaces={'p': uri}, base_uri='https://example.org/a/b/')
        assert context_results('p:v/text()', parser=parser,
                                   context=XPathContext(root)) == expected
        assert result_items(select(root, 'p:v/text()', namespaces={'p': uri})) == expected
        assert str(datatype_expression('resolve-uri("../c.xml")', parser=parser)) == \
            'https://example.org/a/c.xml'
    parser = XPath2Parser(base_uri='https://example.org/other/')
    assert str(datatype_expression('resolve-uri("c.xml")', parser=parser)) == \
        'https://example.org/other/c.xml'


def test_context_clock_and_implicit_timezone():
    fixed = dt.datetime(2004, 2, 29, 23, 45, 6, 123456,
                        tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    context = XPathContext(item=1, current_dt=fixed, timezone='-04:00')
    # Read calendar fields rather than depending on host tzinfo display names.
    expression = ('(year-from-dateTime(current-dateTime()), '
                  'month-from-dateTime(current-dateTime()), '
                  'day-from-dateTime(current-dateTime()), '
                  'hours-from-dateTime(current-dateTime()), '
                  'minutes-from-dateTime(current-dateTime()), '
                  'seconds-from-dateTime(current-dateTime()), '
                  'year-from-date(current-date()), month-from-date(current-date()), '
                  'day-from-date(current-date()), hours-from-time(current-time()), '
                  'minutes-from-time(current-time()), seconds-from-time(current-time()), '
                  'hours-from-duration(timezone-from-dateTime(current-dateTime())), '
                  'minutes-from-duration(timezone-from-dateTime(current-dateTime())), '
                  'hours-from-duration(timezone-from-date(current-date())), '
                  'minutes-from-duration(timezone-from-time(current-time())))')
    expected = [2004, 2, 29, 23, 45, Decimal('6.123456'),
                2004, 2, 29, 23, 45, Decimal('6.123456'), 5, 30, 5, 30]
    for _ in range(2):
        assert context_results(expression, context=context) == expected
    assert datatype_expression('hours-from-duration(implicit-timezone())', context=context) == -4
    assert datatype_expression('string(adjust-dateTime-to-timezone(xs:dateTime("2001-01-01T12:00:00Z")))',
                                   context=context) == '2001-01-01T08:00:00-04:00'
    # The implicit timezone completes a timezone-less operand in calendar subtraction.
    for zone, expected_difference in (('-04:00', 'PT4H'), ('+05:30', '-PT5H30M')):
        zoned = XPathContext(item=1, timezone=zone)
        for expression in ('string(xs:dateTime("2001-01-01T12:00:00") - '
                           'xs:dateTime("2001-01-01T12:00:00Z"))',
                           'string(xs:time("12:00:00") - xs:time("12:00:00Z"))'):
            assert datatype_expression(expression, context=zoned) == expected_difference
    assert time.timezone == 0, 'The acceptance clock-default check requires a UTC host'
    before = dt.datetime.now()
    local = XPathContext(item=1)
    observed = datatype_expression('current-dateTime()', context=local)
    after = dt.datetime.now()
    sample = dt.datetime(observed.year, observed.month, observed.day, observed.hour,
                         observed.minute, observed.second, observed.microsecond)
    assert before <= sample <= after
    date_value = datatype_expression('current-date()', context=local)
    time_value = datatype_expression('current-time()', context=local)
    assert (date_value.year, date_value.month, date_value.day) == \
        (sample.year, sample.month, sample.day)
    assert (time_value.hour, time_value.minute, time_value.second, time_value.microsecond) == \
        (sample.hour, sample.minute, sample.second, sample.microsecond)
    assert datatype_expression('current-dateTime()', context=local) == observed
    assert datatype_expression('seconds-from-duration(implicit-timezone())', context=local) == 0
    assert datatype_expression('string(adjust-time-to-timezone(xs:time("12:00:00+02:00")))',
                                   context=XPathContext(item=1, timezone='+05:30')) == \
        '15:30:00+05:30'


def test_variable_type_declarations_check_bound_values():
    root = ET.fromstring('<r/>')
    datatype_rejection(XPath2Parser, variable_types={'v': 'xs:notAType'},
                       error_class=VelunaraValueError)
    datatype_rejection(XPath2Parser, variable_types={'a': 'xs:integer', 'v': 'xs:notAType'},
                       error_class=VelunaraValueError)
    for declaration, value, expected in (('xs:integer', 7, [7]),
                                          ('xs:integer+', [2, 8], [2, 8]),
                                          ('xs:integer*', [1, 2, 3], [1, 2, 3]),
                                          ('xs:integer?', [], [])):
        assert result_items(select(root, '$v', variable_types={'v': declaration},
                                   variables={'v': value})) == expected
    for declaration, value in (('xs:integer', 'text'), ('xs:integer', [1, 2]),
                                ('xs:integer+', []), ('xs:integer?', [1, 2]),
                                ('xs:integer*', [2, 'text']), ('xs:integer+', [1, 'x'])):
        outcome = observe(select, root, '$v', variable_types={'v': declaration},
                          variables={'v': value}, exceptions=(VelunaraError,))
        assert isinstance(outcome.error, VelunaraTypeError)
        assert outcome.error.code == 'err:XPDY0050'
    # A declared but unbound referenced variable is still a missing variable.
    outcome = observe(select, root, '$v', variable_types={'v': 'xs:integer?'},
                      exceptions=(VelunaraError,))
    assert isinstance(outcome.error, VelunaraNameError)
    assert outcome.error.code == 'err:XPST0008'
    assert result_items(select(root, '$v', variables={'v': [3, 'text', root]})) == [3, 'text', root]


def test_document_and_collection_type_declarations():
    uri = 'https://example.org/data'
    root = ET.fromstring('<r><v/><v/></r>')
    document = ET.ElementTree(root)
    context = XPathContext(root, documents={uri: document},
                           collections={uri: list(root)}, default_collection=list(root))
    for options in ({'document_types': {uri: 'unknown()'}},
                    {'collection_types': {uri: 'unknown()*'}},
                    {'default_collection_type': 'unknown()*'},
                    {'document_types': {'https://example.org/ok': 'document-node()',
                                        uri: 'unknown()'}},
                    {'collection_types': {'https://example.org/ok': 'node()*',
                                          uri: 'unknown()*'}}):
        datatype_rejection(XPath2Parser, error_class=VelunaraValueError, **options)
    for options in ({}, {'document_types': {uri: 'document-node()'},
                         'collection_types': {uri: 'element()+'},
                         'default_collection_type': 'element()+'}):
        parser = XPath2Parser(**options)
        assert datatype_expression('count(doc("https://example.org/data")/r/v)',
                                   parser=parser, context=context) == 2
        for expression in ('collection("https://example.org/data")', 'collection()'):
            outcome = observe(lambda: parser.parse(expression).select_results(context), consume=True)
            assert outcome.value == list(root)
            assert all(a is b for a, b in zip(outcome.value, root))
    for options, expression in (
        ({'document_types': {uri: 'element()'}}, 'doc("https://example.org/data")'),
        ({'document_types': {uri: 'empty-sequence()'}}, 'doc("https://example.org/data")'),
        ({'collection_types': {uri: 'element()'}}, 'collection("https://example.org/data")'),
        ({'collection_types': {uri: 'document-node()*'}}, 'collection("https://example.org/data")'),
        ({'default_collection_type': 'element()'}, 'collection()'),
        ({'default_collection_type': 'document-node()*'}, 'collection()'),
    ):
        datatype_failure(expression, VelunaraTypeError, 'XPDY0050',
                         parser=XPath2Parser(**options), context=context)
    datatype_failure('doc("https://example.org/data")', VelunaraTypeError, 'XPDY0050',
                     context=XPathContext(root, documents={uri: root}))
    empty = XPathContext(root, collections={uri: []}, default_collection=[])
    for expression in ('collection("https://example.org/data")', 'collection()'):
        assert datatype_expression(expression, context=empty) == []
    # One-or-more declarations refuse an empty bound collection.
    for options, expression in (
        ({'collection_types': {uri: 'element()+'}}, 'collection("https://example.org/data")'),
        ({'default_collection_type': 'element()+'}, 'collection()'),
    ):
        datatype_failure(expression, VelunaraTypeError, 'XPDY0050',
                         parser=XPath2Parser(**options), context=empty)


def test_public_expression_failure_categories():
    assert datatype_expression('concat("ready", "!")') == 'ready!'
    for expression, error_class, code in (
        ('1 +', VelunaraSyntaxError, 'XPST0003'),
        ('unknown-axis::v', VelunaraSyntaxError, 'XPST0003'),
        ('not-a-function()', VelunaraTypeError, 'XPST0017'),
        ('true(1)', VelunaraTypeError, 'XPST0017'),
        ('abs()', VelunaraTypeError, 'XPST0017'),
        ('unbound:v', VelunaraNameError, 'XPST0081'),
        ('1 + xs:date("2001-01-01")', VelunaraTypeError, 'XPTY0004'),
        ('last()', MissingContextError, 'XPDY0002'),
    ):
        datatype_failure(expression, error_class, code)
