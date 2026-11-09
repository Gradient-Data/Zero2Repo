# feature: F13
"""Real SQL storage with caller-controlled metadata access and capability."""
from F03_helpers import SQLiteStore


class MetadataAccessStore(SQLiteStore):
    """Keep real bytes while refusing descendant document reads when sealed."""
    def __init__(self, path, *, read_only=False, supports_deletes=True, policy=None):
        super().__init__(path, read_only=read_only, supports_deletes=supports_deletes)
        self.policy = {'supports': True, 'blocked': False} if policy is None else policy

    @property
    def supports_consolidated_metadata(self):
        return self.policy['supports']

    @supports_consolidated_metadata.setter
    def supports_consolidated_metadata(self, value):
        self.policy['supports'] = value

    @property
    def block_descendant_metadata(self):
        return self.policy['blocked']

    @block_descendant_metadata.setter
    def block_descendant_metadata(self, value):
        self.policy['blocked'] = value

    def with_read_only(self, read_only=False):
        return type(self)(self.path, read_only=read_only,
                          supports_deletes=self.supports_deletes, policy=self.policy)

    async def get(self, key, prototype, byte_range=None):
        if (self.block_descendant_metadata and '/' in key
                and key.rsplit('/', 1)[-1] in {'.zattrs', '.zarray', '.zgroup', 'zarr.json', '.zmetadata'}):
            raise AssertionError('Descendant metadata access is disabled: ' + key)
        return await super().get(key, prototype, byte_range)
