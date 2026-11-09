# feature: F03
"""Resource listing parsers and a real, locally installed resource distribution."""

import os
import re
import sys
import uuid
from _helpers import run_command, write_text


def resource_cli(*args, env=None, cwd=None):
    # Inherit the shared bootstrap's fresh installed submission.
    child_env = dict(os.environ if env is None else env)
    result = run_command((sys.executable, '-m', 'talvo', *args),
                         env=child_env, cwd=cwd, timeout=120)
    assert result.returncode == 0, result
    return result.stdout.decode('utf-8')


def listed_names(text, kind):
    """Read the fixed record grammar, without asserting human descriptions."""
    patterns = {
        'templates': r'^- (.+)$',
        'stylesheets': r'^- (.+)$',
        'formats': r'^- (.+) \(\.[^\n]+\) \[[^\n]+\]$',
        'fonts': r'^- (.+) \[[^\n]+\]$',
    }
    return {match.casefold() for match in
            re.findall(patterns[kind], text, re.MULTILINE)}


def listed_faces(text):
    families = {}
    current = None
    for line in text.splitlines():
        family = re.fullmatch(r'- (.+) \[([^\n]+)\]', line)
        if family:
            current = family[1].casefold()
            families[current] = set()
        elif line.startswith('   '):
            record = re.fullmatch(r'   ([^:]+): (.+)', line)
            assert record is not None and current is not None, line
            for style in record[2].split(', '):
                families[current].add((record[1].casefold(), style.casefold()))
    return families


def listed_options(text):
    # Description prose is not graded; name, accepted type and default have
    # dedicated delimiters in the CLI's published record form.
    return {name: (kind, default) for name, kind, default in re.findall(
        r'^- ([^ ]+) \(([^)]+)\): .*\. Default: (.*)$', text, re.MULTILINE)}


def install_resource_bundle(directory):
    """Install executable extension code using pip, never inject entry points."""
    token = 'probe' + uuid.uuid4().hex[:12]
    package = directory / 'package'
    package.mkdir()
    names = {kind: token + kind for kind in
             ('reader', 'empty', 'template', 'sheet', 'face')}
    source = '''from pathlib import Path
from talvo.attribute import Attribute, Integer, Bool
from talvo.frontend import Reader
from talvo.document import DocumentTree
from talvo.paragraph import Paragraph, ParagraphStyle
from talvo.templates import Article
from talvo.templates.article import ArticleBodyPageTemplate
from talvo.paper import Paper
from talvo.dimension import PT
from talvo.style import StyleSheet
from talvo.color import Color
from talvo.font import Typeface
from talvo.fonts.adobe14 import courier

class PlainReader(Reader):
    extensions = ('probe',)
    copies = Attribute(Integer, 2, 'Number of copies')
    uppercase = Attribute(Bool, False, 'Convert letters to capitals')
    def parse(self, filename):
        text = Path(filename).read_text(encoding='utf-8')
        if self['uppercase']:
            text = text.upper()
        return DocumentTree([Paragraph(text) for _ in range(self['copies'])])

class EmptyReader(Reader):
    extensions = ('emptyprobe',)
    def parse(self, filename):
        return DocumentTree([Paragraph(Path(filename).read_text())])

class SizedArticle(Article):
    contents_page = ArticleBodyPageTemplate(page_size=Paper('extension', 360*PT, 500*PT),
                                   left_margin=40*PT, right_margin=40*PT,
                                   top_margin=40*PT, bottom_margin=40*PT)

face = Typeface(FACE_NAME, *courier.fonts())
sheet = StyleSheet('extension style', base='sphinx_article_base14')
sheet['body'] = ParagraphStyle(typeface=Typeface.from_string(FACE_NAME),
                                    font_size=19*PT,
                                    font_color=Color(0, 0, 1))
'''.replace('FACE_NAME', repr(names['face']))
    write_text(package / 'F03_extension.py', source)
    entries = {'talvo.frontends': [names['reader']+'=F03_extension:PlainReader',
                                  names['empty']+'=F03_extension:EmptyReader'],
               'talvo.templates': [names['template']+'=F03_extension:SizedArticle'],
               'talvo.stylesheets': [names['sheet']+'=F03_extension:sheet'],
               'talvo.typefaces': [names['face']+'=F03_extension:face']}
    configuration = ('[project]\nname = "' + token + '"\nversion = "1.0"\n'
                     '[build-system]\nrequires = ["poetry-core"]\n'
                     'build-backend = "poetry.core.masonry.api"\n'
                     '[tool.poetry]\npackages = [{include = "F03_extension.py"}]\n')
    for group, declarations in entries.items():
        configuration += '\n[project.entry-points."' + group + '"]\n'
        for declaration in declarations:
            name, value = declaration.split('=', 1)
            configuration += '"' + name + '" = "' + value + '"\n'
    write_text(package / 'pyproject.toml', configuration)
    target = directory / 'installed'
    result = run_command((sys.executable, '-m', 'pip', 'install', '--no-index',
                          '--no-deps', '--no-build-isolation', '--target',
                          str(target), str(package)), timeout=120)
    assert result.returncode == 0, result
    env = os.environ.copy()
    env['PYTHONPATH'] = str(target) + os.pathsep + env.get('PYTHONPATH', '')
    return names, env
