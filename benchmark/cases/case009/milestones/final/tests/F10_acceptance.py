# feature: F10
"""File locking acceptance tests.

PRD: FP-10. Oracles are whether the locking fixture holds a path, whether
a fresh workspace's live list names it, working-tree write bits on
lockable paths, PUT presence, and whether a verify-class exchange
occurred. Message wording, JSON field names, verify mark characters, and
exit-code numbers are not pinned.
"""

from __future__ import annotations

import re

from pathlib import Path

from _harness import reserve_loopback_port, token, workspace
from _helpers import (
    add_git_remote,
    assert_file_read_only,
    assert_file_writable,
    assert_invalid_unlike_success,
    assert_json_strings_include,
    assert_listing_remainder_stable_unlike,
    assert_server_holds_lock,
    assert_server_lacks_lock,
    caller_visible,
    commit_ordinary_blob,
    disable_lock_verification,
    enable_lock_verification,
    enable_skip_smudge_environment,
    extract_json_listing,
    git_zero_oid,
    head_oid,
    init_bare_git_remote,
    install_credential_helper,
    install_local_keeping_process,
    locking_api_server,
    locks_listing_visible,
    make_file_writable,
    named_path_listing_line,
    path_without_product_bin,
    point_lfs_at,
    prepare_tracked_commit,
    require_file_read_only,
    require_file_writable,
    require_git_config_set,
    require_invalid_unlike_success,
    require_lockable_set,
    require_locking_create_conflict,
    require_locking_verify_received,
    require_no_put_of,
    require_put_of,
    require_server_holds_lock,
    require_server_lacks_lock,
    require_success,
    run_lock,
    run_locks,
    run_post_checkout,
    run_post_commit,
    run_post_merge,
    run_unlock,
    runtime_http_url,
    set_lfs_endpoint,
    sha256_hex,
    strip_listing_covariates,
    track_lockable,
    unset_lock_verification,
)


def _payload(*, pad: int = 0) -> bytes:
    return (f"blob-{token()}\n" + ("x" * pad)).encode("utf-8")


def _rel(prefix: str = "p") -> str:
    return f"{prefix}_{token()}.bin"


def _git_ok(ws, argv, **kwargs):
    result = ws.git(argv, **kwargs)
    assert result.returncode == 0, (
        f"git {argv!r} failed (exit {result.returncode}): {result.stderr_text}"
    )
    return result


def _repo_on(ws, url: str) -> None:
    ws.init_repo()
    commit_ordinary_blob(ws, f"keep_{token()}.txt", f"{token()}\n")
    point_lfs_at(ws, url)


def _live_list(ws) -> tuple:
    result = run_locks(ws, [])
    require_success(result)
    text = locks_listing_visible(result)
    print(f"live locks={text!r}")
    return result, text


def _fresh_live_names(url: str, path: str) -> str:
    with workspace() as other:
        _repo_on(other, url)
        _, text = _live_list(other)
        assert path in text, (
            f"fresh workspace live list does not name {path!r}: {text!r}"
        )
        assert path, "locked path token is empty"
        return text


def _abs(ws, rel: str) -> Path:
    return ws.resolve(rel)


def _records_since(svc, start: int):
    return svc.records[start:]


def _covariates(ws, *tokens: str) -> list[str]:
    out = [str(ws.path.resolve()), *[item for item in tokens if item]]
    return out


def _named_lock_remainders(
    text: str, path_ours: str, path_theirs: str, strip: list[str]
) -> tuple[str, str]:
    """Strip identity covariates from each named lock line of one listing."""
    line_ours = named_path_listing_line(
        text, path_ours, other_paths=[path_theirs]
    )
    line_theirs = named_path_listing_line(
        text, path_theirs, other_paths=[path_ours]
    )
    return (
        strip_listing_covariates(line_ours, strip),
        strip_listing_covariates(line_theirs, strip),
    )


def _mixed_verify_named_remainders(owned_path: str, foreign_path: str):
    """One mixed lock set: unmarked and --verify named remainders keyed by path."""
    assert owned_path != foreign_path, (
        f"owned and foreign paths must differ: {owned_path!r}"
    )
    with locking_api_server() as svc:
        svc.inject_foreign_lock(foreign_path)
        with workspace() as ws:
            _repo_on(ws, svc.url)
            require_success(run_lock(ws, [owned_path]))
            ours_id = svc.lock_id_for(owned_path)
            theirs_id = svc.lock_id_for(foreign_path)
            strip = _covariates(
                ws,
                owned_path,
                foreign_path,
                svc.current_owner,
                svc.foreign_owner,
                ours_id,
                theirs_id,
                svc.url,
                "--verify",
            )

            plain_a = run_locks(ws, [])
            require_success(plain_a)
            plain_b = run_locks(ws, [])
            require_success(plain_b)
            rem_plain_owned_a, rem_plain_foreign_a = _named_lock_remainders(
                locks_listing_visible(plain_a), owned_path, foreign_path, strip
            )
            rem_plain_owned_b, rem_plain_foreign_b = _named_lock_remainders(
                locks_listing_visible(plain_b), owned_path, foreign_path, strip
            )
            print(
                f"unmarked named remainders owned={owned_path!r} "
                f"{rem_plain_owned_a!r}/{rem_plain_owned_b!r} "
                f"foreign={foreign_path!r} "
                f"{rem_plain_foreign_a!r}/{rem_plain_foreign_b!r}"
            )

            marked_a = run_locks(ws, ["--verify"])
            require_success(marked_a)
            marked_b = run_locks(ws, ["--verify"])
            require_success(marked_b)
            rem_mark_owned_a, rem_mark_foreign_a = _named_lock_remainders(
                locks_listing_visible(marked_a), owned_path, foreign_path, strip
            )
            rem_mark_owned_b, rem_mark_foreign_b = _named_lock_remainders(
                locks_listing_visible(marked_b), owned_path, foreign_path, strip
            )
            print(
                f"verify named remainders owned={owned_path!r} "
                f"{rem_mark_owned_a!r}/{rem_mark_owned_b!r} "
                f"foreign={foreign_path!r} "
                f"{rem_mark_foreign_a!r}/{rem_mark_foreign_b!r}"
            )
            return {
                "plain_owned": (rem_plain_owned_a, rem_plain_owned_b),
                "plain_foreign": (rem_plain_foreign_a, rem_plain_foreign_b),
                "mark_owned": (rem_mark_owned_a, rem_mark_owned_b),
                "mark_foreign": (rem_mark_foreign_a, rem_mark_foreign_b),
                "mark_by_path": {
                    owned_path: (rem_mark_owned_a, rem_mark_owned_b),
                    foreign_path: (rem_mark_foreign_a, rem_mark_foreign_b),
                },
            }


def _commit_lockable_pair(ws):
    """Install hooks, track a lockable glob, commit two matches plus a control.

    The lockable commit is never the root commit: post-commit's changed-path
    scan is a HEAD diff, and a root commit has no parent to diff against.
    """
    install_local_keeping_process(ws)
    commit_ordinary_blob(ws, f"keep_{token()}.txt", f"{token()}\n")
    ext = token()
    track_lockable(ws, f"*.{ext}")
    rel_a = f"a_{token()}.{ext}"
    rel_b = f"b_{token()}.{ext}"
    ctrl = f"n_{token()}.txt"
    ws.write(rel_a, _payload())
    ws.write(rel_b, _payload())
    ws.write(ctrl, f"ctrl-{token()}\n")
    _git_ok(ws, ["add", "--", rel_a, rel_b, ctrl, ".gitattributes"])
    _git_ok(ws, ["commit", "-m", "lockable pair"])
    require_lockable_set(ws, rel_a)
    require_lockable_set(ws, rel_b)
    return rel_a, rel_b, ctrl, ext


def _bare_origin(ws, url: str):
    ws.init_repo()
    bare = init_bare_git_remote(ws, f"bare_{token()}")
    add_git_remote(ws, "origin", str(bare))
    set_lfs_endpoint(ws, url)
    return bare


# ---------------------------------------------------------------------------
# A. Lock creates a server-side lock
# ---------------------------------------------------------------------------


def test_lock_creates_server_side_lock_visible_from_fresh_clone():
    """Lock then a fresh workspace's live list still names the path."""
    path = _rel("exist")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            ws.write(path, _payload())
            result = run_lock(ws, [path])
            print(f"lock exit={result.returncode}")
            require_success(result)
            require_server_holds_lock(svc, path)
        _fresh_live_names(svc.url, path)


def test_lock_missing_working_tree_path_still_creates_server_lock():
    """A locally missing path still creates a server-side lock."""
    path = _rel("missing")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            try:
                ws.read_bytes(path)
            except FileNotFoundError:
                pass
            else:
                raise AssertionError(f"precondition: {path!r} already exists")
            result = run_lock(ws, [path])
            print(f"missing-path lock exit={result.returncode}")
            require_success(result)
            require_server_holds_lock(svc, path)
        _fresh_live_names(svc.url, path)


def test_lock_json_success_creates_server_lock():
    """JSON mode is available on a successful create that holds the path."""
    path = _rel("json")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            result = run_lock(ws, ["--json", path])
            print(f"lock --json exit={result.returncode}")
            require_success(result)
            parsed = extract_json_listing(result)
            print(f"lock json={parsed!r}")
            require_server_holds_lock(svc, path)
        _fresh_live_names(svc.url, path)


def test_direct_binary_lock_creates_server_lock():
    """Direct binary lock creates the same server-side lock."""
    path = _rel("bin")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            result = run_lock(ws, [path], via_git=False)
            print(f"direct lock exit={result.returncode}")
            require_success(result)
            require_server_holds_lock(svc, path)
        _fresh_live_names(svc.url, path)


def test_lock_nested_repository_relative_path():
    """A nested repository-relative path is the locked path."""
    nested = f"dir_{token()}/file_{token()}.bin"
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            result = run_lock(ws, [nested])
            print(f"nested lock exit={result.returncode} path={nested!r}")
            require_success(result)
            require_server_holds_lock(svc, nested)
        text = _fresh_live_names(svc.url, nested)
        assert nested in text


# ---------------------------------------------------------------------------
# B. Unlock by path or id; force; dirty / missing
# ---------------------------------------------------------------------------


def test_unlock_by_path_clears_server_lock():
    """Unlock by path removes the server lock; a fresh list omits it."""
    path = _rel("u")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            require_success(run_lock(ws, [path]))
            require_server_holds_lock(svc, path)
            result = run_unlock(ws, [path])
            print(f"unlock-by-path exit={result.returncode}")
            require_success(result)
            require_server_lacks_lock(svc, path)
        with workspace() as other:
            _repo_on(other, svc.url)
            _, text = _live_list(other)
            assert path not in text, (
                f"fresh live list still names unlocked path {path!r}: {text!r}"
            )


def test_unlock_by_id_clears_server_lock():
    """Unlock by id clears only that lock when two locks exist."""
    path_p = _rel("idp")
    path_q = _rel("idq")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            require_success(run_lock(ws, [path_p]))
            require_success(run_lock(ws, [path_q]))
            id_q = require_server_holds_lock(svc, path_q)
            require_server_holds_lock(svc, path_p)
            result = run_unlock(ws, [f"--id={id_q}"])
            print(f"unlock --id exit={result.returncode} id={id_q!r}")
            require_success(result)
            assert_server_lacks_lock(svc, path_q)
            assert_server_holds_lock(svc, path_p)


def test_unlock_by_id_of_dirty_path_reaches_server_without_force():
    """Unlock by id skips the local dirty/missing check and still reaches the server."""
    path_dirty = _rel("idd")
    path_keep = _rel("idk")
    path_gone = _rel("idg")
    path_keep_g = _rel("idkg")

    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            ws.write(path_dirty, _payload())
            ws.write(path_keep, _payload())
            _git_ok(ws, ["add", "--", path_dirty, path_keep])
            _git_ok(ws, ["commit", "-m", "id dirty pair"])
            require_success(run_lock(ws, [path_dirty]))
            require_success(run_lock(ws, [path_keep]))
            id_dirty = require_server_holds_lock(svc, path_dirty)
            require_server_holds_lock(svc, path_keep)
            ws.write(path_dirty, _payload(pad=5))
            result = run_unlock(ws, [f"--id={id_dirty}"])
            print(f"id-dirty unlock exit={result.returncode} id={id_dirty!r}")
            require_success(result)
            require_server_lacks_lock(svc, path_dirty)
            require_server_holds_lock(svc, path_keep)
        with workspace() as other:
            _repo_on(other, svc.url)
            _, text = _live_list(other)
            assert path_dirty not in text, (
                f"fresh live list still names unlocked dirty-id path "
                f"{path_dirty!r}: {text!r}"
            )
            assert path_keep in text, (
                f"fresh live list omitted the remaining lock "
                f"{path_keep!r}: {text!r}"
            )

    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            ws.write(path_gone, _payload())
            ws.write(path_keep_g, _payload())
            _git_ok(ws, ["add", "--", path_gone, path_keep_g])
            _git_ok(ws, ["commit", "-m", "id missing pair"])
            require_success(run_lock(ws, [path_gone]))
            require_success(run_lock(ws, [path_keep_g]))
            id_gone = require_server_holds_lock(svc, path_gone)
            require_server_holds_lock(svc, path_keep_g)
            _abs(ws, path_gone).unlink()
            result = run_unlock(ws, [f"--id={id_gone}"])
            print(f"id-missing unlock exit={result.returncode} id={id_gone!r}")
            require_success(result)
            require_server_lacks_lock(svc, path_gone)
            require_server_holds_lock(svc, path_keep_g)
        with workspace() as other:
            _repo_on(other, svc.url)
            _, text = _live_list(other)
            assert path_gone not in text, (
                f"fresh live list still names unlocked missing-id path "
                f"{path_gone!r}: {text!r}"
            )
            assert path_keep_g in text, (
                f"fresh live list omitted the remaining lock "
                f"{path_keep_g!r}: {text!r}"
            )


def test_unlock_without_force_fails_on_dirty_path_force_reaches_server():
    """Dirty-path check is per unlocked path (path selector)."""
    path = _rel("dirty")
    other = _rel("other")

    with locking_api_server() as svc_dirty:
        with workspace() as ws_dirty:
            _repo_on(ws_dirty, svc_dirty.url)
            ws_dirty.write(path, _payload())
            _git_ok(ws_dirty, ["add", "--", path])
            _git_ok(ws_dirty, ["commit", "-m", "add dirty target"])
            require_success(run_lock(ws_dirty, [path]))
            ws_dirty.write(path, _payload(pad=3))
            blocked = run_unlock(ws_dirty, [path])
            print(f"dirty unlock exit={blocked.returncode}")
            assert blocked.returncode != 0, (
                "unlock without force succeeded on a dirty locked path"
            )
            require_server_holds_lock(svc_dirty, path)

    with locking_api_server() as svc_clean:
        with workspace() as ws_clean:
            _repo_on(ws_clean, svc_clean.url)
            ws_clean.write(path, _payload())
            _git_ok(ws_clean, ["add", "--", path])
            _git_ok(ws_clean, ["commit", "-m", "add clean target"])
            require_success(run_lock(ws_clean, [path]))
            cleared = run_unlock(ws_clean, [path])
            print(f"clean unlock exit={cleared.returncode}")
            require_success(cleared)
            require_server_lacks_lock(svc_clean, path)

    with locking_api_server() as svc_other:
        with workspace() as ws_other:
            _repo_on(ws_other, svc_other.url)
            ws_other.write(path, _payload())
            ws_other.write(other, _payload())
            _git_ok(ws_other, ["add", "--", path, other])
            _git_ok(ws_other, ["commit", "-m", "add pair"])
            require_success(run_lock(ws_other, [path]))
            ws_other.write(other, _payload(pad=4))
            result = run_unlock(ws_other, [path])
            print(f"other-path-dirty unlock exit={result.returncode}")
            require_success(result)
            require_server_lacks_lock(svc_other, path)

    with locking_api_server() as svc_path_force:
        with workspace() as ws_pf:
            _repo_on(ws_pf, svc_path_force.url)
            ws_pf.write(path, _payload())
            _git_ok(ws_pf, ["add", "--", path])
            _git_ok(ws_pf, ["commit", "-m", "path force"])
            require_success(run_lock(ws_pf, [path]))
            ws_pf.write(path, _payload(pad=7))
            forced = run_unlock(ws_pf, ["--force", path])
            print(f"dirty path --force exit={forced.returncode}")
            require_success(forced)
            require_server_lacks_lock(svc_path_force, path)


def test_unlock_without_force_fails_on_missing_path_force_reaches_server():
    """Unlock without force fails when a locked path is gone from the tree."""
    path = _rel("gone")

    with locking_api_server() as svc_block:
        with workspace() as ws:
            _repo_on(ws, svc_block.url)
            ws.write(path, _payload())
            _git_ok(ws, ["add", "--", path])
            _git_ok(ws, ["commit", "-m", "track gone"])
            require_success(run_lock(ws, [path]))
            require_server_holds_lock(svc_block, path)
            _abs(ws, path).unlink()
            blocked = run_unlock(ws, [path])
            print(f"missing-path unlock exit={blocked.returncode}")
            assert blocked.returncode != 0, (
                "unlock without force succeeded for a missing working-tree path"
            )
            require_server_holds_lock(svc_block, path)

    with locking_api_server() as svc_force:
        with workspace() as ws:
            _repo_on(ws, svc_force.url)
            ws.write(path, _payload())
            _git_ok(ws, ["add", "--", path])
            _git_ok(ws, ["commit", "-m", "track gone force"])
            require_success(run_lock(ws, [path]))
            _abs(ws, path).unlink()
            forced = run_unlock(ws, ["--force", path])
            print(f"missing-path --force exit={forced.returncode}")
            require_success(forced)
            require_server_lacks_lock(svc_force, path)


def test_unlock_force_removes_foreign_lock_when_server_permits():
    """Force asks the server to drop a foreign lock; without force it remains."""
    path = _rel("foreign")
    with locking_api_server() as svc_keep:
        with workspace() as ws:
            _repo_on(ws, svc_keep.url)
            ws.write(path, _payload())
            _git_ok(ws, ["add", "--", path])
            _git_ok(ws, ["commit", "-m", "foreign path"])
            svc_keep.inject_foreign_lock(path)
            require_server_holds_lock(svc_keep, path)
            blocked = run_unlock(ws, [path])
            print(f"foreign unlock exit={blocked.returncode}")
            assert blocked.returncode != 0, (
                "unlock without force removed a foreign lock"
            )
            require_server_holds_lock(svc_keep, path)

    with locking_api_server() as svc_drop:
        with workspace() as ws:
            _repo_on(ws, svc_drop.url)
            ws.write(path, _payload())
            _git_ok(ws, ["add", "--", path])
            _git_ok(ws, ["commit", "-m", "foreign force"])
            svc_drop.inject_foreign_lock(path)
            forced = run_unlock(ws, ["--force", path])
            print(f"foreign --force exit={forced.returncode}")
            require_success(forced)
            require_server_lacks_lock(svc_drop, path)


def test_unlock_with_both_or_neither_selector_is_invalid():
    """Unlock needs exactly one of path or lock id."""
    path = _rel("sel")
    with locking_api_server() as svc_ok:
        with workspace() as ws_ok:
            _repo_on(ws_ok, svc_ok.url)
            ws_ok.write(path, _payload())
            _git_ok(ws_ok, ["add", "--", path])
            _git_ok(ws_ok, ["commit", "-m", "selector ok"])
            require_success(run_lock(ws_ok, [path]))
            ok = run_unlock(ws_ok, [path])
            require_success(ok)
            require_server_lacks_lock(svc_ok, path)

    with locking_api_server() as svc_both:
        with workspace() as ws_both:
            _repo_on(ws_both, svc_both.url)
            ws_both.write(path, _payload())
            _git_ok(ws_both, ["add", "--", path])
            _git_ok(ws_both, ["commit", "-m", "both selectors"])
            require_success(run_lock(ws_both, [path]))
            lock_id = require_server_holds_lock(svc_both, path)
            both = run_unlock(ws_both, [path, f"--id={lock_id}"])
            print(f"both-selectors exit={both.returncode}")
            require_invalid_unlike_success(ok, both)
            require_server_holds_lock(svc_both, path)

    with locking_api_server() as svc_none:
        with workspace() as ws_none:
            _repo_on(ws_none, svc_none.url)
            ws_none.write(path, _payload())
            _git_ok(ws_none, ["add", "--", path])
            _git_ok(ws_none, ["commit", "-m", "no selector"])
            require_success(run_lock(ws_none, [path]))
            neither = run_unlock(ws_none, [])
            print(f"neither-selector exit={neither.returncode}")
            require_invalid_unlike_success(ok, neither)
            require_server_holds_lock(svc_none, path)


# ---------------------------------------------------------------------------
# C. Locks listing: filters, local/cached, verify marking, JSON
# ---------------------------------------------------------------------------


def test_locks_path_filter_selects_one_lock():
    """Path filter names the matching lock and omits the others."""
    path_p = _rel("fp")
    path_q = _rel("fq")
    path_r = _rel("fr")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            require_success(run_lock(ws, [path_p]))
            require_success(run_lock(ws, [path_q]))
            listed_p = run_locks(ws, ["--path", path_p])
            require_success(listed_p)
            text_p = locks_listing_visible(listed_p)
            listed_q = run_locks(ws, ["--path", path_q])
            require_success(listed_q)
            text_q = locks_listing_visible(listed_q)
            print(f"path P={text_p!r} Q={text_q!r}")
            assert path_p in text_p and path_q not in text_p, text_p
            assert path_q in text_q and path_p not in text_q, text_q
            listed_r = run_locks(ws, ["--path", path_r])
            require_success(listed_r)
            text_r = locks_listing_visible(listed_r)
            print(f"path R={text_r!r}")
            assert path_p not in text_r and path_q not in text_r, text_r


def test_locks_id_filter_selects_one_lock():
    """Id filter selects one lock and is not an echo of the id token."""
    path_p = _rel("ip")
    path_q = _rel("iq")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            require_success(run_lock(ws, [path_p]))
            require_success(run_lock(ws, [path_q]))
            id_q = require_server_holds_lock(svc, path_q)
            unknown = f"id_{token()}"
            listed_q = run_locks(ws, [f"--id={id_q}"])
            require_success(listed_q)
            text_q = locks_listing_visible(listed_q)
            listed_u = run_locks(ws, [f"--id={unknown}"])
            require_success(listed_u)
            text_u = locks_listing_visible(listed_u)
            print(f"id Q={text_q!r} U={text_u!r}")
            assert path_q in text_q and path_p not in text_q, text_q
            assert path_q not in text_u and path_p not in text_u, text_u
            strip = _covariates(ws, id_q, unknown, svc.url)
            rem_q = strip_listing_covariates(text_q, strip)
            rem_u = strip_listing_covariates(text_u, strip)
            print(f"id-filter remainder Q={rem_q!r} U={rem_u!r}")
            assert rem_q != rem_u, (
                "id filter remainder collapsed to an echo of the id token"
            )


def test_locks_json_names_locked_paths():
    """Live JSON listing is parseable and names the locked path."""
    path = _rel("jl")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            require_success(run_lock(ws, [path]))
            result = run_locks(ws, ["--json"])
            require_success(result)
            parsed = extract_json_listing(result)
            print(f"locks json={parsed!r}")
            assert_json_strings_include(parsed, path)


def test_locks_local_and_cached_do_not_claim_live_server_truth():
    """Local-only and cached listings skip or reuse network results."""
    path_p = _rel("lp")
    path_q = _rel("lq")
    path_r = _rel("lr")
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            require_success(run_lock(ws, [path_p]))
            svc.inject_foreign_lock(path_q)
            _, live = _live_list(ws)
            assert path_p in live and path_q in live, live
            local = run_locks(ws, ["--local"])
            require_success(local)
            local_text = locks_listing_visible(local)
            print(f"local={local_text!r}")
            assert path_p in local_text, local_text
            assert path_q not in local_text, local_text
            cached = run_locks(ws, ["--cached"])
            require_success(cached)
            cached_text = locks_listing_visible(cached)
            print(f"cached-before-R={cached_text!r}")
            assert path_p in cached_text and path_q in cached_text, cached_text
            svc.inject_foreign_lock(path_r)
            cached_after = run_locks(ws, ["--cached"])
            require_success(cached_after)
            cached_after_text = locks_listing_visible(cached_after)
            print(f"cached-after-R={cached_after_text!r}")
            assert path_r not in cached_after_text, cached_after_text
            _, live_after = _live_list(ws)
            assert path_r in live_after, live_after
            local_after = run_locks(ws, ["--local"])
            require_success(local_after)
            local_after_text = locks_listing_visible(local_after)
            assert path_q not in local_after_text, local_after_text
            assert path_r not in local_after_text, local_after_text
            dead_port = reserve_loopback_port()
            closed = f"http://127.0.0.1:{dead_port}/{token()}/info/lfs"
            set_lfs_endpoint(ws, closed)
            print(f"unreachable={closed!r}")
            local_off = run_locks(ws, ["--local"])
            require_success(local_off)
            local_off_text = locks_listing_visible(local_off)
            print(f"local-unreachable={local_off_text!r}")
            assert path_p in local_off_text, local_off_text
            assert path_q not in local_off_text, local_off_text
            assert path_r not in local_off_text, local_off_text


def test_locks_verify_marks_locks_owned_by_current_user():
    """--verify marks owned locks; leftover follows ownership, not path identity."""
    path_a = _rel("va")
    path_b = _rel("vb")
    own_a = _mixed_verify_named_remainders(path_a, path_b)
    own_b = _mixed_verify_named_remainders(path_b, path_a)

    for label, obs in (("own-a", own_a), ("own-b", own_b)):
        rem_plain_owned_a, rem_plain_owned_b = obs["plain_owned"]
        rem_plain_foreign_a, rem_plain_foreign_b = obs["plain_foreign"]
        assert rem_plain_owned_a == rem_plain_owned_b, (
            "unmarked owned-line remainder was not stable across two "
            f"observations of the same listing ({label}): "
            f"{rem_plain_owned_a!r} vs {rem_plain_owned_b!r}"
        )
        assert rem_plain_foreign_a == rem_plain_foreign_b, (
            "unmarked foreign-line remainder was not stable across two "
            f"observations of the same listing ({label}): "
            f"{rem_plain_foreign_a!r} vs {rem_plain_foreign_b!r}"
        )
        assert rem_plain_owned_a == rem_plain_foreign_a, (
            "unmarked listing already distinguished owned from foreign "
            "after stripping path, owner, id, and URL; --verify marking "
            f"is not demonstrated against that baseline ({label}): "
            f"{rem_plain_owned_a!r} vs {rem_plain_foreign_a!r}"
        )

    # In one --verify listing, owned versus foreign named remainders differ.
    assert_listing_remainder_stable_unlike(
        *own_a["mark_owned"],
        *own_a["mark_foreign"],
    )
    assert_listing_remainder_stable_unlike(
        *own_b["mark_owned"],
        *own_b["mark_foreign"],
    )

    # Same two paths, ownership swapped: leftover follows ownership, not
    # which path is lexicographically first.
    assert_listing_remainder_stable_unlike(
        *own_a["mark_by_path"][path_a],
        *own_b["mark_by_path"][path_a],
    )
    assert_listing_remainder_stable_unlike(
        *own_b["mark_by_path"][path_b],
        *own_a["mark_by_path"][path_b],
    )


# ---------------------------------------------------------------------------
# D. Unlock --remote targets that endpoint
# ---------------------------------------------------------------------------


def test_unlock_remote_selection_targets_that_endpoint_locks():
    """Unlock --remote clears only the named endpoint's lock."""
    path_p = _rel("rp")
    path_q = _rel("rq")
    sibling = f"sib_{token()}"
    origin_git = runtime_http_url("origin")
    sibling_git = runtime_http_url("sibling")

    with locking_api_server() as origin_a, locking_api_server() as sib_a:
        origin_a.inject_foreign_lock(path_p)
        sib_a.inject_foreign_lock(path_q)
        with workspace() as ws:
            ws.init_repo()
            commit_ordinary_blob(ws, path_p, f"{token()}\n")
            commit_ordinary_blob(ws, path_q, f"{token()}\n")
            add_git_remote(ws, "origin", origin_git)
            add_git_remote(ws, sibling, sibling_git)
            require_git_config_set(
                ws, "remote.origin.lfsurl", origin_a.url, local=True
            )
            require_git_config_set(
                ws, f"remote.{sibling}.lfsurl", sib_a.url, local=True
            )
            require_git_config_set(ws, "lfs.transfer.maxretries", "1", local=True)
            require_git_config_set(
                ws, "lfs.transfer.maxretrydelay", "0", local=True
            )
            require_git_config_set(ws, "lfs.dialtimeout", "1", local=True)
            result = run_unlock(ws, ["--remote", "origin", "--force", path_p])
            print(f"unlock --remote origin exit={result.returncode}")
            require_success(result)
            assert_server_lacks_lock(origin_a, path_p)
            assert_server_holds_lock(sib_a, path_q)

    with locking_api_server() as origin_b, locking_api_server() as sib_b:
        origin_b.inject_foreign_lock(path_p)
        sib_b.inject_foreign_lock(path_q)
        with workspace() as ws:
            ws.init_repo()
            commit_ordinary_blob(ws, path_p, f"{token()}\n")
            commit_ordinary_blob(ws, path_q, f"{token()}\n")
            add_git_remote(ws, "origin", origin_git)
            add_git_remote(ws, sibling, sibling_git)
            require_git_config_set(
                ws, "remote.origin.lfsurl", origin_b.url, local=True
            )
            require_git_config_set(
                ws, f"remote.{sibling}.lfsurl", sib_b.url, local=True
            )
            require_git_config_set(ws, "lfs.transfer.maxretries", "1", local=True)
            require_git_config_set(
                ws, "lfs.transfer.maxretrydelay", "0", local=True
            )
            require_git_config_set(ws, "lfs.dialtimeout", "1", local=True)
            result = run_unlock(ws, ["--remote", sibling, "--force", path_q])
            print(f"unlock --remote sibling exit={result.returncode}")
            require_success(result)
            assert_server_lacks_lock(sib_b, path_q)
            assert_server_holds_lock(origin_b, path_p)


# ---------------------------------------------------------------------------
# E. Directory, conflict, no locking support, auth failure
# ---------------------------------------------------------------------------


def test_lock_directory_path_fails_and_creates_no_server_lock():
    """Locking a working-copy directory fails and does not create a lock."""
    dirname = f"d_{token()}"
    nested = f"{dirname}/f_{token()}.bin"
    with locking_api_server() as svc:
        with workspace() as ws:
            _repo_on(ws, svc.url)
            ws.write(nested, _payload())
            dirty = run_lock(ws, [dirname])
            print(f"directory lock exit={dirty.returncode}")
            assert_server_lacks_lock(svc, dirname)
            assert_server_lacks_lock(svc, dirname + "/")
            file_ok = run_lock(ws, [nested])
            require_success(file_ok)
            assert_server_holds_lock(svc, nested)
            assert_invalid_unlike_success(file_ok, dirty)


def test_lock_conflict_when_path_already_locked():
    """A second workspace's create is a server conflict; one lock remains."""
    path = _rel("cf")
    with locking_api_server() as svc:
        with workspace() as first:
            _repo_on(first, svc.url)
            first_lock = run_lock(first, [path])
            require_success(first_lock)
            require_server_holds_lock(svc, path)
        with workspace() as second:
            _repo_on(second, svc.url)
            conflict = run_lock(second, [path])
            print(f"conflict lock exit={conflict.returncode}")
            assert conflict.returncode != 0, (
                "second lock of an already-locked path succeeded"
            )
            require_invalid_unlike_success(first_lock, conflict)
            held = svc.held_paths()
            assert [p for p in held if p == path] == [path], held
            require_server_holds_lock(svc, path)
            require_locking_create_conflict(svc, path)


def test_lock_commands_fail_when_endpoint_lacks_locking_support():
    """Lock, unlock, and locks fail when lock routes are absent."""
    path = _rel("nl")
    with locking_api_server() as ok_svc:
        with workspace() as ws_ok:
            _repo_on(ws_ok, ok_svc.url)
            lock_ok = run_lock(ws_ok, [path])
            require_success(lock_ok)
            list_ok = run_locks(ws_ok, [])
            require_success(list_ok)
            unlock_ok = run_unlock(ws_ok, ["--force", path])
            require_success(unlock_ok)
    with locking_api_server(lock_routes="absent") as dead:
        with workspace() as ws:
            _repo_on(ws, dead.url)
            lock_f = run_lock(ws, [path])
            unlock_f = run_unlock(ws, [path])
            list_f = run_locks(ws, [])
            print(
                f"absent lock={lock_f.returncode} unlock={unlock_f.returncode} "
                f"locks={list_f.returncode}"
            )
            assert_invalid_unlike_success(lock_ok, lock_f)
            assert_invalid_unlike_success(unlock_ok, unlock_f)
            assert_invalid_unlike_success(list_ok, list_f)


def test_lock_commands_fail_when_authentication_fails():
    """Lock, unlock, and locks fail when the locking endpoint rejects auth."""
    path = _rel("au")
    with locking_api_server() as ok_svc:
        with workspace() as ws_ok:
            _repo_on(ws_ok, ok_svc.url)
            lock_ok = run_lock(ws_ok, [path])
            require_success(lock_ok)
            list_ok = run_locks(ws_ok, [])
            require_success(list_ok)
            unlock_ok = run_unlock(ws_ok, ["--force", path])
            require_success(unlock_ok)
    with locking_api_server(lock_routes="unauthorized") as gated:
        with workspace() as ws:
            _repo_on(ws, gated.url)
            install_credential_helper(ws, f"u_{token()}", f"p_{token()}")
            lock_f = run_lock(ws, [path])
            unlock_f = run_unlock(ws, [path])
            list_f = run_locks(ws, [])
            print(
                f"auth lock={lock_f.returncode} unlock={unlock_f.returncode} "
                f"locks={list_f.returncode}"
            )
            assert_invalid_unlike_success(lock_ok, lock_f)
            assert_invalid_unlike_success(unlock_ok, unlock_f)
            assert_invalid_unlike_success(list_ok, list_f)


# ---------------------------------------------------------------------------
# F. Lockable working-tree permissions
# ---------------------------------------------------------------------------


def test_unlocked_lockable_file_is_read_only_and_writable_after_lock():
    """Unlocked lockable files are read-only; locking makes them writable."""
    with locking_api_server() as svc:
        with workspace() as ws:
            ws.init_repo()
            point_lfs_at(ws, svc.url)
            rel_a, _rel_b, ctrl, _ext = _commit_lockable_pair(ws)
            assert_file_read_only(_abs(ws, rel_a))
            assert_file_writable(_abs(ws, ctrl))
            locked = run_lock(ws, [rel_a])
            require_success(locked)
            assert_file_writable(_abs(ws, rel_a))
            assert_file_writable(_abs(ws, ctrl))
            unlocked = run_unlock(ws, [rel_a])
            require_success(unlocked)
            assert_file_read_only(_abs(ws, rel_a))
            assert_file_writable(_abs(ws, ctrl))


# ---------------------------------------------------------------------------
# G. post-* scan ranges; held locks stay writable
# ---------------------------------------------------------------------------


def test_post_commit_reapplies_read_only_on_head_changed_lockable_paths():
    """Post-commit resets modified and newly added lockable paths, not others."""
    with workspace() as ws:
        ws.init_repo()
        rel_a, rel_b, ctrl, ext = _commit_lockable_pair(ws)
        make_file_writable(_abs(ws, rel_a))
        make_file_writable(_abs(ws, rel_b))
        ws.write(rel_a, _payload(pad=2))
        _git_ok(ws, ["add", "--", rel_a])
        _git_ok(ws, ["commit", "-m", "modify A"])
        print("post-commit modify arm")
        require_file_read_only(_abs(ws, rel_a))
        require_file_writable(_abs(ws, rel_b))
        require_file_writable(_abs(ws, ctrl))
        make_file_writable(_abs(ws, rel_a))
        make_file_writable(_abs(ws, rel_b))
        rel_c = f"c_{token()}.{ext}"
        ws.write(rel_c, _payload())
        _git_ok(ws, ["add", "--", rel_c])
        _git_ok(ws, ["commit", "-m", "add C"])
        print("post-commit add arm")
        require_file_read_only(_abs(ws, rel_c))
        require_file_writable(_abs(ws, rel_a))
        require_file_writable(_abs(ws, rel_b))
        make_file_writable(_abs(ws, rel_c))
        plumbing = run_post_commit(ws, via_git=False)
        print(f"direct post-commit exit={plumbing.returncode}")
        require_success(plumbing)
        require_file_read_only(_abs(ws, rel_c))


def test_post_merge_reapplies_read_only_on_broader_lockable_set():
    """Post-merge resets lockable paths even if the merge did not touch them."""
    skip = enable_skip_smudge_environment()
    with workspace() as ws:
        ws.init_repo()
        rel_a, rel_b, ctrl, _ext = _commit_lockable_pair(ws)
        feat = f"feat_{token()}"
        _git_ok(ws, ["checkout", "-b", feat], env_updates=skip)
        make_file_writable(_abs(ws, rel_a))
        ws.write(rel_a, _payload(pad=8))
        _git_ok(ws, ["add", "--", rel_a])
        _git_ok(ws, ["commit", "-m", "feat A"])
        _git_ok(ws, ["checkout", "main"], env_updates=skip)
        make_file_writable(_abs(ws, rel_a))
        make_file_writable(_abs(ws, rel_b))
        merged = ws.git(
            ["merge", "--no-ff", "--no-edit", "-m", "merge feat", feat],
            env_updates=skip,
        )
        print(f"git merge exit={merged.returncode}")
        assert merged.returncode == 0, merged.stderr_text
        require_file_read_only(_abs(ws, rel_a))
        require_file_read_only(_abs(ws, rel_b))
        require_file_writable(_abs(ws, ctrl))
        make_file_writable(_abs(ws, rel_a))
        make_file_writable(_abs(ws, rel_b))
        plumbing = run_post_merge(ws, ["0"], via_git=False)
        print(f"direct post-merge exit={plumbing.returncode}")
        require_success(plumbing)
        require_file_read_only(_abs(ws, rel_a))
        require_file_read_only(_abs(ws, rel_b))


def test_post_checkout_file_checkout_scans_broader_lockable_set():
    """File checkout (flag 0) scans the broader lockable set."""
    skip = enable_skip_smudge_environment()
    with workspace() as ws:
        ws.init_repo()
        rel_a, rel_b, ctrl, _ext = _commit_lockable_pair(ws)
        make_file_writable(_abs(ws, rel_a))
        make_file_writable(_abs(ws, rel_b))
        checked = ws.git(["checkout", "--", rel_a, rel_b], env_updates=skip)
        print(f"git checkout -- exit={checked.returncode}")
        assert checked.returncode == 0, checked.stderr_text
        require_file_read_only(_abs(ws, rel_a))
        require_file_read_only(_abs(ws, rel_b))
        require_file_writable(_abs(ws, ctrl))
        make_file_writable(_abs(ws, rel_a))
        make_file_writable(_abs(ws, rel_b))
        head = head_oid(ws)
        plumbing = run_post_checkout(ws, [head, head, "0"], via_git=False)
        print(f"direct file post-checkout exit={plumbing.returncode}")
        require_success(plumbing)
        require_file_read_only(_abs(ws, rel_a))
        require_file_read_only(_abs(ws, rel_b))


def test_post_checkout_initial_checkout_scans_broader_lockable_set():
    """Initial checkout (zero SHA, flag 1) scans the broader lockable set."""
    with workspace() as ws:
        ws.init_repo()
        rel_a, rel_b, ctrl, _ext = _commit_lockable_pair(ws)
        make_file_writable(_abs(ws, rel_a))
        make_file_writable(_abs(ws, rel_b))
        head = head_oid(ws)
        plumbing = run_post_checkout(
            ws, [git_zero_oid(), head, "1"], via_git=False
        )
        print(f"initial post-checkout exit={plumbing.returncode}")
        require_success(plumbing)
        require_file_read_only(_abs(ws, rel_a))
        require_file_read_only(_abs(ws, rel_b))
        require_file_writable(_abs(ws, ctrl))


def test_post_checkout_ordinary_revision_change_only_scans_changed_paths():
    """Ordinary branch checkout resets only paths that changed between SHAs."""
    skip = enable_skip_smudge_environment()
    with workspace() as ws:
        ws.init_repo()
        rel_a, rel_b, ctrl, _ext = _commit_lockable_pair(ws)
        main_sha = head_oid(ws)
        feat = f"feat_{token()}"
        _git_ok(ws, ["checkout", "-b", feat], env_updates=skip)
        make_file_writable(_abs(ws, rel_a))
        ws.write(rel_a, _payload(pad=9))
        _git_ok(ws, ["add", "--", rel_a])
        _git_ok(ws, ["commit", "-m", "feat A"])
        feat_sha = head_oid(ws)
        _git_ok(ws, ["checkout", "main"], env_updates=skip)
        make_file_writable(_abs(ws, rel_a))
        make_file_writable(_abs(ws, rel_b))
        checked = ws.git(["checkout", feat], env_updates=skip)
        print(f"git checkout feat exit={checked.returncode}")
        assert checked.returncode == 0, checked.stderr_text
        require_file_read_only(_abs(ws, rel_a))
        require_file_writable(_abs(ws, rel_b))
        require_file_writable(_abs(ws, ctrl))
        _git_ok(ws, ["checkout", "main"], env_updates=skip)
        make_file_writable(_abs(ws, rel_a))
        make_file_writable(_abs(ws, rel_b))
        plumbing = run_post_checkout(
            ws, [main_sha, feat_sha, "1"], via_git=True
        )
        print(f"ordinary plumbing exit={plumbing.returncode}")
        require_success(plumbing)
        require_file_read_only(_abs(ws, rel_a))
        require_file_writable(_abs(ws, rel_b))


def test_post_hooks_leave_held_lockable_path_writable():
    """A held lockable path stays writable through post-* scans."""
    with locking_api_server() as svc:
        with workspace() as ws:
            ws.init_repo()
            point_lfs_at(ws, svc.url)
            rel_a, rel_b, _ctrl, ext = _commit_lockable_pair(ws)
            require_success(run_lock(ws, [rel_a]))
            require_file_writable(_abs(ws, rel_a))
            rel_c = f"c_{token()}.{ext}"
            ws.write(rel_c, _payload())
            ws.write(rel_a, _payload(pad=1))
            _git_ok(ws, ["add", "--", rel_a, rel_c])
            _git_ok(ws, ["commit", "-m", "held A plus C"])
            print("held post-commit")
            require_file_writable(_abs(ws, rel_a))
            require_file_read_only(_abs(ws, rel_c))
            make_file_writable(_abs(ws, rel_b))
            merge_plumb = run_post_merge(ws, ["0"])
            print(f"held post-merge exit={merge_plumb.returncode}")
            require_success(merge_plumb)
            require_file_writable(_abs(ws, rel_a))
            require_file_read_only(_abs(ws, rel_b))
            make_file_writable(_abs(ws, rel_b))
            head = head_oid(ws)
            checkout_plumb = run_post_checkout(ws, [head, head, "0"])
            print(f"held file post-checkout exit={checkout_plumb.returncode}")
            require_success(checkout_plumb)
            require_file_writable(_abs(ws, rel_a))
            require_file_read_only(_abs(ws, rel_b))


# ---------------------------------------------------------------------------
# H. Push lock verification
# ---------------------------------------------------------------------------


def test_lock_verification_enabled_rejects_foreign_lock_on_updated_path():
    """Enabled verify refuses a foreign lock on an updated path and does not PUT."""
    payload = _payload(pad=21)
    rel = _rel("vj")
    with locking_api_server(payloads=[payload]) as svc:
        with workspace() as ws_lfs:
            ws_lfs.init_repo()
            point_lfs_at(ws_lfs, svc.url)
            enable_lock_verification(ws_lfs)
            prepare_tracked_commit(ws_lfs, rel, payload)
            svc.inject_foreign_lock(rel)
            start = len(svc.records)
            rejected = ws_lfs.invoke_via_git(["push", "origin", "main"])
            print(f"lfs push reject exit={rejected.returncode}")
            assert rejected.returncode != 0, (
                "push succeeded while updating a path locked by others"
            )
            require_no_put_of(_records_since(svc, start), payload)
            require_locking_verify_received(svc)
        with workspace() as ws_git:
            _bare_origin(ws_git, svc.url)
            enable_lock_verification(ws_git)
            prepare_tracked_commit(ws_git, rel, payload)
            start = len(svc.records)
            git_push = ws_git.git(["push", "origin", "main"])
            print(f"git push reject exit={git_push.returncode}")
            assert git_push.returncode != 0, (
                "git push succeeded while updating a path locked by others"
            )
            require_no_put_of(_records_since(svc, start), payload)


def test_lock_verification_enabled_allows_push_when_current_user_holds_the_lock():
    """Enabled verify still PUTs when the current user holds the updated path."""
    payload = _payload(pad=22)
    rel = _rel("own")
    with locking_api_server(payloads=[payload]) as svc:
        with workspace() as ws:
            ws.init_repo()
            point_lfs_at(ws, svc.url)
            enable_lock_verification(ws)
            prepare_tracked_commit(ws, rel, payload)
            require_success(run_lock(ws, [rel]))
            start = len(svc.records)
            ok = ws.invoke_via_git(["push", "origin", "main"])
            print(f"own-lock push exit={ok.returncode}")
            require_success(ok)
            require_put_of(_records_since(svc, start), payload)
            require_locking_verify_received(svc)


def test_lock_verification_enabled_allows_push_when_foreign_lock_is_on_unrelated_path():
    """A foreign lock on an unrelated path does not block the PUT."""
    payload = _payload(pad=23)
    rel = _rel("upd")
    unrelated = _rel("unrel")
    with locking_api_server(payloads=[payload]) as svc:
        with workspace() as ws:
            ws.init_repo()
            point_lfs_at(ws, svc.url)
            enable_lock_verification(ws)
            prepare_tracked_commit(ws, rel, payload)
            svc.inject_foreign_lock(unrelated)
            start = len(svc.records)
            ok = ws.invoke_via_git(["push", "origin", "main"])
            print(f"unrelated-lock push exit={ok.returncode}")
            require_success(ok)
            require_put_of(_records_since(svc, start), payload)
            require_locking_verify_received(svc)


def test_lock_verification_disabled_does_not_refuse_foreign_lock():
    """Disabled verification PUTs even when a foreign lock covers the path."""
    payload = _payload(pad=24)
    rel = _rel("off")
    with locking_api_server(payloads=[payload]) as svc_on:
        with workspace() as ws_on:
            ws_on.init_repo()
            point_lfs_at(ws_on, svc_on.url)
            enable_lock_verification(ws_on)
            prepare_tracked_commit(ws_on, rel, payload)
            svc_on.inject_foreign_lock(rel)
            start = len(svc_on.records)
            rejected = ws_on.invoke_via_git(["push", "origin", "main"])
            assert rejected.returncode != 0
            require_no_put_of(_records_since(svc_on, start), payload)
    with locking_api_server(payloads=[payload]) as svc_off:
        with workspace() as ws_off:
            ws_off.init_repo()
            point_lfs_at(ws_off, svc_off.url)
            disable_lock_verification(ws_off)
            prepare_tracked_commit(ws_off, rel, payload)
            svc_off.inject_foreign_lock(rel)
            start = len(svc_off.records)
            ok = ws_off.invoke_via_git(["push", "origin", "main"])
            print(f"disabled push exit={ok.returncode}")
            require_success(ok)
            require_put_of(_records_since(svc_off, start), payload)


def test_lock_verification_enabled_refuses_foreign_lock_after_verify():
    """Enabled verify refuses a foreign-locked update after a verify exchange (FP-10)."""
    payload = _payload(pad=25)
    rel = _rel("unk")
    with locking_api_server(payloads=[payload]) as svc_on:
        with workspace() as ws_on:
            ws_on.init_repo()
            point_lfs_at(ws_on, svc_on.url)
            enable_lock_verification(ws_on)
            prepare_tracked_commit(ws_on, rel, payload)
            svc_on.inject_foreign_lock(rel)
            start = len(svc_on.records)
            rejected = ws_on.invoke_via_git(["push", "origin", "main"])
            print(f"enabled push reject exit={rejected.returncode}")
            assert rejected.returncode != 0, (
                "push succeeded while updating a path locked by others"
            )
            require_no_put_of(_records_since(svc_on, start), payload)
            require_locking_verify_received(svc_on)


def test_lock_verification_unset_writes_locksverify_advisory():
    """Unset locks-verify: push writes a stderr advisory naming the setting (FP-10).

    The Contract states the carrier: standard error, naming the
    ``lfs.<endpoint-url>.locksverify`` key (wording free). Forced-on and
    forced-off pushes write no such advisory. Success or PUT on the unset
    arm is not required.
    """
    payload = _payload(pad=26)
    rel = _rel("pr")

    def _push(svc, configure):
        with workspace() as ws:
            ws.init_repo()
            point_lfs_at(ws, svc.url)
            configure(ws)
            prepare_tracked_commit(ws, rel, payload)
            start = len(svc.records)
            verifies_before = svc.verify_count()
            result = ws.invoke_via_git(["push", "origin", "main"])
            verifies_after = svc.verify_count()
            recs = list(svc.records[start:])
            print(
                f"locksverify push exit={result.returncode} "
                f"verifies={verifies_before}->{verifies_after} "
                f"visible={caller_visible(result)!r}"
            )
            return result, recs, verifies_after > verifies_before

    with locking_api_server(payloads=[payload]) as svc:
        unk_a, _, _ = _push(svc, unset_lock_verification)
        unk_b, _, _ = _push(svc, unset_lock_verification)
        on_a, recs_oa, verified_oa = _push(svc, enable_lock_verification)
        on_b, recs_ob, verified_ob = _push(svc, enable_lock_verification)
        off_a, recs_ofa, _ = _push(svc, disable_lock_verification)
        off_b, recs_ofb, _ = _push(svc, disable_lock_verification)
        require_success(on_a)
        require_success(on_b)
        require_put_of(recs_oa, payload)
        require_put_of(recs_ob, payload)
        assert verified_oa, (
            "forced-on live baseline recorded no new verify-class exchange"
        )
        assert verified_ob, (
            "forced-on live baseline recorded no new verify-class exchange"
        )
        require_success(off_a)
        require_success(off_b)
        require_put_of(recs_ofa, payload)
        require_put_of(recs_ofb, payload)
        advisory = re.compile(r"lfs\.(?:\S+\.)?locksverify")
        for arm, result in (("unset-a", unk_a), ("unset-b", unk_b)):
            assert advisory.search(result.stderr_text), (
                f"{arm}: unset locks-verify push wrote no stderr advisory "
                f"naming the locksverify setting: {result.stderr_text!r}"
            )
        for arm, result in (
            ("on-a", on_a), ("on-b", on_b), ("off-a", off_a), ("off-b", off_b)
        ):
            assert not advisory.search(result.stderr_text), (
                f"{arm}: a configured locks-verify push still wrote the "
                f"unset-setting advisory: {result.stderr_text!r}"
            )


# ---------------------------------------------------------------------------
# I. Negative control
# ---------------------------------------------------------------------------


def test_lock_commands_fail_when_binary_removed_from_path():
    """Removing the product from PATH fails lock, unlock, locks, and post-*."""
    path = _rel("nc")
    with locking_api_server() as svc:
        with workspace() as ws_ok:
            _repo_on(ws_ok, svc.url)
            ok = run_lock(ws_ok, [path])
            print(f"present lock exit={ok.returncode}")
            require_success(ok)
            require_server_holds_lock(svc, path)
        with workspace() as ws_miss:
            _repo_on(ws_miss, svc.url)
            hidden = path_without_product_bin(ws_miss.env)
            env = {"PATH": hidden}
            head = head_oid(ws_miss)
            lock_f = run_lock(ws_miss, [path], env_updates=env)
            unlock_f = run_unlock(ws_miss, [path], env_updates=env)
            list_f = run_locks(ws_miss, [], env_updates=env)
            co_f = run_post_checkout(
                ws_miss, [head, head, "1"], env_updates=env
            )
            cm_f = run_post_commit(ws_miss, env_updates=env)
            mg_f = run_post_merge(ws_miss, ["0"], env_updates=env)
            print(
                f"absent lock={lock_f.returncode} unlock={unlock_f.returncode} "
                f"locks={list_f.returncode} post-checkout={co_f.returncode} "
                f"post-commit={cm_f.returncode} post-merge={mg_f.returncode}"
            )
            for name, failed in (
                ("lock", lock_f),
                ("unlock", unlock_f),
                ("locks", list_f),
                ("post-checkout", co_f),
                ("post-commit", cm_f),
                ("post-merge", mg_f),
            ):
                assert failed.returncode != 0, (
                    f"{name} succeeded after the product binary was removed "
                    "from PATH"
                )
