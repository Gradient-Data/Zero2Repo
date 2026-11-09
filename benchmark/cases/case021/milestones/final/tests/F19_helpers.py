# feature: F19
"""Real CPython 3.11 analysis builds and bounded public debugger sessions."""
import json
from _helpers import build_extensions, run_command, run_python
from F01_helpers import translate_source

PYTHON311 = '/opt/cpython311/bin/python3.11'


def build_analysis_module(project, name, source, *, options=(), macros=(), debug=False):
    path = project.write(name + '.pyx', source)
    if debug:
        options = (*options, '--gdb-outdir', str(project.root))
    result = translate_source(project, path, options=options)
    assert result.returncode == 0, result.text('stderr')
    result = build_extensions(project, [{'name': name, 'sources': [str(path.with_suffix('.c'))],
        'define_macros': list(macros), 'extra_compile_args': ['-O0', '-g']}],
        python=PYTHON311, env=project.environment())
    assert result.returncode == 0, result.text() + result.text('stderr')
    return path


def analysis_python(project, source):
    result = run_python('import sys\nassert sys.version_info[:2] == (3, 11)\n' + source,
                        python=PYTHON311, env=project.environment())
    assert result.returncode == 0, result.text() + result.text('stderr')
    return json.loads(result.stdout)


DEBUG_SOURCE = '''shadow = "module"
factor = 7

cdef long inner(long seed, object box):
    cdef object shadow = "local"
    cdef long x = seed + 2
    x += 3
    return x

cdef outer(long seed, object box):
    cdef long y = seed * 2
    result = inner(y, box)
    return result + y, box

def run(long seed):
    return outer(seed, [])
'''


def debug_line(text):
    return DEBUG_SOURCE.splitlines().index(text) + 1


def debug_session(project, script, *, seed=5):
    """Capture command results verbatim; GDB errors and script failures fail the run."""
    build_analysis_module(project, 'debug_subject', DEBUG_SOURCE, debug=True)
    outcome = project.path('application.json')
    driver = project.write('debug_driver.py',
        'import json, debug_subject\n'
        f'with open({str(outcome)!r}, "w") as stream:\n'
        f'    json.dump(debug_subject.run({seed}), stream)\n')
    records = project.path('commands.json')
    # GDB Python is only a transport for the public commands and their output.
    # It neither inspects product internals nor substitutes for those commands.
    prelude = f'''import gdb, json, re, traceback
records = {{}}
def command(key, text):
    value = gdb.execute(text, to_string=True)
    records[key] = value
    return value
def scalar(name):
    output = gdb.execute('ve locals', to_string=True)
    matches = re.findall(r'^' + re.escape(name) + r'[ \\t]+= \\([^()\\n]+\\) ([+-]?\\d+)$', output, re.M)
    assert len(matches) == 1, output
    return int(matches[0])
def lineno():
    return int(gdb.parse_and_eval('$ve_lineno()'))
def frame_number(backtrace, name):
    matches = re.findall(r'^#(\\d+)[ \\t]+0x[0-9a-fA-F]+[ \\t]+in[ \\t]+' + re.escape(name) + r'\\(\\)[ \\t]+at[ \\t]+.+:\\d+$', backtrace, re.M)
    assert len(matches) == 1, backtrace
    return int(matches[0])
'''
    body = prelude + script + f'\nwith open({str(records)!r}, "w") as stream: json.dump(records, stream)\n'
    inside = project.write('gdb_observe.py', body)
    commands = project.write('session.gdb',
        'set pagination off\nset confirm off\nset breakpoint pending on\n'
        'set auto-load safe-path /\n'
        'python\nfrom Velora.Debugger import libvelora, libpython\nend\n'
        'set ve_colorize_code off\n'
        f've import {project.path("velora_debug/velora_debug_info_debug_subject")}\n'
        'python\n'
        'try:\n'
        f'    exec(compile(open({str(inside)!r}).read(), {str(inside)!r}, "exec"))\n'
        'except BaseException:\n'
        '    import traceback\n    traceback.print_exc()\n    gdb.execute("quit 1")\n'
        'end\n')
    result = run_command(['gdb', '-nx', '-batch', '-iex', 'set auto-load safe-path /', '-x', str(commands), '--args',
                          PYTHON311, str(driver)], env=project.environment(), timeout=120)
    assert result.returncode == 0, result.text() + result.text('stderr')
    return json.loads(records.read_text()), json.loads(outcome.read_text()), result
