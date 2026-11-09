# feature: F18
"""Bounded real TCP conversations and native Telnet keyword workflows."""
from contextlib import contextmanager
import socket
from threading import Thread, Event

from F07_helpers import utility_run
from F09_helpers import velun_expression


@contextmanager
def telnet_peer(steps):
    """Run one real peer; verify every received byte and propagate worker errors."""
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(15)
    port = listener.getsockname()[1]
    errors, received = [], []
    finished = Event()

    def serve():
        try:
            with listener.accept()[0] as conn:
                conn.settimeout(12)
                for kind, value in steps:
                    if kind == 'send':
                        conn.sendall(value)
                    elif kind == 'receive':
                        data = b''
                        while len(data) < len(value):
                            part = conn.recv(len(value) - len(data))
                            assert part, ('Peer closed before expected input', value, data)
                            data += part
                        received.append(data)
                        assert data == value, (data, value)
                    elif kind == 'delay':
                        assert not finished.wait(value), 'Peer interrupted during delay.'
                    else:
                        raise ValueError(kind)
                # Keep the connection live for reads until the client closes it.
                assert conn.recv(1) == b'', 'Unexpected trailing client input.'
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    worker = Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield port, received
    finally:
        worker.join(16)
        listener.close()
        assert not worker.is_alive(), 'Local peer did not stop.'
        if errors:
            raise errors[0]


class TelnetValue:
    def __init__(self, name):
        self.name = name


class TelnetWorkflow:
    def __init__(self, directory):
        self.directory = directory
        self.lines = ['Conversation']
        self.counter = 0

    def value(self, value):
        if isinstance(value, TelnetValue):
            return '${' + value.name + '}'
        self.counter += 1
        cell = '${arg' + str(self.counter) + '}'
        self.lines.append('    ' + cell + '=    Evaluate    ' + velun_expression(value))
        return cell

    def call(self, keyword, *args, rejected=False, **kwargs):
        cells = [self.value(v) for v in args]
        cells += [k + '=' + self.value(v) for k, v in kwargs.items()]
        self.counter += 1
        result = TelnetValue('result' + str(self.counter))
        target = 'Telnet.' + keyword
        if rejected:
            status = '${status' + str(self.counter) + '}'
            self.lines.append('    ' + status + '    ${' + result.name + '}=    Run Keyword And Ignore Error    '
                              + target + '    ' + '    '.join(cells))
            self.lines.append('    Check    ' + status + '    ' + velun_expression('FAIL'))
            self.lines.append('    Should Not Be Empty    ${' + result.name + '}')
        else:
            self.lines.append('    ${' + result.name + '}=    ' + target + '    ' + '    '.join(cells))
        return result

    def check(self, actual, expected):
        self.lines.append('    Check    ' + self.value(actual) + '    ' + velun_expression(expected))

    def contains(self, actual, text):
        self.lines.append('    Should Contain    ' + self.value(actual) + '    ' + self.value(text))

    def open(self, port, **kwargs):
        return self.call('Open Connection', '127.0.0.1', port=port, **kwargs)

    def available(self, expected):
        # Accumulate arbitrary network chunks without inferring a result from prose.
        self.lines.extend([
            "    ${available}=    Set Variable    ${EMPTY}",
            "    FOR    ${attempt}    IN RANGE    100",
            "        ${chunk}=    Telnet.Read",
            "        ${available}=    Evaluate    $available + $chunk",
            f"        IF    len($available) >= {len(expected)}    BREAK",
            "        Sleep    0.02s",
            "    END",
            "    Check    ${available}    " + velun_expression(expected),
        ])

    def clock(self):
        self.counter += 1
        result = TelnetValue('clock' + str(self.counter))
        self.lines.append('    ${' + result.name + '}=    Evaluate    time.monotonic()    modules=time')
        return result

    def elapsed(self, start, lower, upper):
        self.lines.append('    ${elapsed}=    Evaluate    time.monotonic() - $' + start.name + '    modules=time')
        self.lines.append(f'    Should Be True    {lower} <= $elapsed <= {upper}')

    def run(self):
        return utility_run(self.directory, '\n'.join(self.lines) + '\n', {'Conversation': 'PASS'},
                           settings='Library    Telnet\nTest Teardown    Telnet.Close All Connections\n')
