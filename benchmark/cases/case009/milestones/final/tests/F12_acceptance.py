# feature: F12
"""Local object pruning acceptance tests.

PRD: FP-12. Oracles are which independently hashed objects remain in
the local store after prune (or fetch's prune option). Message wording,
exit-code numbers, recentness-day arithmetic, and verbose layout are
not pinned.
"""

from __future__ import annotations

from pathlib import Path

from _harness import token, workspace
from _helpers import (
    add_git_remote,
    assert_object_absent,
    assert_object_bytes,
    assert_success,
    caller_visible,
    clean_bytes,
    commit_tracked_payload,
    commit_tracked_payload_dated,
    configure_fetch_exclude,
    configure_recentness,
    configure_storage_root,
    configured_lfs_store_root,
    default_lfs_store_root,
    default_lfs_store_root_at,
    git_state_sha_tokens,
    init_bare_git_remote,
    install_local_keeping_process,
    path_without_product_bin,
    require_git_config_set,
    require_object_absent,
    require_object_bytes,
    require_success,
    run_prune,
    run_track,
    set_lfs_endpoint,
    set_remote_tracking,
    sha256_hex,
    storing_batch_server,
    track_pattern,
)

# Commit dates far outside any default recentness window. Setup only.
_FAR = "1990-01-15T12:00:00"
_FAR_LATER = "1990-06-15T12:00:00"
# Covering recentness window for a "now" commit. Setup only; not asserted.
_COVER_DAYS = "2"


def _payload() -> bytes:
    return f"blob-{token()}\n".encode("utf-8")


def _rel(prefix: str = "p") -> str:
    return f"{prefix}_{token()}.bin"


def _git_ok(ws, argv, **kwargs):
    result = ws.git(argv, **kwargs)
    assert result.returncode == 0, (
        f"git {argv!r} failed (exit {result.returncode}): {result.stderr_text}"
    )
    return result


def _branch(ws, *, cwd=None) -> str:
    result = ws.git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    assert result.returncode == 0, (
        "git rev-parse --abbrev-ref HEAD failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    name = result.stdout_text.strip()
    assert name and name != "HEAD", f"not on a named branch: {name!r}"
    return name


def _sha(ws, ref: str = "HEAD", *, cwd=None) -> str:
    result = ws.git(["rev-parse", "--verify", ref], cwd=cwd)
    assert result.returncode == 0, (
        f"git rev-parse --verify {ref!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    sha = result.stdout_text.strip()
    assert sha, f"git rev-parse --verify {ref!r} produced no sha"
    return sha


def _add_origin(ws, *, cwd=None) -> Path:
    bare = init_bare_git_remote(ws, f"rmt_{token()}.git")
    url = str(bare)
    if cwd is None:
        add_git_remote(ws, "origin", url)
    else:
        _git_ok(ws, ["remote", "add", "origin", url], cwd=cwd)
    return bare


def _track_remote(ws, branch: str, sha: str, *, cwd=None) -> None:
    if cwd is None:
        set_remote_tracking(ws, "origin", branch, sha)
        return
    ref = f"refs/remotes/origin/{branch}"
    _git_ok(ws, ["update-ref", ref, sha], cwd=cwd)


def _plant_origin_at(ws, sha: str, *, branch: str | None = None, cwd=None) -> str:
    name = branch if branch is not None else _branch(ws, cwd=cwd)
    _add_origin(ws, cwd=cwd)
    _track_remote(ws, name, sha, cwd=cwd)
    return name


def _init_tracked(ws) -> None:
    ws.init_repo()
    install_local_keeping_process(ws)
    track_pattern(ws, "*.bin")


def _config_at(ws, key: str, value: str, *, cwd) -> None:
    result = ws.git_config_set(key, value, local=True, cwd=cwd)
    assert result.returncode == 0, (
        f"git config {key!r} failed (exit {result.returncode}) cwd={cwd}: "
        f"{result.stderr_text}"
    )


def _recentness_at(ws, cwd, *, ref_days: int) -> None:
    _config_at(ws, "lfs.fetchrecentrefsdays", str(ref_days), cwd=cwd)
    _config_at(ws, "lfs.fetchrecentcommitsdays", "0", cwd=cwd)
    _config_at(ws, "lfs.fetchrecentalways", "false", cwd=cwd)


def _nested_install(ws, cwd) -> None:
    require_success(ws.invoke_via_git(["install", "--local"], cwd=cwd))
    unset = ws.git(
        ["config", "--local", "--unset", "filter.lfs.process"], cwd=cwd
    )
    assert unset.returncode == 0, (
        "failed to disable the process filter so git add uses clean "
        f"(exit {unset.returncode}): {unset.stderr_text}"
    )


def _commit_at(ws, repo_rel: str, rel: str, data: bytes, *, when: str | None = None) -> str:
    ws.write(f"{repo_rel}/{rel}", data)
    digest = sha256_hex(data)
    cwd = ws.resolve(repo_rel)
    to_add = [rel]
    try:
        ws.read_bytes(f"{repo_rel}/.gitattributes")
        to_add.append(".gitattributes")
    except FileNotFoundError:
        pass
    _git_ok(ws, ["add", "--", *to_add], cwd=cwd)
    env = None
    if when is not None:
        env = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    _git_ok(ws, ["commit", "-m", f"add {rel}"], cwd=cwd, env_updates=env)
    return digest


def _main_pushed(ws, *, tracking_at: str = "head"):
    """Pushed stale-then-HEAD on one path. recentness refs/commits are zero.

    *tracking_at*: ``head`` plants origin at HEAD; ``parent`` leaves HEAD
    unpushed.
    """
    _init_tracked(ws)
    rel = _rel("p")
    stale = _payload()
    head = _payload()
    stale_oid = commit_tracked_payload_dated(ws, rel, stale, _FAR)
    head_digest = commit_tracked_payload(ws, rel, head)
    configure_recentness(ws, ref_days=0)
    branch = _branch(ws)
    head_sha = _sha(ws)
    parent_sha = _sha(ws, "HEAD~1")
    _add_origin(ws)
    if tracking_at == "head":
        _track_remote(ws, branch, head_sha)
    elif tracking_at == "parent":
        _track_remote(ws, branch, parent_sha)
    else:
        raise AssertionError(f"tracking_at must be head or parent, got {tracking_at!r}")
    store = default_lfs_store_root(ws)
    require_object_bytes(store, stale_oid, stale)
    require_object_bytes(store, head_digest, head)
    return {
        "rel": rel,
        "stale": stale,
        "head": head,
        "stale_oid": stale_oid,
        "head_oid": head_digest,
        "branch": branch,
        "head_sha": head_sha,
        "parent_sha": parent_sha,
        "store": store,
    }


# ---------------------------------------------------------------------------
# A. Main oracle
# ---------------------------------------------------------------------------


def test_prune_deletes_old_pushed_non_recent_keeps_head():
    """Old pushed non-recent object disappears; HEAD remains."""
    with workspace() as ws:
        layout = _main_pushed(ws)
        result = run_prune(ws)
        print(
            f"prune exit={result.returncode} stale={layout['stale_oid']} "
            f"head={layout['head_oid']}"
        )
        require_success(result)
        require_object_absent(layout["store"], layout["stale_oid"])
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )


def test_direct_binary_prune_deletes_stale_keeps_head():
    """Direct binary prune deletes stale and keeps HEAD."""
    with workspace() as ws:
        layout = _main_pushed(ws)
        result = ws.invoke(["prune"])
        print(f"direct prune exit={result.returncode}")
        require_success(result)
        require_object_absent(layout["store"], layout["stale_oid"])
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )


def test_unpushed_head_is_kept_unlike_pushed_stale_deleted():
    """Unpushed HEAD stays; the same history with tracking at HEAD deletes stale."""
    with workspace() as pushed:
        layout = _main_pushed(pushed, tracking_at="head")
        require_success(run_prune(pushed))
        require_object_absent(layout["store"], layout["stale_oid"])
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
    with workspace() as unpushed:
        layout = _main_pushed(unpushed, tracking_at="parent")
        result = run_prune(unpushed)
        print(f"unpushed-head prune exit={result.returncode}")
        require_success(result)
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )


# ---------------------------------------------------------------------------
# B. Dry-run
# ---------------------------------------------------------------------------


def _two_path_pushed(ws):
    """HEAD is H; S is a pushed object no longer in the HEAD tree."""
    _init_tracked(ws)
    rel_s = _rel("s")
    rel_h = _rel("h")
    data_s = _payload()
    data_h = _payload()
    oid_s = commit_tracked_payload_dated(ws, rel_s, data_s, _FAR)
    _git_ok(ws, ["rm", "--", rel_s])
    oid_h = commit_tracked_payload(ws, rel_h, data_h)
    configure_recentness(ws, ref_days=0)
    _plant_origin_at(ws, _sha(ws))
    store = default_lfs_store_root(ws)
    require_object_bytes(store, oid_s, data_s)
    require_object_bytes(store, oid_h, data_h)
    return {
        "rel_s": rel_s,
        "rel_h": rel_h,
        "data_s": data_s,
        "data_h": data_h,
        "oid_s": oid_s,
        "oid_h": oid_h,
        "store": store,
    }


def test_dry_run_does_not_delete_unlike_live_prune():
    """Dry-run leaves stale in the store; live prune deletes it."""
    with workspace() as live:
        layout = _main_pushed(live)
        require_success(run_prune(live))
        require_object_absent(layout["store"], layout["stale_oid"])
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
    with workspace() as dry:
        layout = _main_pushed(dry)
        result = run_prune(dry, ["--dry-run"])
        print(f"dry-run exit={result.returncode}")
        require_success(result)
        require_object_bytes(
            layout["store"], layout["stale_oid"], layout["stale"]
        )
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )


def test_dry_run_reports_and_keeps_candidate_and_head():
    """Dry-run reports without deleting: prune candidate and HEAD stay in the store."""
    with workspace() as ws:
        layout = _two_path_pushed(ws)
        result = run_prune(ws, ["--dry-run"])
        print(
            f"dry-run exit={result.returncode} "
            f"s={layout['oid_s']} h={layout['oid_h']}"
        )
        assert_success(result)
        visible = caller_visible(result)
        print(f"dry-run visible={visible!r}")
        assert visible.strip(), (
            "dry-run produced no caller-visible report; "
            "FP-12 requires dry-run to report without deleting"
        )
        assert_object_bytes(
            layout["store"], layout["oid_s"], layout["data_s"]
        )
        assert_object_bytes(
            layout["store"], layout["oid_h"], layout["data_h"]
        )


# ---------------------------------------------------------------------------
# C. Retention roots
# ---------------------------------------------------------------------------


def test_stash_retains_object_unlike_unreferenced():
    """A stashed object is kept; the same bytes with no stash are deleted."""
    extra = _payload()
    extra_oid = sha256_hex(extra)
    with workspace() as stashed:
        layout = _main_pushed(stashed)
        stashed.write(layout["rel"], extra)
        _git_ok(stashed, ["stash"])
        require_object_bytes(layout["store"], extra_oid, extra)
        result = run_prune(stashed)
        print(f"stash prune exit={result.returncode} extra={extra_oid}")
        require_success(result)
        require_object_bytes(layout["store"], extra_oid, extra)
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
        require_object_absent(layout["store"], layout["stale_oid"])
    with workspace() as bare_obj:
        layout = _main_pushed(bare_obj)
        require_success(clean_bytes(bare_obj, extra))
        require_object_bytes(layout["store"], extra_oid, extra)
        result = run_prune(bare_obj)
        print(f"no-stash prune exit={result.returncode}")
        require_success(result)
        require_object_absent(layout["store"], extra_oid)
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )


def test_other_worktree_retains_unlike_absent_worktree():
    """Another worktree checkout retains its tip; without that worktree it is deleted."""
    other = f"br_{token()}"
    rel_o = _rel("w")
    data_o = _payload()
    with workspace() as with_wt:
        repo = f"repo_{token()}"
        with_wt.init_repo(repo)
        cwd = with_wt.resolve(repo)
        _nested_install(with_wt, cwd)
        require_success(run_track(with_wt, ["*.bin"], cwd=cwd))
        rel_h = _rel("h")
        data_h = _payload()
        oid_h = _commit_at(with_wt, repo, rel_h, data_h, when=_FAR)
        _git_ok(with_wt, ["checkout", "-b", other], cwd=cwd)
        oid_o = _commit_at(with_wt, repo, rel_o, data_o, when=_FAR)
        _git_ok(with_wt, ["checkout", "main"], cwd=cwd)
        _recentness_at(with_wt, cwd, ref_days=0)
        main_sha = _sha(with_wt, cwd=cwd)
        other_sha = _sha(with_wt, other, cwd=cwd)
        _add_origin(with_wt, cwd=cwd)
        _track_remote(with_wt, "main", main_sha, cwd=cwd)
        _track_remote(with_wt, other, other_sha, cwd=cwd)
        wt = with_wt.resolve(f"wt_{token()}")
        _git_ok(with_wt, ["worktree", "add", str(wt), other], cwd=cwd)
        store = default_lfs_store_root_at(with_wt, cwd)
        require_success(run_prune(with_wt, cwd=cwd))
        print(f"worktree kept other={oid_o} head={oid_h}")
        require_object_bytes(store, oid_o, data_o)
        require_object_bytes(store, oid_h, data_h)
    with workspace() as no_wt:
        repo = f"repo_{token()}"
        no_wt.init_repo(repo)
        cwd = no_wt.resolve(repo)
        _nested_install(no_wt, cwd)
        require_success(run_track(no_wt, ["*.bin"], cwd=cwd))
        rel_h = _rel("h")
        data_h = _payload()
        oid_h = _commit_at(no_wt, repo, rel_h, data_h, when=_FAR)
        _git_ok(no_wt, ["checkout", "-b", other], cwd=cwd)
        oid_o = _commit_at(no_wt, repo, rel_o, data_o, when=_FAR)
        _git_ok(no_wt, ["checkout", "main"], cwd=cwd)
        _recentness_at(no_wt, cwd, ref_days=0)
        main_sha = _sha(no_wt, cwd=cwd)
        other_sha = _sha(no_wt, other, cwd=cwd)
        _add_origin(no_wt, cwd=cwd)
        _track_remote(no_wt, "main", main_sha, cwd=cwd)
        _track_remote(no_wt, other, other_sha, cwd=cwd)
        store = default_lfs_store_root_at(no_wt, cwd)
        require_success(run_prune(no_wt, cwd=cwd))
        print(f"no-worktree deleted other={oid_o}")
        require_object_absent(store, oid_o)
        require_object_bytes(store, oid_h, data_h)


def test_orphaned_commit_object_deleted_reflog_is_not_root():
    """An object only on an orphaned commit is deleted; the same HEAD is kept."""
    with workspace() as reset_ws:
        layout = _main_pushed(reset_ws)
        extra = _payload()
        extra_oid = commit_tracked_payload(reset_ws, layout["rel"], extra)
        _git_ok(reset_ws, ["reset", "--hard", "HEAD~1"])
        configure_recentness(reset_ws, ref_days=0)
        result = run_prune(reset_ws)
        print(f"orphan prune exit={result.returncode} extra={extra_oid}")
        require_success(result)
        require_object_absent(layout["store"], extra_oid)
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
    with workspace() as no_reset:
        layout = _main_pushed(no_reset)
        extra = _payload()
        extra_oid = commit_tracked_payload(no_reset, layout["rel"], extra)
        branch = layout["branch"]
        _track_remote(no_reset, branch, _sha(no_reset))
        configure_recentness(no_reset, ref_days=0)
        require_success(run_prune(no_reset))
        print(f"no-reset extra kept={extra_oid}")
        require_object_bytes(layout["store"], extra_oid, extra)


def test_recent_branch_window_retains_unlike_zero_days():
    """A now-dated other-branch tip is kept when recent refs cover now, deleted at 0."""
    other = f"br_{token()}"
    rel_o = _rel("r")
    data_o = _payload()
    with workspace() as covering:
        _init_tracked(covering)
        rel_h = _rel("h")
        data_h = _payload()
        oid_h = commit_tracked_payload(covering, rel_h, data_h)
        _git_ok(covering, ["checkout", "-b", other])
        oid_o = commit_tracked_payload(covering, rel_o, data_o)
        _git_ok(covering, ["checkout", "main"])
        configure_recentness(covering, ref_days=int(_COVER_DAYS))
        _add_origin(covering)
        _track_remote(covering, "main", _sha(covering))
        _track_remote(covering, other, _sha(covering, other))
        store = default_lfs_store_root(covering)
        require_success(run_prune(covering))
        print(f"recent-refs kept other={oid_o} head={oid_h}")
        require_object_bytes(store, oid_o, data_o)
        require_object_bytes(store, oid_h, data_h)
    with workspace() as zero:
        _init_tracked(zero)
        rel_h = _rel("h")
        data_h = _payload()
        oid_h = commit_tracked_payload(zero, rel_h, data_h)
        _git_ok(zero, ["checkout", "-b", other])
        oid_o = commit_tracked_payload(zero, rel_o, data_o)
        _git_ok(zero, ["checkout", "main"])
        configure_recentness(zero, ref_days=0)
        _add_origin(zero)
        _track_remote(zero, "main", _sha(zero))
        _track_remote(zero, other, _sha(zero, other))
        store = default_lfs_store_root(zero)
        require_success(run_prune(zero))
        print(f"recent-refs-zero deleted other={oid_o}")
        require_object_absent(store, oid_o)
        require_object_bytes(store, oid_h, data_h)


def test_recent_commits_retain_non_head_previous_unlike_zero():
    """A now-dated previous version is kept when the commit window covers now."""
    with workspace() as covering:
        oids = _recent_commit_layout(covering, commits_days=_COVER_DAYS)
        result = run_prune(covering)
        print(f"recent-commits covering exit={result.returncode}")
        assert_success(result)
        assert_object_bytes(oids["store"], oids["prev_oid"], oids["prev"])
        assert_object_bytes(oids["store"], oids["head_oid"], oids["head"])
        assert_object_absent(oids["store"], oids["far_oid"])
    with workspace() as zero:
        oids = _recent_commit_layout(zero, commits_days="0")
        result = run_prune(zero)
        print(f"recent-commits zero exit={result.returncode}")
        assert_success(result)
        assert_object_absent(oids["store"], oids["prev_oid"])
        assert_object_bytes(oids["store"], oids["head_oid"], oids["head"])
        assert_object_absent(oids["store"], oids["far_oid"])


def _recent_commit_layout(ws, *, commits_days: str):
    """HEAD and a now-dated previous on P; far object on F disappeared in 1990."""
    _init_tracked(ws)
    rel_f = _rel("f")
    rel_p = _rel("p")
    far = _payload()
    prev = _payload()
    head = _payload()
    far_oid = commit_tracked_payload_dated(ws, rel_f, far, _FAR)
    _git_ok(ws, ["rm", "--", rel_f])
    _git_ok(
        ws,
        ["commit", "-m", f"drop {rel_f}"],
        env_updates={
            "GIT_AUTHOR_DATE": _FAR_LATER,
            "GIT_COMMITTER_DATE": _FAR_LATER,
        },
    )
    prev_oid = commit_tracked_payload(ws, rel_p, prev)
    head_oid_ = commit_tracked_payload(ws, rel_p, head)
    configure_recentness(ws, ref_days=0)
    require_git_config_set(
        ws, "lfs.fetchrecentcommitsdays", commits_days, local=True
    )
    _plant_origin_at(ws, _sha(ws))
    store = default_lfs_store_root(ws)
    return {
        "far": far,
        "prev": prev,
        "head": head,
        "far_oid": far_oid,
        "prev_oid": prev_oid,
        "head_oid": head_oid_,
        "store": store,
    }


def _other_branch_unpushed(ws, *, catch_up: bool):
    """Main HEAD pushed; other branch tip unique object, tracking at parent or tip."""
    _init_tracked(ws)
    rel_h = _rel("h")
    rel_o = _rel("u")
    data_h = _payload()
    stale = _payload()
    data_o = _payload()
    stale_oid = commit_tracked_payload_dated(ws, rel_h, stale, _FAR)
    head_oid_ = commit_tracked_payload(ws, rel_h, data_h)
    other = f"br_{token()}"
    _git_ok(ws, ["checkout", "-b", other])
    oid_o = commit_tracked_payload_dated(ws, rel_o, data_o, _FAR)
    parent_other = _sha(ws, "HEAD~1")
    tip_other = _sha(ws)
    _git_ok(ws, ["checkout", "main"])
    configure_recentness(ws, ref_days=0)
    _add_origin(ws)
    _track_remote(ws, "main", _sha(ws))
    if catch_up:
        _track_remote(ws, other, tip_other)
    else:
        _track_remote(ws, other, parent_other)
    store = default_lfs_store_root(ws)
    return {
        "oid_o": oid_o,
        "data_o": data_o,
        "head_oid": head_oid_,
        "head": data_h,
        "stale_oid": stale_oid,
        "stale": stale,
        "store": store,
    }


def test_unpushed_other_branch_retained_unlike_when_tracking_caught_up():
    """An unpushed other-branch object is kept; catching that branch up deletes it."""
    with workspace() as unpushed:
        layout = _other_branch_unpushed(unpushed, catch_up=False)
        assert_success(run_prune(unpushed))
        print(f"other-unpushed kept={layout['oid_o']}")
        assert_object_bytes(layout["store"], layout["oid_o"], layout["data_o"])
        assert_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
        assert_object_absent(layout["store"], layout["stale_oid"])
    with workspace() as caught:
        layout = _other_branch_unpushed(caught, catch_up=True)
        assert_success(run_prune(caught))
        print(f"other-caught-up deleted={layout['oid_o']}")
        assert_object_absent(layout["store"], layout["oid_o"])
        assert_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )


def test_unpushed_other_branch_retained_even_if_endpoint_has_bytes():
    """Unpushed other-branch object stays even when the endpoint already holds it."""
    with storing_batch_server() as svc:
        with workspace() as ws:
            layout = _other_branch_unpushed(ws, catch_up=False)
            svc.stored[layout["oid_o"]] = layout["data_o"]
            set_lfs_endpoint(ws, svc.url)
            assert_success(run_prune(ws))
            print(
                f"unpushed-with-endpoint kept={layout['oid_o']} "
                f"deleted_stale={layout['stale_oid']}"
            )
            assert_object_bytes(
                layout["store"], layout["oid_o"], layout["data_o"]
            )
            assert_object_absent(layout["store"], layout["stale_oid"])


# ---------------------------------------------------------------------------
# D. Force / recent
# ---------------------------------------------------------------------------


def test_force_deletes_pushed_head_unlike_default():
    """Force deletes a pushed current checkout; default prune keeps it."""
    with workspace() as default:
        layout = _main_pushed(default)
        require_success(run_prune(default))
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
        require_object_absent(layout["store"], layout["stale_oid"])
    with workspace() as forced:
        layout = _main_pushed(forced)
        result = run_prune(forced, ["--force"])
        print(f"force exit={result.returncode}")
        require_success(result)
        require_object_absent(layout["store"], layout["head_oid"])
        require_object_absent(layout["store"], layout["stale_oid"])


def test_force_keeps_unpushed_head():
    """Force still leaves an unpushed HEAD object."""
    with workspace() as ws:
        layout = _main_pushed(ws, tracking_at="parent")
        result = run_prune(ws, ["--force"])
        print(
            f"force unpushed-head exit={result.returncode} "
            f"deleted_stale={layout['stale_oid']}"
        )
        require_success(result)
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
        require_object_absent(layout["store"], layout["stale_oid"])


def test_force_keeps_unpushed_head_even_if_endpoint_has_bytes():
    """Force still leaves unpushed HEAD when the endpoint already holds the bytes."""
    with storing_batch_server() as svc:
        with workspace() as ws:
            layout = _main_pushed(ws, tracking_at="parent")
            svc.stored[layout["head_oid"]] = layout["head"]
            set_lfs_endpoint(ws, svc.url)
            result = run_prune(ws, ["--force"])
            print(
                f"force unpushed+endpoint exit={result.returncode} "
                f"deleted_stale={layout['stale_oid']}"
            )
            require_success(result)
            require_object_bytes(
                layout["store"], layout["head_oid"], layout["head"]
            )
            require_object_absent(layout["store"], layout["stale_oid"])


def test_recent_flag_deletes_recent_tip_keeps_head_unlike_force():
    """--recent drops a recent other-branch tip but keeps HEAD; --force drops both."""
    other = f"br_{token()}"
    rel_o = _rel("r")
    data_o = _payload()
    with workspace() as baseline:
        _init_tracked(baseline)
        rel_h = _rel("h")
        data_h = _payload()
        oid_h = commit_tracked_payload(baseline, rel_h, data_h)
        _git_ok(baseline, ["checkout", "-b", other])
        oid_o = commit_tracked_payload(baseline, rel_o, data_o)
        _git_ok(baseline, ["checkout", "main"])
        configure_recentness(baseline, ref_days=int(_COVER_DAYS))
        _add_origin(baseline)
        _track_remote(baseline, "main", _sha(baseline))
        _track_remote(baseline, other, _sha(baseline, other))
        store = default_lfs_store_root(baseline)
        require_success(run_prune(baseline))
        require_object_bytes(store, oid_o, data_o)
        require_object_bytes(store, oid_h, data_h)
    with workspace() as recent:
        _init_tracked(recent)
        rel_h = _rel("h")
        data_h = _payload()
        oid_h = commit_tracked_payload(recent, rel_h, data_h)
        _git_ok(recent, ["checkout", "-b", other])
        oid_o = commit_tracked_payload(recent, rel_o, data_o)
        _git_ok(recent, ["checkout", "main"])
        configure_recentness(recent, ref_days=int(_COVER_DAYS))
        _add_origin(recent)
        _track_remote(recent, "main", _sha(recent))
        _track_remote(recent, other, _sha(recent, other))
        store = default_lfs_store_root(recent)
        require_success(run_prune(recent, ["--recent"]))
        print(f"recent-flag deleted tip={oid_o} kept head={oid_h}")
        require_object_absent(store, oid_o)
        require_object_bytes(store, oid_h, data_h)
    with workspace() as forced:
        _init_tracked(forced)
        rel_h = _rel("h")
        data_h = _payload()
        oid_h = commit_tracked_payload(forced, rel_h, data_h)
        _git_ok(forced, ["checkout", "-b", other])
        oid_o = commit_tracked_payload(forced, rel_o, data_o)
        _git_ok(forced, ["checkout", "main"])
        configure_recentness(forced, ref_days=int(_COVER_DAYS))
        _add_origin(forced)
        _track_remote(forced, "main", _sha(forced))
        _track_remote(forced, other, _sha(forced, other))
        store = default_lfs_store_root(forced)
        require_success(run_prune(forced, ["--force"]))
        print(f"force deleted tip={oid_o} and head={oid_h}")
        require_object_absent(store, oid_o)
        require_object_absent(store, oid_h)


# ---------------------------------------------------------------------------
# E. Fetch-exclude
# ---------------------------------------------------------------------------


def _exclude_two_path_head(ws, *, exclude: bool, tracking_at: str = "head"):
    _init_tracked(ws)
    rel_m = _rel("m")
    rel_u = _rel("u")
    data_m = _payload()
    data_u = _payload()
    # Unmatched path first so tracking-at-parent leaves only the matched
    # path in the unpushed tip commit.
    oid_u = commit_tracked_payload_dated(ws, rel_u, data_u, _FAR)
    oid_m = commit_tracked_payload_dated(ws, rel_m, data_m, _FAR)
    configure_recentness(ws, ref_days=0)
    if exclude:
        configure_fetch_exclude(ws, rel_m)
    branch = _branch(ws)
    _add_origin(ws)
    if tracking_at == "head":
        _track_remote(ws, branch, _sha(ws))
    else:
        _track_remote(ws, branch, _sha(ws, "HEAD~1"))
    store = default_lfs_store_root(ws)
    return {
        "rel_m": rel_m,
        "rel_u": rel_u,
        "data_m": data_m,
        "data_u": data_u,
        "oid_m": oid_m,
        "oid_u": oid_u,
        "store": store,
    }


def test_fetch_exclude_deletes_matched_pushed_path_keeps_unmatched():
    """Exclude deletes the matched pushed HEAD path and keeps the unmatched one."""
    with workspace() as excluded:
        layout = _exclude_two_path_head(excluded, exclude=True)
        assert_success(run_prune(excluded))
        print(
            f"exclude deleted m={layout['oid_m']} kept u={layout['oid_u']}"
        )
        assert_object_absent(layout["store"], layout["oid_m"])
        assert_object_bytes(
            layout["store"], layout["oid_u"], layout["data_u"]
        )
    with workspace() as none:
        layout = _exclude_two_path_head(none, exclude=False)
        assert_success(run_prune(none))
        assert_object_bytes(
            layout["store"], layout["oid_m"], layout["data_m"]
        )
        assert_object_bytes(
            layout["store"], layout["oid_u"], layout["data_u"]
        )


def test_fetch_exclude_keeps_unpushed_matched_path():
    """Exclude does not delete a matched path that is still unpushed."""
    with workspace() as ws:
        layout = _exclude_two_path_head(
            ws, exclude=True, tracking_at="parent"
        )
        configure_fetch_exclude(
            ws, f"{layout['rel_m']},{layout['rel_u']}"
        )
        assert_success(run_prune(ws))
        print(
            f"exclude unpushed kept m={layout['oid_m']} "
            f"deleted_pushed_match={layout['oid_u']}"
        )
        assert_object_bytes(
            layout["store"], layout["oid_m"], layout["data_m"]
        )
        assert_object_absent(layout["store"], layout["oid_u"])


def test_fetch_exclude_keeps_stashed_matched_path():
    """Exclude does not delete a matched object retained only by a stash."""
    with workspace() as ws:
        _init_tracked(ws)
        rel_h = _rel("h")
        rel_m = _rel("m")
        rel_d = _rel("d")
        data_h = _payload()
        data_m = _payload()
        data_d = _payload()
        oid_h = commit_tracked_payload_dated(ws, rel_h, data_h, _FAR)
        oid_d = commit_tracked_payload_dated(ws, rel_d, data_d, _FAR)
        configure_recentness(ws, ref_days=0)
        configure_fetch_exclude(ws, f"{rel_m},{rel_d}")
        _plant_origin_at(ws, _sha(ws))
        ws.write(rel_m, data_m)
        _git_ok(ws, ["add", "--", rel_m])
        _git_ok(ws, ["stash"])
        oid_m = sha256_hex(data_m)
        store = default_lfs_store_root(ws)
        require_object_bytes(store, oid_m, data_m)
        require_success(run_prune(ws))
        print(
            f"exclude stash kept m={oid_m} head={oid_h} "
            f"deleted_pushed_match={oid_d}"
        )
        require_object_bytes(store, oid_m, data_m)
        require_object_bytes(store, oid_h, data_h)
        require_object_absent(store, oid_d)


def test_fetch_exclude_deletes_worktree_only_matched_path():
    """A matched path retained only by another worktree is deleted under exclude."""
    other = f"br_{token()}"
    rel_m = _rel("m")
    data_m = _payload()
    with workspace() as excluded:
        repo = f"repo_{token()}"
        excluded.init_repo(repo)
        cwd = excluded.resolve(repo)
        _nested_install(excluded, cwd)
        require_success(run_track(excluded, ["*.bin"], cwd=cwd))
        rel_h = _rel("h")
        data_h = _payload()
        oid_h = _commit_at(excluded, repo, rel_h, data_h, when=_FAR)
        _git_ok(excluded, ["checkout", "-b", other], cwd=cwd)
        oid_m = _commit_at(excluded, repo, rel_m, data_m, when=_FAR)
        _git_ok(excluded, ["checkout", "main"], cwd=cwd)
        _recentness_at(excluded, cwd, ref_days=0)
        _config_at(excluded, "lfs.fetchexclude", rel_m, cwd=cwd)
        _add_origin(excluded, cwd=cwd)
        _track_remote(excluded, "main", _sha(excluded, cwd=cwd), cwd=cwd)
        _track_remote(excluded, other, _sha(excluded, other, cwd=cwd), cwd=cwd)
        wt = excluded.resolve(f"wt_{token()}")
        _git_ok(excluded, ["worktree", "add", str(wt), other], cwd=cwd)
        store = default_lfs_store_root_at(excluded, cwd)
        require_success(run_prune(excluded, cwd=cwd))
        print(f"exclude+worktree deleted m={oid_m}")
        require_object_absent(store, oid_m)
        require_object_bytes(store, oid_h, data_h)
    with workspace() as kept:
        repo = f"repo_{token()}"
        kept.init_repo(repo)
        cwd = kept.resolve(repo)
        _nested_install(kept, cwd)
        require_success(run_track(kept, ["*.bin"], cwd=cwd))
        rel_h = _rel("h")
        data_h = _payload()
        oid_h = _commit_at(kept, repo, rel_h, data_h, when=_FAR)
        _git_ok(kept, ["checkout", "-b", other], cwd=cwd)
        oid_m = _commit_at(kept, repo, rel_m, data_m, when=_FAR)
        _git_ok(kept, ["checkout", "main"], cwd=cwd)
        _recentness_at(kept, cwd, ref_days=0)
        _add_origin(kept, cwd=cwd)
        _track_remote(kept, "main", _sha(kept, cwd=cwd), cwd=cwd)
        _track_remote(kept, other, _sha(kept, other, cwd=cwd), cwd=cwd)
        wt = kept.resolve(f"wt_{token()}")
        _git_ok(kept, ["worktree", "add", str(wt), other], cwd=cwd)
        store = default_lfs_store_root_at(kept, cwd)
        require_success(run_prune(kept, cwd=cwd))
        print(f"no-exclude worktree kept m={oid_m}")
        require_object_bytes(store, oid_m, data_m)
        require_object_bytes(store, oid_h, data_h)


# ---------------------------------------------------------------------------
# F. Verify-remote
# ---------------------------------------------------------------------------


def _two_candidates_plus_head(ws):
    """Two extra pushed non-recent paths plus HEAD; recentness zero."""
    _init_tracked(ws)
    rel_v = _rel("v")
    rel_u = _rel("u")
    rel_h = _rel("h")
    data_v = _payload()
    data_u = _payload()
    data_h = _payload()
    oid_v = commit_tracked_payload_dated(ws, rel_v, data_v, _FAR)
    oid_u = commit_tracked_payload_dated(ws, rel_u, data_u, _FAR)
    _git_ok(ws, ["rm", "--", rel_v, rel_u])
    oid_h = commit_tracked_payload(ws, rel_h, data_h)
    configure_recentness(ws, ref_days=0)
    _plant_origin_at(ws, _sha(ws))
    store = default_lfs_store_root(ws)
    return {
        "oid_v": oid_v,
        "oid_u": oid_u,
        "oid_h": oid_h,
        "data_v": data_v,
        "data_u": data_u,
        "data_h": data_h,
        "store": store,
    }


def test_verify_remote_deletes_when_all_verified():
    """Verify-remote with both candidates on the fixture deletes both, keeps HEAD."""
    with storing_batch_server() as svc:
        with workspace() as ws:
            layout = _two_candidates_plus_head(ws)
            svc.stored[layout["oid_v"]] = layout["data_v"]
            svc.stored[layout["oid_u"]] = layout["data_u"]
            set_lfs_endpoint(ws, svc.url)
            result = run_prune(
                ws, ["--verify-remote", "--when-unverified=halt"]
            )
            print(f"verify-all exit={result.returncode}")
            assert_success(result)
            assert_object_absent(layout["store"], layout["oid_v"])
            assert_object_absent(layout["store"], layout["oid_u"])
            assert_object_bytes(
                layout["store"], layout["oid_h"], layout["data_h"]
            )


def test_verify_remote_halt_keeps_all_candidates():
    """Halt leaves every candidate when one fails remote verification."""
    with workspace() as baseline:
        layout = _two_candidates_plus_head(baseline)
        assert_success(run_prune(baseline))
        assert_object_absent(layout["store"], layout["oid_v"])
        assert_object_absent(layout["store"], layout["oid_u"])
        assert_object_bytes(
            layout["store"], layout["oid_h"], layout["data_h"]
        )
    with storing_batch_server() as svc:
        with workspace() as ws:
            layout = _two_candidates_plus_head(ws)
            svc.stored[layout["oid_v"]] = layout["data_v"]
            set_lfs_endpoint(ws, svc.url)
            result = run_prune(
                ws, ["--verify-remote", "--when-unverified=halt"]
            )
            print(f"halt exit={result.returncode}")
            assert_object_bytes(
                layout["store"], layout["oid_v"], layout["data_v"]
            )
            assert_object_bytes(
                layout["store"], layout["oid_u"], layout["data_u"]
            )
            assert_object_bytes(
                layout["store"], layout["oid_h"], layout["data_h"]
            )


def test_verify_remote_continue_follows_fixture_inventory():
    """Continue deletes only the oid the fixture holds; swapping inventory swaps deletion."""
    with storing_batch_server() as svc_v:
        with workspace() as has_v:
            layout = _two_candidates_plus_head(has_v)
            svc_v.stored[layout["oid_v"]] = layout["data_v"]
            set_lfs_endpoint(has_v, svc_v.url)
            result = run_prune(
                has_v, ["--verify-remote", "--when-unverified=continue"]
            )
            print(f"continue has-v exit={result.returncode}")
            assert_object_absent(layout["store"], layout["oid_v"])
            assert_object_bytes(
                layout["store"], layout["oid_u"], layout["data_u"]
            )
            assert_object_bytes(
                layout["store"], layout["oid_h"], layout["data_h"]
            )
    with storing_batch_server() as svc_u:
        with workspace() as has_u:
            layout = _two_candidates_plus_head(has_u)
            svc_u.stored[layout["oid_u"]] = layout["data_u"]
            set_lfs_endpoint(has_u, svc_u.url)
            result = run_prune(
                has_u, ["--verify-remote", "--when-unverified=continue"]
            )
            print(f"continue has-u exit={result.returncode}")
            assert_object_absent(layout["store"], layout["oid_u"])
            assert_object_bytes(
                layout["store"], layout["oid_v"], layout["data_v"]
            )
            assert_object_bytes(
                layout["store"], layout["oid_h"], layout["data_h"]
            )


def test_verify_unreachable_halt_keeps_reachable_candidate():
    """Unreachable missing plus verify-unreachable halt keeps the reachable candidate too."""
    with storing_batch_server() as without_flag:
        with workspace() as ws:
            layout = _two_candidates_plus_head(ws)
            orphan = _payload()
            orphan_oid = sha256_hex(orphan)
            assert_success(clean_bytes(ws, orphan))
            assert_object_bytes(layout["store"], orphan_oid, orphan)
            without_flag.stored[layout["oid_v"]] = layout["data_v"]
            without_flag.stored[layout["oid_u"]] = layout["data_u"]
            set_lfs_endpoint(ws, without_flag.url)
            result = run_prune(
                ws, ["--verify-remote", "--when-unverified=halt"]
            )
            print(f"verify no-unreachable exit={result.returncode}")
            assert_success(result)
            assert_object_absent(layout["store"], orphan_oid)
            assert_object_absent(layout["store"], layout["oid_v"])
            assert_object_absent(layout["store"], layout["oid_u"])
            assert_object_bytes(
                layout["store"], layout["oid_h"], layout["data_h"]
            )
    with storing_batch_server() as with_flag:
        with workspace() as ws:
            layout = _two_candidates_plus_head(ws)
            orphan = _payload()
            orphan_oid = sha256_hex(orphan)
            assert_success(clean_bytes(ws, orphan))
            with_flag.stored[layout["oid_v"]] = layout["data_v"]
            with_flag.stored[layout["oid_u"]] = layout["data_u"]
            set_lfs_endpoint(ws, with_flag.url)
            result = run_prune(
                ws,
                [
                    "--verify-remote",
                    "--verify-unreachable",
                    "--when-unverified=halt",
                ],
            )
            print(
                f"verify-unreachable halt exit={result.returncode} "
                f"orphan={orphan_oid}"
            )
            assert_object_bytes(layout["store"], orphan_oid, orphan)
            assert_object_bytes(
                layout["store"], layout["oid_v"], layout["data_v"]
            )
            assert_object_bytes(
                layout["store"], layout["oid_u"], layout["data_u"]
            )
            assert_object_bytes(
                layout["store"], layout["oid_h"], layout["data_h"]
            )


# ---------------------------------------------------------------------------
# G. Fetch prune option
# ---------------------------------------------------------------------------


def test_fetch_prune_same_retention_keeps_stash_deletes_stale():
    """Fetch --prune deletes a true-commit stale object, keeps HEAD and stash."""
    extra = _payload()
    extra_oid = sha256_hex(extra)
    with storing_batch_server() as svc:
        with workspace() as no_prune:
            layout = _main_pushed(no_prune)
            no_prune.write(layout["rel"], extra)
            _git_ok(no_prune, ["stash"])
            svc.stored[layout["head_oid"]] = layout["head"]
            svc.stored[layout["stale_oid"]] = layout["stale"]
            svc.stored[extra_oid] = extra
            set_lfs_endpoint(no_prune, svc.url)
            require_success(no_prune.invoke_via_git(["fetch"]))
            print("fetch without prune left stale")
            require_object_bytes(
                layout["store"], layout["stale_oid"], layout["stale"]
            )
            require_object_bytes(
                layout["store"], layout["head_oid"], layout["head"]
            )
            require_object_bytes(layout["store"], extra_oid, extra)
        with workspace() as pruned:
            layout = _main_pushed(pruned)
            pruned.write(layout["rel"], extra)
            _git_ok(pruned, ["stash"])
            svc.stored[layout["head_oid"]] = layout["head"]
            svc.stored[layout["stale_oid"]] = layout["stale"]
            svc.stored[extra_oid] = extra
            set_lfs_endpoint(pruned, svc.url)
            require_success(pruned.invoke_via_git(["fetch", "--prune"]))
            print(f"fetch --prune stash={extra_oid}")
            require_object_absent(layout["store"], layout["stale_oid"])
            require_object_bytes(
                layout["store"], layout["head_oid"], layout["head"]
            )
            require_object_bytes(layout["store"], extra_oid, extra)


# ---------------------------------------------------------------------------
# H. Custom / shared storage
# ---------------------------------------------------------------------------


def test_custom_storage_still_prunes():
    """A custom storage root still deletes stale and keeps HEAD."""
    with workspace() as ws:
        ws.init_repo()
        store_dir = ws.path / f"st_{token()}"
        configure_storage_root(ws, store_dir)
        install_local_keeping_process(ws)
        track_pattern(ws, "*.bin")
        rel = _rel("p")
        stale = _payload()
        head = _payload()
        stale_oid = commit_tracked_payload_dated(ws, rel, stale, _FAR)
        head_digest = commit_tracked_payload(ws, rel, head)
        configure_recentness(ws, ref_days=0)
        _plant_origin_at(ws, _sha(ws))
        store = configured_lfs_store_root(ws)
        assert store == store_dir.resolve(), (
            f"configured store {store} is not {store_dir.resolve()}"
        )
        require_object_bytes(store, stale_oid, stale)
        require_object_bytes(store, head_digest, head)
        require_success(run_prune(ws))
        print(f"custom store stale={stale_oid} head={head_digest}")
        require_object_absent(store, stale_oid)
        require_object_bytes(store, head_digest, head)


def test_shared_storage_uses_invoked_repository_rules():
    """Prune in A deletes B's HEAD object on a shared store; prune in B keeps it."""
    with workspace() as from_a:
        store_dir = from_a.path / f"st_{token()}"
        hb, payload_b = _shared_pair(from_a, store_dir)
        require_success(run_prune(from_a))
        print(f"prune-in-A deleted hb={hb}")
        require_object_absent(store_dir.resolve(), hb)
    with workspace() as from_b:
        store_dir = from_b.path / f"st_{token()}"
        b_rel = f"b_{token()}"
        hb, payload_b = _shared_pair(from_b, store_dir, b_rel=b_rel)
        cwd = from_b.resolve(b_rel)
        require_success(run_prune(from_b, cwd=cwd))
        print(f"prune-in-B kept hb={hb}")
        require_object_bytes(store_dir.resolve(), hb, payload_b)


def _shared_pair(ws, store_dir: Path, *, b_rel: str | None = None):
    """Repo A at workspace root, repo B in a subdir, both using *store_dir*."""
    ws.init_repo()
    configure_storage_root(ws, store_dir)
    install_local_keeping_process(ws)
    track_pattern(ws, "*.bin")
    rel_a = _rel("a")
    stale = _payload()
    head_a = _payload()
    commit_tracked_payload_dated(ws, rel_a, stale, _FAR)
    commit_tracked_payload(ws, rel_a, head_a)
    configure_recentness(ws, ref_days=0)
    _plant_origin_at(ws, _sha(ws))
    repo_b = b_rel if b_rel is not None else f"b_{token()}"
    ws.init_repo(repo_b)
    cwd = ws.resolve(repo_b)
    result = ws.git_config_set(
        "lfs.storage", str(store_dir), local=True, cwd=cwd
    )
    assert result.returncode == 0, (
        f"set lfs.storage in B failed: {result.stderr_text}"
    )
    _nested_install(ws, cwd)
    require_success(run_track(ws, ["*.bin"], cwd=cwd))
    rel_b = _rel("b")
    payload_b = _payload()
    hb = _commit_at(ws, repo_b, rel_b, payload_b)
    _recentness_at(ws, cwd, ref_days=0)
    _add_origin(ws, cwd=cwd)
    _track_remote(ws, _branch(ws, cwd=cwd), _sha(ws, cwd=cwd), cwd=cwd)
    require_object_bytes(store_dir.resolve(), hb, payload_b)
    return hb, payload_b


# ---------------------------------------------------------------------------
# I. Verbose and PATH
# ---------------------------------------------------------------------------


def test_verbose_names_each_pruned_oid():
    """--verbose writes each deleted (or, with --dry-run, would-be-deleted) oid on stdout."""
    with workspace() as live:
        layout = _main_pushed(live)
        result = run_prune(live, ["--verbose"])
        require_success(result)
        print(f"verbose live stdout={result.stdout_text!r}")
        require_object_absent(layout["store"], layout["stale_oid"])
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
        assert layout["stale_oid"] in result.stdout_text, (
            "prune --verbose did not name the deleted object's oid on stdout"
        )
        assert layout["head_oid"] not in result.stdout_text, (
            "prune --verbose named the retained current-checkout oid"
        )
    with workspace() as ws:
        layout = _main_pushed(ws)
        result = run_prune(ws, ["--dry-run", "--verbose"])
        require_success(result)
        print(f"verbose dry-run stdout={result.stdout_text!r}")
        require_object_bytes(
            layout["store"], layout["stale_oid"], layout["stale"]
        )
        assert layout["stale_oid"] in result.stdout_text, (
            "prune --dry-run --verbose did not name the candidate's oid on stdout"
        )
        assert layout["head_oid"] not in result.stdout_text, (
            "prune --dry-run --verbose named the retained current-checkout oid"
        )


def test_prune_fails_without_product_on_path():
    """Prune without the product on PATH is non-success; with PATH it deletes stale."""
    with workspace() as ws:
        layout = _main_pushed(ws)
        blocked = run_prune(
            ws,
            env_updates={"PATH": path_without_product_bin(ws.env)},
        )
        print(f"PATH-blocked prune exit={blocked.returncode}")
        assert blocked.returncode != 0, (
            "prune succeeded after the product was removed from PATH"
        )
        require_object_bytes(
            layout["store"], layout["stale_oid"], layout["stale"]
        )
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
        require_success(run_prune(ws))
        require_object_absent(layout["store"], layout["stale_oid"])
        require_object_bytes(
            layout["store"], layout["head_oid"], layout["head"]
        )
