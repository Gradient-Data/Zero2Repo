# feature: F18
"""Logs, completion, dedup, and merge-driver acceptance tests.

PRD: FP-18, the PRD command inventory (porcelain names), core capabilities (binary off PATH),
track merge=lfs (non-goals, FP-18), sharded store (FP-05, FP-18), LFS namespace (cross-cutting requirements).
Message wording, ioctl names, and flag
spellings are not pinned.
"""

from __future__ import annotations

from pathlib import Path

from _harness import product_bin, token, workspace
from _helpers import (
    add_git_remote,
    assert_clone_among_porcelain_candidates,
    assert_porcelain_subcommand_candidates,
    call_named_logs_diagnostic_exception,
    commit_ordinary_blob,
    configure_user_merge_driver,
    cow_capable_repo_root,
    default_lfs_store_root,
    emit_completion_script,
    fpath_zsh_completion_candidates,
    git_check_attr,
    git_dir,
    independent_cow_supported,
    index_blob,
    install_local_keeping_process,
    invoke_dedup,
    logs_clear,
    logs_list_names,
    logs_show_last,
    logs_show_named,
    non_cow_repo_root,
    path_without_product_bin,
    pointer_matches_digest_and_size,
    prepare_tracked_commit,
    register_byte_transform_extension,
    release_cow_filesystem,
    require_cow_clone,
    require_flag_shaped_candidates,
    require_invalid_unlike_success,
    require_lfs_enable_roles,
    require_listed_log_file_under_lfs_namespace,
    require_not_cow_clone,
    require_object_absent,
    require_object_bytes,
    require_omits_token,
    require_success,
    runtime_http_url,
    set_path_merge_attribute,
    sha256_hex,
    sharded_object_rel,
    shell_completion_candidates,
    track_pattern,
)


def _tracked_rel() -> str:
    return f"blob_{token()}.dat"


def _large_payload() -> bytes:
    marker = token()
    line = f"{marker}\n".encode("utf-8")
    return line * 8000


def _three_way_texts() -> tuple[bytes, bytes, bytes, bytes]:
    ancestor = b"A\nX\nC\n"
    current = b"B\nX\nC\n"
    other = b"A\nX\nD\n"
    merged = b"B\nX\nD\n"
    return ancestor, current, other, merged


def _commit_bytes(ws, relpath: str, data: bytes, message: str) -> None:
    ws.write(relpath, data)
    added = ws.git(["add", "--", relpath, ".gitattributes"])
    assert added.returncode == 0, (
        f"git add {relpath!r} failed (exit {added.returncode}): "
        f"{added.stderr_text}"
    )
    committed = ws.git(["commit", "-m", message])
    assert committed.returncode == 0, (
        f"git commit {relpath!r} failed (exit {committed.returncode}): "
        f"{committed.stderr_text}"
    )


def _setup_tracked_repo(ws, relpath: str, data: bytes) -> str:
    digest = prepare_tracked_commit(ws, relpath, data)
    store = default_lfs_store_root(ws)
    require_object_bytes(store, digest, data)
    require_not_cow_clone(ws.resolve(relpath), store / sharded_object_rel(digest))
    return digest


def _setup_merge_layout(
    ws,
    *,
    relpath: str,
    ancestor: bytes,
    current: bytes,
    other: bytes,
    user_attr: str | None,
) -> str:
    install_local_keeping_process(ws)
    suffix = Path(relpath).suffix
    pattern = f"*{suffix}"
    track_pattern(ws, pattern)
    require_lfs_enable_roles(ws, relpath)
    if user_attr is not None:
        configure_user_merge_driver(ws, user_attr)
        set_path_merge_attribute(ws, pattern, user_attr)
        values = git_check_attr(ws, relpath, ["merge"])
        assert values["merge"] == user_attr, (
            f"merge attribute is {values['merge']!r}, not {user_attr!r}"
        )
    else:
        values = git_check_attr(ws, relpath, ["merge"])
        assert values["merge"] == "lfs", (
            f"track-only merge attribute is {values['merge']!r}, not lfs"
        )
    _commit_bytes(ws, relpath, ancestor, "ancestor")
    other_name = f"other_{token()}"
    branched = ws.git(["checkout", "-b", other_name])
    assert branched.returncode == 0, (
        f"git checkout -b {other_name!r} failed "
        f"(exit {branched.returncode}): {branched.stderr_text}"
    )
    _commit_bytes(ws, relpath, other, "other")
    checked = ws.git(["checkout", "main"])
    assert checked.returncode == 0, (
        f"git checkout main failed (exit {checked.returncode}): "
        f"{checked.stderr_text}"
    )
    _commit_bytes(ws, relpath, current, "current")
    print(
        f"merge layout rel={relpath!r} other_branch={other_name!r} "
        f"user_attr={user_attr!r}"
    )
    return other_name


def test_logs_diagnostic_exception_fails_and_list_shows_new_log() -> None:
    """A diagnostic logs sub-entry fails and the default list names a new log."""
    with workspace() as ws:
        ws.init_repo()
        before = logs_list_names(ws)
        print(f"logs before diagnostic={before!r}")
        assert before == [], f"default logs list was not empty: {before!r}"
        call_named_logs_diagnostic_exception(ws)
        after = logs_list_names(ws, via_git=False)
        print(f"logs after diagnostic={after!r}")
        added = [name for name in after if name not in before]
        assert added, f"diagnostic failure added no listed log; after={after!r}"
        name = added[-1]
        details = logs_show_named(ws, name)
        assert details, f"named log {name!r} was empty after a diagnostic failure"
        disk = require_listed_log_file_under_lfs_namespace(ws, name)
        print(f"listed log file={disk} bytes={len(details)}")
        last = logs_show_last(ws)
        assert last == details, (
            "logs last did not match the only new named show "
            f"name={name!r} last={last!r} named={details!r}"
        )
        namespace = git_dir(ws) / "lfs"
        assert namespace.is_dir(), f"LFS namespace is not a directory: {namespace}"


def test_logs_named_show_and_last_select_the_most_recent() -> None:
    """Named show keeps the first log; last follows the second diagnostic."""
    with workspace() as ws:
        ws.init_repo()
        call_named_logs_diagnostic_exception(ws)
        first_names = logs_list_names(ws)
        assert first_names, f"first diagnostic listed no names: {first_names!r}"
        n1 = first_names[-1]
        b1 = logs_show_named(ws, n1)
        assert b1, f"first named log {n1!r} was empty"
        require_listed_log_file_under_lfs_namespace(ws, n1)
        call_named_logs_diagnostic_exception(ws)
        second_names = logs_list_names(ws)
        added = [name for name in second_names if name not in first_names]
        assert added, (
            "second diagnostic added no new listed name; "
            f"first={first_names!r} second={second_names!r}"
        )
        n2 = added[-1]
        assert n2 != n1, f"second diagnostic reused the first name {n1!r}"
        require_listed_log_file_under_lfs_namespace(ws, n2)
        still_b1 = logs_show_named(ws, n1)
        b2 = logs_show_named(ws, n2)
        assert still_b1 == b1, (
            f"named show of {n1!r} changed after a later diagnostic"
        )
        assert b2, f"second named log {n2!r} was empty"
        last = logs_show_last(ws)
        assert last == b2, (
            "logs last did not match the most recent named show "
            f"n2={n2!r} last={last!r} b2={b2!r}"
        )
        if b1 != b2:
            assert last != b1, (
                "logs last still matched the first log after a newer one "
                f"n1={n1!r} n2={n2!r}"
            )
        print(f"n1={n1!r} n2={n2!r} b1_len={len(b1)} b2_len={len(b2)}")


def test_logs_clear_empties_subsequent_list() -> None:
    """Clear empties the subsequent default list after a live nonempty baseline."""
    with workspace() as ws:
        ws.init_repo()
        call_named_logs_diagnostic_exception(ws)
        names = logs_list_names(ws)
        assert names, f"clear baseline listed no logs: {names!r}"
        require_listed_log_file_under_lfs_namespace(ws, names[-1])
        logs_clear(ws)
        after = logs_list_names(ws)
        print(f"logs after clear={after!r}")
        assert after == [], f"logs list was not empty after clear: {after!r}"


def test_completion_bash_script_yields_porcelain_candidates_for_standalone_binary() -> None:
    """Bash loads the emitted script and completes standalone porcelain names."""
    with workspace() as ws:
        ws.init_repo()
        script = emit_completion_script(ws, "bash")
        bin_name = product_bin().name
        candidates = shell_completion_candidates(
            ws,
            shell="bash",
            script=script,
            words=[bin_name, ""],
        )
        assert_porcelain_subcommand_candidates(candidates)
        assert_clone_among_porcelain_candidates(candidates)


def test_completion_fish_script_yields_porcelain_candidates_for_standalone_binary() -> None:
    """Fish loads the emitted script and completes standalone porcelain names."""
    with workspace() as ws:
        ws.init_repo()
        script = emit_completion_script(ws, "fish")
        bin_name = product_bin().name
        candidates = shell_completion_candidates(
            ws,
            shell="fish",
            script=script,
            words=[bin_name, ""],
        )
        assert_porcelain_subcommand_candidates(candidates)
        assert_clone_among_porcelain_candidates(candidates)


def test_completion_zsh_script_yields_porcelain_candidates_for_standalone_binary() -> None:
    """Zsh loads the emitted script on fpath and completes standalone porcelain names."""
    with workspace() as ws:
        ws.init_repo()
        script = emit_completion_script(ws, "zsh")
        bin_name = product_bin().name
        candidates = fpath_zsh_completion_candidates(
            ws,
            script=script,
            words=[bin_name, ""],
        )
        assert_porcelain_subcommand_candidates(candidates)
        assert_clone_among_porcelain_candidates(candidates)


def test_completion_bash_git_invoked_entry_yields_porcelain_candidates() -> None:
    """Bash plus installed Git completion completes multi-word git orbulk."""
    with workspace() as ws:
        ws.init_repo()
        script = emit_completion_script(ws, "bash")
        candidates = shell_completion_candidates(
            ws,
            shell="bash",
            script=script,
            words=["git", "orbulk", ""],
            git_completion=True,
        )
        assert_porcelain_subcommand_candidates(candidates)
        assert_clone_among_porcelain_candidates(candidates)


def test_completion_unknown_shell_name_exits_nonzero() -> None:
    """Unknown completion shell name is nonzero relative to a live bash emit."""
    with workspace() as ws:
        ws.init_repo()
        clean = ws.invoke_via_git(["completion", "bash"])
        require_success(clean)
        assert clean.stdout, "live baseline bash completion emitted an empty script"
        unknown = f"sh_{token()}"
        dirty = ws.invoke(["completion", unknown])
        print(
            f"unknown shell={unknown!r} exit={dirty.returncode} "
            f"stderr={dirty.stderr_text!r}"
        )
        require_invalid_unlike_success(clean, dirty)


def test_dedup_test_mode_reports_support_on_cow_without_relinking() -> None:
    """On a COW root, test mode succeeds and does not relink the working tree."""
    with workspace() as ws:
        root = cow_capable_repo_root(ws)
        try:
            assert independent_cow_supported(root)
            ws.init_repo()
            rel = _tracked_rel()
            payload = _large_payload()
            digest = _setup_tracked_repo(ws, rel, payload)
            store = default_lfs_store_root(ws)
            stored = store / sharded_object_rel(digest)
            result = invoke_dedup(ws, test_mode=True, via_git=False)
            require_success(result)
            require_not_cow_clone(ws.resolve(rel), stored)
            require_object_bytes(store, digest, payload)
            print(f"test-mode exit={result.returncode} rel={rel!r}")
        finally:
            release_cow_filesystem(root)


def test_dedup_relinks_working_tree_as_cow_clone_of_store_object() -> None:
    """Ordinary dedup on a COW root relinks as an independently writable clone."""
    with workspace() as ws:
        root = cow_capable_repo_root(ws)
        try:
            assert independent_cow_supported(root)
            ws.init_repo()
            rel = _tracked_rel()
            payload = _large_payload()
            digest = _setup_tracked_repo(ws, rel, payload)
            store = default_lfs_store_root(ws)
            stored = store / sharded_object_rel(digest)
            result = invoke_dedup(ws, test_mode=False)
            require_success(result)
            require_cow_clone(ws.resolve(rel), stored)
            require_object_bytes(store, digest, payload)
            print(f"ordinary dedup exit={result.returncode} rel={rel!r}")
        finally:
            release_cow_filesystem(root)


def test_dedup_refuses_when_content_extensions_configured_on_cow() -> None:
    """Registered content extensions refuse both dedup modes and do not relink."""
    payload = _large_payload()
    rel = _tracked_rel()
    with workspace() as baseline:
        root_b = cow_capable_repo_root(baseline)
        try:
            assert independent_cow_supported(root_b)
            baseline.init_repo()
            digest_b = _setup_tracked_repo(baseline, rel, payload)
            store_b = default_lfs_store_root(baseline)
            success = invoke_dedup(baseline, test_mode=True)
            require_success(success)
            require_not_cow_clone(
                baseline.resolve(rel), store_b / sharded_object_rel(digest_b)
            )
        finally:
            release_cow_filesystem(root_b)

    with workspace() as ext_test:
        root_t = cow_capable_repo_root(ext_test)
        try:
            ext_test.init_repo()
            digest_t = _setup_tracked_repo(ext_test, rel, payload)
            register_byte_transform_extension(ext_test)
            store_t = default_lfs_store_root(ext_test)
            stored_t = store_t / sharded_object_rel(digest_t)
            refused_test = invoke_dedup(ext_test, test_mode=True)
            assert refused_test.returncode != 0, (
                "test mode succeeded with content extensions configured"
            )
            assert (refused_test.returncode, refused_test.stdout, refused_test.stderr) != (
                success.returncode,
                success.stdout,
                success.stderr,
            ), "extension test-mode refusal was not distinguishable from support success"
            require_not_cow_clone(ext_test.resolve(rel), stored_t)
        finally:
            release_cow_filesystem(root_t)

    with workspace() as ext_ord:
        root_o = cow_capable_repo_root(ext_ord)
        try:
            ext_ord.init_repo()
            digest_o = _setup_tracked_repo(ext_ord, rel, payload)
            register_byte_transform_extension(ext_ord)
            store_o = default_lfs_store_root(ext_ord)
            stored_o = store_o / sharded_object_rel(digest_o)
            refused_ord = invoke_dedup(ext_ord, test_mode=False)
            assert refused_ord.returncode != 0, (
                "ordinary dedup succeeded with content extensions configured"
            )
            require_not_cow_clone(ext_ord.resolve(rel), stored_o)
            print(
                f"ext test-mode exit={refused_test.returncode} "
                f"ordinary exit={refused_ord.returncode}"
            )
        finally:
            release_cow_filesystem(root_o)


def test_dedup_exits_nonzero_on_filesystem_without_cow() -> None:
    """On a non-COW root both dedup modes fail and do not pretend to save space."""
    with workspace() as ws:
        root = non_cow_repo_root(ws)
        assert not independent_cow_supported(root)
        if root == ws.path:
            ws.init_repo()
            rel = _tracked_rel()
            payload = _large_payload()
            digest = _setup_tracked_repo(ws, rel, payload)
            store = default_lfs_store_root(ws)
            stored = store / sharded_object_rel(digest)
            test_mode = invoke_dedup(ws, test_mode=True)
            ordinary = invoke_dedup(ws, test_mode=False)
            assert test_mode.returncode != 0, (
                "test mode succeeded on a filesystem without copy-on-write"
            )
            assert ordinary.returncode != 0, (
                "ordinary dedup succeeded on a filesystem without copy-on-write"
            )
            require_not_cow_clone(ws.resolve(rel), stored)
            print(
                f"non-cow test-mode exit={test_mode.returncode} "
                f"ordinary exit={ordinary.returncode}"
            )
            return
        raise AssertionError(
            "non-COW root is not the workspace path; helpers observe "
            f"ws.path only (root={root})"
        )


def test_merge_driver_selected_by_user_merge_attribute_writes_pointer_and_stores_object() -> None:
    """User merge attribute selects merge-driver: pointer result and stored bytes."""
    ancestor, current, other, merged = _three_way_texts()
    rel = _tracked_rel()
    attr = f"drv_{token()}"
    digest = sha256_hex(merged)
    with workspace() as ws:
        ws.init_repo()
        other_branch = _setup_merge_layout(
            ws,
            relpath=rel,
            ancestor=ancestor,
            current=current,
            other=other,
            user_attr=attr,
        )
        store = default_lfs_store_root(ws)
        require_object_absent(store, digest)
        merged_run = ws.git(["merge", "--no-edit", other_branch])
        require_success(merged_run)
        pointer = index_blob(ws, rel)
        assert pointer_matches_digest_and_size(
            pointer, digest=digest, size=len(merged)
        ), (
            "index result is not a pointer for the constructed merge bytes "
            f"digest={digest!r} index={pointer!r}"
        )
        require_object_bytes(store, digest, merged)
        print(f"merge stored oid={digest} attr={attr!r} rel={rel!r}")


def test_ordinary_track_merge_lfs_does_not_select_merge_driver() -> None:
    """Track-only merge=lfs does not produce the user-driver success of K."""
    ancestor, current, other, merged = _three_way_texts()
    rel = _tracked_rel()
    attr = f"drv_{token()}"
    digest = sha256_hex(merged)

    with workspace() as success_ws:
        success_ws.init_repo()
        other_ok = _setup_merge_layout(
            success_ws,
            relpath=rel,
            ancestor=ancestor,
            current=current,
            other=other,
            user_attr=attr,
        )
        store_ok = default_lfs_store_root(success_ws)
        require_object_absent(store_ok, digest)
        merged_ok = success_ws.git(["merge", "--no-edit", other_ok])
        require_success(merged_ok)
        pointer_ok = index_blob(success_ws, rel)
        assert pointer_matches_digest_and_size(
            pointer_ok, digest=digest, size=len(merged)
        )
        require_object_bytes(store_ok, digest, merged)

    with workspace() as track_ws:
        track_ws.init_repo()
        other_l = _setup_merge_layout(
            track_ws,
            relpath=rel,
            ancestor=ancestor,
            current=current,
            other=other,
            user_attr=None,
        )
        roles = require_lfs_enable_roles(track_ws, rel)
        assert roles["merge"] == "lfs"
        store_l = default_lfs_store_root(track_ws)
        merged_l = track_ws.git(["merge", "--no-edit", other_l])
        pointer_is_m = False
        try:
            pointer_l = index_blob(track_ws, rel)
            pointer_is_m = pointer_matches_digest_and_size(
                pointer_l, digest=digest, size=len(merged)
            )
        except AssertionError:
            pointer_is_m = False
        object_is_m = False
        try:
            require_object_bytes(store_l, digest, merged)
            object_is_m = True
        except AssertionError:
            object_is_m = False
        print(
            f"track-only merge exit={merged_l.returncode} "
            f"pointer_is_m={pointer_is_m} object_is_m={object_is_m}"
        )
        assert not (pointer_is_m and object_is_m), (
            "ordinary track merge=lfs produced the user-driver success "
            "(index pointer for the merged bytes and that object in the store)"
        )


def test_logs_fails_when_binary_removed_from_path() -> None:
    """PATH without the product binary makes the logs entry fail."""
    with workspace() as ws:
        ws.init_repo()
        present = ws.invoke_via_git(["logs"])
        require_success(present)
        hidden = path_without_product_bin(ws.env)
        dirty = ws.invoke_via_git(["logs"], env_updates={"PATH": hidden})
        print(f"absent-binary logs exit={dirty.returncode}")
        assert dirty.returncode != 0, (
            "logs succeeded after the product binary was removed from PATH"
        )
        assert (dirty.returncode, dirty.stdout, dirty.stderr) != (
            present.returncode,
            present.stdout,
            present.stderr,
        ), "absent-binary logs was not distinguishable from the live baseline"


def test_dedup_fails_outside_a_git_repository() -> None:
    """Ordinary dedup is repo-bound. Test mode only checks filesystem support."""
    with workspace() as inside:
        root = cow_capable_repo_root(inside)
        try:
            assert independent_cow_supported(root)
            inside.init_repo()
            commit_ordinary_blob(inside, "README", f"seed-{token()}\n")
            clean = invoke_dedup(inside, test_mode=True)
            print(f"in-repo test-mode exit={clean.returncode}")
            require_success(clean)
            ordinary = invoke_dedup(inside, test_mode=False)
            print(f"in-repo ordinary exit={ordinary.returncode}")
            require_success(ordinary)
        finally:
            release_cow_filesystem(root)
    with workspace() as outside:
        outside_root = cow_capable_repo_root(outside)
        try:
            assert independent_cow_supported(outside_root)
            dirty = invoke_dedup(outside, test_mode=False)
            print(f"outside-repo ordinary dedup exit={dirty.returncode}")
            require_invalid_unlike_success(ordinary, dirty)
        finally:
            release_cow_filesystem(outside_root)


def test_completion_standalone_yields_flag_candidates_not_git_ref_names() -> None:
    """Fetch-position candidates are flags, not generated Git ref names."""
    with workspace() as ws:
        ws.init_repo()
        empty = ws.write("README", f"seed-{token()}\n")
        del empty
        seeded = ws.git(["add", "--", "README"])
        assert seeded.returncode == 0, (
            f"git add README failed (exit {seeded.returncode}): "
            f"{seeded.stderr_text}"
        )
        committed = ws.git(["commit", "-m", "seed"])
        assert committed.returncode == 0, (
            f"git commit failed (exit {committed.returncode}): "
            f"{committed.stderr_text}"
        )
        remote = f"rm_{token()}"
        branch = f"br_{token()}"
        add_git_remote(ws, remote, runtime_http_url("gamma"))
        branched = ws.git(["branch", branch])
        assert branched.returncode == 0, (
            f"git branch {branch!r} failed (exit {branched.returncode}): "
            f"{branched.stderr_text}"
        )
        bin_name = product_bin().name
        for shell in ("bash", "fish", "zsh"):
            script = emit_completion_script(ws, shell)
            if shell == "zsh":
                top = fpath_zsh_completion_candidates(
                    ws, script=script, words=[bin_name, ""]
                )
            else:
                top = shell_completion_candidates(
                    ws,
                    shell=shell,
                    script=script,
                    words=[bin_name, ""],
                )
            assert_porcelain_subcommand_candidates(top)
            assert_clone_among_porcelain_candidates(top)
            require_omits_token(top, remote)
            require_omits_token(top, branch)
            if shell == "zsh":
                fetch_empty = fpath_zsh_completion_candidates(
                    ws, script=script, words=[bin_name, "fetch", ""]
                )
            else:
                fetch_empty = shell_completion_candidates(
                    ws,
                    shell=shell,
                    script=script,
                    words=[bin_name, "fetch", ""],
                )
            print(
                f"{shell} fetch-empty candidates={fetch_empty!r} "
                f"remote={remote!r} branch={branch!r}"
            )
            require_omits_token(fetch_empty, remote)
            require_omits_token(fetch_empty, branch)
            if shell == "zsh":
                fetch = fpath_zsh_completion_candidates(
                    ws, script=script, words=[bin_name, "fetch", "-"]
                )
            else:
                fetch = shell_completion_candidates(
                    ws,
                    shell=shell,
                    script=script,
                    words=[bin_name, "fetch", "-"],
                )
            print(
                f"{shell} fetch-flag candidates={fetch!r} "
                f"remote={remote!r} branch={branch!r}"
            )
            require_omits_token(fetch, remote)
            require_omits_token(fetch, branch)
            stripped_top = [item for item in top if item not in (remote, branch)]
            stripped_fetch = [
                item for item in fetch if item not in (remote, branch)
            ]
            dash = require_flag_shaped_candidates(
                stripped_fetch, unlike=stripped_top
            )
            print(f"{shell} fetch dash remainder={dash!r}")
