# feature: F18
"""Acceptance evidence from real local Telnet conversations."""
from contextlib import ExitStack
from _helpers import keyword_calls
import socket

from F18_helpers import telnet_peer, TelnetWorkflow


def test_independent_session_lifecycle(tmp_path):
    with ExitStack() as peers:
        a, ar = peers.enter_context(telnet_peer([
            ('receive', b'first'), ('send', b'alpha!'),
            ('receive', b'again'), ('send', b'alpha-again!')]))
        b, br = peers.enter_context(telnet_peer([
            ('receive', b'second'), ('send', b'beta!'),
            ('receive', b'survivor'), ('send', b'beta-alive!')]))
        w = TelnetWorkflow(tmp_path)
        first = w.open(a, alias='left', timeout='0.5s')
        second = w.open(b, alias='right', timeout='0.5s')
        w.call('Write Bare', 'second')
        w.check(w.call('Read Until', '!'), 'beta!')
        w.call('Switch Connection', first)
        w.call('Write Bare', 'first')
        w.check(w.call('Read Until', '!'), 'alpha!')
        w.call('Switch Connection', 'right')
        w.call('Switch Connection', 'left')
        w.call('Write Bare', 'again')
        w.check(w.call('Read Until', '!'), 'alpha-again!')
        w.call('Close Connection')
        w.call('Switch Connection', second)
        w.call('Write Bare', 'survivor')
        w.check(w.call('Read Until', '!'), 'beta-alive!')
        w.call('Switch Connection', 'unknown-session', rejected=True)
        w.call('Close All Connections')
        w.call('Switch Connection', 'right', rejected=True)
        w.call('Switch Connection', first, rejected=True)
        # A bound, non-listening local port produces a real connection refusal.
        with socket.socket() as unavailable:
            unavailable.bind(('127.0.0.1', 0))
            w.open(unavailable.getsockname()[1], rejected=True, connection_timeout='0.5s')
            w.run()
        assert ar == [b'first', b'again']
        assert br == [b'second', b'survivor']


def test_writes_controls_and_read_conditions(tmp_path):
    controls = [('BRK', 243), ('IP', 244), ('AO', 245), ('AYT', 246),
                ('EC', 247), ('EL', 248), ('NOP', 241), (242, 242)]
    steps = [('receive', b'line\n'), ('send', b'line\n'),
             ('receive', b'bare'), ('send', b'pre literal ENDafter;'),
             ('receive', b'regex'), ('send', b'prefix ticket=482;rest!'),
             ('receive', b'prompt'), ('send', b'body ready>'),
             ('receive', b'pattern'), ('send', b'next user7>'),
             ('receive', b'stripped'), ('send', b'more user42>'),
             ('receive', b'available'), ('send', b'unprompted content')]
    steps += [('receive', b''.join(bytes([255, code]) for _, code in controls)), ('send', b'controls-ok!')]
    with telnet_peer(steps) as (port, received):
        w = TelnetWorkflow(tmp_path)
        w.open(port, timeout='0.7s')
        w.call('Set Newline', 'LF')
        w.check(w.call('Write', 'line'), 'line\n')
        w.call('Write Bare', 'bare')
        # Reads end at the stopping match; content after it is returned by the next read.
        w.check(w.call('Read Until', 'END'), 'pre literal END')
        w.check(w.call('Read Until', ';'), 'after;')
        w.call('Write Bare', 'regex')
        w.check(w.call('Read Until Regexp', r'ticket=\d+;'), 'prefix ticket=482;')
        w.check(w.call('Read Until', '!'), 'rest!')
        w.call('Read Until Prompt', rejected=True)
        w.call('Set Prompt', 'ready>')
        w.call('Write Bare', 'prompt')
        w.check(w.call('Read Until Prompt'), 'body ready>')
        w.call('Set Prompt', r'user\d+>', prompt_is_regexp=True)
        w.call('Write Bare', 'pattern')
        w.check(w.call('Read Until Prompt'), 'next user7>')
        # Stripping a pattern prompt removes the matched prompt text, not the pattern's length.
        w.call('Write Bare', 'stripped')
        w.check(w.call('Read Until Prompt', strip_prompt=True), 'more ')
        w.call('Write Bare', 'available')
        w.available('unprompted content')
        for name, _ in controls:
            w.call('Write Control Character', name)
        w.check(w.call('Read Until', '!'), 'controls-ok!')
        w.run()
        assert received == [value for kind, value in steps if kind == 'receive']


def test_login_credentials_and_success_conditions(tmp_path):
    # Each peer conducts the same credential exchange; only its final reply varies.
    replies = [b'accepted shell>', b'accepted but no prompt', b'welcome', b'DENIED']
    with ExitStack() as peers:
        ports = []
        records = []
        for i, reply in enumerate(replies):
            # Without a session prompt the reply arrives after 1.2 s, so only the
            # caller-selected 1.5 s login wait (not a shorter or fixed one) reads it.
            port, record = peers.enter_context(telnet_peer([
                ('send', b'User?'), ('receive', b'visitor\r\n'),
                ('send', b'Secret?'), ('receive', b'passphrase\r\n'),
                ('delay', 0.1 if i < 2 else 1.2), ('send', reply)]))
            ports.append(port)
            records.append(record)
        w = TelnetWorkflow(tmp_path)
        for i, port in enumerate(ports):
            opts = {'prompt': 'shell>'} if i < 2 else {}
            w.open(port, timeout='0.4s', **opts)
            result = w.call('Login', 'visitor', 'passphrase', login_prompt='User?',
                            password_prompt='Secret?', login_timeout='0.2s' if i < 2 else '1.5s', login_incorrect='DENIED',
                            rejected=i in (1, 3))
            if i in (0, 2):
                w.check(result, 'User?Secret?' + replies[i].decode())
            w.call('Close Connection')
        w.run()
        assert records == [[b'visitor\r\n', b'passphrase\r\n']] * 4


def test_command_response_echo_and_prompt_choices(tmp_path):
    # Rebuild identical peer state for each explicit choice.
    with ExitStack() as peers:
        ports = [peers.enter_context(telnet_peer([
            ('receive', b'status\r\n'), ('send', b'status\r\nanswer=running\r\nshell>')]))[0]
                 for _ in range(4)]
        w = TelnetWorkflow(tmp_path)
        for port, keep_echo, strip_prompt in zip(ports, [True, True, False, False], [False, True, False, True]):
            w.open(port, prompt='shell>', timeout='0.7s')
            if keep_echo:
                w.call('Write Bare', 'status\r\n')
                result = w.call('Read Until Prompt', strip_prompt=strip_prompt)
            else:
                result = w.call('Execute Command', 'status', strip_prompt=strip_prompt)
            w.check(result, ('status\r\n' if keep_echo else '') + 'answer=running\r\n'
                    + ('' if strip_prompt else 'shell>'))
            w.call('Close Connection')
        w.run()


def test_timeout_reports_condition_and_received_output(tmp_path):
    with ExitStack() as peers:
        ports = [peers.enter_context(telnet_peer([
            ('receive', b'go'), ('send', b'partial-evidence;')]))[0] for _ in range(4)]
        w = TelnetWorkflow(tmp_path)
        w.open(ports[0], timeout='0.25s')
        w.call('Write Bare', 'go')
        w.check(w.call('Read Until', ';'), 'partial-evidence;')
        w.call('Close Connection')
        for port, keyword, condition in zip(ports[1:], ['Read Until', 'Read Until Regexp', 'Read Until Prompt'],
                                              ['missing-stop', r'final-[0-9]+', 'missing-prompt>']):
            w.open(port, timeout='0.25s')
            w.call('Write Bare', 'go')
            if keyword == 'Read Until Prompt':
                w.call('Set Prompt', condition)
            start = w.clock()
            result = w.call(keyword, *([] if keyword == 'Read Until Prompt' else [condition]), rejected=True)
            w.elapsed(start, 0.2, 2)
            w.contains(result, condition)
            if keyword != 'Read Until Prompt':
                w.contains(result, 'partial-evidence;')
            w.call('Close Connection')
        root = w.run()
        # Prompt timeout reports the received text on the keyword's INFO channel.
        calls = keyword_calls(root, 'Read Until Prompt', owner='Telnet', recursive=True)
        assert len(calls) == 1
        assert calls[0].find('status').attrib['status'] == 'FAIL'
        assert any(m.text == 'partial-evidence;' for m in calls[0].findall("msg[@level='INFO']"))


def test_terminal_rendering_dimensions_and_prompt(tmp_path):
    with ExitStack() as peers:
        # Cursor address, overwrite and erase produce a screen unlike the wire text.
        ports = [peers.enter_context(telnet_peer([
            ('receive', b'go'), ('send', b'abcdefghij\x1b[1;3HXY\x1b[2;1HbadTAIL\x1b[2K\x1b[3;1HOK>')]))[0]
                 for _ in range(2)]
        w = TelnetWorkflow(tmp_path)
        for port, width, expected in zip(ports, [8, 12], ['abXYefgh\r\n\r\nOK>', 'abXYefghij\r\n\r\nOK>']):
            w.open(port, terminal_emulation=True, window_size=f'{width}x4', prompt='OK>', timeout='1s')
            w.call('Write Bare', 'go')
            w.check(w.call('Read Until Prompt'), expected)
            w.call('Close Connection')
        # Read wrapping before any cursor or erase operation can conceal it.
        for width in (8, 12):
            text = 'abcdefghijklmn'[:width + 2]
            port, _ = peers.enter_context(telnet_peer([
                ('receive', b'wrap'), ('send', (text + 'OK>').encode())]))
            w.open(port, terminal_emulation=True, window_size=f'{width}x4', prompt='OK>', timeout='1s')
            w.call('Write Bare', 'wrap')
            w.check(w.call('Read Until Prompt'), text[:width] + '\r\n' + text[width:] + 'OK>')
            w.call('Close Connection')
        w.run()


def test_defaults_binary_encoding_and_session_overrides(tmp_path):
    with ExitStack() as peers:
        default, dr = peers.enter_context(telnet_peer([
            ('receive', 'café\r\n'.encode()), ('send', 'café\r\n'.encode()),
            ('receive', b'raw'), ('send', b'\x1b[31mred\x1b[0m!'),
            ('receive', b'timeout'), ('send', b'waiting'),
            ('receive', b'end'), ('send', b'\xfe' + 'é!'.encode())]))
        altered, ar = peers.enter_context(telnet_peer([
            ('receive', b'caf\n'), ('send', b'caf\n'),
            ('receive', b'badread'), ('send', b'\xfe!'),
            ('receive', b'caf?'), ('send', b'\xfe!'),
            ('receive', b'\x00\x80Z'), ('send', b'\x81\x80!')]))
        later, lr = peers.enter_context(telnet_peer([
            ('receive', 'é\r\n'.encode()), ('send', 'é\r\n'.encode()),
            ('receive', b'later'), ('send', b'\xfe' + 'ü!'.encode())]))
        w = TelnetWorkflow(tmp_path)
        first = w.open(default)
        second = w.open(altered, encoding='ASCII', newline='LF', timeout='0.3s')
        w.check(w.call('Write', 'café'), 'caf\n')
        w.call('Set Encoding', errors='strict')
        w.call('Write Bare', 'café', rejected=True)
        w.call('Write Bare', 'badread')
        w.call('Read Until', '!', rejected=True)
        w.call('Set Encoding', errors='replace')
        w.call('Write Bare', 'café')
        w.check(w.call('Read Until', '!'), '�!')
        w.call('Set Encoding', 'NONE')
        w.call('Write Bare', b'\x00\x80Z')
        w.check(w.call('Read Until', b'!'), b'\x81\x80!')
        # A session opened after another session's overrides still gets the defaults.
        w.open(later)
        w.check(w.call('Write', 'é'), 'é\r\n')
        w.call('Write Bare', 'later')
        w.check(w.call('Read Until', '!'), 'ü!')
        w.call('Close Connection')
        w.call('Switch Connection', first)
        w.check(w.call('Write', 'café'), 'café\r\n')
        # No prompt by default: refused as configuration, not awaited for the 3 s timeout.
        start = w.clock()
        w.call('Read Until Prompt', rejected=True)
        w.elapsed(start, 0, 2)
        w.call('Write Bare', 'raw')
        w.check(w.call('Read Until', '!'), '\x1b[31mred\x1b[0m!')
        w.call('Write Bare', 'timeout')
        start = w.clock()
        failure = w.call('Read Until', 'never-here', rejected=True)
        # The fixed three-second deadline is observed externally, with scheduler reserve.
        w.elapsed(start, 2.7, 6)
        w.contains(failure, 'never-here')
        w.contains(failure, 'waiting')
        w.call('Write Bare', 'end')
        w.check(w.call('Read Until', '!'), 'é!')
        w.run()
        assert dr == ['café\r\n'.encode(), b'raw', b'timeout', b'end']
        assert ar == [b'caf\n', b'badread', b'caf?', b'\x00\x80Z']
        assert lr == ['é\r\n'.encode(), b'later']
