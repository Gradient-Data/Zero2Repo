# feature: F01
"""Observation helpers for FP-01 parse failure reports.

The thrown error carries ``mark.name`` (the source-path label) and
``mark.line`` (how many line breaks precede the error site, a CR/LF
pair counting as one break), as the Interface Contract states.
"""

from __future__ import annotations

from _harness import ErrorInfo, HarnessError


def require_line_break_counts(
    later_error: ErrorInfo,
    earlier_error: ErrorInfo,
    *,
    label: str,
) -> None:
    """Assert the stated ``mark`` form: later line count one, first line zero.

    The thrown error carries ``mark.name`` (the ``filename`` label) and
    ``mark.line`` (the number of line breaks before the error site, a CR/LF
    pair counting as one break).
    """
    for which, error in (("later", later_error), ("earlier", earlier_error)):
        if error is None:
            raise HarnessError(f"{which} failure report is missing")
        if not isinstance(error, ErrorInfo):
            raise HarnessError(
                f"{which} failure report is not ErrorInfo: {type(error).__name__}"
            )
    later_mark = later_error.mark
    earlier_mark = earlier_error.mark
    print(f"later_mark={later_mark!r} earlier_mark={earlier_mark!r}", flush=True)
    assert later_mark is not None and earlier_mark is not None, (
        "a failed parse must throw an error carrying a mark object; "
        f"later={later_mark!r} earlier={earlier_mark!r}"
    )
    assert later_mark.name == label and earlier_mark.name == label, (
        f"mark.name must be the filename label {label!r}; "
        f"later={later_mark.name!r} earlier={earlier_mark.name!r}"
    )
    assert later_mark.line == 1, (
        "mark.line of a failure after one CR/LF break must be 1; "
        f"got {later_mark.line!r}"
    )
    assert earlier_mark.line == 0, (
        "mark.line of a failure on the first line must be 0; "
        f"got {earlier_mark.line!r}"
    )
