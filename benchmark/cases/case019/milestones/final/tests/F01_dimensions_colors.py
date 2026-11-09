# feature: F01
"""Acceptance checks for physical lengths, contextual widths and colors."""

import pytest

from _helpers import call_public, rasterize_pdf_page
from F01_helpers import (pdf_observer_environment, red_band_widths,
                         render_fraction_widths)
from talvo.attribute import ParseError
from talvo.color import Color, Gray, HexColor
from talvo.dimension import (Dimension, PT, PICA, INCH, MM, CM,
                             PERCENT, HALVES, QUARTERS)


def test_physical_units_and_arithmetic():
    # FP-01.01: point values follow the physical unit definitions.
    for unit, magnitude, points in [(PT, 13.5, 13.5), (PICA, 2.5, 30),
                                     (INCH, 1.25, 90), (MM, 25.4, 72),
                                     (CM, 2.54, 72)]:
        assert float(magnitude * unit) == pytest.approx(points)
        assert float(Dimension(magnitude, unit)) == pytest.approx(points)
    assert float(Dimension(8.75)) == 8.75
    assert 1*INCH == 6*PICA
    assert 10*MM == 1*CM
    assert not (1*INCH == 1*CM)
    assert 2*CM < 1*INCH
    assert 1*INCH > 2*CM
    assert 1*INCH <= 6*PICA
    assert 6*PICA >= 1*INCH
    assert not (1*INCH < 2*CM)
    assert not (2*CM > 1*INCH)
    assert not (1*INCH <= 2*CM)
    assert not (2*CM >= 1*INCH)
    expressions = [(1*INCH + 2*PICA, 96), (2*PICA + 1*INCH, 96),
                   (1*INCH - 2*PICA, 48), (2*PICA - 1*INCH, -48),
                   (-2*PICA, -24), (1.5 * (2*PICA), 36),
                   ((2*PICA) * -2, -48), ((1*INCH) / 4, 18),
                   ((1*INCH) / -2, -36), (1*PICA + 5, 17),
                   (5 + 1*PICA, 17), (1*PICA - 5, 7), (5 - 1*PICA, -7)]
    for expression, points in expressions:
        assert float(expression) == pytest.approx(points)


def test_composed_lengths_follow_operand_changes():
    left, right = 30*PT, 2*PICA
    expressions = [left + right, left - right, -left, left*3, left/4,
                   100 - left, (left + right)*2 - left/2]
    assert [float(e) for e in expressions] == pytest.approx(
        [54, 6, -30, 90, 7.5, 70, 93])
    left.grow(6)
    right.grow(1)
    assert [float(e) for e in expressions] == pytest.approx(
        [72, 0, -36, 108, 9, 64, 126])
    left.grow(-10*PT)
    assert [float(e) for e in expressions] == pytest.approx(
        [62, -10, -26, 78, 6.5, 74, 111])


def test_relative_lengths_and_rendered_content_widths(tmp_path):
    fractions = [35*PERCENT, 1*HALVES, 3*QUARTERS]
    for reference in (200, 340*PT):
        assert [f.to_points(reference) for f in fractions] == pytest.approx(
            [float(reference)*0.35, float(reference)*0.5, float(reference)*0.75])
    observer_env = pdf_observer_environment(tmp_path / 'pdf-observer')
    # The same public width values must bind to the actual containing block.
    for containing_width in (240, 360):
        destination = tmp_path / ('widths-{}'.format(containing_width))
        result = call_public(render_fraction_widths, destination,
                             containing_width, fractions)
        assert result.exception is None, result.traceback
        assert result.value is True
        image = destination.with_suffix('.png')
        rasterize_pdf_page(destination.with_suffix('.pdf'), image, dpi=144,
                           env=observer_env)
        # Raster extents allow equivalent PDF drawing operators and encodings.
        # Two pixels per point: allow two edge pixels for raster rounding.
        assert sorted(red_band_widths(image, pixels_per_point=2)) == pytest.approx(
            [containing_width*0.35, containing_width*0.5,
             containing_width*0.75], abs=1)



def test_textual_lengths_and_malformed_input():
    for text, points in [('13.5pt', 13.5), ('2.5 pc', 30), ('1.25in', 90),
                         ('25.4 mm', 72), ('-2.54 cm', -72), ('0', 0)]:
        assert float(Dimension.from_string(text)) == pytest.approx(points)
    for text, points in [('35%', 70), ('1/2', 100), ('3/4', 150)]:
        assert Dimension.from_string(text).to_points(200*PT) == pytest.approx(points)
    for text in ('4furlong', '12', '-3.5', 'pt'):
        with pytest.raises(ParseError):
            Dimension.from_string(text)


def test_color_components_gray_and_ranges():
    for values in [(0.13, 0.57, 0.91), (0, 1, 0), (1, 0, 1),
                   (0.2, 0.4, 0.6, 0.35), (0, 1, 0.5, 0), (1, 0, 0.5, 1)]:
        color = Color(*values)
        assert (color.r, color.g, color.b, color.a) == (
            values if len(values) == 4 else (*values, 1))
    for brightness in (0, 0.37, 1):
        gray = Gray(brightness)
        assert (gray.r, gray.g, gray.b, gray.a) == (brightness,)*3 + (1,)
        gray = Gray(brightness, 0.24)
        assert (gray.r, gray.g, gray.b, gray.a) == (brightness,)*3 + (0.24,)
    for index in range(4):
        for invalid in (-0.01, 1.01):
            values = [0.2, 0.4, 0.6, 0.8]
            values[index] = invalid
            with pytest.raises(ValueError):
                Color(*values)
    for brightness, alpha in [(-0.01, 1), (1.01, 1), (0.5, -0.01), (0.5, 1.01)]:
        with pytest.raises(ValueError):
            Gray(brightness, alpha)


def test_hexadecimal_color_forms_and_rejection():
    # Independent channel values, not a product encode/decode round trip.
    vectors = [('#39c', (51, 153, 204, 255)),
               ('a2D7', (170, 34, 221, 119)),
               ('#174Ba2', (23, 75, 162, 255)),
               ('D1386A52', (209, 56, 106, 82)),
               ('#0000', (0, 0, 0, 0)), ('#FFFFFF', (255, 255, 255, 255))]
    for text, channels in vectors:
        expected = tuple(c/255 for c in channels)
        for color in (HexColor(text), Color.from_string(text)):
            assert (color.r, color.g, color.b, color.a) == pytest.approx(expected)
    for text in ('', '#12', '#12345', '0011223', '#1122334455', '#gg0000'):
        with pytest.raises(ValueError):
            HexColor(text)
        with pytest.raises(ParseError):
            Color.from_string(text)
