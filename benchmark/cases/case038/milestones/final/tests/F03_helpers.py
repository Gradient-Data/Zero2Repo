# feature: F03
"""Public regex observations and independently sourced Unicode vectors."""
import re
from velunara import translate_pattern
from _helpers import observe


def compiled_pattern(pattern, **options):
    translated = observe(translate_pattern, pattern, **options).value
    return re.compile(translated, options.get('flags', 0))


def xml_content(element):
    """Read expanded names and mixed content without serialization choices."""
    return (element.tag, dict(element.attrib), element.text,
            [(xml_content(child), child.tail) for child in element])


# Unicode 16.0 UCD DerivedAge.txt and UnicodeData.txt: one newly assigned
# character at each supplied database boundary (not product-generated data).
UNICODE_VECTORS = (
    ('13.0.0', '\U0001FA84', 'So'),
    ('14.0.0', '\U0001FAE0', 'So'),
    ('15.0.0', '\U0001FAE8', 'So'),
    ('15.1.0', '\U0002EBF0', 'Lo'),
    ('16.0.0', '\U0001FAE9', 'So'),
)
# UCD Blocks.txt for the corresponding releases; endpoints are block
# boundaries, regardless of whether individual codepoints are assigned.
UNICODE_BLOCKS = (
    ('13.0.0', 'CJKUnifiedIdeographsExtensionG', 0x30000, 0x3134F),
    ('14.0.0', 'Tangsa', 0x16A70, 0x16ACF),
    ('15.0.0', 'CJKUnifiedIdeographsExtensionH', 0x31350, 0x323AF),
    ('15.1.0', 'CJKUnifiedIdeographsExtensionI', 0x2EBF0, 0x2EE5F),
    ('16.0.0', 'Todhri', 0x105C0, 0x105FF),
)
# UnicodeData.txt: assigned characters whose general category changed at a
# release boundary (the old category must no longer contain them).
RECATEGORIZED = (
    ('14.0.0', '\u1734', 'Mn', 'Mc'),
    ('16.0.0', '\U0001171E', 'Mn', 'Mc'),
)
# Blocks.txt: blocks whose range changed (grew or shrank) between releases;
# each entry lists (first release with this range, start, end).
RESIZED_BLOCKS = (
    ('Ahom', (('13.0.0', 0x11700, 0x1173F), ('14.0.0', 0x11700, 0x1174F))),
    ('TangutSupplement', (('13.0.0', 0x18D00, 0x18D8F), ('14.0.0', 0x18D00, 0x18D7F))),
    ('EgyptianHieroglyphFormatControls', (('13.0.0', 0x13430, 0x1343F),
                                          ('15.0.0', 0x13430, 0x1345F))),
)
EXPLICIT_VERSIONS = (
    '2.0.0', '2.1.2', '2.1.5', '2.1.8', '2.1.9', '3.0.0', '3.0.1',
    '3.1.0', '3.1.1', '3.2.0', '4.0.0', '4.0.1', '4.1.0', '5.0.0',
    '5.1.0', '5.2.0', '6.0.0', '6.1.0', '6.2.0', '6.3.0', '7.0.0',
    '8.0.0', '9.0.0', '10.0.0', '11.0.0', '12.0.0', '12.1.0',
    '13.0.0', '14.0.0', '15.0.0', '15.1.0', '16.0.0',
)
