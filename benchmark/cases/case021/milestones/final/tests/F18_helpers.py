# feature: F18
"""Read the public annotation HTML structure without inferring prose."""
from _helpers import HTMLNode, parse_html
from F01_helpers import translate_source


def annotation_classes(node):
    return set(dict(node.attrs).get('class', '').split())


def read_annotation(source):
    document = parse_html(source.with_suffix('.html').read_bytes())
    rows = {}
    complete = []
    for container in document.elements('div'):
        if 'velora' not in annotation_classes(container):
            continue
        children = [child for child in container.content if isinstance(child, HTMLNode)]
        for index, node in enumerate(children):
            classes = annotation_classes(node)
            if node.tag != 'pre' or not {'velora', 'line'} <= classes:
                continue
            if not any(value.startswith('score-') for value in classes):
                # The full-source section has a published label and no score.
                if node.text() == '+ Complete veloraized code':
                    assert index + 1 < len(children), 'Missing complete-source body'
                    body = children[index + 1]
                    assert body.tag == 'pre' and {'velora', 'code'} <= annotation_classes(body)
                    complete.append(body.text())
                continue
            number = next(child for child in node.content if isinstance(child, HTMLNode))
            assert number.tag == 'span'
            line = int(number.text())
            assert line not in rows, 'Duplicate annotated source line'
            # The first span is the line-number carrier; subsequent nodes carry
            # the colon separator and highlighted original source.
            number_index = node.content.index(number)
            text = ''.join(child.text() if isinstance(child, HTMLNode) else child
                           for child in node.content[number_index + 1:])
            assert text.startswith(': ')
            body = None
            if index + 1 < len(children):
                candidate = children[index + 1]
                if candidate.tag == 'pre' and {'velora', 'code'} <= annotation_classes(candidate):
                    body = candidate
            scores = [int(value.removeprefix('score-')) for value in classes
                      if value.startswith('score-')]
            assert len(scores) == 1
            rows[line] = {'source': text[2:], 'score': scores[0],
                          'coverage': annotation_classes(number), 'body': body,
                          'expandable': 'onclick' in dict(node.attrs)}
    assert rows, 'No source-line annotation records'
    return rows, complete


def generate_annotation(project, source, *options):
    result = translate_source(project, source, options=options)
    assert result.returncode == 0, result.text('stderr')
    return read_annotation(source)
