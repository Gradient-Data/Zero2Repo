# feature: F09
"""Acceptance tests for remote sessions and terminal controls."""
import pytest
import velnora

from _helpers import bounded, run_async, temporary_environment, opened_connection
from F02_helpers import certificate_identity
from F03_helpers import authorized_line
from F09_helpers import session_connection, observed_session, finish_session


def test_session_activities():
    """F09.T01: all activity kinds are delivered or explicitly refused."""
    async def exercise():
        activities = [({}, ('shell', None)),
                      ({'command': 'inspect --verbose'}, ('command', 'inspect --verbose')),
                      ({'subsystem': 'inventory'}, ('subsystem', 'inventory'))]
        async with session_connection() as (conn, ready):
            for options, expected in activities:
                writer, stdout, stderr, app = await observed_session(conn, ready, **options)
                assert app.activity == expected
                assert app.channel.get_command() == (expected[1] if expected[0] == 'command' else None)
                assert app.channel.get_subsystem() == (expected[1] if expected[0] == 'subsystem' else None)
                app.channel.write('activity accepted\n')
                await finish_session(writer, app)
                assert await bounded(stdout.read()) == 'activity accepted\n'
        async with session_connection(application_options={'accept': False}) as (conn, ready):
            for options, _ in activities:
                with pytest.raises(velnora.ChannelOpenError) as error:
                    await bounded(conn.open_session(**options))
                assert error.value.code == velnora.OPEN_REQUEST_SESSION_FAILED
        async with session_connection(handler=False) as (conn, ready):
            # Each refusal is a channel-open failure (no particular code is
            # promised) and leaves the authenticated connection usable.
            for options, _ in activities:
                with pytest.raises(velnora.ChannelOpenError):
                    await bounded(conn.open_session(**options))
            assert not conn.is_closed()
        return 'test_session_activities'
    assert run_async(exercise()) == 'test_session_activities'


def test_environment_and_forced_commands():
    """F09.T02: actual authenticated sessions apply source precedence."""
    async def exercise():
        key, _ = certificate_identity()
        ca, _ = certificate_identity()
        direct = {'F09_SHARED': 'direct value', 'F09_DIRECT': 'only direct'}
        local = {'F09_SHARED': 'local value', 'F09_LOCAL': 'only local',
                 'OTHER_LOCAL': 'not selected'}
        base = 'environment="F09_SHARED=key default",environment="F09_KEY=only key",environment="F09_LOCAL=key default"'
        activities = ({}, {'command': 'requested command'}, {'subsystem': 'requested-subsystem'})
        # Each identity differs only in its source of forced command.
        identities = [
            (authorized_line(key, base), key, None),
            (authorized_line(key, base + ',command="key command"'), key, 'key command'),
            (authorized_line(ca, 'cert-authority,' + base + ',command="key command"'),
             (key, ca.generate_user_certificate(key, 'session', principals=['member'],
                                                force_command='certificate command')),
             'certificate command'),
        ]
        with temporary_environment(local):
            for text, identity, forced in identities:
                async with session_connection(authorization=velnora.import_authorized_keys(text),
                                              client_keys=[identity]) as (conn, ready):
                    for activity in activities:
                        writer, _, _, app = await observed_session(
                            conn, ready, env=direct, send_env=['F09_*'], **activity)
                        assert dict(app.channel.get_environment()) == {
                            'F09_SHARED': 'direct value', 'F09_DIRECT': 'only direct',
                            'F09_LOCAL': 'only local', 'F09_KEY': 'only key'}
                        expected = (('command', forced) if forced is not None else
                                    ('command', activity['command']) if 'command' in activity else
                                    ('subsystem', activity['subsystem']) if 'subsystem' in activity else
                                    ('shell', None))
                        assert app.activity == expected
                        assert app.channel.get_command() == (expected[1] if expected[0] == 'command' else None)
                        assert app.channel.get_subsystem() == (expected[1] if expected[0] == 'subsystem' else None)
                        await finish_session(writer, app)
        return 'test_environment_and_forced_commands'
    assert run_async(exercise(), timeout=30) == 'test_environment_and_forced_commands'


def test_terminal_requests_and_policies(tmp_path):
    """F09.T03: terminal metadata and selection policies reach the peer."""
    async def exercise():
        # RFC 4254 section 8 opcode assignments, independent of product constants.
        modes = {code: code for code in range(1, 19)}
        modes.update({code: code % 2 for code in
                      [*range(30, 42), *range(50, 63), *range(70, 76), *range(90, 94)]})
        modes.update({128: 19200, 129: 38400})
        async with session_connection() as (conn, ready):
            for size, expected_size in [((103, 37), (103, 37, 0, 0)),
                                        ((103, 37, 824, 592), (103, 37, 824, 592))]:
                writer, _, _, app = await observed_session(
                    conn, ready, term_type='xterm', term_size=size, term_modes=modes)
                assert app.terminal_request == ('xterm', expected_size, modes)
                assert app.channel.get_terminal_type() == 'xterm'
                assert app.channel.get_terminal_size() == expected_size
                assert dict(app.channel.get_terminal_modes()) == modes
                for mode, value in modes.items():
                    assert app.channel.get_terminal_mode(mode) == value
                await finish_session(writer, app)
            # Every policy has a live positive arm; activity changes test auto selection.
            scenarios = [
                ({}, True), ({'command': 'inspect'}, True),
                ({'request_pty': False}, False),
                ({'request_pty': True, 'command': 'inspect'}, True),
                ({'request_pty': True, 'term_type': None}, False),
                ({'request_pty': 'force', 'term_type': None, 'command': 'inspect'}, True),
                ({'request_pty': 'auto'}, True),
                ({'request_pty': 'auto', 'command': 'inspect'}, False),
                ({'request_pty': 'auto', 'subsystem': 'inventory'}, False),
                ({'request_pty': 'auto', 'term_type': None}, False),
                ({'term_type': None}, False),
            ]
            for overrides, requested in scenarios:
                options = dict(term_type='vt100', term_size=(91, 29))
                options.update(overrides)
                writer, _, _, app = await observed_session(conn, ready, **options)
                if requested:
                    assert app.terminal_request == (options['term_type'] or '', (91, 29, 0, 0), {})
                    assert app.channel.get_terminal_type() == (options['term_type'] or '')
                else:
                    assert app.terminal_request is None
                    assert app.channel.get_terminal_type() is None
                # A completed application proves the suppressed request did not kill the session.
                await finish_session(writer, app, 17)
                assert writer.channel.get_exit_status() == 17
        for server_options, application_options in [({'allow_pty': False}, {}),
                                                     ({}, {'accept_terminal': False})]:
            async with session_connection(application_options=application_options,
                                          **server_options) as (conn, ready):
                writer, _, _, app = await observed_session(conn, ready, request_pty=False)
                await finish_session(writer, app)
                with pytest.raises(velnora.ChannelOpenError) as error:
                    await bounded(conn.open_session(term_type='xterm'))
                assert error.value.code == velnora.OPEN_REQUEST_PTY_FAILED
        # An independent OpenSSH server decodes the RFC 4254 encoding into a real
        # terminal: opcode 53 is ECHO, opcode 3 is VERASE (a character value);
        # the size is in characters.
        from F06_helpers import openssh_daemon, daemon_connect
        async with openssh_daemon(tmp_path / 'daemon') as (port, user_key, _, _):
            async with opened_connection(daemon_connect(port, user_key)) as conn:
                for echo, flag, erase, shown in ((1, ' echo ', 8, ' erase = ^H '),
                                                 (0, ' -echo ', 21, ' erase = ^U ')):
                    result = await bounded(conn.run('stty -a', term_type='vt100',
                        term_size=(103, 37), term_modes={53: echo, 3: erase}))
                    assert result.exit_status == 0, result.stderr
                    settings = ' ' + ' '.join(result.stdout.replace(';', ' ').split()) + ' '
                    assert flag in settings, result.stdout
                    assert shown in settings, result.stdout
                    assert ' rows 37 ' in settings and ' columns 103 ' in settings, result.stdout
        return 'test_terminal_requests_and_policies'
    assert run_async(exercise(), timeout=40) == 'test_terminal_requests_and_policies'


def test_controls_output_and_completion():
    """F09.T04: control delivery, output streams and termination remain distinct."""
    async def exercise():
        async with session_connection() as (conn, ready):
            writer, stdout, stderr, app = await observed_session(conn, ready, term_type='xterm')
            for dimensions in [(121, 43, 968, 688), (72, 20, 0, 0)]:
                writer.channel.change_terminal_size(*dimensions)
                assert await bounded(app.events.get()) == ('size', dimensions)
                assert app.channel.get_terminal_size() == dimensions
            writer.channel.send_break(375)
            assert await bounded(app.events.get()) == ('break', 375)
            for signal in ('INT', 'TERM'):
                writer.channel.send_signal(signal)
                assert await bounded(app.events.get()) == ('signal', signal)
            app.channel.write('ordinary: α\n')
            app.channel.write_stderr('diagnostic: β\n')
            await finish_session(writer, app, 23)
            assert await bounded(stdout.read()) == 'ordinary: α\n'
            assert await bounded(stderr.read()) == 'diagnostic: β\n'
            assert writer.channel.get_exit_status() == 23
            assert writer.channel.get_exit_signal() is None
            writer, stdout, stderr, app = await observed_session(conn, ready, command='signal-outcome')
            app.channel.write('before signal\n')
            app.channel.exit_with_signal('TERM', True, 'application detail', 'en-US')
            await bounded(writer.wait_closed())
            assert await bounded(stdout.read()) == 'before signal\n'
            assert writer.channel.get_exit_status() == -1
            # Message wording is application supplied, not a product diagnostic.
            assert writer.channel.get_exit_signal() == ('TERM', True, 'application detail', 'en-US')
        return 'test_controls_output_and_completion'
    assert run_async(exercise()) == 'test_controls_output_and_completion'


def test_session_context_and_identity_permissions():
    """F09.T05: public queries expose real identity restrictions in sessions."""
    async def exercise():
        key, _ = certificate_identity()
        ca, _ = certificate_identity()
        permissions = ('pty', 'X11-forwarding', 'agent-forwarding', 'port-forwarding')
        identities = [
            (authorized_line(key), key, True, True),
            (authorized_line(key, ','.join('no-' + p for p in permissions)), key, False, True),
            (authorized_line(ca, 'cert-authority'),
             (key, ca.generate_user_certificate(key, 'unrestricted', principals=['member'])), True, True),
            (authorized_line(ca, 'cert-authority'),
             (key, ca.generate_user_certificate(key, 'no-terminal', principals=['member'],
                                                permit_pty=False, permit_x11_forwarding=False,
                                                permit_agent_forwarding=False,
                                                permit_port_forwarding=False)), True, False),
        ]
        for text, identity, key_allowed, cert_allowed in identities:
            async with session_connection(authorization=velnora.import_authorized_keys(text),
                                          client_keys=[identity]) as (conn, ready):
                for activity in ({'command': 'context-command'}, {'subsystem': 'context-subsystem'}):
                    writer, _, _, app = await observed_session(
                        conn, ready, env={'SESSION_ROLE': 'analyst'}, request_pty=False, **activity)
                    channel = app.channel
                    peer = channel.get_connection()
                    assert channel.get_extra_info('username') == 'member'
                    assert channel.get_command() == activity.get('command')
                    assert channel.get_subsystem() == activity.get('subsystem')
                    assert dict(channel.get_environment()) == {'SESSION_ROLE': 'analyst'}
                    assert channel.get_terminal_type() is None
                    assert {p: peer.check_key_permission(p) for p in permissions} == {
                        p: key_allowed for p in permissions}
                    assert {p: peer.check_certificate_permission(p) for p in permissions} == {
                        p: cert_allowed for p in permissions}
                    await finish_session(writer, app)
                if key_allowed and cert_allowed:
                    writer, _, _, app = await observed_session(
                        conn, ready, term_type='vt100', term_size=(88, 33))
                    assert app.channel.get_terminal_type() == 'vt100'
                    assert app.channel.get_terminal_size() == (88, 33, 0, 0)
                    await finish_session(writer, app)
                else:
                    with pytest.raises(velnora.ChannelOpenError) as error:
                        await bounded(conn.open_session(term_type='vt100', term_size=(88, 33)))
                    assert error.value.code == velnora.OPEN_REQUEST_PTY_FAILED
        return 'test_session_context_and_identity_permissions'
    assert run_async(exercise(), timeout=30) == 'test_session_context_and_identity_permissions'
