# feature: F07
"""Real caller objects and execution effects for standard utilities."""
import json
from _helpers import write_file
from F01_helpers import execute_source
from F02_helpers import WITNESS
from F03_helpers import library_outcomes
from F04_helpers import TRACE_LIBRARY

UTILITY_LIBRARY = r'''
import json
import time
from pathlib import Path
from velun.api.deco import keyword

class Utility:
    VELUN_LIBRARY_SCOPE = 'SUITE'
    def __init__(self):
        self.items = []
    @keyword(types=None)
    def fresh_object(self):
        return []
    @keyword(types=None)
    def effect(self, path, value, delay='0', fail_until='0'):
        path = Path(path)
        with path.open('a') as stream:
            stream.write(json.dumps(['start', value, time.monotonic()]) + '\n')
        time.sleep(float(delay))
        with path.open('a') as stream:
            stream.write(json.dumps(['end', value, time.monotonic()]) + '\n')
        starts = sum(json.loads(line)[0] == 'start' for line in path.read_text().splitlines())
        if starts <= int(fail_until):
            raise AssertionError('attempt-' + str(starts))
        return value + ':done'
    @keyword(types=None)
    def store(self, value):
        self.items.append(value)
        return list(self.items)
    @keyword(types=None)
    def library_names(self, mapping):
        return list(mapping)
    @keyword(types=None)
    def choice(self):
        return 'utility-choice'
'''


def utility_run(directory, cases, expected, *, settings='', variables='', keywords=''):
    write_file(directory / 'Witness.py', WITNESS)
    write_file(directory / 'Trace.py', TRACE_LIBRARY)
    write_file(directory / 'Utility.py', UTILITY_LIBRARY)
    source = ('*** Settings ***\nLibrary    Witness.py\nLibrary    Trace.py\n'
              'Library    Utility.py    AS    Active\n' + settings +
              '\n*** Variables ***\n' + variables + '\n*** Test Cases ***\n' + cases +
              '\n*** Keywords ***\n' + keywords)
    path = write_file(directory / 'case.velun', source)
    process, root = execute_source(path, directory)
    library_outcomes(process, root, expected)
    # These messages come only from the independent caller's completed checks.
    checks = root.findall('.//msg')
    actual = [m for m in checks if (m.text or '').startswith('F02_CHECK:')]
    wanted = sum(line.strip().split('    ')[0] in ('Check', 'Same', 'Check Members', 'Text Value')
                 for line in cases.splitlines())
    assert len(actual) == wanted, (len(actual), wanted)
    return root


def effect_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]
