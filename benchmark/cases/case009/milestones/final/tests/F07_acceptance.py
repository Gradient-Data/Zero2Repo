# feature: F07
"""Batch negotiation and basic object transfer acceptance tests.

PRD: FP-07. Fetch and push exercise HTTP batch POST plus basic GET/PUT.
Message wording, exit-code numbers, PUT Content-Type, verify HTTP method,
charset as a required client parameter, and exact advertised adapter-list
equality are not pinned.
"""

from __future__ import annotations

from _harness import token, workspace
from _helpers import (
    assert_advanced_advertised,
    assert_basic_only_or_omitted,
    assert_batch_post,
    assert_get_of_href,
    assert_no_put_of,
    assert_object_bytes,
    assert_put_of,
    commit_tracked_payload,
    conforming_batch_server,
    configure_concurrent_transfers,
    contract_basic_adapter_name,
    contract_objects_batch_path,
    contract_tus_adapter_name,
    default_lfs_store_root,
    enable_basic_transfers_only,
    enable_tus_transfers,
    path_without_product_bin,
    point_lfs_at,
    prepare_tracked_commit,
    remove_stored_object,
    require_advanced_advertised,
    require_basic_only_or_omitted,
    require_batch_post,
    require_bound_prevents_overlap_unlike_unbounded,
    require_get_of_href,
    require_href_contacted_after_put,
    require_named_media_type,
    require_no_put_of,
    require_object_absent,
    require_object_bytes,
    require_put_of,
    require_success,
    sha256_hex,
)


def _payload() -> bytes:
    return f"blob-{token()}\n".encode("utf-8")


def _tracked_rel() -> str:
    return f"payload_{token()}.bin"


def _ci_header(headers: dict[str, str], name: str) -> str | None:
    want = name.casefold()
    for key, value in headers.items():
        if key.casefold() == want:
            return value
    return None


def _setup_one(ws, svc, payload: bytes, *, for_download: bool) -> str:
    ws.init_repo()
    point_lfs_at(ws, svc.url)
    digest = prepare_tracked_commit(ws, _tracked_rel(), payload)
    if for_download:
        remove_stored_object(ws, digest)
        require_object_absent(default_lfs_store_root(ws), digest)
    return digest


def _setup_two(
    ws, svc, payloads: list[bytes], *, for_download: bool
) -> list[str]:
    ws.init_repo()
    point_lfs_at(ws, svc.url)
    digests: list[str] = []
    for index, data in enumerate(payloads):
        rel = _tracked_rel()
        if index == 0:
            digest = prepare_tracked_commit(ws, rel, data)
        else:
            digest = commit_tracked_payload(ws, rel, data)
        digests.append(digest)
    if for_download:
        for digest in digests:
            remove_stored_object(ws, digest)
            require_object_absent(default_lfs_store_root(ws), digest)
    return digests


# ---------------------------------------------------------------------------
# A. Batch POST: path, media type, operation, oid/size
# ---------------------------------------------------------------------------


def test_fetch_posts_download_batch_with_designated_media_type():
    """Fetch POSTs a download batch naming the designated JSON media type."""
    payload = _payload()
    with conforming_batch_server(mode="download", payloads=[payload]) as svc:
        with workspace() as ws:
            digest = _setup_one(ws, svc, payload, for_download=True)
            result = ws.invoke_via_git(["fetch"])
            print(
                f"fetch exit={result.returncode} n={len(svc.records)} "
                f"digest={digest}"
            )
            require_success(result)
            parsed = require_batch_post(svc.records, operation="download")
            require_named_media_type(parsed.headers)
            print(
                f"batch path={parsed.path!r} "
                f"objects={list(parsed.objects)!r}"
            )
            assert _request_is_batch_path(parsed.path), (
                f"download batch was not posted to the objects-batch path: "
                f"{parsed.path!r}"
            )
            require_object_bytes(default_lfs_store_root(ws), digest, payload)


def test_push_posts_upload_batch_with_designated_media_type():
    """Push POSTs an upload batch naming the designated JSON media type."""
    payload = _payload()
    with conforming_batch_server(mode="upload", payloads=[payload]) as svc:
        with workspace() as ws:
            digest = _setup_one(ws, svc, payload, for_download=False)
            result = ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            print(f"push exit={result.returncode} n={len(svc.records)}")
            require_success(result)
            parsed = require_batch_post(svc.records, operation="upload")
            require_named_media_type(parsed.headers)
            print(f"batch path={parsed.path!r}")
            assert _request_is_batch_path(parsed.path), (
                f"upload batch was not posted to the objects-batch path: "
                f"{parsed.path!r}"
            )


def test_batch_lists_oid_and_size_for_runtime_object():
    """The batch object list carries the independent oid and byte length."""
    payload = _payload()
    digest = sha256_hex(payload)
    size = len(payload)
    assert size >= 0
    with conforming_batch_server(mode="download", payloads=[payload]) as svc:
        with workspace() as ws:
            stored = _setup_one(ws, svc, payload, for_download=True)
            assert stored == digest
            result = ws.invoke_via_git(["fetch"])
            require_success(result)
            parsed = require_batch_post(svc.records, operation="download")
    print(f"listed={list(parsed.objects)!r} expect=({digest!r}, {size})")
    assert (digest, size) in parsed.objects, (
        "batch object list did not include the independent oid and size "
        f"({digest!r}, {size}); listed={list(parsed.objects)!r}"
    )


def test_direct_binary_fetch_same_batch_and_get_as_via_git():
    """Direct binary fetch posts download batch and GETs the action href."""
    payload = _payload()
    with conforming_batch_server(mode="download", payloads=[payload]) as svc:
        with workspace() as via:
            digest = _setup_one(via, svc, payload, for_download=True)
            via_run = via.invoke_via_git(["fetch"])
            require_success(via_run)
            via_n = len(svc.records)
            assert_batch_post(svc.records[:via_n], operation="download")
            assert_get_of_href(
                svc.records[:via_n],
                svc.action_path(digest),
                header_name=svc.header_name,
                header_value=svc.header_value,
            )
            assert_object_bytes(default_lfs_store_root(via), digest, payload)
        with workspace() as direct:
            digest = _setup_one(direct, svc, payload, for_download=True)
            before = len(svc.records)
            direct_run = direct.invoke(["fetch"])
            print(
                f"via_git exit={via_run.returncode} "
                f"direct exit={direct_run.returncode}"
            )
            require_success(direct_run)
            recs = svc.records[before:]
            assert_batch_post(recs, operation="download")
            assert_get_of_href(
                recs,
                svc.action_path(digest),
                header_name=svc.header_name,
                header_value=svc.header_value,
            )
            assert_object_bytes(
                default_lfs_store_root(direct), digest, payload
            )


def _request_is_batch_path(path: str) -> bool:
    cleaned = path.rstrip("/")
    batch = contract_objects_batch_path().rstrip("/")
    return cleaned == batch or cleaned.endswith(batch)


# ---------------------------------------------------------------------------
# B. Basic download: GET href + supplied headers, store digest
# ---------------------------------------------------------------------------


def test_fetch_get_action_href_with_supplied_headers_populates_store():
    """GET of the download href with supplied headers fills the local store."""
    payload = _payload()
    with conforming_batch_server(mode="download", payloads=[payload]) as svc:
        with workspace() as ws:
            digest = _setup_one(ws, svc, payload, for_download=True)
            result = ws.invoke_via_git(["fetch"])
            print(
                f"fetch exit={result.returncode} href={svc.action_path()!r} "
                f"header={svc.header_name}={svc.header_value!r}"
            )
            require_success(result)
            require_batch_post(svc.records, operation="download")
            assert_get_of_href(
                svc.records,
                svc.action_path(digest),
                header_name=svc.header_name,
                header_value=svc.header_value,
            )
            assert_object_bytes(default_lfs_store_root(ws), digest, payload)


def test_download_action_header_value_is_forwarded():
    """Changing the action header value changes what the GET forwards."""
    payload = _payload()
    value_a = f"va-{token()}"
    value_b = f"vb-{token()}"
    assert value_a != value_b
    header_name = f"X-T{token()}"
    with conforming_batch_server(
        mode="download",
        payloads=[payload],
        header_name=header_name,
        header_value=value_a,
    ) as svc_a:
        with workspace() as ws_a:
            digest_a = _setup_one(ws_a, svc_a, payload, for_download=True)
            run_a = ws_a.invoke_via_git(["fetch"])
            require_success(run_a)
            rec_a = require_get_of_href(
                svc_a.records,
                svc_a.action_path(digest_a),
                header_name=header_name,
                header_value=value_a,
            )
    with conforming_batch_server(
        mode="download",
        payloads=[payload],
        header_name=header_name,
        header_value=value_b,
    ) as svc_b:
        with workspace() as ws_b:
            digest_b = _setup_one(ws_b, svc_b, payload, for_download=True)
            run_b = ws_b.invoke_via_git(["fetch"])
            require_success(run_b)
            rec_b = require_get_of_href(
                svc_b.records,
                svc_b.action_path(digest_b),
                header_name=header_name,
                header_value=value_b,
            )
    print(
        f"header={header_name!r} a={value_a!r} b={value_b!r} "
        f"got_a={rec_a.headers!r} got_b={rec_b.headers!r}"
    )
    assert _ci_header(rec_a.headers, header_name) != value_b
    assert _ci_header(rec_b.headers, header_name) != value_a


# ---------------------------------------------------------------------------
# C. Basic upload: PUT raw bytes; verify contact when present
# ---------------------------------------------------------------------------


def test_push_puts_raw_bytes_to_upload_href_with_supplied_headers():
    """Direct-binary push PUTs original bytes to the upload href."""
    payload = _payload()
    with conforming_batch_server(mode="upload", payloads=[payload]) as svc:
        with workspace() as ws:
            digest = _setup_one(ws, svc, payload, for_download=False)
            result = ws.invoke(["push", "--object-id", "origin", digest])
            print(f"direct push exit={result.returncode} n={len(svc.records)}")
            require_success(result)
            require_batch_post(svc.records, operation="upload")
            put = require_put_of(svc.records, payload)
            print(f"put path={put.path!r} bytes={len(put.body)}")
            observed = _ci_header(put.headers, svc.header_name)
            assert observed == svc.header_value, (
                "PUT did not forward the supplied action header "
                f"{svc.header_name}={svc.header_value!r}; got {observed!r}"
            )


def test_verify_action_contacted_after_successful_put():
    """When a verify href is advertised, it is contacted after the PUT."""
    payload = _payload()
    with conforming_batch_server(
        mode="with_verify", payloads=[payload]
    ) as svc:
        with workspace() as ws:
            digest = _setup_one(ws, svc, payload, for_download=False)
            result = ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            print(
                f"push+verify exit={result.returncode} "
                f"verify={svc.verify_path()!r}"
            )
            require_success(result)
            require_put_of(svc.records, payload)
            contact = require_href_contacted_after_put(
                svc.records, payload, svc.verify_path()
            )
            print(f"verify contact method={contact.method!r} path={contact.path!r}")


def test_absent_verify_action_does_not_contact_verify_href():
    """Upload still PUTs when the batch response advertises no verify action."""
    payload = _payload()
    with conforming_batch_server(mode="upload", payloads=[payload]) as svc:
        with workspace() as ws:
            digest = _setup_one(ws, svc, payload, for_download=False)
            result = ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            print(f"push-no-verify exit={result.returncode}")
            require_success(result)
            require_put_of(svc.records, payload)


# ---------------------------------------------------------------------------
# D. Already-exists omits a second PUT of the same oid
# ---------------------------------------------------------------------------


def test_second_upload_omitted_when_server_reports_already_exists():
    """A new object is PUT; an already-exists response omits a second PUT."""
    payload = _payload()
    with conforming_batch_server(mode="upload", payloads=[payload]) as fresh:
        with workspace() as ws_a:
            digest = _setup_one(ws_a, fresh, payload, for_download=False)
            run_a = ws_a.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            print(f"fresh push exit={run_a.returncode}")
            require_success(run_a)
            assert_put_of(fresh.records, payload)
    with conforming_batch_server(
        mode="already_exists", payloads=[payload]
    ) as exists:
        with workspace() as ws_b:
            digest = _setup_one(ws_b, exists, payload, for_download=False)
            run_b = ws_b.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            print(f"exists push exit={run_b.returncode} n={len(exists.records)}")
            require_success(run_b)
            require_batch_post(exists.records, operation="upload")
            assert_no_put_of(exists.records, payload)


# ---------------------------------------------------------------------------
# E. Per-object batch error and expired action
# ---------------------------------------------------------------------------


def test_per_object_batch_error_fails_command_and_that_object():
    """A per-object error fails the command and does not transfer that object."""
    payload = _payload()
    with conforming_batch_server(mode="download", payloads=[payload]) as ok_dl:
        with workspace() as ws:
            digest = _setup_one(ws, ok_dl, payload, for_download=True)
            run_ok = ws.invoke_via_git(["fetch"])
            require_success(run_ok)
            require_object_bytes(default_lfs_store_root(ws), digest, payload)
            require_get_of_href(
                ok_dl.records,
                ok_dl.action_path(digest),
                header_name=ok_dl.header_name,
                header_value=ok_dl.header_value,
            )
    with conforming_batch_server(
        mode="object_error", payloads=[payload]
    ) as err_dl:
        with workspace() as ws:
            digest = _setup_one(ws, err_dl, payload, for_download=True)
            run_err = ws.invoke_via_git(["fetch"])
            print(f"download error exit={run_err.returncode}")
            assert run_err.returncode != 0, (
                "per-object download error exited 0 as if the object transferred"
            )
            require_object_absent(default_lfs_store_root(ws), digest)
            require_batch_post(err_dl.records, operation="download")
    with conforming_batch_server(mode="upload", payloads=[payload]) as ok_ul:
        with workspace() as ws:
            digest = _setup_one(ws, ok_ul, payload, for_download=False)
            run_ok = ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            require_success(run_ok)
            require_put_of(ok_ul.records, payload)
    with conforming_batch_server(
        mode="object_error", payloads=[payload]
    ) as err_ul:
        with workspace() as ws:
            digest = _setup_one(ws, err_ul, payload, for_download=False)
            run_err = ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            print(f"upload error exit={run_err.returncode}")
            assert run_err.returncode != 0, (
                "per-object upload error exited 0 as if the object transferred"
            )
            require_batch_post(err_ul.records, operation="upload")
            require_no_put_of(err_ul.records, payload)


def test_expired_action_fails_visibly_unlike_unexpired_success():
    """An expired action fails; the same href succeeds when not expired."""
    payload = _payload()
    with conforming_batch_server(mode="download", payloads=[payload]) as live:
        with workspace() as ws:
            digest = _setup_one(ws, live, payload, for_download=True)
            run_ok = ws.invoke_via_git(["fetch"])
            require_success(run_ok)
            require_object_bytes(default_lfs_store_root(ws), digest, payload)
            require_get_of_href(
                live.records,
                live.action_path(digest),
                header_name=live.header_name,
                header_value=live.header_value,
            )
    with conforming_batch_server(
        mode="download,expired", payloads=[payload]
    ) as expired:
        with workspace() as ws:
            digest = _setup_one(ws, expired, payload, for_download=True)
            run_exp = ws.invoke_via_git(["fetch"])
            print(f"expired fetch exit={run_exp.returncode}")
            assert run_exp.returncode != 0, (
                "expired download action exited 0 as if missing content succeeded"
            )
            require_object_absent(default_lfs_store_root(ws), digest)
            require_batch_post(expired.records, operation="download")


# ---------------------------------------------------------------------------
# F. tus advertisement on/off + basic-only peer interoperability
# ---------------------------------------------------------------------------


def test_tus_enabled_advertises_advanced_adapter_in_addition_to_basic():
    """Explicit tus enable advertises that adapter in addition to basic."""
    payload = _payload()
    with conforming_batch_server(
        mode="record_transfers_and_serve_basic", payloads=[payload]
    ) as svc:
        with workspace() as ws:
            digest = _setup_one(ws, svc, payload, for_download=False)
            enable_tus_transfers(ws)
            result = ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            print(f"tus-on push exit={result.returncode}")
            parsed = require_batch_post(svc.records, operation="upload")
            names = assert_advanced_advertised(parsed)
            print(f"advertised={names!r}")


def test_basic_transfers_only_drops_advanced_advertisement():
    """basic-transfers-only drops advanced names under the same tus config."""
    payload = _payload()
    with conforming_batch_server(
        mode="record_transfers_and_serve_basic", payloads=[payload]
    ) as on_svc:
        with workspace() as on_ws:
            digest = _setup_one(on_ws, on_svc, payload, for_download=False)
            enable_tus_transfers(on_ws)
            run_on = on_ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            parsed_on = require_batch_post(on_svc.records, operation="upload")
            names_on = require_advanced_advertised(parsed_on)
            print(f"on advertised={names_on!r} exit={run_on.returncode}")
    with conforming_batch_server(
        mode="record_transfers_and_serve_basic", payloads=[payload]
    ) as off_svc:
        with workspace() as off_ws:
            digest = _setup_one(off_ws, off_svc, payload, for_download=False)
            enable_tus_transfers(off_ws)
            enable_basic_transfers_only(off_ws)
            run_off = off_ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            parsed_off = require_batch_post(off_svc.records, operation="upload")
            names_off = require_basic_only_or_omitted(parsed_off)
            print(f"off advertised={names_off!r} exit={run_off.returncode}")
    tus = contract_tus_adapter_name()
    basic = contract_basic_adapter_name()
    assert tus in names_on and basic in names_on
    assert names_on != names_off


def test_basic_only_server_completes_put_on_basic_advertisement_arm():
    """A basic-only peer completes PUT when the client stays on basic."""
    payload = _payload()
    with conforming_batch_server(
        mode="basic_only_peer", payloads=[payload]
    ) as svc:
        with workspace() as ws:
            digest = _setup_one(ws, svc, payload, for_download=False)
            enable_tus_transfers(ws)
            enable_basic_transfers_only(ws)
            result = ws.invoke_via_git(
                ["push", "--object-id", "origin", digest]
            )
            print(f"basic-peer push exit={result.returncode}")
            require_success(result)
            parsed = require_batch_post(svc.records, operation="upload")
            assert_basic_only_or_omitted(parsed)
            assert_put_of(svc.records, payload)


# ---------------------------------------------------------------------------
# G. Concurrent bound; default parallelism > 1
# ---------------------------------------------------------------------------


def test_default_parallelism_allows_overlapping_transfers():
    """Default fetch of two missing objects overlaps in-flight GETs."""
    payloads = [_payload(), _payload()]
    with conforming_batch_server(
        mode="overlap_gate", payloads=payloads
    ) as svc:
        with workspace() as ws:
            digests = _setup_two(ws, svc, payloads, for_download=True)
            result = ws.invoke_via_git(["fetch"], timeout=90.0)
            print(
                f"default overlap exit={result.returncode} "
                f"max_in_flight={svc.max_in_flight}"
            )
            require_success(result)
            store = default_lfs_store_root(ws)
            for digest, data in zip(digests, payloads):
                require_object_bytes(store, digest, data)
            for digest in digests:
                require_get_of_href(
                    svc.records,
                    svc.action_path(digest),
                    header_name=svc.header_name,
                    header_value=svc.header_value,
                )
    assert svc.max_in_flight >= 2, (
        "default parallelism never overlapped two in-flight transfers "
        f"(max_in_flight={svc.max_in_flight})"
    )


def test_configured_bound_prevents_overlap():
    """A concurrent-transfer bound of 1 keeps a second transfer from overlapping."""
    payloads = [_payload(), _payload()]
    unbounded_max = 0
    with conforming_batch_server(
        mode="overlap_gate", payloads=payloads
    ) as unbounded:
        with workspace() as ws:
            digests = _setup_two(ws, unbounded, payloads, for_download=True)
            result = ws.invoke_via_git(["fetch"], timeout=90.0)
            print(
                f"unbounded overlap exit={result.returncode} "
                f"max_in_flight={unbounded.max_in_flight}"
            )
            require_success(result)
            store = default_lfs_store_root(ws)
            for digest, data in zip(digests, payloads):
                require_object_bytes(store, digest, data)
        unbounded_max = unbounded.max_in_flight
    with conforming_batch_server(
        mode="overlap_gate", payloads=payloads
    ) as bound:
        with workspace() as ws:
            digests = _setup_two(ws, bound, payloads, for_download=True)
            configure_concurrent_transfers(ws, 1)
            result = ws.invoke_via_git(["fetch"], timeout=90.0)
            print(
                f"bound-1 exit={result.returncode} "
                f"max_in_flight={bound.max_in_flight}"
            )
            require_success(result)
            store = default_lfs_store_root(ws)
            for digest, data in zip(digests, payloads):
                require_object_bytes(store, digest, data)
        require_bound_prevents_overlap_unlike_unbounded(
            bound.max_in_flight, unbounded_max
        )


# ---------------------------------------------------------------------------
# H. Negative control
# ---------------------------------------------------------------------------


def test_transfer_fails_when_binary_removed_from_path():
    """Removing the binary from PATH makes fetch fail (PRD core capabilities)."""
    payload = _payload()
    with conforming_batch_server(mode="download", payloads=[payload]) as svc:
        with workspace() as present:
            digest = _setup_one(present, svc, payload, for_download=True)
            ok = present.invoke_via_git(["fetch"])
            require_success(ok)
            require_batch_post(svc.records, operation="download")
            require_object_bytes(
                default_lfs_store_root(present), digest, payload
            )
        with workspace() as missing:
            _setup_one(missing, svc, payload, for_download=True)
            hidden = path_without_product_bin(missing.env)
            failed = missing.invoke_via_git(
                ["fetch"], env_updates={"PATH": hidden}
            )
            print(
                f"present exit={ok.returncode} absent exit={failed.returncode} "
                f"hidden_path={hidden!r}"
            )
            assert failed.returncode != 0, (
                "fetch succeeded after the product binary was removed from PATH"
            )
            assert (failed.returncode, failed.stdout, failed.stderr) != (
                ok.returncode,
                ok.stdout,
                ok.stderr,
            ), "absent-binary fetch was not distinguishable from a successful fetch"
