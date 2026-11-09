# feature: F04
"""Real source access logging, reusing the existing durable adapter."""
from contextlib import contextmanager

from F03_helpers import SQLiteStore
from velnora.storage import MemoryStore
from velnora.experimental.cache_store import CacheStore


class ObservedSQLiteStore(SQLiteStore):
    """Record actual get calls while returning the real SQL-backed bytes."""

    def __init__(self, path, **options):
        super().__init__(path, **options)
        self.reads = []

    async def get(self, key, prototype, byte_range=None):
        self.reads.append((key, byte_range))
        return await super().get(key, prototype, byte_range)


@contextmanager
def cached_source(path, **options):
    source = ObservedSQLiteStore(path)
    reuse = MemoryStore()
    try:
        yield source, CacheStore(source, cache_store=reuse, **options)
    finally:
        reuse.close()
        source.close()
