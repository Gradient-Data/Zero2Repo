# feature: F12
"""Application content providers for list and tree acceptance scenarios."""
import velnora
from _helpers import canvas_snapshot


class TokenRows(velnora.ListWalker):
    """Supply rows on demand, without a sequence or a required total length."""
    # An open-ended provider has no end, so a list may request only the rows that
    # display and focus movement reach; the scenarios reach a few hundred at most.
    # A request beyond REACH is recorded and answered as the end of the rows, so an
    # eager walk fails the scenario instead of running forever.
    REACH = 1000

    def __init__(self, stop=None):
        self.stop = stop
        self.focus = ('entry', 0)
        self.widgets = {}
        self.overreach = None

    def _beyond(self, number):
        if self.stop is None and number > self.REACH:
            if self.overreach is None:
                self.overreach = ('entry', number)
            return True
        return False

    def row(self, position):
        kind, number = position
        if (kind != 'entry' or number < 0 or (self.stop is not None and number >= self.stop)
                or self._beyond(number)):
            raise IndexError(position)
        if position not in self.widgets:
            self.widgets[position] = velnora.Edit('', f'item {number}', edit_pos=0)
        return self.widgets[position], position

    def get_focus(self):
        return self.row(self.focus)

    def set_focus(self, position):
        self.row(position)
        self.focus = position
        self._modified()

    def get_next(self, position):
        number = position[1] + 1
        if (self.stop is not None and number >= self.stop) or self._beyond(number):
            return None, None
        return self.row(('entry', number))

    def get_prev(self, position):
        if position[1] == 0:
            return None, None
        return self.row(('entry', position[1] - 1))


class EstimatedTokenRows(TokenRows):
    """Finite application provider exposing an estimate instead of len()."""
    def __length_hint__(self):
        return self.stop


class LabelTreeWidget(velnora.TreeWidget):
    """Use application-chosen labels, indentation and indicator glyphs."""
    indent_cols = 2
    expanded_icon = velnora.SelectableIcon('v', 0)
    unexpanded_icon = velnora.SelectableIcon('>', 0)

    def get_display_text(self):
        return self.get_node().get_value()[0]

    def is_initially_expanded(self):
        return super().is_initially_expanded() if self.get_node().get_value()[2] else False


class LabelLeaf(velnora.TreeNode):
    def load_widget(self):
        return LabelTreeWidget(self)


class LabelParent(velnora.ParentNode):
    def load_widget(self):
        return LabelTreeWidget(self)

    def load_child_keys(self):
        return list(range(len(self.get_value()[1])))

    def load_child_node(self, key):
        value = self.get_value()[1][key]
        cls = LabelParent if value[1] else LabelLeaf
        return cls(value, parent=self, key=key)


def browsing_tree():
    """Return an application hierarchy with multiple sibling and depth levels."""
    return LabelParent(('root', [
        ('alpha', [('a-leaf', [], True)], True),
        ('omega', [('inner', [('deep-one', [], True), ('deep-two', [], True)], True),
                   ('hidden', [('secret', [('bottom', [], True)], True)], False)], True),
    ], True), key='root')


def assert_tree_row(row, node, width=32):
    """Check hierarchy and labels without choosing icon-to-label spacing."""
    assert len(row) == width
    text = row.decode('utf-8')
    prefix = ' ' * (2 * node.get_depth())
    label = node.get_value()[0]
    if isinstance(node, velnora.ParentNode):
        prefix += 'v' if node.get_widget().expanded else '>'
        assert text.startswith(prefix), text
        assert text[len(prefix):].lstrip(' ').rstrip(' ') == label, text
    else:
        assert text == (prefix + label).ljust(width), text


def assert_tree_rows(box, nodes, width=32):
    """Check all visible nodes, their order and the blank viewport remainder."""
    observed = canvas_snapshot(box.render((width, len(nodes) + 2)))
    assert (observed['cols'], observed['rows']) == (width, len(nodes) + 2)
    assert len(observed['text']) == len(nodes) + 2
    for row, node in zip(observed['text'], nodes):
        assert_tree_row(row, node, width)
    assert observed['text'][len(nodes):] == (b' ' * width,) * 2


def assert_focused_row(box, size, label):
    """Check the focused child's actual text and cursor inside the viewport."""
    observed = canvas_snapshot(box.render(size, focus=True))
    assert (observed['cols'], observed['rows']) == size
    assert observed['cursor'] is not None
    x, y = observed['cursor']
    assert 0 <= x < size[0] and 0 <= y < size[1]
    assert observed['text'][y] == label.encode().ljust(size[0], b' ')
    return observed


class CyclicRows(velnora.ListWalker):
    """Application provider with finite repeating positions and no sequence API."""
    def __init__(self, widgets):
        self.widgets = widgets
        self.position = 0

    def get_focus(self):
        return self.widgets[self.position], self.position

    def set_focus(self, position):
        self.position = position
        self._modified()

    def get_next(self, position):
        following = (position + 1) % len(self.widgets)
        return self.widgets[following], following

    def get_prev(self, position):
        previous = (position - 1) % len(self.widgets)
        return self.widgets[previous], previous
