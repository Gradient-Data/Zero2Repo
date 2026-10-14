# feature: F08
"""Feature-local helpers for opt-in progress on standard error.

These helpers read a process result's standard error and destination
files. They are not a substitute public entry. A completion indication
is a progress update whose text carries the literal 100%. A progress
run is the output up to and including one such indication. One run
versus several is the count of those indications: exactly one at
Vorbis effort 1, two or more at effort 9 of the same input. Label
wording other than that mark is the implementer's and is not scored.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from F01_helpers import require_ok, unique_name
from F04_helpers import archive_bytes, expand_to, require_lossless_archive
from _harness import HarnessError, RunResult, Workspace

COMPLETION_MARK = "100%"


def completion_indication_count(text: str) -> int:
    """Count progress updates whose text carries the literal 100%.

    Type errors raise. Zero is a real observation (no completion mark).
    """
    if not isinstance(text, str):
        raise HarnessError(
            f"completion_indication_count expected str, got {type(text)!r}"
        )
    n = text.count(COMPLETION_MARK)
    print(f"[F08] completion indications={n}", flush=True)
    return n


def require_completion_indication(result: RunResult) -> None:
    """Standard error carries at least one completion indication."""
    if not isinstance(result, RunResult):
        raise HarnessError(
            f"require_completion_indication expected RunResult, "
            f"got {type(result)!r}"
        )
    n = completion_indication_count(result.stderr_text)
    assert n >= 1, (
        "standard error must carry at least one completion indication "
        "(a progress update whose text carries the literal 100%); "
        f"count={n}"
    )


def require_completion_contrast(off: RunResult, on: RunResult) -> None:
    """Off writes no 100% update; on writes at least one.

    Does not treat leftover-nonempty after a path-and-size strip as the
    completion indication. Does not require the raw off-arm standard
    error to be empty.
    """
    if not isinstance(off, RunResult):
        raise HarnessError(
            f"require_completion_contrast expected RunResult off, got {type(off)!r}"
        )
    if not isinstance(on, RunResult):
        raise HarnessError(
            f"require_completion_contrast expected RunResult on, got {type(on)!r}"
        )
    off_n = completion_indication_count(off.stderr_text)
    on_n = completion_indication_count(on.stderr_text)
    assert off_n == 0, (
        "without --progress or -p, standard error must not carry a "
        "completion indication (a progress update whose text carries "
        f"the literal 100%); count={off_n}"
    )
    assert on_n >= 1, (
        "with --progress or -p, standard error must carry at least one "
        "completion indication (a progress update whose text carries "
        f"the literal 100%); count={on_n}"
    )
    print(
        f"[F08] completion contrast off={off_n} on={on_n}",
        flush=True,
    )


def progress_records(text: str, *, newline_only: bool) -> list[str]:
    """Split *text* into nonempty records.

    ``newline_only=True`` splits only on ``\\n``. Otherwise split on
    ``\\n`` and ``\\r``. Whitespace-only records are dropped. Type errors
    raise.
    """
    if not isinstance(text, str):
        raise HarnessError(f"progress_records expected str, got {type(text)!r}")
    if newline_only:
        parts = text.split("\n")
    else:
        parts = re.split(r"[\n\r]", text)
    records = [part.strip() for part in parts if part.strip()]
    print(
        f"[F08] records newline_only={newline_only} count={len(records)}",
        flush=True,
    )
    return records


def require_newline_oriented_records(text: str) -> None:
    """Newline-only split matches ``\\n``/``\\r`` split; more than one line."""
    if not isinstance(text, str):
        raise HarnessError(
            f"require_newline_oriented_records expected str, got {type(text)!r}"
        )
    newline = progress_records(text, newline_only=True)
    either = progress_records(text, newline_only=False)
    assert newline == either, (
        "progress-lines records must be the same whether split only on "
        f"newline or also on carriage return; newline={newline!r} "
        f"either={either!r}"
    )
    assert len(newline) > 1, (
        "progress-lines must write more than one nonempty newline record; "
        f"records={newline!r}"
    )
    print(f"[F08] newline-oriented records={len(newline)}", flush=True)


def _record_has_name(record: str, name: str) -> bool:
    if not isinstance(record, str):
        raise HarnessError(
            f"_record_has_name expected str record, got {type(record)!r}"
        )
    if not isinstance(name, str):
        raise HarnessError(f"_record_has_name expected str name, got {type(name)!r}")
    if name and name in record:
        return True
    base = Path(name).name
    return bool(base) and base in record


def require_names_visible_on_newline_records(
    text: str, names: Sequence[str]
) -> None:
    """More than one newline record; each name or basename appears on them."""
    if not isinstance(text, str):
        raise HarnessError(
            f"require_names_visible_on_newline_records expected str, "
            f"got {type(text)!r}"
        )
    records = progress_records(text, newline_only=True)
    assert len(records) > 1, (
        "batch progress must occupy more than one nonempty newline record; "
        f"records={records!r}"
    )
    joined = "\n".join(records)
    for name in names:
        if not isinstance(name, str):
            raise HarnessError(
                f"require_names_visible_on_newline_records expected str name, "
                f"got {type(name)!r}"
            )
        base = Path(name).name
        present = (name and name in joined) or (base and base in joined)
        assert present, (
            f"batch progress newline records do not name {name!r} "
            f"(basename {base!r}); records={records!r}"
        )
    print(
        f"[F08] names visible on {len(records)} newline records: {list(names)!r}",
        flush=True,
    )


def require_names_on_distinct_newline_lines(
    text: str, names: Sequence[str]
) -> None:
    """Each name appears on a newline record; at least two names differ in line."""
    if not isinstance(text, str):
        raise HarnessError(
            f"require_names_on_distinct_newline_lines expected str, "
            f"got {type(text)!r}"
        )
    records = progress_records(text, newline_only=True)
    locations: list[list[int]] = []
    for name in names:
        if not isinstance(name, str):
            raise HarnessError(
                f"require_names_on_distinct_newline_lines expected str name, "
                f"got {type(name)!r}"
            )
        hits = [i for i, rec in enumerate(records) if _record_has_name(rec, name)]
        assert hits, (
            f"no newline record names {name!r}; records={records!r}"
        )
        locations.append(hits)
    distinct = False
    listed = list(names)
    for i, left in enumerate(listed):
        for j, right in enumerate(listed):
            if i >= j:
                continue
            for ri in locations[i]:
                for rj in locations[j]:
                    if ri != rj:
                        distinct = True
                        break
                if distinct:
                    break
            if distinct:
                break
        if distinct:
            break
    assert distinct, (
        "two batch input names must appear on distinct newline records; "
        f"names={listed!r} records={records!r}"
    )
    print(
        f"[F08] names on distinct newline lines: {listed!r}",
        flush=True,
    )


def require_written_dest(ws: Workspace, src: str, dest: str) -> None:
    """*dest* is a regular file and a different path from *src*."""
    if not isinstance(src, str) or not isinstance(dest, str):
        raise HarnessError("require_written_dest expected str src and dest")
    assert dest != src, f"destination path {dest!r} equals the source path"
    assert ws.path_is_file(dest), (
        f"expected a regular file at destination {dest!r}"
    )


def require_archive_roundtrip(
    ws: Workspace, src: str, dest: str, *, what: str
) -> bytes:
    """Dest exists, dest≠src path, dest bytes ≠ source, expand restores source."""
    require_written_dest(ws, src, dest)
    src_bytes = ws.read_bytes(src)
    dest_bytes = archive_bytes(ws, dest)
    recovered = unique_name("rec")
    expand_to(ws, dest, recovered)
    rec_bytes = ws.read_bytes(recovered)
    require_lossless_archive(dest_bytes, rec_bytes, src_bytes, what=what)
    print(
        f"[F08] roundtrip {what} src={len(src_bytes)} dest={len(dest_bytes)}",
        flush=True,
    )
    return dest_bytes


def require_ok_written(result: RunResult, ws: Workspace, src: str, dest: str) -> None:
    """Exit 0 and *dest* is a regular file distinct from *src*."""
    require_ok(result)
    require_written_dest(ws, src, dest)
