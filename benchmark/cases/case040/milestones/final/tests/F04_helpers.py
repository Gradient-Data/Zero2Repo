# feature: F04
"""Application-owned signal sources and weak-referenceable context."""
import velnora


class SignalContext:
    """Ordinary application context with no product or recording references."""


def signal_source(*names):
    """Return a fresh source of a fresh class declaring names (default: changed and saved)."""
    class Source:
        pass

    velnora.register_signal(Source, list(names) or ['changed', 'saved'])
    return Source()
