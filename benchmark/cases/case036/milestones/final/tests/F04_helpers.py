# feature: F04
"""Native workflow execution and explicit per-test event observations."""
from _helpers import write_file, json_messages
from F02_helpers import variable_run

TRACE_LIBRARY = '''from velun.api import logger
from velun.api.deco import keyword
import json
@keyword(types=None)
def mark(*values):
    logger.info('F04_EVENT:' + json.dumps(list(values)))
'''


def workflow_run(directory, source, *, passed=('Working',), failures=(), checks=0, options=()):
    write_file(directory / 'Trace.py', TRACE_LIBRARY)
    process, root = variable_run(directory, source, passed=passed, failures=failures,
                                 checks=checks, options=options)
    # Every declared case was executed and recorded exactly once.
    assert sorted(t.attrib['name'] for t in root.findall('.//test')) == sorted({*passed, *failures})
    return process, root


def workflow_events(root, name):
    cases = [case for case in root.findall('.//test') if case.attrib['name'] == name]
    assert len(cases) == 1, (name, len(cases))
    return json_messages([m.text or '' for m in cases[0].findall('.//msg')],
                         prefix='F04_EVENT:')
