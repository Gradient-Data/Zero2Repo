# Optlyn — Full Product Requirements Document

## Product overview

**Optlyn** is a Python package for creating command line interfaces in a composable way with as little code as necessary. It is the “Command Line Interface Composition Kit”: highly configurable, with sensible defaults. It exists so that writing command line tools is quick, and so that an intended command-line API can actually be implemented — including arbitrary nesting of commands — rather than being blocked by the parser.

Optlyn in three points, as the product itself states them:

- Arbitrary nesting of commands
- Automatic help page generation
- Support for lazy loading of subcommands at runtime

The finished product is a **library**, not a command users type. An application author declares commands, groups, options, and arguments; Optlyn parses the process argument list, converts values, generates help, dispatches to the author’s callbacks, and supplies terminal helpers. End users of those applications see a POSIX-style command line: options, positional arguments, nested subcommands, and a help page.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, and decorator spellings belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished product. Feature points are ordered so foundational capabilities come first; a later feature point may refine an earlier one only when it says so explicitly.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **Command** | A callable unit that parses a slice of the command line and runs an author-supplied callback. A bare command is a leaf: it has options and arguments, but no nested subcommands. |
| **Group** | A command that dispatches to named subcommands (which may themselves be groups). Groups are how Optlyn nests CLIs. |
| **Option** | A named parameter, typically introduced by a dash prefix (`-` or `--`, or another declared prefix). Options are optional unless the author marks them required. They appear fully on the help page. |
| **Argument** | A positional parameter. Arguments are the usual place for files, URLs, and leftover tokens. They are not fully documented on the help page unless the author supplies help text or documents them in the command’s description. |
| **Parameter** | An option or an argument. |
| **Invocation context** | The per-invocation state Optlyn creates when a command runs: parsed values, parent/child linkage, an optional author object, resource cleanup, and flags that affect parsing and output. |
| **Help page** | The usage text Optlyn generates for a command or group when the user asks for help, or when a group is invoked incorrectly under the default “no arguments means help” policy. Layout is Optlyn’s; wording of descriptions is the author’s. |
| **Callback** | The author function attached to a command, group, or parameter. Command callbacks receive converted parameter values. Parameter callbacks receive the converted value and may replace it or refuse it. |
| **Eager parameter** | A parameter that can finish the invocation even when other required parameters are still missing. Help and version flags are eager. If several eager flags appear, the one the user typed first is the one that takes effect. |
| **Default map** | A nested mapping of parameter defaults supplied on the invocation context, used to override declared defaults (for example from a config file) without changing the command definition. |
| **Chaining group** | A group that runs several subcommands in one invocation, in the order they appear on the command line. |
| **Interactive session** | A run whose standard input is attached to a terminal (PTY), or whose standard input or standard output is a TTY. A piped standard input without a terminal is not interactive. |

## Public surface inventory

Optlyn is imported and used from Python. The public surface, grouped by feature point, is:

- Declaring a function as a command or a group, attaching options and arguments, registering subcommands immediately or later, and invoking the result as a program or as an in-process call.
- Automatic help (default `--help`) and an eager version flag that prints a version identity and exits, including a variant whose identity text is produced by an author callback.
- Built-in parameter types, listed under FP-05; custom types the author supplies.
- Prompts (option-integrated and standalone), confirmation, and hidden password input, including the ready-made password and confirmation option combinations.
- File and path parameters, including `-` as stdin/stdout for the file type.
- Terminal helpers: echo (including to standard error), styling, styled echo, stripping styles, pager output, progress bars, single-character input, pause-until-key, editor launch, application launch, screen clear, application-config directory lookup, filename formatting, text wrapping, and opening files or standard streams.
- Shell completion for Bash (4.4 and newer), Zsh, Fish, and PowerShell, in both registration-script mode and suggestion-emission mode.
- Usage-failure and abort handling with distinct exit-status classes.
- An in-process runner that invokes a command with argument tokens and captures output and exit status.

Feature points below group these entries by capability. They do not invent additional product surfaces. Packaging an application as a console-script entry point is how authors ship tools; it is not itself a Optlyn command.

## Non-functional constraints

- **Form factor:** A pure-Python library. Authors build CLIs with it; Optlyn is not a single end-user binary. The importable package directory is `optlyn` under `src`.
- **Language:** Python 3.10 or newer. The package has zero declared runtime dependencies. Importing the package performs no I/O, starts no processes, and opens no sockets.
- **Platforms:** Intended to work on Linux, macOS, and Windows. The supported target is Linux with a supported Python interpreter. No compiled extensions, native code, GPU, or accelerator are required or claimed. (On Windows, when invoked as a program, glob, home-directory, and environment tokens in the process argument list are expanded unless the author disables that; a Unix shell already expands before the process starts.)
- **Hardware:** CPU-only.
- **Parsing conventions:** Optlyn implements POSIX-style option parsing (short-option stacking, `--` to end option parsing, long options with `--`). Alternative option prefixes such as `/` and `+` are supported when the author declares them. Leaf commands, by default, also allow an option to appear after a positional argument; groups, by default, do not mix the group’s own options with the subcommand name (FP-03).
- **Help layout:** Description text is customizable; the help **layout** is not a free-form author template. Nested Optlyn programs keep a consistent help shape when composed.
- **Unicode:** Command-line values are text. Echo and file helpers exist so misconfigured terminals do not fail on ordinary Unicode output. An ASCII-only environment encoding does not abort invocation (FP-11).
- **Threading:** The current invocation context is available on the thread that is running the command. Other threads do not see that context unless the author enters the same context in that thread. The context is not a thread-safe mutable store.

## Non-goals

- Being a general-purpose argument parser unrelated to command dispatch (Optlyn both parses and dispatches).
- Letting authors fully redesign help-page layout (wording yes; layout no).
- Shipping a remote server, GUI, or web framework.
- Built-in command aliases or plugin discovery. Those are extension patterns authors implement on top of groups; they are not built-in commands of Optlyn itself. FP-06 requires that custom groups *can* resolve names their own way, not that a particular alias scheme ships.
- A configuration-file syntax of Optlyn’s own. A default map can be loaded from whatever the author chooses.
- Thread-safe mutation of an invocation context.
- Guaranteeing color on every Windows console without extra platform support; recent Windows supports ANSI styling, and echo strips styles when the stream is not a terminal.

---

## Feature points

### FP-01: Command declaration, naming, and invocation

**Public entry:** Optlyn’s command declaration (applied to an ordinary Python function) and invoking the resulting command as a program — by calling it, by running it as a script, or as an installed console script. A group’s command-registration helper is also an entry for attaching a leaf command (FP-06).

**Normal behavior:**

- Decorating a function with no extra arguments produces a command whose name is the function name converted to lowercase, with underscores replaced by dashes, and with a trailing `_command`, `_cmd`, `_group`, or `_grp` suffix stripped when present. Passing an explicit name uses that name instead, and then only that name is accepted: the name derived from the function is not.
- Invoking the command with a valid argument list runs the function once and returns a successful process exit when used as a program. The function body is the command’s work: whatever it writes appears, and it is not run more than once.
- A command marked deprecated still runs and still succeeds. On invocation, Optlyn emits a deprecation warning that is distinguishable from ordinary command output and from a usage failure. A custom deprecation note, when the author supplies one, appears in that warning; the command does not refuse to run merely because it is deprecated. An unknown option on a deprecated command is still a usage error.
- Parameters declared on the command are converted and passed into the function under the destination names inferred or declared for those parameters (FP-03). A command with no parameters still runs when invoked with an empty extra-argument list. Creating a command or group moves declarations previously attached to the function onto the new command and removes them from the function; decorating the same function again starts from an empty declaration list.
- When the command is invoked as a standalone program, Optlyn handles the failure classes in FP-13 and exits the process. When the integrator disables standalone program mode, failures propagate to the caller and the command’s return value is available to the caller instead of being discarded.

**Boundary / error behavior:**

- Unknown option tokens, missing required parameters, and values that fail conversion do not run the command callback. They fail as usage errors (FP-13).
- An ASCII-only environment encoding does not abort execution: the same command still runs and produces the same successful outcome as in a Unicode locale.
- Leftover tokens beyond the declared arity that no variadic argument collects are a usage error, unless the command is configured to allow extra arguments. With extra arguments allowed, leftover tokens that are not option-shaped are tolerated and the callback runs; each declared argument still receives only the tokens that fill its own arity. An option-shaped leftover token (a leading dash, not after `--`) remains a usage error under that setting alone; consuming it as an argument requires the ignore-unknown-options setting (FP-03) or a preceding `--`.

---

### FP-02: Automatic help pages and eager documentation flags

**Public entry:** The automatic help option on every command (default `--help`, overridable through the invocation context’s help-option names); the command’s docstring and per-option / per-argument help text; the ready-made version option and the ready-made custom-version option; optional epilog, short-help override, metavar, show-default, and show-environment-variable switches.

**Normal behavior:**

- Asking for help on a command prints a help page and does **not** run the command callback. The page includes a usage line, the command’s description, and a documented options section. Intentional help exits successfully (exit status zero).
- If the function has a docstring, that docstring is the command description, unless the author supplies an explicit help string. A form-feed character in the docstring truncates the help: text after that character is omitted from the help page; text before it remains. The form-feed character itself does not appear on the page.
- Option help strings appear next to those options. Argument help, when the author supplies it, appears in a positional-arguments section; without it, that section does not carry the argument. Arguments may also be described in the docstring by name.
- For subcommands listed on a group help page, the short help is the first sentence of the docstring by default, ellipsized if it cannot fit on one line at the wrap width, or an explicit short-help string when the author sets one (which then replaces the first sentence).
- Group help lists subcommands, the group’s options, positional arguments, and an epilog when one is set. The epilog is printed at the end of the help page, after everything else on it.
- The usage line brackets optional elements and leaves required elements unbracketed. A variadic argument is marked with a trailing ellipsis. The default options placeholder is bracketed and occupies its own place on the usage line, distinct from any argument placeholder; an author override of that placeholder is used as given, without added brackets. A group that can run without a subcommand also brackets the leading command token; a chaining group brackets the extra command-and-args unit as optional and repeatable.
- Help text is rewrapped to the terminal width; a maximum content width that defaults to 80 columns and can be raised by the caller caps auto-detected width only, and an explicit caller-supplied terminal width is the wrap width as-is (whatever the maximum content width). Single newlines inside a paragraph are not preserved as hard breaks. A paragraph whose first line is only a backspace character is not rewrapped: subsequent lines of that paragraph keep their line breaks, and the backspace line itself is stripped from the rendered help.
- The default metavar for an argument is the argument name in uppercase. For an option that takes a value, the default metavar is the type name in uppercase, unless that type supplies its own placeholder (a choice type does); a flag or counting option has no metavar. Authors may override the usage-line options placeholder and per-parameter metavars; an author metavar replaces the type-name placeholder.
- The help entry of an option whose type is a closed choice lists the allowed values; an option of the plain text type does not.
- When show-default is enabled, the help page shows the default in that option’s entry. Show-default may be enabled per parameter or for the whole invocation via the context. The author may supply a custom default description, shown instead of the raw default value. For a single-option boolean flag whose default is off (false), that default remains hidden even if show-default is on; a flag whose default is on (true) shows it. When show-environment-variable is enabled, the associated environment variable name appears in that option’s entry; when disabled, it does not.
- The help page of a deprecated command carries a deprecation mark that the page of an otherwise identical non-deprecated command does not.
- Hidden options, hidden commands, and hidden groups are omitted from help (and from completion — FP-12) but remain invocable if the user types their names.
- Help-option names default to `--help`. The invocation context may replace that list; the new names then print help and a name no longer in the list is an unknown option. If an author-declared option reuses every help-option name, the automatic help option is dropped and the author’s option wins; if it reuses only some of those names, the overlapping name runs the author’s option and the remaining names still print help. A parameter merely *named* `help` (for example a positional argument called `help`) does not disable automatic help: both keep working. Authors may also attach an extra help option that prints help and exits the same way as the automatic option; it does not remove the automatic one.
- The ready-made version option is eager: it prints a version identity and exits without running the command callback, even when other required parameters are missing or present. If the author supplies the version string, the identity contains it. If the author does not supply it, Optlyn detects it from the installed distribution of the given package name; if that name is not an installed distribution, it is treated as an import name and the version of the distribution that provides that import is used. A module’s own version attribute is not consulted. The ready-made custom-version option is the same eager flag, except the whole printed identity is exactly the string returned by an author callback that receives the invocation context: that return value is printed as-is, not wrapped in the built-in package/prog/version template or any other surrounding label. If both help and version appear on the command line, whichever eager flag the user typed first wins and exits; the other’s output does not appear.

**Boundary / error behavior:**

- Help shown because the user invoked a group with no subcommand under the default “no arguments means help” policy is a **usage failure**, not a successful help request: the help page is printed, the group callback is not run (unless the group is configured to invoke without a command — FP-06), and the exit status is the usage-error class (FP-13), not zero.
- Incorrect usage of a command that causes Optlyn to show help (missing subcommand, and similar no-args-is-help paths) likewise uses the usage-error exit class. Passing the help option explicitly uses the success exit class.
- A command may disable automatic help. Then `--help` is an unknown option unless the author declared it (for example with an extra help option of that name, which restores it).

---

### FP-03: Options

**Public entry:** Optlyn’s option declaration on a command or group. Ready-made combinations that are still options (password option, confirmation option) are specified under FP-08; the version option under FP-02.

**Normal behavior:**

- Declarations attached as options (or arguments) live on the function until a command or group is created from it: those declarations are then moved onto the new command and removed from the function. Decorating the same function again starts from an empty declaration list. Several options on one command are independent: each fills only its own destination.
- An option is optional by default. If it is omitted and has no default, the callback receives an absent value. If a default is set, Optlyn infers the type from that default when the author does not set a type (FP-05). A default that is already of the converted type is delivered unchanged. A default may be a callable; that callable is invoked when no earlier value source produced a value.
- One option may be declared with several names (a short name and a long name, and additional aliases) that all set the same destination. Long options use a double-dash prefix and may take a value as `--name=value` or `--name value`. Short options use a single dash and a single character. Single-character short flags may be stacked: a stack is equivalent to each flag given separately. If the last flag in a stack takes a value, that value may be the next token or attached directly after it, whether alone or at the end of a stack. Multi-character short names are not supported: a single-dash token of several characters is a stack of single-character flags, not one option.
- When the author does not give a destination name, it is inferred from the declared option names: a name that is already a valid identifier wins; otherwise the first long name; otherwise the first short name. A leading dash prefix is stripped and remaining dashes become underscores.
- On a leaf command, options and positional arguments may be mixed: an option after an argument is parsed the same as before it. On a group, mixing is off by default: the subcommand name ends that group’s own option parsing, so group options must appear before the subcommand name. Authors may enable mixing on a group, in which case a group option after the subcommand name is still delivered to the group and the subcommand still runs.
- An option may be required. Then omitting it is a usage error and the callback does not run, unless another source (environment, automatic prefix, default map) supplies it.
- Boolean flags: a flag declared as a flag, when omitted, yields false unless the author set a true default; when present, it yields true. After `--`, a token spelled like the flag is an argument, not the flag. An explicit on/off pair (declared with either prefix style) yields true for the on token and false for the off token. Several flags may share one destination as a feature-switch group: the callback receives the flag value of the winning flag (see value resolution below).
- A counting option yields how many times it occurred (zero if omitted). Each flag in a stack counts.
- A repeatable option may be given several times; the callback receives the sequence of values in command-line order. If it is omitted and has no default, the callback receives an empty tuple, not an absent value. A declared default for a repeatable option must be a sequence (list or tuple) of values, delivered as a tuple in that order when the option is omitted. A multi-value option takes a fixed number of tokens per occurrence (strictly positive; not “consume the rest”): it is delivered as an indexable sequence of that length, a following token is left for the next parameter, and too few tokens is a usage error. Combined with repetition, each occurrence takes that many tokens. A tuple type on an option sets that arity to the tuple length and converts each position with the corresponding inner type.
- An option may take an optional value: the flag alone yields the author’s flag-value; the flag plus a token yields that token; omitting the flag entirely yields the default. (A value option without this form, given with no value, is a missing-value usage error.)
- Authors may declare prefixes other than `-`, including `/` and `+`.
- Environment variables: an option may name one variable or a list of names (first one set wins). Names are matched exactly and are not whitespace-trimmed as names. An absent variable, or a variable present with a truly empty value, is treated as not supplying a value (the next source wins). An environment value is converted with the option’s type and may satisfy a required option. For a repeatable or multi-value option, the type splits a non-empty variable’s string: default split is whitespace; file and path types split on the platform path separator (`:` on Unix), keeping left-to-right order.
- For boolean flags, environment values are strings interpreted as follows after stripping surrounding whitespace and ignoring case. Activation: `true`, `1`, `yes`, `on`, `t`, `y`. Deactivation: `false`, `0`, `no`, `off`, `f`, `n`. A whitespace-only value strips to empty and deactivates. Any other non-empty string is a conversion usage error, not a silent deactivation. If the flag has a non-boolean flag-value, a variable whose text equals that flag-value also activates; recognized true/false tokens activate or deactivate as above; unrecognized and empty values are treated as unset (the next source wins), not as a usage error. A paired on/off option recognizes only the single environment name the author attached, not a magically derived negative name.
- A value is filled from command line, then environment, then the default map on the invocation context (FP-07), then the parameter’s declared default; the first of those that produces a value wins. Those four, plus an interactive prompt when one ran (FP-08), are ranked from most explicit to least as: prompt, command line, environment, default map, declared default.
- Feature-switch groups (several options sharing one destination): the option whose source is most explicit wins. Within the default tier, an explicit declared default beats an auto-derived default (bare boolean flags auto-derive default false). If still tied, the last declared option wins.
- A parameter callback sees the invocation context, the parameter, and the converted value, and may replace the value or refuse it. A refusal is a usage error: non-zero usage-class exit, a message on standard error that distinguishes the failure from success, the command callback not run, and the refused value not delivered. Callbacks run for every source including environment, default map, and prompts. An eager flag can finish the invocation even when required non-eager options are missing; when it is not given, the missing required option is still a usage error. A missing parameter still runs its callback, so that callback can default from an earlier parameter’s value (the values already bound are readable on the context). A repeated parameter fires its callback once, with all gathered values.
- A parameter may be hidden from the callback (not passed as a function argument) while still being parsed — used by help, version, and confirmation flags. Its name is still accepted on the command line.
- A deprecated option still parses. A deprecation warning is emitted only when the user actually supplied that option, not when the value came only from a default.

**Boundary / error behavior:**

- An unknown option is a usage error, unless the command is configured to ignore unknown options, in which case option-like tokens may be consumed as arguments without `--`, and leftover option-like tokens become extra arguments that a variadic pass-through argument can collect (FP-04). Unknown long options are left intact. Unknown short options may be split: a known short flag inside a stack is consumed and the unknown rest of the stack stays leftover. An option-like token left over beyond the declared arity is still a usage error unless extra arguments are allowed (FP-01).
- A missing value for an option that requires one is a usage error.
- A bare string (or other non-sequence) default on a repeatable option is a usage error whose report identifies the option and says that it needs an iterable (sequence) default, so that report is distinct from the report for a missing required option; it is not treated as a sequence of characters and not as a single string element. Authors who want one default string must pass a one-element sequence.
- A deprecated option cannot also be required, and cannot use a prompt. Declaring that combination is refused at declaration time.
- Option values belonging to a command must appear after that command’s name and before a nested command name (FP-06). A help option before a subcommand name is help for the parent, not for the subcommand.

---

### FP-04: Positional arguments

**Public entry:** Optlyn’s argument declaration on a command or group.

**Normal behavior:**

- An argument is positional and binds tokens in declaration order. A minimal argument (a destination name only) is required, has no default, and is text unless a type or default implies otherwise (an integer default infers integer conversion, as for options).
- An argument may be marked optional, or given a default; then omitting it is not a usage error and the callback receives the default, or an absent value (neither a string nor a sequence) when there is none. A supplied token overrides a default. An argument may declare a fixed positive arity or a variadic arity (consume the rest). A unary argument is delivered as a scalar; any other arity is delivered as an indexable sequence. Too few tokens for a required fixed arity is a usage error. Variadic arity may be used at most once on a command; a second variadic argument is refused or never runs the callback. A variadic argument omitted yields an empty sequence unless it was marked required, in which case omitting it is a usage error.
- After a `--` token, subsequent tokens are arguments even if they look like options; the `--` token itself is not delivered. Without it, option-shaped tokens are not arguments (FP-01, FP-03).
- An argument declared on a group is delivered to the group callback; the next token after it is the subcommand name.
- Arguments may read from environment variables only when the author names those variables explicitly (one name or a list; first set wins). There is no automatic environment prefix for arguments (that prefix applies to options — FP-07), and a variable merely named like the destination does not fill one. An absent or truly empty variable is treated as not supplying a value. An environment value may satisfy a required argument and is overridden by a command-line token. A non-empty variable for a non-unary argument is split the same way as for a multi-value option (FP-03); a unary argument keeps the whole value.
- Argument help is optional. Without it, the help page’s main description is where authors document them; with it, a positional-arguments section lists them (FP-02). An author metavar is the argument’s placeholder on the usage line.

**Boundary / error behavior:**

- A missing required argument is a usage error that identifies that argument, and the callback does not run.
- Extra tokens beyond declared arity, when no variadic argument collects them and extra arguments are not allowed, are a usage error.
- With ignore-unknown-options enabled, option-shaped tokens may be consumed as arguments without needing `--`.
- A deprecated argument still parses and cannot be required; an argument with neither a default nor an optional marking counts as required. Declaring that combination is refused at declaration time. A deprecation warning is emitted only when the user actually supplied that argument, not when the value came only from a default.

---

### FP-05: Parameter types and conversion

**Public entry:** The type attached to an option or argument, or inferred from a default. Built-in types are a fixed finite set. Authors may also supply a custom type.

**Normal behavior:**

Built-in types:

- **String** — the default; Unicode text. An explicit string type keeps numeric- or boolean-looking tokens as text.
- **Integer** — only integers (a token with a fractional part is not one); delivered as a Python integer. Conversion failure is a usage error. Inferred from an integer default.
- **Float** — only floating-point numbers; delivered as a Python float. Inferred from a float default.
- **Boolean** — used automatically for boolean flags and inferred from a boolean default; delivers a real boolean. Text conversion (case-insensitive) treats `1`, `true`, `t`, `yes`, `y`, `on` as true and `0`, `false`, `f`, `no`, `n`, `off` as false; anything else is a usage error.
- **UUID** — accepts UUID text and yields a UUID value. It is never inferred automatically from a default.
- **Choice** — a closed list of allowed values, or the member names of an enumeration. Matching is case-sensitive unless the author turns that off. The value delivered is the original choice object (enumeration member or original list entry), not merely the matched string, even when matching is case-insensitive. If two choices normalize to the same token, the first registered original is delivered. Repeatable choice options are allowed; a default for a repeatable choice must be a sequence of valid choices.
- **Date-time** — parses into a date-time value. Formats are tried in order; the first success wins. The default format list is the finite set: date `YYYY-MM-DD`; date and time with `T` as `YYYY-MM-DDTHH:MM:SS`; date and time with a space as `YYYY-MM-DD HH:MM:SS`. Authors may supply their own list of format strings, which replaces the default list (it does not extend it). Values parsed under the defaults are not timezone-aware.
- **Integer range** — an integer that must lie in an optional minimum/maximum range. Bounds are closed by default; either side may be open (boundary excluded) or omitted (unbounded). With clamp enabled, a value outside the range (including a value equal to an open bound) is replaced by the nearest included value: the included bound itself for a closed bound, and the adjacent integer inside the range for an open bound.
- **Float range** — the same range rules for floats. Clamp is only allowed when both bounds are closed; a value above is replaced by the maximum and a value below by the minimum.
- **Tuple** — a fixed-length product of inner types, one converted value per position (see multi-value options in FP-03).
- **File** — opens a file; see FP-09.
- **Path** — validates a filesystem path and returns the path (not an open file); see FP-09.
- **Pass-through** — does not convert the token (used when leftover raw tokens must be forwarded).

A custom type converts a string to a value and must pass through a value that is already the right type (so defaults and Python-side calls work). A conversion function that refuses invalid input is also accepted as a type. Conversion must work even when no command or parameter is supplied (prompt-time conversion). Failure of conversion is reported as a usage error that identifies the offending parameter, not as an uncaught crash.

**Boundary / error behavior:**

- A value that cannot convert (wrong kind for the type, a choice not in the list, a date-time that matches none of the formats, a range value outside the bounds without clamp) is a usage error: non-zero usage-class exit, message on standard error that distinguishes this failure from success and names the offending parameter (and no other parameter), callback not run, and no other parameter’s value delivered.
- Float range refuses clamp when a bound is open (declaration error).
- Choice matching after case-folding still returns the originally registered choice, so an enumeration member remains that member.

---

### FP-06: Groups, nesting, and deferred subcommand loading

**Public entry:** Optlyn’s group declaration; attaching commands with the group’s command helper or by registering an already-declared command later; custom groups that override how names are listed and resolved; a command collection that presents subcommands gathered from several groups.

**Normal behavior:**

- A group contains named subcommands. Naming a subcommand runs that subcommand’s callback and no sibling. By default, invoking the group with no arguments does not run the group callback and shows help as a usage failure (FP-02, FP-13).
- The group callback **does** run when a named subcommand is dispatched, before that child, including when that child then shows help or version; group-level help or version still skip the group callback and do not dispatch. Nested groups run from the outside in: each group on the path, then the leaf.
- Parameters belong to the command they were declared on and are delivered only to it. Group options must appear before the subcommand name; subcommand options after it. Help after a subcommand name is help for that subcommand; help before it is help for the group and does not run the subcommand.
- Arbitrary nesting is allowed: groups containing groups containing commands. Every group on the path must be named to reach a nested command; skipping a middle name is an unknown-command failure of the group that was invoked.
- Commands may be registered later, including from another module, and under an explicit name different from the command’s own. Invocation does not depend on whether attachment was immediate or delayed.
- A group may be configured to run even when no subcommand is named. Then the group callback runs, and the invocation context reports whether a subcommand is about to run so the callback can distinguish “group only” from “group then child”.
- Whether no arguments means help defaults to the opposite of whether the group runs without a subcommand. A group may be configured so that no arguments does not mean help: an empty invocation is then the missing-command usage failure without a help page. A leaf command may be configured so that no arguments *does* mean help (the default for leaves is that it does not).
- Naming a nested group with nothing after it runs every outer group callback on the path and then shows that nested group’s own help page (its description, not an outer one) as a usage failure; the nested group’s callback does not run.
- Lazy loading: a group may resolve a subcommand name only when that name is needed — listing commands, generating help (short help for immediate children), completing names (FP-12), or dispatching. A child that is not needed is not loaded: help resolves immediate children only, never grandchildren, and looking up one name does not look up an unrequested sibling. Custom listing and lookup are the supported extension points: the names a custom listing returns are the names shown on help and offered by completion, and a custom lookup that yields nothing for a name makes that name unknown. Optlyn does not ship a particular plugin folder format, but a custom group that loads a command from a named module when first requested must then invoke that command the same as an eagerly attached one.
- A command collection exposes the union of subcommands from exactly the source groups it is given, under one dispatch surface; a name on any source dispatches to that source’s child. The collection is itself a group: its own callback and description govern its help page and its no-arguments behavior, and its help lists the union of names.
- Hidden commands and hidden nested groups are omitted from the parent help listing but remain reachable by name, including commands nested below a hidden group.
- Command names may be given explicitly, independent of the function name (FP-01).

**Boundary / error behavior:**

- An unknown subcommand name, or a parsed invocation that leaves no subcommand name (group options or arguments only) when the group is not configured to invoke without a command, is a usage error and does not run the group callback or any child. Those two failures report a missing or unknown command on standard error; they do not use the no-arguments help page.
- A chaining group (FP-10) cannot nest further groups beneath it.

---

### FP-07: Invocation context, defaults, environment prefix, and value sources

**Public entry:** The invocation context created for each command run; opting a callback into receiving that context; storing an author object on the context for children; the default map; an automatic environment-variable prefix; asking which source supplied a parameter; registering resources to close when the invocation ends; a token-normalization function; invoking or forwarding another command from inside a callback.

**Normal behavior:**

- Each invocation creates a context linked to its parent. Children see the parent chain. An author object stored on the context is passed to children unless a child replaces it; a descendant sees the nearest replacement on its path, and the same object instance is shared, so mutations are visible to later readers. A callback may request the context as its first argument, or request the author object, or request an object of a given type: that request receives the nearest object of exactly that type found by walking from the current context up through its parents, skipping nearer author objects of other types. When the author asked to ensure it and no such object exists, an empty one is created by calling the type with no arguments; without ensure, none is created.
- Automatic environment prefix (options only): when the top-level invocation is given a prefix, each option may be filled from a variable built as the prefix, then the name of each subcommand on the path below the top-level command (the top-level command’s own name is not included), then the option’s destination, all uppercased and joined by underscores, with dashes in every part (including the prefix) turned into underscores. That value is converted with the option’s type and can satisfy a required option. An individual option may opt out of that automatic prefix and then is filled from the prefix-built name only if the author also named that variable explicitly.
- The default map overrides declared defaults. It nests by subcommand name, then by parameter destination; on a leaf invoked directly it is keyed by destination. An entry for a different subcommand does not apply, and an empty entry supplies nothing. It fills options and arguments and can satisfy a required parameter; a command-line value beats it. A string in the default map is split the same way environment values are (FP-03) only when that parameter’s per-occurrence arity is not one (a multi-value option or tuple type); a sequence is used as-is; other values are delivered as given. A default-map string for a repeatable option that takes one value per occurrence is not split and is refused as not an iterable sequence, the same usage error as a declared default (FP-03). The map may be passed at invocation or set as a context default on the command declaration.
- An integrator can ask which source supplied a named parameter. The distinguishable sources are: prompt, command line, environment, default map, and declared default; the same value from two different sources yields two different answers. A name that is not a declared parameter has no source.
- Resources opened for a group can be registered on the context so they stay open through subcommands and are closed when the CLI invocation ends — including after a subcommand’s usage failure and on process exit of that command.
- Token normalization, when the author installs it, applies to option names, choice values, and command names: a token that matches after normalization is accepted. Without it, tokens must match exactly; a token that does not match after normalization is still a usage error.
- One command may invoke another with explicit values, or forward to another filling in the current parameters. Forwarding runs the target with this command’s values; invoke supplies exactly the caller’s chosen values. The author object on the current context is visible to the target. A value that did not go through a declared parameter is not converted and is not reported as coming from a tracked source.
- Within the running thread, the current context can be read (so echo can inherit the color flag, and the author object is readable). Other threads do not see it unless the context is entered there; entering it on another thread makes it current there for that block.
- The invocation may force color on, force color off, or leave autodetection (FP-11).

**Boundary / error behavior:**

- Automatic prefix never invents environment names for arguments (FP-04).
- Resource cleanup runs when the invocation finishes. A file type closed at the end of a chained command is not usable later in a pipeline processor (FP-10).

---

### FP-08: Prompts, confirmation, and hidden input

**Public entry:** Option-integrated prompts; the standalone prompt and confirm helpers; the ready-made password option (hidden input plus confirmation); the ready-made confirmation option (a yes flag that prompts when omitted and aborts when the user declines).

**Normal behavior:**

- An option with prompting enabled, if not supplied on the command line, reads a line from the user (standard input) and uses that as the value, after conversion (FP-05). A custom prompt string replaces the default prompt derived from the option name. Command-line supply skips the prompt and does not consume input; an option without prompting never reads input.
- If the author does not require a prompt merely because the option was omitted, the option does not prompt when fully omitted; it prompts when the flag is present without a value (and still uses the default when fully omitted). If the option is also required, it prompts both when omitted and when the flag is present without a value. A required prompting option that is omitted prompts rather than failing as missing.
- A declared default (static or callable) and a default-map value still prompt — they are shown as the default and used if the user answers with an empty line; a callable default is invoked for that prompt — while an environment value fills the option and skips the prompt.
- Standalone prompt asks for a value with a message and a type (or a type inferred from a default) and returns the converted value. Standalone confirm asks a yes/no question and returns a boolean: the answers `y` and `yes` are yes and `n` and `no` are no, ignoring case; an empty answer takes the default, and any other answer asks again. Confirm may be told to abort the program when the answer is no (FP-13 abort class); otherwise a negative answer simply returns false. Standalone prompt and confirm strip ANSI styles from the prompt text when the output stream is not a terminal, and keep them on a terminal, matching echo (FP-11).
- Hidden input does not echo the typed value. A confirmation prompt (available on any prompting option) asks twice and rejects a mismatch by asking the pair again; mismatched values are not delivered. The password option is that combination: prompt, hide input, confirm.
- The confirmation option adds a boolean flag (by default a yes-style flag) that is not passed to the callback. If the user passes the flag, the command runs without a question and standard input is not read. If the user omits it, Optlyn asks (using the author’s prompt text when given); a negative answer aborts without running the command callback; a positive answer runs it. With standalone mode off, a declined confirmation propagates to the caller.
- Prompts re-ask on conversion failure until a valid value is given or the input stream ends; the first valid line is the answer and later lines are not consumed.

**Boundary / error behavior:**

- Combining deprecated with prompt is refused (FP-03).
- End of file during any prompt or confirmation (including before a confirmation pair is complete) becomes an abort (FP-13), not delivery of a default.
- In the in-process runner (FP-14), supplied input is consumed as if typed; hidden input is not echoed back into captured output; visible prompts are.

---

### FP-09: File and path parameters

**Public entry:** The file parameter type and the path parameter type on options or arguments; the helper that opens a file or a standard stream with the same dash-as-stdin/stdout rule; atomic and lazy open modes. The helper opens immediately unless the caller turns lazy on.

**Normal behavior:**

- File type: the value is an open file, not a path. The default mode is reading text. The token `-` means standard input when the file is opened for reading and standard output when opened for writing, on options and arguments, in text and binary modes. Binary reads return bytes and binary writes store the bytes given. A text file uses a declared encoding when the author sets one, for a real path and for the dash stream alike: a write stores that encoding’s bytes, and a read with the same encoding recovers the text. Files opened for reading (and standard streams) open immediately so a missing file fails before work starts. Files opened for writing open on first I/O by default (lazy), so a write-mode file is not truncated until actually used. Lazy mode can be forced on or off; a non-lazy write file is opened, and so truncated, before the callback runs even if it is never used. Atomic mode writes to a sibling temporary file and replaces the target when the file is closed: until then, other readers of the target see its original contents.
- A dash write does not close the process standard output: output written after the command still appears.
- Path type: the value is a path, not an open file; by default it is the token as given. Optional checks, each independently selectable: the path must exist; files allowed; directories allowed; readable; writable; executable; resolve to an absolute path (symlinks resolved to their real target; a leading tilde is not expanded). By default existence is not required, files and directories are both allowed, a path that exists must be readable, writability and executability are not checked, the path is not resolved, and a dash is not special. Permission checks apply only to a path that exists. A dash may be allowed as a path token meaning a standard stream without opening it: the dash is delivered as the path `-` and no standard stream is read. When the dash is not allowed, `-` is an ordinary path, accepted exactly when a file of that name satisfies the checks, and still no standard stream is read. The author may request the path be produced as a particular path object type (text or a path object); its filesystem path is the token.
- Environment lists of file or path values split on the platform path separator (FP-03), including for a variadic argument of the path type.
- Filename formatting converts a path that may not be Unicode into text that can be printed (and encoded as strict UTF-8) without failing; printable names keep their characters, and different names stay different.

**Boundary / error behavior:**

- A file that cannot be opened while converting the parameter (missing read target, or a non-lazy write that cannot open) is a usage error that identifies the path; the callback does not run. A lazy write that is never used does not fail. A lazy write that fails when I/O starts is a general file-open error (general error class, not the usage-error class) that identifies the path; work after that write does not run.
- Path checks: a missing path fails when existence is required; a directory fails when only files are allowed and a file when only directories are allowed; a path failing a requested permission fails. Each failure is a usage error that identifies the parameter. If existence is not required and the path is missing, further permission checks are not applied.
- Standard input/output returned from the open helper are not closed when the caller’s block ends (unread standard input stays readable); a real file does close.

---

### FP-10: Command chaining and pipelines

**Public entry:** A group declared as a chaining group; an optional result callback on that group that receives subcommand return values.

**Normal behavior:**

- A chaining group runs more than one subcommand in one command line, in the order given. Each subcommand’s options must appear before its arguments: within a chain, options and arguments of a subcommand are not mixed, so an option token placed after a chained subcommand’s argument is not bound to that subcommand’s option.
- The group’s result callback, if registered, runs after the chain. In chain mode it receives the list of subcommand return values in command-line order plus the group’s own parameters (an empty list when no subcommand ran). In non-chain mode it receives the single subcommand return value, or the group’s own return when no subcommand ran. Return values are otherwise ignored when the group is a standalone program.
- With standalone mode off, invoking a chaining group returns the list of the dispatched subcommands’ return values in command-line order, whether or not a result callback is registered.
- If the chaining group is also set to invoke without a command, an empty pipeline still runs the result callback instead of showing help. (A common author pattern, not itself a built-in command, is for subcommands to return processor callables that the result callback applies in order to an input stream.)
- When chaining, asking the invocation context for the current subcommand name does not yield any one child’s name; the value is distinguishable from a single child name and from “no subcommand”.

**Boundary / error behavior:**

- Only the last command in a chain may use a variadic (consume-rest) argument; a consume-rest argument on a non-last command is not refused at declaration, but it consumes the remaining tokens so later command names are not dispatched.
- Groups cannot be nested under a chaining group: attaching a group beneath a chaining group is refused at declaration time. Leaf commands can be attached.
- Files opened as a chained subcommand’s parameter type are closed when that subcommand’s callback returns, so later pipeline processors must not use them; the chaining group’s own files stay available to the result callback.

---

### FP-11: Terminal output and interaction helpers

**Public entry:** Echo (including to standard error), styling, styled echo, unstyling, pager output (including a writable pager stream), progress bars, reading a single character, pause until a key, launching an editor, launching an application, clearing the screen, looking up a per-user application config directory, wrapping text, opening files/streams (shared with FP-09), and binary/text standard-stream accessors.

**Normal behavior:**

- Echo writes text or binary to standard output by default, with a trailing newline unless suppressed. It can write to standard error instead. It is robust to misconfigured terminals where ordinary printing of Unicode would fail: on a standard stream whose declared encoding is ASCII-only, echo writes the text encoded as UTF-8 instead of failing or dropping characters. It never adds styles to plain text. When the stream is not a terminal, ANSI styles in the text are stripped; when it is a terminal, styles are kept. The invocation may force color on (styles kept even when the stream is not a terminal), force color off (styles stripped even on a terminal), or leave autodetection; echo follows the color flag of the context current on its thread, and a thread that has not entered the context autodetects.
- Styling wraps text with ANSI styles. Named foreground/background colors are the finite set: black, red, green, yellow, blue, magenta, cyan, white, bright_black, bright_red, bright_green, bright_yellow, bright_blue, bright_magenta, bright_cyan, bright_white, and reset; a background color is styled differently from the same foreground color, and different names are styled differently. Color may also be an integer in 0–255 inclusive or a sequence of exactly three integers each in 0–255 inclusive (RGB). Independent style switches: bold, dim, underline, overline, italic, blink, reverse, strikethrough; each switch changes the styling, and a combination of switches differs from each switch alone. By default a reset is appended so styles do not leak. Any other color value fails the style call; that call does not succeed as if the color was omitted. Styled echo is echo plus styling in one step. Unstyling removes ANSI sequences and leaves all other text.
- Pager output writes long text through a pager when the session is interactive; the pager command is the one named by the `PAGER` environment variable when it is set. When not interactive, the text is written to standard output without launching any pager. Authors may pass a complete string, an iterator of chunks, or use a writable pager stream; all text written reaches the destination in order. Chunked pager output is flushed as it is written, so each chunk reaches the pager before the next chunk is requested. Styles are kept or stripped according to what that destination supports. A pager that writes to the process standard output does not close that real stream when it finishes.
- A progress bar wraps an iterable (or a known length without an iterable) and, when attached to a terminal (standard output is a terminal), shows advancing progress, plus a remaining-time estimate that changes with elapsed time when the length is known. Every item is still visited, in order, when there is no terminal or when the bar is explicitly hidden. Authors may set a label: with no terminal that label is still printed once; an explicitly hidden bar prints nothing anywhere. Irregular advances use an explicit length and an update of a delta rather than one-step-per-item, and the shown progress reflects the delta.
- Single-character input reads one character from the terminal even if standard input is a pipe (piped bytes are not consumed). Interrupt and end-of-file key sequences become interrupt and end-of-file failures, distinct from each other, not raw characters.
- Pause prints a short message and waits for a key when the session is interactive; when not interactive it does nothing and does not block.
- Editor launch runs the given editor command (or the user’s editor), giving it the path of the file to edit as an argument, on a string (returns the saved text, or absent if the user quits without saving) or on a filename (the file receives the edits; no text is returned).
- Application launch opens a URL or filename with the default associated application, which on Linux is the application chosen by the desktop environment’s standard opener program found on the search path, and passes it the URL or filename. A `locate` argument may be accepted; whether a file manager is actually opened depends on the desktop session.
- Screen clear clears the visible terminal; when not connected to a terminal it does nothing.
- Application directory: given an application name, the path is the platform config location for the platform the Python runtime reports (`sys.platform`). On Unix the folder name is the application name lowercased with each run of whitespace replaced by a single dash; it sits under the user’s config home (`$XDG_CONFIG_HOME` when that variable is set, otherwise `.config` in the home directory). On macOS the folder is the application name as given, under `Library/Application Support` in the home directory. A POSIX-forced mode, on POSIX systems, uses the home directory joined with a dot followed by the Unix folder name, regardless of `XDG_CONFIG_HOME`.
- Text wrapping accepts any string without failing.

**Boundary / error behavior:**

- Echo to a non-terminal strips styles; echo to a terminal keeps them. Forced color on or off overrides that autodetection.
- Progress bars do not require a tty to iterate; they must not skip items when there is no terminal or when explicitly hidden.
- Pause must not block in non-interactive runs.
- Invalid style colors raise an error at the helper call, distinct from writing the original unstyled text.

---

### FP-12: Shell completion

**Public entry:** Completion mode on an installed executable, selected by an environment variable whose name is underscore + the executable name in uppercase with dashes turned into underscores + `_COMPLETE`. Built-in shells are the finite set: `bash`, `zsh`, `fish`, `powershell`. Two instruction families exist: `{shell}_source` prints the script the user sources to register completion; `{shell}_complete` prints suggestions for the current incomplete token.

**Normal behavior:**

- Completion mode is selected only by the variable derived from the program name the command was invoked under; a completion variable derived from any other name is ignored and the command runs normally.
- After registration, completing a command name suggests subcommands. Completing after a dash suggests option names, including the help option. A choice type suggests only its allowed values that match the incomplete prefix (all of them for an empty prefix). File and path types do not list filesystem entries as ordinary suggestions: they ask the shell to complete paths, carrying the incomplete token, and a path type that allows directories but not files asks for directories only. Hidden commands and hidden options are never suggested, whatever the incomplete token. Options are listed only once at least a dash has been typed.
- Built-in source modes: `bash_source`, `zsh_source`, `fish_source`, `powershell_source`. Each prints a shell-specific script, not the application’s normal command output, and does not run the command callback.
- Built-in complete modes: `bash_complete`, `zsh_complete`, `fish_complete`, `powershell_complete`. Each reads the incomplete command line from that shell’s completion environment (the word list and which word is incomplete) and writes suggestions, then exits without running the command callback. The suggestion stream is distinguishable from ordinary command output and from the registration script.
- Authors may attach a completion function to a parameter, or implement completion on a custom type; the function’s suggestions replace the type’s. Suggestions may include a help string. Zsh and Fish display that help next to the value; Bash and PowerShell still suggest the value without requiring that help to appear. A completion function receives the current context (with already-parsed values), the parameter, and the incomplete token (possibly empty).

**Boundary / error behavior:**

- An incomplete token that matches nothing yields an empty suggestion list, not a usage error.
- Hidden names that are omitted from suggestions remain valid if fully typed (FP-02, FP-06).
- An unrecognized instruction value for the completion variable is not treated as a successful source or complete run: the command callback does not run, and the process prints neither a registration script nor a suggestion stream.

---

### FP-13: Usage failures, abort, and exit status

**Public entry:** Standalone program invocation of any command or group; author-initiated clean stop and abort (including from confirm); conversion and usage failures from FP-03–FP-09.

**Normal behavior:**

When run as a standalone program:

- Success (callback completed, or intentional help/version that exited after printing) yields exit status **0**. An author-requested clean stop from inside a callback exits with status 0 when no status is given, and with exactly the status the author supplied otherwise; work after the stop does not run.
- Usage errors — unknown option, unknown subcommand, missing required parameter, conversion failure, incorrect combination — yield a usage-error exit status (**2**). A message is written to standard error that distinguishes the failure from success. The command callback does not run. When the error is “group invoked with no subcommand” under default no-args-is-help, the help page is also shown (FP-02).
- Abort — user declined a confirming abort, end-of-file on a prompt, keyboard interrupt translated into abort, or an author abort — yields a non-zero abort-class exit (**1**), writes an abort indication to standard error that is distinguishable from a usage error and from success, and does not run the remaining command work.
- Other Optlyn-signaled user errors that are not usage errors use a general error exit (**1**) and show an error description on standard error.

When standalone program mode is disabled, those failures propagate to the integrator and the process is not implicitly exited; return values bubble to the caller (FP-01, FP-10). An author clean stop then simply ends the callback without an error.

**Boundary / error behavior:**

- Intentional help is status 0; missing-subcommand help is status 2. Those two must not be collapsed.
- Keyboard interrupt and end-of-file are treated as abort in standalone mode, not as success.
- A usage error identifies the offending parameter when the failure is about a parameter (bad value, missing required), as distinct from an unknown option/command failure.

---

### FP-14: In-process runner

**Public entry:** Optlyn’s runner helpers: a runner that invokes a command with a list of argument tokens (and optional input, environment, program name, terminal width, color, and context settings) and a result object; an isolated-filesystem helper.

**Normal behavior:**

- Invoking a command through the runner executes that command as if from the command line and returns a result that exposes: exit status, captured standard output (text and bytes), captured standard error separately (text and bytes), the combined captured output, and any exception raised by the callback.
- Subcommands are selected by including their names in the argument token list.
- Extra keywords on invoke are passed as invocation-context settings. An environment supplied to one invoke applies to that invoke only.
- Isolated filesystem: a context that sets the current working directory to a new empty directory. File-parameter commands can create and read files there without touching the original working directory. When no parent is given, the runner removes that directory on exit; when a parent path is supplied, the new directory is created as a child under that parent and is left in place.
- Input supplied to invoke is fed to standard input. Visible prompts echo the typed line into the captured output; hidden prompts do not. An optional runner mode also echoes standard-input reads into captured output, not only prompt echoes: it echoes exactly the input that was actually read, never input that remained unread.
- Capture has two modes: interpreter-stream capture (default), which records writes through the interpreter’s standard streams; and file-descriptor capture, which records OS-level writes to descriptors 1 and 2 as well as interpreter writes. Default capture does not provide a real file descriptor on those streams and does not record OS-level descriptor writes. Under file-descriptor capture the interpreter’s standard output and standard error streams report a real file descriptor, and OS-level writes to descriptor 1 are captured as standard output and those to descriptor 2 as standard error.

**Boundary / error behavior:**

- The runner changes interpreter state and is not thread-safe.
- If the command raises, the result still carries an exit status and the exception is inspectable on the result, unless the runner is told not to catch exceptions, in which case the exception propagates out of invoke. With standalone mode off, a raised exception is likewise inspectable on the result.
- Isolated filesystem does not by itself mock Optlyn; commands that write files must actually write them inside the sandbox.

---

## Cross-cutting refinements

- **FP-02 vs FP-13:** Intentional help is a successful documentation request (exit 0, callback skipped). Help shown because the invocation was incorrect is a usage failure (exit 2).
- **FP-03 vs FP-07 vs FP-08:** The same option may be filled from command line, environment, default map, declared default, or prompt. FP-03 states precedence; FP-07 states prefix and source inspection; FP-08 states when a prompt actually runs. A command-line value never prompts; a callable default may still prompt.
- **FP-06 vs FP-10:** Nesting is the default group behavior. Chaining is an explicit group mode that forbids nested groups and changes return-value shape. FP-10 refines FP-06 only for groups declared as chaining.
- **FP-09 vs FP-11:** Opening `-` as a file parameter and opening `-` through the file-open helper obey the same stdin/stdout rule.
- **Hidden names:** Omitted from help (FP-02) and completion (FP-12), still dispatchable (FP-06) and still parsed (FP-03).
