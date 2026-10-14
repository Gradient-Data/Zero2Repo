# feature: F06
"""Groups, nesting, and deferred subcommand loading (FP-06).

Assertions stay at the PRD's precision: named dispatch, outside-in
nesting, parameters staying on the command that declared them, the
no-arguments help page versus leftover-empty / unknown-name usage
failures, invoke-without-command, immediate versus late registration,
custom listing/lookup, command collections, hidden children, and a
chaining group that cannot nest further groups. Wording of usage
sentences, exception types, and context attribute spelling are not
pinned.
"""

from __future__ import annotations

import importlib
import uuid

from optlyn import (
    CommandCollection,
    argument,
    command,
    group,
    option,
    pass_context,
    version_option,
)
from F06_helpers import (
    _LookupGroup,
    _emit_pending_subcommand,
    _group_desc,
    _group_hi,
    _group_ident,
    _group_leaf,
    _group_root,
    _group_run,
    _group_visible,
    _line_starting,
    _on_path,
    _read_order,
    _require_before,
    _require_invocation_reports_unlike,
    _three_layer,
    _trace_loaded,
    _write_leaf_module,
)

from _harness import workspace
from _helpers import (
    assert_declaration_refused,
    assert_eager_identity,
    assert_intentional_help,
    assert_success_marker_present,
    assert_usage_class,
    assert_usage_help,
    assert_usage_without_help_page,
    default_invoked_name,
    unrelated_dispatch_token,
)


# ---------------------------------------------------------------------------
# A. Named dispatch, ownership, child help/version still runs the group
# ---------------------------------------------------------------------------


def test_named_subcommand_runs_matching_callback_only():
    group_hi = _group_hi()
    hi_a = _group_hi()
    hi_b = _group_hi()
    name_a = f"a-{_group_ident()}"
    name_b = f"b-{_group_ident()}"
    cli = _group_root(group_hi)
    cli.add_command(_group_leaf(hi_a, name=name_a))
    cli.add_command(_group_leaf(hi_b, name=name_b))

    ran_a = _group_run(cli, [name_a])
    ran_b = _group_run(cli, [name_b])
    print(
        f"A stdout={ran_a.stdout_text!r} B stdout={ran_b.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(ran_a, hi_a)
    assert_success_marker_present(ran_a, group_hi)
    assert hi_b not in ran_a.stdout_text, (
        f"unmatched child {name_b!r} ran; stdout={ran_a.stdout_text!r}"
    )
    _require_before(ran_a.stdout_text, group_hi, hi_a)

    assert_success_marker_present(ran_b, hi_b)
    assert_success_marker_present(ran_b, group_hi)
    assert hi_a not in ran_b.stdout_text, (
        f"unmatched child {name_a!r} ran; stdout={ran_b.stdout_text!r}"
    )
    _require_before(ran_b.stdout_text, group_hi, hi_b)


def test_group_option_does_not_leak_into_child():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    gflag = f"--{_group_ident()}"
    gdest = _group_ident()
    cflag = f"--{_group_ident()}"
    cdest = _group_ident()
    gval = _group_ident()
    cval = _group_ident()
    assert gval != cval and gflag != cflag

    def root(**kwargs) -> None:
        print(group_hi, flush=True)
        print(f"GVAL:{kwargs[gdest]}", flush=True)

    root.__name__ = f"{_group_ident()}_{_group_ident()}"
    cli = group()(option(gflag, gdest)(root))

    def child(**kwargs) -> None:
        print(child_hi, flush=True)
        print(f"CVAL:{kwargs[cdest]}", flush=True)

    child.__name__ = f"{_group_ident()}_{_group_ident()}"
    cli.add_command(command(name=child_name)(option(cflag, cdest)(child)))

    result = _group_run(cli, [gflag, gval, child_name, cflag, cval])
    print(f"owned stdout={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, group_hi)
    assert_success_marker_present(result, child_hi)
    gline = _line_starting(result.stdout_text, "GVAL:")
    cline = _line_starting(result.stdout_text, "CVAL:")
    assert gline == f"GVAL:{gval}", f"group value line {gline!r}"
    assert cline == f"CVAL:{cval}", f"child value line {cline!r}"
    assert gval not in cline, (
        f"group value leaked into the child line; cline={cline!r}"
    )
    assert cval not in gline, (
        f"child value leaked into the group line; gline={gline!r}"
    )
    _require_before(result.stdout_text, group_hi, child_hi)


def test_named_child_help_or_version_still_runs_group():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    first = f"Short {uuid.uuid4().hex} leaf."
    unique = f"Pageonly {uuid.uuid4().hex} details."
    identity = f"ver-{uuid.uuid4().hex}"
    cli = _group_root(group_hi)

    def child() -> None:
        print(child_hi, flush=True)

    child.__name__ = f"{_group_ident()}_{_group_ident()}"
    child.__doc__ = f"{first}\n\n{unique}"
    cli.add_command(command(name=child_name)(version_option(identity)(child)))

    ran = _group_run(cli, [child_name])
    print(f"child-run stdout={ran.stdout_text!r}", flush=True)
    assert_success_marker_present(ran, child_hi)
    assert_success_marker_present(ran, group_hi)

    helped = _group_run(cli, [child_name, "--help"])
    print(
        f"child-help exit={helped.exit_code} stdout={helped.stdout_text!r}",
        flush=True,
    )
    assert helped.exit_code == 0, (
        f"child --help expected exit 0, got {helped.exit_code}; "
        f"stdout={helped.stdout_text!r} stderr={helped.stderr_text!r}"
    )
    assert group_hi in helped.stdout_text, (
        f"named-child help skipped the group; stdout={helped.stdout_text!r}"
    )
    assert child_hi not in helped.stdout_text, (
        f"named-child help ran the child; stdout={helped.stdout_text!r}"
    )
    assert unique in helped.stdout_text, (
        f"child-page unique mark {unique!r} missing; "
        f"stdout={helped.stdout_text!r}"
    )

    versioned = _group_run(cli, [child_name, "--version"])
    print(f"child-version stdout={versioned.stdout_text!r}", flush=True)
    assert versioned.exit_code == 0, (
        f"child --version expected exit 0, got {versioned.exit_code}; "
        f"stdout={versioned.stdout_text!r} stderr={versioned.stderr_text!r}"
    )
    assert group_hi in versioned.stdout_text, (
        f"named-child version skipped the group; "
        f"stdout={versioned.stdout_text!r}"
    )
    assert child_hi not in versioned.stdout_text, (
        f"named-child version ran the child; stdout={versioned.stdout_text!r}"
    )
    assert identity in versioned.stdout_text, (
        f"child version missing identity {identity!r}; "
        f"stdout={versioned.stdout_text!r}"
    )


def test_group_level_help_or_version_skips_group_and_does_not_group_run():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    desc = _group_desc("G")
    identity = f"ver-{uuid.uuid4().hex}"

    def root() -> None:
        print(group_hi, flush=True)

    root.__name__ = f"{_group_ident()}_{_group_ident()}"
    root.__doc__ = desc
    cli = group()(version_option(identity)(root))
    cli.add_command(_group_leaf(child_hi, name=child_name))

    named = _group_run(cli, [child_name])
    assert_success_marker_present(named, group_hi)

    helped = _group_run(cli, ["--help"])
    print(f"group-help stdout={helped.stdout_text!r}", flush=True)
    assert_intentional_help(helped, group_hi, desc)
    assert child_hi not in helped.stdout_text

    versioned = _group_run(cli, ["--version"])
    print(f"group-version stdout={versioned.stdout_text!r}", flush=True)
    assert_eager_identity(versioned, group_hi, identity)
    assert child_hi not in versioned.stdout_text
    assert child_hi not in versioned.stderr_text


def test_help_before_subcommand_is_group_help():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    desc = _group_desc("G")
    first = f"Short {uuid.uuid4().hex} leaf."
    unique = f"Pageonly {uuid.uuid4().hex} details."

    def root() -> None:
        print(group_hi, flush=True)

    root.__name__ = f"{_group_ident()}_{_group_ident()}"
    root.__doc__ = desc
    cli = group()(root)

    def child() -> None:
        print(child_hi, flush=True)

    child.__name__ = f"{_group_ident()}_{_group_ident()}"
    child.__doc__ = f"{first}\n\n{unique}"
    cli.add_command(command(name=child_name)(child))

    parent_help = _group_run(cli, ["--help", child_name])
    child_help = _group_run(cli, [child_name, "--help"])
    print(
        f"help-sub stdout={parent_help.stdout_text!r} "
        f"sub-help stdout={child_help.stdout_text!r}",
        flush=True,
    )
    assert_intentional_help(parent_help, group_hi, desc)
    assert child_hi not in parent_help.stdout_text
    assert unique not in parent_help.stdout_text, (
        f"child-page unique mark {unique!r} appeared on tool --help sub; "
        f"stdout={parent_help.stdout_text!r}"
    )

    assert child_help.exit_code == 0, (
        f"tool sub --help expected exit 0, got {child_help.exit_code}; "
        f"stdout={child_help.stdout_text!r} stderr={child_help.stderr_text!r}"
    )
    assert group_hi in child_help.stdout_text
    assert child_hi not in child_help.stdout_text
    assert unique in child_help.stdout_text, (
        f"child-page unique mark {unique!r} missing from tool sub --help; "
        f"stdout={child_help.stdout_text!r}"
    )


# ---------------------------------------------------------------------------
# B. Nesting outside-in; every layer; ownership at every layer
# ---------------------------------------------------------------------------


def test_nested_groups_run_outside_in():
    cli, n = _three_layer()
    result = _group_run(cli, [n["mid_name"], n["leaf_name"]])
    print(f"nested stdout={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, n["outer_hi"])
    assert_success_marker_present(result, n["mid_hi"])
    assert_success_marker_present(result, n["leaf_hi"])
    _require_before(result.stdout_text, n["outer_hi"], n["mid_hi"])
    _require_before(result.stdout_text, n["mid_hi"], n["leaf_hi"])


def test_grandchild_is_unreachable_without_middle_group():
    cli, n = _three_layer()
    full = _group_run(cli, [n["mid_name"], n["leaf_name"]])
    assert_success_marker_present(full, n["leaf_hi"])

    skipped = _group_run(cli, [n["leaf_name"]])
    print(
        f"skip-middle exit={skipped.exit_code} stdout={skipped.stdout_text!r} "
        f"stderr={skipped.stderr_text!r}",
        flush=True,
    )
    assert_usage_without_help_page(skipped, n["outer_hi"], n["outer_desc"])
    vis = _group_visible(skipped)
    assert n["mid_hi"] not in vis
    assert n["leaf_hi"] not in vis


def test_nested_group_empty_args_is_that_groups_help_page():
    cli, n = _three_layer()
    full = _group_run(cli, [n["mid_name"], n["leaf_name"]])
    assert_success_marker_present(full, n["leaf_hi"])

    stopped = _group_run(cli, [n["mid_name"]])
    print(
        f"stop-middle exit={stopped.exit_code} stdout={stopped.stdout_text!r} "
        f"stderr={stopped.stderr_text!r}",
        flush=True,
    )
    # Named dispatch to the middle group still runs the outer callback
    # (FP-06); the middle then shows its own no-arguments help page.
    assert_usage_help(stopped, n["mid_hi"], n["mid_desc"])
    vis = _group_visible(stopped)
    assert n["outer_hi"] in vis, (
        f"outer callback did not run before the nested help page; "
        f"visible={vis!r}"
    )
    assert n["leaf_hi"] not in vis
    assert n["outer_desc"] not in vis, (
        f"outer description appeared on the nested empty-args page; "
        f"visible={vis!r}"
    )


def test_nested_option_ownership_at_every_layer():
    outer_hi = _group_hi()
    mid_hi = _group_hi()
    leaf_hi = _group_hi()
    mid_name = f"m-{_group_ident()}"
    leaf_name = f"l-{_group_ident()}"
    oflag, mflag, lflag = f"--{_group_ident()}", f"--{_group_ident()}", f"--{_group_ident()}"
    odest, mdest, ldest = _group_ident(), _group_ident(), _group_ident()
    oval, mval, lval = _group_ident(), _group_ident(), _group_ident()
    assert len({oval, mval, lval}) == 3

    def outer(**kwargs) -> None:
        print(outer_hi, flush=True)
        print(f"OVAL:{kwargs[odest]}", flush=True)

    outer.__name__ = f"{_group_ident()}_{_group_ident()}"
    cli = group()(option(oflag, odest)(outer))

    def middle(**kwargs) -> None:
        print(mid_hi, flush=True)
        print(f"MVAL:{kwargs[mdest]}", flush=True)

    middle.__name__ = f"{_group_ident()}_{_group_ident()}"
    mid = group(name=mid_name)(option(mflag, mdest)(middle))

    def leaf(**kwargs) -> None:
        print(leaf_hi, flush=True)
        print(f"LVAL:{kwargs[ldest]}", flush=True)

    leaf.__name__ = f"{_group_ident()}_{_group_ident()}"
    mid.add_command(command(name=leaf_name)(option(lflag, ldest)(leaf)))
    cli.add_command(mid)

    result = _group_run(
        cli,
        [
            oflag,
            oval,
            mid_name,
            mflag,
            mval,
            leaf_name,
            lflag,
            lval,
        ],
    )
    print(f"tri-owned stdout={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, outer_hi)
    assert_success_marker_present(result, mid_hi)
    assert_success_marker_present(result, leaf_hi)
    oline = _line_starting(result.stdout_text, "OVAL:")
    mline = _line_starting(result.stdout_text, "MVAL:")
    lline = _line_starting(result.stdout_text, "LVAL:")
    assert oline == f"OVAL:{oval}"
    assert mline == f"MVAL:{mval}"
    assert lline == f"LVAL:{lval}"
    assert oval not in mline and oval not in lline
    assert mval not in lline
    _require_before(result.stdout_text, outer_hi, mid_hi)
    _require_before(result.stdout_text, mid_hi, leaf_hi)


# ---------------------------------------------------------------------------
# C. Empty-args help page vs unknown / leftover-empty
# ---------------------------------------------------------------------------


def test_empty_group_args_use_usage_help_page():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    desc = _group_desc("G")
    cli = _group_root(group_hi, doc=desc)
    cli.add_command(_group_leaf(child_hi, name=child_name))

    empty = _group_run(cli, [])
    helped = _group_run(cli, ["--help"])
    print(
        f"empty exit={empty.exit_code} stdout={empty.stdout_text!r} "
        f"help exit={helped.exit_code}",
        flush=True,
    )
    assert_usage_help(empty, group_hi, desc)
    assert child_hi not in _group_visible(empty)
    assert_intentional_help(helped, group_hi, desc)
    assert child_hi not in helped.stdout_text


def test_unknown_subcommand_is_usage_error_without_help_page():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    desc = _group_desc("G")
    cli = _group_root(group_hi, doc=desc)
    cli.add_command(_group_leaf(child_hi, name=child_name))

    empty = _group_run(cli, [])
    assert_usage_help(empty, group_hi, desc)

    token = unrelated_dispatch_token(child_name, group_hi, desc)
    unknown = _group_run(cli, [token])
    print(
        f"unknown token={token!r} exit={unknown.exit_code} "
        f"stderr={unknown.stderr_text!r}",
        flush=True,
    )
    assert_usage_without_help_page(unknown, group_hi, desc)
    vis = _group_visible(unknown)
    assert child_hi not in vis


def test_group_options_or_arguments_only_is_usage_error_without_help_page():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    desc = _group_desc("G")
    gflag = f"--{_group_ident()}"
    gdest = _group_ident()
    gval = _group_ident()
    slot = _group_ident()
    aval = _group_ident()

    def root_opt(**kwargs) -> None:
        print(group_hi, flush=True)
        print(f"GVAL:{kwargs[gdest]}", flush=True)

    root_opt.__name__ = f"{_group_ident()}_{_group_ident()}"
    root_opt.__doc__ = desc
    opt_cli = group()(option(gflag, gdest)(root_opt))
    opt_cli.add_command(_group_leaf(child_hi, name=child_name))

    empty_opt = _group_run(opt_cli, [])
    assert_usage_help(empty_opt, group_hi, desc)
    named_opt = _group_run(opt_cli, [gflag, gval, child_name])
    assert_success_marker_present(named_opt, child_hi)
    leftover_opt = _group_run(opt_cli, [gflag, gval])
    print(
        f"leftover-opt exit={leftover_opt.exit_code} "
        f"stderr={leftover_opt.stderr_text!r}",
        flush=True,
    )
    assert_usage_without_help_page(leftover_opt, group_hi, desc)
    assert child_hi not in _group_visible(leftover_opt)

    def root_arg(**kwargs) -> None:
        print(group_hi, flush=True)
        print(f"GVAL:{kwargs[slot]}", flush=True)

    root_arg.__name__ = f"{_group_ident()}_{_group_ident()}"
    root_arg.__doc__ = desc
    arg_cli = group()(argument(slot)(root_arg))
    arg_cli.add_command(_group_leaf(child_hi, name=child_name))

    empty_arg = _group_run(arg_cli, [])
    assert_usage_help(empty_arg, group_hi, desc)
    leftover_arg = _group_run(arg_cli, [aval])
    print(
        f"leftover-arg exit={leftover_arg.exit_code} "
        f"stderr={leftover_arg.stderr_text!r}",
        flush=True,
    )
    assert_usage_without_help_page(leftover_arg, group_hi, desc)
    assert child_hi not in _group_visible(leftover_arg)


def test_group_argument_then_child_binds_and_dispatches():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    slot = _group_ident()
    aval = _group_ident()

    def root(**kwargs) -> None:
        print(group_hi, flush=True)
        print(f"GVAL:{kwargs[slot]}", flush=True)

    root.__name__ = f"{_group_ident()}_{_group_ident()}"
    cli = group()(argument(slot)(root))
    cli.add_command(_group_leaf(child_hi, name=child_name))

    result = _group_run(cli, [aval, child_name])
    print(f"arg-then-child stdout={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, child_hi)
    assert_success_marker_present(result, group_hi)
    assert _line_starting(result.stdout_text, "GVAL:") == f"GVAL:{aval}"
    _require_before(result.stdout_text, group_hi, child_hi)


# ---------------------------------------------------------------------------
# D. Invoke without a command; no-args-is-help independently on group vs leaf
# ---------------------------------------------------------------------------


def test_invoke_without_command_runs_group_on_empty_and_before_child():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    desc = _group_desc("G")
    default = _group_root(group_hi, doc=desc)
    default.add_command(_group_leaf(child_hi, name=child_name))
    empty_default = _group_run(default, [])
    assert_usage_help(empty_default, group_hi, desc)

    cli = _group_root(group_hi, doc=desc, invoke_without_command=True)
    cli.add_command(_group_leaf(child_hi, name=child_name))
    empty = _group_run(cli, [])
    named = _group_run(cli, [child_name])
    print(
        f"iwo-empty stdout={empty.stdout_text!r} "
        f"iwo-named stdout={named.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(empty, group_hi)
    assert child_hi not in empty.stdout_text, (
        f"invoke-without-command empty run also ran a child; "
        f"stdout={empty.stdout_text!r}"
    )
    assert_success_marker_present(named, group_hi)
    assert_success_marker_present(named, child_hi)
    _require_before(named.stdout_text, group_hi, child_hi)


def test_context_distinguishes_group_only_from_group_then_child():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    pending_label = f"P{uuid.uuid4().hex}:"

    def root(ctx) -> None:
        print(group_hi, flush=True)
        _emit_pending_subcommand(ctx, pending_label)

    root.__name__ = f"{_group_ident()}_{_group_ident()}"
    cli = group(invoke_without_command=True)(pass_context(root))
    cli.add_command(_group_leaf(child_hi, name=child_name))

    empty = _group_run(cli, [])
    named = _group_run(cli, [child_name])
    print(
        f"ctx-empty stdout={empty.stdout_text!r} "
        f"ctx-named stdout={named.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(empty, group_hi)
    assert_success_marker_present(named, group_hi)
    _require_invocation_reports_unlike(empty, named, pending_label)


def test_group_can_disable_no_args_is_help():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    desc = _group_desc("G")
    default = _group_root(group_hi, doc=desc)
    default.add_command(_group_leaf(child_hi, name=child_name))
    empty_default = _group_run(default, [])
    assert_usage_help(empty_default, group_hi, desc)

    cli = _group_root(group_hi, doc=desc, no_args_is_help=False)
    cli.add_command(_group_leaf(child_hi, name=child_name))
    empty = _group_run(cli, [])
    print(
        f"disabled-empty exit={empty.exit_code} stdout={empty.stdout_text!r} "
        f"stderr={empty.stderr_text!r}",
        flush=True,
    )
    assert_usage_without_help_page(empty, group_hi, desc)
    assert child_hi not in _group_visible(empty)


def test_leaf_default_empty_runs_leaf_not_help():
    hi = _group_hi()
    desc = _group_desc("L")
    default = _group_leaf(hi, doc=desc)
    empty = _group_run(default, [])
    print(f"leaf-default stdout={empty.stdout_text!r}", flush=True)
    assert_success_marker_present(empty, hi)

    helped_leaf = _group_leaf(hi, doc=desc, no_args_is_help=True)
    missing = _group_run(helped_leaf, [])
    print(
        f"leaf-help-empty exit={missing.exit_code} "
        f"stdout={missing.stdout_text!r}",
        flush=True,
    )
    assert_usage_help(missing, hi, desc)


# ---------------------------------------------------------------------------
# E. Immediate helper, late registration, other module, explicit name
# ---------------------------------------------------------------------------


def test_group_command_helper_attaches_immediately():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    cli = _group_root(group_hi)

    def child() -> None:
        print(child_hi, flush=True)

    child.__name__ = f"{_group_ident()}_{_group_ident()}"
    cli.command(name=child_name)(child)

    result = _group_run(cli, [child_name])
    print(f"helper stdout={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, group_hi)
    assert_success_marker_present(result, child_hi)
    _require_before(result.stdout_text, group_hi, child_hi)


def test_late_registration_invokes_like_immediate():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"

    immediate = _group_root(group_hi)

    def child_now() -> None:
        print(child_hi, flush=True)

    child_now.__name__ = f"{_group_ident()}_{_group_ident()}"
    immediate.command(name=child_name)(child_now)

    late = _group_root(group_hi)
    leaf = _group_leaf(child_hi, name=child_name)
    late.add_command(leaf)

    now = _group_run(immediate, [child_name])
    later = _group_run(late, [child_name])
    print(
        f"immediate stdout={now.stdout_text!r} late stdout={later.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(now, group_hi)
    assert_success_marker_present(now, child_hi)
    assert_success_marker_present(later, group_hi)
    assert_success_marker_present(later, child_hi)
    _require_before(now.stdout_text, group_hi, child_hi)
    _require_before(later.stdout_text, group_hi, child_hi)


def test_late_registration_from_another_module():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    gmod = f"zxqg{uuid.uuid4().hex}"
    amod = f"zxqa{uuid.uuid4().hex}"

    with workspace() as ws:
        gpath = ws.write(
            f"{gmod}.py",
            "from optlyn import group\n"
            f"def _cb():\n"
            f"    print({group_hi!r}, flush=True)\n"
            f"_cb.__name__ = {_group_ident()!r}\n"
            f"cli = group()(_cb)\n",
        )
        apath = ws.write(
            f"{amod}.py",
            "from optlyn import command\n"
            f"from {gmod} import cli\n"
            f"def _cb():\n"
            f"    print({child_hi!r}, flush=True)\n"
            f"_cb.__name__ = {_group_ident()!r}\n"
            f"cli.add_command(command(name={child_name!r})(_cb))\n",
        )
        if not gpath.is_file() or not apath.is_file():
            raise RuntimeError("failed to write registration modules")
        with _on_path(ws.path, gmod, amod):
            try:
                importlib.import_module(amod)
                cli = importlib.import_module(gmod).cli
            except Exception as exc:
                raise RuntimeError(
                    f"failed to import late-registration modules: {exc}"
                ) from exc
            result = _group_run(cli, [child_name])
        print(f"other-module stdout={result.stdout_text!r}", flush=True)
        assert_success_marker_present(result, group_hi)
        assert_success_marker_present(result, child_hi)
        _require_before(result.stdout_text, group_hi, child_hi)


def test_explicit_name_independent_of_function_name():
    group_hi = _group_hi()
    child_hi = _group_hi()
    func_name = f"{_group_ident()}_command"
    mapped = default_invoked_name(func_name)
    explicit = f"ex-{_group_ident()}"
    assert explicit != mapped
    cli = _group_root(group_hi)

    def child() -> None:
        print(child_hi, flush=True)

    child.__name__ = func_name
    cli.command(name=explicit)(child)

    ok = _group_run(cli, [explicit])
    print(f"explicit stdout={ok.stdout_text!r} mapped={mapped!r}", flush=True)
    assert_success_marker_present(ok, group_hi)
    assert_success_marker_present(ok, child_hi)
    _require_before(ok.stdout_text, group_hi, child_hi)

    token = unrelated_dispatch_token(explicit, mapped, func_name)
    unknown = _group_run(cli, [token])
    print(
        f"unrelated token={token!r} exit={unknown.exit_code} "
        f"stderr={unknown.stderr_text!r}",
        flush=True,
    )
    assert_usage_class(unknown, group_hi)
    assert child_hi not in _group_visible(unknown)


# ---------------------------------------------------------------------------
# F. Custom listing/lookup; load only when needed
# ---------------------------------------------------------------------------


def test_custom_lookup_loads_only_the_requested_child():
    group_hi = _group_hi()
    hi_a = _group_hi()
    hi_b = _group_hi()
    name_a = f"a-{_group_ident()}"
    name_b = f"b-{_group_ident()}"
    mod_a = f"zxqa{uuid.uuid4().hex}"
    mod_b = f"zxqb{uuid.uuid4().hex}"

    with workspace() as ws:
        trace_a = ws.path / f"{mod_a}.loaded"
        trace_b = ws.path / f"{mod_b}.loaded"
        _write_leaf_module(ws, mod_a, hi_a, name_a, trace_a)
        _write_leaf_module(ws, mod_b, hi_b, name_b, trace_b)

        def resolve(name: str):
            if name == name_a:
                return importlib.import_module(mod_a).cli
            if name == name_b:
                return importlib.import_module(mod_b).cli
            return None

        cli = group(cls=_LookupGroup)(_group_root(group_hi).callback)
        assert isinstance(cli, _LookupGroup)
        cli.configure([name_a, name_b], resolve)

        with _on_path(ws.path, mod_a, mod_b):
            ran_a = _group_run(cli, [name_a])
            print(
                f"lazy-A stdout={ran_a.stdout_text!r} "
                f"looked={cli.looked_up!r} a={_trace_loaded(trace_a)} "
                f"b={_trace_loaded(trace_b)}",
                flush=True,
            )
            assert_success_marker_present(ran_a, group_hi)
            assert_success_marker_present(ran_a, hi_a)
            _require_before(ran_a.stdout_text, group_hi, hi_a)
            assert hi_b not in ran_a.stdout_text
            assert _trace_loaded(trace_a), f"requested child {name_a!r} was not loaded"
            assert not _trace_loaded(trace_b), (
                f"unrequested sibling {name_b!r} was loaded"
            )
            if name_a not in cli.looked_up:
                raise AssertionError(
                    f"custom lookup was never asked for {name_a!r}; "
                    f"looked_up={cli.looked_up!r}"
                )

            ran_b = _group_run(cli, [name_b])
            assert_success_marker_present(ran_b, hi_b)
            assert _trace_loaded(trace_b), (
                f"baseline sibling {name_b!r} never produced a load trace"
            )


def test_lazy_loaded_command_invokes_like_eager():
    group_hi = _group_hi()
    child_hi = _group_hi()
    child_name = f"c-{_group_ident()}"
    mod = f"zxql{uuid.uuid4().hex}"

    with workspace() as ws:
        trace = ws.path / f"{mod}.loaded"
        _write_leaf_module(ws, mod, child_hi, child_name, trace)
        with _on_path(ws.path, mod):
            try:
                leaf = importlib.import_module(mod).cli
            except Exception as exc:
                raise RuntimeError(f"failed to import eager leaf module: {exc}") from exc
            eager = _group_root(group_hi)
            eager.add_command(leaf)

            def resolve(name: str):
                if name == child_name:
                    return importlib.import_module(mod).cli
                return None

            lazy = group(cls=_LookupGroup)(_group_root(group_hi).callback)
            assert isinstance(lazy, _LookupGroup)
            lazy.configure([child_name], resolve)

            eager_run = _group_run(eager, [child_name])
            lazy_run = _group_run(lazy, [child_name])
        print(
            f"eager stdout={eager_run.stdout_text!r} "
            f"lazy stdout={lazy_run.stdout_text!r}",
            flush=True,
        )
        assert_success_marker_present(eager_run, group_hi)
        assert_success_marker_present(eager_run, child_hi)
        assert_success_marker_present(lazy_run, group_hi)
        assert_success_marker_present(lazy_run, child_hi)
        _require_before(eager_run.stdout_text, group_hi, child_hi)
        _require_before(lazy_run.stdout_text, group_hi, child_hi)


def test_custom_listing_and_lookup_resolve_alias():
    group_hi = _group_hi()
    child_hi = _group_hi()
    alias = f"al-{_group_ident()}"
    leaf = _group_leaf(child_hi)
    desc = _group_desc("G")

    def resolve(name: str):
        if name == alias:
            return leaf
        return None

    def root() -> None:
        print(group_hi, flush=True)

    root.__name__ = f"{_group_ident()}_{_group_ident()}"
    root.__doc__ = desc
    cli = group(cls=_LookupGroup)(root)
    assert isinstance(cli, _LookupGroup)
    cli.configure([alias], resolve)

    ran = _group_run(cli, [alias])
    helped = _group_run(cli, ["--help"])
    print(
        f"alias-run stdout={ran.stdout_text!r} help={helped.stdout_text!r} "
        f"listed={cli.listed!r} looked={cli.looked_up!r}",
        flush=True,
    )
    assert_success_marker_present(ran, group_hi)
    assert_success_marker_present(ran, child_hi)
    _require_before(ran.stdout_text, group_hi, child_hi)
    assert_intentional_help(helped, group_hi, desc)
    assert alias in helped.stdout_text, (
        f"custom listing alias {alias!r} missing from help; "
        f"stdout={helped.stdout_text!r}"
    )
    if not cli.listed:
        raise AssertionError(
            f"help never asked the custom lister; listed={cli.listed!r}"
        )
    if alias not in cli.looked_up:
        raise AssertionError(
            f"dispatch/help never asked lookup for {alias!r}; "
            f"looked_up={cli.looked_up!r}"
        )


def test_nested_resolve_loads_middle_then_group_leaf():
    outer_hi = _group_hi()
    mid_hi = _group_hi()
    leaf_hi = _group_hi()
    sib_hi = _group_hi()
    mid_name = f"m-{_group_ident()}"
    leaf_name = f"l-{_group_ident()}"
    sib_name = f"s-{_group_ident()}"
    mid_mod = f"zxqm{uuid.uuid4().hex}"
    leaf_mod = f"zxql{uuid.uuid4().hex}"
    sib_mod = f"zxqs{uuid.uuid4().hex}"
    mid_desc = _group_desc("M")

    with workspace() as ws:
        order = ws.path / "load-order.log"
        mid_trace = ws.path / f"{mid_mod}.loaded"
        leaf_trace = ws.path / f"{leaf_mod}.loaded"
        sib_trace = ws.path / f"{sib_mod}.loaded"
        _write_leaf_module(
            ws, leaf_mod, leaf_hi, leaf_name, leaf_trace, order, "leaf"
        )
        _write_leaf_module(
            ws, sib_mod, sib_hi, sib_name, sib_trace, order, "sib"
        )
        mid_body = (
            "from optlyn import Group, group\n"
            f"from pathlib import Path as _Trace\n"
            f"_Trace({str(mid_trace)!r}).write_text('loaded', encoding='utf-8')\n"
            f"_op = _Trace({str(order)!r})\n"
            f"_prev = _op.read_text(encoding='utf-8') if _op.is_file() else ''\n"
            f"_op.write_text(_prev + 'middle\\n', encoding='utf-8')\n"
            f"class _Mid(Group):\n"
            f"    def list_commands(self, ctx):\n"
            f"        return [{leaf_name!r}, {sib_name!r}]\n"
            f"    def get_command(self, ctx, cmd_name):\n"
            f"        if cmd_name == {leaf_name!r}:\n"
            f"            import {leaf_mod} as _leafmod\n"
            f"            return _leafmod.cli\n"
            f"        if cmd_name == {sib_name!r}:\n"
            f"            import {sib_mod} as _sibmod\n"
            f"            return _sibmod.cli\n"
            f"        return None\n"
            f"def _mid():\n"
            f"    print({mid_hi!r}, flush=True)\n"
            f"_mid.__name__ = {_group_ident()!r}\n"
            f"_mid.__doc__ = {mid_desc!r}\n"
            f"cli = group(cls=_Mid, name={mid_name!r})(_mid)\n"
        )
        dest = ws.write(f"{mid_mod}.py", mid_body)
        if not dest.is_file():
            raise RuntimeError(f"failed to write middle module at {dest}")

        def resolve(name: str):
            if name == mid_name:
                return importlib.import_module(mid_mod).cli
            return None

        outer = group(cls=_LookupGroup)(_group_root(outer_hi).callback)
        assert isinstance(outer, _LookupGroup)
        outer.configure([mid_name], resolve)

        with _on_path(ws.path, mid_mod, leaf_mod, sib_mod):
            result = _group_run(outer, [mid_name, leaf_name])
            print(
                f"nested-lazy stdout={result.stdout_text!r} "
                f"order={_read_order(order)!r}",
                flush=True,
            )
            assert_success_marker_present(result, outer_hi)
            assert_success_marker_present(result, mid_hi)
            assert_success_marker_present(result, leaf_hi)
            _require_before(result.stdout_text, outer_hi, mid_hi)
            _require_before(result.stdout_text, mid_hi, leaf_hi)
            assert _trace_loaded(mid_trace)
            assert _trace_loaded(leaf_trace)
            assert not _trace_loaded(sib_trace), (
                f"unrequested grandchild sibling {sib_name!r} was loaded"
            )
            tags = _read_order(order)
            assert "middle" in tags and "leaf" in tags, (
                f"load-order log missing middle/leaf; tags={tags!r}"
            )
            assert tags.index("middle") <= tags.index("leaf"), (
                f"middle loaded after leaf; tags={tags!r}"
            )
            assert "sib" not in tags


def test_help_loads_immediate_children_not_grandchildren():
    outer_hi = _group_hi()
    mid_hi = _group_hi()
    leaf_hi = _group_hi()
    mid_name = f"m-{_group_ident()}"
    leaf_name = f"l-{_group_ident()}"
    mid_mod = f"zxqm{uuid.uuid4().hex}"
    leaf_mod = f"zxql{uuid.uuid4().hex}"
    outer_desc = _group_desc("O")
    mid_desc = _group_desc("M")

    with workspace() as ws:
        order = ws.path / "help-order.log"
        mid_trace = ws.path / f"{mid_mod}.loaded"
        leaf_trace = ws.path / f"{leaf_mod}.loaded"
        _write_leaf_module(
            ws, leaf_mod, leaf_hi, leaf_name, leaf_trace, order, "leaf"
        )
        mid_body = (
            "from optlyn import Group, group\n"
            f"from pathlib import Path as _Trace\n"
            f"_Trace({str(mid_trace)!r}).write_text('loaded', encoding='utf-8')\n"
            f"_op = _Trace({str(order)!r})\n"
            f"_prev = _op.read_text(encoding='utf-8') if _op.is_file() else ''\n"
            f"_op.write_text(_prev + 'middle\\n', encoding='utf-8')\n"
            f"class _Mid(Group):\n"
            f"    def list_commands(self, ctx):\n"
            f"        return [{leaf_name!r}]\n"
            f"    def get_command(self, ctx, cmd_name):\n"
            f"        if cmd_name == {leaf_name!r}:\n"
            f"            import {leaf_mod} as _leafmod\n"
            f"            return _leafmod.cli\n"
            f"        return None\n"
            f"def _mid():\n"
            f"    print({mid_hi!r}, flush=True)\n"
            f"_mid.__name__ = {_group_ident()!r}\n"
            f"_mid.__doc__ = {mid_desc!r}\n"
            f"cli = group(cls=_Mid, name={mid_name!r})(_mid)\n"
        )
        dest = ws.write(f"{mid_mod}.py", mid_body)
        if not dest.is_file():
            raise RuntimeError(f"failed to write middle module at {dest}")

        def resolve(name: str):
            if name == mid_name:
                return importlib.import_module(mid_mod).cli
            return None

        def outer() -> None:
            print(outer_hi, flush=True)

        outer.__name__ = f"{_group_ident()}_{_group_ident()}"
        outer.__doc__ = outer_desc
        cli = group(cls=_LookupGroup)(outer)
        assert isinstance(cli, _LookupGroup)
        cli.configure([mid_name], resolve)

        with _on_path(ws.path, mid_mod, leaf_mod):
            helped = _group_run(cli, ["--help"])
            print(
                f"parent-help stdout={helped.stdout_text!r} "
                f"mid={_trace_loaded(mid_trace)} leaf={_trace_loaded(leaf_trace)}",
                flush=True,
            )
            assert_intentional_help(helped, outer_hi, outer_desc)
            assert _trace_loaded(mid_trace), (
                "parent help did not load the immediate child module"
            )
            assert not _trace_loaded(leaf_trace), (
                "parent help loaded a grandchild module"
            )

            full = _group_run(cli, [mid_name, leaf_name])
            assert_success_marker_present(full, leaf_hi)
            assert _trace_loaded(leaf_trace), (
                "full path never produced a grandchild load trace"
            )


# ---------------------------------------------------------------------------
# G. Command collection: union of sources
# ---------------------------------------------------------------------------


def test_command_collection_dispatches_union_of_sources():
    hi_a = _group_hi()
    hi_b = _group_hi()
    name_a = f"a-{_group_ident()}"
    name_b = f"b-{_group_ident()}"
    coll_hi = _group_hi()
    coll_desc = _group_desc("C")
    src_a = _group_root(_group_hi())
    src_a.add_command(_group_leaf(hi_a, name=name_a))
    src_b = _group_root(_group_hi())
    src_b.add_command(_group_leaf(hi_b, name=name_b))

    def coll_cb() -> None:
        print(coll_hi, flush=True)

    coll_cb.__name__ = f"{_group_ident()}_{_group_ident()}"
    coll_cb.__doc__ = coll_desc
    coll = group(cls=CommandCollection, sources=[src_a, src_b])(coll_cb)

    ran_a = _group_run(coll, [name_a])
    ran_b = _group_run(coll, [name_b])
    print(
        f"coll-A stdout={ran_a.stdout_text!r} coll-B stdout={ran_b.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(ran_a, hi_a)
    assert hi_b not in ran_a.stdout_text
    assert_success_marker_present(ran_b, hi_b)
    assert hi_a not in ran_b.stdout_text

    empty = _group_run(coll, [])
    assert_usage_help(empty, coll_hi, coll_desc)
    token = unrelated_dispatch_token(name_a, name_b)
    unknown = _group_run(coll, [token])
    print(f"coll-unknown stderr={unknown.stderr_text!r}", flush=True)
    assert_usage_without_help_page(unknown, coll_hi, coll_desc)
    vis = _group_visible(unknown)
    assert hi_a not in vis and hi_b not in vis


def test_command_collection_empty_args_is_usage_help_page():
    hi_a = _group_hi()
    hi_b = _group_hi()
    name_a = f"a-{_group_ident()}"
    name_b = f"b-{_group_ident()}"
    coll_hi = _group_hi()
    coll_desc = _group_desc("C")
    src_a = _group_root(_group_hi())
    src_a.add_command(_group_leaf(hi_a, name=name_a))
    src_b = _group_root(_group_hi())
    src_b.add_command(_group_leaf(hi_b, name=name_b))

    def coll_cb() -> None:
        print(coll_hi, flush=True)

    coll_cb.__name__ = f"{_group_ident()}_{_group_ident()}"
    coll_cb.__doc__ = coll_desc
    coll = group(cls=CommandCollection, sources=[src_a, src_b])(coll_cb)

    empty = _group_run(coll, [])
    print(
        f"coll-empty exit={empty.exit_code} stdout={empty.stdout_text!r}",
        flush=True,
    )
    assert_usage_help(empty, coll_hi, coll_desc)
    vis = _group_visible(empty)
    assert hi_a not in vis and hi_b not in vis


def test_command_collection_help_lists_union():
    hi_a = _group_hi()
    hi_b = _group_hi()
    name_a = f"a-{_group_ident()}"
    name_b = f"b-{_group_ident()}"
    name_b2 = f"b2-{_group_ident()}"
    coll_hi = _group_hi()
    coll_desc = _group_desc("C")
    src_a = _group_root(_group_hi())
    src_a.add_command(_group_leaf(hi_a, name=name_a))
    src_b = _group_root(_group_hi())
    src_b.add_command(_group_leaf(hi_b, name=name_b))

    def coll_cb() -> None:
        print(coll_hi, flush=True)

    coll_cb.__name__ = f"{_group_ident()}_{_group_ident()}"
    coll_cb.__doc__ = coll_desc
    coll = group(cls=CommandCollection, sources=[src_a, src_b])(coll_cb)
    helped = _group_run(coll, ["--help"])
    print(f"coll-help stdout={helped.stdout_text!r}", flush=True)
    assert_intentional_help(helped, coll_hi, coll_desc)
    assert name_a in helped.stdout_text
    assert name_b in helped.stdout_text

    src_b2 = _group_root(_group_hi())
    src_b2.add_command(_group_leaf(hi_b, name=name_b2))
    coll2 = group(cls=CommandCollection, sources=[src_a, src_b2])(coll_cb)
    helped2 = _group_run(coll2, ["--help"])
    print(f"coll-help-renamed stdout={helped2.stdout_text!r}", flush=True)
    assert_intentional_help(helped2, coll_hi, coll_desc)
    assert name_a in helped2.stdout_text
    assert name_b2 in helped2.stdout_text
    assert name_b not in helped2.stdout_text, (
        f"stale source name {name_b!r} still listed; "
        f"stdout={helped2.stdout_text!r}"
    )


# ---------------------------------------------------------------------------
# H. Hidden children omitted from parent help, still reachable
# ---------------------------------------------------------------------------


def test_hidden_child_omitted_from_parent_help_but_reachable():
    group_hi = _group_hi()
    vis_hi = _group_hi()
    hid_hi = _group_hi()
    vis_name = f"v-{_group_ident()}"
    hid_name = f"h-{_group_ident()}"
    desc = _group_desc("G")
    visible = _group_root(group_hi, doc=desc)
    visible.add_command(_group_leaf(vis_hi, name=vis_name))
    hidden = _group_root(group_hi, doc=desc)
    hidden.add_command(_group_leaf(hid_hi, name=hid_name, hidden=True))

    vis_page = _group_run(visible, ["--help"])
    hid_page = _group_run(hidden, ["--help"])
    print(
        f"vis-help={vis_page.stdout_text!r} hid-help={hid_page.stdout_text!r}",
        flush=True,
    )
    assert_intentional_help(vis_page, group_hi, desc)
    assert vis_name in vis_page.stdout_text, (
        f"visible twin {vis_name!r} missing from parent help; "
        f"stdout={vis_page.stdout_text!r}"
    )
    assert_intentional_help(hid_page, group_hi, desc)
    assert hid_name not in hid_page.stdout_text, (
        f"hidden child {hid_name!r} still listed; stdout={hid_page.stdout_text!r}"
    )
    ran = _group_run(hidden, [hid_name])
    print(f"hidden-run stdout={ran.stdout_text!r}", flush=True)
    assert_success_marker_present(ran, group_hi)
    assert_success_marker_present(ran, hid_hi)
    _require_before(ran.stdout_text, group_hi, hid_hi)

    outer_hi = _group_hi()
    mid_hi = _group_hi()
    leaf_hi = _group_hi()
    vis_mid = f"vm-{_group_ident()}"
    hid_mid = f"hm-{_group_ident()}"
    leaf_name = f"l-{_group_ident()}"
    outer_desc = _group_desc("O")
    vis_outer = _group_root(outer_hi, doc=outer_desc)
    vis_middle = _group_root(mid_hi, name=vis_mid)
    vis_middle.add_command(_group_leaf(leaf_hi, name=leaf_name))
    vis_outer.add_command(vis_middle)
    hid_outer = _group_root(outer_hi, doc=outer_desc)
    hid_middle = _group_root(mid_hi, name=hid_mid, hidden=True)
    hid_middle.add_command(_group_leaf(leaf_hi, name=leaf_name))
    hid_outer.add_command(hid_middle)

    vis_gpage = _group_run(vis_outer, ["--help"])
    hid_gpage = _group_run(hid_outer, ["--help"])
    assert vis_mid in vis_gpage.stdout_text
    assert hid_mid not in hid_gpage.stdout_text, (
        f"hidden nested group {hid_mid!r} still listed; "
        f"stdout={hid_gpage.stdout_text!r}"
    )
    nested = _group_run(hid_outer, [hid_mid, leaf_name])
    print(f"hidden-mid stdout={nested.stdout_text!r}", flush=True)
    assert_success_marker_present(nested, outer_hi)
    assert_success_marker_present(nested, mid_hi)
    assert_success_marker_present(nested, leaf_hi)
    _require_before(nested.stdout_text, outer_hi, mid_hi)
    _require_before(nested.stdout_text, mid_hi, leaf_hi)


# ---------------------------------------------------------------------------
# I. Chaining group cannot nest further groups
# ---------------------------------------------------------------------------


def test_chaining_group_refuses_nested_group():
    chain_hi = _group_hi()
    mid_hi = _group_hi()
    leaf_hi = _group_hi()
    mid_name = f"m-{_group_ident()}"
    leaf_name = f"l-{_group_ident()}"

    chain_leaf = _group_root(chain_hi, chain=True)
    chain_leaf.add_command(_group_leaf(leaf_hi, name=leaf_name))
    leaf_ok = _group_run(chain_leaf, [leaf_name])
    print(f"chain-leaf stdout={leaf_ok.stdout_text!r}", flush=True)
    assert_success_marker_present(leaf_ok, leaf_hi)

    nested = _group_root(chain_hi)
    middle = _group_root(mid_hi, name=mid_name)
    middle.add_command(_group_leaf(leaf_hi, name=leaf_name))
    nested.add_command(middle)
    nest_ok = _group_run(nested, [mid_name, leaf_name])
    print(f"nonchain-nest stdout={nest_ok.stdout_text!r}", flush=True)
    assert_success_marker_present(nest_ok, chain_hi)
    assert_success_marker_present(nest_ok, mid_hi)
    assert_success_marker_present(nest_ok, leaf_hi)
    _require_before(nest_ok.stdout_text, chain_hi, mid_hi)
    _require_before(nest_ok.stdout_text, mid_hi, leaf_hi)

    probe = _group_root(chain_hi, chain=True)
    probe_mid = _group_root(mid_hi, name=mid_name)
    probe_mid.add_command(_group_leaf(leaf_hi, name=leaf_name))
    refused = assert_declaration_refused(lambda: probe.add_command(probe_mid))
    print(f"declaration refused: {type(refused).__name__}", flush=True)
    assert refused is not None
