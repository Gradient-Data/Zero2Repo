# feature: F03
"""Library fixtures and a real, bounded local XML-RPC keyword service."""
from contextlib import contextmanager
from socketserver import ThreadingMixIn
from threading import Thread
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.client import Binary
import time

from _helpers import write_file
from F01_helpers import execute_source
from F02_helpers import WITNESS, variable_run, document, rejection_cases, rejected_names


def library_run(directory, body, *, libraries='', extra_tests='', failures=(), checks=None, options=()):
    process, root = variable_run(directory, document(body, settings=libraries, extra_tests=extra_tests),
                                 failures=failures, checks=checks, options=options)
    # Every declared case was executed and recorded exactly once.
    assert sorted(t.attrib['name'] for t in root.findall('.//test')) == sorted({'Working', *failures})
    return process, root


def library_outcomes(process, root, expected):
    cases = root.findall('.//test')
    actual = {c.attrib['name']: c.find('status').attrib['status'] for c in cases}
    assert len(cases) == len(actual)
    assert actual == expected, (actual, [(c.attrib['name'], c.find('status').text) for c in cases], process.stderr)
    assert (0 < process.returncode < 251 if 'FAIL' in expected.values() else process.returncode == 0), process.stderr
    for case in cases:
        if expected[case.attrib['name']] != 'PASS':
            assert case.find('status').text


class KeywordService:
    """Operations execute on the server and retain their actual received values."""
    def __init__(self):
        self.calls = []
        self.delay_gate = None

    def get_library_information(self):
        return {name: {'args': ['*args', '**kwargs'], 'doc': 'Local service operation.'}
                for name in ('Echo', 'Combine', 'Ordinary', 'Continuable', 'Fatal', 'Delay', 'Malformed', 'Binary', 'Mapping')}

    def run_keyword(self, name, args, kwargs=None):
        kwargs = {} if kwargs is None else kwargs
        self.calls.append((name, args, kwargs))
        if name == 'Malformed':
            if args == ['missing-status']:
                return {'return': 'structure without a status'}
            return ['invalid result carrier']
        if name in ('Ordinary', 'Continuable', 'Fatal'):
            return {'status': 'FAIL', 'error': 'service failure: ' + name,
                    'continuable': name == 'Continuable', 'fatal': name == 'Fatal'}
        if name == 'Delay':
            gate = self.delay_gate
            if gate is None:
                time.sleep(float(args[0]))
            else:
                entered, release = gate
                entered.set()
                # The caller releases this in finally; its public-call deadline bounds the wait.
                release.wait()
            value = 'completed delayed operation'
        elif name == 'Combine':
            value = args[0] + kwargs['suffix']
        elif name == 'Binary':
            value = Binary(bytes([0, 65, 255]))
        elif name == 'Mapping':
            value = {'outer': {'data': Binary(b'\x00\xff')}, 'records': [{'value': 7}]}
        elif name == 'Echo':
            value = args
        else:
            raise ValueError('Unknown operation: ' + name)
        return {'status': 'PASS', 'return': value, 'output': '*INFO* service executed ' + name + '\n'}


class LocalRPCServer(ThreadingMixIn, SimpleXMLRPCServer):
    daemon_threads = True


@contextmanager
def keyword_service():
    service = KeywordService()
    server = LocalRPCServer(('127.0.0.1', 0), logRequests=False, allow_none=True, use_builtin_types=True)
    server.register_instance(service)
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    worker.start()
    try:
        yield service, 'http://127.0.0.1:' + str(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        assert not worker.is_alive(), 'Local XML-RPC service did not stop.'


TYPED_LIBRARY = r'''
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from enum import Enum, IntEnum
from typing import Any, Literal, TypedDict, NotRequired
from collections.abc import Sequence, Mapping
from velun.api.deco import keyword
from velun.api.types import Secret
VELUN_AUTO_KEYWORDS = False
class Options(TypedDict):
    count: int
    label: NotRequired[str]
class Token:
    def __init__(self, value): self.value = value

def token_from_text(value):
    if not isinstance(value, str) or not value.startswith('token:'):
        raise ValueError('Token requires a token prefix.')
    return Token(value[6:])
VELUN_LIBRARY_CONVERTERS = {Token: token_from_text}

@keyword
def token_value(value: Token): return value.value
@keyword
def typed_options(value: Options): return value
@keyword
def inferred(value=1): return value
@keyword
def alternative(value: int=False): return value
@keyword
def numeric_alternative(value: int=1.5): return value
@keyword(types=None)
def disabled(value: int): return value
@keyword
def retained(value: list[int]): return value
@keyword
def arbitrary(value: object): return value
@keyword
def anything(value: Any): return value
class Choice(Enum):
    Exact = 1
    EXACT = 2
    Blue_Sky = 3
class Number(IntEnum):
    LOW = 4
    HIGH = 9
@keyword
def enum_value(value: Choice): return value.name
@keyword
def integer_enum(value: Number): return value.name
@keyword
def enum_member(): return Choice.Blue_Sky
@keyword
def literal_value(value: Literal['Exact', 'EXACT', 'Blue_Sky', 4, False]): return value
@keyword
def ambiguous_literal(value: Literal[1, '1']): return value
@keyword
def secret_value(value: Secret): return value.value
@keyword
def make_secret(value): return Secret(value)
'''
