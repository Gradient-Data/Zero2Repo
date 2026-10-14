# feature: F04
"""Feature-local helpers for effort selection on compress and expand.

These helpers place runtime-unknown suite inputs and drive the public
CLI. They are not a substitute public entry.
"""

from __future__ import annotations


from pathlib import Path
from typing import Sequence

from F01_helpers import derived_batch_archive, require_ok, token, unique_name
from F02_helpers import complete_packets, is_opus_head, replace_vorbis_comment
from F03_helpers import (
    opus_head_fields,
    place_opus_classified,
    replace_opus_tags,
    run_product_long,
)
from _harness import (
    HarnessError,
    RunResult,
    Workspace,
    purge_side_state,
    read_bytes,
    side_state_snapshot,
    stored_copy,
    workspace,
)

EFFORT_TOKENS = ("-1", "-2", "-3", "-4", "-5", "-6", "-7", "-8", "-9")

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_SCALE_FILES = (
    _FIXTURE_DIR / "vorbis_ordinary_a.ogg",
    _FIXTURE_DIR / "vorbis_ordinary_b.ogg",
    _FIXTURE_DIR / "vorbis_ordinary_c.ogg",
)
_OPUS_KINDS = ("silk", "celt", "hybrid")
# Short conventional single-link Vorbis files, in addition to the scale files.
_SHORT_VORBIS_FILES = (
    _FIXTURE_DIR / "vorbis_a.ogg",
    _FIXTURE_DIR / "vorbis_b.ogg",
)
# Audio packets shorter than this are not measured for verbatim storage:
# a few-byte packet can recur by chance inside any byte stream.
VERBATIM_MIN_PACKET = 16


def _read_fixture(path: Path) -> bytes:
    if not path.is_file():
        raise HarnessError(f"suite fixture missing: {path}")
    try:
        data = read_bytes(path)
    except FileNotFoundError as exc:
        raise HarnessError(f"suite fixture missing: {path}") from exc
    if not data:
        raise HarnessError(f"suite fixture is empty: {path}")
    return data


def _vorbis_comment_variant(data: bytes) -> bytes:
    mark = token().encode("ascii")
    variant = replace_vorbis_comment(
        data,
        vendor=b"suite-vendor-" + mark,
        fields=(b"TITLE=" + mark, b"NOTE=" + mark),
    )
    if variant == data:
        raise HarnessError("Vorbis comment variant equals the unmodified bytes")
    return variant


def _opus_tags_variant(data: bytes) -> bytes:
    mark = token().encode("ascii")
    variant = replace_opus_tags(
        data,
        vendor=b"suite-vendor-" + mark,
        fields=(b"NOTE=" + mark,),
    )
    if variant == data:
        raise HarnessError("Opus tags variant equals the unmodified bytes")
    return variant


def _prove_family0(data: bytes, *, what: str) -> None:
    packets = complete_packets(data)
    if not packets:
        raise HarnessError(f"{what} has no complete packets")
    channels, family = opus_head_fields(packets[0])
    if family != 0:
        raise HarnessError(f"{what} mapping family is {family}, not 0")
    if channels not in (1, 2):
        raise HarnessError(
            f"{what} channel count is {channels}, not 1 or 2 under family 0"
        )


def compress_to(
    ws: Workspace, src: str, dest: str, *effort_tokens: str
) -> RunResult:
    """Compress *src* to *dest*. Effort tokens, if any, precede the verb."""
    args = [*effort_tokens, "e", src, dest]
    result = run_product_long(ws, args)
    require_ok(result)
    if not ws.path_is_file(dest):
        raise HarnessError(f"compress did not write a regular file at {dest}")
    print(
        f"[F04] compress argv={args!r} dest_size={ws.file_size(dest)}",
        flush=True,
    )
    return result


def expand_to(ws: Workspace, archive: str, dest: str) -> RunResult:
    """Expand *archive* to *dest*. Does not compare recovered bytes to a source."""
    args = ["d", archive, dest]
    result = run_product_long(ws, args)
    require_ok(result)
    if not ws.path_is_file(dest):
        raise HarnessError(f"expand did not write a regular file at {dest}")
    print(f"[F04] expand argv={args!r} dest_size={ws.file_size(dest)}", flush=True)
    return result


def archive_bytes(ws: Workspace, dest: str) -> bytes:
    """Read destination bytes. Missing or unreadable destinations raise."""
    try:
        data = ws.read_bytes(dest)
    except FileNotFoundError as exc:
        raise HarnessError(f"archive destination missing: {dest}") from exc
    return data


def measured_round(
    ws: Workspace, src: str, *effort_tokens: str
) -> tuple[bytes, bytes, bytes]:
    """Compress then expand. Return (archive bytes, recovered bytes, src bytes)."""
    dest = unique_name("arc")
    recovered = unique_name("rec")
    compress_to(ws, src, dest, *effort_tokens)
    src_bytes = ws.read_bytes(src)
    dest_bytes = archive_bytes(ws, dest)
    expand_to(ws, dest, recovered)
    rec_bytes = ws.read_bytes(recovered)
    print(
        f"[F04] measured src={len(src_bytes)} dest={len(dest_bytes)} "
        f"rec={len(rec_bytes)} effort={effort_tokens!r}",
        flush=True,
    )
    return dest_bytes, rec_bytes, src_bytes


def vorbis_with_runtime_comment(ws: Workspace) -> str:
    """Write one suite Vorbis whose comment packet carries a runtime token."""
    data = _read_fixture(_SCALE_FILES[0])
    variant = _vorbis_comment_variant(data)
    rel = unique_name("vorbis-rt") + ".ogg"
    ws.write(rel, variant)
    return rel


def opus_with_runtime_tags(ws: Workspace, kind: str) -> str:
    """Place a classified family-0 Opus and rewrite OpusTags at runtime."""
    placed = place_opus_classified(ws, kind)
    original = ws.read_bytes(placed)
    variant = _opus_tags_variant(original)
    _prove_family0(variant, what=f"runtime {kind} OpusTags variant")
    rel = unique_name(f"opus-{kind}-rt") + ".opus"
    ws.write(rel, variant)
    return rel


def place_vorbis_scale_bundle(ws: Workspace) -> list[str]:
    """At least three distinct runtime Vorbis comment variants. Not the originals."""
    paths: list[str] = []
    originals: list[bytes] = []
    variants: list[bytes] = []
    for i, fixture in enumerate(_SCALE_FILES):
        data = _read_fixture(fixture)
        originals.append(data)
        variant = _vorbis_comment_variant(data)
        rel = unique_name(f"vorbis-scale-{i}") + ".ogg"
        ws.write(rel, variant)
        paths.append(rel)
        variants.append(variant)
    if len(paths) < 3:
        raise HarnessError("Vorbis scale bundle needs at least three files")
    if len(set(originals)) < 3:
        raise HarnessError("suite Vorbis scale fixtures are not mutually distinct")
    if len(set(variants)) < 3:
        raise HarnessError("runtime Vorbis variants are not mutually distinct")
    if any(v == o for v, o in zip(variants, originals)):
        raise HarnessError("a Vorbis scale member is still the unmodified fixture")
    return paths


def place_opus_scale_bundle(ws: Workspace) -> list[str]:
    """Three classified family-0 Opus files, each with runtime OpusTags."""
    paths: list[str] = []
    originals: list[bytes] = []
    variants: list[bytes] = []
    for kind in _OPUS_KINDS:
        placed = place_opus_classified(ws, kind)
        original = ws.read_bytes(placed)
        originals.append(original)
        variant = _opus_tags_variant(original)
        _prove_family0(variant, what=f"runtime {kind} scale member")
        rel = unique_name(f"opus-scale-{kind}") + ".opus"
        ws.write(rel, variant)
        paths.append(rel)
        variants.append(variant)
    if len(set(originals)) < 3:
        raise HarnessError("classified Opus fixtures are not mutually distinct")
    if len(set(variants)) < 3:
        raise HarnessError("runtime Opus variants are not mutually distinct")
    if any(v == o for v, o in zip(variants, originals)):
        raise HarnessError("an Opus scale member is still the unmodified fixture")
    return paths


def require_lossless_archive(
    dest_bytes: bytes, rec_bytes: bytes, src_bytes: bytes, *, what: str
) -> None:
    """Assert dest≠src and recovered==src. Observation, not a public entry."""
    assert not stored_copy(dest_bytes, src_bytes), (
        f"{what}: compress destination bytes carry the source verbatim (copy stub)"
    )
    assert rec_bytes == src_bytes, (
        f"{what}: expand did not restore the original bytes"
    )


def batch_compress_to(
    ws: Workspace, src_bytes: bytes, *effort_tokens: str
) -> tuple[str, bytes]:
    """Batch-compress a unique copy of *src_bytes*. Return (derived dest, bytes)."""
    inp = unique_name("batch-in") + ".ogg"
    ws.write(inp, src_bytes)
    dest = derived_batch_archive(inp)
    args = [*effort_tokens, "-b", "e", inp]
    result = run_product_long(ws, args)
    require_ok(result)
    data = archive_bytes(ws, dest)
    print(
        f"[F04] batch argv={args!r} dest={dest!r} size={len(data)}",
        flush=True,
    )
    return dest, data


def split_member(
    pairs: Sequence[tuple[str, bytes, bytes]],
) -> tuple[str, bytes, bytes] | None:
    """Return one pair whose effort-1 archive bytes differ from effort-9.

    None means no pair split. Callers must then treat bundle totals as the
    product verdict (sum at 9 strictly less than sum at 1). None is not a
    pass for default-equals-nine, and is never an unmodified copy fixture.
    """
    if not pairs:
        raise HarnessError("split_member given no measured pairs")
    for src, at_1, at_9 in pairs:
        if at_1 != at_9:
            return src, at_1, at_9
    return None


def place_ordinary_bundle(ws: Workspace) -> list[tuple[str, str]]:
    """Ordinary accepted single-link files with runtime comments.

    Returns ``(codec, relpath)`` pairs: conventional-encoder Vorbis files
    (scale and short) and the classified family-0 Opus files, each with a
    runtime comment so no member is a byte-for-byte suite fixture.
    """
    members: list[tuple[str, str]] = []
    for i, fixture in enumerate((*_SCALE_FILES, *_SHORT_VORBIS_FILES)):
        variant = _vorbis_comment_variant(_read_fixture(fixture))
        rel = unique_name(f"ordinary-vorbis-{i}") + ".ogg"
        ws.write(rel, variant)
        members.append(("vorbis", rel))
    for kind in _OPUS_KINDS:
        original = ws.read_bytes(place_opus_classified(ws, kind))
        variant = _opus_tags_variant(original)
        _prove_family0(variant, what=f"ordinary {kind} member")
        rel = unique_name(f"ordinary-opus-{kind}") + ".opus"
        ws.write(rel, variant)
        members.append(("opus", rel))
    datas = [ws.read_bytes(rel) for _codec, rel in members]
    if len(set(datas)) != len(datas):
        raise HarnessError("ordinary bundle members are not mutually distinct")
    return members


def audio_packets(data: bytes) -> list[bytes]:
    """Complete audio packets of a single-link Vorbis or Opus file."""
    packets = complete_packets(data)
    if not packets:
        raise HarnessError("file has no complete packets")
    n_headers = 2 if is_opus_head(packets[0]) else 3
    if len(packets) <= n_headers:
        raise HarnessError("file has no audio packets")
    return packets[n_headers:]


def verbatim_audio_share(archive: bytes, source: bytes) -> tuple[int, int]:
    """Bytes of measurable audio packets found byte-for-byte in *archive*.

    Returns ``(found, measured)``: *measured* sums audio packets of at
    least VERBATIM_MIN_PACKET bytes; *found* sums those that occur as a
    contiguous run inside the archive. Type errors raise.
    """
    for name, value in (("archive", archive), ("source", source)):
        if not isinstance(value, (bytes, bytearray)):
            raise HarnessError(f"{name} expected bytes, got {type(value)!r}")
    measured = 0
    found = 0
    blob = bytes(archive)
    for packet in audio_packets(bytes(source)):
        if len(packet) < VERBATIM_MIN_PACKET:
            continue
        measured += len(packet)
        if packet in blob:
            found += len(packet)
    return found, measured


def expand_from_archive_alone(
    src_bytes: bytes, effort: str, suffix: str, *, what: str
) -> None:
    """Compress, remove everything but the archive bytes, expand elsewhere.

    Compress runs in one workspace. Every host entry the product created
    outside its destination is then removed, stray processes and SysV IPC
    objects it left are removed, and that workspace (input, HOME, cwd) is
    deleted. Expand then runs on a copy of the archive under another name
    in a fresh workspace with a fresh HOME. The recovered bytes must equal
    the original input.
    """
    arc = unique_name("alone-arc")
    with workspace() as first:
        src = unique_name("alone-src") + suffix
        first.write(src, src_bytes)
        before = side_state_snapshot()
        compress_to(first, src, arc, effort)
        archive = archive_bytes(first, arc)
        changed = purge_side_state(before, keep=[first.resolve(arc)])
        assert not changed, (
            f"{what}: compress changed pre-existing files outside its "
            f"destination: {changed[:5]!r}"
        )
    assert not stored_copy(archive, src_bytes), (
        f"{what}: compress destination carries the source verbatim"
    )
    with workspace() as second:
        moved = unique_name("moved")
        second.write(moved, archive)
        out = unique_name("alone-out") + suffix
        expand_to(second, moved, out)
        recovered = second.read_bytes(out)
    print(
        f"[F04] alone {what} src={len(src_bytes)} archive={len(archive)} "
        f"recovered={len(recovered)}",
        flush=True,
    )
    assert recovered == src_bytes, (
        f"{what}: expand needs only the archive; with the input and every "
        "other trace of compress removed, a copy of the archive in a fresh "
        "working directory and HOME did not restore the original bytes"
    )
