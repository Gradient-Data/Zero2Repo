# feature: F16
"""Template rendering and direct PDF page-label observations."""
from talvo.document import DocumentTree
from _helpers import call_public, observe_pdf
from F07_helpers import visible_lines


def render_template(destination, template, configuration, elements, metadata=None):
    document = template(DocumentTree(elements), configuration=configuration)
    if metadata:
        document.metadata.update(metadata)
    return document.render(str(destination))


def template_snapshot(destination, template, configuration, elements, environment, metadata=None):
    result = call_public(render_template, destination, template, configuration,
                         elements, metadata, cwd=destination.parent, timeout=120)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr, result.warnings)
    snapshot = observe_pdf(destination.with_suffix('.pdf'), env=environment)
    return snapshot


def page_label_field():
    """Caller-labelled page field; numbering remains the selected part's choice."""
    from talvo.reference import Field, PAGE_NUMBER
    from talvo.text import MixedStyledText
    return MixedStyledText(['PageLabel|', Field(PAGE_NUMBER), '|EndLabel'])


def footer_labels(snapshot):
    """Read only the caller-labelled page-number field, never running prose."""
    labels = []
    for index, page in enumerate(snapshot['pages']):
        lines = [line['text'] for line in visible_lines(snapshot)
                 if line['page'] == index and line['text'].startswith('PageLabel|')]
        assert len(lines) <= 1, lines
        if lines:
            fields = lines[0].split('|')
            assert len(fields) == 3 and fields[2] == 'EndLabel', lines
            labels.append(fields[1])
        else:
            labels.append(None)
    return labels


def assert_tex_gyre(snapshot, token):
    from F05_helpers import token_spans
    assert token_spans(snapshot, token)['font'].lower().startswith('texgyre')
