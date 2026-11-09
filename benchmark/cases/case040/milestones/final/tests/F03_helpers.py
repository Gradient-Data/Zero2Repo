# feature: F03
"""Resolve rendered attributes through the public screen interface."""
from _helpers import canvas_snapshot

EFFECTS = ('bold', 'faint', 'italics', 'underline', 'blink', 'standout', 'strikethrough')

# Available component and gray intensities stated by the requirements.
CUBE_256 = (0, 95, 135, 175, 215, 255)
CUBE_88 = (0, 139, 205, 255)
GRAY_256 = (0, 8, 18, 28, 38, 48, 58, 68, 78, 88, 98, 108, 118, 128, 132, 148, 158, 168,
            178, 188, 198, 208, 218, 228, 238, 255)
GRAY_88 = (0, 46, 92, 115, 139, 162, 185, 208, 231, 255)


def nearest(levels, intensity):
    """Nearest available intensity; ties favor the brighter one."""
    return min(levels, key=lambda level: (abs(level - intensity), -level))


def resolved_render(screen, widget, width, focus=False, index=0):
    snapshot = canvas_snapshot(widget.render((width,), focus=focus))
    return snapshot['text'], tuple(
        tuple(screen.resolve_attr(attr, index) for attr in row)
        for row in snapshot['attributes'])


def effect_flags(spec):
    return tuple(getattr(spec, name) for name in EFFECTS)


def is_default_attr(attribute):
    """Recognize the default visible style independently of its carrier."""
    return attribute is None or (
        attribute.get_rgb_values() == (None,) * 6
        and not any(effect_flags(attribute))
        and (attribute.hyperlink is None or attribute.hyperlink.uri == "")
    )
