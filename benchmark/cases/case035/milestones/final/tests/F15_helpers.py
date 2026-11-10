# feature: F15
"""Direct readers for inspection reports and real repository fixtures."""
import re
from collections import Counter
from packaging.utils import canonicalize_name
from packaging.version import Version
from packaging.specifiers import SpecifierSet
from _helpers import parse_json
from F01_helpers import project_cli, succeeded, wheel_observation


def inspection_rows(project, env, *options):
    rows = parse_json(succeeded(project_cli(project, env, 'show', '--format=json', *options)).stdout)
    result = {canonicalize_name(row['name']): row for row in rows}
    assert len(result) == len(rows), rows
    return result


def described_wheel(factory, name, version='1.0', *, dependencies=()):
    source, wheel = factory.create(name, version, dependencies=dependencies)
    document = source / 'pyproject.toml'
    document.write_text(document.read_text().replace('[project]\n', '[project]\ndescription="Inspection metadata for ' + name + '"\n'))
    wheel_observation(source, factory.env)
    return wheel


def equivalent_constraint(text, accepted, rejected):
    # Public reports spell exact constraints as bare versions.
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", text):
        text = "==" + text
    spec = SpecifierSet(text)
    assert all(Version(v) in spec for v in accepted), text
    assert all(Version(v) not in spec for v in rejected), text


def inspection_tree(text):
    """Read root/name lines and four-column tree edges, retaining ancestry."""
    paths = []
    stack = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'((?:[│| ]   )*)(?:[├└]──|[|`]--) ([A-Za-z0-9_.-]+) (.+)', line)
        if match:
            depth = len(match[1]) // 4 + 1
            assert depth <= len(stack), text
            stack = stack[:depth]
            stack.append(canonicalize_name(match[2]))
            paths.append((tuple(stack), bool(re.search(r'\s\([^()]+\)\s*$', match[3]))))
        else:
            match = re.fullmatch(r'([A-Za-z0-9_.-]+) (\S+)(?: .*)?', line)
            assert match, text
            Version(match[2])
            stack = [canonicalize_name(match[1])]
            paths.append((tuple(stack), False))
    return Counter(paths)


def search_rows(text):
    """Read the compact table's named columns; descriptions are not interpreted."""
    lines = [line for line in text.splitlines() if line.strip()]
    header = re.fullmatch(r'\s*Package\s+Version\s+Source\s+Description\s*', lines[0])
    assert header, text
    rows = []
    for line in lines[1:]:
        match = re.fullmatch(r'\s*(\S+)\s+(\S+)\s+(\S+)(?:\s+.*)?', line)
        assert match, text
        rows.append((canonicalize_name(match[1]), Version(match[2]), match[3]))
    return Counter(rows)


def listing_page(root, names):
    (root / 'simple' / 'index.html').write_text('\n'.join(
        '<a href="' + n + '/">' + n + '</a>' for n in names))


def resolution_rows(text):
    before, separator, report = text.partition('Resolution results:\n')
    assert separator, text
    result = {}
    for line in report.splitlines():
        if not line.strip():
            continue
        fields = line.split(maxsplit=2)
        assert len(fields) >= 2, text
        name = canonicalize_name(fields[0])
        assert name not in result, text
        result[name] = Version(fields[1])
    return result


def diagnostic_sections(text):
    sections = {}
    section = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line in ('Velnora', 'Virtualenv', 'Base'):
            section = line
            sections[section] = {}
        else:
            label, separator, value = line.partition(':')
            assert separator and section is not None, text
            assert label not in sections[section], text
            sections[section][label] = value.strip()
    return sections
