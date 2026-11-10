# feature: F04
"""Acceptance of freshness, retention and coherent stored byte reads."""
import time

import pytest
from velnora.abc.store import RangeByteRequest, OffsetByteRequest, SuffixByteRequest
from velnora.experimental.cache_store import CacheStore
from velnora.storage import ZipStore

from _helpers import invoke
from F03_helpers import put_bytes, read_bytes
from F04_helpers import cached_source


def test_f04_t01(tmp_path):
    with cached_source(tmp_path / 'source.sqlite') as (source, cached):
        for key, payload in [('one', b'first\x00\xff'), ('two', b'another payload')]:
            put_bytes(source, key, payload)
            source.reads.clear()
            assert read_bytes(cached, key) == payload
            assert source.reads
            source.reads.clear()
            put_bytes(source, key, b'changed externally')
            assert read_bytes(cached, key) == payload
            assert source.reads == []
        archive = invoke(ZipStore.open, tmp_path / 'reuse.zip', call_kwargs={'mode': 'w'}).value
        try:
            put_bytes(archive, 'live', b'archive works')
            assert read_bytes(archive, 'live') == b'archive works'
            with pytest.raises(ValueError):
                CacheStore(source, cache_store=archive)
        finally:
            archive.close()


def test_f04_t02(tmp_path):
    # Real elapsed time, away from the expiry boundary; a hit must not renew age.
    # Separate keys isolate full and range freshness without prescribing how a
    # cache uses a fresh complete value to answer intervals of the same key.
    # Hits after 20s must not extend the 30s insertion age. The later observation
    # is after 32.5s and before 45s, well before a sliding age could expire.
    with cached_source(tmp_path / 'finite.sqlite', max_age_seconds=30) as (source, cached), \
            cached_source(tmp_path / 'default.sqlite') as (default_source, default_cached):
        put_bytes(source, 'whole', b'old bytes')
        put_bytes(source, 'range', b'old bytes')
        put_bytes(default_source, 'whole', b'old bytes')
        put_bytes(default_source, 'range', b'old bytes')
        window = RangeByteRequest(0, 3)
        admitted = time.monotonic()
        assert read_bytes(default_cached, 'whole') == b'old bytes'
        assert read_bytes(default_cached, 'range', window) == b'old'
        assert read_bytes(cached, 'whole') == b'old bytes'
        assert read_bytes(cached, 'range', window) == b'old'
        started = time.monotonic()
        put_bytes(source, 'whole', b'new bytes')
        put_bytes(source, 'range', b'new bytes')
        put_bytes(default_source, 'whole', b'new bytes')
        put_bytes(default_source, 'range', b'new bytes')
        time.sleep(20)
        source.reads.clear()
        assert read_bytes(cached, 'whole') == b'old bytes'
        assert read_bytes(cached, 'range', window) == b'old'
        assert time.monotonic() - admitted < 28, 'Environment missed the unexpired observation window'
        assert source.reads == []
        # Observe after insertion age expires, but before a sliding hit age would.
        time.sleep(max(0, 32.5 - (time.monotonic() - started)))
        assert time.monotonic() - started < 45, 'Environment missed the sliding-age observation window'
        assert read_bytes(cached, 'whole') == b'new bytes'
        assert source.reads
        source.reads.clear()
        assert read_bytes(cached, 'range', window) == b'new'
        assert source.reads
        source.reads.clear()
        assert read_bytes(cached, 'whole') == b'new bytes'
        assert read_bytes(cached, 'range', window) == b'new'
        assert source.reads == []
        default_source.reads.clear()
        assert read_bytes(default_cached, 'whole') == b'old bytes'
        assert read_bytes(default_cached, 'range', window) == b'old'
        assert default_source.reads == []


def test_f04_t03(tmp_path):
    with cached_source(tmp_path / 'budget.sqlite', max_size=8) as (source, cached):
        put_bytes(source, 'whole', b'fullbyte')
        assert read_bytes(cached, 'whole') == b'fullbyte'
        source.reads.clear()
        assert read_bytes(cached, 'whole') == b'fullbyte'
        assert source.reads == []
        put_bytes(source, 'item', b'0123456789abcdef')
        small = RangeByteRequest(2, 7)
        assert read_bytes(cached, 'item', small) == b'23456'
        source.reads.clear()
        assert read_bytes(cached, 'item', small) == b'23456'
        assert source.reads == []
        large = RangeByteRequest(1, 12)
        for _ in range(2):
            source.reads.clear()
            assert read_bytes(cached, 'item', large) == b'123456789ab'
            assert source.reads
        # Exact-budget ranges are retainable, unlike oversized ranges.
        exact = RangeByteRequest(8, 16)
        assert read_bytes(cached, 'item', exact) == b'89abcdef'
        source.reads.clear()
        assert read_bytes(cached, 'item', exact) == b'89abcdef'
        assert source.reads == []

    # Remove source values only after all admissions. Probing an evicted entry
    # then returns absence instead of admitting data and evicting another entry.
    # Count payload bytes independently, without choosing an eviction order.
    admissions = [
        ('full-a', b'whole', None, b'whole'),
        ('range-a', b'0123456789', RangeByteRequest(2, 6), b'2345'),
        ('full-b', b'abcdef', None, b'abcdef'),
        ('range-b', b'abcdefghij', RangeByteRequest(3, 8), b'defgh'),
    ]
    with cached_source(tmp_path / 'joint.sqlite', max_size=8) as (source, cached):
        for key, payload, _, _ in admissions:
            put_bytes(source, key, payload)
        for key, _, request, expected in admissions:
            assert read_bytes(cached, key, request) == expected
        for key, _, _, _ in admissions:
            invoke(source.delete, key)
        retained_bytes = 0
        for key, _, request, expected in admissions:
            actual = read_bytes(cached, key, request)
            assert actual is None or actual == expected
            if actual is not None:
                retained_bytes += len(actual)
        assert retained_bytes <= 8, 'Full and range values exceeded their joint byte budget'

    # Read A, B, touch A, then admit C. Only B may lose reuse eligibility.
    # Probe both retained results before the evicted result, so the miss cannot
    # re-admit bytes and change later probes. The source remains unchanged.
    # The mixed orders distinguish one joint LRU from separate full/range pools;
    # the range-only sequence distinguishes intervals of the same source key.
    whole = [('a', b'AAAA', None, b'AAAA'),
             ('b', b'BBBB', None, b'BBBB'),
             ('c', b'CCCC', None, b'CCCC')]
    ranges = [('shared', b'AAAABBBBCCCC', RangeByteRequest(i, i + 4), expected)
              for i, expected in ((0, b'AAAA'), (4, b'BBBB'), (8, b'CCCC'))]
    for number, entries in enumerate((whole, ranges,
                                     [whole[0], ranges[1], whole[2]],
                                     [ranges[0], whole[1], ranges[2]])):
        with cached_source(tmp_path / f'lru-{number}.sqlite', max_size=8) as (source, cached):
            for key, payload, _, _ in entries:
                put_bytes(source, key, payload)
            for index in (0, 1, 0, 2):
                key, _, request, expected = entries[index]
                assert read_bytes(cached, key, request) == expected
            for index in (0, 2, 1):
                key, _, request, expected = entries[index]
                source.reads.clear()
                assert read_bytes(cached, key, request) == expected
                if index == 1:
                    assert source.reads
                else:
                    assert source.reads == []


def test_f04_t04(tmp_path):
    for mode in ('default', 'removed'):
        options = {} if mode == 'default' else {'max_size': 4}
        with cached_source(tmp_path / (mode + '.sqlite'), **options) as (source, cached):
            if mode == 'removed':
                cached.max_size = None
            values = {'first': b'first-long-payload', 'second': b'other\x00payload'}
            for key, payload in values.items():
                put_bytes(source, key, payload)
                assert read_bytes(cached, key) == payload
            request = RangeByteRequest(1, 6)
            assert read_bytes(cached, 'first', request) == b'irst-'
            source.reads.clear()
            for key, payload in values.items():
                assert read_bytes(cached, key) == payload
            assert read_bytes(cached, 'first', request) == b'irst-'
            assert source.reads == []
            invoke(cached.clear_cache)
            for key, payload in values.items():
                assert read_bytes(source, key) == payload
            for key, payload in values.items():
                source.reads.clear()
                assert read_bytes(cached, key) == payload
                assert source.reads
            # Clear again to observe range refresh independently of a full read.
            invoke(cached.clear_cache)
            source.reads.clear()
            assert read_bytes(cached, 'first', request) == b'irst-'
            assert source.reads


def test_f04_t05(tmp_path):
    for mode in ('default', 'disabled'):
        options = {} if mode == 'default' else {'cache_set_data': False}
        with cached_source(tmp_path / (mode + '.sqlite'), **options) as (source, cached):
            put_bytes(source, 'key', b'old-value-123')
            assert read_bytes(cached, 'key') == b'old-value-123'
            requests = [(RangeByteRequest(0, 3), b'old', b'NEW'),
                        (SuffixByteRequest(3), b'123', b'987')]
            for request, old, _ in requests:
                assert read_bytes(cached, 'key', request) == old
            put_bytes(cached, 'key', b'NEW-value-987')
            assert read_bytes(source, 'key') == b'NEW-value-987'
            source.reads.clear()
            assert read_bytes(cached, 'key') == b'NEW-value-987'
            if mode == 'default':
                assert source.reads == []
            else:
                assert source.reads
            for request, _, new in requests:
                assert read_bytes(cached, 'key', request) == new
            invoke(cached.delete, 'key')
            assert read_bytes(source, 'key') is None
            assert read_bytes(cached, 'key') is None
            for request, _, _ in requests:
                assert read_bytes(cached, 'key', request) is None


def test_f04_t06(tmp_path):
    with cached_source(tmp_path / 'ranges.sqlite') as (source, cached):
        put_bytes(source, 'item', b'0123456789abcdef')
        requests = [(RangeByteRequest(2, 6), b'2345'),
                    (RangeByteRequest(9, 14), b'9abcd'),
                    (OffsetByteRequest(11), b'bcdef'),
                    (SuffixByteRequest(3), b'def'), (None, b'0123456789abcdef')]
        for request, expected in requests + requests[::-1]:
            assert read_bytes(cached, 'item', request) == expected
        put_bytes(cached, 'writable', b'write baseline')
        assert read_bytes(source, 'writable') == b'write baseline'
        readonly = cached.with_read_only(True)
        try:
            for request, expected in requests:
                assert read_bytes(readonly, 'item', request) == expected
            for entry, args in [(put_bytes, (readonly, 'item', b'bad')),
                                (put_bytes, (readonly, 'new', b'bad')),
                                (readonly.delete, ('item',))]:
                with pytest.raises(ValueError):
                    invoke(entry, *args)
                assert read_bytes(source, 'item') == b'0123456789abcdef'
                assert read_bytes(source, 'new') is None
                assert read_bytes(cached, 'item') == b'0123456789abcdef'
        finally:
            readonly.close()
