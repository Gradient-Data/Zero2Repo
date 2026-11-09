# feature: F15
"""Real child programs and independent Linux process observations."""
import sys
from _helpers import write_file, run_module, read_xml
from F02_helpers import WITNESS
from F03_helpers import library_outcomes
from F14_helpers import OS_OBSERVER

PROCESS_CHILD = r'''
import json, os, signal, subprocess, sys, time
from pathlib import Path
mode = sys.argv[1]
if mode == 'config':
    Path(sys.argv[2]).write_text('executed')
    print(json.dumps({'args': sys.argv[3:], 'cwd': os.getcwd(),
        'env': {k: os.environ.get(k) for k in ('F15_PARENT', 'F15_EXTRA', 'F15_ONLY')}}))
elif mode == 'input':
    print(json.dumps(sys.stdin.read()))
elif mode == 'emit':
    os.write(1, bytes.fromhex(sys.argv[2]))
    os.write(2, bytes.fromhex(sys.argv[3]))
    sys.exit(int(sys.argv[4]))
elif mode == 'managed':
    root = Path(sys.argv[2])
    policy = sys.argv[3]
    def event(name):
        with (root / 'events').open('a') as f:
            f.write(name + '\n')
    def term(signum, frame):
        event('TERM')
        if policy != 'stubborn':
            time.sleep(0.5)
            event('graceful')
            sys.exit(0)
    signal.signal(signal.SIGTERM, term)
    signal.signal(signal.SIGUSR1, lambda *args: event('USR1'))
    root.mkdir(exist_ok=True)
    if policy == 'tree':
        subprocess.Popen([sys.executable, __file__, 'managed', str(root / 'child'), 'normal'])
    (root / 'ready.tmp').write_text(json.dumps({'pid': os.getpid()}))
    (root / 'ready.tmp').replace(root / 'ready')
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if (root / 'release').exists():
            event('completed')
            print(root.name)
            break
        time.sleep(0.02)
    else:
        raise RuntimeError('Child safety deadline expired.')
else:
    raise ValueError(mode)
'''

PROCESS_OBSERVER = r'''
import json, os, shlex, signal, subprocess, sys, time
from pathlib import Path
from velun.api.deco import keyword
VELUN_AUTO_KEYWORDS = False
_streams = []
_controls = []

def until(probe):
    end = time.monotonic() + 8
    while time.monotonic() < end:
        result = probe()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError('Independent observation deadline expired.')

@keyword(types=None)
def ready(path):
    path = Path(path)
    until(lambda: (path / 'ready').exists())
    return json.loads((path / 'ready').read_text())['pid']

def live(pid):
    p = Path('/proc') / str(pid) / 'stat'
    try:
        stat = p.read_text()
    except FileNotFoundError:
        return False
    return stat[stat.rindex(')') + 2:].split()[0] != 'Z'

@keyword(types=None)
def os_alive(pid):
    assert live(pid), 'Selected child is not alive.'

@keyword(types=None)
def os_stopped(pid):
    until(lambda: not live(pid))

@keyword(types=None)
def release_child(path):
    (Path(path) / 'release').write_text('release')

@keyword(types=None)
def events_are(path, expected):
    expected = json.loads(expected)
    until(lambda: (Path(path) / 'events').exists())
    assert (Path(path) / 'events').read_text().splitlines() == expected

@keyword(types=None)
def await_event(path, event):
    until(lambda: (Path(path) / 'events').exists() and event in (Path(path) / 'events').read_text().splitlines())

@keyword(types=None)
def decoded_json(text):
    return json.loads(text)

@keyword(types=None)
def input_stream(path):
    stream = open(path, 'rb')
    _streams.append(stream)
    return stream

@keyword(types=None)
def console_encoded(text):
    import locale
    return text.encode(locale.getpreferredencoding(False)).hex()

@keyword(types=None)
def parse_joined(text):
    # An independent reader accepts alternative valid quote spellings.
    return shlex.split(text)

@keyword(types=None)
def start_control(child, root):
    p = subprocess.Popen([sys.executable, child, 'managed', root, 'normal'], start_new_session=True)
    _controls.append(p)
    return p.pid

@keyword(types=None)
def cleanup_owned(root):
    # Only identities recorded by the children launched in this test directory.
    for path in Path(root).rglob('ready'):
        pid = json.loads(path.read_text())['pid']
        if live(pid):
            os.kill(pid, signal.SIGKILL)
    for p in _controls:
        p.wait(timeout=5)
    for stream in _streams:
        stream.close()
'''


def process_run(directory, cases, failures=(), *, input=b'parent input\n'):
    write_file(directory / 'Witness.py', WITNESS)
    write_file(directory / 'OSObserver.py', OS_OBSERVER)
    write_file(directory / 'ProcessObserver.py', PROCESS_OBSERVER)
    write_file(directory / 'child.py', PROCESS_CHILD)
    source = ("*** Settings ***\nLibrary    Process\nLibrary    Witness.py\n"
              "Library    OSObserver.py\nLibrary    ProcessObserver.py\n"
              "Suite Teardown    Cleanup Processes\n"
              "*** Test Cases ***\n" + cases +
              "\n*** Keywords ***\nCleanup Processes\n"
              "    TRY\n        Terminate All Processes    kill=True\n"
              "    FINALLY\n        Cleanup Owned    @ROOT@\n    END\n")
    source = source.replace('@ROOT@', str(directory)).replace('@PY@', sys.executable)
    path = write_file(directory / 'case.velun', source)
    output = directory / 'result.xml'
    process = run_module('velun', ['--output', str(output), '--log', 'NONE',
                         '--report', 'NONE', str(path)], input=input, timeout=115,
                         env_overrides={'F15_PARENT': 'inherited', 'F15_EXTRA': None, 'F15_ONLY': None})
    root = read_xml(output).getroot()
    names = [line for line in cases.splitlines() if line and not line[0].isspace()]
    library_outcomes(process, root, {n: 'FAIL' if n in failures else 'PASS' for n in names})
    wanted = sum(line.lstrip().startswith('Check    ') for line in cases.splitlines())
    assert sum((m.text or '').startswith('F02_CHECK:') for m in root.findall('.//msg')) == wanted
    return root
