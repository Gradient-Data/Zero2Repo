# klyvmap — Full Product Requirements Document

## Product overview

**klyvmap** is a Zig library of roaring bitmaps over 64-bit unsigned integers. Its defining product property is that **the in-memory form of a bitmap is the serialized form**: one flat byte buffer that can be stored or sent as-is. Opening that buffer does not convert it into a second in-memory form. Reads after open do not require a separate deserialize step the caller must invoke. The first set on a borrowed open does not write the caller’s buffer, which stays byte-identical to what was opened.

A first-time integrator creates an empty bitmap, sets a few values (including values far above 2^32), observes them present and each counted once, optionally compacts for long-term storage, emits the buffer, and later opens that same buffer and iterates the values. Every bitmap round-trips through its own buffer, yields 0 as a real value when 0 is present, and holds values anywhere in the 64-bit range.

klyvmap is a 64-bit roaring bitmap only. It does not offer a run-length packing of consecutive values. It does not implement CRoaring’s portable or frozen interchange formats. The format version stamped into every buffer is tracked separately from the library’s calendar release version; buffers that share a format version read each other.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, and call spellings belong in the Interface Contract, not here.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **klyvmap** | The product. A Zig library that stores a set of 64-bit unsigned integers as one roaring bitmap in one flat buffer. |
| **bitmap** | One such set. Empty until values are set. The caller creates it, mutates it, queries it, emits its buffer, and releases it. |
| **value** | A 64-bit unsigned integer in the closed range from 0 through the maximum 64-bit unsigned integer. Setting a value that is already present does not create a second copy. |
| **prefix** | The group of all values that share every bit above the low 16 bits. Each value belongs to exactly one prefix; the prefix of the values below 2^16 is the lowest prefix. A prefix is *emptied* when it held values and now holds none. |
| **in-use bytes** | The bytes of the bitmap’s emitted borrowed view (FP-04): its whole content and length. Two bitmaps have matching in-use bytes when those views are byte-for-byte equal. |
| **buffer** | The flat, 8-byte-aligned byte sequence that **is** the bitmap. Emitting the buffer does not convert a separate in-memory object graph. Opening the buffer does not build a second representation. |
| **borrow** | An open mode: the caller keeps the buffer. The bitmap never writes it and never frees it. The buffer must outlive the bitmap. The first set leaves the caller’s memory byte-identical to what was opened. |
| **own** | An open mode: the bitmap takes the buffer. Before the caller mutates it, the opened bitmap’s storage is that allocation, not a second buffer. Releasing the bitmap frees whatever storage it then holds. Whether a mutation replaces that allocation is the implementer’s choice. The buffer must be a writable allocation from the same allocator the caller passes in. The transfer is unconditional: success and the failure paths in FP-04 both take responsibility for that allocation. |
| **format version** | An integer field stamped into every buffer, at the same position in every buffer. This product writes format version **1** and, when opening, refuses any other version. The field’s width and position are the implementer’s choice. |
| **compact** | The optional rewrite that produces the smallest buffer that still holds the same set, for long-term storage. Equal sets become byte-identical. The result stays an ordinary mutable bitmap. |
| **cleanup** | The operation that reclaims space left after in-place intersection, in-place difference, or remove have emptied prefixes, without changing membership. |
| **materializing intersection / union** | Entries that return a **new** bitmap equal to the intersection or union of two bitmaps, leaving both operands unchanged. |
| **n-ary union** | Many bitmaps in, one new bitmap out, equal to the union of every input. |
| **in-place intersection / union / difference** | Entries that replace the left bitmap with its intersection with, union with, or difference from the right bitmap. |
| **fused cardinality** | Entries that return how many values the intersection, union, or difference **would** contain, without producing that result bitmap. |
| **iterator** | A forward walk that yields each present value once, in ascending order, until it reports that it is exhausted. Exhaustion is distinct from the value 0. |
| **unsupported-format-version failure** | The distinct failure of opening a buffer that is large enough to be a bitmap but whose format version is not 1. It is not the empty-bitmap outcome used for a buffer that is not a bitmap at all. |
| **owned storage** | Storage a bitmap holds and frees itself. It always comes from the allocator the bitmap was created, opened, or built with (for a clone, the source bitmap’s allocator), and release returns all of it to that allocator. |

## Public surface inventory

klyvmap is a **library**. Integrators reach it by depending on the klyvmap Zig module. There is no command-line product and no I/O inside the library: callers pass allocators and byte buffers.

The public surfaces, grouped by feature point, are:

- Create an empty bitmap, clone it, and release it (FP-01).
- Set, test membership of, and remove 64-bit values (FP-02).
- Report cardinality, emptiness, minimum, and maximum, and enumerate values in ascending order (FP-03).
- Emit the buffer and open it again, in borrow or own mode, including the copying open that accepts unaligned input (FP-04).
- Compact a bitmap to the smallest canonical buffer that still round-trips (FP-05).
- Materialize intersection and union of two bitmaps, and the n-ary union of many (FP-06).
- Intersect, union, or difference **into** an existing bitmap, then reclaim emptied-prefix space with cleanup (FP-07).
- Count intersection, union, and difference without producing a result bitmap (FP-08).
- Build a bitmap from a non-decreasing list of values (FP-09).

Feature points below group these entries by capability. They do not invent additional product surfaces.

## Non-functional constraints

- **Form factor:** A Zig library with no runtime third-party dependencies. Library code performs no file or network I/O. Callers supply a memory allocator and, when opening, a byte buffer.
- **Language / toolchain:** Zig 0.16. The package’s minimum Zig version is 0.16.0.
- **Endianness:** The on-disk format is little-endian by definition. Big-endian targets are refused at compile time: a program that uses the bitmap for a big-endian target does not compile. A file written on any supported machine reads on every supported machine.
- **Platforms:** Little-endian hosts the toolchain supports (including x86-64 and ARM64), on Linux with Zig 0.16.
- **Hardware:** CPU-only. No GPU or accelerator is required or claimed.
- **Integer domain:** 64-bit unsigned integers only. There is no 32-bit variant.
- **Run-length packing:** Not offered. How dense versus sparse runs are packed internally is the implementer’s choice.
- **Trusted buffers:** Beyond the size check and the format-version check in FP-04, a buffer is trusted input. Integrity checks (checksums, signatures) belong a layer above. This product does not promise a distinct diagnostic for a corrupt payload whose version and size look like a bitmap.
- **Release vs format version:** The version the Zig package publishes for itself — its declared release version — is calendar form `0.YYMM.patch`: major 0, then a two-digit year followed by a two-digit month from 01 through 12, then a patch number. That identifier is a different value from the format-version integer in an emitted buffer, which stays 1. Releases that share format version 1 read each other’s buffers.
- **Error policy:** Operations that may allocate can fail by not producing a bitmap when the allocator cannot satisfy the request. That out-of-memory outcome is an allocator failure, not a product boundary. Reads cannot fail. An unsupported format version is the only open-time failure (FP-04).
- **Performance vs CRoaring:** Speed on warm or cold open, and serialized size relative to CRoaring, are design goals, not requirements.

## Required substance (global)

Every feature point below is real roaring-bitmap behavior over 64-bit values whose in-memory form is its serialized buffer, running on a CPU host.

- Membership answers depend on the values actually set; cardinality counts distinct values, never duplicate sets; opening a buffer makes membership available without the caller building a second structure; compact never changes the set; set algebra agrees with ordinary set intersection, union, and difference; the iterator never treats 0 as “done”.

## Non-goals

- CRoaring’s portable format or frozen format. klyvmap does not read or write those encodings.
- Run containers, a 32-bit roaring variant, rank, select, range removal, bitmap splitting, exclusive-or, a materializing difference that returns a new bitmap, or a parallel n-ary union other than the n-ary union in FP-06.
- Bindings in other languages.
- Guaranteeing a particular throughput or a particular serialized size relative to CRoaring.
- Benchmarking and comparison tooling are not product capabilities.
- Optional memory-movement counters a program may enable for profiling.
- Validating untrusted buffers beyond the size and format-version checks in FP-04.

---

## Feature points

### FP-01: Create, clone, and release a bitmap

**Public entry:** klyvmap’s bitmap constructor, which takes a memory allocator and returns an empty bitmap the caller owns and must release; the clone entry, which returns an independent owned copy; and release, which frees the buffer when the bitmap owns it and is safe on a bitmap that only borrows.

**Normal behavior:**

- A freshly created bitmap holds no values. Emptiness is true. Cardinality is 0. Minimum and maximum are absent (not 0). Membership of 0 is false: 0 is a legal value that is simply not present yet.
- A freshly created bitmap owns its buffer: the constructor takes that storage from the allocator it is given. Each constructor call yields a separate bitmap; values set on one never appear on another.
- Emitting that empty bitmap’s buffer (FP-04) yields a non-empty buffer. There is no null-buffer special case for “empty”. Opening that buffer again yields a bitmap that is still empty and still usable: it accepts later sets, and values held by any other bitmap do not appear in it.
- Clone produces a second bitmap that holds the same values. Mutating the clone does not change the original, and mutating the original does not change the clone. Releasing either one leaves the other intact.
- Release of a bitmap that owns its buffer returns all of its owned storage to its allocator, so the allocator’s outstanding total is back to what it was before the bitmap was created. Release of a bitmap opened in borrow mode (FP-04) neither frees nor overwrites the caller’s buffer, which can then be opened again.

**Boundary / error behavior:**

- Creating a bitmap can fail only when the allocator cannot satisfy the request.
- Clone of an empty bitmap is an empty bitmap, still distinct from the original: setting a value on the clone leaves the original empty.

---

### FP-02: Set, membership, and remove of 64-bit values

**Public entry:** The bitmap’s set, membership, and remove operations. Enumeration and extrema are FP-03. Opening and emitting buffers are FP-04. A bitmap opened in borrow mode does not write the caller’s buffer on the first **set** (FP-04). **Remove** on a still-borrowed bitmap is not specified until after a set, or after compact in FP-05.

**Normal behavior:**

- Set adds a 64-bit unsigned integer. It reports whether the value was **newly** added: true on the first set of that value, false on a second set of the same value. Cardinality increases by one only when the report is true.
- Membership is true exactly for values that have been set and not since removed, and false for every other 64-bit unsigned integer.
- Remove deletes a value if it is present and reports whether it was present: true once, then false if called again. Cardinality decreases by one only when the report is true. A removed value can be set again and is then reported newly added. Removing a value never disturbs membership of any other value, whether it shares the removed value’s prefix or not, including when the removal empties that prefix.
- Every 64-bit value is representable, from 0 through the maximum 64-bit unsigned integer. Values that share their low bits but differ in higher bits are distinct members. Values may be set in any order.
- A dense run of consecutive values of any length keeps every value of the run present and counts each once; values just outside the run stay absent.
- Values spread over any number of distinct prefixes, inserted in any order, are all preserved, and cardinality equals the number of distinct values.

**Boundary / error behavior:**

- Set of a value already present does not change cardinality and reports that it was not newly added.
- Remove of a value that was never set reports false and does not change cardinality.
- Remove does not by itself reclaim the room of a prefix it empties: membership and cardinality update immediately, but that prefix’s room stays in the emitted buffer until cleanup (FP-07) or compact (FP-05) reclaims it. Beyond that, how remove changes the emitted buffer is the implementer’s choice.
- Set on a borrowed bitmap never writes the caller’s buffer (FP-04). Remove on a borrowed bitmap is not specified until after a set, or after compact in FP-05.

---

### FP-03: Cardinality, extrema, and ascending enumeration

**Public entry:** The bitmap’s cardinality query, emptiness query, minimum query, maximum query, the forward iterator, the entry that allocates a new array of every value, and the entry that writes every value into a caller-supplied destination whose length equals the cardinality.

**Normal behavior:**

- Cardinality is the number of distinct present values. Emptiness is true exactly when cardinality is 0. On a non-empty bitmap, minimum is the smallest present value and maximum is the largest, whatever order the values were set in. On an empty bitmap both are absent, not 0.
- The iterator yields each present value once, in strictly ascending order, across every prefix, then reports exhaustion. Exhaustion is a distinct outcome from yielding 0: a bitmap that contains 0 yields 0 as a real first value and then continues with the later values. A pull after exhaustion is still exhaustion.
- An empty bitmap’s iterator reports exhaustion on the first pull and on the next pull.
- Removed values and prefixes that no longer hold any value do not appear in the iterator.
- The allocated-array entry returns a slice the caller owns, of length equal to cardinality, holding the same values as a full drain of the iterator, in the same order. On an empty bitmap that slice has length 0.
- The caller-supplied-destination entry writes those same values into a destination whose length equals cardinality. On an empty bitmap the destination has length 0 and nothing is written. Writing into a prefix of a larger reusable buffer leaves the rest of that buffer untouched.

**Boundary / error behavior:**

- The iterator is valid until the bitmap is mutated. Behavior of an iterator used after a mutation of its bitmap is not specified.
- The caller-supplied destination must have length exactly equal to cardinality. Behavior for a destination of any other length is not specified.
- Minimum and maximum skip prefixes that currently hold no values: after every value of the lowest or highest occupied prefix is removed, minimum or maximum is the smallest or largest value that remains, never absent while values remain and never a removed value.

---

### FP-04: Emit and open the buffer (in-memory form is the serialized form)

**Public entry:** The entry that returns the bitmap’s current buffer as a borrowed byte view; the entry that returns an owning copy of those bytes; the entry that opens an 8-byte-aligned buffer as a bitmap in **borrow** or **own** mode; and the copying open, which accepts any byte slice (including a slice that is not 8-byte aligned) and always yields an owned bitmap.

This feature point is the product’s defining surface. Reads after open must work without a second deserialize step the caller has to invoke. Compact before storage is FP-05.

**Normal behavior:**

- Emitting the borrowed view is valid until the bitmap is mutated or released. The owning copy is the same bytes as the view at the moment it is taken, and remains valid after the source bitmap is released. An empty bitmap still emits a buffer of positive length (FP-01).
- Every emitted buffer of a valid bitmap — fresh, populated, compacted, cleaned up, or produced by any entry of this product — has even length, starts at an 8-byte-aligned address, and carries format version **1** in its format-version field.
- Opening a buffer that this product emitted, in borrow or own mode or with the copying open, yields a bitmap with the same membership, cardinality, minimum, maximum, and iterator sequence as the source. The opened bitmap’s in-use bytes match the source’s in-use bytes. Opening the borrowed view of a live bitmap (without taking an owning copy first) is allowed in borrow mode and does not write through that view on reads.
- Borrow: reads (membership, cardinality, emptiness, minimum, maximum, iteration, emitting again, fused counts) do not write the caller’s buffer. The open and those reads allocate nothing through the allocator passed to the open and touch no new memory in proportion to the buffer’s size, however large the buffer is: until the first set, the view the bitmap emits is the caller’s buffer itself, at the same address and of the same length. The first **set** leaves the caller’s buffer byte-identical to what was opened, including when the set would have fitted without growing, and including a set under a prefix the buffer does not yet hold. After that set the bitmap holds the new value; a second open of that same caller buffer still reports the original set, not the values added afterwards.
- Own: before the caller sets a value, an own-open of a well-formed buffer does not build a second buffer — the opened bitmap’s emitted view is the supplied allocation. The open and reads before that set allocate nothing through the allocator. After a set, membership and cardinality follow that set, and release frees whatever the bitmap then owns so the allocator’s outstanding total returns to the total from before the open. The caller must not free the original allocation. Whether any particular value, including a value under a prefix the buffer already holds, fits without replacing the allocation is the implementer’s choice.
- The copying open of a well-formed buffer yields an owned bitmap whose in-use bytes match the source, whatever byte offset or alignment the source slice has. The copying open never writes the source; later changes to the source do not affect the copy, and mutating the copy does not change the source bytes. Release of the copy returns the allocator to its total from before the open; the caller still owns and frees the source.
- After opening in borrow mode, compact (FP-05) also produces an owned mutable bitmap without writing the caller’s buffer.

**Boundary / error behavior:**

- A buffer whose length is **odd**, or that is **shorter than the minimum length** of a buffer that can be a bitmap, is not a bitmap. That minimum is the implementer’s choice; it is at least 8 bytes and never more than the length of a buffer this product emits. Opening such a buffer — borrow, own, or the copying open — yields a **fresh empty bitmap**, not an unsupported-format-version failure, whatever bytes it contains. That fresh bitmap behaves exactly like one from the constructor (FP-01), and the caller’s bytes are left unchanged.
- A buffer that is even-length and at least that minimum, but whose format-version field does **not** hold 1, is refused with an **unsupported-format-version failure** on every open path, whatever the rest of the buffer holds. Nothing is delivered as a bitmap that reports the payload’s values, and the caller’s bytes are left unchanged.
- Own mode takes the allocation on every path: a successful open, an unsupported-format-version failure, and the empty-bitmap path for a too-small or odd-length buffer. The caller does not free the allocation after passing it as own. Borrow mode never frees the caller’s buffer on any path.
- Buffers are otherwise trusted. This feature does not promise a distinct corrupt-payload diagnostic.

---

### FP-05: Compact to the smallest canonical buffer

**Public entry:** The compact operation on a bitmap. It is optional. The intended storage path is: mutate, compact, emit the buffer. Opening is FP-04. Compact does not change the set algebra in FP-06 and FP-07.

**Normal behavior:**

- Compact preserves membership, cardinality, minimum, maximum, and the ascending sequence of values. After compact, every value that was present is still present and no new value appears.
- Compact does not freeze the bitmap. After compact, a second set of an already-present value reports not newly added; setting a value that was not present reports newly added and that value is then present. Compact of an empty bitmap stays empty and still accepts later sets.
- Two bitmaps that hold the same set, built by different routes (any sequence of sets, removes, and set operations) need **not** have identical buffers **before** compact. **After** compact, their in-use buffers are byte-identical. That is the canonical form compact exists to produce.
- The same canonical bytes are produced when a compacted bitmap is then shrunk in place by one value (by remove, by in-place difference, or by in-place intersection) and compacted again: the result matches compact of a bitmap built directly from the remaining values.
- When a bitmap is already the length that compact would produce, compact still makes the in-use bytes match a bitmap built directly from the same values and then compacted: leftover bytes of a just-removed value do not remain as a difference.
- Compact of a borrowed bitmap (already canonical, nothing to reclaim) still hands back a bitmap that owns its storage (taken from the allocator the bitmap was opened with, distinct from the caller’s buffer), of the same length as the caller’s buffer, without writing the caller’s buffer. Later changes to the caller’s buffer no longer affect the bitmap. Set and remove afterwards are then legal and still leave the caller’s bytes unchanged; release returns the allocator to its total from before compact and does not free the caller’s buffer.
- After a workload that inserted many values, removed some of them, and left emptied prefixes, compact shortens the emitted buffer compared with the pre-compact emit, then a second compact leaves that length unchanged.
- A compacted bitmap emits a buffer that opens (FP-04) with the same cardinality and the same value sequence.

**Boundary / error behavior:**

- Compact can fail only when a rewrite needs an allocation the allocator cannot satisfy. A second compact of an already-canonical bitmap succeeds even when the allocator refuses the next allocation.
- Compact is not cleanup (FP-07). Cleanup reclaims emptied prefixes without promising byte-identical canonical form across construction routes. Compact is the step that makes equal sets byte-identical.

---

### FP-06: Materializing intersection, union, and n-ary union

**Public entry:** The two-operand intersection that returns a new bitmap; the two-operand union that returns a new bitmap; and the n-ary union, which takes a list of bitmaps (including the empty list and a one-element list) and returns a new bitmap equal to their union. In-place forms are FP-07. Fused counts are FP-08.

**Normal behavior:**

- Intersection of A and B is the set of values present in both. Union of A and B is the set of values present in either. Neither operand is mutated. Cardinality, membership, minimum, maximum, and the iterator of the result match that set. Both are the same set either operand order.
- Either operand may be empty, and the same bitmap may be passed as both operands; the result is still the intersection or union of the two sets.
- N-ary union of an empty list is an empty bitmap. N-ary union of a one-element list is an independent copy of that one bitmap. N-ary union of many bitmaps equals folding two-operand union across those inputs, whatever the order of the list, however the inputs’ prefixes overlap, and when some inputs are empty or have had every value removed.
- Every result is a new bitmap, independent of every operand and of every other result: mutating the result never changes an operand, and mutating an operand never changes the result. The result is a usable bitmap: it can be compacted (FP-05), emitted and opened (FP-04), and mutated with set and remove (FP-02). A result opens from its emitted buffer with the same values, byte-identical on the in-use region.

**Boundary / error behavior:**

- N-ary union of inputs that hold nothing (empty bitmaps, or bitmaps whose values were all removed) is empty, and that result still accepts a later set.
- Construction of a result can fail only when the allocator cannot satisfy the request.

---

### FP-07: In-place intersection, union, difference, and cleanup

**Public entry:** The in-place intersection, in-place union, and in-place difference entries (left bitmap becomes left ∩ right, left ∪ right, or left \ right); and cleanup, which reclaims space of prefixes left empty by those operations or by remove, without changing membership.

**Normal behavior:**

- After in-place intersection, the left bitmap’s membership is exactly the intersection of the original left set and the right set. After in-place union, it is the union. After in-place difference, it is the values that were in the left and not in the right. The right bitmap is unchanged. This holds whatever the mix of dense runs and scattered values in either operand, within one prefix or across many.
- In-place intersection of a bitmap with itself (left and right the same bitmap, or left and a clone of left) leaves the set unchanged. In-place difference of a bitmap with itself empties it. In-place union of a bitmap with a **distinct** clone of itself leaves the set unchanged.
- Either operand may be empty; the result still follows the same set rules.
- In-place intersection and in-place difference do not by themselves shorten the emitted buffer when they empty prefixes: membership and cardinality update immediately, but the emitted length stays the same until cleanup.
- Cleanup reclaims the room of every emptied prefix other than the lowest one, whatever emptied it (in-place intersection, in-place difference, or remove) and however many such prefixes there are: whenever such a prefix is still empty at cleanup time, cleanup makes the emitted buffer strictly shorter. The lowest prefix is never reclaimed: emptying only the prefix of values below 2^16 does not by itself make cleanup shorten the buffer, including on a bitmap that was compacted before it was emptied. Cleanup does not change membership, and its emitted buffer opens with the same set. A second cleanup on an already-cleaned bitmap leaves the emitted length unchanged.
- Cleanup of a bitmap that is entirely empty, whether fresh or emptied by in-place difference or intersection, stays empty and valid. Cleanup never drops the ability to set new values afterwards, however many prefixes it reclaimed: later sets report newly added, the set then holds exactly the surviving values plus the new ones, and the emitted buffer opens with that set.

**Boundary / error behavior:**

- In-place union is specified when the right bitmap is a **distinct** bitmap. Passing the same bitmap as both operands of in-place union is not specified (the two-operand union in FP-06 covers union-with-self). Passing a clone is the distinct-bitmap case and succeeds.
- In-place intersection and in-place difference on a borrowed bitmap are not specified until the bitmap owns its storage (FP-04, FP-05). In-place union on a borrowed bitmap leaves the caller’s buffer untouched, like set; the bitmap itself holds the union, and a second open of the caller’s buffer still shows the original set.
- Cleanup on a borrowed bitmap is not specified until the bitmap owns its storage.
- In-place union can fail only when an allocation cannot be satisfied. In-place intersection, in-place difference, and cleanup succeed, with their full effect, even when the allocator cannot satisfy a further request; cleanup still shortens the buffer in that situation.

---

### FP-08: Fused intersection, union, and difference cardinalities

**Public entry:** The three fused-cardinality entries on a bitmap, each taking a second bitmap and returning a 64-bit count: how many values the intersection would contain, how many the union would contain, and how many the difference (left minus right) would contain. They do not return a bitmap. Materialized results are FP-06 and FP-07.

**Normal behavior:**

- For any two bitmaps A and B, the fused intersection count equals the cardinality of the materializing intersection of A and B, and equals the cardinality of A after in-place intersection with B (measured on a clone). The fused union count equals the cardinality of the materializing union. The fused difference count equals the cardinality of A after in-place difference with B (measured on a clone). Counts are exact whatever the mix of dense runs and scattered values in either operand, within one prefix or across many.
- Neither operand’s membership, cardinality, or emitted buffer changes, and a borrowed operand’s caller buffer is not written.
- Either operand may be empty, and the same bitmap may be passed as both operands.
- A bitmap whose values were all removed in place (cardinality already 0, cleanup not yet run) counts as the empty set in either operand position.

**Boundary / error behavior:**

- These entries cannot fail, return their count even when the allocator cannot satisfy further requests, and do not produce a bitmap the caller must release.
- Operand order matters for difference and is observable: the fused difference count follows the left operand, and the two directions are different counts when the left-minus-right sizes differ. Intersection and union counts do not depend on operand order.

---

### FP-09: Build a bitmap from a sorted list

**Public entry:** The entry that takes a memory allocator and a sequence of 64-bit unsigned integers that is **non-decreasing**, and returns a new owned bitmap holding the unique values. Repeated set (FP-02) remains the way to build from an unsorted stream.

**Normal behavior:**

- The result’s membership is the unique values in the list, and nothing else. Duplicates in the list are ignored: a list that repeats a value, however many times, still counts it once. Cardinality equals the number of distinct values. Minimum is the first distinct value; maximum is the last. The iterator and the allocated-array entry (FP-03) match the sorted unique list.
- The result matches a bitmap built by setting each list element in turn on a fresh bitmap, whatever non-decreasing list it is given, with or without duplicates.
- An empty list yields an empty bitmap, the same as FP-01’s constructor, still usable for later sets.
- The result is an ordinary owned bitmap: its emitted buffer follows FP-04 and opens with the same in-use bytes and the same membership, and releasing it (and anything opened from a copy of its buffer) returns the allocator to its total from before the call.

**Boundary / error behavior:**

- The entry is specified for a non-decreasing sequence. Behavior on a sequence that decreases at some adjacent pair is not specified.
- Construction can fail only when the allocator cannot satisfy the request.

