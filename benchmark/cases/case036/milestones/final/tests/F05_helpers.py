# feature: F05
"""Lifecycle driving with real, durable execution effects."""
import json
from _helpers import write_file
from F01_helpers import execute_source
from F03_helpers import library_outcomes

LIFECYCLE_LIBRARY = '''import json
import time
from pathlib import Path
from velun.api.deco import keyword
VELUN_AUTO_KEYWORDS = False
@keyword(types=None)
def record(path, *values):
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(list(values)) + '\\n')
@keyword(types=None)
def pause(seconds):
    started = time.monotonic()
    try:
        time.sleep(float(seconds))
    finally:
        with open(Path(__file__).with_name('timings.jsonl'), 'a', encoding='utf-8') as stream:
            stream.write(json.dumps([float(seconds), time.monotonic() - started]) + '\\n')
@keyword(types=None)
def joined(value):
    return value + ':processed'
'''


def lifecycle_source(directory, cases, *, settings='', keywords='', section='Test Cases'):
    library = write_file(directory / 'Lifecycle.py', LIFECYCLE_LIBRARY)
    return (f'*** Settings ***\nLibrary    {library}\n{settings}'
            f'*** Variables ***\n${{EVENTS}}    {directory / "events.jsonl"}\n'
            f'*** {section} ***\n{cases}\n*** Keywords ***\n{keywords}')


def lifecycle_run(directory, cases, expected, *, settings='', keywords='', options=(), section='Test Cases'):
    source = lifecycle_source(directory, cases, settings=settings, keywords=keywords, section=section)
    path = write_file(directory / 'case.velun', source)
    process, root = execute_source(path, directory, *options)
    library_outcomes(process, root, expected)
    return process, root


def lifecycle_records(directory):
    # Every scenario records a live baseline, so a missing file is a probe failure.
    return [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]


def lifecycle_cases(root):
    cases = root.findall('.//test')
    result = {case.attrib['name']: case for case in cases}
    assert len(result) == len(cases), 'Duplicate case names in lifecycle observation.'
    return result


def suite_outcome(root, expected):
    assert root.find('./suite/status').attrib['status'] == expected
