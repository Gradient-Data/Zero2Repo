# feature: F04
"""Observation helpers for emit / open of a klyvmap buffer.

JSON fields are test encoding, not a product output contract. A compile,
a probe exit, a short header, or an allocator log this helper cannot
classify raises. Those outcomes are never reported as an empty bitmap,
a refused open, or "bytes unchanged".
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import secrets
import select
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from F01_helpers import (
    ZIG_PRELUDE,
    _PTRACE_EVENT_CLONE,
    _PTRACE_EVENT_FORK,
    _PTRACE_EVENT_VFORK,
    _PTRACE_GETEVENTMSG,
    _PTRACE_GET_SYSCALL_INFO,
    _PTRACE_O_TRACECLONE,
    _PTRACE_O_TRACEEXEC,
    _PTRACE_O_TRACEFORK,
    _PTRACE_O_TRACESYSGOOD,
    _PTRACE_O_TRACEVFORK,
    _PTRACE_SETOPTIONS,
    _PTRACE_SYSCALL,
    _PTRACE_SYSCALL_INFO_ENTRY,
    _PTRACE_TRACEME,
    _PtraceSyscallInfo,
    _WAIT_WALL,
    _drain_pipe,
    _libc,
    _ptrace,
    _ptrace_ptr,
    _syscall_nr_at_stop,
    require_empty_snapshot,
    require_positive_buffer_length,
)
from F02_helpers import (
    F02_NAMED_U64_SAMPLES,
    require_bool_field,
    require_int_field,
)
from F03_helpers import F03_NAMED_U64_SAMPLES, unpublished_u64_f03
from _helpers import DEFAULT_TIMEOUT, HarnessError, RunResult, repo_root

# Values this feature's PRD names, plus earlier public samples.
F04_NAMED_U64 = frozenset(
    {
        0,
        7,
        42,
        100,
        2999 * 7,
        (1 << 64) - 1,
    }
)

_BLOCKED_U64 = frozenset(F02_NAMED_U64_SAMPLES) | frozenset(F03_NAMED_U64_SAMPLES) | F04_NAMED_U64

U64_MAX = (1 << 64) - 1


def unpublished_u64_f04(
    forbidden: set[int] | frozenset[int] | None = None,
    *,
    above: int | None = None,
) -> int:
    """A 64-bit value F01–F04 public materials do not name.

    Raises if the draw lands on a named sample or on *forbidden*.
    """
    extra = set(F04_NAMED_U64)
    if forbidden is not None:
        extra.update(forbidden)
    value = unpublished_u64_f03(extra, above=above)
    if value in extra or value in _BLOCKED_U64:
        raise HarnessError(
            f"unpublished_u64_f04 collided with a forbidden value: {value}"
        )
    return value


def unpublished_population_f04(count: int) -> list[int]:
    """*count* distinct unpublished values. *count* must not be 0, 100, or 3000."""
    if count <= 0:
        raise HarnessError(f"population count {count} is empty")
    values: list[int] = []
    forbidden: set[int] = set()
    while len(values) < count:
        value = unpublished_u64_f04(forbidden=forbidden)
        if value in forbidden:
            raise HarnessError(f"population redraw collided: {value}")
        forbidden.add(value)
        values.append(value)
    return values


def unpublished_count_f04() -> int:
    """A set size that is not the named 0, 100, or 3000."""
    count = 4 + secrets.randbelow(9)
    if count in (0, 100, 3000):
        raise HarnessError(f"unpublished count landed on a named size: {count}")
    return count


def prefix_seed_f04() -> tuple[int, list[int]]:
    """Two unpublished values that share one high-48-bit prefix.

    The prefix is not 0 and is not a prefix of a named sample. Raises if
    no such pair appears.
    """
    blocked_prefixes = {value >> 16 for value in _BLOCKED_U64}
    blocked_prefixes.add(0)
    for _ in range(64):
        prefix = 1 + secrets.randbelow((1 << 48) - 2)
        if prefix in blocked_prefixes:
            continue
        lows: list[int] = []
        while len(lows) < 2:
            low = secrets.randbelow(1 << 16)
            if low not in lows:
                lows.append(low)
        values = [(prefix << 16) | low for low in lows]
        if any(value in _BLOCKED_U64 for value in values):
            continue
        return prefix, values
    raise HarnessError("could not draw an unpublished same-prefix seed")


def same_prefix_candidates_f04(prefix: int, present: Sequence[int], limit: int = 8) -> list[int]:
    """Unpublished values under *prefix* that are not already present."""
    if limit < 1:
        raise HarnessError("candidate limit must be positive")
    used = {value & 0xFFFF for value in present}
    found: list[int] = []
    for _ in range(256):
        if len(found) == limit:
            return found
        low = secrets.randbelow(1 << 16)
        if low in used:
            continue
        value = (prefix << 16) | low
        if value in _BLOCKED_U64:
            continue
        used.add(low)
        found.append(value)
    raise HarnessError("could not draw same-prefix candidates")


def fresh_high_prefix_f04(prefixes: Sequence[int]) -> int:
    """An unpublished value whose high 48 bits are not in *prefixes*."""
    blocked = set(prefixes)
    for _ in range(32):
        value = unpublished_u64_f04()
        if (value >> 16) not in blocked:
            return value
    raise HarnessError("could not draw a value on a fresh high-48 prefix")


def dense_and_sparse_f04(*, dense_blocks: int, sparse_count: int) -> tuple[int, list[int], list[int]]:
    """A run of full high-48 prefixes plus scattered single values.

    Returns ``(dense_base, sparse, absent)``: prefixes ``dense_base ..
    dense_base + dense_blocks - 1`` are to be filled with all 65536 values;
    *sparse* are unpublished values each on its own prefix outside that run;
    *absent* are values next to the run and next to sparse values that none
    of those holds.
    """
    blocked = {value >> 16 for value in _BLOCKED_U64} | {0}
    for _ in range(64):
        dense_base = 2 + secrets.randbelow((1 << 48) - dense_blocks - 4)
        run = set(range(dense_base - 1, dense_base + dense_blocks + 1))
        if run & blocked:
            continue
        sparse: list[int] = []
        used = set(run)
        while len(sparse) < sparse_count:
            value = unpublished_u64_f04(forbidden=set(sparse))
            if (value >> 16) in used:
                continue
            used.add(value >> 16)
            sparse.append(value)
        absent = [(dense_base << 16) - 1, (dense_base + dense_blocks) << 16]
        for value in sparse[:32]:
            other = value ^ (1 + secrets.randbelow(0xFFFF))
            if other >> 16 != value >> 16 or other in sparse:
                raise HarnessError("could not place an absent value beside a sparse one")
            absent.append(other)
        return dense_base, sparse, absent
    raise HarnessError("could not draw an unpublished dense run")


# Even lengths below the PRD's floor for the shortest buffer that can be a
# bitmap (at least 8 bytes): every one of them is "too short", whatever
# minimum the implementation chose.
TINY_EVEN_LENGTHS = (2, 4, 6)


def unpublished_short_even_f04() -> int:
    """A tiny even length (below 8) that is not 0, 2, or 6."""
    choices = [n for n in TINY_EVEN_LENGTHS if n not in (0, 2, 6)]
    if not choices:
        raise HarnessError("no unpublished short even length")
    return secrets.choice(choices)


def unpublished_odd_f04(avoid: int) -> int:
    """An odd length that is not 65 and not *avoid*."""
    choices = [n for n in range(1, 63, 2) if n != 65 and n != avoid]
    if not choices:
        raise HarnessError("no unpublished odd length")
    return secrets.choice(choices)


def unpublished_residue_f04() -> int:
    """A byte offset mod 8 that is neither 0 nor 2."""
    return secrets.choice((1, 3, 4, 5, 6, 7))


def unpublished_body_byte_f04() -> int:
    """A payload byte for a buffer this product did not emit.

    Not 0 and not 1, so the body is not a zero fill and not a version-1 tail.
    """
    return secrets.randbelow(254) + 2


def unpublished_version_value_f04() -> int:
    """A version byte that is not 1 and not one of the named 0, 2, 3, or 255."""
    return 4 + secrets.randbelow(251)


def require_emit_shape(
    report: Mapping[str, Any],
    *,
    length: str,
    b0: str | None = None,
    b1: str | None = None,
    residue: str,
) -> int:
    """Positive even length, address mod 8 is 0.

    *b0* / *b1* are accepted for older probes and ignored: where the format
    version sits is the implementer's choice, and the version-1 stamp is
    checked against the position derived from the implementation's own
    emits (:func:`format_version_offset`). A missing field or a non-integer
    raises. It is not treated as length 0.
    """
    del b0, b1
    n = require_positive_buffer_length(require_int_field(report, length))
    if n % 2 != 0:
        raise AssertionError(f"emitted length {n} is not even")
    if require_int_field(report, residue) != 0:
        raise AssertionError(
            f"emitted buffer address mod 8 is {report.get(residue)!r}, not 0"
        )
    return n


def require_true_fields(report: Mapping[str, Any], *keys: str) -> None:
    for key in keys:
        if require_bool_field(report, key) is not True:
            raise AssertionError(f"{key} is not true")


def require_false_fields(report: Mapping[str, Any], *keys: str) -> None:
    for key in keys:
        if require_bool_field(report, key) is not False:
            raise AssertionError(f"{key} is not false")


def require_fresh_empty(report: Mapping[str, Any], *, prefix: str = "") -> None:
    """Empty snapshot, then a later set is visible on that bitmap.

    *prefix* selects ``empty`` / ``cardinality`` / ``contains0`` / ``min`` /
    ``max``. ``{prefix}set_visible`` must be true: the fresh bitmap accepted
    a value. ``{prefix}legal_emit`` must be true: its later emit has a
    positive even length and an 8-byte-aligned address.
    """
    require_empty_snapshot(report, prefix=prefix)
    require_true_fields(report, f"{prefix}set_visible", f"{prefix}legal_emit")


_CALENDAR_RELEASE = re.compile(r"^0\.(\d{2})(0[1-9]|1[0-2])\.(\d+)$")




def _strip_zon_comments(text: str) -> str:
    """Drop ``//`` comments. A comment marker inside a string stays."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\n\r":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_top_level_zon_fields(text: str) -> list[tuple[str, str]]:
    """Top-level ``.name = value`` pairs of one zon struct.

    A file that is not a single struct is not a package description.
    Nested values stay inside the field they belong to. A file this
    splitter cannot read raises: silence is not "no release".
    """
    body = _strip_zon_comments(text).strip()
    if not body.startswith(".{") or not body.endswith("}"):
        raise HarnessError("zon text is not a single struct")
    inner = body[2:-1]
    fields: list[tuple[str, str]] = []
    i = 0
    n = len(inner)
    while i < n:
        while i < n and inner[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        if inner[i] != ".":
            raise HarnessError("zon struct field does not start with a dot")
        i += 1
        start = i
        while i < n and (inner[i].isalnum() or inner[i] == "_"):
            i += 1
        name = inner[start:i]
        if name == "":
            raise HarnessError("zon struct field has an empty name")
        while i < n and inner[i] in " \t\r\n":
            i += 1
        if i >= n or inner[i] != "=":
            raise HarnessError(f"zon field {name} has no '='")
        i += 1
        while i < n and inner[i] in " \t\r\n":
            i += 1
        value_start = i
        depth_brace = 0
        depth_paren = 0
        in_string = False
        while i < n:
            ch = inner[i]
            if in_string:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == '"':
                    in_string = False
                i += 1
                continue
            if ch == '"':
                in_string = True
                i += 1
                continue
            if ch == "{":
                depth_brace += 1
            elif ch == "}":
                if depth_brace == 0:
                    raise HarnessError("zon struct ended inside a field value")
                depth_brace -= 1
            elif ch == "(":
                depth_paren += 1
            elif ch == ")":
                if depth_paren == 0:
                    raise HarnessError("zon value has an unmatched ')'")
                depth_paren -= 1
            elif ch == "," and depth_brace == 0 and depth_paren == 0:
                break
            i += 1
        value = inner[value_start:i].strip()
        if value == "":
            raise HarnessError(f"zon field {name} has an empty value")
        fields.append((name, value))
        if i < n and inner[i] == ",":
            i += 1
    return fields


def _zon_string_literal(raw: str) -> str | None:
    """The body of a plain zon string literal, or ``None`` when *raw* is not one."""
    text = raw.strip()
    if len(text) < 2 or text[0] != '"' or text[-1] != '"':
        return None
    body = text[1:-1]
    if '"' in body or "\\" in body:
        return None
    return body


def _declared_release(root: Path) -> str:
    """The ``.version`` string of the package manifest at the repository root.

    The Contract states the form: ``<root>/build.zig.zon`` is one zon
    struct whose top-level field ``.version`` is a string literal holding
    the declared release. A missing file, an unreadable struct, a missing
    field, or a value that is not a string literal fails the read.
    """
    path = root / "build.zig.zon"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AssertionError(f"package manifest {path} is missing") from exc
    except (OSError, UnicodeError) as exc:
        raise AssertionError(f"cannot read package manifest {path}: {exc}") from exc
    try:
        fields = _split_top_level_zon_fields(text)
    except HarnessError as exc:
        raise AssertionError(f"package manifest {path} is not one zon struct: {exc}") from exc
    values = [raw for name, raw in fields if name == "version"]
    if len(values) != 1:
        raise AssertionError(
            f"package manifest {path} has {len(values)} top-level .version fields, expected 1"
        )
    release = _zon_string_literal(values[0])
    if release is None:
        raise AssertionError(
            f"top-level .version of {path} is not a string literal: {values[0]!r}"
        )
    return release


def observe_declared_release_and_format_word() -> tuple[str, int]:
    """The release the Zig package publishes for itself, and an emit's format word.

    The declared release is the top-level ``.version`` string of
    ``build.zig.zon`` at the repository root (the Contract's stated form).
    The format word is the byte of a fresh emit at the format-version
    position derived from the implementation's own emits. A compile or
    probe failure raises.
    """
    from F01_helpers import _fail_if_nonzero, product_run_argv, workspace

    release = _declared_release(repo_root())
    voff = format_version_offset()
    source = wrap_f04_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const view = bm.toBuffer();
    const voff: usize = __VOFF__;
    if (view.len <= voff) return error.ShortEmit;
    const format_word: u16 = view[voff];
    try emitJson(init, init.gpa, "{{\"format_word\":{d}}}", .{format_word});
""".replace("__VOFF__", str(voff))
    )
    with workspace() as ws:
        probe = ws.path / f".f04-release-{secrets.token_hex(4)}.zig"
        created = False
        try:
            probe.write_text(source, encoding="utf-8")
            created = True
            result = ws.run_command(product_run_argv(probe))
        finally:
            if created:
                probe.unlink()
    _fail_if_nonzero(result, what="bitmap probe")
    report = result.stdout_json()
    if not isinstance(report, dict):
        raise HarnessError(f"probe stdout is not a JSON object: {type(report)!r}")
    return release, require_int_field(report, "format_word")


def require_calendar_release_form(version: str) -> None:
    """``version`` must be calendar form ``0.YYMM.patch`` (year-month, then a patch).

    Major is 0. The middle component is a two-digit year and a month 01–12.
    The last component is a patch. ``1.0.0`` is not that form.
    """
    if _CALENDAR_RELEASE.fullmatch(version) is None:
        raise AssertionError(
            f"release version {version!r} is not calendar form 0.YYMM.patch"
        )


def require_big_endian_compile_refused(ws, source: str) -> None:
    """The library must fail to compile for a big-endian target.

    The same source must compile for the host. A program that does not
    import the library must compile for that big-endian triple, so a
    broken triple is not the refusal. A non-zero compile status is the
    refusal. Diagnostic text is not part of the contract.
    """
    from F01_helpers import BIG_ENDIAN_TARGET, compile_product_source

    native = compile_product_source(ws, source, output="probe-native")
    if native.returncode != 0:
        raise HarnessError(
            "native compile of the emit/open probe failed "
            f"(live baseline)\n{native.stderr_text}"
        )
    hello_be = compile_product_source(
        ws,
        "pub fn main() void {}\n",
        relpath="hello.zig",
        output="hello-be",
        target=BIG_ENDIAN_TARGET,
        include_product=False,
    )
    if hello_be.returncode != 0:
        raise HarnessError(
            f"trivial program failed to compile for {BIG_ENDIAN_TARGET}; "
            "the triple is not a usable contrast\n"
            f"{hello_be.stderr_text}"
        )
    product_be = compile_product_source(
        ws,
        source,
        relpath="probe-be.zig",
        output="probe-be",
        target=BIG_ENDIAN_TARGET,
        include_product=True,
    )
    assert product_be.returncode != 0, (
        f"library compiled for big-endian target {BIG_ENDIAN_TARGET}"
    )


_F04_ZIG = r"""
const LOG_CAP: usize = 256;

const Window = struct {
    parent: std.mem.Allocator,
    live: usize = 0,
    watch: bool = false,
    threshold: usize = 0,
    saw_ge: bool = false,
    last_len: usize = 0,
    overflow: bool = false,
    log_n: usize = 0,
    log_lens: [LOG_CAP]usize = undefined,

    fn allocator(self: *Window) std.mem.Allocator {
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

    fn note(self: *Window, len: usize) void {
        self.last_len = len;
        if (!self.watch) return;
        if (self.threshold > 0 and len >= self.threshold) self.saw_ge = true;
        if (self.log_n >= LOG_CAP) {
            self.overflow = true;
            return;
        }
        self.log_lens[self.log_n] = len;
        self.log_n += 1;
    }

    fn alloc(ctx: *anyopaque, len: usize, alignment: std.mem.Alignment, ret_addr: usize) ?[*]u8 {
        const self: *Window = @ptrCast(@alignCast(ctx));
        const p = self.parent.vtable.alloc(self.parent.ptr, len, alignment, ret_addr) orelse return null;
        self.live += len;
        self.note(len);
        return p;
    }

    fn resize(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) bool {
        const self: *Window = @ptrCast(@alignCast(ctx));
        if (!self.parent.vtable.resize(self.parent.ptr, memory, alignment, new_len, ret_addr)) return false;
        self.live = self.live - memory.len + new_len;
        self.note(new_len);
        return true;
    }

    fn remap(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) ?[*]u8 {
        const self: *Window = @ptrCast(@alignCast(ctx));
        const p = self.parent.vtable.remap(self.parent.ptr, memory, alignment, new_len, ret_addr) orelse return null;
        self.live = self.live - memory.len + new_len;
        self.note(new_len);
        return p;
    }

    fn free(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, ret_addr: usize) void {
        const self: *Window = @ptrCast(@alignCast(ctx));
        @memset(memory, 0xa5);
        self.parent.vtable.free(self.parent.ptr, memory, alignment, ret_addr);
        self.live -= memory.len;
    }
};

fn beginWatch(track: *Window, threshold: usize) void {
    track.watch = true;
    track.threshold = threshold;
    track.saw_ge = false;
    track.overflow = false;
    track.log_n = 0;
}

fn endWatch(track: *Window) !void {
    track.watch = false;
    if (track.overflow) return error.AllocLogOverflow;
}

fn positiveControl(track: *Window, n: usize) !void {
    if (n == 0) return error.ZeroControl;
    const before = track.live;
    const p = try track.allocator().alignedAlloc(u8, .@"8", n);
    if (track.last_len < n) return error.ObserverSilent;
    if (track.live < before + n) return error.ObserverSilent;
    track.allocator().free(p);
    if (track.live != before) return error.ObserverSilent;
    const q = try track.allocator().alignedAlloc(u8, .@"8", n);
    if (!(track.live > before)) return error.ObserverSilent;
    track.allocator().free(q);
    if (track.live != before) return error.ObserverSilent;
}

fn viewIsHandedAllocation(bm: *const klyvmap.Bitmap, alloc_ptr: usize, alloc_len: usize) bool {
    const view = bm.toBuffer();
    return view.len == alloc_len and @intFromPtr(view.ptr) == alloc_ptr;
}

fn headerOf(buf: []const u8) !struct { len: usize, b0: u8, b1: u8, res: usize } {
    if (buf.len < 2) return error.ShortHeader;
    return .{
        .len = buf.len,
        .b0 = buf[0],
        .b1 = buf[1],
        .res = @intFromPtr(buf.ptr) % 8,
    };
}

fn shapeOk(buf: []const u8) bool {
    if (buf.len == 0 or buf.len % 2 != 0) return false;
    return @intFromPtr(buf.ptr) % 8 == 0;
}

fn emptySnap(bm: *const klyvmap.Bitmap) bool {
    return bm.isEmpty() and bm.getCardinality() == 0 and !bm.contains(0) and bm.minimum() == null and bm.maximum() == null;
}

fn membersExact(bm: *const klyvmap.Bitmap, vals: []const u64, absent: u64) bool {
    if (bm.getCardinality() != vals.len) return false;
    for (vals) |v| {
        if (!bm.contains(v)) return false;
    }
    return !bm.contains(absent);
}

fn iterExact(bm: *const klyvmap.Bitmap, sorted: []const u64) bool {
    var it = bm.iterator();
    for (sorted) |w| {
        const got = it.next() orelse return false;
        if (got != w) return false;
    }
    return it.next() == null;
}

fn arrayExact(bm: *const klyvmap.Bitmap, alloc: std.mem.Allocator, sorted: []const u64) !bool {
    const arr = try bm.toArray(alloc);
    defer alloc.free(arr);
    if (arr.len != sorted.len) return false;
    for (sorted, arr) |w, g| {
        if (w != g) return false;
    }
    return true;
}

fn extremaExact(bm: *const klyvmap.Bitmap, want_min: u64, want_max: u64) bool {
    const mn = bm.minimum() orelse return false;
    const mx = bm.maximum() orelse return false;
    return mn == want_min and mx == want_max;
}

const Opened = struct {
    yielded: bool = false,
    bm: klyvmap.Bitmap = undefined,
    storage: []align(8) u8 = undefined,
    have_storage: bool = false,
    before: usize = 0,
    held: usize = 0,
    ptr: usize = 0,
};

fn openMode(track: *Window, src: []const u8, own: bool) !Opened {
    const before = track.live;
    const buf = try track.allocator().alignedAlloc(u8, .@"8", src.len);
    if (src.len != 0) @memcpy(buf, src);
    const held = track.live;
    const ptr = @intFromPtr(buf.ptr);
    if (own) {
        if (klyvmap.Bitmap.fromBuffer(track.allocator(), buf, .own)) |bm| {
            return .{ .yielded = true, .bm = bm, .have_storage = false, .before = before, .held = held, .ptr = ptr };
        } else |_| {
            return .{ .yielded = false, .have_storage = false, .before = before, .held = held, .ptr = ptr };
        }
    }
    if (klyvmap.Bitmap.fromBuffer(track.allocator(), buf, .borrow)) |bm| {
        return .{ .yielded = true, .bm = bm, .storage = buf, .have_storage = true, .before = before, .held = held, .ptr = ptr };
    } else |_| {
        return .{ .yielded = false, .storage = buf, .have_storage = true, .before = before, .held = held, .ptr = ptr };
    }
}

fn openCopy(track: *Window, src: []const u8) !Opened {
    const before = track.live;
    if (klyvmap.Bitmap.fromBufferCopy(track.allocator(), src)) |bm| {
        return .{ .yielded = true, .bm = bm, .before = before, .held = track.live };
    } else |_| {
        return .{ .yielded = false, .before = before, .held = track.live };
    }
}

fn releaseOpened(track: *Window, opened: *Opened) void {
    _ = track;
    if (opened.yielded) opened.bm.deinit();
    opened.yielded = false;
}

fn callerFree(track: *Window, opened: *Opened) void {
    if (opened.have_storage) {
        track.allocator().free(opened.storage);
        opened.have_storage = false;
    }
}

fn copyPrefix(buf: []u8, template: []const u8) void {
    @memset(buf, 0);
    const n = @min(buf.len, template.len);
    if (n != 0) @memcpy(buf[0..n], template[0..n]);
}

fn app(buf: []u8, i: *usize, s: []const u8) !void {
    if (i.* + s.len > buf.len) return error.JsonOverflow;
    @memcpy(buf[i.*..][0..s.len], s);
    i.* += s.len;
}

fn appFmt(buf: []u8, i: *usize, gpa: std.mem.Allocator, comptime fmt: []const u8, args: anytype) !void {
    const s = try std.fmt.allocPrint(gpa, fmt, args);
    defer gpa.free(s);
    try app(buf, i, s);
}

fn appSnap(buf: []u8, i: *usize, gpa: std.mem.Allocator, name: []const u8, bm: *const klyvmap.Bitmap) !void {
    const min_j = try optU64Json(gpa, bm.minimum());
    defer gpa.free(min_j);
    const max_j = try optU64Json(gpa, bm.maximum());
    defer gpa.free(max_j);
    try appFmt(buf, i, gpa,
        "\"{s}empty\":{s},\"{s}cardinality\":{d},\"{s}contains0\":{s},\"{s}min\":{s},\"{s}max\":{s}",
        .{ name, jsonBool(bm.isEmpty()), name, bm.getCardinality(), name, jsonBool(bm.contains(0)), name, min_j, name, max_j });
}

const Modes = struct {
    borrow_yield: bool = false,
    own_yield: bool = false,
    copy_yield: bool = false,
    borrow_fresh: bool = false,
    own_fresh: bool = false,
    copy_fresh: bool = false,
    own_baseline: bool = false,
    borrow_caller_same: bool = false,
    borrow_held: bool = false,
    copy_source_same: bool = false,
    copy_owns: bool = false,
    copy_released: bool = false,
};

fn dropBorrow(track: *Window, opened: *Opened) void {
    releaseOpened(track, opened);
    if (opened.have_storage and track.live == opened.held) callerFree(track, opened);
}

fn freshModes(track: *Window, gpa: std.mem.Allocator, src: []const u8, newv: u64, banned: u64, have_banned: bool) !Modes {
    var result: Modes = .{};
    var borrowed = try openMode(track, src, false);
    result.borrow_yield = borrowed.yielded;
    if (borrowed.yielded) {
        const snap = try gpa.dupe(u8, borrowed.storage);
        defer gpa.free(snap);
        const was_empty = emptySnap(&borrowed.bm);
        const banned_absent = !have_banned or !borrowed.bm.contains(banned);
        _ = try borrowed.bm.set(newv);
        const visible = borrowed.bm.contains(newv) and borrowed.bm.getCardinality() == 1;
        const legal = shapeOk(borrowed.bm.toBuffer());
        result.borrow_fresh = was_empty and banned_absent and visible and legal;
        result.borrow_caller_same = std.mem.eql(u8, borrowed.storage, snap);
        const held = borrowed.held;
        const before = borrowed.before;
        releaseOpened(track, &borrowed);
        const still = track.live == held;
        if (borrowed.have_storage and track.live == held) callerFree(track, &borrowed);
        result.borrow_held = still and track.live == before;
    } else {
        result.borrow_caller_same = borrowed.have_storage and std.mem.eql(u8, borrowed.storage, src);
        const held = track.live == borrowed.held;
        const before = borrowed.before;
        dropBorrow(track, &borrowed);
        result.borrow_held = held and track.live == before;
    }

    var owned = try openMode(track, src, true);
    result.own_yield = owned.yielded;
    if (owned.yielded) {
        const was_empty = emptySnap(&owned.bm);
        const banned_absent = !have_banned or !owned.bm.contains(banned);
        _ = try owned.bm.set(newv);
        const visible = owned.bm.contains(newv) and owned.bm.getCardinality() == 1;
        const legal = shapeOk(owned.bm.toBuffer());
        result.own_fresh = was_empty and banned_absent and visible and legal;
        const before = owned.before;
        releaseOpened(track, &owned);
        result.own_baseline = track.live == before;
    } else {
        result.own_baseline = track.live == owned.before;
    }

    const src_snap = try gpa.dupe(u8, src);
    defer gpa.free(src_snap);
    const before_copy = track.live;
    var copied = try openCopy(track, src);
    result.copy_yield = copied.yielded;
    if (copied.yielded) {
        const view = copied.bm.toBuffer();
        result.copy_owns = view.len > 0 and track.live >= before_copy + view.len;
        const was_empty = emptySnap(&copied.bm);
        const banned_absent = !have_banned or !copied.bm.contains(banned);
        _ = try copied.bm.set(newv);
        const visible = copied.bm.contains(newv) and copied.bm.getCardinality() == 1;
        const legal = shapeOk(copied.bm.toBuffer());
        result.copy_fresh = was_empty and banned_absent and visible and legal;
        result.copy_source_same = std.mem.eql(u8, src, src_snap);
        releaseOpened(track, &copied);
        result.copy_released = track.live == before_copy;
    }
    return result;
}

fn versionModes(track: *Window, src: []const u8) !Modes {
    var result: Modes = .{};
    var borrowed = try openMode(track, src, false);
    result.borrow_yield = borrowed.yielded;
    if (borrowed.have_storage) result.borrow_caller_same = std.mem.eql(u8, borrowed.storage, src);
    const held = !borrowed.yielded and track.live == borrowed.held;
    const before = borrowed.before;
    if (borrowed.yielded) releaseOpened(track, &borrowed);
    if (borrowed.have_storage and track.live == borrowed.held) callerFree(track, &borrowed);
    result.borrow_held = held and track.live == before;

    var owned = try openMode(track, src, true);
    result.own_yield = owned.yielded;
    if (owned.yielded) releaseOpened(track, &owned);
    result.own_baseline = track.live == owned.before;

    const before_copy = track.live;
    var copied = try openCopy(track, src);
    result.copy_yield = copied.yielded;
    if (copied.yielded) releaseOpened(track, &copied);
    result.copy_released = track.live == before_copy;
    return result;
}
"""


def walk_regular_files_through_cache(root: Path) -> set[Path]:
    """Regular files under *root*, including ``zig-cache`` and ``.cache``.

    A missing root is an empty set. Any other stat failure raises: a
    walk that cannot see a path is not "no file".
    """
    found: set[Path] = set()
    try:
        if not root.exists():
            return found
    except OSError as exc:
        raise HarnessError(f"cannot stat {root}: {exc}") from exc
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.is_file() and not path.is_symlink():
                    found.add(path.resolve())
            except OSError as exc:
                raise HarnessError(f"cannot stat {path}: {exc}") from exc
    return found


def files_created_through_cache(
    *,
    before: set[Path],
    roots: Sequence[Path],
) -> set[Path]:
    """Regular files under *roots* that were not in *before*.

    Directories named zig-cache or .cache are entered. A file created
    inside one of those names during the run is part of the result.
    Files already present in *before* — including a compiler cache that
    existed before the run — are not.
    """
    after: set[Path] = set()
    for root in roots:
        after |= walk_regular_files_through_cache(root)
    return after - before


def wrap_f04_probe(body: str) -> str:
    """Wrap a probe body with the allocation-window observer.

    The product allocator is that observer. ``init.gpa`` is only for
    snapshots the observer must not count.
    """
    src = (
        ZIG_PRELUDE
        + "\n"
        + _F04_ZIG
        + "\nfn run(init: std.process.Init, allocator: std.mem.Allocator, track: *Window) !void {\n"
        + "    const alloc_anchor = allocator;\n"
        + "    _ = alloc_anchor;\n"
        + "    const track_anchor = track;\n"
        + "    _ = track_anchor;\n"
        + body
        + "\n}\n\n"
        + "pub fn main(init: std.process.Init) !void {\n"
        + "    var track: Window = .{ .parent = init.gpa };\n"
        + "    try run(init, track.allocator(), &track);\n"
        + "}\n"
    )
    return src


# ---------------------------------------------------------------------------
# Where the format version sits (derived, not assumed)
# ---------------------------------------------------------------------------
#
# The PRD fixes that every buffer carries a format-version field holding 1,
# at the same position in every buffer, and that opening a large-enough
# buffer whose field does not hold 1 is refused. Width and position are the
# implementer's choice. The tests therefore read the position off the
# implementation's own emits: candidates are byte positions that hold 1 in
# every emitted buffer of a varied corpus; the version position is the first
# candidate where changing that byte to 2 is refused on every open path while
# the unchanged buffer opens. A candidate whose change makes a probe exit
# abnormally is not the version field (beyond the version check, a buffer
# is trusted input).

_VERSION_OFFSET_CACHE: list[int] = []
_VERSION_CANDIDATE_LIMIT = 16

_CORPUS_ZIG = r"""
    const sparse = [_]u64{ __SPARSE__ };
    const sorted = [_]u64{ __SORTED__ };
    const dense_base: u64 = __DENSE__;
    var bufs: [16][]u8 = undefined;
    var nb: usize = 0;
    defer {
        for (bufs[0..nb]) |b| init.gpa.free(b);
    }
    {
        var bm = try klyvmap.Bitmap.init(allocator);
        defer bm.deinit();
        bufs[nb] = try init.gpa.dupe(u8, bm.toBuffer());
        nb += 1;
        try bm.compact();
        bufs[nb] = try init.gpa.dupe(u8, bm.toBuffer());
        nb += 1;
        _ = try bm.set(0);
        bufs[nb] = try init.gpa.dupe(u8, bm.toBuffer());
        nb += 1;
    }
    var sp = try klyvmap.Bitmap.init(allocator);
    defer sp.deinit();
    for (sparse) |v| _ = try sp.set(v);
    bufs[nb] = try init.gpa.dupe(u8, sp.toBuffer());
    nb += 1;
    var dn = try klyvmap.Bitmap.init(allocator);
    defer dn.deinit();
    var k: u64 = 0;
    while (k < 5000) : (k += 1) _ = try dn.set(dense_base + k);
    bufs[nb] = try init.gpa.dupe(u8, dn.toBuffer());
    nb += 1;
    {
        var u = try klyvmap.Bitmap.Or(allocator, &sp, &dn);
        defer u.deinit();
        bufs[nb] = try init.gpa.dupe(u8, u.toBuffer());
        nb += 1;
        try u.compact();
        bufs[nb] = try init.gpa.dupe(u8, u.toBuffer());
        nb += 1;
    }
    {
        var x = try klyvmap.Bitmap.And(allocator, &sp, &dn);
        defer x.deinit();
        bufs[nb] = try init.gpa.dupe(u8, x.toBuffer());
        nb += 1;
    }
    {
        const ptrs = [_]*const klyvmap.Bitmap{ &sp, &dn };
        var f = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
        defer f.deinit();
        bufs[nb] = try init.gpa.dupe(u8, f.toBuffer());
        nb += 1;
    }
    {
        var c = try sp.clone();
        defer c.deinit();
        for (sparse[0 .. sparse.len / 2]) |v| _ = c.remove(v);
        c.cleanup();
        bufs[nb] = try init.gpa.dupe(u8, c.toBuffer());
        nb += 1;
        c.andNotInPlace(&sp);
        c.cleanup();
        bufs[nb] = try init.gpa.dupe(u8, c.toBuffer());
        nb += 1;
    }
    {
        var s = try klyvmap.Bitmap.fromSortedList(allocator, &sorted);
        defer s.deinit();
        bufs[nb] = try init.gpa.dupe(u8, s.toBuffer());
        nb += 1;
    }
    {
        var o = try klyvmap.Bitmap.fromBufferCopy(allocator, sp.toBuffer());
        defer o.deinit();
        _ = try o.set(dense_base);
        bufs[nb] = try init.gpa.dupe(u8, o.toBuffer());
        nb += 1;
    }
    var minlen: usize = std.math.maxInt(usize);
    for (bufs[0..nb]) |b| minlen = @min(minlen, b.len);
    var raw: [4096]u8 = undefined;
    var i: usize = 0;
    try appFmt(&raw, &i, init.gpa, "{{\"n\":{d},\"minlen\":{d},\"cands\":[", .{ nb, minlen });
    var found: usize = 0;
    var off: usize = 0;
    while (off < minlen and found < 256) : (off += 1) {
        var all_one = true;
        for (bufs[0..nb]) |b| {
            if (b[off] != 1) all_one = false;
        }
        if (!all_one) continue;
        if (found != 0) try app(&raw, &i, ",");
        try appFmt(&raw, &i, init.gpa, "{d}", .{off});
        found += 1;
    }
    try app(&raw, &i, "]}");
    try writeStdout(init, raw[0..i]);
"""

_CANDIDATE_ZIG = r"""
    const vals = [_]u64{ __VALS__ };
    const voff: usize = __VOFF__;
    var built = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try built.set(v);
    const full = try init.gpa.dupe(u8, built.toBuffer());
    defer init.gpa.free(full);
    built.deinit();
    var fresh = try klyvmap.Bitmap.init(allocator);
    const empty = try init.gpa.dupe(u8, fresh.toBuffer());
    defer init.gpa.free(empty);
    fresh.deinit();
    if (voff >= full.len or voff >= empty.len) return error.OffsetOutside;
    var control = try openMode(track, full, false);
    if (!control.yielded) return error.ControlFailed;
    const control_has = control.bm.contains(vals[0]) and control.bm.getCardinality() == vals.len;
    releaseOpened(track, &control);
    callerFree(track, &control);
    const pf = try init.gpa.dupe(u8, full);
    defer init.gpa.free(pf);
    pf[voff] = 2;
    const pe = try init.gpa.dupe(u8, empty);
    defer init.gpa.free(pe);
    pe[voff] = 2;
    const mf = try versionModes(track, pf);
    const me = try versionModes(track, pe);
    try emitJson(init, init.gpa,
        "{{\"control_has\":{s},\"f_borrow\":{s},\"f_own\":{s},\"f_copy\":{s},\"e_borrow\":{s},\"e_own\":{s},\"e_copy\":{s}}}",
        .{
            jsonBool(control_has), jsonBool(mf.borrow_yield), jsonBool(mf.own_yield), jsonBool(mf.copy_yield),
            jsonBool(me.borrow_yield), jsonBool(me.own_yield), jsonBool(me.copy_yield),
        },
    );
"""


def _zig_u64s(values: Sequence[int]) -> str:
    return ", ".join(str(v) for v in values)


def format_version_offset() -> int:
    """Byte position of the format-version field, read off the product's own emits.

    Raises ``AssertionError`` when no position holds 1 in every emitted
    buffer, or when no such position acts as the format version (changing
    it is not refused on every open path). The result is cached for the
    session: the implementation under test does not change between tests.
    """
    if _VERSION_OFFSET_CACHE:
        return _VERSION_OFFSET_CACHE[0]
    from F01_helpers import run_bitmap_probe

    sparse: list[int] = [U64_MAX, 1 << 40]
    while len(sparse) < 48:
        value = unpublished_u64_f04(forbidden=set(sparse))
        sparse.append(value)
    dense_base = 0
    while dense_base == 0 or any(dense_base <= v < dense_base + 5000 for v in sparse):
        dense_base = (1 + secrets.randbelow((1 << 47) - 2)) << 16
    corpus = wrap_f04_probe(
        _CORPUS_ZIG.replace("__SPARSE__", _zig_u64s(sparse))
        .replace("__SORTED__", _zig_u64s(sorted(set(sparse))))
        .replace("__DENSE__", str(dense_base))
    )
    report = run_bitmap_probe(corpus)
    cands = report.get("cands")
    if not isinstance(cands, list) or not all(isinstance(c, int) for c in cands):
        raise HarnessError(f"corpus probe returned no candidate list: {report!r}")
    if not cands:
        raise AssertionError(
            "no byte position holds 1 in every emitted buffer: no format-version "
            "field holding 1 is stamped into every buffer"
        )
    vals = sparse[2:12]
    tried: list[str] = []
    for off in cands[:_VERSION_CANDIDATE_LIMIT]:
        probe = wrap_f04_probe(
            _CANDIDATE_ZIG.replace("__VALS__", _zig_u64s(vals)).replace("__VOFF__", str(off))
        )
        try:
            rep = run_bitmap_probe(probe)
        except HarnessError as exc:
            tried.append(f"{off}: probe exited abnormally ({str(exc).splitlines()[0]})")
            continue
        yields = [require_bool_field(rep, k) for k in ("f_borrow", "f_own", "f_copy", "e_borrow", "e_own", "e_copy")]
        if require_bool_field(rep, "control_has") is True and not any(yields):
            _VERSION_OFFSET_CACHE.append(off)
            return off
        tried.append(f"{off}: control={rep.get('control_has')!r} yields={yields}")
    raise AssertionError(
        "no byte position that holds 1 in every emitted buffer acts as the format "
        "version (changing it to 2 is not refused on every open path): "
        + "; ".join(tried)
    )


# Linux open(2) intent bits. A read-only open is not a file write.
_O_ACCMODE = 0o3
_O_WRONLY = 0o1
_O_RDWR = 0o2
_O_CREAT = 0o100
_O_TRUNC = 0o1000
_O_APPEND = 0o2000

# (syscall number) -> (name, kind, arg index of fd or flags).
# kind "fd" ignores writes to stdin/stdout/stderr. kind "flags" is an
# open-family call. kind "creat" always creates a file.
_X86_FILE_WRITES = {
    1: ("write", "fd", 0),
    2: ("open", "flags", 1),
    18: ("pwrite64", "fd", 0),
    20: ("writev", "fd", 0),
    85: ("creat", "creat", 0),
    257: ("openat", "flags", 2),
    296: ("pwritev", "fd", 0),
    328: ("pwritev2", "fd", 0),
    437: ("openat2", "openat2", 0),
}
# asm-generic unistd: 69 is preadv (read table), 70 is pwritev.
# Write classification runs first, so 69 must not be labeled a write.
_AARCH64_FILE_WRITES = {
    56: ("openat", "flags", 2),
    64: ("write", "fd", 0),
    66: ("writev", "fd", 0),
    68: ("pwrite64", "fd", 0),
    70: ("pwritev", "fd", 0),
    276: ("renameat2", "rename", 0),
    437: ("openat2", "openat2", 0),
}


def _file_write_table() -> dict[int, tuple[str, str, int]]:
    machine = platform.machine()
    if machine in {"x86_64", "amd64"}:
        return _X86_FILE_WRITES
    if machine in {"aarch64", "arm64"}:
        return _AARCH64_FILE_WRITES
    raise HarnessError(f"no file-write syscall table for {machine}")


def _open_flags_write(flags: int) -> bool:
    access = flags & _O_ACCMODE
    if access in {_O_WRONLY, _O_RDWR}:
        return True
    return bool(flags & (_O_CREAT | _O_TRUNC | _O_APPEND))


# Read-family syscalls. (number) -> (name, fd arg index).
# A read-only open is classified separately from the write table.
_X86_FILE_READS = {
    0: ("read", 0),
    17: ("pread64", 0),
    19: ("readv", 0),
    295: ("preadv", 0),
    327: ("preadv2", 0),
}
_AARCH64_FILE_READS = {
    63: ("read", 0),
    65: ("readv", 0),
    67: ("pread64", 0),
    69: ("preadv", 0),
    286: ("preadv2", 0),
}
_AT_FDCWD = -100
# The dynamic linker reads these without mapping them. They are the
# loader's own files, not a path the library probe needed.
_LOADER_UNMAPPED = ("/etc/ld.so.cache", "/etc/ld.so.preload")


def _file_read_table() -> dict[int, tuple[str, int]]:
    machine = platform.machine()
    if machine in {"x86_64", "amd64"}:
        return _X86_FILE_READS
    if machine in {"aarch64", "arm64"}:
        return _AARCH64_FILE_READS
    raise HarnessError(f"no file-read syscall table for {machine}")


def _signed_arg(value: int) -> int:
    # dirfd and fd are 32-bit. AT_FDCWD (-100) arrives as 0xffffff9c,
    # not a sign-extended 64-bit value.
    return int(ctypes.c_int32(value & 0xFFFFFFFF).value)


def _read_cstr(pid: int, addr: int, *, limit: int = 4096) -> str:
    if addr == 0:
        raise HarnessError(f"syscall path pointer is null in pid {pid}")
    mem = Path(f"/proc/{pid}/mem")
    try:
        with mem.open("rb") as handle:
            handle.seek(addr)
            blob = handle.read(limit)
    except OSError as exc:
        raise HarnessError(f"cannot read {mem} at {addr:#x}: {exc}") from exc
    if not blob:
        raise HarnessError(f"empty path read from pid {pid} at {addr:#x}")
    raw = blob.split(b"\0", 1)[0]
    if len(raw) == len(blob):
        raise HarnessError(f"unterminated path in pid {pid} at {addr:#x}")
    return raw.decode("utf-8", "surrogateescape")


def _fd_target(pid: int, fd: int) -> str:
    link = Path(f"/proc/{pid}/fd/{fd}")
    try:
        return os.readlink(link)
    except OSError as exc:
        raise HarnessError(f"cannot read {link}: {exc}") from exc


def _mapped_file_paths(pid: int) -> set[str]:
    """File paths currently mapped into *pid*. Missing maps after exit is a failure."""
    maps = Path(f"/proc/{pid}/maps")
    try:
        text = maps.read_text()
    except OSError as exc:
        raise HarnessError(f"cannot read {maps}: {exc}") from exc
    found: set[str] = set()
    for line in text.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        path = parts[5].strip()
        if path.endswith(" (deleted)"):
            path = path[: -len(" (deleted)")]
        if not path.startswith("/"):
            continue
        found.add(path)
    return found


def _note_loader_paths(pid: int, needed: set[str]) -> None:
    """Remember the executable and every file mapping seen so far.

    The loader reads a shared object before that object shows up in
    the map, so the needed set is the union across the whole run.
    """
    exe = f"/proc/{pid}/exe"
    try:
        needed.add(os.path.realpath(exe))
    except OSError as exc:
        raise HarnessError(f"cannot resolve {exe}: {exc}") from exc
    for path in _mapped_file_paths(pid):
        needed.add(path)
        try:
            needed.add(os.path.realpath(path))
        except OSError:
            needed.add(path)


def _resolve_opened_path(pid: int, dirfd: int | None, pathname: str) -> str:
    if pathname.startswith("/"):
        try:
            return os.path.realpath(pathname)
        except OSError as exc:
            raise HarnessError(f"cannot resolve {pathname}: {exc}") from exc
    if dirfd is None or dirfd == _AT_FDCWD:
        try:
            base = os.readlink(f"/proc/{pid}/cwd")
        except OSError as exc:
            raise HarnessError(f"cannot read cwd of pid {pid}: {exc}") from exc
    else:
        base = _fd_target(pid, dirfd)
        if not base.startswith("/"):
            raise HarnessError(
                f"openat dirfd {dirfd} in pid {pid} is not a directory path: {base}"
            )
    try:
        return os.path.realpath(os.path.join(base, pathname))
    except OSError as exc:
        raise HarnessError(f"cannot resolve {pathname!r} against {base}: {exc}") from exc


def _path_is_loader_needed(path: str, needed: set[str]) -> bool:
    cleaned = path[: -len(" (deleted)")] if path.endswith(" (deleted)") else path
    if not cleaned.startswith("/"):
        return False
    if cleaned in needed:
        return True
    try:
        return os.path.realpath(cleaned) in needed
    except OSError as exc:
        raise HarnessError(f"cannot resolve {cleaned}: {exc}") from exc


def _candidate_file_read(
    nr: int,
    args: list[int],
    pid: int,
    write_table: Mapping[int, tuple[str, str, int]],
    read_table: Mapping[int, tuple[str, int]],
) -> str | None:
    """A read, pread, or read-only open of a filesystem path.

    Stdin, stdout, stderr, pipes, and sockets are not file paths.
    Whether the path is one the loader needed is decided after the
    run, once every mapping has been seen.
    """
    read_spec = read_table.get(nr)
    if read_spec is not None:
        name, index = read_spec
        fd = _signed_arg(args[index])
        if fd <= 2:
            return None
        target = _fd_target(pid, fd)
        if not target.startswith("/") and not target.endswith(" (deleted)"):
            return None
        return f"{name}:{target}"
    write_spec = write_table.get(nr)
    if write_spec is None:
        return None
    name, kind, index = write_spec
    if kind != "flags":
        return None
    if _open_flags_write(args[index]):
        return None
    pathname_index = index - 1
    if pathname_index < 0:
        raise HarnessError(f"{name} flags arg {index} has no path")
    pathname = _read_cstr(pid, args[pathname_index])
    dirfd = _signed_arg(args[0]) if index >= 2 else None
    resolved = _resolve_opened_path(pid, dirfd, pathname)
    return f"{name}:{resolved}"


def _drop_loader_reads(candidates: Sequence[str], needed: set[str]) -> list[str]:
    """Drop reads of the executable, mapped objects, and the linker's cache."""
    for extra in _LOADER_UNMAPPED:
        if os.path.isfile(extra):
            needed.add(extra)
            try:
                needed.add(os.path.realpath(extra))
            except OSError as exc:
                raise HarnessError(f"cannot resolve loader file {extra}: {exc}") from exc
    kept: list[str] = []
    for item in candidates:
        path = item.split(":", 1)[1] if ":" in item else ""
        if not path:
            raise HarnessError(f"file-read trace entry has no path: {item!r}")
        if _path_is_loader_needed(path, needed):
            continue
        kept.append(item)
    return kept


def _file_syscall_at_stop(lib: ctypes.CDLL, pid: int) -> tuple[int, list[int]] | None:
    """Syscall number and six args at a ptrace entry stop.

    Exit stops are ignored. A missing ``/proc/<pid>/syscall`` after
    GET_SYSCALL_INFO fails is a harness failure, not “no write”.
    """
    info = _PtraceSyscallInfo()
    rv = _ptrace_ptr(
        lib,
        _PTRACE_GET_SYSCALL_INFO,
        pid,
        ctypes.sizeof(info),
        ctypes.byref(info),
    )
    if rv != -1:
        if info.op == _PTRACE_SYSCALL_INFO_ENTRY:
            args = [int(info.u.entry.args[i]) for i in range(6)]
            return int(info.u.entry.nr), args
        return None
    path = Path(f"/proc/{pid}/syscall")
    try:
        text = path.read_text().strip()
    except OSError as exc:
        raise HarnessError(f"cannot read {path}: {exc}") from exc
    if text in {"running", ""}:
        return None
    parts = text.split()
    if not parts or parts[0].startswith("-"):
        return None
    try:
        nr = int(parts[0], 0)
        args = [int(part, 0) for part in parts[1:7]]
    except ValueError as exc:
        raise HarnessError(f"{path} is not a syscall record: {text!r}") from exc
    while len(args) < 6:
        args.append(0)
    return nr, args


def _classify_file_write(nr: int, args: list[int], table: Mapping[int, tuple[str, str, int]]) -> str | None:
    spec = table.get(nr)
    if spec is None:
        return None
    name, kind, index = spec
    if kind == "fd":
        if args[index] <= 2:
            return None
        return name
    if kind == "flags":
        if not _open_flags_write(args[index]):
            return None
        return name
    if kind == "creat":
        return name
    if kind == "openat2":
        # openat2's flags live in a struct. Any openat2 during emit/open
        # is file I/O the snapshot would miss; the honest library does not
        # issue it. A read-only openat2 is still an open the PRD forbids,
        # and the positive control uses createFile, which is openat.
        return name
    if kind == "rename":
        return name
    return None


def trace_file_write_syscalls(
    argv: Sequence[str],
    *,
    cwd: str | Path,
    env: Mapping[str, str],
    timeout: float | None = DEFAULT_TIMEOUT,
) -> tuple[RunResult, list[str], list[str]]:
    """Run *argv* under ptrace and return ``(result, write names, unexpected reads)``.

    The observer is outside the product. Writes to stdin, stdout, and
    stderr are not file writes. A read, pread, or read-only open counts
    only when the path is not one the loader needed to run this probe.
    A silent tracer (no syscall stops) is a harness failure. Does not
    require a strace binary.
    """
    if not argv:
        raise HarnessError("trace argv must be non-empty")
    table = _file_write_table()
    read_table = _file_read_table()
    workdir = str(Path(cwd).resolve())
    child_env = dict(env)
    lib = ctypes.CDLL(None, use_errno=True)
    lib.ptrace.restype = ctypes.c_long
    lib.ptrace.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    timeout_s = DEFAULT_TIMEOUT if timeout is None else float(timeout)

    def _traceme() -> None:
        os.setpgid(0, 0)
        if _ptrace(lib, _PTRACE_TRACEME) == -1:
            os._exit(126)

    proc = subprocess.Popen(
        list(argv),
        cwd=workdir,
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        preexec_fn=_traceme,
    )
    if proc.stdout is None or proc.stderr is None:
        raise HarnessError("traced child has no stdout/stderr pipes")
    out_fd = proc.stdout.fileno()
    err_fd = proc.stderr.fileno()
    os.set_blocking(out_fd, False)
    os.set_blocking(err_fd, False)
    out_b: list[bytes] = []
    err_b: list[bytes] = []
    stop = threading.Event()

    def _drain_loop() -> None:
        while not stop.is_set():
            ready, _, _ = select.select([out_fd, err_fd], [], [], 0.05)
            for fd in ready:
                _drain_pipe(fd, out_b if fd == out_fd else err_b)

    reader = threading.Thread(target=_drain_loop, daemon=True)
    reader.start()

    pgid = proc.pid
    options = (
        _PTRACE_O_TRACESYSGOOD
        | _PTRACE_O_TRACEFORK
        | _PTRACE_O_TRACEVFORK
        | _PTRACE_O_TRACECLONE
        | _PTRACE_O_TRACEEXEC
    )
    hits: list[str] = []
    read_hits: list[str] = []
    loader_paths: set[str] = set()
    syscall_stops = 0
    returncode: int | None = None
    deadline = time.monotonic() + timeout_s

    def _resume(pid: int, sig: int = 0) -> None:
        _ptrace(lib, _PTRACE_SYSCALL, pid, 0, sig)

    def _kill_group() -> None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except OSError:
                pass

    try:
        try:
            _wpid, status = os.waitpid(proc.pid, _WAIT_WALL)
        except ChildProcessError as exc:
            raise HarnessError(f"traced child {proc.pid} vanished before stop") from exc
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -os.WTERMSIG(status)
            raise HarnessError(
                f"traced child exited {code} before a ptrace stop "
                "(PTRACE_TRACEME is not available on this image)"
            )
        if not os.WIFSTOPPED(status):
            raise HarnessError(f"traced child status {status:#x} is not a stop")
        if _ptrace(lib, _PTRACE_SETOPTIONS, proc.pid, 0, options) == -1:
            err = ctypes.get_errno()
            raise HarnessError(
                f"PTRACE_SETOPTIONS failed errno={err} {os.strerror(err)}"
            )
        _resume(proc.pid)

        while returncode is None:
            if time.monotonic() > deadline:
                _kill_group()
                raise HarnessError(
                    f"file-write trace of {list(argv)!r} exceeded {timeout_s}s"
                )
            try:
                wpid, status = os.waitpid(-pgid, _WAIT_WALL)
            except ChildProcessError:
                break
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                if wpid == proc.pid:
                    returncode = (
                        os.WEXITSTATUS(status)
                        if os.WIFEXITED(status)
                        else -os.WTERMSIG(status)
                    )
                continue
            if not os.WIFSTOPPED(status):
                continue
            sig = os.WSTOPSIG(status)
            event = status >> 16
            if sig == (signal.SIGTRAP | 0x80):
                syscall_stops += 1
                _note_loader_paths(wpid, loader_paths)
                entered = _file_syscall_at_stop(lib, wpid)
                if entered is not None:
                    nr, args = entered
                    name = _classify_file_write(nr, args, table)
                    if name is not None:
                        hits.append(name)
                    else:
                        read_name = _candidate_file_read(
                            nr, args, wpid, table, read_table
                        )
                        if read_name is not None:
                            read_hits.append(read_name)
                _resume(wpid)
            elif sig == signal.SIGTRAP and event in (
                _PTRACE_EVENT_FORK,
                _PTRACE_EVENT_VFORK,
                _PTRACE_EVENT_CLONE,
            ):
                msg = ctypes.c_ulong(0)
                _ptrace_ptr(
                    lib,
                    _PTRACE_GETEVENTMSG,
                    wpid,
                    0,
                    ctypes.byref(msg),
                )
                newpid = int(msg.value)
                if newpid:
                    _ptrace(lib, _PTRACE_SETOPTIONS, newpid, 0, options)
                    _resume(newpid)
                _resume(wpid)
            elif sig in (signal.SIGSTOP, signal.SIGTRAP):
                _ptrace(lib, _PTRACE_SETOPTIONS, wpid, 0, options)
                _resume(wpid)
            else:
                _resume(wpid, sig)
    finally:
        stop.set()
        reader.join(timeout=1.0)
        if returncode is None and proc.poll() is None:
            _kill_group()
            try:
                os.waitpid(proc.pid, _WAIT_WALL)
            except ChildProcessError:
                pass
        for fd, bucket in ((out_fd, out_b), (err_fd, err_b)):
            _drain_pipe(fd, bucket)

    if returncode is None:
        raise HarnessError("traced child produced no exit status")
    if syscall_stops == 0:
        raise HarnessError(
            "ptrace observed no syscall stops; the file-write observer is silent"
        )
    result = RunResult(
        returncode=returncode,
        stdout=b"".join(out_b),
        stderr=b"".join(err_b),
        argv=tuple(str(item) for item in argv),
        cwd=workdir,
        environ=child_env,
        phase="run",
        binary=Path(argv[0]),
    )
    return result, hits, _drop_loader_reads(read_hits, loader_paths)


def run_traced_file_writes(
    ws,
    argv: Sequence[str],
    *,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> tuple[RunResult, list[str], list[str]]:
    """Trace *argv* in *ws* for file writes and for reads of unneeded paths."""
    return trace_file_write_syscalls(
        argv,
        cwd=ws.path,
        env=ws.env,
        timeout=timeout,
    )


_UNEXPECTED_READ_NAMES = frozenset(
    {"read", "pread64", "readv", "preadv", "preadv2", "open", "openat"}
)


def unexpected_file_reads_in_trace(names: Sequence[str]) -> list[str]:
    """Keep reads of a path the probe itself did not need.

    Each entry is ``syscall:path``. Loader opens of the executable,
    mapped objects, and the linker's cache are not in this list.
    """
    kept: list[str] = []
    for name in names:
        syscall = name.split(":", 1)[0]
        if syscall not in _UNEXPECTED_READ_NAMES:
            raise HarnessError(f"file-read trace recorded {name!r}, which is not a read")
        kept.append(name)
    return kept


# Socket-family numbers, one table per architecture. x86_64 and aarch64
# do not share these numbers: on x86_64, 200 is tkill, 201 is time, 202
# is futex, and 203 is sched_setaffinity. Those are not bind, listen,
# accept, or connect. A lock, a thread kill, time, or sched_setaffinity
# is not network I/O.
# x86_64: arch/x86/entry/syscalls/syscall_64.tbl
_X86_64_NETWORK_SYSCALLS = {
    41: "socket",
    42: "connect",
    43: "accept",
    44: "sendto",
    45: "recvfrom",
    46: "sendmsg",
    47: "recvmsg",
    49: "bind",
    50: "listen",
    288: "accept4",
}
# aarch64: include/uapi/asm-generic/unistd.h
_AARCH64_NETWORK_SYSCALLS = {
    198: "socket",
    200: "bind",
    201: "listen",
    202: "accept",
    203: "connect",
    206: "sendto",
    207: "recvfrom",
    211: "sendmsg",
    212: "recvmsg",
    242: "accept4",
}


def _network_syscall_table() -> dict[int, str]:
    machine = platform.machine()
    if machine in {"x86_64", "amd64"}:
        return _X86_64_NETWORK_SYSCALLS
    if machine in {"aarch64", "arm64"}:
        return _AARCH64_NETWORK_SYSCALLS
    raise HarnessError(f"no network syscall table for {machine}")


def trace_arch_network_syscalls(
    argv: Sequence[str],
    *,
    cwd: str | Path,
    env: Mapping[str, str],
    timeout: float | None = DEFAULT_TIMEOUT,
) -> tuple[RunResult, list[str]]:
    """Run *argv* under ptrace and return ``(result, network-syscall names)``.

    Numbers come from the table for this machine only. A silent tracer
    (no syscall stops) is a harness failure, not an empty-network pass.
    """
    if not argv:
        raise HarnessError("trace argv must be non-empty")
    table = _network_syscall_table()
    workdir = str(Path(cwd).resolve())
    child_env = dict(env)
    lib = _libc()
    timeout_s = DEFAULT_TIMEOUT if timeout is None else float(timeout)

    def _traceme() -> None:
        os.setpgid(0, 0)
        if _ptrace(lib, _PTRACE_TRACEME) == -1:
            os._exit(126)

    proc = subprocess.Popen(
        list(argv),
        cwd=workdir,
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        preexec_fn=_traceme,
    )
    if proc.stdout is None or proc.stderr is None:
        raise HarnessError("traced child has no stdout/stderr pipes")
    out_fd = proc.stdout.fileno()
    err_fd = proc.stderr.fileno()
    os.set_blocking(out_fd, False)
    os.set_blocking(err_fd, False)
    out_b: list[bytes] = []
    err_b: list[bytes] = []
    stop = threading.Event()

    def _drain_loop() -> None:
        while not stop.is_set():
            ready, _, _ = select.select([out_fd, err_fd], [], [], 0.05)
            for fd in ready:
                _drain_pipe(fd, out_b if fd == out_fd else err_b)

    reader = threading.Thread(target=_drain_loop, daemon=True)
    reader.start()

    pgid = proc.pid
    options = (
        _PTRACE_O_TRACESYSGOOD
        | _PTRACE_O_TRACEFORK
        | _PTRACE_O_TRACEVFORK
        | _PTRACE_O_TRACECLONE
        | _PTRACE_O_TRACEEXEC
    )
    hits: list[str] = []
    syscall_stops = 0
    returncode: int | None = None
    deadline = time.monotonic() + timeout_s

    def _resume(pid: int, sig: int = 0) -> None:
        _ptrace(lib, _PTRACE_SYSCALL, pid, 0, sig)

    def _kill_group() -> None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except OSError:
                pass

    try:
        try:
            _wpid, status = os.waitpid(proc.pid, _WAIT_WALL)
        except ChildProcessError as exc:
            raise HarnessError(f"traced child {proc.pid} vanished before stop") from exc
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -os.WTERMSIG(status)
            raise HarnessError(
                f"traced child exited {code} before a ptrace stop "
                "(PTRACE_TRACEME is not available on this image)"
            )
        if not os.WIFSTOPPED(status):
            raise HarnessError(f"traced child status {status:#x} is not a stop")
        if _ptrace(lib, _PTRACE_SETOPTIONS, proc.pid, 0, options) == -1:
            err = ctypes.get_errno()
            raise HarnessError(
                f"PTRACE_SETOPTIONS failed errno={err} {os.strerror(err)}"
            )
        _resume(proc.pid)

        while returncode is None:
            if time.monotonic() > deadline:
                _kill_group()
                raise HarnessError(
                    f"network trace of {list(argv)!r} exceeded {timeout_s}s"
                )
            try:
                wpid, status = os.waitpid(-pgid, _WAIT_WALL)
            except ChildProcessError:
                break
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                if wpid == proc.pid:
                    returncode = (
                        os.WEXITSTATUS(status)
                        if os.WIFEXITED(status)
                        else -os.WTERMSIG(status)
                    )
                continue
            if not os.WIFSTOPPED(status):
                continue
            sig = os.WSTOPSIG(status)
            event = status >> 16
            if sig == (signal.SIGTRAP | 0x80):
                syscall_stops += 1
                nr = _syscall_nr_at_stop(lib, wpid)
                if nr is not None and nr in table:
                    hits.append(table[nr])
                _resume(wpid)
            elif sig == signal.SIGTRAP and event in (
                _PTRACE_EVENT_FORK,
                _PTRACE_EVENT_VFORK,
                _PTRACE_EVENT_CLONE,
            ):
                msg = ctypes.c_ulong(0)
                _ptrace_ptr(
                    lib,
                    _PTRACE_GETEVENTMSG,
                    wpid,
                    0,
                    ctypes.byref(msg),
                )
                newpid = int(msg.value)
                if newpid:
                    _ptrace(lib, _PTRACE_SETOPTIONS, newpid, 0, options)
                    _resume(newpid)
                _resume(wpid)
            elif sig in (signal.SIGSTOP, signal.SIGTRAP):
                _ptrace(lib, _PTRACE_SETOPTIONS, wpid, 0, options)
                _resume(wpid)
            else:
                _resume(wpid, sig)
    finally:
        stop.set()
        reader.join(timeout=1.0)
        if returncode is None and proc.poll() is None:
            _kill_group()
            try:
                os.waitpid(proc.pid, _WAIT_WALL)
            except ChildProcessError:
                pass
        for fd, bucket in ((out_fd, out_b), (err_fd, err_b)):
            _drain_pipe(fd, bucket)

    if returncode is None:
        raise HarnessError("traced child produced no exit status")
    if syscall_stops == 0:
        raise HarnessError(
            "ptrace observed no syscall stops; the network observer is silent"
        )
    result = RunResult(
        returncode=returncode,
        stdout=b"".join(out_b),
        stderr=b"".join(err_b),
        argv=tuple(str(item) for item in argv),
        cwd=workdir,
        environ=child_env,
        phase="run",
        binary=Path(argv[0]),
    )
    return result, hits


def run_traced_arch_network(
    ws,
    argv: Sequence[str],
    *,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> tuple[RunResult, list[str]]:
    """Trace *argv* in *ws* for this machine's socket-family syscalls."""
    return trace_arch_network_syscalls(
        argv,
        cwd=ws.path,
        env=ws.env,
        timeout=timeout,
    )


def file_write_syscalls_in_trace(names: Sequence[str]) -> list[str]:
    """Keep names that create or write a file, not stdio."""
    keys = frozenset(
        {
            "write",
            "pwrite64",
            "writev",
            "pwritev",
            "pwritev2",
            "open",
            "openat",
            "openat2",
            "creat",
            "renameat2",
        }
    )
    return [name for name in names if name in keys]
