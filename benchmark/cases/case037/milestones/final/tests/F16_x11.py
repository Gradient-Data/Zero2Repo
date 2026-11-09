# feature: F16
"""Acceptance tests for session X11 forwarding through real display sockets."""
import velnora
import pytest

from _helpers import bounded, run_async, temporary_environment
from F09_helpers import observed_session, finish_session
from F16_helpers import (local_display, x11_connection, display_options,
                         forwarded_authorization, display_exchange, rejected_x11)


def test_display_authorization_traffic_and_default(tmp_path):
    """F16.T01: selected and environment displays receive authenticated traffic."""
    async def exercise():
        async with local_display(tmp_path / 'local.auth', b'display-selected') as selected:
            async with local_display(tmp_path / 'env.auth', b'display-environment') as env_display:
                for environment_selected in (False, True):
                    display = env_display if environment_selected else selected
                    server_auth = tmp_path / 'remote.auth'
                    with temporary_environment({'DISPLAY': env_display.address,
                                                'XAUTHORITY': str(env_display.auth_path)}):
                        async with x11_connection(server_auth) as (conn, ready):
                            options = (dict(x11_forwarding=True) if environment_selected
                                       else display_options(display,
                                            x11_display=display.address.rsplit('.', 1)[0] + '.3'))
                            writer, _, _, app = await observed_session(conn, ready, **options)
                            remote = app.channel.get_x11_display()
                            assert isinstance(remote, str)
                            assert int(remote.rsplit('.', 1)[1]) == (0 if environment_selected else 3)
                            authorization = forwarded_authorization(server_auth, remote)
                            await display_exchange(display, remote, authorization,
                                                   b'first request\x00\xff', order=b'B')
                            await display_exchange(display, remote, authorization,
                                                   b'second request', order=b'l')
                            await finish_session(writer, app)
                        async with x11_connection(server_auth) as (conn, ready):
                            writer, _, _, app = await observed_session(conn, ready)
                            assert app.channel.get_x11_display() is None
                            # An unsolicited X11 channel is refused; no code is promised.
                            with pytest.raises(velnora.ChannelOpenError):
                                await bounded(app.channel.get_connection().create_x11_connection(
                                    velnora.SSHTCPSession))
                            await finish_session(writer, app)
        return 'test_display_authorization_traffic_and_default'
    assert run_async(exercise(), timeout=40) == 'test_display_authorization_traffic_and_default'


def test_authorization_isolation_displays_and_single_connection(tmp_path):
    """F16.T02: independent displays, rejected credentials, and one-use access."""
    async def exercise():
        async with local_display(tmp_path / 'a.auth', b'display-A') as first:
            async with local_display(tmp_path / 'b.auth', b'display-B') as second:
                async with x11_connection(tmp_path / 'ra.auth') as (conn_a, ready_a):
                    async with x11_connection(tmp_path / 'rb.auth') as (conn_b, ready_b):
                        wa, _, _, aa = await observed_session(
                            conn_a, ready_a, **display_options(first))
                        wb, _, _, ab = await observed_session(
                            conn_b, ready_b, **display_options(second))
                        da, db = aa.channel.get_x11_display(), ab.channel.get_x11_display()
                        auth_a = forwarded_authorization(tmp_path / 'ra.auth', da)
                        auth_b = forwarded_authorization(tmp_path / 'rb.auth', db)
                        await display_exchange(first, da, auth_a, b'route-A')
                        await display_exchange(second, db, auth_b, b'route-B')
                        before_a, before_b = list(first.delivered), list(second.delivered)
                        await rejected_x11(da, auth_b, b'forbidden-A')
                        await rejected_x11(db, auth_a, b'forbidden-B')
                        # Live valid exchanges fence the rejected packets on both transports.
                        await display_exchange(first, da, auth_a, b'fence-A')
                        await display_exchange(second, db, auth_b, b'fence-B')
                        assert first.delivered == before_a + [first.delivered[-1]]
                        assert second.delivered == before_b + [second.delivered[-1]]
                        assert all(b'forbidden' not in data and b'route-B' not in data
                                   for data in first.delivered)
                        assert all(b'forbidden' not in data and b'route-A' not in data
                                   for data in second.delivered)
                        await finish_session(wa, aa)
                        await finish_session(wb, ab)
                async with x11_connection(tmp_path / 'single.auth') as (conn, ready):
                    writer, _, _, app = await observed_session(
                        conn, ready, **display_options(first, x11_single_connection=True))
                    remote = app.channel.get_x11_display()
                    auth = forwarded_authorization(tmp_path / 'single.auth', remote)
                    await display_exchange(first, remote, auth, b'one-use')
                    before = list(first.delivered)
                    await rejected_x11(remote, auth, b'forbidden-reuse')
                    await finish_session(writer, app)
                    assert first.delivered == before
        return 'test_authorization_isolation_displays_and_single_connection'
    assert run_async(exercise(), timeout=40) == 'test_authorization_isolation_displays_and_single_connection'


def test_required_and_optional_setup_failures(tmp_path):
    """F16.T03: failed required setup refuses; optional setup retains the session."""
    async def exercise():
        async with local_display(tmp_path / 'local.auth', b'ready') as display:
            # 'server-default' leaves server X11 forwarding unset: it is disabled
            # by default, while the same client request succeeds against an
            # enabling server in test_display_authorization_traffic_and_default.
            for failure in ('missing-display', 'invalid-display', 'corrupt-auth',
                            'prohibited', 'server-default', 'listener-auth'):
                for optional in (False, True):
                    server_auth = tmp_path / 'server.auth'
                    if failure == 'listener-auth':
                        server_auth.write_bytes(b'\xff\xff\x00')
                    else:
                        server_auth.write_bytes(b'')
                    corrupt = tmp_path / 'corrupt.auth'
                    corrupt.write_bytes(b'\xff\xff\x00')
                    options = display_options(display)
                    if failure == 'missing-display':
                        options['x11_display'] = None
                    elif failure == 'invalid-display':
                        options['x11_display'] = 'invalid-display'
                    elif failure == 'corrupt-auth':
                        options['x11_auth_path'] = str(corrupt)
                    options['x11_forwarding'] = 'ignore_failure' if optional else True
                    with temporary_environment(remove=('DISPLAY',)):
                        enabled = {'prohibited': False, 'server-default': None}.get(failure, True)
                        async with x11_connection(server_auth, enabled=enabled) as (conn, ready):
                            if failure == 'listener-auth':
                                # An unparsable server output file may be refused or replaced;
                                # either way the outcome stays a coherent session or the stated refusal.
                                try:
                                    writer, reader, _, app = await observed_session(conn, ready, **options)
                                except velnora.ChannelOpenError as error:
                                    assert not optional
                                    assert error.code == velnora.OPEN_REQUEST_X11_FORWARDING_FAILED
                                else:
                                    if not optional:
                                        assert app.channel.get_x11_display() is not None
                                    app.channel.write('ordinary-session-still-works')
                                    assert await bounded(reader.readexactly(28)) == 'ordinary-session-still-works'
                                    await finish_session(writer, app, status=7)
                                    assert writer.channel.get_exit_status() == 7
                            elif optional:
                                writer, reader, _, app = await observed_session(conn, ready, **options)
                                assert app.channel.get_x11_display() is None
                                app.channel.write('ordinary-session-still-works')
                                assert await bounded(reader.readexactly(28)) == 'ordinary-session-still-works'
                                await finish_session(writer, app, status=7)
                                assert writer.channel.get_exit_status() == 7
                            else:
                                with pytest.raises(velnora.ChannelOpenError) as error:
                                    await bounded(conn.open_session(**options))
                                assert error.value.code == velnora.OPEN_REQUEST_X11_FORWARDING_FAILED
        return 'test_required_and_optional_setup_failures'
    assert run_async(exercise(), timeout=60) == 'test_required_and_optional_setup_failures'
