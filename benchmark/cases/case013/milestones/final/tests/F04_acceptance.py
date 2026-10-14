# feature: F04
"""Acceptance tests for searching concepts and path-bound governance (FP-04).

Public entries: the ``membundle search`` command and the ``membundle_search`` Model
Context Protocol tool. Observations go through the sealed harness
``workspace`` / ``invoke`` / ``mcp_batch`` path and the on-disk files
the tests wrote. These tests do not import Go packages, do not call
internal Search / SearchForPath helpers, and do not use ``membundle validate``
/ ``membundle create`` / ``membundle show`` to judge results.
"""

from __future__ import annotations

import os

import pytest

from _harness import workspace
from F01_helpers import combined_report, split_yaml_frontmatter
from F03_helpers import (
    assert_snapshot_helper_sees_write,
    markdown_link,
    render_concept_markdown,
    snapshot_tree,
    unique_tokens,
    write_bundle,
)
from F04_helpers import (
    SAMPLE_BARE_GO,
    SAMPLE_BIG_CAP,
    SAMPLE_FILE,
    SAMPLE_HIGH_ID,
    SAMPLE_LOW_ID,
    SAMPLE_NESTED_DIR,
    SAMPLE_PREFIX_DIR,
    SAMPLE_SHARED_TITLE,
    SAMPLE_SHARED_WORD,
    SAMPLE_SIBLING_DIR,
    SAMPLE_SIBLING_FILE,
    SAMPLE_TERM,
    SAMPLE_TERM_TITLE,
    SAMPLE_TOP_DIR,
    abs_workspace_path,
    assert_human_concept_identity_after_badge,
    assert_human_path_hit_reports,
    assert_human_zero_hit_miss_statement,
    assert_identifiable_human_hits,
    assert_folded_declared_governance,
    assert_lowercase_effective_governance,
    assert_matched_keyword_fields,
    assert_path_hit_reports,
    assert_single_effective_governance,
    code_ref_match_reported,
    compact_token,
    field_tokens_do_not_start_with,
    deeper_convention_omit_identity,
    earlier_segment_glob_probe,
    generated_deep_directory_prefix_probe,
    prefix_sharing_convention_omit_identity,
    prefix_sharing_human_omit_identity,
    prefix_sharing_tool_omit_identity,
    generated_filesystem_absolute_relative_probe,
    concept_identity_order,
    hit_field,
    hit_identities,
    hit_list,
    identity_in_records,
    longer_filesystem_absolute_caller,
    inverted_convention_identities,
    inverted_governance_identities,
    inverted_nested_convention_identities,
    inverted_tool_path_governance_identities,
    matched_field_tokens,
    mcp_membundle_search,
    mcp_search,
    numbered_identities,
    other_non_markdown_filename,
    one_segment_recursive_suffix_paths,
    partial_segment_glob_probe,
    path_tokens_for_search,
    plant_escaping_markdown_symlink,
    plant_keyword_score_tie_later_first,
    plant_same_governance_path_query_tie_later_first,
    plant_same_governance_path_tie_later_first,
    plant_markdown_file,
    queries_with_term_starting_at_position_1000,
    query_cut_inside_one_term,
    term_character_outside_fixture_prefixes,
    record_for_identity,
    record_has_json_number,
    require_call_leaves_bundle_bytes_unchanged,
    require_core_fields,
    require_planted_code_refs_is_sole_copy,
    require_planted_recognized_field_is_sole_copy,
    require_planted_resource_is_sole_copy,
    require_planted_unknown_frontmatter,
    require_cap_above_100_returns_at_most_100,
    require_identity_order,
    require_repeated_human_search_identity_order,
    require_repeated_search_identity_order,
    require_mcp_empty_success,
    require_mcp_search_success,
    require_mcp_search_load_failure,
    require_escaping_directory_symlink_not_walked,
    require_search_entry_load_refusal,
    require_search_load_error,
    require_search_load_failure,
    require_human_identity_absent,
    require_human_identity_prefix,
    require_human_identity_present,
    require_human_ranked_prefix,
    require_human_ranked_hits,
    require_search_structured_success,
    require_search_success,
    require_search_tool_title_hit,
    require_search_tool_title_omitted,
    require_search_usage_failure,
    require_unmatched_path_filter_is_miss,
    require_zero_hits_success,
    run_search,
    search_concept_spec,
    non_ascii_term_splitter,
    other_case_token_with_non_ascii_letter,
    other_letter_case,
    query_joined_on_non_ascii_letter,
    require_non_ascii_letters_then_ascii_tail,
    space_free_joined_terms,
    term_splitter_outside_closed_set,
    unique_compact,
    unknown_frontmatter_scalar,
    unsuffixed_recursive_directory_probe,
    write_concepts_later_first,
    write_equal_score_title_bundle,
)


def _kb() -> str:
    return unique_tokens("kb")[0]


def _filler() -> tuple[str, str, str]:
    return unique_tokens("typ", "dsc", "bod")


# ---------------------------------------------------------------------------
# A. Keyword hit includes identity/type/title/description; omits non-matches
# ---------------------------------------------------------------------------


def test_keyword_hit_includes_identity_type_title_description_and_omits_non_match():
    """Named-bundle keyword search returns the titled hit and omits a non-match."""
    with workspace() as ws:
        early, late, typ, early_title, late_title, early_desc, late_desc, body, obody = unique_tokens(
            "ea", "la", "typ", "etl", "ltl", "edc", "ldc", "bod", "obod"
        )
        early_id = f"a{early}"
        late_id = f"z{late}"
        assert early_id < late_id
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    early_id,
                    concept_type=typ,
                    title=early_title,
                    description=early_desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    late_id,
                    concept_type=typ,
                    title=late_title,
                    description=late_desc,
                    body=f"{obody}\n",
                    governance="CONTEXT",
                ),
            ],
        )
        later = require_search_structured_success(
            run_search(ws, late_title, rel, structured=True)
        )
        assert identity_in_records(later, late_id), (
            f"structured search omitted the later title {late_id!r}: {later!r}"
        )
        assert not identity_in_records(later, early_id), (
            f"structured search returned the other concept {early_id!r}: {later!r}"
        )
        require_core_fields(
            record_for_identity(later, late_id), late_id, typ, late_title, late_desc
        )
        earlier = require_search_structured_success(
            run_search(ws, early_title, rel, structured=True)
        )
        assert identity_in_records(earlier, early_id)
        assert not identity_in_records(earlier, late_id)
        require_core_fields(
            record_for_identity(earlier, early_id),
            early_id,
            typ,
            early_title,
            early_desc,
        )
        human = require_search_success(run_search(ws, late_title, rel))
        assert_identifiable_human_hits(
            human,
            [("context", (late_id, late_title, late_desc))],
        )
        print(f"keyword hit later={late_id!r} earlier={early_id!r}", flush=True)


def test_unknown_frontmatter_field_remains_a_title_hit():
    """A key the document does not name still leaves a title hit.

    Recognized concept fields are type and the named optional fields. One
    concept carries a different key and a title that is the query. Structured
    search on the command still returns that concept and reports the match
    on title. The same bundle is then searched through membundle_search, which
    loads that file itself: the concept remains a title hit. The concept
    written first has no such key and a different title, so it stays omitted
    on both entries. Search does not rewrite the concept: the key is not
    required to appear on the hit.
    """
    with workspace() as ws:
        early, late, typ, title, other_title, desc, body, obody = unique_tokens(
            "ea", "la", "typ", "ttl", "ott", "dsc", "bod", "obd"
        )
        early_id = f"a{early}"
        late_id = f"z{late}"
        assert early_id < late_id
        extra_key, extra_value = unknown_frontmatter_scalar(
            early_id,
            late_id,
            typ,
            title,
            other_title,
            desc,
            body,
            obody,
        )
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    early_id,
                    concept_type=typ,
                    title=other_title,
                    description=desc,
                    body=f"{obody}\n",
                ),
                search_concept_spec(
                    late_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    extra={extra_key: extra_value},
                ),
            ],
        )
        require_planted_unknown_frontmatter(
            root / f"{late_id}.md", extra_key, extra_value
        )
        control_mapping, _control_body = split_yaml_frontmatter(
            (root / f"{early_id}.md").read_text(encoding="utf-8")
        )
        control_keys = [
            line.split(":", 1)[0].strip()
            for line in control_mapping.splitlines()
            if line.strip() and not line.startswith((" ", "\t")) and ":" in line
        ]
        assert extra_key not in control_keys, (
            f"control concept also carries unrecognized key {extra_key!r}"
        )
        hits = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert identity_in_records(hits, late_id), (
            f"title search omitted the concept that carries unrecognized "
            f"frontmatter key {extra_key!r}: {hits!r}"
        )
        assert not identity_in_records(hits, early_id), (
            f"title search returned the concept whose title is not the query: "
            f"{early_id!r}"
        )
        rec = record_for_identity(hits, late_id)
        require_core_fields(rec, late_id, typ, title, desc)
        assert_matched_keyword_fields(
            rec,
            [
                late_id,
                early_id,
                typ,
                title,
                other_title,
                desc,
                body,
                obody,
                extra_key,
                extra_value,
            ],
            ["title"],
        )
        print(
            f"unknown frontmatter {extra_key!r} kept title hit {late_id!r}",
            flush=True,
        )
        require_planted_unknown_frontmatter(
            root / f"{late_id}.md", extra_key, extra_value
        )
        tool_hits = require_mcp_search_success(
            mcp_search(ws, query=title, bundle=rel)
        )
        assert identity_in_records(tool_hits, late_id), (
            "membundle_search title search omitted the concept that carries "
            f"unrecognized frontmatter key {extra_key!r}: {tool_hits!r}"
        )
        assert not identity_in_records(tool_hits, early_id), (
            "membundle_search title search returned the concept whose title is "
            f"not the query: {early_id!r}"
        )
        tool_rec = record_for_identity(tool_hits, late_id)
        require_core_fields(tool_rec, late_id, typ, title, desc)
        assert_matched_keyword_fields(
            tool_rec,
            [
                late_id,
                early_id,
                typ,
                title,
                other_title,
                desc,
                body,
                obody,
                extra_key,
                extra_value,
            ],
            ["title"],
        )
        print(
            f"membundle_search unknown frontmatter {extra_key!r} kept title hit "
            f"{late_id!r}",
            flush=True,
        )


def test_keyword_title_hit_runtime_twin():
    """A runtime-unique title hit is not the only fixture that matches."""
    with workspace() as ws:
        early, late, typ, title, desc, body, otitle = unique_tokens(
            "ea", "la", "ttyp", "tttl", "tdsc", "tbod", "tottl"
        )
        other = f"a{early}"
        ident = f"z{late}"
        assert other < ident
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    other,
                    concept_type=typ,
                    title=otitle,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert identity_in_records(records, ident)
        assert not identity_in_records(records, other)
        print(f"runtime twin hit={ident!r}", flush=True)


def test_human_mode_is_not_replaced_by_structured_only():
    """Default output prefixes the hit with the lowercase governance badge."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "hid", "htyp", "httl", "hdsc", "hbod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    governance="CONTEXT",
                )
            ],
        )
        report = require_search_success(run_search(ws, title, rel))
        assert_identifiable_human_hits(
            report, [("context", (ident, title, desc))]
        )
        print("human mode presented an identifiable hit", flush=True)


# ---------------------------------------------------------------------------
# B. Term split and prefix match, not mid-token substring, on all five fields
# ---------------------------------------------------------------------------


def test_non_letter_digit_characters_split_terms():
    """Non-letter, non-digit characters split terms.

    Comma, hyphen, period, underscore, and slash split. One further ASCII
    mark that is not a letter, not a digit, and not one of those joiners
    or a space joins the same two pieces. A non-ASCII character that is
    not a letter and not a digit joins those same title prefixes, on the
    command line and on the search tool. Each piece is a prefix of its
    own title and of no other concept, so a search that keeps the joiner
    inside one term hits neither concept.
    """
    with workspace() as ws:
        piece1, piece2, suffix1, suffix2, unused = unique_compact(
            "p1", "p2", "s1", "s2", "u"
        )
        title1 = piece1 + suffix1
        title2 = piece2 + suffix2
        id1, id2, idu, typ, desc, body = unique_tokens(
            "a", "b", "c", "typ", "dsc", "bod"
        )
        # Each piece belongs to one title. The joiner is not in either title,
        # so the unsplit query is not a prefix of, or equal to, either title.
        assert piece1 not in title2 and piece2 not in title1
        assert piece1 not in unused and piece2 not in unused
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    id1, concept_type=typ, title=title1, description=desc, body=f"{body}\n"
                ),
                search_concept_spec(
                    id2, concept_type=typ, title=title2, description=desc, body=f"{body}\n"
                ),
                search_concept_spec(
                    idu,
                    concept_type=typ,
                    title=unused,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        already = (",", "-", ".", "_", "/")
        extra = term_splitter_outside_closed_set()
        assert len(extra) == 1
        assert not extra.isalnum()
        assert not extra.isspace()
        assert extra not in already and extra != " "
        for splitter in (*already, extra):
            query = f"{piece1}{splitter}{piece2}"
            assert splitter not in title1 and splitter not in title2
            assert title1 not in query and title2 not in query
            assert title1.startswith(piece1) and title2.startswith(piece2)
            records = require_search_structured_success(
                run_search(ws, query, rel, structured=True)
            )
            found = {
                ident
                for ident in (id1, id2, idu)
                if identity_in_records(records, ident)
            }
            print(f"split {splitter!r} found={found!r}", flush=True)
            assert found == {id1, id2}, (
                f"query {query!r} should hit only the two prefixed titles; found={found!r}"
            )
        mark = non_ascii_term_splitter()
        assert len(mark) == 1
        assert not mark.isascii()
        assert not mark.isalpha()
        assert not mark.isdigit()
        assert not mark.isalnum()
        assert not mark.isspace()
        assert mark not in already and mark != extra and mark != " "
        query = f"{piece1}{mark}{piece2}"
        assert mark not in title1 and mark not in title2
        assert title1 not in query and title2 not in query
        assert title1.startswith(piece1) and title2.startswith(piece2)

        def _prefixed_hits(records: list, surface: str) -> None:
            found = {
                ident
                for ident in (id1, id2, idu)
                if identity_in_records(records, ident)
            }
            print(
                f"non-ascii split {surface} mark={mark!r} found={found!r}",
                flush=True,
            )
            assert found == {id1, id2}, (
                f"{surface} query {query!r} should hit only the two "
                f"prefixed titles; found={found!r}"
            )

        _prefixed_hits(
            require_search_structured_success(
                run_search(ws, query, rel, structured=True)
            ),
            "command line",
        )
        _prefixed_hits(
            require_mcp_search_success(mcp_search(ws, query=query, bundle=rel)),
            "search tool",
        )


def test_digit_is_not_a_term_splitter():
    """A digit stays inside the term; pieces of a digit split do not hit.

    The command line and the search tool both search one title token that
    has a digit between two pieces. That concept is required. Concepts
    whose titles are only the piece before the digit, or only the piece
    after it, are omitted. Splitting the digit on the tool yields those
    side titles.
    """
    with workspace() as ws:
        left, right, extra, unused = unique_compact("dl", "dr", "dx", "du")
        query = f"{left}7{right}"
        title = f"{left}7{right}{extra}"
        _hit, _left, _right, _unused, typ, desc, body = unique_tokens(
            "hit", "lft", "rgt", "unu", "typ", "dsc", "bod"
        )
        id_left = f"a{_left}"
        id_right = f"b{_right}"
        id_unused = f"c{_unused}"
        id_hit = f"z{_hit}"
        assert id_hit > id_left
        assert title not in query
        assert title.startswith(query)
        assert left in query and right in query
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    id_left, concept_type=typ, title=left, description=desc, body=f"{body}\n"
                ),
                search_concept_spec(
                    id_right,
                    concept_type=typ,
                    title=right,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    id_unused,
                    concept_type=typ,
                    title=unused,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    id_hit, concept_type=typ, title=title, description=desc, body=f"{body}\n"
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, query, rel, structured=True)
        )
        found = {
            ident
            for ident in (id_hit, id_left, id_right, id_unused)
            if identity_in_records(records, ident)
        }
        print(f"digit-kept query={query!r} found={found!r}", flush=True)
        assert found == {id_hit}, (
            f"a digit must stay inside the term; query {query!r} found={found!r}"
        )
        tool_records = require_mcp_search_success(
            mcp_search(ws, query=query, bundle=rel)
        )
        tool_found = {
            ident
            for ident in (id_hit, id_left, id_right, id_unused)
            if identity_in_records(tool_records, ident)
        }
        print(
            f"digit-kept search tool query={query!r} found={tool_found!r}",
            flush=True,
        )
        assert tool_found == {id_hit}, (
            "a digit must stay inside the term on the search tool; "
            f"query {query!r} found={tool_found!r}"
        )


def test_term_matches_equal_or_prefix_token_not_mid_token_substring():
    """Query matches a prefix token and does not match a mid-token substring."""
    with workspace() as ws:
        needle = compact_token("n")
        prefix_token = f"{needle}aaa"
        mid_token = f"zzz{needle}zzz"
        id_pre, id_mid, typ, desc, body = unique_tokens(
            "pre", "mid", "typ", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    id_pre,
                    concept_type=typ,
                    title=prefix_token,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    id_mid,
                    concept_type=typ,
                    title=mid_token,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        prefix_hits = require_search_structured_success(
            run_search(ws, needle, rel, structured=True)
        )
        assert identity_in_records(prefix_hits, id_pre), (
            f"prefix token {prefix_token!r} did not hit query {needle!r}"
        )
        assert not identity_in_records(prefix_hits, id_mid), (
            f"mid-token title {mid_token!r} hit query {needle!r}"
        )
        iddle = "iddle"
        middlerun = "middlerun"
        id_mid2, id_ok = unique_tokens("m2", "ok")
        rel2 = _kb()
        write_bundle(
            ws,
            rel2,
            [
                search_concept_spec(
                    id_mid2,
                    concept_type=typ,
                    title=middlerun,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    id_ok,
                    concept_type=typ,
                    title="prefixrun",
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        miss = require_search_structured_success(
            run_search(ws, iddle, rel2, structured=True)
        )
        assert not identity_in_records(miss, id_mid2), (
            f"iddle matched middlerun identity {id_mid2!r}"
        )
        pref = require_search_structured_success(
            run_search(ws, "pref", rel2, structured=True)
        )
        assert identity_in_records(pref, id_ok)
        print("prefix vs mid-token title contrast ok", flush=True)


def test_term_prefix_and_mid_token_rule_on_all_five_fields():
    """Equals-or-prefix, not mid-token substring, on title/tags/description/id/body.

    Title, tags, description, and body also carry a later token that is
    longer than the term and only starts with it. That field text does
    not itself start with the term.
    """
    with workspace() as ws:
        needle = compact_token("n")
        prefix_token = f"{needle}run"
        mid_token = f"zz{needle}zz"
        lead = compact_token("ld")
        # Later token, not the whole field: an earlier token, then one
        # token that is longer than the term and only starts with it.
        later_field = f"{lead} {prefix_token}"
        assert prefix_token.startswith(needle) and len(prefix_token) > len(needle)
        assert not lead.lower().startswith(needle.lower())
        assert needle.lower() not in lead.lower()
        assert not later_field.lower().startswith(needle.lower())
        head, tail = later_field.split(" ")
        assert head == lead and tail == prefix_token
        assert tail.lower() != needle.lower()
        typ, desc_f, body_f = _filler()
        title_f, tag_f = unique_compact("tf", "tg")
        for filler in (title_f, tag_f, typ, desc_f, body_f):
            assert not filler.lower().startswith(needle.lower())
            assert needle.lower() not in filler.lower()
        rel = _kb()

        def _spec(ident: str, **fields: object):
            return search_concept_spec(
                ident,
                concept_type=typ,
                title=str(fields.get("title", title_f)),
                description=str(fields.get("description", desc_f)),
                body=str(fields.get("body", f"{body_f}\n")),
                tags=list(fields["tags"]) if "tags" in fields else None,
            )

        id_title, id_tags, id_desc, id_body = unique_tokens(
            "ttl", "tag", "dsc", "bod"
        )
        id_ident_pre = f"architecture/{prefix_token}"
        id_ident_mid = f"architecture/{mid_token}x"
        id_title_mid, id_tags_mid, id_desc_mid, id_body_mid = unique_tokens(
            "ttlm", "tagm", "dscm", "bodm"
        )
        id_title_later, id_tags_later, id_desc_later, id_body_later = unique_tokens(
            "ttll", "tagl", "dscl", "bodl"
        )
        for ident in (
            id_title_later,
            id_tags_later,
            id_desc_later,
            id_body_later,
        ):
            assert needle.lower() not in ident.lower()
        write_bundle(
            ws,
            rel,
            [
                _spec(id_title, title=prefix_token),
                _spec(id_title_mid, title=mid_token),
                _spec(id_title_later, title=later_field),
                _spec(id_tags, tags=[prefix_token]),
                _spec(id_tags_mid, tags=[mid_token]),
                _spec(id_tags_later, tags=[later_field]),
                _spec(id_desc, description=prefix_token),
                _spec(id_desc_mid, description=mid_token),
                _spec(id_desc_later, description=later_field),
                _spec(id_ident_pre),
                _spec(id_ident_mid),
                _spec(id_body, body=f"{prefix_token}\n"),
                _spec(id_body_mid, body=f"{mid_token}\n"),
                _spec(id_body_later, body=f"{later_field}\n"),
            ],
        )
        hits = require_search_structured_success(
            run_search(ws, needle, rel, structured=True)
        )
        expected = {id_title, id_tags, id_desc, id_ident_pre, id_body}
        forbidden = {id_title_mid, id_tags_mid, id_desc_mid, id_ident_mid, id_body_mid}
        for ident in expected:
            assert identity_in_records(hits, ident), (
                f"five-field prefix miss for {ident!r} query={needle!r}"
            )
        for ident in forbidden:
            assert not identity_in_records(hits, ident), (
                f"five-field mid-token hit for {ident!r} query={needle!r}"
            )
        # Nine hits: five whole-field prefix arms plus these four. Default
        # cap is 10, so a real match is not truncated away.
        later_cases = (
            (
                id_title_later,
                "title",
                [later_field, id_title_later, typ, desc_f, body_f, lead, prefix_token],
            ),
            (
                id_tags_later,
                "tags",
                [later_field, id_tags_later, typ, title_f, desc_f, body_f, lead, prefix_token],
            ),
            (
                id_desc_later,
                "description",
                [later_field, id_desc_later, typ, title_f, body_f, lead, prefix_token],
            ),
            (
                id_body_later,
                "body",
                [later_field, id_body_later, typ, title_f, desc_f, lead, prefix_token],
            ),
        )
        assert len(expected) + len(later_cases) <= 10
        for ident, field, strip in later_cases:
            assert identity_in_records(hits, ident), (
                f"later prefix token missed on {field} for {ident!r} "
                f"query={needle!r} field={later_field!r}"
            )
            rec = record_for_identity(hits, ident)
            assert_matched_keyword_fields(rec, strip, [field])
        print("five-field prefix/mid-token ok", flush=True)


def test_keyword_match_is_case_insensitive():
    """A capital stays inside the title token, and the other letter case still matches.

    Same-case whole-token prefix hits, and an interior slice misses. On the
    search command and on the search tool, a title token that equals the
    term, and a longer title token that starts with the term, still hit
    when the query's letter case differs from the stored token. A concept
    that does not contain the token stays absent.

    The same two token shapes, on both public entries, also hit when that
    differing letter case is the only copy of the term in each scored
    field (title, tags, description, concept identity, and body). The
    letters whose case differs include a non-ASCII letter.
    """
    with workspace() as ws:
        tail = compact_token("s")
        title = f"AbC{tail}"
        prefix_query = "AbC"
        interior = f"C{tail}"
        assert title.startswith(prefix_query)
        assert title.endswith(interior)
        assert prefix_query != interior
        early, late, typ, desc, body, otitle = unique_tokens(
            "ea", "la", "typ", "dsc", "bod", "ott"
        )
        other = f"a{early}"
        ident = f"z{late}"
        assert other < ident
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    other,
                    concept_type=typ,
                    title=otitle,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, prefix_query, rel, structured=True)
        )
        assert identity_in_records(records, ident), (
            f"prefix {prefix_query!r} of {title!r} missed the concept"
        )
        assert not identity_in_records(records, other), (
            f"prefix query returned the concept that contains neither: {other!r}"
        )
        interior_hits = require_search_structured_success(
            run_search(ws, interior, rel, structured=True)
        )
        assert not identity_in_records(interior_hits, ident), (
            f"slice {interior!r} after an interior capital still hit {title!r}"
        )
        assert not identity_in_records(interior_hits, other)
        print(f"capital stayed inside title={title!r}", flush=True)

    # Opposite letter case, on the command and on the search tool.
    # The capital-stay arm above keeps the query in the stored token's case.
    with workspace() as ws:
        (
            equal_base,
            prefix_base,
            prefix_tail,
            absent_title,
            typ,
            desc,
            body,
            equal_id,
            prefix_id,
            absent_id,
        ) = unique_compact(
            "eq", "px", "tl", "ab", "typ", "dsc", "bod", "ie", "ip", "ia"
        )
        equal_stored = other_letter_case(equal_base)
        equal_query = equal_base
        prefix_stored = other_letter_case(prefix_base) + prefix_tail
        prefix_query = prefix_base
        assert equal_stored != equal_query
        assert equal_stored.casefold() == equal_query.casefold()
        assert prefix_stored.casefold().startswith(prefix_query.casefold())
        assert prefix_stored.casefold() != prefix_query.casefold()
        assert prefix_stored[: len(prefix_query)] != prefix_query
        assert equal_stored.isalnum() and prefix_stored.isalnum()

        def _stored_token_rejects(token: str, term: str) -> None:
            folded = token.casefold()
            needle = term.casefold()
            assert folded != needle and not folded.startswith(needle), (
                f"fixture token {token!r} already matches term {term!r}"
            )

        for term in (equal_query, prefix_query):
            _stored_token_rejects(desc, term)
            _stored_token_rejects(body, term)
            _stored_token_rejects(absent_title, term)
            _stored_token_rejects(absent_id, term)
        _stored_token_rejects(equal_stored, prefix_query)
        _stored_token_rejects(equal_id, prefix_query)
        _stored_token_rejects(equal_id, equal_query)
        _stored_token_rejects(prefix_stored, equal_query)
        _stored_token_rejects(prefix_id, equal_query)
        _stored_token_rejects(prefix_id, prefix_query)
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    equal_id,
                    concept_type=typ,
                    title=equal_stored,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    prefix_id,
                    concept_type=typ,
                    title=prefix_stored,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    absent_id,
                    concept_type=typ,
                    title=absent_title,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        arms = (
            ("equals", equal_query, equal_id, (prefix_id, absent_id)),
            ("starts-with", prefix_query, prefix_id, (equal_id, absent_id)),
        )
        for shape, query, wanted, missing in arms:
            command_hits = require_search_structured_success(
                run_search(ws, query, rel, structured=True)
            )
            tool_hits = require_mcp_search_success(
                mcp_search(ws, query=query, bundle=rel)
            )
            for entry, hits in (("command", command_hits), ("tool", tool_hits)):
                assert identity_in_records(hits, wanted), (
                    f"{entry} {shape} query whose letter case differs from "
                    f"the stored title token missed {wanted!r} query={query!r}"
                )
                for ident in missing:
                    assert not identity_in_records(hits, ident), (
                        f"{entry} {shape} query returned {ident!r}, which "
                        f"does not contain that token; query={query!r}"
                    )
        print(
            "opposite letter case matched equals and prefix on command and tool",
            flush=True,
        )

    # Closed ASCII title equals and title prefix arms stay above.
    # Each scored field, both token shapes, both public entries. The
    # letter whose case differs includes a non-ASCII letter, and that
    # token is the only copy of the term in the field under test.
    with workspace() as ws:
        fields = ("title", "tags", "description", "id", "body")
        piece_names = (
            [f"eq{index}" for index in range(len(fields))]
            + [f"px{index}" for index in range(len(fields))]
            + [f"tl{index}" for index in range(len(fields))]
            + ["typ", "ftl", "fdc", "fbd", "abs", "abt", "dir"]
            + [f"id{index}" for index in range(len(fields) * 2 - 2)]
        )
        pieces = dict(zip(piece_names, unique_compact(*piece_names), strict=True))
        typ = pieces["typ"]
        filler_title = pieces["ftl"]
        filler_desc = pieces["fdc"]
        filler_body = pieces["fbd"]
        absent_id = pieces["abs"]
        absent_title = pieces["abt"]
        id_dir = pieces["dir"]
        plain_ids = iter(
            pieces[f"id{index}"] for index in range(len(fields) * 2 - 2)
        )
        arms: list[tuple[str, str, str, str, str]] = []
        for index, field in enumerate(fields):
            for shape, base_name, tail_name in (
                ("equals", f"eq{index}", None),
                ("starts-with", f"px{index}", f"tl{index}"),
            ):
                query, stored = other_case_token_with_non_ascii_letter(
                    pieces[base_name],
                    prefix_tail=pieces[tail_name] if tail_name else None,
                )
                if field == "id":
                    identity = f"{id_dir}/{stored}"
                else:
                    identity = next(plain_ids)
                arms.append((field, shape, query, stored, identity))

        def _scored_text(field: str, identity: str, stored: str, name: str) -> str:
            if name == field:
                return identity if field == "id" else stored
            if name == "title":
                return filler_title
            if name == "description":
                return filler_desc
            if name == "body":
                return filler_body
            if name == "id":
                return identity
            if name == "tags":
                return ""
            raise AssertionError(f"unknown scored field {name!r}")

        specs = []
        for field, shape, query, stored, identity in arms:
            folded_query = query.casefold()
            for name in ("title", "tags", "description", "id", "body"):
                text = _scored_text(field, identity, stored, name)
                if name == field:
                    assert folded_query in text.casefold(), (
                        f"{field} {shape} did not store the term only in "
                        f"that field: query={query!r} text={text!r}"
                    )
                else:
                    assert folded_query not in text.casefold(), (
                        f"{field} {shape} also stored the term in {name}: "
                        f"query={query!r} text={text!r}"
                    )
            assert folded_query not in typ.casefold()
            for other_field, other_shape, _other_query, other_stored, other_identity in arms:
                if other_field == field and other_shape == shape:
                    assert (
                        other_stored.casefold() == folded_query
                        or other_stored.casefold().startswith(folded_query)
                    )
                    continue
                assert not (
                    other_stored.casefold() == folded_query
                    or other_stored.casefold().startswith(folded_query)
                ), (
                    f"{other_field} {other_shape} token also matches "
                    f"{field} {shape} query {query!r}"
                )
                assert folded_query not in other_identity.casefold()
            for untouched in (
                absent_title,
                absent_id,
                filler_title,
                filler_desc,
                filler_body,
                typ,
                id_dir,
            ):
                assert folded_query not in untouched.casefold()
            specs.append(
                search_concept_spec(
                    identity,
                    concept_type=typ,
                    title=stored if field == "title" else filler_title,
                    description=stored if field == "description" else filler_desc,
                    body=(
                        f"{stored}\n" if field == "body" else f"{filler_body}\n"
                    ),
                    tags=[stored] if field == "tags" else None,
                )
            )
        specs.append(
            search_concept_spec(
                absent_id,
                concept_type=typ,
                title=absent_title,
                description=filler_desc,
                body=f"{filler_body}\n",
            )
        )
        rel = _kb()
        write_bundle(ws, rel, specs)
        for field, shape, query, _stored, identity in arms:
            command_hits = require_search_structured_success(
                run_search(ws, query, rel, structured=True)
            )
            tool_hits = require_mcp_search_success(
                mcp_search(ws, query=query, bundle=rel)
            )
            for entry, hits in (("command", command_hits), ("tool", tool_hits)):
                assert identity_in_records(hits, identity), (
                    f"{entry} {field} {shape} query whose letter case differs "
                    f"from the stored token, including a non-ASCII letter, "
                    f"missed {identity!r} query={query!r}"
                )
                assert not identity_in_records(hits, absent_id), (
                    f"{entry} {field} {shape} returned {absent_id!r}, which "
                    f"does not contain that token; query={query!r}"
                )
                for other_field, other_shape, _other_query, _other_stored, other_identity in arms:
                    if other_identity == identity:
                        continue
                    assert not identity_in_records(hits, other_identity), (
                        f"{entry} {field} {shape} also returned "
                        f"{other_identity!r} ({other_field} {other_shape}), "
                        f"which does not contain this token; query={query!r}"
                    )
        print(
            "opposite letter case including a non-ASCII letter matched "
            "equals and prefix on every scored field, on command and tool",
            flush=True,
        )


# ---------------------------------------------------------------------------
# C. Each of the five keyword fields can produce a hit.
#    code_refs is not one, concept type is not one, and resource is not one.
#    generated, verified, status, stale_after, and sources are not ones either.
# ---------------------------------------------------------------------------


def test_title_tags_description_id_and_body_each_produce_a_keyword_hit():
    """Term T in exactly one of title/tags/description/id/body still hits."""
    with workspace() as ws:
        term = compact_token("term")
        typ, desc_f, body_f, title_f, tag_f = unique_tokens(
            "typ", "dsc", "bod", "ttl", "tg"
        )
        id_title, id_tags, id_desc, id_body, id_none = unique_tokens(
            "it", "ig", "idc", "ib", "ino"
        )
        id_ident = f"architecture/{term}"
        none_title, none_desc, none_body = unique_tokens("nt", "nd", "nb")
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    id_title,
                    concept_type=typ,
                    title=term,
                    description=desc_f,
                    body=f"{body_f}\n",
                ),
                search_concept_spec(
                    id_tags,
                    concept_type=typ,
                    title=title_f,
                    description=desc_f,
                    body=f"{body_f}\n",
                    tags=[term],
                ),
                search_concept_spec(
                    id_desc,
                    concept_type=typ,
                    title=title_f,
                    description=term,
                    body=f"{body_f}\n",
                ),
                search_concept_spec(
                    id_ident,
                    concept_type=typ,
                    title=title_f,
                    description=desc_f,
                    body=f"{body_f}\n",
                ),
                search_concept_spec(
                    id_body,
                    concept_type=typ,
                    title=title_f,
                    description=desc_f,
                    body=f"{term}\n",
                ),
                search_concept_spec(
                    id_none,
                    concept_type=typ,
                    title=none_title,
                    description=none_desc,
                    body=f"{none_body}\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        for ident in (id_title, id_tags, id_desc, id_ident, id_body):
            assert identity_in_records(records, ident), (
                f"field-only concept {ident!r} omitted for term {term!r}"
            )
        assert not identity_in_records(records, id_none), (
            f"concept with the term in no scored field was returned: {id_none!r}"
        )
        print("five keyword fields each hit", flush=True)


def test_code_refs_alone_is_not_a_keyword_hit():
    """A term that lives only in code_refs is omitted from keyword search.

    The search command omits that concept. A keyword query for the same
    concept's own title still returns it, so dropping the file at load
    time is not a pass. A path query that matches the stored code_refs
    shows the path match. That path query is not the title query.
    """
    with workspace() as ws:
        term = compact_token("cref")
        decoy, only_refs, scored, typ, decoy_title, refs_title, desc, body = unique_tokens(
            "de", "cr", "sc", "typ", "dtt", "rtt", "dsc", "bod"
        )
        rel = _kb()
        path = f"pkg/{term}/file.go"
        other_path = f"pkg/{compact_token('o')}/file.go"
        if refs_title.lower() in path.lower() or term.lower() in refs_title.lower():
            raise AssertionError(
                "code_refs title query overlaps the planted path term"
            )
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    decoy,
                    concept_type=typ,
                    title=decoy_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[other_path],
                ),
                search_concept_spec(
                    only_refs,
                    concept_type=typ,
                    title=refs_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                ),
                search_concept_spec(
                    scored,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[other_path],
                ),
            ],
        )
        require_planted_code_refs_is_sole_copy(
            root / f"{only_refs}.md", term, path
        )
        keyword = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        assert identity_in_records(keyword, scored), (
            f"keyword search omitted the concept whose title is the term {term!r}"
        )
        assert not identity_in_records(keyword, only_refs), (
            f"code_refs-only term {term!r} produced a keyword hit"
        )
        assert not identity_in_records(keyword, decoy)
        by_title = require_search_structured_success(
            run_search(ws, refs_title, rel, structured=True)
        )
        assert identity_in_records(by_title, only_refs), (
            f"keyword search omitted the concept whose title is {refs_title!r}; "
            "the code_refs-only concept was not loaded"
        )
        assert not identity_in_records(by_title, scored), (
            f"title query {refs_title!r} returned the concept whose title is the term"
        )
        assert not identity_in_records(by_title, decoy), (
            f"title query {refs_title!r} returned a concept that does not contain it"
        )
        path_hits = require_search_structured_success(
            run_search(ws, None, rel, for_path=path, structured=True)
        )
        assert identity_in_records(path_hits, only_refs), (
            f"path search did not hit code_refs-only concept {only_refs!r}"
        )
        assert not identity_in_records(path_hits, decoy), (
            f"path search returned a concept whose code_refs do not cover {path!r}"
        )
        print("code_refs is not a keyword field", flush=True)


def _planted_type_is_the_only_copy_of_term(path, term: str) -> None:
    """The file the test wrote keeps *term* on the type line and nowhere else.

    This checks the fixture, not the product. A leak into title, tags,
    description, the filename (concept identity), or the body would make
    a correct keyword search return the concept.
    """
    text = path.read_text(encoding="utf-8")
    mapping, body = split_yaml_frontmatter(text)
    needle = term.lower()
    if needle in path.name.lower():
        raise AssertionError(
            f"planted identity filename contains the type term {term!r}: {path.name!r}"
        )
    if needle in body.lower():
        raise AssertionError(
            f"planted body contains the type term {term!r}: {body!r}"
        )
    type_lines = [line for line in mapping.splitlines() if line.startswith("type:")]
    if len(type_lines) != 1:
        raise AssertionError(
            f"planted concept does not have exactly one type line: {mapping!r}"
        )
    type_value = type_lines[0].split(":", 1)[1].strip().strip("'\"")
    if type_value != term:
        raise AssertionError(
            f"planted type {type_value!r} is not the query term {term!r}"
        )
    for line in mapping.splitlines():
        if line.startswith("type:"):
            continue
        if needle in line.lower():
            raise AssertionError(
                f"planted frontmatter other than type contains {term!r}: {line!r}"
            )


def test_concept_type_alone_is_not_a_keyword_hit():
    """A term that lives only in the concept type is omitted.

    Title, tags, description, identity, and body of that concept do not
    contain the term. A different concept whose title is the term is
    returned, so an empty result is not a pass. Searching the type-only
    concept by its own title still returns it, so dropping the file at
    load time is not a pass either.

    Another concept keeps that same term only in its resource field, not
    in type, code_refs, or governance. Keyword search omits it. Searching
    that concept by its own title still returns it, so dropping the file
    at load time is not a pass.
    """
    with workspace() as ws:
        (
            term,
            own_title,
            decoy_title,
            filler_type,
            desc,
            body,
            tag,
            only_id,
            scored_id,
            decoy_id,
            resource_title,
            resource_id,
        ) = unique_compact(
            "typ",
            "own",
            "dtt",
            "fty",
            "dsc",
            "bod",
            "tag",
            "oid",
            "sid",
            "did",
            "rtl",
            "rid",
        )
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    only_id,
                    concept_type=term,
                    title=own_title,
                    description=desc,
                    body=f"{body}\n",
                    tags=[tag],
                ),
                search_concept_spec(
                    scored_id,
                    concept_type=filler_type,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                    tags=[tag],
                ),
                search_concept_spec(
                    decoy_id,
                    concept_type=filler_type,
                    title=decoy_title,
                    description=desc,
                    body=f"{body}\n",
                    tags=[tag],
                ),
                search_concept_spec(
                    resource_id,
                    concept_type=filler_type,
                    title=resource_title,
                    description=desc,
                    body=f"{body}\n",
                    tags=[tag],
                    resource=term,
                ),
            ],
        )
        _planted_type_is_the_only_copy_of_term(root / f"{only_id}.md", term)
        require_planted_resource_is_sole_copy(root / f"{resource_id}.md", term)
        keyword = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        assert identity_in_records(keyword, scored_id), (
            f"keyword search omitted the concept whose title is the term {term!r}"
        )
        assert not identity_in_records(keyword, only_id), (
            f"concept type alone produced a keyword hit for {term!r}"
        )
        assert not identity_in_records(keyword, resource_id), (
            f"resource alone produced a keyword hit for {term!r}"
        )
        assert not identity_in_records(keyword, decoy_id), (
            f"keyword search returned a concept that does not contain {term!r}"
        )
        by_title = require_search_structured_success(
            run_search(ws, own_title, rel, structured=True)
        )
        assert identity_in_records(by_title, only_id), (
            f"keyword search omitted the concept whose title is {own_title!r}; "
            "the type-only concept was not loaded"
        )
        assert not identity_in_records(by_title, scored_id), (
            f"title query {own_title!r} returned the concept that does not contain it"
        )
        assert not identity_in_records(by_title, decoy_id), (
            f"title query {own_title!r} returned a concept that does not contain it"
        )
        assert not identity_in_records(by_title, resource_id), (
            f"title query {own_title!r} returned the resource-only concept"
        )
        by_resource_title = require_search_structured_success(
            run_search(ws, resource_title, rel, structured=True)
        )
        assert identity_in_records(by_resource_title, resource_id), (
            f"keyword search omitted the concept whose title is {resource_title!r}; "
            "the resource-only concept was not loaded"
        )
        assert not identity_in_records(by_resource_title, only_id), (
            f"title query {resource_title!r} returned the type-only concept"
        )
        assert not identity_in_records(by_resource_title, scored_id), (
            f"title query {resource_title!r} returned the concept that does not contain it"
        )
        assert not identity_in_records(by_resource_title, decoy_id), (
            f"title query {resource_title!r} returned a concept that does not contain it"
        )
        print("concept type is not a keyword field", flush=True)
        print("resource is not a keyword field", flush=True)


def test_unscored_recognized_fields_alone_are_not_keyword_hits():
    """A term that lives only in an unscored recognized field is omitted.

    Keyword scoring uses title, tags, description, concept identity, and
    body. Generated, verified, status, stale_after, and sources are
    recognized and are not in that set. On the search command and on the
    search tool, each of those fields is the only copy of its term, and
    that concept is omitted. Status is planted once as an arbitrary token
    and once as each validator status word, so indexing the field text
    fails either way. Searching the concept by its own title still returns
    it, so dropping the file at load time is not a pass. Governance is not
    planted. Type, code_refs, and resource stay on their own checks.
    """
    with workspace() as ws:
        (
            gen_term,
            ver_term,
            status_term,
            stale_term,
            src_term,
            gen_title,
            ver_title,
            status_title,
            stale_title,
            src_title,
            draft_title,
            stable_title,
            deprecated_title,
            gen_id,
            ver_id,
            status_id,
            stale_id,
            src_id,
            draft_id,
            stable_id,
            deprecated_id,
            scored_id,
            decoy_id,
            decoy_title,
            filler_type,
            desc,
            body,
            tag,
        ) = unique_compact(
            "pgen",
            "pver",
            "psta",
            "pstl",
            "psrc",
            "gttl",
            "vttl",
            "sttl",
            "ltl",
            "rtt2",
            "dttl",
            "bttl",
            "pttl",
            "gid",
            "vid",
            "sid",
            "lid",
            "rid",
            "did",
            "bid",
            "pid",
            "scid",
            "dcid",
            "dttl2",
            "fty",
            "dsc",
            "bod",
            "tag",
        )
        status_words = ("draft", "stable", "deprecated")
        for word in status_words:
            for token in (
                gen_term,
                ver_term,
                status_term,
                stale_term,
                src_term,
                gen_title,
                ver_title,
                status_title,
                stale_title,
                src_title,
                draft_title,
                stable_title,
                deprecated_title,
                gen_id,
                ver_id,
                status_id,
                stale_id,
                src_id,
                draft_id,
                stable_id,
                deprecated_id,
                scored_id,
                decoy_id,
                decoy_title,
                filler_type,
                desc,
                body,
                tag,
            ):
                if word in token.lower() or token.lower() in word:
                    raise AssertionError(
                        f"fixture token {token!r} overlaps status word {word!r}"
                    )
        plants = (
            (
                "generated",
                gen_term,
                gen_id,
                gen_title,
                {"generated": {"by": gen_term, "at": gen_term}},
                {},
            ),
            (
                "verified",
                ver_term,
                ver_id,
                ver_title,
                {},
                {"verified": f"{{ by: {ver_term}, at: {ver_term} }}"},
            ),
            (
                "status",
                status_term,
                status_id,
                status_title,
                {},
                {"status": status_term},
            ),
            (
                "stale_after",
                stale_term,
                stale_id,
                stale_title,
                {},
                {"stale_after": stale_term},
            ),
            (
                "sources",
                src_term,
                src_id,
                src_title,
                {},
                {
                    "sources": (
                        f"\n  - id: {src_term}\n"
                        f"    resource: {src_term}\n"
                        f"    title: {src_term}\n"
                        f"    author: {src_term}"
                    )
                },
            ),
            (
                "status",
                "draft",
                draft_id,
                draft_title,
                {},
                {"status": "draft"},
            ),
            (
                "status",
                "stable",
                stable_id,
                stable_title,
                {},
                {"status": "stable"},
            ),
            (
                "status",
                "deprecated",
                deprecated_id,
                deprecated_title,
                {},
                {"status": "deprecated"},
            ),
        )
        query_terms = [plant[1] for plant in plants]
        rel = _kb()

        def _concept(identity: str, title: str, **kwargs):
            return search_concept_spec(
                identity,
                concept_type=filler_type,
                title=title,
                description=desc,
                body=f"{body}\n",
                tags=[tag],
                **kwargs,
            )

        specs = []
        for _field, _term, identity, title, generated_kwargs, extra in plants:
            specs.append(
                _concept(
                    identity,
                    title,
                    generated=generated_kwargs.get("generated"),
                    extra=extra or None,
                )
            )
        specs.append(_concept(scored_id, " ".join(query_terms)))
        specs.append(_concept(decoy_id, decoy_title))
        root = write_bundle(ws, rel, specs)
        planted_ids = {plant[2] for plant in plants}
        for field, term, identity, _title, _generated, _extra in plants:
            require_planted_recognized_field_is_sole_copy(
                root / f"{identity}.md", field, term
            )
            for other in specs:
                other_id = str(other["identity"])
                if other_id in {identity, scored_id}:
                    continue
                other_text = (root / f"{other_id}.md").read_text(encoding="utf-8")
                if term.lower() in other_text.lower():
                    raise AssertionError(
                        f"{field} term {term!r} also appears in {other_id!r}"
                    )
        scored_text = (root / f"{scored_id}.md").read_text(encoding="utf-8")
        for term in query_terms:
            if term.lower() not in scored_text.lower():
                raise AssertionError(
                    f"scored title is missing the control term {term!r}"
                )
        if planted_ids != {
            gen_id,
            ver_id,
            status_id,
            stale_id,
            src_id,
            draft_id,
            stable_id,
            deprecated_id,
        }:
            raise AssertionError("status and the other four fields were not all planted")

        def hits_for(query: str) -> tuple[list, list]:
            command_hits = require_search_structured_success(
                run_search(ws, query, rel, structured=True, limit=100)
            )
            tool_hits = require_mcp_search_success(
                mcp_search(ws, query=query, bundle=rel, limit=100)
            )
            return command_hits, tool_hits

        for field, term, identity, title, _generated, _extra in plants:
            others = [item[2] for item in plants if item[2] != identity]
            command_hits, tool_hits = hits_for(term)
            for entry, hits in (("command", command_hits), ("tool", tool_hits)):
                assert identity_in_records(hits, scored_id), (
                    f"{entry} keyword search omitted the concept whose title "
                    f"contains the term {term!r}"
                )
                assert not identity_in_records(hits, identity), (
                    f"{entry} indexed {field} and returned {identity!r} "
                    f"for term {term!r}"
                )
                assert not identity_in_records(hits, decoy_id), (
                    f"{entry} returned {decoy_id!r}, which does not contain "
                    f"{term!r}"
                )
                for other_id in others:
                    assert not identity_in_records(hits, other_id), (
                        f"{entry} term {term!r} also returned {other_id!r}"
                    )
            command_title, tool_title = hits_for(title)
            for entry, hits in (("command", command_title), ("tool", tool_title)):
                assert identity_in_records(hits, identity), (
                    f"{entry} title search omitted {identity!r}; "
                    f"the {field}-only concept was not loaded"
                )
                assert not identity_in_records(hits, scored_id), (
                    f"{entry} title query {title!r} returned the concept "
                    "whose title is the planted term"
                )
                assert not identity_in_records(hits, decoy_id), (
                    f"{entry} title query {title!r} returned {decoy_id!r}"
                )
                for other_id in others:
                    assert not identity_in_records(hits, other_id), (
                        f"{entry} title query {title!r} also returned {other_id!r}"
                    )
            print(
                f"{field} is not a keyword field for term {term!r}",
                flush=True,
            )


def test_structured_reports_which_fields_matched():
    """Structured hit names exactly the keyword fields the term matched.

    Each single-field concept matches in one of title, tags, description,
    id, or body. One further concept matches the same term in title and
    tags together. After field text is stripped, the remaining set members
    are those fields and no other member of that set.
    """
    with workspace() as ws:
        term = compact_token("fld")
        typ, desc_f, body_f, title_f = unique_tokens("typ", "dsc", "bod", "ttl")
        id_title, id_tags, id_desc, id_body, id_both = unique_tokens(
            "t", "g", "d", "b", "bt"
        )
        id_ident = f"architecture/{term}"
        rel = _kb()
        specs = [
            search_concept_spec(
                id_title,
                concept_type=typ,
                title=term,
                description=desc_f,
                body=f"{body_f}\n",
            ),
            search_concept_spec(
                id_tags,
                concept_type=typ,
                title=title_f,
                description=desc_f,
                body=f"{body_f}\n",
                tags=[term],
            ),
            search_concept_spec(
                id_desc,
                concept_type=typ,
                title=title_f,
                description=term,
                body=f"{body_f}\n",
            ),
            search_concept_spec(
                id_ident,
                concept_type=typ,
                title=title_f,
                description=desc_f,
                body=f"{body_f}\n",
            ),
            search_concept_spec(
                id_body,
                concept_type=typ,
                title=title_f,
                description=desc_f,
                body=f"{term}\n",
            ),
            search_concept_spec(
                id_both,
                concept_type=typ,
                title=term,
                description=desc_f,
                body=f"{body_f}\n",
                tags=[term],
            ),
        ]
        write_bundle(ws, rel, specs)
        records = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        cases = [
            (id_title, [term, id_title, typ, desc_f, body_f], frozenset({"title"}), "title", "body"),
            (id_tags, [term, id_tags, typ, title_f, desc_f, body_f], frozenset({"tags"}), "tags", "title"),
            (id_desc, [term, id_desc, typ, title_f, body_f], frozenset({"description"}), "description", "title"),
            (id_ident, [term, id_ident, typ, title_f, desc_f, body_f], frozenset({"id"}), "id", "title"),
            (id_body, [term, id_body, typ, title_f, desc_f], frozenset({"body"}), "body", "title"),
            (
                id_both,
                [term, id_both, typ, desc_f, body_f],
                frozenset({"title", "tags"}),
                "title",
                "body",
            ),
        ]
        for ident, strip, expected, present, absent in cases:
            rec = record_for_identity(records, ident)
            tokens = assert_matched_keyword_fields(rec, strip, expected)
            print(f"matched {ident!r} tokens={sorted(tokens)}", flush=True)
            assert present in tokens, (
                f"{ident!r} missing matched-field {present!r}; tokens={sorted(tokens)}"
            )
            assert absent not in tokens, (
                f"{ident!r} still contains {absent!r} after strip; tokens={sorted(tokens)}"
            )
            if "tags" not in expected:
                assert "tags" not in tokens, (
                    f"{ident!r} names tags though that field did not match; "
                    f"tokens={sorted(tokens)}"
                )
        tool_records = require_mcp_search_success(
            mcp_search(ws, query=term, bundle=rel)
        )
        both_ident, both_strip, both_expected, _, _ = cases[-1]
        if both_ident != id_both or both_expected != frozenset({"title", "tags"}):
            raise AssertionError(
                "the title-and-tags command case is no longer the last "
                f"planted hit: {both_ident!r} {both_expected!r}"
            )
        assert_matched_keyword_fields(
            record_for_identity(tool_records, id_both),
            both_strip,
            both_expected,
        )
        print(
            "search tool title-and-tags hit names exactly those two members",
            flush=True,
        )


# ---------------------------------------------------------------------------
# D. Title-over-incidental-body rank; identity tie-break
# ---------------------------------------------------------------------------


def test_title_match_ranks_above_single_incidental_body_match():
    """Titled hit ranks first even when the body-only identity sorts earlier."""
    with workspace() as ws:
        stem = compact_token("rk")
        body_id = f"abody{stem}"
        titled_id = f"ztitle{stem}"
        assert body_id < titled_id
        typ, titled_desc, body_desc, filler = unique_tokens("typ", "td", "bd", "fil")
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    body_id,
                    concept_type=typ,
                    title=filler,
                    description=body_desc,
                    body=f"Mentions {SAMPLE_TERM} only in passing.\n",
                ),
                search_concept_spec(
                    titled_id,
                    concept_type=typ,
                    title=SAMPLE_TERM_TITLE,
                    description=titled_desc,
                    body=f"{filler}\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, SAMPLE_TERM, rel, structured=True)
        )
        require_identity_order(records, [titled_id, body_id])
        human = require_search_success(run_search(ws, SAMPLE_TERM, rel))
        require_human_ranked_hits(
            human,
            [
                ("context", (titled_id, SAMPLE_TERM_TITLE, titled_desc)),
                ("context", (body_id, filler, body_desc)),
            ],
            planted_order=(body_id, titled_id),
        )
        print("title-over-body order ok", flush=True)


def test_title_over_body_reports_title_match_on_the_titled_hit():
    """The titled hit still contains matched-field title after stripping texts."""
    with workspace() as ws:
        stem = compact_token("tm")
        titled_id = f"atitle{stem}"
        body_id = f"zbody{stem}"
        assert titled_id < body_id
        typ, desc, filler = unique_tokens("typ", "dsc", "fil")
        title = SAMPLE_TERM_TITLE
        rel = _kb()
        write_concepts_later_first(
            ws,
            rel,
            [
                search_concept_spec(
                    titled_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{filler}\n",
                ),
                search_concept_spec(
                    body_id,
                    concept_type=typ,
                    title=filler,
                    description=desc,
                    body=f"Mentions {SAMPLE_TERM} only in passing.\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, SAMPLE_TERM, rel, structured=True)
        )
        rec = record_for_identity(records, titled_id)
        tokens = matched_field_tokens(
            rec, [title, titled_id, typ, desc, filler]
        )
        assert "title" in tokens, f"titled hit missing title match; tokens={sorted(tokens)}"
        print("titled hit reports title", flush=True)


def test_title_over_body_runtime_twin():
    """Runtime-unique title vs incidental body, identities still inverted."""
    with workspace() as ws:
        term = compact_token("tw")
        body_id = f"abody{term}"
        titled_id = f"ztitle{term}"
        assert body_id < titled_id
        typ, desc, filler = unique_tokens("typ", "dsc", "fil")
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    body_id,
                    concept_type=typ,
                    title=filler,
                    description=desc,
                    body=f"Incidental {term} once.\n",
                ),
                search_concept_spec(
                    titled_id,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{filler}\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        ordered = require_identity_order(records, [titled_id, body_id])
        assert ordered == [titled_id, body_id], (
            f"title match must rank above incidental body; order={ordered!r}"
        )
        human = require_search_success(run_search(ws, term, rel))
        require_human_ranked_hits(
            human,
            [
                ("context", (titled_id,)),
                ("context", (body_id,)),
            ],
            planted_order=(body_id, titled_id),
        )
        print("runtime title-over-body twin ok", flush=True)


def test_equal_scores_order_by_identity_ascending_cap_1_returns_alpha():
    """Equal title scores: lower identity first; cap 1 returns only that one."""
    with workspace() as ws:
        rel = _kb()
        write_equal_score_title_bundle(ws, rel, SAMPLE_SHARED_TITLE, [SAMPLE_LOW_ID, SAMPLE_HIGH_ID])
        capped = require_search_structured_success(
            run_search(ws, SAMPLE_SHARED_WORD, rel, limit=1, structured=True)
        )
        require_identity_order(capped, [SAMPLE_LOW_ID])
        both = require_search_structured_success(
            run_search(ws, SAMPLE_SHARED_WORD, rel, structured=True)
        )
        require_identity_order(both, [SAMPLE_LOW_ID, SAMPLE_HIGH_ID])
        human = require_search_success(run_search(ws, SAMPLE_SHARED_WORD, rel))
        require_human_ranked_hits(
            human,
            [
                ("context", (SAMPLE_LOW_ID,)),
                ("context", (SAMPLE_HIGH_ID,)),
            ],
            planted_order=(SAMPLE_HIGH_ID, SAMPLE_LOW_ID),
        )
        twin_rel = _kb()
        a_id, z_id = f"aaa{compact_token('a')}", f"zzz{compact_token('z')}"
        assert a_id < z_id
        title = compact_token("sh")
        write_equal_score_title_bundle(ws, twin_rel, title, [a_id, z_id])
        twin_capped = require_search_structured_success(
            run_search(ws, title, twin_rel, limit=1, structured=True)
        )
        require_identity_order(twin_capped, [a_id])
        human_twin = require_search_success(run_search(ws, title, twin_rel))
        require_human_ranked_hits(
            human_twin,
            [
                ("context", (a_id,)),
                ("context", (z_id,)),
            ],
            planted_order=(z_id, a_id),
        )
        print("identity tie-break cap 1 ok", flush=True)


# ---------------------------------------------------------------------------
# E. Structured extras: governance, code_refs, tags, inbound/outbound, score
# ---------------------------------------------------------------------------


def test_structured_reports_effective_governance_including_convention_default():
    """Declared hold, convention omit → constraint, other omit → context.

    The omitted convention identities are one segment and
    ``convention/<dir>/<leaf>``. Both effective values are constraint.
    An omitted identity whose first segment only shares that prefix
    (``convention<extra>/<leaf>``, the same boundary as
    ``conventional/<leaf>``) is not under ``convention/`` and is context.
    """
    with workspace() as ws:
        hold_id, conv_leaf, ctx_id = unique_compact("h", "cv", "x")
        conv_id = f"convention/{conv_leaf}"
        deep_id = deeper_convention_omit_identity(conv_id)
        prefix_id = prefix_sharing_convention_omit_identity(
            hold_id, conv_id, deep_id, ctx_id
        )
        if prefix_id.startswith("convention/") or not prefix_id.startswith("convention"):
            raise AssertionError(
                "prefix-sharing omit must share the convention characters "
                f"without the directory slash: {prefix_id!r}"
            )
        if prefix_id.split("/")[0] == "convention":
            raise AssertionError(
                "prefix-sharing omit must not be the convention directory: "
                f"{prefix_id!r}"
            )
        typ, title, desc, body = unique_tokens("typ", "ttl", "dsc", "bod")
        rel = _kb()
        prefix_title = f"{title}v"
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    hold_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    governance="hold",
                ),
                search_concept_spec(
                    conv_id,
                    concept_type=typ,
                    title=f"{title}c",
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    deep_id,
                    concept_type=typ,
                    title=f"{title}n",
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    prefix_id,
                    concept_type=typ,
                    title=prefix_title,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    ctx_id,
                    concept_type=typ,
                    title=f"{title}x",
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        hold_title = title
        conv_title = f"{title}c"
        deep_title = f"{title}n"
        ctx_title = f"{title}x"
        assert_single_effective_governance(
            record_for_identity(records, hold_id),
            "hold",
            [hold_id, typ, hold_title, desc, body],
        )
        assert_single_effective_governance(
            record_for_identity(records, conv_id),
            "constraint",
            [conv_id, typ, conv_title, desc, body],
        )
        assert_single_effective_governance(
            record_for_identity(records, deep_id),
            "constraint",
            [deep_id, typ, deep_title, desc, body],
        )
        assert_single_effective_governance(
            record_for_identity(records, prefix_id),
            "context",
            [prefix_id, typ, prefix_title, desc, body],
        )
        assert_single_effective_governance(
            record_for_identity(records, ctx_id),
            "context",
            [ctx_id, typ, ctx_title, desc, body],
        )
        print("effective governance is one value", flush=True)


def test_declared_governance_is_compared_case_insensitively():
    """Declared governance folds any capitalization to the lowercase word.

    The structured hit's effective value is that lowercase word. The
    spelling written in the file may remain beside it; a hit whose only
    governance word is the un-normalized spelling does not pass. A mixed
    spelling such as Hold or Constraint is the same effective value on
    the structured hit and on the human badge. A non-convention identity
    defaults to context, so ignoring that mixed spelling cannot hide
    behind the default. Context is planted under convention/, whose
    default is constraint, for the same reason.
    """
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "hid", "typ", "ttl", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    governance="HOLD",
                )
            ],
        )
        records = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert_lowercase_effective_governance(
            record_for_identity(records, ident),
            "hold",
            [ident, typ, title, desc, body],
        )
        print("HOLD normalized", flush=True)
        # Title case is not the all-caps spelling the closed checks store.
        # convention/ defaults to constraint; every other identity defaults
        # to context. Each declared word differs from that default.
        mixed = (
            ("Hold", "hold", False),
            ("Constraint", "constraint", False),
            ("Context", "context", True),
        )
        for declared, effective, under_convention in mixed:
            leaf, typ, title, desc, body = unique_tokens(
                "mid", "typ", "ttl", "dsc", "bod"
            )
            ident = f"convention/{leaf}" if under_convention else leaf
            rel = _kb()
            write_bundle(
                ws,
                rel,
                [
                    search_concept_spec(
                        ident,
                        concept_type=typ,
                        title=title,
                        description=desc,
                        body=f"{body}\n",
                        governance=declared,
                    )
                ],
            )
            records = require_search_structured_success(
                run_search(ws, title, rel, structured=True)
            )
            assert_lowercase_effective_governance(
                record_for_identity(records, ident),
                effective,
                [ident, typ, title, desc, body],
            )
            report = require_search_success(run_search(ws, title, rel))
            assert_identifiable_human_hits(
                report, [(effective, (ident, title, desc))]
            )
            print(
                f"mixed {declared!r} effective {effective!r}",
                flush=True,
            )


def test_structured_includes_code_refs_and_tags_when_present():
    """code_refs path and unique tag appear only on the concept that has them."""
    with workspace() as ws:
        tagged, plain, typ, title, desc, body, ptitle = unique_tokens(
            "tg", "pl", "typ", "ttl", "dsc", "bod", "ptt"
        )
        tag = compact_token("tag")
        path = f"pkg/{compact_token('p')}/x.go"
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    tagged,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    tags=[tag],
                    code_refs=[path],
                ),
                search_concept_spec(
                    plain,
                    concept_type=typ,
                    title=ptitle,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        tagged_hit = record_for_identity(records, tagged)
        assert path in hit_list(tagged_hit, "code_refs"), (
            f"code_refs path missing: {tagged_hit!r}"
        )
        assert tag in hit_list(tagged_hit, "tags"), f"tag missing: {tagged_hit!r}"
        plain_records = require_search_structured_success(
            run_search(ws, ptitle, rel, structured=True)
        )
        plain_hit = record_for_identity(plain_records, plain)
        assert path not in hit_list(plain_hit, "code_refs")
        assert tag not in hit_list(plain_hit, "tags")
        print("code_refs and tags presence contrast ok", flush=True)


def test_structured_includes_outbound_identity_when_present():
    """A bundle-relative href plus .md leaves that identity after the body is removed."""
    with workspace() as ws:
        p_leaf, q_leaf, r_leaf, ptyp, qtyp, rtyp, pttl, qttl, rttl, pdsc, qdsc, rdsc, ptok, qtok, rtok = unique_tokens(
            "pl",
            "ql",
            "rl",
            "pt",
            "qt",
            "rt",
            "ptt",
            "qtt",
            "rtt",
            "pd",
            "qd",
            "rd",
            "pb",
            "qb",
            "rb",
        )
        p_id = p_leaf
        q_id = f"architecture/{q_leaf}"
        r_id = r_leaf
        href = f"{q_id}.md"
        p_body = f"{ptok}\n\n{markdown_link(q_leaf, href)}\n"
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    p_id,
                    concept_type=ptyp,
                    title=pttl,
                    description=pdsc,
                    body=p_body,
                ),
                search_concept_spec(
                    q_id,
                    concept_type=qtyp,
                    title=qttl,
                    description=qdsc,
                    body=f"{qtok}\n",
                ),
                search_concept_spec(
                    r_id,
                    concept_type=rtyp,
                    title=rttl,
                    description=rdsc,
                    body=f"{rtok}\n",
                ),
            ],
        )
        p_hit = record_for_identity(
            require_search_structured_success(
                run_search(ws, pttl, rel, structured=True)
            ),
            p_id,
        )
        q_hit = record_for_identity(
            require_search_structured_success(
                run_search(ws, qttl, rel, structured=True)
            ),
            q_id,
        )
        r_hit = record_for_identity(
            require_search_structured_success(
                run_search(ws, rttl, rel, structured=True)
            ),
            r_id,
        )
        p_out = hit_list(p_hit, "outbound")
        q_in = hit_list(q_hit, "inbound")
        r_links = hit_list(r_hit, "outbound") + hit_list(r_hit, "inbound")
        print(f"P outbound has Q={q_id in p_out} Q inbound has P={p_id in q_in}", flush=True)
        assert q_id in p_out, f"outbound Q missing; outbound={p_out!r}"
        assert p_id in q_in, f"inbound P missing; inbound={q_in!r}"
        assert q_id not in r_links, f"unrelated R still carries Q; links={r_links!r}"


def test_structured_hit_includes_a_numeric_score():
    """Each structured hit includes a numeric score; title still ranks first."""
    with workspace() as ws:
        term = compact_token("sc")
        body_id = f"abody{term}"
        titled_id = f"ztitle{term}"
        assert body_id < titled_id
        typ, desc, filler = unique_tokens("typ", "dsc", "fil")
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    body_id,
                    concept_type=typ,
                    title=filler,
                    description=desc,
                    body=f"Incidental {term} once.\n",
                ),
                search_concept_spec(
                    titled_id,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{filler}\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        require_identity_order(records, [titled_id, body_id])
        titled_hit = record_for_identity(records, titled_id)
        body_hit = record_for_identity(records, body_id)
        assert record_has_json_number(titled_hit), (
            f"titled hit has no numeric score: {titled_hit!r}"
        )
        assert record_has_json_number(body_hit), (
            f"incidental-body hit has no numeric score: {body_hit!r}"
        )
        print("both hits carry a numeric score", flush=True)


# ---------------------------------------------------------------------------
# F. Human prefixes each hit with a governance badge
# ---------------------------------------------------------------------------


def test_human_prefixes_each_hit_with_constraint_hold_or_context_badge():
    """Declared HOLD, CONSTRAINT, and CONTEXT still prefix each human hit in lowercase."""
    with workspace() as ws:
        hold_id, con_id, ctx_id = inverted_governance_identities()
        typ, htitle, ctitle, xtitle, hdesc, cdesc, xdesc, body = unique_tokens(
            "typ", "ht", "ct", "xt", "hd", "cd", "xd", "bod"
        )
        path = f"pkg/{compact_token('p')}/login.go"
        rel = _kb()
        write_concepts_later_first(
            ws,
            rel,
            [
                search_concept_spec(
                    hold_id,
                    concept_type=typ,
                    title=htitle,
                    description=hdesc,
                    body=f"{body}\n",
                    governance="HOLD",
                    code_refs=[path],
                ),
                search_concept_spec(
                    con_id,
                    concept_type=typ,
                    title=ctitle,
                    description=cdesc,
                    body=f"{body}\n",
                    governance="CONSTRAINT",
                    code_refs=[path],
                ),
                search_concept_spec(
                    ctx_id,
                    concept_type=typ,
                    title=xtitle,
                    description=xdesc,
                    body=f"{body}\n",
                    governance="CONTEXT",
                    code_refs=[path],
                ),
            ],
        )
        report = require_search_success(run_search(ws, None, rel, for_path=path))
        assert_identifiable_human_hits(
            report,
            [
                ("hold", (hold_id, htitle, hdesc)),
                ("constraint", (con_id, ctitle, cdesc)),
                ("context", (ctx_id, xtitle, xdesc)),
            ],
        )
        print("human three-way badge contrast ok", flush=True)


def test_human_badges_convention_omit_as_constraint():
    """Omitted identities under convention/ badge as constraint, including a nested leaf.

    The one-segment omit stays. Governance is also omitted on
    ``convention/<dir>/<leaf>``. That hit's human badge is the lowercase
    word constraint, as a prefix of that hit. Declared HOLD and CONTEXT
    still badge in lowercase. A default that fires only for a single
    segment and badges the nested omit as context fails here.

    Governance is also omitted on an identity whose first segment only
    shares the convention characters, the same boundary as
    ``conventional/<leaf>``. That identity is not under the directory
    ``convention/``. Its human badge is the lowercase word context. A
    badge that treats a leading convention string as the directory,
    without the slash, labels that hit constraint.
    """
    with workspace() as ws:
        hold_id, conv_id, deep_id, ctx_id = inverted_nested_convention_identities()
        prefix_id = prefix_sharing_human_omit_identity(
            hold_id, conv_id, deep_id, ctx_id
        )
        deep_parts = deep_id.split("/")
        prefix_parts = prefix_id.split("/")
        if (
            deep_parts[0] != "convention"
            or len(deep_parts) != 3
            or not all(deep_parts)
            or conv_id.count("/") != 1
            or not conv_id.startswith("convention/")
        ):
            raise AssertionError(
                "human convention badges need one convention/<leaf> omit and "
                "one convention/<dir>/<leaf> omit: "
                f"shallow={conv_id!r} nested={deep_id!r}"
            )
        if (
            len(prefix_parts) != 2
            or not all(prefix_parts)
            or prefix_id.startswith("convention/")
            or not prefix_id.startswith("convention")
            or prefix_parts[0] == "convention"
        ):
            raise AssertionError(
                "human prefix-sharing omit must share the convention "
                "characters without the directory slash: "
                f"{prefix_id!r}"
            )
        if not (hold_id < ctx_id < conv_id < deep_id < prefix_id):
            raise AssertionError(
                "nested omit must sort after the one-segment omit, and the "
                "declared context identity must sort before both, so a "
                "single-segment default that badges the nested omit as "
                "context is not hold, constraint, constraint, context; the "
                "prefix-sharing omit sorts after that nested omit, so a "
                "leading convention string would badge it constraint in "
                "the constraint group: "
                f"{hold_id!r} {ctx_id!r} {conv_id!r} {deep_id!r} {prefix_id!r}"
            )
        typ, htitle, ctitle, dtitle, xtitle, ptitle, hdesc, cdesc, ddesc, xdesc, pdesc, body = (
            unique_tokens(
                "typ", "ht", "ct", "dt", "xt", "pt",
                "hd", "cd", "dd", "xd", "pd", "bod",
            )
        )
        path = f"pkg/{compact_token('p')}/x.go"
        rel = _kb()
        shallow_spec = search_concept_spec(
            conv_id,
            concept_type=typ,
            title=ctitle,
            description=cdesc,
            body=f"{body}\n",
            code_refs=[path],
        )
        deep_spec = search_concept_spec(
            deep_id,
            concept_type=typ,
            title=dtitle,
            description=ddesc,
            body=f"{body}\n",
            code_refs=[path],
        )
        prefix_spec = search_concept_spec(
            prefix_id,
            concept_type=typ,
            title=ptitle,
            description=pdesc,
            body=f"{body}\n",
            code_refs=[path],
        )
        for spec, label in (
            (shallow_spec, "one-segment convention"),
            (deep_spec, "nested convention"),
            (prefix_spec, "prefix-sharing convention"),
        ):
            extra = spec.get("extra") or {}
            if "governance" in extra:
                raise AssertionError(
                    f"{label} identity must omit governance; extra={extra!r}"
                )
        write_concepts_later_first(
            ws,
            rel,
            [
                search_concept_spec(
                    hold_id,
                    concept_type=typ,
                    title=htitle,
                    description=hdesc,
                    body=f"{body}\n",
                    governance="HOLD",
                    code_refs=[path],
                ),
                shallow_spec,
                deep_spec,
                prefix_spec,
                search_concept_spec(
                    ctx_id,
                    concept_type=typ,
                    title=xtitle,
                    description=xdesc,
                    body=f"{body}\n",
                    governance="CONTEXT",
                    code_refs=[path],
                ),
            ],
        )
        report = require_search_success(run_search(ws, None, rel, for_path=path))
        assert_identifiable_human_hits(
            report,
            [
                ("hold", (hold_id, htitle, hdesc)),
                ("constraint", (conv_id, ctitle, cdesc)),
                ("constraint", (deep_id, dtitle, ddesc)),
                ("context", (ctx_id, xtitle, xdesc)),
                ("context", (prefix_id, ptitle, pdesc)),
            ],
        )
        print("convention omit human badge is constraint", flush=True)


# ---------------------------------------------------------------------------
# G. Result caps 10 / 100 / 3 and non-positive = default, keyword and path
# ---------------------------------------------------------------------------


def test_omit_cap_returns_all_when_under_10_and_truncates_to_10_when_over():
    """5 matches omit-cap → 5 identity-ascending; 15 omit-cap → first 10.

    Keyword search as human text, structured output not requested, uses
    the same caps. These hits share one title, so the kept hits are the
    ranked identity prefix. That human prefix is the concept identities
    inside successive governance-badge spans, not the first time each
    identity appears in the report. On 15 equal-score hits, omitting the cap,
    cap 0, and a negative cap each present that prefix of 10 and withhold
    every later identity. On more than 100 equal-score hits, a cap above
    100 presents the prefix of 100 and withholds the rest. The human
    cap-of-3 check is a different test.
    """
    with workspace() as ws:
        term5 = compact_token("t5")
        ids5 = numbered_identities(5, compact_token("s5"))
        rel5 = _kb()
        write_equal_score_title_bundle(ws, rel5, term5, ids5)
        records5 = require_search_structured_success(
            run_search(ws, term5, rel5, structured=True)
        )
        require_identity_order(records5, ids5)
        term15 = compact_token("t15")
        ids15 = numbered_identities(15, compact_token("s15"))
        rel15 = _kb()
        write_equal_score_title_bundle(ws, rel15, term15, ids15)
        records15 = require_search_structured_success(
            run_search(ws, term15, rel15, structured=True)
        )
        require_identity_order(records15, ids15[:10])
        expected10 = ids15[:10]
        withheld15 = ids15[10:]
        assert len(withheld15) >= 1 and len(ids15) > 10, (
            f"human default-cap probe planted {len(ids15)} hits; need more than 10"
        )
        human_omit = require_search_success(run_search(ws, term15, rel15))
        human_omit_prefix = require_human_identity_prefix(
            human_omit, expected10, withheld15
        )
        assert human_omit_prefix == expected10, (
            f"human omit-cap must present the first 10 identities; "
            f"order={human_omit_prefix!r}"
        )
        for cap in (0, -5):
            human_nonpos = require_search_success(
                run_search(ws, term15, rel15, limit=cap)
            )
            human_nonpos_prefix = require_human_identity_prefix(
                human_nonpos, expected10, withheld15
            )
            assert human_nonpos_prefix == expected10, (
                f"human non-positive cap {cap} must present the first 10 "
                f"identities; order={human_nonpos_prefix!r}"
            )
        term_hi = compact_token("thi")
        ids_hi = numbered_identities(120, compact_token("shi"))
        assert len(ids_hi) > 100, (
            f"human ceiling probe planted {len(ids_hi)} hits; need more than 100"
        )
        rel_hi = _kb()
        write_equal_score_title_bundle(ws, rel_hi, term_hi, ids_hi)
        human_above = require_search_success(
            run_search(ws, term_hi, rel_hi, limit=101)
        )
        human_above_prefix = require_human_identity_prefix(
            human_above, ids_hi[:100], ids_hi[100:]
        )
        assert human_above_prefix == ids_hi[:100], (
            f"human cap above 100 must present the first 100 identities; "
            f"order={human_above_prefix!r}"
        )
        print("omit-cap 5 vs 15 ok; human 10 and 100 ok", flush=True)


def test_non_positive_cap_is_the_default_10():
    """--limit 0 and a negative cap on 15 matches still return the first 10."""
    with workspace() as ws:
        term = compact_token("np")
        ids = numbered_identities(15, compact_token("snp"))
        rel = _kb()
        write_equal_score_title_bundle(ws, rel, term, ids)
        expected10 = ids[:10]
        for cap in (0, -5):
            records = require_search_structured_success(
                run_search(ws, term, rel, limit=cap, structured=True)
            )
            ordered = require_identity_order(records, expected10)
            assert ordered == expected10, (
                f"non-positive cap {cap} must return the first 10 identities; "
                f"order={ordered!r}"
            )
        mcp = require_mcp_search_success(
            mcp_search(ws, query=term, bundle=rel, limit=0)
        )
        mcp_ordered = require_identity_order(mcp, expected10)
        assert mcp_ordered == expected10, (
            f"MCP limit 0 must return the first 10 identities; "
            f"order={mcp_ordered!r}"
        )
        print("non-positive cap is default 10", flush=True)


def test_cap_3_returns_at_most_3_ranked_prefix():
    """Cap 3 on 15 matches returns the 3 lexicographically first identities.

    Structured output is a separate request. The same cap on human output
    presents those three identities inside successive governance-badge
    spans, in concept-identity order, and does not present a later one.
    Omitting the cap on that human request still presents the later identity.
    """
    with workspace() as ws:
        term15 = compact_token("c3")
        ids15 = numbered_identities(15, compact_token("s3"))
        rel15 = _kb()
        write_equal_score_title_bundle(ws, rel15, term15, ids15)
        records = require_search_structured_success(
            run_search(ws, term15, rel15, limit=3, structured=True)
        )
        ordered3 = require_identity_order(records, ids15[:3])
        assert ordered3 == ids15[:3], (
            f"cap 3 must return the first 3 identities; order={ordered3!r}"
        )
        human_capped = require_search_success(
            run_search(ws, term15, rel15, limit=3)
        )
        human_prefix = require_human_identity_prefix(
            human_capped, ids15[:3], ids15[3:]
        )
        assert human_prefix == ids15[:3], (
            f"human cap 3 must present only the first 3 identities; "
            f"order={human_prefix!r}"
        )
        human_open = require_search_success(run_search(ws, term15, rel15))
        require_human_identity_present(human_open, ids15[3])
        term5 = compact_token("c5")
        ids5 = numbered_identities(5, compact_token("s5b"))
        rel5 = _kb()
        write_equal_score_title_bundle(ws, rel5, term5, ids5)
        under = require_search_structured_success(
            run_search(ws, term5, rel5, structured=True)
        )
        ordered5 = require_identity_order(under, ids5)
        assert ordered5 == ids5, (
            f"omit-cap on 5 matches must return all 5; order={ordered5!r}"
        )
        print("cap 3 vs omit-on-5 contrast ok", flush=True)


def test_cap_above_100_returns_at_most_100():
    """A large cap and cap 101 on 120 matches each return the first 100.

    101 is above 100 and is not the large cap. Omit-cap returns 10.
    Cap 100 returns 100.
    """
    with workspace() as ws:
        term = compact_token("mx")
        ids = numbered_identities(120, compact_token("smx"))
        rel = _kb()
        write_equal_score_title_bundle(ws, rel, term, ids)
        huge = require_search_structured_success(
            run_search(ws, term, rel, limit=SAMPLE_BIG_CAP, structured=True)
        )
        assert len(huge) == 100, f"cap {SAMPLE_BIG_CAP} returned {len(huge)}"
        require_identity_order(huge, ids[:100])
        above = require_search_structured_success(
            run_search(ws, term, rel, limit=101, structured=True)
        )
        require_cap_above_100_returns_at_most_100(
            above,
            ids[:100],
            requested_cap=101,
            planted=len(ids),
            surface="keyword command",
        )
        omitted = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        require_identity_order(omitted, ids[:10])
        exact = require_search_structured_success(
            run_search(ws, term, rel, limit=100, structured=True)
        )
        require_identity_order(exact, ids[:100])
        print("max cap 100 ok", flush=True)


def test_mcp_search_limits_default_10_and_max_100():
    """MCP omit and a negative cap on 15 are the first 10; cap 3 is the first 3; a large cap and 101 on 120 are 100."""
    with workspace() as ws:
        term15 = compact_token("m15")
        ids15 = numbered_identities(15, compact_token("ms15"))
        rel15 = _kb()
        write_equal_score_title_bundle(ws, rel15, term15, ids15)
        expected10 = ids15[:10]
        mcp15 = require_mcp_search_success(mcp_search(ws, query=term15, bundle=rel15))
        ordered15 = require_identity_order(mcp15, expected10)
        assert ordered15 == expected10, (
            f"MCP omit-cap must return the first 10 identities; order={ordered15!r}"
        )
        mcp3 = require_mcp_search_success(
            mcp_search(ws, query=term15, bundle=rel15, limit=3)
        )
        ordered3 = require_identity_order(mcp3, ids15[:3])
        assert len(ordered3) <= 3 and ordered3 == ids15[:3], (
            f"MCP cap 3 must return at most the first 3 ranked identities; "
            f"order={ordered3!r}"
        )
        mcp_neg = require_mcp_search_success(
            mcp_search(ws, query=term15, bundle=rel15, limit=-1)
        )
        ordered_neg = require_identity_order(mcp_neg, expected10)
        assert ordered_neg == expected10, (
            f"MCP negative cap must return the default first 10 identities; "
            f"order={ordered_neg!r}"
        )
        term120 = compact_token("m120")
        ids120 = numbered_identities(120, compact_token("ms120"))
        rel120 = _kb()
        write_equal_score_title_bundle(ws, rel120, term120, ids120)
        mcp120 = require_mcp_search_success(
            mcp_search(ws, query=term120, bundle=rel120, limit=SAMPLE_BIG_CAP)
        )
        assert len(mcp120) == 100, f"MCP cap {SAMPLE_BIG_CAP} returned {len(mcp120)}"
        require_identity_order(mcp120, ids120[:100])
        mcp_above = require_mcp_search_success(
            mcp_search(ws, query=term120, bundle=rel120, limit=101)
        )
        require_cap_above_100_returns_at_most_100(
            mcp_above,
            ids120[:100],
            requested_cap=101,
            planted=len(ids120),
            surface="keyword search tool",
        )
        print("MCP limits 3/10/100 ok", flush=True)


def test_omit_cap_on_path_search_truncates_to_10():
    """Fifteen same-governance path hits, cap omitted, return the first 10 identities.

    Structured output is a separate request. The same path request as
    human text, with structured output not requested, presents that
    ranked identity prefix as the concept identities inside successive
    governance-badge spans, and does not present a later path hit. The
    human path cap of 3 is a different test.
    """
    with workspace() as ws:
        path = f"pkg/{compact_token('pp')}/x.go"
        ids = numbered_identities(15, compact_token("ps"))
        typ, desc, body = unique_tokens("typ", "dsc", "bod")
        rel = _kb()
        specs = [
            search_concept_spec(
                ident,
                concept_type=typ,
                title=ident,
                description=desc,
                body=f"{body}\n",
                governance="context",
                code_refs=[path],
            )
            for ident in ids
        ]
        write_concepts_later_first(ws, rel, specs)
        expected10 = ids[:10]
        withheld = ids[10:]
        assert len(ids) > 10 and len(withheld) >= 1, (
            f"human path omit-cap probe planted {len(ids)} path hits; "
            "need more than 10"
        )
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=path, structured=True)
        )
        ordered = require_identity_order(records, expected10)
        assert ordered == expected10, (
            f"path omit-cap must return the first 10 identities; order={ordered!r}"
        )
        human_omit = require_search_success(
            run_search(ws, None, rel, for_path=path)
        )
        human_omit_prefix = require_human_identity_prefix(
            human_omit, expected10, withheld
        )
        assert human_omit_prefix == expected10, (
            f"human path omit-cap must present the first 10 identities; "
            f"order={human_omit_prefix!r}"
        )
        print("path omit-cap 10 ok", flush=True)


def test_non_positive_cap_on_path_search_is_the_default_10():
    """Fifteen path-only hits with cap 0 and a negative cap return the first 10.

    The same two caps on human path output, with structured output not
    requested, present that ranked identity prefix as the concept
    identities inside successive governance-badge spans, and do not
    present a later path hit.
    """
    with workspace() as ws:
        path = f"pkg/{compact_token('np')}/x.go"
        ids = numbered_identities(15, compact_token("nps"))
        typ, desc, body = unique_tokens("typ", "dsc", "bod")
        rel = _kb()
        specs = [
            search_concept_spec(
                ident,
                concept_type=typ,
                title=ident,
                description=desc,
                body=f"{body}\n",
                governance="context",
                code_refs=[path],
            )
            for ident in ids
        ]
        write_concepts_later_first(ws, rel, specs)
        expected10 = ids[:10]
        withheld = ids[10:]
        assert len(ids) > 10 and len(withheld) >= 1, (
            f"human path non-positive probe planted {len(ids)} path hits; "
            "need more than 10"
        )
        for cap in (0, -5):
            records = require_search_structured_success(
                run_search(
                    ws, None, rel, for_path=path, limit=cap, structured=True
                )
            )
            ordered = require_identity_order(records, expected10)
            assert ordered == expected10, (
                f"path non-positive cap {cap} must return the first 10 "
                f"identities; order={ordered!r}"
            )
            human_nonpos = require_search_success(
                run_search(ws, None, rel, for_path=path, limit=cap)
            )
            human_nonpos_prefix = require_human_identity_prefix(
                human_nonpos, expected10, withheld
            )
            assert human_nonpos_prefix == expected10, (
                f"human path non-positive cap {cap} must present the first "
                f"10 identities; order={human_nonpos_prefix!r}"
            )
        print("path non-positive cap is default 10", flush=True)


def test_cap_3_on_path_search_returns_at_most_3():
    """Fifteen path hits with --limit 3 return the first 3 identities.

    The same cap on human output presents those three inside successive
    governance-badge spans, in concept-identity order, and does not
    present a later path hit. Omitting the cap on that human request
    still does.
    """
    with workspace() as ws:
        path = f"pkg/{compact_token('p3')}/x.go"
        ids = numbered_identities(15, compact_token("p3s"))
        typ, desc, body = unique_tokens("typ", "dsc", "bod")
        rel = _kb()
        specs = [
            search_concept_spec(
                ident,
                concept_type=typ,
                title=ident,
                description=desc,
                body=f"{body}\n",
                governance="context",
                code_refs=[path],
            )
            for ident in ids
        ]
        write_concepts_later_first(ws, rel, specs)
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=path, limit=3, structured=True)
        )
        ordered = require_identity_order(records, ids[:3])
        assert ordered == ids[:3], (
            f"path cap 3 must return the first 3 identities; order={ordered!r}"
        )
        human_capped = require_search_success(
            run_search(ws, None, rel, for_path=path, limit=3)
        )
        human_prefix = require_human_identity_prefix(
            human_capped, ids[:3], ids[3:]
        )
        assert human_prefix == ids[:3], (
            f"human path cap 3 must present only the first 3 identities; "
            f"order={human_prefix!r}"
        )
        human_open = require_search_success(
            run_search(ws, None, rel, for_path=path)
        )
        require_human_identity_present(human_open, ids[3])
        print("path cap 3 ok", flush=True)


def test_cap_above_100_on_path_search_returns_at_most_100():
    """120 path-only hits with a large cap or cap 101 return the first 100.

    The command, human path text, and the search tool share this ceiling.
    Structured output is a separate request. On human path output, with
    structured output not requested, both caps present the ranked identity
    prefix of 100 as the concept identities inside successive
    governance-badge spans, and do not present a later path hit. 101 is above 100
    and is not the large cap. A cap above 100 on a path search is
    not the omitted-cap default of 10, and it is not the keyword-search
    ceiling already locked on 120 title matches.
    """
    with workspace() as ws:
        path = f"pkg/{compact_token('p100')}/x.go"
        ids = numbered_identities(120, compact_token("p100s"))
        assert len(ids) > 100, (
            f"path ceiling probe planted {len(ids)} matches; need more than 100"
        )
        typ, desc, body = unique_tokens("typ", "dsc", "bod")
        rel = _kb()
        specs = [
            search_concept_spec(
                ident,
                concept_type=typ,
                title=ident,
                description=desc,
                body=f"{body}\n",
                governance="context",
                code_refs=[path],
            )
            for ident in ids
        ]
        write_concepts_later_first(ws, rel, specs)
        expected = ids[:100]
        records = require_search_structured_success(
            run_search(
                ws, None, rel, for_path=path, limit=SAMPLE_BIG_CAP, structured=True
            )
        )
        assert len(records) == 100, (
            f"path cap {SAMPLE_BIG_CAP} returned {len(records)} of {len(ids)} path hits; "
            "a requested cap above 100 returns at most 100"
        )
        ordered = require_identity_order(records, expected)
        assert ordered == expected, (
            f"path cap {SAMPLE_BIG_CAP} must return the first 100 identities; "
            f"order={ordered!r}"
        )
        mcp = require_mcp_search_success(
            mcp_search(ws, for_path=path, bundle=rel, limit=SAMPLE_BIG_CAP)
        )
        assert len(mcp) == 100, (
            f"path-tool cap {SAMPLE_BIG_CAP} returned {len(mcp)} of {len(ids)} path hits; "
            "a requested cap above 100 returns at most 100"
        )
        mcp_ordered = require_identity_order(mcp, expected)
        assert mcp_ordered == expected, (
            f"path-tool cap {SAMPLE_BIG_CAP} must return the first 100 identities; "
            f"order={mcp_ordered!r}"
        )
        above = require_search_structured_success(
            run_search(
                ws, None, rel, for_path=path, limit=101, structured=True
            )
        )
        require_cap_above_100_returns_at_most_100(
            above,
            expected,
            requested_cap=101,
            planted=len(ids),
            surface="path command",
        )
        mcp_above = require_mcp_search_success(
            mcp_search(ws, for_path=path, bundle=rel, limit=101)
        )
        require_cap_above_100_returns_at_most_100(
            mcp_above,
            expected,
            requested_cap=101,
            planted=len(ids),
            surface="path search tool",
        )
        withheld = ids[100:]
        assert len(withheld) >= 1, (
            f"human path ceiling probe withheld {len(withheld)}; "
            "need a path hit past 100"
        )
        for cap in (SAMPLE_BIG_CAP, 101):
            human_above = require_search_success(
                run_search(ws, None, rel, for_path=path, limit=cap)
            )
            human_above_prefix = require_human_identity_prefix(
                human_above, expected, withheld
            )
            assert human_above_prefix == expected, (
                f"human path cap {cap} must present the first 100 "
                f"identities; order={human_above_prefix!r}"
            )
        print("path cap above 100 is 100", flush=True)


def test_mcp_path_search_limits_default_10_and_max_100():
    """Tool path search uses the same caps as a keyword call on that tool.

    Fifteen path hits and a positive cap of 15 return all fifteen, so the
    default is not "only ten path hits existed". Omitting the cap, cap 0,
    and a negative cap each return the first 10. One hundred twenty path
    hits and a cap above 100 return the first 100, the same prefix as a
    cap of 100. Cap 1 on three governance hits is a different check.
    """
    with workspace() as ws:
        path15 = f"pkg/{compact_token('mp15')}/x.go"
        ids15 = numbered_identities(15, compact_token("mp15s"))
        assert len(ids15) > 10, (
            f"tool path default probe planted {len(ids15)} matches; "
            "need more than 10"
        )
        typ15, desc15, body15 = unique_tokens("typ", "dsc", "bod")
        rel15 = _kb()
        write_concepts_later_first(
            ws,
            rel15,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ15,
                    title=ident,
                    description=desc15,
                    body=f"{body15}\n",
                    governance="context",
                    code_refs=[path15],
                )
                for ident in ids15
            ],
        )
        wide = require_mcp_search_success(
            mcp_search(ws, for_path=path15, bundle=rel15, limit=15)
        )
        wide_order = require_identity_order(wide, ids15)
        assert wide_order == ids15, (
            f"tool path cap 15 must return every planted path hit; "
            f"order={wide_order!r}"
        )
        expected10 = ids15[:10]
        omitted = require_mcp_search_success(
            mcp_search(ws, for_path=path15, bundle=rel15)
        )
        omitted_order = require_identity_order(omitted, expected10)
        assert omitted_order == expected10 and len(omitted_order) < len(wide_order), (
            f"tool path omit-cap must return the first 10 of "
            f"{len(wide_order)} path hits; order={omitted_order!r}"
        )
        for cap in (0, -1):
            capped = require_mcp_search_success(
                mcp_search(ws, for_path=path15, bundle=rel15, limit=cap)
            )
            capped_order = require_identity_order(capped, expected10)
            assert capped_order == expected10, (
                f"tool path non-positive cap {cap} must return the first 10 "
                f"identities; order={capped_order!r}"
            )

        path120 = f"pkg/{compact_token('mp100')}/x.go"
        ids120 = numbered_identities(120, compact_token("mp100s"))
        assert len(ids120) > 100, (
            f"tool path ceiling probe planted {len(ids120)} matches; "
            "need more than 100"
        )
        typ120, desc120, body120 = unique_tokens("typ", "dsc", "bod")
        rel120 = _kb()
        write_concepts_later_first(
            ws,
            rel120,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ120,
                    title=ident,
                    description=desc120,
                    body=f"{body120}\n",
                    governance="context",
                    code_refs=[path120],
                )
                for ident in ids120
            ],
        )
        expected100 = ids120[:100]
        at_ceiling = require_mcp_search_success(
            mcp_search(ws, for_path=path120, bundle=rel120, limit=100)
        )
        ceiling_order = require_identity_order(at_ceiling, expected100)
        assert ceiling_order == expected100, (
            f"tool path cap 100 must return the first 100 identities; "
            f"order={ceiling_order!r}"
        )
        over = require_mcp_search_success(
            mcp_search(ws, for_path=path120, bundle=rel120, limit=SAMPLE_BIG_CAP)
        )
        assert len(over) == 100, (
            f"tool path cap {SAMPLE_BIG_CAP} returned {len(over)} of {len(ids120)} "
            "path hits; a requested cap above 100 returns at most 100"
        )
        over_order = require_identity_order(over, expected100)
        assert over_order == expected100, (
            f"tool path cap {SAMPLE_BIG_CAP} must return the first 100 identities; "
            f"order={over_order!r}"
        )
        other = require_mcp_search_success(
            mcp_search(ws, for_path=path120, bundle=rel120, limit=101)
        )
        require_cap_above_100_returns_at_most_100(
            other,
            expected100,
            requested_cap=101,
            planted=len(ids120),
            surface="path search tool",
        )
        print("MCP path limits 10/100 ok", flush=True)


# ---------------------------------------------------------------------------
# H. Query truncated to 1000 characters; at most the first 50 terms
# ---------------------------------------------------------------------------


def test_query_longer_than_1000_characters_drops_the_tail_term():
    """Distinctive term after the 1000th character is not used; leading term still hits.

    Structured output is a separate request. The same two queries on human
    output, with structured output not requested, still use only the first
    1000 characters: the hit inside that window carries the concept identity
    after its governance badge, and the term that begins after the cut is a
    miss that does not present the concept.
    """
    with workspace() as ws:
        term = compact_token("d1000")
        ident, typ, desc, body = unique_tokens("id", "typ", "dsc", "bod")
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        live = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        assert identity_in_records(live, ident)
        truncated = "x" * 1000 + " " + term
        inside = term + " " + ("x" * 1000)
        assert len(truncated) > 1000
        assert term not in truncated[:1000]
        assert len(inside) > 1000
        assert term in inside[:1000]
        assert ident not in truncated and ident not in inside
        zero = run_search(ws, truncated, rel, structured=True)
        require_zero_hits_success(zero, structured=True, live_identities=[ident])
        control = require_search_structured_success(
            run_search(ws, inside, rel, structured=True)
        )
        assert identity_in_records(control, ident)
        human_inside = require_search_success(run_search(ws, inside, rel))
        assert_human_concept_identity_after_badge(
            human_inside, "context", ident, query=inside
        )
        human_tail = require_zero_hits_success(
            run_search(ws, truncated, rel),
            structured=False,
            live_identities=[ident],
        )
        require_human_identity_absent(human_tail, ident)
        assert_human_zero_hit_miss_statement(
            human_tail,
            human_inside,
            path_tokens_for_search(rel, ws.path),
            (ident, typ, term, desc, body, truncated, inside),
            live_identities=[ident],
        )
        print("1000-character truncation ok", flush=True)


def test_term_split_by_the_1000_character_cut_matches_its_kept_prefix():
    """A term that crosses the 1000-character cut still matches on what remains.

    Truncation keeps the first 1000 characters and then splits that prefix.
    The cut falls inside one term. The concept whose title is exactly the
    part that remains is a hit. The concept whose title is only the
    characters past the cut is not. The same pair is searched on the
    command line, on human output with structured output not requested,
    and on the search tool. On that human cut, the kept concept's identity
    sits after its governance badge. A short query for each title shows
    that title is a real hit when the cut is not involved.
    """
    with workspace() as ws:
        kept, discarded = unique_compact("kept", "tail")
        prefix_id, tail_id, typ, prefix_desc, tail_desc, body = unique_tokens(
            "kp", "tl", "typ", "pds", "tds", "bod"
        )
        assert not prefix_id.startswith("convention/")
        assert not tail_id.startswith("convention/")
        assert prefix_id not in tail_id and tail_id not in prefix_id
        query = query_cut_inside_one_term(kept, discarded)
        assert len(query) > 1000
        assert query[:1000].endswith(kept)
        assert query[1000:] == discarded
        assert query[1000 - len(kept) - 1] == " "
        assert (kept + discarded) in query
        assert kept not in query.split()
        field_tokens_do_not_start_with(
            kept,
            prefix_id,
            tail_id,
            typ,
            prefix_desc,
            tail_desc,
            body,
            discarded,
        )
        field_tokens_do_not_start_with(
            discarded,
            prefix_id,
            tail_id,
            typ,
            prefix_desc,
            tail_desc,
            body,
            kept,
        )
        rel = _kb()
        # The concept that must not hit on the cut query is written first.
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    tail_id,
                    concept_type=typ,
                    title=discarded,
                    description=tail_desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    prefix_id,
                    concept_type=typ,
                    title=kept,
                    description=prefix_desc,
                    body=f"{body}\n",
                ),
            ],
        )

        kept_only = require_search_structured_success(
            run_search(ws, kept, rel, structured=True)
        )
        assert kept_only and identity_in_records(kept_only, prefix_id)
        assert not identity_in_records(kept_only, tail_id)
        assert len(kept_only) == 1

        discarded_only = require_search_structured_success(
            run_search(ws, discarded, rel, structured=True)
        )
        assert discarded_only and identity_in_records(discarded_only, tail_id)
        assert not identity_in_records(discarded_only, prefix_id)
        assert len(discarded_only) == 1

        cut_records = require_search_structured_success(
            run_search(ws, query, rel, structured=True)
        )
        assert cut_records and identity_in_records(cut_records, prefix_id), (
            "structured search dropped the term the 1000-character cut "
            f"splits; kept prefix {kept!r} was not a hit"
        )
        assert not identity_in_records(cut_records, tail_id), (
            "structured search matched the characters past the "
            f"1000-character cut: {discarded!r}"
        )
        assert len(cut_records) == 1

        human_kept = require_search_success(run_search(ws, kept, rel))
        assert_identifiable_human_hits(
            human_kept, [("context", (prefix_id, kept, prefix_desc))]
        )
        require_human_identity_absent(human_kept, tail_id)

        human_discarded = require_search_success(run_search(ws, discarded, rel))
        assert_identifiable_human_hits(
            human_discarded, [("context", (tail_id, discarded, tail_desc))]
        )
        require_human_identity_absent(human_discarded, prefix_id)

        human_cut = require_search_success(run_search(ws, query, rel))
        assert_human_concept_identity_after_badge(
            human_cut, "context", prefix_id, query=query
        )
        # The concept whose title is only the characters past the
        # 1000-character cut is not a human hit.
        require_human_identity_absent(human_cut, tail_id)

        tool_kept = require_mcp_search_success(
            mcp_search(ws, query=kept, bundle=rel)
        )
        assert tool_kept and identity_in_records(tool_kept, prefix_id)
        assert not identity_in_records(tool_kept, tail_id)
        assert len(tool_kept) == 1

        tool_discarded = require_mcp_search_success(
            mcp_search(ws, query=discarded, bundle=rel)
        )
        assert tool_discarded and identity_in_records(tool_discarded, tail_id)
        assert not identity_in_records(tool_discarded, prefix_id)
        assert len(tool_discarded) == 1

        tool_cut = require_mcp_search_success(
            mcp_search(ws, query=query, bundle=rel)
        )
        assert tool_cut and identity_in_records(tool_cut, prefix_id), (
            "search tool dropped the term the 1000-character cut splits; "
            f"kept prefix {kept!r} was not a hit"
        )
        assert not identity_in_records(tool_cut, tail_id), (
            "search tool matched the characters past the 1000-character cut: "
            f"{discarded!r}"
        )
        assert len(tool_cut) == 1
        print("cut inside one term keeps the prefix ok", flush=True)


def test_term_at_position_1000_matches_and_exact_1000_is_not_cut():
    """The character at position 1000 is matched, and length 1000 is not cut.

    A splitter sits immediately before position 1000. The concept whose
    title is exactly the term that begins there is a hit. A query of
    length exactly 1000 whose last character is that same term is also a
    hit. Both queries are searched on the command line, on human output
    with structured output not requested, and on the search tool. Human
    output identifies the concept by its identity, which neither query
    contains. A window of 999 characters ends on the splitter and does
    not contain the term.
    """
    with workspace() as ws:
        ident, decoy, typ, desc, decoy_desc, body = unique_tokens(
            "id", "dy", "typ", "dsc", "ddc", "bod"
        )
        decoy_title = compact_token("dti")
        assert not ident.startswith("convention/")
        assert not decoy.startswith("convention/")
        assert ident not in decoy and decoy not in ident
        term = term_character_outside_fixture_prefixes(
            ident,
            decoy,
            typ,
            desc,
            decoy_desc,
            body,
            decoy_title,
        )
        exact, longer = queries_with_term_starting_at_position_1000(term)
        assert len(exact) == 1000
        assert exact[-1] == term
        assert len(longer) > 1000
        assert longer[998] == " "
        assert longer[999] == term
        assert longer[:1000] == exact
        assert term not in exact[:999] and term not in longer[:999]
        assert ident not in exact and ident not in longer
        assert decoy not in exact and decoy not in longer
        field_tokens_do_not_start_with(
            term,
            ident,
            decoy,
            typ,
            desc,
            decoy_desc,
            body,
            decoy_title,
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    decoy,
                    concept_type=typ,
                    title=decoy_title,
                    description=decoy_desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )

        alone = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        assert alone and identity_in_records(alone, ident)
        assert not identity_in_records(alone, decoy)
        assert len(alone) == 1

        def _structured_boundary(query: str, label: str) -> None:
            records = require_search_structured_success(
                run_search(ws, query, rel, structured=True)
            )
            assert records and identity_in_records(records, ident), (
                f"structured search dropped the term at position 1000 "
                f"on the {label} query: {term!r}"
            )
            assert not identity_in_records(records, decoy), (
                f"structured search hit the other concept on the {label} query"
            )
            assert len(records) == 1

        _structured_boundary(longer, "longer-than-1000")
        _structured_boundary(exact, "exactly-1000")

        def _human_boundary(query: str, label: str) -> None:
            report = require_search_success(run_search(ws, query, rel))
            assert_human_concept_identity_after_badge(
                report, "context", ident, query=query
            )
            # The other concept is not a human hit on this query.
            require_human_identity_absent(report, decoy)

        _human_boundary(longer, "longer-than-1000")
        _human_boundary(exact, "exactly-1000")

        def _tool_boundary(query: str, label: str) -> None:
            records = require_mcp_search_success(
                mcp_search(ws, query=query, bundle=rel)
            )
            assert records and identity_in_records(records, ident), (
                f"search tool dropped the term at position 1000 "
                f"on the {label} query: {term!r}"
            )
            assert not identity_in_records(records, decoy), (
                f"search tool hit the other concept on the {label} query"
            )
            assert len(records) == 1

        _tool_boundary(longer, "longer-than-1000")
        _tool_boundary(exact, "exactly-1000")
        print("position 1000 term and exact 1000 query ok", flush=True)


def test_query_cap_is_characters_not_bytes():
    """The 1000 cut is characters: a head term still hits, a tail term does not.

    A head of 600 non-ASCII letters is under 1000 characters and over 1000
    bytes, so the tail term still matches. A head of 1001 of those letters
    puts the tail term past the cut. Human output, with structured output
    not requested, uses that same pair: the shorter head still presents the
    concept identity, which neither query contains, and the longer head is
    a miss that does not present the concept.
    """
    with workspace() as ws:
        term = compact_token("cjk")
        ident, other, typ, desc, body, otitle = unique_tokens(
            "id", "oid", "typ", "dsc", "bod", "ott"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    other,
                    concept_type=typ,
                    title=otitle,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        over = ("文" * 1001) + " " + term
        assert len(over) > 1000
        assert len(over.encode("utf-8")) > len(over)
        assert over[:1000] == "文" * 1000
        assert term not in over[:1000]
        assert ident not in over and other not in over
        zero = run_search(ws, over, rel, structured=True)
        require_zero_hits_success(zero, structured=True, live_identities=[ident, other])
        zero_records = require_search_structured_success(zero)
        assert not identity_in_records(zero_records, ident)
        inside = term + " " + ("y" * 1000)
        assert len(inside) > 1000
        assert term in inside[:1000]
        kept = require_search_structured_success(
            run_search(ws, inside, rel, structured=True)
        )
        assert identity_in_records(kept, ident)
        assert not identity_in_records(kept, other)
        under = ("文" * 600) + " " + term
        assert len(under.encode("utf-8")) > 1000
        assert len(under) < 1000
        assert term in under[:1000]
        assert ident not in under and other not in under
        assert not ident.startswith("convention/")
        hits = require_search_structured_success(
            run_search(ws, under, rel, structured=True)
        )
        assert identity_in_records(hits, ident)
        assert not identity_in_records(hits, other)
        # Same pair, human output, structured output not requested.
        # A 1000-byte cut drops the tail on the shorter head; a
        # 1000-character cut keeps it and drops it only on the longer head.
        human_kept = require_search_success(run_search(ws, under, rel))
        assert_human_concept_identity_after_badge(
            human_kept, "context", ident, query=under
        )
        require_human_identity_absent(human_kept, other)
        human_tail = require_zero_hits_success(
            run_search(ws, over, rel),
            structured=False,
            live_identities=[ident, other],
        )
        require_human_identity_absent(human_tail, ident)
        require_human_identity_absent(human_tail, other)
        assert_human_zero_hit_miss_statement(
            human_tail,
            human_kept,
            path_tokens_for_search(rel, ws.path),
            (ident, other, typ, term, otitle, desc, body, over, under),
            live_identities=[ident, other],
        )
        print("character not byte cap ok", flush=True)


def test_only_the_first_50_terms_are_used():
    """Term 51 is ignored; the 50th term and term 1 still match.

    Structured output is a separate request. The same three queries on human
    output, with structured output not requested, still use only the first
    50 terms: term 1 and term 50 each carry the concept identity after the
    governance badge, and term 51 is a miss that does not present the
    concept. The same holds when the terms are joined by a mark other than
    space.

    Splitting is every non-letter non-digit, not spaces alone. The same
    three positions are searched again with the terms joined by a mark
    that is not a space and is outside the joiners already used to split
    two terms. That query is one whitespace word and at most 1000
    characters, so keeping the first 50 whitespace-separated words and
    then splitting those words still sees term 51.
    """
    with workspace() as ws:
        term = compact_token("late")
        ident, typ, desc, body = unique_tokens("id", "typ", "dsc", "bod")
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        dummies = [f"q{i:02d}" for i in range(50)]
        tail_query = " ".join(dummies + [term])
        kept_query = " ".join(dummies[:49] + [term])
        first_query = " ".join([term] + dummies)
        assert tail_query.split()[:50] == dummies
        assert term not in tail_query.split()[:50]
        assert kept_query.split()[:50][-1] == term
        assert first_query.split()[0] == term
        assert ident not in tail_query and ident not in kept_query
        assert ident not in first_query
        dropped = run_search(ws, tail_query, rel, structured=True)
        require_zero_hits_success(dropped, structured=True, live_identities=[ident])
        kept50 = require_search_structured_success(
            run_search(ws, kept_query, rel, structured=True)
        )
        assert identity_in_records(kept50, ident)
        first = require_search_structured_success(
            run_search(ws, first_query, rel, structured=True)
        )
        assert identity_in_records(first, ident)
        human_kept = require_search_success(run_search(ws, kept_query, rel))
        assert_human_concept_identity_after_badge(
            human_kept, "context", ident, query=kept_query
        )
        human_first = require_search_success(run_search(ws, first_query, rel))
        assert_human_concept_identity_after_badge(
            human_first, "context", ident, query=first_query
        )
        human_tail = require_zero_hits_success(
            run_search(ws, tail_query, rel),
            structured=False,
            live_identities=[ident],
        )
        require_human_identity_absent(human_tail, ident)
        assert_human_zero_hit_miss_statement(
            human_tail,
            human_kept,
            path_tokens_for_search(rel, ws.path),
            (ident, typ, term, desc, body, tail_query, kept_query, first_query),
            live_identities=[ident],
        )
        # One non-space joiner, including the mark outside the closed set.
        # No whitespace, so a whitespace-word cap does not drop term 51.
        already = (",", "-", ".", "_", "/")
        mark = term_splitter_outside_closed_set()
        assert len(mark) == 1
        assert not mark.isalnum()
        assert not mark.isspace()
        assert mark not in already and mark != " "
        assert all(mark not in piece and piece.isalnum() for piece in (*dummies, term))
        assert all(dummy not in term and not term.startswith(dummy) for dummy in dummies)
        mark_tail = space_free_joined_terms([*dummies, term], mark)
        mark_kept = space_free_joined_terms([*dummies[:49], term], mark)
        mark_first = space_free_joined_terms([term, *dummies], mark)
        assert len(mark_tail) <= 1000 and len(mark_kept) <= 1000
        assert len(mark_first) <= 1000
        assert len(mark_tail.split()) == 1
        assert len(mark_kept.split()) == 1
        assert len(mark_first.split()) == 1
        assert mark_tail.split(mark)[:50] == dummies
        assert term not in mark_tail.split(mark)[:50]
        assert mark_kept.split(mark)[:50][-1] == term
        assert mark_first.split(mark)[0] == term
        assert ident not in mark_tail and ident not in mark_kept
        assert ident not in mark_first
        mark_dropped = run_search(ws, mark_tail, rel, structured=True)
        require_zero_hits_success(
            mark_dropped, structured=True, live_identities=[ident]
        )
        mark_kept50 = require_search_structured_success(
            run_search(ws, mark_kept, rel, structured=True)
        )
        assert identity_in_records(mark_kept50, ident)
        mark_first_hits = require_search_structured_success(
            run_search(ws, mark_first, rel, structured=True)
        )
        assert identity_in_records(mark_first_hits, ident)
        human_mark_kept = require_search_success(run_search(ws, mark_kept, rel))
        assert_human_concept_identity_after_badge(
            human_mark_kept, "context", ident, query=mark_kept
        )
        human_mark_first = require_search_success(run_search(ws, mark_first, rel))
        assert_human_concept_identity_after_badge(
            human_mark_first, "context", ident, query=mark_first
        )
        human_mark_tail = require_zero_hits_success(
            run_search(ws, mark_tail, rel),
            structured=False,
            live_identities=[ident],
        )
        require_human_identity_absent(human_mark_tail, ident)
        assert_human_zero_hit_miss_statement(
            human_mark_tail,
            human_mark_kept,
            path_tokens_for_search(rel, ws.path),
            (
                ident,
                typ,
                term,
                desc,
                body,
                tail_query,
                kept_query,
                first_query,
                mark_tail,
                mark_kept,
                mark_first,
            ),
            live_identities=[ident],
        )
        print("first 50 terms ok", flush=True)


def test_mcp_query_longer_than_1000_characters_drops_the_tail_term():
    """MCP drops a distinctive term that sits after the 1000-character cut."""
    with workspace() as ws:
        term = compact_token("md1k")
        ident, typ, desc, body = unique_tokens("id", "typ", "dsc", "bod")
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        live = require_mcp_search_success(mcp_search(ws, query=term, bundle=rel))
        assert identity_in_records(live, ident)
        truncated = require_mcp_search_success(
            mcp_search(ws, query=("x" * 1000 + " " + term), bundle=rel)
        )
        assert not identity_in_records(truncated, ident)
        control = require_mcp_search_success(
            mcp_search(ws, query=(term + " " + ("x" * 1000)), bundle=rel)
        )
        assert identity_in_records(control, ident)
        print("MCP 1000-character truncation ok", flush=True)


def test_mcp_query_cap_is_characters_not_bytes():
    """The search tool cuts at 1000 characters, not 1000 bytes.

    A head of 600 non-ASCII letters is under 1000 characters and over 1000
    bytes, so the tail term still matches. A head of 1001 of those letters
    puts the tail term past the cut, so that concept is not a hit.
    """
    with workspace() as ws:
        term = compact_token("mcjk")
        ident, other, typ, desc, body, otitle = unique_tokens(
            "id", "oid", "typ", "dsc", "bod", "ott"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    other,
                    concept_type=typ,
                    title=otitle,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        live = require_mcp_search_success(mcp_search(ws, query=term, bundle=rel))
        assert identity_in_records(live, ident)
        assert not identity_in_records(live, other)
        over = ("文" * 1001) + " " + term
        assert len(over) > 1000
        assert term not in over[:1000]
        dropped = require_mcp_search_success(
            mcp_search(ws, query=over, bundle=rel)
        )
        assert not dropped, (
            "search tool kept hits for a query whose distinctive term "
            f"begins only after 1000 characters: {dropped!r}"
        )
        assert not identity_in_records(dropped, ident)
        under = ("文" * 600) + " " + term
        assert len(under.encode("utf-8")) > 1000
        assert len(under) < 1000
        assert term in under[:1000]
        hits = require_mcp_search_success(
            mcp_search(ws, query=under, bundle=rel)
        )
        assert identity_in_records(hits, ident)
        assert not identity_in_records(hits, other)
        print("MCP character not byte cap ok", flush=True)


def test_mcp_only_the_first_50_terms_are_used():
    """MCP ignores term 51 and still hits when the distinctive term is among the first 50.

    The same cap holds when the terms are joined by a non-space mark
    outside the joiners already used to split two terms. That query is
    one whitespace word and at most 1000 characters.
    """
    with workspace() as ws:
        term = compact_token("mlate")
        ident, typ, desc, body = unique_tokens("id", "typ", "dsc", "bod")
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        dummies = [f"q{i:02d}" for i in range(50)]
        dropped = require_mcp_search_success(
            mcp_search(ws, query=" ".join(dummies + [term]), bundle=rel)
        )
        assert not identity_in_records(dropped, ident)
        kept = require_mcp_search_success(
            mcp_search(ws, query=" ".join(dummies[:49] + [term]), bundle=rel)
        )
        assert identity_in_records(kept, ident)
        already = (",", "-", ".", "_", "/")
        mark = term_splitter_outside_closed_set()
        assert len(mark) == 1
        assert not mark.isalnum()
        assert not mark.isspace()
        assert mark not in already and mark != " "
        assert all(mark not in piece and piece.isalnum() for piece in (*dummies, term))
        assert all(dummy not in term and not term.startswith(dummy) for dummy in dummies)
        mark_tail = space_free_joined_terms([*dummies, term], mark)
        mark_kept = space_free_joined_terms([*dummies[:49], term], mark)
        assert len(mark_tail) <= 1000 and len(mark_kept) <= 1000
        assert len(mark_tail.split()) == 1 and len(mark_kept.split()) == 1
        assert mark_tail.split(mark)[:50] == dummies
        assert term not in mark_tail.split(mark)[:50]
        assert mark_kept.split(mark)[-1] == term
        mark_dropped = require_mcp_search_success(
            mcp_search(ws, query=mark_tail, bundle=rel)
        )
        assert not mark_dropped, (
            "search tool kept hits for a space-free query whose distinctive "
            f"term is term 51: {mark_dropped!r}"
        )
        assert not identity_in_records(mark_dropped, ident)
        mark_kept_hits = require_mcp_search_success(
            mcp_search(ws, query=mark_kept, bundle=rel)
        )
        assert identity_in_records(mark_kept_hits, ident)
        print("MCP first 50 terms ok", flush=True)


# ---------------------------------------------------------------------------
# Query and path on the same call. Closed keyword-only cuts and closed
# path-only caps stay above; they never supply both inputs together.
# ---------------------------------------------------------------------------

_BOTH_SURFACES = ("command-structured", "command-human", "tool")
# Caps the closed path-only ceiling already requests. A combined call that
# reuses one of these values does not show the ceiling on a query plus a path.
_CLOSED_PATH_ONLY_ABOVE_100 = frozenset({101, SAMPLE_BIG_CAP})


def _search_query_and_path(ws, query, bundle, path, surface, limit=None):
    """One search that supplies both a query and a path on *surface*."""
    if surface == "command-structured":
        return require_search_structured_success(
            run_search(
                ws,
                query,
                bundle,
                for_path=path,
                limit=limit,
                structured=True,
            )
        )
    if surface == "command-human":
        return require_search_success(
            run_search(ws, query, bundle, for_path=path, limit=limit)
        )
    if surface == "tool":
        return require_mcp_search_success(
            mcp_search(
                ws,
                query=query,
                for_path=path,
                bundle=bundle,
                limit=limit,
            )
        )
    raise AssertionError(f"unknown search surface {surface!r}")


def _assert_combined_path_fields(
    surface,
    observation,
    identity,
    cohort,
    strip,
    keyword_fields,
):
    """The path hit names code_refs and exactly *keyword_fields*."""
    expected = frozenset(keyword_fields)
    if surface == "command-human":
        found = assert_human_path_hit_reports(
            observation,
            identity,
            keyword_fields,
            cohort=cohort,
            strip_texts=strip,
        )
    else:
        found = assert_path_hit_reports(
            record_for_identity(observation, identity),
            strip,
            keyword_fields,
        )
    assert found == expected, (
        f"{surface} path hit {identity!r} named {sorted(found)!r}, "
        f"not {sorted(expected)!r}"
    )


def _query_with_term_after_1000(kept: str, cut: str) -> str:
    """ASCII query whose second term begins only after 1000 characters."""
    if (
        not kept
        or not cut
        or not kept.isalnum()
        or not cut.isalnum()
        or kept in cut
        or cut in kept
    ):
        raise AssertionError(
            f"kept and cut terms must be distinct alphanumeric tokens: "
            f"{kept!r} / {cut!r}"
        )
    pad = 1000 - len(kept) - 1
    if pad < 1:
        raise AssertionError(f"kept term {kept!r} leaves no room before the cut")
    query = kept + " " + ("x" * pad) + " " + cut
    if len(query) <= 1000 or query[:1000] != kept + " " + ("x" * pad):
        raise AssertionError("1000-character window was not built from the kept term")
    if cut in query[:1000] or query[1000:] != " " + cut:
        raise AssertionError(
            f"cut term {cut!r} does not begin only after character 1000"
        )
    return query


def _fifty_term_query(kept: str, cut: str) -> tuple[str, str]:
    """51 terms joined by a non-space mark. *cut* is term 51. *kept* is earlier.

    The query is one whitespace word and at most 1000 characters, so a
    1000-character cut is not what drops term 51, and keeping the first
    50 whitespace-separated words still holds term 51.
    """
    mark = term_splitter_outside_closed_set()
    if len(mark) != 1 or mark.isalnum() or mark.isspace() or mark == " ":
        raise AssertionError(f"term joiner {mark!r} is not a non-space splitter")
    tag = compact_token("z")[-6:]
    if not tag.isalnum() or len(tag) != 6:
        raise AssertionError(f"term tag {tag!r} is not 6 alphanumeric characters")
    dummies = [f"d{i:02d}{tag}" for i in range(49)]
    if kept in dummies or cut in dummies or kept == cut:
        raise AssertionError("kept, cut, and filler terms are not distinct")
    terms = [*dummies, kept, cut]
    if any(not part.isalnum() for part in terms):
        raise AssertionError("a 51-term query term is not alphanumeric")
    query = space_free_joined_terms(terms, mark)
    parts = query.split(mark)
    if (
        len(query) > 1000
        or len(query.split()) != 1
        or parts != terms
        or cut in parts[:50]
        or kept not in parts[:50]
    ):
        raise AssertionError(
            "51-term query is not one short whitespace word whose 51st "
            f"term is the cut term: {query!r}"
        )
    for part in parts[:50]:
        if part == kept:
            continue
        if (
            cut.startswith(part)
            or part.startswith(cut)
            or kept.startswith(part)
            or part.startswith(kept)
        ):
            raise AssertionError(
                f"filler term {part!r} shares a prefix with a planted title"
            )
    return query, mark


def _write_shared_title_path_hits(ws, count: int):
    """*count* concepts, one title term, one path, context, later identity first.

    Path order is identity ascending: governance and the combined score tie.
    The title term is the query. It is not a token of the identity, the
    path, or the filler fields.
    """
    if count < 3:
        raise AssertionError(f"shared path bundle needs at least 3 concepts, got {count}")
    term = compact_token("bq")
    ids = numbered_identities(count, compact_token("bi"))
    path_dir = compact_token("bp")
    path = f"pkg/{path_dir}/x.go"
    typ, desc, body = unique_tokens("typ", "dsc", "bod")
    field_tokens_do_not_start_with(term, *ids, path, path_dir, typ, desc, body)
    for ident in ids:
        if ident in desc or ident in body or ident in typ or ident in path or ident in term:
            raise AssertionError(
                f"identity {ident!r} sits inside another planted string"
            )
    rel = _kb()
    write_concepts_later_first(
        ws,
        rel,
        [
            search_concept_spec(
                ident,
                concept_type=typ,
                title=term,
                description=desc,
                body=f"{body}\n",
                governance="context",
                code_refs=[path],
            )
            for ident in ids
        ],
    )
    return rel, path, term, ids


def _assert_combined_cap(surface, observation, kept, withheld, *, above=None, planted=None):
    """Returned hits are the path-order prefix *kept*, and *withheld* are absent."""
    if surface == "command-human":
        ordered = require_human_ranked_prefix(observation, kept, withheld)
    elif above is not None:
        ordered = require_cap_above_100_returns_at_most_100(
            observation,
            kept,
            requested_cap=above,
            planted=planted,
            surface=surface,
        )
        for ident in withheld:
            assert not identity_in_records(observation, ident), (
                f"{surface} cap {above} still returned {ident!r}"
            )
    else:
        ordered = require_identity_order(observation, kept)
    assert ordered == list(kept), (
        f"{surface} returned {ordered!r}, not the path-order prefix {list(kept)!r}"
    )
    assert len(ordered) <= len(kept)


@pytest.mark.parametrize("surface", _BOTH_SURFACES)
def test_query_and_path_truncate_to_1000_characters_before_matching(surface):
    """A query and a path together still truncate the query to 1000 characters.

    Both concepts match the path. One title is a term inside the first
    1000 characters. The other title is a term that begins only after
    that cut. The cut hit names code_refs and not title. The kept hit
    names code_refs and title. Dropping every keyword field fails the
    kept hit. Matching the cut term fails the cut hit. The closed
    keyword-only cut does not pass this call.
    """
    with workspace() as ws:
        kept, cut, ident_kept, ident_cut, typ, desc, body, path_dir = unique_compact(
            "kp", "ct", "ik", "ic", "ty", "ds", "bd", "pd"
        )
        assert not ident_kept.startswith("convention/")
        assert not ident_cut.startswith("convention/")
        path = f"pkg/{path_dir}/x.go"
        query = _query_with_term_after_1000(kept, cut)
        field_tokens_do_not_start_with(
            kept, ident_kept, ident_cut, typ, desc, body, cut, path, path_dir
        )
        field_tokens_do_not_start_with(
            cut, ident_kept, ident_cut, typ, desc, body, kept, path, path_dir
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident_cut,
                    concept_type=typ,
                    title=cut,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                ),
                search_concept_spec(
                    ident_kept,
                    concept_type=typ,
                    title=kept,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                ),
            ],
        )
        cohort = [ident_kept, ident_cut]
        strip = [
            kept,
            cut,
            ident_kept,
            ident_cut,
            typ,
            desc,
            body,
            path,
            path_dir,
            query,
        ]
        observation = _search_query_and_path(ws, query, rel, path, surface)
        _assert_combined_path_fields(
            surface, observation, ident_cut, cohort, strip, []
        )
        _assert_combined_path_fields(
            surface, observation, ident_kept, cohort, strip, ["title"]
        )
        print(f"query+path 1000-character cut on {surface}", flush=True)


@pytest.mark.parametrize("surface", _BOTH_SURFACES)
def test_query_and_path_use_at_most_the_first_50_terms(surface):
    """A query and a path together still use only the first 50 terms.

    The terms are joined by a character that is not a letter, a digit,
    or a space, so the query is one whitespace word. Term 51 is the only
    title of one path hit. A term among the first 50 is the title of the
    other path hit. The 51st hit names code_refs and not title. The kept
    hit names code_refs and title.
    """
    with workspace() as ws:
        tag = compact_token("z")[-6:]
        kept = f"k{tag}"
        cut = f"c{tag}"
        ident_kept, ident_cut, typ, desc, body, path_dir = unique_compact(
            "ik", "ic", "ty", "ds", "bd", "pd"
        )
        assert not ident_kept.startswith("convention/")
        assert not ident_cut.startswith("convention/")
        path = f"pkg/{path_dir}/x.go"
        query, mark = _fifty_term_query(kept, cut)
        assert mark != " "
        parts = query.split(mark)
        assert len(parts) == 51 and parts[-1] == cut and kept in parts[:50]
        field_tokens_do_not_start_with(
            kept, ident_kept, ident_cut, typ, desc, body, cut, path, path_dir
        )
        field_tokens_do_not_start_with(
            cut, ident_kept, ident_cut, typ, desc, body, kept, path, path_dir
        )
        for part in parts[:50]:
            if part == kept:
                continue
            field_tokens_do_not_start_with(
                part, ident_kept, ident_cut, typ, desc, body, kept, cut, path, path_dir
            )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident_cut,
                    concept_type=typ,
                    title=cut,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                ),
                search_concept_spec(
                    ident_kept,
                    concept_type=typ,
                    title=kept,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                ),
            ],
        )
        cohort = [ident_kept, ident_cut]
        strip = [
            kept,
            cut,
            ident_kept,
            ident_cut,
            typ,
            desc,
            body,
            path,
            path_dir,
            query,
            mark,
            *parts,
        ]
        observation = _search_query_and_path(ws, query, rel, path, surface)
        _assert_combined_path_fields(
            surface, observation, ident_cut, cohort, strip, []
        )
        _assert_combined_path_fields(
            surface, observation, ident_kept, cohort, strip, ["title"]
        )
        print(f"query+path first 50 terms on {surface}", flush=True)


@pytest.mark.parametrize("surface", _BOTH_SURFACES)
def test_query_and_path_omit_or_non_positive_cap_returns_at_most_10(surface):
    """Omitting the cap, or passing a non-positive cap, returns at most 10.

    More than 10 concepts match both the query and the path. The hits
    that come back are the first 10 in path order. A later identity is
    absent. The closed path-only cap does not pass this call.
    """
    with workspace() as ws:
        rel, path, term, ids = _write_shared_title_path_hits(ws, 15)
        assert len(ids) > 10
        kept = ids[:10]
        withheld = ids[10:]
        for limit in (None, 0, -5):
            observation = _search_query_and_path(
                ws, term, rel, path, surface, limit=limit
            )
            _assert_combined_cap(surface, observation, kept, withheld)
        print(f"query+path omit and non-positive cap on {surface}", flush=True)


@pytest.mark.parametrize("surface", _BOTH_SURFACES)
def test_query_and_path_cap_3_returns_at_most_3_in_path_order(surface):
    """A cap of 3 on a query plus a path returns at most 3 hits, in path order.

    More than 3 concepts match both. The hits are the first 3 identities.
    A later identity is absent.
    """
    with workspace() as ws:
        rel, path, term, ids = _write_shared_title_path_hits(ws, 15)
        assert len(ids) > 3
        observation = _search_query_and_path(
            ws, term, rel, path, surface, limit=3
        )
        _assert_combined_cap(surface, observation, ids[:3], ids[3:])
        print(f"query+path cap 3 on {surface}", flush=True)


@pytest.mark.parametrize("surface", _BOTH_SURFACES)
def test_query_and_path_cap_above_100_returns_at_most_100(surface):
    """A cap above 100 on a query plus a path returns at most 100, in path order.

    The requested cap is above 100 and is not a value the closed
    path-only ceiling already requests. More than 100 concepts match
    both the query and the path. The hits are the first 100 identities.
    """
    with workspace() as ws:
        rel, path, term, ids = _write_shared_title_path_hits(ws, 120)
        assert len(ids) > 100
        requested = 250
        assert requested > 100 and requested not in _CLOSED_PATH_ONLY_ABOVE_100
        observation = _search_query_and_path(
            ws, term, rel, path, surface, limit=requested
        )
        _assert_combined_cap(
            surface,
            observation,
            ids[:100],
            ids[100:],
            above=requested,
            planted=len(ids),
        )
        print(f"query+path cap {requested} on {surface}", flush=True)


# ---------------------------------------------------------------------------
# I. Path-bound code_refs matching
# ---------------------------------------------------------------------------


def test_exact_code_ref_matches_slash_normalized_path_including_dot_slash_and_leading_slash():
    """Exact path, ./ on ref or path, and leading / on the path or the stored ref still hit."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[SAMPLE_FILE],
                )
            ],
        )
        for path in (
            SAMPLE_FILE,
            "./" + SAMPLE_FILE,
            "/" + SAMPLE_FILE,
        ):
            records = require_search_structured_success(
                run_search(ws, None, rel, for_path=path, structured=True)
            )
            assert identity_in_records(records, ident), (
                f"exact path {path!r} missed relative code_ref"
            )
        ident2, title2 = unique_tokens("id2", "ttl2")
        rel2 = _kb()
        write_bundle(
            ws,
            rel2,
            [
                search_concept_spec(
                    ident2,
                    concept_type=typ,
                    title=title2,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=["./" + SAMPLE_FILE],
                )
            ],
        )
        records2 = require_search_structured_success(
            run_search(
                ws, None, rel2, for_path=SAMPLE_FILE, structured=True
            )
        )
        assert identity_in_records(records2, ident2)
        # A stored ref that itself begins with / is the same path as the bare
        # relative caller path. Stripping / only from the caller, and ./ only
        # from stored refs, leaves this ref unmatched.
        slash_ident, slash_title = unique_tokens("ids", "ttls")
        twin_ident, twin_title = unique_tokens("idt", "ttlt")
        twin_leaf = compact_token("leaf")
        public_bare = SAMPLE_FILE
        twin_bare = f"{twin_leaf}/widget.go"
        rel3 = _kb()
        write_bundle(
            ws,
            rel3,
            [
                search_concept_spec(
                    slash_ident,
                    concept_type=typ,
                    title=slash_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=["/" + public_bare],
                ),
                search_concept_spec(
                    twin_ident,
                    concept_type=typ,
                    title=twin_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=["/" + twin_bare],
                ),
            ],
        )
        for bare, hit_ident, miss_ident in (
            (public_bare, slash_ident, twin_ident),
            (twin_bare, twin_ident, slash_ident),
        ):
            stored_hits = require_search_structured_success(
                run_search(ws, None, rel3, for_path=bare, structured=True)
            )
            assert identity_in_records(stored_hits, hit_ident), (
                f"bare path {bare!r} missed a code_ref that begins with /"
            )
            assert not identity_in_records(stored_hits, miss_ident), (
                f"bare path {bare!r} kept a code_ref for a different path"
            )
        print("exact slash-normalized path ok", flush=True)


def test_absolute_path_still_matches_relative_code_ref():
    """A workspace-absolute path still matches a relative code_ref.

    The fixed probe stays on the command line. A generated relative ref
    is searched as a longer filesystem-absolute path (the workspace
    directory plus that ref) on the command and on the search tool. A
    second concept whose relative ref is a different generated path is
    omitted, and the two absolute paths swap which concept hits. The
    command-line pair and the tool's stored-leading-slash check stay.
    """
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[SAMPLE_FILE],
                )
            ],
        )
        abs_path = abs_workspace_path(ws, SAMPLE_FILE)
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=abs_path, structured=True)
        )
        assert identity_in_records(records, ident), (
            f"absolute path {abs_path!r} missed relative code_ref"
        )
        # A longer absolute caller against a generated relative ref. Stripping
        # one leading slash, and treating a longer absolute path as a match
        # only when the stored ref is the fixed probe, leaves this ref
        # unmatched.
        probe = generated_filesystem_absolute_relative_probe()
        hit_ident, miss_ident = unique_tokens("idh", "idm")
        rel_gen = _kb()
        write_bundle(
            ws,
            rel_gen,
            [
                search_concept_spec(
                    hit_ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.relative_ref],
                ),
                search_concept_spec(
                    miss_ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.other_ref],
                ),
            ],
        )
        abs_hit = longer_filesystem_absolute_caller(
            ws, probe.relative_ref, absent_refs=(probe.other_ref,)
        )
        abs_other = longer_filesystem_absolute_caller(
            ws, probe.other_ref, absent_refs=(probe.relative_ref,)
        )
        assert probe.relative_ref != SAMPLE_FILE
        assert probe.other_ref != SAMPLE_FILE
        assert abs_hit.endswith("/" + probe.relative_ref)
        assert abs_hit[1:] != probe.relative_ref
        assert not abs_hit.endswith("/" + probe.other_ref)
        assert abs_other.endswith("/" + probe.other_ref)
        assert abs_other[1:] != probe.other_ref
        hit_records = require_search_structured_success(
            run_search(ws, None, rel_gen, for_path=abs_hit, structured=True)
        )
        assert identity_in_records(hit_records, hit_ident), (
            f"absolute path {abs_hit!r} missed generated relative code_ref "
            f"{probe.relative_ref!r}"
        )
        assert not identity_in_records(hit_records, miss_ident), (
            f"absolute path {abs_hit!r} kept relative code_ref {probe.other_ref!r}"
        )
        other_records = require_search_structured_success(
            run_search(ws, None, rel_gen, for_path=abs_other, structured=True)
        )
        assert identity_in_records(other_records, miss_ident), (
            f"absolute path {abs_other!r} missed generated relative code_ref "
            f"{probe.other_ref!r}"
        )
        assert not identity_in_records(other_records, hit_ident), (
            f"absolute path {abs_other!r} kept relative code_ref "
            f"{probe.relative_ref!r}"
        )
        # Same generated pair on the search tool. The caller is the longer
        # filesystem-absolute path, not a bare relative path and not one
        # leading slash. Stripping only that slash, or matching the longer
        # path only on the command line, leaves the stored ref unmatched.
        # The command-line checks above and the tool's stored-leading-slash
        # check (bare relative caller) stay as they are.
        for caller, hit_ident_tool, miss_ident_tool, hit_ref, miss_ref in (
            (abs_hit, hit_ident, miss_ident, probe.relative_ref, probe.other_ref),
            (abs_other, miss_ident, hit_ident, probe.other_ref, probe.relative_ref),
        ):
            if not caller.startswith("/") or caller[1:] == hit_ref:
                raise AssertionError(
                    "search tool caller is not a longer filesystem-absolute path"
                )
            tool_records = require_mcp_search_success(
                mcp_search(ws, for_path=caller, bundle=rel_gen)
            )
            assert identity_in_records(tool_records, hit_ident_tool), (
                f"search tool absolute path {caller!r} missed generated "
                f"relative code_ref {hit_ref!r}"
            )
            assert not identity_in_records(tool_records, miss_ident_tool), (
                f"search tool absolute path {caller!r} kept relative code_ref "
                f"{miss_ref!r}"
            )
        print(
            f"absolute path matches generated relative ref {probe.relative_ref}",
            flush=True,
        )


def test_directory_prefix_code_ref_matches_nested_path_not_a_sibling_prefix():
    """A directory code_ref hits a path under it; a character-sibling ref does not.

    The fixed directory/character-sibling pair stays. A generated
    directory is stored, and the searched path sits two or more segments
    under it. The sibling ref shares those characters and is not a
    directory boundary.
    """
    with workspace() as ws:
        nested, sibling, typ, ntitle, stitle, desc, body = unique_tokens(
            "nid", "sid", "typ", "ntt", "stt", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    nested,
                    concept_type=typ,
                    title=ntitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[SAMPLE_PREFIX_DIR],
                ),
                search_concept_spec(
                    sibling,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[SAMPLE_SIBLING_DIR],
                ),
            ],
        )
        hit = require_search_structured_success(
            run_search(
                ws, None, rel, for_path=SAMPLE_FILE, structured=True
            )
        )
        assert identity_in_records(hit, nested)
        assert not identity_in_records(hit, sibling)
        miss = require_search_structured_success(
            run_search(
                ws, None, rel, for_path=SAMPLE_SIBLING_FILE, structured=True
            )
        )
        assert identity_in_records(miss, sibling)
        assert not identity_in_records(miss, nested)
        probe = generated_deep_directory_prefix_probe()
        if probe.segments_under < 2:
            raise AssertionError(
                "generated path is not two or more segments under the directory"
            )
        if probe.path_under_sibling[len(probe.directory_ref):len(probe.directory_ref) + 1] == "/":
            raise AssertionError(
                "sibling path is a directory boundary of the shorter ref"
            )
        gen_nested, gen_sibling, gtitle, gstitle = unique_tokens(
            "gn", "gs", "gnt", "gst"
        )
        rel_generated = _kb()
        write_bundle(
            ws,
            rel_generated,
            [
                search_concept_spec(
                    gen_nested,
                    concept_type=typ,
                    title=gtitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.directory_ref],
                ),
                search_concept_spec(
                    gen_sibling,
                    concept_type=typ,
                    title=gstitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.sibling_ref],
                ),
            ],
        )
        deep = require_search_structured_success(
            run_search(
                ws,
                None,
                rel_generated,
                for_path=probe.path_under_directory,
                structured=True,
            )
        )
        assert identity_in_records(deep, gen_nested), (
            "directory prefix missed a path two or more segments under it"
        )
        assert not identity_in_records(deep, gen_sibling), (
            "character-sibling ref matched a path that does not continue it"
        )
        beside = require_search_structured_success(
            run_search(
                ws,
                None,
                rel_generated,
                for_path=probe.path_under_sibling,
                structured=True,
            )
        )
        assert identity_in_records(beside, gen_sibling), (
            "sibling directory missed a path two or more segments under it"
        )
        assert not identity_in_records(beside, gen_nested), (
            "shorter ref matched a path that shares its characters "
            "without a directory boundary"
        )
        print(
            "directory prefix vs sibling prefix ok "
            f"segments_under={probe.segments_under}",
            flush=True,
        )


def test_single_segment_glob_star_does_not_cross_a_slash():
    """*.go hits a bare .go name, not <dir>/<name>; <dir>/*.go hits <dir>/<name>, not a deeper path.

    A runtime directory-scoped star is itself the hit for the file in that
    directory, and is not a hit for a path that would need the star to
    cross a slash. A star that is only part of one filename
    stem, ``{prefix}*.{ext}``, hits ``{prefix}{leaf}.{ext}`` and misses a
    path that would need that star to cross a slash.
    """
    with workspace() as ws:
        star, nested, anchor, typ, stitle, ntitle, desc, body = unique_tokens(
            "st", "nv", "an", "typ", "stt", "ntt", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    star,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=["*.go"],
                ),
                search_concept_spec(
                    nested,
                    concept_type=typ,
                    title=ntitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[SAMPLE_TOP_DIR + "/*.go"],
                ),
                search_concept_spec(
                    anchor,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[SAMPLE_NESTED_DIR + "/" + SAMPLE_BARE_GO],
                ),
            ],
        )
        foo = require_search_structured_success(
            run_search(ws, None, rel, for_path=SAMPLE_BARE_GO, structured=True)
        )
        assert identity_in_records(foo, star)
        assert not identity_in_records(foo, nested)
        assert not identity_in_records(foo, anchor)
        pkg_foo = require_search_structured_success(
            run_search(ws, None, rel, for_path=SAMPLE_TOP_DIR + "/" + SAMPLE_BARE_GO, structured=True)
        )
        assert not identity_in_records(pkg_foo, star), (
            "*.go crossed a slash onto pkg/foo.go"
        )
        assert identity_in_records(pkg_foo, nested)
        assert not identity_in_records(pkg_foo, anchor)
        deep = require_search_structured_success(
            run_search(ws, None, rel, for_path=SAMPLE_NESTED_DIR + "/" + SAMPLE_BARE_GO, structured=True)
        )
        assert identity_in_records(deep, anchor), (
            "exact code_ref was not a hit for the nested .go path"
        )
        assert not identity_in_records(deep, nested), (
            "<dir>/*.go crossed a slash onto the nested .go path"
        )
        assert not identity_in_records(deep, star)
        ext, leaf, scope, deeper = unique_compact("ext", "lf", "sc", "dp")
        scoped_ref = f"{scope}/*.{ext}"
        one_seg = f"{scope}/{leaf}.{ext}"
        crossed = f"{scope}/{deeper}/{leaf}.{ext}"
        if one_seg.count("/") != 1 or crossed.count("/") != 2:
            raise AssertionError(
                "directory-scoped star probe is not one segment under the "
                "directory versus a path the star would have to cross"
            )
        if not one_seg.endswith(f".{ext}") or not crossed.endswith(f".{ext}"):
            raise AssertionError(
                "directory-scoped star probe lost its filename suffix"
            )
        twin_star, twin_nested, twin_anchor = unique_tokens("ts", "tn", "ta")
        rel2 = _kb()
        write_bundle(
            ws,
            rel2,
            [
                search_concept_spec(
                    twin_star,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[f"*.{ext}"],
                ),
                search_concept_spec(
                    twin_nested,
                    concept_type=typ,
                    title=ntitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[scoped_ref],
                ),
                search_concept_spec(
                    twin_anchor,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[crossed],
                ),
            ],
        )
        twin_hit = require_search_structured_success(
            run_search(ws, None, rel2, for_path=f"{leaf}.{ext}", structured=True)
        )
        assert identity_in_records(twin_hit, twin_star)
        assert not identity_in_records(twin_hit, twin_nested), (
            f"{scoped_ref} matched a file outside its directory"
        )
        assert not identity_in_records(twin_hit, twin_anchor)
        twin_miss = require_search_structured_success(
            run_search(ws, None, rel2, for_path=one_seg, structured=True)
        )
        assert not identity_in_records(twin_miss, twin_star)
        assert identity_in_records(twin_miss, twin_nested), (
            f"{scoped_ref} was not the hit for {one_seg}"
        )
        twin_deep = require_search_structured_success(
            run_search(ws, None, rel2, for_path=crossed, structured=True)
        )
        assert identity_in_records(twin_deep, twin_anchor), (
            f"exact code_ref was not a hit for {crossed}"
        )
        assert not identity_in_records(twin_deep, twin_nested), (
            f"{scoped_ref} crossed a slash onto {crossed}"
        )
        assert not identity_in_records(twin_deep, twin_star)
        assert not identity_in_records(twin_miss, twin_anchor)
        probe = partial_segment_glob_probe()
        if "/" in probe.pattern or probe.pattern.startswith("*") or probe.pattern.count("*") != 1:
            raise AssertionError(
                f"stored pattern is still a whole-stem star: {probe.pattern!r}"
            )
        star_at = probe.pattern.index("*")
        if star_at <= 0:
            raise AssertionError(
                "star is not part-way through a single filename segment"
            )
        if "/" in probe.hit_path:
            raise AssertionError(
                f"partial-segment hit is not one segment: {probe.hit_path!r}"
            )
        partial_id, cross_id, nest_id, stem_id, suffix_id = unique_tokens(
            "ps", "pc", "pn", "pw", "pu"
        )
        probe_texts = (
            probe.pattern,
            probe.hit_path,
            probe.cross_path,
            probe.nested_path,
            probe.whole_stem_path,
            probe.wrong_suffix_path,
        )
        for ident in (partial_id, cross_id, nest_id, stem_id, suffix_id):
            if ident in probe_texts or any(ident in text for text in probe_texts):
                raise AssertionError(
                    "concept identity collides with a partial-segment probe path"
                )
        rel3 = _kb()
        write_bundle(
            ws,
            rel3,
            [
                search_concept_spec(
                    partial_id,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.pattern],
                ),
                search_concept_spec(
                    cross_id,
                    concept_type=typ,
                    title=ntitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.cross_path],
                ),
                search_concept_spec(
                    nest_id,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.nested_path],
                ),
                search_concept_spec(
                    stem_id,
                    concept_type=typ,
                    title=ntitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.whole_stem_path],
                ),
                search_concept_spec(
                    suffix_id,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.wrong_suffix_path],
                ),
            ],
        )
        partial_hit = require_search_structured_success(
            run_search(ws, None, rel3, for_path=probe.hit_path, structured=True)
        )
        assert identity_in_records(partial_hit, partial_id), (
            f"{probe.pattern} missed {probe.hit_path}"
        )
        assert not identity_in_records(partial_hit, cross_id)
        assert not identity_in_records(partial_hit, nest_id)
        assert not identity_in_records(partial_hit, stem_id)
        assert not identity_in_records(partial_hit, suffix_id)
        crossed = require_search_structured_success(
            run_search(ws, None, rel3, for_path=probe.cross_path, structured=True)
        )
        assert identity_in_records(crossed, cross_id), (
            f"exact code_ref was not a hit for {probe.cross_path}"
        )
        assert not identity_in_records(crossed, partial_id), (
            f"{probe.pattern} matched {probe.cross_path}; "
            "the star would have to cross a slash"
        )
        nested_records = require_search_structured_success(
            run_search(ws, None, rel3, for_path=probe.nested_path, structured=True)
        )
        assert identity_in_records(nested_records, nest_id), (
            f"exact code_ref was not a hit for {probe.nested_path}"
        )
        assert not identity_in_records(nested_records, partial_id), (
            f"{probe.pattern} matched {probe.nested_path}; "
            "the star would have to cross a slash to match the whole path"
        )
        stem_records = require_search_structured_success(
            run_search(
                ws, None, rel3, for_path=probe.whole_stem_path, structured=True
            )
        )
        assert identity_in_records(stem_records, stem_id), (
            f"exact code_ref was not a hit for {probe.whole_stem_path}"
        )
        assert not identity_in_records(stem_records, partial_id), (
            f"{probe.pattern} matched {probe.whole_stem_path}; "
            "the star is not the whole filename stem"
        )
        suffix_records = require_search_structured_success(
            run_search(
                ws, None, rel3, for_path=probe.wrong_suffix_path, structured=True
            )
        )
        assert identity_in_records(suffix_records, suffix_id), (
            f"exact code_ref was not a hit for {probe.wrong_suffix_path}"
        )
        assert not identity_in_records(suffix_records, partial_id), (
            f"{probe.pattern} matched {probe.wrong_suffix_path}"
        )
        print(
            f"partial-segment glob ref={probe.pattern!r} hit={probe.hit_path!r}",
            flush=True,
        )
        print("glob star does not cross slash", flush=True)


def test_glob_star_in_an_earlier_segment_does_not_cross_a_slash():
    """A star before the filename matches one segment and does not cross a slash.

    Stored refs are ``*/{leaf}.{ext}`` and ``{dir}/*/{leaf}.{ext}``.
    Each hits a path whose star span is exactly one segment. Each misses a
    path that would need that star to consume a slash, a same-shape path
    whose literal filename differs, and, for the directory-scoped pattern,
    a path whose literal directory differs. An exact code_ref for every
    searched path keeps a miss a non-empty hit list.
    """
    with workspace() as ws:
        typ, desc, body = _filler()
        probe = earlier_segment_glob_probe()
        if "*" in probe.leading_pattern.split("/")[-1]:
            raise AssertionError(
                f"leading star is still in the filename: {probe.leading_pattern!r}"
            )
        if "*" in probe.scoped_pattern.split("/")[-1]:
            raise AssertionError(
                f"scoped star is still in the filename: {probe.scoped_pattern!r}"
            )
        if probe.leading_pattern.count("*") != 1 or probe.scoped_pattern.count("*") != 1:
            raise AssertionError(
                "earlier-segment probe does not store exactly one star in each pattern"
            )
        leading_glob, leading_hit_id, leading_cross_id, leading_other_id = unique_tokens(
            "lg", "lh", "lc", "lo"
        )
        scoped_glob, scoped_hit_id, scoped_cross_id, scoped_other_id, scoped_dir_id = unique_tokens(
            "sg", "sh", "sc", "so", "sd"
        )
        titles = unique_tokens("t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8")
        idents = (
            leading_glob,
            leading_hit_id,
            leading_cross_id,
            leading_other_id,
            scoped_glob,
            scoped_hit_id,
            scoped_cross_id,
            scoped_other_id,
            scoped_dir_id,
        )
        probe_texts = (
            probe.leading_pattern,
            probe.leading_hit,
            probe.leading_cross,
            probe.leading_other_leaf,
            probe.scoped_pattern,
            probe.scoped_hit,
            probe.scoped_cross,
            probe.scoped_other_leaf,
            probe.scoped_other_dir,
        )
        for ident in idents:
            if ident in probe_texts or any(ident in text for text in probe_texts):
                raise AssertionError(
                    "concept identity collides with an earlier-segment probe path"
                )
        rel_leading = _kb()
        write_bundle(
            ws,
            rel_leading,
            [
                search_concept_spec(
                    leading_glob,
                    concept_type=typ,
                    title=titles[0],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.leading_pattern],
                ),
                search_concept_spec(
                    leading_hit_id,
                    concept_type=typ,
                    title=titles[1],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.leading_hit],
                ),
                search_concept_spec(
                    leading_cross_id,
                    concept_type=typ,
                    title=titles[2],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.leading_cross],
                ),
                search_concept_spec(
                    leading_other_id,
                    concept_type=typ,
                    title=titles[3],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.leading_other_leaf],
                ),
            ],
        )
        rel_scoped = _kb()
        write_bundle(
            ws,
            rel_scoped,
            [
                search_concept_spec(
                    scoped_glob,
                    concept_type=typ,
                    title=titles[4],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.scoped_pattern],
                ),
                search_concept_spec(
                    scoped_hit_id,
                    concept_type=typ,
                    title=titles[5],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.scoped_hit],
                ),
                search_concept_spec(
                    scoped_cross_id,
                    concept_type=typ,
                    title=titles[6],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.scoped_cross],
                ),
                search_concept_spec(
                    scoped_other_id,
                    concept_type=typ,
                    title=titles[7],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.scoped_other_leaf],
                ),
                search_concept_spec(
                    scoped_dir_id,
                    concept_type=typ,
                    title=titles[8],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.scoped_other_dir],
                ),
            ],
        )
        cases = (
            (
                rel_leading,
                probe.leading_hit,
                (leading_glob, leading_hit_id),
                (leading_cross_id, leading_other_id),
                f"{probe.leading_pattern} missed {probe.leading_hit}",
            ),
            (
                rel_leading,
                probe.leading_cross,
                (leading_cross_id,),
                (leading_glob, leading_hit_id, leading_other_id),
                f"{probe.leading_pattern} matched {probe.leading_cross}; "
                "the star would have to cross a slash",
            ),
            (
                rel_leading,
                probe.leading_other_leaf,
                (leading_other_id,),
                (leading_glob, leading_hit_id, leading_cross_id),
                f"{probe.leading_pattern} matched {probe.leading_other_leaf}; "
                "the filename segment is literal",
            ),
            (
                rel_scoped,
                probe.scoped_hit,
                (scoped_glob, scoped_hit_id),
                (scoped_cross_id, scoped_other_id, scoped_dir_id),
                f"{probe.scoped_pattern} missed {probe.scoped_hit}",
            ),
            (
                rel_scoped,
                probe.scoped_cross,
                (scoped_cross_id,),
                (scoped_glob, scoped_hit_id, scoped_other_id, scoped_dir_id),
                f"{probe.scoped_pattern} matched {probe.scoped_cross}; "
                "the star would have to cross a slash",
            ),
            (
                rel_scoped,
                probe.scoped_other_leaf,
                (scoped_other_id,),
                (scoped_glob, scoped_hit_id, scoped_cross_id, scoped_dir_id),
                f"{probe.scoped_pattern} matched {probe.scoped_other_leaf}; "
                "the filename segment is literal",
            ),
            (
                rel_scoped,
                probe.scoped_other_dir,
                (scoped_dir_id,),
                (scoped_glob, scoped_hit_id, scoped_cross_id, scoped_other_id),
                f"{probe.scoped_pattern} matched {probe.scoped_other_dir}; "
                "the directory segment is literal",
            ),
        )
        for bundle, path, present, absent, why in cases:
            records = require_search_structured_success(
                run_search(ws, None, bundle, for_path=path, structured=True)
            )
            for ident in present:
                assert identity_in_records(records, ident), (
                    f"{why}; missing {ident!r} for {path!r}"
                )
            for ident in absent:
                assert not identity_in_records(records, ident), (
                    f"{why}; kept {ident!r} for {path!r}"
                )
        print(
            f"earlier-segment globs leading={probe.leading_pattern!r} "
            f"scoped={probe.scoped_pattern!r}",
            flush=True,
        )


def test_recursive_glob_matches_filename_suffix():
    """**/*.go hits a nested .go and not .md; pkg/**/*.go stays under pkg/.

    The same recursive suffix match is not limited to those two patterns:
    a runtime extension other than .go hits a nested file of that suffix
    and misses a different suffix, and a scoped pattern with that extension
    stays under its directory. The same stored ``**/*.{ext}`` also
    hits a one-segment ``{leaf}.{ext}`` and misses a one-segment file
    whose suffix is different.
    """
    with workspace() as ws:
        rec, scoped, typ, rtitle, stitle, desc, body = unique_tokens(
            "rc", "sc", "typ", "rtt", "stt", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    rec,
                    concept_type=typ,
                    title=rtitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=["**/*.go"],
                ),
                search_concept_spec(
                    scoped,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[SAMPLE_TOP_DIR + "/**/*.go"],
                ),
            ],
        )
        go_hit = require_search_structured_success(
            run_search(
                ws, None, rel, for_path=SAMPLE_FILE, structured=True
            )
        )
        assert identity_in_records(go_hit, rec)
        md_miss = run_search(
            ws, None, rel, for_path=SAMPLE_FILE[:-3] + ".md", structured=True
        )
        md_records = require_search_structured_success(md_miss)
        assert not identity_in_records(md_records, rec)
        scoped_hit = require_search_structured_success(
            run_search(
                ws, None, rel, for_path=SAMPLE_NESTED_DIR + "/parser.go", structured=True
            )
        )
        assert identity_in_records(scoped_hit, scoped)
        outside = require_search_structured_success(
            run_search(
                ws, None, rel, for_path="cmd/membundle/main.go", structured=True
            )
        )
        assert not identity_in_records(outside, scoped)
        ext, other, leaf, scope, deep, outside_dir = unique_compact(
            "rxe", "rxo", "rxl", "rxs", "rxd", "rxu"
        )
        rec2, scoped2 = unique_tokens("r2", "s2")
        unscoped_ref, one_seg_hit, one_seg_miss = one_segment_recursive_suffix_paths(
            leaf, ext, other
        )
        scoped_ref = f"{scope}/**/*.{ext}"
        nested_hit = f"{scope}/{deep}/{leaf}.{ext}"
        nested_miss = f"{scope}/{deep}/{leaf}.{other}"
        outside_hit = f"{outside_dir}/{leaf}.{ext}"
        if "/" not in nested_hit or not nested_hit.endswith(f".{ext}"):
            raise AssertionError(
                f"recursive suffix probe is not a nested file of .{ext}"
            )
        if not nested_miss.endswith(f".{other}") or nested_miss.endswith(f".{ext}"):
            raise AssertionError(
                "recursive suffix miss is not a different filename suffix"
            )
        rel2 = _kb()
        write_bundle(
            ws,
            rel2,
            [
                search_concept_spec(
                    rec2,
                    concept_type=typ,
                    title=rtitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[unscoped_ref],
                ),
                search_concept_spec(
                    scoped2,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[scoped_ref],
                ),
            ],
        )
        ext_hit = require_search_structured_success(
            run_search(ws, None, rel2, for_path=nested_hit, structured=True)
        )
        assert identity_in_records(ext_hit, rec2), (
            f"{unscoped_ref} missed nested file {nested_hit}"
        )
        assert identity_in_records(ext_hit, scoped2), (
            f"{scoped_ref} missed nested file {nested_hit}"
        )
        ext_miss = require_search_structured_success(
            run_search(ws, None, rel2, for_path=nested_miss, structured=True)
        )
        assert not identity_in_records(ext_miss, rec2), (
            f"{unscoped_ref} kept a different filename suffix {nested_miss}"
        )
        assert not identity_in_records(ext_miss, scoped2), (
            f"{scoped_ref} kept a different filename suffix {nested_miss}"
        )
        ext_outside = require_search_structured_success(
            run_search(ws, None, rel2, for_path=outside_hit, structured=True)
        )
        assert identity_in_records(ext_outside, rec2), (
            f"{unscoped_ref} missed {outside_hit}"
        )
        assert not identity_in_records(ext_outside, scoped2), (
            f"{scoped_ref} matched outside its directory: {outside_hit}"
        )
        bare_hit = require_search_structured_success(
            run_search(ws, None, rel2, for_path=one_seg_hit, structured=True)
        )
        assert identity_in_records(bare_hit, rec2), (
            f"{unscoped_ref} missed one-segment file {one_seg_hit}"
        )
        bare_miss = require_search_structured_success(
            run_search(ws, None, rel2, for_path=one_seg_miss, structured=True)
        )
        assert not identity_in_records(bare_miss, rec2), (
            f"{unscoped_ref} kept a one-segment file of a different suffix "
            f"{one_seg_miss}"
        )
        print(
            f"recursive glob ok one_seg_hit={one_seg_hit!r} "
            f"one_seg_miss={one_seg_miss!r}",
            flush=True,
        )


def test_directory_scoped_recursive_glob_without_filename_suffix():
    """A stored directory-scoped ** with no filename suffix hits any nested name.

    The ref is ``<dir>/**``, not ``**/*.<ext>`` and not ``<dir>/**/*.<ext>``.
    The nested file's name has no suffix and sits more than one segment
    under that directory. The same tail outside that directory is not a
    hit. Exact-path concepts on each file keep both searches a
    non-empty hit list, so a miss is the scoped concept's absence.
    """
    with workspace() as ws:
        ident, nested_ident, outside_ident, typ, title, desc, body = unique_tokens(
            "ur", "un", "uo", "ut", "utt", "udc", "ubd"
        )
        probe = unsuffixed_recursive_directory_probe()
        if not probe.code_ref.endswith("/**") or "*." in probe.code_ref:
            raise AssertionError(
                f"stored ref is not an unsuffixed directory **: {probe.code_ref!r}"
            )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.code_ref],
                ),
                search_concept_spec(
                    nested_ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.nested_path],
                ),
                search_concept_spec(
                    outside_ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.outside_path],
                ),
            ],
        )
        hit = require_search_structured_success(
            run_search(
                ws, None, rel, for_path=probe.nested_path, structured=True
            )
        )
        assert identity_in_records(hit, nested_ident), (
            f"exact nested ref missed {probe.nested_path}"
        )
        assert identity_in_records(hit, ident), (
            f"{probe.code_ref} missed nested file {probe.nested_path}"
        )
        assert not identity_in_records(hit, outside_ident), (
            f"outside exact ref matched nested file {probe.nested_path}"
        )
        miss = require_search_structured_success(
            run_search(
                ws, None, rel, for_path=probe.outside_path, structured=True
            )
        )
        assert identity_in_records(miss, outside_ident), (
            f"exact outside ref missed {probe.outside_path}"
        )
        assert not identity_in_records(miss, ident), (
            f"{probe.code_ref} matched a file outside its directory: "
            f"{probe.outside_path}"
        )
        assert not identity_in_records(miss, nested_ident), (
            f"exact nested ref matched outside file {probe.outside_path}"
        )
        print(
            f"unsuffixed recursive directory glob ref={probe.code_ref!r} "
            f"nested={probe.nested_path!r}",
            flush=True,
        )


def test_code_refs_list_matches_if_any_entry_matches():
    """A later matching list entry still hits; a non-match does not.

    Beside that hit, a concept that omits code_refs and a concept whose
    code_refs list is empty are not path hits. Both are still keyword hits
    on their own titles, so a path filter that treats a missing or empty
    list as matching every path cannot pass by dropping those concepts
    at load time.

    The same bundle is searched through membundle_search. A list whose first
    entry misses and whose second hits is a path hit. The omitted list
    and the empty list are absent from that path search. A title search
    on the tool still returns those two concepts.
    """
    with workspace() as ws:
        (
            hit_id,
            miss_id,
            omitted_id,
            empty_id,
            typ,
            htitle,
            mtitle,
            otitle,
            etitle,
            desc,
            body,
        ) = unique_tokens(
            "hit",
            "miss",
            "omit",
            "empty",
            "typ",
            "ht",
            "mt",
            "ot",
            "et",
            "dsc",
            "bod",
        )
        matching = SAMPLE_FILE
        non_matching = "docs/README.md"
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    miss_id,
                    concept_type=typ,
                    title=mtitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[non_matching],
                ),
                search_concept_spec(
                    hit_id,
                    concept_type=typ,
                    title=htitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[non_matching, matching],
                ),
                search_concept_spec(
                    omitted_id,
                    concept_type=typ,
                    title=otitle,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    empty_id,
                    concept_type=typ,
                    title=etitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[],
                ),
            ],
        )
        omitted_text = (root / f"{omitted_id}.md").read_text(encoding="utf-8")
        empty_text = (root / f"{empty_id}.md").read_text(encoding="utf-8")
        if "code_refs:" in omitted_text:
            raise AssertionError(
                "omitted-code_refs fixture still contains a code_refs field"
            )
        if "code_refs: []" not in empty_text:
            raise AssertionError(
                "empty code_refs fixture is not an empty list"
            )
        omitted_kw = require_search_structured_success(
            run_search(ws, otitle, rel, structured=True)
        )
        assert identity_in_records(omitted_kw, omitted_id), (
            "concept that omits code_refs was not a keyword hit on its title"
        )
        empty_kw = require_search_structured_success(
            run_search(ws, etitle, rel, structured=True)
        )
        assert identity_in_records(empty_kw, empty_id), (
            "concept with an empty code_refs list was not a keyword hit "
            "on its title"
        )
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=matching, structured=True)
        )
        assert identity_in_records(records, hit_id)
        assert not identity_in_records(records, miss_id)
        assert not identity_in_records(records, omitted_id), (
            "a concept that omits code_refs matched the path"
        )
        assert not identity_in_records(records, empty_id), (
            "a concept whose code_refs list is empty matched the path"
        )
        mcp_omitted = require_mcp_search_success(
            mcp_search(ws, query=otitle, bundle=rel)
        )
        assert identity_in_records(mcp_omitted, omitted_id), (
            "tool title search did not return the concept that omits code_refs"
        )
        mcp_empty_kw = require_mcp_search_success(
            mcp_search(ws, query=etitle, bundle=rel)
        )
        assert identity_in_records(mcp_empty_kw, empty_id), (
            "tool title search did not return the concept whose code_refs "
            "list is empty"
        )
        mcp_path = require_mcp_search_success(
            mcp_search(ws, for_path=matching, bundle=rel)
        )
        assert identity_in_records(mcp_path, hit_id), (
            "tool path search missed a concept whose first code_refs entry "
            "does not match and whose later entry does"
        )
        assert not identity_in_records(mcp_path, miss_id), (
            "tool path search kept a concept whose code_refs entries do not match"
        )
        assert not identity_in_records(mcp_path, omitted_id), (
            "tool path search kept a concept that omits code_refs"
        )
        assert not identity_in_records(mcp_path, empty_id), (
            "tool path search kept a concept whose code_refs list is empty"
        )
        print("code_refs any-entry match ok", flush=True)


def test_empty_path_filter_with_query_is_ordinary_keyword_search():
    """Omitting --for-path, and MCP for_path omitted or empty, still keyword-search."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        omitted = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert identity_in_records(omitted, ident)
        empty = require_search_structured_success(
            run_search(ws, title, rel, for_path="", structured=True)
        )
        assert identity_in_records(empty, ident)
        mcp_omitted = require_mcp_search_success(
            mcp_search(ws, query=title, bundle=rel)
        )
        assert identity_in_records(mcp_omitted, ident)
        mcp_empty = require_mcp_search_success(
            mcp_search(ws, query=title, for_path="", bundle=rel)
        )
        assert identity_in_records(mcp_empty, ident)
        print("empty path filter is keyword search", flush=True)


def test_path_filter_with_no_code_ref_match_is_empty_even_if_keywords_would_hit():
    """Path docs/README.md plus a titled query is empty; the same query without path hits.

    The structured command-line list stays the closed empty-list arm.
    The same path on human output, with structured output not requested,
    is a success that states nothing matched and does not present the
    concept. The search tool returns an empty list, not that keyword hit.
    """
    with workspace() as ws:
        ident, typ, desc, body = unique_tokens("id", "typ", "dsc", "bod")
        rel = _kb()
        title = SAMPLE_TERM_TITLE
        query = SAMPLE_TERM
        unmatched = "docs/README.md"
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[SAMPLE_FILE],
                )
            ],
        )
        live = require_search_structured_success(
            run_search(ws, query, rel, structured=True)
        )
        assert identity_in_records(live, ident)
        empty = run_search(
            ws,
            query,
            rel,
            for_path=unmatched,
            structured=True,
        )
        require_zero_hits_success(empty, structured=True, live_identities=[ident])
        require_unmatched_path_filter_is_miss(
            ws,
            query,
            rel,
            unmatched,
            ident,
            (ident, typ, title, query, desc, body),
            badge="context",
        )
        twin_id, twin_title = unique_tokens("tid", "ttt")
        rel2 = _kb()
        write_bundle(
            ws,
            rel2,
            [
                search_concept_spec(
                    twin_id,
                    concept_type=typ,
                    title=twin_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=["pkg/other.go"],
                )
            ],
        )
        live2 = require_search_structured_success(
            run_search(ws, twin_title, rel2, structured=True)
        )
        assert identity_in_records(live2, twin_id)
        empty2 = run_search(
            ws, twin_title, rel2, for_path=unmatched, structured=True
        )
        require_zero_hits_success(empty2, structured=True, live_identities=[twin_id])
        require_unmatched_path_filter_is_miss(
            ws,
            twin_title,
            rel2,
            unmatched,
            twin_id,
            (twin_id, typ, twin_title, desc, body),
            badge="context",
        )
        print("path filter mismatch is empty", flush=True)


# ---------------------------------------------------------------------------
# J. Path-bound order: hold, then constraint, then context
# ---------------------------------------------------------------------------


def test_path_search_orders_hold_then_constraint_then_context():
    """Inverted identities still rank hold, constraint, context on a path search."""
    with workspace() as ws:
        hold_id, con_id, ctx_id = inverted_governance_identities()
        typ, htitle, ctitle, xtitle, desc, body = unique_tokens(
            "typ", "ht", "ct", "xt", "dsc", "bod"
        )
        path = SAMPLE_FILE
        rel = _kb()
        write_concepts_later_first(
            ws,
            rel,
            [
                search_concept_spec(
                    hold_id,
                    concept_type=typ,
                    title=htitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="hold",
                    code_refs=[path],
                ),
                search_concept_spec(
                    con_id,
                    concept_type=typ,
                    title=ctitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="constraint",
                    code_refs=[path],
                ),
                search_concept_spec(
                    ctx_id,
                    concept_type=typ,
                    title=xtitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="context",
                    code_refs=[path],
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=path, structured=True)
        )
        ordered = require_identity_order(records, [hold_id, con_id, ctx_id])
        assert ordered == [hold_id, con_id, ctx_id], (
            f"path search must rank hold then constraint then context; "
            f"order={ordered!r}"
        )
        print("path governance order ok", flush=True)


def test_path_governance_order_beats_a_higher_keyword_score_on_context():
    """Context with a strong title match still ranks after hold on a path+query.

    The structured command keeps its closed triple: the keyword baseline
    ranks the titled context concept first, and the path search ranks
    hold, then constraint, then context. That structured list is not the
    human cell and not the search-tool cell. On human text, with
    structured output not requested, the same path search presents the
    badge-prefixed hits in hold, then constraint, then context. On one
    membundle_search call the same triple sits on that path, the keyword
    baseline ranks the titled context concept first, and the path search
    ranks hold, then constraint, then context. An order that follows the
    keyword score fails each of those cells.
    """
    with workspace() as ws:
        hold_id, con_id, ctx_id = inverted_governance_identities()
        term = compact_token("kw")
        typ, htitle, ctitle, desc, filler = unique_tokens(
            "typ", "ht", "ct", "dsc", "fil"
        )
        path = SAMPLE_FILE
        rel = _kb()
        write_concepts_later_first(
            ws,
            rel,
            [
                search_concept_spec(
                    hold_id,
                    concept_type=typ,
                    title=htitle,
                    description=desc,
                    body=f"incidental {term} once\n",
                    governance="hold",
                    code_refs=[path],
                ),
                search_concept_spec(
                    con_id,
                    concept_type=typ,
                    title=ctitle,
                    description=desc,
                    body=f"{filler}\n",
                    governance="constraint",
                    code_refs=[path],
                ),
                search_concept_spec(
                    ctx_id,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{filler}\n",
                    governance="context",
                    code_refs=[path],
                ),
            ],
        )
        keyword = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        keyword_order = hit_identities(keyword, [ctx_id, hold_id])
        assert keyword_order == [ctx_id, hold_id], (
            "keyword-only baseline must put the titled context concept before "
            f"the incidental-body hold concept; order={keyword_order!r}"
        )
        assert not identity_in_records(keyword, con_id), (
            "keyword-only baseline returned the concept that does not contain the term"
        )
        records = require_search_structured_success(
            run_search(ws, term, rel, for_path=path, structured=True)
        )
        ordered = require_identity_order(records, [hold_id, con_id, ctx_id])
        assert ordered == [hold_id, con_id, ctx_id], (
            f"hold must still rank before a higher-scoring context hit; "
            f"order={ordered!r}"
        )
        assert sorted([hold_id, con_id, ctx_id], reverse=True) != [
            hold_id,
            con_id,
            ctx_id,
        ]
        keyword_score_order = [ctx_id, hold_id, con_id]
        assert keyword_score_order != [hold_id, con_id, ctx_id]
        planted = tuple(sorted((hold_id, con_id, ctx_id), reverse=True))
        human = require_search_success(
            run_search(ws, term, rel, for_path=path)
        )
        require_human_ranked_hits(
            human,
            [
                ("hold", (hold_id,)),
                ("constraint", (con_id,)),
                ("context", (ctx_id,)),
            ],
            planted_order=planted,
        )
        human_order = concept_identity_order(
            human, [hold_id, con_id, ctx_id], form="human"
        )
        assert human_order == [hold_id, con_id, ctx_id], (
            "when structured output is not requested, badge-prefixed path "
            "hits must rank hold, then constraint, then context, even "
            "though a keyword search ranks the titled context concept "
            f"first; keyword-score order {keyword_score_order!r} fails; "
            f"order={human_order!r} keyword_order={keyword_order!r}"
        )
        assert human_order != keyword_score_order
        tool_keyword = require_mcp_search_success(
            mcp_search(ws, query=term, bundle=rel)
        )
        tool_keyword_order = hit_identities(tool_keyword, [ctx_id, hold_id])
        assert tool_keyword_order == [ctx_id, hold_id], (
            "search tool keyword baseline must rank the titled context "
            "concept before the incidental-body hold concept; "
            f"order={tool_keyword_order!r}"
        )
        assert not identity_in_records(tool_keyword, con_id), (
            "search tool keyword baseline returned the concept that does "
            "not contain the term"
        )
        tool_records = require_mcp_search_success(
            mcp_search(ws, query=term, for_path=path, bundle=rel)
        )
        tool_ordered = require_identity_order(
            tool_records, [hold_id, con_id, ctx_id]
        )
        assert tool_ordered == [hold_id, con_id, ctx_id], (
            "membundle_search path search must rank hold, then constraint, then "
            "context, even when the titled context concept ranks first as "
            f"a keyword hit; keyword-score order {keyword_score_order!r} "
            f"fails; order={tool_ordered!r} "
            f"keyword_order={tool_keyword_order!r}"
        )
        assert tool_ordered != keyword_score_order
        print("governance beats keyword on context", flush=True)


def test_path_governance_order_runtime_twin():
    """Runtime-unique path and inverted identities still rank hold then constraint then context."""
    with workspace() as ws:
        hold_id, con_id, ctx_id = inverted_governance_identities()
        typ, htitle, ctitle, xtitle, desc, body = unique_tokens(
            "typ", "ht", "ct", "xt", "dsc", "bod"
        )
        path = f"src/{compact_token('p')}/mod.go"
        rel = _kb()
        write_concepts_later_first(
            ws,
            rel,
            [
                search_concept_spec(
                    hold_id,
                    concept_type=typ,
                    title=htitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="hold",
                    code_refs=[path],
                ),
                search_concept_spec(
                    con_id,
                    concept_type=typ,
                    title=ctitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="constraint",
                    code_refs=[path],
                ),
                search_concept_spec(
                    ctx_id,
                    concept_type=typ,
                    title=xtitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="context",
                    code_refs=[path],
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=path, structured=True)
        )
        ordered = require_identity_order(records, [hold_id, con_id, ctx_id])
        assert ordered == [hold_id, con_id, ctx_id], (
            f"runtime twin must still rank hold then constraint then context; "
            f"order={ordered!r}"
        )
        print("runtime path-governance twin ok", flush=True)


def test_path_effective_governance_orders_HOLD_and_convention_omit():
    """HOLD ranks as hold; convention/ omits rank as constraint; other omit as context.

    One omitted identity is ``convention/<leaf>``. The other is
    ``convention/<dir>/<leaf>``. Both sit in the constraint slot, and the
    nested hit's effective value is constraint.
    """
    with workspace() as ws:
        hold_id, conv_id, deep_id, ctx_id = inverted_nested_convention_identities()
        typ, htitle, ctitle, dtitle, xtitle, desc, body = unique_tokens(
            "typ", "ht", "ct", "dt", "xt", "dsc", "bod"
        )
        path = f"pkg/{compact_token('p')}/x.go"
        rel = _kb()
        write_concepts_later_first(
            ws,
            rel,
            [
                search_concept_spec(
                    hold_id,
                    concept_type=typ,
                    title=htitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="HOLD",
                    code_refs=[path],
                ),
                search_concept_spec(
                    conv_id,
                    concept_type=typ,
                    title=ctitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                ),
                search_concept_spec(
                    deep_id,
                    concept_type=typ,
                    title=dtitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                ),
                search_concept_spec(
                    ctx_id,
                    concept_type=typ,
                    title=xtitle,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=path, structured=True)
        )
        ordered = require_identity_order(
            records, [hold_id, conv_id, deep_id, ctx_id]
        )
        assert ordered == [hold_id, conv_id, deep_id, ctx_id], (
            "HOLD then one-segment convention omit then nested convention "
            f"omit then context omit; order={ordered!r}"
        )
        assert_single_effective_governance(
            record_for_identity(records, deep_id),
            "constraint",
            [deep_id, typ, dtitle, desc, body, path],
        )
        print("HOLD and convention omit path order ok", flush=True)


def test_same_governance_path_hits_tie_break_by_identity():
    """Same-governance path hits break the remaining tie by identity ascending.

    The path-only command pair is unchanged: no query, in structured output
    and in human text, for the literal identities and for a later-identity
    first runtime pair. A third command-line pair supplies a query beside
    the path. Those two hits share one governance and the same keyword
    contribution, and their identity order is not write order. Structured
    results and badge-prefixed human hits follow identity order. Sorting
    that queried pair by write order fails. The path-only command tie and
    the search-tool tie stay as they are.
    """
    with workspace() as ws:
        typ, desc, body = unique_tokens("typ", "dsc", "bod")
        shared_title = compact_token("tie")
        path = f"pkg/{compact_token('p')}/x.go"
        rel = _kb()
        write_concepts_later_first(
            ws,
            rel,
            [
                search_concept_spec(
                    SAMPLE_LOW_ID,
                    concept_type=typ,
                    title=shared_title,
                    description=desc,
                    body=f"{body}\n",
                    governance="constraint",
                    code_refs=[path],
                ),
                search_concept_spec(
                    SAMPLE_HIGH_ID,
                    concept_type=typ,
                    title=shared_title,
                    description=desc,
                    body=f"{body}\n",
                    governance="constraint",
                    code_refs=[path],
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=path, structured=True)
        )
        ordered = require_identity_order(records, [SAMPLE_LOW_ID, SAMPLE_HIGH_ID])
        assert ordered == [SAMPLE_LOW_ID, SAMPLE_HIGH_ID], (
            f"same-governance path hits must order by identity ascending; "
            f"order={ordered!r}"
        )
        human = require_search_success(
            run_search(ws, None, rel, for_path=path)
        )
        require_human_ranked_hits(
            human,
            [
                ("constraint", (SAMPLE_LOW_ID,)),
                ("constraint", (SAMPLE_HIGH_ID,)),
            ],
            planted_order=(SAMPLE_HIGH_ID, SAMPLE_LOW_ID),
        )
        closed_literals = (SAMPLE_LOW_ID, SAMPLE_HIGH_ID)
        early_id = f"aaa{compact_token('a')}"
        late_id = f"zzz{compact_token('z')}"
        assert early_id not in closed_literals and late_id not in closed_literals
        assert early_id < late_id
        runtime_path = f"pkg/{compact_token('r')}/x.go"
        runtime_rel = _kb()
        write_order = plant_same_governance_path_tie_later_first(
            ws,
            runtime_rel,
            runtime_path,
            early_id,
            late_id,
            governance="constraint",
        )
        assert write_order[0] > write_order[1], (
            "fixture write order is already identity ascending; "
            "this call cannot tell identity order from write order; "
            f"write_order={write_order!r}"
        )
        assert list(write_order) != sorted(write_order)
        runtime_records = require_search_structured_success(
            run_search(
                ws, None, runtime_rel, for_path=runtime_path, structured=True
            )
        )
        runtime_ordered = require_identity_order(
            runtime_records, [early_id, late_id]
        )
        assert runtime_ordered == [early_id, late_id], (
            "same-governance path hits must order by identity ascending, "
            f"not write order; order={runtime_ordered!r} "
            f"write_order={write_order!r}"
        )
        assert runtime_ordered != list(write_order)
        assert runtime_ordered[0] != write_order[0], (
            "structured path search returned the first written identity; "
            "a remaining tie must break by identity; "
            f"order={runtime_ordered!r} write_order={write_order!r}"
        )
        runtime_human = require_search_success(
            run_search(ws, None, runtime_rel, for_path=runtime_path)
        )
        require_human_ranked_hits(
            runtime_human,
            [
                ("constraint", (early_id,)),
                ("constraint", (late_id,)),
            ],
            planted_order=write_order,
        )
        query = compact_token("qry")
        query_early = f"aaa{compact_token('qe')}"
        query_late = f"zzz{compact_token('ql')}"
        assert query_early not in closed_literals and query_late not in closed_literals
        assert query_early < query_late
        assert query_early != early_id and query_late != late_id
        query_path = f"pkg/{compact_token('pq')}/x.go"
        query_rel = _kb()
        query_write = plant_same_governance_path_query_tie_later_first(
            ws,
            query_rel,
            query_path,
            query_early,
            query_late,
            query,
            governance="constraint",
        )
        assert query_write[0] > query_write[1], (
            "queried path tie was written in identity order; "
            "this call cannot tell identity order from write order; "
            f"write_order={query_write!r}"
        )
        assert list(query_write) != sorted(query_write)
        query_records = require_search_structured_success(
            run_search(
                ws,
                query,
                query_rel,
                for_path=query_path,
                structured=True,
            )
        )
        query_ordered = require_identity_order(
            query_records, [query_early, query_late]
        )
        assert query_ordered == [query_early, query_late], (
            "same-governance path hits with a query whose keyword "
            "contribution does not break the tie must order by identity "
            f"ascending, not write order; order={query_ordered!r} "
            f"write_order={query_write!r}"
        )
        assert query_ordered != list(query_write)
        assert query_ordered[0] != query_write[0], (
            "structured path search with a query returned the first "
            "written identity; a remaining tie must break by identity; "
            f"order={query_ordered!r} write_order={query_write!r}"
        )
        query_human = require_search_success(
            run_search(ws, query, query_rel, for_path=query_path)
        )
        query_human_order = concept_identity_order(
            query_human, [query_early, query_late], form="human"
        )
        assert query_human_order == [query_early, query_late], (
            "human path hits with a query, read from the badge-prefixed "
            "hits, must order by identity ascending, not write order; "
            f"order={query_human_order!r} write_order={query_write!r}"
        )
        assert query_human_order != list(query_write)
        assert query_human_order[0] != query_write[0], (
            "human path search with a query listed the first written "
            "identity inside the first governance-badge span; a remaining "
            "tie must break by identity; "
            f"order={query_human_order!r} write_order={query_write!r}"
        )
        print("same-governance identity tie-break ok", flush=True)


def test_same_governance_higher_combined_score_ranks_first():
    """Title-matching constraint ranks before a path-only sibling; both remain hits."""
    with workspace() as ws:
        term = compact_token("cmb")
        path_only_id = f"aaa{compact_token('p')}"
        title_id = f"zzz{compact_token('t')}"
        assert path_only_id < title_id
        typ, miss_title, desc, body = unique_tokens("typ", "mt", "dsc", "bod")
        path = f"pkg/{compact_token('q')}/x.go"
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    path_only_id,
                    concept_type=typ,
                    title=miss_title,
                    description=desc,
                    body=f"{body}\n",
                    governance="constraint",
                    code_refs=[path],
                ),
                search_concept_spec(
                    title_id,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=f"{body}\n",
                    governance="constraint",
                    code_refs=[path],
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, term, rel, for_path=path, structured=True)
        )
        require_identity_order(records, [title_id, path_only_id])
        human = require_search_success(
            run_search(ws, term, rel, for_path=path)
        )
        require_human_ranked_hits(
            human,
            [
                ("constraint", (title_id,)),
                ("constraint", (path_only_id,)),
            ],
            planted_order=(path_only_id, title_id),
        )
        print("combined score keeps both path hits", flush=True)


# ---------------------------------------------------------------------------
# K. Path hits report matched on code_refs and any keyword fields
# ---------------------------------------------------------------------------


def test_path_hit_reports_code_refs_match():
    """Path-only structured hit contains code_refs and not title after stripping the path."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        path = f"pkg/{compact_token('p')}/x.go"
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                )
            ],
        )
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=path, structured=True)
        )
        rec = record_for_identity(records, ident)
        strip = [path, ident, typ, title, desc, body]
        tokens = matched_field_tokens(rec, strip)
        assert "title" not in tokens, f"path-only still has title; tokens={sorted(tokens)}"
        assert_matched_keyword_fields(rec, strip, ())
        assert code_ref_match_reported(rec, strip), (
            "path-only hit does not report a code_refs match after the path "
            f"and the concept's own texts are stripped; record={rec!r}"
        )
        tool_records = require_mcp_search_success(
            mcp_search(ws, for_path=path, bundle=rel)
        )
        assert_path_hit_reports(
            record_for_identity(tool_records, ident),
            strip,
            (),
        )
        print("path-only hit reports the code-ref channel", flush=True)


def test_path_plus_query_reports_code_refs_and_keyword_fields():
    """Path plus a query reports code_refs and exactly the keyword fields that matched.

    The closed title presence check stays. On the command and on the
    search tool, a path hit whose only keyword match is one of title,
    tags, description, id, or body names code_refs and that member, and
    no other member of that set. A path hit that matched title and tags,
    and no other member of that set, names code_refs and exactly those
    two members.
    """
    with workspace() as ws:
        ident, other, typ, title, desc, body = unique_tokens(
            "id", "oid", "typ", "ttl", "dsc", "bod"
        )
        path = f"pkg/{compact_token('p')}/x.go"
        elsewhere = f"pkg/{compact_token('e')}/y.go"
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    other,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[elsewhere],
                ),
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, title, rel, for_path=path, structured=True)
        )
        assert identity_in_records(records, ident)
        assert not identity_in_records(records, other), (
            "a title match whose code_refs do not cover the path was returned"
        )
        rec = record_for_identity(records, ident)
        strip = [path, ident, typ, title, desc, body, elsewhere]
        tokens = matched_field_tokens(rec, strip)
        assert "title" in tokens, (
            f"path-plus-query hit does not report title; tokens={sorted(tokens)}"
        )
        assert code_ref_match_reported(rec, strip), (
            "path-plus-query hit does not report a code_refs match; "
            f"title alone is not enough; record={rec!r}"
        )
        assert_path_hit_reports(rec, strip, ["title"])
        tool_title = require_mcp_search_success(
            mcp_search(ws, query=title, for_path=path, bundle=rel)
        )
        assert identity_in_records(tool_title, ident)
        assert not identity_in_records(tool_title, other), (
            "search tool returned a title match whose code_refs do not "
            "cover the path"
        )
        tool_rec = record_for_identity(tool_title, ident)
        tool_tokens = matched_field_tokens(tool_rec, strip)
        assert "title" in tool_tokens, (
            "path-plus-query tool hit does not report title; "
            f"tokens={sorted(tool_tokens)}"
        )
        assert_path_hit_reports(tool_rec, strip, ["title"])
        print("path+query reports the code-ref channel and title", flush=True)

    with workspace() as ws:
        (
            term,
            typ,
            filler_title,
            filler_desc,
            filler_body,
            id_title,
            id_tags,
            id_desc,
            id_body,
            id_decoy,
            dir_tok,
            path_dir,
            else_dir,
        ) = unique_compact(
            "tm", "ty", "ft", "fd", "fb",
            "it", "ig", "ic", "ib", "iy",
            "dr", "pd", "ed",
        )
        id_ident = f"{dir_tok}/{term}"
        if "/" not in id_ident or id_ident.startswith("convention/"):
            raise AssertionError(
                f"identity keyword plant is not a non-convention path: {id_ident!r}"
            )
        field_tokens_do_not_start_with(
            term,
            filler_title,
            filler_desc,
            filler_body,
            id_title,
            id_tags,
            id_desc,
            id_body,
            id_decoy,
            dir_tok,
            path_dir,
            else_dir,
            typ,
        )
        path = f"pkg/{path_dir}/x.go"
        elsewhere = f"pkg/{else_dir}/y.go"
        plants = (
            ("title", id_title, {"title": term}),
            ("tags", id_tags, {"tags": [term]}),
            ("description", id_desc, {"description": term}),
            ("id", id_ident, {}),
            ("body", id_body, {"body": f"{term}\n"}),
        )
        specs = []
        for _field, ident, overrides in plants:
            fields = {
                "concept_type": typ,
                "title": filler_title,
                "description": filler_desc,
                "body": f"{filler_body}\n",
                "code_refs": [path],
            }
            fields.update(overrides)
            specs.append(search_concept_spec(ident, **fields))
        specs.append(
            search_concept_spec(
                id_decoy,
                concept_type=typ,
                title=term,
                description=filler_desc,
                body=f"{filler_body}\n",
                code_refs=[elsewhere],
            )
        )
        rel = _kb()
        write_bundle(ws, rel, specs)
        keyword_command = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        keyword_tool = require_mcp_search_success(
            mcp_search(ws, query=term, bundle=rel)
        )
        for entry, hits in (("command", keyword_command), ("tool", keyword_tool)):
            assert identity_in_records(hits, id_decoy), (
                f"{entry} keyword search omitted the concept that matches "
                "the term and does not cover the path"
            )
        command_hits = require_search_structured_success(
            run_search(ws, term, rel, for_path=path, structured=True)
        )
        tool_hits = require_mcp_search_success(
            mcp_search(ws, query=term, for_path=path, bundle=rel)
        )
        shared_strip = [
            term,
            typ,
            filler_title,
            filler_desc,
            filler_body,
            path,
            elsewhere,
            dir_tok,
            path_dir,
            else_dir,
            id_title,
            id_tags,
            id_desc,
            id_body,
            id_decoy,
            id_ident,
        ]
        for entry, hits in (("command", command_hits), ("tool", tool_hits)):
            assert not identity_in_records(hits, id_decoy), (
                f"{entry} path search returned the concept whose code_refs "
                "do not cover the path"
            )
            for field, ident, _overrides in plants:
                assert identity_in_records(hits, ident), (
                    f"{entry} path-plus-query omitted the concept whose only "
                    f"keyword match is {field}"
                )
                assert_path_hit_reports(
                    record_for_identity(hits, ident),
                    [ident, *shared_strip],
                    [field],
                )
        print(
            "path-plus-query names code_refs and exactly one keyword field",
            flush=True,
        )

    with workspace() as ws:
        (
            term,
            typ,
            filler_desc,
            filler_body,
            both_id,
            decoy_id,
            path_dir,
            else_dir,
        ) = unique_compact(
            "tm", "ty", "fd", "fb", "ib", "iy", "pd", "ed",
        )
        field_tokens_do_not_start_with(
            term,
            filler_desc,
            filler_body,
            both_id,
            decoy_id,
            typ,
            path_dir,
            else_dir,
        )
        path = f"pkg/{path_dir}/x.go"
        elsewhere = f"pkg/{else_dir}/y.go"
        field_tokens_do_not_start_with(term, path, elsewhere)
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    both_id,
                    concept_type=typ,
                    title=term,
                    description=filler_desc,
                    body=f"{filler_body}\n",
                    tags=[term],
                    code_refs=[path],
                ),
                search_concept_spec(
                    decoy_id,
                    concept_type=typ,
                    title=term,
                    description=filler_desc,
                    body=f"{filler_body}\n",
                    tags=[term],
                    code_refs=[elsewhere],
                ),
            ],
        )
        strip = [
            term,
            typ,
            filler_desc,
            filler_body,
            both_id,
            decoy_id,
            path,
            elsewhere,
            path_dir,
            else_dir,
        ]
        command_hits = require_search_structured_success(
            run_search(ws, term, rel, for_path=path, structured=True)
        )
        tool_hits = require_mcp_search_success(
            mcp_search(ws, query=term, for_path=path, bundle=rel)
        )
        for entry, hits in (("command", command_hits), ("tool", tool_hits)):
            assert identity_in_records(hits, both_id), (
                f"{entry} path-plus-query omitted the concept whose title "
                "and tags both match"
            )
            assert not identity_in_records(hits, decoy_id), (
                f"{entry} path-plus-query returned the concept whose "
                "code_refs do not cover the path"
            )
            assert_path_hit_reports(
                record_for_identity(hits, both_id),
                strip,
                ["title", "tags"],
            )
        print(
            "path-plus-query names code_refs and exactly title and tags",
            flush=True,
        )


# ---------------------------------------------------------------------------
# L. Unicode query matches Unicode title
# ---------------------------------------------------------------------------


def _unicode_letter_title(token: str) -> str:
    """Map an alphanumeric token onto letters that are not ASCII.

    The tool query is this title. An ASCII tail would still match after
    the non-ASCII letters were dropped, so the title has none.
    """
    letters = "абвгдежзийклмнопрстуфхцчшщъыьэюя"
    digits = "αβγδεζηθικ"
    parts: list[str] = []
    for ch in token:
        if "a" <= ch <= "z":
            parts.append(letters[ord(ch) - ord("a")])
        elif "A" <= ch <= "Z":
            parts.append(letters[ord(ch) - ord("A")])
        elif ch.isdigit():
            parts.append(digits[ord(ch) - ord("0")])
        else:
            raise AssertionError(
                f"unicode title source is not alphanumeric: {token!r}"
            )
    title = "".join(parts)
    if not title or title.isascii() or not title.isalpha():
        raise AssertionError(f"unicode title is not non-ASCII letters: {title!r}")
    return title


def test_unicode_query_matches_unicode_title():
    """A same-case Unicode title query returns that concept.

    The command and the search tool are that search. The command line
    returns its Unicode title and omits the other concept. On the tool,
    a separate Unicode title and a different concept are planted, that
    title is the query, and only the Unicode concept comes back.
    """
    with workspace() as ws:
        early, late, typ, desc, body, otitle = unique_tokens(
            "ea", "la", "typ", "dsc", "bod", "ott"
        )
        other = f"a{early}"
        ident = f"z{late}"
        assert other < ident
        title = f"Тензорная{compact_token('u')}"
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    other,
                    concept_type=typ,
                    title=otitle,
                    description=desc,
                    body=f"{body}\n",
                ),
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert identity_in_records(records, ident)
        assert not identity_in_records(records, other)
        tool_early, tool_late, tool_typ, tool_desc, tool_body, tool_otitle = (
            unique_tokens("tea", "tla", "typ", "dsc", "bod", "ott")
        )
        tool_other = f"a{tool_early}"
        tool_ident = f"z{tool_late}"
        assert tool_other < tool_ident
        tool_title = _unicode_letter_title(compact_token("uq"))
        assert tool_title not in tool_otitle
        assert tool_otitle.isascii()
        tool_rel = _kb()
        write_bundle(
            ws,
            tool_rel,
            [
                search_concept_spec(
                    tool_other,
                    concept_type=tool_typ,
                    title=tool_otitle,
                    description=tool_desc,
                    body=f"{tool_body}\n",
                ),
                search_concept_spec(
                    tool_ident,
                    concept_type=tool_typ,
                    title=tool_title,
                    description=tool_desc,
                    body=f"{tool_body}\n",
                ),
            ],
        )
        tool_records = require_mcp_search_success(
            mcp_search(ws, query=tool_title, bundle=tool_rel)
        )
        assert identity_in_records(tool_records, tool_ident), (
            "search tool omitted the concept whose title is the Unicode query"
        )
        assert not identity_in_records(tool_records, tool_other), (
            "search tool returned the other concept for a Unicode title query"
        )
        print("unicode title hit", flush=True)


def test_unicode_title_runtime_twin():
    """Non-ASCII letters stay in one term on the command and the search tool.

    Each surface searches a title whose non-ASCII letters are followed by
    an ASCII tail. The whole string returns that concept. The ASCII tail
    alone omits it. The command-line title is a fixed non-ASCII head. The
    tool plants a different runtime letter head so the tool term is not
    that head.
    """
    with workspace() as ws:
        early, late, typ, desc, body = unique_tokens(
            "ea", "la", "typ", "dsc", "bod"
        )
        other = f"a{early}"
        ident = f"z{late}"
        assert other < ident
        ascii_tail = compact_token("u")
        title = require_non_ascii_letters_then_ascii_tail(
            f"概念{ascii_tail}", ascii_tail
        )
        other_title = f"別物{compact_token('o')}"
        shared_body = f"{body}\n"
        field_tokens_do_not_start_with(
            ascii_tail, other_title, desc, body, ident, other, typ
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    other,
                    concept_type=typ,
                    title=other_title,
                    description=desc,
                    body=shared_body,
                ),
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=shared_body,
                ),
            ],
        )
        records = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert identity_in_records(records, ident)
        assert not identity_in_records(records, other)
        ascii_only = require_search_structured_success(
            run_search(ws, ascii_tail, rel, structured=True)
        )
        assert not identity_in_records(ascii_only, ident), (
            "dropping the non-ASCII letters from the term still hit the title"
        )
        assert not identity_in_records(ascii_only, other)

        tool_early, tool_late, tool_typ, tool_desc, tool_body = unique_tokens(
            "tea", "tla", "typ", "dsc", "bod"
        )
        tool_other = f"a{tool_early}"
        tool_ident = f"z{tool_late}"
        assert tool_other < tool_ident
        tool_tail = compact_token("ut")
        tool_title = require_non_ascii_letters_then_ascii_tail(
            _unicode_letter_title(compact_token("ul")) + tool_tail,
            tool_tail,
        )
        tool_other_title = compact_token("uo")
        tool_shared_body = f"{tool_body}\n"
        field_tokens_do_not_start_with(
            tool_tail,
            tool_other_title,
            tool_desc,
            tool_body,
            tool_ident,
            tool_other,
            tool_typ,
        )
        tool_rel = _kb()
        write_bundle(
            ws,
            tool_rel,
            [
                search_concept_spec(
                    tool_other,
                    concept_type=tool_typ,
                    title=tool_other_title,
                    description=tool_desc,
                    body=tool_shared_body,
                ),
                search_concept_spec(
                    tool_ident,
                    concept_type=tool_typ,
                    title=tool_title,
                    description=tool_desc,
                    body=tool_shared_body,
                ),
            ],
        )
        tool_full = require_mcp_search_success(
            mcp_search(ws, query=tool_title, bundle=tool_rel)
        )
        assert identity_in_records(tool_full, tool_ident), (
            "search tool omitted the concept whose title is non-ASCII "
            "letters followed by an ASCII tail"
        )
        assert not identity_in_records(tool_full, tool_other), (
            "search tool returned the other concept for that whole title"
        )
        tool_tail_only = require_mcp_search_success(
            mcp_search(ws, query=tool_tail, bundle=tool_rel)
        )
        assert not identity_in_records(tool_tail_only, tool_ident), (
            "search tool still hit the title from the ASCII tail after "
            "the non-ASCII letters were split out of the term"
        )
        assert not identity_in_records(tool_tail_only, tool_other)

        # A non-ASCII letter between two letter-digit pieces stays inside
        # one term. The head-plus-tail pair above still hits when each
        # non-ASCII letter is its own term, because that first term is a
        # prefix of the title. The pieces on either side of this letter
        # are the titles that appear when the letter splits the term.
        piece_left, piece_right, piece_extra, piece_unused = unique_compact(
            "jl", "jr", "jx", "ju"
        )
        joined = query_joined_on_non_ascii_letter(piece_left, piece_right)
        joined_title = f"{joined}{piece_extra}"
        if (
            not joined_title.startswith(joined)
            or joined_title == joined
            or piece_left == joined
            or piece_right == joined
        ):
            raise AssertionError(
                f"joined title {joined_title!r} does not start with the "
                f"whole query {joined!r} and continue past it"
            )
        j_hit, j_left, j_right, j_unused, j_typ, j_desc, j_body = unique_tokens(
            "jhit", "jlft", "jrgt", "junu", "typ", "dsc", "bod"
        )
        id_joined = f"z{j_hit}"
        id_piece_left = f"a{j_left}"
        id_piece_right = f"b{j_right}"
        id_piece_unused = f"c{j_unused}"
        assert id_joined > id_piece_left
        for text in (
            piece_left,
            piece_right,
            piece_unused,
            j_typ,
            j_desc,
            j_body,
            id_joined,
            id_piece_left,
            id_piece_right,
            id_piece_unused,
        ):
            if not text.isascii() or joined.casefold() in text.casefold():
                raise AssertionError(
                    f"fixture text {text!r} already carries the joined "
                    f"query {joined!r}"
                )
        joined_rel = _kb()
        write_bundle(
            ws,
            joined_rel,
            [
                search_concept_spec(
                    id_piece_left,
                    concept_type=j_typ,
                    title=piece_left,
                    description=j_desc,
                    body=f"{j_body}\n",
                ),
                search_concept_spec(
                    id_piece_right,
                    concept_type=j_typ,
                    title=piece_right,
                    description=j_desc,
                    body=f"{j_body}\n",
                ),
                search_concept_spec(
                    id_piece_unused,
                    concept_type=j_typ,
                    title=piece_unused,
                    description=j_desc,
                    body=f"{j_body}\n",
                ),
                search_concept_spec(
                    id_joined,
                    concept_type=j_typ,
                    title=joined_title,
                    description=j_desc,
                    body=f"{j_body}\n",
                ),
            ],
        )
        joined_ids = (id_joined, id_piece_left, id_piece_right, id_piece_unused)
        records = require_search_structured_success(
            run_search(ws, joined, joined_rel, structured=True)
        )
        found = {
            ident
            for ident in joined_ids
            if identity_in_records(records, ident)
        }
        print(
            f"non-ascii-letter-kept command line query={joined!r} "
            f"found={found!r}",
            flush=True,
        )
        assert found == {id_joined}, (
            "a non-ASCII letter must stay inside the term; "
            f"command line query {joined!r} found={found!r}"
        )
        tool_records = require_mcp_search_success(
            mcp_search(ws, query=joined, bundle=joined_rel)
        )
        tool_found = {
            ident
            for ident in joined_ids
            if identity_in_records(tool_records, ident)
        }
        print(
            f"non-ascii-letter-kept search tool query={joined!r} "
            f"found={tool_found!r}",
            flush=True,
        )
        assert tool_found == {id_joined}, (
            "a non-ASCII letter must stay inside the term on the search tool; "
            f"query {joined!r} found={tool_found!r}"
        )
        print("unicode runtime twin ok", flush=True)


# ---------------------------------------------------------------------------
# M. Zero hits; CLI usage; MCP empty; missing bundle load error
# ---------------------------------------------------------------------------


def test_zero_hits_is_success_with_no_hits():
    """A matching-nothing query is success with no hits; human text states a miss."""
    with workspace() as ws:
        ident, typ, title, desc, body, miss = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod", "miss"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        live = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert identity_in_records(live, ident)
        structured_zero = run_search(ws, miss, rel, structured=True)
        require_zero_hits_success(
            structured_zero, structured=True, live_identities=[ident]
        )
        human_live = require_search_success(run_search(ws, title, rel))
        assert_identifiable_human_hits(
            human_live, [("context", (ident, title, desc))]
        )
        human_zero = run_search(ws, miss, rel)
        zero_report = require_zero_hits_success(
            human_zero, structured=False, live_identities=[ident]
        )
        assert_human_zero_hit_miss_statement(
            zero_report,
            human_live,
            path_tokens_for_search(rel, ws.path),
            (ident, typ, title, desc, body, miss),
            live_identities=[ident],
        )
        print("zero-hit success ok", flush=True)


def test_cli_neither_query_nor_path_is_non_success_usage():
    """Neither query nor path is usage: non-success, remainder ≠ zero-hit and ≠ load."""
    with workspace() as ws:
        ident, typ, title, desc, body, miss = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod", "miss"
        )
        write_bundle(
            ws,
            ".",
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        human_live = require_search_success(run_search(ws, title))
        zero_report = require_zero_hits_success(
            run_search(ws, miss), structured=False, live_identities=[ident]
        )
        assert_human_zero_hit_miss_statement(
            zero_report,
            human_live,
            path_tokens_for_search(".", ws.path),
            (ident, typ, title, desc, body, miss),
            live_identities=[ident],
        )
        missing = unique_tokens("gone")[0]
        load = run_search(ws, title, missing)
        load_report = require_search_load_failure(load)
        # TEST-FIX(F04): with no bin/membundle there is no product to run before search; per the Contract "Build" form, make build at the repository root writes that binary.
        usage = run_search(ws)
        fixture = (ident, typ, title, desc, body, miss, missing)
        require_search_usage_failure(
            usage,
            zero_report,
            load_report,
            path_tokens_for_search(".", ws.path, missing),
            fixture,
        )
        for flagged in (
            run_search(ws, structured=True),
            run_search(ws, extra_args=["--limit", "5"]),
        ):
            require_search_usage_failure(
                flagged,
                zero_report,
                load_report,
                path_tokens_for_search(".", ws.path, missing),
                fixture,
            )
        print("CLI neither is usage", flush=True)


def test_mcp_neither_query_nor_path_succeeds_with_empty_list():
    """MCP with neither query nor path is success with an empty list, not a tool error."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        live = require_mcp_search_success(mcp_search(ws, query=title, bundle=rel))
        assert identity_in_records(live, ident)
        empty = require_mcp_empty_success(
            mcp_membundle_search(ws, {"bundle": rel})
        )
        assert empty == []
        empty2 = require_mcp_empty_success(mcp_search(ws, bundle=rel))
        assert empty2 == []
        print("MCP neither is empty success", flush=True)


def test_missing_bundle_is_load_error_not_zero_hits():
    """A named missing directory is a load error, not zero-hit success."""
    with workspace() as ws:
        ident, typ, title, desc, body, miss = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod", "miss"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        # TEST-FIX(F04): with no bin/membundle there is no product to run before search; per the Contract "Build" form, make build at the repository root writes that binary.
        usage = run_search(ws)
        usage_report = combined_report(usage)
        missing = unique_tokens("gone")[0]
        load = run_search(ws, title, missing)
        human_live = require_search_success(run_search(ws, title, rel))
        zero_human = require_zero_hits_success(
            run_search(ws, miss, rel),
            structured=False,
            live_identities=[ident],
        )
        assert_human_zero_hit_miss_statement(
            zero_human,
            human_live,
            path_tokens_for_search(missing, ws.path, rel),
            (ident, typ, title, desc, body, miss),
            live_identities=[ident],
        )
        require_search_load_error(
            load,
            usage_report,
            path_tokens_for_search(missing, ws.path, rel),
            (ident, typ, title, desc, body, miss, missing),
            zero_human,
        )
        zero = run_search(ws, miss, rel, structured=True)
        require_zero_hits_success(zero, structured=True, live_identities=[ident])
        assert load.returncode != 0
        assert zero.returncode == 0
        print("missing bundle is load error", flush=True)


def test_mcp_missing_bundle_is_tool_error():
    """MCP named missing bundle fails the load, not a successful search.

    The same query on a real bundle returns that concept. Against a missing
    bundle the call must be a tool-error result or a JSON-RPC protocol error.
    A successful tools/call is not a load failure, including an empty list,
    a hit list, JSON null, and a payload that is not a hit list. This
    feature does not choose between the two error channels.
    """
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        rel = _kb()
        write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        live = require_mcp_search_success(mcp_search(ws, query=title, bundle=rel))
        assert identity_in_records(live, ident)
        missing = unique_tokens("gone")[0]
        outcome = mcp_search(ws, query=title, bundle=missing)
        require_mcp_search_load_failure(outcome)
        print("MCP missing bundle is a load failure", flush=True)


# ---------------------------------------------------------------------------
# N. Default bundle path and nested-knowledge load redirect
# ---------------------------------------------------------------------------


def test_omit_path_without_knowledge_dir_loads_cwd():
    """No knowledge/ directory: omit-path search loads the cwd bundle."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        write_bundle(
            ws,
            ".",
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        assert not (ws.path / "knowledge").exists()
        records = require_search_structured_success(
            run_search(ws, title, structured=True)
        )
        assert identity_in_records(records, ident)
        print("omit-path cwd load ok", flush=True)


def test_omit_path_with_knowledge_dir_loads_knowledge_not_cwd_decoy():
    """knowledge/ as a directory wins omit-path; cwd decoy title is absent."""
    with workspace() as ws:
        ident, typ, title, desc, body, dtitle, dtok = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod", "dtt", "db"
        )
        write_bundle(
            ws,
            "knowledge",
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        ws.write(
            f"{ident}.md",
            render_concept_markdown(
                concept_type=typ,
                title=dtitle,
                description=desc,
                body=f"{dtok}\n",
            ),
        )
        records = require_search_structured_success(
            run_search(ws, title, structured=True)
        )
        assert identity_in_records(records, ident)
        hit = record_for_identity(records, ident)
        hit_title = hit_field(hit, "title")
        assert hit_title == title, f"omit-path hit title is not the query: {hit!r}"
        assert hit_title != dtitle, (
            f"omit-path hit still carries the cwd decoy: {hit!r}"
        )
        report = require_search_success(run_search(ws, title))
        # The human hit is the knowledge concept the title query selects;
        # the cwd decoy does not carry that title, so it cannot be this hit.
        require_human_identity_present(report, ident)
        print("omit-path knowledge decoy absent", flush=True)


def test_omit_path_knowledge_file_is_not_treated_as_bundle_dir():
    """A file named knowledge is not the omit-path bundle directory."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        write_bundle(
            ws,
            ".",
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        (ws.path / "knowledge").write_text("not-a-directory\n", encoding="utf-8")
        records = require_search_structured_success(
            run_search(ws, title, structured=True)
        )
        assert identity_in_records(records, ident)
        print("knowledge file is cwd", flush=True)


def test_named_path_without_root_index_loads_nested_knowledge():
    """Named path with no root index.md loads nested knowledge/."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        proj = unique_tokens("proj")[0]
        write_bundle(
            ws,
            f"{proj}/knowledge",
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        assert not (ws.path / proj / "index.md").exists()
        records = require_search_structured_success(
            run_search(ws, title, proj, structured=True)
        )
        assert identity_in_records(records, ident)
        print("nested knowledge named-path load ok", flush=True)


def test_named_path_with_root_index_loads_root_concept_not_nested_knowledge():
    """Named path that already has root index.md loads that concept.

    The same path also contains knowledge/ with a different concept. Loading
    resolves into that nested directory only when the named path has no root
    index.md. The root concept must be the one returned.
    """
    with workspace() as ws:
        ident, decoy_id, typ, title, desc, body, dtitle, dtok = unique_tokens(
            "id", "did", "typ", "ttl", "dsc", "bod", "dtt", "db"
        )
        proj = unique_tokens("proj")[0]
        write_bundle(
            ws,
            proj,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        write_bundle(
            ws,
            f"{proj}/knowledge",
            [
                search_concept_spec(
                    decoy_id,
                    concept_type=typ,
                    title=dtitle,
                    description=desc,
                    body=f"{dtok}\n",
                )
            ],
        )
        assert (ws.path / proj / "index.md").is_file()
        assert (ws.path / proj / "knowledge").is_dir()
        assert (ws.path / proj / "knowledge" / f"{decoy_id}.md").is_file()
        records = require_search_structured_success(
            run_search(ws, title, proj, structured=True)
        )
        assert identity_in_records(records, ident)
        assert not identity_in_records(records, decoy_id)
        root_hit = record_for_identity(records, ident)
        root_title = hit_field(root_hit, "title")
        assert root_title == title, (
            f"named path with root index did not load the root concept: {root_hit!r}"
        )
        assert root_title != dtitle, (
            f"named path with root index carried the nested knowledge concept: {root_hit!r}"
        )
        print("named path with root index loads root concept", flush=True)


def test_explicit_bundle_path_is_not_overridden_by_cwd_knowledge():
    """A named bundle is the load root even when cwd has knowledge/."""
    with workspace() as ws:
        ident, decoy_id, typ, title, desc, body, dtitle, dtok = unique_tokens(
            "id", "did", "typ", "ttl", "dsc", "bod", "dtt", "db"
        )
        named = unique_tokens("namedb")[0]
        write_bundle(
            ws,
            named,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        write_bundle(
            ws,
            "knowledge",
            [
                search_concept_spec(
                    decoy_id,
                    concept_type=typ,
                    title=dtitle,
                    description=desc,
                    body=f"{dtok}\n",
                )
            ],
        )
        records = require_search_structured_success(
            run_search(ws, title, named, structured=True)
        )
        assert identity_in_records(records, ident)
        assert not identity_in_records(records, decoy_id)
        named_hit = record_for_identity(records, ident)
        named_title = hit_field(named_hit, "title")
        assert named_title == title, (
            f"named-path hit title is not the named concept: {named_hit!r}"
        )
        assert named_title != dtitle, (
            f"named-path hit carries the knowledge-directory title: {named_hit!r}"
        )
        print("named bundle not overridden by cwd knowledge", flush=True)


# ---------------------------------------------------------------------------
# O. Escaping symlinks, hidden / node_modules / non-Markdown / reserved
# ---------------------------------------------------------------------------


def test_escaping_symlink_makes_search_a_load_error():
    """A Markdown symlink whose target leaves the bundle is a load error.

    The load does not succeed, and search fails as a load error. That
    failure is distinct from a successful search with no hit records, and
    distinct from a directory symlink, which is not walked.
    """
    with workspace() as ws:
        ident, typ, title, desc, body, otyp, otitle, odesc, otoken = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod", "ot", "ott", "od", "ob"
        )
        rel_good = unique_tokens("kbgood")[0]
        rel_bad = unique_tokens("kbbad")[0]
        specs = [
            search_concept_spec(
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=f"{body}\n",
            )
        ]
        write_bundle(ws, rel_good, specs)
        bad_root = write_bundle(ws, rel_bad, specs)
        secret = ws.write(
            f"{unique_tokens('secret')[0]}.md",
            render_concept_markdown(
                concept_type=otyp,
                title=otitle,
                description=odesc,
                body=f"{otoken}\n",
            ),
        )
        os.symlink(secret, bad_root / f"{unique_tokens('leak')[0]}.md")
        good = require_search_structured_success(
            run_search(ws, title, rel_good, structured=True)
        )
        assert identity_in_records(good, ident)
        leaked = run_search(ws, title, rel_bad, structured=True)
        require_search_load_failure(leaked)
        print("escaping symlink is load error", flush=True)


def test_escaping_directory_symlink_is_not_walked_and_search_succeeds():
    """A directory symlink whose target leaves the bundle is not walked.

    The search command loads the bundle. An in-bundle concept the query
    matches is a hit. A concept that exists only through the symlink, and
    that the same query matches when the file is a real path, is not a
    hit. The search succeeds. A non-success load fails. A hit that is the
    outside concept fails.
    """
    with workspace() as ws:
        require_escaping_directory_symlink_not_walked(ws, "command")
        print("escaping directory symlink is not walked", flush=True)


@pytest.mark.parametrize("entry", ["command", "tool"])
@pytest.mark.parametrize("kind", ["markdown-file", "directory"])
def test_escaping_symlink_load_refusal_crosses_public_entries(entry, kind):
    """Directory and Markdown symlinks have different load outcomes.

    ``command`` is ``membundle search``. ``tool`` is ``membundle_search``. A symlink
    that is itself a Markdown file and whose resolved target leaves the
    bundle makes the load not succeed: that entry fails as a load error,
    distinct from a successful search. A symlink that is a directory and
    whose resolved target leaves the bundle is not walked: the search
    succeeds, an in-bundle concept the query matches is a hit, and a
    concept that exists only through the symlink is not.
    """
    with workspace() as ws:
        if kind == "directory":
            require_escaping_directory_symlink_not_walked(ws, entry)
            print(
                f"escaping directory symlink is not walked on {entry}",
                flush=True,
            )
            return
        if kind != "markdown-file":
            raise AssertionError(f"unknown symlink kind {kind!r}")
        real_dir, stem, typ, title, desc, body = unique_tokens(
            "dir", "stem", "typ", "ttl", "dsc", "bod"
        )
        identity = f"{real_dir}/{stem}"
        concept_filename = f"{stem}.md"
        markdown = render_concept_markdown(
            concept_type=typ,
            title=title,
            description=desc,
            body=f"{body}\n",
        )
        rel_good = unique_tokens("kbgood")[0]
        rel_bad = unique_tokens("kbbad")[0]
        good_root = write_bundle(ws, rel_good, [])
        plant_markdown_file(
            good_root,
            f"{real_dir}/{concept_filename}",
            markdown,
            distinctive=title,
        )
        bad_root = write_bundle(ws, rel_bad, [])
        outside = ws.path / unique_tokens("outside")[0] / concept_filename
        plant_escaping_markdown_symlink(
            bad_root,
            concept_filename,
            markdown,
            distinctive=title,
            outside_file=outside,
        )
        require_search_tool_title_hit(ws, rel_good, title, identity)
        require_search_entry_load_refusal(ws, entry, rel_bad, title)
        print(
            f"escaping markdown-file symlink is a load refusal on {entry}",
            flush=True,
        )


def test_hidden_markdown_is_not_a_search_hit():
    """Hidden files and hidden directories are not hits; a visible sibling is.

    Names that begin with a dot are one class. The command line omits the
    planted ``.secret.md`` and a generated hidden file whose name is not
    that literal, and the visible sibling stays a hit. On the search tool
    the same bundle omits that generated hidden file and the existing
    hidden-file title, a concept under a hidden directory, a markdown file
    under a nested node_modules directory, a notes.txt title, and a nested
    log.md. A nested AGENTS.md title is a hit, and a title search for the
    visible sibling is a hit.
    """
    with workspace() as ws:
        (
            ident,
            typ,
            title,
            desc,
            body,
            htitle,
            dtitle,
            gtitle,
            gdir,
            dot_stem,
            dot_title,
        ) = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod", "htt", "dtt", "gtt", "gdr", "dfs", "dft"
        )
        (
            nm_dir,
            nm_stem,
            nm_title,
            txt_title,
            log_dir,
            log_title,
            agents_dir,
            agents_title,
        ) = unique_tokens(
            "nmd", "nms", "nmt", "txt", "lgd", "lgt", "agd", "agt"
        )
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        (root / ".secret.md").write_text(
            render_concept_markdown(
                concept_type=typ,
                title=htitle,
                description=desc,
                body=f"{body}\n",
            ),
            encoding="utf-8",
        )
        # A second hidden file, not the literal already planted above.
        dot_file_rel = f".{dot_stem}.md"
        plant_markdown_file(
            root,
            dot_file_rel,
            render_concept_markdown(
                concept_type=typ,
                title=dot_title,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=dot_title,
        )
        plant_markdown_file(
            root,
            ".hidden/note.md",
            render_concept_markdown(
                concept_type=typ,
                title=dtitle,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=dtitle,
        )
        generated_hidden = f".{gdir}/note.md"
        plant_markdown_file(
            root,
            generated_hidden,
            render_concept_markdown(
                concept_type=typ,
                title=gtitle,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=gtitle,
        )
        plant_markdown_file(
            root,
            f"{nm_dir}/node_modules/{nm_stem}.md",
            render_concept_markdown(
                concept_type=typ,
                title=nm_title,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=nm_title,
        )
        plant_markdown_file(
            root,
            "notes.txt",
            render_concept_markdown(
                concept_type=typ,
                title=txt_title,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=txt_title,
        )
        plant_markdown_file(
            root,
            f"{log_dir}/log.md",
            render_concept_markdown(
                concept_type=typ,
                title=log_title,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=log_title,
        )
        agents_identity = f"{agents_dir}/AGENTS"
        plant_markdown_file(
            root,
            f"{agents_dir}/AGENTS.md",
            render_concept_markdown(
                concept_type=typ,
                title=agents_title,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=agents_title,
        )
        live = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert identity_in_records(live, ident)
        hidden = run_search(ws, htitle, rel, structured=True)
        require_zero_hits_success(
            hidden, structured=True, live_identities=[ident, ".secret"]
        )
        hidden_file = run_search(ws, dot_title, rel, structured=True)
        require_zero_hits_success(
            hidden_file,
            structured=True,
            live_identities=[ident, f".{dot_stem}"],
        )
        under_dot_dir = run_search(ws, dtitle, rel, structured=True)
        require_zero_hits_success(
            under_dot_dir,
            structured=True,
            live_identities=[ident, ".hidden/note"],
        )
        under_generated = run_search(ws, gtitle, rel, structured=True)
        require_zero_hits_success(
            under_generated,
            structured=True,
            live_identities=[ident, f".{gdir}/note"],
        )
        require_search_tool_title_hit(ws, rel, title, ident)
        require_search_tool_title_omitted(ws, rel, htitle)
        require_search_tool_title_omitted(ws, rel, dot_title)
        require_search_tool_title_omitted(ws, rel, dtitle)
        require_search_tool_title_omitted(ws, rel, gtitle)
        require_search_tool_title_omitted(ws, rel, nm_title)
        require_search_tool_title_omitted(ws, rel, txt_title)
        require_search_tool_title_omitted(ws, rel, log_title)
        require_search_tool_title_hit(ws, rel, agents_title, agents_identity)
        print("hidden file and hidden directory are not hits", flush=True)


def test_node_modules_markdown_is_not_a_search_hit():
    """Only a directory whose name is exactly node_modules is skipped.

    The skip applies at the bundle root and under another directory. A
    directory whose name only begins with that string is loaded, and so is
    a concept file of that name. The note under the prefix directory is a
    hit for its title. The concept file is a hit for its identity.

    The command-line checks in this test are unchanged. On the search
    tool the same bundle omits the concept under the root directory of
    that exact name, and still returns the prefix-directory concept, the
    concept file of that name, and the visible sibling. Nested omission
    on the tool stays in the hidden-file test.
    """
    with workspace() as ws:
        (
            ident,
            typ,
            title,
            desc,
            body,
            ntitle,
            nest_title,
            nest_dir,
            nest_stem,
            cache_title,
            file_title,
        ) = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod", "ntt", "nst", "pkg", "ndc", "ctt", "ftt"
        )
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        nm = root / "node_modules"
        nm.mkdir()
        (nm / "decoy.md").write_text(
            render_concept_markdown(
                concept_type=typ,
                title=ntitle,
                description=desc,
                body=f"{body}\n",
            ),
            encoding="utf-8",
        )
        nested_rel = f"{nest_dir}/node_modules/{nest_stem}.md"
        nested_identity = f"{nest_dir}/node_modules/{nest_stem}"
        plant_markdown_file(
            root,
            nested_rel,
            render_concept_markdown(
                concept_type=typ,
                title=nest_title,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=nest_title,
        )
        # A directory name that only begins with node_modules is not that directory.
        cache_dir = "node_modules_cache"
        cache_rel = f"{cache_dir}/note.md"
        cache_identity = f"{cache_dir}/note"
        plant_markdown_file(
            root,
            cache_rel,
            render_concept_markdown(
                concept_type=typ,
                title=cache_title,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=cache_title,
        )
        # A markdown file named node_modules.md is not a directory of that name.
        file_rel = "node_modules.md"
        file_identity = "node_modules"
        plant_markdown_file(
            root,
            file_rel,
            render_concept_markdown(
                concept_type=typ,
                title=file_title,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=file_title,
        )
        live = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert identity_in_records(live, ident)
        decoy = run_search(ws, ntitle, rel, structured=True)
        records = require_search_structured_success(decoy)
        assert not identity_in_records(records, "node_modules/decoy")
        require_zero_hits_success(
            decoy, structured=True, live_identities=[ident, "node_modules/decoy"]
        )
        nested = run_search(ws, nest_title, rel, structured=True)
        nested_records = require_search_structured_success(nested)
        assert not identity_in_records(nested_records, nested_identity)
        require_zero_hits_success(
            nested,
            structured=True,
            live_identities=[ident, nested_identity],
        )
        cache_hit = require_search_structured_success(
            run_search(ws, cache_title, rel, structured=True)
        )
        cache_record = record_for_identity(cache_hit, cache_identity)
        assert hit_field(cache_record, "title") == cache_title, (
            f"note under {cache_dir} is not a hit for its title {cache_title!r}"
        )
        file_hit = require_search_structured_success(
            run_search(ws, file_title, rel, structured=True)
        )
        assert identity_in_records(file_hit, file_identity), (
            f"concept file {file_rel} is not a hit for identity {file_identity!r}"
        )
        # Search tool, same bundle. Root directory of that exact name is
        # omitted. A directory whose name only begins with the string, a
        # concept file of that name, and the visible sibling stay hits.
        # Omitting the directory only when nested still returns the root
        # concept. Omitting every path that contains the string drops the
        # prefix directory and the concept file.
        require_search_tool_title_omitted(ws, rel, ntitle)
        require_search_tool_title_hit(ws, rel, cache_title, cache_identity)
        require_search_tool_title_hit(ws, rel, file_title, file_identity)
        require_search_tool_title_hit(ws, rel, title, ident)
        print(
            "exact node_modules directories are not hits; "
            "a prefix directory and node_modules.md are hits",
            flush=True,
        )


def test_non_markdown_file_is_not_a_search_hit():
    """notes.txt is not a search hit.

    Only Markdown files are loaded. The notes.txt checks are unchanged.
    A second non-markdown file, whose name is not notes.txt, is omitted
    on the search command and on the search tool. The markdown sibling
    in the same bundle stays a hit on both.
    """
    with workspace() as ws:
        ident, typ, title, desc, body, ntok = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod", "ntx"
        )
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        ntitle = unique_tokens("ntt")[0]
        (root / "notes.txt").write_text(
            render_concept_markdown(
                concept_type=typ,
                title=ntitle,
                description=desc,
                body=f"{ntok}\n",
            ),
            encoding="utf-8",
        )
        other_stem, other_title = unique_tokens("jst", "jtt")
        other_name = other_non_markdown_filename(other_stem)
        plant_markdown_file(
            root,
            other_name,
            render_concept_markdown(
                concept_type=typ,
                title=other_title,
                description=desc,
                body=f"{other_stem}\n",
            ),
            distinctive=other_title,
        )
        live = require_search_structured_success(
            run_search(ws, title, rel, structured=True)
        )
        assert identity_in_records(live, ident)
        txt = run_search(ws, ntitle, rel, structured=True)
        require_zero_hits_success(txt, structured=True, live_identities=[ident])
        print("non-markdown is not a hit", flush=True)
        other = run_search(ws, other_title, rel, structured=True)
        require_zero_hits_success(
            other, structured=True, live_identities=[ident]
        )
        require_search_tool_title_hit(ws, rel, title, ident)
        require_search_tool_title_omitted(ws, rel, other_title)
        print(
            "non-markdown file other than notes.txt is not a hit",
            flush=True,
        )


def test_reserved_index_and_log_are_not_search_hits():
    """Root index.md / log.md and a nested log.md are not concept hits."""
    with workspace() as ws:
        (
            ident,
            typ,
            title,
            desc,
            body,
            body_tok,
            reserved,
            rtitle,
            nest,
            sib,
            stitle,
            ntitle,
            nbody,
        ) = unique_tokens(
            "id",
            "typ",
            "ttl",
            "dsc",
            "bod",
            "btk",
            "rsv",
            "rtt",
            "nest",
            "sib",
            "stt",
            "nlg",
            "nlb",
        )
        rel = _kb()
        sib_ident = f"{nest}/{sib}"
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body_tok}\n",
                ),
                search_concept_spec(
                    sib_ident,
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                ),
            ],
        )
        shaped = render_concept_markdown(
            concept_type=typ,
            title=rtitle,
            description=desc,
            body=f"{reserved}\n",
        )
        (root / "index.md").write_text(shaped, encoding="utf-8")
        (root / "log.md").write_text(shaped, encoding="utf-8")
        plant_markdown_file(
            root,
            f"{nest}/log.md",
            render_concept_markdown(
                concept_type=typ,
                title=ntitle,
                description=desc,
                body=f"{nbody}\n",
            ),
            distinctive=nbody,
        )
        live = require_search_structured_success(
            run_search(ws, body_tok, rel, structured=True)
        )
        assert identity_in_records(live, ident)
        reserved_hits = run_search(ws, reserved, rel, structured=True)
        require_zero_hits_success(
            reserved_hits, structured=True, live_identities=[ident, sib_ident]
        )
        sibling = require_search_structured_success(
            run_search(ws, stitle, rel, structured=True)
        )
        assert identity_in_records(sibling, sib_ident)
        require_zero_hits_success(
            run_search(ws, ntitle, rel, structured=True),
            structured=True,
            live_identities=[ident, sib_ident],
        )
        require_zero_hits_success(
            run_search(ws, nbody, rel, structured=True),
            structured=True,
            live_identities=[ident, sib_ident],
        )
        print("reserved index/log and nested log are not hits", flush=True)


def test_reserved_nested_index_and_root_agents_are_not_search_hits():
    """Nested index and root AGENTS.md are not hits; nested AGENTS.md is.

    The command-line checks below are unchanged. On the search tool the
    same bundle omits a concept-shaped root index.md, the nested index.md,
    the bundle-root log.md, and the bundle-root AGENTS.md. The normal
    sibling and the nested AGENTS.md stay hits, so an empty tool result
    and a tool that drops every AGENTS.md both fail. The closed tool
    checks for a nested log.md and a nested AGENTS.md in the hidden-file
    test are unchanged.
    """
    with workspace() as ws:
        sib, typ, stitle, desc, body, nidx, nag, nagt, rix, rlg = unique_tokens(
            "sib", "typ", "stt", "dsc", "bod", "nidx", "nag", "zqx", "rix", "rlg"
        )
        rel = _kb()
        nested_ident = "dir/AGENTS"
        sib_ident = f"dir/{sib}"
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    f"dir/{sib}",
                    concept_type=typ,
                    title=stitle,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
            agents=render_concept_markdown(
                concept_type=typ,
                title=nag,
                description=desc,
                body=f"{body}\n",
            ),
        )
        # Concept-shaped navigation files. A tool that indexes them returns
        # these titles; the command-line checks below do not search them.
        plant_markdown_file(
            root,
            "index.md",
            render_concept_markdown(
                concept_type=typ,
                title=rix,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=rix,
        )
        plant_markdown_file(
            root,
            "log.md",
            render_concept_markdown(
                concept_type=typ,
                title=rlg,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=rlg,
        )
        (root / "dir" / "index.md").write_text(
            render_concept_markdown(
                concept_type=typ,
                title=nidx,
                description=desc,
                body=f"{body}\n",
            ),
            encoding="utf-8",
        )
        plant_markdown_file(
            root,
            "dir/AGENTS.md",
            render_concept_markdown(
                concept_type=typ,
                title=nagt,
                description=desc,
                body=f"{body}\n",
            ),
            distinctive=nagt,
        )
        live = require_search_structured_success(
            run_search(ws, stitle, rel, structured=True)
        )
        assert identity_in_records(live, sib_ident)
        idx_hits = require_search_structured_success(
            run_search(ws, nidx, rel, structured=True)
        )
        assert idx_hits == [], f"nested index title was a hit: {idx_hits!r}"
        agents_hits = require_search_structured_success(
            run_search(ws, nag, rel, structured=True)
        )
        assert agents_hits == [], f"root AGENTS title was a hit: {agents_hits!r}"
        nested_hits = require_search_structured_success(
            run_search(ws, nagt, rel, structured=True)
        )
        assert identity_in_records(nested_hits, nested_ident), (
            f"nested AGENTS.md title was not a hit: {nested_hits!r}"
        )
        require_core_fields(
            record_for_identity(nested_hits, nested_ident),
            nested_ident,
            typ,
            nagt,
            desc,
        )
        print("nested index and root AGENTS are not hits", flush=True)
        # Search tool, same bundle. Root index, nested index, root log, and
        # root AGENTS are absent. The sibling and the nested AGENTS stay.
        require_search_tool_title_omitted(ws, rel, rix)
        require_search_tool_title_omitted(ws, rel, nidx)
        require_search_tool_title_omitted(ws, rel, rlg)
        require_search_tool_title_omitted(ws, rel, nag)
        require_search_tool_title_hit(ws, rel, stitle, sib_ident)
        require_search_tool_title_hit(ws, rel, nagt, nested_ident)
        print(
            "search tool omits root index, nested index, root log, "
            "and root AGENTS; sibling and nested AGENTS stay hits",
            flush=True,
        )


# ---------------------------------------------------------------------------
# P. Search does not write the bundle
# ---------------------------------------------------------------------------


def test_search_success_does_not_mutate_bundle_files():
    """Keyword success, and a path search that returns hits, leave bundle bytes unchanged.

    Search does not write the bundle. A keyword search that returns hits
    is one cell on human text when structured output is not requested,
    one cell on structured command-line output, and one cell on the
    search tool. Each cell reads bundle bytes immediately before that
    call and immediately after it, with no other search call between the
    two reads. A later call that puts the bytes back does not hide an
    earlier write.

    A path search that returns the planted concept stays as it was:
    command-line human text, command-line structured output, and the
    search tool. Each of those calls is compared to the bytes taken
    before any path search.
    """
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        assert_snapshot_helper_sees_write(ws, unique_tokens("probe")[0])
        human = require_search_success(
            require_call_leaves_bundle_bytes_unchanged(
                root,
                lambda: run_search(ws, title, rel, structured=False),
                label="keyword search on human text",
            )
        )
        assert_identifiable_human_hits(
            human, [("context", (ident, title, desc))]
        )
        records = require_search_structured_success(
            require_call_leaves_bundle_bytes_unchanged(
                root,
                lambda: run_search(ws, title, rel, structured=True),
                label="keyword search on structured command-line output",
            )
        )
        assert identity_in_records(records, ident)
        mcp_records = require_mcp_search_success(
            require_call_leaves_bundle_bytes_unchanged(
                root,
                lambda: mcp_search(ws, query=title, bundle=rel),
                label="keyword search on the search tool",
            )
        )
        assert identity_in_records(mcp_records, ident)
        print("keyword success cells unchanged", flush=True)

    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        path = f"pkg/{compact_token('p')}/x.go"
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[path],
                )
            ],
        )
        assert_snapshot_helper_sees_write(ws, unique_tokens("probe")[0])
        before = snapshot_tree(root)
        human = require_search_success(run_search(ws, None, rel, for_path=path))
        assert_identifiable_human_hits(
            human, [("context", (ident, title, desc))]
        )
        after_human = snapshot_tree(root)
        assert before == after_human, (
            f"command-line path search mutated bundle files; "
            f"before={sorted(before)} after={sorted(after_human)}"
        )
        records = require_search_structured_success(
            run_search(ws, None, rel, for_path=path, structured=True)
        )
        assert identity_in_records(records, ident), (
            f"structured path search omitted the concept {ident!r}: {records!r}"
        )
        after_structured = snapshot_tree(root)
        assert before == after_structured, (
            f"structured path search mutated bundle files; "
            f"before={sorted(before)} after={sorted(after_structured)}"
        )
        mcp_records = require_mcp_search_success(
            mcp_search(ws, for_path=path, bundle=rel)
        )
        assert identity_in_records(mcp_records, ident), (
            f"path search tool omitted the concept {ident!r}: {mcp_records!r}"
        )
        after_tool = snapshot_tree(root)
        assert before == after_tool, (
            f"path search tool mutated bundle files; "
            f"before={sorted(before)} after={sorted(after_tool)}"
        )
        print("path-search snapshot unchanged", flush=True)


def test_search_failures_and_zero_hits_do_not_create_or_mutate_files():
    """Zero-hit, usage, and a missing bundle leave bundle bytes unchanged.

    Search does not write the bundle. The command that prints usage
    because neither a query nor a path was supplied reads bundle bytes
    immediately before that call and immediately after it. One
    command-line zero-hit that requests optional structured output does
    the same. The command's human zero-hit, the command's missing-bundle
    load error, and those two outcomes on the search tool stay isolated
    cells. The usage call does not sit between either of those command
    cells' two reads.
    """
    with workspace() as ws:
        ident, typ, title, desc, body, miss = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod", "miss"
        )
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                )
            ],
        )
        assert_snapshot_helper_sees_write(ws, unique_tokens("probe2")[0])
        human_live = require_search_success(run_search(ws, title, rel))

        before_cmd_zero = snapshot_tree(root)
        zero_result = run_search(ws, miss, rel)
        after_cmd_zero = snapshot_tree(root)
        assert before_cmd_zero == after_cmd_zero, (
            "command-line zero-hit mutated bundle files; "
            f"before={sorted(before_cmd_zero)} after={sorted(after_cmd_zero)}"
        )
        zero_report = require_zero_hits_success(
            zero_result,
            structured=False,
            live_identities=[ident],
        )
        assert_human_zero_hit_miss_statement(
            zero_report,
            human_live,
            path_tokens_for_search(rel, ws.path),
            (ident, typ, title, desc, body, miss),
            live_identities=[ident],
        )
        print("command zero-hit snapshot unchanged", flush=True)

        struct_zero = require_call_leaves_bundle_bytes_unchanged(
            root,
            lambda: run_search(ws, miss, rel, structured=True),
            label="structured command-line zero-hit",
        )
        require_zero_hits_success(
            struct_zero,
            structured=True,
            live_identities=[ident],
        )
        print("structured command-line zero-hit snapshot unchanged", flush=True)

        usage = require_call_leaves_bundle_bytes_unchanged(
            root,
            # TEST-FIX(F04): with no bin/membundle there is no product to run before search; per the Contract "Build" form, make build at the repository root writes that binary.
            lambda: run_search(ws),
            label="command that prints usage",
        )
        print("usage snapshot unchanged", flush=True)

        missing = unique_tokens("gone")[0]
        missing_path = ws.path / missing
        assert not missing_path.exists()
        before_cmd_load = snapshot_tree(root)
        load = run_search(ws, title, missing)
        after_cmd_load = snapshot_tree(root)
        assert before_cmd_load == after_cmd_load, (
            "command-line missing-bundle search mutated bundle files; "
            f"before={sorted(before_cmd_load)} after={sorted(after_cmd_load)}"
        )
        assert not missing_path.exists(), (
            f"search of a missing bundle created {missing_path}"
        )
        require_search_usage_failure(
            usage,
            zero_report,
            combined_report(load),
            path_tokens_for_search(rel, ws.path, missing),
            (ident, typ, title, desc, body, miss, missing),
        )
        require_search_load_error(
            load,
            combined_report(usage),
            path_tokens_for_search(rel, ws.path, missing),
            (ident, typ, title, desc, body, miss, missing),
            zero_report,
        )
        print("command missing-bundle snapshot unchanged", flush=True)

        before_tool_zero = snapshot_tree(root)
        tool_zero = require_mcp_search_success(
            mcp_search(ws, query=miss, bundle=rel)
        )
        assert tool_zero == [], (
            f"search tool zero-hit returned hits: {tool_zero!r}"
        )
        after_tool_zero = snapshot_tree(root)
        assert before_tool_zero == after_tool_zero, (
            "search tool zero-hit mutated bundle files; "
            f"before={sorted(before_tool_zero)} after={sorted(after_tool_zero)}"
        )
        print("search tool zero-hit snapshot unchanged", flush=True)

        tool_missing = unique_tokens("tgone")[0]
        tool_missing_path = ws.path / tool_missing
        assert not tool_missing_path.exists()
        before_tool_load = snapshot_tree(root)
        tool_load = mcp_search(ws, query=title, bundle=tool_missing)
        require_mcp_search_load_failure(tool_load)
        assert not tool_missing_path.exists(), (
            f"search tool of a missing bundle created {tool_missing_path}"
        )
        after_tool_load = snapshot_tree(root)
        assert before_tool_load == after_tool_load, (
            "search tool load error mutated bundle files; "
            f"before={sorted(before_tool_load)} after={sorted(after_tool_load)}"
        )
        print("search tool load-error snapshot unchanged", flush=True)


# ---------------------------------------------------------------------------
# Q. MCP membundle_search is the same search; identical reruns are deterministic
# ---------------------------------------------------------------------------


def _reject_fixture_token_overlap(token: str, occupied: list[str], label: str) -> None:
    """Fixture tokens must not sit inside each other.

    Keyword matching treats a field token that equals the query or starts
    with it as a hit. Overlapping fixture tokens would make a correct
    search return a concept this test meant to keep free of that term.
    """
    folded = token.casefold()
    if not folded:
        raise AssertionError(f"fixture token {label} is empty")
    for other in occupied:
        other_folded = str(other).casefold()
        if not other_folded:
            raise AssertionError(f"occupied fixture text for {label} is empty")
        if folded in other_folded or other_folded in folded:
            raise AssertionError(
                f"fixture token {label}={token!r} overlaps occupied text {other!r}"
            )


def _assert_sole_term_copy(root, identity: str, term: str, field: str) -> None:
    """Fixture guard: *term* occurs once, and only in *field* of this concept.

    Does not call the product. A second copy in another keyword field, or
    in the filename when the field is not the concept identity, would make
    a hit on this concept mean something other than the field under test.
    """
    path = root / f"{identity}.md"
    text = path.read_text(encoding="utf-8")
    mapping, body = split_yaml_frontmatter(text)
    needle = term.lower()
    ident_count = identity.lower().count(needle)
    if field == "id":
        if ident_count != 1:
            raise AssertionError(
                f"identity {identity!r} should contain {term!r} once, "
                f"found {ident_count}"
            )
        if needle in text.lower():
            raise AssertionError(
                f"identity plant {identity!r} also copies {term!r} into the file"
            )
        return
    if ident_count != 0:
        raise AssertionError(
            f"{field} plant identity {identity!r} contains {term!r}"
        )
    if text.lower().count(needle) != 1:
        raise AssertionError(
            f"{field} plant {identity!r} should contain {term!r} once in the "
            f"file; count={text.lower().count(needle)}"
        )
    if field == "body":
        if needle not in body.lower() or needle in mapping.lower():
            raise AssertionError(
                f"body plant {identity!r} does not keep {term!r} only in the body"
            )
        return
    if needle in body.lower():
        raise AssertionError(
            f"{field} plant {identity!r} copies {term!r} into the body"
        )
    if field == "tags":
        tag_lines = [
            line
            for line in mapping.splitlines()
            if line[:1].isspace() and needle in line.lower()
        ]
        other = [
            line
            for line in mapping.splitlines()
            if needle in line.lower() and not line[:1].isspace()
        ]
        if len(tag_lines) != 1 or other:
            raise AssertionError(
                f"tag plant {identity!r} does not keep {term!r} on one tag "
                f"line; tag_lines={tag_lines!r} other={other!r}"
            )
        return
    if field not in ("title", "description"):
        raise AssertionError(f"unknown sole-copy field {field!r}")
    key_lines = [
        line
        for line in mapping.splitlines()
        if line.lower().startswith(f"{field}:") and needle in line.lower()
    ]
    elsewhere = [
        line
        for line in mapping.splitlines()
        if needle in line.lower() and not line.lower().startswith(f"{field}:")
    ]
    if len(key_lines) != 1 or elsewhere:
        raise AssertionError(
            f"{field} plant {identity!r} does not keep {term!r} on that "
            f"field; lines={key_lines!r} elsewhere={elsewhere!r}"
        )


def test_mcp_keyword_search_returns_the_same_ordered_identities_as_cli():
    """MCP keyword order matches CLI, and each tool hit carries the structured shape.

    Identity order is not enough. A tool keyword hit also carries type,
    title, description, effective governance, a numeric score, and the
    keyword fields that matched. The titled concept has a code_refs path,
    a tag, and a link; that hit names the path, the tag, and the outbound
    identity. The incidental-body concept has none of those. A later tool
    query for the link target names the titled concept as inbound.

    Two further concepts keep that same query term only in type, and only
    in code_refs. Keyword search on the tool omits both, and the command
    line on the same plants omits both. A tool query for each concept's
    own title still returns that concept, so dropping the file is not a
    pass.

    One further concept keeps that same query term only in its resource
    field. The field is not governance. Keyword search on the tool omits
    that concept, and the command line on the same plant omits it. A tool
    query for that concept's own title still returns it, so dropping the
    file at load time is not a pass.

    A second bundle, queried only through the search tool, plants one
    later token that is longer than the query and only starts with it.
    That token is the only copy of the query, in a title, a tag, a
    description, a body, and a concept identity. Each of those concepts
    is returned. The tags-only hit names tags, the description-only hit
    names description, and the identity-only hit names id; on each of
    those hits the other members of that set are absent. A mid-token
    substring in each of those fields is omitted. A separate tool query
    for a token those omitted concepts carry still returns them, so
    dropping the file is not a pass.

    A further bundle, queried only through the search tool and with no
    path, declares Hold, Constraint, and Context in a spelling that is
    not already the lowercase word. Hold and Constraint sit outside
    convention/, so an omitted value would be context. Context sits
    under convention/, so an omitted value would be constraint. Each
    keyword hit's effective governance is the lowercase word.
    """
    with workspace() as ws:
        term = compact_token("par")
        body_id = f"abody{term}"
        titled_id = f"ztitle{term}"
        assert body_id < titled_id
        typ, desc, filler, target_id, label = unique_tokens(
            "typ", "dsc", "fil", "tgt", "lbl"
        )
        tag = compact_token("tag")
        path = f"pkg/{compact_token('p')}/x.go"
        href = f"{target_id}.md"
        incidental = f"Incidental {term} once.\n"
        titled_body = f"{filler}\n\n{markdown_link(label, href)}\n"
        target_body = f"{label}\n"
        target_title = compact_token("qtt")
        (
            type_only_id,
            refs_only_id,
            type_title,
            refs_title,
            filler_type,
            type_body,
            refs_body,
            resource_only_id,
            resource_title,
            resource_body,
        ) = unique_compact(
            "tyo",
            "cro",
            "ttl",
            "rtl",
            "fty",
            "tbd",
            "rbd",
            "rso",
            "rst",
            "rsb",
        )
        if term.casefold() in path.casefold():
            raise AssertionError(
                f"titled concept code_refs path contains the query term {term!r}"
            )
        refs_path = f"pkg/{term}/file.go"
        occupied = [
            term,
            body_id,
            titled_id,
            typ,
            desc,
            filler,
            target_id,
            label,
            tag,
            path,
            href,
            incidental,
            titled_body,
            target_body,
            target_title,
            refs_path,
        ]
        for token, label in (
            (type_only_id, "type-only identity"),
            (refs_only_id, "code_refs-only identity"),
            (type_title, "type-only title"),
            (refs_title, "code_refs-only title"),
            (filler_type, "code_refs-only type"),
            (type_body, "type-only body"),
            (refs_body, "code_refs-only body"),
            (resource_only_id, "resource-only identity"),
            (resource_title, "resource-only title"),
            (resource_body, "resource-only body"),
        ):
            _reject_fixture_token_overlap(token, occupied, label)
        rel = _kb()
        root = write_bundle(
            ws,
            rel,
            [
                search_concept_spec(
                    body_id,
                    concept_type=typ,
                    title=filler,
                    description=desc,
                    body=incidental,
                ),
                search_concept_spec(
                    titled_id,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=titled_body,
                    tags=[tag],
                    code_refs=[path],
                ),
                search_concept_spec(
                    target_id,
                    concept_type=typ,
                    title=target_title,
                    description=desc,
                    body=target_body,
                ),
                search_concept_spec(
                    type_only_id,
                    concept_type=term,
                    title=type_title,
                    description=desc,
                    body=f"{type_body}\n",
                ),
                search_concept_spec(
                    refs_only_id,
                    concept_type=filler_type,
                    title=refs_title,
                    description=desc,
                    body=f"{refs_body}\n",
                    code_refs=[refs_path],
                ),
                search_concept_spec(
                    resource_only_id,
                    concept_type=filler_type,
                    title=resource_title,
                    description=desc,
                    body=f"{resource_body}\n",
                    resource=term,
                ),
            ],
        )
        _planted_type_is_the_only_copy_of_term(root / f"{type_only_id}.md", term)
        require_planted_code_refs_is_sole_copy(
            root / f"{refs_only_id}.md", term, refs_path
        )
        require_planted_resource_is_sole_copy(
            root / f"{resource_only_id}.md", term
        )
        cli = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        mcp = require_mcp_search_success(mcp_search(ws, query=term, bundle=rel))
        for ident, where in (
            (type_only_id, "type"),
            (refs_only_id, "code_refs"),
        ):
            assert not identity_in_records(cli, ident), (
                f"command-line keyword search returned {ident!r}; "
                f"the term lives only in {where}"
            )
            assert not identity_in_records(mcp, ident), (
                f"search tool returned {ident!r} for a term that lives only "
                f"in {where}; the command line omits that concept"
            )
        assert not identity_in_records(cli, resource_only_id), (
            f"command-line keyword search returned {resource_only_id!r}; "
            "the term lives only in resource"
        )
        assert not identity_in_records(mcp, resource_only_id), (
            f"search tool returned {resource_only_id!r} for a term that "
            "lives only in resource; the command line omits that concept"
        )
        cli_order = hit_identities(cli, [titled_id, body_id])
        mcp_order = hit_identities(mcp, [titled_id, body_id])
        assert cli_order == mcp_order == [titled_id, body_id]
        titled = record_for_identity(mcp, titled_id)
        body_hit = record_for_identity(mcp, body_id)
        require_core_fields(titled, titled_id, typ, term, desc)
        require_core_fields(body_hit, body_id, typ, filler, desc)
        titled_own = [
            titled_id,
            typ,
            term,
            desc,
            titled_body,
            filler,
            tag,
            path,
            href,
            label,
            target_id,
            incidental,
            body_id,
        ]
        body_own = [
            body_id,
            typ,
            filler,
            desc,
            incidental,
            term,
            titled_id,
            titled_body,
            tag,
            path,
            href,
            label,
            target_id,
        ]
        assert_single_effective_governance(titled, "context", titled_own)
        assert_single_effective_governance(body_hit, "context", body_own)
        assert record_has_json_number(titled), (
            f"titled tool hit has no numeric score: {titled!r}"
        )
        assert record_has_json_number(body_hit), (
            f"incidental-body tool hit has no numeric score: {body_hit!r}"
        )
        assert_matched_keyword_fields(titled, titled_own, ["title"])
        assert_matched_keyword_fields(body_hit, body_own, ["body"])
        assert path in hit_list(titled, "code_refs"), (
            f"tool hit omitted the concept's code_refs path: {titled!r}"
        )
        assert tag in hit_list(titled, "tags"), (
            f"tool hit omitted the concept's tag: {titled!r}"
        )
        assert target_id in hit_list(titled, "outbound"), (
            f"tool hit omitted the outbound identity: {titled!r}"
        )
        assert path not in hit_list(body_hit, "code_refs"), (
            "incidental-body tool hit carries a code_refs path it does not have"
        )
        assert tag not in hit_list(body_hit, "tags"), (
            "incidental-body tool hit carries a tag it does not have"
        )
        assert target_id not in hit_list(body_hit, "outbound"), (
            "incidental-body tool hit carries an outbound identity it does not have"
        )
        inbound_hits = require_mcp_search_success(
            mcp_search(ws, query=target_title, bundle=rel)
        )
        require_identity_order(inbound_hits, [target_id])
        target_hit = record_for_identity(inbound_hits, target_id)
        target_own = [
            target_id,
            typ,
            target_title,
            desc,
            target_body,
            label,
            href,
            titled_id,
            term,
        ]
        require_core_fields(target_hit, target_id, typ, target_title, desc)
        assert_single_effective_governance(target_hit, "context", target_own)
        assert record_has_json_number(target_hit), (
            f"inbound tool hit has no numeric score: {target_hit!r}"
        )
        assert_matched_keyword_fields(target_hit, target_own, ["title"])
        assert path not in hit_list(target_hit, "code_refs")
        assert tag not in hit_list(target_hit, "tags")
        assert titled_id in hit_list(target_hit, "inbound"), (
            f"tool hit omitted the inbound identity: {target_hit!r}"
        )
        by_type_title = require_mcp_search_success(
            mcp_search(ws, query=type_title, bundle=rel)
        )
        assert identity_in_records(by_type_title, type_only_id), (
            f"tool title query {type_title!r} omitted {type_only_id!r}; "
            "the type-only concept was not loaded"
        )
        for ident in (refs_only_id, titled_id, body_id, target_id):
            assert not identity_in_records(by_type_title, ident), (
                f"tool title query {type_title!r} returned {ident!r}"
            )
        by_refs_title = require_mcp_search_success(
            mcp_search(ws, query=refs_title, bundle=rel)
        )
        assert identity_in_records(by_refs_title, refs_only_id), (
            f"tool title query {refs_title!r} omitted {refs_only_id!r}; "
            "the code_refs-only concept was not loaded"
        )
        for ident in (type_only_id, titled_id, body_id, target_id):
            assert not identity_in_records(by_refs_title, ident), (
                f"tool title query {refs_title!r} returned {ident!r}"
            )
        by_resource_title = require_mcp_search_success(
            mcp_search(ws, query=resource_title, bundle=rel)
        )
        assert identity_in_records(by_resource_title, resource_only_id), (
            f"tool title query {resource_title!r} omitted {resource_only_id!r}; "
            "the resource-only concept was not loaded"
        )
        for ident in (type_only_id, refs_only_id, titled_id, body_id, target_id):
            assert not identity_in_records(by_resource_title, ident), (
                f"tool title query {resource_title!r} returned {ident!r}"
            )

        # Tool keyword prefix, separate bundle so the exact title token and
        # the incidental body token above stay the only hits of that query.
        # The command-line five-field prefix checks are left as they are.
        (
            needle,
            lead,
            shared,
            typ_p,
            title_f,
            desc_f,
            body_f,
            id_title,
            id_tags,
            id_desc,
            id_body,
            id_title_m,
            id_tags_m,
            id_desc_m,
            id_body_m,
        ) = unique_compact(
            "px",
            "ld",
            "sh",
            "ty",
            "tf",
            "df",
            "bf",
            "ttl",
            "tag",
            "dsc",
            "bod",
            "ttm",
            "tgm",
            "dcm",
            "bdm",
        )
        prefix_token = f"{needle}run"
        mid_token = f"zz{needle}zz"
        later = f"{lead} {prefix_token}"
        mid_field = f"{lead} {mid_token}"
        id_pre = f"{lead}/{prefix_token}"
        id_mid = f"{lead}/{mid_token}"
        assert prefix_token.startswith(needle) and len(prefix_token) > len(needle)
        assert prefix_token != needle
        assert prefix_token.lower().count(needle.lower()) == 1
        assert later.split(" ") == [lead, prefix_token]
        assert not later.lower().startswith(needle.lower())
        assert needle.lower() in mid_token.lower()
        assert not mid_token.lower().startswith(needle.lower())
        assert mid_token != needle
        assert mid_token.lower().count(needle.lower()) == 1
        assert mid_field.split(" ") == [lead, mid_token]
        assert not mid_field.lower().startswith(needle.lower())
        assert id_pre.split("/") == [lead, prefix_token]
        assert not id_pre.lower().startswith(needle.lower())
        assert id_mid.split("/") == [lead, mid_token]
        assert not id_mid.lower().startswith(needle.lower())
        assert not lead.lower().startswith("convention")
        field_tokens_do_not_start_with(
            needle,
            lead,
            shared,
            typ_p,
            title_f,
            desc_f,
            body_f,
            id_title,
            id_tags,
            id_desc,
            id_body,
            id_title_m,
            id_tags_m,
            id_desc_m,
            id_body_m,
        )
        field_tokens_do_not_start_with(
            shared,
            needle,
            lead,
            typ_p,
            title_f,
            desc_f,
            body_f,
            later,
            mid_field,
            id_pre,
            id_mid,
            id_title,
            id_tags,
            id_desc,
            id_body,
        )

        def _prefix_spec(ident: str, **fields: object):
            return search_concept_spec(
                ident,
                concept_type=typ_p,
                title=str(fields.get("title", title_f)),
                description=str(fields.get("description", desc_f)),
                body=str(fields.get("body", f"{body_f}\n")),
                tags=list(fields["tags"]) if "tags" in fields else None,
            )

        prefix_ids = {
            "title": id_title,
            "tags": id_tags,
            "description": id_desc,
            "body": id_body,
            "id": id_pre,
        }
        mid_ids = {
            "title": id_title_m,
            "tags": id_tags_m,
            "description": id_desc_m,
            "body": id_body_m,
            "id": id_mid,
        }
        prefix_bundle = _kb()
        prefix_root = write_bundle(
            ws,
            prefix_bundle,
            [
                _prefix_spec(id_title, title=later),
                _prefix_spec(id_tags, tags=[later]),
                _prefix_spec(id_desc, description=later),
                _prefix_spec(id_pre),
                _prefix_spec(id_body, body=f"{later}\n"),
                _prefix_spec(id_title_m, title=mid_field, body=f"{shared}\n"),
                _prefix_spec(id_tags_m, tags=[mid_field], title=shared),
                _prefix_spec(id_desc_m, description=mid_field, title=shared),
                _prefix_spec(id_body_m, body=f"{mid_field}\n", title=shared),
                _prefix_spec(id_mid, title=shared),
            ],
        )
        for field, ident in prefix_ids.items():
            _assert_sole_term_copy(prefix_root, ident, needle, field)
        for field, ident in mid_ids.items():
            _assert_sole_term_copy(prefix_root, ident, needle, field)
        tool_prefix = require_mcp_search_success(
            mcp_search(ws, query=needle, bundle=prefix_bundle)
        )
        assert len(tool_prefix) == len(prefix_ids), (
            "search tool prefix query returned "
            f"{len(tool_prefix)} hits; the later prefix token is the only "
            f"copy of {needle!r} on five concepts"
        )
        for field, ident in prefix_ids.items():
            assert identity_in_records(tool_prefix, ident), (
                f"search tool omitted {ident!r}; the only copy of {needle!r} "
                f"is a later token on {field} that is longer than the query "
                f"and starts with it ({later!r})"
            )
        # Title and body on this tool stay on the titled hit and the
        # incidental body hit above. These three hits are the ones that
        # matched only tags, only description, or only identity.
        sole_field_hits = (
            (
                "tags",
                id_tags,
                [later, id_tags, typ_p, title_f, desc_f, body_f, lead, prefix_token],
            ),
            (
                "description",
                id_desc,
                [later, id_desc, typ_p, title_f, body_f, lead, prefix_token],
            ),
            (
                "id",
                id_pre,
                [id_pre, typ_p, title_f, desc_f, body_f, lead, prefix_token],
            ),
        )
        for field, ident, strip in sole_field_hits:
            assert_matched_keyword_fields(
                record_for_identity(tool_prefix, ident),
                strip,
                [field],
            )
        for field, ident in mid_ids.items():
            assert not identity_in_records(tool_prefix, ident), (
                f"search tool returned {ident!r}; {needle!r} is only a "
                f"mid-token substring on {field} ({mid_field!r})"
            )
        tool_loaded = require_mcp_search_success(
            mcp_search(ws, query=shared, bundle=prefix_bundle)
        )
        assert len(tool_loaded) == len(mid_ids), (
            "search tool did not return each mid-token concept from the "
            f"token those concepts carry outside the query; hits={len(tool_loaded)}"
        )
        for field, ident in mid_ids.items():
            assert identity_in_records(tool_loaded, ident), (
                f"search tool omitted mid-token concept {ident!r} on a query "
                f"for the token it carries outside {field}; the file was not loaded"
            )
        for ident in prefix_ids.values():
            assert not identity_in_records(tool_loaded, ident), (
                f"search tool returned prefix concept {ident!r} for a token "
                "that concept does not carry"
            )

        # Keyword search on the tool supplies no path. The command-line
        # keyword fold and the tool path-hit fold stay in their own tests.
        # Hold and Constraint sit outside convention/, so an omitted value
        # is context. Context sits under convention/, so an omitted value
        # is constraint. Each declared spelling differs from that default
        # and from the lowercase word.
        declared_folds = (
            ("Hold", False),
            ("Constraint", False),
            ("Context", True),
        )
        for declared, under_convention in declared_folds:
            effective = declared.lower()
            omit_default = "constraint" if under_convention else "context"
            if effective == omit_default or declared == effective:
                raise AssertionError(
                    "mixed spelling must differ from the lowercase word "
                    "and from the default for an omitted value: "
                    f"declared={declared!r} default={omit_default!r}"
                )
            leaf, typ, title, desc, body = unique_tokens(
                "mid", "typ", "ttl", "dsc", "bod"
            )
            ident = f"convention/{leaf}" if under_convention else leaf
            if under_convention:
                if not ident.startswith("convention/") or ident.count("/") != 1:
                    raise AssertionError(
                        "context fold identity is not convention/<leaf>: "
                        f"{ident!r}"
                    )
            elif ident.startswith("convention"):
                raise AssertionError(
                    "hold and constraint folds sit outside convention/: "
                    f"{ident!r}"
                )
            fold_rel = _kb()
            spec = search_concept_spec(
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=f"{body}\n",
                governance=declared,
            )
            if (spec.get("extra") or {}).get("governance") != declared:
                raise AssertionError(
                    "keyword concept must declare the mixed spelling "
                    f"{declared!r}"
                )
            fold_root = write_bundle(ws, fold_rel, [spec])
            planted = (fold_root / f"{ident}.md").read_text(encoding="utf-8")
            if f"governance: {declared}" not in planted:
                raise AssertionError(
                    f"planted file does not declare {declared!r}"
                )
            if f"governance: {effective}\n" in planted:
                raise AssertionError(
                    "planted file stored the lowercase word "
                    f"{effective!r}; the fold would be invisible"
                )
            tool_hits = require_mcp_search_success(
                mcp_search(ws, query=title, bundle=fold_rel)
            )
            assert_folded_declared_governance(
                record_for_identity(tool_hits, ident),
                declared,
                [ident, typ, title, desc, body],
            )
            print(
                f"tool keyword {declared!r} effective {effective!r}",
                flush=True,
            )
        print("MCP keyword order and structured hit shape ok", flush=True)


def test_mcp_equal_keyword_scores_cap_1_returns_ascending_identity():
    """Keyword tool, two equal title scores, cap 1: the earlier identity.

    The later identity is written first, so ordering by score and breaking
    the tie by write order keeps that later identity. The query is keyword
    only. The identities are a runtime pair, not the literals alpha and zeta.
    """
    with workspace() as ws:
        early_id = f"aaa{compact_token('a')}"
        late_id = f"zzz{compact_token('z')}"
        title = compact_token("sh")
        rel = _kb()
        write_order = plant_keyword_score_tie_later_first(
            ws, rel, title, early_id, late_id
        )
        assert write_order[0] > write_order[1], (
            "fixture write order is already identity ascending; "
            "this call cannot tell identity order from write order; "
            f"write_order={write_order!r}"
        )
        capped = require_mcp_search_success(
            mcp_search(ws, query=title, bundle=rel, limit=1)
        )
        ordered = require_identity_order(capped, [early_id])
        assert ordered == [early_id], (
            "equal keyword scores on the search tool must keep the "
            "ascending identity when the cap is 1; "
            f"order={ordered!r} write_order={write_order!r}"
        )
        assert ordered[0] != write_order[0], (
            "cap 1 returned the first written identity; equal keyword "
            f"scores must break the tie by identity; order={ordered!r} "
            f"write_order={write_order!r}"
        )
        both = require_mcp_search_success(
            mcp_search(ws, query=title, bundle=rel)
        )
        both_order = require_identity_order(both, [early_id, late_id])
        assert both_order == [early_id, late_id], (
            "equal keyword scores on the search tool must list the "
            "earlier identity first; "
            f"order={both_order!r} write_order={write_order!r}"
        )
        print("MCP equal-score identity cap 1 ok", flush=True)


def test_mcp_path_search_orders_governance():
    """MCP path search folds Hold, then a nested convention omit, then another omit.

    One path hit declares the mixed spelling Hold. Governance is omitted
    on ``convention/<dir>/<leaf>`` and on an identity outside that
    directory. The tool orders hold, then constraint, then context, and
    the Hold hit's effective value is the lowercase word. Cap 1 keeps
    only that hold hit. A path-only tool hit reports a code_refs match.
    The same tool call with a query also reports the keyword field on
    the concept that matched that query.

    A second tool bundle omits governance on ``convention/<dir>/<leaf>``
    and on an identity whose first segment only shares that prefix
    (``convention<extra>/<leaf>``). The nested omit's effective value is
    constraint. The prefix-sharing omit's effective value is context.
    With no path, the tool ranks that prefix-sharing title match ahead of
    the nested identity's single body occurrence of the same term, and the
    effective values on that call are context and constraint. With the
    path, the nested identity still ranks first, with the same values.
    """
    with workspace() as ws:
        hold_id, deep_id, ctx_id = inverted_tool_path_governance_identities()
        declared = "Hold"
        if declared == "hold" or declared.lower() != "hold":
            raise AssertionError(
                "mixed spelling must fold to hold and must not already "
                f"be the lowercase word: {declared!r}"
            )
        deep_parts = deep_id.split("/")
        if (
            deep_parts[0] != "convention"
            or len(deep_parts) != 3
            or not all(deep_parts)
        ):
            raise AssertionError(
                "omitted convention identity is not convention/<dir>/<leaf>: "
                f"{deep_id!r}"
            )
        if ctx_id.startswith("convention/") or hold_id.startswith("convention/"):
            raise AssertionError(
                "only the nested convention identity may sit under convention/: "
                f"hold={hold_id!r} outside={ctx_id!r}"
            )
        if not (hold_id < ctx_id < deep_id):
            raise AssertionError(
                "the outside omit must sort before the nested convention "
                "omit, so treating both omissions as context is not "
                f"hold then constraint then context: "
                f"{hold_id!r} {ctx_id!r} {deep_id!r}"
            )
        typ, htitle, dtitle, xtitle, desc, body = unique_tokens(
            "typ", "ht", "dt", "xt", "dsc", "bod"
        )
        path = f"pkg/{compact_token('p')}/x.go"
        rel = _kb()
        hold_spec = search_concept_spec(
            hold_id,
            concept_type=typ,
            title=htitle,
            description=desc,
            body=f"{body}\n",
            governance=declared,
            code_refs=[path],
        )
        deep_spec = search_concept_spec(
            deep_id,
            concept_type=typ,
            title=dtitle,
            description=desc,
            body=f"{body}\n",
            code_refs=[path],
        )
        ctx_spec = search_concept_spec(
            ctx_id,
            concept_type=typ,
            title=xtitle,
            description=desc,
            body=f"{body}\n",
            code_refs=[path],
        )
        for spec, label in (
            (deep_spec, "nested convention"),
            (ctx_spec, "outside"),
        ):
            extra = spec.get("extra") or {}
            if "governance" in extra:
                raise AssertionError(
                    f"{label} identity must omit governance; extra={extra!r}"
                )
        if (hold_spec.get("extra") or {}).get("governance") != declared:
            raise AssertionError(
                "hold path hit must declare the mixed spelling Hold"
            )
        write_concepts_later_first(
            ws,
            rel,
            [hold_spec, deep_spec, ctx_spec],
        )
        records = require_mcp_search_success(
            mcp_search(ws, for_path=path, bundle=rel)
        )
        ordered = require_identity_order(records, [hold_id, deep_id, ctx_id])
        assert ordered == [hold_id, deep_id, ctx_id], (
            "MCP path search must rank folded Hold, then the omitted "
            "convention/<dir>/<leaf> identity, then the omitted identity "
            f"outside that directory; order={ordered!r}"
        )
        shared = [
            path,
            typ,
            desc,
            body,
            htitle,
            dtitle,
            xtitle,
            hold_id,
            deep_id,
            ctx_id,
        ]
        assert_lowercase_effective_governance(
            record_for_identity(records, hold_id),
            "hold",
            [hold_id, htitle, *shared],
        )
        assert_lowercase_effective_governance(
            record_for_identity(records, deep_id),
            "constraint",
            [deep_id, dtitle, *shared],
        )
        assert_lowercase_effective_governance(
            record_for_identity(records, ctx_id),
            "context",
            [ctx_id, xtitle, *shared],
        )
        capped = require_mcp_search_success(
            mcp_search(ws, for_path=path, bundle=rel, limit=1)
        )
        capped_order = require_identity_order(capped, [hold_id])
        assert capped_order == [hold_id], (
            f"MCP path search with cap 1 must return only the first "
            f"governance hit; order={capped_order!r}"
        )
        for ident, title in ((hold_id, htitle), (deep_id, dtitle), (ctx_id, xtitle)):
            rec = record_for_identity(records, ident)
            strip = [ident, title, *shared]
            assert code_ref_match_reported(rec, strip), (
                "path-only tool hit does not report a code_refs match after "
                "the path and the concept's own texts are stripped; "
                f"identity={ident!r} record={rec!r}"
            )
            assert_matched_keyword_fields(rec, strip, ())
        hold_cap = record_for_identity(capped, hold_id)
        assert code_ref_match_reported(hold_cap, [hold_id, htitle, *shared]), (
            "path-only tool hit under cap 1 does not report a code_refs "
            f"match; record={hold_cap!r}"
        )
        assert_matched_keyword_fields(hold_cap, [hold_id, htitle, *shared], ())
        assert_lowercase_effective_governance(
            hold_cap,
            "hold",
            [hold_id, htitle, *shared],
        )
        with_query = require_mcp_search_success(
            mcp_search(ws, query=xtitle, for_path=path, bundle=rel)
        )
        for ident, title in ((hold_id, htitle), (deep_id, dtitle), (ctx_id, xtitle)):
            rec = record_for_identity(with_query, ident)
            strip = [ident, title, *shared]
            assert code_ref_match_reported(rec, strip), (
                "path-plus-query tool hit does not report a code_refs match; "
                f"identity={ident!r} record={rec!r}"
            )
        queried = record_for_identity(with_query, ctx_id)
        query_tokens = matched_field_tokens(queried, [ctx_id, xtitle, *shared])
        assert "title" in query_tokens, (
            "path-plus-query tool hit does not report the keyword field; "
            f"tokens={sorted(query_tokens)}"
        )

        # Directory boundary on the tool: convention/<dir>/<leaf> stays
        # constraint; convention<extra>/<leaf> is context. The closed
        # three-identity order above does not share that prefix.
        shallow_id = f"convention/{compact_token('cv')}"
        edge_deep = deeper_convention_omit_identity(shallow_id)
        edge_prefix = prefix_sharing_tool_omit_identity(edge_deep, shallow_id)
        edge_deep_parts = edge_deep.split("/")
        edge_prefix_parts = edge_prefix.split("/")
        if (
            edge_deep_parts[0] != "convention"
            or len(edge_deep_parts) != 3
            or not all(edge_deep_parts)
        ):
            raise AssertionError(
                "tool directory omit is not convention/<dir>/<leaf>: "
                f"{edge_deep!r}"
            )
        if (
            len(edge_prefix_parts) != 2
            or not all(edge_prefix_parts)
            or edge_prefix.startswith("convention/")
            or not edge_prefix.startswith("convention")
            or edge_prefix_parts[0] == "convention"
        ):
            raise AssertionError(
                "tool prefix-sharing omit must share the convention "
                "characters without the directory slash: "
                f"{edge_prefix!r}"
            )
        if shallow_id in (edge_deep, edge_prefix) or not edge_deep < edge_prefix:
            raise AssertionError(
                "prefix-sharing omit must sort after the nested convention "
                f"identity and the one-segment identity is not planted: "
                f"{shallow_id!r} {edge_deep!r} {edge_prefix!r}"
            )
        term = compact_token("kw")
        edge_typ, edge_deep_title, edge_desc, edge_filler = unique_tokens(
            "typ", "dt", "dsc", "fil"
        )
        edge_path = f"pkg/{compact_token('p')}/x.go"
        field_tokens_do_not_start_with(
            term,
            edge_deep,
            edge_prefix,
            shallow_id,
            edge_typ,
            edge_deep_title,
            edge_desc,
            edge_filler,
            edge_path,
            "incidental",
            "once",
        )
        edge_rel = _kb()
        edge_deep_spec = search_concept_spec(
            edge_deep,
            concept_type=edge_typ,
            title=edge_deep_title,
            description=edge_desc,
            body=f"incidental {term} once\n",
            code_refs=[edge_path],
        )
        edge_prefix_spec = search_concept_spec(
            edge_prefix,
            concept_type=edge_typ,
            title=term,
            description=edge_desc,
            body=f"{edge_filler}\n",
            code_refs=[edge_path],
        )
        for spec, label in (
            (edge_deep_spec, "nested convention"),
            (edge_prefix_spec, "prefix-sharing"),
        ):
            extra = spec.get("extra") or {}
            if "governance" in extra:
                raise AssertionError(
                    f"{label} identity must omit governance; extra={extra!r}"
                )
        write_concepts_later_first(
            ws,
            edge_rel,
            [edge_deep_spec, edge_prefix_spec],
        )
        edge_shared = [
            edge_path,
            edge_typ,
            edge_desc,
            edge_filler,
            term,
            edge_deep,
            edge_prefix,
            edge_deep_title,
            "incidental",
            "once",
        ]
        keyword_hits = require_mcp_search_success(
            mcp_search(ws, query=term, bundle=edge_rel)
        )
        keyword_order = require_identity_order(
            keyword_hits, [edge_prefix, edge_deep]
        )
        assert keyword_order == [edge_prefix, edge_deep], (
            "search tool keyword baseline must rank the prefix-sharing "
            "title match before the nested convention identity's single "
            f"body occurrence; order={keyword_order!r}"
        )
        assert_lowercase_effective_governance(
            record_for_identity(keyword_hits, edge_deep),
            "constraint",
            [edge_deep, edge_deep_title, *edge_shared],
        )
        assert_lowercase_effective_governance(
            record_for_identity(keyword_hits, edge_prefix),
            "context",
            [edge_prefix, term, *edge_shared],
        )
        edge_records = require_mcp_search_success(
            mcp_search(ws, query=term, for_path=edge_path, bundle=edge_rel)
        )
        edge_ordered = require_identity_order(
            edge_records, [edge_deep, edge_prefix]
        )
        assert edge_ordered == [edge_deep, edge_prefix], (
            "search tool must rank the omitted convention/<dir>/<leaf> "
            "identity before the omitted prefix-sharing identity; a "
            "leading convention string is not the convention/ directory; "
            f"order={edge_ordered!r} keyword_order={keyword_order!r}"
        )
        assert_lowercase_effective_governance(
            record_for_identity(edge_records, edge_deep),
            "constraint",
            [edge_deep, edge_deep_title, *edge_shared],
        )
        assert_lowercase_effective_governance(
            record_for_identity(edge_records, edge_prefix),
            "context",
            [edge_prefix, term, *edge_shared],
        )
        print("MCP path governance order and cap 1 ok", flush=True)


def test_mcp_path_search_matches_directory_prefix_star_and_leading_slash():
    """membundle_search keeps a code_ref that is not the same string as the path.

    A generated directory ref hits a path two or more segments under it and
    misses the character sibling. A single-segment star hits a file in that
    segment and misses a path that would need the star to cross a slash.
    A stored ref that begins with / hits the bare relative path. A generated
    bare relative ref hits when that same path is searched with a leading ./
    and when it is searched with a single leading /, and a different stored
    ref misses. An unscoped recursive suffix for an extension other than .go
    hits a one-segment file of that suffix and a nested file, and misses a
    different suffix. A
    directory-scoped recursive wildcard with no filename suffix hits a file
    more than one segment under that directory and misses a file outside it.
    A star that is only part of one filename stem, ``{prefix}*.{ext}``, hits
    ``{prefix}{leaf}.{ext}`` and misses a path that would need that star to
    cross a slash, including a different one-segment file of the same suffix.
    A star in an earlier segment, ``*/{leaf}.{ext}`` and
    ``{dir}/*/{leaf}.{ext}``, hits when that star matches exactly one segment
    and misses a path that would need the star to cross a slash. The closed
    whole-stem tool checks and the command-line checks for these shapes stay
    as they are.
    """
    with workspace() as ws:
        typ, desc, body = _filler()
        title, other_title, third_title = unique_tokens("ttl", "otl", "ttl3")

        probe = generated_deep_directory_prefix_probe()
        if probe.segments_under < 2:
            raise AssertionError(
                "generated path is not two or more segments under the directory"
            )
        if (
            probe.path_under_sibling[len(probe.directory_ref) : len(probe.directory_ref) + 1]
            == "/"
        ):
            raise AssertionError(
                "sibling path is a directory boundary of the shorter ref"
            )
        if probe.directory_ref == probe.path_under_directory:
            raise AssertionError("directory probe collapsed to the searched path")
        if probe.sibling_ref == probe.path_under_sibling:
            raise AssertionError("sibling probe collapsed to the searched path")
        dir_hit, dir_miss = unique_tokens("dh", "dm")
        rel_dir = _kb()
        write_bundle(
            ws,
            rel_dir,
            [
                search_concept_spec(
                    dir_hit,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.directory_ref],
                ),
                search_concept_spec(
                    dir_miss,
                    concept_type=typ,
                    title=other_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[probe.sibling_ref],
                ),
            ],
        )
        deep = require_mcp_search_success(
            mcp_search(ws, for_path=probe.path_under_directory, bundle=rel_dir)
        )
        assert identity_in_records(deep, dir_hit), (
            "search tool directory ref missed a path two or more segments under it"
        )
        assert not identity_in_records(deep, dir_miss), (
            "search tool character-sibling ref matched a path that does not continue it"
        )
        beside = require_mcp_search_success(
            mcp_search(ws, for_path=probe.path_under_sibling, bundle=rel_dir)
        )
        assert identity_in_records(beside, dir_miss), (
            "search tool sibling directory missed a path two or more segments under it"
        )
        assert not identity_in_records(beside, dir_hit), (
            "search tool shorter ref matched a path that shares its characters "
            "without a directory boundary"
        )

        ext, leaf, scope, deeper = unique_compact("ext", "lf", "sc", "dp")
        unscoped = f"*.{ext}"
        scoped = f"{scope}/*.{ext}"
        file_only = f"{leaf}.{ext}"
        one_seg = f"{scope}/{leaf}.{ext}"
        crossed = f"{scope}/{deeper}/{leaf}.{ext}"
        scoped_parts = scoped.split("/")
        if (
            "/" in unscoped
            or unscoped.count("*") != 1
            or unscoped == file_only
            or "/" in file_only
        ):
            raise AssertionError(
                f"unscoped star is not one segment distinct from its hit: "
                f"{unscoped!r} vs {file_only!r}"
            )
        if (
            len(scoped_parts) != 2
            or scoped_parts[0] != scope
            or scoped_parts[1].count("*") != 1
            or "/" in scoped_parts[1]
        ):
            raise AssertionError(
                f"scoped star is not one filename segment: {scoped!r}"
            )
        if one_seg.count("/") != 1:
            raise AssertionError(
                f"scoped hit is not a file in the starred segment: {one_seg!r}"
            )
        if crossed.count("/") != 2 or "/" not in crossed[len(scope) + 1 :]:
            raise AssertionError(
                "cross path does not put a slash inside the starred segment"
            )
        if not file_only.endswith(f".{ext}") or not one_seg.endswith(f".{ext}"):
            raise AssertionError("single-segment star probe lost its filename suffix")
        if not crossed.endswith(f".{ext}"):
            raise AssertionError("cross path lost the starred filename suffix")
        star_id, scoped_id, exact_id = unique_tokens("su", "ss", "se")
        star_texts = (unscoped, scoped, file_only, one_seg, crossed)
        for ident in (star_id, scoped_id, exact_id):
            if ident in star_texts or any(ident in text for text in star_texts):
                raise AssertionError(
                    "concept identity collides with a single-segment star path"
                )
        rel_star = _kb()
        write_bundle(
            ws,
            rel_star,
            [
                search_concept_spec(
                    star_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[unscoped],
                ),
                search_concept_spec(
                    scoped_id,
                    concept_type=typ,
                    title=other_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[scoped],
                ),
                search_concept_spec(
                    exact_id,
                    concept_type=typ,
                    title=third_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[crossed],
                ),
            ],
        )
        file_hits = require_mcp_search_success(
            mcp_search(ws, for_path=file_only, bundle=rel_star)
        )
        assert identity_in_records(file_hits, star_id), (
            f"search tool {unscoped} missed the file in that segment"
        )
        assert not identity_in_records(file_hits, scoped_id), (
            f"search tool {scoped} matched a file outside its directory"
        )
        assert not identity_in_records(file_hits, exact_id)
        segment_hits = require_mcp_search_success(
            mcp_search(ws, for_path=one_seg, bundle=rel_star)
        )
        assert identity_in_records(segment_hits, scoped_id), (
            f"search tool {scoped} missed the file in that segment"
        )
        assert not identity_in_records(segment_hits, star_id), (
            f"search tool {unscoped} matched a path that would need the star "
            "to cross a slash"
        )
        assert not identity_in_records(segment_hits, exact_id)
        cross_hits = require_mcp_search_success(
            mcp_search(ws, for_path=crossed, bundle=rel_star)
        )
        assert identity_in_records(cross_hits, exact_id), (
            "search tool exact code_ref was not a hit for the deeper path"
        )
        assert not identity_in_records(cross_hits, star_id), (
            f"search tool {unscoped} matched a path that would need the star "
            "to cross a slash"
        )
        assert not identity_in_records(cross_hits, scoped_id), (
            f"search tool {scoped} matched a path that would need the star "
            "to cross a slash"
        )

        left, right, name, slash_ext = unique_compact("pa", "pb", "nm", "sx")
        bare = f"{left}/{name}.{slash_ext}"
        other_bare = f"{right}/{name}.{slash_ext}"
        stored = "/" + bare
        other_stored = "/" + other_bare
        if (
            not stored.startswith("/")
            or stored[1:] != bare
            or bare.startswith(("/", "./", "."))
            or stored == bare
            or other_stored == other_bare
        ):
            raise AssertionError(
                "leading-slash probe collapsed to the bare relative path"
            )
        if (
            bare.startswith(other_bare)
            or other_bare.startswith(bare)
            or "/" not in bare
            or "/" not in other_bare
        ):
            raise AssertionError(
                "leading-slash pair is a prefix of itself or is one segment"
            )
        slash_id, other_id = unique_tokens("sl", "so")
        slash_texts = (bare, other_bare, stored, other_stored)
        for ident in (slash_id, other_id):
            if ident in slash_texts or any(ident in text for text in slash_texts):
                raise AssertionError(
                    "concept identity collides with a leading-slash path"
                )
        rel_slash = _kb()
        write_bundle(
            ws,
            rel_slash,
            [
                search_concept_spec(
                    slash_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[stored],
                ),
                search_concept_spec(
                    other_id,
                    concept_type=typ,
                    title=other_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[other_stored],
                ),
            ],
        )
        for caller, hit_ident, miss_ident in (
            (bare, slash_id, other_id),
            (other_bare, other_id, slash_id),
        ):
            slash_hits = require_mcp_search_success(
                mcp_search(ws, for_path=caller, bundle=rel_slash)
            )
            assert identity_in_records(slash_hits, hit_ident), (
                f"search tool bare path {caller!r} missed a code_ref that begins with /"
            )
            assert not identity_in_records(slash_hits, miss_ident), (
                f"search tool bare path {caller!r} kept a code_ref for a different path"
            )

        # Caller-side optional ./ and a single leading / against a generated
        # bare relative ref. The stored-leading-slash check above stays.
        # Stripping a leading slash only from the stored ref, and comparing
        # the caller path unchanged, leaves both prefixed callers unmatched.
        call_left, call_right, call_name, call_ext = unique_compact(
            "cpa", "cpb", "cpn", "cpx"
        )
        call_bare = f"{call_left}/{call_name}.{call_ext}"
        call_other = f"{call_right}/{call_name}.{call_ext}"
        dot_call = "./" + call_bare
        slash_call = "/" + call_bare
        dot_other_call = "./" + call_other
        slash_other_call = "/" + call_other
        if (
            call_bare == SAMPLE_FILE
            or call_other == SAMPLE_FILE
            or call_bare.startswith(("/", "./", "."))
            or call_other.startswith(("/", "./", "."))
            or "/" not in call_bare
            or "/" not in call_other
            or call_bare.startswith(call_other)
            or call_other.startswith(call_bare)
            or call_bare.endswith("/" + call_other)
            or call_other.endswith("/" + call_bare)
            or dot_call != "./" + call_bare
            or slash_call != "/" + call_bare
            or slash_call.startswith("//")
            or dot_call.startswith("././")
            or dot_call.startswith(".//")
            or dot_call[2:] != call_bare
            or slash_call[1:] != call_bare
        ):
            raise AssertionError(
                "caller-prefix probe is not a generated bare relative ref "
                f"with one leading ./ or /: {call_bare!r} vs {call_other!r}"
            )
        call_id, call_miss_id = unique_tokens("cpi", "cpm")
        call_texts = (
            call_bare,
            call_other,
            dot_call,
            slash_call,
            dot_other_call,
            slash_other_call,
        )
        for ident in (call_id, call_miss_id):
            if ident in call_texts or any(ident in text for text in call_texts):
                raise AssertionError(
                    "concept identity collides with a caller-prefix path"
                )
        rel_call = _kb()
        write_bundle(
            ws,
            rel_call,
            [
                search_concept_spec(
                    call_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[call_bare],
                ),
                search_concept_spec(
                    call_miss_id,
                    concept_type=typ,
                    title=other_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[call_other],
                ),
            ],
        )
        for caller, hit_ident, miss_ident in (
            (dot_call, call_id, call_miss_id),
            (slash_call, call_id, call_miss_id),
            (dot_other_call, call_miss_id, call_id),
            (slash_other_call, call_miss_id, call_id),
        ):
            prefixed = require_mcp_search_success(
                mcp_search(ws, for_path=caller, bundle=rel_call)
            )
            assert identity_in_records(prefixed, hit_ident), (
                f"search tool caller path {caller!r} missed bare relative code_ref"
            )
            assert not identity_in_records(prefixed, miss_ident), (
                f"search tool caller path {caller!r} kept a different stored ref"
            )

        ext, other, leaf, scope, deep = unique_compact(
            "mxe", "mxo", "mxl", "mxs", "mxd"
        )
        if ext.lower() == "go" or other.lower() == "go":
            raise AssertionError(
                "unscoped recursive suffix must use an extension other than .go"
            )
        unscoped_ref, one_seg_hit, one_seg_miss = one_segment_recursive_suffix_paths(
            leaf, ext, other
        )
        nested_hit = f"{scope}/{deep}/{leaf}.{ext}"
        nested_miss = f"{scope}/{deep}/{leaf}.{other}"
        if (
            not unscoped_ref.startswith("**/")
            or unscoped_ref.count("**") != 1
            or not unscoped_ref.endswith("*." + ext)
            or "/" in unscoped_ref[3:]
        ):
            raise AssertionError(
                "stored ref is not an unscoped recursive suffix other than "
                f".go: {unscoped_ref!r}"
            )
        if "/" in one_seg_hit or not one_seg_hit.endswith("." + ext):
            raise AssertionError(
                f"one-segment hit is not a file of .{ext}: {one_seg_hit!r}"
            )
        if (
            "/" in one_seg_miss
            or not one_seg_miss.endswith("." + other)
            or one_seg_miss.endswith("." + ext)
        ):
            raise AssertionError(
                "different-suffix miss is not a one-segment file of a "
                f"different suffix: {one_seg_miss!r}"
            )
        if nested_hit.count("/") < 1 or not nested_hit.endswith("." + ext):
            raise AssertionError(
                f"nested hit is not a nested file of .{ext}: {nested_hit!r}"
            )
        if (
            nested_miss.count("/") < 1
            or not nested_miss.endswith("." + other)
            or nested_miss.endswith("." + ext)
        ):
            raise AssertionError(
                "nested miss is not a nested file of a different suffix: "
                f"{nested_miss!r}"
            )
        suffix_id = unique_tokens("msf")[0]
        suffix_texts = (
            unscoped_ref,
            one_seg_hit,
            one_seg_miss,
            nested_hit,
            nested_miss,
        )
        if suffix_id in suffix_texts or any(
            suffix_id in text for text in suffix_texts
        ):
            raise AssertionError(
                "concept identity collides with a recursive suffix path"
            )
        rel_suffix = _kb()
        write_bundle(
            ws,
            rel_suffix,
            [
                search_concept_spec(
                    suffix_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[unscoped_ref],
                ),
            ],
        )
        bare_suffix = require_mcp_search_success(
            mcp_search(ws, for_path=one_seg_hit, bundle=rel_suffix)
        )
        assert identity_in_records(bare_suffix, suffix_id), (
            f"search tool {unscoped_ref} missed one-segment file {one_seg_hit}"
        )
        nested_suffix = require_mcp_search_success(
            mcp_search(ws, for_path=nested_hit, bundle=rel_suffix)
        )
        assert identity_in_records(nested_suffix, suffix_id), (
            f"search tool {unscoped_ref} missed nested file {nested_hit}"
        )
        other_suffix = require_mcp_search_success(
            mcp_search(ws, for_path=one_seg_miss, bundle=rel_suffix)
        )
        assert not identity_in_records(other_suffix, suffix_id), (
            f"search tool {unscoped_ref} kept a different suffix {one_seg_miss}"
        )
        nested_other = require_mcp_search_success(
            mcp_search(ws, for_path=nested_miss, bundle=rel_suffix)
        )
        assert not identity_in_records(nested_other, suffix_id), (
            f"search tool {unscoped_ref} kept a nested different suffix "
            f"{nested_miss}"
        )

        recur = unsuffixed_recursive_directory_probe()
        if (
            not recur.code_ref.endswith("/**")
            or "*." in recur.code_ref
            or recur.code_ref.count("**") != 1
        ):
            raise AssertionError(
                "stored ref is not an unsuffixed directory recursive "
                f"wildcard: {recur.code_ref!r}"
            )
        under = recur.nested_path.split(recur.directory + "/", 1)[-1]
        if under.count("/") < 1 or "." in under.split("/")[-1]:
            raise AssertionError(
                "recursive directory hit is not an unsuffixed file more "
                f"than one segment under the directory: {recur.nested_path!r}"
            )
        if (
            recur.outside_path.startswith(recur.directory + "/")
            or not recur.outside_path.endswith("/" + under)
        ):
            raise AssertionError(
                "outside file is not the same tail outside the directory: "
                f"{recur.outside_path!r}"
            )
        recur_id = unique_tokens("mrd")[0]
        recur_texts = (recur.code_ref, recur.nested_path, recur.outside_path)
        if recur_id in recur_texts or any(
            recur_id in text for text in recur_texts
        ):
            raise AssertionError(
                "concept identity collides with a directory-scoped recursive path"
            )
        rel_recur = _kb()
        write_bundle(
            ws,
            rel_recur,
            [
                search_concept_spec(
                    recur_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[recur.code_ref],
                ),
            ],
        )
        deep_recur = require_mcp_search_success(
            mcp_search(ws, for_path=recur.nested_path, bundle=rel_recur)
        )
        assert identity_in_records(deep_recur, recur_id), (
            f"search tool {recur.code_ref} missed a file more than one "
            f"segment under it: {recur.nested_path}"
        )
        outside_recur = require_mcp_search_success(
            mcp_search(ws, for_path=recur.outside_path, bundle=rel_recur)
        )
        assert not identity_in_records(outside_recur, recur_id), (
            f"search tool {recur.code_ref} matched a file outside it: "
            f"{recur.outside_path}"
        )

        partial = partial_segment_glob_probe()
        if (
            "/" in partial.pattern
            or partial.pattern.startswith("*")
            or partial.pattern.count("*") != 1
        ):
            raise AssertionError(
                "search tool partial-segment pattern is still a whole-stem "
                f"star: {partial.pattern!r}"
            )
        if partial.pattern.index("*") <= 0 or "/" in partial.hit_path:
            raise AssertionError(
                "search tool star is not part-way through one filename segment"
            )
        (
            partial_id,
            partial_cross_id,
            partial_nest_id,
            partial_stem_id,
            partial_suffix_id,
        ) = unique_tokens("mps", "mpc", "mpn", "mpw", "mpu")
        partial_texts = (
            partial.pattern,
            partial.hit_path,
            partial.cross_path,
            partial.nested_path,
            partial.whole_stem_path,
            partial.wrong_suffix_path,
        )
        for ident in (
            partial_id,
            partial_cross_id,
            partial_nest_id,
            partial_stem_id,
            partial_suffix_id,
        ):
            if ident in partial_texts or any(ident in text for text in partial_texts):
                raise AssertionError(
                    "concept identity collides with a partial-segment probe path"
                )
        rel_partial = _kb()
        write_bundle(
            ws,
            rel_partial,
            [
                search_concept_spec(
                    partial_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[partial.pattern],
                ),
                search_concept_spec(
                    partial_cross_id,
                    concept_type=typ,
                    title=other_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[partial.cross_path],
                ),
                search_concept_spec(
                    partial_nest_id,
                    concept_type=typ,
                    title=third_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[partial.nested_path],
                ),
                search_concept_spec(
                    partial_stem_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[partial.whole_stem_path],
                ),
                search_concept_spec(
                    partial_suffix_id,
                    concept_type=typ,
                    title=other_title,
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[partial.wrong_suffix_path],
                ),
            ],
        )
        partial_hit = require_mcp_search_success(
            mcp_search(ws, for_path=partial.hit_path, bundle=rel_partial)
        )
        assert identity_in_records(partial_hit, partial_id), (
            f"search tool {partial.pattern} missed {partial.hit_path}"
        )
        assert not identity_in_records(partial_hit, partial_cross_id)
        assert not identity_in_records(partial_hit, partial_nest_id)
        assert not identity_in_records(partial_hit, partial_stem_id)
        assert not identity_in_records(partial_hit, partial_suffix_id)
        partial_crossed = require_mcp_search_success(
            mcp_search(ws, for_path=partial.cross_path, bundle=rel_partial)
        )
        assert identity_in_records(partial_crossed, partial_cross_id), (
            f"search tool exact code_ref was not a hit for {partial.cross_path}"
        )
        assert not identity_in_records(partial_crossed, partial_id), (
            f"search tool {partial.pattern} matched {partial.cross_path}; "
            "the star would have to cross a slash"
        )
        partial_nested = require_mcp_search_success(
            mcp_search(ws, for_path=partial.nested_path, bundle=rel_partial)
        )
        assert identity_in_records(partial_nested, partial_nest_id), (
            f"search tool exact code_ref was not a hit for {partial.nested_path}"
        )
        assert not identity_in_records(partial_nested, partial_id), (
            f"search tool {partial.pattern} matched {partial.nested_path}; "
            "the star would have to cross a slash to match the whole path"
        )
        partial_stem = require_mcp_search_success(
            mcp_search(ws, for_path=partial.whole_stem_path, bundle=rel_partial)
        )
        assert identity_in_records(partial_stem, partial_stem_id), (
            f"search tool exact code_ref was not a hit for {partial.whole_stem_path}"
        )
        assert not identity_in_records(partial_stem, partial_id), (
            f"search tool {partial.pattern} matched {partial.whole_stem_path}; "
            "the star is not the whole filename stem"
        )
        partial_suffix = require_mcp_search_success(
            mcp_search(ws, for_path=partial.wrong_suffix_path, bundle=rel_partial)
        )
        assert identity_in_records(partial_suffix, partial_suffix_id), (
            "search tool exact code_ref was not a hit for "
            f"{partial.wrong_suffix_path}"
        )
        assert not identity_in_records(partial_suffix, partial_id), (
            f"search tool {partial.pattern} matched {partial.wrong_suffix_path}"
        )

        earlier = earlier_segment_glob_probe()
        if "*" in earlier.leading_pattern.split("/")[-1]:
            raise AssertionError(
                "search tool leading star is still in the filename: "
                f"{earlier.leading_pattern!r}"
            )
        if "*" in earlier.scoped_pattern.split("/")[-1]:
            raise AssertionError(
                "search tool scoped star is still in the filename: "
                f"{earlier.scoped_pattern!r}"
            )
        if (
            earlier.leading_pattern.count("*") != 1
            or earlier.scoped_pattern.count("*") != 1
        ):
            raise AssertionError(
                "search tool earlier-segment probe does not store exactly "
                "one star in each pattern"
            )
        (
            leading_glob,
            leading_hit_id,
            leading_cross_id,
            leading_other_id,
        ) = unique_tokens("mlg", "mlh", "mlc", "mlo")
        (
            scoped_glob,
            scoped_hit_id,
            scoped_cross_id,
            scoped_other_id,
            scoped_dir_id,
        ) = unique_tokens("msg", "msh", "msc", "mso", "msd")
        earlier_titles = unique_tokens(
            "et0", "et1", "et2", "et3", "et4", "et5", "et6", "et7", "et8"
        )
        earlier_idents = (
            leading_glob,
            leading_hit_id,
            leading_cross_id,
            leading_other_id,
            scoped_glob,
            scoped_hit_id,
            scoped_cross_id,
            scoped_other_id,
            scoped_dir_id,
        )
        earlier_texts = (
            earlier.leading_pattern,
            earlier.leading_hit,
            earlier.leading_cross,
            earlier.leading_other_leaf,
            earlier.scoped_pattern,
            earlier.scoped_hit,
            earlier.scoped_cross,
            earlier.scoped_other_leaf,
            earlier.scoped_other_dir,
        )
        for ident in earlier_idents:
            if ident in earlier_texts or any(ident in text for text in earlier_texts):
                raise AssertionError(
                    "concept identity collides with an earlier-segment probe path"
                )
        rel_leading = _kb()
        write_bundle(
            ws,
            rel_leading,
            [
                search_concept_spec(
                    leading_glob,
                    concept_type=typ,
                    title=earlier_titles[0],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[earlier.leading_pattern],
                ),
                search_concept_spec(
                    leading_hit_id,
                    concept_type=typ,
                    title=earlier_titles[1],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[earlier.leading_hit],
                ),
                search_concept_spec(
                    leading_cross_id,
                    concept_type=typ,
                    title=earlier_titles[2],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[earlier.leading_cross],
                ),
                search_concept_spec(
                    leading_other_id,
                    concept_type=typ,
                    title=earlier_titles[3],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[earlier.leading_other_leaf],
                ),
            ],
        )
        rel_scoped = _kb()
        write_bundle(
            ws,
            rel_scoped,
            [
                search_concept_spec(
                    scoped_glob,
                    concept_type=typ,
                    title=earlier_titles[4],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[earlier.scoped_pattern],
                ),
                search_concept_spec(
                    scoped_hit_id,
                    concept_type=typ,
                    title=earlier_titles[5],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[earlier.scoped_hit],
                ),
                search_concept_spec(
                    scoped_cross_id,
                    concept_type=typ,
                    title=earlier_titles[6],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[earlier.scoped_cross],
                ),
                search_concept_spec(
                    scoped_other_id,
                    concept_type=typ,
                    title=earlier_titles[7],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[earlier.scoped_other_leaf],
                ),
                search_concept_spec(
                    scoped_dir_id,
                    concept_type=typ,
                    title=earlier_titles[8],
                    description=desc,
                    body=f"{body}\n",
                    code_refs=[earlier.scoped_other_dir],
                ),
            ],
        )
        earlier_cases = (
            (
                rel_leading,
                earlier.leading_hit,
                (leading_glob, leading_hit_id),
                (leading_cross_id, leading_other_id),
                f"search tool {earlier.leading_pattern} missed {earlier.leading_hit}",
            ),
            (
                rel_leading,
                earlier.leading_cross,
                (leading_cross_id,),
                (leading_glob, leading_hit_id, leading_other_id),
                f"search tool {earlier.leading_pattern} matched "
                f"{earlier.leading_cross}; the star would have to cross a slash",
            ),
            (
                rel_leading,
                earlier.leading_other_leaf,
                (leading_other_id,),
                (leading_glob, leading_hit_id, leading_cross_id),
                f"search tool {earlier.leading_pattern} matched "
                f"{earlier.leading_other_leaf}; the filename segment is literal",
            ),
            (
                rel_scoped,
                earlier.scoped_hit,
                (scoped_glob, scoped_hit_id),
                (scoped_cross_id, scoped_other_id, scoped_dir_id),
                f"search tool {earlier.scoped_pattern} missed {earlier.scoped_hit}",
            ),
            (
                rel_scoped,
                earlier.scoped_cross,
                (scoped_cross_id,),
                (scoped_glob, scoped_hit_id, scoped_other_id, scoped_dir_id),
                f"search tool {earlier.scoped_pattern} matched "
                f"{earlier.scoped_cross}; the star would have to cross a slash",
            ),
            (
                rel_scoped,
                earlier.scoped_other_leaf,
                (scoped_other_id,),
                (scoped_glob, scoped_hit_id, scoped_cross_id, scoped_dir_id),
                f"search tool {earlier.scoped_pattern} matched "
                f"{earlier.scoped_other_leaf}; the filename segment is literal",
            ),
            (
                rel_scoped,
                earlier.scoped_other_dir,
                (scoped_dir_id,),
                (scoped_glob, scoped_hit_id, scoped_cross_id, scoped_other_id),
                f"search tool {earlier.scoped_pattern} matched "
                f"{earlier.scoped_other_dir}; the directory segment is literal",
            ),
        )
        for bundle, path, present, absent, why in earlier_cases:
            records = require_mcp_search_success(
                mcp_search(ws, for_path=path, bundle=bundle)
            )
            for ident in present:
                assert identity_in_records(records, ident), (
                    f"{why}; missing {ident!r} for {path!r}"
                )
            for ident in absent:
                assert not identity_in_records(records, ident), (
                    f"{why}; kept {ident!r} for {path!r}"
                )
        print(
            "MCP path match is not exact equality "
            f"suffix={unscoped_ref!r} recur={recur.code_ref!r} "
            f"partial={partial.pattern!r} leading={earlier.leading_pattern!r} "
            f"scoped={earlier.scoped_pattern!r}",
            flush=True,
        )


def test_mcp_same_governance_ranks_combined_score_then_identity():
    """Search tool, query beside a path: higher combined score, then identity.

    Three path hits share one governance. The title match sorts after both
    path-only concepts, so identity order alone would not put it first.
    The two path-only hits are a remaining tie and are written later
    identity first, so write order is not identity ascending.
    """
    with workspace() as ws:
        (
            term,
            typ,
            miss_title,
            desc,
            body,
            dir_tok,
            early_tok,
            late_tok,
            title_tok,
        ) = unique_compact(
            "qry", "typ", "mt", "dsc", "bod", "dir", "ea", "la", "ti"
        )
        early_id = f"a{early_tok}"
        late_id = f"m{late_tok}"
        title_id = f"z{title_tok}"
        assert early_id < late_id < title_id
        expected = [title_id, early_id, late_id]
        assert expected != sorted([early_id, late_id, title_id])
        assert expected != sorted([early_id, late_id, title_id], reverse=True)
        path = f"pkg/{dir_tok}/x.go"
        rel = _kb()
        shared_body = f"{body}\n"
        write_concepts_later_first(
            ws,
            rel,
            [
                search_concept_spec(
                    early_id,
                    concept_type=typ,
                    title=miss_title,
                    description=desc,
                    body=shared_body,
                    governance="constraint",
                    code_refs=[path],
                ),
                search_concept_spec(
                    late_id,
                    concept_type=typ,
                    title=miss_title,
                    description=desc,
                    body=shared_body,
                    governance="constraint",
                    code_refs=[path],
                ),
                search_concept_spec(
                    title_id,
                    concept_type=typ,
                    title=term,
                    description=desc,
                    body=shared_body,
                    governance="constraint",
                    code_refs=[path],
                ),
            ],
        )
        records = require_mcp_search_success(
            mcp_search(ws, query=term, for_path=path, bundle=rel)
        )
        ordered = require_identity_order(records, expected)
        assert ordered == expected, (
            "within one governance the search tool must rank the higher "
            "combined score first and break the remaining tie by concept "
            f"identity ascending, not write order; order={ordered!r}"
        )
        companions = [path, early_id, late_id, title_id, typ, term, miss_title, desc, body]
        titled = record_for_identity(records, title_id)
        assert code_ref_match_reported(titled, companions), (
            "path-plus-query tool hit does not report a code_refs match; "
            f"record={titled!r}"
        )
        titled_tokens = matched_field_tokens(titled, companions)
        assert "title" in titled_tokens, (
            "path-plus-query tool hit does not report the keyword field; "
            f"tokens={sorted(titled_tokens)}"
        )
        assert_path_hit_reports(titled, companions, ["title"])
        for ident in (early_id, late_id):
            other = record_for_identity(records, ident)
            assert code_ref_match_reported(other, companions), (
                "path hit on a path-plus-query tool call does not report a "
                f"code_refs match; identity={ident!r} record={other!r}"
            )
            assert_matched_keyword_fields(other, companions, ())
        print("MCP same-governance score then identity ok", flush=True)


def test_identical_reruns_return_the_same_identity_order():
    """Identical reruns keep one identity order.

    The command line reruns one keyword query twice with structured
    output and twice without it. The search tool reruns that same
    keyword query, and reruns one path query. The command line also
    reruns one path query twice with structured output and twice
    without it. Each pair must list the same identities in the same
    order. Structured form, including both tool calls, reads that order
    from the hit records. Human form, keyword and path, reads it from
    the concept identity inside each successive governance-badge span.
    An identity that appears only outside those spans is not a position.
    One call may already match a rank some other test checks; the next
    identical call still has to list that same order.
    """
    with workspace() as ws:
        term = compact_token("det")
        ids = numbered_identities(5, compact_token("ds"))
        rel = _kb()
        write_equal_score_title_bundle(ws, rel, term, ids)
        first = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        second = require_search_structured_success(
            run_search(ws, term, rel, structured=True)
        )
        order1 = concept_identity_order(first, ids, form="structured")
        order2 = concept_identity_order(second, ids, form="structured")
        assert order1 == order2 == ids

        # Same keyword query, human text: structured output is not
        # requested. Order is the badge-span reader, shared with the
        # path human rerun. The title, the shared concept text, and the
        # bundle path are stable across hits. An identity sitting inside
        # one of those strings is not how this cell reads order.
        planted = ws.resolve(rel) / f"{ids[0]}.md"
        try:
            planted_text = planted.read_text(encoding="utf-8")
        except OSError as exc:
            raise AssertionError(
                f"could not read planted keyword concept {planted}: {exc}"
            ) from exc
        if not planted_text:
            raise AssertionError(
                f"planted keyword concept {planted} is empty; "
                "stable text cannot be checked"
            )
        for ident in ids:
            for stable in (term, rel, planted_text):
                assert ident not in stable, (
                    f"identity {ident!r} sits inside stable keyword text "
                    f"{stable!r}"
                )
        human_keyword_first = require_search_success(run_search(ws, term, rel))
        human_keyword_second = require_search_success(run_search(ws, term, rel))
        require_repeated_human_search_identity_order(
            human_keyword_first, human_keyword_second, ids
        )

        tool_keyword_first = require_mcp_search_success(
            mcp_search(ws, query=term, bundle=rel)
        )
        tool_keyword_second = require_mcp_search_success(
            mcp_search(ws, query=term, bundle=rel)
        )
        require_repeated_search_identity_order(
            tool_keyword_first, tool_keyword_second, ids
        )

        hold_id, con_id, ctx_id = inverted_governance_identities()
        path_ids = [hold_id, con_id, ctx_id]
        typ, htitle, ctitle, xtitle, desc, body = unique_tokens(
            "typ", "ht", "ct", "xt", "dsc", "bod"
        )
        path = f"pkg/{compact_token('p')}/x.go"
        path_rel = _kb()
        write_concepts_later_first(
            ws,
            path_rel,
            [
                search_concept_spec(
                    hold_id,
                    concept_type=typ,
                    title=htitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="hold",
                    code_refs=[path],
                ),
                search_concept_spec(
                    con_id,
                    concept_type=typ,
                    title=ctitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="constraint",
                    code_refs=[path],
                ),
                search_concept_spec(
                    ctx_id,
                    concept_type=typ,
                    title=xtitle,
                    description=desc,
                    body=f"{body}\n",
                    governance="context",
                    code_refs=[path],
                ),
            ],
        )
        tool_path_first = require_mcp_search_success(
            mcp_search(ws, for_path=path, bundle=path_rel)
        )
        tool_path_second = require_mcp_search_success(
            mcp_search(ws, for_path=path, bundle=path_rel)
        )
        require_repeated_search_identity_order(
            tool_path_first, tool_path_second, path_ids
        )

        # The path string and the texts shared by every hit are stable.
        # Human order is still the badge-span reader, not where an
        # identity first appears in the report.
        for ident in path_ids:
            for stable in (path, path_rel, typ, desc, body, htitle, ctitle, xtitle):
                assert ident not in stable, (
                    f"identity {ident!r} sits inside stable text {stable!r}"
                )

        cli_path_structured_first = require_search_structured_success(
            run_search(ws, None, path_rel, for_path=path, structured=True)
        )
        cli_path_structured_second = require_search_structured_success(
            run_search(ws, None, path_rel, for_path=path, structured=True)
        )
        require_repeated_search_identity_order(
            cli_path_structured_first,
            cli_path_structured_second,
            path_ids,
        )

        human_path_first = require_search_success(
            run_search(ws, None, path_rel, for_path=path)
        )
        human_path_second = require_search_success(
            run_search(ws, None, path_rel, for_path=path)
        )
        require_repeated_human_search_identity_order(
            human_path_first, human_path_second, path_ids
        )
        print("deterministic reruns ok", flush=True)
