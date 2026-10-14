# feature: F06
"""Observation helpers for materializing intersection, union, and n-ary union.

JSON fields a probe emits are test encoding, not a product output contract.
A compile or run that cannot be classified raises. It is never folded into
“empty”, “operands unchanged”, or “bytes matched”.
"""

from __future__ import annotations

import secrets
from typing import Any, Mapping, Sequence

from F01_helpers import PUBLIC_U64_SAMPLES, fill_u64, run_bitmap_probe, wrap_probe_body
from F02_helpers import F02_NAMED_U64_SAMPLES, LARGE_PROBE_TIMEOUT
from F03_helpers import F03_NAMED_U64_SAMPLES
from F04_helpers import F04_NAMED_U64
from F05_helpers import F05_NAMED_U64, unpublished_u64_f05
from _helpers import HarnessError

# Values FP-06 names. Unpublished draws must not land here.
F06_NAMED_U64 = frozenset({0, 3, 1 << 16, 1 << 32, 1 << 40, 1 << 48})

_EARLIER_NAMED = (
    frozenset(PUBLIC_U64_SAMPLES)
    | frozenset(F02_NAMED_U64_SAMPLES)
    | frozenset(F03_NAMED_U64_SAMPLES)
    | frozenset(F04_NAMED_U64)
    | frozenset(F05_NAMED_U64)
    | F06_NAMED_U64
)

U64_MAX = (1 << 64) - 1
PREFIX_SPACE = 1 << 48
LOW_SPACE = 1 << 16


def unpublished_u64_f06(
    forbidden: set[int] | frozenset[int] | None = None,
    *,
    above: int | None = None,
) -> int:
    """A 64-bit value this feature's named samples do not include.

    Also avoids values earlier features published. A draw that lands in
    *forbidden* or on a named sample raises.
    """
    extra = set(F06_NAMED_U64)
    if forbidden is not None:
        extra.update(forbidden)
    value = unpublished_u64_f05(extra, above=above)
    if value in extra or value in _EARLIER_NAMED:
        raise HarnessError(
            f"unpublished_u64_f06 collided with a forbidden value: {value}"
        )
    return value


def _blocked_prefixes() -> set[int]:
    return {value >> 16 for value in _EARLIER_NAMED} | {0}


def draw_distinct_f06(
    count: int,
    forbidden: set[int] | frozenset[int] | None = None,
    *,
    above: int | None = None,
) -> list[int]:
    """*count* distinct unpublished values. A collision raises."""
    if count <= 0:
        raise HarnessError(f"draw count {count} is empty")
    blocked: set[int] = set(forbidden) if forbidden is not None else set()
    out: list[int] = []
    while len(out) < count:
        value = unpublished_u64_f06(blocked, above=above)
        if value in blocked or value in out:
            raise HarnessError(f"distinct draw collided: {value}")
        blocked.add(value)
        out.append(value)
    return out


def unpublished_pair_size_f06() -> int:
    """A pair width that is neither the named 1500 nor the named 4."""
    size = 5 + secrets.randbelow(24)
    if size in (4, 1500):
        raise HarnessError(f"unpublished pair size landed on a named width: {size}")
    return size


def unpublished_nary_count_f06() -> int:
    """A list length that is not the named 0, 1, or 60."""
    count = 3 + secrets.randbelow(6)
    if count in (0, 1, 60):
        raise HarnessError(f"n-ary count landed on a named width: {count}")
    return count


def split_pair_f06(size: int) -> tuple[list[int], list[int], list[int], int]:
    """Two *size*-value sets with a non-empty overlap and both exclusive sides.

    Every value is above 2^32. Returns ``(left, right, expected_intersection, absent)``.
    The expected union is ``sorted(set(left) | set(right))`` and is not returned
    so a caller cannot treat one list as both answers.
    """
    if size < 3:
        raise HarnessError(f"split pair size {size} cannot show all three parts")
    overlap_n = max(1, size // 3)
    only_n = size - overlap_n
    if only_n < 1:
        raise HarnessError("split pair has no exclusive side")
    shared = draw_distinct_f06(overlap_n, above=1 << 32)
    left_only = draw_distinct_f06(only_n, set(shared), above=1 << 32)
    right_only = draw_distinct_f06(only_n, set(shared) | set(left_only), above=1 << 32)
    left = shared + left_only
    right = shared + right_only
    if len(set(left)) != size or len(set(right)) != size:
        raise HarnessError("split pair is not the requested width")
    both = set(left) & set(right)
    if not both or not (set(left) - set(right)) or not (set(right) - set(left)):
        raise HarnessError("split pair is missing overlap or an exclusive side")
    if not any(v > (1 << 32) for v in left) or not any(v > (1 << 32) for v in right):
        raise HarnessError("split pair has no value above 2^32")
    absent = unpublished_u64_f06(set(left) | set(right), above=1 << 32)
    return left, right, sorted(both), absent


def disjoint_sides_f06(width: int = 4) -> tuple[list[int], list[int]]:
    """Two unpublished sets of *width* with nothing in common."""
    left = draw_distinct_f06(width, above=1 << 32)
    right = draw_distinct_f06(width, set(left), above=1 << 32)
    if set(left) & set(right):
        raise HarnessError("disjoint draw overlapped")
    if len(left) != width or len(right) != width:
        raise HarnessError("disjoint draw has the wrong width")
    return left, right


def consecutive_run_f06(
    avoid_prefixes: set[int] | None = None,
) -> tuple[int, list[int]]:
    """A consecutive run under one high-48 prefix, length at least 1000.

    The low start is drawn at runtime and is not 0. The prefix is not a
    prefix of a named sample. Raises if no such run can be drawn.
    """
    length = 1000 + secrets.randbelow(300)
    if length < 1000 or length >= LOW_SPACE:
        raise HarnessError(f"run length {length} is out of range")
    blocked = _blocked_prefixes()
    if avoid_prefixes:
        blocked |= set(avoid_prefixes)
    room = LOW_SPACE - length - 1
    if room <= 1:
        raise HarnessError("no room for a non-zero consecutive start")
    for _ in range(64):
        prefix = 1 + secrets.randbelow(PREFIX_SPACE - 2)
        if prefix in blocked:
            continue
        start = 1 + secrets.randbelow(room)
        values = [(prefix << 16) | (start + i) for i in range(length)]
        if any(value in _EARLIER_NAMED for value in values):
            continue
        if len(set(values)) != length:
            raise HarnessError("consecutive run produced duplicates")
        return prefix, values
    raise HarnessError("could not draw a consecutive run")


def values_at_named_position_f06(position: int, extra: int) -> list[int]:
    """*extra* unpublished lows under the high-48 prefix of *position*, plus *position*.

    *position* is a value the PRD names as a location (2^32 or 2^48).
    """
    if position not in F06_NAMED_U64 and position not in (1 << 32, 1 << 48):
        raise HarnessError(f"{position} is not a named position")
    prefix = position >> 16
    lows = {position & 0xFFFF}
    values = [position]
    guard = 0
    while len(values) < extra + 1:
        guard += 1
        if guard > 10000:
            raise HarnessError("could not draw lows under a named position")
        low = secrets.randbelow(LOW_SPACE)
        if low in lows:
            continue
        value = (prefix << 16) | low
        if value in _EARLIER_NAMED:
            continue
        lows.add(low)
        values.append(value)
    return values


def fresh_prefix_values_f06(
    count: int,
    avoid_prefixes: set[int],
    forbidden_values: set[int],
) -> tuple[int, list[int]]:
    """*count* values under one high-48 prefix that *avoid_prefixes* does not use."""
    if count <= 0 or count > 16:
        raise HarnessError(f"fresh prefix count {count} is out of range")
    blocked = _blocked_prefixes() | set(avoid_prefixes)
    for _ in range(64):
        prefix = 1 + secrets.randbelow(PREFIX_SPACE - 2)
        if prefix in blocked:
            continue
        lows: list[int] = []
        used: set[int] = set()
        guard = 0
        while len(lows) < count:
            guard += 1
            if guard > 10000:
                break
            low = secrets.randbelow(LOW_SPACE)
            if low in used:
                continue
            value = (prefix << 16) | low
            if value in forbidden_values or value in _EARLIER_NAMED:
                continue
            used.add(low)
            lows.append(value)
        if len(lows) != count:
            continue
        return prefix, lows
    raise HarnessError("could not draw a fresh prefix")


def run_f06_probe(body: str, **values: int | str) -> dict[str, Any]:
    """Compile and run one probe. Non-zero status or a non-object is a harness failure."""
    source = wrap_f06_probe(fill_u64(body, **values) if values else body)
    return run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)


def require_probe_true(report: Mapping[str, Any], *keys: str) -> None:
    """Every named JSON bool is true. Missing or non-bool raises."""
    from F02_helpers import require_bool_field

    for key in keys:
        if require_bool_field(report, key) is not True:
            raise AssertionError(f"{key} is not true")


_F06_ZIG = r"""
fn valuesMatch(bm: *const klyvmap.Bitmap, sorted: []const u64) bool {
    if (bm.getCardinality() != sorted.len) return false;
    var it = bm.iterator();
    for (sorted) |want| {
        const got = it.next() orelse return false;
        if (got != want) return false;
    }
    if (it.next() != null) return false;
    return it.next() == null;
}

fn containsAll(bm: *const klyvmap.Bitmap, vals: []const u64) bool {
    for (vals) |v| if (!bm.contains(v)) return false;
    return true;
}

fn containsNone(bm: *const klyvmap.Bitmap, vals: []const u64) bool {
    for (vals) |v| if (bm.contains(v)) return false;
    return true;
}

fn extremaMatch(bm: *const klyvmap.Bitmap, sorted: []const u64) bool {
    if (sorted.len == 0) return false;
    if (bm.getCardinality() != sorted.len) return false;
    const mn = bm.minimum() orelse return false;
    const mx = bm.maximum() orelse return false;
    return mn == sorted[0] and mx == sorted[sorted.len - 1];
}

fn buildFrom(alloc: std.mem.Allocator, vals: []const u64) !klyvmap.Bitmap {
    var bm = try klyvmap.Bitmap.init(alloc);
    for (vals) |v| _ = try bm.set(v);
    return bm;
}

fn shapeOf(buf: []const u8) !struct { len: usize, b0: u8, b1: u8, res: usize } {
    if (buf.len < 2) return error.ShortHeader;
    return .{
        .len = buf.len,
        .b0 = buf[0],
        .b1 = buf[1],
        .res = @intFromPtr(buf.ptr) % 8,
    };
}

fn zeroThenRest(bm: *const klyvmap.Bitmap, rest: []const u64) bool {
    var it = bm.iterator();
    const first = it.next() orelse return false;
    if (first != 0) return false;
    for (rest) |want| {
        const got = it.next() orelse return false;
        if (got != want) return false;
    }
    if (it.next() != null) return false;
    return it.next() == null;
}

fn emptyView(bm: *const klyvmap.Bitmap) struct { empty: bool, card: u64, c0: bool, exh: bool } {
    var it = bm.iterator();
    const first_null = it.next() == null;
    const second_null = it.next() == null;
    return .{
        .empty = bm.isEmpty(),
        .card = bm.getCardinality(),
        .c0 = bm.contains(0),
        .exh = first_null and second_null,
    };
}

fn foldUnion(alloc: std.mem.Allocator, bitmaps: []const *const klyvmap.Bitmap) !klyvmap.Bitmap {
    if (bitmaps.len < 2) return error.FoldNeedsTwo;
    var acc = try klyvmap.Bitmap.Or(alloc, bitmaps[0], bitmaps[1]);
    for (bitmaps[2..]) |bm| {
        const next = try klyvmap.Bitmap.Or(alloc, &acc, bm);
        acc.deinit();
        acc = next;
    }
    return acc;
}

fn openedMatches(alloc: std.mem.Allocator, bm: *const klyvmap.Bitmap, sorted: []const u64) !bool {
    const emitted = bm.toBuffer();
    var opened = try klyvmap.Bitmap.fromBufferCopy(alloc, emitted);
    defer opened.deinit();
    const same_bytes = std.mem.eql(u8, opened.toBuffer(), emitted);
    const same_vals = valuesMatch(&opened, sorted) and valuesMatch(bm, sorted);
    return same_bytes and same_vals;
}
"""


def wrap_f06_probe(body: str) -> str:
    """Wrap *body* in the tracking-allocator probe with F06 comparisons in scope."""
    src = wrap_probe_body(body)
    marker = "\nfn run("
    idx = src.find(marker)
    if idx < 0:
        raise HarnessError("wrap_probe_body produced no run function")
    src = src[:idx] + "\n" + _F06_ZIG + src[idx:]
    needle = "    const alloc_anchor = allocator;\n"
    insert = (
        needle
        + "    comptime { _ = valuesMatch; _ = containsAll; _ = containsNone; "
        + "_ = extremaMatch; _ = buildFrom; _ = shapeOf; _ = zeroThenRest; "
        + "_ = emptyView; _ = foldUnion; _ = openedMatches; }\n"
    )
    if needle not in src:
        raise HarnessError("tracking probe has no alloc anchor")
    return src.replace(needle, insert, 1)


def bitmap_block(specs: Sequence[tuple]) -> str:
    """Zig that builds ``b0..`` and ``ptrs`` from value lists, empties, or removed sets.

    Each spec is ``("values", [ints])``, ``("empty",)``, or ``("removed", [ints])``.
    """
    if not specs:
        raise HarnessError("bitmap block has no inputs")
    lines: list[str] = []
    names: list[str] = []
    for index, spec in enumerate(specs):
        kind = spec[0]
        name = f"b{index}"
        names.append(name)
        if kind == "empty":
            lines.append(f"    var {name} = try klyvmap.Bitmap.init(allocator);")
            lines.append(f"    defer {name}.deinit();")
            continue
        if kind not in ("values", "removed"):
            raise HarnessError(f"unknown bitmap spec {kind!r}")
        values = spec[1]
        if not values:
            raise HarnessError(f"{kind} bitmap {index} has no values")
        from F02_helpers import zig_u64_list

        literal = zig_u64_list(values)
        lines.append(f"    const ins{index} = [_]u64{{ {literal} }};")
        lines.append(f"    var {name} = try buildFrom(allocator, &ins{index});")
        lines.append(f"    defer {name}.deinit();")
        if kind == "removed":
            lines.append(f"    for (ins{index}) |gone| _ = {name}.remove(gone);")
            lines.append(
                f"    if ({name}.getCardinality() != 0) return error.RemovedStillHolds;"
            )
    joined = ", ".join(f"&{name}" for name in names)
    lines.append(f"    const ptrs = [_]*const klyvmap.Bitmap{{ {joined} }};")
    return "\n".join(lines)
