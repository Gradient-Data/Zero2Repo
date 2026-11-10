# feature: F11
"""Acceptance of interactive editing through real SSH terminal sessions."""
from _helpers import run_async, bounded
from F11_helpers import editing_session, edit_send, submitted


def test_editing_and_history():
    async def exercise():
        # Each editing operation must change the line delivered to the application.
        cases = [
            ('crate\x02\x02X\n', 'craXte\n'),
            ('boat\x08\n', 'boa\n'),
            ('abcd\x02\x02\x08\n', 'acd\n'),
            ('planet\x02\x02\x04\n', 'plant\n'),
            ('abcd\x02\x02\x06X\n', 'abcXd\n'),
            ('tail\x01head-\x05!\n', 'head-tail!\n'),
            ('discard\x15new\n', 'new\n'),
            ('keep\x02\x02\x15\n', '\n'),
            ('north-south\x02\x02\x02\x02\x02\x0b\n', 'north-\n'),
            ('saved\x15\x19\n', 'saved\n'),
            ('prefix-tail\x02\x02\x02\x02\x0b\x19\n', 'prefix-tail\n'),
        ]
        async with editing_session() as (channel, client, app):
            await edit_send(channel, client, 'visible')
            assert client.screen.display[0].rstrip() == 'visible'
            assert app.input.empty()
            await edit_send(channel, client, '\x15')
            for keys, expected in cases:
                await edit_send(channel, client, keys)
                assert await submitted(app) == expected
            await edit_send(channel, client, 'first\nsecond\n\x10\x10\x0e!\n')
            assert [await submitted(app) for _ in range(3)] == [
                'first\n', 'second\n', 'second!\n']
        return 'test_editing_and_history'
    assert run_async(exercise(), timeout=30) == 'test_editing_and_history'


def test_modes_and_echo():
    async def exercise():
        async with editing_session(line_editor=False) as (channel, client, app):
            await edit_send(channel, client, 'raw\x08')
            assert await submitted(app, 4) == 'raw\x08'
        async with editing_session() as (channel, client, app):
            await edit_send(channel, client, 'pending')
            assert app.input.empty()
            app.channel.set_line_mode(False)
            assert await submitted(app, 7) == 'pending'
            await edit_send(channel, client, 'Z')
            assert await submitted(app, 1) == 'Z'
            # Reset the pending line and cursor before returning after a flush.
            app.channel.set_input('', 0)
            app.channel.set_line_mode(True)
            await edit_send(channel, client, 'line\x08!\n')
            assert await submitted(app) == 'lin!\n'
        async with editing_session() as (channel, client, app):
            app.channel.set_line_mode(False)
            await edit_send(channel, client, 'Z')
            assert await submitted(app, 1) == 'Z'
            app.channel.set_line_mode(True)
            await edit_send(channel, client, 'line\x08!\n')
            assert await submitted(app) == 'lin!\n'
        async with editing_session() as (channel, client, app):
            await edit_send(channel, client, 'public\n')
            assert await submitted(app) == 'public\n'
            assert client.screen.display[0].rstrip() == 'public'
            app.channel.set_echo(False)
            start = len(client.output)
            await edit_send(channel, client, 'confidential\x08\n')
            assert await submitted(app) == 'confidentia\n'
            assert 'confidentia' not in client.output[start:]
            assert all(not row.strip() for row in client.screen.display[1:])
            app.channel.set_echo(True)
            await edit_send(channel, client, '\x10\n')
            assert await submitted(app) == 'public\n'
            assert any(row.rstrip() == 'public' for row in client.screen.display[1:])
        return 'test_modes_and_echo'
    assert run_async(exercise(), timeout=30) == 'test_modes_and_echo'


def test_line_and_history_limits():
    async def exercise():
        for options, size in (({}, 1024), ({'max_line_length': 17}, 17),
                              ({'max_line_length': 0}, 4096)):
            async with editing_session(**options) as (channel, client, app):
                text = ('界a' * (size // 2 + 5))[:size]
                extra = '' if options.get('max_line_length') == 0 else 'overflow'
                await edit_send(channel, client, text + extra + '\n')
                assert await submitted(app) == text + '\n'
                # A deletion frees exactly one character of capacity.
                await edit_send(channel, client, text + '\x08Z\n')
                assert await submitted(app) == text[:-1] + 'Z\n'
        for options, count, earliest in (({}, 1001, 'h1'),
                                         ({'line_history': 2}, 3, 'h1'),
                                         ({'line_history': 0}, 3, ''),
                                         ({'line_history': -2}, 3, '')):
            async with editing_session(**options) as (channel, client, app):
                lines = [f'h{i}' for i in range(count)]
                await edit_send(channel, client, '\n'.join(lines) + '\n\n')
                assert [await submitted(app) for _ in range(count + 1)] == [
                    line + '\n' for line in lines] + ['\n']
                await edit_send(channel, client, '\x10' * (count + 1) + '\n')
                assert await submitted(app) == earliest + '\n'
        return 'test_line_and_history_limits'
    assert run_async(exercise(), timeout=60) == 'test_line_and_history_limits'


def test_pending_input_and_custom_keys():
    async def exercise():
        async with editing_session() as (channel, client, app):
            await edit_send(channel, client, 'discard')
            app.channel.clear_input()
            await edit_send(channel, client, 'kept\n')
            assert await submitted(app) == 'kept\n'
            await edit_send(channel, client, 'old')
            app.channel.set_input('abcde', 2)
            await edit_send(channel, client, 'X\n')
            assert await submitted(app) == 'abXcde\n'
            app.channel.register_key('!', lambda line, pos: (line[:pos] + 'NEW' + line[pos:], pos + 3))
            app.channel.register_key('?', lambda line, pos: True)
            app.channel.register_key('#', lambda line, pos: False)
            app.channel.register_key('\x1a', lambda line, pos: ('ALERT', -1))
            await edit_send(channel, client, 'ab\x02!?#\x1a\n')
            assert await bounded(app.events.get()) == ('signal', 'ALERT')
            assert await submitted(app) == 'aNEW?b\n'
            for key in ('!', '?', '#', '\x1a'):
                app.channel.unregister_key(key)
            await edit_send(channel, client, '!?#\n')
            assert await submitted(app) == '!?#\n'
        return 'test_pending_input_and_custom_keys'
    assert run_async(exercise(), timeout=30) == 'test_pending_input_and_custom_keys'


def test_terminal_resize_and_wide_characters():
    async def exercise():
        async with editing_session(width=12) as (channel, client, app):
            await edit_send(channel, client, 'abcdefg界')
            await edit_send(channel, client, '\x02Z')
            assert client.screen.display[0].rstrip() == 'abcdefgZ界'
            await edit_send(channel, client, '\x05')
            assert (client.screen.cursor.x, client.screen.cursor.y) == (10, 0)
            await edit_send(channel, client, '\x08Q\n')
            assert await submitted(app) == 'abcdefgZQ\n'
            assert client.screen.display[0].rstrip() == 'abcdefgZQ'
            await edit_send(channel, client, 'fit')
            # Resize an unwrapped pending line: no emulator-specific reflow needed.
            client.screen.resize(lines=24, columns=20)
            channel.change_terminal_size(20, 24)
            await edit_send(channel, client, 'ABCDEFGHI界')
            assert client.screen.display[1].rstrip() == 'fitABCDEFGHI界'
            assert (client.screen.cursor.x, client.screen.cursor.y) == (14, 1)
            await edit_send(channel, client, '\x02\x02')
            assert (client.screen.cursor.x, client.screen.cursor.y) == (11, 1)
            await edit_send(channel, client, 'Z\x05\x08Q\n')
            assert await submitted(app) == 'fitABCDEFGHZIQ\n'
            assert client.screen.display[1].rstrip() == 'fitABCDEFGHZIQ'
            await edit_send(channel, client, 'A界B\x02\x02\x04C\n')
            assert await submitted(app) == 'ACB\n'
            assert client.screen.display[2].rstrip() == 'ACB'
        return 'test_terminal_resize_and_wide_characters'
    assert run_async(exercise(), timeout=30) == 'test_terminal_resize_and_wide_characters'
