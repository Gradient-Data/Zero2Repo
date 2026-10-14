"""Sealed helpers for FP-01 parse, FP-02 inspect/mutate, FP-03 search
params, and FP-04 URLPattern matching.

Feature tests import names from this module. Probe sources are compiled
against the recipe-built library via ``_harness.invoke``; compile or
protocol failures raise ``HarnessError`` and are never mapped to a
product parse/IDNA/write/search-params/URLPattern failure.
"""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from _harness import (
    DEFAULT_CXX_STD,
    DEFAULT_TIMEOUT,
    HarnessError,
    RunResult,
    cxx_compiler,
    include_dir,
    invoke,
    run_command,
)

# ---------------------------------------------------------------------------
# Fixed sample inputs. Hyphen in the 7-Eleven host is U+2011.
# ---------------------------------------------------------------------------

UINT32_MAX: int = 2**32 - 1

GOOGLE_URL = "https://www.google.com"
GOOGLE_HREF = "https://www.google.com/"

SEVEN_ELEVEN_INPUT = (
    "https://www.7\u2011Eleven.com/Home/Privacy/Montr\u00e9al"
)
SEVEN_ELEVEN_HREF = (
    "https://www.xn--7eleven-506c.com/Home/Privacy/Montr%C3%A9al"
)
SEVEN_ELEVEN_ACE_HOST = "www.xn--7eleven-506c.com"

NFC_PERCENT_URL = "http://%C3%A1%CC%A3/"
NFC_UTF8_HOST_URL = "http://\u00e1\u0323/"
NFC_ACE_HOSTNAME = "xn--lsa752l"

MIXED_IPV4_INPUT = "http://0300.168.0xF0"
MIXED_IPV4_HOSTNAME = "192.168.0.240"
MIXED_IPV4_HREF = "http://192.168.0.240/"

# Four mixed-base octets whose decimal form is not 192.168.0.240.
NONPUBLIC_IPV4_TOKENS: tuple[str, str, str, str] = ("0x11", "032", "0x4", "0x5")


# ---------------------------------------------------------------------------
# Probe sources (C++ library parse vs matching C interface)
# ---------------------------------------------------------------------------

_CXX_PROBE = r"""
#include "hrefparse.h"

#include <cstdint>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

static std::string read_stdin() {
  std::string data;
  char buf[4096];
  while (true) {
    std::cin.read(buf, sizeof(buf));
    const std::streamsize n = std::cin.gcount();
    if (n <= 0) {
      break;
    }
    data.append(buf, static_cast<size_t>(n));
  }
  return data;
}

static void emit_status(const char* status) { std::cout << status << '\n'; }

static void emit_field(const char* key, std::string_view val) {
  std::cout << key << ' ' << val.size() << '\n';
  std::cout.write(val.data(), static_cast<std::streamsize>(val.size()));
  std::cout.put('\n');
}

static void emit_can(bool yes) {
  std::cout << "CAN " << (yes ? "yes" : "no") << '\n';
}

int main(int argc, char** argv) {
  std::ios::sync_with_stdio(false);
  if (argc < 2) {
    std::cerr << "missing op\n";
    return 2;
  }
  const std::string op = argv[1];
  bool have_max = false;
  uint32_t max_value = 0;
  bool have_base = false;
  std::string base;
  std::string ok_url;
  for (int i = 2; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--max" && i + 1 < argc) {
      max_value = static_cast<uint32_t>(std::stoul(argv[++i]));
      have_max = true;
    } else if (arg == "--base" && i + 1 < argc) {
      base = argv[++i];
      have_base = true;
    } else if (arg == "--ok" && i + 1 < argc) {
      ok_url = argv[++i];
    } else {
      std::cerr << "unknown arg\n";
      return 2;
    }
  }
  const std::string input = read_stdin();
  if (have_max) {
    hrefparse::set_max_input_length(max_value);
  }

  auto run_parse = [&](const std::string& url_input,
                         bool with_base) -> hrefparse::result<hrefparse::url_aggregator> {
    if (with_base) {
      auto parsed_base = hrefparse::parse(std::string_view(base));
      if (!parsed_base) {
        return hrefparse::parse(std::string_view());
      }
      return hrefparse::parse(std::string_view(url_input), &*parsed_base);
    }
    return hrefparse::parse(std::string_view(url_input));
  };

  auto emit_parse = [&](hrefparse::result<hrefparse::url_aggregator> parsed) {
    if (parsed) {
      const std::string href(parsed->get_href());
      const std::string host(parsed->get_hostname());
      emit_status("OK");
      emit_field("HREF", href);
      emit_field("HOST", host);
    } else {
      emit_status("FAIL");
    }
  };

  auto run_can = [&](const std::string& url_input) -> bool {
    if (have_base) {
      std::string_view view(base);
      return hrefparse::can_parse(std::string_view(url_input), &view);
    }
    return hrefparse::can_parse(std::string_view(url_input));
  };

  if (op == "parse") {
    emit_parse(run_parse(input, have_base));
    return 0;
  }
  if (op == "can") {
    emit_can(run_can(input));
    return 0;
  }
  if (op == "both") {
    emit_parse(run_parse(input, have_base));
    emit_can(run_can(input));
    return 0;
  }
  if (op == "file") {
    const std::string href = hrefparse::href_from_file(std::string_view(input));
    emit_status("OK");
    emit_field("HREF", href);
    return 0;
  }
  if (op == "pathname") {
    auto parsed = hrefparse::parse(std::string_view("file://"));
    if (!parsed) {
      std::cerr << "file:// parse failed\n";
      return 2;
    }
    parsed->set_pathname(std::string_view(input));
    const std::string href(parsed->get_href());
    emit_status("OK");
    emit_field("HREF", href);
    return 0;
  }
  if (op == "cap-get") {
    const std::string cap = std::to_string(hrefparse::get_max_input_length());
    emit_status("OK");
    emit_field("CAP", cap);
    return 0;
  }
  if (op == "cap-rw") {
    if (!have_max) {
      std::cerr << "cap-rw requires --max\n";
      return 2;
    }
    hrefparse::set_max_input_length(max_value);
    const std::string after_set = std::to_string(hrefparse::get_max_input_length());
    hrefparse::set_max_input_length(std::numeric_limits<uint32_t>::max());
    const std::string after_default =
        std::to_string(hrefparse::get_max_input_length());
    emit_status("OK");
    emit_field("SET", after_set);
    emit_field("DEFAULT", after_default);
    return 0;
  }
  if (op == "cap-restore") {
    if (ok_url.empty()) {
      std::cerr << "cap-restore requires --ok\n";
      return 2;
    }
    auto long_parsed = hrefparse::parse(std::string_view(input));
    if (long_parsed) {
      emit_status("LONG_OK");
      emit_field("HREF", std::string(long_parsed->get_href()));
    } else {
      emit_status("LONG_FAIL");
    }
    hrefparse::set_max_input_length(std::numeric_limits<uint32_t>::max());
    auto restored = hrefparse::parse(std::string_view(ok_url));
    if (restored) {
      emit_status("RESTORE_OK");
      emit_field("HREF", std::string(restored->get_href()));
    } else {
      emit_status("RESTORE_FAIL");
    }
    return 0;
  }

  std::cerr << "unknown op\n";
  return 2;
}
"""

_C_PROBE = r"""
#ifdef __cplusplus
extern "C" {
#endif
#include "hrefparse_c.h"
#ifdef __cplusplus
}
#endif

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char* read_stdin(size_t* out_len) {
  size_t cap = 4096;
  size_t n = 0;
  char* buf = (char*)malloc(cap);
  if (buf == NULL) {
    return NULL;
  }
  for (;;) {
    if (n + 1 >= cap) {
      cap *= 2;
      char* grown = (char*)realloc(buf, cap);
      if (grown == NULL) {
        free(buf);
        return NULL;
      }
      buf = grown;
    }
    size_t got = fread(buf + n, 1, cap - n, stdin);
    n += got;
    if (got == 0) {
      break;
    }
  }
  *out_len = n;
  return buf;
}

static void emit_status(const char* status) { fprintf(stdout, "%s\n", status); }

static void emit_field(const char* key, const char* data, size_t len) {
  fprintf(stdout, "%s %zu\n", key, len);
  if (len > 0 && data != NULL) {
    fwrite(data, 1, len, stdout);
  }
  fputc('\n', stdout);
}

static void emit_can(int yes) {
  fprintf(stdout, "CAN %s\n", yes ? "yes" : "no");
}

int main(int argc, char** argv) {
  if (argc < 2) {
    fprintf(stderr, "missing op\n");
    return 2;
  }
  const char* op = argv[1];
  int have_max = 0;
  uint32_t max_value = 0;
  int have_base = 0;
  const char* base = NULL;
  const char* ok_url = NULL;
  for (int i = 2; i < argc; ++i) {
    if (strcmp(argv[i], "--max") == 0 && i + 1 < argc) {
      max_value = (uint32_t)strtoul(argv[++i], NULL, 10);
      have_max = 1;
    } else if (strcmp(argv[i], "--base") == 0 && i + 1 < argc) {
      base = argv[++i];
      have_base = 1;
    } else if (strcmp(argv[i], "--ok") == 0 && i + 1 < argc) {
      ok_url = argv[++i];
    } else {
      fprintf(stderr, "unknown arg\n");
      return 2;
    }
  }
  size_t input_len = 0;
  char* input = read_stdin(&input_len);
  if (input == NULL) {
    fprintf(stderr, "stdin alloc failed\n");
    return 2;
  }
  if (have_max) {
    hrefparse_set_max_input_length(max_value);
  }

  if (strcmp(op, "parse") == 0 || strcmp(op, "both") == 0) {
    hrefparse_url url;
    if (have_base) {
      url = hrefparse_parse_with_base(input, input_len, base, strlen(base));
    } else {
      url = hrefparse_parse(input, input_len);
    }
    if (hrefparse_is_valid(url)) {
      hrefparse_string href = hrefparse_get_href(url);
      hrefparse_string host = hrefparse_get_hostname(url);
      emit_status("OK");
      emit_field("HREF", href.data, href.length);
      emit_field("HOST", host.data, host.length);
    } else {
      emit_status("FAIL");
    }
    hrefparse_free(url);
    if (strcmp(op, "both") == 0) {
      int can = have_base
                    ? (int)hrefparse_can_parse_with_base(input, input_len, base,
                                                   strlen(base))
                    : (int)hrefparse_can_parse(input, input_len);
      emit_can(can);
    }
    free(input);
    return 0;
  }
  if (strcmp(op, "can") == 0) {
    int can = have_base ? (int)hrefparse_can_parse_with_base(input, input_len, base,
                                                        strlen(base))
                        : (int)hrefparse_can_parse(input, input_len);
    emit_can(can);
    free(input);
    return 0;
  }
  if (strcmp(op, "cap-get") == 0) {
    char cap[32];
    int n = snprintf(cap, sizeof(cap), "%u", hrefparse_get_max_input_length());
    if (n < 0) {
      free(input);
      return 2;
    }
    emit_status("OK");
    emit_field("CAP", cap, (size_t)n);
    free(input);
    return 0;
  }
  if (strcmp(op, "cap-rw") == 0) {
    if (!have_max) {
      fprintf(stderr, "cap-rw requires --max\n");
      free(input);
      return 2;
    }
    hrefparse_set_max_input_length(max_value);
    char set_buf[32];
    int ns = snprintf(set_buf, sizeof(set_buf), "%u", hrefparse_get_max_input_length());
    hrefparse_set_max_input_length(0xffffffffu);
    char def_buf[32];
    int nd =
        snprintf(def_buf, sizeof(def_buf), "%u", hrefparse_get_max_input_length());
    emit_status("OK");
    emit_field("SET", set_buf, (size_t)ns);
    emit_field("DEFAULT", def_buf, (size_t)nd);
    free(input);
    return 0;
  }
    if (strcmp(op, "cap-restore") == 0) {
    if (ok_url == NULL) {
      fprintf(stderr, "cap-restore requires --ok\n");
      free(input);
      return 2;
    }
    hrefparse_url long_url = hrefparse_parse(input, input_len);
    if (hrefparse_is_valid(long_url)) {
      hrefparse_string href = hrefparse_get_href(long_url);
      emit_status("LONG_OK");
      emit_field("HREF", href.data, href.length);
    } else {
      emit_status("LONG_FAIL");
    }
    hrefparse_free(long_url);
    hrefparse_set_max_input_length(0xffffffffu);
    hrefparse_url restored = hrefparse_parse(ok_url, strlen(ok_url));
    if (hrefparse_is_valid(restored)) {
      hrefparse_string href = hrefparse_get_href(restored);
      emit_status("RESTORE_OK");
      emit_field("HREF", href.data, href.length);
    } else {
      emit_status("RESTORE_FAIL");
    }
    hrefparse_free(restored);
    free(input);
    return 0;
  }
  if (strcmp(op, "idna-ascii") == 0) {
    hrefparse_owned_string owned = hrefparse_idna_to_ascii(input, input_len);
    /* Usable ASCII domain: non-null data and non-zero length.
       Null data, or a zero-length owned string, is "no usable domain".
       Do not treat empty string as the only failure encoding. */
    if (owned.data != NULL && owned.length > 0) {
      emit_status("OK");
      emit_field("PAYLOAD", owned.data, owned.length);
    } else {
      emit_status("FAIL");
      size_t n = owned.data == NULL ? 0 : owned.length;
      emit_field("PAYLOAD", owned.data == NULL ? "" : owned.data, n);
    }
    hrefparse_free_owned_string(owned);
    free(input);
    return 0;
  }
  if (strcmp(op, "idna-unicode") == 0) {
    hrefparse_owned_string owned = hrefparse_idna_to_unicode(input, input_len);
    if (owned.data != NULL && owned.length > 0) {
      emit_status("OK");
      emit_field("PAYLOAD", owned.data, owned.length);
    } else {
      emit_status("FAIL");
      size_t n = owned.data == NULL ? 0 : owned.length;
      emit_field("PAYLOAD", owned.data == NULL ? "" : owned.data, n);
    }
    hrefparse_free_owned_string(owned);
    free(input);
    return 0;
  }
  if (strcmp(op, "idna-round") == 0) {
    hrefparse_owned_string uni = hrefparse_idna_to_unicode(input, input_len);
    if (uni.data == NULL) {
      emit_status("FAIL");
      emit_field("PAYLOAD", "", 0);
      hrefparse_free_owned_string(uni);
      free(input);
      return 0;
    }
    hrefparse_owned_string ascii = hrefparse_idna_to_ascii(uni.data, uni.length);
    if (uni.length > 0) {
      emit_status("OK");
    } else {
      emit_status("FAIL");
    }
    emit_field("UNI", uni.data, uni.length);
    if (ascii.data != NULL && ascii.length > 0) {
      emit_field("ASCII_OK", "yes", 3);
      emit_field("ASCII", ascii.data, ascii.length);
    } else {
      emit_field("ASCII_OK", "no", 2);
      size_t n = ascii.data == NULL ? 0 : ascii.length;
      emit_field("ASCII", ascii.data == NULL ? "" : ascii.data, n);
    }
    hrefparse_free_owned_string(ascii);
    hrefparse_free_owned_string(uni);
    free(input);
    return 0;
  }

  fprintf(stderr, "unknown op\n");
  free(input);
  return 2;
}
"""


# ---------------------------------------------------------------------------
# Observation types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParseOutcome:
    """Classified parse observation. ``href``/``hostname`` are set only on OK."""

    ok: bool
    href: str | None
    hostname: str | None
    stderr: str


@dataclass(frozen=True)
class IdnaOutcome:
    """Standalone IDNA observation.

    ``ok`` means a usable payload was handed to the caller. ``payload`` is
    whatever the C entry returned (may be empty on failure); it is never used
    as the sole definition of failure — classification already happened.
    """

    ok: bool
    payload: str
    stderr: str


@dataclass(frozen=True)
class IdnaRoundtrip:
    unicode_ok: bool
    unicode_payload: str
    ascii_ok: bool
    ascii_payload: str
    stderr: str


@dataclass(frozen=True)
class CapRestoreOutcome:
    long_ok: bool
    restore_ok: bool
    restore_href: str | None
    stderr: str


# ---------------------------------------------------------------------------
# Probe I/O
# ---------------------------------------------------------------------------


def _normalize_language(language: str) -> str:
    key = language.strip().lower()
    if key in ("c++", "cpp", "cxx", "cc"):
        return "c++"
    if key == "c":
        return "c"
    raise ValueError(f"unsupported language: {language!r}")


def _probe_source(language: str) -> str:
    return _C_PROBE if language == "c" else _CXX_PROBE


def _run_probe(
    op: str,
    input_bytes: bytes = b"",
    *,
    language: str = "c++",
    max_length: int | None = None,
    base: str | None = None,
    ok_url: str | None = None,
) -> RunResult:
    lang = _normalize_language(language)
    args: list[str] = [op]
    if max_length is not None:
        args.extend(["--max", str(int(max_length))])
    if base is not None:
        args.extend(["--base", base])
    if ok_url is not None:
        args.extend(["--ok", ok_url])
    result = invoke(
        _probe_source(lang),
        args,
        language=lang,
        stdin=input_bytes,
    )
    if result.returncode != 0:
        err = result.stderr_text
        raise HarnessError(
            f"probe op={op!r} language={lang} exited {result.returncode} "
            f"(not a classified product outcome): {err}"
        )
    return result


def _parse_fields(raw: bytes) -> tuple[list[str], dict[str, str]]:
    """Parse STATUS lines plus KEY <len> / payload records.

    Raises HarnessError if the stream cannot be classified.
    """
    if not raw:
        raise HarnessError("probe produced empty stdout; cannot classify")
    statuses: list[str] = []
    fields: dict[str, str] = {}
    offset = 0
    while offset < len(raw):
        nl = raw.find(b"\n", offset)
        if nl < 0:
            leftover = raw[offset:]
            if leftover.strip():
                raise HarnessError(
                    f"probe stdout truncated before newline: {leftover!r}"
                )
            break
        header = raw[offset:nl]
        offset = nl + 1
        if header in (b"OK", b"FAIL", b"LONG_OK", b"LONG_FAIL", b"RESTORE_OK",
                      b"RESTORE_FAIL"):
            statuses.append(header.decode("ascii"))
            continue
        if header == b"CAN yes" or header == b"CAN no":
            fields["CAN"] = header[4:].decode("ascii")
            continue
        # KEY <decimal-len>
        try:
            key_b, len_b = header.split(b" ", 1)
            key = key_b.decode("ascii")
            length = int(len_b.decode("ascii"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HarnessError(
                f"probe stdout line is not a status or field header: "
                f"{header!r}"
            ) from exc
        payload = raw[offset : offset + length]
        if len(payload) != length:
            raise HarnessError(
                f"probe field {key!r} declared {length} bytes but only "
                f"{len(payload)} remain"
            )
        offset += length
        if offset < len(raw) and raw[offset : offset + 1] == b"\n":
            offset += 1
        else:
            raise HarnessError(
                f"probe field {key!r} not followed by a newline"
            )
        try:
            fields[key] = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HarnessError(
                f"probe field {key!r} is not valid UTF-8: {exc}"
            ) from exc
    if not statuses and "CAN" not in fields:
        raise HarnessError(
            f"probe stdout had no classifiable status line: {raw[:200]!r}"
        )
    return statuses, fields


def _require_status(
    result: RunResult, *, expect: str | tuple[str, ...]
) -> tuple[list[str], dict[str, str]]:
    statuses, fields = _parse_fields(result.stdout)
    allowed = (expect,) if isinstance(expect, str) else expect
    if not statuses or statuses[0] not in allowed:
        raise HarnessError(
            f"probe status {statuses!r} not in {allowed}; "
            f"stderr={result.stderr_text!r}"
        )
    return statuses, fields


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def unique_token() -> str:
    """Runtime path/host segment that cannot be memorized from public materials."""
    return "t" + secrets.token_hex(8)


def ipv4_octet_from_mixed_token(token: str) -> int:
    """Independent mixed-base octet arithmetic (not the product IPv4 parser)."""
    t = token.strip()
    if t.lower().startswith("0x"):
        value = int(t, 16)
    elif len(t) > 1 and t[0] == "0" and all(c in "01234567" for c in t):
        value = int(t, 8)
    else:
        value = int(t, 10)
    if value < 0 or value > 255:
        raise ValueError(f"IPv4 octet {token!r} out of 0..255: {value}")
    return value


def dotted_ipv4_from_mixed_octets(parts: tuple[str, str, str, str]) -> str:
    """Four mixed-base tokens → dotted decimal via independent arithmetic."""
    return ".".join(str(ipv4_octet_from_mixed_token(p)) for p in parts)


def parse_url(
    input_url: str,
    base: str | None = None,
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> ParseOutcome:
    """Parse through the public parse entry. Compile failure raises."""
    result = _run_probe(
        "parse",
        input_url.encode("utf-8"),
        language=language,
        max_length=max_length,
        base=base,
    )
    statuses, fields = _parse_fields(result.stdout)
    if not statuses:
        raise HarnessError("parse probe omitted OK/FAIL")
    status = statuses[0]
    stderr = result.stderr_text
    if status == "OK":
        if "HREF" not in fields:
            raise HarnessError("parse OK without HREF field")
        return ParseOutcome(
            ok=True,
            href=fields["HREF"],
            hostname=fields.get("HOST"),
            stderr=stderr,
        )
    if status == "FAIL":
        return ParseOutcome(ok=False, href=None, hostname=None, stderr=stderr)
    raise HarnessError(f"unclassified parse status {status!r}")


def can_parse_url(
    input_url: str,
    base: str | None = None,
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> bool:
    """Dedicated can-parse entry. Unclassifiable output raises, never False."""
    result = _run_probe(
        "can",
        input_url.encode("utf-8"),
        language=language,
        max_length=max_length,
        base=base,
    )
    _, fields = _parse_fields(result.stdout)
    can = fields.get("CAN")
    if can == "yes":
        return True
    if can == "no":
        return False
    raise HarnessError(
        f"can-parse probe did not emit CAN yes/no; stderr={result.stderr_text!r}"
    )


def parse_and_can_parse(
    input_url: str,
    base: str | None = None,
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> tuple[ParseOutcome, bool]:
    """Same-process parse and dedicated can-parse (same cap, same base)."""
    result = _run_probe(
        "both",
        input_url.encode("utf-8"),
        language=language,
        max_length=max_length,
        base=base,
    )
    statuses, fields = _parse_fields(result.stdout)
    if not statuses:
        raise HarnessError("both-probe omitted parse status")
    can = fields.get("CAN")
    if can not in ("yes", "no"):
        raise HarnessError(
            f"both-probe omitted CAN yes/no; stderr={result.stderr_text!r}"
        )
    stderr = result.stderr_text
    if statuses[0] == "OK":
        if "HREF" not in fields:
            raise HarnessError("both-probe OK without HREF")
        parsed = ParseOutcome(
            ok=True,
            href=fields["HREF"],
            hostname=fields.get("HOST"),
            stderr=stderr,
        )
    elif statuses[0] == "FAIL":
        parsed = ParseOutcome(ok=False, href=None, hostname=None, stderr=stderr)
    else:
        raise HarnessError(f"unclassified parse status {statuses[0]!r}")
    return parsed, can == "yes"


def require_parse_href(
    input_url: str,
    expected_href: str,
    base: str | None = None,
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> ParseOutcome:
    outcome = parse_url(
        input_url, base, language=language, max_length=max_length
    )
    assert outcome.ok, (
        f"parse failed for {input_url!r} base={base!r} language={language}; "
        f"stderr={outcome.stderr!r}"
    )
    assert outcome.href == expected_href, (
        f"href mismatch language={language}: got {outcome.href!r} "
        f"expected {expected_href!r}; stderr={outcome.stderr!r}"
    )
    return outcome


def require_parse_failure(
    input_url: str,
    base: str | None = None,
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> ParseOutcome:
    outcome = parse_url(
        input_url, base, language=language, max_length=max_length
    )
    assert not outcome.ok, (
        f"parse unexpectedly succeeded for {input_url!r} "
        f"href={outcome.href!r} language={language}; stderr={outcome.stderr!r}"
    )
    assert outcome.href is None, (
        "failed parse must not hand the caller a usable href; "
        f"got {outcome.href!r}"
    )
    return outcome


def require_can_parse_agrees(
    input_url: str,
    base: str | None = None,
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> tuple[ParseOutcome, bool]:
    parsed, can = parse_and_can_parse(
        input_url, base, language=language, max_length=max_length
    )
    assert can is parsed.ok, (
        f"can-parse {can} disagrees with parse ok={parsed.ok} "
        f"for {input_url!r} base={base!r} cap={max_length} "
        f"language={language}; stderr={parsed.stderr!r}"
    )
    return parsed, can


def href_from_file_path(path: str, *, max_length: int | None = None) -> str:
    """C++ filesystem-path conversion. Probe crash does not become empty string."""
    result = _run_probe(
        "file",
        path.encode("utf-8"),
        language="c++",
        max_length=max_length,
    )
    statuses, fields = _require_status(result, expect="OK")
    if "HREF" not in fields:
        raise HarnessError(
            f"href_from_file OK without HREF; stderr={result.stderr_text!r}"
        )
    return fields["HREF"]


def file_href_via_pathname(path: str) -> str:
    """Parse ``file://``, assign pathname, read href. ``file://`` must parse."""
    result = _run_probe("pathname", path.encode("utf-8"), language="c++")
    statuses, fields = _parse_fields(result.stdout)
    if not statuses or statuses[0] != "OK":
        raise HarnessError(
            f"file:// parse or pathname assignment failed for {path!r}; "
            f"stdout={result.stdout!r} stderr={result.stderr_text!r}"
        )
    if "HREF" not in fields:
        raise HarnessError("pathname assignment OK without HREF")
    return fields["HREF"]


def idna_to_ascii(domain: str) -> IdnaOutcome:
    """Standalone ToASCII on the C interface only."""
    result = _run_probe(
        "idna-ascii", domain.encode("utf-8"), language="c"
    )
    statuses, fields = _parse_fields(result.stdout)
    if not statuses:
        raise HarnessError("idna-ascii omitted OK/FAIL")
    payload = fields.get("PAYLOAD", "")
    if statuses[0] == "OK":
        return IdnaOutcome(ok=True, payload=payload, stderr=result.stderr_text)
    if statuses[0] == "FAIL":
        return IdnaOutcome(ok=False, payload=payload, stderr=result.stderr_text)
    raise HarnessError(f"unclassified idna status {statuses[0]!r}")


def idna_to_unicode(domain: str) -> IdnaOutcome:
    """Standalone ToUnicode on the C interface only."""
    result = _run_probe(
        "idna-unicode", domain.encode("utf-8"), language="c"
    )
    statuses, fields = _parse_fields(result.stdout)
    if not statuses:
        raise HarnessError("idna-unicode omitted OK/FAIL")
    payload = fields.get("PAYLOAD", "")
    if statuses[0] == "OK":
        return IdnaOutcome(ok=True, payload=payload, stderr=result.stderr_text)
    if statuses[0] == "FAIL":
        return IdnaOutcome(ok=False, payload=payload, stderr=result.stderr_text)
    raise HarnessError(f"unclassified idna-unicode status {statuses[0]!r}")


def idna_unicode_then_ascii(domain: str) -> IdnaRoundtrip:
    """ToUnicode then ToASCII on that result, same C-interface process."""
    result = _run_probe(
        "idna-round", domain.encode("utf-8"), language="c"
    )
    statuses, fields = _parse_fields(result.stdout)
    if not statuses:
        raise HarnessError("idna-round omitted status")
    ascii_flag = fields.get("ASCII_OK")
    if ascii_flag not in ("yes", "no"):
        raise HarnessError(
            f"idna-round omitted ASCII_OK; stderr={result.stderr_text!r}"
        )
    return IdnaRoundtrip(
        unicode_ok=statuses[0] == "OK",
        unicode_payload=fields.get("UNI", ""),
        ascii_ok=ascii_flag == "yes",
        ascii_payload=fields.get("ASCII", ""),
        stderr=result.stderr_text,
    )


def get_max_input_length_value(*, language: str = "c++") -> int:
    """Read the process-wide cap in a fresh process (the recipe default)."""
    result = _run_probe("cap-get", b"", language=language)
    _, fields = _require_status(result, expect="OK")
    if "CAP" not in fields:
        raise HarnessError(
            f"cap-get OK without CAP; stderr={result.stderr_text!r}"
        )
    try:
        return int(fields["CAP"], 10)
    except ValueError as exc:
        raise HarnessError(f"cap-get CAP not an integer: {fields['CAP']!r}") from exc


def set_and_restore_cap_values(
    set_to: int, *, language: str = "c++"
) -> tuple[int, int]:
    """Same process: set cap, read, raise to the 32-bit maximum, read."""
    result = _run_probe(
        "cap-rw", b"", language=language, max_length=set_to
    )
    _, fields = _require_status(result, expect="OK")
    try:
        return int(fields["SET"], 10), int(fields["DEFAULT"], 10)
    except (KeyError, ValueError) as exc:
        raise HarnessError(
            f"cap-rw missing SET/DEFAULT integers: {fields!r}"
        ) from exc


def parse_long_then_restore(
    long_url: str,
    ok_url: str,
    *,
    max_length: int,
    language: str = "c++",
) -> CapRestoreOutcome:
    """Set cap, parse long input, restore default, parse ordinary URL."""
    result = _run_probe(
        "cap-restore",
        long_url.encode("utf-8"),
        language=language,
        max_length=max_length,
        ok_url=ok_url,
    )
    statuses, fields = _parse_fields(result.stdout)
    if "LONG_FAIL" not in statuses and "LONG_OK" not in statuses:
        raise HarnessError(
            f"cap-restore omitted LONG status; stderr={result.stderr_text!r}"
        )
    if "RESTORE_OK" not in statuses and "RESTORE_FAIL" not in statuses:
        raise HarnessError(
            f"cap-restore omitted RESTORE status; stderr={result.stderr_text!r}"
        )
    restore_href = fields.get("HREF") if "RESTORE_OK" in statuses else None
    return CapRestoreOutcome(
        long_ok="LONG_OK" in statuses,
        restore_ok="RESTORE_OK" in statuses,
        restore_href=restore_href,
        stderr=result.stderr_text,
    )


def try_parse_without_linked_library(
    input_url: str = GOOGLE_URL,
) -> tuple[str, RunResult | None]:
    """Compile the C++ parse probe without linking the recipe library.

    Returns ``("link_failed", compile_result)`` when the compiler/linker
    refuses to produce a binary — that is "no successful product URL".
    Returns ``("ran", run_result)`` if a binary was produced; the caller
    must then show it did not yield the successful Google href.

    Never skips. Missing compiler is ``FileNotFoundError``.
    """
    include = include_dir()
    compiler = cxx_compiler()
    work = Path(tempfile.mkdtemp(prefix="f01-nolink-"))
    try:
        source_path = work / "probe.cpp"
        source_path.write_text(_CXX_PROBE, encoding="utf-8")
        out_path = work / "probe"
        argv = [
            compiler,
            f"-std={DEFAULT_CXX_STD}",
            f"-I{include}",
            str(source_path),
            "-o",
            str(out_path),
        ]
        if os.name != "nt":
            argv.append("-pthread")
        compile_result = run_command(argv, cwd=work)
        if compile_result.returncode != 0:
            return "link_failed", compile_result
        if not out_path.is_file():
            raise HarnessError(
                "compiler exited 0 without a binary while not linking the library"
            )
        run_result = run_command(
            [str(out_path), "parse"],
            cwd=work,
            stdin=input_url.encode("utf-8"),
            timeout=DEFAULT_TIMEOUT,
        )
        return "ran", run_result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def probe_result_has_href(result: RunResult, href: str) -> bool:
    """True only if a completed probe classified OK with this exact href."""
    if result.returncode != 0:
        return False
    try:
        statuses, fields = _parse_fields(result.stdout)
    except HarnessError:
        return False
    return statuses[:1] == ["OK"] and fields.get("HREF") == href


# ---------------------------------------------------------------------------
# FP-02: inspect / mutate / clear on one parsed URL object
# ---------------------------------------------------------------------------

FLAGGED_WRITE_FIELDS = frozenset(
    {
        "host",
        "hostname",
        "protocol",
        "pathname",
        "username",
        "password",
        "port",
        "href",
    }
)

_SNAPSHOT_KEYS = (
    "HREF",
    "ORIGIN",
    "PROTOCOL",
    "USERNAME",
    "PASSWORD",
    "HOST",
    "HOSTNAME",
    "PORT",
    "PATHNAME",
    "SEARCH",
    "HASH",
    "KIND",
    "HAS_CRED",
    "HAS_HOST",
    "HAS_PORT",
    "HAS_SEARCH",
    "HAS_HASH",
)


@dataclass(frozen=True)
class InspectOutcome:
    """Named readers, presence flags, and an opaque host-kind token."""

    href: str
    origin: str
    protocol: str
    username: str
    password: str
    host: str
    hostname: str
    port: str
    pathname: str
    search: str
    hash: str
    host_kind: str
    has_credentials: bool
    has_hostname: bool
    has_port: bool
    has_search: bool
    has_hash: bool
    stderr: str

    def components(self) -> tuple:
        """Equality key: every named reader, presence flag, and kind token."""
        return (
            self.href,
            self.origin,
            self.protocol,
            self.username,
            self.password,
            self.host,
            self.hostname,
            self.port,
            self.pathname,
            self.search,
            self.hash,
            self.host_kind,
            self.has_credentials,
            self.has_hostname,
            self.has_port,
            self.has_search,
            self.has_hash,
        )


@dataclass(frozen=True)
class MutateOutcome:
    """After-write snapshot. ``accepted`` is None for search/hash (no flag)."""

    accepted: bool | None
    after: InspectOutcome
    stderr: str


_CXX_COMPONENT_PROBE = r"""
#include "hrefparse.h"

#include <cstdint>
#include <iostream>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

static std::string read_stdin() {
  std::string data;
  char buf[4096];
  while (true) {
    std::cin.read(buf, sizeof(buf));
    const std::streamsize n = std::cin.gcount();
    if (n <= 0) {
      break;
    }
    data.append(buf, static_cast<size_t>(n));
  }
  return data;
}

static void emit_status(const char* status) { std::cout << status << '\n'; }

static void emit_field(const char* key, std::string_view val) {
  std::cout << key << ' ' << val.size() << '\n';
  std::cout.write(val.data(), static_cast<std::streamsize>(val.size()));
  std::cout.put('\n');
}

static void emit_snapshot(const hrefparse::url_aggregator& url) {
  emit_status("OK");
  emit_field("HREF", url.get_href());
  const std::string origin = url.get_origin();
  emit_field("ORIGIN", origin);
  emit_field("PROTOCOL", url.get_protocol());
  emit_field("USERNAME", url.get_username());
  emit_field("PASSWORD", url.get_password());
  emit_field("HOST", url.get_host());
  emit_field("HOSTNAME", url.get_hostname());
  emit_field("PORT", url.get_port());
  emit_field("PATHNAME", url.get_pathname());
  emit_field("SEARCH", url.get_search());
  emit_field("HASH", url.get_hash());
  const std::string kind = std::to_string(static_cast<unsigned>(url.host_type));
  emit_field("KIND", kind);
  emit_field("HAS_CRED", url.has_credentials() ? "yes" : "no");
  emit_field("HAS_HOST", url.has_hostname() ? "yes" : "no");
  emit_field("HAS_PORT", url.has_port() ? "yes" : "no");
  emit_field("HAS_SEARCH", url.has_search() ? "yes" : "no");
  emit_field("HAS_HASH", url.has_hash() ? "yes" : "no");
}

static bool apply_write(hrefparse::url_aggregator& url, const std::string& field,
                        const std::string& value, bool* flagged,
                        bool* accepted) {
  *flagged = (field == "host" || field == "hostname" || field == "protocol" ||
              field == "pathname" || field == "username" ||
              field == "password" || field == "port" || field == "href");
  const std::string_view v(value);
  if (field == "host") {
    *accepted = url.set_host(v);
    return true;
  }
  if (field == "hostname") {
    *accepted = url.set_hostname(v);
    return true;
  }
  if (field == "protocol") {
    *accepted = url.set_protocol(v);
    return true;
  }
  if (field == "pathname") {
    *accepted = url.set_pathname(v);
    return true;
  }
  if (field == "username") {
    *accepted = url.set_username(v);
    return true;
  }
  if (field == "password") {
    *accepted = url.set_password(v);
    return true;
  }
  if (field == "port") {
    *accepted = url.set_port(v);
    return true;
  }
  if (field == "href") {
    *accepted = url.set_href(v);
    return true;
  }
  if (field == "search") {
    url.set_search(v);
    *accepted = true;
    return true;
  }
  if (field == "hash") {
    url.set_hash(v);
    *accepted = true;
    return true;
  }
  return false;
}

int main(int argc, char** argv) {
  std::ios::sync_with_stdio(false);
  if (argc < 2) {
    std::cerr << "missing op\n";
    return 2;
  }
  const std::string op = argv[1];
  bool have_max = false;
  uint32_t max_value = 0;
  std::string clear_field;
  std::vector<std::pair<std::string, std::string>> writes;
  for (int i = 2; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--max" && i + 1 < argc) {
      max_value = static_cast<uint32_t>(std::stoul(argv[++i]));
      have_max = true;
    } else if ((arg == "--write" || arg == "--field") && i + 1 < argc) {
      const std::string field = argv[++i];
      if (op == "clear") {
        clear_field = field;
        continue;
      }
      if (i + 2 >= argc || std::string(argv[i + 1]) != "--value") {
        std::cerr << "write requires --value\n";
        return 2;
      }
      i += 1;
      writes.emplace_back(field, argv[++i]);
    } else {
      std::cerr << "unknown arg\n";
      return 2;
    }
  }
  const std::string input = read_stdin();
  if (have_max) {
    hrefparse::set_max_input_length(max_value);
  }
  auto parsed = hrefparse::parse(std::string_view(input));
  if (!parsed) {
    emit_status("FAIL");
    return 0;
  }
  hrefparse::url_aggregator& url = *parsed;

  if (op == "inspect") {
    emit_snapshot(url);
    return 0;
  }
  if (op == "clear") {
    if (clear_field == "port") {
      url.clear_port();
    } else if (clear_field == "search") {
      url.clear_search();
    } else if (clear_field == "hash") {
      url.clear_hash();
    } else {
      std::cerr << "unknown clear field\n";
      return 2;
    }
    emit_snapshot(url);
    return 0;
  }
  if (op == "mutate") {
    if (writes.empty()) {
      std::cerr << "mutate requires --write\n";
      return 2;
    }
    bool any_flagged = false;
    bool all_flagged_ok = true;
    for (const auto& item : writes) {
      bool flagged = false;
      bool accepted = false;
      if (!apply_write(url, item.first, item.second, &flagged, &accepted)) {
        std::cerr << "unknown write field\n";
        return 2;
      }
      if (flagged) {
        any_flagged = true;
        if (!accepted) {
          all_flagged_ok = false;
        }
      }
    }
    if (any_flagged) {
      emit_field("WRITE", all_flagged_ok ? "ACCEPTED" : "REFUSED");
    }
    emit_snapshot(url);
    return 0;
  }
  std::cerr << "unknown op\n";
  return 2;
}
"""

_C_COMPONENT_PROBE = r"""
#ifdef __cplusplus
extern "C" {
#endif
#include "hrefparse_c.h"
#ifdef __cplusplus
}
#endif

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char* read_stdin(size_t* out_len) {
  size_t cap = 4096;
  size_t n = 0;
  char* buf = (char*)malloc(cap);
  if (buf == NULL) {
    return NULL;
  }
  for (;;) {
    if (n + 1 >= cap) {
      cap *= 2;
      char* grown = (char*)realloc(buf, cap);
      if (grown == NULL) {
        free(buf);
        return NULL;
      }
      buf = grown;
    }
    size_t got = fread(buf + n, 1, cap - n, stdin);
    n += got;
    if (got == 0) {
      break;
    }
  }
  *out_len = n;
  return buf;
}

static void emit_status(const char* status) { fprintf(stdout, "%s\n", status); }

static void emit_field(const char* key, const char* data, size_t len) {
  fprintf(stdout, "%s %zu\n", key, len);
  if (len > 0 && data != NULL) {
    fwrite(data, 1, len, stdout);
  }
  fputc('\n', stdout);
}

static void emit_yesno(const char* key, int yes) {
  const char* v = yes ? "yes" : "no";
  emit_field(key, v, strlen(v));
}

static void emit_snapshot(hrefparse_url url) {
  emit_status("OK");
  hrefparse_string href = hrefparse_get_href(url);
  emit_field("HREF", href.data, href.length);
  hrefparse_owned_string origin = hrefparse_get_origin(url);
  emit_field("ORIGIN", origin.data, origin.length);
  hrefparse_free_owned_string(origin);
  hrefparse_string protocol = hrefparse_get_protocol(url);
  emit_field("PROTOCOL", protocol.data, protocol.length);
  hrefparse_string username = hrefparse_get_username(url);
  emit_field("USERNAME", username.data, username.length);
  hrefparse_string password = hrefparse_get_password(url);
  emit_field("PASSWORD", password.data, password.length);
  hrefparse_string host = hrefparse_get_host(url);
  emit_field("HOST", host.data, host.length);
  hrefparse_string hostname = hrefparse_get_hostname(url);
  emit_field("HOSTNAME", hostname.data, hostname.length);
  hrefparse_string port = hrefparse_get_port(url);
  emit_field("PORT", port.data, port.length);
  hrefparse_string pathname = hrefparse_get_pathname(url);
  emit_field("PATHNAME", pathname.data, pathname.length);
  hrefparse_string search = hrefparse_get_search(url);
  emit_field("SEARCH", search.data, search.length);
  hrefparse_string hash = hrefparse_get_hash(url);
  emit_field("HASH", hash.data, hash.length);
  char kind[16];
  int kn = snprintf(kind, sizeof(kind), "%u", (unsigned)hrefparse_get_host_type(url));
  if (kn < 0) {
    return;
  }
  emit_field("KIND", kind, (size_t)kn);
  emit_yesno("HAS_CRED", hrefparse_has_credentials(url) ? 1 : 0);
  emit_yesno("HAS_HOST", hrefparse_has_hostname(url) ? 1 : 0);
  emit_yesno("HAS_PORT", hrefparse_has_port(url) ? 1 : 0);
  emit_yesno("HAS_SEARCH", hrefparse_has_search(url) ? 1 : 0);
  emit_yesno("HAS_HASH", hrefparse_has_hash(url) ? 1 : 0);
}

static int apply_write(hrefparse_url url, const char* field, const char* value,
                       int* flagged, int* accepted) {
  size_t n = strlen(value);
  *flagged = 0;
  *accepted = 1;
  if (strcmp(field, "host") == 0) {
    *flagged = 1;
    *accepted = hrefparse_set_host(url, value, n) ? 1 : 0;
    return 1;
  }
  if (strcmp(field, "hostname") == 0) {
    *flagged = 1;
    *accepted = hrefparse_set_hostname(url, value, n) ? 1 : 0;
    return 1;
  }
  if (strcmp(field, "protocol") == 0) {
    *flagged = 1;
    *accepted = hrefparse_set_protocol(url, value, n) ? 1 : 0;
    return 1;
  }
  if (strcmp(field, "pathname") == 0) {
    *flagged = 1;
    *accepted = hrefparse_set_pathname(url, value, n) ? 1 : 0;
    return 1;
  }
  if (strcmp(field, "username") == 0) {
    *flagged = 1;
    *accepted = hrefparse_set_username(url, value, n) ? 1 : 0;
    return 1;
  }
  if (strcmp(field, "password") == 0) {
    *flagged = 1;
    *accepted = hrefparse_set_password(url, value, n) ? 1 : 0;
    return 1;
  }
  if (strcmp(field, "port") == 0) {
    *flagged = 1;
    *accepted = hrefparse_set_port(url, value, n) ? 1 : 0;
    return 1;
  }
  if (strcmp(field, "href") == 0) {
    *flagged = 1;
    *accepted = hrefparse_set_href(url, value, n) ? 1 : 0;
    return 1;
  }
  if (strcmp(field, "search") == 0) {
    hrefparse_set_search(url, value, n);
    return 1;
  }
  if (strcmp(field, "hash") == 0) {
    hrefparse_set_hash(url, value, n);
    return 1;
  }
  return 0;
}

int main(int argc, char** argv) {
  if (argc < 2) {
    fprintf(stderr, "missing op\n");
    return 2;
  }
  const char* op = argv[1];
  int have_max = 0;
  uint32_t max_value = 0;
  const char* clear_field = NULL;
  const char* write_fields[16];
  const char* write_values[16];
  int nwrites = 0;
  for (int i = 2; i < argc; ++i) {
    if (strcmp(argv[i], "--max") == 0 && i + 1 < argc) {
      max_value = (uint32_t)strtoul(argv[++i], NULL, 10);
      have_max = 1;
    } else if ((strcmp(argv[i], "--write") == 0 ||
                strcmp(argv[i], "--field") == 0) &&
               i + 1 < argc) {
      const char* field = argv[++i];
      if (strcmp(op, "clear") == 0) {
        clear_field = field;
        continue;
      }
      if (i + 2 >= argc || strcmp(argv[i + 1], "--value") != 0) {
        fprintf(stderr, "write requires --value\n");
        return 2;
      }
      i += 1;
      if (nwrites >= 16) {
        fprintf(stderr, "too many writes\n");
        return 2;
      }
      write_fields[nwrites] = field;
      write_values[nwrites] = argv[++i];
      nwrites += 1;
    } else {
      fprintf(stderr, "unknown arg\n");
      return 2;
    }
  }
  size_t input_len = 0;
  char* input = read_stdin(&input_len);
  if (input == NULL) {
    fprintf(stderr, "stdin alloc failed\n");
    return 2;
  }
  if (have_max) {
    hrefparse_set_max_input_length(max_value);
  }
  hrefparse_url url = hrefparse_parse(input, input_len);
  if (!hrefparse_is_valid(url)) {
    emit_status("FAIL");
    hrefparse_free(url);
    free(input);
    return 0;
  }
  if (strcmp(op, "inspect") == 0) {
    emit_snapshot(url);
    hrefparse_free(url);
    free(input);
    return 0;
  }
  if (strcmp(op, "clear") == 0) {
    if (clear_field == NULL) {
      fprintf(stderr, "clear requires --field\n");
      hrefparse_free(url);
      free(input);
      return 2;
    }
    if (strcmp(clear_field, "port") == 0) {
      hrefparse_clear_port(url);
    } else if (strcmp(clear_field, "search") == 0) {
      hrefparse_clear_search(url);
    } else if (strcmp(clear_field, "hash") == 0) {
      hrefparse_clear_hash(url);
    } else {
      fprintf(stderr, "unknown clear field\n");
      hrefparse_free(url);
      free(input);
      return 2;
    }
    emit_snapshot(url);
    hrefparse_free(url);
    free(input);
    return 0;
  }
  if (strcmp(op, "mutate") == 0) {
    if (nwrites == 0) {
      fprintf(stderr, "mutate requires --write\n");
      hrefparse_free(url);
      free(input);
      return 2;
    }
    int any_flagged = 0;
    int all_flagged_ok = 1;
    for (int w = 0; w < nwrites; ++w) {
      int flagged = 0;
      int accepted = 0;
      if (!apply_write(url, write_fields[w], write_values[w], &flagged,
                       &accepted)) {
        fprintf(stderr, "unknown write field\n");
        hrefparse_free(url);
        free(input);
        return 2;
      }
      if (flagged) {
        any_flagged = 1;
        if (!accepted) {
          all_flagged_ok = 0;
        }
      }
    }
    if (any_flagged) {
      const char* w = all_flagged_ok ? "ACCEPTED" : "REFUSED";
      emit_field("WRITE", w, strlen(w));
    }
    emit_snapshot(url);
    hrefparse_free(url);
    free(input);
    return 0;
  }
  fprintf(stderr, "unknown op\n");
  hrefparse_free(url);
  free(input);
  return 2;
}
"""


def _component_probe_source(language: str) -> str:
    return _C_COMPONENT_PROBE if language == "c" else _CXX_COMPONENT_PROBE


def _yesno_field(fields: dict[str, str], key: str) -> bool:
    value = fields.get(key)
    if value == "yes":
        return True
    if value == "no":
        return False
    raise HarnessError(f"probe field {key!r} is not yes/no: {value!r}")


def _inspect_from_fields(fields: dict[str, str], stderr: str) -> InspectOutcome:
    missing = [key for key in _SNAPSHOT_KEYS if key not in fields]
    if missing:
        raise HarnessError(f"inspect snapshot missing {missing}; fields={fields!r}")
    return InspectOutcome(
        href=fields["HREF"],
        origin=fields["ORIGIN"],
        protocol=fields["PROTOCOL"],
        username=fields["USERNAME"],
        password=fields["PASSWORD"],
        host=fields["HOST"],
        hostname=fields["HOSTNAME"],
        port=fields["PORT"],
        pathname=fields["PATHNAME"],
        search=fields["SEARCH"],
        hash=fields["HASH"],
        host_kind=fields["KIND"],
        has_credentials=_yesno_field(fields, "HAS_CRED"),
        has_hostname=_yesno_field(fields, "HAS_HOST"),
        has_port=_yesno_field(fields, "HAS_PORT"),
        has_search=_yesno_field(fields, "HAS_SEARCH"),
        has_hash=_yesno_field(fields, "HAS_HASH"),
        stderr=stderr,
    )


def _run_component_probe(
    op: str,
    input_url: str,
    *,
    language: str = "c++",
    max_length: int | None = None,
    extra_args: Sequence[str] | None = None,
) -> RunResult:
    lang = _normalize_language(language)
    args: list[str] = [op]
    if max_length is not None:
        args.extend(["--max", str(int(max_length))])
    if extra_args:
        args.extend(str(a) for a in extra_args)
    result = invoke(
        _component_probe_source(lang),
        args,
        language=lang,
        stdin=input_url.encode("utf-8"),
    )
    if result.returncode != 0:
        raise HarnessError(
            f"component probe op={op!r} language={lang} exited "
            f"{result.returncode} (not a classified product outcome): "
            f"{result.stderr_text!r}"
        )
    return result


def same_components(left: InspectOutcome, right: InspectOutcome) -> bool:
    """True when every named reader, presence flag, and kind token matches."""
    return left.components() == right.components()


def inspect_url(
    input_url: str,
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> InspectOutcome:
    """Parse then read every named component. Parse failure raises."""
    result = _run_component_probe(
        "inspect", input_url, language=language, max_length=max_length
    )
    statuses, fields = _parse_fields(result.stdout)
    if not statuses:
        raise HarnessError("inspect probe omitted OK/FAIL")
    if statuses[0] != "OK":
        raise HarnessError(
            f"inspect requires a successful parse of {input_url!r}; "
            f"status={statuses!r} stderr={result.stderr_text!r}"
        )
    return _inspect_from_fields(fields, result.stderr_text)


def mutate_many(
    input_url: str,
    writes: Sequence[tuple[str, str]],
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> MutateOutcome:
    """Same-object parse then a sequence of public writes; reread snapshot."""
    if not writes:
        raise ValueError("mutate_many requires at least one write")
    extra: list[str] = []
    flagged = False
    for field, value in writes:
        extra.extend(["--write", field, "--value", value])
        if field in FLAGGED_WRITE_FIELDS:
            flagged = True
    result = _run_component_probe(
        "mutate",
        input_url,
        language=language,
        max_length=max_length,
        extra_args=extra,
    )
    statuses, fields = _parse_fields(result.stdout)
    if "OK" not in statuses:
        raise HarnessError(
            f"mutate omitted OK snapshot for {input_url!r} writes={writes!r}; "
            f"status={statuses!r} stderr={result.stderr_text!r}"
        )
    write_flag = fields.get("WRITE")
    if flagged:
        if write_flag == "ACCEPTED":
            accepted: bool | None = True
        elif write_flag == "REFUSED":
            accepted = False
        else:
            raise HarnessError(
                f"flagged write omitted WRITE ACCEPTED/REFUSED; "
                f"fields={fields!r} stderr={result.stderr_text!r}"
            )
    else:
        if write_flag is not None:
            raise HarnessError(
                f"search/hash write must not emit WRITE; got {write_flag!r}"
            )
        accepted = None
    return MutateOutcome(
        accepted=accepted,
        after=_inspect_from_fields(fields, result.stderr_text),
        stderr=result.stderr_text,
    )


def mutate_component(
    input_url: str,
    field: str,
    value: str,
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> MutateOutcome:
    """Same-object parse → one public write → reread snapshot."""
    return mutate_many(
        input_url, ((field, value),), language=language, max_length=max_length
    )


def clear_component(
    input_url: str,
    field: str,
    *,
    language: str = "c++",
    max_length: int | None = None,
) -> InspectOutcome:
    """Dedicated clear of port, search, or hash on one parsed URL."""
    result = _run_component_probe(
        "clear",
        input_url,
        language=language,
        max_length=max_length,
        extra_args=["--field", field],
    )
    statuses, fields = _parse_fields(result.stdout)
    if not statuses or statuses[0] != "OK":
        raise HarnessError(
            f"clear {field!r} omitted OK for {input_url!r}; "
            f"status={statuses!r} stderr={result.stderr_text!r}"
        )
    return _inspect_from_fields(fields, result.stderr_text)


def try_inspect_without_linked_library(
    input_url: str = GOOGLE_URL,
) -> tuple[str, RunResult | None]:
    """Compile the C++ inspect probe without linking the recipe library.

    Returns ``("link_failed", compile_result)`` when the compiler/linker
    refuses to produce a binary. Returns ``("ran", run_result)`` if a
    binary was produced; the caller must show it did not yield the
    successful named href and origin. Never skips.
    """
    include = include_dir()
    compiler = cxx_compiler()
    work = Path(tempfile.mkdtemp(prefix="f02-nolink-"))
    try:
        source_path = work / "probe.cpp"
        source_path.write_text(_CXX_COMPONENT_PROBE, encoding="utf-8")
        out_path = work / "probe"
        argv = [
            compiler,
            f"-std={DEFAULT_CXX_STD}",
            f"-I{include}",
            str(source_path),
            "-o",
            str(out_path),
        ]
        if os.name != "nt":
            argv.append("-pthread")
        compile_result = run_command(argv, cwd=work)
        if compile_result.returncode != 0:
            return "link_failed", compile_result
        if not out_path.is_file():
            raise HarnessError(
                "compiler exited 0 without a binary while not linking the library"
            )
        run_result = run_command(
            [str(out_path), "inspect"],
            cwd=work,
            stdin=input_url.encode("utf-8"),
            timeout=DEFAULT_TIMEOUT,
        )
        return "ran", run_result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def inspect_probe_has_href_and_origin(
    result: RunResult, href: str, origin: str
) -> bool:
    """True only if a completed inspect classified OK with this href and origin."""
    if result.returncode != 0:
        return False
    try:
        statuses, fields = _parse_fields(result.stdout)
    except HarnessError:
        return False
    return (
        statuses[:1] == ["OK"]
        and fields.get("HREF") == href
        and fields.get("ORIGIN") == origin
    )


# ---------------------------------------------------------------------------
# FP-03: URL Search Params
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GetOutcome:
    """Classified get. ``value`` is set only when ``present`` is true."""

    present: bool
    value: str | None


@dataclass(frozen=True)
class SearchParamsSnapshot:
    """After-ops list: size, serialize, iterators, and requested lookups.

    ``construct_size`` / ``construct_serialize`` / ``construct_gets`` are
    the object immediately after construction, before any listed op.
    """

    size: int
    serialize: str
    keys: tuple[str, ...]
    values: tuple[str, ...]
    entries: tuple[tuple[str, str], ...]
    gets: dict[str, GetOutcome]
    get_alls: dict[str, tuple[str, ...]]
    has_keys: dict[str, bool]
    has_pairs: dict[tuple[str, str], bool]
    construct_size: int
    construct_serialize: str
    construct_gets: dict[str, GetOutcome]
    stderr: str


_CXX_SEARCH_PROBE = r"""
#include "hrefparse.h"

#include <cstdint>
#include <iostream>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

static std::string read_stdin() {
  std::string data;
  char buf[4096];
  while (true) {
    std::cin.read(buf, sizeof(buf));
    const std::streamsize n = std::cin.gcount();
    if (n <= 0) {
      break;
    }
    data.append(buf, static_cast<size_t>(n));
  }
  return data;
}

static void emit_status(const char* status) { std::cout << status << '\n'; }

static void emit_field(const char* key, std::string_view val) {
  std::cout << key << ' ' << val.size() << '\n';
  std::cout.write(val.data(), static_cast<std::streamsize>(val.size()));
  std::cout.put('\n');
}

static void emit_indexed(const char* prefix, size_t i, std::string_view val) {
  const std::string key = std::string(prefix) + std::to_string(i);
  emit_field(key.c_str(), val);
}

static void emit_get(hrefparse::url_search_params& p, const std::string& key,
                     const char* flag_prefix, const char* val_prefix,
                     size_t i) {
  auto got = p.get(key);
  if (!got.has_value()) {
    emit_indexed(flag_prefix, i, "ABSENT");
    return;
  }
  emit_indexed(flag_prefix, i, "PRESENT");
  emit_indexed(val_prefix, i, *got);
}

static void emit_get_all(hrefparse::url_search_params& p, const std::string& key,
                         size_t i) {
  const auto all = p.get_all(key);
  emit_indexed("AN", i, std::to_string(all.size()));
  for (size_t j = 0; j < all.size(); ++j) {
    const std::string name =
        std::string("A") + std::to_string(i) + "_" + std::to_string(j);
    emit_field(name.c_str(), all[j]);
  }
}

int main(int argc, char** argv) {
  std::ios::sync_with_stdio(false);
  if (argc < 2) {
    std::cerr << "missing op\n";
    return 2;
  }
  const std::string op = argv[1];
  if (op != "session") {
    std::cerr << "unknown op\n";
    return 2;
  }
  bool have_max = false;
  uint32_t max_value = 0;
  std::vector<std::string> kinds;
  std::vector<std::string> a1;
  std::vector<std::string> a2;
  std::vector<std::string> lookup_keys;
  std::vector<std::pair<std::string, std::string>> lookup_pairs;
  for (int i = 2; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--max" && i + 1 < argc) {
      max_value = static_cast<uint32_t>(std::stoul(argv[++i]));
      have_max = true;
    } else if (arg == "--append" && i + 2 < argc) {
      kinds.emplace_back("append");
      a1.emplace_back(argv[++i]);
      a2.emplace_back(argv[++i]);
    } else if (arg == "--set" && i + 2 < argc) {
      kinds.emplace_back("set");
      a1.emplace_back(argv[++i]);
      a2.emplace_back(argv[++i]);
    } else if (arg == "--remove" && i + 1 < argc) {
      kinds.emplace_back("remove");
      a1.emplace_back(argv[++i]);
      a2.emplace_back();
    } else if (arg == "--remove-value" && i + 2 < argc) {
      kinds.emplace_back("remove-value");
      a1.emplace_back(argv[++i]);
      a2.emplace_back(argv[++i]);
    } else if (arg == "--sort") {
      kinds.emplace_back("sort");
      a1.emplace_back();
      a2.emplace_back();
    } else if (arg == "--reset" && i + 1 < argc) {
      kinds.emplace_back("reset");
      a1.emplace_back(argv[++i]);
      a2.emplace_back();
    } else if (arg == "--get" && i + 1 < argc) {
      lookup_keys.emplace_back(argv[++i]);
    } else if (arg == "--has-value" && i + 2 < argc) {
      const std::string hk = argv[++i];
      const std::string hv = argv[++i];
      lookup_pairs.emplace_back(hk, hv);
    } else {
      std::cerr << "unknown arg\n";
      return 2;
    }
  }
  const std::string input = read_stdin();
  if (have_max) {
    hrefparse::set_max_input_length(max_value);
  }
  hrefparse::url_search_params params{std::string_view(input)};

  const size_t construct_size = params.size();
  const std::string construct_serial = params.to_string();
  std::vector<std::string> construct_flags;
  std::vector<std::string> construct_vals;
  for (const auto& key : lookup_keys) {
    auto got = params.get(key);
    if (!got.has_value()) {
      construct_flags.emplace_back("ABSENT");
      construct_vals.emplace_back();
    } else {
      construct_flags.emplace_back("PRESENT");
      construct_vals.emplace_back(*got);
    }
  }

  for (size_t i = 0; i < kinds.size(); ++i) {
    const std::string& kind = kinds[i];
    if (kind == "append") {
      params.append(a1[i], a2[i]);
    } else if (kind == "set") {
      params.set(a1[i], a2[i]);
    } else if (kind == "remove") {
      params.remove(a1[i]);
    } else if (kind == "remove-value") {
      params.remove(a1[i], a2[i]);
    } else if (kind == "sort") {
      params.sort();
    } else if (kind == "reset") {
      params.reset(a1[i]);
    }
  }

  emit_status("OK");
  emit_field("CSIZE", std::to_string(construct_size));
  emit_field("CSERIAL", construct_serial);
  for (size_t i = 0; i < lookup_keys.size(); ++i) {
    emit_indexed("CG", i, construct_flags[i]);
    if (construct_flags[i] == "PRESENT") {
      emit_indexed("CGV", i, construct_vals[i]);
    }
  }
  emit_field("SIZE", std::to_string(params.size()));
  emit_field("SERIAL", params.to_string());

  std::vector<std::string> keys;
  auto key_it = params.get_keys();
  while (key_it.has_next()) {
    auto item = key_it.next();
    if (!item.has_value()) {
      break;
    }
    keys.emplace_back(*item);
  }
  emit_field("NKEYS", std::to_string(keys.size()));
  for (size_t i = 0; i < keys.size(); ++i) {
    emit_indexed("K", i, keys[i]);
  }

  std::vector<std::string> values;
  auto val_it = params.get_values();
  while (val_it.has_next()) {
    auto item = val_it.next();
    if (!item.has_value()) {
      break;
    }
    values.emplace_back(*item);
  }
  emit_field("NVALUES", std::to_string(values.size()));
  for (size_t i = 0; i < values.size(); ++i) {
    emit_indexed("V", i, values[i]);
  }

  std::vector<std::pair<std::string, std::string>> entries;
  auto ent_it = params.get_entries();
  while (ent_it.has_next()) {
    auto item = ent_it.next();
    if (!item.has_value()) {
      break;
    }
    entries.emplace_back(std::string(item->first), std::string(item->second));
  }
  emit_field("NENTRIES", std::to_string(entries.size()));
  for (size_t i = 0; i < entries.size(); ++i) {
    emit_indexed("EK", i, entries[i].first);
    emit_indexed("EV", i, entries[i].second);
  }

  for (size_t i = 0; i < lookup_keys.size(); ++i) {
    emit_get(params, lookup_keys[i], "G", "GV", i);
    emit_get_all(params, lookup_keys[i], i);
    emit_indexed("HK", i, params.has(lookup_keys[i]) ? "yes" : "no");
  }
  for (size_t i = 0; i < lookup_pairs.size(); ++i) {
    const bool yes =
        params.has(lookup_pairs[i].first, lookup_pairs[i].second);
    emit_indexed("HV", i, yes ? "yes" : "no");
  }
  return 0;
}
"""

_C_SEARCH_PROBE = r"""
#ifdef __cplusplus
extern "C" {
#endif
#include "hrefparse_c.h"
#ifdef __cplusplus
}
#endif

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { MAX_OPS = 32, MAX_LOOK = 16 };

static char* read_stdin(size_t* out_len) {
  size_t cap = 4096;
  size_t n = 0;
  char* buf = (char*)malloc(cap);
  if (buf == NULL) {
    return NULL;
  }
  for (;;) {
    if (n + 1 >= cap) {
      cap *= 2;
      char* grown = (char*)realloc(buf, cap);
      if (grown == NULL) {
        free(buf);
        return NULL;
      }
      buf = grown;
    }
    size_t got = fread(buf + n, 1, cap - n, stdin);
    n += got;
    if (got == 0) {
      break;
    }
  }
  *out_len = n;
  return buf;
}

static void emit_status(const char* status) { fprintf(stdout, "%s\n", status); }

static void emit_field(const char* key, const char* data, size_t len) {
  fprintf(stdout, "%s %zu\n", key, len);
  if (len > 0 && data != NULL) {
    fwrite(data, 1, len, stdout);
  }
  fputc('\n', stdout);
}

static void emit_indexed(const char* prefix, size_t i, const char* data,
                         size_t len) {
  char key[32];
  int n = snprintf(key, sizeof(key), "%s%zu", prefix, i);
  if (n < 0) {
    return;
  }
  emit_field(key, data, len);
}

static void emit_indexed_cstr(const char* prefix, size_t i, const char* s) {
  emit_indexed(prefix, i, s, strlen(s));
}

static char* copy_hrefparse_string(hrefparse_string s, size_t* out_len) {
  *out_len = s.length;
  char* p = (char*)malloc(s.length + 1);
  if (p == NULL) {
    return NULL;
  }
  if (s.length > 0 && s.data != NULL) {
    memcpy(p, s.data, s.length);
  }
  p[s.length] = '\0';
  return p;
}

int main(int argc, char** argv) {
  if (argc < 2) {
    fprintf(stderr, "missing op\n");
    return 2;
  }
  if (strcmp(argv[1], "session") != 0) {
    fprintf(stderr, "unknown op\n");
    return 2;
  }
  int have_max = 0;
  uint32_t max_value = 0;
  const char* kinds[MAX_OPS];
  const char* op_a[MAX_OPS];
  const char* op_b[MAX_OPS];
  int nops = 0;
  const char* lookup_keys[MAX_LOOK];
  int nlook = 0;
  const char* pair_k[MAX_LOOK];
  const char* pair_v[MAX_LOOK];
  int npairs = 0;
  for (int i = 2; i < argc; ++i) {
    if (strcmp(argv[i], "--max") == 0 && i + 1 < argc) {
      max_value = (uint32_t)strtoul(argv[++i], NULL, 10);
      have_max = 1;
    } else if (strcmp(argv[i], "--append") == 0 && i + 2 < argc &&
               nops < MAX_OPS) {
      kinds[nops] = "append";
      op_a[nops] = argv[++i];
      op_b[nops] = argv[++i];
      nops += 1;
    } else if (strcmp(argv[i], "--set") == 0 && i + 2 < argc &&
               nops < MAX_OPS) {
      kinds[nops] = "set";
      op_a[nops] = argv[++i];
      op_b[nops] = argv[++i];
      nops += 1;
    } else if (strcmp(argv[i], "--remove") == 0 && i + 1 < argc &&
               nops < MAX_OPS) {
      kinds[nops] = "remove";
      op_a[nops] = argv[++i];
      op_b[nops] = "";
      nops += 1;
    } else if (strcmp(argv[i], "--remove-value") == 0 && i + 2 < argc &&
               nops < MAX_OPS) {
      kinds[nops] = "remove-value";
      op_a[nops] = argv[++i];
      op_b[nops] = argv[++i];
      nops += 1;
    } else if (strcmp(argv[i], "--sort") == 0 && nops < MAX_OPS) {
      kinds[nops] = "sort";
      op_a[nops] = "";
      op_b[nops] = "";
      nops += 1;
    } else if (strcmp(argv[i], "--reset") == 0 && i + 1 < argc &&
               nops < MAX_OPS) {
      kinds[nops] = "reset";
      op_a[nops] = argv[++i];
      op_b[nops] = "";
      nops += 1;
    } else if (strcmp(argv[i], "--get") == 0 && i + 1 < argc &&
               nlook < MAX_LOOK) {
      lookup_keys[nlook++] = argv[++i];
    } else if (strcmp(argv[i], "--has-value") == 0 && i + 2 < argc &&
               npairs < MAX_LOOK) {
      pair_k[npairs] = argv[++i];
      pair_v[npairs] = argv[++i];
      npairs += 1;
    } else {
      fprintf(stderr, "unknown arg\n");
      return 2;
    }
  }
  size_t input_len = 0;
  char* input = read_stdin(&input_len);
  if (input == NULL) {
    fprintf(stderr, "stdin alloc failed\n");
    return 2;
  }
  if (have_max) {
    hrefparse_set_max_input_length(max_value);
  }
  hrefparse_url_search_params params = hrefparse_parse_search_params(input, input_len);

  char csize_buf[32];
  int csn = snprintf(csize_buf, sizeof(csize_buf), "%zu",
                     hrefparse_search_params_size(params));
  hrefparse_owned_string cserial = hrefparse_search_params_to_string(params);
  const char* cflags[MAX_LOOK];
  char* cvals[MAX_LOOK];
  size_t cvlen[MAX_LOOK];
  for (int i = 0; i < nlook; ++i) {
    size_t kl = strlen(lookup_keys[i]);
    if (hrefparse_search_params_has(params, lookup_keys[i], kl)) {
      cflags[i] = "PRESENT";
      hrefparse_string g = hrefparse_search_params_get(params, lookup_keys[i], kl);
      cvals[i] = copy_hrefparse_string(g, &cvlen[i]);
    } else {
      cflags[i] = "ABSENT";
      cvals[i] = NULL;
      cvlen[i] = 0;
    }
  }

  for (int i = 0; i < nops; ++i) {
    size_t al = strlen(op_a[i]);
    size_t bl = strlen(op_b[i]);
    if (strcmp(kinds[i], "append") == 0) {
      hrefparse_search_params_append(params, op_a[i], al, op_b[i], bl);
    } else if (strcmp(kinds[i], "set") == 0) {
      hrefparse_search_params_set(params, op_a[i], al, op_b[i], bl);
    } else if (strcmp(kinds[i], "remove") == 0) {
      hrefparse_search_params_remove(params, op_a[i], al);
    } else if (strcmp(kinds[i], "remove-value") == 0) {
      hrefparse_search_params_remove_value(params, op_a[i], al, op_b[i], bl);
    } else if (strcmp(kinds[i], "sort") == 0) {
      hrefparse_search_params_sort(params);
    } else if (strcmp(kinds[i], "reset") == 0) {
      hrefparse_search_params_reset(params, op_a[i], al);
    }
  }

  emit_status("OK");
  emit_field("CSIZE", csize_buf, (size_t)(csn < 0 ? 0 : csn));
  emit_field("CSERIAL", cserial.data, cserial.length);
  hrefparse_free_owned_string(cserial);
  for (int i = 0; i < nlook; ++i) {
    emit_indexed_cstr("CG", (size_t)i, cflags[i]);
    if (strcmp(cflags[i], "PRESENT") == 0) {
      emit_indexed("CGV", (size_t)i, cvals[i] == NULL ? "" : cvals[i],
                   cvlen[i]);
    }
    free(cvals[i]);
  }

  char size_buf[32];
  int sn = snprintf(size_buf, sizeof(size_buf), "%zu",
                    hrefparse_search_params_size(params));
  emit_field("SIZE", size_buf, (size_t)(sn < 0 ? 0 : sn));
  hrefparse_owned_string serial = hrefparse_search_params_to_string(params);
  emit_field("SERIAL", serial.data, serial.length);
  hrefparse_free_owned_string(serial);

  hrefparse_url_search_params_keys_iter kit = hrefparse_search_params_get_keys(params);
  char* keys[64];
  size_t keylens[64];
  int nkeys = 0;
  while (hrefparse_search_params_keys_iter_has_next(kit) && nkeys < 64) {
    keys[nkeys] = copy_hrefparse_string(hrefparse_search_params_keys_iter_next(kit),
                                  &keylens[nkeys]);
    nkeys += 1;
  }
  hrefparse_free_search_params_keys_iter(kit);
  char nkeys_buf[32];
  int nkn = snprintf(nkeys_buf, sizeof(nkeys_buf), "%d", nkeys);
  emit_field("NKEYS", nkeys_buf, (size_t)(nkn < 0 ? 0 : nkn));
  for (int i = 0; i < nkeys; ++i) {
    emit_indexed("K", (size_t)i, keys[i] == NULL ? "" : keys[i], keylens[i]);
    free(keys[i]);
  }

  hrefparse_url_search_params_values_iter vit = hrefparse_search_params_get_values(params);
  char* vals[64];
  size_t vallens[64];
  int nvals = 0;
  while (hrefparse_search_params_values_iter_has_next(vit) && nvals < 64) {
    vals[nvals] = copy_hrefparse_string(hrefparse_search_params_values_iter_next(vit),
                                  &vallens[nvals]);
    nvals += 1;
  }
  hrefparse_free_search_params_values_iter(vit);
  char nvals_buf[32];
  int nvn = snprintf(nvals_buf, sizeof(nvals_buf), "%d", nvals);
  emit_field("NVALUES", nvals_buf, (size_t)(nvn < 0 ? 0 : nvn));
  for (int i = 0; i < nvals; ++i) {
    emit_indexed("V", (size_t)i, vals[i] == NULL ? "" : vals[i], vallens[i]);
    free(vals[i]);
  }

  hrefparse_url_search_params_entries_iter eit =
      hrefparse_search_params_get_entries(params);
  char* eks[64];
  char* evs[64];
  size_t eklens[64];
  size_t evlens[64];
  int nent = 0;
  while (hrefparse_search_params_entries_iter_has_next(eit) && nent < 64) {
    hrefparse_string_pair pair = hrefparse_search_params_entries_iter_next(eit);
    eks[nent] = copy_hrefparse_string(pair.key, &eklens[nent]);
    evs[nent] = copy_hrefparse_string(pair.value, &evlens[nent]);
    nent += 1;
  }
  hrefparse_free_search_params_entries_iter(eit);
  char nent_buf[32];
  int nen = snprintf(nent_buf, sizeof(nent_buf), "%d", nent);
  emit_field("NENTRIES", nent_buf, (size_t)(nen < 0 ? 0 : nen));
  for (int i = 0; i < nent; ++i) {
    emit_indexed("EK", (size_t)i, eks[i] == NULL ? "" : eks[i], eklens[i]);
    emit_indexed("EV", (size_t)i, evs[i] == NULL ? "" : evs[i], evlens[i]);
    free(eks[i]);
    free(evs[i]);
  }

  for (int i = 0; i < nlook; ++i) {
    size_t kl = strlen(lookup_keys[i]);
    if (hrefparse_search_params_has(params, lookup_keys[i], kl)) {
      emit_indexed_cstr("G", (size_t)i, "PRESENT");
      hrefparse_string g = hrefparse_search_params_get(params, lookup_keys[i], kl);
      emit_indexed("GV", (size_t)i, g.data, g.length);
    } else {
      emit_indexed_cstr("G", (size_t)i, "ABSENT");
    }
    hrefparse_strings all = hrefparse_search_params_get_all(params, lookup_keys[i], kl);
    size_t an = hrefparse_strings_size(all);
    char anbuf[32];
    int ann = snprintf(anbuf, sizeof(anbuf), "%zu", an);
    emit_indexed("AN", (size_t)i, anbuf, (size_t)(ann < 0 ? 0 : ann));
    for (size_t j = 0; j < an; ++j) {
      hrefparse_string item = hrefparse_strings_get(all, j);
      char name[40];
      snprintf(name, sizeof(name), "A%zu_%zu", (size_t)i, j);
      emit_field(name, item.data, item.length);
    }
    hrefparse_free_strings(all);
    emit_indexed_cstr(
        "HK", (size_t)i,
        hrefparse_search_params_has(params, lookup_keys[i], kl) ? "yes" : "no");
  }
  for (int i = 0; i < npairs; ++i) {
    int yes = hrefparse_search_params_has_value(params, pair_k[i], strlen(pair_k[i]),
                                          pair_v[i], strlen(pair_v[i]))
                  ? 1
                  : 0;
    emit_indexed_cstr("HV", (size_t)i, yes ? "yes" : "no");
  }

  hrefparse_free_search_params(params);
  free(input);
  return 0;
}
"""


def _search_probe_source(language: str) -> str:
    return _C_SEARCH_PROBE if language == "c" else _CXX_SEARCH_PROBE


def _require_int_field(fields: dict[str, str], key: str) -> int:
    if key not in fields:
        raise HarnessError(f"search-params probe omitted {key}")
    try:
        return int(fields[key], 10)
    except ValueError as exc:
        raise HarnessError(
            f"search-params {key} is not an integer: {fields[key]!r}"
        ) from exc


def _require_get_outcome(
    fields: dict[str, str], flag_prefix: str, val_prefix: str, index: int
) -> GetOutcome:
    flag_key = f"{flag_prefix}{index}"
    if flag_key not in fields:
        raise HarnessError(f"search-params probe omitted {flag_key}")
    flag = fields[flag_key]
    if flag == "ABSENT":
        return GetOutcome(present=False, value=None)
    if flag == "PRESENT":
        val_key = f"{val_prefix}{index}"
        if val_key not in fields:
            raise HarnessError(
                f"PRESENT get omitted value field {val_key}"
            )
        return GetOutcome(present=True, value=fields[val_key])
    raise HarnessError(f"{flag_key} is not ABSENT/PRESENT: {flag!r}")


def _require_get_all(fields: dict[str, str], index: int) -> tuple[str, ...]:
    count = _require_int_field(fields, f"AN{index}")
    if count < 0:
        raise HarnessError(f"GETALL count negative: {count}")
    items: list[str] = []
    for j in range(count):
        key = f"A{index}_{j}"
        if key not in fields:
            raise HarnessError(f"GETALL omitted {key}")
        items.append(fields[key])
    return tuple(items)


def _require_indexed_list(
    fields: dict[str, str], count_key: str, prefix: str
) -> tuple[str, ...]:
    count = _require_int_field(fields, count_key)
    if count < 0:
        raise HarnessError(f"{count_key} negative: {count}")
    items: list[str] = []
    for i in range(count):
        key = f"{prefix}{i}"
        if key not in fields:
            raise HarnessError(f"list omitted {key} (count={count})")
        items.append(fields[key])
    return tuple(items)


def _snapshot_from_fields(
    fields: dict[str, str],
    stderr: str,
    lookup_keys: Sequence[str],
    lookup_pairs: Sequence[tuple[str, str]],
) -> SearchParamsSnapshot:
    size = _require_int_field(fields, "SIZE")
    if "SERIAL" not in fields:
        raise HarnessError("search-params probe omitted SERIAL")
    keys = _require_indexed_list(fields, "NKEYS", "K")
    values = _require_indexed_list(fields, "NVALUES", "V")
    nent = _require_int_field(fields, "NENTRIES")
    entries: list[tuple[str, str]] = []
    for i in range(nent):
        ek = f"EK{i}"
        ev = f"EV{i}"
        if ek not in fields or ev not in fields:
            raise HarnessError(f"entries omitted {ek}/{ev}")
        entries.append((fields[ek], fields[ev]))
    gets: dict[str, GetOutcome] = {}
    get_alls: dict[str, tuple[str, ...]] = {}
    has_keys: dict[str, bool] = {}
    construct_gets: dict[str, GetOutcome] = {}
    for i, key in enumerate(lookup_keys):
        gets[key] = _require_get_outcome(fields, "G", "GV", i)
        get_alls[key] = _require_get_all(fields, i)
        has_keys[key] = _yesno_field(fields, f"HK{i}")
        construct_gets[key] = _require_get_outcome(fields, "CG", "CGV", i)
    has_pairs: dict[tuple[str, str], bool] = {}
    for i, pair in enumerate(lookup_pairs):
        has_pairs[pair] = _yesno_field(fields, f"HV{i}")
    construct_size = _require_int_field(fields, "CSIZE")
    if "CSERIAL" not in fields:
        raise HarnessError("search-params probe omitted CSERIAL")
    return SearchParamsSnapshot(
        size=size,
        serialize=fields["SERIAL"],
        keys=keys,
        values=values,
        entries=tuple(entries),
        gets=gets,
        get_alls=get_alls,
        has_keys=has_keys,
        has_pairs=has_pairs,
        construct_size=construct_size,
        construct_serialize=fields["CSERIAL"],
        construct_gets=construct_gets,
        stderr=stderr,
    )


def run_search_params(
    init: str,
    ops: Sequence[tuple[str, ...]] | None = None,
    *,
    language: str = "c++",
    max_length: int | None = None,
    lookup_keys: Sequence[str] | None = None,
    lookup_pairs: Sequence[tuple[str, str]] | None = None,
) -> SearchParamsSnapshot:
    """Same process: optional cap, construct, ops, fresh-iterator snapshot."""
    lang = _normalize_language(language)
    keys = tuple(lookup_keys or ())
    pairs = tuple(lookup_pairs or ())
    args: list[str] = ["session"]
    if max_length is not None:
        args.extend(["--max", str(int(max_length))])
    for op in ops or ():
        if not op:
            raise ValueError("empty search-params op")
        kind = op[0]
        if kind == "append":
            args.extend(["--append", op[1], op[2]])
        elif kind == "set":
            args.extend(["--set", op[1], op[2]])
        elif kind == "remove":
            args.extend(["--remove", op[1]])
        elif kind == "remove-value":
            args.extend(["--remove-value", op[1], op[2]])
        elif kind == "sort":
            args.append("--sort")
        elif kind == "reset":
            args.extend(["--reset", op[1]])
        else:
            raise ValueError(f"unknown search-params op {kind!r}")
    for key in keys:
        args.extend(["--get", key])
    for key, value in pairs:
        args.extend(["--has-value", key, value])
    result = invoke(
        _search_probe_source(lang),
        args,
        language=lang,
        stdin=init.encode("utf-8"),
    )
    if result.returncode != 0:
        raise HarnessError(
            f"search-params probe language={lang} exited "
            f"{result.returncode} (not a classified product outcome): "
            f"{result.stderr_text!r}"
        )
    statuses, fields = _parse_fields(result.stdout)
    if not statuses or statuses[0] != "OK":
        raise HarnessError(
            f"search-params probe omitted OK; status={statuses!r} "
            f"stderr={result.stderr_text!r}"
        )
    return _snapshot_from_fields(fields, result.stderr_text, keys, pairs)


def search_params_probe_has_named_append_success(result: RunResult) -> bool:
    """True only if a completed session has size 4 and get g present as h."""
    if result.returncode != 0:
        return False
    try:
        statuses, fields = _parse_fields(result.stdout)
        if statuses[:1] != ["OK"]:
            return False
        snap = _snapshot_from_fields(
            fields, result.stderr_text, ("g",), ()
        )
    except HarnessError:
        return False
    got = snap.gets.get("g")
    return (
        snap.size == 4
        and got is not None
        and got.present
        and got.value == "h"
    )


def try_search_params_without_linked_library(
    init: str = "a=b&c=d&e=f",
) -> tuple[str, RunResult | None]:
    """Compile the C++ search-params probe without linking the recipe library.

    Returns ``("link_failed", compile_result)`` when the compiler/linker
    refuses to produce a binary. Returns ``("ran", run_result)`` if a
    binary was produced; the caller must show it did not yield get g==h
    and size 4. Never skips.
    """
    include = include_dir()
    compiler = cxx_compiler()
    work = Path(tempfile.mkdtemp(prefix="f03-nolink-"))
    try:
        source_path = work / "probe.cpp"
        source_path.write_text(_CXX_SEARCH_PROBE, encoding="utf-8")
        out_path = work / "probe"
        argv = [
            compiler,
            f"-std={DEFAULT_CXX_STD}",
            f"-I{include}",
            str(source_path),
            "-o",
            str(out_path),
        ]
        if os.name != "nt":
            argv.append("-pthread")
        compile_result = run_command(argv, cwd=work)
        if compile_result.returncode != 0:
            return "link_failed", compile_result
        if not out_path.is_file():
            raise HarnessError(
                "compiler exited 0 without a binary while not linking the library"
            )
        run_result = run_command(
            [str(out_path), "session", "--append", "g", "h", "--get", "g"],
            cwd=work,
            stdin=init.encode("utf-8"),
            timeout=DEFAULT_TIMEOUT,
        )
        return "ran", run_result
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# FP-04: URLPattern compile / test / execute (C++ library, caller engine)
# ---------------------------------------------------------------------------

_PATTERN_COMPONENTS = (
    "protocol",
    "username",
    "password",
    "hostname",
    "port",
    "pathname",
    "search",
    "hash",
)

_PATTERN_PREFIX = {
    "protocol": "PROT",
    "username": "USER",
    "password": "PASS",
    "hostname": "HOST",
    "port": "PORT",
    "pathname": "PATH",
    "search": "SRCH",
    "hash": "HASH",
}

_BOOKS_ID_PATTERN = "/books/:id"
_HTTPS_EXAMPLE_BASE = "https://example.com"
_NAMED_BOOKS_URL = "https://example.com/books/123"


@dataclass(frozen=True)
class GroupCapture:
    """One named capture. ``value`` is set only when ``present`` is true."""

    present: bool
    value: str | None


@dataclass(frozen=True)
class PatternCompile:
    """Classified compile. Pattern strings exist only when ``ok`` is true."""

    ok: bool
    protocol: str | None
    username: str | None
    password: str | None
    hostname: str | None
    port: str | None
    pathname: str | None
    search: str | None
    hash: str | None
    has_regexp_groups: bool | None
    stderr: str


@dataclass(frozen=True)
class ComponentMatch:
    """One component of a successful execute/match."""

    input: str
    groups: dict[str, GroupCapture]


@dataclass(frozen=True)
class PatternMatch:
    """Same-process compile then optional test / execute.

    ``test`` and ``exec_matched`` are None when compile failed or no
    match was requested. They are never False on ``COMPILE_FAIL``.
    """

    compile: PatternCompile
    test: bool | None
    exec_matched: bool | None
    protocol: ComponentMatch | None
    username: ComponentMatch | None
    password: ComponentMatch | None
    hostname: ComponentMatch | None
    port: ComponentMatch | None
    pathname: ComponentMatch | None
    search: ComponentMatch | None
    hash: ComponentMatch | None
    stderr: str


_CXX_PATTERN_PROBE = r"""
#include "hrefparse.h"

#include <iostream>
#include <optional>
#include <regex>
#include <string>
#include <string_view>
#include <vector>

static std::string read_stdin() {
  std::string data;
  char buf[4096];
  while (true) {
    std::cin.read(buf, sizeof(buf));
    const std::streamsize n = std::cin.gcount();
    if (n <= 0) {
      break;
    }
    data.append(buf, static_cast<size_t>(n));
  }
  return data;
}

static void emit_status(const char* status) { std::cout << status << '\n'; }

static void emit_field(const char* key, std::string_view val) {
  std::cout << key << ' ' << val.size() << '\n';
  std::cout.write(val.data(), static_cast<std::streamsize>(val.size()));
  std::cout.put('\n');
}

class usable_regex_provider {
 public:
  usable_regex_provider() = default;
  using regex_type = std::regex;
  static std::optional<regex_type> create_instance(std::string_view pattern,
                                                   bool ignore_case) {
    auto flags = ignore_case
                     ? std::regex::icase | std::regex_constants::ECMAScript
                     : std::regex_constants::ECMAScript;
    try {
      return std::regex(pattern.data(), pattern.size(), flags);
    } catch (const std::regex_error&) {
      return std::nullopt;
    }
  }
  static std::optional<std::vector<std::optional<std::string>>> regex_search(
      std::string_view input, const regex_type& pattern) {
    std::match_results<std::string_view::const_iterator> match_result;
    try {
      if (!std::regex_search(input.begin(), input.end(), match_result, pattern,
                             std::regex_constants::match_any)) {
        return std::nullopt;
      }
    } catch (const std::regex_error&) {
      return std::nullopt;
    }
    std::vector<std::optional<std::string>> matches;
    if (match_result.empty()) {
      return matches;
    }
    matches.reserve(match_result.size());
    for (size_t i = 1; i < match_result.size(); ++i) {
      if (auto entry = match_result[i]; entry.matched) {
        matches.emplace_back(entry.str());
      } else {
        matches.emplace_back(std::nullopt);
      }
    }
    return matches;
  }
  static bool regex_match(std::string_view input, const regex_type& pattern) {
    try {
      return std::regex_match(input.begin(), input.end(), pattern);
    } catch (const std::regex_error&) {
      return false;
    }
  }
};

class unusable_regex_provider {
 public:
  unusable_regex_provider() = default;
  using regex_type = int;
  static std::optional<regex_type> create_instance(std::string_view,
                                                   bool) {
    return std::nullopt;
  }
  static std::optional<std::vector<std::optional<std::string>>> regex_search(
      std::string_view, const regex_type&) {
    return std::nullopt;
  }
  static bool regex_match(std::string_view, const regex_type&) { return false; }
};

static void apply_comp(hrefparse::url_pattern_init& init, const std::string& field,
                       const std::string& value) {
  if (field == "protocol") {
    init.protocol = value;
  } else if (field == "username") {
    init.username = value;
  } else if (field == "password") {
    init.password = value;
  } else if (field == "hostname") {
    init.hostname = value;
  } else if (field == "port") {
    init.port = value;
  } else if (field == "pathname") {
    init.pathname = value;
  } else if (field == "search") {
    init.search = value;
  } else if (field == "hash") {
    init.hash = value;
  } else {
    std::cerr << "unknown component field\n";
    std::exit(2);
  }
}

static void emit_groups(
    const char* prefix, const hrefparse::url_pattern_component_result& result) {
  emit_field((std::string(prefix) + "_IN").c_str(), result.input);
  emit_field((std::string(prefix) + "_NG").c_str(),
             std::to_string(result.groups.size()));
  size_t i = 0;
  for (const auto& entry : result.groups) {
    const std::string nk = std::string(prefix) + "_NK" + std::to_string(i);
    const std::string np = std::string(prefix) + "_NP" + std::to_string(i);
    emit_field(nk.c_str(), entry.first);
    if (entry.second.has_value()) {
      emit_field(np.c_str(), "PRESENT");
      const std::string nv = std::string(prefix) + "_NV" + std::to_string(i);
      emit_field(nv.c_str(), *entry.second);
    } else {
      emit_field(np.c_str(), "ABSENT");
    }
    ++i;
  }
}

template <typename Provider>
int run_session(bool have_pattern, const std::string& pattern, bool have_base,
                const std::string& base, bool ignore_case, bool do_match,
                bool have_input, const std::string& input_url,
                const std::vector<std::pair<std::string, std::string>>& comps,
                const std::vector<std::pair<std::string, std::string>>&
                    in_comps) {
  hrefparse::url_pattern_options options;
  options.ignore_case = ignore_case;
  const hrefparse::url_pattern_options* opt_ptr = &options;

  auto compiled = [&]() -> tl::expected<hrefparse::url_pattern<Provider>, hrefparse::errors> {
    if (have_pattern) {
      std::string_view pat = pattern;
      std::string_view base_sv = base;
      const std::string_view* base_ptr = have_base ? &base_sv : nullptr;
      return hrefparse::parse_url_pattern<Provider>(std::string_view(pat), base_ptr,
                                                  opt_ptr);
    }
    hrefparse::url_pattern_init init;
    for (const auto& kv : comps) {
      apply_comp(init, kv.first, kv.second);
    }
    if (have_base) {
      init.base_url = base;
    }
    return hrefparse::parse_url_pattern<Provider>(std::move(init), nullptr,
                                                opt_ptr);
  }();

  if (!compiled) {
    emit_status("FAIL");
    return 0;
  }

  emit_status("OK");
  emit_field("REGEXP", compiled->has_regexp_groups() ? "yes" : "no");
  emit_field("PROT_PAT", compiled->get_protocol());
  emit_field("USER_PAT", compiled->get_username());
  emit_field("PASS_PAT", compiled->get_password());
  emit_field("HOST_PAT", compiled->get_hostname());
  emit_field("PORT_PAT", compiled->get_port());
  emit_field("PATH_PAT", compiled->get_pathname());
  emit_field("SRCH_PAT", compiled->get_search());
  emit_field("HASH_PAT", compiled->get_hash());

  if (!do_match) {
    return 0;
  }

  // The Contract leaves hrefparse::errors to the implementer, so default
  // construction and assignment of a result are not promised; each result
  // is initialized directly from its call.
  const std::string_view in = input_url;
  hrefparse::url_pattern_init in_init;
  if (!have_input) {
    for (const auto& kv : in_comps) {
      apply_comp(in_init, kv.first, kv.second);
    }
  }
  auto test_result = [&]() {
    if (have_input) {
      return compiled->test(in, nullptr);
    }
    return compiled->test(in_init, nullptr);
  }();
  auto exec_result = [&]() {
    if (have_input) {
      return compiled->exec(in, nullptr);
    }
    return compiled->exec(in_init, nullptr);
  }();

  if (!test_result) {
    std::cerr << "test returned an unexpected error\n";
    return 2;
  }
  if (!exec_result) {
    std::cerr << "exec returned an unexpected error\n";
    return 2;
  }

  emit_field("TEST", *test_result ? "yes" : "no");
  if (!exec_result->has_value()) {
    emit_field("EXEC", "NONE");
    return 0;
  }

  emit_field("EXEC", "MATCH");
  const auto& got = exec_result->value();
  emit_groups("PROT", got.protocol);
  emit_groups("USER", got.username);
  emit_groups("PASS", got.password);
  emit_groups("HOST", got.hostname);
  emit_groups("PORT", got.port);
  emit_groups("PATH", got.pathname);
  emit_groups("SRCH", got.search);
  emit_groups("HASH", got.hash);
  return 0;
}

int main(int argc, char** argv) {
  std::ios::sync_with_stdio(false);
  bool have_pattern = false;
  std::string pattern;
  bool have_base = false;
  std::string base;
  bool ignore_case = false;
  std::string engine = "usable";
  bool do_match = false;
  bool have_input = false;
  std::string input_url;
  std::vector<std::pair<std::string, std::string>> comps;
  std::vector<std::pair<std::string, std::string>> in_comps;

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--pattern" && i + 1 < argc) {
      pattern = argv[++i];
      have_pattern = true;
    } else if (arg == "--comp" && i + 2 < argc) {
      const std::string field = argv[++i];
      const std::string value = argv[++i];
      comps.emplace_back(field, value);
    } else if (arg == "--base" && i + 1 < argc) {
      base = argv[++i];
      have_base = true;
    } else if (arg == "--ignore-case") {
      ignore_case = true;
    } else if (arg == "--engine" && i + 1 < argc) {
      engine = argv[++i];
    } else if (arg == "--match") {
      do_match = true;
    } else if (arg == "--input" && i + 1 < argc) {
      input_url = argv[++i];
      have_input = true;
    } else if (arg == "--in-comp" && i + 2 < argc) {
      const std::string field = argv[++i];
      const std::string value = argv[++i];
      in_comps.emplace_back(field, value);
    } else {
      std::cerr << "unknown arg\n";
      return 2;
    }
  }

  if (have_pattern == !comps.empty()) {
    std::cerr << "need exactly one of --pattern or --comp\n";
    return 2;
  }
  if (do_match && have_input == !in_comps.empty()) {
    std::cerr << "match needs exactly one of --input or --in-comp\n";
    return 2;
  }

  if (engine == "unusable") {
    return run_session<unusable_regex_provider>(
        have_pattern, pattern, have_base, base, ignore_case, do_match,
        have_input, input_url, comps, in_comps);
  }
  if (engine != "usable") {
    std::cerr << "engine must be usable or unusable\n";
    return 2;
  }
  return run_session<usable_regex_provider>(
      have_pattern, pattern, have_base, base, ignore_case, do_match, have_input,
      input_url, comps, in_comps);
}
"""


def unique_digits() -> str:
    """Runtime pathname segment of ASCII digits only."""
    return str(secrets.randbelow(10**12 - 10**8) + 10**8)


def unique_letters() -> str:
    """Runtime pathname segment of ASCII letters only (never a hex token)."""
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    return "".join(alphabet[secrets.randbelow(26)] for _ in range(10))


def _run_pattern_probe(args: Sequence[str]) -> RunResult:
    result = invoke(_CXX_PATTERN_PROBE, args, language="c++")
    if result.returncode != 0:
        raise HarnessError(
            f"urlpattern probe exited {result.returncode} "
            f"(not a classified product outcome): {result.stderr_text!r}"
        )
    return result


def _groups_from_fields(
    fields: dict[str, str], prefix: str
) -> dict[str, GroupCapture]:
    count_key = f"{prefix}_NG"
    if count_key not in fields:
        raise HarnessError(f"match omitted {count_key}; fields={fields!r}")
    try:
        count = int(fields[count_key], 10)
    except ValueError as exc:
        raise HarnessError(
            f"{count_key} is not an integer: {fields[count_key]!r}"
        ) from exc
    if count < 0:
        raise HarnessError(f"{count_key} negative: {count}")
    groups: dict[str, GroupCapture] = {}
    for i in range(count):
        name_key = f"{prefix}_NK{i}"
        flag_key = f"{prefix}_NP{i}"
        if name_key not in fields:
            raise HarnessError(f"match omitted {name_key}")
        if flag_key not in fields:
            raise HarnessError(f"match omitted {flag_key}")
        name = fields[name_key]
        flag = fields[flag_key]
        if flag == "PRESENT":
            val_key = f"{prefix}_NV{i}"
            if val_key not in fields:
                raise HarnessError(
                    f"PRESENT group omitted value field {val_key}"
                )
            groups[name] = GroupCapture(present=True, value=fields[val_key])
        elif flag == "ABSENT":
            groups[name] = GroupCapture(present=False, value=None)
        else:
            raise HarnessError(
                f"{flag_key} is not PRESENT/ABSENT: {flag!r}"
            )
    return groups


def _component_from_fields(
    fields: dict[str, str], prefix: str
) -> ComponentMatch:
    in_key = f"{prefix}_IN"
    if in_key not in fields:
        raise HarnessError(
            f"MATCH omitted component input {in_key}; fields={fields!r}"
        )
    return ComponentMatch(
        input=fields[in_key],
        groups=_groups_from_fields(fields, prefix),
    )


def _compile_from_fields(
    statuses: list[str], fields: dict[str, str], stderr: str
) -> PatternCompile:
    if not statuses:
        raise HarnessError("urlpattern probe omitted OK/FAIL")
    if statuses[0] == "FAIL":
        return PatternCompile(
            ok=False,
            protocol=None,
            username=None,
            password=None,
            hostname=None,
            port=None,
            pathname=None,
            search=None,
            hash=None,
            has_regexp_groups=None,
            stderr=stderr,
        )
    if statuses[0] != "OK":
        raise HarnessError(
            f"unclassified urlpattern status {statuses[0]!r}; "
            f"stderr={stderr!r}"
        )
    missing = [
        f"{_PATTERN_PREFIX[name]}_PAT" for name in _PATTERN_COMPONENTS
        if f"{_PATTERN_PREFIX[name]}_PAT" not in fields
    ]
    if missing:
        raise HarnessError(
            f"COMPILE_OK omitted pattern strings {missing}; "
            f"fields={fields!r}"
        )
    regexp = fields.get("REGEXP")
    if regexp == "yes":
        has_re = True
    elif regexp == "no":
        has_re = False
    else:
        raise HarnessError(
            f"COMPILE_OK omitted REGEXP yes/no; stderr={stderr!r}"
        )
    return PatternCompile(
        ok=True,
        protocol=fields["PROT_PAT"],
        username=fields["USER_PAT"],
        password=fields["PASS_PAT"],
        hostname=fields["HOST_PAT"],
        port=fields["PORT_PAT"],
        pathname=fields["PATH_PAT"],
        search=fields["SRCH_PAT"],
        hash=fields["HASH_PAT"],
        has_regexp_groups=has_re,
        stderr=stderr,
    )


def _pattern_session_args(
    pattern: str | None,
    *,
    base: str | None,
    ignore_case: bool,
    engine: str,
    components: dict[str, str] | None,
    do_match: bool,
    input_url: str | None,
    input_components: dict[str, str] | None,
) -> list[str]:
    if engine not in ("usable", "unusable"):
        raise ValueError(f"engine must be usable or unusable, got {engine!r}")
    if (pattern is None) == (not components):
        raise ValueError("need exactly one of pattern or components")
    args: list[str] = ["--engine", engine]
    if ignore_case:
        args.append("--ignore-case")
    if base is not None:
        args.extend(["--base", base])
    if pattern is not None:
        args.extend(["--pattern", pattern])
    else:
        for field, value in components.items():
            if field not in _PATTERN_PREFIX:
                raise ValueError(f"unknown component field {field!r}")
            args.extend(["--comp", field, value])
    if do_match:
        args.append("--match")
        if (input_url is None) == (not input_components):
            raise ValueError(
                "match needs exactly one of input or input_components"
            )
        if input_url is not None:
            args.extend(["--input", input_url])
        else:
            for field, value in input_components.items():
                if field not in _PATTERN_PREFIX:
                    raise ValueError(f"unknown input component {field!r}")
                args.extend(["--in-comp", field, value])
    return args


def _match_from_result(result: RunResult, *, do_match: bool) -> PatternMatch:
    statuses, fields = _parse_fields(result.stdout)
    compiled = _compile_from_fields(statuses, fields, result.stderr_text)
    if not compiled.ok:
        return PatternMatch(
            compile=compiled,
            test=None,
            exec_matched=None,
            protocol=None,
            username=None,
            password=None,
            hostname=None,
            port=None,
            pathname=None,
            search=None,
            hash=None,
            stderr=result.stderr_text,
        )
    if not do_match:
        return PatternMatch(
            compile=compiled,
            test=None,
            exec_matched=None,
            protocol=None,
            username=None,
            password=None,
            hostname=None,
            port=None,
            pathname=None,
            search=None,
            hash=None,
            stderr=result.stderr_text,
        )
    test_raw = fields.get("TEST")
    exec_raw = fields.get("EXEC")
    if test_raw not in ("yes", "no"):
        raise HarnessError(
            f"compile succeeded but TEST was not yes/no: {test_raw!r}; "
            f"stderr={result.stderr_text!r}"
        )
    if exec_raw not in ("MATCH", "NONE"):
        raise HarnessError(
            f"compile succeeded but EXEC was not MATCH/NONE: {exec_raw!r}; "
            f"stderr={result.stderr_text!r}"
        )
    test_yes = test_raw == "yes"
    exec_matched = exec_raw == "MATCH"
    if not exec_matched:
        return PatternMatch(
            compile=compiled,
            test=test_yes,
            exec_matched=False,
            protocol=None,
            username=None,
            password=None,
            hostname=None,
            port=None,
            pathname=None,
            search=None,
            hash=None,
            stderr=result.stderr_text,
        )
    return PatternMatch(
        compile=compiled,
        test=test_yes,
        exec_matched=True,
        protocol=_component_from_fields(fields, "PROT"),
        username=_component_from_fields(fields, "USER"),
        password=_component_from_fields(fields, "PASS"),
        hostname=_component_from_fields(fields, "HOST"),
        port=_component_from_fields(fields, "PORT"),
        pathname=_component_from_fields(fields, "PATH"),
        search=_component_from_fields(fields, "SRCH"),
        hash=_component_from_fields(fields, "HASH"),
        stderr=result.stderr_text,
    )


def compile_url_pattern(
    pattern: str | None = None,
    *,
    base: str | None = None,
    ignore_case: bool = False,
    engine: str = "usable",
    components: dict[str, str] | None = None,
) -> PatternCompile:
    """Compile a pattern string or per-component initializer. C++ only."""
    args = _pattern_session_args(
        pattern,
        base=base,
        ignore_case=ignore_case,
        engine=engine,
        components=components,
        do_match=False,
        input_url=None,
        input_components=None,
    )
    result = _run_pattern_probe(args)
    return _match_from_result(result, do_match=False).compile


def match_url_pattern(
    pattern: str | None = None,
    *,
    input: str | None = None,
    input_components: dict[str, str] | None = None,
    base: str | None = None,
    ignore_case: bool = False,
    engine: str = "usable",
    components: dict[str, str] | None = None,
) -> PatternMatch:
    """Same process: compile, then test and execute/match. C++ only."""
    args = _pattern_session_args(
        pattern,
        base=base,
        ignore_case=ignore_case,
        engine=engine,
        components=components,
        do_match=True,
        input_url=input,
        input_components=input_components,
    )
    result = _run_pattern_probe(args)
    return _match_from_result(result, do_match=True)


def url_pattern_probe_has_named_books_id(result: RunResult) -> bool:
    """True only if a completed session matched the named books URL with id=123."""
    if result.returncode != 0:
        return False
    try:
        match = _match_from_result(result, do_match=True)
    except HarnessError:
        return False
    if not match.compile.ok or not match.exec_matched:
        return False
    if match.pathname is None:
        return False
    got = match.pathname.groups.get("id")
    return got is not None and got.present and got.value == "123"


def try_url_pattern_without_linked_library(
    pattern: str = _BOOKS_ID_PATTERN,
    *,
    base: str = _HTTPS_EXAMPLE_BASE,
    input_url: str = _NAMED_BOOKS_URL,
) -> tuple[str, RunResult | None]:
    """Compile the C++ URLPattern probe without linking the recipe library.

    Returns ``("link_failed", compile_result)`` when the compiler/linker
    refuses to produce a binary. Returns ``("ran", run_result)`` if a
    binary was produced; the caller must show it did not yield the named
    ``id=123`` match. Never skips.
    """
    include = include_dir()
    compiler = cxx_compiler()
    work = Path(tempfile.mkdtemp(prefix="f04-nolink-"))
    try:
        source_path = work / "probe.cpp"
        source_path.write_text(_CXX_PATTERN_PROBE, encoding="utf-8")
        out_path = work / "probe"
        argv = [
            compiler,
            f"-std={DEFAULT_CXX_STD}",
            f"-I{include}",
            str(source_path),
            "-o",
            str(out_path),
        ]
        if os.name != "nt":
            argv.append("-pthread")
        compile_result = run_command(argv, cwd=work)
        if compile_result.returncode != 0:
            return "link_failed", compile_result
        if not out_path.is_file():
            raise HarnessError(
                "compiler exited 0 without a binary while not linking the library"
            )
        run_result = run_command(
            [
                str(out_path),
                "--engine",
                "usable",
                "--pattern",
                pattern,
                "--base",
                base,
                "--match",
                "--input",
                input_url,
            ],
            cwd=work,
            timeout=DEFAULT_TIMEOUT,
        )
        return "ran", run_result
    finally:
        shutil.rmtree(work, ignore_errors=True)

