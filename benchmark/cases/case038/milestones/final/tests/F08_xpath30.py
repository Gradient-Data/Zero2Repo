# feature: F08
"""XPath 3.0 acceptance tests; oracles follow the 2014 W3C Recommendations.

Mathematical finite expectations use Python's independent math library.
Pictures below use unambiguous standard presentations, not diagnostic prose.
"""
import math
import re
import xml.etree.ElementTree as ET
from decimal import Decimal

from velunara import XPathContext, VelunaraTypeError, VelunaraValueError
from velunara.xpath30 import XPath30Parser
from F02_helpers import datatype_failure
from F04_helpers import context_results


def test_expression_extensions_and_type_tests():
    parser = XPath30Parser(namespaces={'n': 'urn:items'})
    context = XPathContext(ET.fromstring('<r xmlns:n="urn:items"><n:v>7</n:v></r>'))
    cases = (
        ('let $x := 4 return ($x, let $x := 9 return $x, $x)', [4, 9, 4]),
        ('let $x := 3, $y := $x + 2 return $x * $y', [15]),
        ('let $x := 1 return let $y := $x + 1 return let $x := 10 return $x + $y', [12]),
        ('for $n in (1, 2) return let $y := $n * 10 return $y + $n', [11, 22]),
        ('(2, 5, 8) ! (. * 3)', [6, 15, 24]),
        ('(4, 9, 2) ! (string(position()) || ":" || string(.))', ['1:4', '2:9', '3:2']),
        ('(10, 20, 30) ! last()', [3, 3, 3]),
        ('(1, 2) ! (3, 4)', [3, 4, 3, 4]),
        ('"a" || 1 || true()', ['a1true']),
        ('"ab" || () || "cd"', ['abcd']),
        ('Q{http://www.w3.org/2005/xpath-functions}concat("u", "v")', ['uv']),
        ('Q{urn:items}v/string()', ['7']),
        ('count(namespace-node()) ge 1', [True]),
        ('every $n in namespace-node() satisfies $n instance of namespace-node()', [True]),
        ('(abs#1 instance of function(*), 7 instance of function(*))', [True, False]),
        ('function($v as xs:integer) as xs:integer {$v + 2} instance of function(xs:integer) as xs:integer', [True]),
        ('function($v as xs:integer) as xs:integer {$v + 2} instance of function(xs:integer, xs:integer) as xs:integer', [False]),
        ('function($v as xs:integer) as xs:integer {$v + 2} instance of function(xs:string) as xs:integer', [False]),
        ('function($v as xs:integer) as xs:integer {$v + 2} instance of function(xs:integer) as xs:string', [False]),
    )
    for expression, expected in cases:
        assert context_results(expression, parser=parser, context=context) == expected, expression


def test_function_items_lookup_inspection_calls_and_partial_application():
    parser = XPath30Parser()
    context = XPathContext(ET.Element('r'))
    cases = (
        ('let $f := substring#2 return $f("planet", 3)', ['anet']),
        ('function-lookup(xs:QName("fn:substring"), 3)("planet", 2, 3)', ['lan']),
        ('function-lookup(QName("urn:absent", "missing"), 1)', []),
        ('function-lookup(xs:QName("fn:substring"), 8)', []),
        ('function-lookup(xs:QName("fn:abs"), 2)', []),
        ('function-lookup(xs:QName("fn:concat"), 3)("a", "b", "c")', ['abc']),
        ('function-lookup(QName("http://www.w3.org/2005/xpath-functions/math", "pi"), 0)()', [math.pi]),
        ('(local-name-from-QName(function-name(concat#2)), namespace-uri-from-QName(function-name(concat#2)))',
         ['concat', 'http://www.w3.org/2005/xpath-functions']),
        ('(function-arity(concat#2), function-arity(function($x, $y, $z) {$x}))', [2, 3]),
        ('function-name(function($x) {$x})', []),
        ('function($x, $y) {$x * 10 + $y}(3, 8)', [38]),
        # Inline functions capture in-scope variables where they are created.
        ('let $k := 5, $f := function($x) {$x + $k} return let $k := 9 return $f(1)', [6]),
        ('function($x) {function($y) {$x * 10 + $y}}(2)(3)', [23]),
        ('let $f := concat("pre-", ?, "-post") return ($f("one"), $f("two"))', ['pre-one-post', 'pre-two-post']),
        ('let $f := substring(?, 2, ?) return $f("abcdef", 3)', ['bcd']),
        ('function($a, $b) {$a - $b}(?, 3)(10)', [7]),
        ('function($a, $b) {$a - $b}(3, ?)(10)', [-7]),
        ('let $f := function($a, $b, $c) {$a || $b || $c} return $f(?, "m", ?)("l", "r")', ['lmr']),
        ('let $f := function($a, $b, $c) {$a || $b || $c} return $f(?, ?, ?)("x", "y", "z")', ['xyz']),
        ('(function-arity(substring(?, 2, ?)), function-arity(concat("p", ?, "q")))', [2, 1]),
    )
    for expression, expected in cases:
        assert context_results(expression, parser=parser, context=context) == expected, expression
    for expression, code in (('let $f := 7 return $f(1)', 'XPTY0004'),
                              ('(substring#2)("abc")', 'XPTY0004'),
                              ('substring#8', 'XPST0017'),
                              ('function($x as xs:integer) {$x}("s")', 'XPTY0004'),
                              ('function($x) as xs:integer {"s"}(1)', 'XPTY0004')):
        datatype_failure(expression, VelunaraTypeError, code, parser=parser, context=context)


def test_higher_order_mapping_filtering_folds_and_pairs():
    parser = XPath30Parser()
    context = XPathContext(ET.Element('r'))
    cases = (
        ('for-each((3, 1, 4), function($x) {($x, -$x)})', [3, -3, 1, -1, 4, -4]),
        ('filter((7, 2, 9, 4), function($x) {$x mod 2 = 0})', [2, 4]),
        ('fold-left((1, 2, 3), "s", function($a, $b) {concat($a, "[", $b, "]")})', ['s[1][2][3]']),
        ('fold-right((1, 2, 3), "s", function($a, $b) {concat("[", $a, "]", $b)})', ['[1][2][3]s']),
        ('for-each-pair((2, 4, 8), (3, 5), function($a, $b) {$a * 10 + $b})', [23, 45]),
        ('for-each-pair((2), (3, 5), function($a, $b) {$a + $b})', [5]),
        ('fold-left((), 17, function($a, $b) {$a + $b})', [17]),
        ('fold-right((), 19, function($a, $b) {$a + $b})', [19]),
        ('for-each((), abs#1)', []), ('filter((), function($x) {true()})', []),
        ('for-each-pair((), (1), function($a, $b) {$a + $b})', []),
        ('fold-left((10, 3), 100, function($a, $b) {$a - $b})', [87]),
        ('fold-right((10, 3), 100, function($a, $b) {$a - $b})', [107]),
        ('fold-left((1, 2, 3), (), function($a, $b) {($b, $a)})', [3, 2, 1]),
        ('for-each-pair(("a", "b", "c"), ("x", "y", "z"), concat#2)', ['ax', 'by', 'cz']),
    )
    for expression, expected in cases:
        assert context_results(expression, parser=parser, context=context) == expected, expression
    # F&O 3.0 signatures: the supplied function must be a matching function item
    # and filter requires a single boolean, not an effective boolean value.
    for expression in ('filter((1, 2), function($x) {$x})',
                       'fold-left((1), 0, function($a) {$a})',
                       'fold-right((1), 0, function($a) {$a})',
                       'for-each-pair((1), (2), abs#1)'):
        datatype_failure(expression, VelunaraTypeError, 'XPTY0004', parser=parser, context=context)


def test_sequence_heads_node_boundaries_paths_and_identity():
    root = ET.fromstring('<r><a k="1"><b/><b><c/></b></a><a/><p:a xmlns:p="urn:p"/><t>x</t></r>')
    context = XPathContext(ET.ElementTree(root))
    parser = XPath30Parser()
    cases = (
        ('head((9, 2, 7))', [9]), ('tail((9, 2, 7))', [2, 7]),
        ('head(())', []), ('tail(())', []), ('tail((9))', []),
        ('(has-children(/r), has-children(/r/a[2]), has-children(()))', [True, False, False]),
        ('has-children(/r/t)', [True]),
        ('innermost((/r/a, /r/a/b, /r/a/b/c))', [root[0][0], root[0][1][0], root[1]]),
        ('outermost((/r/a, /r/a/b, /r/a/b/c))', [root[0], root[1]]),
        # Unsorted input with duplicates still yields each node once in document order.
        ('innermost((/r/a[2], /r/a/b/c, /r/a[2], /r/a/b[1]))', [root[0][0], root[0][1][0], root[1]]),
        ('outermost((/r/a/b/c, /r/a[2], /r/a/b[1], /r/a[2]))', [root[0][0], root[0][1][0], root[1]]),
        # An ancestor that is not the parent also counts.
        ('innermost((/r, /r/a/b/c))', [root[0][1][0]]),
        ('outermost((/r/a/b/c, /r))', [root]),
        ('path(/r/a[2])', ['/Q{}r[1]/Q{}a[2]']),
        ('path(/r/*[3])', ['/Q{}r[1]/Q{urn:p}a[1]']),
        ('path(/r/a[1]/@k)', ['/Q{}r[1]/Q{}a[1]/@k']),
        ('path(())', []),
        # These paths have canonical URI-qualified names under F&O 3.0 section 14.2.
        ('path(/r/a[1]/b[2]/c)', ['/Q{}r[1]/Q{}a[1]/Q{}b[2]/Q{}c[1]']),
        ('path(/)', ['/']),
        ('let $n := /r/a[1] return generate-id($n) = generate-id($n)', [True]),
        ('generate-id(/r/a[1]) ne generate-id(/r/a[2])', [True]),
        ('generate-id(/r/a[1]/b[1]) = generate-id((/r/a/b)[1])', [True]),
        ('generate-id(/r) ne generate-id(/r/a[1])', [True]),
        ('generate-id(/r/a[1]) ne generate-id(/r/a[1]/@k)', [True]),
        ('generate-id(())', ['']),
    )
    for expression, expected in cases:
        assert context_results(expression, parser=parser, context=context) == expected, expression


def test_mathematical_functions_finite_empty_and_nonfinite_results():
    parser = XPath30Parser()
    # F&O 3.0 section 4: all enumerated members have a numerical oracle.
    cases = [
        ('pi()', math.pi), ('exp(1.3)', math.exp(1.3)), ('exp10(2.3)', 10 ** 2.3),
        ('log(3.2)', math.log(3.2)), ('log10(7.5)', math.log10(7.5)),
        ('pow(3, 2.5)', 3 ** 2.5), ('sqrt(7)', math.sqrt(7)),
        ('sin(0.7)', math.sin(.7)), ('cos(0.7)', math.cos(.7)),
        ('tan(0.7)', math.tan(.7)), ('asin(0.4)', math.asin(.4)),
        ('acos(0.4)', math.acos(.4)), ('atan(2)', math.atan(2)),
        ('atan2(2, -3)', math.atan2(2, -3)), ('atan2(-2, -3)', math.atan2(-2, -3)),
        ('atan2(-1, 1)', math.atan2(-1, 1)), ('atan2(-1, 0)', -math.pi / 2),
        ('atan2(0e0, -1)', math.pi), ('atan2(-0e0, -1)', -math.pi),
        ('exp10(-2)', 0.01), ('pow(2, -2)', 0.25), ('pow(-2e0, 3)', -8.0),
    ]
    for expression, expected in cases:
        actual = context_results('math:' + expression, parser=parser)
        assert len(actual) == 1
        assert math.isclose(actual[0], expected, rel_tol=1e-6, abs_tol=0), expression
    for name in ('exp', 'exp10', 'log', 'log10', 'sqrt', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan'):
        assert context_results('math:' + name + '(())', parser=parser) == []
    assert context_results('math:pow((), 2)', parser=parser) == []
    for expression in ('sqrt(-1)', 'log(-1)', 'log10(-1)', 'asin(2)', 'acos(2)',
                       'pow(-2e0, 0.5e0)', 'sin(xs:double("INF"))',
                       'cos(xs:double("INF"))', 'tan(xs:double("INF"))', 'exp(xs:double("NaN"))'):
        actual = context_results('math:' + expression, parser=parser)
        assert len(actual) == 1 and math.isnan(actual[0]), expression
    for expression, expected in (('log(0)', -math.inf), ('log10(0)', -math.inf),
                                 ('exp(xs:double("INF"))', math.inf),
                                 ('exp10(xs:double("-INF"))', 0.0),
                                 ('sqrt(xs:double("INF"))', math.inf),
                                 # F&O 3.0 math:pow table: zero base with negative exponent.
                                 ('pow(0, -3)', math.inf), ('pow(0e0, -4)', math.inf),
                                 ('pow(-0e0, -3)', -math.inf), ('pow(-0e0, -4)', math.inf),
                                 ('pow(2, 0)', 1.0), ('pow(0e0, 0)', 1.0),
                                 ('pow(xs:double("NaN"), 0)', 1.0)):
        assert context_results('math:' + expression, parser=parser) == [expected]


def test_integer_pictures_languages_and_invalid_picture():
    parser = XPath30Parser()
    cases = (
        ('format-integer(42, "0000")', '0042'),
        ('format-integer(1234567, "#,##0")', '1,234,567'),
        ('format-integer(1234567, "#_##0")', '1_234_567'),
        ('format-integer(1234567, "# ##0")', '1 234 567'),
        ('format-integer(12345678, "0,000")', '12,345,678'),
        # Irregular grouping keeps only the stated separators (F&O 3.0 section 4.6.1).
        ('format-integer(123456789, "#,##,##0")', '1234,56,789'),
        ('format-integer(5, "#00")', '05'), ('format-integer(7, "##0")', '7'),
        ('format-integer(-42, "0000")', '-0042'), ('format-integer((), "0")', ''),
        ('format-integer(28, "A")', 'AB'), ('format-integer(28, "a")', 'ab'),
        # Bijective alphabetic numbering: there is no zero digit at any position.
        ('format-integer(1, "a")', 'a'), ('format-integer(26, "a")', 'z'),
        ('format-integer(27, "A")', 'AA'), ('format-integer(52, "a")', 'az'),
        ('format-integer(702, "A")', 'ZZ'), ('format-integer(703, "A")', 'AAA'),
        ('format-integer(4, "I")', 'IV'), ('format-integer(9, "i")', 'ix'),
        ('format-integer(40, "I")', 'XL'), ('format-integer(90, "I")', 'XC'),
        ('format-integer(400, "I")', 'CD'), ('format-integer(1994, "I")', 'MCMXCIV'),
        ('format-integer(3999, "I")', 'MMMCMXCIX'),
        ('format-integer(49, "I")', 'XLIX'), ('format-integer(49, "i")', 'xlix'),
        ('format-integer(12, "w")', 'twelve'),
        ('format-integer(12, "W", "en")', 'TWELVE'),
        ('format-integer(12, "w", "it")', 'dodici'),
        ('format-integer(12, "Ww", "it")', 'Dodici'),
        # Single-word values only: compound-word spelling is not judged.
        ('format-integer(0, "w")', 'zero'), ('format-integer(17, "w")', 'seventeen'),
        ('format-integer(40, "w")', 'forty'), ('format-integer(90, "w", "en")', 'ninety'),
        ('format-integer(19, "w", "it")', 'diciannove'),
        ('format-integer(40, "w", "it")', 'quaranta'),
    )
    for expression, expected in cases:
        assert context_results(expression, parser=parser) == [expected], expression
    # English compound numbers: judge the ordered number words only, so either
    # convention for "and", hyphens and spacing is accepted.
    for number, words in ((42, ['forty', 'two']),
                          (342, ['three', 'hundred', 'forty', 'two']),
                          (7021, ['seven', 'thousand', 'twenty', 'one'])):
        actual = context_results('format-integer(%d, "w")' % number, parser=parser)
        assert len(actual) == 1 and isinstance(actual[0], str), number
        assert [w for w in re.split('[^a-z]+', actual[0]) if w and w != 'and'] == words, actual
    # F&O 3.0 primary format token grammar for decimal-digit patterns.
    for picture in ('', '0#', ',0', '0,', '0,,0'):
        datatype_failure('format-integer(3, "%s")' % picture, VelunaraValueError, 'FODF1310', parser=parser)


def test_number_pictures_named_symbols_and_defaults():
    parser = XPath30Parser(decimal_formats={'custom': {'decimal-separator': ',', 'grouping-separator': '.'},
                                            'signs': {'minus-sign': '~', 'percent': 'p',
                                                      'infinity': 'Forever', 'NaN': 'Missing'}})
    cases = (
        ('format-number(1234.5, "#,##0.00")', '1,234.50'),
        ('format-number(-12.5, "0.00;(0.00)")', '(12.50)'),
        ('format-number(0.125, "0.0%")', '12.5%'),
        ('format-number(1234.5, "#.##0,00", "custom")', '1.234,50'),
        ('format-number(-3.5, "0,00", "custom")', '-3,50'),
        ('format-number(xs:double("NaN"), "0", "custom")', 'NaN'),
        ('format-number(xs:double("INF"), "0", "custom")', 'Infinity'),
        ('format-number(-3.5, "0.0", "signs")', '~3.5'),
        ('format-number(0.25, "0p", "signs")', '25p'),
        ('format-number(xs:double("INF"), "0", "signs")', 'Forever'),
        ('format-number(xs:double("NaN"), "0", "signs")', 'Missing'),
        # Value-dependent choice of subpicture; a negative subpicture replaces the minus sign.
        ('format-number(12.5, "0.00;(0.00)")', '12.50'),
        ('format-number(0, "0.00;(0.00)")', '0.00'),
        # Non-tie rounding, optional and mandatory fractional digits, padding.
        ('format-number(1234.5678, "#,##0.0#")', '1,234.57'),
        ('format-number(1234.5, "#,##0.0#")', '1,234.5'),
        ('format-number(1234, "#,##0.0#")', '1,234.0'),
        ('format-number(0.5, "0.0###")', '0.5'),
        ('format-number(123, "00000")', '00123'),
        ('format-number(1234567, "#,##,##0")', '12,34,567'),
        # Per-mille scales by 1000, and fractional grouping counts from the separator.
        ('format-number(0.0125, "0.0\u2030")', '12.5\u2030'),
        ('format-number(1.23456, "0.000,00")', '1.234,56'),
        # Omitted symbols of a named format use the defaults.
        ('format-number(0.25, "0%", "custom")', '25%'),
        ('format-number(-1234.5, "#,##0.00", "signs")', '~1,234.50'),
        ('format-number((), "0")', 'NaN'),
        ('format-number(1234567.5, "#.##0,0", "custom")', '1.234.567,5'),
        ('format-number(-0.25, "0p", "signs")', '~25p'),
    )
    for expression, expected in cases:
        assert context_results(expression, parser=parser) == [expected], expression
    # F&O 3.0 section 4.7.3 picture-string rules.
    for picture in ('0.0.0', '', '.', '0;0;0', '0%%', '0%\u2030', '0.#0'):
        datatype_failure('format-number(3, "%s")' % picture, VelunaraValueError, 'FODF1310', parser=parser)
    datatype_failure('format-number(3, "0", "unknown")', VelunaraValueError, 'FODF1280', parser=parser)


def test_calendar_pictures_languages_and_invalid_components():
    parser = XPath30Parser()
    cases = (
        ('format-date(xs:date("2024-03-05"), "[Y0001]-[M01]-[D01]")', '2024-03-05'),
        ('format-time(xs:time("16:07:09"), "[H01]:[m01]:[s01]")', '16:07:09'),
        ('format-dateTime(xs:dateTime("2024-03-05T16:07:09"), "[D01]/[M01]/[Y0001] [H01]:[m01]")', '05/03/2024 16:07'),
        ('format-date(xs:date("2024-03-05"), "[MNn] [FNn]", "en", (), ())', 'March Tuesday'),
        ('format-date(xs:date("2024-03-05"), "[MNn] [FNn]", "it", (), ())', 'Marzo Martedì'),
        # Presentation and width: F&O 3.0 section 9.8.4.
        ('format-date(xs:date("2024-03-05"), "[D1]/[M1]/[Y]")', '5/3/2024'),
        ('format-date(xs:date("2024-11-25"), "[D1]/[M1]")', '25/11'),
        ('format-date(xs:date("2024-03-05"), "[D,2]")', '05'),
        ('format-date(xs:date("2024-03-05"), "[Y01]")', '24'),
        ('format-date(xs:date("2024-03-05"), "[Y,2-2]")', '24'),
        ('format-date(xs:date("2024-03-05"), "[Y,2]")', '2024'),
        ('format-date(xs:date("2024-03-05"), "[d]")', '65'),
        ('format-date(xs:date("2024-12-31"), "[d]")', '366'),
        ('format-date(xs:date("2024-03-05"), "[[[Y]]]")', '[2024]'),
        ('format-date(xs:date("2024-03-05"), "Year: [Y]")', 'Year: 2024'),
        # Names: letter case and the whole name table, not only the first entry.
        ('format-date(xs:date("2024-03-05"), "[MN]", "en", (), ())', 'MARCH'),
        ('format-date(xs:date("2024-03-05"), "[Mn]", "en", (), ())', 'march'),
        ('format-date(xs:date("2024-03-10"), "[FNn]", "en", (), ())', 'Sunday'),
        ('format-date(xs:date("2024-03-10"), "[FN]", "it", (), ())', 'DOMENICA'),
        ('format-date(xs:date("2024-12-05"), "[MNn]", "it", (), ())', 'Dicembre'),
        ('format-date(xs:date("2024-01-05"), "[MNn]", "it", (), ())', 'Gennaio'),
        ('format-dateTime(xs:dateTime("2024-03-05T16:07:09"), "[FNn], [D] [MNn] [Y]", "en", (), ())',
         'Tuesday, 5 March 2024'),
        # Twelve-hour clock, default time widths, fractional seconds.
        ('format-time(xs:time("16:07:09"), "[h]:[m01]")', '4:07'),
        ('format-time(xs:time("04:07:09"), "[H]:[m]:[s]")', '4:07:09'),
        ('format-time(xs:time("16:07:09.5"), "[s01].[f001]")', '09.500'),
        ('format-dateTime(xs:dateTime("2024-03-05T16:07:09"), "[H01]:[m01]:[s01] [Y]")', '16:07:09 2024'),
    )
    for expression, expected in cases:
        assert context_results(expression, parser=parser) == [expected], expression
    # A maximum width shortens a name; the abbreviation form itself is
    # implementation-defined, so only its length and initial are judged.
    for month, day, picture_value, name in (('03', '05', '[MNn,*-3]', 'March'), ('09', '05', '[MNn,*-3]', 'September'),
                                            ('03', '05', '[FNn,*-3]', 'Tuesday')):
        actual = context_results('format-date(xs:date("2024-%s-%s"), "%s", "en", (), ())' % (month, day, picture_value),
                                 parser=parser)
        assert len(actual) == 1 and 1 <= len(actual[0]) <= 3 and actual[0][0] == name[0], actual
    for expression, code in (
        ('format-date(xs:date("2024-03-05"), "[Y")', 'FOFD1340'),
        ('format-date(xs:date("2024-03-05"), "[Y]]")', 'FOFD1340'),
        ('format-date(xs:date("2024-03-05"), "[]")', 'FOFD1340'),
        ('format-date(xs:date("2024-03-05"), "[Q]")', 'FOFD1340'),
        ('format-date(xs:date("2024-03-05"), "[Y,0]")', 'FOFD1340'),
        ('format-date(xs:date("2024-03-05"), "[h]")', 'FOFD1350'),
        ('format-date(xs:date("2024-03-05"), "[m]")', 'FOFD1350'),
        ('format-time(xs:time("16:07:09"), "[D]")', 'FOFD1350'),
        ('format-time(xs:time("16:07:09"), "[MNn]")', 'FOFD1350'),
        ('format-date(xs:date("2024-03-05"), "[H01]")', 'FOFD1350'),
        ('format-time(xs:time("16:07:09"), "[Y]")', 'FOFD1350'),
    ):
        datatype_failure(expression, VelunaraValueError, code, parser=parser)


def test_optional_join_separator_and_rounding_precision():
    parser = XPath30Parser()
    cases = (
        ('string-join(("a", "bc", "d"))', ['abcd']),
        ('string-join(("a", "bc", "d"), "::")', ['a::bc::d']),
        ('string-join(())', ['']),
        ('string-join("solo", "::")', ['solo']), ('string-join((), "::")', ['']),
        ('round(12.345, 2)', [Decimal('12.35')]),
        ('round(12.345, 1)', [Decimal('12.3')]),
        ('round(-12.345, 2)', [Decimal('-12.34')]),
        ('round(1261, -2)', [1300]), ('round(-1261, -2)', [-1300]),
        ('round(12.8, 0)', [13]), ('round((), 2)', []),
        # Positive-direction ties at each precision, including the one-argument form.
        ('round(2.5)', [3]), ('round(-2.5)', [-2]), ('round(-4.5)', [-4]),
        ('round(2.5, 0)', [3]), ('round(-2.5, 0)', [-2]),
        ('round(1.25, 1)', [Decimal('1.3')]), ('round(-1.25, 1)', [Decimal('-1.2')]),
        ('round(12.3456, 3)', [Decimal('12.346')]),
        ('round(12, 2)', [12]), ('round(12.345, 5)', [Decimal('12.345')]),
        # Negative precision, away from the excluded exact ties.
        ('round(1349, -2)', [1300]), ('round(1351, -2)', [1400]), ('round(-1349, -2)', [-1300]),
        ('round(123.456, -1)', [120]), ('round(1951, -3)', [2000]), ('round(1, -3)', [0]),
        ('round(xs:double("INF"), 2)', [math.inf]),
    )
    for expression, expected in cases:
        assert context_results(expression, parser=parser) == expected, expression
