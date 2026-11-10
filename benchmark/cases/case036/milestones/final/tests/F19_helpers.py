# feature: F19
"""Documentation inputs and explicit generation/reader observations."""
import json
from lxml import html
from _helpers import run_module, write_file, read_json, index_by_identity
from F10_helpers import rendered_probe

DOC_LIBRARY = '''from enum import Enum
from velun.api.deco import keyword
class Shade(Enum):
    """Available pigment choices."""
    AMBER = 'amber'
    TEAL = 'teal'
class Atlas:
    """Atlas introduction with `Paint Item` reference."""
    VELUN_LIBRARY_VERSION = '3.7-doc'
    def __init__(self, region: str = 'west'):
        """Select the documented region."""
        self.region = region
    @keyword('Paint Item', tags=['palette', 'public'])
    def paint_item(self, shade: Shade, count: int = 4) -> str:
        """Apply pigment to the requested items."""
        return shade.value * count
    @keyword('Inspect Item')
    def inspect_item(self, item):
        """Inspect an item without changing it."""
        return item
    @keyword('Repaint Items')
    def repaint_items(self, item='wall'):
        """Reapply pigment to an existing item."""
        return item
    @keyword('Pin')
    def pin(self):
        """Keep the selected location."""
    @keyword('Pan')
    def pan(self):
        """Move the selected location."""
'''

DYNAMIC_LIBRARY = '''class Dynamic:
    """Configurable operation catalogue."""
    def __init__(self, area): self.area = area
    def get_keyword_names(self): return ['Visit ' + self.area]
    def get_keyword_arguments(self, name): return ['place', 'visits=2']
    def get_keyword_documentation(self, name):
        return 'Visit documentation for ' + self.area + '.'
    def get_keyword_tags(self, name): return ['travel']
    def run_keyword(self, name, args, kwargs): return args[0]
'''

RESOURCE = '''*** Settings ***
Documentation    Resource introduction.
*** Keywords ***
Public Route
    [Documentation]    Route description.
    [Arguments]    ${origin}    ${target}=harbour
    [Tags]    navigation
    No Operation
Hidden Route
    [Documentation]    Private route description.
    [Tags]    velun:private
    No Operation
'''

NATIVE_DOC = '''= Field guide =

First paragraph with *strong pigment* and _gentle shade_ and ``inline sample``.
Second line.

Separate paragraph.

- first entry
- second entry

| = Column = | = Value = |
| pigment | amber |

| code sample
|     indented sample

[https://example.org/guide|Field reference]

[https://example.org/pigment.png|Pigment picture]

See `Paint Item`.
'''


def doc_library(directory):
    return write_file(directory / 'Atlas.py', DOC_LIBRARY)


def generate_doc(source, target, *options):
    process = run_module('velun.velunexdocs', [*options, str(source), str(target)])
    assert process.returncode == 0, (process.stdout, process.stderr)
    assert target.is_file(), (target, process.stdout)
    return process


def json_doc(source, target, *options):
    generate_doc(source, target, '--specdocformat', 'RAW', *options)
    return read_json(target)


def doc_keywords(data):
    return index_by_identity(data['keywords'], lambda kw: kw['name'])


def check_paint(data):
    """Check caller-declared documentation, not a round-trip oracle."""
    assert data['name'] == 'Atlas'
    assert data['version'] == '3.7-doc'
    assert 'Atlas introduction' in data['doc']
    keyword = doc_keywords(data)['Paint Item']
    assert 'Apply pigment to the requested items.' in keyword['doc']
    assert set(keyword['tags']) == {'palette', 'public'}
    args = keyword['args']
    assert [a['name'] for a in args] == ['shade', 'count']
    assert [a['required'] for a in args] == [True, False]
    assert args[0]['type']['name'] == 'Shade'
    assert args[1]['type']['name'] == 'int'
    assert args[1]['defaultValue'] == '4'
    assert keyword['returnType']['name'] == 'str'


def reader_snapshot(directory, target):
    return rendered_probe(directory, target, '''
const doc=frame.contentDocument;
return {names:Array.from(doc.querySelectorAll('.keyword-container .kw-name')).map(e=>e.textContent.trim()),
intro:doc.querySelector('#introduction-container .doc').textContent,
paint:doc.getElementById('Paint Item').textContent,
args:Array.from(doc.querySelectorAll('#keywords-container .arg-name')).map(e=>e.textContent.trim()),
types:Array.from(doc.querySelectorAll('#keywords-container .type')).map(e=>e.textContent.trim())};
''')


def markup_tree(text):
    return html.fragment_fromstring(text, create_parent='div')


def check_blocks(root):
    assert any(e.text_content().strip() == 'Field guide' for e in root.xpath('.//h1|.//h2|.//h3|.//h4'))
    assert any('First paragraph' in e.text_content() for e in root.xpath('.//p'))
    assert any('Separate paragraph.' in e.text_content() for e in root.xpath('.//p'))
    assert any(e.text_content().strip() == 'strong pigment' for e in root.xpath('.//b|.//strong'))
    assert any(e.text_content().strip() == 'gentle shade' for e in root.xpath('.//i|.//em'))
    assert any(e.text_content() == 'inline sample' for e in root.xpath('.//code'))
    assert [e.text_content().strip() for e in root.xpath('.//ul/li')] == ['first entry', 'second entry']
    assert [e.text_content().strip() for e in root.xpath('.//table//th')] == ['Column', 'Value']
    assert [e.text_content().strip() for e in root.xpath('.//table//td')] == ['pigment', 'amber']
    assert any('code sample\n    indented sample' in e.text_content() for e in root.xpath('.//pre'))
    assert any(e.text_content().strip() == "Field reference"
               for e in root.xpath('.//a[@href="https://example.org/guide"]'))
    assert root.xpath('.//img[@src="https://example.org/pigment.png"]')



def animated_document_probe(directory, target, script):
    """Use Chromium's normal event loop for animation-frame-driven interactions.

    The shared dump-DOM probe uses virtual time, which does not reliably run
    animation frames scheduled by interactive search. CDP keeps real time.
    """
    import fcntl
    import os
    import select
    import signal
    import subprocess
    import sys
    import time

    child_read, parent_write = os.pipe()
    parent_read, child_write = os.pipe()
    child_fds = [fcntl.fcntl(fd, fcntl.F_DUPFD, 20) for fd in (child_read, child_write)]
    os.close(child_read)
    os.close(child_write)
    launcher = '''import os, sys
os.dup2(int(sys.argv[1]), 3)
os.dup2(int(sys.argv[2]), 4)
os.set_inheritable(3, True)
os.set_inheritable(4, True)
os.execvp('chromium', sys.argv[3:])
'''
    errors = (directory / 'browser-stderr.txt').open('wb')
    process = subprocess.Popen(
        [sys.executable, '-c', launcher, *map(str, child_fds), 'chromium',
         '--headless', '--no-sandbox', '--disable-dev-shm-usage',
         '--remote-debugging-pipe', '--no-first-run',
         '--user-data-dir=' + str(directory / 'animation-profile'), 'about:blank'],
        pass_fds=child_fds, stdout=subprocess.DEVNULL, stderr=errors,
        start_new_session=True,
    )
    for fd in child_fds:
        os.close(fd)
    pending = b''
    serial = 0

    def command(method, params=None, session=None):
        nonlocal pending, serial
        serial += 1
        message = {'id': serial, 'method': method, 'params': params or {}}
        if session:
            message['sessionId'] = session
        os.write(parent_write, json.dumps(message).encode() + b'\0')
        deadline = time.monotonic() + 20
        while True:
            while b'\0' in pending:
                raw, pending = pending.split(b'\0', 1)
                response = json.loads(raw)
                if response.get('id') == serial:
                    assert 'error' not in response, response
                    return response['result']
            remaining = deadline - time.monotonic()
            assert remaining > 0, f'Browser command timed out: {method}'
            assert select.select([parent_read], [], [], remaining)[0], method
            chunk = os.read(parent_read, 65536)
            assert chunk, (directory / 'browser-stderr.txt').read_text()
            pending += chunk

    try:
        page = command('Target.createTarget', {'url': 'about:blank'})['targetId']
        session = command('Target.attachToTarget', {'targetId': page, 'flatten': True})['sessionId']
        url = target.resolve().as_uri()
        navigation = command('Page.navigate', {'url': url}, session)
        assert 'errorText' not in navigation, navigation
        deadline = time.monotonic() + 15
        while True:
            ready = command('Runtime.evaluate', {'expression': '({url:location.href,state:document.readyState})', 'returnByValue': True}, session)
            assert 'exceptionDetails' not in ready, ready
            if ready['result']['value'] == {'url': url, 'state': 'complete'}:
                break
            assert time.monotonic() < deadline, 'Document did not finish loading.'
            time.sleep(.05)
        result = command('Runtime.evaluate', {
            'expression': '(async()=>{const frame={contentDocument:document,contentWindow:window}; const pause=()=>new Promise(r=>setTimeout(r,200)); await pause();' + script + '})()',
            'awaitPromise': True, 'returnByValue': True,
        }, session)
        assert 'exceptionDetails' not in result, result
        return result['result']['value']
    finally:
        os.close(parent_write)
        os.close(parent_read)
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # The owned browser already exited.
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        errors.close()
