# feature: F16
"""Acceptance observations for progress, charts and large lettering."""
import pytest

from _helpers import canvas_snapshot, velnora
from F01_helpers import encoding_state
from F06_helpers import label_lines
from F16_helpers import MosaicFont, TwoBlockFont, artwork_cells, assert_digit_style, block_ink
from velnora import BarGraphError


def test_progress_ratio_updates_and_bounds():
    # F16.T01: percentage labels and fill share the specified bounds.
    with encoding_state():
        velnora.set_encoding('utf-8')
        progress = velnora.ProgressBar('empty', 'filled')
        assert progress.get_text() == '0 %'
        assert canvas_snapshot(progress.render((20,)))['attributes'] == (('empty',) * 20,)
        # The first update also establishes that the omitted completion amount is 100.
        progress.set_completion(33.9)
        assert progress.get_text() == '33 %'
        assert canvas_snapshot(progress.render((20,)))['attributes'] == (('filled',) * 6 + ('empty',) * 14,)
        for current, done, percent, columns in ((7, 12, 58, 11),
                                                 (12, 12, 100, 20), (0, 12, 0, 0)):
            progress.done = done
            progress.set_completion(current)
            assert progress.get_text() == f'{percent} %'
            observed = canvas_snapshot(progress.render((20,)))
            assert (observed['cols'], observed['rows']) == (20, 1)
            assert observed['attributes'] == (('filled',) * columns + ('empty',) * (20 - columns),)
            label = f'{percent} %'
            # Both center choices are valid when padding has an odd remainder.
            padding = 20 - len(label)
            assert observed['text'][0].decode() in {
                ' ' * left + label + ' ' * (padding - left)
                for left in {padding // 2, (padding + 1) // 2}
            }
        progress.current = 3
        progress.done = 12
        assert progress.get_text() == '25 %'
        assert canvas_snapshot(progress.render((20,)))['attributes'] == (('filled',) * 5 + ('empty',) * 15,)
        # Boundary labels are promised exactly: 0 % below, 100 % beyond, 0 % without a positive
        # completion amount, however the values arrive (assigned or constructed).
        for current, done, columns, percent in ((-4, 12, 0, 0), (19, 12, 20, 100), (3, 0, 0, 0), (3, -8, 0, 0),
                                                 (-3, -8, 0, 0), (0, 0, 0, 0), (-1, 100, 0, 0), (101, 100, 20, 100)):
            progress.current = current
            progress.done = done
            built = velnora.ProgressBar('empty', 'filled', current=current, done=done)
            for bar in (progress, built):
                assert bar.get_text() == f'{percent} %'
                observed = canvas_snapshot(bar.render((20,)))
                assert observed['text'][0].decode().strip() == f'{percent} %'
                assert (observed['cols'], observed['rows']) == (20, 1)
                assert observed['attributes'] == (('filled',) * columns + ('empty',) * (20 - columns),)
        # Rounding down is exact: no rounding up near a whole percent or column, and no
        # binary-fraction loss when the true ratio is a whole percent.
        for current, done, percent in ((199, 200, 99), (29, 100, 29), (57, 100, 57), (2, 3, 66), (999, 1000, 99)):
            progress = velnora.ProgressBar('empty', 'filled', current=current, done=done)
            assert progress.get_text() == f'{percent} %'
            for width in (20, 13, 7):
                columns = current * width // done
                observed = canvas_snapshot(progress.render((width,)))
                assert observed['attributes'] == (('filled',) * columns + ('empty',) * (width - columns),)


def test_cumulative_charts_widths_lines_and_scale():
    # F16.T02: integer heights avoid unspecified fractional-row rounding.
    with encoding_state():
        velnora.set_encoding('utf-8')
        graph = velnora.BarGraph([('background', '.'), ('upper', 'U'), ('lower', 'L')],
                               hatt=['line-bg', 'line-upper', 'line-lower'])
        graph.set_data([[8, 3], [4, 7], [13, -2]], 10)
        expected = ('....UU', '....UU', 'UU..UU', 'UULLUU', 'UULLUU',
                    'UULLUU', 'UULLUU', 'LLLLUU', 'LLLLUU', 'LLLLUU')
        observed = canvas_snapshot(graph.render((6, 10)))
        assert (observed['cols'], observed['rows']) == (6, 10)
        assert observed['text'] == tuple(row.encode() for row in expected)
        styles = {'.': 'background', 'U': 'upper', 'L': 'lower'}
        assert observed['attributes'] == tuple(tuple(styles[ch] for ch in row) for row in expected)
        graph.set_data([[8, 3], [4, 7], [13, -2]], 10, [5])
        lined = canvas_snapshot(graph.render((6, 10)))
        # The reference-line glyph is presentation; observe its position and styles.
        line_rows = [row for row, attributes in enumerate(lined['attributes'])
                     if any(style in {'line-bg', 'line-upper', 'line-lower'} for style in attributes)]
        assert len(line_rows) == 1
        line_row = line_rows[0]
        assert line_row in {4, 5}
        assert lined['attributes'][line_row] == ('line-upper',) * 2 + ('line-lower',) * 2 + ('line-upper',) * 2
        for row in range(10):
            if row != line_row:
                assert lined['text'][row] == observed['text'][row]
                assert lined['attributes'][row] == observed['attributes'][row]
        assert all(ch != ord(' ') for ch in lined['text'][line_row])
        graph.set_data([[8, 3], [4, 7], [13, -2]], 10)
        graph.set_bar_width(2)
        assert canvas_snapshot(graph.render((4, 10)))['text'] == tuple(row[:4].encode() for row in expected)
        graph.set_bar_width(1)
        graph.set_data([[10], [0], [10]], 10)
        assert canvas_snapshot(graph.render((3, 2)))['text'] == (b'U.U', b'U.U')
        # With spare columns the preferred width is still retained; where the spare goes is open.
        spare = canvas_snapshot(graph.render((6, 2)))
        assert (spare['cols'], spare['rows']) == (6, 2)
        for row in spare['text']:
            assert b'U.U' in row and row.count(b'U') == 2
        # A refused width leaves the configured one in place.
        for width in (0, -2):
            with pytest.raises(ValueError):
                graph.set_bar_width(width)
        assert canvas_snapshot(graph.render((3, 2)))['text'] == (b'U.U', b'U.U')
        graph.set_bar_width(None)
        assert canvas_snapshot(graph.render((9, 2)))['text'] == (b'UUU...UUU',) * 2
        # Heights are relative to the supplied maximum, not to a fixed scale or the tallest bar.
        graph.set_data([[16, 6], [8, 14], [26, -4]], 20)
        assert canvas_snapshot(graph.render((6, 10)))['text'] == tuple(row.encode() for row in expected)
        graph.set_data([[2], [1]], 4)
        assert canvas_snapshot(graph.render((2, 4)))['text'] == (b'..', b'..', b'U.', b'UU')
        # Each of several reference lines appears, at its own height.
        graph.set_data([[10, 10], [10, 10]], 10, [2, 7])
        multi = canvas_snapshot(graph.render((2, 10)))
        line_rows = [row for row, attributes in enumerate(multi['attributes'])
                     if set(attributes) & {'line-bg', 'line-upper', 'line-lower'}]
        assert len(line_rows) == 2
        assert line_rows[0] in {2, 3} and line_rows[1] in {7, 8}
        graph.set_data([[8, 3], [4, 7], [13, -2]], 10)
        # No width-remainder tie is specified or tested.
        scale = velnora.GraphVScale([(8, ('high-style', 'high')), (2, ('low-style', 'low'))], 10)
        scaled = canvas_snapshot(scale.render((5, 10)))
        assert (scaled['cols'], scaled['rows']) == (5, 10)
        # Inspect cells adjacent to each exact height; do not pin edge conventions.
        assert b'high ' in scaled['text'][1:3]
        assert b'low  ' in scaled['text'][7:9]
        for text, style in ((b'high ', 'high-style'), (b'low  ', 'low-style')):
            row = scaled['text'].index(text)
            assert scaled['attributes'][row][:len(text.rstrip())] == (style,) * len(text.rstrip())
        doubled = velnora.GraphVScale([(16, ('high-style', 'high')), (4, ('low-style', 'low'))], 20)
        assert canvas_snapshot(doubled.render((5, 10)))['text'] == scaled['text']
        for attributes in ([], ['background']):
            with pytest.raises(BarGraphError):
                velnora.BarGraph(attributes)


def test_fractional_smoothing_and_label_protection():
    # F16.T03: exercise every nonintegral eighth, not a self-reported switch.
    with encoding_state():
        velnora.set_encoding('utf-8')
        for eighth, horizontal, vertical in zip(range(1, 8), '▏▎▍▌▋▊▉', '▁▂▃▄▅▆▇'):
            progress = velnora.ProgressBar('empty', 'filled', eighth / 8, done=16, satt='edge')
            smooth = canvas_snapshot(progress.render((16,)))
            assert smooth['text'][0].decode()[0] == horizontal
            assert smooth['attributes'][0][:len(horizontal.encode())] == ('edge',) * len(horizontal.encode())
            assert smooth['attributes'][0][len(horizontal.encode()):] == ('empty',) * 15
            graph = velnora.BarGraph(['empty', 'filled'], satt={(1, 0): 'edge'})
            graph.set_data([[eighth]], 8)
            bar = canvas_snapshot(graph.render((1, 1)))
            assert bar['text'] == (vertical.encode(),)
            assert bar['attributes'] == (('edge',) * len(vertical.encode()),)
            # The boundary cell is found wherever it falls: an interior blank progress cell...
            progress = velnora.ProgressBar('empty', 'filled', 32 + eighth, done=128, satt='edge')
            smooth = canvas_snapshot(progress.render((16,)))
            assert smooth['text'][0].decode()[4] == horizontal
            assert smooth['text'][0].decode().strip(' ' + horizontal) == progress.get_text()
            size_edge = len(horizontal.encode())
            assert smooth['attributes'][0] == ('filled',) * 4 + ('edge',) * size_edge + ('empty',) * 11
            # ...and the partially filled upper row of a taller bar, over its whole row.
            graph = velnora.BarGraph(['empty', 'filled'], satt={(1, 0): 'edge'})
            graph.set_data([[8 + eighth]], 16)
            tall = canvas_snapshot(graph.render((1, 2)))
            assert tall['text'][0] == vertical.encode()
            assert tall['attributes'] == (('edge',) * len(vertical.encode()), ('filled',))
        # Identical values and sizes, changing only smoothing or output encoding.
        for encoding, smoothing in (('utf-8', False), ('ascii', True)):
            velnora.set_encoding(encoding)
            progress = velnora.ProgressBar('empty', 'filled', 0.5, done=16,
                                         satt='edge' if smoothing else None)
            assert label_lines(progress, 16)[0] in {'      3 %       ', '       3 %      '}
            assert canvas_snapshot(progress.render((16,)))['attributes'] == (('empty',) * 16,)
            graph = velnora.BarGraph(['empty', 'filled'], satt={(1, 0): 'edge'} if smoothing else None)
            graph.set_data([[4]], 8)
            plain = canvas_snapshot(graph.render((1, 1)))
            assert plain['text'] == (b' ',)
            assert plain['attributes'][0][0] in {'empty', 'filled'}
        velnora.set_encoding('utf-8')
        # At 37.5%, the fractional boundary lands on the first label digit.
        progress = velnora.ProgressBar('empty', 'filled', 37.5, satt='edge')
        assert label_lines(progress, 10) == ('   37 %   ',)
        assert canvas_snapshot(progress.render((10,)))['attributes'] == (('filled',) * 3 + ('empty',) * 7,)
        # Whole-cell boundaries must remain whole even with smoothing enabled.
        progress = velnora.ProgressBar('empty', 'filled', 25, satt='edge')
        assert canvas_snapshot(progress.render((16,)))['attributes'] == (('filled',) * 4 + ('empty',) * 12,)
        graph = velnora.BarGraph(['empty', 'filled'], satt={(1, 0): 'edge'})
        graph.set_data([[8]], 8)
        assert canvas_snapshot(graph.render((1, 1)))['attributes'] == (('filled',),)


def test_custom_font_composition_attributes_and_missing_characters():
    # F16.T04: expected artwork comes from caller-supplied data, not Font.render.
    with encoding_state():
        velnora.set_encoding('utf-8')
        font = MosaicFont()
        assert set(font.characters()) == {'A', 'B'}
        assert (font.height, font.char_width('A'), font.char_width('B'), font.char_width('?')) == (3, 2, 3, 0)
        assert font.char_data('A') == ['/\\', '||', '==']
        text = velnora.BigText([('first', 'B'), ('ignored', '?'), ('second', 'A')], font)
        assert text.pack(()) == (5, 3)
        observed = canvas_snapshot(text.render(()))
        assert (observed['cols'], observed['rows']) == (5, 3)
        assert observed['text'] == (b'###/\\', b'# #||', b'###==')
        assert observed['attributes'] == (('first',) * 3 + ('second',) * 2,) * 3
        text.set_text([('second', 'A'), ('first', 'B')])
        assert canvas_snapshot(text.render(()))['text'] == (b'/\\###', b'||# #', b'==###')
        for value in ('', '?'):
            text.set_text(value)
            assert text.pack(()) == (0, 3)
            empty = canvas_snapshot(text.render(()))
            assert (empty['cols'], empty['rows'], empty['text']) == (0, 3, (b'',) * 3)
        # Glyphs may come from any data block; the declared height governs, and repeats add.
        split = TwoBlockFont()
        assert set(split.characters()) == {'P', 'Q', 'R'}
        assert (split.height, split.char_width('P'), split.char_width('R')) == (2, 1, 3)
        assert split.char_data('R') == ['abc', 'def']
        text = velnora.BigText([('first', 'RP'), ('second', 'QQ')], split)
        assert text.pack(()) == (6, 2)
        joined = canvas_snapshot(text.render(()))
        assert joined['text'] == (b'abc122', b'def344')
        assert joined['attributes'] == (('first',) * 4 + ('second',) * 2,) * 2
        text.set_text('')
        assert text.pack(()) == (0, 2)


def test_builtin_font_catalog_digit_geometry_and_distinction():
    # F16.T05: style uses a broad Unicode character-class oracle, never reference artwork.
    sizes = {'Thin 3x3': (3, 3), 'Thin 4x3': (4, 3), 'Thin 6x6': (6, 6),
             'Sextant 3x3': (3, 3), 'Sextant 2x2': (2, 2),
             'Half Block 5x4': (5, 4), 'Half Block 6x5': (6, 5),
             'Half Block Heavy 6x5': (6, 5), 'Half Block 7x7': (7, 7)}
    with encoding_state():
        velnora.set_encoding('utf-8')
        catalog = dict(velnora.get_all_fonts())
        assert sizes.keys() <= catalog.keys()
        rendered = {}
        for name, (width, height) in sizes.items():
            font = catalog[name]()
            required = set('0123456789.')
            if name not in ('Half Block 6x5', 'Half Block Heavy 6x5'):
                required.update(',%')
            if name != 'Sextant 2x2':
                required.update(' /:')
            if name in ('Thin 4x3', 'Sextant 3x3', 'Half Block 5x4', 'Thin 6x6', 'Half Block 7x7'):
                required.update('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
            if name in ('Half Block 5x4', 'Thin 6x6', 'Half Block 7x7'):
                required.update('abcdefghijklmnopqrstuvwxyz{|}~')
            if name in ('Thin 3x3', 'Thin 4x3'):
                required.update('!"\'#${}%*+-;=?[\\]^_`'.replace('{}', ''))
            if name in ('Sextant 3x3', 'Half Block 5x4', 'Thin 6x6', 'Half Block 7x7'):
                required.update(chr(code) for code in range(32, 97) if not chr(code).isalnum())
            assert required <= set(font.characters()), name
            for character in sorted(required - set('0123456789')):
                glyph_width = font.char_width(character)
                assert glyph_width > 0, (name, character)
                glyph = canvas_snapshot(velnora.BigText(('letter-style', character), font).render(()))
                assert (glyph['cols'], glyph['rows']) == (glyph_width, height)
                assert glyph['attributes'] == tuple(('letter-style',) * len(row) for row in glyph['text'])
                if character != ' ':
                    assert any(row.strip() for row in glyph['text']), (name, character)
            assert font.height == height
            glyphs = []
            for digit in '0123456789':
                assert font.char_width(digit) == width
                text = velnora.BigText(('digit-style', digit), font)
                assert text.pack(()) == (width, height)
                observed = canvas_snapshot(text.render(()))
                assert (observed['cols'], observed['rows']) == (width, height)
                assert observed['attributes'] == tuple(('digit-style',) * len(row) for row in observed['text'])
                glyphs.append(observed['text'])
            assert len(set(glyphs)) == 10
            assert_digit_style(name, glyphs)
            rendered[name] = tuple(glyphs)
            # Supporting a letter case means more than one placeholder glyph for all of it.
            for letters in ('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'):
                if set(letters) <= required:
                    shapes = {canvas_snapshot(velnora.BigText(letter, font).render(()))['text'] for letter in letters}
                    assert 2 * len(shapes) >= len(letters), name
        assert rendered['Half Block 6x5'] != rendered['Half Block Heavy 6x5']
        # "Heavy" compared on the same digits at the same size: more inked area in total.
        ink = {name: sum(block_ink(artwork_cells(glyph)) for glyph in rendered[name])
               for name in ('Half Block 6x5', 'Half Block Heavy 6x5')}
        assert ink['Half Block Heavy 6x5'] > ink['Half Block 6x5']
