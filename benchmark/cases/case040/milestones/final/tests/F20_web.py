# feature: F20
"""CGI input, HTML and web output in a real browser, and the serial LCD display."""
import re
import time

import velnora
from velnora.display.html_fragment import HtmlGenerator, screenshot_collect
from velnora.display.lcd import CF635Screen

from _helpers import canvas_snapshot
from F01_helpers import encoding_state
from F20_helpers import (DisplayPeer, browser_page, cell_pixels, cgi_gateway, cgi_input_session,
                         load_fragment, page_links, page_rows, row_text, selected_lines,
                         settle, visible_lines, wait_for_text)

ALLOWED_LINKS = ['http://example.org/a?b=1&c=2', 'https://example.org/secure',
                 'mailto:person@example.org', 'sftp://example.org/file',
                 'file:///tmp/document']
REFUSED_LINKS = ['javascript:alert(1)', ' javascript:alert(1)', 'JaVaScRiPt:alert(1)',
                 'data:text/html,x', 'ftp://example.org/x', 'tel:5551234',
                 'example.org/page', 'httpx://example.org/', 'https.example:x',
                 'fileish:///x']


def link_labels():
    return ([(f'ALLOWED{index}', target) for index, target in enumerate(ALLOWED_LINKS)],
            [(f'REFUSED{index}', target) for index, target in enumerate(REFUSED_LINKS)])


def assert_links(page, allowed, refused):
    # Text survives on both sides; only permitted targets are something to follow.
    lines = ' '.join(visible_lines(page))
    for label, _ in allowed + refused:
        assert label in lines
    # Only links carrying drawn labels belong to the screen; the client page may add its own.
    links = {href: text for href, text in page_links(page).items()
             if 'ALLOWED' in text or 'REFUSED' in text}
    assert links == {target: label for label, target in allowed}


def test_cgi_keyboard_encoding_and_resize_delivery():
    malformed = [
        'window resize 31',
        'window resize 31 9 extra',
        'window resize -31 9',
        'window resize 31.5 9',
        'window resize many 9',
    ]
    requests = [
        ('iso-8859-1', 'é\nup\nup\n'.encode('iso-8859-1')),
        ('utf-8', b'window resize 0 0\n'),
        ('utf-8', b'window resize 250 120\n'),
        ('utf-8', b'window resize 200 100\n'),
        ('utf-8', b'window resize 43 8\n'),
        ('utf-8', ('\n'.join(malformed) + '\n').encode('ascii')),
        ('utf-8', b'\xff\n'),
        ('not-a-character-encoding', b'q\n'),
        ('utf-8', '界\ndown\n'.encode('utf-8')),
    ]
    observation = cgi_input_session((67, 13), requests)
    assert observation['initial_size'] == [67, 13]
    outcomes = observation['requests']
    assert len(outcomes) == len(requests)
    expected = [
        (['é', 'up', 'up'], [67, 13]),
        (['window resize'], [0, 0]),
        (['window resize'], [200, 100]),
        (['window resize'], [200, 100]),
        (['window resize'], [43, 8]),
        (malformed, [43, 8]),
        ([], [43, 8]),
        ([], [43, 8]),
        (['界', 'down'], [43, 8]),
    ]
    for index, (outcome, (keys, size)) in enumerate(zip(outcomes, expected)):
        assert outcome['keys'] == keys, (index, outcome)
        assert outcome['size'] == size, (index, outcome)
        if index in (6, 7):
            # Assert the positive rejection carrier as well as non-delivery.
            assert outcome['headers']['status'].split()[0] == '400'
        else:
            assert outcome['headers']['content-type'] == 'text/plain'


def run_html_application(root, sizes, keys, **options):
    HtmlGenerator.sizes = list(sizes)
    HtmlGenerator.keys = [list(batch) for batch in keys]
    screenshot_collect()
    velnora.MainLoop(root, screen=HtmlGenerator(), **options).run()
    return screenshot_collect()


def test_html_screenshot_text_style_cursor_and_event_chain():
    with encoding_state():
        velnora.set_encoding('utf-8')
        # The application consumes ordered events and sizes, which change later frames.
        editor = velnora.Edit('> ')
        pile = velnora.Pile([editor, velnora.Text('alpha beta gamma delta')])
        fragments = run_html_application(
            velnora.Filler(pile, valign='top'), [(24, 3), (12, 5)],
            [['a', 'b'], ['left', 'X'], ['window resize', 'c', 'c']])
        assert editor.edit_text == 'aXccb'
        assert screenshot_collect() == []
        wide = 'alpha beta gamma delta'
        expected = [['>', wide], ['> aXccb', 'alpha beta', 'gamma delta']]
        with browser_page() as page:
            frames = []
            for fragment in fragments:
                load_fragment(page, fragment)
                frames.append(visible_lines(page))
            # Redraw scheduling is free; the collected frames start before input and end after it.
            assert frames[0] == expected[0] and frames[-1] == expected[-1], frames
            assert len(page_rows(page)) <= 5
            assert all(len(row_text(row)) <= 12 for row in page_rows(page))

            # Literal markup-significant text, reachable by a real user selection.
            literal = '<b>bold</b> & "q" \'r\' <script>window.injected=1</script> é'
            fragments = run_html_application(
                velnora.Filler(velnora.Text(['top ', literal]), valign='top'), [(70, 2)], [])
            load_fragment(page, fragments[-1])
            assert visible_lines(page) == ['top ' + literal]
            assert page.evaluate('() => window.injected === undefined')
            assert selected_lines(page) == ['top ' + literal]

            # Supplied colors reach the displayed cells, whatever the markup.
            for colors, foreground, background, expected_colors in [
                    (2**24, '#123456', '#abcdef', ('rgb(18, 52, 86)', 'rgb(171, 205, 239)')),
                    (2**24, '#fedcba', '#012345', ('rgb(254, 220, 186)', 'rgb(1, 35, 69)')),
                    (256, 'h196', 'h21', ('rgb(255, 0, 0)', 'rgb(0, 0, 255)')),
                    (16, 'yellow', 'dark blue', None)]:
                screen = HtmlGenerator()
                screen.set_terminal_properties(colors=colors)
                screen.register_palette_entry('named', 'yellow', 'dark blue')
                attribute = velnora.AttrSpec(foreground, background, colors)
                markup = [(attribute, 'Direct'), ' ', ('named', 'Named')]
                canvas = velnora.Filler(velnora.Text(markup), valign='top').render((20, 1))
                screenshot_collect()
                screen.draw_screen((20, 1), canvas)
                load_fragment(page, screenshot_collect()[-1])
                row = page_rows(page)[0]
                assert row_text(row[:12]) == 'Direct Named'
                direct = {(cell['color'], cell['background']) for cell in row[:6]}
                named = {(cell['color'], cell['background']) for cell in row[7:12]}
                assert len(direct) == 1 and len(named) == 1
                if expected_colors is None:
                    assert direct == named
                    assert len(set(next(iter(direct)))) == 2
                else:
                    assert direct == {expected_colors}
                    assert direct != named

            # The cursor is seen by comparing frames with and without it.
            def frame(position, focus):
                field = velnora.Edit('', 'hello world', edit_pos=position)
                canvas = velnora.Filler(field, valign='top').render((20, 2), focus)
                assert (canvas.cursor is not None) == focus
                screen = HtmlGenerator()
                screenshot_collect()
                screen.draw_screen((20, 2), canvas)
                load_fragment(page, screenshot_collect()[-1])
                return [cell_pixels(page, cell) for cell in page_rows(page)[0][:11]]

            plain = frame(3, False)
            for position, elsewhere in ((3, 8), (7, 1)):
                shown = frame(position, True)
                assert shown[position] != plain[position]
                assert shown[elsewhere] == plain[elsewhere]


def test_html_screenshot_links_only_for_permitted_destinations():
    allowed, refused = link_labels()
    with encoding_state():
        velnora.set_encoding('utf-8')
        rows = [velnora.Text([(velnora.AttrSpec('default', 'default', hyperlink=target), label), ' plain'])
                for label, target in allowed + refused]
        fragments = run_html_application(
            velnora.Filler(velnora.Pile(rows), valign='top'), [(30, len(rows))], [])
    with browser_page() as page:
        load_fragment(page, fragments[-1])
        assert_links(page, allowed, refused)


def test_browser_client_receives_updates_and_sends_keys_and_resizes():
    allowed, refused = link_labels()
    with cgi_gateway(allowed + refused) as url, browser_page() as page:
        dialogs = []
        page.on('dialog', lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
        page.goto(url)
        wait_for_text(page, 'TYPED')

        def size():
            text = page.evaluate('() => document.body.innerText')
            found = re.findall(r'SIZE (\d+) (\d+)', text)
            assert len(found) == 1, text
            return int(found[0][0]), int(found[0][1])

        first = size()
        assert first[0] > 0 and first[1] > 0
        # Drawn text arrives without a reload, including repeated and ordered input.
        page.keyboard.type('abba')
        wait_for_text(page, 'TYPED abba')
        page.keyboard.press('ArrowUp')
        page.keyboard.press('F2')
        wait_for_text(page, 'PRESSED up f2')
        assert_links(page, allowed, refused)

        # The client asks for a new size; the application then draws at it.
        page.set_viewport_size({'width': 600, 'height': 420})
        page.wait_for_function(r'''
            before => {
                const found = /SIZE (\d+) (\d+)/.exec(document.body.innerText);
                return found && Number(found[1]) < before[0] && Number(found[2]) < before[1];
            }''', arg=list(first), timeout=15000)
        smaller = size()
        assert smaller[0] > 0 and smaller[1] > 0
        page.keyboard.type('z')
        wait_for_text(page, 'TYPED abbaz')
        assert dialogs == []


def test_cf635_draws_text_and_cursor_and_reports_six_buttons():
    with encoding_state():
        velnora.set_encoding('ascii')
        peer = DisplayPeer()
        try:
            screen = CF635Screen(peer.path)
            assert screen.get_cols_rows() == (20, 4)

            def draw(widget, focus=False):
                canvas = velnora.Filler(widget, valign='top').render((20, 4), focus)
                screen.draw_screen((20, 4), canvas)
                assert settle(peer, screen) == []
                assert peer.rejected == []
                return canvas

            def labels(lines):
                return velnora.Pile([velnora.Text(line.rstrip()) for line in lines])

            first = ['first row of text   ', 'second              ',
                     '                    ', 'FOURTH ROW IS FULL!!']
            draw(labels(first))
            assert peer.lines() == first
            assert peer.visible_cursor() is None

            # A later frame changes one row and leaves the others displayed.
            changed = [first[0], 'CHANGED             ', first[2], first[3]]
            draw(labels(changed))
            assert peer.lines() == changed

            # The cursor follows the canvas, and goes away with it.
            for position, expected in ((3, (6, 1)), (7, (10, 1))):
                editor = velnora.Edit('ab ', 'field text', edit_pos=position)
                canvas = draw(velnora.Pile([velnora.Text('caption'), editor]), focus=True)
                assert canvas_snapshot(canvas)['cursor'] == expected
                assert peer.lines()[:2] == ['caption             ', 'ab field text       ']
                assert peer.visible_cursor() == expected
            draw(velnora.Pile([velnora.Text('caption'), velnora.Edit('ab ', 'field text')]))
            assert peer.visible_cursor() is None

            # Color and hyperlink attributes never reach the character screen.
            styled = velnora.AttrSpec('dark red,bold', 'dark blue', hyperlink='https://example.org/')
            baseline = peer.commands
            draw(velnora.Pile([velnora.Text('Plain words here'),
                             velnora.Text([(styled, 'Styled'), ' words here'])]))
            assert peer.commands > baseline
            assert peer.lines()[:2] == ['Plain words here    ', 'Styled words here   ']

            # Each button maps to its own key once per press, never on release.
            names = {1: 'up', 2: 'down', 3: 'left', 4: 'right', 5: 'enter', 6: 'esc'}
            for code in (3, 1, 6, 2, 5, 4, 4):
                peer.report_key(code, code + 6)
                assert settle(peer, screen) == [names[code]], code
            peer.report_key(1, 7, 3, 9, 1, 7)
            assert settle(peer, screen) == ['up', 'left', 'up']
        finally:
            peer.close()


def test_cf635_waits_for_each_device_acknowledgement():
    peer = DisplayPeer(auto_ack=False)
    try:
        screen = CF635Screen(peer.path)
        canvas = velnora.Filler(velnora.Text('ACK controlled drawing'), valign='top').render((20, 4))
        screen.draw_screen((20, 4), canvas)
        def observe_until(predicate):
            limit = time.monotonic() + 5
            while not predicate():
                assert time.monotonic() < limit, 'Expected serial command was not received'
                peer.service()
                screen.get_input_nonblocking()
                time.sleep(0.001)
        observe_until(lambda: peer.commands >= 1)
        assert peer.commands == 1
        # Poll through the public entry while the device withholds its response.
        limit = time.monotonic() + 0.1
        while time.monotonic() < limit:
            peer.service()
            screen.get_input_nonblocking()
            assert peer.commands == 1, 'A second command arrived before device acknowledgement'
            time.sleep(0.001)
        peer.acknowledge()
        observe_until(lambda: peer.commands >= 2)
        assert peer.commands == 2
        assert peer.rejected == []
        peer.auto_ack = True
        peer.acknowledge()
        settle(peer, screen)
        assert peer.lines() == [row.decode('ascii') for row in canvas.text]
    finally:
        peer.close()
