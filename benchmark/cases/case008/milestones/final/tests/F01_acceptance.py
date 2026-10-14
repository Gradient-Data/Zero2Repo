# feature: F01
"""FP-01: parse, validate, and serialize URLs (C++ library and matching C interface)."""

from __future__ import annotations

from functools import lru_cache

import pytest

from _helpers import (
    GOOGLE_HREF,
    GOOGLE_URL,
    MIXED_IPV4_HOSTNAME,
    MIXED_IPV4_HREF,
    MIXED_IPV4_INPUT,
    NFC_ACE_HOSTNAME,
    NFC_PERCENT_URL,
    NFC_UTF8_HOST_URL,
    NONPUBLIC_IPV4_TOKENS,
    SEVEN_ELEVEN_ACE_HOST,
    SEVEN_ELEVEN_HREF,
    SEVEN_ELEVEN_INPUT,
    UINT32_MAX,
    can_parse_url,
    dotted_ipv4_from_mixed_octets,
    file_href_via_pathname,
    get_max_input_length_value,
    href_from_file_path,
    idna_to_ascii,
    idna_unicode_then_ascii,
    parse_long_then_restore,
    parse_url,
    probe_result_has_href,
    require_can_parse_agrees,
    require_parse_failure,
    require_parse_href,
    set_and_restore_cap_values,
    try_parse_without_linked_library,
    unique_token,
)

BOTH_LANGS = ("c++", "c")


@lru_cache(maxsize=4)
def _expansion_over_cap_url(cap: int = 1024) -> str:
    """Raw input under *cap*; `%20` expansion of path spaces makes href longer than *cap*."""
    prefix = "https://example.com/x"
    suffix = "z"
    n = max(1, (cap + 1 - len(prefix) - len(suffix)) // 3 + 8)
    url = prefix + (" " * n) + suffix
    while len(url) < cap:
        live = parse_url(url)
        assert live.ok, (
            f"default-cap parse of expansion candidate failed n={n} "
            f"stderr={live.stderr!r}"
        )
        print(
            f"expansion candidate n={n} raw={len(url)} href_len={len(live.href)}"
        )
        if len(live.href) > cap:
            assert "%20" in live.href
            return url
        n += 16
        url = prefix + (" " * n) + suffix
    raise AssertionError("could not construct raw<cap href>cap URL")


def _file_path_expansion_over_cap(cap: int = 1024) -> str:
    n = max(1, cap // 3)
    while True:
        path = "/x" + (" " * n) + "z"
        if len(path) >= cap:
            raise AssertionError("raw path reached the cap before href did")
        href = href_from_file_path(path)
        print(f"file expansion n={n} raw={len(path)} href_len={len(href)}")
        assert href, "default cap must produce a non-empty file: href"
        assert href.startswith("file:")
        assert "%20" in href
        if len(href) > cap:
            return path
        n += 16


# ---------------------------------------------------------------------------
# A. Absolute URL → WHATWG href
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_google_href_gains_trailing_slash(language: str) -> None:
    outcome = require_parse_href(GOOGLE_URL, GOOGLE_HREF, language=language)
    print(f"google href={outcome.href!r} language={language}")
    assert outcome.href != GOOGLE_URL


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_idn_host_and_non_ascii_path_normalized(language: str) -> None:
    assert "\u2011" in SEVEN_ELEVEN_INPUT
    assert "\u00e9" in SEVEN_ELEVEN_INPUT
    outcome = require_parse_href(
        SEVEN_ELEVEN_INPUT, SEVEN_ELEVEN_HREF, language=language
    )
    print(f"seven-eleven href={outcome.href!r} language={language}")
    assert outcome.href != SEVEN_ELEVEN_INPUT
    assert outcome.hostname == SEVEN_ELEVEN_ACE_HOST


def test_two_nonpublic_idn_hosts_distinct_ace() -> None:
    host_a = "münchen.example"
    url_a = "http://münchen.example/café"
    host_b = "δοκιμή.test"
    url_b = "http://δοκιμή.test/ψ"
    parsed_a = parse_url(url_a)
    parsed_b = parse_url(url_b)
    print(f"idn a href={parsed_a.href!r} host={parsed_a.hostname!r}")
    print(f"idn b href={parsed_b.href!r} host={parsed_b.hostname!r}")
    assert parsed_a.ok and parsed_b.ok
    assert parsed_a.href != url_a
    assert parsed_b.href != url_b
    assert parsed_a.hostname is not None and parsed_b.hostname is not None
    assert parsed_a.hostname.isascii() and parsed_b.hostname.isascii()
    assert "xn--" in parsed_a.hostname and "xn--" in parsed_b.hostname
    ascii_a = idna_to_ascii(host_a)
    ascii_b = idna_to_ascii(host_b)
    assert ascii_a.ok and ascii_b.ok
    assert parsed_a.hostname == ascii_a.payload
    assert parsed_b.hostname == ascii_b.payload
    assert parsed_a.hostname != parsed_b.hostname
    assert "é" not in parsed_a.href
    assert "ψ" not in parsed_b.href
    assert "%" in parsed_a.href and "%" in parsed_b.href


def test_leading_trailing_space_stripped() -> None:
    wrapped = " " + GOOGLE_URL + " "
    outcome = require_parse_href(wrapped, GOOGLE_HREF)
    print(f"space-wrapped href={outcome.href!r}")
    assert outcome.ok
    assert outcome.href == GOOGLE_HREF
    assert outcome.href != wrapped


def test_leading_trailing_c0_stripped() -> None:
    wrapped = "\x01" + GOOGLE_URL + "\x01"
    outcome = require_parse_href(wrapped, GOOGLE_HREF)
    print(f"c0-wrapped href={outcome.href!r}")
    assert outcome.ok
    assert outcome.href == GOOGLE_HREF
    assert outcome.href != wrapped


def test_runtime_url_leading_trailing_space_stripped() -> None:
    token = unique_token()
    inner = f"https://example.com/{token}"
    bare = parse_url(inner)
    wrapped = parse_url(" " + inner + " ")
    print(f"runtime token={token} bare={bare.href!r} wrapped={wrapped.href!r}")
    assert bare.ok and wrapped.ok
    assert wrapped.href == bare.href
    assert token in wrapped.href


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_tab_in_query_removed_not_percent_encoded(language: str) -> None:
    raw = "http://ab?a" + "\t" + "b"
    outcome = require_parse_href(raw, "http://ab/?ab", language=language)
    print(f"tab-query href={outcome.href!r} language={language}")
    assert "%09" not in outcome.href


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_space_in_query_percent_encoded(language: str) -> None:
    outcome = require_parse_href(
        "http://ab?x y", "http://ab/?x%20y", language=language
    )
    print(f"space-query href={outcome.href!r} language={language}")
    assert outcome.ok
    assert outcome.href == "http://ab/?x%20y"
    assert "%20" in outcome.href


def test_lf_and_cr_in_query_removed_like_tab() -> None:
    expected = "http://ab/?ab"
    tab = require_parse_href("http://ab?a" + "\t" + "b", expected)
    lf = require_parse_href("http://ab?a" + "\n" + "b", expected)
    cr = require_parse_href("http://ab?a" + "\r" + "b", expected)
    print(f"tab={tab.href!r} lf={lf.href!r} cr={cr.href!r}")
    assert lf.href == tab.href
    assert cr.href == tab.href
    assert "%0A" not in lf.href and "%0D" not in cr.href


def test_tab_lf_cr_in_path_removed_space_percent20() -> None:
    tab = parse_url("http://example.com/a" + "\t" + "b")
    lf = parse_url("http://example.com/a" + "\n" + "b")
    cr = parse_url("http://example.com/a" + "\r" + "b")
    space = parse_url("http://example.com/a b")
    print(
        f"path tab={tab.href!r} lf={lf.href!r} cr={cr.href!r} space={space.href!r}"
    )
    assert tab.ok and lf.ok and cr.ok and space.ok
    assert tab.href == "http://example.com/ab"
    assert lf.href == tab.href
    assert cr.href == tab.href
    assert "%09" not in tab.href
    assert "%0A" not in lf.href
    assert "%0D" not in cr.href
    assert space.href != tab.href
    assert "%20" in space.href


def test_runtime_path_space_percent20_plus_kept() -> None:
    token = unique_token()
    spaced = parse_url(f"https://example.com/{token} x")
    plused = parse_url(f"https://example.com/{token}+x")
    print(f"space href={spaced.href!r} plus={plused.href!r}")
    assert spaced.ok and plused.ok
    assert token in spaced.href and "%20" in spaced.href
    assert token in plused.href
    assert "+" in plused.href
    assert "%20" not in plused.href
    assert f"{token}+x" in plused.href


def test_c_parse_agrees_on_named_hrefs() -> None:
    language = "c"
    require_parse_href(GOOGLE_URL, GOOGLE_HREF, language=language)
    require_parse_href(SEVEN_ELEVEN_INPUT, SEVEN_ELEVEN_HREF, language=language)
    require_parse_href(MIXED_IPV4_INPUT, MIXED_IPV4_HREF, language=language)
    require_parse_href(
        "http://ab?a" + "\t" + "b", "http://ab/?ab", language=language
    )
    require_parse_href("http://ab?x y", "http://ab/?x%20y", language=language)
    nfc = parse_url(NFC_PERCENT_URL, language=language)
    assert nfc.ok and nfc.hostname == NFC_ACE_HOSTNAME
    require_parse_href("file:c:/..", "file:///c:/", language=language)
    require_parse_href("file:c:x/..", "file:///", language=language)
    require_parse_href("http://.", "http://./", language=language)
    require_parse_href("a:/..", "a:/", language=language)
    print(f"named href table ok language={language}")


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_dot_only_special_scheme_hostname(language: str) -> None:
    """WHATWG: a host that is only `.` stays a host, not a path."""
    outcome = require_parse_href("http://.", "http://./", language=language)
    assert outcome.hostname == "."
    require_parse_href("https://.", "https://./", language=language)
    require_parse_href("http://./path", "http://./path", language=language)
    print(f"dot-only host ok language={language} href={outcome.href!r}")


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_nonspecial_scheme_path_dotdot_is_not_file_drive(language: str) -> None:
    """WHATWG: `a:` is not special; `a:/..` collapses the path, not a drive."""
    require_parse_href("a:/..", "a:/", language=language)
    require_parse_href("a:/../x", "a:/x", language=language)
    print(f"nonspecial a:/.. ok language={language}")


# ---------------------------------------------------------------------------
# B. Relative input and base
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_relative_fails_without_base(language: str) -> None:
    outcome = require_parse_failure("/hello", language=language)
    print(f"/hello without base failed language={language}")
    assert not outcome.ok
    assert outcome.href is None


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_relative_hello_resolves_against_base(language: str) -> None:
    outcome = require_parse_href(
        "/hello",
        "https://www.google.com/hello",
        base=GOOGLE_URL,
        language=language,
    )
    print(f"/hello with google base language={language}")
    assert outcome.ok
    assert outcome.href == "https://www.google.com/hello"


def test_dotdot_relative_resolves() -> None:
    outcome = require_parse_href(
        "../other/page",
        "https://example.com/other/page",
        base="https://example.com/dir/",
    )
    print(f"dotdot href={outcome.href!r}")
    assert outcome.ok
    assert outcome.href == "https://example.com/other/page"


def test_dotdot_relative_drops_runtime_base_segment() -> None:
    token = unique_token()
    base = f"https://example.com/{token}/"
    dropped = parse_url("../x", base=base)
    kept = parse_url("x", base=base)
    print(f"dotdot href={dropped.href!r} sibling={kept.href!r} token={token}")
    assert dropped.ok and kept.ok
    assert token not in dropped.href
    assert token in kept.href


def test_hello_world_relative_with_and_without_base() -> None:
    require_parse_failure("/hello-world")
    ok = parse_url("/hello-world", base=GOOGLE_URL)
    print(f"/hello-world href={ok.href!r}")
    assert ok.ok
    assert ok.href is not None
    assert ok.href.startswith("https://www.google.com")
    assert "hello-world" in ok.href


def test_c_parse_relative_with_base() -> None:
    language = "c"
    failed = require_parse_failure("/hello", language=language)
    resolved = require_parse_href(
        "/hello",
        "https://www.google.com/hello",
        base=GOOGLE_URL,
        language=language,
    )
    print(f"c relative fail ok={failed.ok} resolved={resolved.href!r}")
    assert not failed.ok
    assert failed.href is None
    assert resolved.ok
    assert resolved.href == "https://www.google.com/hello"


# ---------------------------------------------------------------------------
# C. WHATWG hosts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_mixed_base_ipv4_canonicalized(language: str) -> None:
    outcome = require_parse_href(
        MIXED_IPV4_INPUT, MIXED_IPV4_HREF, language=language
    )
    print(f"mixed ipv4 host={outcome.hostname!r} language={language}")
    assert outcome.hostname == MIXED_IPV4_HOSTNAME


def test_mixed_base_ipv4_non_public_octets() -> None:
    dotted = dotted_ipv4_from_mixed_octets(NONPUBLIC_IPV4_TOKENS)
    assert dotted != MIXED_IPV4_HOSTNAME
    raw = "http://" + ".".join(NONPUBLIC_IPV4_TOKENS)
    expected_href = f"http://{dotted}/"
    outcome = require_parse_href(raw, expected_href)
    print(f"nonpublic ipv4 {raw} -> {outcome.href!r}")
    assert outcome.hostname == dotted


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_ipv6_brackets_and_default_port_omitted(language: str) -> None:
    outcome = require_parse_href(
        "http://[::1]:80/", "http://[::1]/", language=language
    )
    print(f"ipv6 href={outcome.href!r} language={language}")
    assert "[" in outcome.href and "]" in outcome.href
    assert ":80" not in outcome.href


def test_ipv6_second_address_not_identity_copy() -> None:
    first = require_parse_href("http://[::1]:80/", "http://[::1]/")
    # No-zero groups: IPv6-in-brackets plus default-port omit fix the href
    # without claiming compression or pairwise-distinct IPv6 serializations.
    second_input = "http://[1:2:3:4:5:6:7:8]:80/"
    second = require_parse_href(second_input, "http://[1:2:3:4:5:6:7:8]/")
    print(f"ipv6 first={first.href!r} second={second.href!r}")
    assert "[" in first.href and "]" in first.href
    assert ":80" not in first.href
    assert "[" in second.href and "]" in second.href
    assert ":80" not in second.href
    assert second.href != second_input


def test_special_host_ascii_case_insensitive() -> None:
    outcome = parse_url("http://GOOgoo.com", base="http://other.com/")
    print(f"GOOgoo hostname={outcome.hostname!r} href={outcome.href!r}")
    assert outcome.ok
    assert outcome.hostname == "googoo.com"


def test_special_scheme_ascii_case_insensitive_default_port() -> None:
    outcome = parse_url("HTTP://example.com:80/")
    print(f"HTTP href={outcome.href!r}")
    assert outcome.ok
    assert outcome.href is not None
    # Scheme matching is ASCII-case-insensitive; do not pin scheme letter case.
    assert outcome.href.lower() == "http://example.com/"
    assert "example.com" in outcome.href
    assert ":80" not in outcome.href


# ---------------------------------------------------------------------------
# D. Path, default ports, file drive letter
# ---------------------------------------------------------------------------


def test_path_space_percent20_plus_kept() -> None:
    space = require_parse_href(
        "http://www.google.com/%37/ /",
        "http://www.google.com/%37/%20/",
    )
    plus = parse_url("http://www.google.com/%37+/")
    print(f"percent37 space={space.href!r} plus={plus.href!r}")
    assert plus.ok
    assert "%37+" in plus.href


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_invalid_percent_sequence_kept_in_path(language: str) -> None:
    outcome = parse_url("http://www.google.com/%X%", language=language)
    print(f"invalid-percent path href={outcome.href!r} language={language}")
    assert outcome.ok
    assert "%X%" in outcome.href


def test_default_ports_omitted_for_each_special_scheme() -> None:
    cases = (
        ("http://example.com:80/", "http://example.com/", ":80"),
        ("ws://example.com:80/", "ws://example.com/", ":80"),
        ("https://example.com:443/", "https://example.com/", ":443"),
        ("wss://example.com:443/", "wss://example.com/", ":443"),
        ("ftp://example.com:21/", "ftp://example.com/", ":21"),
    )
    for raw, expected, port in cases:
        outcome = require_parse_href(raw, expected)
        print(f"default port {raw} -> {outcome.href!r}")
        assert "example.com" in outcome.href
        assert port not in outcome.href


def test_non_default_port_kept_on_special_scheme() -> None:
    default = require_parse_href("http://example.com:80/", "http://example.com/")
    other = parse_url("http://example.com:8080/")
    print(f"default={default.href!r} other={other.href!r}")
    assert other.ok
    assert other.href is not None
    assert other.href != default.href
    assert "example.com" in other.href
    assert "8080" in other.href
    stripped_default = default.href.replace("example.com", "", 1)
    stripped_other = other.href.replace("example.com", "", 1)
    print(f"stripped default={stripped_default!r} other={stripped_other!r}")
    assert "8080" not in stripped_default
    assert "80" not in stripped_default
    assert "8080" in stripped_other


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_file_drive_letter_protected_from_dotdot(language: str) -> None:
    outcome = require_parse_href(
        "file:c:/..", "file:///c:/", language=language
    )
    print(f"drive-protected href={outcome.href!r} language={language}")
    assert outcome.ok
    assert outcome.href == "file:///c:/"


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_file_longer_segment_not_drive_protected(language: str) -> None:
    outcome = require_parse_href(
        "file:c:x/..", "file:///", language=language
    )
    print(f"drive-shortened href={outcome.href!r} language={language}")
    assert outcome.ok
    assert outcome.href == "file:///"


def test_file_drive_letter_rule_second_letter() -> None:
    letter = "d"
    protected = parse_url(f"file:{letter}:/..")
    shortened = parse_url(f"file:{letter}x/..")
    print(f"letter={letter} protected={protected.href!r} short={shortened.href!r}")
    assert protected.ok and shortened.ok
    assert f"file:///{letter}:/" in protected.href
    assert shortened.href == "file:///"


# ---------------------------------------------------------------------------
# E. Filesystem path → file: URL
# ---------------------------------------------------------------------------


def test_href_from_file_matches_pathname_assignment() -> None:
    paths = (
        "/home/user/txt.txt",
        "",
        "C:\\blabala\\fdfds\\back.txt",
    )
    hrefs: list[str] = []
    for path in paths:
        converted = href_from_file_path(path)
        assigned = file_href_via_pathname(path)
        print(f"path={path!r} converted={converted!r} assigned={assigned!r}")
        assert converted == assigned
        assert converted.startswith("file:")
        assert converted != ""
        for segment in path.replace("\\", "/").split("/"):
            if segment and not (len(segment) == 2 and segment[1] == ":"):
                assert segment in converted, (
                    f"path {path!r} must be reflected in file: href "
                    f"{converted!r}; missing segment {segment!r}"
                )
        hrefs.append(converted)
    posix_href, empty_href, windows_href = hrefs
    assert "txt.txt" in posix_href
    assert "back.txt" in windows_href
    assert "txt.txt" not in empty_href
    assert "back.txt" not in empty_href
    assert len(set(hrefs)) == len(hrefs), (
        f"distinct paths must not share one file: href; got {hrefs!r}"
    )


def test_href_from_file_empty_when_raw_length_exceeds_cap() -> None:
    baseline = href_from_file_path("/home/user/txt.txt")
    print(f"baseline file href={baseline!r} len={len(baseline)}")
    assert baseline.startswith("file:")
    long_path = "a" * 1025
    assert len(long_path) > 1024
    empty = href_from_file_path(long_path, max_length=1024)
    print(f"raw-over-cap converted={empty!r}")
    assert empty == ""
    restored = href_from_file_path("/home/user/txt.txt")
    assert restored.startswith("file:") and restored != ""


def test_href_from_file_empty_when_percent_expansion_exceeds_cap() -> None:
    over = _file_path_expansion_over_cap(1024)
    assert len(over) < 1024
    default_href = href_from_file_path(over)
    print(f"over path raw={len(over)} default href_len={len(default_href)}")
    assert default_href.startswith("file:") and "%20" in default_href
    assert len(default_href) > 1024
    empty = href_from_file_path(over, max_length=1024)
    print(f"expansion-over-cap converted={empty!r}")
    assert empty == ""
    under = "/x yz"
    under_default = href_from_file_path(under)
    print(f"under default={under_default!r} len={len(under_default)}")
    assert under_default.startswith("file:")
    assert "%20" in under_default
    assert len(under_default) < 1024
    under_capped = href_from_file_path(under, max_length=1024)
    assigned = file_href_via_pathname(under)
    assert under_capped.startswith("file:") and under_capped != ""
    assert under_capped == assigned


# ---------------------------------------------------------------------------
# F. Can-parse iff parse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_can_parse_agrees_on_fixed_inputs(language: str) -> None:
    successes = (
        GOOGLE_URL,
        SEVEN_ELEVEN_INPUT,
        MIXED_IPV4_INPUT,
        "file:c:/..",
        "http://ab?a" + "\t" + "b",
        "http://ab?x y",
        "https://example.com/ok",
        "file:c:x/..",
    )
    failures = (
        "",
        "/hello",
        "http://www.google com/",
        "http://www.google%X%.com/",
    )
    for raw in successes:
        parsed, can = require_can_parse_agrees(raw, language=language)
        print(f"can-parse yes {raw!r} href={parsed.href!r} language={language}")
        assert can is True
        alone = can_parse_url(raw, language=language)
        assert alone is True
    for raw in failures:
        parsed, can = require_can_parse_agrees(raw, language=language)
        print(f"can-parse no {raw!r} language={language}")
        assert can is False
        alone = can_parse_url(raw, language=language)
        assert alone is False


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_can_parse_agrees_with_base(language: str) -> None:
    parsed, can = require_can_parse_agrees(
        "/hello", base=GOOGLE_URL, language=language
    )
    print(f"can-parse /hello+base href={parsed.href!r} language={language}")
    assert can is True
    assert can_parse_url("/hello", base=GOOGLE_URL, language=language) is True
    assert can_parse_url("/hello", language=language) is False


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_can_parse_agrees_on_length_cap_raw_and_expansion(language: str) -> None:
    long_url = "https://example.com/" + ("a" * 1024)
    parsed_long, can_long = require_can_parse_agrees(
        long_url, language=language, max_length=1024
    )
    print(f"cap long can={can_long} language={language}")
    assert parsed_long.ok is False and can_long is False
    parsed_ok, can_ok = require_can_parse_agrees(
        "https://example.com/ok", language=language, max_length=1024
    )
    print(f"cap ok href={parsed_ok.href!r} language={language}")
    assert parsed_ok.ok and can_ok
    over = _expansion_over_cap_url(1024)
    parsed_over, can_over = require_can_parse_agrees(
        over, language=language, max_length=1024
    )
    print(f"cap expansion-over can={can_over} raw={len(over)}")
    assert parsed_over.ok is False and can_over is False
    under = "https://example.com/a b"
    parsed_under, can_under = require_can_parse_agrees(
        under, language=language, max_length=1024
    )
    print(f"cap under-space href={parsed_under.href!r} language={language}")
    assert parsed_under.ok and can_under
    assert parsed_under.href is not None and "%20" in parsed_under.href
    assert len(parsed_under.href) < 1024


def test_c_can_parse_agrees_on_discriminators() -> None:
    language = "c"
    successes = (
        SEVEN_ELEVEN_INPUT,
        "file:c:/..",
        MIXED_IPV4_INPUT,
        "http://ab?a" + "\t" + "b",
        "http://ab?x y",
    )
    failures = (
        "http://www.google com/",
        "http://www.google%X%.com/",
    )
    for raw in successes:
        parsed, can = require_can_parse_agrees(raw, language=language)
        print(f"c can-parse yes {raw!r} href={parsed.href!r}")
        assert can is True
        assert parsed.ok
        alone = can_parse_url(raw, language=language)
        assert alone is True
    for raw in failures:
        parsed, can = require_can_parse_agrees(raw, language=language)
        print(f"c can-parse no {raw!r}")
        assert can is False
        assert parsed.ok is False
        alone = can_parse_url(raw, language=language)
        assert alone is False
    print(f"c discriminators can-parse ok language={language}")


# ---------------------------------------------------------------------------
# G. Standalone ToASCII / ToUnicode and host ToASCII
# ---------------------------------------------------------------------------


def test_to_ascii_plain_ascii_domain_succeeds() -> None:
    outcome = idna_to_ascii("www.google.com")
    print(f"toascii google payload={outcome.payload!r} ok={outcome.ok}")
    assert outcome.ok
    assert outcome.payload == "www.google.com"


def test_to_ascii_embedded_space_succeeds_while_host_parse_fails() -> None:
    ascii_space = idna_to_ascii("www.google com")
    host_parse = parse_url("http://www.google com/")
    print(
        f"toascii space ok={ascii_space.ok} payload={ascii_space.payload!r} "
        f"parse ok={host_parse.ok}"
    )
    assert ascii_space.ok
    assert ascii_space.payload == "www.google com"
    assert not host_parse.ok
    assert host_parse.href is None


def test_to_ascii_20000_a_fails_short_idn_still_punycode() -> None:
    huge = "a" * 20000
    huge_out = idna_to_ascii(huge)
    print(
        f"20000-a ok={huge_out.ok} payload_len={len(huge_out.payload)} "
        f"payload_prefix={huge_out.payload[:16]!r}"
    )
    assert not huge_out.ok
    assert huge_out.payload != huge
    short = idna_to_ascii("münchen")
    print(f"short idn ok={short.ok} payload={short.payload!r}")
    assert short.ok
    assert short.payload.isascii()
    assert "xn--" in short.payload
    assert short.payload != "münchen"


def test_to_ascii_matches_parsed_http_hostname() -> None:
    parsed = parse_url(SEVEN_ELEVEN_INPUT)
    host = "www.7\u2011Eleven.com"
    ascii_out = idna_to_ascii(host)
    print(
        f"parsed host={parsed.hostname!r} toascii={ascii_out.payload!r}"
    )
    assert parsed.ok
    assert ascii_out.ok
    assert parsed.hostname == ascii_out.payload
    assert parsed.hostname == SEVEN_ELEVEN_ACE_HOST


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_http_host_nfc_reordering_hostname(language: str) -> None:
    outcome = parse_url(NFC_PERCENT_URL, language=language)
    print(f"nfc percent host={outcome.hostname!r} language={language}")
    assert outcome.ok
    assert outcome.hostname == NFC_ACE_HOSTNAME


def test_nfc_equivalent_bytes_same_ace() -> None:
    percent = parse_url(NFC_PERCENT_URL)
    utf8 = parse_url(NFC_UTF8_HOST_URL)
    print(f"percent host={percent.hostname!r} utf8 host={utf8.hostname!r}")
    assert percent.ok and utf8.ok
    assert NFC_UTF8_HOST_URL != NFC_PERCENT_URL
    assert percent.hostname == NFC_ACE_HOSTNAME
    assert utf8.hostname == NFC_ACE_HOSTNAME


def test_to_unicode_reverse_roundtrip_to_ascii() -> None:
    for ace in (NFC_ACE_HOSTNAME, SEVEN_ELEVEN_ACE_HOST):
        trip = idna_unicode_then_ascii(ace)
        print(
            f"ace={ace!r} uni={trip.unicode_payload!r} "
            f"ascii={trip.ascii_payload!r} ascii_ok={trip.ascii_ok}"
        )
        assert trip.unicode_ok
        assert trip.unicode_payload != ace
        assert trip.ascii_ok
        assert trip.ascii_payload == ace


# ---------------------------------------------------------------------------
# H. Length cap and unusable failed parse
# ---------------------------------------------------------------------------


def test_length_cap_round_trip_and_default() -> None:
    default = get_max_input_length_value()
    print(f"default cap={default}")
    assert default == UINT32_MAX
    set_to, restored = set_and_restore_cap_values(1024)
    print(f"set={set_to} restored={restored}")
    assert set_to == 1024
    assert restored == UINT32_MAX


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_length_cap_1024_rejects_long_path_accepts_ok(language: str) -> None:
    ok = parse_url("https://example.com/ok", language=language, max_length=1024)
    print(f"ok href={ok.href!r} language={language}")
    assert ok.ok
    assert ok.href is not None
    long_url = "https://example.com/" + ("a" * 1024)
    bad = parse_url(long_url, language=language, max_length=1024)
    print(f"long ok={bad.ok} language={language}")
    assert not bad.ok
    assert bad.href is None


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_length_cap_rejects_percent_encoding_expansion(language: str) -> None:
    over = _expansion_over_cap_url(1024)
    print(f"expansion-over raw={len(over)} language={language}")
    assert len(over) < 1024
    bad = parse_url(over, language=language, max_length=1024)
    can = can_parse_url(over, language=language, max_length=1024)
    print(f"expansion-over parse ok={bad.ok} can={can}")
    assert not bad.ok
    assert bad.href is None
    assert can is False


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_length_cap_space_under_cap_still_succeeds(language: str) -> None:
    under = "https://example.com/a b"
    outcome = parse_url(under, language=language, max_length=1024)
    print(f"under-space href={outcome.href!r} language={language}")
    assert outcome.ok
    assert outcome.href is not None
    assert "%20" in outcome.href
    assert len(outcome.href) < 1024


def test_length_cap_restore_accepts_ordinary() -> None:
    long_url = "https://example.com/" + ("a" * 1024)
    outcome = parse_long_then_restore(
        long_url, "https://example.com/ok", max_length=1024
    )
    print(
        f"long_ok={outcome.long_ok} restore_ok={outcome.restore_ok} "
        f"href={outcome.restore_href!r}"
    )
    assert not outcome.long_ok
    assert outcome.restore_ok
    assert outcome.restore_href is not None
    assert outcome.restore_href.startswith("https://example.com/ok")


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_empty_fragment_space_host_fail(language: str) -> None:
    cases = ("", "#x", "http://www.google com/", "http://www.google%X%.com/")
    failed: list[str] = []
    for raw in cases:
        outcome = require_parse_failure(raw, language=language)
        print(f"fail {raw!r} language={language} ok={outcome.ok}")
        assert not outcome.ok
        assert outcome.href is None
        failed.append(raw)
    assert failed == list(cases)


@pytest.mark.parametrize("language", BOTH_LANGS)
def test_invalid_percent_host_fails_unlike_invalid_percent_path(
    language: str,
) -> None:
    host = parse_url("http://www.google%X%.com/", language=language)
    path = parse_url("http://www.google.com/%X%", language=language)
    print(
        f"percent-host ok={host.ok} percent-path ok={path.ok} "
        f"href={path.href!r} language={language}"
    )
    assert not host.ok
    assert host.href is None
    assert path.ok
    assert path.href is not None
    assert "%X%" in path.href


def test_failed_parse_not_usable_url() -> None:
    success = parse_url(GOOGLE_URL)
    print(f"success href={success.href!r}")
    assert success.ok
    assert success.href == GOOGLE_HREF
    failed = parse_url("")
    print(f"empty ok={failed.ok} href={failed.href!r}")
    assert not failed.ok
    assert failed.href is None


def test_c_parse_failure_not_usable() -> None:
    language = "c"
    success = parse_url(GOOGLE_URL, language=language)
    assert success.ok and success.href == GOOGLE_HREF
    failed = parse_url("http://www.google com/", language=language)
    print(f"c fail ok={failed.ok} href={failed.href!r} language={language}")
    assert not failed.ok
    assert failed.href is None


# ---------------------------------------------------------------------------
# I. Negative control
# ---------------------------------------------------------------------------


def test_parse_fails_when_library_absent_from_link_path() -> None:
    baseline = parse_url(GOOGLE_URL)
    print(f"baseline href={baseline.href!r}")
    assert baseline.ok
    assert baseline.href == GOOGLE_HREF
    kind, result = try_parse_without_linked_library(GOOGLE_URL)
    print(f"absent-library kind={kind}")
    assert result is not None
    if kind == "link_failed":
        assert result.returncode != 0
        print(f"link stderr={result.stderr_text[:800]!r}")
        return
    produced = probe_result_has_href(result, GOOGLE_HREF)
    assert not produced, (
        "parse without the recipe library still produced the successful href"
    )
