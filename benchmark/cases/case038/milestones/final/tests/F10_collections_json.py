# feature: F10
"""Acceptance oracles: W3C XPath/F&O 3.1 Recommendations, 21 March 2017.

Collection projections use the corresponding map/array function definitions;
JSON expectations use F&O section 17's XML representation and Python's
independent JSON parser. No map enumeration order or diagnostic prose is pinned.
"""
import json
import itertools
import xml.etree.ElementTree as ET
from velunara import XPathContext
from velunara.xpath31 import XPath31Parser
from F09_helpers import xpath_string, http_files
from F10_helpers import (xpath31_items, xpath31_error, xpath31_cases,
                         continued_random_numbers, continued_random_permutations)
from _helpers import observe


CI = 'http://www.w3.org/2005/xpath-functions/collation/html-ascii-case-insensitive'
NS = 'http://www.w3.org/2005/xpath-functions'
CP = 'http://www.w3.org/2005/xpath-functions/collation/codepoint'


def test_constructors_and_member_structure():
    xpath31_cases([
        ('let $m := map{7:"seven", "7":"text", "n":map{"v":19}} return ($m(7), $m("7"), $m?n?v)', ['seven', 'text', 19]),
        ('let $a := [(2,3), (), [5,8]] return (array:size($a), count($a(1)), count($a(2)), array:size($a(3)), $a(3)(2))', [3, 2, 0, 2, 8]),
        ('let $a := array{(2,3), (), 5} return (array:size($a), $a?*)', [3, 2, 3, 5]),
        # op:same-key: numeric types share a key space, strings and numbers do not.
        ('let $m := map{7:"seven"} return ($m(7.0e0), $m(xs:decimal("7")), $m("7"))', ['seven', 'seven']),
        ('map{"7":"text"}(7)', []),
        ('map{"7":"text"}?7', []),
    ])


def test_lookup_arrow_and_apply():
    xpath31_cases([
        ('(map{"v":3}, map{"v":8}) ! ?v', [3, 8]),
        ('map{"v":(3,8)}?("v")', [3, 8]),
        ('[4, (6,7)]?*', [4, 6, 7]),
        ('map{"a":2,"b":9}?* => fn:sort()', [2, 9]),
        ('"planet" => substring(2,3) => upper-case()', ['LAN']),
        ('apply(concat#3, ["north", "-", "west"])', ['north-west']),
        ('apply(function($x,$y){sum($x) * $y}, [(2,3),4])', [20]),
        # Every left-hand item and every key of a parenthesized specifier, in order.
        ('(map{"v":3},map{"v":8})?v', [3, 8]),
        ('(map{"v":3},[4,5])?*', [3, 4, 5]),
        ('map{"a":1,"b":2,"c":3}?("c","a")', [3, 1]),
        ('[3,8,9]?(3,1)', [9, 3]),
    ])
    for expression in ('apply(concat#3, ["a","b"])', 'apply(concat#3, ["a","b","c","d"])'):
        xpath31_error(expression, 'FOAP0001')


def test_collection_lookup_failures():
    xpath31_cases([('map{"v":2}?missing', []), ('[3,8]?1', [3]), ('[3,8]?2', [8])])
    for expression, code in [('map{"v":1,"v":2}', 'XQDY0137'),
                             ('map{1:"a",1.0e0:"b"}', 'XQDY0137'),
                             ('[3,8]?0', 'FOAY0001'), ('[3,8]?3', 'FOAY0001'),
                             ('7?v', 'XPTY0004'), ('[3,8]?v', 'XPTY0004')]:
        xpath31_error(expression, code)


def test_map_operations():
    xpath31_cases([
        ('let $m := map{"a":(2,3),"b":7} return (map:size($m),map:contains($m,"a"),map:contains($m,"c"),map:get($m,"a"))', [2, True, False, 2, 3]),
        ('sort(map:keys(map{"b":7,"a":2}))', ['a', 'b']),
        ('let $m := map{"a":2} return (map:get(map:put($m,"a",9),"a"),map:size(map:put($m,"b",4)), $m?a)', [9, 2, 2]),
        ('map:keys(map:remove(map{"a":2,"b":4,"c":6},("a","c")))', ['b']),
        ('map:get(map:entry(12,(3,5)),12)', [3, 5]),
        ('array:flatten(map:find(map{"v":1,"nest":[map{"v":3},map{"v":5}]},"v")) => fn:sort()', [1, 3, 5]),
        ('sort(map:for-each(map{"a":2,"b":4},function($k,$v){$k || string($v * 3)}))', ['a6', 'b12']),
        ('map:for-each(map{"a":1},function($k,$v){($k,$v)})', ['a', 1]),
        # Membership and replacement use op:same-key; an empty value is still an entry.
        ('(map:contains(map{"k":()},"k"),map:contains(map{7:1},"7"),map:contains(map{7:1},7.0e0))', [True, False, True]),
        ('let $m := map:put(map{"1":1},1,2) return (map:size($m),$m("1"),$m(1))', [2, 1, 2]),
        ('let $m := map:put(map{1:1},1.0e0,2) return (map:size($m),$m(1))', [1, 2]),
        ('map:keys(map:remove(map{7:1,"7":2},"7"))', [7]),
        ('map:keys(map:remove(map{7:1,8:2},7.0e0))', [8]),
        ('(map:size(map:remove(map{"a":1,"b":2},())),map:size(map:remove(map{"a":1,"b":2},"z")))', [2, 2]),
        # map:find: a value is one member, matching values are searched too, keys are not text.
        ('let $r := map:find(map{"v":(1,2)},"v") return (array:size($r),$r(1))', [1, 1, 2]),
        ('array:size(map:find(map{"v":map{"v":7}},"v"))', [2]),
        ('map:find(map{"x":(map{"v":1},map{"v":2})},"v")?*', [1, 2]),
        ('map:find((map{"v":1},map{"v":2}),"v")?*', [1, 2]),
        ('map:find(map{1:"a","1":"b"},1)?*', ['a']),
        ('array:size(map:find(map{"a":1},"v"))', [0]),
    ])


def test_map_merge_policies():
    source = '(map{"v":3,"a":1},map{"v":8},map{"v":13})'
    for option, expected in [('', [3]), (',map{"duplicates":"use-first"}', [3]),
                             (',map{"duplicates":"use-last"}', [13]),
                             (',map{"duplicates":"combine"}', [3, 8, 13])]:
        assert xpath31_items('map:merge(' + source + option + ')?v') == expected
    assert xpath31_items('map:merge(' + source + ',map{"duplicates":"use-any"})?v') in ([3], [8], [13])
    assert xpath31_items('map:merge(' + source + ')?a') == [1]
    xpath31_error('map:merge(' + source + ',map{"duplicates":"reject"})', 'FOJS0003')
    # The policies apply to numeric keys of different types, which are the same key.
    numeric = '(map{1:"x",2:"w"},map{1.0e0:"y"},map{xs:decimal("1"):"z"})'
    for option, expected in [('', ['x']), (',map{"duplicates":"use-first"}', ['x']),
                             (',map{"duplicates":"use-last"}', ['z']),
                             (',map{"duplicates":"combine"}', ['x', 'y', 'z'])]:
        assert xpath31_items('map:merge(' + numeric + option + ')?1') == expected
        assert xpath31_items('map:merge(' + numeric + option + ')?2') == ['w']
    xpath31_error('map:merge(' + numeric + ',map{"duplicates":"reject"})', 'FOJS0003')
    # A number and its text form are different keys, so this is not a duplicate.
    for pair in ('map{"1":"x"},map{1:"y"}', 'map{1:"y"},map{"1":"x"}'):
        assert xpath31_items('map:size(map:merge((' + pair + '),map{"duplicates":"reject"}))') == [2]
    xpath31_error('map:merge(map{"a":1},map{"duplicates":"unknown"})', 'FOJS0005')


def test_array_structural_operations():
    xpath31_cases([
        ('(array:size([2,(4,6),()]), array:get([2,(4,6)],2))', [3, 4, 6]),
        ('array:put([2,4,6],2,(8,9))?*', [2, 8, 9, 6]),
        ('array:insert-before([2,6],2,(3,4))?*', [2, 3, 4, 6]),
        ('let $a := array:append([2],(4,6)) return (array:size($a),$a?2)', [2, 4, 6]),
        ('array:remove([2,4,6,8],(2,4))?*', [2, 6]),
        ('array:subarray([2,4,6,8],2,2)?*', [4, 6]),
        ('array:head([(2,3),4])', [2, 3]),
        ('array:tail([2,4,6])?*', [4, 6]),
        ('array:reverse([2,(4,6),8])?*', [8, 4, 6, 2]),
        ('array:join(([2,4],[6],[]))?*', [2, 4, 6]),
        ('array:flatten((1,[2,[3,(4,5)]],6))', [1, 2, 3, 4, 5, 6]),
        # An inserted sequence is one member; position size+1 is the valid append position.
        ('let $a := array:insert-before([2,6],2,(3,4)) return (array:size($a),$a(2))', [3, 3, 4]),
        ('array:insert-before([2,6],3,7)?*', [2, 6, 7]),
        ('array:remove([2,4,6],())?*', [2, 4, 6]),
        ('array:subarray([2,4,6,8],1,4)?*', [2, 4, 6, 8]),
        ('array:subarray([2,4,6,8],4,1)?*', [8]),
        ('array:subarray([2,4,6,8],5,0)?*', []),
        ('array:subarray([2,4,6,8],2)?*', [4, 6, 8]),
        ('array:subarray([2,4,6,8],5)?*', []),
        ('array:subarray([2,4,6,8],2,0)?*', []),
    ])
    for expression, code in [('array:get([2,4],0)', 'FOAY0001'), ('array:get([2,4],3)', 'FOAY0001'),
                             ('array:put([2,4,6],0,9)', 'FOAY0001'), ('array:put([2,4,6],4,9)', 'FOAY0001'),
                             ('array:insert-before([2,6],0,7)', 'FOAY0001'),
                             ('array:insert-before([2,6],4,7)', 'FOAY0001'),
                             ('array:remove([2,4,6],0)', 'FOAY0001'), ('array:remove([2,4,6],4)', 'FOAY0001'),
                             ('array:subarray([2,4,6,8],0,1)', 'FOAY0001'),
                             ('array:subarray([2,4,6,8],5,1)', 'FOAY0001'),
                             ('array:subarray([2,4,6,8],2,4)', 'FOAY0001'),
                             ('array:subarray([2,4,6,8],2,-1)', 'FOAY0002'),
                             ('array:head([])', 'FOAY0001'), ('array:tail([])', 'FOAY0001')]:
        xpath31_error(expression, code)


def test_array_higher_order_and_sorting():
    xpath31_cases([
        ('array:for-each([(2,3),4],function($x){sum($x)*2})?*', [10, 8]),
        ('array:for-each-pair([2,4,8],[3,5],function($x,$y){$x*10+$y})?*', [23, 45]),
        ('array:filter([7,2,9,4],function($x){$x mod 2 = 0})?*', [2, 4]),
        ('array:fold-left([1,2,3],"s",function($a,$b){$a||$b})', ['s123']),
        ('array:fold-right([1,2,3],"s",function($a,$b){$a||$b})', ['123s']),
        ('array:sort([8,2,5])?*', [2, 5, 8]),
        ('array:sort(["z","B","a"],"' + CI + '")?*', ['a', 'B', 'z']),
        ('array:sort([2,8,5],(),function($x){-$x})?*', [8, 5, 2]),
        ('sort((8,2,5))', [2, 5, 8]),
        ('sort(("z","B","a"),"' + CI + '")', ['a', 'B', 'z']),
        ('sort((2,8,5),(),function($x){-$x})', [8, 5, 2]),
        # Items with equal sort keys keep their input order.
        ('array:sort([3,1,2,4],(),function($x){$x mod 2})?*', [2, 4, 3, 1]),
        ('sort((3,1,2,4),(),function($x){$x mod 2})', [2, 4, 3, 1]),
        ('array:sort(["b","A","a","B"],"' + CI + '")?*', ['A', 'a', 'b', 'B']),
        ('sort(("b","A","a","B"),"' + CI + '")', ['A', 'a', 'b', 'B']),
    ])


def test_json_values_and_strictness():
    text = '{"s":"hello","a":[3,true,null],"n":1.25,"f":false}'
    xpath31_cases([
        ('let $m := parse-json(' + xpath_string(text) + ') return ($m?s,$m?a?1,$m?a?2,empty($m?a?3),$m?n,$m?f)', ['hello', 3, True, True, 1.25, False]),
        ('parse-json("null")', []), ('parse-json("17")', [17]),
        ('let $m := parse-json(' + xpath_string(text) + ') return ($m instance of map(*),$m?a instance of array(*),$m?s instance of xs:string,$m?a?2 instance of xs:boolean,$m?n instance of xs:numeric,$m?f instance of xs:boolean)', [True] * 6),
        ('parse-json(' + xpath_string('"word"') + ')', ['word']),
        # null is an entry or a member holding the empty sequence, not an absent one.
        ('let $m := parse-json(' + xpath_string('{"s":"x","z":null}') + ') return (map:size($m),map:contains($m,"z"),empty($m?z))', [2, True, True]),
        ('let $a := parse-json(' + xpath_string('[null,"x",[]]') + ') return (array:size($a),empty($a(1)),$a(2),array:size($a(3)))', [3, True, 'x', 0]),
        # A surrogate pair is one character; an unpaired surrogate cannot be represented.
        ('string-to-codepoints(parse-json(' + xpath_string(r'"\ud83d\ude00"') + '))', [128512]),
        ('string-to-codepoints(json-to-xml(' + xpath_string(r'"\ud83d\ude00"') + ')/*/string())', [128512]),
        ('string-to-codepoints(parse-json(' + xpath_string(r'"x\ud83dy"') + '))', [120, 65533, 121]),
    ])
    control = xpath_string('"line\nbreak"')
    xpath31_error('parse-json(' + control + ')', 'FOJS0001')
    assert xpath31_items('parse-json(' + control + ',map{"liberal":true()})') == ['line\nbreak']


def test_json_duplicate_options_and_errors():
    text = xpath_string('{"v":3,"v":8}')
    for option, expected in [('', [3]), (',map{"duplicates":"use-first"}', [3]),
                             (',map{"duplicates":"use-last"}', [8])]:
        assert xpath31_items('parse-json(' + text + option + ')?v') == expected
    # The policy applies whatever the value's type and at any depth.
    assert xpath31_items('parse-json(' + xpath_string('{"v":{"x":1},"v":{"x":2}}') + ',map{"duplicates":"use-last"})?v?x') == [2]
    assert xpath31_items('parse-json(' + xpath_string('{"v":[1],"v":[2]}') + ',map{"duplicates":"use-last"})?v?1') == [2]
    assert xpath31_items('parse-json(' + xpath_string('[{"v":3,"v":8}]') + ',map{"duplicates":"use-last"})?1?v') == [8]
    assert xpath31_items('parse-json(' + xpath_string('[{"v":3,"v":8}]') + ')?1?v') == [3]
    xpath31_error('parse-json(' + xpath_string('[{"v":3,"v":8}]') + ',map{"duplicates":"reject"})', 'FOJS0003')
    for expression, code in [('parse-json(' + text + ',map{"duplicates":"reject"})', 'FOJS0003'),
                             ('parse-json("{}",map{"duplicates":"unknown"})', 'FOJS0005'),
                             ('parse-json("{}",map{"liberal":"yes"})', 'XPTY0004'),
                             ('parse-json("{}",map{"duplicates":3})', 'XPTY0004'),
                             ('parse-json("{")', 'FOJS0001')]:
        xpath31_error(expression, code)


def test_json_resources_and_options(tmp_path):
    path = tmp_path / 'data.json'
    path.write_text('{"v":3,"v":8}', encoding='utf-8')
    allowed = XPath31Parser(allow_external_resources=True)
    uri = xpath_string(path.as_uri())
    assert xpath31_items('json-doc(' + uri + ')?v', parser=allowed) == [3]
    for option, expected in [('use-first', [3]), ('use-last', [8])]:
        assert xpath31_items('json-doc(' + uri + ',map{"duplicates":"' + option + '"})?v', parser=allowed) == expected
    xpath31_error('json-doc(' + uri + ',map{"duplicates":"reject"})', 'FOJS0003', parser=allowed)
    xpath31_error('json-doc(' + uri + ')', 'FOUT1170', parser=XPath31Parser(allow_external_resources=False))
    with http_files(tmp_path) as (base, requests):
        assert xpath31_items('json-doc(' + xpath_string(base + path.name) + ')?v', parser=allowed) == [3]
        assert '/' + path.name in requests
    path.write_text('"line\nbreak"', encoding='utf-8')
    xpath31_error('json-doc(' + uri + ')', 'FOJS0001', parser=allowed)
    assert xpath31_items('json-doc(' + uri + ',map{"liberal":true()})', parser=allowed) == ['line\nbreak']
    path.write_text('"\\u0000"', encoding='utf-8')
    assert xpath31_items('json-doc(' + uri + ')', parser=allowed) == ['\ufffd']
    assert xpath31_items('json-doc(' + uri + ',map{"escape":true()})', parser=allowed) == [r'\u0000']
    assert xpath31_items('json-doc(' + uri + ',map{"fallback":function($s){"replacement"}})', parser=allowed) == ['replacement']


def test_json_character_options():
    assert xpath31_items('parse-json(' + xpath_string(r'"\u0000"') + ')') == ['\ufffd']
    for function, suffix in [('parse-json', ''), ('json-to-xml', '/*/string()')]:
        for text, option, expected in [(r'"a\nb"', '', 'a\nb'),
                                       (r'"a\nb"', ',map{"escape":true()}', r'a\nb'),
                                       (r'"\u0000"', ',map{"fallback":function($s){"["||$s||"]"}}', r'[\u0000]')]:
            assert xpath31_items(function + '(' + xpath_string(text) + option + ')' + suffix) == [expected]
    assert xpath31_items('json-to-xml(' + xpath_string(r'"a\nb"') + ',map{"escape":true()})/*/@escaped/string()') in (['true'], ['1'])
    replace = ',map{"fallback":function($s){"["||$s||"]"}}'
    for function, suffix in [('parse-json', ''), ('json-to-xml', '/*/string()')]:
        # Each unrepresentable character is replaced individually.
        assert xpath31_items(function + '(' + xpath_string(r'"\u0000x\u0000"') + replace + ')' + suffix) == [r'[\u0000]x[\u0000]']
    # Replacement also covers array members and object names.
    assert xpath31_items('parse-json(' + xpath_string(r'["a\u0000"]') + ')?1') == ['a\ufffd']
    assert xpath31_items('map:keys(parse-json(' + xpath_string(r'{"\u0000":1}') + '))') == ['\ufffd']
    assert xpath31_items('json-to-xml(' + xpath_string(r'{"\u0000":1}') + replace + ')/*/*/@key/string()') == [r'[\u0000]']
    # Escaped retention covers members and names; only special characters are escaped.
    keep = ',map{"escape":true()}'
    assert xpath31_items('parse-json(' + xpath_string(r'["a\nb"]') + keep + ')?1') == [r'a\nb']
    assert xpath31_items('map:keys(parse-json(' + xpath_string(r'{"k\n":1}') + keep + '))') == [r'k\n']
    assert xpath31_items('parse-json(' + xpath_string(r'"a\"c"') + keep + ')') == ['a"c']
    assert xpath31_items('parse-json(' + xpath_string(r'"a\\c"') + keep + ')') == [r'a\\c']
    entry = 'json-to-xml(' + xpath_string(r'{"k\n":1}') + keep + ')/*/*'
    assert xpath31_items(entry + '/@key/string()') == [r'k\n']
    assert xpath31_items(entry + '/@escaped-key/string()') in (['true'], ['1'])


def test_json_to_xml_standard_representation():
    text = '{"name":"oak","items":[2,true,null,"leaf"],"flag":false}'
    result = xpath31_items('json-to-xml(' + xpath_string(text) + ')')[0]
    root = result.getroot()
    assert root.tag == '{' + NS + '}map'
    entries = {child.attrib['key']: child for child in root}
    assert set(entries) == {'name', 'items', 'flag'}
    assert entries['name'].tag == '{' + NS + '}string'
    assert entries['name'].text == 'oak'
    assert entries['flag'].tag == '{' + NS + '}boolean'
    assert entries['flag'].text in ('false', '0')
    array = entries['items']
    assert array.tag == '{' + NS + '}array'
    assert [child.tag for child in array] == ['{' + NS + '}' + name for name in ('number','boolean','null','string')]
    assert float(array[0].text) == 2
    assert array[1].text in ('true','1')
    assert not (array[2].text or '').strip() and len(array[2]) == 0
    assert array[3].text == 'leaf'
    # Nested objects keep their own name and their members' names.
    nested = xpath31_items('json-to-xml(' + xpath_string('{"o":{"p":[{"q":null}]}}') + ')')[0].getroot()
    assert nested[0].tag == '{' + NS + '}map' and nested[0].attrib['key'] == 'o'
    assert nested[0][0].tag == '{' + NS + '}array' and nested[0][0].attrib['key'] == 'p'
    assert nested[0][0][0][0].tag == '{' + NS + '}null' and nested[0][0][0][0].attrib['key'] == 'q'


def test_json_to_xml_duplicate_validation_options():
    assert xpath31_items("json-to-xml('{\"v\":3}',map{'validate':true()})/*/*/number()") == [3]
    text = xpath_string('{"v":3,"v":8}')
    for option in ('', ',map{"duplicates":"retain"}'):
        assert xpath31_items('json-to-xml(' + text + option + ')/*/*/number()') == [3, 8]
    assert xpath31_items('json-to-xml(' + text + ',map{"duplicates":"use-first"})/*/*/number()') == [3]
    for option, code in [('map{"duplicates":"reject"}', 'FOJS0003'),
                         ('map{"validate":true()}', 'FOJS0003'),
                         ('map{"validate":true(),"duplicates":"retain"}', 'FOJS0005'),
                         ('map{"duplicates":"unknown"}', 'FOJS0005'),
                         ('map{"duplicates":"use-last"}', 'FOJS0005')]:
        xpath31_error('json-to-xml(' + text + ',' + option + ')', code)
    xpath31_error('json-to-xml(' + xpath_string('"line\nbreak"') + ')', 'FOJS0001')


def test_xml_to_json_independent_input():
    root = ET.fromstring('<map xmlns="' + NS + '"><string key="name">oak &amp; ash</string>'
                         '<array key="items"><number>2.5</number><boolean>true</boolean><null/>'
                         '<map><string key="x">leaf</string></map></array><boolean key="flag">false</boolean></map>')
    value = xpath31_items('xml-to-json(.)', context=XPathContext(root))
    assert len(value) == 1
    assert json.loads(value[0]) == {'name':'oak & ash','items':[2.5,True,None,{'x':'leaf'}],'flag':False}
    # Text output must stay valid JSON denoting the same string; escaped="true" content is
    # already in JSON form. Python's parser is the oracle, the chosen spelling is not pinned.
    for content, expected in [('say "hi"', 'say "hi"'), ('one&#10;two', 'one\ntwo'), ('one&#9;two', 'one\ttwo'),
                              (r'a\\b', r'a\\b')]:
        element = ET.fromstring('<string xmlns="' + NS + '">' + content + '</string>')
        assert json.loads(xpath31_items('xml-to-json(.)', context=XPathContext(element))[0]) == expected
    element = ET.fromstring('<string xmlns="' + NS + '" escaped="true">' + r'a\nb\u0041' + '</string>')
    assert json.loads(xpath31_items('xml-to-json(.)', context=XPathContext(element))[0]) == 'a\nbA'


def test_dates_tokens_and_collation_keys():
    xpath31_cases([
        ('let $d := parse-ietf-date("Sunday, 06-Nov-94 08:49:37 GMT") return (year-from-dateTime($d),month-from-dateTime($d),day-from-dateTime($d),hours-from-dateTime($d),minutes-from-dateTime($d),seconds-from-dateTime($d),timezone-from-dateTime($d) = xs:dayTimeDuration("PT0S"))', [1994, 11, 6, 8, 49, 37, True]),
        ('parse-ietf-date("Wed, 6 Jun 94 07:29:35 +0500") = xs:dateTime("1994-06-06T02:29:35Z")', [True]),
        ('(contains-token(("red green","blue")," green "),contains-token("greenish","green"),contains-token("red GREEN","green"))', [True, False, False]),
        ('contains-token("red GREEN","green","' + CI + '")', [True]),
        ('collation-key("oak") instance of xs:base64Binary', [True]),
        ('(collation-key("oak") = collation-key("oak"),collation-key("oak") = collation-key("ash"))', [True, False]),
        ('collation-key("Oak","' + CI + '") = collation-key("OAK","' + CI + '")', [True]),
        # Key equality must agree with string equality under the same collation.
        ('collation-key("Oak","' + CI + '") = collation-key("Oat","' + CI + '")', [False]),
        ('collation-key("oak","' + CP + '") = collation-key("OAK","' + CP + '")', [False]),
        ('collation-key("oak","' + CP + '") = collation-key("oak","' + CP + '")', [True]),
        # Examples and rules of fn:parse-ietf-date: each timezone name has its own offset.
        ('parse-ietf-date("Wed Jun 06 11:54:45 EST 2013") = xs:dateTime("2013-06-06T11:54:45-05:00")', [True]),
        ('parse-ietf-date("Thu Feb 4 10:15:30 -0200 2021") = xs:dateTime("2021-02-04T10:15:30-02:00")', [True]),
        ('parse-ietf-date("Thu, 4 Feb 2021 10:15 GMT") = xs:dateTime("2021-02-04T10:15:00Z")', [True]),
        ('parse-ietf-date("  Thu,  4-Feb-2021   10:15:30 GMT  ") = xs:dateTime("2021-02-04T10:15:30Z")', [True]),
        ('parse-ietf-date("4 FEB 2021 10:15:30 gmt") = xs:dateTime("2021-02-04T10:15:30Z")', [True]),
        ('parse-ietf-date("Thu, 4 Feb 2021 10:15:30 +0200 (EST)") = xs:dateTime("2021-02-04T10:15:30+02:00")', [True]),
        ('parse-ietf-date("Thu, 4 Feb 2021 24:00:00 GMT") = xs:dateTime("2021-02-05T00:00:00Z")', [True]),
        ('parse-ietf-date(())', []),
        # Tokens: every input string, the three separators, trimming, no empty or spaced token.
        ('contains-token(("red","blue green"),"green")', [True]),
        ('contains-token("red"||codepoints-to-string(9)||"green","green")', [True]),
        ('contains-token("red"||codepoints-to-string(10)||"green","red")', [True]),
        ('contains-token("red"||codepoints-to-string(13)||"green","green")', [True]),
        ('contains-token("red green","  ")', [False]),
        ('contains-token("red green","red green")', [False]),
        ('contains-token((),"red")', [False]),
    ])
    for name, offset in [('UT', 'Z'), ('UTC', 'Z'), ('GMT', 'Z'), ('EST', '-05:00'), ('EDT', '-04:00'),
                         ('CST', '-06:00'), ('CDT', '-05:00'), ('MST', '-07:00'), ('MDT', '-06:00'),
                         ('PST', '-08:00'), ('PDT', '-07:00'), ('pdt', '-07:00')]:
        assert xpath31_items('parse-ietf-date("Thu, 4 Feb 2021 10:15:30 ' + name + '") = xs:dateTime("2021-02-04T10:15:30' + offset + '")') == [True], name
    for text in ('Wed, 31 Feb 2021 10:00:00 GMT', 'Thu, 4 Feb 2021 25:00:00 GMT', 'Thu, 4 Foo 2021 10:00:00 GMT',
                 'Thu, 4 Feb 2021', 'Thu, 4 Feb 2021 10:00:00 CET', 'Thu, 4 Feb 2021 10:00:00 +15:00'):
        xpath31_error('parse-ietf-date("' + text + '")', 'FORG0010')


def test_random_range_seed_continuation_and_permutation():
    for seed in (7, 103):
        expression = 'let $g := random-number-generator(' + str(seed) + ') return '
        assert set(xpath31_items(expression + 'map:keys($g)')) >= {'next', 'number', 'permute'}
        first = xpath31_items(expression + '$g?number')
        assert len(first) == 1 and 0 <= first[0] < 1
        assert xpath31_items(expression + '$g?number') == first
        values = xpath31_items(expression + '($g?next())?next() ?number')
        assert len(values) == 1 and 0 <= values[0] < 1
        assert sorted(xpath31_items(expression + '$g?permute((2,2,5,9))')) == [2,2,5,9]
        assert xpath31_items(expression + '$g?permute(())') == []
    # Any atomic seed is a seed. Each pair runs in one expression and is preceded by a
    # different explicit seed, so a generator that ignored this seed would differ.
    for seed in ('"oak"', 'xs:date("2020-01-01")'):
        for other in ('"ash"', '11'):
            assert xpath31_items('let $o := random-number-generator(' + other + ')?number,'
                                 ' $a := random-number-generator(' + seed + ')?number,'
                                 ' $p := random-number-generator(' + other + ')?next()?next()?number,'
                                 ' $b := random-number-generator(' + seed + ')?number'
                                 ' return $a = $b') == [True]
    number = xpath31_items('random-number-generator()?number')
    assert len(number) == 1 and 0 <= number[0] < 1


def test_random_continuation_distribution():
    # FP-10.05 promises independent uniform sampling, not just a valid range.
    # Hoeffding + union bound: 8 marginal bins on 16384 samples, 16 pair bins on
    # the 8192 disjoint pairs (v1,v2),(v3,v4),... and 16 pair bins on the 8191
    # disjoint pairs (v2,v3),(v4,v5),..., each with absolute frequency
    # tolerance .05, have total false-rejection probability below 2e-16.
    # Both alignments are read so dependence between every other step is seen.
    # No reference seed values, exact counts or particular PRNG are required.
    values = observe(continued_random_numbers, 'continuation-quality', 16384,
                     consume=True, timeout=60, max_items=16384).value
    assert len(values) == 16384
    counts = [0] * 8
    pairs = [0] * 16
    for value in values:
        assert 0 <= value < 1
        counts[int(8 * value)] += 1
    for first, second in zip(values[::2], values[1::2]):
        pairs[4 * int(4 * first) + int(4 * second)] += 1
    assert all(abs(count / len(values) - 1 / 8) <= .05 for count in counts), counts
    assert all(abs(count / (len(values) // 2) - 1 / 16) <= .05 for count in pairs), pairs
    shifted = [0] * 16
    for first, second in zip(values[1::2], values[2::2]):
        shifted[4 * int(4 * first) + int(4 * second)] += 1
    assert all(abs(count / (len(values) // 2 - 1) - 1 / 16) <= .05 for count in shifted), shifted


def test_random_permutation_continuation_distribution():
    # Uniform position permutations have 24 equally likely outcomes here.
    # Each outcome frequency has tolerance .02. The binomial KL Chernoff
    # bound, summed over the upper/lower tails of all 24 bins, is below 6e-15
    # for 8192 independent uniform permutations. Missing outcomes are rejected.
    # The position, parity and first-member pair checks retain tolerance .075;
    # their combined Hoeffding + union bound is below 7e-19.
    # This does not assume distinct fixed seeds create distinct generator states.
    members = [1, 2, 3, 4]
    samples = observe(continued_random_permutations, 'permutation-quality', members, 8192,
                      consume=True, timeout=60, max_items=8192).value
    assert len(samples) == 8192
    counts = dict.fromkeys(itertools.permutations(members), 0)
    pairs = [0] * 16
    for permutation in samples:
        assert sorted(permutation) == members
        counts[tuple(permutation)] += 1
    for first, second in zip(samples[::2], samples[1::2]):
        pairs[4 * (first[0] - 1) + second[0] - 1] += 1
    assert all(abs(count / len(samples) - 1 / 24) <= .02
               for count in counts.values()), counts
    assert all(abs(count / (len(samples) // 2) - 1 / 16) <= .075
               for count in pairs), pairs
    shifted = [0] * 16
    for first, second in zip(samples[1::2], samples[2::2]):
        shifted[4 * (first[0] - 1) + second[0] - 1] += 1
    assert all(abs(count / (len(samples) // 2 - 1) - 1 / 16) <= .075
               for count in shifted), shifted
    # Also check position marginals and parity using the same samples.
    for position in range(4):
        for member in members:
            share = sum(count for permutation, count in counts.items()
                        if permutation[position] == member) / len(samples)
            assert abs(share - 1 / 4) <= .075, (position, member, share)
    even = sum(count for permutation, count in counts.items()
               if sum(permutation[i] > permutation[j]
                      for i in range(4) for j in range(i + 1, 4)) % 2 == 0)
    assert abs(even / len(samples) - 1 / 2) <= .075, even


def test_atomic_join_numeric_conversion_and_language():
    xpath31_cases([
        ('string-join((2,true(),xs:decimal("3.5")),"|")', ['2|true|3.5']),
        ('string-join((2,3))', ['23']),
        ('(xs:numeric(7),xs:numeric(xs:decimal("2.5")))', [7, 2.5]),
        ('(xs:numeric("17"),xs:numeric("-2.5"),xs:numeric("1.25e2"))', [17, -2.5, 125]),
    ])
    xpath31_error('xs:numeric("abc")', 'FORG0001')
    for language in ('it', 'fr'):
        assert xpath31_items('default-language()', context=XPathContext(ET.Element('r'), default_language=language)) == [language]
