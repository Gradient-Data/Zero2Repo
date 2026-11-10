# feature: F01
"""Acceptance coverage for encoding, screen geometry and replacements."""
import json
import sys

import pytest
import velnora
from velnora import calc_text_pos, calc_width, move_next_char, move_prev_char
from velnora.util import trim_text_attr_cs

from _helpers import canvas_snapshot, environment, run_process
from F01_helpers import assert_cluster_sequence, encoded_observation, encoding_state


def test_selected_encoding_and_encoded_passthrough():
    # Values observed on the original; use representable members of each family.
    vectors = [
        ('utf-8', 'é中', b'\xc3\xa9\xe4\xb8\xad'),
        ('iso8859-1', 'é', b'\xe9'),
        ('iso8859-7', 'Ωα', b'\xd9\xe1'),
        ('euc-jp', '日本', b'\xc6\xfc\xcb\xdc'),
        ('euc-kr', '한국', b'\xc7\xd1\xb1\xb9'),
        ('euc-cn', '中文', b'\xd6\xd0\xce\xc4'),
        ('gb2312', '中文', b'\xd6\xd0\xce\xc4'),
        ('gbk', '汉语', b'\xba\xba\xd3\xef'),
        ('big5', '中文', b'\xa4\xa4\xa4\xe5'),
        ('uhc', '한국', b'\xc7\xd1\xb1\xb9'),
    ]
    with encoding_state():
        for encoding, text, expected in vectors:
            velnora.set_encoding(encoding)
            assert encoded_observation(text) == (expected, (None,) * len(expected)), encoding
            assert encoded_observation(expected) == (expected, (None,) * len(expected)), encoding
        # These names select double-byte geometry but lack Python converters.
        # Their encoded-byte and geometry support remains independently checked.
        for encoding, data in [('cn-gb', b'\xd6\xd0'), ('euc-tw', b'\xc4\xe3')]:
            velnora.set_encoding(encoding)
            assert encoded_observation(data) == (data, (None,) * len(data))
        # Already encoded text is never decoded, even when it is not valid in the selected
        # encoding or spells a graphic character's encoded form in another encoding.
        foreign = b'\xff\xe2\x94\x82\x80'
        for encoding in ('utf-8', 'ascii', 'iso8859-7', 'euc-jp', 'gbk', 'big5'):
            velnora.set_encoding(encoding)
            assert encoded_observation(foreign) == (foreign, (None,) * len(foreign)), encoding


def test_initial_encoding_follows_real_locale():
    script = '''
import codecs, json, locale
from velnora import apply_target_encoding, calc_width
from velnora.util import get_encoding
actual = locale.getpreferredencoding(False)
print(json.dumps({"locale": codecs.lookup(actual).name,
                  "selected": codecs.lookup(get_encoding()).name,
                  "encoded": list(apply_target_encoding("\\u00e9")[0]),
                  "graphic": list(apply_target_encoding("\\u2502")[0]),
                  "width": calc_width(b"\\xc3\\xa9", 0, 2)}))
'''
    observations = []
    for name in ('C', 'C.UTF-8'):
        result = run_process(
            [sys.executable, '-c', script],
            env=environment({'LC_ALL': name, 'LANG': name,
                             'PYTHONUTF8': '0', 'PYTHONCOERCECLOCALE': '0'}),
        )
        assert result.returncode == 0, result.stderr
        observation = json.loads(result.stdout)
        assert observation['selected'] == observation['locale']
        observations.append(observation)
    assert [o['locale'] for o in observations] == ['ascii', 'utf-8'], (
        'Environment must provide distinct real C and C.UTF-8 encodings', observations
    )
    # The missing glyph is deliberately not pinned to the reference question mark.
    missing = bytes(observations[0]['encoded'])
    assert len(missing) == 1 and 33 <= missing[0] <= 126
    assert bytes(observations[1]['encoded']) == b'\xc3\xa9'
    # The derived encoding governs geometry and graphics as well, not only conversion.
    assert observations[0]['width'] == 2 and observations[1]['width'] == 1
    assert bytes(observations[0]['graphic']) == b'x'
    assert bytes(observations[1]['graphic']) == '\u2502'.encode()


def test_column_geometry_grapheme_navigation_and_clipping():
    clusters = [('a', 1), ('é', 1), ('e\u0301', 1), ('中', 2),
                ('👨\u200d👩\u200d👧', 2), ('👋🏻', 2), ('🇨🇦', 2)]
    with encoding_state():
        velnora.set_encoding('utf-8')
        for cluster, width in clusters:
            for middle in (cluster, cluster.encode('utf-8')):
                prefix = 'A' if isinstance(middle, str) else b'A'
                suffix = 'B' if isinstance(middle, str) else b'B'
                text = prefix + middle + suffix
                end = 1 + len(middle)
                assert calc_width(text, 0, len(text)) == width + 2
                # Offsets bound every measurement.
                assert calc_width(text, 1, end) == width
                assert calc_width(text, end, len(text)) == 1
                assert move_next_char(text, 1, len(text)) == end
                assert move_prev_char(text, 0, end) == 1
                assert calc_text_pos(text, 0, len(text), 1 + width) == (end, 1 + width)
                assert calc_text_pos(text, 1, len(text), width) == (end, width)
                assert calc_text_pos(text, 0, end, 99) == (end, 1 + width)
                if width == 2:
                    assert calc_text_pos(text, 0, len(text), 2) == (1, 1)
            raw = ('A' + cluster + 'B').encode('utf-8')
            assert trim_text_attr_cs(raw, [], [], 1, 1 + width)[0] == cluster.encode('utf-8')
            if width == 2:
                assert trim_text_attr_cs(raw, [], [], 2, 4)[0] == b' B'
                assert trim_text_attr_cs(raw, [], [], 0, 2)[0] == b'A '
        assert calc_width('', 0, 0) == 0
        # A run of adjacent clusters: every boundary and every clipping window, from the cell model.
        sequence = [('e\u0301\u0323', 1), ('中', 2), ('👋🏻', 2), ('🇨🇦', 2), ('🇺🇸', 2),
                    ('👨\u200d👩\u200d👧', 2), ('z', 1)]
        assert_cluster_sequence(sequence)
        # Unicode text keeps its screen geometry whatever the selected byte encoding.
        for encoding in ('iso8859-1', 'euc-jp', 'big5'):
            velnora.set_encoding(encoding)
            for cluster, width in clusters:
                text = 'A' + cluster + 'B'
                end = 1 + len(cluster)
                assert calc_width(text, 0, len(text)) == width + 2, (encoding, cluster)
                assert calc_width(text, 1, end) == width, (encoding, cluster)
                assert move_next_char(text, 1, len(text)) == end, (encoding, cluster)
                assert move_prev_char(text, 0, end) == 1, (encoding, cluster)
                assert calc_text_pos(text, 1, len(text), width) == (end, width), (encoding, cluster)
        # Single-byte encodings count bytes: adjacent high bytes are never a pair.
        for encoding in ('iso8859-1', 'iso8859-7'):
            velnora.set_encoding(encoding)
            text = b'A\xe9\xe8B'
            assert calc_width(text, 0, 4) == 4
            assert [move_next_char(text, i, 4) for i in range(3)] == [1, 2, 3]
            assert [move_prev_char(text, 0, i) for i in (3, 2, 1)] == [2, 1, 0]
            assert calc_text_pos(text, 0, 4, 2) == (2, 2)
            assert trim_text_attr_cs(text, [], [], 1, 2)[0] == b'\xe9'
            assert trim_text_attr_cs(text, [], [], 2, 4)[0] == b'\xe8B'
        # Adjacent double-byte characters, including trail bytes in the ASCII range.
        for encoding, first, second in [('euc-jp', b'\xc6\xfc', b'\xcb\xdc'),
                                        ('euc-kr', b'\xc7\xd1', b'\xb1\xb9'),
                                        ('gbk', b'\x81\x40', b'\xba\xba'),
                                        ('big5', b'\xa4\x40', b'\xa4\xe5'),
                                        ('uhc', b'\x81\x41', b'\xc7\xd1')]:
            velnora.set_encoding(encoding)
            text = b'A' + first + second + b'B'
            assert calc_width(text, 0, 6) == 6, encoding
            assert [move_next_char(text, i, 6) for i in (0, 1, 3, 5)] == [1, 3, 5, 6], encoding
            assert [move_prev_char(text, 0, i) for i in (6, 5, 3, 1)] == [5, 3, 1, 0], encoding
            assert calc_text_pos(text, 0, 6, 2) == (1, 1), encoding
            assert calc_text_pos(text, 0, 6, 4) == (5 - 2, 3), encoding
            assert trim_text_attr_cs(text, [], [], 1, 3)[0] == first, encoding
            assert trim_text_attr_cs(text, [], [], 3, 5)[0] == second, encoding
            assert trim_text_attr_cs(text, [], [], 2, 5)[0] == b' ' + second, encoding
            assert trim_text_attr_cs(text, [], [], 1, 4)[0] == first + b' ', encoding
        for encoding, data in [('iso8859-1', b'\xe9'), ('euc-jp', b'\xc6\xfc'),
                               ('euc-kr', b'\xc7\xd1'), ('euc-cn', b'\xd6\xd0'),
                               ('cn-gb', b'\xd6\xd0'), ('euc-tw', b'\xc4\xe3'),
                               ('gb2312', b'\xd6\xd0'), ('gbk', b'\xba\xba'),
                               ('big5', b'\xa4\xa4'), ('uhc', b'\xc7\xd1')]:
            velnora.set_encoding(encoding)
            text = b'A' + data + b'B'
            assert calc_width(text, 0, len(text)) == 2 + len(data)
            assert move_next_char(text, 1, len(text)) == 1 + len(data)
            assert move_prev_char(text, 0, 1 + len(data)) == 1
            assert calc_text_pos(text, 0, len(text), 1 + len(data)) == (1 + len(data), 1 + len(data))
            if len(data) == 2:
                assert trim_text_attr_cs(text, [], [], 2, 4)[0] == b' B'
                assert trim_text_attr_cs(text, [], [], 0, 2)[0] == b'A '


def test_replacement_encoding_precedence_and_byte_markup():
    with encoding_state():
        velnora.set_ascii_fallbacks({'é': 'e', '•': '*', '█': '│', '°': '+'})
        velnora.set_encoding('ascii')
        # DEC Special Graphics character positions, in terminal code order.
        graphics = '▮◆▒␉␌␍␊°±␤␋┘┐┌└┼⎺⎻─⎼⎽├┤┴┬│≤≥π≠£·'
        codes = b'_`abcdefghijklmnopqrstuvwxyz{|}~'
        assert encoded_observation(graphics) == (codes, ('0',) * len(codes))
        graphic_canvas = canvas_snapshot(velnora.Text(('graphics', graphics)).render((len(codes),)))
        assert graphic_canvas['text'] == (codes,)
        assert graphic_canvas['charsets'] == (('0',) * len(codes),)
        assert graphic_canvas['attributes'] == (('graphics',) * len(codes),)
        assert encoded_observation('Aé•B') == (b'Ae*B', (None,) * 4)
        assert encoded_observation('█│°') == (b'xxf', ('0',) * 3)
        # Only the graphic bytes carry the graphic charset, including when they spell ordinary letters.
        assert encoded_observation('x│x°') == (b'xxxf', (None, '0', None, '0'))
        velnora.set_encoding('iso8859-1')
        assert encoded_observation('é•') == (b'\xe9*', (None,) * 2)
        # The graphic repertoire applies to all non-UTF-8 output and precedes the encoding's own
        # character for a symbol it could represent directly (degree sign in ISO-8859-1).
        for encoding in ('iso8859-1', 'euc-jp', 'gbk', 'big5'):
            velnora.set_encoding(encoding)
            assert encoded_observation(graphics) == (codes, ('0',) * len(codes)), encoding
            assert encoded_observation('A°') == (b'Af', (None, '0')), encoding
            # A replacement or marker stands in for only the unrepresentable character.
            data, charsets = encoded_observation('A✓B')
            assert len(data) == 3 and data[:1] == b'A' and data[2:] == b'B', encoding
            assert 33 <= data[1] <= 126 and charsets == (None,) * 3, encoding
        velnora.set_encoding('utf-8')
        text = 'é•█│°'
        assert encoded_observation(text) == (text.encode(), (None,) * len(text.encode()))
        velnora.set_encoding('ascii')
        marker, charsets = encoded_observation('✓')
        assert len(marker) == 1 and 33 <= marker[0] <= 126
        assert charsets == (None,)
        canvas = canvas_snapshot(velnora.Text([b'A', '•', ('mark', '█'), b'B']).render((4,)))
        row, = canvas['text']
        assert len(row) == 4 and row[:2] == b'A*' and row[3:] == b'B'
        assert 33 <= row[2] <= 126
        assert canvas['attributes'] == ((None, None, 'mark', None),)
        assert canvas['charsets'] == ((None,) * 4,)


def test_replacement_validation_atomicity_and_collection_isolation():
    with encoding_state():
        velnora.set_encoding('ascii')
        supplied = {'•': '*', 'é': 'e'}
        velnora.set_ascii_fallbacks(supplied)
        supplied['•'] = '+'
        supplied['✓'] = '!'
        assert dict(velnora.get_ascii_fallbacks()) == {'•': '*', 'é': 'e'}
        assert encoded_observation('•é')[0] == b'*e'
        invalid = [('', '*'), ('ab', '*'), ('A', '*'), (' ', '*'), ('~', '*'),
                   ('中', '*'), ('\u0301', '*'), ('\n', '*'), ('\ud800', '*'),
                   ('✓', ''), ('✓', '**'), ('✓', '\n'), ('✓', '\x7f'), ('✓', 'é')]
        for key, value in invalid:
            with pytest.raises(ValueError):
                velnora.set_ascii_fallbacks({'█': '#', key: value})
            assert dict(velnora.get_ascii_fallbacks()) == {'•': '*', 'é': 'e'}
            assert encoded_observation('•é')[0] == b'*e'
        for key, value in [(1, '*'), ('✓', 1)]:
            with pytest.raises(TypeError):
                velnora.set_ascii_fallbacks({'█': '#', key: value})
            assert dict(velnora.get_ascii_fallbacks()) == {'•': '*', 'é': 'e'}
            assert encoded_observation('•é')[0] == b'*e'
        velnora.set_ascii_fallbacks({'✓': '+', '•': ' ', 'é': '~'})
        assert dict(velnora.get_ascii_fallbacks()) == {'✓': '+', '•': ' ', 'é': '~'}
        assert encoded_observation('✓•é')[0] == b'+ ~'
        velnora.set_ascii_fallbacks({})
        assert dict(velnora.get_ascii_fallbacks()) == {}
        missing, charsets = encoded_observation('✓')
        assert len(missing) == 1 and 33 <= missing[0] <= 126
        assert charsets == (None,)
