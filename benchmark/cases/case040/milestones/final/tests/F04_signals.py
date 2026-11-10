# feature: F04
"""Acceptance tests for notification delivery and connection lifetime."""
import gc
import weakref

import pytest
import velnora

from _helpers import CallbackRecorder
from F04_helpers import SignalContext, signal_source


def test_delivery_context_handling_and_failures():
    source = signal_source()
    assert velnora.emit_signal(source, 'changed', 'empty') is False
    calls = []

    def listener(*args):
        calls.append(args)
        return args[0]

    # Context precedes event data; legacy context follows it.
    velnora.connect_signal(source, 'changed', listener, user_args=[False, 'first'])
    velnora.connect_signal(source, 'changed', listener, 'tail', user_args=[None, 'second'])
    assert velnora.emit_signal(source, 'changed', 'draft', 3) is False
    assert calls == [(False, 'first', 'draft', 3), (None, 'second', 'draft', 3, 'tail')]
    calls.clear()
    velnora.connect_signal(source, 'changed', listener, user_args=[True, 'third'])
    velnora.connect_signal(source, 'changed', listener, user_args=[False, 'fourth'])
    assert velnora.emit_signal(source, 'changed', 'ready', 7) is True
    assert calls == [(False, 'first', 'ready', 7), (None, 'second', 'ready', 7, 'tail'),
                     (True, 'third', 'ready', 7), (False, 'fourth', 'ready', 7)]
    other = CallbackRecorder(return_value=True)
    velnora.connect_signal(source, 'saved', other)
    assert velnora.emit_signal(source, 'saved', 'file') is True
    assert other.calls == [(('file',), {})]
    with pytest.raises(NameError):
        velnora.connect_signal(source, 'undeclared', other)

    class ListenerFailure(Exception):
        pass

    def fail(*args):
        raise ListenerFailure('Application listener failed')

    velnora.connect_signal(source, 'changed', fail)
    with pytest.raises(ListenerFailure):
        velnora.emit_signal(source, 'changed', 'failure', 9)

    # An empty result is not affirmative; a falsy legacy context is still supplied context.
    source = signal_source()
    results = CallbackRecorder(return_value=[])
    velnora.connect_signal(source, 'changed', results, 0)
    assert velnora.emit_signal(source, 'changed', 'event') is False
    assert results.calls == [(('event', 0), {})]
    # One-shot iterables supply the same context for each emission.
    context = SignalContext()
    repeated = CallbackRecorder()
    velnora.connect_signal(source, 'saved', repeated, weak_args=iter([context]), user_args=iter(['user']))
    velnora.emit_signal(source, 'saved', 1)
    velnora.emit_signal(source, 'saved', 2)
    assert repeated.calls == [((context, 'user', 1), {}), ((context, 'user', 2), {})]

    # Notifications are per source: instances of a class do not share listeners, and a
    # declaration belongs to its class. A refused connection leaves delivery untouched.
    source_class = type(source)
    first, second = source_class(), source_class()
    on_first, on_second = CallbackRecorder(return_value=True), CallbackRecorder(return_value=True)
    velnora.connect_signal(first, 'changed', on_first)
    assert velnora.emit_signal(second, 'changed', 'other') is False
    assert on_first.calls == []
    velnora.connect_signal(second, 'changed', on_second)
    assert velnora.emit_signal(first, 'changed', 'mine') is True
    assert on_first.calls == [(('mine',), {})] and on_second.calls == []
    foreign = signal_source('changed', 'closed')
    velnora.connect_signal(foreign, 'closed', CallbackRecorder())
    with pytest.raises(NameError):
        velnora.connect_signal(first, 'closed', on_second)
    undeclared_class = type('Undeclared', (), {})
    with pytest.raises(NameError):
        velnora.connect_signal(undeclared_class(), 'changed', on_second)
    assert velnora.emit_signal(first, 'closed') is False
    assert on_second.calls == []


def test_disconnect_identity_matching_and_absent():
    source = signal_source()
    callback = CallbackRecorder(return_value=True)
    survivor = CallbackRecorder(return_value=False)
    context = SignalContext()
    first = velnora.connect_signal(source, 'changed', callback, user_args=['first'])
    velnora.connect_signal(source, 'changed', callback, 'tail',
                         weak_args=[context], user_args=['second'])
    velnora.connect_signal(source, 'changed', survivor)
    velnora.connect_signal(source, 'saved', callback, user_args=['other'])
    velnora.disconnect_signal(source, 'changed', callback, 'tail',
                            weak_args=[context], user_args=['unmatched'])
    # Each registration field matters: none of these match, nor does another notification or source.
    unrelated = SignalContext()
    for arguments, options in [(('other tail',), dict(weak_args=[context], user_args=['second'])),
                               ((), dict(weak_args=[context], user_args=['second'])),
                               (('tail',), dict(weak_args=[unrelated], user_args=['second'])),
                               (('tail',), dict(user_args=['second']))]:
        velnora.disconnect_signal(source, 'changed', callback, *arguments, **options)
    velnora.disconnect_signal(source, 'changed', CallbackRecorder(), 'tail',
                            weak_args=[context], user_args=['second'])
    velnora.disconnect_signal(source, 'saved', callback, user_args=['first'])
    velnora.disconnect_signal_by_key(source, 'saved', first)
    untouched = signal_source()
    velnora.disconnect_signal(untouched, 'changed', callback)
    velnora.disconnect_signal_by_key(untouched, 'changed', first)
    assert velnora.emit_signal(untouched, 'changed', 0) is False
    assert velnora.emit_signal(source, 'changed', 1) is True
    assert callback.calls == [(('first', 1), {}), ((context, 'second', 1, 'tail'), {})]
    assert survivor.calls == [((1,), {})]
    callback.calls.clear()
    survivor.calls.clear()
    velnora.disconnect_signal_by_key(source, 'changed', first)
    velnora.disconnect_signal_by_key(source, 'changed', first)
    assert velnora.emit_signal(source, 'changed', 2) is True
    assert callback.calls == [((context, 'second', 2, 'tail'), {})]
    assert survivor.calls == [((2,), {})]
    callback.calls.clear()
    survivor.calls.clear()
    velnora.disconnect_signal(source, 'changed', callback, 'tail',
                            weak_args=[context], user_args=['second'])
    velnora.disconnect_signal(source, 'changed', callback, 'tail',
                            weak_args=[context], user_args=['second'])
    assert velnora.emit_signal(source, 'changed', 3) is False
    assert callback.calls == []
    assert survivor.calls == [((3,), {})]
    assert velnora.emit_signal(source, 'saved', 4) is True
    assert callback.calls == [(('other', 4), {})]

    # Identical registrations are distinct connections, each with its own identity.
    source = signal_source()
    twin = CallbackRecorder()
    twin_first = velnora.connect_signal(source, 'changed', twin, user_args=['same'])
    twin_second = velnora.connect_signal(source, 'changed', twin, user_args=['same'])
    velnora.emit_signal(source, 'changed', 1)
    assert len(twin.calls) == 2
    twin.calls.clear()
    velnora.disconnect_signal_by_key(source, 'changed', twin_first)
    velnora.emit_signal(source, 'changed', 2)
    assert twin.calls == [(('same', 2), {})]
    twin.calls.clear()
    velnora.disconnect_signal_by_key(source, 'changed', twin_second)
    velnora.emit_signal(source, 'changed', 3)
    assert twin.calls == []


def test_weak_context_lifetime_and_delivery():
    source = signal_source()
    first, second = SignalContext(), SignalContext()
    first_ref, second_ref = weakref.ref(first), weakref.ref(second)
    callback = CallbackRecorder(return_value=True)
    survivor = CallbackRecorder(return_value=False)
    velnora.connect_signal(source, 'changed', callback, 'tail',
                         weak_args=[first, second], user_args=['context'])
    velnora.connect_signal(source, 'changed', survivor)
    assert velnora.emit_signal(source, 'changed', 'before') is True
    assert callback.calls == [((first, second, 'context', 'before', 'tail'), {})]
    assert survivor.calls == [(('before',), {})]
    # Recorded arguments are application references too: release them first.
    callback.calls.clear()
    survivor.calls.clear()
    del second
    gc.collect()
    assert second_ref() is None
    assert first_ref() is first
    assert velnora.emit_signal(source, 'changed', 'after') is False
    assert callback.calls == []
    assert survivor.calls == [(('after',), {})]
    del first
    gc.collect()
    assert first_ref() is None
    # A single context can back several connections: all of them stop together, on every
    # notification, and removing an expired connection afterwards has no effect.
    source = signal_source()
    shared = SignalContext()
    shared_ref = weakref.ref(shared)
    changed, saved = CallbackRecorder(return_value=True), CallbackRecorder(return_value=True)
    expired_key = velnora.connect_signal(source, 'changed', changed, weak_args=[shared])
    velnora.connect_signal(source, 'changed', changed, weak_args=[shared], user_args=['again'])
    velnora.connect_signal(source, 'saved', saved, weak_args=[shared])
    assert velnora.emit_signal(source, 'changed', 1) is True
    assert velnora.emit_signal(source, 'saved', 1) is True
    changed.calls.clear()
    saved.calls.clear()
    del shared
    gc.collect()
    assert shared_ref() is None
    velnora.disconnect_signal_by_key(source, 'changed', expired_key)
    assert velnora.emit_signal(source, 'changed', 2) is False
    assert velnora.emit_signal(source, 'saved', 2) is False
    assert changed.calls == [] and saved.calls == []


def test_changes_during_delivery_and_expired_context():
    source = signal_source()
    calls = []

    def added(event):
        calls.append(('added', event))
        return True

    def removed(event):
        calls.append(('removed', event))
        return True

    def change(event):
        calls.append(('change', event))
        velnora.disconnect_signal(source, 'changed', change)
        velnora.disconnect_signal_by_key(source, 'changed', removed_key)
        velnora.connect_signal(source, 'changed', added)
        return False

    def survivor(event):
        calls.append(('survivor', event))
        return False

    velnora.connect_signal(source, 'changed', change)
    removed_key = velnora.connect_signal(source, 'changed', removed)
    velnora.connect_signal(source, 'changed', survivor)
    assert velnora.emit_signal(source, 'changed', 1) is True
    assert calls == [('change', 1), ('removed', 1), ('survivor', 1)]
    calls.clear()
    assert velnora.emit_signal(source, 'changed', 2) is True
    assert calls == [('survivor', 2), ('added', 2)]

    # An emission started from inside a listener is a subsequent emission: it sees the changes
    # already made, while the outer emission finishes with the registrations it started with.
    source = signal_source()
    calls = []
    inner_results = []

    def later(event):
        calls.append(('later', event))
        return False

    def joined(event):
        calls.append(('joined', event))
        return False

    def on_saved(event):
        calls.append(('saved', event))
        return True

    def reentrant(event):
        calls.append(('reentrant', event))
        if event == 'outer':
            velnora.disconnect_signal_by_key(source, 'changed', later_key)
            velnora.connect_signal(source, 'changed', joined)
            velnora.connect_signal(source, 'saved', on_saved)
            inner_results.append(velnora.emit_signal(source, 'saved', 'nested saved'))
            inner_results.append(velnora.emit_signal(source, 'changed', 'inner'))
        return False

    velnora.connect_signal(source, 'changed', reentrant)
    later_key = velnora.connect_signal(source, 'changed', later)
    assert velnora.emit_signal(source, 'changed', 'outer') is False
    assert inner_results == [True, False]
    assert calls == [('reentrant', 'outer'), ('saved', 'nested saved'),
                     ('reentrant', 'inner'), ('joined', 'inner'), ('later', 'outer')]

    # Establish live delivery, then expire context in an earlier listener.
    source = signal_source()
    holder = [SignalContext()]
    context_ref = weakref.ref(holder[0])
    weak_listener = CallbackRecorder(return_value=True)
    remaining = CallbackRecorder(return_value=False)
    released = []

    def release(expire):
        released.append(expire)
        if expire:
            holder.clear()
            gc.collect()
        return False

    velnora.connect_signal(source, 'changed', release)
    velnora.connect_signal(source, 'changed', weak_listener, weak_args=holder)
    velnora.connect_signal(source, 'changed', remaining)
    assert velnora.emit_signal(source, 'changed', False) is True
    assert weak_listener.calls == [((holder[0], False), {})]
    assert remaining.calls == [((False,), {})]
    weak_listener.calls.clear()
    remaining.calls.clear()
    assert velnora.emit_signal(source, 'changed', True) is False
    assert context_ref() is None
    assert weak_listener.calls == []
    assert remaining.calls == [((True,), {})]
    remaining.calls.clear()
    assert velnora.emit_signal(source, 'changed', True) is False
    assert weak_listener.calls == []
    assert remaining.calls == [((True,), {})]
    assert released == [False, True, True]
