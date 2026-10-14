# feature: F06
"""Endpoint discovery and authentication acceptance tests.

PRD: FP-06. Dedicated indications come from ``git orbulk env`` (FP-01).
Transfer contact and credentials are observed on fetch / push / lock
requests to loopback servers. Message wording, Endpoint= labels, and
exit-code numbers are not pinned.
"""

from __future__ import annotations

import json

from _harness import token, workspace
from _helpers import (
    TwoRemoteLayout,
    add_git_remote,
    caller_visible,
    contacts,
    dedicated_server_url,
    default_lfs_store_root,
    derived_https_endpoint,
    env_report,
    fake_ssh_authenticate,
    force_hybrid_ssh,
    indication_names,
    install_credential_helper,
    install_two_remote_layout,
    make_two_remote_layout,
    path_without_product_bin,
    prepare_tracked_commit,
    recording_api_server,
    records_include_basic,
    require_authenticate_invocation,
    require_git_config_set,
    require_request_carries_basic,
    require_success,
    runtime_http_url,
    sharded_object_rel,
)


def _origin_dedicated(report: str, origin_url: str, sibling_name: str) -> str:
    return dedicated_server_url(
        report,
        remote_name="origin",
        git_remote_url=origin_url,
        other_remote_name=sibling_name,
    )


def _sibling_dedicated(report: str, sibling_name: str, sibling_url: str) -> str:
    return dedicated_server_url(
        report,
        remote_name=sibling_name,
        git_remote_url=sibling_url,
        other_remote_name="origin",
    )


def _dedicated_pair(report: str, layout: TwoRemoteLayout) -> tuple[str, str]:
    origin = _origin_dedicated(
        report, layout.origin_url, layout.sibling_name
    )
    sibling = _sibling_dedicated(
        report, layout.sibling_name, layout.sibling_url
    )
    return origin, sibling


def _distinct_from_git_remote(observed: str, git_remote_url: str) -> None:
    """Dedicated indication must not be a Git-remote listing related fact."""
    assert observed.rstrip("/") != git_remote_url.rstrip("/"), (
        "dedicated indication of the Git Orbulk server URL that would be used "
        "must be distinct from a Git-remote listing"
    )


def _payload() -> bytes:
    return f"blob-{token()}\n".encode("utf-8")


def _tracked_rel() -> str:
    return f"payload_{token()}.bin"


def _remove_stored_object(ws, oid: str) -> None:
    path = default_lfs_store_root(ws) / sharded_object_rel(oid)
    try:
        path.unlink()
    except FileNotFoundError:
        raise AssertionError(
            f"cannot remove stored object; missing at {path}"
        ) from None
    except OSError as exc:
        raise AssertionError(
            f"cannot remove stored object at {path}: {exc}"
        ) from exc


def _current_branch(ws) -> str:
    result = ws.git(["rev-parse", "--abbrev-ref", "HEAD"])
    assert result.returncode == 0, (
        "git rev-parse --abbrev-ref HEAD failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    name = result.stdout_text.strip()
    assert name and name != "HEAD", (
        f"no current branch name: {result.stdout_text!r}"
    )
    return name


def _live_two_remote_layout(
    origin_base: str, sibling_base: str
) -> TwoRemoteLayout:
    return TwoRemoteLayout(
        origin_url=f"{origin_base.rstrip('/')}/{token()}/repo.git",
        sibling_name=f"sib_{token()}",
        sibling_url=f"{sibling_base.rstrip('/')}/{token()}/repo.git",
    )


def _layout_without_git_suffix() -> TwoRemoteLayout:
    return TwoRemoteLayout(
        origin_url=runtime_http_url("alpha", path=f"{token()}/repo"),
        sibling_name=f"sib_{token()}",
        sibling_url=runtime_http_url("beta", path=f"{token()}/repo"),
    )


def _https_host_path_from_ssh(ssh_url: str) -> str:
    """Translate an SSH-style Git remote into HTTPS host/path form (FP-06)."""
    if ssh_url.startswith("ssh://"):
        rest = ssh_url[len("ssh://") :]
        if "@" in rest:
            rest = rest.split("@", 1)[1]
        host, sep, path = rest.partition("/")
        assert sep, f"ssh URL has no path: {ssh_url!r}"
        if ":" in host:
            host = host.rsplit(":", 1)[0]
        return f"https://{host}/{path}"
    assert ":" in ssh_url, f"not an SSH-style Git remote: {ssh_url!r}"
    left, path = ssh_url.split(":", 1)
    host = left.split("@", 1)[-1]
    return f"https://{host}/{path}"


def _fast_fail_transfers(ws) -> None:
    require_git_config_set(ws, "lfs.transfer.maxretries", "1", local=True)
    require_git_config_set(ws, "lfs.transfer.maxretrydelay", "0", local=True)
    require_git_config_set(ws, "lfs.dialtimeout", "1", local=True)


def _embed_userinfo(url: str, username: str, password: str) -> str:
    assert "://" in url, f"not a URL: {url!r}"
    scheme, rest = url.split("://", 1)
    return f"{scheme}://{username}:{password}@{rest}"


def _require_names_override(observed: str, override: str, *, role: str) -> None:
    assert indication_names(observed, override), (
        f"{role} dedicated indication did not name the override {override!r}: "
        f"{observed!r}"
    )


def _require_contacted(records, url: str, *, role: str) -> None:
    hit = contacts(records, url_or_host=url)
    print(f"contact {role} url={url!r} hit={hit} n={len(records)}")
    assert hit, f"{role} endpoint was not contacted ({url!r})"


def _require_not_contacted(records, url: str, *, role: str) -> None:
    hit = contacts(records, url_or_host=url)
    print(f"contact {role} url={url!r} hit={hit} n={len(records)}")
    assert not hit, f"{role} endpoint was contacted unexpectedly ({url!r})"


# ---------------------------------------------------------------------------
# A. Default derivation
# ---------------------------------------------------------------------------


def test_https_remote_without_git_suffix_derives_info_lfs():
    """HTTPS remotes that do not end in .git pick up .git/info/lfs."""
    layout = _layout_without_git_suffix()
    expected_origin = derived_https_endpoint(layout.origin_url)
    expected_sibling = derived_https_endpoint(layout.sibling_url)
    with workspace() as ws:
        install_two_remote_layout(ws, layout)
        report = env_report(ws)
        origin, sibling = _dedicated_pair(report, layout)
    print(f"origin git={layout.origin_url!r} dedicated={origin!r}")
    print(f"expected origin={expected_origin!r}")
    _distinct_from_git_remote(origin, layout.origin_url)
    _distinct_from_git_remote(sibling, layout.sibling_url)
    assert indication_names(origin, expected_origin), (
        "dedicated indication did not name the .git/info/lfs derivation "
        f"for a remote without a .git suffix: {origin!r}"
    )
    assert indication_names(sibling, expected_sibling), (
        "sibling dedicated indication did not name the .git/info/lfs "
        f"derivation: {sibling!r}"
    )
    assert ".git.git/" not in expected_origin


def test_https_remote_already_ending_in_git_does_not_double_git():
    """HTTPS remotes that already end in .git must not become .git.git."""
    layout = make_two_remote_layout()
    expected_origin = derived_https_endpoint(layout.origin_url)
    expected_sibling = derived_https_endpoint(layout.sibling_url)
    assert layout.origin_url.rstrip("/").endswith(".git")
    assert ".git.git/" not in expected_origin
    with workspace() as ws:
        install_two_remote_layout(ws, layout)
        report = env_report(ws)
        origin, sibling = _dedicated_pair(report, layout)
    print(f"origin git={layout.origin_url!r} dedicated={origin!r}")
    print(f"expected origin={expected_origin!r}")
    _distinct_from_git_remote(origin, layout.origin_url)
    _distinct_from_git_remote(sibling, layout.sibling_url)
    assert indication_names(origin, expected_origin), (
        "dedicated indication did not name /info/lfs on a remote that "
        f"already ended in .git: {origin!r}"
    )
    assert indication_names(sibling, expected_sibling)
    assert ".git.git/" not in origin
    assert ".git.git/" not in sibling


def test_ssh_style_remote_translates_to_https_info_lfs(isolated_ws):
    """SSH-style Git remotes become HTTPS host/path plus .git/info/lfs."""
    isolated_ws.init_repo()
    host = f"{token()}.ssh.example.test"
    repo_path = f"{token()}/repo.git"
    ssh_url = f"git@{host}:{repo_path}"
    https_form = _https_host_path_from_ssh(ssh_url)
    expected = derived_https_endpoint(https_form)
    add_git_remote(isolated_ws, "origin", ssh_url)
    report = env_report(isolated_ws)
    origin = dedicated_server_url(
        report, remote_name="origin", git_remote_url=ssh_url
    )
    print(f"ssh remote={ssh_url!r} dedicated={origin!r} expected={expected!r}")
    _distinct_from_git_remote(origin, ssh_url)
    assert indication_names(origin, expected), (
        "SSH-style remote dedicated indication was not the HTTPS "
        f".git/info/lfs form: {origin!r}"
    )
    assert not origin.startswith("ssh://"), origin
    assert "git@" not in origin


def test_derived_indication_agrees_via_git_and_direct_binary(isolated_ws):
    """Direct binary env and git orbulk env name the same dedicated indication."""
    layout = make_two_remote_layout()
    install_two_remote_layout(isolated_ws, layout)
    via_git = require_success(isolated_ws.invoke_via_git(["env"]))
    direct = require_success(isolated_ws.invoke(["env"]))
    origin_git, sibling_git = _dedicated_pair(via_git.stdout_text, layout)
    origin_bin, sibling_bin = _dedicated_pair(direct.stdout_text, layout)
    print(f"via git origin={origin_git!r} direct origin={origin_bin!r}")
    _distinct_from_git_remote(origin_git, layout.origin_url)
    assert origin_git == origin_bin, (
        "direct binary env named a different origin dedicated indication"
    )
    assert sibling_git == sibling_bin, (
        "direct binary env named a different sibling dedicated indication"
    )
    assert indication_names(
        origin_git, derived_https_endpoint(layout.origin_url)
    )


# ---------------------------------------------------------------------------
# B. Repository / global / per-remote overrides
# ---------------------------------------------------------------------------


def test_repo_lfs_url_replaces_derivation_on_every_remote():
    """A repository LFS URL override replaces derivation on every remote."""
    layout = make_two_remote_layout()
    override = runtime_http_url("orepo")
    with workspace() as baseline:
        install_two_remote_layout(baseline, layout)
        base_origin, base_sibling = _dedicated_pair(env_report(baseline), layout)
    with workspace() as overridden:
        install_two_remote_layout(overridden, layout)
        require_git_config_set(overridden, "lfs.url", override, local=True)
        origin, sibling = _dedicated_pair(env_report(overridden), layout)
    print(f"override={override!r} origin={origin!r} sibling={sibling!r}")
    _distinct_from_git_remote(base_origin, layout.origin_url)
    _require_names_override(origin, override, role="origin")
    _require_names_override(sibling, override, role="sibling")
    assert origin != base_origin
    assert sibling != base_sibling
    assert not indication_names(origin, derived_https_endpoint(layout.origin_url))


def test_global_lfs_url_replaces_derivation_on_every_remote():
    """A global LFS URL override replaces derivation on every remote."""
    layout = make_two_remote_layout()
    override = runtime_http_url("oglobal")
    with workspace() as baseline:
        install_two_remote_layout(baseline, layout)
        base_origin, base_sibling = _dedicated_pair(env_report(baseline), layout)
    with workspace() as overridden:
        install_two_remote_layout(overridden, layout)
        require_git_config_set(overridden, "lfs.url", override, global_=True)
        origin, sibling = _dedicated_pair(env_report(overridden), layout)
    print(f"global override={override!r} origin={origin!r}")
    _distinct_from_git_remote(base_origin, layout.origin_url)
    _require_names_override(origin, override, role="origin")
    _require_names_override(sibling, override, role="sibling")
    assert origin != base_origin
    assert sibling != base_sibling


def test_override_echo_in_related_facts_is_not_replacement():
    """Stdout containing the override is not enough; dedicated must name it."""
    layout = make_two_remote_layout()
    override = runtime_http_url("echo")
    with workspace() as baseline:
        install_two_remote_layout(baseline, layout)
        base_origin, base_sibling = _dedicated_pair(env_report(baseline), layout)
    with workspace() as overridden:
        install_two_remote_layout(overridden, layout)
        require_git_config_set(overridden, "lfs.url", override, local=True)
        report = env_report(overridden)
        origin, sibling = _dedicated_pair(report, layout)
    print(f"stdout contains override={override in report}")
    _require_names_override(origin, override, role="origin")
    _require_names_override(sibling, override, role="sibling")
    assert origin != base_origin
    assert sibling != base_sibling


def test_per_remote_override_without_repo_url_spares_sibling():
    """A per-remote LFS URL changes only that remote when no repo/global URL."""
    layout = make_two_remote_layout()
    sib_override = runtime_http_url("psib")
    origin_override = runtime_http_url("porig")
    with workspace() as baseline:
        install_two_remote_layout(baseline, layout)
        base_origin, base_sibling = _dedicated_pair(env_report(baseline), layout)
    with workspace() as sib_only:
        install_two_remote_layout(sib_only, layout)
        require_git_config_set(
            sib_only,
            f"remote.{layout.sibling_name}.lfsurl",
            sib_override,
            local=True,
        )
        origin, sibling = _dedicated_pair(env_report(sib_only), layout)
    print(f"sib-only origin={origin!r} sibling={sibling!r}")
    _require_names_override(sibling, sib_override, role="sibling")
    assert origin == base_origin
    assert not indication_names(origin, sib_override)
    with workspace() as origin_only:
        install_two_remote_layout(origin_only, layout)
        require_git_config_set(
            origin_only,
            "remote.origin.lfsurl",
            origin_override,
            local=True,
        )
        origin, sibling = _dedicated_pair(env_report(origin_only), layout)
    _require_names_override(origin, origin_override, role="origin")
    assert sibling == base_sibling
    assert not indication_names(sibling, origin_override)


def test_repo_lfs_url_wins_over_per_remote_on_dedicated_indication():
    """Repository LFS URL replaces derivation even when a per-remote URL is set."""
    layout = make_two_remote_layout()
    repo_override = runtime_http_url("repo")
    sib_override = runtime_http_url("onlysib")
    with workspace() as per_only:
        install_two_remote_layout(per_only, layout)
        require_git_config_set(
            per_only,
            f"remote.{layout.sibling_name}.lfsurl",
            sib_override,
            local=True,
        )
        per_origin, per_sibling = _dedicated_pair(env_report(per_only), layout)
    with workspace() as combined:
        install_two_remote_layout(combined, layout)
        require_git_config_set(combined, "lfs.url", repo_override, local=True)
        require_git_config_set(
            combined,
            f"remote.{layout.sibling_name}.lfsurl",
            sib_override,
            local=True,
        )
        origin, sibling = _dedicated_pair(env_report(combined), layout)
    print(f"per-only sibling={per_sibling!r} combined sibling={sibling!r}")
    _require_names_override(per_sibling, sib_override, role="per-only sibling")
    _require_names_override(origin, repo_override, role="combined origin")
    _require_names_override(sibling, repo_override, role="combined sibling")
    assert not indication_names(origin, sib_override)
    assert not indication_names(sibling, sib_override)
    assert sibling != per_sibling


def test_global_lfs_url_wins_over_per_remote_on_dedicated_indication():
    """Global LFS URL replaces derivation even when a per-remote URL is set."""
    layout = make_two_remote_layout()
    global_override = runtime_http_url("gwin")
    sib_override = runtime_http_url("gsib")
    with workspace() as per_only:
        install_two_remote_layout(per_only, layout)
        require_git_config_set(
            per_only,
            f"remote.{layout.sibling_name}.lfsurl",
            sib_override,
            local=True,
        )
        _per_origin, per_sibling = _dedicated_pair(env_report(per_only), layout)
    with workspace() as combined:
        install_two_remote_layout(combined, layout)
        require_git_config_set(
            combined, "lfs.url", global_override, global_=True
        )
        require_git_config_set(
            combined,
            f"remote.{layout.sibling_name}.lfsurl",
            sib_override,
            local=True,
        )
        origin, sibling = _dedicated_pair(env_report(combined), layout)
    print(f"global win origin={origin!r} sibling={sibling!r}")
    _require_names_override(per_sibling, sib_override, role="per-only sibling")
    _require_names_override(origin, global_override, role="combined origin")
    _require_names_override(sibling, global_override, role="combined sibling")
    assert not indication_names(sibling, sib_override)
    assert sibling != per_sibling


# ---------------------------------------------------------------------------
# C. Push URL: dedicated stays download; upload contacts another host
# ---------------------------------------------------------------------------


def test_push_url_does_not_replace_dedicated_download_indication():
    """A push URL override leaves the dedicated download indication unchanged."""
    download = runtime_http_url("dl")
    upload = runtime_http_url("ul")
    layout = make_two_remote_layout()
    with workspace() as baseline:
        install_two_remote_layout(baseline, layout)
        require_git_config_set(baseline, "lfs.url", download, local=True)
        base_origin, base_sibling = _dedicated_pair(env_report(baseline), layout)
    with workspace() as with_push:
        install_two_remote_layout(with_push, layout)
        require_git_config_set(with_push, "lfs.url", download, local=True)
        require_git_config_set(with_push, "lfs.pushurl", upload, local=True)
        origin, sibling = _dedicated_pair(env_report(with_push), layout)
    print(f"download={download!r} upload={upload!r} origin={origin!r}")
    _require_names_override(base_origin, download, role="baseline origin")
    _require_names_override(origin, download, role="push-url origin")
    _require_names_override(sibling, download, role="push-url sibling")
    assert not indication_names(origin, upload)
    assert not indication_names(sibling, upload)
    assert origin == base_origin
    assert sibling == base_sibling


def test_push_url_makes_upload_contact_different_endpoint_than_download():
    """Upload contacts the push URL host; download still contacts the LFS URL."""
    with recording_api_server() as (download_url, download_recs):
        with recording_api_server() as (upload_url, upload_recs):
            layout = make_two_remote_layout()
            with workspace() as split:
                install_two_remote_layout(split, layout)
                require_git_config_set(
                    split, "lfs.url", download_url, local=True
                )
                require_git_config_set(
                    split, "lfs.pushurl", upload_url, local=True
                )
                rel = _tracked_rel()
                digest = prepare_tracked_commit(split, rel, _payload())
                pushed = split.invoke_via_git(
                    ["push", "--object-id", "origin", digest]
                )
                print(
                    f"split push exit={pushed.returncode} "
                    f"upload_n={len(upload_recs)} download_n={len(download_recs)}"
                )
                _require_contacted(upload_recs, upload_url, role="upload")
                download_before = list(download_recs)
                _remove_stored_object(split, digest)
                fetched = split.invoke_via_git(["fetch"])
                print(f"split fetch exit={fetched.returncode}")
                assert len(download_recs) > len(download_before), (
                    "download path did not contact the download endpoint"
                )
                _require_contacted(
                    download_recs, download_url, role="download"
                )
            download_recs.clear()
            upload_recs.clear()
            with workspace() as unified:
                install_two_remote_layout(unified, layout)
                require_git_config_set(
                    unified, "lfs.url", download_url, local=True
                )
                rel = _tracked_rel()
                digest = prepare_tracked_commit(unified, rel, _payload())
                pushed = unified.invoke_via_git(
                    ["push", "--object-id", "origin", digest]
                )
                print(f"unified push exit={pushed.returncode}")
                _require_contacted(
                    download_recs, download_url, role="unified-upload"
                )
                _require_not_contacted(
                    upload_recs, upload_url, role="unified-upload-other"
                )


def test_per_remote_push_url_same_download_vs_upload_split():
    """A per-remote push URL splits upload from that remote's download URL."""
    with recording_api_server() as (download_url, download_recs):
        with recording_api_server() as (upload_url, upload_recs):
            with workspace() as ws:
                ws.init_repo()
                origin_git = f"{download_url}/{token()}/repo.git"
                add_git_remote(ws, "origin", origin_git)
                require_git_config_set(
                    ws, "remote.origin.lfsurl", download_url, local=True
                )
                require_git_config_set(
                    ws, "remote.origin.lfspushurl", upload_url, local=True
                )
                rel = _tracked_rel()
                digest = prepare_tracked_commit(ws, rel, _payload())
                report = env_report(ws)
                origin = dedicated_server_url(
                    report,
                    remote_name="origin",
                    git_remote_url=origin_git,
                )
                print(f"per-remote dedicated={origin!r}")
                assert indication_names(origin, download_url), (
                    "dedicated indication did not remain the download URL "
                    f"after a per-remote push URL: {origin!r}"
                )
                assert not indication_names(origin, upload_url)
                pushed = ws.invoke_via_git(
                    ["push", "--object-id", "origin", digest]
                )
                print(f"per-remote push exit={pushed.returncode}")
                _require_contacted(upload_recs, upload_url, role="per-remote-upload")
                download_before = len(download_recs)
                _remove_stored_object(ws, digest)
                fetched = ws.invoke_via_git(["fetch"])
                print(f"per-remote fetch exit={fetched.returncode}")
                assert len(download_recs) > download_before
                _require_contacted(
                    download_recs, download_url, role="per-remote-download"
                )


# ---------------------------------------------------------------------------
# D. Default remote selection (transfer path; no explicit remote name)
# ---------------------------------------------------------------------------


def test_branch_remote_selects_that_remote_for_fetch():
    """Current branch remote, when set, is the fetch remote."""
    with recording_api_server() as (origin_url, origin_recs):
        with recording_api_server() as (sib_url, sib_recs):
            layout = _live_two_remote_layout(origin_url, sib_url)
            with workspace() as selected:
                install_two_remote_layout(selected, layout)
                rel = _tracked_rel()
                digest = prepare_tracked_commit(selected, rel, _payload())
                branch = _current_branch(selected)
                require_git_config_set(
                    selected,
                    f"branch.{branch}.remote",
                    layout.sibling_name,
                    local=True,
                )
                _remove_stored_object(selected, digest)
                selected.invoke_via_git(["fetch"])
                _require_contacted(sib_recs, sib_url, role="branch-remote")
                _require_not_contacted(
                    origin_recs, origin_url, role="branch-remote-origin"
                )
            origin_recs.clear()
            sib_recs.clear()
            with workspace() as unset:
                install_two_remote_layout(unset, layout)
                rel = _tracked_rel()
                digest = prepare_tracked_commit(unset, rel, _payload())
                _remove_stored_object(unset, digest)
                unset.invoke_via_git(["fetch"])
                _require_contacted(origin_recs, origin_url, role="no-branch-origin")
                _require_not_contacted(
                    sib_recs, sib_url, role="no-branch-sibling"
                )


def test_lfs_default_remote_used_when_branch_remote_unset():
    """Configured LFS default remote is used when branch remote is unset."""
    with recording_api_server() as (origin_url, origin_recs):
        with recording_api_server() as (sib_url, sib_recs):
            layout = _live_two_remote_layout(origin_url, sib_url)
            with workspace() as selected:
                install_two_remote_layout(selected, layout)
                rel = _tracked_rel()
                digest = prepare_tracked_commit(selected, rel, _payload())
                require_git_config_set(
                    selected,
                    "remote.lfsdefault",
                    layout.sibling_name,
                    local=True,
                )
                _remove_stored_object(selected, digest)
                selected.invoke_via_git(["fetch"])
                _require_contacted(sib_recs, sib_url, role="lfsdefault")
                _require_not_contacted(
                    origin_recs, origin_url, role="lfsdefault-origin"
                )
            origin_recs.clear()
            sib_recs.clear()
            with workspace() as unset:
                install_two_remote_layout(unset, layout)
                rel = _tracked_rel()
                digest = prepare_tracked_commit(unset, rel, _payload())
                _remove_stored_object(unset, digest)
                unset.invoke_via_git(["fetch"])
                _require_contacted(
                    origin_recs, origin_url, role="no-lfsdefault-origin"
                )
                _require_not_contacted(
                    sib_recs, sib_url, role="no-lfsdefault-sibling"
                )


def test_branch_remote_wins_over_lfs_default_when_both_set():
    """When both knobs are set, fetch follows the branch remote, not lfsdefault."""
    with recording_api_server() as (origin_url, origin_recs):
        with recording_api_server() as (sib_url, sib_recs):
            layout = _live_two_remote_layout(origin_url, sib_url)
            with workspace() as branch_wins:
                install_two_remote_layout(branch_wins, layout)
                rel = _tracked_rel()
                digest = prepare_tracked_commit(branch_wins, rel, _payload())
                branch = _current_branch(branch_wins)
                require_git_config_set(
                    branch_wins,
                    f"branch.{branch}.remote",
                    layout.sibling_name,
                    local=True,
                )
                require_git_config_set(
                    branch_wins, "remote.lfsdefault", "origin", local=True
                )
                _remove_stored_object(branch_wins, digest)
                branch_wins.invoke_via_git(["fetch"])
                _require_contacted(
                    sib_recs, sib_url, role="both-set-branch-wins"
                )
                _require_not_contacted(
                    origin_recs, origin_url, role="both-set-lfsdefault"
                )
            origin_recs.clear()
            sib_recs.clear()
            with workspace() as swapped:
                install_two_remote_layout(swapped, layout)
                rel = _tracked_rel()
                digest = prepare_tracked_commit(swapped, rel, _payload())
                branch = _current_branch(swapped)
                require_git_config_set(
                    swapped, f"branch.{branch}.remote", "origin", local=True
                )
                require_git_config_set(
                    swapped,
                    "remote.lfsdefault",
                    layout.sibling_name,
                    local=True,
                )
                _remove_stored_object(swapped, digest)
                swapped.invoke_via_git(["fetch"])
                _require_contacted(
                    origin_recs, origin_url, role="swapped-branch-origin"
                )
                _require_not_contacted(
                    sib_recs, sib_url, role="swapped-lfsdefault-sibling"
                )


def test_single_non_origin_remote_is_selected():
    """A sole existing remote is selected even when it is not named origin."""
    with recording_api_server() as (only_url, only_recs):
        with recording_api_server() as (origin_url, origin_recs):
            only_name = f"only_{token()}"
            only_git = f"{only_url.rstrip('/')}/{token()}/repo.git"
            origin_git = f"{origin_url.rstrip('/')}/{token()}/repo.git"
            with workspace() as sole:
                sole.init_repo()
                add_git_remote(sole, only_name, only_git)
                rel = _tracked_rel()
                digest = prepare_tracked_commit(sole, rel, _payload())
                _remove_stored_object(sole, digest)
                sole.invoke_via_git(["fetch"])
                _require_contacted(only_recs, only_url, role="sole-remote")
                _require_not_contacted(
                    origin_recs, origin_url, role="sole-unused-origin-server"
                )
            only_recs.clear()
            origin_recs.clear()
            with workspace() as both:
                both.init_repo()
                add_git_remote(both, only_name, only_git)
                add_git_remote(both, "origin", origin_git)
                rel = _tracked_rel()
                digest = prepare_tracked_commit(both, rel, _payload())
                _remove_stored_object(both, digest)
                both.invoke_via_git(["fetch"])
                _require_contacted(
                    origin_recs, origin_url, role="two-remote-origin"
                )
                _require_not_contacted(
                    only_recs, only_url, role="two-remote-non-origin"
                )


def test_two_remotes_fall_back_to_origin():
    """Two remotes and no higher knob: fetch uses origin."""
    with recording_api_server() as (origin_url, origin_recs):
        with recording_api_server() as (sib_url, sib_recs):
            layout = _live_two_remote_layout(origin_url, sib_url)
            with workspace() as ws:
                install_two_remote_layout(ws, layout)
                rel = _tracked_rel()
                digest = prepare_tracked_commit(ws, rel, _payload())
                _remove_stored_object(ws, digest)
                ws.invoke_via_git(["fetch"])
            _require_contacted(origin_recs, origin_url, role="fallback-origin")
            _require_not_contacted(sib_recs, sib_url, role="fallback-sibling")


def test_push_default_remote_analogous_selection():
    """Push-default remote (lfspushdefault) selects the upload/lock endpoint."""
    with recording_api_server() as (origin_url, origin_recs):
        with recording_api_server() as (sib_url, sib_recs):
            layout = _live_two_remote_layout(origin_url, sib_url)
            with workspace() as selected:
                install_two_remote_layout(selected, layout)
                rel = _tracked_rel()
                prepare_tracked_commit(selected, rel, _payload())
                require_git_config_set(
                    selected,
                    "remote.lfspushdefault",
                    layout.sibling_name,
                    local=True,
                )
                selected.invoke_via_git(["lock", rel])
                _require_contacted(sib_recs, sib_url, role="lfspushdefault")
                _require_not_contacted(
                    origin_recs, origin_url, role="lfspushdefault-origin"
                )
            origin_recs.clear()
            sib_recs.clear()
            with workspace() as unset:
                install_two_remote_layout(unset, layout)
                rel = _tracked_rel()
                prepare_tracked_commit(unset, rel, _payload())
                unset.invoke_via_git(["lock", rel])
                _require_contacted(
                    origin_recs, origin_url, role="no-lfspushdefault-origin"
                )
                _require_not_contacted(
                    sib_recs, sib_url, role="no-lfspushdefault-sibling"
                )


def test_push_remote_wins_over_lfs_push_default_when_both_set():
    """branch pushRemote wins over lfspushdefault when both are set."""
    with recording_api_server() as (origin_url, origin_recs):
        with recording_api_server() as (sib_url, sib_recs):
            layout = _live_two_remote_layout(origin_url, sib_url)
            with workspace() as branch_wins:
                install_two_remote_layout(branch_wins, layout)
                rel = _tracked_rel()
                prepare_tracked_commit(branch_wins, rel, _payload())
                branch = _current_branch(branch_wins)
                require_git_config_set(
                    branch_wins,
                    f"branch.{branch}.pushRemote",
                    layout.sibling_name,
                    local=True,
                )
                require_git_config_set(
                    branch_wins,
                    "remote.lfspushdefault",
                    "origin",
                    local=True,
                )
                branch_wins.invoke_via_git(["lock", rel])
                _require_contacted(
                    sib_recs, sib_url, role="pushRemote-wins"
                )
                _require_not_contacted(
                    origin_recs, origin_url, role="lfspushdefault-loses"
                )
            origin_recs.clear()
            sib_recs.clear()
            with workspace() as swapped:
                install_two_remote_layout(swapped, layout)
                rel = _tracked_rel()
                prepare_tracked_commit(swapped, rel, _payload())
                branch = _current_branch(swapped)
                require_git_config_set(
                    swapped,
                    f"branch.{branch}.pushRemote",
                    "origin",
                    local=True,
                )
                require_git_config_set(
                    swapped,
                    "remote.lfspushdefault",
                    layout.sibling_name,
                    local=True,
                )
                swapped.invoke_via_git(["lock", rel])
                _require_contacted(
                    origin_recs, origin_url, role="swapped-pushRemote-origin"
                )
                _require_not_contacted(
                    sib_recs, sib_url, role="swapped-lfspushdefault-sibling"
                )


# ---------------------------------------------------------------------------
# E. Hybrid path git-orbulk-authenticate
# ---------------------------------------------------------------------------


def _ssh_remote_and_path() -> tuple[str, str]:
    host = f"{token()}.ssh.example.test"
    repo_path = f"{token()}/repo.git"
    return f"git@{host}:{repo_path}", repo_path


def test_ssh_hybrid_runs_authenticate_with_path_and_download():
    """Fetch on the hybrid path runs git-orbulk-authenticate with download."""
    ssh_url, repo_path = _ssh_remote_and_path()
    with recording_api_server() as (api_url, records):
        with workspace() as ws:
            ws.init_repo()
            add_git_remote(ws, "origin", ssh_url)
            force_hybrid_ssh(ws)
            payload = json.dumps({"href": api_url, "header": {}})
            env, log_path = fake_ssh_authenticate(ws.home, stdout_json=payload)
            rel = _tracked_rel()
            digest = prepare_tracked_commit(ws, rel, _payload())
            _remove_stored_object(ws, digest)
            result = ws.invoke_via_git(["fetch"], env_updates=env)
            print(f"hybrid fetch exit={result.returncode}")
            require_authenticate_invocation(
                log_path, repo_path_fragment=repo_path, operation="download"
            )
            _require_contacted(records, api_url, role="hybrid-download")


def test_ssh_hybrid_authenticate_upload_operation_on_push():
    """Push on the hybrid path runs git-orbulk-authenticate with upload."""
    ssh_url, repo_path = _ssh_remote_and_path()
    with recording_api_server() as (api_url, records):
        with workspace() as ws:
            ws.init_repo()
            add_git_remote(ws, "origin", ssh_url)
            force_hybrid_ssh(ws)
            payload = json.dumps({"href": api_url, "header": {}})
            env, log_path = fake_ssh_authenticate(ws.home, stdout_json=payload)
            rel = _tracked_rel()
            digest = prepare_tracked_commit(ws, rel, _payload())
            result = ws.invoke_via_git(
                ["push", "--object-id", "origin", digest], env_updates=env
            )
            print(f"hybrid push exit={result.returncode}")
            require_authenticate_invocation(
                log_path, repo_path_fragment=repo_path, operation="upload"
            )
            _require_contacted(records, api_url, role="hybrid-upload")


def test_authenticate_headers_attached_to_subsequent_api_request():
    """Helper JSON authorization headers are attached to later API requests."""
    ssh_url, repo_path = _ssh_remote_and_path()
    token_a = f"tok_{token()}"
    token_b = f"tok_{token()}"
    with recording_api_server() as (api_url, records_a):
        with workspace() as ws_a:
            ws_a.init_repo()
            add_git_remote(ws_a, "origin", ssh_url)
            force_hybrid_ssh(ws_a)
            payload = json.dumps(
                {
                    "href": api_url,
                    "header": {"Authorization": f"Bearer {token_a}"},
                }
            )
            env, log_path = fake_ssh_authenticate(
                ws_a.home, stdout_json=payload
            )
            rel = _tracked_rel()
            digest = prepare_tracked_commit(ws_a, rel, _payload())
            _remove_stored_object(ws_a, digest)
            ws_a.invoke_via_git(["fetch"], env_updates=env)
            require_authenticate_invocation(
                log_path, repo_path_fragment=repo_path, operation="download"
            )
            auths_a = [rec.authorization for rec in records_a if rec.authorization]
            print(f"headers A={auths_a!r}")
            assert any(token_a in auth for auth in auths_a), (
                "helper authorization material was not attached to the "
                f"API request: {auths_a!r}"
            )
            assert not any(token_b in auth for auth in auths_a)
    with recording_api_server() as (api_url, records_b):
        with workspace() as ws_b:
            ws_b.init_repo()
            add_git_remote(ws_b, "origin", ssh_url)
            force_hybrid_ssh(ws_b)
            payload = json.dumps(
                {
                    "href": api_url,
                    "header": {"Authorization": f"Bearer {token_b}"},
                }
            )
            env, log_path = fake_ssh_authenticate(
                ws_b.home, stdout_json=payload
            )
            rel = _tracked_rel()
            digest = prepare_tracked_commit(ws_b, rel, _payload())
            _remove_stored_object(ws_b, digest)
            ws_b.invoke_via_git(["fetch"], env_updates=env)
            auths_b = [rec.authorization for rec in records_b if rec.authorization]
            print(f"headers B={auths_b!r}")
            assert any(token_b in auth for auth in auths_b), (
                "second helper token was not attached to the API request"
            )
            assert not any(token_a in auth for auth in auths_b)
            assert auths_a != auths_b


def test_authenticate_alternate_url_used_instead_of_derived_https():
    """When helper JSON names an alternate URL, later requests use that URL."""
    ssh_url, repo_path = _ssh_remote_and_path()
    with recording_api_server() as (alt_url, alt_recs):
        with recording_api_server() as (other_url, other_recs):
            with workspace() as named:
                named.init_repo()
                add_git_remote(named, "origin", ssh_url)
                force_hybrid_ssh(named)
                payload = json.dumps({"href": alt_url, "header": {}})
                env, log_path = fake_ssh_authenticate(
                    named.home, stdout_json=payload
                )
                rel = _tracked_rel()
                digest = prepare_tracked_commit(named, rel, _payload())
                _remove_stored_object(named, digest)
                named.invoke_via_git(["fetch"], env_updates=env)
                require_authenticate_invocation(
                    log_path,
                    repo_path_fragment=repo_path,
                    operation="download",
                )
                _require_contacted(alt_recs, alt_url, role="alternate")
                _require_not_contacted(
                    other_recs, other_url, role="unused-other"
                )
            alt_recs.clear()
            other_recs.clear()
            with workspace() as unnamed:
                unnamed.init_repo()
                add_git_remote(unnamed, "origin", ssh_url)
                force_hybrid_ssh(unnamed)
                payload = json.dumps({"header": {"Authorization": f"t_{token()}"}})
                env, log_path = fake_ssh_authenticate(
                    unnamed.home, stdout_json=payload
                )
                rel = _tracked_rel()
                digest = prepare_tracked_commit(unnamed, rel, _payload())
                _remove_stored_object(unnamed, digest)
                unnamed.invoke_via_git(["fetch"], env_updates=env)
                require_authenticate_invocation(
                    log_path,
                    repo_path_fragment=repo_path,
                    operation="download",
                )
                _require_not_contacted(
                    alt_recs, alt_url, role="no-href-alternate"
                )
                _require_not_contacted(
                    other_recs, other_url, role="no-href-other"
                )


def test_failed_authenticate_surfaces_helper_stderr_and_fails():
    """A failing authenticate helper fails the transfer and surfaces its stderr."""
    ssh_url, repo_path = _ssh_remote_and_path()
    marker = f"ssherr_{token()}"
    with recording_api_server() as (api_url, success_recs):
        with workspace() as ok_ws:
            ok_ws.init_repo()
            add_git_remote(ok_ws, "origin", ssh_url)
            force_hybrid_ssh(ok_ws)
            payload = json.dumps({"href": api_url, "header": {}})
            env, log_path = fake_ssh_authenticate(
                ok_ws.home, stdout_json=payload
            )
            rel = _tracked_rel()
            digest = prepare_tracked_commit(ok_ws, rel, _payload())
            _remove_stored_object(ok_ws, digest)
            ok_ws.invoke_via_git(["fetch"], env_updates=env)
            require_authenticate_invocation(
                log_path, repo_path_fragment=repo_path, operation="download"
            )
            _require_contacted(success_recs, api_url, role="success-helper")
        with workspace() as fail_ws:
            fail_ws.init_repo()
            add_git_remote(fail_ws, "origin", ssh_url)
            force_hybrid_ssh(fail_ws)
            env, log_path = fake_ssh_authenticate(
                fail_ws.home,
                stdout_json="",
                stderr_text=marker + "\n",
                exit_code=1,
            )
            rel = _tracked_rel()
            digest = prepare_tracked_commit(fail_ws, rel, _payload())
            _remove_stored_object(fail_ws, digest)
            failed = fail_ws.invoke_via_git(["fetch"], env_updates=env)
            visible = caller_visible(failed)
            print(f"failed authenticate exit={failed.returncode} visible={visible!r}")
            require_authenticate_invocation(
                log_path, repo_path_fragment=repo_path, operation="download"
            )
            assert failed.returncode != 0, (
                "failed git-orbulk-authenticate still exited 0"
            )
            assert marker in visible, (
                "helper stderr token was not surfaced to the caller"
            )


# ---------------------------------------------------------------------------
# F. HTTPS credentials
# ---------------------------------------------------------------------------


def test_https_uses_credential_helper_material_on_api_request():
    """Git credential helper username/password are sent as HTTP Basic."""
    user = f"u_{token()}"
    password = f"p_{token()}"
    with recording_api_server(
        accepted_user=user, accepted_password=password
    ) as (url, records):
        with workspace() as ws:
            ws.init_repo()
            add_git_remote(ws, "origin", f"{url}/{token()}/repo.git")
            install_credential_helper(ws, user, password)
            rel = _tracked_rel()
            digest = prepare_tracked_commit(ws, rel, _payload())
            _remove_stored_object(ws, digest)
            result = ws.invoke_via_git(["fetch"])
            print(f"cred-helper fetch exit={result.returncode} n={len(records)}")
            rec = require_request_carries_basic(records, user, password)
            print(f"matching basic status={rec.status}")
            assert rec.status == 200, (
                "matching Basic was not accepted at the HTTP layer"
            )


def test_url_embedded_credentials_are_used():
    """Credentials embedded in the URL are sent even without a helper."""
    user = f"u_{token()}"
    password = f"p_{token()}"
    with recording_api_server(
        accepted_user=user, accepted_password=password
    ) as (url, records):
        embedded = _embed_userinfo(f"{url}/{token()}/repo.git", user, password)
        with workspace() as ws:
            ws.init_repo()
            add_git_remote(ws, "origin", embedded)
            rel = _tracked_rel()
            digest = prepare_tracked_commit(ws, rel, _payload())
            _remove_stored_object(ws, digest)
            result = ws.invoke_via_git(["fetch"])
            print(f"embedded fetch exit={result.returncode} n={len(records)}")
            rec = require_request_carries_basic(records, user, password)
            assert rec.status == 200


def test_missing_credentials_fail_nonzero_unlike_authenticated_path():
    """Missing credentials fail non-zero; they are not a silent skip."""
    user = f"u_{token()}"
    password = f"p_{token()}"
    with recording_api_server(
        accepted_user=user, accepted_password=password
    ) as (url, records):
        with workspace() as accepted:
            accepted.init_repo()
            add_git_remote(accepted, "origin", f"{url}/{token()}/repo.git")
            install_credential_helper(accepted, user, password)
            rel = _tracked_rel()
            digest = prepare_tracked_commit(accepted, rel, _payload())
            _remove_stored_object(accepted, digest)
            accepted.invoke_via_git(["fetch"])
            rec = require_request_carries_basic(records, user, password)
            assert rec.status == 200
        accepted_n = len(records)
        with workspace() as missing:
            missing.init_repo()
            add_git_remote(missing, "origin", f"{url}/{token()}/repo.git")
            rel = _tracked_rel()
            digest = prepare_tracked_commit(missing, rel, _payload())
            _remove_stored_object(missing, digest)
            failed = missing.invoke_via_git(["fetch"])
            print(
                f"missing creds exit={failed.returncode} "
                f"records after={len(records)} (accepted_n={accepted_n})"
            )
            assert failed.returncode != 0, (
                "missing credentials exited 0 as if the transfer succeeded"
            )
            later = records[accepted_n:]
            assert not records_include_basic(later, user, password), (
                "missing-credentials path sent the accepted Basic pair"
            )


def test_invalid_credentials_fail_nonzero_unlike_accepted_path():
    """Non-matching Basic is refused at HTTP and the command exits non-zero."""
    user = f"u_{token()}"
    good = f"p_{token()}"
    bad = f"p_{token()}"
    assert good != bad
    with recording_api_server(
        accepted_user=user, accepted_password=good
    ) as (url, records):
        with workspace() as accepted:
            accepted.init_repo()
            add_git_remote(accepted, "origin", f"{url}/{token()}/repo.git")
            install_credential_helper(accepted, user, good)
            rel = _tracked_rel()
            digest = prepare_tracked_commit(accepted, rel, _payload())
            _remove_stored_object(accepted, digest)
            accepted.invoke_via_git(["fetch"])
            rec_ok = require_request_carries_basic(records, user, good)
            assert rec_ok.status == 200
        accepted_n = len(records)
        with workspace() as invalid:
            invalid.init_repo()
            add_git_remote(invalid, "origin", f"{url}/{token()}/repo.git")
            install_credential_helper(invalid, user, bad)
            rel = _tracked_rel()
            digest = prepare_tracked_commit(invalid, rel, _payload())
            _remove_stored_object(invalid, digest)
            failed = invalid.invoke_via_git(["fetch"])
            later = records[accepted_n:]
            print(
                f"invalid creds exit={failed.returncode} later_n={len(later)}"
            )
            rec_bad = require_request_carries_basic(later, user, bad)
            assert rec_bad.status != 200, (
                "non-matching Basic was accepted at the HTTP layer"
            )
            assert failed.returncode != 0, (
                "invalid credentials exited 0 as if the transfer succeeded"
            )


# ---------------------------------------------------------------------------
# G. Empty underivable endpoint
# ---------------------------------------------------------------------------


def test_empty_underivable_endpoint_fails_before_pretending_transfer_succeeded():
    """No remote and no LFS URL: fetch fails and does not invent an HTTP target."""
    with recording_api_server() as (url, records):
        with workspace() as reachable:
            reachable.init_repo()
            add_git_remote(reachable, "origin", f"{url}/{token()}/repo.git")
            rel = _tracked_rel()
            digest = prepare_tracked_commit(reachable, rel, _payload())
            _remove_stored_object(reachable, digest)
            reachable.invoke_via_git(["fetch"])
            _require_contacted(records, url, role="reachable-baseline")
        baseline_n = len(records)
        with workspace() as empty:
            empty.init_repo()
            rel = _tracked_rel()
            digest = prepare_tracked_commit(empty, rel, _payload())
            _remove_stored_object(empty, digest)
            _fast_fail_transfers(empty)
            failed = empty.invoke_via_git(["fetch"])
            print(
                f"empty endpoint exit={failed.returncode} "
                f"records={len(records)} baseline_n={baseline_n}"
            )
            assert failed.returncode != 0, (
                "empty underivable endpoint exited 0 as if a transfer succeeded"
            )
            assert len(records) == baseline_n, (
                "empty-endpoint fetch contacted a test HTTP server"
            )


# ---------------------------------------------------------------------------
# H. Negative control
# ---------------------------------------------------------------------------


def test_fetch_fails_when_binary_removed_from_path(isolated_ws, product_binary):
    """Removing the binary from PATH makes the env entry fail (PRD core capabilities)."""
    isolated_ws.init_repo()
    present = isolated_ws.invoke_via_git(["env"])
    require_success(present)
    hidden_path = path_without_product_bin(isolated_ws.env)
    missing = isolated_ws.invoke_via_git(
        ["env"], env_updates={"PATH": hidden_path}
    )
    print(
        f"product_binary={product_binary} hidden_path={hidden_path!r} "
        f"absent-env exit={missing.returncode}"
    )
    assert missing.returncode != 0, (
        "git orbulk env succeeded after the product binary was removed from PATH"
    )
    assert (missing.returncode, missing.stdout, missing.stderr) != (
        present.returncode,
        present.stdout,
        present.stderr,
    ), "absent-binary env was not distinguishable from env with the binary"
