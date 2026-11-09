# feature: F02
"""Construct and render caller-supplied articles using public library entries."""


def pdf_plain_text(snapshot):
    """Read page text, accepting Unicode ligatures and layout whitespace."""
    import unicodedata

    text = ' '.join(page['text'] for page in snapshot['pages'])
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def render_plain_article(destination, paragraphs, page_size=(420, 560),
                         metadata=None):
    from talvo.dimension import PT
    from talvo.document import DocumentTree
    from talvo.paper import Paper
    from talvo.paragraph import Paragraph
    from talvo.templates import Article

    configuration = Article.Configuration('caller page arrangement')
    configuration('contents_page',
                  page_size=Paper('caller paper', page_size[0]*PT,
                                  page_size[1]*PT),
                  left_margin=40*PT, right_margin=40*PT,
                  top_margin=40*PT, bottom_margin=40*PT)
    document = Article(DocumentTree([Paragraph(text) for text in paragraphs]),
                       configuration=configuration)
    if metadata is not None:
        document.metadata.update(metadata)
    if destination is None:
        return document.render()
    return document.render(str(destination))
