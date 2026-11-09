# feature: F06
"""Render language and string configuration through real document content."""


def render_language_book(destination, language=None, replacements=(), custom=(),
                         kinds=('warning', 'note'), section_reference=False):
    from talvo.document import DocumentTree
    from talvo.flowable import DummyFlowable
    from talvo.language import Language
    from talvo.paragraph import Paragraph
    from talvo.strings import Strings, StringField
    from talvo.structure import Section, Heading, Admonition, AdmonitionFlowables
    from talvo.templates import Book

    options = dict(parts=['contents'])
    if language is not None:
        options['language'] = Language.from_string(language)
    strings = Strings()
    for key, value in replacements:
        strings['@' + key] = value
    for key, value in custom:
        strings['$' + key] = value
    options['strings'] = strings
    if section_reference:
        from F05_helpers import caller_sheet
        from talvo.text import SingleStyledText
        options['stylesheet'] = caller_sheet([('reference numbering', Heading,
            dict(number_separator=SingleStyledText('.')))], base='sphinx')
    configuration = Book.Configuration('language observation', **options)
    if custom:
        # Exercise the same custom values in independently rendered locations.
        from talvo.text import MixedStyledText
        footer = MixedStyledText(['FooterStart '] +
                                 [StringField(key, user=True) + ' / ' for key, _ in custom] +
                                 ['FooterEnd'])
        configuration('contents_page', footer_text=footer)
        configuration('contents_right_page', chapter_footer_text=footer)
    content = [Heading('Orchard survey'), Paragraph('BodyStart')]
    for kind in kinds:
        content.append(Admonition(
            DummyFlowable(),
            AdmonitionFlowables([Paragraph('Advice for ' + kind)]),
            type=kind))
    for key, _ in custom:
        content.append(Paragraph('FirstUse ' + StringField(key, user=True) + ' EndFirst'))
        content.append(Paragraph('SecondUse ' + StringField(key, user=True) + ' EndSecond'))
    if section_reference:
        from talvo.reference import Reference
        content.append(Section([Heading('Nested heading'), Paragraph('Nested body')],
                               id='nested'))
        content.append(Paragraph(['SectionStart ', Reference('nested', type='reference'), ' SectionEnd']))
    content.append(Paragraph('BodyEnd'))
    return Book(DocumentTree([Section(content)]), configuration=configuration).render(str(destination))
