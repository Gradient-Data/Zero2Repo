# feature: F17
"""Pure SSH transfer protocol acceptance tests.

PRD: FP-17 and the PRD core capabilities (binary off PATH). Fetch and
push-object-id against an SSH Git remote exercise git-orbulk-transfer,
hybrid fallback, the negotiate/always/never triad, and post-put
verification. Command tokens, pkt-line status numbers, and message
wording are not pinned.
"""

from __future__ import annotations

import json
import os

from _harness import token, workspace
from _helpers import (
    add_git_remote,
    assert_no_authenticate_invocation,
    assert_no_http_exchanges,
    assert_object_bytes,
    assert_post_put_roundtrip,
    assert_ssh_channel_delivered,
    assert_ssh_peer_stored,
    assert_success,
    assert_transfer_invocation,
    assert_version_1_selected,
    configure_ssh_transfer_mode,
    default_lfs_store_root,
    install_ssh_transfer_peer,
    path_without_product_bin,
    prepare_tracked_commit,
    remove_stored_object,
    require_authenticate_invocation,
    require_no_authenticate_invocation,
    require_no_http_exchanges,
    require_no_put_of,
    require_no_transfer_invocation,
    require_object_absent,
    require_object_bytes,
    require_post_put_roundtrip,
    require_put_of,
    require_put_step_error,
    require_ssh_channel_delivered,
    require_ssh_peer_stored,
    require_success,
    require_transfer_invocation,
    require_version_1_selected,
    sha256_hex,
    ssh_env_updates,
    ssh_style_remote,
    storing_batch_server,
    write_pointer_placeholders_from_index,
)


def _payload() -> bytes:
    return f"blob-{token()}\n".encode("utf-8")


def _rel() -> str:
    return f"payload_{token()}.bin"


def _auth_json(url: str) -> str:
    return json.dumps({"href": url, "header": {}})


def _seed_peer(probe, payload: bytes) -> str:
    oid = sha256_hex(payload)
    dest = probe.seed_dir / oid
    dest.write_bytes(payload)
    return oid


def _prepare(ws, ssh_url: str, payload: bytes) -> tuple[str, str]:
    ws.init_repo()
    add_git_remote(ws, "origin", ssh_url)
    rel = _rel()
    digest = prepare_tracked_commit(ws, rel, payload)
    return rel, digest


def _gap_download(ws, rel: str, digest: str) -> None:
    remove_stored_object(ws, digest)
    write_pointer_placeholders_from_index(ws, [rel])
    require_object_absent(default_lfs_store_root(ws), digest)


def _fetch(ws, env, *, via_git: bool = True):
    if via_git:
        return ws.invoke_via_git(["fetch"], env_updates=env)
    return ws.invoke(["fetch"], env_updates=env)


def _push(ws, env, digest: str, *, via_git: bool = True):
    argv = ["push", "--object-id", "origin", digest]
    if via_git:
        return ws.invoke_via_git(argv, env_updates=env)
    return ws.invoke(argv, env_updates=env)


def _no_https_object_bytes(records, payload: bytes) -> None:
    require_no_put_of(records, payload)
    hits = [rec for rec in records if rec.method in ("GET", "HEAD")]
    print(f"https_get_head={len(hits)}")
    assert not hits, (
        "HTTPS GET/HEAD of an object action; object bytes were not kept "
        f"off HTTPS: {[(rec.method, rec.path) for rec in hits]!r}"
    )


def _https_got_object(records) -> None:
    gets = [rec for rec in records if rec.method == "GET"]
    print(f"https_gets={len(gets)}")
    assert gets, (
        "hybrid download did not GET object bytes; "
        f"records={[(rec.method, rec.path) for rec in records]!r}"
    )


def _peer_lacks_payload(probe, payload: bytes) -> None:
    store = probe.store_dir
    try:
        names = os.listdir(store)
    except FileNotFoundError:
        raise AssertionError(
            f"ssh peer store directory is missing at {store}"
        ) from None
    except OSError as exc:
        raise AssertionError(f"cannot list ssh peer store {store}: {exc}") from exc
    for name in names:
        path = store / name
        try:
            is_file = path.is_file()
        except OSError as exc:
            raise AssertionError(f"cannot stat {path}: {exc}") from exc
        if not is_file:
            continue
        try:
            body = path.read_bytes()
        except OSError as exc:
            raise AssertionError(f"cannot read {path}: {exc}") from exc
        assert body != payload, (
            f"ssh peer store held the payload on a non-SSH success path "
            f"at {path}"
        )


# ---------------------------------------------------------------------------
# A. Default unset: download over SSH, bytes from the channel
# ---------------------------------------------------------------------------


def test_default_negotiate_downloads_object_bytes_over_ssh_without_https():
    """Unset ssh-transfer download uses git-orbulk-transfer; bytes come from SSH."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as ws:
            probe = install_ssh_transfer_peer(
                ws, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(ws, ssh_url, payload)
            _seed_peer(probe, payload)
            _gap_download(ws, rel, digest)
            env = ssh_env_updates(probe)
            result = _fetch(ws, env, via_git=False)
            print(
                f"A download exit={result.returncode} "
                f"digest={digest} nhttp={len(svc.records)}"
            )
            require_success(result)
            require_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            require_version_1_selected(probe)
            require_ssh_channel_delivered(probe, payload)
            require_object_bytes(default_lfs_store_root(ws), digest, payload)
            _no_https_object_bytes(svc.records, payload)


# ---------------------------------------------------------------------------
# B. Default unset: upload over SSH with post-put round-trip
# ---------------------------------------------------------------------------


def test_default_negotiate_uploads_object_bytes_over_ssh_with_post_put_roundtrip():
    """Unset ssh-transfer upload stores on the peer and still verifies after put."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as ws:
            probe = install_ssh_transfer_peer(
                ws, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest = _prepare(ws, ssh_url, payload)
            env = ssh_env_updates(probe)
            result = _push(ws, env, digest, via_git=True)
            print(
                f"B upload exit={result.returncode} "
                f"digest={digest} nhttp={len(svc.records)}"
            )
            require_success(result)
            require_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            require_version_1_selected(probe)
            require_ssh_peer_stored(probe, payload)
            require_post_put_roundtrip(probe)
            _no_https_object_bytes(svc.records, payload)


# ---------------------------------------------------------------------------
# C. Default unset: session cannot start → hybrid fallback
# ---------------------------------------------------------------------------


def test_default_unset_falls_back_to_hybrid_when_transfer_session_cannot_be_established():
    """Unset negotiate falls back to authenticate+HTTPS when the session cannot start."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as down:
            probe = install_ssh_transfer_peer(
                down, mode="no_session", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(down, ssh_url, payload)
            svc.stored[digest] = payload
            _gap_download(down, rel, digest)
            env = ssh_env_updates(probe)
            result = _fetch(down, env)
            print(f"C download exit={result.returncode} nhttp={len(svc.records)}")
            require_success(result)
            require_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            require_authenticate_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            _https_got_object(svc.records)
            require_object_bytes(default_lfs_store_root(down), digest, payload)
            _peer_lacks_payload(probe, payload)
        svc.stored.clear()
        n0 = len(svc.records)
        with workspace() as up:
            probe_up = install_ssh_transfer_peer(
                up, mode="no_session", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest_up = _prepare(up, ssh_url, payload)
            env_up = ssh_env_updates(probe_up)
            pushed = _push(up, env_up, digest_up)
            later = svc.records[n0:]
            print(f"C upload exit={pushed.returncode} nhttp={len(later)}")
            require_success(pushed)
            require_transfer_invocation(
                probe_up.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            require_authenticate_invocation(
                probe_up.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            require_put_of(later, payload)
            _peer_lacks_payload(probe_up, payload)


# ---------------------------------------------------------------------------
# D. never: hybrid only, do not attempt git-orbulk-transfer
# ---------------------------------------------------------------------------


def test_never_mode_uses_only_hybrid_and_does_not_attempt_git_orbulk_transfer():
    """Git-config never skips git-orbulk-transfer and completes via hybrid HTTPS."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        svc.stored[sha256_hex(payload)] = payload
        with workspace() as base_down:
            probe_base = install_ssh_transfer_peer(
                base_down, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(base_down, ssh_url, payload)
            _seed_peer(probe_base, payload)
            _gap_download(base_down, rel, digest)
            env_base = ssh_env_updates(probe_base)
            require_success(_fetch(base_down, env_base))
            require_transfer_invocation(
                probe_base.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            print("D download baseline attempted git-orbulk-transfer")
        n1 = len(svc.records)
        with workspace() as never_down:
            probe = install_ssh_transfer_peer(
                never_down, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(never_down, ssh_url, payload)
            configure_ssh_transfer_mode(never_down, "never")
            _seed_peer(probe, payload)
            _gap_download(never_down, rel, digest)
            env = ssh_env_updates(probe)
            result = _fetch(never_down, env)
            later = svc.records[n1:]
            print(f"D download never exit={result.returncode} nhttp={len(later)}")
            require_success(result)
            require_no_transfer_invocation(probe.argv_log)
            require_authenticate_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            _https_got_object(later)
            require_object_bytes(
                default_lfs_store_root(never_down), digest, payload
            )
        with workspace() as base_up:
            probe_bu = install_ssh_transfer_peer(
                base_up, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest_bu = _prepare(base_up, ssh_url, payload)
            require_success(
                _push(base_up, ssh_env_updates(probe_bu), digest_bu)
            )
            require_transfer_invocation(
                probe_bu.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            print("D upload baseline attempted git-orbulk-transfer")
        n3 = len(svc.records)
        with workspace() as never_up:
            probe_nu = install_ssh_transfer_peer(
                never_up, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest_nu = _prepare(never_up, ssh_url, payload)
            configure_ssh_transfer_mode(never_up, "never")
            pushed = _push(never_up, ssh_env_updates(probe_nu), digest_nu)
            later_up = svc.records[n3:]
            print(
                f"D upload never exit={pushed.returncode} nhttp={len(later_up)}"
            )
            require_success(pushed)
            require_no_transfer_invocation(probe_nu.argv_log)
            require_authenticate_invocation(
                probe_nu.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            require_put_of(later_up, payload)


# ---------------------------------------------------------------------------
# E. SET negotiate: session cannot start → hybrid fallback
# ---------------------------------------------------------------------------


def test_negotiate_falls_back_to_hybrid_when_transfer_session_cannot_be_established():
    """SET negotiate still tries git-orbulk-transfer then completes via hybrid."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as down:
            probe = install_ssh_transfer_peer(
                down, mode="no_session", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(down, ssh_url, payload)
            configure_ssh_transfer_mode(down, "negotiate")
            svc.stored[digest] = payload
            _gap_download(down, rel, digest)
            result = _fetch(down, ssh_env_updates(probe))
            print(f"E download exit={result.returncode} nhttp={len(svc.records)}")
            require_success(result)
            require_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            require_authenticate_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            _https_got_object(svc.records)
            require_object_bytes(default_lfs_store_root(down), digest, payload)
            _peer_lacks_payload(probe, payload)
        svc.stored.clear()
        n0 = len(svc.records)
        with workspace() as up:
            probe_up = install_ssh_transfer_peer(
                up, mode="no_session", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest_up = _prepare(up, ssh_url, payload)
            configure_ssh_transfer_mode(up, "negotiate")
            pushed = _push(up, ssh_env_updates(probe_up), digest_up)
            later = svc.records[n0:]
            print(f"E upload exit={pushed.returncode} nhttp={len(later)}")
            require_success(pushed)
            require_transfer_invocation(
                probe_up.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            require_authenticate_invocation(
                probe_up.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            require_put_of(later, payload)
            _peer_lacks_payload(probe_up, payload)


# ---------------------------------------------------------------------------
# F. SET negotiate: working peer keeps object bytes on SSH
# ---------------------------------------------------------------------------


def test_set_negotiate_keeps_ssh_object_bytes_when_peer_works():
    """SET negotiate still moves object bytes on SSH when the peer speaks."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as down:
            probe = install_ssh_transfer_peer(
                down, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(down, ssh_url, payload)
            configure_ssh_transfer_mode(down, "negotiate")
            _seed_peer(probe, payload)
            _gap_download(down, rel, digest)
            result = _fetch(down, ssh_env_updates(probe))
            print(f"F download exit={result.returncode} nhttp={len(svc.records)}")
            require_success(result)
            require_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            require_version_1_selected(probe)
            require_ssh_channel_delivered(probe, payload)
            require_object_bytes(default_lfs_store_root(down), digest, payload)
            _no_https_object_bytes(svc.records, payload)
        n0 = len(svc.records)
        with workspace() as up:
            probe_up = install_ssh_transfer_peer(
                up, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest_up = _prepare(up, ssh_url, payload)
            configure_ssh_transfer_mode(up, "negotiate")
            pushed = _push(up, ssh_env_updates(probe_up), digest_up)
            later = svc.records[n0:]
            print(f"F upload exit={pushed.returncode} nhttp={len(later)}")
            require_success(pushed)
            require_transfer_invocation(
                probe_up.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            require_version_1_selected(probe_up)
            require_ssh_peer_stored(probe_up, payload)
            require_post_put_roundtrip(probe_up)
            _no_https_object_bytes(later, payload)


# ---------------------------------------------------------------------------
# G. always: session cannot start → fail, do not start hybrid
# ---------------------------------------------------------------------------


def test_always_mode_fails_without_hybrid_when_transfer_session_cannot_be_established():
    """always plus a session that cannot start fails and does not start hybrid."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as down:
            probe = install_ssh_transfer_peer(
                down, mode="no_session", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(down, ssh_url, payload)
            configure_ssh_transfer_mode(down, "always")
            svc.stored[digest] = payload
            _gap_download(down, rel, digest)
            result = _fetch(down, ssh_env_updates(probe))
            print(
                f"G download exit={result.returncode} nhttp={len(svc.records)}"
            )
            assert result.returncode != 0, (
                "always download succeeded after git-orbulk-transfer session "
                "could not be established"
            )
            require_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            require_no_authenticate_invocation(probe.argv_log)
            require_no_http_exchanges(svc.records)
            require_object_absent(default_lfs_store_root(down), digest)
        svc.stored.clear()
        n0 = len(svc.records)
        with workspace() as up:
            probe_up = install_ssh_transfer_peer(
                up, mode="no_session", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest_up = _prepare(up, ssh_url, payload)
            configure_ssh_transfer_mode(up, "always")
            pushed = _push(up, ssh_env_updates(probe_up), digest_up)
            later = svc.records[n0:]
            print(f"G upload exit={pushed.returncode} nhttp={len(later)}")
            assert pushed.returncode != 0, (
                "always upload succeeded after git-orbulk-transfer session "
                "could not be established"
            )
            require_transfer_invocation(
                probe_up.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            require_no_authenticate_invocation(probe_up.argv_log)
            require_no_http_exchanges(later)


# ---------------------------------------------------------------------------
# H. always: working peer uses pure SSH and does not start hybrid
# ---------------------------------------------------------------------------


def test_always_mode_uses_pure_ssh_not_hybrid_https_when_peer_works():
    """always with a working peer moves bytes on SSH and does not start hybrid."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as down:
            probe = install_ssh_transfer_peer(
                down, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(down, ssh_url, payload)
            configure_ssh_transfer_mode(down, "always")
            _seed_peer(probe, payload)
            svc.stored[digest] = payload
            _gap_download(down, rel, digest)
            result = _fetch(down, ssh_env_updates(probe))
            print(
                f"H download exit={result.returncode} nhttp={len(svc.records)}"
            )
            assert_success(result)
            assert_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )
            assert_version_1_selected(probe)
            assert_ssh_channel_delivered(probe, payload)
            assert_object_bytes(default_lfs_store_root(down), digest, payload)
            assert_no_authenticate_invocation(probe.argv_log)
            assert_no_http_exchanges(svc.records)
        svc.stored.clear()
        n0 = len(svc.records)
        with workspace() as up:
            probe_up = install_ssh_transfer_peer(
                up, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest_up = _prepare(up, ssh_url, payload)
            configure_ssh_transfer_mode(up, "always")
            pushed = _push(up, ssh_env_updates(probe_up), digest_up)
            later = svc.records[n0:]
            print(f"H upload exit={pushed.returncode} nhttp={len(later)}")
            assert_success(pushed)
            assert_transfer_invocation(
                probe_up.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            assert_version_1_selected(probe_up)
            assert_ssh_peer_stored(probe_up, payload)
            assert_post_put_roundtrip(probe_up)
            assert_no_authenticate_invocation(probe_up.argv_log)
            assert_no_http_exchanges(later)


# ---------------------------------------------------------------------------
# I. Established-session download error packet: fail, no hybrid
# ---------------------------------------------------------------------------


def test_server_error_packet_on_established_session_fails_download_without_hybrid_fallback():
    """A download error packet after version 1 fails fetch and does not start hybrid."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as ok_ws:
            probe_ok = install_ssh_transfer_peer(
                ok_ws, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(ok_ws, ssh_url, payload)
            _seed_peer(probe_ok, payload)
            svc.stored[digest] = payload
            _gap_download(ok_ws, rel, digest)
            ok = _fetch(ok_ws, ssh_env_updates(probe_ok))
            print(f"I baseline exit={ok.returncode}")
            require_success(ok)
            require_ssh_channel_delivered(probe_ok, payload)
            require_object_bytes(default_lfs_store_root(ok_ws), digest, payload)
        n0 = len(svc.records)
        with workspace() as bad:
            probe = install_ssh_transfer_peer(
                bad, mode="download_error", authenticate_json=_auth_json(svc.url)
            )
            rel, digest = _prepare(bad, ssh_url, payload)
            _seed_peer(probe, payload)
            svc.stored[digest] = payload
            _gap_download(bad, rel, digest)
            result = _fetch(bad, ssh_env_updates(probe))
            later = svc.records[n0:]
            print(f"I error exit={result.returncode} nhttp={len(later)}")
            require_version_1_selected(probe)
            assert result.returncode != 0, (
                "download error packet on an established session still "
                "succeeded"
            )
            require_object_absent(default_lfs_store_root(bad), digest)
            require_no_authenticate_invocation(probe.argv_log)
            require_no_http_exchanges(later)
            require_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="download",
            )


# ---------------------------------------------------------------------------
# J. Post-put verification error: upload fails after peer stored bytes
# ---------------------------------------------------------------------------


def test_post_upload_verification_error_after_stored_bytes_fails_upload():
    """A verification-step error after the peer stored bytes fails the upload."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as ok_ws:
            probe_ok = install_ssh_transfer_peer(
                ok_ws, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest = _prepare(ok_ws, ssh_url, payload)
            ok = _push(ok_ws, ssh_env_updates(probe_ok), digest)
            print(f"J baseline exit={ok.returncode}")
            require_success(ok)
            require_ssh_peer_stored(probe_ok, payload)
            require_post_put_roundtrip(probe_ok)
        n0 = len(svc.records)
        with workspace() as bad:
            probe = install_ssh_transfer_peer(
                bad, mode="verify_error", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest = _prepare(bad, ssh_url, payload)
            result = _push(bad, ssh_env_updates(probe), digest)
            later = svc.records[n0:]
            print(f"J error exit={result.returncode} nhttp={len(later)}")
            assert result.returncode != 0, (
                "post-put verification error still left the upload successful"
            )
            require_ssh_peer_stored(probe, payload)
            require_post_put_roundtrip(probe)
            require_no_authenticate_invocation(probe.argv_log)
            require_no_http_exchanges(later)
            require_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )


# ---------------------------------------------------------------------------
# L. Put-step error packet: upload fails, no hybrid, peer need not store
# ---------------------------------------------------------------------------


def test_server_error_packet_on_upload_put_fails_without_hybrid_fallback():
    """A put-step error after version 1 fails upload and does not start hybrid."""
    payload = _payload()
    ssh_url, repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as ws:
            probe = install_ssh_transfer_peer(
                ws, mode="put_error", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest = _prepare(ws, ssh_url, payload)
            result = _push(ws, ssh_env_updates(probe), digest)
            print(f"L put-error exit={result.returncode} nhttp={len(svc.records)}")
            require_version_1_selected(probe)
            require_put_step_error(probe)
            assert result.returncode != 0, (
                "put-step error packet on an established session still "
                "succeeded"
            )
            require_no_authenticate_invocation(probe.argv_log)
            require_no_http_exchanges(svc.records)
            require_transfer_invocation(
                probe.argv_log,
                repo_path_fragment=repo_path,
                operation="upload",
            )
            _peer_lacks_payload(probe, payload)


# ---------------------------------------------------------------------------
# K. PATH negative control
# ---------------------------------------------------------------------------


def test_pure_ssh_transfer_fails_when_binary_removed_from_path():
    """A live SSH upload succeeds; the same entry fails when the binary is gone."""
    payload = _payload()
    ssh_url, _repo_path = ssh_style_remote()
    with storing_batch_server() as svc:
        with workspace() as ws:
            probe = install_ssh_transfer_peer(
                ws, mode="serve", authenticate_json=_auth_json(svc.url)
            )
            _rel_name, digest = _prepare(ws, ssh_url, payload)
            env = ssh_env_updates(probe)
            ok = _push(ws, env, digest)
            print(f"K baseline exit={ok.returncode}")
            require_success(ok)
            require_ssh_peer_stored(probe, payload)
            hidden = path_without_product_bin(ws.env)
            failed = _push(ws, {**env, "PATH": hidden}, digest)
            print(f"K absent-binary exit={failed.returncode} hidden={hidden!r}")
            assert failed.returncode != 0, (
                "push succeeded after the product binary was removed from PATH"
            )
            assert (failed.returncode, failed.stdout, failed.stderr) != (
                ok.returncode,
                ok.stdout,
                ok.stderr,
            ), (
                "absent-binary push was not distinguishable from a successful "
                "SSH upload"
            )
