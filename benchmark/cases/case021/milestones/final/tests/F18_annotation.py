# feature: F18
"""Acceptance checks for source, complete-code and coverage annotation."""
import re
import xml.etree.ElementTree as ET

from _helpers import temporary_project, parse_xml
from F18_helpers import generate_annotation, annotation_classes


SOURCE = '''cdef extern from *:
    """
    static int native_mix(int x) { return x * 7 + 13; }
    static int native_finish(int x) { return x - 5; }
    """
    int native_mix(int x) noexcept nogil
    int native_finish(int x) noexcept nogil

def calculate(int value, object sink):
    cdef int mixed
    mixed = native_mix(value)
    sink.append(mixed)
    mixed = native_finish(mixed)
    return mixed

def convert(object value, object sink):
    cdef int mixed
    mixed = native_mix(value)
    sink.append(mixed)
    mixed = native_finish(mixed)
    return mixed
'''


def test_f18_t01():
    with temporary_project() as project:
        source = project.write('line_annotation.pyx', SOURCE)
        rows, _ = generate_annotation(project, source, '--annotate')
        assert {line: row['source'] for line, row in rows.items()} == dict(
            enumerate(SOURCE.splitlines(), 1))
        native = [11, 13, 20]
        python = 12
        assert all(rows[line]['score'] == 0 for line in native)
        assert rows[python]['score'] > 0
        # Same source text as line 11, but the argument is a Python object, so
        # the assignment converts it through the Python runtime. The category
        # follows the analysed operations, not the spelling of the line.
        assert rows[18]['source'] == rows[11]['source']
        assert rows[18]['score'] > 0
        generated = source.with_suffix('.c').read_text(encoding='utf-8')
        # User-supplied C names identify separate native operations without
        # fixing any compiler-generated identifier or code generation style.
        for line, operation in [(11, 'native_mix'), (13, 'native_finish')]:
            row = rows[line]
            assert row['expandable'] and row['body'] is not None
            code = row['body'].text()
            assert re.search(r'\b' + re.escape(operation) + r'\b', code) and ';' in code
            assert code.strip() != row['source'].strip()
            assert all(part.strip() in generated for part in code.split('/* … */') if part.strip())
        row = rows[python]
        assert row['expandable'] and row['body'] is not None
        assert row['body'].text().strip() and row['body'].text().strip() != row['source'].strip()
        assert rows[11]['body'].text() != rows[13]['body'].text()


def test_f18_t02():
    with temporary_project() as project:
        source = project.write('full_annotation.pyx', SOURCE)
        rows, complete = generate_annotation(project, source, '--annotate-fullc')
        assert len(complete) == 1
        generated = source.with_suffix('.c').read_text(encoding='utf-8')
        # Decode highlighting/HTML entities through the HTML parser, then
        # compare content rather than HTML representation or compiler spelling.
        assert complete[0].strip() == generated.strip()
        expansions = [row['body'].text() for row in rows.values() if row['body'] is not None]
        assert expansions
        assert any(line.strip() and not any(line.strip() in block for block in expansions)
                   for line in complete[0].splitlines())


def test_f18_t03():
    with temporary_project() as project:
        sources = [project.write('coverage_left.pyx', SOURCE),
                   project.write('coverage_right.pyx', SOURCE)]
        # Opposite statuses for the same line numbers in two real source files
        # distinguish filename association from a line-only lookup. A second
        # report reverses them at the same path to expose stale report state.
        for reverse in (False, True):
            root = ET.Element('coverage')
            classes = ET.SubElement(ET.SubElement(ET.SubElement(root, 'packages'), 'package'), 'classes')
            for index, source in enumerate(sources):
                entry = ET.SubElement(classes, 'class', filename=str(source))
                lines = ET.SubElement(entry, 'lines')
                for number in (11, 12, 13):
                    hit = (number == 12) ^ bool(index) ^ reverse
                    ET.SubElement(lines, 'line', number=str(number), hits='3' if hit else '0')
            report = project.write('coverage.xml', ET.tostring(root))
            supplied = parse_xml(report.read_bytes())
            for source in sources:
                rows, _ = generate_annotation(project, source, '--annotate-coverage', str(report))
                entry = next(item for item in supplied.findall('.//class')
                             if item.attrib['filename'] == str(source))
                for item in entry.findall('lines/line'):
                    number = int(item.attrib['number'])
                    expected = 'run' if int(item.attrib['hits']) else 'mis'
                    assert rows[number]['source'] == SOURCE.splitlines()[number - 1]
                    assert rows[number]['coverage'] == {expected}
                    assert rows[number]['body'] is not None
                    assert expected in annotation_classes(rows[number]['body'])
