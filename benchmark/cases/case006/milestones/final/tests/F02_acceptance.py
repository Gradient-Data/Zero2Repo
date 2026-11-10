# feature: F02
"""Automatic help pages and eager documentation flags (FP-02).

Assertions stay at the PRD's precision: help-page content and layout
effects, eager version / custom-version, hidden names omitted but
invocable, help-option name override and conflict, and the intentional
help vs no-args-is-help exit split. Wording of usage labels, type
metavars, ellipsis characters, and default-placeholder spelling is not
pinned.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import sys
import uuid

from optlyn import (
    INT,
    STRING,
    Choice,
    Context,
    argument,
    command,
    custom_version_option,
    group,
    help_option,
    option,
    version_option,
)

from F02_helpers import (
    _help_hi,
    _help_ident,
    _help_leaf,
    _help_run,
    _run_python_on_sized_tty,
)
from _harness import workspace
from _helpers import (
    assert_eager_identity,
    assert_intentional_help,
    assert_printed_identity_is,
    assert_success_marker_present,
    assert_usage_class,
    assert_usage_help,
    assert_usage_names_option,
    description_block,
    option_help_record,
    usage_line,
    write_installed_distribution,
)


def _page(result) -> str:
    text = result.stdout_text
    if text is None:
        raise RuntimeError("help-page stdout is None; cannot observe")
    return text


def _strip_record(record: str, *pieces: str) -> str:
    text = record
    for piece in pieces:
        if piece:
            text = text.replace(piece, "")
    return text


# ---------------------------------------------------------------------------
# A. Intentional help: page, no callback, exit 0
# ---------------------------------------------------------------------------


def test_help_prints_page_without_running_callback_exits_zero():
    greeting = _help_hi()
    desc = f"Describe {uuid.uuid4().hex} path."
    prog = f"p{_help_ident()}"
    fired = []

    def callback(**kwargs) -> None:
        fired.append(True)
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    callback.__doc__ = desc
    leaf = command()(callback)

    helped = _help_run(leaf, ["--help"], prog_name=prog)
    print(
        f"help exit={helped.exit_code} stdout={helped.stdout_text!r} "
        f"stderr={helped.stderr_text!r}",
        flush=True,
    )
    assert_intentional_help(helped, greeting, desc, "Options", prog)
    assert greeting not in helped.stderr_text, (
        f"intentional help ran the callback; greeting {greeting!r} on stderr; "
        f"stderr={helped.stderr_text!r}"
    )
    usage_line(_page(helped), prog)
    assert not fired, (
        f"intentional help ran the command callback; fired={fired!r} "
        f"stdout={helped.stdout_text!r} stderr={helped.stderr_text!r}"
    )

    executed = _help_run(leaf, [], prog_name=prog)
    assert_success_marker_present(executed, greeting)
    assert fired, (
        "live baseline did not run the command callback; "
        f"stdout={executed.stdout_text!r}"
    )
    print(f"run exit={executed.exit_code} stdout={executed.stdout_text!r}", flush=True)


def test_help_eager_exits_without_required_params():
    greeting = _help_hi()
    desc = f"Needopt {uuid.uuid4().hex}."
    flag = f"--{_help_ident()}"

    def callback(needed) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    callback.__doc__ = desc
    leaf = command()(option(flag, "needed", required=True)(callback))

    helped = _help_run(leaf, ["--help"])
    print(f"help-missing exit={helped.exit_code}", flush=True)
    assert_intentional_help(helped, greeting, desc)

    missing = _help_run(leaf, [])
    print(
        f"missing exit={missing.exit_code} stdout={missing.stdout_text!r} "
        f"stderr={missing.stderr_text!r}",
        flush=True,
    )
    assert_usage_class(missing, greeting)
    assert_usage_names_option(missing, greeting, flag)


def test_help_page_contains_description_and_option_help():
    greeting = _help_hi()
    desc = f"Describe {uuid.uuid4().hex} path."
    left, right = _help_ident(), _help_ident()
    flag_a, flag_b = f"--{left}", f"--{right}"
    help_a = f"ha-{uuid.uuid4().hex}"
    help_b = f"hb-{uuid.uuid4().hex}"
    prog = f"p{_help_ident()}"

    def callback(left_dest, right_dest) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    callback.__doc__ = desc
    decorated = option(flag_b, "right_dest", help=help_b)(callback)
    decorated = option(flag_a, "left_dest", help=help_a)(decorated)
    leaf = command()(decorated)

    result = _help_run(leaf, ["--help"], prog_name=prog)
    print(f"page={result.stdout_text!r}", flush=True)
    assert_intentional_help(result, greeting, desc, "Options", prog)
    page = _page(result)
    rec_a = option_help_record(page, flag_a, flag_b, "--help")
    rec_b = option_help_record(page, flag_b, flag_a, "--help")
    assert help_a in rec_a, f"option {flag_a} record missing its help; rec={rec_a!r}"
    assert help_b not in rec_a, f"option {flag_a} record contains sibling help; rec={rec_a!r}"
    assert help_b in rec_b, f"option {flag_b} record missing its help; rec={rec_b!r}"
    assert help_a not in rec_b, f"option {flag_b} record contains sibling help; rec={rec_b!r}"
    desc_span = description_block(page, desc)
    assert help_a not in desc_span, (
        f"option help {help_a!r} leaked into the description block; "
        f"block={desc_span!r}"
    )
    assert help_b not in desc_span, (
        f"option help {help_b!r} leaked into the description block; "
        f"block={desc_span!r}"
    )


def test_group_help_does_not_run_group_callback():
    greeting = _help_hi()
    desc = f"Group {uuid.uuid4().hex}."
    child_name = f"c-{_help_ident()}"

    def root() -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = desc
    cli = group()(root)

    def child() -> None:
        print("child", flush=True)

    child.__name__ = f"{_help_ident()}_{_help_ident()}"
    cli.add_command(command(name=child_name)(child))

    live = _help_run(cli, [child_name])
    print(
        f"group-live exit={live.exit_code} stdout={live.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(live, greeting)

    result = _help_run(cli, ["--help"])
    print(f"group-help exit={result.exit_code}", flush=True)
    assert_intentional_help(result, greeting, desc)


# ---------------------------------------------------------------------------
# B. Description source, form-feed, positional section, short-help, epilog
# ---------------------------------------------------------------------------


def test_docstring_is_description_unless_explicit_help():
    greeting = _help_hi()
    doc_word = f"doc-{uuid.uuid4().hex}"
    help_word = f"hlp-{uuid.uuid4().hex}"

    from_doc = _help_leaf(greeting, doc=f"Uses {doc_word} as description.")
    doc_page = _help_run(from_doc, ["--help"])
    assert_intentional_help(doc_page, greeting, doc_word)

    def callback() -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    callback.__doc__ = f"Uses {doc_word} as description."
    explicit = command(help=f"Uses {help_word} instead.")(callback)
    help_page = _help_run(explicit, ["--help"])
    print(f"explicit page={help_page.stdout_text!r}", flush=True)
    assert_intentional_help(help_page, greeting, help_word)
    assert doc_word not in _page(help_page), (
        f"explicit help still showed docstring word {doc_word!r}; "
        f"stdout={help_page.stdout_text!r}"
    )


def test_form_feed_truncates_description_and_is_omitted():
    greeting = _help_hi()
    before = f"BF{uuid.uuid4().hex[:10]}"
    after = f"AF{uuid.uuid4().hex[:10]}"

    truncated = _help_leaf(greeting, doc=f"{before}\f{after}")
    cut = _help_run(truncated, ["--help"])
    print(f"truncated={cut.stdout_text!r}", flush=True)
    assert_intentional_help(cut, greeting, before)
    page = _page(cut)
    assert after not in page, f"text after form-feed still on page; page={page!r}"
    assert "\f" not in page, f"form-feed character appeared on the page; page={page!r}"

    live = _help_leaf(greeting, doc=f"{before}{after}")
    kept = _help_run(live, ["--help"])
    assert_intentional_help(kept, greeting, before, after)


def test_argument_help_appears_in_positional_arguments_section():
    greeting = _help_hi()
    arg_help = f"argh-{uuid.uuid4().hex}"
    dest = f"{_help_ident()}_{_help_ident()}"

    def with_help(**kwargs) -> None:
        print(greeting, flush=True)

    with_help.__name__ = f"{_help_ident()}_{_help_ident()}"
    with_help.__doc__ = f"Has {uuid.uuid4().hex}."
    has = command()(argument(dest, help=arg_help)(with_help))
    has_page = _help_run(has, ["--help"])
    print(f"with-arg-help={has_page.stdout_text!r}", flush=True)
    assert_intentional_help(has_page, greeting, "Positional arguments", arg_help)

    def without_help(**kwargs) -> None:
        print(greeting, flush=True)

    without_help.__name__ = f"{_help_ident()}_{_help_ident()}"
    without_help.__doc__ = f"Has {uuid.uuid4().hex}."
    missing = command()(argument(dest)(without_help))
    no_page = _help_run(missing, ["--help"])
    print(f"without-arg-help={no_page.stdout_text!r}", flush=True)
    assert_intentional_help(no_page, greeting)


def test_subcommand_short_help_is_first_sentence():
    greeting = _help_hi()
    head = f"Hd{uuid.uuid4().hex[:8]}"
    mid = f"Md{uuid.uuid4().hex[:8]}"
    tail = f"Tl{uuid.uuid4().hex[:8]}"
    child_name = f"c-{_help_ident()}"

    def root() -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = f"Group {uuid.uuid4().hex}."
    cli = group()(root)

    def child() -> None:
        return None

    child.__name__ = f"{_help_ident()}_{_help_ident()}"
    child.__doc__ = f"{head} {mid} is short enough. {tail} stays in the second sentence."
    cli.add_command(command(name=child_name)(child))

    result = _help_run(cli, ["--help"], terminal_width=200)
    print(f"short-help page={result.stdout_text!r}", flush=True)
    assert_intentional_help(result, greeting, child_name, head, mid)
    page = _page(result)
    listing = option_help_record(page, child_name)
    assert head in listing, (
        f"first-sentence head {head!r} missing from the child listing; "
        f"listing={listing!r}"
    )
    assert mid in listing, (
        f"first-sentence later word {mid!r} missing from the child listing; "
        f"listing={listing!r}"
    )
    assert tail not in page, (
        f"second-sentence unique word {tail!r} appeared in short help; page={page!r}"
    )


def test_long_short_help_ellipsized_to_one_line():
    greeting = _help_hi()
    head = f"Hd{uuid.uuid4().hex[:8]}"
    mid = f"Md{uuid.uuid4().hex[:8]}"
    tail = f"Tl{uuid.uuid4().hex[:8]}"
    child_name = f"c-{_help_ident()}"

    def root() -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = f"Group {uuid.uuid4().hex}."
    cli = group()(root)

    def child() -> None:
        return None

    child.__name__ = f"{_help_ident()}_{_help_ident()}"
    child.__doc__ = f"{head} {mid} " + ("xx " * 40) + tail
    cli.add_command(command(name=child_name)(child))

    fits = _help_run(cli, ["--help"], terminal_width=200)
    print(f"fits page={fits.stdout_text!r}", flush=True)
    assert_intentional_help(fits, greeting, child_name, head, mid, tail)
    fits_listing = option_help_record(_page(fits), child_name)
    assert tail in fits_listing, (
        f"over-long first-sentence tail {tail!r} missing at a width that "
        f"fits; listing={fits_listing!r}"
    )

    result = _help_run(cli, ["--help"], terminal_width=48)
    print(f"ellipsized page={result.stdout_text!r}", flush=True)
    assert_intentional_help(result, greeting, child_name, head, mid)
    page = _page(result)
    assert tail not in page, (
        f"over-budget tail word {tail!r} still listed in short help; page={page!r}"
    )


def test_explicit_short_help_overrides_first_sentence():
    greeting = _help_hi()
    short = f"sh-{uuid.uuid4().hex}"
    first = f"fs-{uuid.uuid4().hex}"
    child_name = f"c-{_help_ident()}"

    def root() -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = f"Group {uuid.uuid4().hex}."
    cli = group()(root)

    def child() -> None:
        return None

    child.__name__ = f"{_help_ident()}_{_help_ident()}"
    child.__doc__ = f"{first} is the first sentence. More follows."
    cli.add_command(command(name=child_name, short_help=short)(child))

    result = _help_run(cli, ["--help"])
    print(f"explicit-short page={result.stdout_text!r}", flush=True)
    assert_intentional_help(result, greeting, child_name, short)
    assert first not in _page(result), (
        f"docstring first-sentence word {first!r} still listed; "
        f"stdout={result.stdout_text!r}"
    )


def test_group_help_lists_children_options_and_epilog_at_end():
    greeting = _help_hi()
    desc = f"Gdesc {uuid.uuid4().hex}."
    opt_help = f"gopt-{uuid.uuid4().hex}"
    arg_help = f"garg-{uuid.uuid4().hex}"
    epilog = f"epi-{uuid.uuid4().hex}"
    child_a = f"ca-{_help_ident()}"
    child_b = f"cb-{_help_ident()}"
    flag = f"--{_help_ident()}"
    dest = f"{_help_ident()}_{_help_ident()}"

    def root(**kwargs) -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = desc
    cli = group(epilog=epilog)(option(flag, help=opt_help)(argument(dest, help=arg_help)(root)))

    def _child(name: str):
        def callback() -> None:
            return None

        callback.__name__ = f"{_help_ident()}_{_help_ident()}"
        callback.__doc__ = f"Child {name}."
        return command(name=name)(callback)

    cli.add_command(_child(child_a))
    cli.add_command(_child(child_b))

    result = _help_run(cli, ["--help"])
    page = _page(result)
    print(f"group listing page={page!r}", flush=True)
    assert_intentional_help(result, greeting, desc, opt_help, arg_help, child_a, child_b, epilog)
    epi_at = page.find(epilog)
    assert epi_at >= 0
    for earlier in (desc, opt_help, arg_help, child_a, child_b):
        pos = page.find(earlier)
        assert 0 <= pos < epi_at, (
            f"{earlier!r} is not before epilog on the help page; "
            f"pos={pos} epi={epi_at} page={page!r}"
        )


# ---------------------------------------------------------------------------
# C. Usage bracketing, metavars, wrap, backspace
# ---------------------------------------------------------------------------


def test_usage_brackets_optional_not_required_argument():
    greeting = _help_hi()
    dest = f"{_help_ident()}_{_help_ident()}"
    upper = dest.upper()
    prog = f"p{_help_ident()}"

    def required_cb(**kwargs) -> None:
        print(greeting, flush=True)

    required_cb.__name__ = f"{_help_ident()}_{_help_ident()}"
    required_cb.__doc__ = "req."
    required = command()(argument(dest, required=True)(required_cb))

    def optional_cb(**kwargs) -> None:
        print(greeting, flush=True)

    optional_cb.__name__ = f"{_help_ident()}_{_help_ident()}"
    optional_cb.__doc__ = "opt."
    optional = command()(argument(dest, required=False)(optional_cb))

    req_page = _help_run(required, ["--help"], prog_name=prog, terminal_width=120)
    opt_page = _help_run(optional, ["--help"], prog_name=prog, terminal_width=120)
    print(f"req usage={usage_line(_page(req_page), prog)!r}", flush=True)
    print(f"opt usage={usage_line(_page(opt_page), prog)!r}", flush=True)
    assert_intentional_help(req_page, greeting, upper)
    assert_intentional_help(opt_page, greeting, upper)
    req_rest = usage_line(_page(req_page), prog).replace(prog, "").replace(upper, "")
    opt_rest = usage_line(_page(opt_page), prog).replace(prog, "").replace(upper, "")
    assert req_rest != opt_rest, (
        "optional and required argument usage remainders match after "
        f"stripping prog and metavar; req={req_rest!r} opt={opt_rest!r}"
    )


def test_variadic_argument_marked_with_trailing_ellipsis():
    greeting = _help_hi()
    dest = f"{_help_ident()}_{_help_ident()}"
    upper = dest.upper()
    prog = f"p{_help_ident()}"

    def one(**kwargs) -> None:
        print(greeting, flush=True)

    one.__name__ = f"{_help_ident()}_{_help_ident()}"
    optional = command()(argument(dest, required=False)(one))

    def many(**kwargs) -> None:
        print(greeting, flush=True)

    many.__name__ = f"{_help_ident()}_{_help_ident()}"
    variadic = command()(argument(dest, nargs=-1)(many))

    opt_page = _help_run(optional, ["--help"], prog_name=prog, terminal_width=120)
    var_page = _help_run(variadic, ["--help"], prog_name=prog, terminal_width=120)
    opt_line = usage_line(_page(opt_page), prog)
    var_line = usage_line(_page(var_page), prog)
    print(f"optional={opt_line!r} variadic={var_line!r}", flush=True)
    assert_intentional_help(opt_page, greeting, upper)
    assert_intentional_help(var_page, greeting, upper)
    opt_rest = opt_line.replace(prog, "").replace(upper, "")
    var_rest = var_line.replace(prog, "").replace(upper, "")
    assert opt_rest != var_rest, (
        "variadic usage remainder matches optional-single after stripping; "
        f"optional={opt_rest!r} variadic={var_rest!r}"
    )
    idx = var_line.find(upper)
    assert idx >= 0
    trailing = var_line[idx + len(upper) :]
    opt_trailing = opt_line[opt_line.find(upper) + len(upper) :]
    assert trailing != opt_trailing, (
        "variadic mark is not after the uppercase name; "
        f"variadic trailing={trailing!r} optional trailing={opt_trailing!r}"
    )


def test_author_options_placeholder_appears_on_usage():
    greeting = _help_hi()
    word = f"PH{uuid.uuid4().hex[:8]}"
    dest = f"{_help_ident()}_{_help_ident()}"
    upper = dest.upper()
    prog = f"p{_help_ident()}"

    def overridden(**kwargs) -> None:
        print(greeting, flush=True)

    overridden.__name__ = f"{_help_ident()}_{_help_ident()}"
    over = command(options_metavar=word)(argument(dest, required=True)(overridden))
    over_page = _help_run(over, ["--help"], prog_name=prog, terminal_width=120)
    over_line = usage_line(_page(over_page), prog)
    print(f"override usage={over_line!r}", flush=True)
    assert_intentional_help(over_page, greeting, word, upper)
    assert word in over_line.split(), (
        "author options-placeholder was not used as given on the usage line "
        f"(re-wrapped in extra brackets); line={over_line!r}"
    )
    over_rest = over_line.replace(prog, "").replace(upper, "")
    assert over_rest.strip(), (
        "options placeholder left no remainder after stripping prog and "
        f"required metavar; line={over_line!r}"
    )

    def embedded(**kwargs) -> None:
        print(greeting, flush=True)

    embedded.__name__ = f"{_help_ident()}_{_help_ident()}"
    as_arg = command()(argument(dest, required=True, metavar=word)(embedded))
    arg_page = _help_run(as_arg, ["--help"], prog_name=prog, terminal_width=120)
    arg_line = usage_line(_page(arg_page), prog)
    print(f"embedded usage={arg_line!r}", flush=True)
    assert_intentional_help(arg_page, greeting, word)
    over_after_prog = over_line.replace(prog, "")
    arg_after_prog = arg_line.replace(prog, "")
    assert over_after_prog != arg_after_prog, (
        "options-placeholder usage matches required-metavar embedding; "
        f"placeholder={over_after_prog!r} embedded={arg_after_prog!r}"
    )

    def default_ph(**kwargs) -> None:
        print(greeting, flush=True)

    default_ph.__name__ = f"{_help_ident()}_{_help_ident()}"
    defaulted = command()(argument(dest, required=True)(default_ph))
    def_page = _help_run(defaulted, ["--help"], prog_name=prog, terminal_width=120)
    def_line = usage_line(_page(def_page), prog)
    def_rest = def_line.replace(prog, "").replace(upper, "")
    assert def_rest.strip(), (
        "default options placeholder left no remainder after stripping; "
        f"line={def_line!r}"
    )


def test_invoke_without_command_brackets_leading_command_token():
    greeting = _help_hi()
    child_name = f"c-{_help_ident()}"
    prog = f"p{_help_ident()}"

    def _group(*, invoke_without_command: bool):
        def root() -> None:
            print(greeting, flush=True)

        root.__name__ = f"{_help_ident()}_{_help_ident()}"
        root.__doc__ = "grp."
        cli = group(invoke_without_command=invoke_without_command)(root)

        def child() -> None:
            return None

        child.__name__ = f"{_help_ident()}_{_help_ident()}"
        cli.add_command(command(name=child_name)(child))
        return cli

    default_page = _help_run(
        _group(invoke_without_command=False),
        ["--help"],
        prog_name=prog,
        terminal_width=120,
    )
    optional_page = _help_run(
        _group(invoke_without_command=True),
        ["--help"],
        prog_name=prog,
        terminal_width=120,
    )
    default_rest = (
        usage_line(_page(default_page), prog).replace(prog, "").replace(child_name, "")
    )
    optional_rest = (
        usage_line(_page(optional_page), prog).replace(prog, "").replace(child_name, "")
    )
    print(f"default={default_rest!r} optional={optional_rest!r}", flush=True)
    assert_intentional_help(default_page, greeting)
    assert_intentional_help(optional_page, greeting)
    assert default_rest != optional_rest, (
        "invoke-without-command usage remainder matches the default group; "
        f"default={default_rest!r} optional={optional_rest!r}"
    )


def test_chaining_group_usage_marks_repeatable_command_unit():
    greeting = _help_hi()
    child_name = f"c-{_help_ident()}"
    prog = f"p{_help_ident()}"

    def _group(*, chain: bool, invoke_without_command: bool):
        def root() -> None:
            print(greeting, flush=True)

        root.__name__ = f"{_help_ident()}_{_help_ident()}"
        root.__doc__ = "grp."
        cli = group(chain=chain, invoke_without_command=invoke_without_command)(root)

        def child() -> None:
            return None

        child.__name__ = f"{_help_ident()}_{_help_ident()}"
        cli.add_command(command(name=child_name)(child))
        return cli

    default_page = _help_run(
        _group(chain=False, invoke_without_command=False),
        ["--help"],
        prog_name=prog,
        terminal_width=120,
    )
    chain_page = _help_run(
        _group(chain=True, invoke_without_command=False),
        ["--help"],
        prog_name=prog,
        terminal_width=120,
    )
    optional_page = _help_run(
        _group(chain=False, invoke_without_command=True),
        ["--help"],
        prog_name=prog,
        terminal_width=120,
    )

    def _rest(result):
        return usage_line(_page(result), prog).replace(prog, "").replace(child_name, "")

    default_rest, chain_rest, optional_rest = (
        _rest(default_page),
        _rest(chain_page),
        _rest(optional_page),
    )
    print(
        f"default={default_rest!r} chain={chain_rest!r} optional={optional_rest!r}",
        flush=True,
    )
    assert_intentional_help(default_page, greeting)
    assert_intentional_help(chain_page, greeting)
    assert_intentional_help(optional_page, greeting)
    assert chain_rest != default_rest, (
        "chaining usage remainder matches the default group; "
        f"chain={chain_rest!r} default={default_rest!r}"
    )
    assert chain_rest != optional_rest, (
        "chaining usage remainder matches invoke-without-command; "
        f"chain={chain_rest!r} optional={optional_rest!r}"
    )


def test_argument_default_metavar_is_name_uppercased():
    greeting = _help_hi()
    dest = f"{_help_ident()}_{_help_ident()}"
    upper = dest.upper()
    prog = f"p{_help_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    leaf = command()(argument(dest)(callback))
    result = _help_run(leaf, ["--help"], prog_name=prog, terminal_width=120)
    line = usage_line(_page(result), prog)
    print(f"usage={line!r} upper={upper!r}", flush=True)
    assert_intentional_help(result, greeting, upper)
    assert upper in line, f"uppercase argument name missing from usage; line={line!r}"


def test_value_option_metavar_is_type_name_not_parameter_name():
    greeting = _help_hi()
    a, b, c = _help_ident(), _help_ident(), _help_ident()
    flag_a, flag_b, flag_c = f"--{a}", f"--{b}", f"--{c}"
    ha, hb, hc = f"ha-{uuid.uuid4().hex}", f"hb-{uuid.uuid4().hex}", f"hc-{uuid.uuid4().hex}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    decorated = option(flag_c, type=STRING, help=hc)(callback)
    decorated = option(flag_b, type=INT, help=hb)(decorated)
    decorated = option(flag_a, type=INT, help=ha)(decorated)
    leaf = command()(decorated)
    result = _help_run(leaf, ["--help"])
    page = _page(result)
    print(f"metavar page={page!r}", flush=True)
    assert_intentional_help(result, greeting)
    rec_a = option_help_record(page, flag_a, flag_b, flag_c, "--help")
    rec_b = option_help_record(page, flag_b, flag_a, flag_c, "--help")
    rec_c = option_help_record(page, flag_c, flag_a, flag_b, "--help")
    rest_a = _strip_record(rec_a, flag_a, ha)
    rest_b = _strip_record(rec_b, flag_b, hb)
    rest_c = _strip_record(rec_c, flag_c, hc)
    assert rest_a == rest_b, (
        "same-type value options have different metavar remainders; "
        f"a={rest_a!r} b={rest_b!r}"
    )
    assert rest_a != rest_c, (
        "integer and string value-option remainders match; "
        f"int={rest_a!r} string={rest_c!r}"
    )
    assert a.upper() not in rest_a, (
        "value-option remainder still contains this option's uppercase name; "
        f"rest={rest_a!r}"
    )
    assert b.upper() not in rest_b, (
        "value-option remainder still contains the sibling option's uppercase name; "
        f"rest={rest_b!r}"
    )


def test_flag_and_count_options_have_no_metavar():
    greeting = _help_hi()
    val, flg, cnt = _help_ident(), _help_ident(), _help_ident()
    flag_v, flag_f, flag_c = f"--{val}", f"--{flg}", f"--{cnt}"
    hv, hf, hc = f"hv-{uuid.uuid4().hex}", f"hf-{uuid.uuid4().hex}", f"hc-{uuid.uuid4().hex}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    decorated = option(flag_c, count=True, help=hc)(callback)
    decorated = option(flag_f, is_flag=True, help=hf)(decorated)
    decorated = option(flag_v, type=INT, help=hv)(decorated)
    leaf = command()(decorated)
    result = _help_run(leaf, ["--help"])
    page = _page(result)
    print(f"flag/count page={page!r}", flush=True)
    assert_intentional_help(result, greeting)
    val_rest = _strip_record(
        option_help_record(page, flag_v, flag_f, flag_c, "--help"), flag_v, hv
    )
    flg_rest = _strip_record(
        option_help_record(page, flag_f, flag_v, flag_c, "--help"), flag_f, hf
    )
    cnt_rest = _strip_record(
        option_help_record(page, flag_c, flag_v, flag_f, "--help"), flag_c, hc
    )
    assert val_rest.strip(), f"value option remainder has no metavar; rest={val_rest!r}"
    assert len(flg_rest.strip()) < len(val_rest.strip()), (
        "flag remainder is not emptier than the value-option remainder; "
        f"flag={flg_rest!r} value={val_rest!r}"
    )
    assert len(cnt_rest.strip()) < len(val_rest.strip()), (
        "count remainder is not emptier than the value-option remainder; "
        f"count={cnt_rest!r} value={val_rest!r}"
    )


def test_choice_type_supplies_own_metavar_placeholder():
    greeting = _help_hi()
    public = f"--{_help_ident()}"
    help_s = f"ch-{uuid.uuid4().hex}"
    left, right = f"ca{uuid.uuid4().hex[:6]}", f"cb{uuid.uuid4().hex[:6]}"

    def _typed(typ):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)

        callback.__name__ = f"{_help_ident()}_{_help_ident()}"
        return command()(option(public, type=typ, help=help_s)(callback))

    choice_page = _help_run(_typed(Choice([left, right])), ["--help"])
    string_page = _help_run(_typed(STRING), ["--help"])
    int_page = _help_run(_typed(INT), ["--help"])
    print(f"choice page={choice_page.stdout_text!r}", flush=True)
    assert_intentional_help(choice_page, greeting)
    assert_intentional_help(string_page, greeting)
    assert_intentional_help(int_page, greeting)

    def _rest(result):
        rec = option_help_record(_page(result), public, "--help")
        return _strip_record(rec, public, help_s)

    choice_rest, string_rest, int_rest = (
        _rest(choice_page),
        _rest(string_page),
        _rest(int_page),
    )
    assert choice_rest != string_rest, (
        "choice metavar remainder matches the string twin; "
        f"choice={choice_rest!r} string={string_rest!r}"
    )
    assert choice_rest != int_rest, (
        "choice metavar remainder matches the integer twin; "
        f"choice={choice_rest!r} int={int_rest!r}"
    )


def test_author_metavar_override_appears():
    greeting = _help_hi()
    word = f"MV{uuid.uuid4().hex[:8]}"
    flag = f"--{_help_ident()}"
    dest = f"{_help_ident()}_{_help_ident()}"
    prog = f"p{_help_ident()}"

    def opt_cb(**kwargs) -> None:
        print(greeting, flush=True)

    opt_cb.__name__ = f"{_help_ident()}_{_help_ident()}"
    as_opt = command()(option(flag, metavar=word)(opt_cb))
    opt_page = _help_run(as_opt, ["--help"], prog_name=prog)
    print(f"opt metavar page={opt_page.stdout_text!r}", flush=True)
    assert_intentional_help(opt_page, greeting, word)

    def arg_cb(**kwargs) -> None:
        print(greeting, flush=True)

    arg_cb.__name__ = f"{_help_ident()}_{_help_ident()}"
    as_arg = command()(argument(dest, metavar=word)(arg_cb))
    arg_page = _help_run(as_arg, ["--help"], prog_name=prog, terminal_width=120)
    assert_intentional_help(arg_page, greeting, word)
    assert word in usage_line(_page(arg_page), prog)


def test_help_rewrapped_to_width_capped_at_default_80():
    greeting = _help_hi()
    head = f"HD{uuid.uuid4().hex[:8]}"
    tail = f"TL{uuid.uuid4().hex[:8]}"
    filler = " ".join(["zz"] * 90)
    doc = f"{head} {filler} {tail}"

    leaf = _help_leaf(greeting, doc=doc)
    # Narrower-vs-default rewrap: an explicit narrower width versus the
    # same command with no width supplied.
    # The default-80 maximum content width caps auto-detected width only
    # (the omitted-width arm). Both explicit-width arms share one
    # caller-supplied terminal width; that width is the wrap width
    # as-is, with or without a raised cap.
    wide = 200
    narrow = _help_run(leaf, ["--help"], terminal_width=40)
    defaulted = _help_run(leaf, ["--help"])
    explicit = _help_run(leaf, ["--help"], terminal_width=wide)
    explicit_raised = _help_run(
        leaf, ["--help"], terminal_width=wide, max_content_width=wide
    )

    def _omitted_width_on_detected_terminal(*, max_content_width: int | None):
        max_expr = "None" if max_content_width is None else repr(max_content_width)
        code = (
            "from optlyn import command\n"
            f"GREET = {greeting!r}\n"
            f"DOC = {doc!r}\n"
            "def callback():\n"
            "    print(GREET, flush=True)\n"
            "callback.__doc__ = DOC\n"
            "leaf = command()(callback)\n"
            "leaf.main(args=['--help'], standalone_mode=True, "
            f"prog_name='app', max_content_width={max_expr})\n"
        )
        return _run_python_on_sized_tty(code, wide)

    omitted_capped = _omitted_width_on_detected_terminal(max_content_width=None)
    omitted_raised = _omitted_width_on_detected_terminal(max_content_width=wide)
    print(
        f"narrow={description_block(_page(narrow), head, tail)!r}",
        flush=True,
    )
    print(
        f"defaulted={description_block(_page(defaulted), head, tail)!r}",
        flush=True,
    )
    print(
        f"explicit={description_block(_page(explicit), head, tail)!r}",
        flush=True,
    )
    print(
        f"explicit_raised={description_block(_page(explicit_raised), head, tail)!r}",
        flush=True,
    )
    print(
        f"omitted_capped={description_block(_page(omitted_capped), head, tail)!r}",
        flush=True,
    )
    print(
        f"omitted_raised={description_block(_page(omitted_raised), head, tail)!r}",
        flush=True,
    )
    assert_intentional_help(narrow, greeting, head, tail)
    assert_intentional_help(defaulted, greeting, head, tail)
    assert_intentional_help(explicit, greeting, head, tail)
    assert_intentional_help(explicit_raised, greeting, head, tail)
    assert_intentional_help(omitted_capped, greeting, head, tail)
    assert_intentional_help(omitted_raised, greeting, head, tail)

    def _lines(result):
        return [
            line.replace("\r", "")
            for line in description_block(_page(result), head, tail).splitlines()
        ]

    narrow_lines = _lines(narrow)
    defaulted_lines = _lines(defaulted)
    explicit_lines = _lines(explicit)
    explicit_raised_lines = _lines(explicit_raised)
    omitted_capped_lines = _lines(omitted_capped)
    omitted_raised_lines = _lines(omitted_raised)
    narrow_max = max(len(line) for line in narrow_lines)
    defaulted_max = max(len(line) for line in defaulted_lines)
    explicit_max = max(len(line) for line in explicit_lines)
    explicit_raised_max = max(len(line) for line in explicit_raised_lines)
    omitted_capped_max = max(len(line) for line in omitted_capped_lines)
    omitted_raised_max = max(len(line) for line in omitted_raised_lines)
    assert narrow_max < defaulted_max, (
        "narrow width did not produce shorter description lines; "
        f"narrow_max={narrow_max} defaulted_max={defaulted_max}"
    )
    assert len(defaulted_lines) > 1, (
        "omitted-width run did not wrap the long description; "
        f"defaulted_lines={defaulted_lines!r}"
    )
    assert defaulted_max <= 80, (
        "omitted-width auto-detected wrap exceeded the default "
        "maximum content width of 80; "
        f"defaulted_max={defaulted_max} lines={defaulted_lines!r}"
    )
    assert len(explicit_lines) > 1, (
        "explicit terminal width did not wrap the long description; "
        f"explicit_lines={explicit_lines!r}"
    )
    assert explicit_max > 80, (
        "explicit terminal width was still bounded by the default "
        "80-column cap; "
        f"explicit_max={explicit_max} lines={explicit_lines!r}"
    )
    assert explicit_max <= wide, (
        "explicit terminal width did not bound description lines "
        f"at the supplied width {wide}; "
        f"explicit_max={explicit_max} lines={explicit_lines!r}"
    )
    assert len(explicit_raised_lines) > 1, (
        "explicit terminal width with a raised cap did not wrap "
        "the long description; "
        f"explicit_raised_lines={explicit_raised_lines!r}"
    )
    assert explicit_raised_max > 80, (
        "explicit terminal width with a raised cap was still bounded "
        "by the default 80-column cap; "
        f"explicit_raised_max={explicit_raised_max} "
        f"lines={explicit_raised_lines!r}"
    )
    assert explicit_raised_max <= wide, (
        "explicit terminal width with a raised cap did not bound "
        f"description lines at the supplied width {wide}; "
        f"explicit_raised_max={explicit_raised_max} "
        f"lines={explicit_raised_lines!r}"
    )
    assert len(omitted_capped_lines) > 1, (
        "omitted-width auto-detected wrap under the default cap "
        "did not wrap the long description; "
        f"omitted_capped_lines={omitted_capped_lines!r}"
    )
    assert omitted_capped_max <= 80, (
        "omitted-width auto-detected wrap under the default cap "
        "exceeded 80 columns; "
        f"omitted_capped_max={omitted_capped_max} "
        f"lines={omitted_capped_lines!r}"
    )
    assert omitted_raised_max > omitted_capped_max, (
        "raising the maximum content width did not lengthen "
        "omitted-width auto-detected lines; "
        f"omitted_capped_max={omitted_capped_max} "
        f"omitted_raised_max={omitted_raised_max} "
        f"capped={omitted_capped_lines!r} raised={omitted_raised_lines!r}"
    )
    assert omitted_raised_max > 80, (
        "raising the maximum content width did not let omitted-width "
        "auto-detected wrap exceed the default 80-column cap; "
        f"omitted_raised_max={omitted_raised_max} "
        f"lines={omitted_raised_lines!r}"
    )


def test_single_newlines_in_paragraph_are_not_hard_breaks():
    greeting = _help_hi()
    w1, w2 = f"N1{uuid.uuid4().hex[:8]}", f"N2{uuid.uuid4().hex[:8]}"

    joined = _help_leaf(greeting, doc=f"{w1}\n{w2} stay together.")
    joined_page = _help_run(joined, ["--help"], terminal_width=200)
    print(f"joined={joined_page.stdout_text!r}", flush=True)
    assert_intentional_help(joined_page, greeting, w1, w2)
    block = description_block(_page(joined_page), w1, w2)
    same_line = any(w1 in line and w2 in line for line in block.splitlines())
    assert same_line, (
        f"{w1!r} and {w2!r} were not on one rendered line; block={block!r}"
    )

    broken = _help_leaf(greeting, doc=f"lead {uuid.uuid4().hex}\n\n\b\n{w1}\n{w2}\n")
    broken_page = _help_run(broken, ["--help"], terminal_width=200)
    print(f"broken={broken_page.stdout_text!r}", flush=True)
    assert_intentional_help(broken_page, greeting, w1, w2)
    bblock = description_block(_page(broken_page), w1, w2)
    still_split = any(w1 in line and w2 in line for line in bblock.splitlines())
    assert not still_split, (
        "backspace paragraph still joined the two words onto one line; "
        f"block={bblock!r}"
    )


def test_backspace_paragraph_keeps_breaks_and_strips_marker():
    greeting = _help_hi()
    rows = [f"R{i}{uuid.uuid4().hex[:6]}" for i in range(3)]
    lead = f"LD{uuid.uuid4().hex[:8]}"

    raw = _help_leaf(greeting, doc=f"{lead}\n\n\b\n" + "\n".join(rows) + "\n")
    raw_page = _help_run(raw, ["--help"], terminal_width=200)
    print(f"backspace page={raw_page.stdout_text!r}", flush=True)
    assert_intentional_help(raw_page, greeting, lead, *rows)
    page = _page(raw_page)
    assert "\b" not in page, f"backspace marker still on the page; page={page!r}"
    block = description_block(page, *rows)
    for token in rows:
        own = [line for line in block.splitlines() if token in line]
        assert own, f"{token!r} missing from backspace block; block={block!r}"
        others = [t for t in rows if t != token]
        assert all(o not in own[0] for o in others), (
            f"{token!r} shares a line with another backspace row; line={own[0]!r}"
        )

    wrapped = _help_leaf(greeting, doc=f"{lead} " + " ".join(rows))
    wrap_page = _help_run(wrapped, ["--help"], terminal_width=200)
    assert_intentional_help(wrap_page, greeting, lead, *rows)
    wrap_block = description_block(_page(wrap_page), *rows)
    wrap_lines = wrap_block.splitlines()
    raw_lines = [line for line in block.splitlines() if any(t in line for t in rows)]
    assert len(wrap_lines) < len(raw_lines) or (
        any(sum(t in line for t in rows) > 1 for line in wrap_lines)
    ), (
        "without backspace the same words were not joined into fewer lines; "
        f"wrap={wrap_lines!r} raw={raw_lines!r}"
    )


# ---------------------------------------------------------------------------
# D. Show-default and environment variable name
# ---------------------------------------------------------------------------


def test_show_default_per_parameter_and_via_context():
    greeting = _help_hi()
    flag = f"--{_help_ident()}"
    default = f"dv-{uuid.uuid4().hex}"
    help_s = f"hs-{uuid.uuid4().hex}"

    def _make(*, show_default=None):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)

        callback.__name__ = f"{_help_ident()}_{_help_ident()}"
        kwargs = {}
        if show_default is not None:
            kwargs["show_default"] = show_default
        return command()(
            option(flag, default=default, help=help_s, **kwargs)(callback)
        )

    hidden = _help_run(_make(), ["--help"], terminal_width=200)
    shown = _help_run(_make(show_default=True), ["--help"], terminal_width=200)
    via_ctx = _help_run(_make(), ["--help"], show_default=True, terminal_width=200)
    print(
        f"hidden={hidden.stdout_text!r} shown={shown.stdout_text!r} "
        f"ctx={via_ctx.stdout_text!r}",
        flush=True,
    )
    assert_intentional_help(hidden, greeting, help_s)
    assert_intentional_help(shown, greeting, help_s, default)
    assert_intentional_help(via_ctx, greeting, help_s, default)
    hidden_rest = _strip_record(
        option_help_record(_page(hidden), flag, "--help"), flag, help_s
    )
    assert default not in hidden_rest, (
        f"default {default!r} shown without show-default; rest={hidden_rest!r}"
    )


def test_custom_default_description_replaces_raw_default():
    greeting = _help_hi()
    flag = f"--{_help_ident()}"
    raw = f"raw-{uuid.uuid4().hex}"
    custom = f"cus-{uuid.uuid4().hex}"
    help_s = f"hs-{uuid.uuid4().hex}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    leaf = command()(
        option(flag, default=raw, show_default=custom, help=help_s)(callback)
    )
    result = _help_run(leaf, ["--help"], terminal_width=200)
    print(f"custom-default page={result.stdout_text!r}", flush=True)
    assert_intentional_help(result, greeting, custom)
    rec = option_help_record(_page(result), flag, "--help")
    assert raw not in rec, (
        f"raw default {raw!r} still on the option record; rec={rec!r}"
    )


def test_off_boolean_flag_default_stays_hidden():
    greeting = _help_hi()
    flag = f"--{_help_ident()}"
    help_s = f"hs-{uuid.uuid4().hex}"
    default_s = f"dv-{uuid.uuid4().hex}"

    def _flag(*, default: bool, show_default: bool):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)

        callback.__name__ = f"{_help_ident()}_{_help_ident()}"
        return command()(
            option(flag, is_flag=True, default=default, show_default=show_default, help=help_s)(
                callback
            )
        )

    def _value(*, show_default: bool):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)

        callback.__name__ = f"{_help_ident()}_{_help_ident()}"
        return command()(
            option(flag, default=default_s, show_default=show_default, help=help_s)(
                callback
            )
        )

    def _rest(result):
        return _strip_record(
            option_help_record(_page(result), flag, "--help"), flag, help_s
        )

    off_hide = _help_run(
        _flag(default=False, show_default=False), ["--help"], terminal_width=200
    )
    off_show = _help_run(
        _flag(default=False, show_default=True), ["--help"], terminal_width=200
    )
    on_hide = _help_run(
        _flag(default=True, show_default=False), ["--help"], terminal_width=200
    )
    on_show = _help_run(
        _flag(default=True, show_default=True), ["--help"], terminal_width=200
    )
    val_hide = _help_run(_value(show_default=False), ["--help"], terminal_width=200)
    val_show = _help_run(_value(show_default=True), ["--help"], terminal_width=200)
    print(
        f"off-hide={_rest(off_hide)!r} off-show={_rest(off_show)!r} "
        f"on-hide={_rest(on_hide)!r} on-show={_rest(on_show)!r}",
        flush=True,
    )
    assert_intentional_help(off_hide, greeting, help_s)
    assert_intentional_help(off_show, greeting, help_s)
    assert_intentional_help(on_hide, greeting, help_s)
    assert_intentional_help(on_show, greeting, help_s)
    assert_intentional_help(val_hide, greeting, help_s)
    assert_intentional_help(val_show, greeting, help_s, default_s)
    assert default_s not in _rest(val_hide)
    assert _rest(off_hide) == _rest(on_hide), (
        "off and on flags differ while show-default is off; "
        f"off={_rest(off_hide)!r} on={_rest(on_hide)!r}"
    )
    assert _rest(off_show) == _rest(off_hide), (
        "show-default revealed the off boolean default; "
        f"show={_rest(off_show)!r} hide={_rest(off_hide)!r}"
    )
    assert _rest(on_show) != _rest(on_hide), (
        "show-default did not reveal the on boolean default; "
        f"show={_rest(on_show)!r} hide={_rest(on_hide)!r}"
    )


def test_show_environment_variable_name_appears():
    greeting = _help_hi()
    flag = f"--{_help_ident()}"
    env_name = f"EV_{uuid.uuid4().hex[:10].upper()}"
    help_s = f"hs-{uuid.uuid4().hex}"

    def _make(*, show_envvar: bool):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)

        callback.__name__ = f"{_help_ident()}_{_help_ident()}"
        return command()(
            option(flag, envvar=env_name, show_envvar=show_envvar, help=help_s)(
                callback
            )
        )

    shown = _help_run(_make(show_envvar=True), ["--help"])
    hidden = _help_run(_make(show_envvar=False), ["--help"])
    print(f"env shown={shown.stdout_text!r} hidden={hidden.stdout_text!r}", flush=True)
    assert_intentional_help(shown, greeting, env_name)
    assert_intentional_help(hidden, greeting, help_s)
    shown_rec = option_help_record(_page(shown), flag, "--help")
    hidden_rec = option_help_record(_page(hidden), flag, "--help")
    assert env_name in shown_rec, (
        f"environment name {env_name!r} missing from the option record; "
        f"rec={shown_rec!r}"
    )
    assert env_name not in hidden_rec, (
        f"environment name {env_name!r} appeared on the hidden-switch record; "
        f"rec={hidden_rec!r}"
    )
    shown_rest = _strip_record(shown_rec, flag, help_s)
    hidden_rest = _strip_record(hidden_rec, flag, help_s)
    assert shown_rest != hidden_rest, (
        "show-environment-variable left no distinct mark after stripping "
        f"the option name and help; shown={shown_rest!r} hidden={hidden_rest!r}"
    )


# ---------------------------------------------------------------------------
# E. Hidden options / commands / groups
# ---------------------------------------------------------------------------


def test_hidden_option_omitted_from_help_but_accepted():
    greeting = _help_hi()
    flag = f"--{_help_ident()}"
    help_s = f"hs-{uuid.uuid4().hex}"
    value = f"hv-{uuid.uuid4().hex}"

    def _make(*, hidden: bool):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)
            received = next(iter(kwargs.values()))
            if received is not None:
                print(received, flush=True)

        callback.__name__ = f"{_help_ident()}_{_help_ident()}"
        return command()(option(flag, hidden=hidden, help=help_s)(callback))

    hidden = _make(hidden=True)
    visible = _make(hidden=False)
    hidden_help = _help_run(hidden, ["--help"])
    visible_help = _help_run(visible, ["--help"])
    print(f"hidden help={hidden_help.stdout_text!r}", flush=True)
    assert_intentional_help(hidden_help, greeting)
    assert flag not in _page(hidden_help), (
        f"hidden option {flag!r} still on the help page; "
        f"stdout={hidden_help.stdout_text!r}"
    )
    assert_intentional_help(visible_help, greeting, flag, help_s)

    typed = _help_run(hidden, [flag, value])
    print(f"typed={typed.stdout_text!r}", flush=True)
    assert_success_marker_present(typed, greeting)
    assert value in typed.stdout_text, (
        f"typed hidden option value {value!r} did not reach the callback; "
        f"stdout={typed.stdout_text!r}"
    )
    omitted = _help_run(hidden, [])
    assert_success_marker_present(omitted, greeting)
    assert value not in omitted.stdout_text, (
        f"omitted hidden option still produced {value!r}; "
        f"stdout={omitted.stdout_text!r}"
    )


def test_hidden_command_omitted_from_group_help_but_invocable():
    greeting = _help_hi()
    child_g = _help_hi()
    child_name = f"c-{_help_ident()}"
    sibling_name = f"s-{_help_ident()}"
    desc = f"Gdesc {uuid.uuid4().hex}."

    def root() -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = desc
    cli = group()(root)

    def child() -> None:
        print(child_g, flush=True)

    child.__name__ = f"{_help_ident()}_{_help_ident()}"
    cli.add_command(command(name=child_name, hidden=True)(child))

    def sibling() -> None:
        return None

    sibling.__name__ = f"{_help_ident()}_{_help_ident()}"
    cli.add_command(command(name=sibling_name)(sibling))

    helped = _help_run(cli, ["--help"])
    print(f"hidden-cmd help={helped.stdout_text!r}", flush=True)
    assert_intentional_help(helped, greeting, desc, sibling_name)
    assert child_name not in _page(helped), (
        f"hidden command {child_name!r} listed on group help; "
        f"stdout={helped.stdout_text!r}"
    )
    ran = _help_run(cli, [child_name])
    assert_success_marker_present(ran, child_g)


def test_hidden_group_omitted_from_parent_help_but_invocable():
    greeting = _help_hi()
    leaf_g = _help_hi()
    hidden_name = f"hg-{_help_ident()}"
    visible_name = f"vg-{_help_ident()}"
    leaf_name = f"lf-{_help_ident()}"
    desc = f"Parent {uuid.uuid4().hex}."

    def root() -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = desc
    cli = group()(root)

    def hidden_root() -> None:
        return None

    hidden_root.__name__ = f"{_help_ident()}_{_help_ident()}"
    hidden_grp = group(name=hidden_name, hidden=True)(hidden_root)

    def leaf() -> None:
        print(leaf_g, flush=True)

    leaf.__name__ = f"{_help_ident()}_{_help_ident()}"
    hidden_grp.add_command(command(name=leaf_name)(leaf))
    cli.add_command(hidden_grp)

    def visible_root() -> None:
        return None

    visible_root.__name__ = f"{_help_ident()}_{_help_ident()}"
    visible_grp = group(name=visible_name)(visible_root)

    def visible_leaf() -> None:
        return None

    visible_leaf.__name__ = f"{_help_ident()}_{_help_ident()}"
    visible_grp.add_command(command(name=f"vl-{_help_ident()}")(visible_leaf))
    cli.add_command(visible_grp)

    helped = _help_run(cli, ["--help"])
    print(f"hidden-group help={helped.stdout_text!r}", flush=True)
    assert_intentional_help(helped, greeting, desc, visible_name)
    assert hidden_name not in _page(helped), (
        f"hidden group {hidden_name!r} listed on parent help; "
        f"stdout={helped.stdout_text!r}"
    )
    ran = _help_run(cli, [hidden_name, leaf_name])
    assert_success_marker_present(ran, leaf_g)


# ---------------------------------------------------------------------------
# F. Help-option names, conflict, extra help option, disable automatic help
# ---------------------------------------------------------------------------


def test_context_replaces_help_option_names():
    greeting = _help_hi()
    desc = f"Describe {uuid.uuid4().hex} path."
    custom = f"--{_help_ident()}"
    leaf = _help_leaf(greeting, doc=desc)
    helped = _help_run(leaf, [custom], help_option_names=[custom])
    print(f"custom help={helped.stdout_text!r}", flush=True)
    assert_intentional_help(helped, greeting, desc)

    default = _help_run(leaf, ["--help"], help_option_names=[custom])
    print(f"stale --help exit={default.exit_code}", flush=True)
    assert_usage_class(default, greeting)
    assert desc not in default.stdout_text + default.stderr_text, (
        "replaced help names still treated --help as successful help; "
        f"stdout={default.stdout_text!r} stderr={default.stderr_text!r}"
    )


def test_author_option_wins_only_when_every_help_name_reused():
    greeting = _help_hi()
    desc = f"Describe {uuid.uuid4().hex} path."
    mark = f"AUTH-{uuid.uuid4().hex}"
    names = ["--help", "-h"]

    def partial_cb(help: bool = False) -> None:
        print(greeting, flush=True)
        if help:
            print(mark, flush=True)

    partial_cb.__name__ = f"{_help_ident()}_{_help_ident()}"
    partial_cb.__doc__ = desc
    partial = command()(option("--help", is_flag=True)(partial_cb))

    dash_h = _help_run(partial, ["-h"], help_option_names=names)
    print(f"partial -h={dash_h.stdout_text!r}", flush=True)
    assert_intentional_help(dash_h, greeting, desc)

    overlap = _help_run(partial, ["--help"], help_option_names=names)
    print(f"partial --help={overlap.stdout_text!r}", flush=True)
    assert_success_marker_present(overlap, greeting)
    assert mark in overlap.stdout_text, (
        "overlapping help-option name did not run the author's option; "
        f"stdout={overlap.stdout_text!r}"
    )
    assert overlap.exit_code == 0

    def full_cb(help: bool = False) -> None:
        print(greeting, flush=True)
        if help:
            print(mark, flush=True)

    full_cb.__name__ = f"{_help_ident()}_{_help_ident()}"
    full_cb.__doc__ = desc
    full = command()(option("--help", "-h", is_flag=True)(full_cb))
    for token in names:
        result = _help_run(full, [token], help_option_names=names)
        print(f"full {token}={result.stdout_text!r}", flush=True)
        assert_success_marker_present(result, greeting)
        assert mark in result.stdout_text, (
            f"occupied name {token!r} did not produce the author mark; "
            f"stdout={result.stdout_text!r}"
        )
        assert result.exit_code == 0


def test_parameter_named_help_does_not_disable_automatic_help():
    greeting = _help_hi()
    desc = f"Describe {uuid.uuid4().hex} path."
    value = f"hv-{uuid.uuid4().hex}"

    def callback(help) -> None:
        print(greeting, flush=True)
        print(help, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    callback.__doc__ = desc
    leaf = command()(argument("help")(callback))

    helped = _help_run(leaf, ["--help"])
    print(f"named-help --help={helped.stdout_text!r}", flush=True)
    assert_intentional_help(helped, greeting, desc, "Options")
    assert value not in helped.stdout_text, (
        f"intentional help echoed the unused positional token {value!r}; "
        f"stdout={helped.stdout_text!r}"
    )

    ran = _help_run(leaf, [value])
    assert_success_marker_present(ran, greeting)
    assert value in ran.stdout_text, (
        f"positional help value {value!r} did not reach the callback; "
        f"stdout={ran.stdout_text!r}"
    )
    assert desc not in ran.stdout_text, (
        f"positional help run printed the help-page description {desc!r}; "
        f"stdout={ran.stdout_text!r}"
    )


def test_extra_help_option_prints_help_and_exits():
    greeting = _help_hi()
    desc = f"Describe {uuid.uuid4().hex} path."
    extra = f"--{_help_ident()}"

    def callback() -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    callback.__doc__ = desc
    leaf = command()(help_option(extra)(callback))

    for token in (extra, "--help"):
        result = _help_run(leaf, [token])
        print(f"extra {token}={result.stdout_text!r}", flush=True)
        assert_intentional_help(result, greeting, desc)


def test_disabled_automatic_help_makes_help_unknown_unless_declared():
    greeting = _help_hi()
    desc = f"Describe {uuid.uuid4().hex} path."

    enabled = _help_leaf(greeting, doc=desc)
    enabled_help = _help_run(enabled, ["--help"])
    assert_intentional_help(enabled_help, greeting, desc)

    disabled = _help_leaf(greeting, doc=desc, add_help_option=False)
    unknown = _help_run(disabled, ["--help"])
    print(
        f"disabled --help exit={unknown.exit_code} "
        f"stdout={unknown.stdout_text!r} stderr={unknown.stderr_text!r}",
        flush=True,
    )
    assert_usage_class(unknown, greeting)
    visible = unknown.stdout_text + unknown.stderr_text
    assert desc not in visible, (
        "disabled automatic help still printed the description page for --help; "
        f"visible={visible!r}"
    )

    def declared_cb() -> None:
        print(greeting, flush=True)

    declared_cb.__name__ = f"{_help_ident()}_{_help_ident()}"
    declared_cb.__doc__ = desc
    declared = command(add_help_option=False)(help_option("--help")(declared_cb))
    declared_help = _help_run(declared, ["--help"])
    assert_intentional_help(declared_help, greeting, desc)

    def root() -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = desc
    grp = group()(root)

    def child() -> None:
        return None

    child.__name__ = f"{_help_ident()}_{_help_ident()}"
    grp.add_command(command()(child))
    missing = _help_run(grp, [])
    assert_usage_help(missing, greeting, desc)
    assert visible != missing.stdout_text + missing.stderr_text, (
        "disabled --help is indistinguishable from missing-subcommand help; "
        f"unknown={visible!r} missing={missing.stdout_text + missing.stderr_text!r}"
    )


# ---------------------------------------------------------------------------
# G. Eager version, package detection, custom-version, first-eager-wins
# ---------------------------------------------------------------------------


def test_version_option_eager_exits_without_required_params():
    greeting = _help_hi()
    identity = f"ver-{uuid.uuid4().hex}"
    flag = f"--{_help_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    leaf = command()(
        option(flag, required=True)(version_option(identity)(callback))
    )

    missing = _help_run(leaf, ["--version"])
    print(f"version-missing={missing.stdout_text!r}", flush=True)
    assert_eager_identity(missing, greeting, identity)

    supplied = _help_run(leaf, ["--version", flag, "x"])
    print(f"version-supplied={supplied.stdout_text!r}", flush=True)
    assert_eager_identity(supplied, greeting, identity)

    usage = _help_run(leaf, [])
    print(
        f"usage exit={usage.exit_code} stdout={usage.stdout_text!r} "
        f"stderr={usage.stderr_text!r}",
        flush=True,
    )
    assert_usage_class(usage, greeting)
    assert_usage_names_option(usage, greeting, flag)
    assert identity not in usage.stdout_text + usage.stderr_text, (
        f"missing required option still printed version {identity!r}; "
        f"stdout={usage.stdout_text!r} stderr={usage.stderr_text!r}"
    )


def test_version_detects_installed_distribution():
    greeting = _help_hi()
    dist_a = f"zxqdist{uuid.uuid4().hex[:8]}"
    dist_b = f"zxqdist{uuid.uuid4().hex[:8]}"
    ver_a = f"3.{uuid.uuid4().int % 50}.{uuid.uuid4().int % 50}"
    ver_b = f"8.{uuid.uuid4().int % 50}.{uuid.uuid4().int % 50}"
    mod_a = f"zxqmod{uuid.uuid4().hex[:8]}"
    mod_b = f"zxqmod{uuid.uuid4().hex[:8]}"
    mod_ver = f"0.0.{uuid.uuid4().int % 90}-mod"
    assert ver_a != ver_b and mod_ver not in (ver_a, ver_b)

    def callback() -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    leaf = command()(version_option(package_name=dist_a)(callback))

    with workspace() as ws:
        write_installed_distribution(ws.path, dist_a, ver_a, [mod_a])
        write_installed_distribution(ws.path, dist_b, ver_b, [mod_b])
        (ws.path / mod_a).mkdir()
        (ws.path / mod_a / "__init__.py").write_text(
            f'__version__ = "{mod_ver}"\n', encoding="utf-8"
        )
        inserted = str(ws.path)
        sys.path.insert(0, inserted)
        try:
            importlib.invalidate_caches()
            found = importlib.metadata.version(dist_a)
            if found != ver_a:
                raise RuntimeError(
                    f"fixture distribution {dist_a!r} not visible; "
                    f"got {found!r} expected {ver_a!r}"
                )
            other = importlib.metadata.version(dist_b)
            if other != ver_b:
                raise RuntimeError(
                    f"second fixture distribution {dist_b!r} not visible; "
                    f"got {other!r} expected {ver_b!r}"
                )
            loaded = importlib.import_module(mod_a)
            if loaded.__version__ != mod_ver:
                raise RuntimeError(
                    f"fixture module __version__ is {loaded.__version__!r}, "
                    f"not {mod_ver!r}"
                )
            result = _help_run(leaf, ["--version"])
        finally:
            sys.modules.pop(mod_a, None)
            if inserted in sys.path:
                sys.path.remove(inserted)

    print(f"detected={result.stdout_text!r}", flush=True)
    assert_eager_identity(result, greeting, ver_a)
    assert ver_b not in result.stdout_text, (
        f"detected the other distribution version {ver_b!r}; "
        f"stdout={result.stdout_text!r}"
    )
    assert mod_ver not in result.stdout_text, (
        f"detected module __version__ {mod_ver!r} instead of dist metadata; "
        f"stdout={result.stdout_text!r}"
    )


def test_version_resolves_import_name_to_distribution():
    greeting = _help_hi()
    dist_a = f"zxqdist{uuid.uuid4().hex[:8]}"
    dist_b = f"zxqdist{uuid.uuid4().hex[:8]}"
    ver_a = f"4.{uuid.uuid4().int % 50}.{uuid.uuid4().int % 50}"
    ver_b = f"7.{uuid.uuid4().int % 50}.{uuid.uuid4().int % 50}"
    import_a = f"zxqimp{uuid.uuid4().hex[:8]}"
    import_b = f"zxqimp{uuid.uuid4().hex[:8]}"
    assert import_a != dist_a

    def callback() -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    leaf = command()(version_option(package_name=import_a)(callback))

    with workspace() as ws:
        write_installed_distribution(ws.path, dist_a, ver_a, [import_a])
        write_installed_distribution(ws.path, dist_b, ver_b, [import_b])
        inserted = str(ws.path)
        sys.path.insert(0, inserted)
        try:
            importlib.invalidate_caches()
            mapping = importlib.metadata.packages_distributions()
            mapped = mapping.get(import_a, [])
            if dist_a not in mapped:
                raise RuntimeError(
                    f"import name {import_a!r} did not map to {dist_a!r}; "
                    f"got {mapped!r}"
                )
            result = _help_run(leaf, ["--version"])
        finally:
            if inserted in sys.path:
                sys.path.remove(inserted)

    print(f"resolved={result.stdout_text!r}", flush=True)
    assert_eager_identity(result, greeting, ver_a)
    assert ver_b not in result.stdout_text, (
        f"resolved the other distribution version {ver_b!r}; "
        f"stdout={result.stdout_text!r}"
    )


def test_custom_version_prints_callback_string_not_template():
    greeting = _help_hi()
    unique = f"cver-{uuid.uuid4().hex}"
    prog = f"p{_help_ident()}"
    flag = f"--{_help_ident()}"
    received: list[object] = []

    def identity(ctx: Context) -> str:
        received.append(ctx)
        return unique

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    custom = command()(
        option(flag, required=True)(custom_version_option(identity)(callback))
    )
    result = _help_run(custom, ["--version"], prog_name=prog)
    print(f"custom-version={result.stdout_text!r}", flush=True)
    assert_printed_identity_is(result, greeting, unique)
    assert received, (
        f"custom-version did not call the author callback; "
        f"stdout={result.stdout_text!r}"
    )
    assert isinstance(received[0], Context), (
        "custom-version callback did not receive an invocation context; "
        f"got {type(received[0])!r}"
    )

    missing = _help_run(custom, ["--version"], prog_name=prog)
    assert_printed_identity_is(missing, greeting, unique)

    def ready_cb(**kwargs) -> None:
        print(greeting, flush=True)

    ready_cb.__name__ = f"{_help_ident()}_{_help_ident()}"
    ready = command()(version_option("9.9.9")(ready_cb))
    ready_result = _help_run(ready, ["--version"], prog_name=prog)
    assert_eager_identity(ready_result, greeting, "9.9.9")
    assert ready_result.stdout_text != result.stdout_text, (
        "custom-version stdout matched the ready-made version template; "
        f"custom={result.stdout_text!r} ready={ready_result.stdout_text!r}"
    )


def test_first_eager_flag_on_command_line_wins():
    greeting = _help_hi()
    desc = f"Describe {uuid.uuid4().hex} path."
    identity = f"ver-{uuid.uuid4().hex}"

    def callback() -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_help_ident()}_{_help_ident()}"
    callback.__doc__ = desc
    leaf = command()(version_option(identity)(callback))

    help_first = _help_run(leaf, ["--help", "--version"])
    print(f"help-first={help_first.stdout_text!r}", flush=True)
    assert_intentional_help(help_first, greeting, desc)
    assert identity not in _page(help_first), (
        f"version identity {identity!r} appeared when --help was first; "
        f"stdout={help_first.stdout_text!r}"
    )

    version_first = _help_run(leaf, ["--version", "--help"])
    print(f"version-first={version_first.stdout_text!r}", flush=True)
    assert_eager_identity(version_first, greeting, identity)
    assert desc not in version_first.stdout_text, (
        f"help description appeared when --version was first; "
        f"stdout={version_first.stdout_text!r}"
    )


# ---------------------------------------------------------------------------
# H. No-args-is-help is a usage failure
# ---------------------------------------------------------------------------


def test_missing_subcommand_help_is_usage_error_not_success():
    greeting = _help_hi()
    desc = f"Group {uuid.uuid4().hex}."

    def root() -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = desc
    cli = group()(root)

    def child() -> None:
        return None

    child.__name__ = f"{_help_ident()}_{_help_ident()}"
    cli.add_command(command()(child))

    missing = _help_run(cli, [])
    print(
        f"missing exit={missing.exit_code} stdout={missing.stdout_text!r} "
        f"stderr={missing.stderr_text!r}",
        flush=True,
    )
    assert_usage_help(missing, greeting, desc)

    helped = _help_run(cli, ["--help"])
    assert_intentional_help(helped, greeting, desc)
    assert missing.exit_code != helped.exit_code, (
        "missing-subcommand help and --help share an exit status; "
        f"missing={missing.exit_code} help={helped.exit_code}"
    )


def test_leaf_no_args_is_help_is_usage_error():
    greeting = _help_hi()
    desc = f"Leaf {uuid.uuid4().hex}."
    leaf = _help_leaf(greeting, doc=desc, no_args_is_help=True)

    missing = _help_run(leaf, [])
    print(
        f"leaf missing exit={missing.exit_code} "
        f"stdout={missing.stdout_text!r} stderr={missing.stderr_text!r}",
        flush=True,
    )
    assert_usage_help(missing, greeting, desc)

    helped = _help_run(leaf, ["--help"])
    assert_intentional_help(helped, greeting, desc)
    assert missing.exit_code != helped.exit_code


def test_invoke_without_command_skips_no_args_help():
    greeting = _help_hi()
    desc = f"Group {uuid.uuid4().hex}."

    def root() -> None:
        print(greeting, flush=True)

    root.__name__ = f"{_help_ident()}_{_help_ident()}"
    root.__doc__ = desc
    cli = group(invoke_without_command=True)(root)

    def child() -> None:
        return None

    child.__name__ = f"{_help_ident()}_{_help_ident()}"
    cli.add_command(command()(child))

    result = _help_run(cli, [])
    print(f"invoke-without={result.stdout_text!r} exit={result.exit_code}", flush=True)
    assert_success_marker_present(result, greeting)
    assert result.exit_code == 0
