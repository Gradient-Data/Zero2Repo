# feature: F02
"""FP-02: inspect and mutate URL components (C++ library and matching C interface)."""

from __future__ import annotations

import pytest

from _helpers import (
    GOOGLE_HREF,
    GOOGLE_URL,
    MIXED_IPV4_HOSTNAME,
    MIXED_IPV4_HREF,
    MIXED_IPV4_INPUT,
    NONPUBLIC_IPV4_TOKENS,
    clear_component,
    dotted_ipv4_from_mixed_octets,
    inspect_probe_has_href_and_origin,
    inspect_url,
    mutate_component,
    mutate_many,
    same_components,
    try_inspect_without_linked_library,
    unique_token,
)

BOTH_LANGS = ("c++", "c")

QUALIFIED_GOOGLE = (
    "https://username:password@www.google.com:8080/pathname"
    "?query=true#hash-exists"
)
NAMED_ORIGIN = "https://www.google.com:8080"
DEFAULT_PORT_ORIGIN = "https://www.google.com"
CREDENTIAL_HREF = "https://username:password@www.google.com/"
WSS_HREF = "wss://www.google.com/"
INVALID_PERCENT_HOST = "www.google%X%.com"
MAILTO = "mailto:a@b.com"
OPAQUE_DATA = "data:text/plain,hello"
EMPTY_HOST_FILE = "file:"
NON_SPECIAL_EMPTY = "non-special:/x"
NON_SPEC_EMPTY = "non-spec:/x"
SC_EMPTY = "sc:/x"
GIT_EXAMPLE = "git://example.com/"
PORT_ZERO = "a://h:0"
HTTPS_EXAMPLE = "https://example.com/"
IPV4_LOOPBACK = "http://127.0.0.1/"
IPV6_LOOPBACK = "http://[::1]/"
IPV4_OTHER = "http://10.0.0.1/"


def _print_inspect(label: str, snap, *, language: str) -> None:
    print(
        f"{label} language={language} href={snap.href!r} origin={snap.origin!r} "
        f"protocol={snap.protocol!r} user={snap.username!r} pass={snap.password!r} "
        f"host={snap.host!r} hostname={snap.hostname!r} port={snap.port!r} "
        f"path={snap.pathname!r} search={snap.search!r} hash={snap.hash!r} "
        f"kind={snap.host_kind!r} cred={snap.has_credentials} "
        f"has_host={snap.has_hostname} has_port={snap.has_port} "
        f"has_search={snap.has_search} has_hash={snap.has_hash}"
    )


def _require_accepted(outcome, *, what: str):
    assert outcome.accepted is True, (
        f"{what} must be WRITE ACCEPTED; accepted={outcome.accepted!r} "
        f"href={outcome.after.href!r} stderr={outcome.stderr!r}"
    )
    return outcome


def _require_refused(outcome, before, *, what: str):
    assert outcome.accepted is False, (
        f"{what} must be WRITE REFUSED; accepted={outcome.accepted!r} "
        f"href={outcome.after.href!r} stderr={outcome.stderr!r}"
    )
    assert same_components(outcome.after, before), (
        f"{what} must leave every named component unchanged; "
        f"before={before.components()!r} after={outcome.after.components()!r}"
    )
    return outcome


def _grow_pathname_href(start: str, min_len: int, *, language: str = "c++") -> str:
    extra = max(16, min_len)
    while True:
        path = "/" + ("a" * extra)
        grown = mutate_component(start, "pathname", path, language=language)
        assert grown.accepted is True, (
            f"default-cap pathname growth failed extra={extra} "
            f"stderr={grown.stderr!r}"
        )
        print(f"grown href_len={len(grown.after.href)} extra={extra}")
        if len(grown.after.href) >= min_len:
            return grown.after.href
        extra *= 2


# ---------------------------------------------------------------------------
# A. Readers after parse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_qualified_google_components_and_origin(language: str) -> None:
    snap = inspect_url(QUALIFIED_GOOGLE, language=language)
    _print_inspect("qualified", snap, language=language)
    assert snap.href
    assert "username" in snap.href
    assert "password" in snap.href
    assert ":8080" in snap.href
    assert "/pathname" in snap.href
    assert "query=true" in snap.href
    assert "hash-exists" in snap.href
    assert snap.origin == NAMED_ORIGIN
    assert "username" not in snap.origin
    assert "password" not in snap.origin
    assert "/pathname" not in snap.origin
    assert "query" not in snap.origin
    assert "hash-exists" not in snap.origin
    assert snap.protocol == "https:"
    assert snap.username == "username"
    assert snap.password == "password"
    assert snap.port == "8080"
    assert snap.hash == "#hash-exists"
    assert snap.host == "www.google.com:8080"
    assert snap.hostname == "www.google.com"
    assert snap.pathname == "/pathname"
    assert snap.search == "?query=true"
    ipv4 = inspect_url(IPV4_LOOPBACK, language=language)
    ipv6 = inspect_url(IPV6_LOOPBACK, language=language)
    assert snap.host_kind != ipv4.host_kind
    assert snap.host_kind != ipv6.host_kind


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_default_pathname_slash_when_input_omits_path(language: str) -> None:
    snap = inspect_url(GOOGLE_URL, language=language)
    _print_inspect("no-path", snap, language=language)
    assert snap.pathname == "/"
    assert snap.href.endswith("/")
    assert snap.search == ""
    assert snap.hash == ""


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_origin_default_port_differs_from_named_tuple(language: str) -> None:
    snap = inspect_url(GOOGLE_URL, language=language)
    _print_inspect("default-port origin", snap, language=language)
    assert snap.origin == DEFAULT_PORT_ORIGIN
    assert snap.origin != NAMED_ORIGIN
    assert "username" not in snap.origin
    assert ":443" not in snap.origin


# ---------------------------------------------------------------------------
# B. Presence queries and host-kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_has_credentials_username_or_password(language: str) -> None:
    bare = inspect_url(GOOGLE_URL, language=language)
    print(f"bare cred={bare.has_credentials} language={language}")
    assert bare.has_credentials is False
    named = inspect_url(QUALIFIED_GOOGLE, language=language)
    assert named.has_credentials is True
    user = mutate_component(GOOGLE_URL, "username", "username", language=language)
    _require_accepted(user, what="username write")
    _print_inspect("after username", user.after, language=language)
    assert user.after.has_credentials is True
    assert user.after.username == "username"
    if language == "c++":
        only_pass = mutate_component(
            GOOGLE_URL, "password", "password", language=language
        )
        _require_accepted(only_pass, what="password-only write")
        print(f"password-only cred={only_pass.after.has_credentials}")
        assert only_pass.after.has_credentials is True
        assert only_pass.after.password == "password"


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_has_hostname_true_for_empty_host(language: str) -> None:
    mailto = inspect_url(MAILTO, language=language)
    before = inspect_url(NON_SPECIAL_EMPTY, language=language)
    print(
        f"mailto has_host={mailto.has_hostname} "
        f"non-special before has_host={before.has_hostname} href={before.href!r}"
    )
    assert mailto.has_hostname is False
    assert before.has_hostname is False
    inserted = mutate_component(
        NON_SPECIAL_EMPTY, "host", "", language=language
    )
    _require_accepted(inserted, what="empty host insert")
    _print_inspect("empty host", inserted.after, language=language)
    assert inserted.after.href == "non-special:///x"
    assert inserted.after.has_hostname is True
    google = inspect_url(GOOGLE_URL, language=language)
    assert google.has_hostname is True


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_has_port_search_hash_track_writes(language: str) -> None:
    before = inspect_url(GOOGLE_URL, language=language)
    print(
        f"before port/search/hash "
        f"{before.has_port}/{before.has_search}/{before.has_hash}"
    )
    assert before.has_port is False
    assert before.has_search is False
    assert before.has_hash is False
    after = mutate_many(
        GOOGLE_URL,
        (
            ("port", "8080"),
            ("search", "target=self"),
            ("hash", "is-this-the-real-life"),
        ),
        language=language,
    )
    _require_accepted(after, what="port/search/hash writes")
    _print_inspect("after presence writes", after.after, language=language)
    assert after.after.has_port is not before.has_port
    assert after.after.has_search is not before.has_search
    assert after.after.has_hash is not before.has_hash
    assert after.after.port == "8080"
    assert after.after.search == "?target=self"
    assert after.after.hash == "#is-this-the-real-life"


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_has_port_search_hash_independent(language: str) -> None:
    start = inspect_url(GOOGLE_URL, language=language)
    only_port = mutate_component(GOOGLE_URL, "port", "8080", language=language)
    _require_accepted(only_port, what="port-only")
    print(
        f"port-only has_port={only_port.after.has_port} "
        f"search={only_port.after.has_search} hash={only_port.after.has_hash}"
    )
    assert only_port.after.has_port is True
    assert only_port.after.has_search is start.has_search
    assert only_port.after.has_hash is start.has_hash
    only_search = mutate_component(
        GOOGLE_URL, "search", "target=self", language=language
    )
    assert only_search.after.has_search is True
    assert only_search.after.has_port is start.has_port
    assert only_search.after.has_hash is start.has_hash
    only_hash = mutate_component(
        GOOGLE_URL, "hash", "is-this-the-real-life", language=language
    )
    assert only_hash.after.has_hash is True
    assert only_hash.after.has_port is start.has_port
    assert only_hash.after.has_search is start.has_search


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_host_kind_ipv4_ipv6_domain_distinguishable(language: str) -> None:
    ipv4 = inspect_url(IPV4_LOOPBACK, language=language)
    ipv6 = inspect_url(IPV6_LOOPBACK, language=language)
    domain = inspect_url(HTTPS_EXAMPLE, language=language)
    google = inspect_url(GOOGLE_URL, language=language)
    print(
        f"kinds ipv4={ipv4.host_kind!r} ipv6={ipv6.host_kind!r} "
        f"domain={domain.host_kind!r} google={google.host_kind!r} "
        f"language={language}"
    )
    assert ipv4.host_kind != ipv6.host_kind
    assert ipv4.host_kind != domain.host_kind
    assert ipv6.host_kind != domain.host_kind
    assert google.host_kind == domain.host_kind
    assert google.host_kind != ipv4.host_kind
    assert google.host_kind != ipv6.host_kind
    if language == "c++":
        other_ipv4 = inspect_url(IPV4_OTHER, language=language)
        print(f"other ipv4 kind={other_ipv4.host_kind!r}")
        assert other_ipv4.host_kind == ipv4.host_kind
        assert other_ipv4.host_kind != ipv6.host_kind
        assert other_ipv4.host_kind != domain.host_kind


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_opaque_origin_matches_across_schemes(language: str) -> None:
    mailto = inspect_url(MAILTO, language=language)
    data = inspect_url(OPAQUE_DATA, language=language)
    file_empty = inspect_url(EMPTY_HOST_FILE, language=language)
    https = inspect_url(GOOGLE_URL, language=language)
    print(
        f"opaque mailto={mailto.origin!r} data={data.origin!r} "
        f"file={file_empty.origin!r} https={https.origin!r}"
    )
    assert mailto.origin == data.origin == file_empty.origin
    assert mailto.origin != https.origin
    assert "file://" not in file_empty.origin
    hosted_file = mutate_component(
        EMPTY_HOST_FILE, "host", "google.com", language=language
    )
    _require_accepted(hosted_file, what="file host write")
    print(f"file-with-host origin={hosted_file.after.origin!r}")
    assert hosted_file.after.origin == mailto.origin
    assert "file://" not in hosted_file.after.origin


# ---------------------------------------------------------------------------
# C. Successful writes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_set_credentials_appear_in_href(language: str) -> None:
    before = inspect_url(GOOGLE_URL, language=language)
    written = mutate_many(
        GOOGLE_URL,
        (("username", "username"), ("password", "password")),
        language=language,
    )
    _require_accepted(written, what="credential write")
    _print_inspect("credentials", written.after, language=language)
    assert written.after.href == CREDENTIAL_HREF
    assert written.after.username == "username"
    assert written.after.password == "password"
    assert "username" not in written.after.origin
    assert "password" not in written.after.origin
    assert written.after.origin != NAMED_ORIGIN
    assert written.after.has_credentials is True
    assert before.has_credentials is False


def test_runtime_credentials_in_href() -> None:
    user = unique_token()
    password = unique_token()
    written = mutate_many(
        GOOGLE_URL, (("username", user), ("password", password))
    )
    _require_accepted(written, what="runtime credentials")
    print(f"runtime cred href={written.after.href!r}")
    assert user in written.after.href
    assert password in written.after.href
    assert "@" in written.after.href
    assert written.after.username == user
    assert written.after.password == password


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_special_to_special_protocol_wss_then_http(language: str) -> None:
    before = inspect_url(GOOGLE_URL, language=language)
    wss = mutate_component(GOOGLE_URL, "protocol", "wss", language=language)
    _require_accepted(wss, what="protocol wss")
    _print_inspect("wss", wss.after, language=language)
    assert wss.after.protocol == "wss:"
    assert wss.after.href == WSS_HREF
    assert wss.after.origin != before.origin
    assert wss.after.origin != NAMED_ORIGIN
    http = mutate_component(wss.after.href, "protocol", "http", language=language)
    _require_accepted(http, what="protocol http after wss")
    print(f"after http protocol={http.after.protocol!r} href={http.after.href!r}")
    assert http.after.protocol != "wss:"
    assert http.after.href != WSS_HREF


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_set_host_port_pathname_search_hash_readers(language: str) -> None:
    before = inspect_url(GOOGLE_URL, language=language)
    host_only = mutate_component(
        GOOGLE_URL, "host", "github.com", language=language
    )
    _require_accepted(host_only, what="host github.com")
    print(f"host-before-port host={host_only.after.host!r}")
    assert host_only.after.host == "github.com"
    after = mutate_many(
        GOOGLE_URL,
        (
            ("host", "github.com"),
            ("port", "8080"),
            ("pathname", "/my-super-long-path"),
            ("search", "target=self"),
            ("hash", "is-this-the-real-life"),
        ),
        language=language,
    )
    _require_accepted(after, what="host/port/path/search/hash")
    _print_inspect("sequential writes", after.after, language=language)
    assert after.after.pathname == "/my-super-long-path"
    assert after.after.search == "?target=self"
    assert after.after.hash == "#is-this-the-real-life"
    assert after.after.port == "8080"
    assert "8080" in after.after.host
    assert "8080" not in after.after.hostname
    assert after.after.host != after.after.hostname
    assert after.after.has_port is not before.has_port
    assert after.after.has_search is not before.has_search
    assert after.after.has_hash is not before.has_hash


class TestSearchHashWriters:
    """Optional-delimiter search/hash writes must store the component, not report success and leave the URL unchanged."""

    @pytest.mark.parametrize("language", BOTH_LANGS)
    def test_search_hash_writers_optional_delimiters(self, language: str) -> None:
        absent = inspect_url(GOOGLE_URL, language=language)
        assert absent.search == ""
        assert absent.hash == ""
        assert absent.has_search is False
        assert absent.has_hash is False
        bare_search = mutate_component(
            GOOGLE_URL, "search", "target=self", language=language
        )
        marked_search = mutate_component(
            GOOGLE_URL, "search", "?target=self", language=language
        )
        print(
            f"search bare={bare_search.after.search!r} "
            f"marked={marked_search.after.search!r} "
            f"href={bare_search.after.href!r}"
        )
        assert bare_search.after.search == "?target=self"
        assert marked_search.after.search == "?target=self"
        assert bare_search.after.has_search is True
        assert marked_search.after.has_search is True
        assert bare_search.after.href != absent.href
        assert marked_search.after.href != absent.href
        assert "?target=self" in bare_search.after.href
        assert "?target=self" in marked_search.after.href
        bare_hash = mutate_component(
            GOOGLE_URL, "hash", "is-this-the-real-life", language=language
        )
        marked_hash = mutate_component(
            GOOGLE_URL, "hash", "#is-this-the-real-life", language=language
        )
        print(
            f"hash bare={bare_hash.after.hash!r} marked={marked_hash.after.hash!r} "
            f"href={bare_hash.after.href!r}"
        )
        assert bare_hash.after.hash == "#is-this-the-real-life"
        assert marked_hash.after.hash == "#is-this-the-real-life"
        assert bare_hash.after.has_hash is True
        assert marked_hash.after.has_hash is True
        assert bare_hash.after.href != absent.href
        assert marked_hash.after.href != absent.href
        assert "#is-this-the-real-life" in bare_hash.after.href
        assert "#is-this-the-real-life" in marked_hash.after.href


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_runtime_search_hash_pathname_tokens(language: str) -> None:
    path_token = unique_token()
    path = mutate_component(
        GOOGLE_URL, "pathname", f"/{path_token}", language=language
    )
    _require_accepted(path, what="runtime pathname")
    print(f"runtime path={path.after.pathname!r}")
    assert path_token in path.after.pathname
    if language != "c++":
        return
    search_token = unique_token()
    hash_token = unique_token()
    search = mutate_component(GOOGLE_URL, "search", search_token)
    hashed = mutate_component(GOOGLE_URL, "hash", hash_token)
    print(f"runtime search={search.after.search!r} hash={hashed.after.hash!r}")
    assert search.after.search.startswith("?")
    assert search_token in search.after.search
    assert hashed.after.hash.startswith("#")
    assert hash_token in hashed.after.hash


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_set_host_consumes_port_hostname_does_not(language: str) -> None:
    hosted = mutate_component(
        GOOGLE_URL, "host", "changed-host:9090", language=language
    )
    _require_accepted(hosted, what="host with port")
    _print_inspect("host consumes port", hosted.after, language=language)
    assert hosted.after.port == "9090"
    assert "9090" not in hosted.after.hostname
    assert "9090" in hosted.after.host
    with_port = mutate_component(GOOGLE_URL, "port", "8080", language=language)
    _require_accepted(with_port, what="seed port 8080")
    hostname_write = mutate_component(
        with_port.after.href, "hostname", "changed-host:9090", language=language
    )
    print(
        f"hostname write accepted={hostname_write.accepted} "
        f"port={hostname_write.after.port!r} "
        f"hostname={hostname_write.after.hostname!r}"
    )
    assert hostname_write.after.port != "9090"
    assert hostname_write.after.port == with_port.after.port
    if hostname_write.accepted is True:
        assert "9090" not in hostname_write.after.hostname
        assert hostname_write.after.host != hostname_write.after.hostname
    else:
        assert hostname_write.accepted is False
        assert same_components(hostname_write.after, with_port.after)
    token_host = unique_token()
    renamed = mutate_component(
        with_port.after.href, "hostname", token_host, language=language
    )
    _require_accepted(renamed, what="hostname without port")
    print(f"renamed hostname={renamed.after.hostname!r} port={renamed.after.port!r}")
    assert renamed.after.hostname == token_host
    assert renamed.after.port == with_port.after.port


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_replace_href_rebuilds_components(language: str) -> None:
    start = inspect_url(QUALIFIED_GOOGLE, language=language)
    assert start.port == "8080"
    assert start.has_credentials is True
    replaced = mutate_component(
        QUALIFIED_GOOGLE, "href", GOOGLE_URL, language=language
    )
    _require_accepted(replaced, what="href replace to google")
    _print_inspect("href rebuilt", replaced.after, language=language)
    assert replaced.after.pathname == "/"
    assert replaced.after.username == ""
    assert replaced.after.password == ""
    assert replaced.after.has_credentials is False
    assert replaced.after.protocol == "https:"
    assert replaced.after.search == ""
    assert replaced.after.hash == ""
    assert replaced.after.port != "8080"
    assert replaced.after.origin != NAMED_ORIGIN


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_replace_href_ipv4_canonicalization(language: str) -> None:
    replaced = mutate_component(
        GOOGLE_URL, "href", MIXED_IPV4_INPUT, language=language
    )
    _require_accepted(replaced, what="href mixed IPv4")
    print(
        f"ipv4 href={replaced.after.href!r} hostname={replaced.after.hostname!r}"
    )
    assert replaced.after.href == MIXED_IPV4_HREF
    assert replaced.after.hostname == MIXED_IPV4_HOSTNAME


def test_replace_href_nonpublic_mixed_ipv4() -> None:
    dotted = dotted_ipv4_from_mixed_octets(NONPUBLIC_IPV4_TOKENS)
    assert dotted != MIXED_IPV4_HOSTNAME
    raw = "http://" + ".".join(NONPUBLIC_IPV4_TOKENS)
    replaced = mutate_component(GOOGLE_URL, "href", raw)
    _require_accepted(replaced, what="nonpublic mixed IPv4")
    print(f"nonpublic href={replaced.after.href!r} host={replaced.after.hostname!r}")
    assert replaced.after.href == f"http://{dotted}/"
    assert replaced.after.hostname == dotted


# ---------------------------------------------------------------------------
# D. Empty authority insert and non-special protocol
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_empty_host_inserts_authority_on_non_special(language: str) -> None:
    written = mutate_component(
        NON_SPECIAL_EMPTY, "host", "", language=language
    )
    _require_accepted(written, what="empty host on non-special")
    print(f"inserted href={written.after.href!r}")
    assert written.after.href == "non-special:///x"
    assert written.after.has_hostname is True


def test_empty_hostname_inserts_authority_on_sc() -> None:
    written = mutate_component(SC_EMPTY, "hostname", "")
    _require_accepted(written, what="empty hostname on sc")
    print(f"sc href={written.after.href!r}")
    assert written.after.href == "sc:///x"
    assert written.after.has_hostname is True


def test_empty_host_inserts_authority_runtime_scheme() -> None:
    scheme = unique_token()
    start = f"{scheme}:/x"
    written = mutate_component(start, "host", "")
    _require_accepted(written, what="runtime empty host insert")
    print(f"runtime insert href={written.after.href!r}")
    assert written.after.href == f"{scheme}:///x"
    assert written.after.has_hostname is True


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_nonspecial_to_nonspecial_protocol_git_svn(language: str) -> None:
    before = inspect_url(GIT_EXAMPLE, language=language)
    written = mutate_component(
        GIT_EXAMPLE, "protocol", "svn", language=language
    )
    _require_accepted(written, what="git to svn")
    print(
        f"git→svn protocol={written.after.protocol!r} href={written.after.href!r}"
    )
    assert written.after.protocol != before.protocol
    assert "git" not in written.after.protocol
    assert not written.after.href.startswith("git:")


def test_nonspecial_protocol_keeps_port_zero() -> None:
    written = mutate_component(PORT_ZERO, "protocol", "b")
    _require_accepted(written, what="a to b keep port 0")
    print(f"port-zero href={written.after.href!r} port={written.after.port!r}")
    assert written.after.href == "b://h:0"
    assert written.after.port == "0"


# ---------------------------------------------------------------------------
# E. Refused writes leave the URL unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_failed_host_write_does_not_invent_authority(language: str) -> None:
    inserted = mutate_component(NON_SPEC_EMPTY, "host", "", language=language)
    _require_accepted(inserted, what="empty host insert baseline")
    print(f"non-spec empty-host href={inserted.after.href!r}")
    assert inserted.after.href == "non-spec:///x"
    before = inspect_url(NON_SPEC_EMPTY, language=language)
    assert before.href == NON_SPEC_EMPTY
    assert "///" not in before.href
    # A host containing a literal space is a host-parse failure.
    garbage = "www.google com"
    for field in ("host", "hostname"):
        refused = mutate_component(
            NON_SPEC_EMPTY, field, garbage, language=language
        )
        print(
            f"non-spec {field} garbage accepted={refused.accepted} "
            f"href={refused.after.href!r}"
        )
        _require_refused(refused, before, what=f"{field} garbage on non-spec")
        assert refused.after.href == NON_SPEC_EMPTY
        assert "///" not in refused.after.href


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_mailto_refuses_host_and_hostname(language: str) -> None:
    live = mutate_component(GOOGLE_URL, "host", "github.com", language=language)
    _require_accepted(live, what="successful host baseline")
    before = inspect_url(MAILTO, language=language)
    host = mutate_component(MAILTO, "host", "example.com", language=language)
    hostname = mutate_component(
        MAILTO, "hostname", "example.com", language=language
    )
    print(f"mailto host accepted={host.accepted} hostname={hostname.accepted}")
    _require_refused(host, before, what="mailto host")
    _require_refused(hostname, before, what="mailto hostname")


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_file_empty_host_refuses_protocol_until_host_set(language: str) -> None:
    wss = mutate_component(GOOGLE_URL, "protocol", "wss", language=language)
    _require_accepted(wss, what="special-to-special baseline")
    before = inspect_url(EMPTY_HOST_FILE, language=language)
    _print_inspect("empty file", before, language=language)
    mailto = inspect_url(MAILTO, language=language)
    https = mutate_component(
        EMPTY_HOST_FILE, "protocol", "https", language=language
    )
    foo = mutate_component(EMPTY_HOST_FILE, "protocol", "foo", language=language)
    _require_refused(https, before, what="empty-host file → https")
    _require_refused(foo, before, what="empty-host file → foo")
    assert https.after.protocol == "file:"
    hosted = mutate_component(
        EMPTY_HOST_FILE, "host", "google.com", language=language
    )
    _require_accepted(hosted, what="set file host")
    print(
        f"file-with-host origin={hosted.after.origin!r} href={hosted.after.href!r}"
    )
    assert hosted.after.origin == mailto.origin
    assert "file://" not in hosted.after.origin
    switched = mutate_component(
        hosted.after.href, "protocol", "https", language=language
    )
    _require_accepted(switched, what="file-with-host → https")
    print(f"file→https href={switched.after.href!r}")
    assert switched.after.href == "https://google.com/"


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_special_to_nonspecial_protocol_refused(language: str) -> None:
    live = mutate_component(GOOGLE_URL, "protocol", "wss", language=language)
    _require_accepted(live, what="wss success baseline")
    before = inspect_url(HTTPS_EXAMPLE, language=language)
    refused = mutate_component(
        HTTPS_EXAMPLE, "protocol", "foo", language=language
    )
    print(f"https→foo accepted={refused.accepted} href={refused.after.href!r}")
    _require_refused(refused, before, what="https → foo")
    assert refused.after.protocol == "https:"


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_opaque_path_refuses_pathname(language: str) -> None:
    live = mutate_component(
        GOOGLE_URL, "pathname", "/my-super-long-path", language=language
    )
    _require_accepted(live, what="hierarchical pathname baseline")
    before = inspect_url(MAILTO, language=language)
    refused = mutate_component(
        MAILTO, "pathname", "/nope", language=language
    )
    print(f"opaque path accepted={refused.accepted} href={refused.after.href!r}")
    _require_refused(refused, before, what="opaque pathname")


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_no_host_refuses_credentials(language: str) -> None:
    live = mutate_component(
        GOOGLE_URL, "username", "username", language=language
    )
    _require_accepted(live, what="credential success baseline")
    for start in (MAILTO, NON_SPEC_EMPTY):
        before = inspect_url(start, language=language)
        user = mutate_component(start, "username", "u", language=language)
        password = mutate_component(start, "password", "p", language=language)
        print(
            f"{start!r} user={user.accepted} pass={password.accepted} "
            f"href={user.after.href!r}"
        )
        _require_refused(user, before, what=f"username on {start}")
        _require_refused(password, before, what=f"password on {start}")


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_empty_port_string_clears_port(language: str) -> None:
    seeded = mutate_component(GOOGLE_URL, "port", "8080", language=language)
    _require_accepted(seeded, what="seed port")
    assert seeded.after.has_port is True
    cleared = mutate_component(
        seeded.after.href, "port", "", language=language
    )
    _require_accepted(cleared, what="empty port string")
    print(
        f"empty-port port={cleared.after.port!r} has_port={cleared.after.has_port}"
    )
    assert cleared.after.port == ""
    assert cleared.after.has_port is False


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_port_refused_when_url_cannot_have_port(language: str) -> None:
    live = mutate_component(GOOGLE_URL, "port", "8080", language=language)
    _require_accepted(live, what="port success baseline")
    empty_clear = mutate_component(live.after.href, "port", "", language=language)
    _require_accepted(empty_clear, what="empty-string clear baseline")
    before = inspect_url(MAILTO, language=language)
    refused = mutate_component(MAILTO, "port", "80", language=language)
    print(f"mailto port accepted={refused.accepted} href={refused.after.href!r}")
    _require_refused(refused, before, what="port on mailto")
    assert refused.accepted is not empty_clear.accepted


def test_href_replace_refused_leaves_unchanged() -> None:
    before = inspect_url(GOOGLE_URL)
    live = mutate_component(GOOGLE_URL, "href", MIXED_IPV4_INPUT)
    _require_accepted(live, what="href replace success baseline")
    print(f"href success href={live.after.href!r}")
    assert live.after.href != before.href, (
        "href replace success baseline must change the URL so refusal "
        f"is not compared against a no-op; before={before.href!r} "
        f"after={live.after.href!r}"
    )
    token = unique_token()
    # Fixed inputs the parser rejects (empty, host with a literal space) plus
    # runtime variants.
    bad_hrefs = (
        "",
        "http://www.google com/",
        f"#{token}",
        f"http://www.{token} com/",
    )
    for bad in bad_hrefs:
        refused = mutate_component(GOOGLE_URL, "href", bad)
        print(f"href {bad!r} accepted={refused.accepted}")
        _require_refused(refused, before, what=f"href replace {bad!r}")
        assert live.accepted is not refused.accepted


# ---------------------------------------------------------------------------
# F. Dedicated clears
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_clear_port_search_hash_independently(language: str) -> None:
    start = inspect_url(QUALIFIED_GOOGLE, language=language)
    _print_inspect("clear start", start, language=language)
    cleared_port = clear_component(QUALIFIED_GOOGLE, "port", language=language)
    _print_inspect("cleared port", cleared_port, language=language)
    assert cleared_port.port == ""
    assert cleared_port.has_port is False
    assert cleared_port.search == start.search
    assert cleared_port.hash == start.hash
    assert cleared_port.has_search == start.has_search
    assert cleared_port.has_hash == start.has_hash
    assert cleared_port.href != start.href
    assert ":8080" not in cleared_port.href
    assert "8080" not in cleared_port.href
    assert cleared_port.origin != NAMED_ORIGIN
    assert "8080" not in cleared_port.origin
    cleared_search = clear_component(
        QUALIFIED_GOOGLE, "search", language=language
    )
    assert cleared_search.search == ""
    assert cleared_search.has_search is False
    assert cleared_search.hash == start.hash
    assert cleared_search.port == start.port
    assert cleared_search.href != start.href
    assert "query=true" not in cleared_search.href
    cleared_hash = clear_component(QUALIFIED_GOOGLE, "hash", language=language)
    assert cleared_hash.hash == ""
    assert cleared_hash.has_hash is False
    assert cleared_hash.search == start.search
    assert cleared_hash.port == start.port
    assert cleared_hash.href != start.href
    assert "hash-exists" not in cleared_hash.href


# ---------------------------------------------------------------------------
# G. Length cap on writes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_pathname_over_cap_leaves_url_unchanged(language: str) -> None:
    start = inspect_url(GOOGLE_URL, language=language)
    long_path = "/" + ("p" * 80)
    baseline = mutate_component(
        GOOGLE_URL, "pathname", long_path, language=language
    )
    _require_accepted(baseline, what="default-cap long pathname")
    assert len(baseline.after.href) > len(start.href)
    print(
        f"pathname baseline href_len={len(baseline.after.href)} "
        f"start={len(start.href)}"
    )
    cap = len(start.href) + 8
    refused = mutate_component(
        GOOGLE_URL, "pathname", long_path, language=language, max_length=cap
    )
    print(f"pathname over cap accepted={refused.accepted} href={refused.after.href!r}")
    _require_refused(refused, start, what="pathname over cap")
    assert refused.after.pathname == start.pathname


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_search_over_cap_leaves_url_unchanged_no_flag(language: str) -> None:
    start = inspect_url(GOOGLE_URL, language=language)
    long_search = "q=" + ("s" * 80)
    baseline = mutate_component(
        GOOGLE_URL, "search", long_search, language=language
    )
    print(
        f"search baseline search={baseline.after.search!r} "
        f"href_len={len(baseline.after.href)}"
    )
    assert baseline.accepted is None
    assert baseline.after.search.startswith("?")
    assert len(baseline.after.href) > len(start.href)
    cap = len(start.href) + 8
    over = mutate_component(
        GOOGLE_URL, "search", long_search, language=language, max_length=cap
    )
    print(f"search over cap href={over.after.href!r} search={over.after.search!r}")
    assert over.accepted is None
    assert over.after.search == start.search
    assert over.after.hash == start.hash
    assert over.after.href == start.href


def test_hash_over_cap_leaves_url_unchanged() -> None:
    start = inspect_url(GOOGLE_URL)
    long_hash = "h" * 80
    baseline = mutate_component(GOOGLE_URL, "hash", long_hash)
    assert baseline.accepted is None
    assert baseline.after.hash.startswith("#")
    assert len(baseline.after.href) > len(start.href)
    cap = len(start.href) + 8
    over = mutate_component(GOOGLE_URL, "hash", long_hash, max_length=cap)
    print(f"hash over cap href={over.after.href!r} hash={over.after.hash!r}")
    assert over.accepted is None
    assert over.after.hash == start.hash
    assert over.after.search == start.search
    assert over.after.href == start.href


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_short_write_succeeds_under_lowered_cap(language: str) -> None:
    start = inspect_url(GOOGLE_URL, language=language)
    cap = len(start.href) + 32
    assert cap < 2**32 - 1
    written = mutate_component(
        GOOGLE_URL, "pathname", "/x", language=language, max_length=cap
    )
    _require_accepted(written, what="short write under lowered cap")
    print(f"short write href={written.after.href!r} cap={cap}")
    assert written.after.href != start.href
    assert "/x" in written.after.pathname


def test_named_writers_over_cap_refused() -> None:
    long_host = "h" * 40 + ".example"
    cases: list[tuple[str, str, str, str]] = [
        (GOOGLE_URL, "host", long_host, "host"),
        (GOOGLE_URL, "hostname", long_host, "hostname"),
        (GOOGLE_URL, "username", "username", "username"),
        (GOOGLE_URL, "password", "password", "password"),
        (GOOGLE_URL, "href", "https://example.com/" + ("z" * 80), "href"),
    ]
    for input_url, field, value, label in cases:
        before = inspect_url(input_url)
        baseline = mutate_component(input_url, field, value)
        _require_accepted(baseline, what=f"default-cap {label}")
        assert baseline.after.href != before.href, (
            f"default-cap {label} must change href so the over-cap arm "
            f"is not comparing two no-ops"
        )
        cap = len(before.href) + 2
        refused = mutate_component(input_url, field, value, max_length=cap)
        print(
            f"{label} over cap accepted={refused.accepted} "
            f"href_len={len(refused.after.href)} cap={cap}"
        )
        _require_refused(refused, before, what=f"{label} over cap")

    long_http = _grow_pathname_href("http://example.com/", 80)
    proto_ok = mutate_component(long_http, "protocol", "https")
    _require_accepted(proto_ok, what="default-cap http→https")
    proto_before = inspect_url(long_http)
    proto_refused = mutate_component(
        long_http, "protocol", "https", max_length=len(proto_before.href)
    )
    print(f"protocol over cap accepted={proto_refused.accepted}")
    _require_refused(proto_refused, proto_before, what="protocol over cap")

    long_https = _grow_pathname_href(GOOGLE_URL, 80)
    port_ok = mutate_component(long_https, "port", "8080")
    _require_accepted(port_ok, what="default-cap port on long href")
    port_before = inspect_url(long_https)
    port_refused = mutate_component(
        long_https, "port", "8080", max_length=len(port_before.href) + 2
    )
    print(f"port over cap accepted={port_refused.accepted}")
    _require_refused(port_refused, port_before, what="port over cap")


def test_write_percent_expansion_counts_against_cap() -> None:
    start = inspect_url(GOOGLE_URL)
    n = 8
    long_spaces = "/" + (" " * n)
    baseline = mutate_component(GOOGLE_URL, "pathname", long_spaces)
    while len(baseline.after.href) <= len(start.href) + 12:
        n += 4
        long_spaces = "/" + (" " * n)
        baseline = mutate_component(GOOGLE_URL, "pathname", long_spaces)
        _require_accepted(baseline, what="space pathname baseline")
    _require_accepted(baseline, what="space pathname default cap")
    assert "%20" in baseline.after.href
    print(f"space n={n} href_len={len(baseline.after.href)} start={len(start.href)}")
    cap = len(start.href) + 8
    over = mutate_component(
        GOOGLE_URL, "pathname", long_spaces, max_length=cap
    )
    print(f"space over cap accepted={over.accepted}")
    _require_refused(over, start, what="space pathname over cap")
    short = mutate_component(GOOGLE_URL, "pathname", "/ ", max_length=cap)
    _require_accepted(short, what="short space under lowered cap")
    assert "%20" in short.after.href
    assert short.after.href != start.href


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_invalid_percent_host_write_refused_href_path_accepted(
    language: str,
) -> None:
    live_host = mutate_component(
        GOOGLE_URL, "host", "github.com", language=language
    )
    _require_accepted(live_host, what="valid host baseline")
    before = inspect_url(GOOGLE_URL, language=language)
    refused = mutate_component(
        GOOGLE_URL, "host", INVALID_PERCENT_HOST, language=language
    )
    print(f"%X% host accepted={refused.accepted} href={refused.after.href!r}")
    _require_refused(refused, before, what="invalid percent host")
    start = inspect_url(NON_SPEC_EMPTY, language=language)
    print(
        f"%X% non-spec start href={start.href!r} has_host={start.has_hostname}"
    )
    assert start.href == NON_SPEC_EMPTY
    assert start.has_hostname is False
    empty_authority = "non-spec:///x"
    for field in ("host", "hostname"):
        inserted = mutate_component(
            NON_SPEC_EMPTY, field, INVALID_PERCENT_HOST, language=language
        )
        print(
            f"%X% non-spec {field} accepted={inserted.accepted} "
            f"href={inserted.after.href!r} "
            f"host={inserted.after.host!r} "
            f"hostname={inserted.after.hostname!r} "
            f"has_host={inserted.after.has_hostname}"
        )
        _require_accepted(inserted, what=f"%X% {field} on non-spec")
        assert inserted.after.href != NON_SPEC_EMPTY, (
            f"%X% {field} on authority-less non-spec must leave the "
            f"no-authority form; href stayed {inserted.after.href!r}"
        )
        assert inserted.after.has_hostname is True, (
            f"%X% {field} on non-spec must insert an authority; "
            f"has_hostname={inserted.after.has_hostname}"
        )
        assert inserted.after.href != empty_authority, (
            f"%X% {field} on non-spec must not be the empty-authority "
            f"triple-slash; href={inserted.after.href!r}"
        )
        assert inserted.after.host == INVALID_PERCENT_HOST, (
            f"%X% {field} on non-spec must be accepted as that host; "
            f"host={inserted.after.host!r}"
        )
        assert inserted.after.hostname == INVALID_PERCENT_HOST, (
            f"%X% {field} on non-spec must be accepted as that hostname; "
            f"hostname={inserted.after.hostname!r}"
        )
    accepted = mutate_component(
        GOOGLE_URL, "href", "http://www.google.com/%X%", language=language
    )
    _require_accepted(accepted, what="%X% in href path")
    print(f"%X% href={accepted.after.href!r}")
    assert "%X%" in accepted.after.href


# ---------------------------------------------------------------------------
# H. Negative control
# ---------------------------------------------------------------------------


def test_inspect_fails_when_library_absent_from_link_path() -> None:
    baseline = inspect_url(GOOGLE_URL)
    print(f"baseline href={baseline.href!r} origin={baseline.origin!r}")
    assert baseline.href == GOOGLE_HREF
    assert baseline.origin
    kind, result = try_inspect_without_linked_library(GOOGLE_URL)
    print(f"absent-library kind={kind}")
    assert result is not None
    if kind == "link_failed":
        assert result.returncode != 0
        print(f"link stderr={result.stderr_text[:800]!r}")
        return
    produced = inspect_probe_has_href_and_origin(
        result, baseline.href, baseline.origin
    )
    assert not produced, (
        "inspect without the recipe library still produced the successful "
        "Google href and origin"
    )
    assert not inspect_probe_has_href_and_origin(
        result, GOOGLE_HREF, baseline.origin
    )
