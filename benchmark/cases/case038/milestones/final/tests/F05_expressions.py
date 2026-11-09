# feature: F05
"""XPath 1.0/2.0 acceptance observations.

Oracles: XPath 1.0 sections 2-4; XPath 2.0 sections 2-3; Functions and
Operators 2.0 sections 6-15. Literal vectors below follow those Recommendations,
independently of the product's implementation. Unicode vectors use Python's
Unicode normalization and URI vectors use the standard library URI encoder.
"""
import datetime as dt
import locale
import math
import unicodedata
from decimal import Decimal
from urllib.parse import quote, urljoin
import xml.etree.ElementTree as ET

from velunara import (XPath1Parser, XPath2Parser, XPathContext,
                         VelunaraError, VelunaraTypeError,
                         VelunaraValueError, VelunaraSyntaxError, VelunaraLocaleError,
                         MissingContextError)
from velunara.xpath3 import XPath30Parser, XPath31Parser
from _helpers import observe, evaluate_expression
from F02_helpers import datatype_expression, datatype_failure
from F04_helpers import context_results


def test_all_axes_and_node_tests():
    root = ET.fromstring('<r><a/><b k="v"><x/><y/></b><c/></r>')
    a, b, c = root
    x, y = b
    parser = XPath1Parser(namespaces={'p': 'urn:p'})
    for expression, expected in (
        ('self::node()', [x]), ('child::*', []), ('parent::*', [b]),
        ('ancestor::*', [root, b]), ('ancestor-or-self::*', [root, b, x]),
        ('descendant::*', []), ('descendant-or-self::*', [x]),
        ('following::*', [y, c]), ('preceding::*', [a]),
        ('following-sibling::*', [y]), ('preceding-sibling::*', []),
        ('../child::*', [x, y]), ('../descendant::*', [x, y]),
        ('../attribute::k', ['v']), ('../../preceding-sibling::*', []),
    ):
        actual = context_results(expression, parser=parser, context=XPathContext(root, item=x))
        assert actual == expected, expression
        for actual_node, source in zip(actual, expected):
            if ET.iselement(source):
                assert actual_node is source
    assert context_results('following::*', parser=parser,
                           context=XPathContext(root, item=b)) == [c]
    assert context_results('preceding-sibling::*', parser=parser,
                           context=XPathContext(root, item=y)) == [x]
    assert set(context_results('namespace::*', parser=parser,
                              context=XPathContext(root, namespaces={'p': 'urn:p'}))) == {
                                  ('xml', 'http://www.w3.org/XML/1998/namespace'), ('p', 'urn:p')}
    mixed = ET.fromstring('<r xmlns:p="urn:p">head<!--note--><?go now?><p:v/>tail<v/><?stop here?></r>',
                         parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True)))
    for expression, expected in (
        ('child::comment()', [mixed[0]]), ('processing-instruction("go")', [mixed[1]]),
        ('processing-instruction()', [mixed[1], mixed[4]]),
        ('text()', ['head', 'tail']), ('p:v', [mixed[2]]), ('p:*', [mixed[2]]),
        ('v', [mixed[3]]), ('*', [mixed[2], mixed[3]]),
        ('node()', ['head', mixed[0], mixed[1], mixed[2], 'tail', mixed[3], mixed[4]]),
    ):
        assert context_results(expression, parser=parser, context=XPathContext(mixed)) == expected
    attributes = ET.fromstring('<r xmlns:p="urn:p" k="1" p:k="2" p:j="3"/>')
    for expression, expected in (('@k', ['1']), ('@p:k', ['2']), ('@p:*', ['2', '3']),
                                 ('@*', ['1', '2', '3']), ('attribute::p:j', ['3'])):
        assert sorted(context_results(expression, parser=parser,
                                      context=XPathContext(attributes))) == expected, expression


def test_reverse_predicates_union_and_document_order():
    root = ET.fromstring('<r><a><x/></a><b/><c/><d/></r>')
    context = XPathContext(root, item=root[3])
    for expression, expected in (
        ('preceding-sibling::*[1]', [root[2]]),
        ('(preceding-sibling::*)[1]', [root[0]]),
        ('preceding::*[1]', [root[2]]),
        ('preceding::*[last()]', [root[0]]),
        ('../d | ../a | ../d | ../b', [root[0], root[1], root[3]]),
        ('../*/parent::*', [root]),
    ):
        assert context_results(expression, parser=XPath1Parser(), context=context) == expected
    assert context_results('ancestor::*[1]', parser=XPath1Parser(),
                           context=XPathContext(root, item=root[0][0])) == [root[0]]
    assert context_results('ancestor::*[last()]', parser=XPath1Parser(),
                           context=XPathContext(root, item=root[0][0])) == [root]


def test_xpath1_grammar_precedence_and_conversions():
    root = ET.fromstring('<r><g><v n="2">7</v><v n="6">11</v></g><g><v n="9">13</v></g></r>')
    for expression, expected in (
        ('.//v[@n > 3][1]', [root[0][1], root[1][0]]),
        ('(.//v[@n > 3])[1]', [root[0][1]]),
        ('g/v/../@missing', []), ('g/./v[2]/../v[1]', [root[0][0]]),
        ('2 + 3 * 4', [14]), ('(2 + 3) * 4', [20]),
        ('-3 + 8 div 2', [1]), ('true() or false() and false()', [True]),
        ('g/v = "11"', [True]), ('g/v != "11"', [True]),
        ('boolean(g/v)', [True]), ('string(g/v)', ['7']),
        # A numeric predicate is compared with position(), never converted to boolean.
        ('g/v[1.5]', []), ('g/v[2.0]', [root[0][1]]), ('g/v[$n]', [root[0][1]]), ('$n + 1', [3]),
        ('.//v[last()]', [root[0][1], root[1][0]]), ('g[last()]/v', [root[1][0]]),
        # The argument-less forms read the context node.
        ('.//v[number() > 8]', [root[0][1], root[1][0]]), ('.//v[string() = "11"]', [root[0][1]]),
        ('.//*[name() = "g"]', list(root)),
    ):
        assert context_results(expression, parser=XPath1Parser(),
                               context=XPathContext(root, variables={'n': 2})) == expected, expression


def test_xpath1_context_node_and_language_functions():
    # The trailing element carries the identifier values only in an ordinary
    # attribute and in text; identifier lookup must not select it.
    # The nearest xml:lang decides language membership.
    root = ET.fromstring('<r xml:lang="en-GB" xmlns:p="urn:p"><p:v xml:id="first"/>'
                         '<p:v xml:id="second" xml:lang="fr-CA"/>'
                         '<d code="second" ref="first">first</d></r>')
    parser = XPath1Parser(namespaces={'p': 'urn:p'})
    context = XPathContext(ET.ElementTree(root), namespaces={'p': 'urn:p'})
    for expression, expected in (
        ('/r/p:v[position() = last()]', [root[1]]), ('count(/r/p:v)', [2]),
        ('id("second")', [root[1]]), ('id("first")', [root[0]]),
        ('id("missing")', []), ('name(/r/p:v[1])', ['p:v']),
        ('local-name(/r/p:v[1])', ['v']), ('namespace-uri(/r/p:v[1])', ['urn:p']),
        ('/r/p:v[lang("en")]', [root[0]]), ('/r/p:v[lang("fr")]', [root[1]]),
        ('/r/p:v[lang("e")]', []), ('/r/p:v[lang("EN")]', [root[0]]),
        ('/r/*[lang("de")]', []),
    ):
        assert context_results(expression, parser=parser, context=context) == expected, expression


def test_xpath1_string_and_boolean_functions():
    for expression, expected in (
        ('string(false())', 'false'), ('string(12)', '12'),
        ('concat("red", "-", "blue")', 'red-blue'),
        ('starts-with("abc", "ab")', True), ('starts-with("abc", "bc")', False),
        ('contains("abc", "bc")', True), ('contains("abc", "xy")', False),
        ('substring-before("a:b:c", ":")', 'a'), ('substring-after("a:b:c", ":")', 'b:c'),
        ('substring("12345", 1.5, 2.6)', '234'), ('substring("12345", 3)', '345'),
        # XPath 1.0 section 4.2 examples: positions are rounded and compared, not sliced.
        ('substring("12345", 0, 3)', '12'), ('substring("12345", 0 div 0, 3)', ''),
        ('substring("12345", 1, 0 div 0)', ''), ('substring("12345", -42, 1 div 0)', '12345'),
        ('substring("12345", -1 div 0, 1 div 0)', ''),
        ('substring-before("abc", "x")', ''), ('substring-after("abc", "x")', ''),
        ('string-length("Aé中")', 3),
        ('normalize-space("  a\tb\n c  ")', 'a b c'),
        ('translate("bar", "abc", "AB")', 'BAr'), ('translate("--aaa--", "abc-", "ABC")', 'AAA'),
        ('string(number("3.0"))', '3'), ('string(number("2.50"))', '2.5'),
        ('boolean("")', False), ('boolean("0")', True), ('boolean("false")', True),
        ('not(false())', True), ('not(true())', False), ('true()', True), ('false()', False),
    ):
        assert datatype_expression(expression, parser=XPath1Parser()) == expected, expression


def test_xpath1_numeric_arithmetic_and_comparisons():
    root = ET.fromstring('<r><v>2</v><v>5</v><v>9</v></r>')
    for expression, expected in (
        ('number(" 12.5 ")', 12.5), ('number(true())', 1), ('sum(v)', 16),
        ('floor(-2.3)', -3), ('ceiling(-2.3)', -2), ('round(2.5)', 3),
        ('floor(2.7)', 2), ('ceiling(2.1)', 3),
        ('round(-2.5)', -2), ('17 mod 5', 2), ('-17 mod 5', -2),
        ('5.5 mod 2', 1.5), ('-5.5 mod 2', -1.5), ('sum(missing)', 0),
        ('7 div 2', 3.5), ('3 - 2 + 4', 5), ('2 < 3 and 4 >= 4', True),
        ('v < 3', True), ('v > 10', False), ('v = "5"', True), ('v != "5"', True),
        # Existential node-set comparison: only the last node satisfies these.
        ('v > 8', True), ('v >= 9', True), ('v < 2', False),
        ('boolean(0 div 0)', False), ('number("wrong") = number("wrong")', False),
    ):
        assert datatype_expression(expression, parser=XPath1Parser(), context=XPathContext(root)) == expected
    assert math.isnan(datatype_expression('number("wrong")', parser=XPath1Parser()))


def test_xpath2_sequences_iteration_quantifiers_and_conditionals():
    for expression, expected in (
        ('(1, (: outer (: nested :) end :) (2, (), 3), 4)', [1, 2, 3, 4]),
        ('()', []), ('3 to 6', [3, 4, 5, 6]), ('6 to 3', []),
        ('for $x in (2, 4), $y in (1, 3) return $x + $y', [3, 5, 5, 7]),
        ('some $x in (2, 4) satisfies $x = 4', [True]),
        ('some $x in (2, 4) satisfies $x > 9', [False]),
        ('some $x in () satisfies true()', [False]),
        ('every $x in (2, 4) satisfies $x > 1', [True]),
        ('every $x in (2, 4) satisfies $x < 4', [False]),
        ('every $x in () satisfies false()', [True]),
        ('some $x in (1, 2), $y in (2, 3) satisfies $x = $y', [True]),
        ('some $x in (1, 2), $y in (3, 4) satisfies $x = $y', [False]),
        ('every $x in (1, 2), $y in (3, 4) satisfies $x < $y', [True]),
        ('every $x in (1, 2), $y in (2, 3) satisfies $x < $y', [False]),
        ('for $x in (1, 2) return for $y in (3) return $x * $y', [3, 6]),
        ('if ("") then 1 else 2', [2]), ('if (()) then 1 else 2', [2]), ('if (0) then 1 else 2', [2]),
        ('if (true()) then 7 else error()', [7]),
        ('if (false()) then error() else (8, 9)', [8, 9]),
    ):
        assert context_results(expression, context=XPathContext(item=1)) == expected, expression


def test_iteration_and_quantifiers_require_supplied_dynamic_context():
    cases = (
        ('for $value in (3, 6) return $value + 2', [5, 8]),
        ('some $value in (3, 6) satisfies $value > 4', [True]),
        ('every $value in (3, 6) satisfies $value > 2', [True]),
    )
    for expression, expected in cases:
        assert context_results(expression, context=XPathContext(item=1)) == expected
        outcome = observe(evaluate_expression, XPath2Parser(), expression,
                          context=None, result_method='select_results', consume=True,
                          exceptions=(VelunaraError,))
        assert isinstance(outcome.error, MissingContextError), expression
        assert outcome.error.code == 'err:XPDY0002', expression


def test_xpath2_comparisons_node_sets_and_integer_division():
    root = ET.fromstring('<r><v/><v/><v/></r>')
    for expression, expected in (
        ('(1, 2) = (2, 3)', [True]), ('(1, 2) != (1, 2)', [True]),
        ('2 eq 2', [True]), ('2 ne 2', [False]), ('2 lt 3', [True]),
        ('2 le 2', [True]), ('3 gt 2', [True]), ('3 ge 3', [True]),
        ('() eq 1', []), ('v[1] is v[1]', [True]), ('v[1] is v[2]', [False]),
        ('v[1] << v[2]', [True]), ('v[3] >> v[2]', [True]),
        ('v[2] << v[1]', [False]), ('v[1] >> v[2]', [False]), ('v[1] << v[1]', [False]),
        ('(v[3], v[1], v[1]) intersect (v[1], v[3])', [root[0], root[2]]),
        ('v except v[2]', [root[0], root[2]]), ('-7 idiv 2', [-3]),
        ('(v[3], v[1]) intersect (v[2], v[3])', [root[2]]),
        ('(v[3], v[1]) except v[2]', [root[0], root[2]]),
    ):
        assert context_results(expression, context=XPathContext(root)) == expected
    datatype_failure('(1, 2) eq 2', VelunaraTypeError, 'XPTY0004')
    numbers = ET.fromstring('<r><v>3</v><v>10</v></r>')
    for expression, expected in (
        # General comparison: existential, untyped operands follow the other operand's type.
        ('v = 10', [True]), ('v > 5', [True]), ('v < 2', [False]), ('v = "10"', [True]),
        ('(1, 2) = (3, 4)', [False]), ('(1, 2) != 1', [True]), ('(1, 1) != 1', [False]), ('() = 1', [False]),
        # Value comparison: untyped operands are strings, so "10" sorts before "9".
        ('v[1] eq "3"', [True]), ('"10" lt "9"', [True]), ('10 lt 9', [False]),
    ):
        assert context_results(expression, context=XPathContext(numbers)) == expected, expression
    for expression in ('v[1] eq 3', '1 eq "1"', '1 = "1"', 'v lt 5'):
        datatype_failure(expression, VelunaraError, 'XPTY0004', context=XPathContext(numbers))
    datatype_failure('7 idiv 0', VelunaraError, 'FOAR0001')


def test_xpath2_types_assertions_and_casts():
    root = ET.fromstring('<r k="x"><v/></r>')
    for expression, expected in (
        ('(1, 2) instance of xs:integer+', [True]), ('() instance of empty-sequence()', [True]),
        ('() instance of xs:integer?', [True]), ('"a" instance of xs:integer', [False]),
        ('. instance of element(r)', [True]), ('@k instance of attribute(k)', [True]),
        ('v instance of node()', [True]), ('(1, 2) treat as xs:integer+', [1, 2]),
        ('"23" cast as xs:integer', [23]), ('"23" castable as xs:integer', [True]),
        ('"bad" castable as xs:integer', [False]), ('() cast as xs:integer?', []),
        ('(1, 2) instance of xs:integer', [False]), ('(1, 2) instance of xs:integer?', [False]),
        ('() instance of xs:integer', [False]), ('(1, 2) instance of xs:integer*', [True]),
        ('() castable as xs:integer', [False]), ('(1, 2) castable as xs:integer', [False]),
        ('() castable as xs:integer?', [True]), ('"maybe" castable as xs:boolean', [False]),
        ('. instance of element(x)', [False]), ('@k instance of attribute(z)', [False]),
        ('(v, v) instance of element()+', [True]),
        ('() instance of node()', [False]), ('() instance of node()?', [True]),
        ('3 instance of xs:decimal', [True]), ('3 instance of xs:double', [False]),
        ('() treat as xs:integer?', []), ('3.7 cast as xs:integer', [3]), ('1 cast as xs:string', ['1']),
    ):
        assert context_results(expression, context=XPathContext(root)) == expected
    for expression, cls, code in (
        ('"bad" cast as xs:integer', VelunaraValueError, 'FORG0001'),
        ('"bad" treat as xs:integer', VelunaraTypeError, 'XPDY0050'),
        ('(1, 2) cast as xs:integer', VelunaraTypeError, 'XPTY0004'),
        ('() cast as xs:integer', VelunaraError, 'XPTY0004'),
        ('() treat as xs:integer', VelunaraError, 'XPDY0050'),
        ('(1, 2) treat as xs:integer', VelunaraError, 'XPDY0050'),
    ):
        datatype_failure(expression, cls, code)


def test_xpath2_numeric_and_sequence_functions():
    for expression, expected in (
        ('abs(-8)', [8]), ('round-half-to-even(2.5)', [2]), ('round-half-to-even(3.5)', [4]),
        ('empty(())', [True]), ('empty((1, 2))', [False]),
        ('exists(())', [False]), ('exists((0))', [True]),
        ('boolean(())', [False]), ('boolean(1)', [True]), ('not(false())', [True]),
        ('zero-or-one(())', []), ('zero-or-one(7)', [7]),
        ('one-or-more((4, 8))', [4, 8]), ('exactly-one(9)', [9]),
        ('index-of((4, 7, 4), 4)', [1, 3]),
        ('insert-before((1, 3), 2, (7, 8))', [1, 7, 8, 3]),
        ('insert-before((1, 3), 9, 7)', [1, 3, 7]), ('insert-before((1, 3), 0, 7)', [7, 1, 3]),
        ('remove((1, 2, 3), 2)', [1, 3]), ('reverse((1, 2, 3))', [3, 2, 1]),
        ('remove((1, 2, 3), 0)', [1, 2, 3]), ('remove((1, 2, 3), 4)', [1, 2, 3]),
        ('subsequence((1, 2, 3, 4), 2, 2)', [2, 3]),
        # Rounded start and length; positions before 1 still consume the length.
        ('subsequence((1, 2, 3, 4, 5), 0, 3)', [1, 2]),
        ('subsequence((1, 2, 3, 4, 5), 2.5, 2)', [3, 4]),
        ('subsequence((1, 2, 3, 4, 5), 1.5, 2.5)', [2, 3, 4]),
        ('unordered((8))', [8]), ('avg((2, 4, 9))', [5]), ('avg((1, 2))', [Decimal('1.5')]),
        ('avg((1, 2)) instance of xs:decimal', [True]), ('sum(())', [0]),
        ('avg(())', []), ('min(())', []), ('max(())', []), ('index-of((1, 2), 3)', []),
        ('min((3, 1.5, 2))', [Decimal('1.5')]), ('max((1, 2.5))', [Decimal('2.5')]),
        ('sum((1, 2.5))', [Decimal('3.5')]), ('max((1, xs:double(2)))', [2]),
        ('string(sum((xs:dayTimeDuration("PT1H"), xs:dayTimeDuration("PT2H"))))', ['PT3H']),
        ('string(avg((xs:yearMonthDuration("P1Y"), xs:yearMonthDuration("P3Y"))))', ['P2Y']),
        ('count(distinct-values((1, 1.0, 2)))', [2]),
        ('count(distinct-values((xs:double("NaN"), xs:double("NaN"))))', [1]),
        ('boolean(0)', [False]), ('not(())', [True]), ('not("")', [True]), ('subsequence((), 1, 2)', []),
        ('min((9, 2, 7))', [2]), ('max((9, 2, 7))', [9]), ('sum((2, 4, 9))', [15]),
    ):
        assert context_results(expression) == expected, expression
    distinct = context_results('distinct-values((4, 7, 4, 9, 7))')
    assert len(distinct) == 3 and set(distinct) == {4, 7, 9}
    for expression, code in (('zero-or-one((1, 2))', 'FORG0003'),
                              ('one-or-more(())', 'FORG0004'),
                              ('exactly-one(())', 'FORG0005'),
                              ('exactly-one((1, 2))', 'FORG0005')):
        datatype_failure(expression, VelunaraValueError, code)
    for expression in ('sum("a")', 'avg(("a", "b"))', 'max(("a", 1))', 'boolean((1, 2))'):
        datatype_failure(expression, VelunaraError, 'FORG0006')


def test_xpath2_strings_codepoints_normalization_and_uris():
    for expression, expected in (
        ('upper-case("Abé")', ['ABÉ']), ('lower-case("AbÉ")', ['abé']),
        ('ends-with("abcd", "cd")', [True]), ('ends-with("abcd", "bc")', [False]),
        ('string-join(("red", "blue", "gold"), "|")', ['red|blue|gold']),
        ('string-to-codepoints("Aé😀")', [65, 233, 128512]),
        ('codepoints-to-string((65, 233, 128512))', ['Aé😀']),
        ('codepoint-equal("Ab", "ab")', [False]), ('codepoint-equal("é", "é")', [True]),
        ('codepoint-equal((), "a")', []), ('string-to-codepoints("")', []), ('codepoints-to-string(())', ['']),
        ('string-join((), "-")', ['']), ('string-join("a", "-")', ['a']), ('upper-case(())', ['']),
        ('ends-with("abc", "")', [True]), ('encode-for-uri(())', ['']), ('normalize-unicode((), "NFC")', ['']),
    ):
        assert context_results(expression) == expected
    text = 'é\u212b\ufb03'
    for form in ('NFC', 'NFD', 'NFKC', 'NFKD'):
        assert context_results('normalize-unicode($text, $form)',
                               context=XPathContext(item=1, variables={'text': text, 'form': form})) == [
                                   unicodedata.normalize(form, text)]
    # The effective form drops surrounding blanks and ignores case; an empty form leaves the value.
    for form, expected in ((' nfkd ', unicodedata.normalize('NFKD', text)),
                           ('nfd', unicodedata.normalize('NFD', text)), ('', text)):
        assert context_results('normalize-unicode($text, $form)',
                               context=XPathContext(item=1, variables={'text': text, 'form': form})) == [expected]
    datatype_failure('normalize-unicode("x", "NFX")', VelunaraError, 'FOCH0003')
    datatype_failure('codepoints-to-string(0)', VelunaraError, 'FOCH0001')
    # escape-html-uri escapes only characters outside printable ASCII, while
    # iri-to-uri also escapes space and the ASCII characters invalid in URIs.
    def html_escape(text):
        return ''.join(c if ' ' <= c <= '~' else quote(c) for c in text)

    iri = 'https://example.org/a b<é>?q=中'
    for function, text, expected in (
        ('encode-for-uri', 'a/b é?x=1', quote('a/b é?x=1', safe='-_.~')),
        ('iri-to-uri', iri, quote(iri, safe=":/?#[]@!$&'()*+,;=-_.~%")),
        ('escape-html-uri', iri, html_escape(iri)),
    ):
        assert context_results(function + '($text)', context=XPathContext(item=1, variables={'text': text})) == [
            expected], function
    base = 'https://example.org/a/b/'
    assert context_results('resolve-uri("../c.xml", "' + base + '")') == [urljoin(base, '../c.xml')]
    # The base's last segment is replaced and an absolute reference ignores the base.
    assert context_results('resolve-uri("c.xml", "https://example.org/a/b")') == ['https://example.org/a/c.xml']
    assert context_results('resolve-uri("https://other.org/q", "' + base + '")') == ['https://other.org/q']
    assert context_results('resolve-uri((), "' + base + '")') == []


def test_xpath2_qnames_nodes_atomization_root_and_references():
    root = ET.fromstring('<r xmlns:p="urn:p" xml:base="https://example.org/base/"><v xml:id="key">key</v><ref>key</ref><v>other</v><v>other</v><p:part xml:lang="en-GB"/>'
                         '<list>other key</list><near>keys</near>'
                         '<a k="1" j="2"/><a k="1" j="3"/><a j="2" k="1"/><dup xml:id="other-key"/></r>')
    document = ET.ElementTree(root)
    context = XPathContext(document, namespaces={'p': 'urn:p'})
    parser = XPath2Parser(namespaces={'p': 'urn:p'})
    for expression, expected in (
        ('local-name-from-QName(QName("urn:p", "p:part"))', ['part']),
        ('namespace-uri-from-QName(QName("urn:p", "p:part"))', ['urn:p']),
        ('prefix-from-QName(QName("urn:p", "p:part"))', ['p']),
        ('resolve-QName("p:part", /r) eq QName("urn:p", "q:part")', [True]),
        ('namespace-uri-for-prefix("p", /r)', ['urn:p']), ('namespace-uri-for-prefix("q", /r)', []),
        ('prefix-from-QName(resolve-QName("p:part", /r))', ['p']),
        ('namespace-uri(/r/p:part)', ['urn:p']), ('namespace-uri(/r/v[1])', ['']),
        ('/r/*[lang("en")]', [root[4]]), ('/r/*[lang("EN-gb")]', [root[4]]),
        ('/r/*[lang("e")]', []), ('/r/*[lang("fr")]', []),
        ('local-name-from-QName(node-name(/r/v[1]))', ['v']),
        ('nilled(/r/v[1])', [False]), ('string(data(/r/v[1]))', ['key']),
        ('data(/r/v[1]) instance of xs:untypedAtomic', [True]),
        ('data(/r/v) = "other"', [True]), ('root(/r/v[1])', [document]),
        ('base-uri(/r/v[1])', ['https://example.org/base/']),
        ('deep-equal((1, "a"), (1, "a"))', [True]),
        ('deep-equal((1, "a"), (1, "b"))', [False]),
        ('deep-equal(/r/v[1], /r/v[2])', [False]),
        ('deep-equal(/r/v[2], /r/v[3])', [True]),
        # Attributes are compared as an unordered set of name/value pairs.
        ('deep-equal(/r/a[1], /r/a[2])', [False]), ('deep-equal(/r/a[1], /r/a[3])', [True]),
        # Token matching: "other key" refers to key, "keys" does not.
        ('id("key")', [root[0]]), ('idref("key")', [root[0], root[1], root[5]]),
        # id() tokenizes its argument and eliminates repeated references.
        ('id("nothing key")', [root[0]]), ('id(("key", "key"))', [root[0]]),
    ):
        assert context_results(expression, parser=parser,
                               context=XPathContext(document, namespaces={'p': 'urn:p'})) == expected, expression
    assert set(context_results('in-scope-prefixes(/r)', parser=parser, context=context)) >= {'p', 'xml'}
    assert context_results('document-uri(.)', context=XPathContext(document,
                           uri='https://example.org/doc.xml')) == ['https://example.org/doc.xml']


def test_xpath2_calendar_duration_and_timezone_functions():
    for kind, lexical, parts in (
        ('dateTime', '2004-02-29T23:45:06.123456+05:30',
         [('year', 2004), ('month', 2), ('day', 29), ('hours', 23), ('minutes', 45), ('seconds', Decimal('6.123456'))]),
        ('date', '2004-02-29-04:00', [('year', 2004), ('month', 2), ('day', 29)]),
        ('time', '23:45:06.123456Z', [('hours', 23), ('minutes', 45), ('seconds', Decimal('6.123456'))]),
        ('duration', 'P1Y14M1DT2H3M4.5S',
         [('years', 2), ('months', 2), ('days', 1), ('hours', 2), ('minutes', 3), ('seconds', Decimal('4.5'))]),
        ('duration', '-P2Y3M4DT5H6M7.125S',
         [('years', -2), ('months', -3), ('days', -4), ('hours', -5), ('minutes', -6), ('seconds', Decimal('-7.125'))]),
    ):
        for part, expected in parts:
            assert context_results(f'{part}-from-{kind}(xs:{kind}("{lexical}"))') == [expected]
    for expression, expected in (
        ('string(adjust-dateTime-to-timezone(xs:dateTime("2004-03-01T01:15:06.123456+05:30"), xs:dayTimeDuration("PT0S")))', '2004-02-29T19:45:06.123456Z'),
        ('string(adjust-date-to-timezone(xs:date("2004-03-01+05:30"), xs:dayTimeDuration("PT0S")))', '2004-02-29Z'),
        ('string(adjust-time-to-timezone(xs:time("01:15:06.123456+05:30"), xs:dayTimeDuration("PT0S")))', '19:45:06.123456Z'),
        ('hours-from-duration(timezone-from-dateTime(xs:dateTime("2004-02-29T12:00:00+05:30")))', 5),
        ('minutes-from-duration(timezone-from-date(xs:date("2004-02-29+05:30")))', 30),
        ('seconds-from-duration(timezone-from-time(xs:time("12:00:00Z")))', 0),
    ):
        assert context_results(expression) == [expected]
    fixed = dt.datetime(2004, 2, 29, 23, 45, 6, 123456, tzinfo=dt.timezone.utc)
    context = XPathContext(item=1, current_dt=fixed, timezone='-04:00')
    assert context_results('(year-from-dateTime(current-dateTime()), '
                           'month-from-date(current-date()), day-from-date(current-date()), '
                           'hours-from-time(current-time()), minutes-from-time(current-time()), '
                           'seconds-from-time(current-time()), '
                           'seconds-from-duration(timezone-from-dateTime(current-dateTime())), '
                           'hours-from-duration(implicit-timezone()))', context=context) == [
                               2004, 2, 29, 23, 45, Decimal('6.123456'), 0, -4]


def test_namespace_defaults_and_strict_name_syntax():
    root = ET.fromstring('<r xmlns="urn:n" k="plain"><v k="value"/></r>')
    for factory in (XPath1Parser, XPath2Parser, XPath30Parser, XPath31Parser):
        options = {'namespaces': {'': 'urn:n'}} if factory is XPath1Parser else {'default_namespace': 'urn:n'}
        parser = factory(**options)
        assert context_results('v/@k', parser=parser, context=XPathContext(root)) == (
            [] if factory is XPath1Parser else ['value'])
        assert context_results('count(@k)', parser=parser, context=XPathContext(root)) == [1]
        assert context_results('concat("a", "b")', parser=parser) == ['ab']
        if factory in (XPath1Parser, XPath2Parser):
            datatype_failure('{urn:n}v', VelunaraSyntaxError, 'XPST0003',
                             parser=factory(), context=XPathContext(root))
            assert context_results('{urn:n}v', parser=factory(strict=False), context=XPathContext(root)) == [root[0]]
        else:
            assert context_results('Q{urn:n}v', parser=parser, context=XPathContext(root)) == [root[0]]
    plain = ET.fromstring('<r><v/></r>')
    assert context_results('v', context=XPathContext(plain)) == [plain[0]]


def test_compatibility_defaults_and_explicit_conversion():
    root = ET.fromstring('<r><v>3</v><v>7</v></r>')
    expression = 'v + 2'
    assert context_results(expression, parser=XPath1Parser(), context=XPathContext(root)) == [5]
    for factory in (XPath2Parser, XPath30Parser, XPath31Parser):
        datatype_failure(expression, VelunaraTypeError, 'XPTY0004',
                         parser=factory(), context=XPathContext(root))
        assert context_results(expression, parser=factory(compatibility_mode=True),
                               context=XPathContext(root)) == [5]
        assert context_results('string(v)', parser=factory(compatibility_mode=True),
                               context=XPathContext(root)) == ['3']


def test_collations_explicit_host_default_and_failures():
    codepoint = 'http://www.w3.org/2005/xpath-functions/collation/codepoint'
    insensitive = 'http://www.w3.org/2005/xpath-functions/collation/html-ascii-case-insensitive'
    for collation, expected in ((codepoint, [False, -1]),
                                (insensitive, [True, 0])):
        parser = XPath2Parser(default_collation=collation)
        assert context_results('default-collation()', parser=parser) == [collation]
        assert context_results('(compare("A", "a") = 0, compare("A", "a"))', parser=parser) == expected
        assert context_results('compare("A", "a", "' + collation + '")',
                               parser=XPath2Parser(default_collation=codepoint)) == [expected[1]]
    for collation, expected in ((codepoint, [3]), (insensitive, [1, 3])):
        assert context_results('index-of(("A", "b", "a"), "a")',
                               parser=XPath2Parser(default_collation=collation)) == expected
    for expression, sensitive, blind in (
        ('contains("ABC", "b")', False, True), ('starts-with("ABC", "a")', False, True),
        ('ends-with("ABC", "c")', False, True), ('substring-before("xABC", "b")', '', 'xA'),
        ('substring-after("xABC", "b")', '', 'C'), ('deep-equal(("A", "b"), ("a", "B"))', False, True),
    ):
        assert context_results(expression, parser=XPath2Parser(default_collation=codepoint)) == [sensitive], expression
        assert context_results(expression, parser=XPath2Parser(default_collation=insensitive)) == [blind], expression
    assert context_results('(min(("a", "B")), max(("a", "B")))',
                           parser=XPath2Parser(default_collation=codepoint)) == ['B', 'a']
    previous = locale.setlocale(locale.LC_COLLATE)
    try:
        # C is an installed POSIX locale; C.UTF-8 is an explicit environment requirement.
        for host in ('C', 'C.UTF-8'):
            locale.setlocale(locale.LC_COLLATE, host)
            comparison = locale.strcoll('a', 'B')
            sign = (comparison > 0) - (comparison < 0)
            assert context_results('compare("a", "B", "' + host + '")') == [sign]
            assert context_results('compare("a", "B")') == [sign]
            assert context_results('compare("A", "a")',
                                   parser=XPath2Parser(default_collation=insensitive)) == [0]
    finally:
        locale.setlocale(locale.LC_COLLATE, previous)
    datatype_failure('compare("a", "b", "urn:unavailable-collation")',
                     VelunaraLocaleError, 'FOCH0002')


def test_explicit_error_identity_description_and_trace_sequence():
    for expression, code, message in (
        ('error()', 'err:FOER0000', None),
        ('error(QName("urn:application", "app:STOP"), "caller detail")', 'app:STOP', 'caller detail'),
        ('error(QName("http://www.w3.org/2005/xqt-errors", "err:FOER0000"), "another detail")',
         'err:FOER0000', 'another detail'),
        ('error((), "empty identity")', 'err:FOER0000', 'empty identity'),
    ):
        outcome = observe(evaluate_expression, XPath2Parser(), expression,
                          exceptions=(VelunaraError,), result_method='select_results', consume=True)
        assert isinstance(outcome.error, VelunaraError)
        assert outcome.error.code == code
        if message is not None:
            assert outcome.error.message == message
    root = ET.fromstring('<r><v/><v/></r>')
    assert context_results('trace((3, "x", v[2], 3), "diagnostic")',
                           context=XPathContext(root)) == [3, 'x', root[1], 3]
    assert context_results('trace((), "empty")') == []
