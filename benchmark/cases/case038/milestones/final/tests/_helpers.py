# feature: F00
"""Shared public-call machinery, without feature expectations.

Pass public package exports (or documented public entry points) as factories
and callables. No product is loaded from a repository path. Use ``observe``
around the entire operation, including construction and parsing, when failure
timing is intentionally unspecified. In-process observations have no exit
status: success is represented by ``error is None``. Only explicitly nominated
exception classes are recorded; every other failure propagates.

The deadline requires a POSIX main thread with no active real-time alarm.
It covers construction, evaluation and complete iterator consumption together.
Feature-specific resources and expected outcomes belong in feature helpers.
"""

import contextlib as _contextlib
import dataclasses as _dataclasses
import io as _io
import json as _json
import math as _math
import signal as _signal
import threading as _threading
import xml.etree.ElementTree as _ET


__all__ = [
    "Observation", "SourceRecord", "observe", "make_parser", "make_context",
    "evaluate_expression", "result_items", "read_json", "read_xml",
]


@_dataclasses.dataclass(frozen=True)
class Observation:
    """Return carrier for one in-process call, with no process exit status.

    ``value`` is the unmodified return value, or a fully consumed list when
    iteration was requested. On a nominated exception it is None and ``error``
    is the original exception, including its public code/message attributes
    and traceback. Partial iterator results are never returned as success.
    ``stdout`` and ``stderr`` are captured Python text streams. Unknown errors
    and machinery failures raise instead of producing this carrier.
    """

    value: object
    error: object
    stdout: str
    stderr: str


@_dataclasses.dataclass(frozen=True)
class SourceRecord:
    """Record an independent expectation's source; performs no product call.

    ``reference`` identifies a standard, URL or asset; ``locator`` identifies
    its section or record; ``derivation`` describes how the expected value
    was obtained. This is provenance supplied by the author, not verification
    of its truth. Construction errors propagate; there is no exit status.
    """

    reference: str
    locator: str
    derivation: str


class _ObservationLimit(AssertionError):
    """A machinery limit was exceeded, rather than a product result obtained."""


@_contextlib.contextmanager
def _deadline(seconds):
    if not isinstance(seconds, (int, float)) or not _math.isfinite(seconds):
        raise ValueError("timeout must be a finite positive number")
    if seconds <= 0:
        raise ValueError("timeout must be a finite positive number")
    if _threading.current_thread() is not _threading.main_thread():
        raise RuntimeError("bounded observations require the main thread")
    if not hasattr(_signal, "setitimer"):
        raise RuntimeError("bounded observations require POSIX interval timers")
    if any(_signal.getitimer(_signal.ITIMER_REAL)):
        raise RuntimeError("an existing real-time timer prevents observation")

    def expired(signum, frame):
        raise _ObservationLimit("public call exceeded its observation deadline")

    previous = _signal.signal(_signal.SIGALRM, expired)
    try:
        _signal.setitimer(_signal.ITIMER_REAL, seconds)
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, previous)


def _consume(iterator, max_items):
    items = []
    for item in iterator:
        if len(items) >= max_items:
            raise _ObservationLimit("iterator exceeded its observation item limit")
        items.append(item)
    return items


def observe(call, *args, exceptions=(), consume=False, timeout=10.0,
            max_items=100000, **kwargs):
    """Return an Observation of ``call(*args, **kwargs)`` and optional iteration.

    ``exceptions`` must be a tuple of public exception classes the caller
    deliberately wants to inspect. The default captures no errors. A recorded
    exception remains intact; inspect its public fields directly. This helper
    neither decides whether an error is expected nor interprets error text.
    ``consume=True`` consumes precisely the returned iterable, preserving each
    item and nested value. False leaves the return value untouched, including
    any lazy iterator; its later consumption is outside this observation.

    Python stdout/stderr are captured across invocation and consumption. There
    is no exit status. Time/item limits raise AssertionError, even if included
    among nominated classes; configuration and unknown errors propagate.
    Limits are observation budgets, not limits on legitimate product results;
    callers with larger finite workloads must supply appropriate budgets.
    """
    if not isinstance(exceptions, tuple) or any(
        not isinstance(cls, type) or not issubclass(cls, Exception)
        for cls in exceptions
    ):
        raise TypeError("exceptions must be a tuple of Exception subclasses")
    if type(max_items) is not int or max_items < 0:
        raise ValueError("max_items must be a nonnegative integer")
    stdout, stderr = _io.StringIO(), _io.StringIO()
    value = None
    error = None
    with _deadline(timeout):
        with _contextlib.redirect_stdout(stdout), _contextlib.redirect_stderr(stderr):
            try:
                value = call(*args, **kwargs)
                if consume:
                    value = _consume(value, max_items)
            except _ObservationLimit:
                raise
            except exceptions as caught:
                value = None
                error = caught
    return Observation(value, error, stdout.getvalue(), stderr.getvalue())


def make_parser(parser_factory, **options):
    """Return a fresh public parser from the supplied factory and exact options.

    No parser version or configuration is selected here. Errors propagate;
    there is no exit status. Wrap in observe to bound and record construction.
    """
    return parser_factory(**options)


def make_context(context_factory, **options):
    """Return a fresh public context from the supplied factory and exact options.

    Options are forwarded without invented roots, focus or bindings. Errors
    propagate; there is no exit status. Wrap in observe for bounded capture.
    """
    return context_factory(**options)


def evaluate_expression(parser, expression, *, context=None, result_method="evaluate"):
    """Return the parsed expression's public evaluate or select_results result.

    The caller supplies the parser, dynamic context (None means absent), and
    result method. No normalization or iteration is implicit. Parsing and
    evaluation errors propagate, with no exit status. Use observe around this
    call, with consume=True for select_results, to capture either failure phase
    within one deadline. Other public APIs can be passed directly to observe.
    """
    if result_method not in ("evaluate", "select_results"):
        raise ValueError("result_method must be evaluate or select_results")
    token = parser.parse(expression)
    if result_method == "evaluate":
        return token.evaluate(context)
    return token.select_results(context)


def result_items(value, *, sequence_type=list):
    """Return a shallow list of items using an explicitly selected outer type.

    A ``sequence_type`` instance, including a subclass, is an outer sequence;
    every other value becomes one item. The default is the public list result
    carrier, used for expressions whose items are not themselves list-valued
    atomics. Nested items are never recursively flattened. None is not guessed
    to mean an empty sequence. For iter_select/select_results use
    observe(consume=True).
    No product call or exit status is involved; configuration errors raise.
    """
    if sequence_type not in (list, tuple):
        raise ValueError("sequence_type must be list or tuple")
    return list(value) if isinstance(value, sequence_type) else [value]


def _reject_json_constant(value):
    raise ValueError("non-JSON numeric constant: " + value)


def read_json(text):
    """Return independently parsed JSON text, rejecting NaN and infinities.

    Uses the standard JSON parser without whitespace or key-order assumptions.
    Repeated names follow that parser's last-name semantics; tests concerned
    with repeated names must inspect them separately, not infer multiplicity
    from this dictionary result. Syntax/type errors propagate, never becoming
    an empty result. No product call or exit status is involved.
    """
    return _json.loads(text, parse_constant=_reject_json_constant)


def read_xml(text):
    """Return a standard-library XML root parsed from a document string/bytes.

    Expanded names, attributes, child order, text and tails remain accessible
    directly; whitespace is not stripped. Comments and processing instructions
    within the root are retained. This reads document content, not lexical
    prefix spelling or document-level siblings. Parse/type errors propagate;
    no product call or exit status is involved.
    """
    parser = _ET.XMLParser(target=_ET.TreeBuilder(insert_comments=True, insert_pis=True))
    return _ET.fromstring(text, parser=parser)
