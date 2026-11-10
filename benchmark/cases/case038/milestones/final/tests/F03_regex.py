# feature: F03
"""Acceptance of XML Schema/XPath regular expressions and Unicode controls.

Regex outcomes use the XML Schema and F&O Recommendations named by FP-03.
Unicode vectors are independent UCD records; no translated pattern text or
human-readable exception sentence is an oracle.
"""
import gzip
import hashlib
from pathlib import Path
import re
import unicodedata

from velunara import XPath2Parser, XPathContext, VelunaraValueError
from velunara.xpath30 import XPath30Parser
from velunara import RegexError, translate_pattern, install_unicode_data, unicode_version
from _helpers import read_xml, result_items
from F02_helpers import datatype_expression as value, datatype_failure as failure
from F02_helpers import datatype_rejection as reject
from F03_helpers import (compiled_pattern, xml_content, UNICODE_VECTORS,
                         UNICODE_BLOCKS, EXPLICIT_VERSIONS, RECATEGORIZED,
                         RESIZED_BLOCKS)


def test_translation_extensions_and_whole_string_semantics():
    match = compiled_pattern(r'([a-z]+)-\1').search('!echo-echo?')
    assert match is not None
    assert match.group(0) == 'echo-echo'
    assert match.groups() == ('echo',)
    # \NN is one reference only if NN groups precede it; otherwise \N then a digit.
    assert compiled_pattern(r'^(a)\10$').search('aa0') is not None
    assert compiled_pattern(r'^(a)\10$').search('aa') is None
    ten = compiled_pattern(r'^(a)(b)(c)(d)(e)(f)(g)(h)(i)(j)\10$')
    assert ten.search('abcdefghijj') is not None
    assert ten.search('abcdefghija0') is None
    assert compiled_pattern('a+?').search('aaaa').group(0) == 'a'
    assert compiled_pattern('a+').search('aaaa').group(0) == 'aaaa'
    assert compiled_pattern('^word$').search('word') is not None
    assert compiled_pattern('^word$').search('a word') is None
    assert compiled_pattern('^word$').search('word\n') is None
    for separator in ('\n', '\r'):
        assert compiled_pattern('a.b').search('a' + separator + 'b') is None
        assert compiled_pattern('a.b', flags=re.S).search('a' + separator + 'b') is not None
    assert compiled_pattern('a.b').search('a\tb') is not None
    options = dict(back_references=False, lazy_quantifiers=False, anchors=False)
    pattern = compiled_pattern('(ab|cd)+', **options)
    assert pattern.search('abcd').group(0) == 'abcd'
    for text in ('!abcd', 'abcd!', 'abcd\n'):
        assert pattern.search(text) is None
    literal_anchors = compiled_pattern('a^b$', **options)
    assert literal_anchors.search('a^b$') is not None
    assert literal_anchors.search('ab') is None
    assert compiled_pattern('^a.b$', flags=re.I | re.S).search('A\nB') is not None


def test_schema_versions_and_malformed_patterns():
    # XML Schema 1.1 permits this otherwise ambiguous hyphen as a literal.
    for options in ({}, {'xsd_version': '1.0'}):
        reject(translate_pattern, '[a-b-c]', error_class=RegexError, **options)
    pattern = compiled_pattern('[a-b-c]', xsd_version='1.1')
    assert [c for c in '-abcdez' if pattern.fullmatch(c)] == list('-abc')
    for version in ('1.0', '1.1'):
        assert compiled_pattern('[a-c]{2}', xsd_version=version).fullmatch('bc') is not None
        for malformed in ('[abc', '(ab', 'a{1,2,3}', '[z-a]', r'\p{NotACategory}'):
            reject(translate_pattern, malformed, xsd_version=version, error_class=RegexError)


def test_xpath_matching_replacement_tokenization_and_flags():
    assert value(r'matches("an echo-echo!", "([a-z]+)-\1")') is True
    assert value(r'replace("ab12 cd34", "([a-z]+)([0-9]+)", "$2:$1")') == '12:ab 34:cd'
    assert result_items(value(r'tokenize("red, green;blue", "[,;]\s*")')) == ['red', 'green', 'blue']
    assert value('matches((), "a")') is False
    assert value('replace((), "a", "b")') == ''
    assert result_items(value('tokenize((), ",")')) == []
    assert result_items(value('tokenize("", ",")')) == []
    assert result_items(value('tokenize(",a,,b,", ",")')) == ['', 'a', '', 'b', '']
    assert result_items(value('tokenize("abracadabra", "(ab)|(a)")')) == ['', 'r', 'c', 'd', 'r', '']
    # $N takes the longest digit run naming an existing group; \$ and \\ are literals.
    groups = '"(a)(b)(c)(d)(e)(f)(g)(h)(i)(j)"'
    assert value(f'replace("abcdefghij", {groups}, "[$10]")') == '[j]'
    assert value('replace("ab", "(a)(b)", "[$10]")') == '[a0]'
    assert value('replace("abc", "b", "[$0]")') == 'a[b]c'
    assert value(r'replace("abc", "(b)", "\$1")') == 'a$1c'
    assert value(r'replace("abc", "b", "\\")') == 'a\\c'
    assert value('matches("Ab", "ab", "ii")') is True
    # i leaves category escapes alone; x keeps whitespace inside character classes.
    assert value(r'matches("a", "\p{Lu}", "i")') is False
    assert value('matches("helloworld", "hello[ ]world", "x")') is False
    assert value('matches("hello world", "hello[ ]world", "x")') is True
    # Multi-line ^ follows a newline only if that newline does not end the input.
    for text, pattern, expected in (('a\n', '\n^', False), ('a\nb', '\n^b', True),
                                    ('a\n', '^$', False), ('a\n\nb', '^$', True)):
        context = XPathContext(item=1, variables={'text': text, 'pattern': pattern})
        assert value('matches($text, $pattern, "m")', context=context) is expected
    # Every flag has a live baseline and an otherwise identical disabled arm.
    cases = [('Ab', 'ab', 'i'), ('a\nb', '^b$', 'm'),
             ('a\nb', 'a.b', 's'), ('ab', 'a b', 'x')]
    for text, pattern, flag in cases:
        context = XPathContext(item=1, variables={'text': text, 'pattern': pattern})
        assert value('matches($text, $pattern)', context=context) is False
        assert value(f'matches($text, $pattern, "{flag}")', context=context) is True
    # One shared input needs all four flags; dropping any one loses the match.
    context = XPathContext(item=1, variables={'text': 'pre\nAB\nc\npost',
                                             'pattern': ' ^ ab . c $ '})
    for flags in ('imsx', 'msx', 'isx', 'imx', 'ims'):
        matched = flags == 'imsx'
        assert value(f'replace($text, $pattern, "X", "{flags}")', context=context) == (
            'pre\nX\npost' if matched else 'pre\nAB\nc\npost')
        assert result_items(value(f'tokenize($text, $pattern, "{flags}")', context=context)) == (
            ['pre\n', '\npost'] if matched else ['pre\nAB\nc\npost'])
    parser = XPath30Parser()
    assert value('matches("a.b", "a.b", "q")', parser=parser) is True
    assert value('matches("axb", "a.b", "q")', parser=parser) is False
    assert value('matches("axb", "a.b")', parser=parser) is True
    assert value('matches("Mr. B. Obama", "B. OBAMA", "iq")', parser=parser) is True
    assert value('matches("abcd", ".*", "q")', parser=parser) is False
    # With q, x has no effect and replacement backslashes are literal.
    assert value('matches("ab", "a b", "qx")', parser=parser) is False
    assert value('matches("a b", "a b", "qx")', parser=parser) is True
    assert value(r'replace("a\b\c", "\", "\\", "q")', parser=parser) == 'a\\\\b\\\\c'
    # XPath 3.0 non-capturing groups are not numbered.
    assert value('replace("xy", "(?:x)(y)", "[$1]")', parser=parser) == '[y]'
    assert value('replace("a.b axb", "a.b", "$1", "q")', parser=parser) == '$1 axb'
    assert result_items(value('tokenize("a.b.c", ".", "q")', parser=parser)) == ['a', 'b', 'c']


def test_xpath_regex_failures_have_distinct_codes():
    assert value('matches("abc", "b")') is True
    assert value('replace("abc", "b", "X")') == 'aXc'
    assert result_items(value('tokenize("a,b", ",")')) == ['a', 'b']
    for name, arguments in [('matches', '"abc", "a", "z"'),
                            ('replace', '"abc", "a", "X", "z"'),
                            ('tokenize', '"abc", "a", "z"'),
                            ('matches', '"abc", "a", "I"'),
                            ('replace', '"abc", "a", "X", "M"')]:
        failure(f'{name}({arguments})', VelunaraValueError, 'FORX0001')
    for expression in ('matches("abc", "[")', 'replace("abc", "[", "X")',
                       'tokenize("abc", "[")'):
        failure(expression, VelunaraValueError, 'FORX0002')
    for replacement in ('$x', '\\x', 'x$'):
        failure(f'replace("abc", "(b)", "{replacement}")', VelunaraValueError, 'FORX0004')
    for expression in ('replace("abc", "a*", "X")', 'tokenize("abc", "a*")'):
        failure(expression, VelunaraValueError, 'FORX0003')
    failure('analyze-string("abc", "a*")', VelunaraValueError, 'FORX0003',
            parser=XPath30Parser())


def test_match_analysis_preserves_nested_capture_structure():
    result = value('analyze-string("!ab12?cd3.", "(([a-z]+)([0-9]+))")',
                   parser=XPath30Parser(), context=XPathContext(item=1))
    expected = read_xml('''<analyze-string-result xmlns="http://www.w3.org/2005/xpath-functions"><non-match>!</non-match><match><group nr="1"><group nr="2">ab</group><group nr="3">12</group></group></match><non-match>?</non-match><match><group nr="1"><group nr="2">cd</group><group nr="3">3</group></group></match><non-match>.</non-match></analyze-string-result>''')
    assert xml_content(result.elem) == xml_content(expected)
    result = value(r'analyze-string("xAbc1x", "(?:a)(b)c\d", "i")',
                   parser=XPath30Parser(), context=XPathContext(item=1))
    expected = read_xml('''<analyze-string-result xmlns="http://www.w3.org/2005/xpath-functions"><non-match>x</non-match><match>A<group nr="1">b</group>c1</match><non-match>x</non-match></analyze-string-result>''')
    assert xml_content(result.elem) == xml_content(expected)
    # An empty inner group stays nested inside its enclosing group.
    result = value('analyze-string("a-a", "(a(x?))")', parser=XPath30Parser(),
                   context=XPathContext(item=1))
    expected = read_xml('''<analyze-string-result xmlns="http://www.w3.org/2005/xpath-functions"><match><group nr="1">a<group nr="2"/></group></match><non-match>-</non-match><match><group nr="1">a<group nr="2"/></group></match></analyze-string-result>''')
    assert xml_content(result.elem) == xml_content(expected)
    result = value('analyze-string("", "a")', parser=XPath30Parser(), context=XPathContext(item=1))
    assert result.elem.tag == '{http://www.w3.org/2005/xpath-functions}analyze-string-result'
    assert list(result.elem) == [] and not result.elem.text


def test_character_classes_xml_names_and_unicode_properties():
    cases = [('[a-f]+', ('face', 'bed'), ('g', 'abc1')),
             ('[^a-f]+', ('xyz', 'G'), ('a', 'xa')),
             ('[a-z-[aeiou]]+', ('rhythm', 'bcdf'), ('team', 'ae')),
             ('[a-z-[^aeiou]]+', ('aei',), ('b', 'A')),
             (r'[^a-c-[\d]]+', ('dA',), ('b', '5', '٣')),
             ('[a-z-[b-y-[c]]]+', ('acz',), ('b', 'd', 'y')),
             (r'\i\c*', ('_node-2', ':name', 'Élément', 'a·b'), ('2node', '-name', 'a b', '·a')),
             (r'\I', ('7', '-'), ('A', '_', ':')),
             (r'\C', (' ', '/'), ('7', '-', '.')),
             (r'\p{Lu}+', ('ÉΩ', 'ABC'), ('é', '7')),
             (r'\p{L}+', ('汉字', 'éΩ'), ('7', '€')),
             (r'\p{Nd}+', ('١२3',), ('A', 'Ⅳ')),
             (r'\d+', ('١२3',), ('A', 'Ⅳ')),
             (r'\D', ('A', 'Ⅳ'), ('٣', '7')),
             (r'[\s]+', (' \t\n\r',), ('\xa0', '\x0c', '\u2028')),
             (r'[\P{L}\p{Lu}]+', ('7A', '€É'), ('a', 'é')),
             (r'\P{L}+', ('7€',), ('é', '汉')),
             (r'\p{IsGreek}+', ('Ωα',), ('A', 'Ж')),
             (r'\P{IsBasicLatin}', ('é', 'Ω'), ('A', '7')),
             (r'\p{IsLatin-1Supplement}', ('é', '\xa0'), ('A', 'Ā'))]
    for source, accepted, refused in cases:
        pattern = compiled_pattern(source)
        for text in accepted:
            assert pattern.fullmatch(text) is not None, (source, text)
        for text in refused:
            assert pattern.fullmatch(text) is None, (source, text)


def test_builtin_unicode_switching_and_default_restoration():
    assert unicode_version() == unicodedata.unidata_version
    versions = [entry[0] for entry in UNICODE_VECTORS]
    try:
        # Reverse traversal also exercises invalidation after newer data was active.
        for version in versions + list(reversed(versions)):
            install_unicode_data(version)
            assert unicode_version() == version
            current = tuple(map(int, version.split('.')))
            for introduced, char, category in UNICODE_VECTORS:
                assigned = current >= tuple(map(int, introduced.split('.')))
                assert bool(compiled_pattern(r'\p{' + category + '}').fullmatch(char)) == assigned
                assert bool(compiled_pattern(r'\p{Cn}').fullmatch(char)) == (not assigned)
                # The XSD word class (all but P, Z, C) must follow the switch too.
                assert bool(compiled_pattern(r'[\w]').fullmatch(char)) == assigned
            for introduced, block, start, end in UNICODE_BLOCKS:
                if current < tuple(map(int, introduced.split('.'))):
                    reject(translate_pattern, r'\p{Is' + block + '}', error_class=RegexError)
                else:
                    pattern = compiled_pattern(r'\p{Is' + block + '}')
                    for point in (start, end):
                        assert pattern.fullmatch(chr(point)) is not None
                    for point in (start - 1, end + 1):
                        assert pattern.fullmatch(chr(point)) is None
            for changed, char, old, new in RECATEGORIZED:
                moved = current >= tuple(map(int, changed.split('.')))
                assert bool(compiled_pattern(r'\p{' + new + '}').fullmatch(char)) == moved
                assert bool(compiled_pattern(r'\p{' + old + '}').fullmatch(char)) == (not moved)
            for block, ranges in RESIZED_BLOCKS:
                start, end = [r[1:] for r in ranges
                              if current >= tuple(map(int, r[0].split('.')))][-1]
                pattern = compiled_pattern(r'\p{Is' + block + '}')
                assert [point for point in range(start - 1, max(r[2] for r in ranges) + 2)
                        if pattern.fullmatch(chr(point))] == list(range(start, end + 1))
    finally:
        install_unicode_data()
    assert unicode_version() == unicodedata.unidata_version
    for _, char, category in UNICODE_VECTORS:
        assert bool(compiled_pattern(r'\p{' + category + '}').fullmatch(char)) == (
            unicodedata.category(char) == category)
    assert compiled_pattern(r'\p{IsBasicLatin}').fullmatch('A') is not None


def test_supplied_unicode_categories_versions_and_configuration_errors(tmp_path):
    # Official, unmodified UCD 3.2 data; stored compressed solely for transport.
    data = gzip.decompress(Path(__file__).with_name('F03_UnicodeData-3.2.0.txt.gz').read_bytes())
    assert hashlib.sha256(data).hexdigest() == '5e444028b6e76d96f9dc509609c5e3222bf609056f35e5fcde7e6fb8a58cd446'
    source = tmp_path / 'UnicodeData.txt'
    source.write_bytes(data)
    uri = source.as_uri()
    try:
        # Caller-supplied categories and the version label are separate inputs.
        # Reuse the same real table to isolate acceptance of every explicit label;
        # version-specific semantic expectations below apply only to label 3.2.
        for version in EXPLICIT_VERSIONS:
            install_unicode_data(version, uri)
            assert unicode_version() == version
            assert compiled_pattern(r'\p{Lu}').fullmatch('A') is not None
        install_unicode_data('16.0.0')
        assert compiled_pattern(r'\p{Ll}').fullmatch('\u1D00') is not None
        install_unicode_data('3.2.0', uri)
        assert unicode_version() == '3.2.0'
        # U+1D00 was assigned in 4.0; U+0220 is Lu in the supplied 3.2 file.
        assert compiled_pattern(r'\p{Cn}').fullmatch('\u1D00') is not None
        assert compiled_pattern(r'\p{Ll}').fullmatch('\u1D00') is None
        assert compiled_pattern(r'\p{Lu}').fullmatch('\u0220') is not None
        # Major categories come from the supplied records too.
        assert compiled_pattern(r'\p{L}').fullmatch('\u1D00') is None
        assert compiled_pattern(r'\p{C}').fullmatch('\u1D00') is not None
        # <..., First>/<..., Last> record pairs denote whole ranges (UCD 3.2:
        # CJK 4E00..9FA5, Hangul AC00..D7A3); 9FA6 was unassigned in 3.2.
        for char in ('\u4E01', '\u9FA5', '\uAC01', '\uD7A3'):
            assert compiled_pattern(r'\p{Lo}').fullmatch(char) is not None
        assert compiled_pattern(r'\p{Cn}').fullmatch('\u9FA6') is not None
        assert compiled_pattern(r'\p{IsBasicLatin}').fullmatch('A') is not None
        reject(install_unicode_data, '14.1.0')
        reject(install_unicode_data, '14.1.0', uri)
        reject(install_unicode_data, name_or_url=uri, error_class=TypeError)
    finally:
        install_unicode_data()
    assert unicode_version() == unicodedata.unidata_version
    assert bool(compiled_pattern(r'\p{Ll}').fullmatch('\u1D00')) == (
        unicodedata.category('\u1D00') == 'Ll')
