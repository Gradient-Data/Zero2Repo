# feature: F09
"""Container scenarios using real application widgets and public interfaces."""
import velnora
from F02_helpers import ActionRow


def sequential_containers():
    """Yield fresh containers, viewport sizes and their selectable endpoints."""
    for kind in ('columns', 'pile', 'grid', 'list', 'frame'):
        children = [ActionRow(), velnora.Text('-'), velnora.WidgetDisable(ActionRow()), ActionRow()]
        if kind == 'columns':
            yield velnora.Columns(children), (40,), 0, 3
        elif kind == 'pile':
            yield velnora.Pile(children), (10,), 0, 3
        elif kind == 'grid':
            yield velnora.GridFlow(children, 8, 1, 0, 'left'), (26,), 0, 3
        elif kind == 'list':
            yield velnora.ListBox(velnora.SimpleFocusListWalker(children)), (10, 6), 0, 3
        else:
            yield velnora.Frame(velnora.Filler(children[2]), header=children[0],
                              footer=children[3], focus_part='header'), (10, 6), 'header', 'footer'
