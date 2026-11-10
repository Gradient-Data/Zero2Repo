# feature: F11
"""Observe choice notifications through public callbacks and state inspection."""
import velnora


class ChoiceObserver:
    """Record signal payloads together with the state visible inside each callback."""

    def __init__(self, *widgets):
        self.events = []
        for widget in widgets:
            velnora.connect_signal(widget, 'change', self.before)
            velnora.connect_signal(widget, 'postchange', self.after)

    def before(self, source, proposed):
        self.events.append((source, 'before', proposed, source.get_state()))

    def after(self, source, previous):
        self.events.append((source, 'after', previous, source.get_state()))
