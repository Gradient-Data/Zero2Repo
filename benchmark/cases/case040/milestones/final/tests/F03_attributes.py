# feature: F03
"""Acceptance coverage for palette, layered styling and hyperlink metadata."""
import math

import pytest
import velnora
from velnora import AttrSpecError
from velnora.display.raw import Screen
from F03_helpers import (CUBE_256, CUBE_88, EFFECTS, GRAY_256, GRAY_88, effect_flags, nearest,
                         resolved_render)


def test_color_modes_palette_and_rejections():
    names = ('black', 'dark red', 'dark green', 'brown', 'dark blue',
             'dark magenta', 'dark cyan', 'light gray', 'dark gray',
             'light red', 'light green', 'yellow', 'light blue',
             'light magenta', 'light cyan', 'white')
    screen = Screen()
    implicit = velnora.AttrSpec('h173', 'h229')
    assert (implicit.foreground_number, implicit.background_number) == (173, 229)
    for number, name in enumerate(names):
        direct = velnora.AttrSpec(name, name, 16)
        assert (direct.foreground_number, direct.background_number) == (number, number)
        screen.register_palette([(name, name, name)])
        resolved = screen.resolve_attr(name, 0)
        assert (resolved.foreground_number, resolved.background_number) == (number, number)
    for mode in (1, 16, 88, 256, 2**24):
        default = velnora.AttrSpec('default,bold', 'default', mode)
        assert default.foreground_basic is False
        assert default.background_basic is False
        assert default.get_rgb_values() == (None,) * 6
        assert default.bold
    for mode in (88, 256):
        for number in (0, 16, mode - 1):
            attr = velnora.AttrSpec(f'h{number}', f'h{number}', mode)
            assert (attr.foreground_number, attr.background_number) == (number, number)
        for invalid in (f'h{mode}', 'h-1'):
            for fg, bg in ((invalid, 'default'), ('default', invalid)):
                with pytest.raises(AttrSpecError):
                    velnora.AttrSpec(fg, bg, mode)
    # True-color mode accepts the 256 indices, and only those.
    assert velnora.AttrSpec('h0', 'h255', 2**24).get_rgb_values()[:3] == (0, 0, 0)
    for fg, bg in (('h256', 'default'), ('default', 'h256'), ('h-1', 'default')):
        with pytest.raises(AttrSpecError):
            velnora.AttrSpec(fg, bg, 2**24)
    # Resolve independently specified palette appearances through every public mode.
    screen.register_palette([('multi', 'dark red,bold', 'dark blue', 'underline', '#ddb', '#004'),
                             ('copy', 'multi'), ('basic-only', 'yellow,blink', 'dark green')])
    expected_rgb = {0: (205, 0, 0, 0, 0, 238), 2: (205, 205, 205, 0, 0, 0),
                    3: (215, 215, 175, 0, 0, 95), 4: (215, 215, 175, 0, 0, 95)}
    for index in range(5):
        value = screen.resolve_attr('multi', index)
        copied = screen.resolve_attr('copy', index)
        assert copied.get_rgb_values() == value.get_rgb_values()
        assert effect_flags(copied) == effect_flags(value)
        if index == 1:
            assert value.get_rgb_values() == (None,) * 6
            assert effect_flags(value) == (False, False, False, True, False, False, False)
        else:
            assert value.get_rgb_values() == expected_rgb[index]
            assert value.bold is (index == 0)
        basic = screen.resolve_attr('basic-only', index)
        if index == 1:
            assert basic.get_rgb_values() == (None,) * 6
            assert not any(effect_flags(basic))
        else:
            assert (basic.foreground_number, basic.background_number) == (11, 2)
            assert basic.blink
    # Either indexed high-color channel above fifteen makes the 88-color pair basic.
    for foreground_high, background_high in [('h196', '#004'), ('#ddb', 'h21'), ('h16', 'h0')]:
        screen.register_palette_entry('indexed', 'yellow,bold', 'dark green',
                                      foreground_high=foreground_high, background_high=background_high)
        basic = screen.resolve_attr('indexed', 2)
        assert (basic.foreground_number, basic.background_number) == (11, 2)
        assert basic.bold
        high = screen.resolve_attr('indexed', 3)
        assert high.get_rgb_values() != basic.get_rgb_values()
    # Indices up to fifteen keep the 88-color high appearance.
    screen.register_palette_entry('indexed', 'yellow,bold', 'dark green',
                                  foreground_high='h15', background_high='h0')
    kept = screen.resolve_attr('indexed', 2)
    assert (kept.foreground_number, kept.background_number) == (15, 0)
    assert not kept.bold
    screen.register_palette_entry('multi', 'white', 'black')
    assert screen.resolve_attr('multi', 0).foreground_number == 15
    assert screen.resolve_attr('copy', 0).foreground_number == 1
    assert screen.resolve_attr('copy', 3).get_rgb_values() == expected_rgb[3]
    with pytest.raises(velnora.ScreenError):
        screen.register_palette([('invalid-copy', 'not-registered')])
    # Explicit colors are unavailable in monochrome and beyond-basic colors in 16-color mode;
    # effects and default or inherited colors remain available.
    for fg, bg, mode in [('bold,underline', 'default', 1), ('inherit,italics', 'inherit', 1),
                         ('dark red,bold,no-italics', 'default', 16)]:
        velnora.AttrSpec(fg, bg, mode)
    for fg, bg, mode in [('unknown-color', 'default', 256), ('default', 'unknown-color', 256),
                         ('black', 'default', 1), ('default', 'white', 1),
                         ('h3', 'default', 1), ('g50', 'default', 1), ('default', '#fff', 1),
                         ('h5', 'default', 16), ('default', '#fff', 16), ('g50', 'default', 16),
                         ('default', 'default', 42)]:
        with pytest.raises(AttrSpecError):
            velnora.AttrSpec(fg, bg, mode)
    # Repeated or contradictory effect declarations are refused.
    for fg in ('bold,bold', 'bold,no-bold', 'no-italics,italics',
               'dark red,underline,underline', 'no-blink,no-blink'):
        with pytest.raises(AttrSpecError):
            velnora.AttrSpec(fg, 'default')


def test_rgb_quantization_and_grayscale():
    for fg, bg, expected in [('#0017ff', '#fe8001', (0, 23, 255, 254, 128, 1)),
                             ('#a54c09', '#ffffff', (165, 76, 9, 255, 255, 255))]:
        assert velnora.AttrSpec(fg, bg, 2**24).get_rgb_values() == expected
    # These vectors were observed on the original; none uses a nearest-level tie.
    # Oracle: each sixteen-level component selects the nearest palette component of L/15 intensity.
    for mode, levels in [(256, CUBE_256), (88, CUBE_88), (2**24, CUBE_256)]:
        for level in range(16):
            digit = '%x' % level
            want = nearest(levels, level * 255 / 15)
            rgb = velnora.AttrSpec('#%s00' % digit, '#0%s%s' % (digit, digit), mode).get_rgb_values()
            assert rgb == (want, 0, 0, 0, want, want), (mode, level)
        if mode == 2**24:
            continue
        for value in range(256):
            want = nearest(levels, (value // 16) * 255 / 15)
            rgb = velnora.AttrSpec('#%02x0000' % value, '#00%02x%02x' % (value, value), mode).get_rgb_values()
            assert rgb == (want, 0, 0, 0, want, want), (mode, value)
    for mode, levels in [(256, GRAY_256), (88, GRAY_88), (2**24, GRAY_256)]:
        for percent in range(101):
            exact = percent * 255 / 100
            # Rounding to the nearest intensity; an exact half may round either way.
            allowed = {nearest(levels, math.floor(exact + 0.5)), nearest(levels, math.ceil(exact - 0.5))}
            rgb = velnora.AttrSpec(f'g{percent}', 'default', mode).get_rgb_values()
            assert rgb[0] == rgb[1] == rgb[2] and rgb[0] in allowed, (mode, percent, rgb)
    for mode, expected in [(256, (215, 215, 175, 0, 0, 95)),
                           (88, (205, 205, 205, 0, 0, 0))]:
        assert velnora.AttrSpec('#ddb', '#004', mode).get_rgb_values() == expected
        values = []
        for percent in range(101):
            rgb = velnora.AttrSpec(f'g{percent}', f'g{100-percent}', mode).get_rgb_values()
            assert rgb[0] == rgb[1] == rgb[2]
            assert rgb[3] == rgb[4] == rgb[5]
            values.append((rgb[0], rgb[3]))
        assert values[0] == (0, 255)
        assert values[-1] == (255, 0)
        assert all(a[0] <= b[0] and a[1] >= b[1] for a, b in zip(values, values[1:]))
        assert len({fg for fg, bg in values}) == (26 if mode == 256 else 10)


def test_nested_color_and_effect_inheritance():
    screen = Screen()
    screen.register_palette([(None, 'light gray', 'dark magenta'),
                             ('outer', 'yellow,' + ','.join(EFFECTS), 'dark blue')])
    children = [velnora.AttrSpec('dark red', 'inherit'),
                velnora.AttrSpec('inherit', 'dark green'),
                velnora.AttrSpec('default', 'default')]
    for child, fg, bg, flags in [(children[0], 1, 4, (True,) * 7),
                                 (children[1], 11, 2, (True,) * 7),
                                 (children[2], None, None, (False,) * 7),
                                 (velnora.AttrSpec(), 11, 4, (True,) * 7)]:
        widget = velnora.AttrMap(velnora.Text(('outer', ['A', (child, 'B'), 'C'])), None)
        text, rows = resolved_render(screen, widget, 3)
        assert text == (b'ABC',)
        left, middle, right = rows[0]
        assert effect_flags(left) == effect_flags(right) == (True,) * 7
        assert effect_flags(middle) == flags
        if fg is None:
            assert middle.get_rgb_values() == (None,) * 6
        else:
            assert (middle.foreground_number, middle.background_number) == (fg, bg)
    for position, effect in enumerate(EFFECTS):
        child = velnora.AttrSpec('inherit,no-' + effect, 'inherit')
        text, rows = resolved_render(screen, velnora.Text(('outer', (child, 'X'))), 1)
        assert text == (b'X',)
        assert effect_flags(rows[0][0]) == tuple(i != position for i in range(7))
        text, rows = resolved_render(screen, velnora.Text((velnora.AttrSpec('inherit,' + effect, 'inherit'), 'Y')), 1)
        assert effect_flags(rows[0][0]) == tuple(i == position for i in range(7))
        assert (rows[0][0].foreground_number, rows[0][0].background_number) == (7, 5)


def test_mapping_focus_blanks_and_palette_replacement():
    screen = Screen()
    screen.register_palette([('normal', 'white', 'dark blue'), ('focus', 'black', 'light cyan'),
                             ('marked', 'dark red', 'dark cyan')])
    widget = velnora.AttrMap(velnora.Text([('tag', 'A'), 'B']),
                          {None: 'normal', 'tag': 'marked'},
                          {None: 'focus', 'tag': 'marked'})
    for focus, background, foreground in [(False, 4, 15), (True, 14, 0), (False, 4, 15)]:
        text, rows = resolved_render(screen, widget, 5, focus)
        assert text == (b'AB   ',)
        assert [(a.foreground_number, a.background_number) for a in rows[0]] == [(1, 6)] + [(foreground, background)] * 4
    screen.register_palette_entry('normal', 'yellow', 'dark green')
    text, rows = resolved_render(screen, widget, 5)
    assert text == (b'AB   ',)
    assert [(a.foreground_number, a.background_number) for a in rows[0]] == [(1, 6)] + [(11, 2)] * 4


def test_nested_hyperlink_scope_and_removal():
    screen = Screen()
    outer = velnora.AttrSpec(hyperlink=velnora.Hyperlink('https://example.org/outer', id='group'))
    replacement = velnora.AttrSpec(hyperlink=velnora.Hyperlink('https://example.org/inner', id='part'))
    removed = velnora.AttrSpec(hyperlink=velnora.Hyperlink('', id=''))
    widget = velnora.AttrMap(velnora.Text(['A', (velnora.AttrSpec('dark red', 'default'), 'B'),
                                     (replacement, ['C', (removed, 'D'), 'E']), 'F']), outer)
    text, rows = resolved_render(screen, widget, 6)
    assert text == (b'ABCDEF',)
    assert [(a.hyperlink.uri, a.hyperlink.id) for a in rows[0]] == [
        ('https://example.org/outer', 'group'), ('https://example.org/outer', 'group'),
        ('https://example.org/inner', 'part'), ('', ''),
        ('https://example.org/inner', 'part'), ('https://example.org/outer', 'group')]


def test_hyperlink_validation_and_length_boundaries():
    printable = ''.join(chr(i) for i in range(32, 127))
    identity = printable.replace(':', '').replace(';', '')
    for uri, link_id in [(printable, identity), ('', ''), ('x' * 2083, 'i' * 250),
                         ('https://example.org', '')]:
        link = velnora.Hyperlink(uri, id=link_id)
        assert (link.uri, link.id) == (uri, link_id)
    for char in ('\x00', '\n', '\x1b', '\x7f', '\x80', '中'):
        for uri, link_id in [('https://example.org/' + char, ''), ('https://example.org', 'a' + char)]:
            with pytest.raises(ValueError):
                velnora.Hyperlink(uri, id=link_id)
    for uri, link_id in [('x' * 2084, ''), ('x', 'i' * 251), ('', 'id'), ('x', 'a:b'), ('x', 'a;b')]:
        with pytest.raises(ValueError):
            velnora.Hyperlink(uri, id=link_id)


def test_indexed_rgb_and_integer_grayscale_intensity():
    basic = [(0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
             (0, 0, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229),
             (127, 127, 127), (255, 0, 0), (0, 255, 0), (255, 255, 0),
             (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]
    for mode, cube, grays in ((88, CUBE_88, GRAY_88), (256, CUBE_256, GRAY_256),
                               (2**24, CUBE_256, GRAY_256)):
        palette = basic + [(r, g, b) for r in cube for g in cube for b in cube]
        palette += [(g, g, g) for g in grays[1:-1]]
        for index, rgb in enumerate(palette):
            assert velnora.AttrSpec(f'h{index}', f'h{index}', mode).get_rgb_values() == rgb * 2
        for intensity in range(256):
            other = 255 - intensity
            fg, bg = nearest(grays, intensity), nearest(grays, other)
            actual = velnora.AttrSpec(f'g#{intensity:02x}', f'g#{other:02x}', mode)
            assert actual.get_rgb_values() == (fg, fg, fg, bg, bg, bg)
