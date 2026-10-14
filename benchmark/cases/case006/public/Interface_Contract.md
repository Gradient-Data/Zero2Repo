# Interface Contract

This Contract is the shell of **Optlyn**: what an application author imports and calls, the parameters each entry accepts, and the form of everything the library puts out. What the library does with those inputs, and every default value that changes behaviour, is stated in the PRD. Wherever a form is not stated below, it is the implementer’s choice.

## 1. Package and modules

- Distribution and import package: `optlyn`, laid out as `src/optlyn`. Python 3.10 or newer, no runtime dependencies.
- The package root `optlyn` exports these names (all importable as `from optlyn import <name>`):
  - Declaration: `command`, `group`, `option`, `argument`, `help_option`, `version_option`, `custom_version_option`, `password_option`, `confirmation_option`, `pass_context`, `pass_obj`, `make_pass_decorator`.
  - Classes: `Command`, `Group`, `CommandCollection`, `Context`, `Option`, `Parameter`, `ParamType`, `BadParameter`, `Abort`.
  - Parameter types: `STRING`, `INT`, `FLOAT`, `BOOL`, `UUID`, `UNPROCESSED` (ready-made instances); `Choice`, `DateTime`, `IntRange`, `FloatRange`, `Tuple`, `File`, `Path` (constructible).
  - Terminal helpers: `echo`, `secho`, `style`, `unstyle`, `echo_via_pager`, `get_pager_file`, `progressbar`, `prompt`, `confirm`, `getchar`, `pause`, `edit`, `launch`, `clear`, `get_app_dir`, `get_current_context`, `format_filename`, `open_file`.
- `optlyn.testing` exports `CliRunner`.
- `optlyn.formatting` exports `wrap_text`.
- Further exports are the implementer’s choice.

## 2. Global output forms

### Exit statuses (standalone mode)

| status | meaning |
| --- | --- |
| `0` | success, intentional help, version, or an author clean stop with no status |
| `2` | usage error |
| `1` | abort, or another library-signalled error that is not a usage error (including a file that fails to open at first I/O) |
| `<n>` | an author clean stop with status `<n>` |

Standalone mode ends the process with `SystemExit` carrying that status. With standalone mode off, the process is not exited: failures surface to the caller as raised exceptions, and the call returns the callback’s return value. Exception class names other than those listed in section 1 are the implementer’s choice.

### Channels

| output | channel |
| --- | --- |
| help page asked for intentionally | standard output |
| help page shown because of incorrect usage (for example a group invoked with no subcommand) | standard error |
| version identity | standard output |
| usage-error report | standard error |
| abort indication | standard error |
| general error report (for example a file that cannot be opened at first I/O) | standard error |
| deprecation warning for a command, option or argument | standard error |
| completion registration script and suggestion stream | standard output |
| prompt and confirmation question text | standard output |
| progress bar, pause message, screen-clear sequence | standard output |

Wording of every report, warning and indication is the implementer’s choice, with these exceptions: a usage-error report about a parameter contains that parameter’s identity, which is one of the option’s declared flag names exactly as declared or the argument’s name (letter case is the implementer’s choice). A report about a path that cannot be opened or fails a path check contains that path. A custom deprecation note appears verbatim in the deprecation warning.

### Help page

Printed on the channel given above. It contains, in this order:

1. A usage line that contains the program name, the options placeholder (default spelling the implementer’s choice; an author `options_metavar` appears verbatim as its own whitespace-separated token), and each argument’s placeholder (its `metavar`, by default the argument name in uppercase).
2. The command description.
3. A section headed `Positional arguments` when at least one argument has `help`; each entry carries the argument’s placeholder and its help text.
4. A section headed `Options`; each option’s entry is contiguous and starts with its declared names, followed by its metavar (if any) and its help text. Extras (shown default, environment variable name, choice values) follow inside that entry, in a form that is the implementer’s choice.
5. For a group, a section that lists each visible child with its short help.
6. The epilog, when set.

Section ordering beyond the above, the deprecation mark, punctuation and indentation are the implementer’s choice.

### Version identity

The version flag prints a single page on standard output. For `version_option` the page contains the version string, and the surrounding text is the implementer’s choice. For `custom_version_option` the page is exactly the callback’s returned string followed by a newline.

## 3. Declaring commands and groups

### `command`

```
command(name=None, cls=None, **attrs)
```

- Used as `@command()` or `@command` on a function. It returns a command instance (a `Command`, or an instance of `cls`).
- `name`: the exported name (`str`), or `None` to derive it from the function.
- `attrs` keywords accepted: `help` (description text), `short_help`, `epilog`, `options_metavar`, `context_settings` (mapping, see `Context`), `add_help_option` (bool), `no_args_is_help` (bool), `deprecated` (bool, or a `str` note), `hidden` (bool).

Command instance members:

- `main(args=None, prog_name=None, complete_var=None, standalone_mode=True, **extra)`: runs the command. `args` is a list of tokens, and `None` means `sys.argv[1:]`. `prog_name` is the program name shown on usage lines and used to derive the completion variable, and `None` derives it from the process. `complete_var` replaces the derived completion-variable name. `extra` keywords go to the invocation `Context`.
- Calling the instance (`cmd(...)`) is `main(...)`.
- `callback`: the author function.
- `params`: the list of declared parameter objects.

### `group`

```
group(name=None, cls=None, **attrs)
```

- Used as `@group()` or `@group`. It returns a group instance (a `Group`, or an instance of `cls`).
- `attrs` keywords accepted are those of `command`, plus `chain` (bool), `invoke_without_command` (bool), and, when `cls=CommandCollection`, `sources` (a list of groups).

### `Group`

```
Group(name=None, commands=None, invoke_without_command=False, no_args_is_help=None, subcommand_metavar=None, chain=False, result_callback=None, **kwargs)
```

- `no_args_is_help=None` means “derive it from `invoke_without_command`”, as stated in the PRD.
- A subclass may be passed as `cls` to `group`. The instance is then of that subclass, and the subclass receives the same constructor arguments.
- Members:
  - `add_command(cmd, name=None)`: registers `cmd` under `name`, or under the command’s own name when `name` is `None`. Attaching a group beneath a chaining group raises at that call.
  - `command(*args, **kwargs)` and `group(*args, **kwargs)`: the same arguments as the root decorators. The decorated child is registered on this group.
  - `result_callback()`: returns a decorator. The decorated function is called as `f(value, **group_params)`, where `value` is a list of child returns (chain mode) or the single return (non-chain mode).
  - `list_commands(ctx) -> list[str]` and `get_command(ctx, cmd_name) -> Command | None`: listing and lookup. These are the override points for custom groups.
  - `callback`: the group’s author function.

### `CommandCollection`

```
CommandCollection(name=None, sources=None, **kwargs)
```

A `Group` subclass. `sources` is a list of groups, and `None` means an empty list. It is normally built as `group(cls=CommandCollection, sources=[...])(callback)`.

## 4. Parameters

### `option`

```
option(*param_decls, cls=None, **attrs)
```

- `param_decls`: names starting with a prefix character are flag names (`<prefix><prefix><long>` or `<prefix><c>`, where `<prefix>` is `-` or another declared prefix character). A declaration of the form `<on-flag>/<off-flag>` declares an on/off pair. A name with no prefix is the destination.
- It returns a decorator that attaches the option and returns the function.
- `attrs` keywords accepted:

| keyword | meaning |
| --- | --- |
| `type` | a parameter type instance, a `ParamType` subclass instance, or a conversion function `f(token) -> value` that refuses by raising `ValueError` |
| `default` | a value, or a zero-argument callable |
| `required` | bool |
| `is_flag` | bool |
| `flag_value` | the value delivered when the flag is present |
| `count` | bool: counting option |
| `multiple` | bool: repeatable |
| `nargs` | positive int: tokens per occurrence |
| `envvar` | `str` or list of `str` |
| `allow_from_autoenv` | bool |
| `prompt` | bool, or a `str` question |
| `prompt_required` | bool |
| `hide_input` | bool |
| `confirmation_prompt` | bool |
| `callback` | `f(ctx, param, value) -> value`; refuses by raising `BadParameter` |
| `is_eager` | bool |
| `expose_value` | bool |
| `hidden` | bool |
| `deprecated` | bool, or a `str` note |
| `help` | text |
| `metavar` | text |
| `show_default` | bool, or a `str` shown instead of the value |
| `show_envvar` | bool |
| `shell_complete` | `f(ctx, param, incomplete)`; see section 8 |

An invalid combination of keywords (as the PRD defines) raises at declaration, when the decorator is applied.

### `argument`

```
argument(*param_decls, cls=None, **attrs)
```

- `param_decls`: a single destination name.
- `attrs` keywords accepted: `type`, `default`, `required`, `nargs` (positive int, or `-1` for variadic), `envvar`, `deprecated`, `help`, `metavar`. An invalid combination raises at declaration.

### Delivered values

The command callback is called with keyword arguments named by the parameter destinations.

| case | value delivered |
| --- | --- |
| unary parameter | a scalar |
| `nargs` other than 1, or a `Tuple` type | a tuple |
| `multiple=True` | a tuple, one entry per occurrence |
| omitted variadic argument or repeatable option | `()` |
| omitted parameter with no value from any source | `None` |
| flag | a `bool`, or its `flag_value` |
| counting option | an `int` |

### Parameter objects

`Option` and the argument class are `Parameter` subclasses. Parameter callbacks and completion functions receive these objects. Each exposes `name` (the destination) and `metavar` (the author string, or `None` when not given).

### Ready-made option decorators

| signature | default flag name | what it attaches |
| --- | --- | --- |
| `help_option(*param_decls, **kwargs)` | | an extra eager help flag |
| `version_option(version=None, *param_decls, package_name=None, prog_name=None, message=None, **kwargs)` | `--version` | an eager version flag |
| `custom_version_option(callback, *param_decls, **kwargs)` | `--version` | an eager version flag; `callback(ctx) -> str` |
| `password_option(*param_decls, **kwargs)` | `--password` | a prompting, hidden, confirmed option |
| `confirmation_option(*param_decls, **kwargs)` | `--yes` | a confirmation flag; `prompt=` sets the question text |

- `help_option`: the declared names print the help page.
- `version_option`: `version` is the identity, and `None` means it is detected via `package_name`.
- `custom_version_option`: the identity is the string `callback(ctx)` returns.

### `BadParameter`

```
BadParameter(message, ctx=None, param=None, param_hint=None)
```

Raised from a parameter callback, from a `ParamType.convert`, or from a conversion function, to refuse a value. `message` is text, and the remaining arguments are optional.

## 5. Parameter types

| entry | form |
| --- | --- |
| `STRING`, `INT`, `FLOAT`, `BOOL`, `UUID`, `UNPROCESSED` | ready-made instances. They deliver `str`, `int`, `float`, `bool`, `uuid.UUID`, and the raw token, respectively |
| `Choice(choices, case_sensitive=True)` | `choices` is an iterable of values, or an `enum.Enum` subclass (members are matched by name) |
| `DateTime(formats=None)` | `formats` is a sequence of `strftime` format strings, and `None` means the default list. Delivers `datetime.datetime` |
| `IntRange(min=None, max=None, min_open=False, max_open=False, clamp=False)` | delivers `int` |
| `FloatRange(min=None, max=None, min_open=False, max_open=False, clamp=False)` | delivers `float`. An invalid combination raises when constructed |
| `Tuple(types)` | `types` is a sequence of types, one per position |
| `File(mode="r", encoding=None, errors="strict", lazy=None, atomic=False)` | `mode` is one of `r`, `w`, `rb`, `wb`. `lazy=None` means the mode-dependent behaviour the PRD states. Delivers an open file object |
| `Path(exists=False, file_okay=True, dir_okay=True, writable=False, readable=True, resolve_path=False, allow_dash=False, path_type=None, executable=False)` | `path_type` is `str`, `pathlib.Path`, or `None` (deliver `str`). Delivers a path, not an open file |
| `ParamType` | base class for custom types. A subclass sets `name` (text, shown upper-cased as the default metavar) and implements `convert(value, param, ctx)`, which must accept `param=None, ctx=None` and refuses by raising `BadParameter`. It may implement `shell_complete(ctx, param, incomplete)` (section 8) |

## 6. Invocation context

### `Context`

Built by the library, one per invocation. Settings reach it from three places:

- `main(**extra)`;
- `CliRunner.invoke(**extra)`;
- the `context_settings` mapping on `command`/`group`.

The setting keys are:

| key | form |
| --- | --- |
| `auto_envvar_prefix` | `str` |
| `default_map` | `dict` of destination to value; a group’s map nests a `dict` under each child name |
| `terminal_width` | `int` |
| `max_content_width` | `int` |
| `help_option_names` | list of `str` |
| `token_normalize_func` | `f(str) -> str` |
| `color` | `True`, `False` or `None` |
| `show_default` | bool |
| `allow_extra_args` | bool |
| `ignore_unknown_options` | bool |
| `allow_interspersed_args` | bool |

Members available to callbacks:

| member | form |
| --- | --- |
| `obj` | the author object, readable and assignable |
| `params` | a `dict` of destination to the value already bound in this invocation |
| `parent` | the parent context, or `None` |
| `invoked_subcommand` | the child’s exported name (`str`) when one is about to run; `None` when none will; on a chaining group about to run children, a value that is neither `None` nor a child name (its form is the implementer’s choice) |
| `get_parameter_source(name)` | `None` for a name that is not declared; otherwise one of five distinct values, one per source (their form is the implementer’s choice; equal sources compare equal) |
| `with_resource(cm)` | enters the context manager `cm` and returns its value |
| `invoke(cmd, **values)` / `forward(cmd, **values)` | run another command from inside a callback |
| `exit(code=0)` | author clean stop |
| `abort()` | author abort |
| context-manager protocol | `with ctx:` makes `ctx` current on the entering thread |

### Callback decorators

| signature | the decorated callback receives as its first positional argument |
| --- | --- |
| `pass_context(f)` | the current `Context` |
| `pass_obj(f)` | the current context’s `obj` |
| `make_pass_decorator(object_type, ensure=False)` | the object of type `object_type` that the PRD lookup finds; with `ensure=True`, a newly created `object_type()` when none is found |

### `get_current_context(silent=False)`

Returns the `Context` that is current on the calling thread. When there is none, it raises if `silent` is false and returns `None` if `silent` is true.

## 7. Terminal helpers

All helpers write through the interpreter’s standard streams (`sys.stdout` and `sys.stderr`) unless stated otherwise.

| signature | form |
| --- | --- |
| `echo(message=None, file=None, nl=True, err=False, color=None)` | `message` is `str` or `bytes`. Writes to standard output, or to standard error when `err=True`, or to `file` |
| `secho(message=None, file=None, nl=True, err=False, color=None, **styles)` | `styles` are the keywords of `style` |
| `style(text, fg=None, bg=None, bold=None, dim=None, underline=None, overline=None, italic=None, blink=None, reverse=None, strikethrough=None, reset=True) -> str` | a color is a name (`str`), an `int`, or a 3-item sequence of `int`. Returns `text` wrapped in ANSI SGR escape sequences (`ESC [ … m`). The exact codes are the implementer’s choice. An invalid color raises |
| `unstyle(text) -> str` | |
| `echo_via_pager(text_or_generator, color=None)` | accepts a `str`, an iterable of `str`, or a zero-argument callable returning one |
| `get_pager_file(color=None)` | context manager yielding a writable text stream |
| `progressbar(iterable=None, length=None, label=None, hidden=False, **options)` | context manager yielding a bar. The bar is iterable (yields the original items) and has `update(n_steps)`. Further keyword `options` are the implementer’s choice |
| `prompt(text, default=None, hide_input=False, confirmation_prompt=False, type=None, ...)` | returns the converted value |
| `confirm(text, default=False, abort=False, ...) -> bool` | |
| `getchar(echo=False) -> str` | reads from the process’s controlling terminal. The interrupt key raises `KeyboardInterrupt`; the end-of-file key raises `EOFError` |
| `pause(info=None, err=False)` | |
| `edit(text=None, editor=None, env=None, require_save=True, extension=".txt", filename=None)` | `editor` is a command line. The library runs it with the path of the file to edit among its command-line arguments; the argument position is the implementer’s choice. Returns the saved text as `str`, or `None` (also `None` when `filename` is given) |
| `launch(url, wait=False, locate=False) -> int` | `url` is a URL or a path. The default application receives it as a command-line argument. The returned status value is the implementer’s choice |
| `clear()` | |
| `get_app_dir(app_name, roaming=True, force_posix=False) -> str` | returns the directory path as `str`. `roaming` is accepted; its effect is the implementer’s choice |
| `format_filename(filename, shorten=False) -> str` | `filename` is `str`, `bytes`, or a path-like object |
| `open_file(filename, mode="r", encoding=None, errors="strict", lazy=False, atomic=False)` | returns a file object usable as a context manager. `filename` may be `-` |
| `wrap_text(text, ...)` (from `optlyn.formatting`) | returns the wrapped `str` |

- Pager: when a pager runs, it is the command line in the `PAGER` environment variable, and the text is written to that command’s standard input.
- Interactivity: whether a session is interactive is decided by the terminal state of the standard streams (see the PRD).

## 8. Shell completion

- Variable: `_<PROG>_COMPLETE`, where `<PROG>` is the program name upper-cased with `-` replaced by `_`. `main(complete_var=...)` replaces that name.
- Values: `<shell>_source` or `<shell>_complete`, with `<shell>` one of `bash`, `zsh`, `fish`, `powershell`.
- Inputs in complete mode:
  - `COMP_WORDS` is the command line as one space-joined string, starting with the executable name.
  - For `bash`, `zsh` and `powershell`, `COMP_CWORD` is the integer index of the incomplete word (equal to the word count when the incomplete token is empty).
  - For `fish`, `COMP_CWORD` is the incomplete token itself, which may be empty.
- Output on standard output, after which the process exits with status 0:
  - Source mode prints the registration script.
  - Complete mode prints the suggestions. Each suggested value appears verbatim. For `zsh` and `fish`, a suggestion’s help text appears too. A path request is a non-value entry that carries the incomplete token and is of one of two kinds, a directories-only request or a file/any-path request; the two kinds are distinguishable from each other, in a form that is the implementer’s choice. Script syntax, entry framing and separators are the implementer’s choice.
- Completion functions:
  - `shell_complete(ctx, param, incomplete)` on an option, or the same method on a custom `ParamType`.
  - `ctx.params` holds the values already parsed, `param` is the parameter object, and `incomplete` is a `str`.
  - It returns a list whose items are `str`, or objects exposing `value` (`str`), `help` (`str` or `None`) and `type` (`"plain"` for an ordinary value; any other `type` value and its meaning are the implementer’s choice).

## 9. In-process runner (`optlyn.testing.CliRunner`)

```
CliRunner(charset="utf-8", env=None, echo_stdin=False, catch_exceptions=True, capture="sys")
```

`capture` is `"sys"` (interpreter streams) or `"fd"` (descriptor capture).

```
CliRunner.invoke(cli, args=None, input=None, env=None, catch_exceptions=None, color=False, **extra) -> Result
```

- `args` is a list of tokens.
- `input` is `str` or `bytes` fed to standard input.
- `env` is a mapping, in which a value of `None` unsets that variable.
- `extra` covers `standalone_mode`, `prog_name`, and `Context` settings such as `terminal_width`.

`Result` attributes:

| attribute | value |
| --- | --- |
| `exit_code` | `int` |
| `output` | `str`: standard output and standard error in write order |
| `stdout`, `stderr` | `str` |
| `stdout_bytes`, `stderr_bytes` | `bytes` |
| `exception` | the caught exception, or `None` |

`CliRunner.isolated_filesystem(temp_dir=None)` is a context manager that yields the path of the new working directory (`str`).
