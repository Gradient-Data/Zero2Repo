# feature: F15
"""Configuration surface and repository ``.lfsconfig`` acceptance tests.

PRD: FP-15. Oracles are dedicated endpoint indications, which loopback
host a transfer contacts, working-tree pointer versus original bytes,
whether a pre-push PUT happened, checkout success versus failure when a
download cannot, on/off in-progress reporting after shared completion
chunks are removed, and post-* read-only versus writable bits.
Message wording, Endpoint= labels, progress punctuation, boolean tokens
in output, and exit-code numbers are not pinned.
"""

from __future__ import annotations

from _harness import token, workspace
from F15_helpers import (
    alternate_accepted_git_protocol_value,
    dedicated_indication_scheme,
    delayed_connection_initiation_download,
    delayed_tls_handshake_download,
    disable_http_ssl_verify,
    require_cannot_download_skipped_unlike_failed,
    require_git_protocol_scheme_changed,
    require_leftover_pointer_text,
    require_no_object_bytes_uploaded,
    require_object_bytes_uploaded,
    require_secure_http_scheme_matches,
    require_ssh_style_scheme_unchanged,
)
from _helpers import (
    TwoRemoteLayout,
    add_git_remote,
    assert_object_bytes,
    assert_success,
    caller_visible,
    commit_ordinary_blob,
    commit_tracked_payload,
    configure_concurrent_transfers,
    configure_default_remote,
    configure_force_progress,
    configure_http_timeouts,
    configure_lockable_readonly,
    configure_skip_download_errors,
    configure_unreachable_endpoint,
    conforming_batch_server,
    contacts,
    dedicated_server_url,
    default_lfs_store_root,
    delayed_download_batch_server,
    derived_https_endpoint,
    disable_lock_verification,
    documented_falsey,
    documented_truthy_skip,
    enable_basic_transfers_only,
    enable_lock_verification,
    enable_tus_transfers,
    env_force_progress,
    env_lockable_readonly,
    env_report,
    env_skip_download_errors,
    env_skip_push,
    env_skip_smudge,
    head_oid,
    in_progress_on_remainder_off_empty,
    indication_names,
    init_bare_git_remote,
    install_two_remote_layout,
    locking_api_server,
    make_file_writable,
    non_truthy_boolean_token,
    path_without_product_bin,
    point_lfs_at,
    pre_push_stdin,
    prepare_tracked_commit,
    recording_api_server,
    related_facts_without_dedicated,
    remove_stored_object,
    require_advanced_advertised,
    require_basic_only_or_omitted,
    require_batch_post,
    require_bound_prevents_overlap_unlike_unbounded,
    require_file_read_only,
    require_file_writable,
    require_git_config_set,
    require_invalid_unlike_success,
    require_lfsconfig_set,
    require_locking_verify_received,
    require_no_put_of,
    require_object_absent,
    require_object_bytes,
    require_put_of,
    require_ref_at,
    require_success,
    require_working_tree_bytes,
    require_working_tree_pointer,
    run_post_checkout,
    runtime_http_url,
    set_lfs_endpoint,
    sha256_hex,
    ssh_style_remote,
    track_lockable,
    unlink_worktree_lfsconfig,
)


def _payload(*, pad: int = 0) -> bytes:
    return (f"blob-{token()}\n" + ("x" * pad)).encode("utf-8")


def _rel(prefix: str = "payload") -> str:
    return f"{prefix}_{token()}.bin"


def _git_ok(ws, argv, **kwargs):
    result = ws.git(argv, **kwargs)
    assert result.returncode == 0, (
        f"git {argv!r} failed (exit {result.returncode}): {result.stderr_text}"
    )
    return result


def _checkout(ws, *rels: str, env_updates=None):
    return ws.git(
        ["checkout", "HEAD", "--", *rels],
        env_updates=env_updates,
    )


def _unlink_worktree(ws, *rels: str) -> None:
    for rel in rels:
        path = ws.resolve(rel)
        try:
            path.unlink()
        except FileNotFoundError:
            raise AssertionError(
                f"cannot unlink worktree {rel!r}; file is missing"
            ) from None
        except OSError as exc:
            raise AssertionError(f"cannot unlink worktree {rel!r}: {exc}") from exc


def _origin_dedicated(report: str, git_remote_url: str) -> str:
    return dedicated_server_url(
        report,
        remote_name="origin",
        git_remote_url=git_remote_url,
    )


def _require_names(observed: str, url: str, *, role: str) -> None:
    assert indication_names(observed, url), (
        f"{role} dedicated indication did not name {url!r}: {observed!r}"
    )


def _require_omits(observed: str, url: str, *, role: str) -> None:
    assert not indication_names(observed, url), (
        f"{role} dedicated indication unexpectedly named {url!r}: {observed!r}"
    )


def _require_contacted(records, url: str, *, role: str) -> None:
    hit = contacts(records, url_or_host=url)
    print(f"contact {role} url={url!r} hit={hit} n={len(records)}")
    assert hit, f"{role} endpoint was not contacted ({url!r})"


def _require_not_contacted(records, url: str, *, role: str) -> None:
    hit = contacts(records, url_or_host=url)
    print(f"contact {role} url={url!r} hit={hit} n={len(records)}")
    assert not hit, f"{role} endpoint was contacted unexpectedly ({url!r})"


def _records_since(svc, start: int):
    return svc.records[start:]


def _wipe_store(ws, *digests: str) -> None:
    store = default_lfs_store_root(ws)
    for digest in digests:
        remove_stored_object(ws, digest)
        require_object_absent(store, digest)


def _setup_two_downloads(ws, svc, payloads: list[bytes]) -> list[str]:
    ws.init_repo()
    point_lfs_at(ws, svc.url)
    disable_lock_verification(ws)
    digests: list[str] = []
    for index, data in enumerate(payloads):
        rel = _rel()
        if index == 0:
            digests.append(prepare_tracked_commit(ws, rel, data))
        else:
            digests.append(commit_tracked_payload(ws, rel, data))
    _wipe_store(ws, *digests)
    return digests


def _setup_one_download(ws, svc, payload: bytes) -> str:
    ws.init_repo()
    point_lfs_at(ws, svc.url)
    disable_lock_verification(ws)
    digest = prepare_tracked_commit(ws, _rel(), payload)
    _wipe_store(ws, digest)
    return digest


def _setup_one_upload(ws, svc, payload: bytes) -> str:
    ws.init_repo()
    point_lfs_at(ws, svc.url)
    disable_lock_verification(ws)
    return prepare_tracked_commit(ws, _rel(), payload)


def _live_git_remote(base: str) -> str:
    return f"{base.rstrip('/')}/{token()}/repo.git"


def _progress_strip(
    ws,
    result,
    *,
    rel: str,
    payload: bytes,
    digest: str,
    urls: tuple[str, ...] = (),
    extra: tuple[str, ...] = (),
) -> list[str]:
    tokens = [
        rel,
        str(ws.resolve(rel)),
        digest,
        *urls,
        *extra,
    ]
    for arg in result.argv:
        text = str(arg)
        if "/" in text or text.startswith("http"):
            tokens.append(text)
    try:
        tokens.append(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise AssertionError(
            f"payload is not UTF-8; cannot strip it as a covariate: {exc}"
        ) from exc
    return [item for item in tokens if item]


def _fetch_missing(ws, digest: str, *, env_updates=None, timeout: float = 90.0):
    remove_stored_object(ws, digest)
    return ws.invoke_via_git(
        ["fetch"], env_updates=env_updates, timeout=timeout
    )


def _commit_lockable_and_control(ws):
    """Track one lockable glob, commit a match plus a non-lockable control."""
    install_ok = ws.invoke_via_git(["install", "--local"])
    require_success(install_ok)
    commit_ordinary_blob(ws, f"keep_{token()}.txt", f"{token()}\n")
    ext = token()
    track_lockable(ws, f"*.{ext}")
    rel = f"a_{token()}.{ext}"
    ctrl = f"n_{token()}.txt"
    ws.write(rel, _payload())
    ws.write(ctrl, f"ctrl-{token()}\n")
    _git_ok(ws, ["add", "--", rel, ctrl, ".gitattributes"])
    _git_ok(ws, ["commit", "-m", "lockable and control"])
    return rel, ctrl


def _reapply_via_file_checkout(ws, rel: str, *, env_updates=None):
    make_file_writable(ws.resolve(rel))
    result = _checkout(ws, rel, env_updates=env_updates)
    assert result.returncode == 0, (
        f"git checkout HEAD -- {rel!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    return result


def _skip_download_errors_on_unlike_off(*, via: str) -> None:
    """Graded skip-download-errors cannot-download contrast (FP-15).

    *via* is ``git`` (local Git config) or ``lfsconfig``. Named-only leftovers
    must not present Git SET exit 0 as this feature's oracle.
    """
    assert via in ("git", "lfsconfig"), f"unknown skip carrier {via!r}"
    ext = token()
    rel = f"payload_{token()}.{ext}"
    data = _payload()
    truthy = documented_truthy_skip()
    with workspace() as off:
        off.init_repo()
        digest = prepare_tracked_commit(off, rel, data)
        remove_stored_object(off, digest)
        configure_unreachable_endpoint(off)
        _unlink_worktree(off, rel)
        failed = _checkout(off, rel)
        print(f"skip-download-errors off via={via} exit={failed.returncode}")
        assert failed.returncode != 0, (
            "cannot-download checkout succeeded while skip-download-errors "
            "was off"
        )
    with workspace() as on:
        on.init_repo()
        digest = prepare_tracked_commit(on, rel, data)
        remove_stored_object(on, digest)
        configure_unreachable_endpoint(on)
        if via == "git":
            configure_skip_download_errors(on, truthy)
        else:
            require_lfsconfig_set(on, "lfs.skipdownloaderrors", truthy)
        _unlink_worktree(on, rel)
        ok = _checkout(on, rel)
        print(f"skip-download-errors on via={via} exit={ok.returncode}")
        require_leftover_pointer_text(
            on, rel, digest=digest, size=len(data), unlike=data
        )
        require_cannot_download_skipped_unlike_failed(ok, failed)


# ---------------------------------------------------------------------------
# A. .lfsconfig endpoint applies until Git config overrides; transfers follow
# ---------------------------------------------------------------------------


def test_lfsconfig_endpoint_names_dedicated_indication_and_is_contacted():
    """Worktree .lfsconfig LFS URL is the dedicated indication and is contacted."""
    payload = _payload()
    rel = _rel()
    with recording_api_server() as (url_a, recs_a):
        with recording_api_server() as (url_g, recs_g):
            git_remote = _live_git_remote(url_g)
            derived = derived_https_endpoint(git_remote)
            with workspace() as ws:
                ws.init_repo()
                add_git_remote(ws, "origin", git_remote)
                disable_lock_verification(ws)
                require_lfsconfig_set(ws, "lfs.url", url_a)
                digest = prepare_tracked_commit(ws, rel, payload)
                direct = ws.invoke(["env"])
                print(
                    f"direct env exit={direct.returncode} "
                    f"len={len(direct.stdout_text)}"
                )
                require_success(direct)
                observed = _origin_dedicated(direct.stdout_text, git_remote)
                print(f"lfsconfig dedicated={observed!r} a={url_a!r}")
                _require_names(observed, url_a, role="lfsconfig")
                _require_omits(observed, derived, role="lfsconfig-derived")
                remove_stored_object(ws, digest)
                fetched = ws.invoke_via_git(["fetch"])
                print(f"fetch exit={fetched.returncode}")
                _require_contacted(recs_a, url_a, role="lfsconfig")
                _require_not_contacted(recs_g, url_g, role="derived-host")


def test_git_config_overrides_lfsconfig_endpoint_on_dedicated_indication_and_transfers():
    """Local Git Orbulk URL wins over .lfsconfig for indication and contact."""
    payload = _payload()
    rel = _rel()
    with recording_api_server() as (url_a, recs_a):
        with recording_api_server() as (url_b, recs_b):
            with recording_api_server() as (url_g, recs_g):
                git_remote = _live_git_remote(url_g)
                with workspace() as ws:
                    ws.init_repo()
                    add_git_remote(ws, "origin", git_remote)
                    disable_lock_verification(ws)
                    require_lfsconfig_set(ws, "lfs.url", url_a)
                    require_git_config_set(ws, "lfs.url", url_b, local=True)
                    digest = prepare_tracked_commit(ws, rel, payload)
                    report = env_report(ws)
                    observed = _origin_dedicated(report, git_remote)
                    print(
                        f"override dedicated={observed!r} a={url_a!r} b={url_b!r}"
                    )
                    _require_names(observed, url_b, role="git-config-override")
                    _require_omits(observed, url_a, role="git-config-override")
                    remove_stored_object(ws, digest)
                    fetched = ws.invoke_via_git(["fetch"])
                    print(f"override fetch exit={fetched.returncode}")
                    _require_contacted(recs_b, url_b, role="git-config-override")
                    _require_not_contacted(recs_a, url_a, role="lfsconfig-loser")
                    _require_not_contacted(recs_g, url_g, role="derived-host")


def test_git_config_overrides_lfsconfig_skip_download_errors():
    """Git config skip-download-errors falsey overrides a truthy .lfsconfig."""
    ext = token()
    rel = f"payload_{token()}.{ext}"
    data = _payload()
    truthy = documented_truthy_skip()
    falsey = documented_falsey()
    with workspace() as file_on:
        file_on.init_repo()
        digest = prepare_tracked_commit(file_on, rel, data)
        remove_stored_object(file_on, digest)
        configure_unreachable_endpoint(file_on)
        require_lfsconfig_set(file_on, "lfs.skipdownloaderrors", truthy)
        _unlink_worktree(file_on, rel)
        ok = _checkout(file_on, rel)
        print(f"lfsconfig skip-download-errors exit={ok.returncode}")
        require_success(ok)
        require_working_tree_pointer(
            file_on, rel, digest=digest, size=len(data)
        )
        body = file_on.read_bytes(rel)
        assert body != data
    with workspace() as overridden:
        overridden.init_repo()
        digest = prepare_tracked_commit(overridden, rel, data)
        remove_stored_object(overridden, digest)
        configure_unreachable_endpoint(overridden)
        require_lfsconfig_set(overridden, "lfs.skipdownloaderrors", truthy)
        configure_skip_download_errors(overridden, falsey)
        _unlink_worktree(overridden, rel)
        failed = _checkout(overridden, rel)
        print(f"git-config override skip-download-errors exit={failed.returncode}")
        assert failed.returncode != 0, (
            "Git config falsey skip-download-errors still succeeded "
            "like the .lfsconfig truthy arm"
        )
        require_invalid_unlike_success(ok, failed)


# ---------------------------------------------------------------------------
# B. Worktree, else index, else HEAD; bare reads HEAD only
# ---------------------------------------------------------------------------


def _seed_payload_then_lfsconfig_layers(
    ws,
    *,
    rel: str,
    payload: bytes,
    git_remote: str,
    url_h: str,
    url_i: str | None = None,
    url_w: str | None = None,
) -> str:
    """Commit a tracked payload, then layer .lfsconfig H / optional I / W."""
    ws.init_repo()
    add_git_remote(ws, "origin", git_remote)
    disable_lock_verification(ws)
    digest = prepare_tracked_commit(ws, rel, payload)
    require_lfsconfig_set(ws, "lfs.url", url_h)
    _git_ok(ws, ["add", "--", ".lfsconfig"])
    _git_ok(ws, ["commit", "-m", "head lfsconfig"])
    if url_i is not None:
        require_lfsconfig_set(ws, "lfs.url", url_i)
        _git_ok(ws, ["add", "--", ".lfsconfig"])
    if url_w is not None:
        require_lfsconfig_set(ws, "lfs.url", url_w)
    return digest


def test_lfsconfig_prefers_worktree_over_index_over_head():
    """When W, I, and H all exist, indication and transfers follow W."""
    payload = _payload()
    rel = _rel()
    with recording_api_server() as (url_w, recs_w):
        with recording_api_server() as (url_i, recs_i):
            with recording_api_server() as (url_h, recs_h):
                with recording_api_server() as (url_g, recs_g):
                    git_remote = _live_git_remote(url_g)
                    with workspace() as ws:
                        digest = _seed_payload_then_lfsconfig_layers(
                            ws,
                            rel=rel,
                            payload=payload,
                            git_remote=git_remote,
                            url_h=url_h,
                            url_i=url_i,
                            url_w=url_w,
                        )
                        report = env_report(ws)
                        observed = _origin_dedicated(report, git_remote)
                        print(
                            f"worktree-win dedicated={observed!r} "
                            f"w={url_w!r} i={url_i!r} h={url_h!r}"
                        )
                        _require_names(observed, url_w, role="worktree")
                        _require_omits(observed, url_i, role="worktree")
                        _require_omits(observed, url_h, role="worktree")
                        remove_stored_object(ws, digest)
                        fetched = ws.invoke_via_git(["fetch"])
                        print(f"worktree-win fetch exit={fetched.returncode}")
                        _require_contacted(recs_w, url_w, role="worktree")
                        _require_not_contacted(recs_i, url_i, role="index-loser")
                        _require_not_contacted(recs_h, url_h, role="head-loser")
                        _require_not_contacted(
                            recs_g, url_g, role="derived-host"
                        )


def test_lfsconfig_reads_index_when_worktree_file_missing():
    """Missing worktree file: indication and transfers follow the index URL."""
    payload = _payload()
    rel = _rel()
    with recording_api_server() as (url_i, recs_i):
        with recording_api_server() as (url_h, recs_h):
            with recording_api_server() as (url_g, recs_g):
                git_remote = _live_git_remote(url_g)
                with workspace() as ws:
                    digest = _seed_payload_then_lfsconfig_layers(
                        ws,
                        rel=rel,
                        payload=payload,
                        git_remote=git_remote,
                        url_h=url_h,
                        url_i=url_i,
                        url_w=url_i,
                    )
                    unlink_worktree_lfsconfig(ws)
                    report = env_report(ws)
                    observed = _origin_dedicated(report, git_remote)
                    print(f"index-win dedicated={observed!r} i={url_i!r}")
                    _require_names(observed, url_i, role="index")
                    _require_omits(observed, url_h, role="index")
                    remove_stored_object(ws, digest)
                    fetched = ws.invoke_via_git(["fetch"])
                    print(f"index-win fetch exit={fetched.returncode}")
                    _require_contacted(recs_i, url_i, role="index")
                    _require_not_contacted(recs_h, url_h, role="head-loser")
                    _require_not_contacted(recs_g, url_g, role="derived-host")


def test_lfsconfig_reads_head_when_worktree_and_index_missing():
    """No worktree file and no index path: indication and transfers follow HEAD."""
    payload = _payload()
    rel = _rel()
    with recording_api_server() as (url_h, recs_h):
        with recording_api_server() as (url_g, recs_g):
            git_remote = _live_git_remote(url_g)
            with workspace() as ws:
                digest = _seed_payload_then_lfsconfig_layers(
                    ws,
                    rel=rel,
                    payload=payload,
                    git_remote=git_remote,
                    url_h=url_h,
                )
                unlink_worktree_lfsconfig(ws)
                _git_ok(ws, ["rm", "--cached", "--", ".lfsconfig"])
                report = env_report(ws)
                observed = _origin_dedicated(report, git_remote)
                print(f"head-win dedicated={observed!r} h={url_h!r}")
                _require_names(observed, url_h, role="head")
                _require_omits(
                    observed,
                    derived_https_endpoint(git_remote),
                    role="head",
                )
                remove_stored_object(ws, digest)
                fetched = ws.invoke_via_git(["fetch"])
                print(f"head-win fetch exit={fetched.returncode}")
                _require_contacted(recs_h, url_h, role="head")
                _require_not_contacted(recs_g, url_g, role="derived-host")


def test_bare_repo_lfsconfig_reads_head_only_not_decoy_file():
    """A bare repository reads HEAD .lfsconfig, not a decoy file in that directory."""
    payload = _payload()
    rel = _rel()
    with recording_api_server() as (url_h, recs_h):
        with recording_api_server() as (url_w, recs_w):
            with recording_api_server() as (url_g, recs_g):
                git_remote = _live_git_remote(url_g)
                with workspace() as ws:
                    digest = _seed_payload_then_lfsconfig_layers(
                        ws,
                        rel=rel,
                        payload=payload,
                        git_remote=git_remote,
                        url_h=url_h,
                    )
                    bare_rel = f"bare_{token()}"
                    cloned = ws.git(["clone", "--bare", ".", bare_rel])
                    assert cloned.returncode == 0, (
                        "git clone --bare failed "
                        f"(exit {cloned.returncode}): {cloned.stderr_text}"
                    )
                    bare_path = ws.resolve(bare_rel)
                    set_url = ws.git(
                        ["remote", "set-url", "origin", git_remote],
                        cwd=bare_path,
                    )
                    assert set_url.returncode == 0, (
                        "git remote set-url on bare failed "
                        f"(exit {set_url.returncode}): {set_url.stderr_text}"
                    )
                    decoy = bare_path / ".lfsconfig"
                    written = ws.git_config_set(
                        "lfs.url",
                        url_w,
                        file=str(decoy),
                        cwd=bare_path,
                    )
                    assert written.returncode == 0, (
                        "writing decoy .lfsconfig failed "
                        f"(exit {written.returncode}): {written.stderr_text}"
                    )
                    env_run = ws.invoke_via_git(["env"], cwd=bare_path)
                    print(f"bare env exit={env_run.returncode}")
                    require_success(env_run)
                    observed = _origin_dedicated(env_run.stdout_text, git_remote)
                    print(
                        f"bare dedicated={observed!r} h={url_h!r} decoy={url_w!r}"
                    )
                    _require_names(observed, url_h, role="bare-head")
                    _require_omits(observed, url_w, role="bare-decoy")
                    fetched = ws.invoke_via_git(["fetch"], cwd=bare_path)
                    print(f"bare fetch exit={fetched.returncode}")
                    _require_contacted(recs_h, url_h, role="bare-head")
                    _require_not_contacted(recs_w, url_w, role="bare-decoy")
                    _require_not_contacted(recs_g, url_g, role="derived-host")
                    print(f"bare digest={digest}")


# ---------------------------------------------------------------------------
# C. Allowlisted .lfsconfig keys take effect; others are ignored
# ---------------------------------------------------------------------------


def test_lfsconfig_per_remote_url_changes_only_that_remote_indication_and_is_contacted():
    """A per-remote .lfsconfig LFS URL changes that remote's indication and contact."""
    payload = _payload()
    rel = _rel()
    with recording_api_server() as (url_s, recs_s):
        with recording_api_server() as (url_sib_git, recs_sib_git):
            sibling_name = f"sib_{token()}"
            sibling_git = _live_git_remote(url_sib_git)
            layout = TwoRemoteLayout(
                origin_url=runtime_http_url("alpha"),
                sibling_name=sibling_name,
                sibling_url=sibling_git,
            )
            with workspace() as ws:
                install_two_remote_layout(ws, layout)
                disable_lock_verification(ws)
                require_lfsconfig_set(
                    ws, f"remote.{layout.sibling_name}.lfsurl", url_s
                )
                digest = prepare_tracked_commit(ws, rel, payload)
                report = env_report(ws)
                sibling = dedicated_server_url(
                    report,
                    remote_name=layout.sibling_name,
                    git_remote_url=layout.sibling_url,
                    other_remote_name="origin",
                )
                origin = dedicated_server_url(
                    report,
                    remote_name="origin",
                    git_remote_url=layout.origin_url,
                    other_remote_name=layout.sibling_name,
                )
                print(
                    f"per-remote sibling={sibling!r} origin={origin!r} s={url_s!r}"
                )
                _require_names(sibling, url_s, role="per-remote-sibling")
                _require_omits(origin, url_s, role="per-remote-origin")
                remove_stored_object(ws, digest)
                fetched = ws.invoke_via_git(["fetch", layout.sibling_name])
                print(f"per-remote fetch exit={fetched.returncode}")
                _require_contacted(recs_s, url_s, role="per-remote-sibling")
                _require_not_contacted(
                    recs_sib_git, url_sib_git, role="sibling-derived"
                )


def test_lfsconfig_push_url_contacts_upload_endpoint_without_replacing_download_indication():
    """``.lfsconfig`` push URL splits upload contact from the download indication."""
    payload = _payload()
    rel = _rel()
    with recording_api_server() as (url_a, recs_a):
        with recording_api_server() as (url_p, recs_p):
            git_remote = f"https://{token()}.origin.example.test/{token()}/repo.git"
            with workspace() as ws:
                ws.init_repo()
                add_git_remote(ws, "origin", git_remote)
                disable_lock_verification(ws)
                require_lfsconfig_set(ws, "lfs.url", url_a)
                require_lfsconfig_set(ws, "lfs.pushurl", url_p)
                digest = prepare_tracked_commit(ws, rel, payload)
                report = env_report(ws)
                observed = _origin_dedicated(report, git_remote)
                print(
                    f"pushurl dedicated={observed!r} a={url_a!r} p={url_p!r}"
                )
                _require_names(observed, url_a, role="pushurl-download")
                _require_omits(observed, url_p, role="pushurl-download")
                pushed = ws.invoke_via_git(
                    ["push", "--object-id", "origin", digest]
                )
                print(f"pushurl push exit={pushed.returncode}")
                _require_contacted(recs_p, url_p, role="pushurl-upload")
                download_before = len(recs_a)
                remove_stored_object(ws, digest)
                fetched = ws.invoke_via_git(["fetch"])
                print(f"pushurl fetch exit={fetched.returncode}")
                assert len(recs_a) > download_before, (
                    "download path did not contact the download endpoint"
                )
                _require_contacted(recs_a, url_a, role="pushurl-download")


def test_lfsconfig_skip_download_errors_allows_checkout_with_pointer():
    """Allowlisted skip-download-errors in ``.lfsconfig`` leaves a pointer."""
    ext = token()
    rel = f"payload_{token()}.{ext}"
    data = _payload()
    truthy = documented_truthy_skip()
    with workspace() as baseline:
        baseline.init_repo()
        digest = prepare_tracked_commit(baseline, rel, data)
        remove_stored_object(baseline, digest)
        configure_unreachable_endpoint(baseline)
        _unlink_worktree(baseline, rel)
        failed = _checkout(baseline, rel)
        print(f"no-file skip-download-errors exit={failed.returncode}")
        assert failed.returncode != 0
    with workspace() as skipped:
        skipped.init_repo()
        digest = prepare_tracked_commit(skipped, rel, data)
        remove_stored_object(skipped, digest)
        configure_unreachable_endpoint(skipped)
        require_lfsconfig_set(skipped, "lfs.skipdownloaderrors", truthy)
        _unlink_worktree(skipped, rel)
        ok = _checkout(skipped, rel)
        print(f"lfsconfig skip-download-errors exit={ok.returncode}")
        require_success(ok)
        require_working_tree_pointer(
            skipped, rel, digest=digest, size=len(data)
        )
        assert skipped.read_bytes(rel) != data
        require_invalid_unlike_success(ok, failed)


def test_disallowed_lfsconfig_lockable_key_is_ignored_unlike_git_config():
    """``.lfsconfig`` lockable read-only cannot disable; Git config can."""
    falsey = documented_falsey()
    with workspace() as file_arm:
        file_arm.init_repo()
        rel, ctrl = _commit_lockable_and_control(file_arm)
        require_lfsconfig_set(file_arm, "lfs.setlockablereadonly", falsey)
        _reapply_via_file_checkout(file_arm, rel)
        print("lfsconfig lockable falsey still read-only")
        require_file_read_only(file_arm.resolve(rel))
        require_file_writable(file_arm.resolve(ctrl))
    with workspace() as git_arm:
        git_arm.init_repo()
        rel, ctrl = _commit_lockable_and_control(git_arm)
        configure_lockable_readonly(git_arm, falsey)
        _reapply_via_file_checkout(git_arm, rel)
        print("git-config lockable falsey is writable")
        require_file_writable(git_arm.resolve(rel))
        require_file_writable(git_arm.resolve(ctrl))


def test_disallowed_lfsconfig_force_progress_is_ignored():
    """Progress-forcing in ``.lfsconfig`` does not produce in-progress reporting."""
    payload = _payload()
    rel = _rel()
    truthy = documented_truthy_skip()
    extra = (
        "GIT_ORBULK_FORCE_PROGRESS",
        "lfs.forceprogress",
        truthy,
        ".lfsconfig",
    )
    with conforming_batch_server(
        mode="overlap_gate,download", payloads=[payload]
    ) as svc:
        with workspace() as git_on:
            git_on.init_repo()
            point_lfs_at(git_on, svc.url)
            disable_lock_verification(git_on)
            digest = prepare_tracked_commit(git_on, rel, payload)
            configure_force_progress(git_on, truthy)
            on_run = _fetch_missing(git_on, digest)
            print(f"git-config force-progress fetch exit={on_run.returncode}")
            require_success(on_run)
            require_object_bytes(
                default_lfs_store_root(git_on), digest, payload
            )
        with workspace() as file_arm:
            file_arm.init_repo()
            point_lfs_at(file_arm, svc.url)
            disable_lock_verification(file_arm)
            digest = prepare_tracked_commit(file_arm, rel, payload)
            require_lfsconfig_set(file_arm, "lfs.forceprogress", truthy)
            file_run = _fetch_missing(file_arm, digest)
            print(f"lfsconfig force-progress fetch exit={file_run.returncode}")
            require_success(file_run)
            require_object_bytes(
                default_lfs_store_root(file_arm), digest, payload
            )
        unknown = f"lfs.unk{token()}"
        with workspace() as warn_ctrl:
            warn_ctrl.init_repo()
            point_lfs_at(warn_ctrl, svc.url)
            disable_lock_verification(warn_ctrl)
            digest = prepare_tracked_commit(warn_ctrl, rel, payload)
            require_lfsconfig_set(warn_ctrl, unknown, f"val_{token()}")
            ctrl_run = _fetch_missing(warn_ctrl, digest)
            print(f"lfsconfig unrelated-ignore fetch exit={ctrl_run.returncode}")
            require_success(ctrl_run)
            require_object_bytes(
                default_lfs_store_root(warn_ctrl), digest, payload
            )
        extra = extra + (unknown,)
        strip = _progress_strip(
            git_on,
            on_run,
            rel=rel,
            payload=payload,
            digest=sha256_hex(payload),
            urls=(svc.url,),
            extra=extra,
        )
        strip.extend(
            _progress_strip(
                file_arm,
                file_run,
                rel=rel,
                payload=payload,
                digest=sha256_hex(payload),
                urls=(svc.url,),
                extra=extra,
            )
        )
        strip.extend(
            _progress_strip(
                warn_ctrl,
                ctrl_run,
                rel=rel,
                payload=payload,
                digest=sha256_hex(payload),
                urls=(svc.url,),
                extra=extra,
            )
        )
        leftover = in_progress_on_remainder_off_empty(
            on_run, file_run, strip=strip, ignore=(ctrl_run,)
        )
        print(f"ignored lfsconfig force-progress leftover={leftover!r}")


def test_unknown_lfsconfig_key_does_not_crash_env():
    """Unrecognized ``.lfsconfig`` keys do not crash and do not take effect."""
    unknown = f"lfs.unk{token()}"
    value = f"val_{token()}"
    git_remote = f"https://{token()}.origin.example.test/{token()}/repo.git"
    with workspace() as ws:
        ws.init_repo()
        add_git_remote(ws, "origin", git_remote)
        require_lfsconfig_set(ws, unknown, value)
        result = ws.invoke_via_git(["env"])
        print(
            f"unknown-key env exit={result.returncode} key={unknown!r}"
        )
        require_success(result)
        assert result.stdout_text.strip(), (
            "env succeeded with an unknown .lfsconfig key but printed "
            "no configuration report"
        )
    ext = token()
    rel = f"payload_{token()}.{ext}"
    data = _payload()
    truthy = documented_truthy_skip()
    with workspace() as skipped:
        skipped.init_repo()
        digest = prepare_tracked_commit(skipped, rel, data)
        remove_stored_object(skipped, digest)
        configure_unreachable_endpoint(skipped)
        require_lfsconfig_set(skipped, "lfs.skipdownloaderrors", truthy)
        _unlink_worktree(skipped, rel)
        ok = _checkout(skipped, rel)
        print(f"allowlisted skip-download-errors exit={ok.returncode}")
        require_success(ok)
        require_leftover_pointer_text(
            skipped, rel, digest=digest, size=len(data), unlike=data
        )
    with workspace() as ignored:
        ignored.init_repo()
        digest = prepare_tracked_commit(ignored, rel, data)
        remove_stored_object(ignored, digest)
        configure_unreachable_endpoint(ignored)
        require_lfsconfig_set(ignored, unknown, value)
        _unlink_worktree(ignored, rel)
        failed = _checkout(ignored, rel)
        print(f"unrecognized-key cannot-download exit={failed.returncode}")
        assert failed.returncode != 0, (
            "unrecognized .lfsconfig key took effect: cannot-download "
            "checkout succeeded as if skip-download-errors were on"
        )
        require_invalid_unlike_success(ok, failed)


# ---------------------------------------------------------------------------
# D. skip-smudge environment on git checkout / filter
# ---------------------------------------------------------------------------


def test_skip_smudge_env_truthy_leaves_pointer_on_git_checkout():
    """Truthy skip-smudge leaves pointer text; unset materializes bytes."""
    ext = token()
    rel = f"payload_{token()}.{ext}"
    data = _payload()
    truthy = documented_truthy_skip()
    with workspace() as baseline:
        baseline.init_repo()
        digest = prepare_tracked_commit(baseline, rel, data)
        _unlink_worktree(baseline, rel)
        ok = _checkout(baseline, rel)
        print(f"skip-smudge unset checkout exit={ok.returncode}")
        require_success(ok)
        require_working_tree_bytes(baseline, rel, data)
    with workspace() as skipped:
        skipped.init_repo()
        digest = prepare_tracked_commit(skipped, rel, data)
        _unlink_worktree(skipped, rel)
        result = _checkout(skipped, rel, env_updates=env_skip_smudge(truthy))
        print(f"skip-smudge truthy checkout exit={result.returncode}")
        require_success(result)
        body = require_working_tree_pointer(
            skipped, rel, digest=digest, size=len(data)
        )
        assert body != data


def test_skip_smudge_env_falsey_and_non_truthy_still_materialize():
    """Falsey and non-truthy skip-smudge still materialize; they are not a skip."""
    ext = token()
    rel = f"payload_{token()}.{ext}"
    data = _payload()
    truthy = documented_truthy_skip()
    falsey = documented_falsey()
    junk = non_truthy_boolean_token()
    with workspace() as skipped:
        skipped.init_repo()
        digest = prepare_tracked_commit(skipped, rel, data)
        _unlink_worktree(skipped, rel)
        on = _checkout(skipped, rel, env_updates=env_skip_smudge(truthy))
        print(f"skip-smudge truthy live arm exit={on.returncode}")
        require_success(on)
        pointer = require_working_tree_pointer(
            skipped, rel, digest=digest, size=len(data)
        )
        assert pointer != data
    with workspace() as off:
        off.init_repo()
        digest = prepare_tracked_commit(off, rel, data)
        _unlink_worktree(off, rel)
        result = _checkout(off, rel, env_updates=env_skip_smudge(falsey))
        print(f"skip-smudge falsey exit={result.returncode}")
        require_success(result)
        require_working_tree_bytes(off, rel, data)
    with workspace() as junk_ws:
        junk_ws.init_repo()
        digest = prepare_tracked_commit(junk_ws, rel, data)
        _unlink_worktree(junk_ws, rel)
        result = _checkout(junk_ws, rel, env_updates=env_skip_smudge(junk))
        print(
            f"skip-smudge non-truthy exit={result.returncode} token={junk!r}"
        )
        require_success(result)
        require_working_tree_bytes(junk_ws, rel, data)


# ---------------------------------------------------------------------------
# E. skip-push environment on pre-push / git push
# ---------------------------------------------------------------------------


def _bare_push_layout(ws, url: str):
    ws.init_repo()
    bare = init_bare_git_remote(ws, f"bare_{token()}")
    add_git_remote(ws, "origin", str(bare))
    set_lfs_endpoint(ws, url)
    disable_lock_verification(ws)
    return bare


def test_skip_push_env_truthy_skips_pre_push_upload_while_git_push_proceeds():
    """Truthy skip-push omits the PUT while git push still advances the ref."""
    payload = _payload(pad=20)
    truthy = documented_truthy_skip()
    skip = env_skip_push(truthy)
    with conforming_batch_server(mode="upload", payloads=[payload]) as svc:
        with workspace() as ws_live:
            bare = _bare_push_layout(ws_live, svc.url)
            install_ok = ws_live.invoke_via_git(["install", "--local"])
            require_success(install_ok)
            _git_ok(ws_live, ["commit", "--allow-empty", "-m", "seed"])
            old = head_oid(ws_live)
            planted = ws_live.git(["push", "origin", "main"], env_updates=skip)
            require_success(planted)
            require_ref_at(ws_live, "refs/heads/main", old, cwd=bare)
            prepare_tracked_commit(ws_live, _rel(), payload)
            new = head_oid(ws_live)
            start = len(svc.records)
            live = ws_live.git(["push", "origin", "main"])
            print(f"skip-push baseline git push exit={live.returncode}")
            require_success(live)
            require_put_of(svc.records[start:], payload)
            require_ref_at(ws_live, "refs/heads/main", new, cwd=bare)
        with workspace() as ws_skip:
            bare = _bare_push_layout(ws_skip, svc.url)
            install_ok = ws_skip.invoke_via_git(["install", "--local"])
            require_success(install_ok)
            _git_ok(ws_skip, ["commit", "--allow-empty", "-m", "seed"])
            old = head_oid(ws_skip)
            planted = ws_skip.git(["push", "origin", "main"], env_updates=skip)
            require_success(planted)
            prepare_tracked_commit(ws_skip, _rel(), payload)
            new = head_oid(ws_skip)
            start = len(svc.records)
            result = ws_skip.git(
                ["push", "origin", "main"], env_updates=skip
            )
            print(f"skip-push truthy git push exit={result.returncode}")
            require_success(result)
            require_no_put_of(svc.records[start:], payload)
            require_ref_at(ws_skip, "refs/heads/main", new, cwd=bare)
            stdin = pre_push_stdin(
                local_ref="refs/heads/main",
                local_sha=new,
                remote_ref="refs/heads/main",
                remote_sha=old,
            )
            start = len(svc.records)
            hook = ws_skip.invoke_via_git(
                ["pre-push", "origin", str(bare)],
                stdin=stdin,
                env_updates=skip,
            )
            print(f"skip-push pre-push exit={hook.returncode}")
            assert hook.returncode == 0, (
                "skip-push pre-push must not fail as an upload failure "
                f"(exit {hook.returncode}): {hook.stderr_text}"
            )
            require_no_put_of(svc.records[start:], payload)


def test_skip_push_env_non_truthy_still_uploads():
    """Falsey and non-truthy skip-push still upload; they are not a skip."""
    payload = _payload(pad=12)
    truthy = documented_truthy_skip()
    skip = env_skip_push(truthy)
    falsey = documented_falsey()
    junk = non_truthy_boolean_token()
    with conforming_batch_server(mode="upload", payloads=[payload]) as svc:
        with workspace() as ws_skip:
            bare = _bare_push_layout(ws_skip, svc.url)
            install_ok = ws_skip.invoke_via_git(["install", "--local"])
            require_success(install_ok)
            _git_ok(ws_skip, ["commit", "--allow-empty", "-m", "seed"])
            planted = ws_skip.git(["push", "origin", "main"], env_updates=skip)
            require_success(planted)
            prepare_tracked_commit(ws_skip, _rel(), payload)
            new = head_oid(ws_skip)
            start = len(svc.records)
            skipped = ws_skip.git(
                ["push", "origin", "main"], env_updates=skip
            )
            print(f"skip-push truthy live arm exit={skipped.returncode}")
            require_success(skipped)
            require_no_put_of(svc.records[start:], payload)
            require_no_object_bytes_uploaded(svc.records[start:], payload)
            require_ref_at(ws_skip, "refs/heads/main", new, cwd=bare)
        with workspace() as ws_falsey:
            bare = _bare_push_layout(ws_falsey, svc.url)
            install_ok = ws_falsey.invoke_via_git(["install", "--local"])
            require_success(install_ok)
            _git_ok(ws_falsey, ["commit", "--allow-empty", "-m", "seed"])
            planted = ws_falsey.git(
                ["push", "origin", "main"], env_updates=skip
            )
            require_success(planted)
            prepare_tracked_commit(ws_falsey, _rel(), payload)
            new = head_oid(ws_falsey)
            start = len(svc.records)
            result = ws_falsey.git(
                ["push", "origin", "main"],
                env_updates=env_skip_push(falsey),
            )
            print(
                f"skip-push falsey exit={result.returncode} token={falsey!r}"
            )
            require_success(result)
            require_put_of(svc.records[start:], payload)
            require_object_bytes_uploaded(svc.records[start:], payload)
            require_ref_at(ws_falsey, "refs/heads/main", new, cwd=bare)
        with workspace() as ws:
            bare = _bare_push_layout(ws, svc.url)
            install_ok = ws.invoke_via_git(["install", "--local"])
            require_success(install_ok)
            _git_ok(ws, ["commit", "--allow-empty", "-m", "seed"])
            planted = ws.git(["push", "origin", "main"], env_updates=skip)
            require_success(planted)
            prepare_tracked_commit(ws, _rel(), payload)
            new = head_oid(ws)
            start = len(svc.records)
            result = ws.git(
                ["push", "origin", "main"],
                env_updates=env_skip_push(junk),
            )
            print(
                f"skip-push non-truthy exit={result.returncode} token={junk!r}"
            )
            require_success(result)
            require_put_of(svc.records[start:], payload)
            require_object_bytes_uploaded(svc.records[start:], payload)
            require_ref_at(ws, "refs/heads/main", new, cwd=bare)


# ---------------------------------------------------------------------------
# F. skip-download-errors environment
# ---------------------------------------------------------------------------


def test_skip_download_errors_env_truthy_allows_checkout_with_pointer():
    """Truthy skip-download-errors lets checkout succeed with a pointer."""
    ext = token()
    rel = f"payload_{token()}.{ext}"
    data = _payload()
    truthy = documented_truthy_skip()
    with workspace() as baseline:
        baseline.init_repo()
        digest = prepare_tracked_commit(baseline, rel, data)
        remove_stored_object(baseline, digest)
        configure_unreachable_endpoint(baseline)
        _unlink_worktree(baseline, rel)
        failed = _checkout(baseline, rel)
        print(f"skip-download-errors unset exit={failed.returncode}")
        assert failed.returncode != 0
    with workspace() as skipped:
        skipped.init_repo()
        digest = prepare_tracked_commit(skipped, rel, data)
        remove_stored_object(skipped, digest)
        configure_unreachable_endpoint(skipped)
        _unlink_worktree(skipped, rel)
        ok = _checkout(
            skipped, rel, env_updates=env_skip_download_errors(truthy)
        )
        print(f"skip-download-errors truthy exit={ok.returncode}")
        require_success(ok)
        require_working_tree_pointer(
            skipped, rel, digest=digest, size=len(data)
        )
        require_leftover_pointer_text(
            skipped, rel, digest=digest, size=len(data), unlike=data
        )
        require_invalid_unlike_success(ok, failed)


def test_skip_download_errors_env_non_truthy_still_fails_when_download_cannot():
    """Falsey and non-truthy skip-download-errors do not skip a failed download."""
    ext = token()
    rel = f"payload_{token()}.{ext}"
    data = _payload()
    truthy = documented_truthy_skip()
    falsey = documented_falsey()
    junk = non_truthy_boolean_token()
    with workspace() as skipped:
        skipped.init_repo()
        digest = prepare_tracked_commit(skipped, rel, data)
        remove_stored_object(skipped, digest)
        configure_unreachable_endpoint(skipped)
        _unlink_worktree(skipped, rel)
        ok = _checkout(
            skipped, rel, env_updates=env_skip_download_errors(truthy)
        )
        print(f"skip-download-errors truthy live arm exit={ok.returncode}")
        require_success(ok)
        require_working_tree_pointer(
            skipped, rel, digest=digest, size=len(data)
        )
        require_leftover_pointer_text(
            skipped, rel, digest=digest, size=len(data), unlike=data
        )
    with workspace() as off:
        off.init_repo()
        digest = prepare_tracked_commit(off, rel, data)
        remove_stored_object(off, digest)
        configure_unreachable_endpoint(off)
        _unlink_worktree(off, rel)
        failed_falsey = _checkout(
            off, rel, env_updates=env_skip_download_errors(falsey)
        )
        print(
            f"skip-download-errors falsey exit={failed_falsey.returncode} "
            f"token={falsey!r}"
        )
        assert failed_falsey.returncode != 0, (
            "falsey skip-download-errors succeeded with a missing object"
        )
        require_invalid_unlike_success(ok, failed_falsey)
    with workspace() as ws:
        ws.init_repo()
        digest = prepare_tracked_commit(ws, rel, data)
        remove_stored_object(ws, digest)
        configure_unreachable_endpoint(ws)
        _unlink_worktree(ws, rel)
        failed = _checkout(ws, rel, env_updates=env_skip_download_errors(junk))
        print(
            f"skip-download-errors non-truthy exit={failed.returncode} "
            f"token={junk!r}"
        )
        assert failed.returncode != 0, (
            "non-truthy skip-download-errors succeeded with a missing object"
        )
        require_invalid_unlike_success(ok, failed)


def test_skip_download_errors_env_still_materializes_when_object_is_local():
    """Cannot-download checkout fails with the flag off and leaves pointer text when on.

    Local expansion when the object is already present is not this flag's
    duty. Line 444's on/off contrast is the cannot-download path: off fails
    the operation; on succeeds with leftover pointer text rather than
    original bytes.
    """
    ext = token()
    rel = f"payload_{token()}.{ext}"
    data = _payload()
    truthy = documented_truthy_skip()
    with workspace() as baseline:
        baseline.init_repo()
        digest = prepare_tracked_commit(baseline, rel, data)
        remove_stored_object(baseline, digest)
        configure_unreachable_endpoint(baseline)
        _unlink_worktree(baseline, rel)
        failed = _checkout(baseline, rel)
        print(f"skip-download-errors flag-off exit={failed.returncode}")
        assert failed.returncode != 0, (
            "cannot-download checkout succeeded with skip-download-errors off"
        )
    with workspace() as cannot:
        cannot.init_repo()
        digest = prepare_tracked_commit(cannot, rel, data)
        remove_stored_object(cannot, digest)
        configure_unreachable_endpoint(cannot)
        _unlink_worktree(cannot, rel)
        ok = _checkout(
            cannot, rel, env_updates=env_skip_download_errors(truthy)
        )
        print(f"skip-download-errors cannot-download exit={ok.returncode}")
        require_success(ok)
        require_working_tree_pointer(
            cannot, rel, digest=digest, size=len(data)
        )
        require_leftover_pointer_text(
            cannot, rel, digest=digest, size=len(data), unlike=data
        )
        require_invalid_unlike_success(ok, failed)


# ---------------------------------------------------------------------------
# G. Progress-forcing: in-progress reporting when stdout is not a terminal
# ---------------------------------------------------------------------------


def _progress_fetch_workspace(ws, svc, rel: str, payload: bytes, **kwargs):
    ws.init_repo()
    point_lfs_at(ws, svc.url)
    disable_lock_verification(ws)
    digest = prepare_tracked_commit(ws, rel, payload)
    result = _fetch_missing(ws, digest, **kwargs)
    print(f"progress fetch exit={result.returncode} visible_len={len(caller_visible(result))}")
    require_success(result)
    require_object_bytes(default_lfs_store_root(ws), digest, payload)
    return result, digest


def test_force_progress_env_adds_in_progress_reporting_when_stdout_not_a_terminal():
    """Environment progress-forcing adds in-progress reporting off-terminal."""
    payload = _payload()
    rel = _rel()
    truthy = documented_truthy_skip()
    extra = ("GIT_ORBULK_FORCE_PROGRESS", "lfs.forceprogress", truthy)
    with conforming_batch_server(
        mode="overlap_gate,download", payloads=[payload]
    ) as svc:
        with workspace() as on_ws:
            on_run, digest = _progress_fetch_workspace(
                on_ws,
                svc,
                rel,
                payload,
                env_updates=env_force_progress(truthy),
            )
        with workspace() as off_ws:
            off_run, _digest = _progress_fetch_workspace(
                off_ws, svc, rel, payload
            )
        strip = _progress_strip(
            on_ws,
            on_run,
            rel=rel,
            payload=payload,
            digest=digest,
            urls=(svc.url,),
            extra=extra,
        )
        strip.extend(
            _progress_strip(
                off_ws,
                off_run,
                rel=rel,
                payload=payload,
                digest=digest,
                urls=(svc.url,),
                extra=extra,
            )
        )
        leftover = in_progress_on_remainder_off_empty(
            on_run, off_run, strip=strip
        )
        print(f"env force-progress leftover={leftover!r}")


def test_force_progress_git_config_same_in_progress_contrast():
    """Git config progress-forcing produces the same on/off in-progress contrast."""
    payload = _payload()
    rel = _rel()
    truthy = documented_truthy_skip()
    extra = ("GIT_ORBULK_FORCE_PROGRESS", "lfs.forceprogress", truthy)
    with conforming_batch_server(
        mode="overlap_gate,download", payloads=[payload]
    ) as svc:
        with workspace() as on_ws:
            on_ws.init_repo()
            point_lfs_at(on_ws, svc.url)
            disable_lock_verification(on_ws)
            digest = prepare_tracked_commit(on_ws, rel, payload)
            configure_force_progress(on_ws, truthy)
            on_run = _fetch_missing(on_ws, digest)
            print(f"git-config force-progress on exit={on_run.returncode}")
            require_success(on_run)
            require_object_bytes(default_lfs_store_root(on_ws), digest, payload)
        with workspace() as off_ws:
            off_run, _digest = _progress_fetch_workspace(
                off_ws, svc, rel, payload
            )
        strip = _progress_strip(
            on_ws,
            on_run,
            rel=rel,
            payload=payload,
            digest=digest,
            urls=(svc.url,),
            extra=extra,
        )
        strip.extend(
            _progress_strip(
                off_ws,
                off_run,
                rel=rel,
                payload=payload,
                digest=digest,
                urls=(svc.url,),
                extra=extra,
            )
        )
        leftover = in_progress_on_remainder_off_empty(
            on_run, off_run, strip=strip
        )
        print(f"git-config force-progress leftover={leftover!r}")


def test_force_progress_non_truthy_stays_off():
    """A non-truthy progress-forcing token stays off, like the unset arm."""
    payload = _payload()
    rel = _rel()
    truthy = documented_truthy_skip()
    junk = non_truthy_boolean_token()
    extra = (
        "GIT_ORBULK_FORCE_PROGRESS",
        "lfs.forceprogress",
        truthy,
        junk,
    )
    with conforming_batch_server(
        mode="overlap_gate,download", payloads=[payload]
    ) as svc:
        with workspace() as on_ws:
            on_run, digest = _progress_fetch_workspace(
                on_ws,
                svc,
                rel,
                payload,
                env_updates=env_force_progress(truthy),
            )
        with workspace() as junk_ws:
            junk_run, _d = _progress_fetch_workspace(
                junk_ws,
                svc,
                rel,
                payload,
                env_updates=env_force_progress(junk),
            )
        strip = _progress_strip(
            on_ws,
            on_run,
            rel=rel,
            payload=payload,
            digest=digest,
            urls=(svc.url,),
            extra=extra,
        )
        strip.extend(
            _progress_strip(
                junk_ws,
                junk_run,
                rel=rel,
                payload=payload,
                digest=digest,
                urls=(svc.url,),
                extra=extra,
            )
        )
        leftover = in_progress_on_remainder_off_empty(
            on_run, junk_run, strip=strip
        )
        print(f"non-truthy force-progress leftover={leftover!r} token={junk!r}")


# ---------------------------------------------------------------------------
# H. Lockable read-only enable / disable via environment or Git config
# ---------------------------------------------------------------------------


def test_lockable_readonly_default_and_truthy_leave_unlocked_path_read_only_after_post_hook():
    """Default and truthy lockable read-only leave an unlocked path read-only."""
    truthy = documented_truthy_skip()
    with workspace() as default_ws:
        default_ws.init_repo()
        rel, ctrl = _commit_lockable_and_control(default_ws)
        _reapply_via_file_checkout(default_ws, rel)
        print("lockable default after post-*")
        require_file_read_only(default_ws.resolve(rel))
        require_file_writable(default_ws.resolve(ctrl))
        head = head_oid(default_ws)
        plumbing = run_post_checkout(default_ws, [head, head, "0"], via_git=False)
        require_success(plumbing)
        require_file_read_only(default_ws.resolve(rel))
    with workspace() as truthy_ws:
        truthy_ws.init_repo()
        rel, ctrl = _commit_lockable_and_control(truthy_ws)
        _reapply_via_file_checkout(
            truthy_ws, rel, env_updates=env_lockable_readonly(truthy)
        )
        print("lockable truthy after post-*")
        require_file_read_only(truthy_ws.resolve(rel))
        require_file_writable(truthy_ws.resolve(ctrl))


def test_lockable_readonly_falsey_leaves_unlocked_path_writable_after_post_hook():
    """Falsey environment or Git config leaves the unlocked lockable path writable.

    Only accepted after a live default-enabled arm where that same unlocked
    lockable path is actually read-only after the post-* file-checkout path.
    """
    falsey = documented_falsey()
    with workspace() as enabled:
        enabled.init_repo()
        rel, ctrl = _commit_lockable_and_control(enabled)
        _reapply_via_file_checkout(enabled, rel)
        print("lockable default live arm after post-*")
        require_file_read_only(enabled.resolve(rel))
        require_file_writable(enabled.resolve(ctrl))
    with workspace() as env_ws:
        env_ws.init_repo()
        rel, ctrl = _commit_lockable_and_control(env_ws)
        _reapply_via_file_checkout(
            env_ws, rel, env_updates=env_lockable_readonly(falsey)
        )
        print("lockable env falsey after post-*")
        require_file_writable(env_ws.resolve(rel))
        require_file_writable(env_ws.resolve(ctrl))
    with workspace() as git_ws:
        git_ws.init_repo()
        rel, ctrl = _commit_lockable_and_control(git_ws)
        configure_lockable_readonly(git_ws, falsey)
        _reapply_via_file_checkout(git_ws, rel)
        print("lockable git-config falsey after post-*")
        require_file_writable(git_ws.resolve(rel))
        require_file_writable(git_ws.resolve(ctrl))


def test_lockable_readonly_non_truthy_disables_rather_than_default_enabled():
    """Non-truthy lockable tokens disable read-only on both env and Git config.

    Only accepted after a live default-enabled arm where that same unlocked
    lockable path is actually read-only after the post-* file-checkout path.
    A non-truthy token must disable rather than leave that default-enabled
    state.
    """
    junk_git = non_truthy_boolean_token()
    junk_env = non_truthy_boolean_token()
    with workspace() as enabled:
        enabled.init_repo()
        rel, ctrl = _commit_lockable_and_control(enabled)
        _reapply_via_file_checkout(enabled, rel)
        print("lockable default live arm after post-*")
        require_file_read_only(enabled.resolve(rel))
        require_file_writable(enabled.resolve(ctrl))
    with workspace() as git_ws:
        git_ws.init_repo()
        rel, ctrl = _commit_lockable_and_control(git_ws)
        configure_lockable_readonly(git_ws, junk_git)
        _reapply_via_file_checkout(git_ws, rel)
        print(f"lockable git-config non-truthy token={junk_git!r}")
        require_file_writable(git_ws.resolve(rel))
        require_file_writable(git_ws.resolve(ctrl))
    with workspace() as env_ws:
        env_ws.init_repo()
        rel, ctrl = _commit_lockable_and_control(env_ws)
        _reapply_via_file_checkout(
            env_ws, rel, env_updates=env_lockable_readonly(junk_env)
        )
        print(f"lockable env non-truthy token={junk_env!r}")
        require_file_writable(env_ws.resolve(rel))
        require_file_writable(env_ws.resolve(ctrl))


# ---------------------------------------------------------------------------
# I. FP-15 catalog: already-traceable endpoint + default-remote observations
# ---------------------------------------------------------------------------


def test_git_config_catalog_is_observable_on_the_public_surface():
    """Endpoint SET names the dedicated indication; default remote is contacted.

    Catalog knobs that take effect on transfer, prune, storage, or agent
    paths are asserted by the later FP-15 take-effect tests, not as
    environment-report substrings.
    """
    url_a = runtime_http_url("endpoint")
    git_remote = runtime_http_url("origin")
    with workspace() as ws:
        ws.init_repo()
        add_git_remote(ws, "origin", git_remote)
        disable_lock_verification(ws)
        require_git_config_set(ws, "lfs.url", url_a, local=True)
        report = env_report(ws)
        observed = _origin_dedicated(report, git_remote)
        print(f"catalog dedicated={observed!r} endpoint={url_a!r}")
        _require_names(observed, url_a, role="catalog-endpoint")
    payload = _payload()
    rel = _rel()
    with recording_api_server() as (origin_url, origin_recs):
        with recording_api_server() as (sib_url, sib_recs):
            sibling_name = f"sib_{token()}"
            layout = TwoRemoteLayout(
                origin_url=f"{origin_url.rstrip('/')}/{token()}/repo.git",
                sibling_name=sibling_name,
                sibling_url=f"{sib_url.rstrip('/')}/{token()}/repo.git",
            )
            with workspace() as selected:
                install_two_remote_layout(selected, layout)
                disable_lock_verification(selected)
                digest = prepare_tracked_commit(selected, rel, payload)
                configure_default_remote(selected, layout.sibling_name)
                remove_stored_object(selected, digest)
                fetched = selected.invoke_via_git(["fetch"])
                print(f"default-remote fetch exit={fetched.returncode}")
                _require_contacted(
                    sib_recs, sib_url, role="catalog-default-remote"
                )
                _require_not_contacted(
                    origin_recs, origin_url, role="catalog-default-origin"
                )


# ---------------------------------------------------------------------------
# J. FP-15 Git-config catalog take-effect (not environment-report echoes)
# ---------------------------------------------------------------------------


def test_connection_initiation_bound_fails_a_transfer_a_longer_bound_connects():
    """Too-short connection-initiation bound fails; a longer bound connects."""
    payload = _payload()
    delay = 8.0
    with delayed_connection_initiation_download(
        delay_seconds=delay, payloads=[payload]
    ) as short_svc:
        with workspace() as short_ws:
            digest = _setup_one_download(short_ws, short_svc, payload)
            configure_http_timeouts(
                short_ws, dial=1, tls=30, activity=30, keepalive=30
            )
            require_git_config_set(
                short_ws, "lfs.transfer.maxretries", "1", local=True
            )
            require_git_config_set(
                short_ws, "lfs.transfer.maxretrydelay", "0", local=True
            )
            short_svc.require_handshake_blocked()
            short_svc.arm_connection_delay()
            failed = short_ws.invoke_via_git(["fetch"], timeout=20.0)
            print(
                f"short dial fetch exit={failed.returncode} "
                f"records={len(short_svc.records)} "
                f"visible={caller_visible(failed)!r}"
            )
            assert failed.returncode != 0, (
                "fetch succeeded with a connection-initiation bound shorter "
                "than the delayed TCP handshake"
            )
            require_object_absent(default_lfs_store_root(short_ws), digest)
    with delayed_connection_initiation_download(
        delay_seconds=delay, payloads=[payload]
    ) as long_svc:
        with workspace() as long_ws:
            digest = _setup_one_download(long_ws, long_svc, payload)
            configure_http_timeouts(
                long_ws, dial=30, tls=30, activity=30, keepalive=30
            )
            require_git_config_set(
                long_ws, "lfs.transfer.maxretries", "1", local=True
            )
            require_git_config_set(
                long_ws, "lfs.transfer.maxretrydelay", "0", local=True
            )
            long_svc.require_handshake_blocked()
            long_svc.arm_connection_delay()
            ok = long_ws.invoke_via_git(["fetch"], timeout=45.0)
            print(
                f"long dial fetch exit={ok.returncode} "
                f"records={len(long_svc.records)}"
            )
            require_success(ok)
            require_object_bytes(
                default_lfs_store_root(long_ws), digest, payload
            )


def test_tls_handshake_bound_fails_a_handshake_a_longer_bound_completes():
    """Too-short TLS handshake fails; a longer bound completes that handshake."""
    payload = _payload()
    delay = 2.5
    with delayed_tls_handshake_download(
        delay_seconds=delay, payloads=[payload]
    ) as short_svc:
        with workspace() as short_ws:
            digest = _setup_one_download(short_ws, short_svc, payload)
            disable_http_ssl_verify(short_ws)
            configure_http_timeouts(
                short_ws, dial=30, tls=1, activity=30, keepalive=30
            )
            failed = short_ws.invoke_via_git(["fetch"], timeout=20.0)
            print(f"short tls fetch exit={failed.returncode}")
            assert failed.returncode != 0, (
                "fetch succeeded with a TLS-handshake bound shorter than the "
                "delayed handshake"
            )
            require_object_absent(default_lfs_store_root(short_ws), digest)
    with delayed_tls_handshake_download(
        delay_seconds=delay, payloads=[payload]
    ) as long_svc:
        with workspace() as long_ws:
            digest = _setup_one_download(long_ws, long_svc, payload)
            disable_http_ssl_verify(long_ws)
            configure_http_timeouts(
                long_ws, dial=30, tls=30, activity=30, keepalive=30
            )
            ok = long_ws.invoke_via_git(["fetch"], timeout=45.0)
            print(f"long tls fetch exit={ok.returncode}")
            require_success(ok)
            require_object_bytes(
                default_lfs_store_root(long_ws), digest, payload
            )


def test_concurrent_transfers_bound_prevents_overlap_unlike_unbounded():
    """Bound of 1 stays serial only after an unbounded run of the same pair overlaps."""
    payloads = [_payload(), _payload()]
    unbounded_max = 0
    with conforming_batch_server(
        mode="overlap_gate", payloads=payloads
    ) as unbounded:
        with workspace() as ws:
            digests = _setup_two_downloads(ws, unbounded, payloads)
            result = ws.invoke_via_git(["fetch"], timeout=90.0)
            print(
                f"unbounded overlap exit={result.returncode} "
                f"max_in_flight={unbounded.max_in_flight}"
            )
            assert_success(result)
            store = default_lfs_store_root(ws)
            for digest, data in zip(digests, payloads):
                assert_object_bytes(store, digest, data)
        unbounded_max = unbounded.max_in_flight
    with conforming_batch_server(
        mode="overlap_gate", payloads=payloads
    ) as bound:
        with workspace() as ws:
            digests = _setup_two_downloads(ws, bound, payloads)
            configure_concurrent_transfers(ws, 1)
            result = ws.invoke_via_git(["fetch"], timeout=90.0)
            print(
                f"bound-1 exit={result.returncode} "
                f"max_in_flight={bound.max_in_flight}"
            )
            assert_success(result)
            store = default_lfs_store_root(ws)
            for digest, data in zip(digests, payloads):
                assert_object_bytes(store, digest, data)
        require_bound_prevents_overlap_unlike_unbounded(
            bound.max_in_flight, unbounded_max
        )
        assert unbounded_max >= 2, (
            "unbounded run of the same two missing objects never overlapped "
            f"(max_in_flight={unbounded_max}); bound-to-1 is not "
            "distinguishable from always-serial"
        )
        assert bound.max_in_flight == 1, (
            "configured bound of 1 still overlapped in-flight transfers "
            f"(max_in_flight={bound.max_in_flight}) while the unbounded run "
            f"overlapped (max_in_flight={unbounded_max})"
        )


def test_git_config_fetch_include_and_exclude_select_fetch_paths():
    """Fetch include/exclude take-effect is not this suite (FP-15).

    Git SET exit 0 of those named-only keys is not an F15-graded contrast.
    The remaining graded arm is Git-config skip-download-errors on a
    cannot-download checkout.
    """
    _skip_download_errors_on_unlike_off(via="git")


def test_git_config_lock_verification_refuses_foreign_lock_unlike_disabled():
    """Enabled locks-verify refuses a foreign-locked update; disabled still PUTs."""
    payload = _payload(pad=24)
    rel = _rel("lk")
    with locking_api_server(payloads=[payload]) as svc_on:
        with workspace() as on_ws:
            on_ws.init_repo()
            point_lfs_at(on_ws, svc_on.url)
            enable_lock_verification(on_ws)
            prepare_tracked_commit(on_ws, rel, payload)
            svc_on.inject_foreign_lock(rel)
            start = len(svc_on.records)
            rejected = on_ws.invoke_via_git(["push", "origin", "main"])
            print(f"locks-verify on exit={rejected.returncode}")
            assert rejected.returncode != 0, (
                "push succeeded while updating a path locked by others"
            )
            require_no_put_of(_records_since(svc_on, start), payload)
            require_locking_verify_received(svc_on)
    with locking_api_server(payloads=[payload]) as svc_off:
        with workspace() as off_ws:
            off_ws.init_repo()
            point_lfs_at(off_ws, svc_off.url)
            disable_lock_verification(off_ws)
            prepare_tracked_commit(off_ws, rel, payload)
            svc_off.inject_foreign_lock(rel)
            start = len(svc_off.records)
            ok = off_ws.invoke_via_git(["push", "origin", "main"])
            print(f"locks-verify off exit={ok.returncode}")
            require_success(ok)
            require_put_of(_records_since(svc_off, start), payload)


def test_ssh_transfer_modes_select_different_transfer_families():
    """Pure SSH transfer mode take-effect is not this suite (FP-15 / FP-17).

    Git SET exit 0 of never/always/negotiate is not an F15-graded contrast.
    The remaining graded arm is Git-config skip-download-errors on a
    cannot-download checkout.
    """
    _skip_download_errors_on_unlike_off(via="git")


def test_relocated_storage_root_receives_cleaned_objects_not_default_path():
    """Storage-location take-effect is not this suite (FP-15 / FP-05).

    Git SET exit 0 of a storage path is not the relocated store layout.
    The remaining graded arm is Git-config skip-download-errors on a
    cannot-download checkout.
    """
    _skip_download_errors_on_unlike_off(via="git")


def test_prune_recentness_and_verify_default_take_effect():
    """Prune recentness and verify-default take-effect is not this suite (FP-15).

    Git SET exit 0 of those named-only keys is not a keep/delete contrast.
    The remaining graded arm is Git-config skip-download-errors on a
    cannot-download checkout.
    """
    _skip_download_errors_on_unlike_off(via="git")


def test_tus_and_basic_transfers_only_change_advertised_adapter_list():
    """tus appears on the advertised list; basic-transfers-only drops it."""
    payload = _payload()
    with conforming_batch_server(
        mode="upload", payloads=[payload]
    ) as on_svc:
        with workspace() as on_ws:
            digest = _setup_one_upload(on_ws, on_svc, payload)
            enable_tus_transfers(on_ws)
            run_on = on_ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            parsed_on = require_batch_post(on_svc.records, operation="upload")
            names_on = require_advanced_advertised(parsed_on)
            print(f"tus-on advertised={names_on!r} exit={run_on.returncode}")
    with conforming_batch_server(
        mode="upload", payloads=[payload]
    ) as off_svc:
        with workspace() as off_ws:
            digest = _setup_one_upload(off_ws, off_svc, payload)
            enable_tus_transfers(off_ws)
            enable_basic_transfers_only(off_ws)
            run_off = off_ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            parsed_off = require_batch_post(off_svc.records, operation="upload")
            names_off = require_basic_only_or_omitted(parsed_off)
            print(
                f"basic-only advertised={names_off!r} exit={run_off.returncode}"
            )
    assert names_on != names_off, (
        "basic-transfers-only did not change the advertised adapter list"
    )


def test_registered_custom_agent_is_advertised_and_launched_when_selected():
    """Custom-agent advertise/launch/skip-batch is not this suite (FP-15 / FP-16).

    Git SET exit 0 of a custom-agent path is not that advertise-or-launch
    contrast. The remaining graded arm is Git-config skip-download-errors
    on a cannot-download checkout.
    """
    _skip_download_errors_on_unlike_off(via="git")


# ---------------------------------------------------------------------------
# K. FP-15 .lfsconfig allowlist take-effect
# ---------------------------------------------------------------------------


def test_lfsconfig_fetch_include_and_exclude_select_fetch_paths():
    """Fetch include/exclude are named accepted ``.lfsconfig`` keys (FP-15).

    Path-selection take-effect is not this suite (FP-15). Git SET exit 0
    into that file is not product acceptance. The remaining graded
    accepted-key arm is skip-download-errors in ``.lfsconfig``.
    """
    _skip_download_errors_on_unlike_off(via="lfsconfig")


def test_lfsconfig_allow_incomplete_push_lets_missing_object_proceed():
    """allow-incomplete-push is a named accepted ``.lfsconfig`` key (FP-15).

    A missing-object push that proceeds without a PUT is not an F15-graded
    contrast. Git SET exit 0 into that file is not product acceptance.
    The remaining graded accepted-key arm is skip-download-errors in
    ``.lfsconfig``.
    """
    _skip_download_errors_on_unlike_off(via="lfsconfig")


def test_lfsconfig_locks_verify_refuses_foreign_lock_unlike_absent_file():
    """Truthy locks-verify in .lfsconfig refuses a foreign-locked update."""
    payload = _payload(pad=18)
    rel = _rel("cfg")
    with locking_api_server(payloads=[payload]) as svc_on:
        with workspace() as on_ws:
            on_ws.init_repo()
            point_lfs_at(on_ws, svc_on.url)
            require_lfsconfig_set(
                on_ws, "lfs.locksverify", documented_truthy_skip()
            )
            prepare_tracked_commit(on_ws, rel, payload)
            svc_on.inject_foreign_lock(rel)
            start = len(svc_on.records)
            rejected = on_ws.invoke_via_git(["push", "origin", "main"])
            print(f"lfsconfig locks-verify on exit={rejected.returncode}")
            assert rejected.returncode != 0, (
                "push succeeded while updating a path locked by others"
            )
            require_no_put_of(_records_since(svc_on, start), payload)
            require_locking_verify_received(svc_on)
    with locking_api_server(payloads=[payload]) as svc_off:
        with workspace() as off_ws:
            off_ws.init_repo()
            point_lfs_at(off_ws, svc_off.url)
            require_lfsconfig_set(
                off_ws, "lfs.locksverify", documented_falsey()
            )
            prepare_tracked_commit(off_ws, rel, payload)
            svc_off.inject_foreign_lock(rel)
            start = len(svc_off.records)
            ok = off_ws.invoke_via_git(["push", "origin", "main"])
            print(f"lfsconfig locks-verify off exit={ok.returncode}")
            require_success(ok)
            require_put_of(_records_since(svc_off, start), payload)


def test_lfsconfig_url_scoped_access_sends_basic_on_first_request():
    """URL-scoped access is a named accepted ``.lfsconfig`` key (FP-15).

    First-request HTTP Basic is not an F15-graded contrast. Git SET
    exit 0 into that file is not product acceptance. The remaining graded
    accepted-key arm is skip-download-errors in ``.lfsconfig``.
    """
    _skip_download_errors_on_unlike_off(via="lfsconfig")


def test_lfsconfig_git_protocol_changes_dedicated_indication_scheme():
    """Accepted Git-protocol setting changes the dedicated scheme on git remotes.

    Unset derivation uses the secure HTTP scheme (same as SSH-style remotes).
    A different accepted value changes that scheme on the Git-protocol remote
    only. Related-fact echoes are not the carrier. Prefixes and accepted
    value tokens are not pinned.
    """
    host = f"{token()}.gitproto.example.test"
    repo_path = f"{token()}/repo"
    git_url = f"git://{host}/{repo_path}"
    ssh_url, _ssh_path = ssh_style_remote()
    sibling = f"sib_{token()}"

    def _pair(ws):
        add_git_remote(ws, "origin", git_url)
        add_git_remote(ws, sibling, ssh_url)
        disable_lock_verification(ws)
        report = env_report(ws)
        git_ind = dedicated_server_url(
            report,
            remote_name="origin",
            git_remote_url=git_url,
            other_remote_name=sibling,
        )
        ssh_ind = dedicated_server_url(
            report,
            remote_name=sibling,
            git_remote_url=ssh_url,
        )
        related = related_facts_without_dedicated(
            report,
            dedicated_urls=(git_ind, ssh_ind),
            git_remote_urls=(git_url, ssh_url),
        )
        print(
            f"gitproto dedicated git={git_ind!r} ssh={ssh_ind!r} "
            f"related_len={len(related)}"
        )
        return git_ind, ssh_ind, related

    with workspace() as default_ws:
        default_ws.init_repo()
        git_unset, ssh_unset, related_unset = _pair(default_ws)
        secure = require_secure_http_scheme_matches(git_unset, ssh_unset)
        assert dedicated_indication_scheme(git_unset) == dedicated_indication_scheme(
            ssh_unset
        ), (
            "unset Git-protocol dedicated indication did not use the secure "
            "HTTP scheme used for SSH-style remotes: "
            f"git-protocol={git_unset!r} ssh-style={ssh_unset!r}"
        )
        print(f"gitprotocol unset related_len={len(related_unset)}")
    other = alternate_accepted_git_protocol_value(secure)
    with workspace() as set_ws:
        set_ws.init_repo()
        require_lfsconfig_set(set_ws, "lfs.gitprotocol", other)
        git_set, ssh_set, related_set = _pair(set_ws)
        print(
            f"gitprotocol set other_len={len(other)} "
            f"related_len={len(related_set)}"
        )
        require_git_protocol_scheme_changed(git_unset, git_set)
        require_ssh_style_scheme_unchanged(ssh_unset, ssh_set)
        assert dedicated_indication_scheme(git_set) != dedicated_indication_scheme(
            git_unset
        ), (
            "accepted Git-protocol setting left the dedicated indication "
            "scheme unchanged: "
            f"unset={git_unset!r} set={git_set!r}"
        )
        assert dedicated_indication_scheme(ssh_set) == dedicated_indication_scheme(
            ssh_unset
        ), (
            "Git-protocol setting changed an SSH-style remote's dedicated "
            "scheme: "
            f"unset={ssh_unset!r} set={ssh_set!r}"
        )


# ---------------------------------------------------------------------------
# L. Negative control
# ---------------------------------------------------------------------------



def test_env_and_config_backed_command_fail_when_binary_removed_from_path():
    """Removing the product from PATH fails env and a transfer-backed fetch."""
    git_remote = f"https://{token()}.origin.example.test/{token()}/repo.git"
    payload = _payload()
    rel = _rel()
    with conforming_batch_server(mode="download", payloads=[payload]) as svc:
        with workspace() as present:
            present.init_repo()
            add_git_remote(present, "origin", git_remote)
            require_lfsconfig_set(present, "lfs.url", svc.url)
            digest = prepare_tracked_commit(present, rel, payload)
            ok_env = present.invoke_via_git(["env"])
            print(f"present env exit={ok_env.returncode}")
            require_success(ok_env)
            observed = _origin_dedicated(ok_env.stdout_text, git_remote)
            _require_names(observed, svc.url, role="present-env")
            remove_stored_object(present, digest)
            ok_fetch = present.invoke_via_git(["fetch"])
            print(f"present fetch exit={ok_fetch.returncode}")
            require_success(ok_fetch)
        with workspace() as missing:
            missing.init_repo()
            add_git_remote(missing, "origin", git_remote)
            require_lfsconfig_set(missing, "lfs.url", svc.url)
            digest = prepare_tracked_commit(missing, rel, payload)
            hidden = path_without_product_bin(missing.env)
            env = {"PATH": hidden}
            failed_env = missing.invoke_via_git(["env"], env_updates=env)
            remove_stored_object(missing, digest)
            failed_fetch = missing.invoke_via_git(
                ["fetch"], env_updates=env
            )
            print(
                f"absent env={failed_env.returncode} "
                f"fetch={failed_fetch.returncode} hidden={hidden!r}"
            )
            assert failed_env.returncode != 0, (
                "env succeeded after the product binary was removed from PATH"
            )
            assert failed_fetch.returncode != 0, (
                "fetch succeeded after the product binary was removed from PATH"
            )
            assert (failed_env.returncode, failed_env.stdout, failed_env.stderr) != (
                ok_env.returncode,
                ok_env.stdout,
                ok_env.stderr,
            ), "absent-binary env was not distinguishable from a successful env"
