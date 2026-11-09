# feature: F19
"""Enabled analysis observes execution, not merely generated metadata."""
from _helpers import temporary_project
from F19_helpers import build_analysis_module, analysis_python


PROFILE_SOURCE = '''cimport velora
cdef long leaf(long x):
    return x * 2 + 1

{decoration}cdef long quiet(long x):
    return x * 3

def run(long count):
    cdef long i, total = 0
    for i in range(count):
        total += leaf(i) + quiet(i)
    return total
'''


def test_profiling_enablement_counts_and_callers():
    for mode in ('default', 'enabled', 'excluded'):
        with temporary_project() as project:
            source = PROFILE_SOURCE.format(decoration='@velora.profile(False)\n' if mode == 'excluded' else '')
            path = build_analysis_module(project, 'profile_subject', source,
                options=() if mode == 'default' else ('-X', 'profile=True'))
            rows = analysis_python(project, '''import cProfile, pstats, json
from pathlib import Path
import profile_subject
observations = []
for count in (3, 6):
    profiler = cProfile.Profile()
    value = profiler.runcall(profile_subject.run, count)
    stats = pstats.Stats(profiler).stats
    records = []
    for (filename, line, name), (primitive, calls, own, cumulative, callers) in stats.items():
        if Path(filename).name == 'profile_subject.pyx':
            records.append([line, name, calls, [[Path(k[0]).name, k[1], k[2], v[1]] for k, v in callers.items()]])
    observations.append([value, records])
print(json.dumps(observations))
''')
            for count, (value, records) in zip((3, 6), rows):
                assert value == 5 * sum(range(count)) + count
                if mode == 'default':
                    assert records == [], records
                    continue
                by_name = {r[1]: r for r in records}
                expected = {'run': 1, 'leaf': count}
                if mode == 'enabled':
                    expected['quiet'] = count
                else:
                    assert 'quiet' not in by_name
                for name, calls in expected.items():
                    line, _, actual_calls, callers = by_name[name]
                    assert actual_calls == calls
                    assert source.splitlines()[line - 1].startswith(('def ' + name + '(', 'cdef long ' + name + '('))
                    if name != 'run':
                        assert [path.name, by_name['run'][0], 'run', count] in callers


TRACE_SOURCE = '''cdef long unlocked(long x) noexcept nogil:
    cdef long result
    if x > 0:
        result = x + 4
    else:
        result = x - 6
    return result

def run(long x):
    cdef long value
    if x > 0:
        value = x * 3
    else:
        value = x * 5
    with nogil:
        value += unlocked(x)
    return value
'''


def test_line_tracing_enablement_and_nogil():
    variants = [([], [('VELORA_TRACE_NOGIL', '1')], False, False),
                (['-X', 'linetrace=True'], [], False, False),
                (['-X', 'linetrace=True'], [('VELORA_TRACE', '1')], True, False),
                (['-X', 'linetrace=True'], [('VELORA_TRACE_NOGIL', '1')], True, True)]
    for options, macros, locked, unlocked in variants:
        with temporary_project() as project:
            build_analysis_module(project, 'trace_subject', TRACE_SOURCE, options=options, macros=macros)
            observations = analysis_python(project, '''import sys, json
from pathlib import Path
import trace_subject
observations = []
for x in (2, -3):
    lines = []
    def trace(frame, event, arg):
        if event == 'line' and Path(frame.f_code.co_filename).name == 'trace_subject.pyx':
            lines.append(frame.f_lineno)
        return trace
    sys.settrace(trace)
    try:
        value = trace_subject.run(x)
    finally:
        sys.settrace(None)
    observations.append([value, lines])
print(json.dumps(observations))
''')
            def line(text):
                return TRACE_SOURCE.splitlines().index(text) + 1
            for x, (value, events) in zip((2, -3), observations):
                assert value == (x * 3 + x + 4 if x > 0 else x * 5 + x - 6)
                if not locked:
                    assert events == [], events
                    continue
                taken, untaken = ('        value = x * 3', '        value = x * 5') if x > 0 else ('        value = x * 5', '        value = x * 3')
                assert line(taken) in events
                assert line(untaken) not in events
                taken, untaken = ('        result = x + 4', '        result = x - 6') if x > 0 else ('        result = x - 6', '        result = x + 4')
                if unlocked:
                    assert line(taken) in events
                else:
                    assert line(taken) not in events
                assert line(untaken) not in events
