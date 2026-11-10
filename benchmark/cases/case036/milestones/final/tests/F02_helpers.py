# feature: F02
"""Real input library and variable execution observations."""
import json
from _helpers import write_file, json_messages
from F01_helpers import execute_source

WITNESS = r'''
import os
import json
import datetime
import pathlib
from decimal import Decimal
from typing import Any
from collections.abc import Mapping
from velun.api import logger
from velun.api.deco import keyword
from velun.api.types import Secret

VELUN_AUTO_KEYWORDS = False

def equivalent(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, Mapping) and len(actual) == len(expected) and all(
            any(type(key) is type(k) and key == k for key in actual) and equivalent(actual[k], v) for k, v in expected.items())
    if isinstance(expected, (list, tuple)):
        return type(actual) is type(expected) and len(actual) == len(expected) and all(
            equivalent(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected

@keyword(types=None)
def check(value, expected):
    wanted = eval(expected, {'Decimal': Decimal, 'date': datetime.date,
                  'datetime': datetime.datetime, 'timedelta': datetime.timedelta,
                  'Path': pathlib.Path, 'bytes': bytes, 'bytearray': bytearray,
                  'set': set, 'frozenset': frozenset})
    assert equivalent(value, wanted), (type(value), repr(value), type(wanted), repr(wanted))
    logger.info('F02_CHECK:' + json.dumps({'checked': True}))

@keyword(types=None)
def check_members(value, expected):
    assert set(value) == set(eval(expected)), (value, expected)
    logger.info('F02_CHECK:' + json.dumps({'checked': True}))

@keyword(types=None)
def text_value(value):
    assert type(value) is str
    logger.info('F02_CHECK:' + json.dumps({'checked': True}))

@keyword(types=None)
def same(left, right):
    assert left is right, (left, right)
    logger.info('F02_CHECK:' + json.dumps({'checked': True}))

@keyword(types=None)
def arguments(*args, **kwargs):
    return [list(args), dict(kwargs)]

@keyword(types=None)
def give(value):
    return value

@keyword(types={'value': int | float})
def number(value):
    return value

@keyword(types={'value': float | int})
def reverse_number(value):
    return value

@keyword(types={'value': int | Any})
def unrestricted(value):
    return value

@keyword(types={'value': Any | int})
def unrestricted_first(value):
    return value

@keyword(types={'value': int | object})
def general(value):
    return value

@keyword(types={'value': object | int})
def general_first(value):
    return value

@keyword(types={'value': list[int] | list[str]})
def collection_union(value):
    return value

@keyword(types={'value': Secret})
def accept_secret(value):
    assert value.value == os.environ['F02_PRIVATE']
    logger.info('F02_CHECK:' + json.dumps({'checked': True}))

@keyword(types=None)
def calendar_boundary():
    return datetime.date.today()

@keyword(types=None)
def date_is_current(value, before):
    assert type(value) is datetime.date
    assert before <= value <= datetime.date.today()
    logger.info('F02_CHECK:' + json.dumps({'checked': True}))
'''


def variable_run(directory, text, *, options=(), failures=(), checks=None, passed=('Working',)):
    """Run native data; require exact case outcomes and completed oracle calls."""
    write_file(directory / 'Witness.py', WITNESS)
    source = write_file(directory / 'case.velun', text)
    process, root = execute_source(source, directory, *options)
    if checks is None:
        checks = sum(line.strip().split('    ')[0] in ('Check', 'Same', 'Accept Secret', 'Date Is Current', 'Text Value', 'Check Members')
                     for line in text.splitlines())
    assert_variable_outcomes(process, root, passed, failures, checks)
    return process, root


def assert_variable_outcomes(process, root, passed, failures, checks):
    cases = root.findall('.//test')
    actual = {case.attrib['name']: case.find('status').attrib['status'] for case in cases}
    assert len(actual) == len(cases), "Duplicate test identities in observation."
    assert set(actual) == set(passed) | set(failures), actual
    assert actual == {name: ('FAIL' if name in failures else 'PASS') for name in actual}, (
        actual, [(c.attrib['name'], c.find('status').text) for c in cases], process.stderr)
    assert (0 < process.returncode < 251 if failures else process.returncode == 0), (process.stdout, process.stderr)
    for case in cases:
        if case.attrib['name'] in failures:
            assert case.find('status').text, case.attrib
    records = json_messages([m.text or '' for m in root.findall('.//msg')], prefix='F02_CHECK:')
    assert records == [{'checked': True}] * checks, (records, checks, process.stderr)


def variable_tree_run(tree, results, *, passed, failures, checks):
    write_file(tree / 'Witness.py', WITNESS)
    process, root = execute_source(tree, results, '--pythonpath', str(tree))
    assert_variable_outcomes(process, root, passed, failures, checks)
    return process, root


def document(body, *, variables='', settings='', keywords='', extra_tests=''):
    return ('*** Settings ***\nLibrary    Witness.py\n' + settings +
            '\n*** Variables ***\n' + variables +
            '\n*** Test Cases ***\nWorking\n' + body + '\n' + extra_tests +
            '\n*** Keywords ***\n' + keywords)


def rejection_cases(statements):
    return ''.join(f'Invalid {i}\n    {statement}\n' for i, statement in enumerate(statements))


def rejected_names(statements):
    return [f'Invalid {i}' for i in range(len(statements))]
