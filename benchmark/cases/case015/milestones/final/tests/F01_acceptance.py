# feature: F01
"""Acceptance: command invocation, verbs, help, version, and exit status."""

from __future__ import annotations

from F01_helpers import (
    MEMCAP_ENV,
    PRODUCT_NAME,
    REQUIRED_HELP_NAMES,
    SIMD_ENV,
    SIMD_NATIVE,
    SIMD_PORTABLE,
    cli_tokens,
    derived_batch_archive,
    files_identical,
    invalid_simd_token,
    jobs_trailing_value,
    malformed_memcap_runtime,
    place_non_ogg,
    place_opus,
    place_placeholder,
    place_vorbis,
    require_bytes_unchanged,
    require_file_access,
    require_help_usage,
    require_ok,
    require_path_absent,
    require_refusal,
    require_compiled_in_identity_field,
    require_stderr_identifies_path_failure,
    require_stdout_text,
    require_usage,
    require_version_identity,
    run_expect_usage,
    run_expect_usage_no_archive,
    run_product,
    same_existing_file,
    unique_name,
    unknown_long_option,
    unknown_short_option,
    unknown_verb,
    version_dispatch,
)
from _harness import stored_copy, workspace


# ---------------------------------------------------------------------------
# A. Help
# ---------------------------------------------------------------------------


def test_help_short_and_long_exit_0_on_stdout():
    with workspace() as ws:
        for flag in ("-h", "--help"):
            result = run_product(ws, [flag])
            require_ok(result)
            text = require_stdout_text(result)
            assert result.returncode == 0, (
                f"{flag} exited {result.returncode}; stderr={result.stderr!r}"
            )
            assert text, (
                f"{flag} wrote no usage on stdout; stderr={result.stderr!r}"
            )
            print(f"[F01] {flag} stdout_len={len(text)}", flush=True)


def test_help_names_verbs_effort_options_and_status_classes():
    with workspace() as ws:
        for flag in ("-h", "--help"):
            result = run_product(ws, [flag])
            require_ok(result)
            text = require_stdout_text(result)
            require_help_usage(text)
            tokens = cli_tokens(text)
            missing = [name for name in REQUIRED_HELP_NAMES if name not in tokens]
            assert not missing, (
                f"{flag} help stdout missing required whole tokens {missing}; "
                f"have={sorted(tokens)}"
            )
            assert "-1" in text and "-9" in text, (
                f"{flag} help stdout does not name effort options -1 and -9"
            )
            print(
                f"[F01] {flag} named verbs, range, options, statuses, "
                f"and default effort -9",
                flush=True,
            )


# ---------------------------------------------------------------------------
# B. Version
# ---------------------------------------------------------------------------


def test_version_short_and_long_exit_0_on_stdout():
    with workspace() as ws:
        for flag in ("-v", "--version"):
            result = run_product(ws, [flag])
            require_ok(result)
            text = require_stdout_text(result)
            assert result.returncode == 0, (
                f"{flag} exited {result.returncode}; stderr={result.stderr!r}"
            )
            assert text, (
                f"{flag} wrote no identity on stdout; stderr={result.stderr!r}"
            )


def test_help_and_version_stdout_differ():
    with workspace() as ws:
        help_run = run_product(ws, ["-h"])
        version_run = run_product(ws, ["-v"])
        require_ok(help_run)
        require_ok(version_run)
        help_text = require_stdout_text(help_run)
        version_text = require_stdout_text(version_run)
        require_help_usage(help_text)
        require_version_identity(version_text, help_text)
        payloads = require_compiled_in_identity_field(version_text, help_text)
        assert help_text != version_text, (
            "help stdout and version stdout are identical"
        )
        print(
            "[F01] help names usage including default effort -9; "
            "version names version, host, dedicated compiled-in field, code path; "
            f"compiled_in_payloads={len(payloads)}",
            flush=True,
        )


def test_version_names_the_product():
    with workspace() as ws:
        result = run_product(ws, ["--version"])
        require_ok(result)
        text = require_stdout_text(result)
        tokens = cli_tokens(text)
        assert PRODUCT_NAME in tokens, (
            f"version stdout does not name the product as a whole token; "
            f"tokens={sorted(tokens)}"
        )


def test_version_identity_names_version_host_opus_and_dispatch():
    with workspace() as ws:
        help_run = run_product(ws, ["--help"])
        version_run = run_product(ws, ["--version"])
        require_ok(help_run)
        require_ok(version_run)
        help_text = require_stdout_text(help_run)
        version_text = require_stdout_text(version_run)
        require_version_identity(version_text, help_text)
        tokens = cli_tokens(version_text)
        dispatched = version_dispatch(version_text)
        payloads = require_compiled_in_identity_field(version_text, help_text)
        assert PRODUCT_NAME in tokens, (
            f"version stdout does not name the product as a whole token; "
            f"tokens={sorted(tokens)}"
        )
        print(
            f"[F01] version identity named; dispatch={dispatched} "
            f"compiled_in_payloads={len(payloads)}",
            flush=True,
        )


def test_version_portable_override_is_not_usage_error():
    with workspace() as ws:
        unset = run_product(ws, ["-v"])
        require_ok(unset)
        require_stdout_text(unset)
        assert unset.returncode == 0, (
            f"unset SIMD version exited {unset.returncode}; stderr={unset.stderr!r}"
        )
        portable = run_product(ws, ["-v"], env_updates={SIMD_ENV: SIMD_PORTABLE})
        require_ok(portable)
        text = require_stdout_text(portable)
        assert portable.returncode == 0, (
            f"ORP_SIMD={SIMD_PORTABLE} on version exited {portable.returncode}; "
            f"stderr={portable.stderr!r}"
        )
        assert text, (
            f"ORP_SIMD={SIMD_PORTABLE} on version wrote no identity; "
            f"stderr={portable.stderr!r}"
        )
        print(f"[F01] ORP_SIMD={SIMD_PORTABLE} on version is not a usage error", flush=True)


# ---------------------------------------------------------------------------
# C. Short Vorbis compress then expand
# ---------------------------------------------------------------------------


def test_compress_expand_two_distinct_vorbis_files_exit_0_and_restore_bytes():
    with workspace() as ws:
        seen_src: list[bytes] = []
        for which in ("a", "b"):
            src = place_vorbis(ws, which)
            src_bytes = ws.read_bytes(src)
            seen_src.append(src_bytes)
            dest = unique_name(f"arc-{which}")
            recovered = unique_name(f"out-{which}")
            enc = run_product(ws, ["e", src, dest])
            require_ok(enc)
            assert ws.path_is_file(dest), f"compress did not write {dest}"
            dest_bytes = ws.read_bytes(dest)
            assert not stored_copy(dest_bytes, src_bytes), (
                "compress destination bytes carry the source verbatim (copy stub)"
            )
            dec = run_product(ws, ["d", dest, recovered])
            require_ok(dec)
            assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
                f"expand of {which} did not restore the source bytes"
            )
            print(
                f"[F01] round-trip {which} src={len(src_bytes)} dest={len(dest_bytes)}",
                flush=True,
            )
        assert seen_src[0] != seen_src[1], "suite Vorbis fixtures were not distinct"


def test_compress_valid_opus_to_distinct_destination_exits_0():
    with workspace() as ws:
        src = place_opus(ws)
        src_bytes = ws.read_bytes(src)
        dest = unique_name("opus-arc")
        enc = run_product(ws, ["e", src, dest])
        require_ok(enc)
        assert ws.path_is_file(dest), f"Opus compress did not write {dest}"
        dest_bytes = ws.read_bytes(dest)
        assert not stored_copy(dest_bytes, src_bytes), (
            "Opus compress destination bytes carry the source verbatim (copy stub)"
        )
        print(f"[F01] Opus compress src={len(src_bytes)} dest={len(dest_bytes)}", flush=True)


# ---------------------------------------------------------------------------
# E. Missing input is 3; non-Ogg is 1
# ---------------------------------------------------------------------------


def test_missing_compress_input_is_file_access_not_refusal():
    with workspace() as ws:
        missing = unique_name("missing-in")
        dest = unique_name("missing-out")
        result = run_product(ws, ["e", missing, dest])
        require_file_access(result)
        assert result.returncode != 1, (
            "missing compress input exited 1 (refusal) instead of 3"
        )
        require_stderr_identifies_path_failure(result, missing)
        print("[F01] missing input exit=3", flush=True)


def test_non_ogg_compress_is_refusal():
    with workspace() as ws:
        src = place_non_ogg(ws)
        dest = unique_name("nonogg-out")
        result = run_product(ws, ["e", src, dest])
        require_refusal(result)
        assert result.returncode != 3, (
            "non-Ogg compress exited 3 (file-access) instead of 1"
        )
        print("[F01] non-Ogg exit=1", flush=True)


# ---------------------------------------------------------------------------
# F. Usage errors
# ---------------------------------------------------------------------------


def test_empty_argv_is_usage_error():
    with workspace() as ws:
        run_expect_usage_no_archive(ws, [])


def test_unknown_verb_is_usage_error():
    with workspace() as ws:
        left = place_placeholder(ws)
        right = place_placeholder(ws)
        left_bytes = ws.read_bytes(left)
        right_bytes = ws.read_bytes(right)
        verb = unknown_verb()
        result = run_expect_usage_no_archive(ws, [verb, left, right])
        assert result.returncode != 3, (
            f"unknown verb {verb!r} exited 3 (treated as a path)"
        )
        require_bytes_unchanged(ws, left, left_bytes)
        require_bytes_unchanged(ws, right, right_bytes)
        print(f"[F01] unknown verb {verb!r} exit=2", flush=True)


def test_unknown_long_option_is_usage_error():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        dest = unique_name("longopt-out")
        flag = unknown_long_option()
        run_expect_usage(ws, [flag, "e", src, dest])
        require_path_absent(ws, dest)
        print(f"[F01] unknown long option {flag!r} exit=2", flush=True)


def test_unknown_short_option_is_usage_error():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        dest = unique_name("shortopt-out")
        flag = unknown_short_option()
        run_expect_usage(ws, [flag, "e", src, dest])
        require_path_absent(ws, dest)
        print(f"[F01] unknown short option {flag!r} exit=2", flush=True)


def test_compress_and_expand_require_two_paths():
    with workspace() as ws:
        vorbis = place_vorbis(ws, "a")
        vorbis_bytes = ws.read_bytes(vorbis)

        run_expect_usage_no_archive(ws, ["e"])

        run_expect_usage_no_archive(ws, ["e", vorbis])
        require_bytes_unchanged(ws, vorbis, vorbis_bytes)

        never = unique_name("never-e")
        run_expect_usage(ws, ["e", never])
        require_path_absent(ws, never)

        archive = unique_name("need-two-arc")
        enc = run_product(ws, ["e", vorbis, archive])
        require_ok(enc)
        assert ws.path_is_file(archive), "setup compress did not write an archive"
        archive_bytes = ws.read_bytes(archive)

        run_expect_usage_no_archive(ws, ["d"])

        run_expect_usage_no_archive(ws, ["d", archive])
        require_bytes_unchanged(ws, archive, archive_bytes)

        never_d = unique_name("never-d")
        run_expect_usage(ws, ["d", never_d])
        require_path_absent(ws, never_d)


def test_dump_and_pages_require_exactly_one_path():
    with workspace() as ws:
        first = place_placeholder(ws)
        second = place_placeholder(ws)
        for verb in ("dump", "pages"):
            run_expect_usage_no_archive(ws, [verb])
            run_expect_usage_no_archive(ws, [verb, first, second])
            print(f"[F01] {verb} zero/two paths exit=2", flush=True)


def test_batch_without_paths_is_usage_error():
    with workspace() as ws:
        run_expect_usage_no_archive(ws, ["-b", "e"])
        run_expect_usage_no_archive(ws, ["--batch", "d"])


def test_jobs_zero_with_batch_is_usage_error():
    with workspace() as ws:
        baseline_src = place_vorbis(ws, "a")
        baseline = run_product(ws, ["--jobs=1", "-b", "e", baseline_src])
        assert baseline.returncode != 2, (
            f"--jobs=1 with batch exited 2; stderr={baseline.stderr!r}"
        )
        print(f"[F01] --jobs=1 batch baseline exit={baseline.returncode}", flush=True)

        error_src = place_vorbis(ws, "b")
        run_expect_usage_no_archive(ws, ["--jobs=0", "-b", "e", error_src])
        require_path_absent(ws, derived_batch_archive(error_src))


def test_jobs_syntax_on_single_file_compress_is_usage_error():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        ok_dest = unique_name("jobs-ok")
        baseline = run_product(ws, ["--jobs=1", "e", src, ok_dest])
        assert baseline.returncode != 2, (
            f"--jobs=1 on single-file compress exited 2; stderr={baseline.stderr!r}"
        )
        print(
            f"[F01] --jobs=1 single-file baseline exit={baseline.returncode}",
            flush=True,
        )

        zero_dest = unique_name("jobs-zero")
        run_expect_usage(ws, ["--jobs=0", "e", src, zero_dest])
        require_path_absent(ws, zero_dest)

        sign_dest = unique_name("jobs-sign")
        run_expect_usage(ws, ["--jobs=+1", "e", src, sign_dest])
        require_path_absent(ws, sign_dest)

        trail = jobs_trailing_value()
        assert any(not ch.isdigit() for ch in trail), (
            f"--jobs trailing sample {trail!r} is a bare integer, not trailing text"
        )
        trail_dest = unique_name("jobs-trail")
        run_expect_usage(ws, [f"--jobs={trail}", "e", src, trail_dest])
        require_path_absent(ws, trail_dest)
        print(f"[F01] --jobs trailing {trail!r} exit=2", flush=True)


# ---------------------------------------------------------------------------
# G. Missing output directory
# ---------------------------------------------------------------------------


def test_missing_output_directory_is_file_access():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        dest = f"{unique_name('no-dir')}/out"
        result = run_product(ws, ["e", src, dest])
        require_file_access(result)
        require_path_absent(ws, dest)
        require_stderr_identifies_path_failure(result, dest)
        assert result.returncode == 3, (
            f"missing output directory exited {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"missing output directory left stderr empty; stdout={result.stdout!r}"
        )
        print("[F01] missing output directory exit=3", flush=True)


# ---------------------------------------------------------------------------
# H. Same file as input and output
# ---------------------------------------------------------------------------


def test_compress_same_path_string_is_file_access_and_preserves_bytes():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        before = ws.read_bytes(src)
        result = run_product(ws, ["e", src, src])
        require_file_access(result)
        require_bytes_unchanged(ws, src, before)
        assert result.returncode == 3, (
            f"compress same-path exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"compress same-path left stderr empty; stdout={result.stdout!r}"
        )
        assert ws.read_bytes(src) == before, (
            f"compress same-path changed input bytes of {src!r}"
        )


def test_compress_same_existing_file_via_two_paths():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        abs_src = str(ws.resolve(src))
        assert same_existing_file(ws.resolve(src), abs_src), (
            "fixture paths do not name the same existing file"
        )
        before = ws.read_bytes(src)
        result = run_product(ws, ["e", src, abs_src])
        require_file_access(result)
        require_bytes_unchanged(ws, src, before)


def test_expand_same_path_string_is_file_access_and_preserves_bytes():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        archive = unique_name("same-str-arc")
        enc = run_product(ws, ["e", src, archive])
        require_ok(enc)
        before = ws.read_bytes(archive)
        result = run_product(ws, ["d", archive, archive])
        require_file_access(result)
        require_bytes_unchanged(ws, archive, before)
        assert result.returncode == 3, (
            f"expand same-path exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"expand same-path left stderr empty; stdout={result.stdout!r}"
        )
        assert ws.read_bytes(archive) == before, (
            f"expand same-path changed archive bytes of {archive!r}"
        )


def test_expand_same_existing_file_via_two_paths():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        archive = unique_name("same-two-arc")
        enc = run_product(ws, ["e", src, archive])
        require_ok(enc)
        abs_arc = str(ws.resolve(archive))
        assert same_existing_file(ws.resolve(archive), abs_arc), (
            "archive paths do not name the same existing file"
        )
        before = ws.read_bytes(archive)
        result = run_product(ws, ["d", archive, abs_arc])
        require_file_access(result)
        require_bytes_unchanged(ws, archive, before)


# ---------------------------------------------------------------------------
# I. ORP_MEMCAP
# ---------------------------------------------------------------------------


def test_malformed_memcap_abc_is_usage_error_on_a_verb():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        dest = unique_name("memcap-abc")
        run_expect_usage(
            ws, ["e", src, dest], env_updates={MEMCAP_ENV: "abc"}
        )
        require_path_absent(ws, dest)


def test_malformed_memcap_runtime_value_is_usage_error():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        dest = unique_name("memcap-rt")
        value = malformed_memcap_runtime()
        run_expect_usage(
            ws, ["e", src, dest], env_updates={MEMCAP_ENV: value}
        )
        require_path_absent(ws, dest)
        print(f"[F01] ORP_MEMCAP={value!r} exit=2", flush=True)


def test_malformed_memcap_on_version_is_usage_error():
    with workspace() as ws:
        run_expect_usage(ws, ["-v"], env_updates={MEMCAP_ENV: "abc"})


def test_well_formed_memcap_zero_is_not_usage_error_on_compress():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        dest = unique_name("memcap-zero")
        result = run_product(
            ws, ["e", src, dest], env_updates={MEMCAP_ENV: "0"}
        )
        assert result.returncode != 2, (
            f"ORP_MEMCAP=0 on compress exited 2; stderr={result.stderr!r}"
        )
        if result.returncode == 0:
            assert ws.path_is_file(dest), (
                "ORP_MEMCAP=0 compress exited 0 but did not write dest"
            )
        print(f"[F01] ORP_MEMCAP=0 compress exit={result.returncode}", flush=True)


# ---------------------------------------------------------------------------
# J. ORP_SIMD on version
# ---------------------------------------------------------------------------


def test_invalid_simd_token_on_version_is_usage_error():
    with workspace() as ws:
        good = run_product(ws, ["-v"], env_updates={SIMD_ENV: SIMD_PORTABLE})
        require_ok(good)
        require_stdout_text(good)
        assert good.returncode == 0, (
            f"ORP_SIMD={SIMD_PORTABLE} baseline exited {good.returncode}; "
            f"stderr={good.stderr!r}"
        )

        bad = invalid_simd_token()
        result = run_product(ws, ["-v"], env_updates={SIMD_ENV: bad})
        require_usage(result)
        assert result.returncode == 2, (
            f"ORP_SIMD={bad!r} on version exited {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"ORP_SIMD={bad!r} on version left stderr empty; "
            f"stdout={result.stdout!r}"
        )
        print(f"[F01] ORP_SIMD={bad!r} on version exit=2", flush=True)


def test_code_path_override_reports_dispatch_and_keeps_archives_identical():
    with workspace() as ws:
        unset = run_product(ws, ["-v"])
        require_ok(unset)
        default_path = version_dispatch(require_stdout_text(unset))
        print(f"[F01] default dispatch={default_path}", flush=True)

        accepted: list[str] = []
        refused: list[str] = []
        for name in (SIMD_PORTABLE, SIMD_NATIVE):
            result = run_product(ws, ["-v"], env_updates={SIMD_ENV: name})
            if result.returncode == 0:
                dispatched = version_dispatch(require_stdout_text(result))
                assert dispatched == name, (
                    f"ORP_SIMD={name} on version reports dispatch {dispatched!r}"
                )
                accepted.append(name)
            elif result.returncode == 2:
                require_usage(result)
                refused.append(name)
            else:
                raise AssertionError(
                    f"ORP_SIMD={name} exited {result.returncode}; "
                    f"stderr={result.stderr!r}"
                )
        assert SIMD_PORTABLE in accepted, (
            f"forcing the portable path was not accepted; accepted={accepted} "
            f"refused={refused}"
        )
        if default_path == SIMD_NATIVE:
            assert SIMD_NATIVE in accepted, (
                "default dispatch is a CPU-specific path, yet forcing a "
                "CPU-specific path was a usage error"
            )

        from F03_helpers import place_opus_classified

        sources = (
            ("vorbis", place_vorbis(ws, "a")),
            ("opus", place_opus_classified(ws, "hybrid")),
        )
        arms: list[str | None] = [None, *accepted]
        runs = [(codec, src, effort) for codec, src in sources for effort in ((), ("-1",))]
        for codec, src, effort in runs:
            src_bytes = ws.read_bytes(src)
            archives: list[bytes] = []
            for name in arms:
                label = name or "unset"
                env = {SIMD_ENV: name} if name else None
                dest = unique_name(f"k-{label}")
                recovered = unique_name(f"o-{label}")
                enc = run_product(ws, [*effort, "e", src, dest], env_updates=env)
                require_ok(enc)
                assert ws.path_is_file(dest), f"{label} compress did not write {dest}"
                dest_bytes = ws.read_bytes(dest)
                assert not stored_copy(dest_bytes, src_bytes), (
                    f"{label} compress destination bytes carry the source verbatim"
                )
                archives.append(dest_bytes)
                dec = run_product(ws, ["d", dest, recovered])
                require_ok(dec)
                assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
                    f"expand after the {label} path did not restore the source bytes"
                )
            first = archives[0]
            for other, name in zip(archives[1:], arms[1:]):
                assert other == first, (
                    f"archive under ORP_SIMD={name} differs from the default "
                    f"(every path must be bit-identical; {codec} effort {effort!r})"
                )
        print(
            f"[F01] code path accepted={accepted} refused={refused} "
            f"archives={len(archives)}",
            flush=True,
        )
