# feature: F00
"""HTTP server handling for clients that deliberately stop reading a response."""
import warnings


class ClientDisconnects:
    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError) as error:
            # Range and metadata readers may close a response before its end.
            warnings.warn(f"HTTP client disconnected: {error!r}", RuntimeWarning)
