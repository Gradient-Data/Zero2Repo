# feature: F13
"""Caller-owned extensions driven through real execution and artifact entries."""
import json
from _helpers import write_file


def extension_bank(directory):
    return write_file(directory / 'HookBank.py', EXTENSIONS)


def extension_records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def extension_errors(process, root):
    assert b'[ ERROR ]' in process.stderr, process.stderr
    messages = root.findall('./errors/msg')
    assert any(m.attrib['level'] == 'ERROR' and m.text for m in messages), messages


EXTENSIONS = r'''
import json
import sys
from pathlib import Path
from velun.api import TestSuite, SuiteVisitor, ResultVisitor


def record(path, *values):
    with Path(path).open('a') as stream:
        stream.write(json.dumps(values) + '\n')

class Partial:
    def __init__(self, path, label, priority=None):
        self.path, self.label = path, label
        if priority is not None:
            self.VELUN_LISTENER_PRIORITY = float(priority)
    def start_test(self, data, result):
        record(self.path, self.label, 'start_test', data.name)
    def end_test(self, data, result):
        record(self.path, self.label, 'end_test', data.name, result.status)

class LibraryOrder:
    VELUN_LIBRARY_SCOPE = 'SUITE'
    def __init__(self, path):
        self.VELUN_LIBRARY_LISTENER = [Partial(path, 'library-default'), Partial(path, 'library-zero', 0),
                                       Partial(path, 'library-ten', 10)]
    def present(self):
        return 'live'

class Trace:
    def __init__(self, path): self.path = path
    def log_message(self, msg): record(self.path, 'message', msg.level, msg.message)
    def output_file(self, path): record(self.path, 'artifact', 'output', str(path))
    def log_file(self, path): record(self.path, 'artifact', 'log', str(path))
    def report_file(self, path): record(self.path, 'artifact', 'report', str(path))

def event_method(event):
    def callback(self, data, result):
        record(self.path, event, result.type, result.name if result.type in ('SUITE', 'TEST', 'KEYWORD') else None, result.status)
    return callback
for kind in ('suite', 'test', 'keyword', 'for', 'for_iteration', 'if', 'if_branch',
             'while', 'while_iteration', 'try', 'try_branch', 'group'):
    for edge in ('start', 'end'):
        event = edge + '_' + kind
        setattr(Trace, event, event_method(event))

class Legacy:
    VELUN_LISTENER_API_VERSION = 2
    def __init__(self, path): self.path = path
    def start_test(self, name, attrs): record(self.path, 'legacy-start', name, attrs['tags'])
    def end_test(self, name, attrs): record(self.path, 'legacy-end', name, attrs['status'])
    def log_message(self, msg): record(self.path, 'legacy-log', msg['level'], msg['message'])

class Edit:
    def start_suite(self, data, result): result.metadata['Review'] = 'listener-edit'
    def start_test(self, data, result):
        if data.name == 'Rewritten': data.body[0].name = 'Log'
    def start_keyword(self, data, result):
        if data.name == 'Log': data.args = ('rewritten-call',)
    def end_test(self, data, result):
        result.tags.add('reviewed')
        result.metadata['Decision'] = 'edited'
        if data.name == 'Override':
            result.status = 'FAIL'
            result.message = 'caller outcome'

class Scoped:
    VELUN_LIBRARY_SCOPE = 'SUITE'
    def __init__(self, path):
        self.path = path
        self.VELUN_LIBRARY_LISTENER = self
    def start_test(self, data, result): record(self.path, 'scoped', data.name)
    def present(self): return 'active'

class BadVersion:
    VELUN_LISTENER_API_VERSION = 'unsupported'

class BadLibrary:
    def __init__(self): self.VELUN_LIBRARY_LISTENER = BadVersion()
    def present(self): return 'loaded'

class BrokenCallback:
    def start_test(self, data, result): raise RuntimeError('callback sentinel')

class First(SuiteVisitor):
    def start_suite(self, suite):
        suite.metadata['Sequence'] = 'first'
        for test in suite.tests:
            if test.name == 'Original':
                test.name = 'Renamed'
                test.tags.add('selected')
                test.body[0].args = ('first',)
                test.body = [test.body[0]]
            elif test.name == 'Remove': test.tags.add('selected')

class Second(SuiteVisitor):
    def start_suite(self, suite):
        if suite.name == 'Tree':
            suite.suites = [s for s in suite.suites if s.name != 'Discard']
            child = suite.suites.create(name='Inserted')
            test = child.tests.create(name='Suite Added', tags=['selected'])
            test.body.create_keyword(name='Log', args=['suite-added-effect'])
            suite.suites = list(reversed(suite.suites))
        if suite.name != 'Nested': return
        suite.metadata['Sequence'] = suite.metadata['Sequence'] + '-second'
        for test in suite.tests:
            if test.name == 'Renamed':
                test.body[0].args = (test.body[0].args[0] + '-second',)
        suite.tests = [t for t in suite.tests if t.name != 'Remove']
        added = suite.tests.create(name='Added', tags=['selected'])
        added.body.create_keyword(name='Log', args=['added-effect'])
        suite.tests = list(reversed(suite.tests))
        for test in suite.tests:
            if test.name == 'Renamed':
                test.body.create_keyword(name='Should Be Equal', args=[test.body[0].args[0], 'first-second'])

class BrokenModifier(SuiteVisitor):
    def start_suite(self, suite): raise RuntimeError('modifier sentinel')

class ResultEdit(ResultVisitor):
    def start_suite(self, suite):
        if suite.name == 'Deep': suite.metadata['Review'] = 'result-edit'
    def visit_test(self, test):
        if test.name == 'Chosen':
            test.status = 'PASS'
            test.message = 'review accepted'
            test.doc = 'edited descendant documentation'
            test.tags.add('result-reviewed')
            test.body.clear()
            test.body.create_message(message='replacement-content', level='INFO')

class SourceParser:
    def __init__(self, extension='spec', mode='normal'):
        self.extension, self.mode = extension, mode
    def parse_init(self, source, defaults):
        config = json.loads(source.read_text())
        defaults.tags = config['tags']
        defaults.timeout = config['timeout']
        defaults.setup = {'name':'Log', 'args':[config['setup']]}
        defaults.teardown = {'name':'Log', 'args':[config['teardown']]}
        return TestSuite(name=config['name'], source=source.parent, metadata={'Origin':config['origin']})
    def parse(self, source, defaults):
        if self.mode == 'raise': raise ValueError('source sentinel')
        if self.mode == 'invalid': return ['not a suite']
        config = json.loads(source.read_text())
        suite = TestSuite(name=config['name'], source=source)
        for item in config['tests']:
            test = suite.tests.create(name=item['name'])
            defaults.set_to(test)
            for name, args in item['calls']:
                test.body.create_keyword(name=name, args=args)
        return suite

class Console:
    def start_suite(self, data, result): print(json.dumps(['suite', data.name]), file=sys.__stdout__)
    def end_test(self, data, result): print(json.dumps(['test', data.name, result.status]), file=sys.__stdout__)
    def output_file(self, path): print(json.dumps(['output', str(path)]), file=sys.__stdout__)
    def log_file(self, path): print(json.dumps(['log', str(path)]), file=sys.__stdout__)
    def report_file(self, path): print(json.dumps(['report', str(path)]), file=sys.__stdout__)
    def close(self): print(json.dumps(['closed']), file=sys.__stdout__)
'''
