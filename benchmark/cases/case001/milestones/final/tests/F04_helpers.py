# feature: F04
"""Observation helpers for refusing invalid TOML (FP-04).

Reason, document, offset, line, and column are read from the attributes the
Interface Contract states on the decode-error instance (``msg``, ``doc``,
``pos``, ``lineno``, ``colno``). The line and column must equal the 1-based
place of ``pos`` in ``doc`` (PRD FP-04 location rules).
A missing value or a wrong type is a harness failure, never a sentinel.
"""

from __future__ import annotations

from typing import Any

from _harness import CallResult, HarnessError, call
from F01_helpers import decode_error_type, string_parse_entry


def call_string_parse(obj: Any) -> CallResult:
    """Call the public string-parse entry with *obj* of any Python type.

    Does not require *obj* to be ``str``. Harness failures propagate.
    """
    return call(string_parse_entry(), obj)


def construct_decode_error(reason: str, document: str, offset: int) -> Any:
    """Build a decode-error instance from reason, document, and 0-based offset.

    Construction is a call of the public decode-error type, not a parse.
    A product exception raised by the constructor is not swallowed: it is
    re-raised as ``AssertionError`` carrying that exception. Harness
    failures propagate. Does not compute line or column and write them back.
    """
    if not isinstance(reason, str):
        raise HarnessError(
            f"construct_decode_error reason must be str, got {type(reason)!r}"
        )
    if not isinstance(document, str):
        raise HarnessError(
            f"construct_decode_error document must be str, got {type(document)!r}"
        )
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise HarnessError(
            f"construct_decode_error offset must be int, got {type(offset)!r}"
        )
    result = call(decode_error_type(), reason, document, offset)
    if result.exception is not None:
        raise AssertionError(
            "constructing decode error raised "
            f"{type(result.exception).__name__}: {result.exception!r}"
        )
    value = result.value
    decode_type = decode_error_type()
    if not isinstance(value, decode_type):
        raise AssertionError(
            "constructing decode error returned "
            f"{type(value)!r}: {value!r}"
        )
    if not isinstance(value, ValueError):
        raise AssertionError(
            "constructed decode error is not a value error: "
            f"{type(value).__name__}: {value!r}"
        )
    return value


def _require_field(exc: BaseException, name: str) -> Any:
    try:
        return getattr(exc, name)
    except AttributeError as err:
        raise HarnessError(
            f"decode error has no recoverable {name!r}: {exc!r}"
        ) from err


def recover_reason(exc: BaseException) -> str:
    """Return the unformatted reason text from a decode-error instance."""
    value = _require_field(exc, "msg")
    if not isinstance(value, str):
        raise HarnessError(
            f"unformatted reason is not text: {type(value)!r}: {value!r}"
        )
    return value


def recover_document(exc: BaseException) -> str:
    """Return the original document text from a decode-error instance."""
    value = _require_field(exc, "doc")
    if not isinstance(value, str):
        raise HarnessError(
            f"original document is not text: {type(value)!r}: {value!r}"
        )
    return value


def recover_offset(exc: BaseException) -> int:
    """Return the 0-based character offset from a decode-error instance."""
    value = _require_field(exc, "pos")
    if isinstance(value, bool) or not isinstance(value, int):
        raise HarnessError(
            f"offset is not an int: {type(value)!r}: {value!r}"
        )
    return value


def _is_place_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _one_based_place(document: str, offset: int) -> tuple[int, int]:
    """1-based line and column of the character at 0-based *offset*.

    This is the meaning of those two numbers given the recovered document
    and offset (PRD: 1-based line and 1-based column of that character).
    It is not a lookup of a product field name.
    """
    if not isinstance(document, str):
        raise HarnessError(
            f"document for place recovery is not text: {type(document)!r}"
        )
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise HarnessError(
            f"offset for place recovery is not an int: {type(offset)!r}"
        )
    if offset < 0:
        raise HarnessError(f"offset {offset} is negative")
    line = document.count("\n", 0, offset) + 1
    if line == 1:
        column = offset + 1
    else:
        column = offset - document.rindex("\n", 0, offset)
    return line, column


def _recover_place_pair(exc: BaseException) -> tuple[int, int]:
    """Return the 1-based line and column stored on *exc*.

    Reads the stated ``lineno`` and ``colno`` attributes and requires them to
    be the 1-based place of the recovered offset in the recovered document.
    """
    document = recover_document(exc)
    offset = recover_offset(exc)
    line = _require_field(exc, "lineno")
    column = _require_field(exc, "colno")
    if not _is_place_int(line):
        raise AssertionError(
            f"lineno is not an int: {type(line)!r}: {line!r} on {exc!r}"
        )
    if not _is_place_int(column):
        raise AssertionError(
            f"colno is not an int: {type(column)!r}: {column!r} on {exc!r}"
        )
    want_line, want_column = _one_based_place(document, offset)
    if line != want_line:
        raise AssertionError(
            f"lineno {line} is not the 1-based line {want_line} of offset "
            f"{offset} in {document!r}"
        )
    if column != want_column:
        raise AssertionError(
            f"colno {column} is not the 1-based column {want_column} of "
            f"offset {offset} in {document!r}"
        )
    return line, column


def recover_line(exc: BaseException) -> int:
    """Return the 1-based line number from a decode-error instance."""
    line, _column = _recover_place_pair(exc)
    return line


def recover_column(exc: BaseException) -> int:
    """Return the 1-based column number from a decode-error instance."""
    _line, column = _recover_place_pair(exc)
    return column


def formatted_report(exc: BaseException) -> str:
    """Return the formatted report for *exc* (``str(exc)``)."""
    return str(exc)


def require_interior_place(exc: BaseException, document: str) -> None:
    """Require a decode error whose place is a character inside *document*."""
    decode_type = decode_error_type()
    if not isinstance(exc, decode_type):
        raise AssertionError(
            f"expected decode error, got {type(exc).__name__}: {exc!r}"
        )
    if not isinstance(exc, ValueError):
        raise AssertionError(
            "decode error is not a value error: "
            f"{type(exc).__name__}: {exc!r}"
        )
    recovered = recover_document(exc)
    if recovered != document:
        raise AssertionError(
            f"recovered document {recovered!r} != input {document!r}"
        )
    offset = recover_offset(exc)
    if not (0 <= offset < len(document)):
        raise AssertionError(
            f"offset {offset} is not an interior index of document "
            f"len {len(document)}"
        )
    line = recover_line(exc)
    column = recover_column(exc)
    if line < 1:
        raise AssertionError(f"line {line} is not 1-based (>= 1)")
    if column < 1:
        raise AssertionError(f"column {column} is not 1-based (>= 1)")
    print(
        f"interior offset={offset} line={line} column={column} "
        f"doc_len={len(document)}",
        flush=True,
    )


def require_recoverable_offset(exc: BaseException, document: str) -> int:
    """Require a decode error with original text and a recoverable int offset.

    Does not by itself require the offset to be at or past the end.
    """
    decode_type = decode_error_type()
    if not isinstance(exc, decode_type):
        raise AssertionError(
            f"expected decode error, got {type(exc).__name__}: {exc!r}"
        )
    if not isinstance(exc, ValueError):
        raise AssertionError(
            "decode error is not a value error: "
            f"{type(exc).__name__}: {exc!r}"
        )
    recovered = recover_document(exc)
    if recovered != document:
        raise AssertionError(
            f"recovered document {recovered!r} != input {document!r}"
        )
    offset = recover_offset(exc)
    print(f"recoverable offset={offset} doc_len={len(document)}", flush=True)
    return offset


def require_end_of_document_place(exc: BaseException, document: str) -> int:
    """Require a decode error whose place is the end of *document*, not interior.

    The named carrier is the recoverable 0-based offset: it is at or
    past the end, so the failure is not a character inside the document with
    an interior 1-based line and column. Does not pin report wording.
    """
    offset = require_recoverable_offset(exc, document)
    if offset < len(document):
        line = recover_line(exc)
        column = recover_column(exc)
        raise AssertionError(
            f"offset {offset} is an interior index of document len "
            f"{len(document)} (line {line}, column {column}); expected "
            "end-of-document, not a line and column in the interior"
        )
    print(
        f"end-of-document offset={offset} doc_len={len(document)}",
        flush=True,
    )
    return offset


def require_end_distinct_from_interior(
    end_exc: BaseException,
    end_doc: str,
    interior_exc: BaseException,
    interior_doc: str,
) -> None:
    """Require the early-end failure to be end-of-document, not interior."""
    require_interior_place(interior_exc, interior_doc)
    require_end_of_document_place(end_exc, end_doc)


def require_same_recovered_place(
    exc_a: BaseException, exc_b: BaseException
) -> None:
    """Require two failures to recover the same document, offset, line, and column."""
    doc_a = recover_document(exc_a)
    doc_b = recover_document(exc_b)
    if doc_a != doc_b:
        raise AssertionError(
            f"recovered documents differ: {doc_a!r} vs {doc_b!r}"
        )
    off_a = recover_offset(exc_a)
    off_b = recover_offset(exc_b)
    if off_a != off_b:
        raise AssertionError(f"recovered offsets differ: {off_a} vs {off_b}")
    line_a = recover_line(exc_a)
    line_b = recover_line(exc_b)
    if line_a != line_b:
        raise AssertionError(f"recovered lines differ: {line_a} vs {line_b}")
    col_a = recover_column(exc_a)
    col_b = recover_column(exc_b)
    if col_a != col_b:
        raise AssertionError(
            f"recovered columns differ: {col_a} vs {col_b}"
        )
    print(
        f"same place document={doc_a!r} offset={off_a} line={line_a} column={col_a}",
        flush=True,
    )
