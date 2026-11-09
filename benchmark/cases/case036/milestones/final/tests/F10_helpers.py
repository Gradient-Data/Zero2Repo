# feature: F10
"""Real execution artifacts, external timing witness, and rendered browser probes."""
import json
import time
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from lxml import html

from _helpers import run_module, run_command, write_file, read_xml, read_json
from F03_helpers import library_outcomes
from F05_helpers import lifecycle_cases

ARTIFACT_CASES = '''*** Settings ***
Documentation    Artifact suite documentation
Metadata    Owner    Acceptance team
*** Test Cases ***
Accepted
    [Documentation]    Accepted documentation
    [Tags]    red    common
    Nested
Rejected
    [Tags]    blue    common
    Fail    deliberate rejection
Omitted
    [Tags]    red
    Skip    deliberate omission
*** Keywords ***
Nested
    IF    True
        Log    nested payload
        Log    execution warning    WARN
        Log    execution error    ERROR
    END
'''


def artifact_run(directory, source=ARTIFACT_CASES, options=(), expected=None):
    directory.mkdir(parents=True, exist_ok=True)
    path = write_file(directory / 'artifact.velun', source)
    process = run_module('velun', ['--outputdir', str(directory), '--consolecolors', 'off',
                                 '--consolelinks', 'off', *options, str(path)])
    output = directory / 'output.xml'
    if expected is not None:
        library_outcomes(process, read_xml(output).getroot(), expected)
    return process


def artifact_cases(directory):
    return lifecycle_cases(read_xml(directory / 'output.xml').getroot())


@contextmanager
def timing_endpoint():
    intervals = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            started, wall_started = time.monotonic(), datetime.now()
            time.sleep(.18)
            finished, wall_finished = time.monotonic(), datetime.now()
            # Monotonic duration first (existing callers); wall-clock bounds of the
            # witnessed operation follow for start/end enclosure checks.
            intervals.append((started, finished, wall_started, wall_finished))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'operation completed')
        def log_message(self, *args):
            pass  # Test-owned HTTP access logging is unrelated to product output.
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/operation', intervals
    finally:
        server.shutdown()
        server.server_close()
        worker.join(3)
        assert not worker.is_alive()


def timed_artifacts(directory, *, output='output.xml'):
    library = write_file(directory / 'Timing.py', '''import urllib.request

def controlled_operation(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.read() == b'operation completed'
''')
    with timing_endpoint() as (url, intervals):
        source = ARTIFACT_CASES.replace('Documentation    Artifact', f'Library    {library}\nDocumentation    Artifact').replace('    Nested\n', f'    Controlled Operation    {url}\n    Nested\n')
        before = datetime.now()
        process = artifact_run(directory, source, ['--output', output])
        after = datetime.now()
    assert 0 < process.returncode < 251, process.stderr
    assert len(intervals) == 1
    return process, before, after, intervals[0]


def check_recorded_interval(start, elapsed, process, before, after, interval,
                            start_resolution=.001, elapsed_resolution=.001):
    # The PRD permits one millisecond of rounding error per reported value.
    # This applies equally to stored fields and values returned by public readers.
    start_seconds = start.timestamp()
    tolerance = start_resolution + elapsed_resolution
    assert before.timestamp() - start_resolution <= start_seconds <= after.timestamp() + start_resolution
    assert interval[1] - interval[0] - elapsed_resolution <= elapsed <= process.finished - process.started + elapsed_resolution
    assert start_seconds + elapsed <= after.timestamp() + tolerance
    if len(interval) == 4:
        # The recorded item encloses the externally witnessed operation in wall-clock time:
        # it started before the operation started and ended after the operation ended.
        assert start_seconds <= interval[2].timestamp() + start_resolution, (start, interval[2])
        assert start_seconds + elapsed >= interval[3].timestamp() - tolerance, (start, elapsed, interval[3])


def rendered_probe(directory, target, script):
    """Execute caller-supplied DOM actions in Chromium; return explicit JSON."""
    wrapper = write_file(directory / 'browser-probe.html', '''<!doctype html><meta charset="utf-8">
<iframe id="product" style="width:1400px;height:1000px"></iframe>
<pre id="observation"></pre><script>
const frame = document.querySelector('#product');
function resultTestName(row) {
const cell = row.querySelector('.details-col-name').cloneNode(true);
for (const prefix of cell.querySelectorAll('.parent-name')) prefix.remove();
return cell.textContent.trim();
}
const pause = () => new Promise(resolve => setTimeout(resolve, 150));
(async () => {
try {
frame.src = ''' + json.dumps(target.resolve().as_uri()) + ''';
await new Promise(resolve => frame.onload = resolve);
await pause();
const result = await (async () => {''' + script + '''})();
document.querySelector('#observation').textContent = JSON.stringify({result});
} catch (error) {
document.querySelector('#observation').textContent = JSON.stringify({error:String(error)});
}
})();</script>''')
    process = run_command(['chromium', '--headless', '--no-sandbox', '--disable-dev-shm-usage',
                           '--allow-file-access-from-files', '--user-data-dir=' + str(directory / 'profile'),
                           '--dump-dom', '--virtual-time-budget=6000', wrapper.as_uri()], timeout=40)
    assert process.returncode == 0, process.stderr
    document = html.fromstring(process.stdout)
    nodes = document.xpath('//pre[@id="observation"]')
    assert len(nodes) == 1
    observation = json.loads(nodes[0].text_content())
    assert 'error' not in observation, observation
    return observation['result']


def statistic_counts(element):
    return tuple(int(element.attrib[name]) for name in ('pass', 'fail', 'skip'))


def public_result_messages(result):
    from velun.api import ResultVisitor
    class Messages(ResultVisitor):
        def __init__(self):
            self.messages = []
        def visit_message(self, message):
            self.messages.append((message.level, message.message))
    visitor = Messages()
    result.visit(visitor)
    return visitor.messages
