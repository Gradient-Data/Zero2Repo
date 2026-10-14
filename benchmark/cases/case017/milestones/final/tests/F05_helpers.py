# feature: F05
"""Observation helpers for compacting a bitmap to its canonical buffer.

JSON fields a probe emits are test encoding, not a product output contract.
A compile failure, a non-zero probe, or a JSON shape this helper cannot
classify raises. It is never reported as "length unchanged", "bytes match",
or "the caller buffer was not written".
"""

from __future__ import annotations

import secrets
from typing import Sequence

from F01_helpers import (
    ZIG_PRELUDE,
    _walk_regular_files,
    compile_product_source,
    fill_u64,
    network_syscalls_in_trace,
    product_created_files,
    require_empty_snapshot,
    require_positive_buffer_length,
    run_bitmap_probe,
    run_traced_network,
    wrap_probe_body,
)
from F02_helpers import (
    require_bool_field,
    require_int_field,
    shuffle_not_sorted,
    unpublished_u64_f02,
    zig_u64_list,
)
from F03_helpers import require_no_integer, require_strictly_ascending_once
from F04_helpers import (
    file_write_syscalls_in_trace,
    require_emit_shape,
    run_traced_arch_network,
    run_traced_file_writes,
    unpublished_u64_f04,
    wrap_f04_probe,
)
from _helpers import HarnessError

# Values FP-05 names, plus 0 which the empty-bitmap contract names.
F05_NAMED_U64 = frozenset({0, 42, 99, 1 << 40})

# Repo scripts this feature must not replay: 20000, 1200, 500, and 30..46.
_BANNED_COUNTS = frozenset({500, 1200, 20000}) | frozenset(range(30, 47))

U64_MAX = (1 << 64) - 1
PREFIX_SPACE = 1 << 48


def unpublished_u64_f05(
    forbidden: set[int] | frozenset[int] | None = None,
    *,
    above: int | None = None,
) -> int:
    """A 64-bit value this feature's named samples do not include.

    The draw also avoids values earlier features published. A collision raises.
    """
    extra = set(F05_NAMED_U64)
    if forbidden is not None:
        extra.update(forbidden)
    value = unpublished_u64_f04(extra, above=above)
    if value in extra or value in F05_NAMED_U64:
        raise HarnessError(f"unpublished_u64_f05 collided with a forbidden value: {value}")
    return value


def _fresh_prefix(blocked: set[int]) -> int:
    for _ in range(128):
        prefix = 1 + secrets.randbelow(PREFIX_SPACE - 2)
        if prefix in blocked or prefix == 0:
            continue
        return prefix
    raise HarnessError("could not draw an unpublished high-48 prefix")


def values_under_prefix(prefix: int, count: int, forbidden: set[int]) -> list[int]:
    """*count* distinct values whose high 48 bits are *prefix*."""
    if count <= 0 or count > (1 << 16):
        raise HarnessError(f"prefix population {count} is out of range")
    lows: list[int] = []
    used: set[int] = set()
    guard = 0
    while len(lows) < count:
        guard += 1
        if guard > count + (1 << 16):
            raise HarnessError("could not draw distinct lows for a prefix")
        low = secrets.randbelow(1 << 16)
        if low in used:
            continue
        value = (prefix << 16) | low
        if value in forbidden or value in F05_NAMED_U64:
            continue
        used.add(low)
        lows.append(low)
    return [(prefix << 16) | low for low in lows]


def runtime_count(low: int, high: int) -> int:
    """A count in ``[low, high]`` that is not a replayed repository script size."""
    if high < low:
        raise HarnessError(f"count range {low}..{high} is empty")
    for _ in range(64):
        count = low + secrets.randbelow(high - low + 1)
        if count not in _BANNED_COUNTS:
            return count
    raise HarnessError(f"could not draw a count in {low}..{high}")


def slack_parts() -> dict[str, list[int]]:
    """A dense low prefix, a mid prefix, and many one-or-two-value high prefixes.

    Counts are drawn at runtime and are not the repository's fixed scripts.
    ``removed`` are values taken back out so at least one high prefix is emptied.
    ``kept`` is what remains.
    """
    forbidden: set[int] = set(F05_NAMED_U64)
    blocked_prefixes = {value >> 16 for value in forbidden}
    dense_n = runtime_count(900, 1400)
    dense = list(range(dense_n))
    forbidden.update(dense)
    blocked_prefixes.add(0)

    mid_prefix = _fresh_prefix(blocked_prefixes)
    blocked_prefixes.add(mid_prefix)
    mid = values_under_prefix(mid_prefix, runtime_count(12, 40), forbidden)
    forbidden.update(mid)

    high_groups: list[list[int]] = []
    group_n = runtime_count(24, 48)
    for _ in range(group_n):
        prefix = _fresh_prefix(blocked_prefixes)
        blocked_prefixes.add(prefix)
        width = 1 + secrets.randbelow(2)
        group = values_under_prefix(prefix, width, forbidden)
        forbidden.update(group)
        high_groups.append(group)

    emptied = high_groups[: runtime_count(2, 5)]
    removed = [value for group in emptied for value in group]
    # Also drop some mid values. The mid prefix itself stays occupied.
    mid_drop_n = runtime_count(2, min(6, len(mid) - 1))
    removed.extend(mid[:mid_drop_n])
    removed_set = set(removed)
    inserted = dense + mid + [value for group in high_groups for value in group]
    kept = [value for value in inserted if value not in removed_set]
    if not removed_set.isdisjoint(kept):
        raise HarnessError("slack workload removed a value it also kept")
    emptied_prefixes = {value >> 16 for value in removed}
    if any((value >> 16) in emptied_prefixes and value in kept for value in kept):
        # A prefix counts as emptied only when no kept value remains under it.
        pass
    still = {value >> 16 for value in kept}
    if not (emptied_prefixes - still):
        raise HarnessError("slack workload emptied no high prefix")
    if len(kept) < 2:
        raise HarnessError("slack workload kept fewer than two values")
    return {
        "inserted": shuffle_not_sorted(inserted),
        "removed": removed,
        "kept": sorted(kept),
    }


def shrink_search_inputs() -> tuple[list[int], list[int], list[int], list[int]]:
    """Many same-prefix populations, each with one value marked to drop.

    Counts run across a runtime window that is not 30..46. Whether any
    shrink already has the length of a direct remainder compact is not
    required: packing, and whether an in-place shrink shortens the buffer,
    are not scored.
    """
    origin = runtime_count(2, 9)
    counts = list(range(origin, origin + 22))
    inserted: list[int] = []
    remainders: list[int] = []
    widths: list[int] = []
    drops: list[int] = []
    blocked: set[int] = {0}
    forbidden: set[int] = set(F05_NAMED_U64)
    for count in counts:
        if count < 2:
            raise HarnessError(f"shrink population {count} cannot drop one and keep one")
        prefix = _fresh_prefix(blocked)
        blocked.add(prefix)
        values = values_under_prefix(prefix, count, forbidden)
        forbidden.update(values)
        order = shuffle_not_sorted(values)
        drop_at = secrets.randbelow(count)
        dropped = order[drop_at]
        rest = sorted(value for value in order if value != dropped)
        if len(rest) != count - 1:
            raise HarnessError("shrink remainder lost more than the dropped value")
        if any((value >> 16) != prefix for value in rest):
            raise HarnessError("shrink remainder left its prefix")
        inserted.extend(order)
        remainders.extend(rest)
        widths.append(count)
        drops.append(drop_at)
    return inserted, remainders, widths, drops


def two_routes() -> tuple[list[int], list[int], list[int]]:
    """A final set, extras whose removal empties a prefix, and the shuffled union.

    Returns ``(shuffled_union, removed, sorted_final)``.
    """
    forbidden: set[int] = set(F05_NAMED_U64)
    blocked: set[int] = {0}
    final_groups: list[list[int]] = []
    for _ in range(runtime_count(3, 6)):
        prefix = _fresh_prefix(blocked)
        blocked.add(prefix)
        group = values_under_prefix(prefix, runtime_count(2, 8), forbidden)
        forbidden.update(group)
        final_groups.append(group)
    final = [value for group in final_groups for value in group]
    extra_groups: list[list[int]] = []
    for _ in range(runtime_count(2, 4)):
        prefix = _fresh_prefix(blocked)
        blocked.add(prefix)
        group = values_under_prefix(prefix, runtime_count(1, 3), forbidden)
        forbidden.update(group)
        extra_groups.append(group)
    removed = [value for group in extra_groups for value in group]
    union = final + removed
    if len(set(union)) != len(union):
        raise HarnessError("two-route construction repeated a value")
    return shuffle_not_sorted(union), removed, sorted(final)


def fresh_high_prefix_values(existing: Sequence[int], count: int) -> list[int]:
    """*count* values under one high-48 prefix that *existing* does not use."""
    blocked = {value >> 16 for value in existing}
    blocked.add(0)
    prefix = _fresh_prefix(blocked)
    forbidden = set(existing) | set(F05_NAMED_U64)
    return values_under_prefix(prefix, count, forbidden)


_GATE_ZIG = r"""
const Gate = struct {
    parent: std.mem.Allocator,
    live: usize = 0,
    block: bool = false,
    refused: usize = 0,

    fn allocator(self: *Gate) std.mem.Allocator {
        return .{
            .ptr = self,
            .vtable = &.{
                .alloc = alloc,
                .resize = resize,
                .remap = remap,
                .free = free,
            },
        };
    }

    fn alloc(ctx: *anyopaque, len: usize, alignment: std.mem.Alignment, ret_addr: usize) ?[*]u8 {
        const self: *Gate = @ptrCast(@alignCast(ctx));
        if (self.block) {
            self.refused += 1;
            return null;
        }
        const p = self.parent.vtable.alloc(self.parent.ptr, len, alignment, ret_addr) orelse return null;
        self.live += len;
        return p;
    }

    fn resize(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) bool {
        const self: *Gate = @ptrCast(@alignCast(ctx));
        if (self.block) {
            self.refused += 1;
            return false;
        }
        if (!self.parent.vtable.resize(self.parent.ptr, memory, alignment, new_len, ret_addr)) return false;
        self.live = self.live - memory.len + new_len;
        return true;
    }

    fn remap(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) ?[*]u8 {
        const self: *Gate = @ptrCast(@alignCast(ctx));
        if (self.block) {
            self.refused += 1;
            return null;
        }
        const p = self.parent.vtable.remap(self.parent.ptr, memory, alignment, new_len, ret_addr) orelse return null;
        self.live = self.live - memory.len + new_len;
        return p;
    }

    fn free(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, ret_addr: usize) void {
        const self: *Gate = @ptrCast(@alignCast(ctx));
        self.parent.vtable.free(self.parent.ptr, memory, alignment, ret_addr);
        self.live -= memory.len;
    }
};
"""

_F05_ZIG = r"""
fn valuesMatch(bm: *const klyvmap.Bitmap, sorted: []const u64) bool {
    if (bm.getCardinality() != sorted.len) return false;
    var it = bm.iterator();
    for (sorted) |want| {
        const got = it.next() orelse return false;
        if (got != want) return false;
    }
    return it.next() == null;
}

fn containsAll(bm: *const klyvmap.Bitmap, vals: []const u64) bool {
    for (vals) |v| if (!bm.contains(v)) return false;
    return true;
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

fn buildFrom(alloc: std.mem.Allocator, vals: []const u64) !klyvmap.Bitmap {
    var bm = try klyvmap.Bitmap.init(alloc);
    for (vals) |v| _ = try bm.set(v);
    return bm;
}

fn dropFrom(alloc: std.mem.Allocator, vals: []const u64, gone: []const u64) !void {
    var bm = try buildFrom(alloc, vals);
    defer bm.deinit();
    for (gone) |v| _ = bm.remove(v);
}

fn bytesEqual(a: *const klyvmap.Bitmap, b: *const klyvmap.Bitmap) bool {
    return std.mem.eql(u8, a.toBuffer(), b.toBuffer());
}

fn fillRest(order: []const u64, drop_at: usize, dest: []u64) void {
    var w: usize = 0;
    for (order, 0..) |v, i| {
        if (i == drop_at) continue;
        dest[w] = v;
        w += 1;
    }
}
"""


def wrap_f05_probe(body: str) -> str:
    """Wrap *body* with the allocation gate used for the second-compact arms.

    ``allocator`` is that gate. ``init.gpa`` is for snapshots the gate must
    not count. ``gate.block`` refuses every allocation until cleared.
    """
    return (
        ZIG_PRELUDE
        + "\n"
        + _GATE_ZIG
        + "\n"
        + _F05_ZIG
        + "\nfn run(init: std.process.Init, allocator: std.mem.Allocator, gate: *Gate) !void {\n"
        + "    comptime { _ = valuesMatch; _ = containsAll; _ = shapeOf; _ = buildFrom; _ = dropFrom; _ = bytesEqual; _ = fillRest; }\n"
        + body
        + "\n}\n\n"
        + "pub fn main(init: std.process.Init) !void {\n"
        + "    var gate: Gate = .{ .parent = init.gpa };\n"
        + "    try run(init, gate.allocator(), &gate);\n"
        + "}\n"
    )


def wrap_f05_tracking(body: str) -> str:
    """Tracking-allocator probe with the compact comparisons in scope."""
    src = wrap_probe_body(body)
    marker = "\nfn run("
    idx = src.find(marker)
    if idx < 0:
        raise HarnessError("wrap_probe_body produced no run function")
    src = src[:idx] + "\n" + _F05_ZIG + src[idx:]
    needle = "    const alloc_anchor = allocator;\n"
    insert = (
        needle
        + "    comptime { _ = valuesMatch; _ = containsAll; _ = shapeOf; _ = buildFrom; _ = dropFrom; _ = bytesEqual; _ = fillRest; }\n"
    )
    if needle not in src:
        raise HarnessError("tracking probe has no alloc anchor")
    return src.replace(needle, insert, 1)


# Re-export sealed helpers the acceptance module calls by one name.
__all__ = [
    "fill_u64",
    "require_bool_field",
    "require_empty_snapshot",
    "require_emit_shape",
    "require_int_field",
    "require_no_integer",
    "require_positive_buffer_length",
    "require_strictly_ascending_once",
    "run_bitmap_probe",
    "unpublished_u64_f05",
    "zig_u64_list",
]
