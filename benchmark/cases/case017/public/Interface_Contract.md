# Interface Contract

## Product overview

`klyvmap` is a Zig library of roaring bitmaps over 64-bit unsigned integers. This document is the library’s shell: the module, the package manifest, the published types, every public entry with its signature, what each entry takes, what it returns, and who owns and frees what. What each entry does is stated in the product requirements (PRD); this document does not restate it.

## Shape of the public surface

The product is an **importable Zig library**, not a command-line program, not a network service, and not a wire protocol. There is no published console binary and no product-owned configuration file.

**Module.** Integrators compile a Zig program that depends on the Zig module named `klyvmap`. The module root source file, relative to the repository root, is `src/klyvmap.zig`. Attaching the module at compile time uses that module name with that root source (Zig `--dep klyvmap` / `-Mklyvmap=<repository root>/src/klyvmap.zig` form). Callers write `@import("klyvmap")` and then use `klyvmap.Bitmap` and `klyvmap.Iterator`.

**Package manifest.** The repository root holds the Zig package manifest `build.zig.zon`. Its top-level field `.version` is the package’s declared release version, written as a string literal `.version = "<release>"`, where `<release>` has the calendar form the PRD states. The manifest’s other fields are the implementer’s choice.

**Toolchain and targets.** Zig 0.16. The PRD states which targets the library supports. On a target the library refuses, the refusal shows as a compile error of a program that imports `klyvmap` and uses `Bitmap`; the error text is the implementer’s choice.

**Values and buffers.** Values are `u64`. A buffer the product emits is a `[]align(8) const u8` view or a `[]align(8) u8` owning copy; its byte layout is stated in the PRD as far as callers rely on it and is otherwise the implementer’s choice.

**Failures.** An entry whose return type is an error union (`!T`) reports failure through that error union and then delivers no result. The error set and error names are the implementer’s choice. An entry whose return type is not an error union cannot fail.

**Allocators.** Every entry that takes a `std.mem.Allocator` takes the storage it allocates from that allocator. Entries without an allocator argument that may allocate (`clone`, `set`, `compact`, `orInPlace`) use the allocator the bitmap was created, opened, or built with. Every bitmap an entry returns is owned by the caller and is released with `deinit`.

## Naming conventions

The product identity and the module name are both spelled `klyvmap`. The published types are `klyvmap.Bitmap` and `klyvmap.Iterator`. Every entry below is a method or associated function of `Bitmap`, except `next`, which is a method of `Iterator`; none is a free function on the module root. Parameter names in the blocks below match the published signatures.

## Construction and release

```
pub fn init(allocator: std.mem.Allocator) !Bitmap
pub fn deinit(self: *Bitmap) void
pub fn clone(self: *const Bitmap) !Bitmap
```

- `init` returns a new empty bitmap the caller owns.
- `deinit` releases a bitmap: it frees the storage the bitmap owns and never frees or writes a buffer the bitmap only borrows.
- `clone` returns a new owned bitmap holding the same values; it uses the source bitmap’s allocator.

## Membership and queries

```
pub fn set(self: *Bitmap, x: u64) !bool
pub fn contains(self: *const Bitmap, x: u64) bool
pub fn remove(self: *Bitmap, x: u64) bool
pub fn isEmpty(self: *const Bitmap) bool
pub fn getCardinality(self: *const Bitmap) u64
pub fn minimum(self: *const Bitmap) ?u64
pub fn maximum(self: *const Bitmap) ?u64
```

- `set` returns `true` when `x` was newly added and `false` when it was already present.
- `contains` returns `true` when `x` is present.
- `remove` returns `true` when `x` was present (and is now removed) and `false` otherwise.
- `isEmpty` returns `true` when the bitmap holds no values.
- `getCardinality` returns the number of distinct present values.
- `minimum` / `maximum` return the smallest / largest present value, or `null` when the bitmap is empty.

## Enumeration

```
pub fn iterator(self: *const Bitmap) Iterator
pub fn next(self: *Iterator) ?u64
pub fn toArray(self: *const Bitmap, allocator: std.mem.Allocator) ![]u64
pub fn toArrayInto(self: *const Bitmap, dest: []u64) void
```

- `bm.iterator()` returns a `klyvmap.Iterator`; callers do not construct an `Iterator` any other way.
- `it.next()` returns the next value, or `null` when the walk is exhausted.
- `toArray` returns a `[]u64` slice the caller owns and frees with the same allocator.
- `toArrayInto` writes values into the caller’s `dest`, whose length the caller sets to `getCardinality()`.

## Buffer emit and open

```
pub fn toBuffer(self: *const Bitmap) []align(8) const u8
pub fn toBufferCopy(self: *const Bitmap, allocator: std.mem.Allocator) ![]align(8) u8
pub fn fromBuffer(allocator: std.mem.Allocator, buf: []align(8) const u8, ownership: <open mode>) !Bitmap
pub fn fromBufferCopy(allocator: std.mem.Allocator, buf: []const u8) !Bitmap
```

- `toBuffer` returns a view of the bitmap’s buffer, borrowed from the bitmap; the caller does not free it. The view stays valid until the bitmap is mutated or released.
- `toBufferCopy` returns an owning copy of that buffer, allocated from `allocator`; the caller frees it with that allocator.
- `fromBuffer` opens `buf` and returns a `Bitmap`. The third parameter, `<open mode>`, is an enum with exactly the members `borrow` and `own`; callers pass `.borrow` or `.own`. The enum type’s name and where it is declared are the implementer’s choice.
  - `.borrow`: the caller keeps `buf`, must keep it alive while the bitmap is in use, and frees it after `deinit`.
  - `.own`: `buf` must be a writable allocation from `allocator`; the bitmap takes it on every outcome, including a failure, and the caller never frees it.
- `fromBufferCopy` opens a copy of `buf`, which may have any alignment and start at any offset, and returns an owned `Bitmap`. The caller keeps and frees `buf`.

## Compact and cleanup

```
pub fn compact(self: *Bitmap) !void
pub fn cleanup(self: *Bitmap) void
```

- Both act on the bitmap in place and return nothing on success.

## Two-operand algebra

```
pub fn And(allocator: std.mem.Allocator, a: *const Bitmap, b: *const Bitmap) !Bitmap
pub fn Or(allocator: std.mem.Allocator, a: *const Bitmap, b: *const Bitmap) !Bitmap
pub fn andInPlace(self: *Bitmap, other: *const Bitmap) void
pub fn andNotInPlace(self: *Bitmap, other: *const Bitmap) void
pub fn orInPlace(self: *Bitmap, other: *const Bitmap) !void
```

- `And` and `Or` are associated functions: callers write `klyvmap.Bitmap.And(allocator, &a, &b)` and `klyvmap.Bitmap.Or(allocator, &a, &b)`. Each returns a new bitmap the caller owns.
- `andInPlace`, `andNotInPlace`, and `orInPlace` are methods: callers write `left.andInPlace(&right)`, `left.andNotInPlace(&right)`, `try left.orInPlace(&right)`. The result is written into the receiver; nothing is returned on success.

## N-ary union

```
pub fn fastOr(allocator: std.mem.Allocator, bitmaps: []const *const Bitmap) !Bitmap
```

- Callers write `klyvmap.Bitmap.fastOr(allocator, &ptrs)` where `ptrs` is an array or slice of `*const Bitmap`; a zero-length and a one-element slice are legal inputs. It returns a new bitmap the caller owns.

## Fused cardinalities

```
pub fn andCardinality(self: *const Bitmap, other: *const Bitmap) u64
pub fn orCardinality(self: *const Bitmap, other: *const Bitmap) u64
pub fn andNotCardinality(self: *const Bitmap, other: *const Bitmap) u64
```

- Methods: callers write `left.andCardinality(&right)` (or pass a pointer they already hold), and likewise for the other two. Each returns a `u64` count and no bitmap.

## Build from a sorted list

```
pub fn fromSortedList(allocator: std.mem.Allocator, vals: []const u64) !Bitmap
```

- An associated function: callers write `try klyvmap.Bitmap.fromSortedList(allocator, &vals)`. `vals` is a non-decreasing slice of `u64` and may be empty. It returns a new bitmap the caller owns; the caller keeps `vals`.

## I/O

No entry, and importing the module, reads or writes files, starts processes, or opens sockets.
