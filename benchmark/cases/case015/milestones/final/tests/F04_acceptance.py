# feature: F04
"""Acceptance: effort selection on compress and expand."""

from __future__ import annotations

from F01_helpers import (
    derived_batch_archive,
    require_ok,
    require_path_absent,
    run_expect_usage,
    run_product,
    unique_name,
)
from F03_helpers import run_product_long
from F04_helpers import (
    EFFORT_TOKENS,
    archive_bytes,
    batch_compress_to,
    compress_to,
    expand_to,
    measured_round,
    opus_with_runtime_tags,
    place_opus_scale_bundle,
    place_ordinary_bundle,
    place_vorbis_scale_bundle,
    require_lossless_archive,
    split_member,
    verbatim_audio_share,
    vorbis_with_runtime_comment,
)
from _harness import HarnessError, stored_copy, workspace


# ---------------------------------------------------------------------------
# A. `-1` through `-9` accepted on compress; each expands to the original
# ---------------------------------------------------------------------------


def test_each_effort_one_through_nine_accepted_and_lossless():
    with workspace() as ws:
        vorbis_src = vorbis_with_runtime_comment(ws)
        opus_src = opus_with_runtime_tags(ws, "silk")
        for label, src in (("vorbis", vorbis_src), ("opus", opus_src)):
            src_bytes = ws.read_bytes(src)
            for effort in EFFORT_TOKENS:
                dest = unique_name(f"arc-{label}")
                recovered = unique_name(f"out-{label}")
                compress_to(ws, src, dest, effort)
                dest_bytes = archive_bytes(ws, dest)
                assert not stored_copy(dest_bytes, src_bytes), (
                    f"{label} {effort}: compress destination bytes equal "
                    "the source (copy stub)"
                )
                expand_to(ws, dest, recovered)
                rec_bytes = ws.read_bytes(recovered)
                assert rec_bytes == src_bytes, (
                    f"{label} {effort}: expand did not restore the original bytes"
                )
                print(
                    f"[F04] A {label} {effort} src={len(src_bytes)} "
                    f"dest={len(dest_bytes)}",
                    flush=True,
                )


# ---------------------------------------------------------------------------
# B. Omitted effort matches `-9`; on a split member it is not `-1`
# ---------------------------------------------------------------------------


def test_omitted_effort_matches_explicit_nine():
    with workspace() as ws:
        vorbis_one = vorbis_with_runtime_comment(ws)
        omit_b, rec_omit, src_b = measured_round(ws, vorbis_one)
        nine_b, rec_nine, _ = measured_round(ws, vorbis_one, "-9")
        require_lossless_archive(omit_b, rec_omit, src_b, what="omit Vorbis")
        require_lossless_archive(nine_b, rec_nine, src_b, what="-9 Vorbis")
        assert omit_b == nine_b, (
            "omitting effort on compress of a valid Vorbis file must "
            "produce the same archive bytes as -9"
        )
        print(f"[F04] B omit==9 bytes={len(omit_b)}", flush=True)

        bundle = place_vorbis_scale_bundle(ws)
        pairs: list[tuple[str, bytes, bytes]] = []
        sum_1 = 0
        sum_9 = 0
        for src in bundle:
            at_1, rec_1, src_bytes = measured_round(ws, src, "-1")
            at_9, rec_9, _ = measured_round(ws, src, "-9")
            require_lossless_archive(at_1, rec_1, src_bytes, what=f"bundle -1 {src}")
            require_lossless_archive(at_9, rec_9, src_bytes, what=f"bundle -9 {src}")
            pairs.append((src, at_1, at_9))
            sum_1 += len(at_1)
            sum_9 += len(at_9)
        chosen = split_member(pairs)
        if chosen is None:
            assert sum_9 < sum_1, (
                "default effort must not match -1: the runtime Vorbis bundle "
                "did not split at 1 versus 9, so the totals at 9 must still "
                f"be strictly smaller than at 1 (sum_9={sum_9} sum_1={sum_1})"
            )
            raise HarnessError(
                "bundle totals split but no member archive bytes differed"
            )
        src, at_1, at_9 = chosen
        omit_split, rec_os, src_bytes = measured_round(ws, src)
        require_lossless_archive(
            omit_split, rec_os, src_bytes, what="omit on split member"
        )
        assert omit_split != at_1, (
            "omitted effort on a member whose -1 and -9 archives differ "
            "must not match the -1 archive"
        )
        print(
            f"[F04] B split omit={len(omit_split)} -1={len(at_1)} "
            f"-9={len(at_9)}",
            flush=True,
        )

        opus_src = opus_with_runtime_tags(ws, "celt")
        opus_omit, rec_oo, opus_bytes = measured_round(ws, opus_src)
        opus_nine, rec_on, _ = measured_round(ws, opus_src, "-9")
        require_lossless_archive(opus_omit, rec_oo, opus_bytes, what="omit Opus")
        require_lossless_archive(opus_nine, rec_on, opus_bytes, what="-9 Opus")
        assert opus_omit == opus_nine, (
            "omitting effort must produce the same archive bytes as -9 "
            "on a family-0 Opus file"
        )
        opus_one, rec_o1, _ = measured_round(ws, opus_src, "-1")
        require_lossless_archive(opus_one, rec_o1, opus_bytes, what="-1 Opus")
        if opus_one != opus_nine:
            assert opus_omit != opus_one, (
                "when a family-0 Opus file splits at 1 versus 9, omitted "
                "effort must not match -1"
            )
            print("[F04] B Opus omit!=-1 on split member", flush=True)
        else:
            print("[F04] B Opus 1==9; omit!=-1 not asserted", flush=True)


# ---------------------------------------------------------------------------
# C. Last effort option on the command line applies
# ---------------------------------------------------------------------------


def test_last_effort_option_wins():
    with workspace() as ws:
        bundle = place_vorbis_scale_bundle(ws)
        pairs: list[tuple[str, bytes, bytes]] = []
        sum_1 = 0
        sum_9 = 0
        for src in bundle:
            at_1, rec_1, src_bytes = measured_round(ws, src, "-1")
            at_9, rec_9, _ = measured_round(ws, src, "-9")
            require_lossless_archive(at_1, rec_1, src_bytes, what=f"C -1 {src}")
            require_lossless_archive(at_9, rec_9, src_bytes, what=f"C -9 {src}")
            pairs.append((src, at_1, at_9))
            sum_1 += len(at_1)
            sum_9 += len(at_9)
        chosen = split_member(pairs)
        if chosen is None:
            assert sum_9 < sum_1, (
                "last effort option must apply: the runtime Vorbis bundle "
                "did not split at 1 versus 9, so the totals at 9 must still "
                f"be strictly smaller than at 1 (sum_9={sum_9} sum_1={sum_1})"
            )
            raise HarnessError(
                "bundle totals split but no member archive bytes differed"
            )
        src, at_1, at_9 = chosen
        last_nine, rec_ln, src_bytes = measured_round(ws, src, "-1", "-9")
        last_one, rec_lo, _ = measured_round(ws, src, "-9", "-1")
        last_one_triple, rec_lt, _ = measured_round(ws, src, "-1", "-9", "-1")
        require_lossless_archive(
            last_nine, rec_ln, src_bytes, what="-1 -9 last-wins"
        )
        require_lossless_archive(
            last_one, rec_lo, src_bytes, what="-9 -1 last-wins"
        )
        require_lossless_archive(
            last_one_triple, rec_lt, src_bytes, what="-1 -9 -1 last-wins"
        )
        assert last_nine == at_9, (
            "-1 -9 e must write the same archive bytes as -9 alone"
        )
        assert last_one == at_1, (
            "-9 -1 e must write the same archive bytes as -1 alone"
        )
        assert last_one_triple == at_1, (
            "-1 -9 -1 e must write the same archive bytes as -1 alone"
        )
        print(
            f"[F04] C Vorbis last-wins -1={len(at_1)} -9={len(at_9)}",
            flush=True,
        )

        opus_src = opus_with_runtime_tags(ws, "hybrid")
        opus_one, rec_o1, opus_bytes = measured_round(ws, opus_src, "-1")
        opus_nine, rec_o9, _ = measured_round(ws, opus_src, "-9")
        require_lossless_archive(opus_one, rec_o1, opus_bytes, what="C Opus -1")
        require_lossless_archive(opus_nine, rec_o9, opus_bytes, what="C Opus -9")
        if opus_one != opus_nine:
            last_one, rec_lo, _ = measured_round(ws, opus_src, "-9", "-1")
            require_lossless_archive(
                last_one, rec_lo, opus_bytes, what="C Opus -9 -1"
            )
            assert last_one == opus_one, (
                "when a family-0 Opus file splits at 1 versus 9, "
                "-9 -1 e must match -1 alone"
            )
            assert last_one != opus_nine, (
                "when a family-0 Opus file splits at 1 versus 9, "
                "-9 -1 e must not match -9 alone"
            )
            print("[F04] C Opus last-wins -1 on split member", flush=True)
        else:
            print("[F04] C Opus 1==9; last-wins not asserted", flush=True)


# ---------------------------------------------------------------------------
# D. Effort on expand does not change recovered bytes
# ---------------------------------------------------------------------------


def test_expand_with_effort_token_recovers_original():
    with workspace() as ws:
        for label, src in (
            ("vorbis", vorbis_with_runtime_comment(ws)),
            ("opus", opus_with_runtime_tags(ws, "silk")),
        ):
            src_bytes = ws.read_bytes(src)
            archive_1 = unique_name(f"{label}-a1")
            compress_to(ws, src, archive_1, "-1")
            assert not stored_copy(archive_bytes(ws, archive_1), src_bytes), (
                f"{label} -1 compress destination equals the source"
            )

            base = unique_name(f"{label}-base")
            expand_to(ws, archive_1, base)
            assert ws.read_bytes(base) == src_bytes, (
                f"{label}: expand without effort did not restore the original"
            )

            for effort in ("-3", "-1", "-9"):
                dest = unique_name(f"{label}-eff")
                result = run_product_long(ws, [effort, "d", archive_1, dest])
                require_ok(result)
                if not ws.path_is_file(dest):
                    raise HarnessError(
                        f"{label} {effort} d did not write a regular file"
                    )
                rec = ws.read_bytes(dest)
                assert rec == src_bytes, (
                    f"{label}: {effort} d did not restore the original bytes"
                )
                print(
                    f"[F04] D {label} {effort} d recovered={len(rec)}",
                    flush=True,
                )

            archive_9 = unique_name(f"{label}-a9")
            compress_to(ws, src, archive_9, "-9")
            assert not stored_copy(archive_bytes(ws, archive_9), src_bytes), (
                f"{label} -9 compress destination equals the source"
            )
            out9 = unique_name(f"{label}-from9")
            expand_to(ws, archive_9, out9)
            assert ws.read_bytes(out9) == src_bytes, (
                f"{label}: expand of a -9 archive did not restore the original"
            )


# ---------------------------------------------------------------------------
# E. Vorbis bundle: total size at 9 is strictly smaller than at 1
# ---------------------------------------------------------------------------


def test_vorbis_bundle_effort_nine_total_strictly_smaller_than_one():
    with workspace() as ws:
        bundle = place_vorbis_scale_bundle(ws)
        sum_1 = 0
        sum_9 = 0
        for src in bundle:
            at_1, rec_1, src_bytes = measured_round(ws, src, "-1")
            at_9, rec_9, _ = measured_round(ws, src, "-9")
            require_lossless_archive(at_1, rec_1, src_bytes, what=f"E -1 {src}")
            require_lossless_archive(at_9, rec_9, src_bytes, what=f"E -9 {src}")
            sum_1 += len(at_1)
            sum_9 += len(at_9)
            print(
                f"[F04] E member src={len(src_bytes)} -1={len(at_1)} "
                f"-9={len(at_9)}",
                flush=True,
            )
        assert sum_9 < sum_1, (
            "on a bundle of accepted Vorbis files, the total size of "
            "archives at effort 9 must be strictly smaller than at effort 1: "
            f"sum_9={sum_9} sum_1={sum_1}"
        )
        print(f"[F04] E totals sum_9={sum_9} sum_1={sum_1}", flush=True)


# ---------------------------------------------------------------------------
# F. Opus bundle: total size at 9 is at most the total at 1
# ---------------------------------------------------------------------------


def test_opus_bundle_effort_nine_total_not_larger_than_one():
    with workspace() as ws:
        bundle = place_opus_scale_bundle(ws)
        sum_1 = 0
        sum_9 = 0
        for src in bundle:
            at_1, rec_1, src_bytes = measured_round(ws, src, "-1")
            at_9, rec_9, _ = measured_round(ws, src, "-9")
            require_lossless_archive(at_1, rec_1, src_bytes, what=f"F -1 {src}")
            require_lossless_archive(at_9, rec_9, src_bytes, what=f"F -9 {src}")
            sum_1 += len(at_1)
            sum_9 += len(at_9)
            print(
                f"[F04] F member src={len(src_bytes)} -1={len(at_1)} "
                f"-9={len(at_9)}",
                flush=True,
            )
        assert sum_9 <= sum_1, (
            "on a bundle of accepted family-0 Opus files, the total size "
            "at effort 9 must be less than or equal to the total at effort 1: "
            f"sum_9={sum_9} sum_1={sum_1}"
        )
        print(f"[F04] F totals sum_9={sum_9} sum_1={sum_1}", flush=True)


# ---------------------------------------------------------------------------
# G. Lone `-0` is an unknown option (usage error)
# ---------------------------------------------------------------------------


def test_lone_minus_zero_is_usage_error():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        src_bytes = ws.read_bytes(src)

        dest_ok = unique_name("ok-arc")
        compress_to(ws, src, dest_ok)
        assert not stored_copy(archive_bytes(ws, dest_ok), src_bytes), (
            "baseline compress without -0 did not write a distinct archive"
        )

        dest_bad = unique_name("bad-arc")
        run_expect_usage(ws, ["-0", "e", src, dest_bad])
        require_path_absent(ws, dest_bad)
        print("[F04] G compress -0 dest absent", flush=True)

        out_ok = unique_name("ok-out")
        expand_to(ws, dest_ok, out_ok)
        assert ws.read_bytes(out_ok) == src_bytes, (
            "baseline expand without -0 did not restore the original"
        )

        out_bad = unique_name("bad-out")
        run_expect_usage(ws, ["-0", "d", dest_ok, out_bad])
        require_path_absent(ws, out_bad)
        print("[F04] G expand -0 dest absent", flush=True)

        inp_ok = unique_name("batch-ok") + ".ogg"
        ws.write(inp_ok, src_bytes)
        orp_ok = derived_batch_archive(inp_ok)
        baseline = run_product_long(ws, ["-b", "e", inp_ok])
        require_ok(baseline)
        assert ws.path_is_file(orp_ok), (
            "baseline batch compress without -0 did not write the derived archive"
        )

        inp_bad = unique_name("batch-bad") + ".ogg"
        ws.write(inp_bad, src_bytes)
        orp_bad = derived_batch_archive(inp_bad)
        run_expect_usage(ws, ["-0", "-b", "e", inp_bad])
        require_path_absent(ws, orp_bad)
        print("[F04] G batch -0 derived dest absent", flush=True)


# ---------------------------------------------------------------------------
# G2. Effort 10 is not an effort option (L189). Not a named error class.
# ---------------------------------------------------------------------------


def test_effort_ten_is_not_an_effort_option():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        src_bytes = ws.read_bytes(src)

        dest_ok = unique_name("ok-nine")
        compress_to(ws, src, dest_ok, "-9")
        assert not stored_copy(archive_bytes(ws, dest_ok), src_bytes), (
            "baseline compress with effort option -9 did not write a "
            "distinct archive"
        )

        dest_ten = unique_name("ten-arc")
        result = run_product(ws, ["-10", "e", src, dest_ten])
        print(
            f"[F04] G2 -10 e exit={result.returncode} "
            f"stderr_len={len(result.stderr)} dest_present="
            f"{ws.path_is_file(dest_ten)}",
            flush=True,
        )
        assert result.returncode != 0, (
            "there is no effort 10: the token that would name that effort "
            "is not an effort option and must not be accepted on compress "
            f"(exit={result.returncode})"
        )
        require_path_absent(ws, dest_ten)


# ---------------------------------------------------------------------------
# H. Batch compress honours effort, default, last-wins, and a mid token
# ---------------------------------------------------------------------------


def test_batch_compress_honours_effort_and_default():
    with workspace() as ws:
        bundle = place_vorbis_scale_bundle(ws)
        pairs: list[tuple[str, bytes, bytes]] = []
        sum_1 = 0
        sum_9 = 0
        for src in bundle:
            at_1, rec_1, src_bytes = measured_round(ws, src, "-1")
            at_9, rec_9, _ = measured_round(ws, src, "-9")
            require_lossless_archive(at_1, rec_1, src_bytes, what=f"H -1 {src}")
            require_lossless_archive(at_9, rec_9, src_bytes, what=f"H -9 {src}")
            pairs.append((src, at_1, at_9))
            sum_1 += len(at_1)
            sum_9 += len(at_9)
        chosen = split_member(pairs)
        if chosen is None:
            assert sum_9 < sum_1, (
                "batch compress must honour effort: the runtime Vorbis bundle "
                "did not split at 1 versus 9, so the totals at 9 must still "
                f"be strictly smaller than at 1 (sum_9={sum_9} sum_1={sum_1})"
            )
            raise HarnessError(
                "bundle totals split but no member archive bytes differed"
            )

        src, _at_1, _at_9 = chosen
        src_bytes = ws.read_bytes(src)

        dest_1, bytes_1 = batch_compress_to(ws, src_bytes, "-1")
        dest_9, bytes_9 = batch_compress_to(ws, src_bytes, "-9")
        assert not stored_copy(bytes_1, src_bytes), (
            "-1 -b e destination bytes carry the source verbatim (copy stub)"
        )
        assert not stored_copy(bytes_9, src_bytes), (
            "-9 -b e destination bytes carry the source verbatim (copy stub)"
        )
        assert bytes_1 != bytes_9, (
            "batch compress of a member that splits at 1 versus 9 must "
            "write different .orp bytes at -1 and at -9"
        )
        rec_1 = unique_name("batch-r1")
        rec_9 = unique_name("batch-r9")
        expand_to(ws, dest_1, rec_1)
        expand_to(ws, dest_9, rec_9)
        assert ws.read_bytes(rec_1) == src_bytes, (
            "expand of the -1 batch archive did not restore the original"
        )
        assert ws.read_bytes(rec_9) == src_bytes, (
            "expand of the -9 batch archive did not restore the original"
        )

        dest_omit, bytes_omit = batch_compress_to(ws, src_bytes)
        rec_omit = unique_name("batch-ro")
        expand_to(ws, dest_omit, rec_omit)
        assert ws.read_bytes(rec_omit) == src_bytes, (
            "expand of the omitted-effort batch archive did not restore "
            "the original"
        )
        assert bytes_omit == bytes_9, (
            "batch compress with omitted effort must match -9 -b"
        )
        assert bytes_omit != bytes_1, (
            "batch compress with omitted effort must not match -1 -b"
        )

        dest_last1, bytes_last1 = batch_compress_to(ws, src_bytes, "-9", "-1")
        rec_last1 = unique_name("batch-rl1")
        expand_to(ws, dest_last1, rec_last1)
        assert ws.read_bytes(rec_last1) == src_bytes, (
            "expand of the -9 -1 batch archive did not restore the original"
        )
        assert bytes_last1 == bytes_1, (
            "-9 -1 -b e must write the same .orp bytes as -1 -b"
        )
        assert bytes_last1 != bytes_9, (
            "-9 -1 -b e must not write the same .orp bytes as -9 -b"
        )

        dest_last9, bytes_last9 = batch_compress_to(ws, src_bytes, "-1", "-9")
        rec_last9 = unique_name("batch-rl9")
        expand_to(ws, dest_last9, rec_last9)
        assert ws.read_bytes(rec_last9) == src_bytes, (
            "expand of the -1 -9 batch archive did not restore the original"
        )
        assert bytes_last9 == bytes_9, (
            "-1 -9 -b e must write the same .orp bytes as -9 -b"
        )

        dest_mid, bytes_mid = batch_compress_to(ws, src_bytes, "-5")
        rec_mid = unique_name("batch-rm")
        expand_to(ws, dest_mid, rec_mid)
        assert ws.path_is_file(dest_mid), (
            "batch compress with -5 did not write the derived archive"
        )
        assert not stored_copy(bytes_mid, src_bytes), (
            "-5 -b e destination bytes carry the source verbatim (copy stub)"
        )
        assert ws.read_bytes(rec_mid) == src_bytes, (
            "expand of the -5 batch archive did not restore the original"
        )
        print(
            f"[F04] H -1={len(bytes_1)} -9={len(bytes_9)} omit={len(bytes_omit)} "
            f"mid={len(bytes_mid)}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# I. Effort 9 recompresses each ordinary file below its own size
# ---------------------------------------------------------------------------


def test_effort_nine_archive_of_each_ordinary_file_is_smaller_than_the_file():
    with workspace() as ws:
        members = place_ordinary_bundle(ws)
        codecs = {codec for codec, _rel in members}
        assert codecs == {"vorbis", "opus"}, f"bundle lacks a codec: {codecs}"
        for codec, src in members:
            archive, recovered, src_bytes = measured_round(ws, src, "-9")
            require_lossless_archive(archive, recovered, src_bytes, what=f"I {src}")
            print(
                f"[F04] I {codec} src={len(src_bytes)} -9={len(archive)}",
                flush=True,
            )
            assert len(archive) < len(src_bytes), (
                f"I: the effort-9 archive of an ordinary {codec} input is not "
                "smaller than its input: "
                f"{src!r} is {len(src_bytes)} bytes, archive {len(archive)}"
            )


# ---------------------------------------------------------------------------
# J. No effort stores the input's audio packets as copies
# ---------------------------------------------------------------------------


def test_no_effort_carries_the_audio_packets_as_stored_copies():
    with workspace() as ws:
        members = place_ordinary_bundle(ws)
        measured_any = {"vorbis": 0, "opus": 0}
        for codec, src in members:
            for effort in ("-1", "-5", "-9"):
                archive, recovered, src_bytes = measured_round(ws, src, effort)
                require_lossless_archive(
                    archive, recovered, src_bytes, what=f"J {effort} {src}"
                )
                found, measured = verbatim_audio_share(archive, src_bytes)
                print(
                    f"[F04] J {codec} {effort} verbatim={found}/{measured}",
                    flush=True,
                )
                if measured == 0:
                    continue
                measured_any[codec] += measured
                assert 2 * found < measured, (
                    "J: the archive holds at least half of the measured audio "
                    "bytes verbatim; "
                    f"{src!r} at {effort}: {found} of {measured} bytes verbatim"
                )
        assert all(measured_any.values()), (
            f"verbatim measurement covered no audio bytes: {measured_any}"
        )
