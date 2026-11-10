# feature: F19
"""Source debugging commands act on a live compiled application."""
import re
from _helpers import temporary_project
from F19_helpers import debug_session, debug_line


def test_debug_source_stops_steps_and_values():
    call = debug_line('    result = inner(y, box)')
    body = debug_line('    x += 3')
    after = debug_line('    return result + y, box')
    with temporary_project() as project:
        records, application, _ = debug_session(project, f'''
command('break', 've break debug_subject:{call}')
command('run', 'run')
records['call_line'] = lineno()
records['caller_value'] = scalar('y')
command('step', 've step')
records['entry_line'] = lineno()
command('entry_stack', 've bt')
command('inner_break', 've break debug_subject:{body}')
command('continue', 'continue')
records['body_line'] = lineno()
records['inner_value'] = scalar('x')
command('list', 've list')
command('stack', 've bt')
command('finish', 've finish')
command('next', 've next')
records['after_line'] = lineno()
records['answer'] = scalar('y')
command('delete', 'delete breakpoints')
command('resume', 'continue')
''')
    assert records['call_line'] == call
    assert records['caller_value'] == 10
    assert debug_line('cdef long inner(long seed, object box):') <= records['entry_line'] < body
    assert re.search(r'^#\d+[ \t]+0x[0-9a-fA-F]+[ \t]+in[ \t]+inner\(\)[ \t]+at[ \t]+(?:.*/)?debug_subject\.pyx:' + str(records['entry_line']) + '$', records['entry_stack'], re.M)
    assert records['body_line'] == body
    assert records['inner_value'] == 12
    assert re.search(r'^>\s*' + str(body) + r'\s+x \+= 3\s*$', records['list'], re.M)
    assert re.search(r'^#\d+[ \t]+0x[0-9a-fA-F]+[ \t]+in[ \t]+inner\(\)[ \t]+at[ \t]+(?:.*/)?debug_subject\.pyx:' + str(body) + '$', records['stack'], re.M)
    assert re.search(r'^#\d+[ \t]+0x[0-9a-fA-F]+[ \t]+in[ \t]+outer\(\)[ \t]+at[ \t]+(?:.*/)?debug_subject\.pyx:' + str(call) + '$', records['stack'], re.M)
    assert records['after_line'] == after
    assert records['answer'] == 10
    assert application == [25, []]
    # A fresh session proves next steps over the same call that step entered.
    with temporary_project() as project:
        records, application, _ = debug_session(project, f'''
command('break', 've break debug_subject:{call}')
command('run', 'run')
command('next', 've next')
records['line'] = lineno()
command('resume', 'continue')
''')
    assert records['line'] == after
    assert application == [25, []]


def test_debug_frame_selection_and_native_assignment():
    body = debug_line('    x += 3')
    with temporary_project() as project:
        records, application, _ = debug_session(project, f'''
command('break', 've break debug_subject:{body}')
command('run', 'run')
stack = command('stack', 've bt')
command('select_outer', 've select %d' % frame_number(stack, 'outer'))
records['outer_before'] = scalar('y')
command('set_outer', 've set y = 31')
records['outer_after'] = scalar('y')
command('select_inner', 've select %d' % frame_number(stack, 'inner'))
records['inner_before'] = scalar('x')
command('set_inner', 've set x = -8')
records['inner_after'] = scalar('x')
command('resume', 'continue')
''')
    assert records['outer_before'] == 10
    assert records['outer_after'] == 31
    assert records['inner_before'] == 12
    assert records['inner_after'] == -8
    assert application == [26, []]


def test_debug_python_expression_namespaces_mutation_and_failure():
    body = debug_line('    x += 3')
    with temporary_project() as project:
        evaluation = project.path('evaluation.json')
        expression = ('ve exec box.append((shadow, factor ** 2)); '
                      '__import__("json").dump([shadow, factor + 2], '
                      f'open({str(evaluation)!r}, "w"))')
        records, application, result = debug_session(project, f'''
command('break', 've break debug_subject:{body}')
command('run', 'run')
stack = command('stack', 've bt')
command('select', 've select %d' % frame_number(stack, 'inner'))
command('evaluate', {expression!r})
command('invalid', 've exec 1 / 0')
command('resume', 'continue')
''')
        import json
        assert json.loads(evaluation.read_text()) == ['local', 9]
    assert application == [25, [['local', 49]]]
    # Python evaluation reports the inferior's traceback, not a fabricated GDB error.
    assert re.search(r'^ZeroDivisionError: .+$', result.text('stderr'), re.M), result.text('stderr')
