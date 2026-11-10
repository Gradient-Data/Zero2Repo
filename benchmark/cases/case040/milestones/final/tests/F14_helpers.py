# feature: F14
"""Application launchers shared by overlay and selection scenarios."""
import velnora


class PopUpKeys(velnora.WidgetWrap):
    """Application dialog binding Escape to its owner's close operation."""

    def __init__(self, body, close):
        super().__init__(body)
        self.close = close

    def keypress(self, size, key):
        if key == 'esc':
            self.close()
            return None
        return super().keypress(size, key)


class ApplicationLauncher(velnora.PopUpLauncher):
    """A real application launcher with caller-supplied content and geometry."""

    def __init__(self, body, pop_up, parameters):
        super().__init__(body)
        self.dialog = pop_up
        self.parameters = dict(parameters)

    def create_pop_up(self):
        return PopUpKeys(self.dialog, self.close_pop_up)

    def get_pop_up_parameters(self):
        return dict(self.parameters)

    def keypress(self, size, key):
        if key == 'f2':
            self.open_pop_up()
            return None
        return super().keypress(size, key)


def located_launcher(launcher, column, row):
    """Place a flow launcher at a caller-selected visible screen position."""
    padded = velnora.Padding(launcher, align='left', width=1, left=column)
    children = [velnora.Text('')] * row + [padded]
    return velnora.Filler(velnora.Pile(children), valign='top')
