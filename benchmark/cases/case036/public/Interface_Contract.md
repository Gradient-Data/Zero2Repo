# Interface Contract

The Python package is `velun`, importable from the product working directory. Command invocations use the active Python interpreter with `-m velun`, `-m velun.velunexmerge`, `-m velun.velunexdocs`, or `-m velun.velunexplan`. Input and output paths can be absolute; relative artifact paths for execution and result post-processing are relative to the selected output directory, and other relative paths are relative to the invocation working directory. Python interfaces accept `pathlib.Path` where a path is specified below.

`stdout` and `stderr` are separate process byte streams. Console and generated text documents use UTF-8; binary file and network interfaces exchange bytes. Native data and caller-owned Python extension modules are read from caller-selected filesystem paths.

## `velun`

### Invocation

`python -m velun [options] <source> ...` accepts suite files and directories as positional arguments.

| Option syntax | Argument form |
| --- | --- |
| `--outputdir <directory>` | Artifact directory |
| `--output <path>` | Structured result path |
| `--log <path>`; `--report <path>` | HTML artifact paths |
| `--xunit <path>`; `--debugfile <path>` | Additional artifact paths |
| `--legacyoutput` | Compatibility output switch |
| `--language <language>` | Language name, code, or extension path |
| `--extension <extensions>` | Colon-separated extensions |
| `--parseinclude <pattern>` | Source name or path selector; repeatable |
| `--name <name>`; `--doc <text>` | Top-level suite information |
| `--metadata <name>:<value>` | Metadata entry; repeatable |
| `--settag <tag>` | Tag; repeatable |
| `--suite <pattern>`; `--test <pattern>` | Name selectors; repeatable |
| `--include <expression>`; `--exclude <expression>` | Tag selectors; repeatable |
| `--rerunfailed <path>`; `--rerunfailedsuites <path>` | Saved-result path |
| `--runemptysuite` | Empty-selection switch |
| `--variable <name>:<value>` | Execution variable; repeatable |
| `--variablefile <path>` | Variable file; repeatable |
| `--pythonpath <directory>` | Python import search path; repeatable |
| `--argumentfile <path>` | Text argument-file path |
| `--randomize <mode>[:<seed>]` | Order mode and optional integer seed |
| `--dryrun`; `--nostatusrc`; `--exitonerror`; `--exitonfailure`; `--skipteardownonexit` | Execution switches |
| `--skip <tag>`; `--skiponfailure <tag>` | Tag selectors |
| `--rpa`; `--norpa` | Execution-mode switches |
| `--loglevel <level>` | Recording threshold |
| `--console <mode-or-class>` | Console presentation or extension |
| `--consolecolors <value>`; `--consolelinks <value>` | Console decoration settings |
| `--suitestatlevel <depth>` | Statistics hierarchy depth |
| `--tagstatinclude <pattern>`; `--tagstatexclude <pattern>` | Statistics selectors; repeatable |
| `--tagstatcombine <expression>:<label>` | Statistics group; repeatable |
| `--tagdoc <tag>:<text>` | Tag documentation |
| `--tagstatlink <tag>:<url>:<title>` | Tag link |
| `--listener <extension>[:<argument>...]` | Listener; repeatable |
| `--prerunmodifier <extension>[:<argument>...]` | Suite visitor; repeatable |
| `--parser <extension>[:<argument>...]` | Source parser; repeatable |

`VELUN_OPTIONS` is an environment entry containing space-separated command options. Argument files contain one option and its value per line, including values containing spaces.

### Outcomes and console carriers

Exit `0` denotes completion without a failure-based process status. Completed executions with failed tests use an integer from `1` through `250`; the value is the failed-test count capped at `250`. Invalid input or configuration exits `252`. With `--nostatusrc`, completed test failures also exit `0`. Configuration and execution diagnostics use `stderr` with the label `[ ERROR ]`; warnings use `stderr`. Diagnostics carry the affected source, library, option, or language identity and location when applicable.

Detailed console output on `stdout` carries test names and status markers such as `| PASS |`. Its summary has the form `<total> tests, <passed> passed, <failed> failed` or `<total> tasks, <passed> passed, <failed> failed`. Dotted progress uses a line of `.`, `F`, and `s` for passed, failed, and skipped tests, followed by summary counts. Library console writes are on `stdout`.

Artifact names are `output.xml`, `log.html`, and `report.html` beneath the selected output directory when their path options are omitted. The path argument `NONE` is the artifact-disabling spelling.

Console mode spellings are `verbose`, `dotted`, `quiet`, and `none`. Recording-threshold spellings are `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, and `NONE`. Randomization syntax uses `none`, `suites`, `tests`, or `all`, optionally followed by a colon and integer seed.

Name and tag pattern syntax uses `*`, `?`, and bracketed character sets. Tag expressions join patterns with `AND`, `OR`, and `NOT`; `NOT` can also prefix a pattern. Source-path pattern syntax also includes `**`.

The `--consolecolors` and `--consolelinks` options accept `off` as a decoration selector.

Exit `253` denotes a user interruption during source preparation, with a diagnostic on `stderr` labelled `[ ERROR ]`. `SIGINT` is the external interruption signal.

## `velun.velunexmerge`

`python -m velun.velunexmerge [options] <result-path> ...` accepts saved XML and JSON result paths.

| Option syntax | Argument form |
| --- | --- |
| `--outputdir <directory>`; `--output <path>` | Artifact directory and structured output |
| `--log <path>`; `--report <path>`; `--xunit <path>` | HTML and xUnit output paths |
| `--rpa` | Task-mode switch |
| `--suite <pattern>`; `--test <pattern>`; `--include <expression>` | Selection options |
| `--name <name>`; `--doc <text>`; `--metadata <name>:<value>` | Suite overrides |
| `--tagstatinclude <pattern>` | Statistics selection; repeatable |
| `--merge` | Merge operation switch |
| `--removekeywords <selector>`; `--flattenkeywords <selector>` | Detail selectors; repeatable |
| `--pythonpath <directory>` | Extension import path |
| `--prevelunexmergemodifier <extension>[:<argument>...]` | Result visitor; repeatable |

The selected structured output can be named `output.xml`. `NONE` is the disabling path spelling. Successful completion exits `0`; failed-test results use `1` through `250`; invalid input exits `252` and carries a diagnostic on `stderr`.

Removal selector syntax is `all`, `passed`, `for`, `while`, `wuks`, `name:<pattern>`, or `tag:<pattern>`. Flattening selector syntax is `for`, `while`, `iteration`, `name:<pattern>`, or `tag:<pattern>`.

## `velun.api`

The module `velun.api` exposes `TestSuite`, `TestSuiteBuilder`, `ExecutionResult`, `ResultVisitor`, `ResultWriter`, `SuiteVisitor`, and `Language`. It also exposes the library logging module as `logger`.

## `velun.api.parsing`

The module `velun.api.parsing` exposes `get_model`, `get_init_model`, `get_tokens`, `Token`, `ModelVisitor`, and the syntax-node class `TestCase`.

## `velun.errors`

The module `velun.errors` exposes the exception class `DataError`.

## `velun.errors.DataError`

`DataError` is the catchable exception class for rejected executable construction and unreadable or malformed result input. Its message is diagnostic text.

## `velun.api.TestSuite`

`TestSuite(name=..., doc=..., metadata=..., source=...)` constructs an executable suite. `name` and `doc` are strings, `metadata` maps strings to strings, and `source` is a path.

Class methods are `from_file_system(*paths)`, `from_model(model)`, `from_string(string, lang=...)`, `from_dict(data)`, and `from_json(path)`. They return a `TestSuite`. A rejected construction raises `DataError`.

Suite fields are `name: str`, `doc: str`, `metadata: mapping`, `rpa: bool`, `suites: sequence`, `tests: sequence`, and `resource`. Suite and test sequences support iteration, indexing, length, and assignment from a member list. Construction uses `suites.append(suite)`, `suites.create(name=...)`, and `tests.create(name=..., tags=...)`; the two `create` methods return the created member. Tags support iteration, membership, length, `add(tag)`, and assignment from a string sequence.

Test members expose `name`, `doc`, `tags`, `setup`, `teardown`, `timeout`, `template`, and editable `body`. Fixture and keyword calls expose `name: str` and `args: tuple`. `timeout` and `template` are strings or `None`. `body` supports indexing, iteration, assignment from a list, and `create_keyword(name, args=...)`, also callable with `name=...`.

`resource.imports` is an iterable with import `type` and `name` strings. Its type labels are `LIBRARY`, `RESOURCE`, and `VARIABLES`. `resource.variables` members expose `name` and iterable `value`. `resource.keywords` supports iteration and `create(name=..., args=...)`; created user keywords expose `name` and `body` with `create_keyword`.

`to_dict()` returns nested suite data. `to_json(path)` writes that data as JSON. Suite objects have `name`, `doc`, `rpa`, `metadata`, `suites`, `tests`, and `resource` keys when present in exchanged data. Test objects have `name`, `doc`, `tags`, and `body`, plus `setup`, `teardown` (objects with `name` and `args`) and `timeout` when declared; keyword-call objects have `name` and `args`; `resource` has `keywords`, whose members have `name`, `args`, and `body`.

`run(output=..., log=..., report=..., console=...)` returns an execution result exposing `suite`, whose tests expose `status` strings. The status label for successful execution is `PASS`.

The `output`, `log`, and `report` options accept paths or `None`. The `console` option accepts the selector `none`.

## `velun.api.TestSuiteBuilder`

`TestSuiteBuilder(custom_parsers=..., included_extensions=...)` accepts parser objects and extension strings as sequences. Both arguments can be omitted. `build(*paths)` accepts file or directory paths and returns an executable `TestSuite`. Parser objects expose `extension: str` and `parse(source, defaults)`.

## `velun.api.parsing.get_model`

`get_model(source, lang=...)` accepts a filesystem path or readable text stream and returns a syntax `File`. `lang` accepts a language name. The language argument can be omitted.

## `velun.api.parsing.get_init_model`

`get_init_model(source)` accepts an initialization-file path and returns a syntax `File`.

## `velun.api.parsing.get_tokens`

`get_tokens(source)` accepts a source path and returns an iterable of `Token` objects.

## `velun.api.parsing.Token`

`Token.KEYWORD` and `Token.ARGUMENT` are token-kind constants. A token exposes `type`, editable `value: str`, `lineno: int`, `col_offset: int`, and `error`, which carries a diagnostic string or an absent value. Line numbers are one-based; columns are zero-based.

## `velun.api.parsing.ModelVisitor`

`ModelVisitor()` is subclassable. `visit(model)` accepts the syntax root. The callback `visit_KeywordCall(node)` receives nodes exposing `keyword: str` and `get_token(Token.ARGUMENT)`, which returns an editable token.

## `velun.api.parsing.File`

The syntax root is compatible with Python `ast.walk`. It exposes `source`, its source path, and `save(path)`, which writes native source text. Traversed nodes expose `lineno: int` and `errors: tuple[str, ...]`; statements can expose iterable `tokens`. Diagnostics carry the invalid construct and its position.

## `velun.api.parsing.TestCase`

`TestCase` is the syntax-node class usable in `isinstance(node, TestCase)` during `ast.walk`. Its `name` is a string.

## `velun.api.Language`

`Language` is a subclassable class exported from `velun.api`. A custom-language module supplies class attributes `settings_header`, `test_cases_header`, `documentation_setting`, and `tags_setting` as strings, and `given_prefixes`, `true_strings`, and `false_strings` as lists of strings.

Built-in language selectors accept the full language names. The code `fi` denotes Finnish and `zh-CN` denotes Chinese Simplified.

## `velun.api.ExecutionResult`

`ExecutionResult(path)` accepts an XML or JSON result path and returns an editable result. Invalid result input raises `DataError`.

The result has `suite`, `errors`, and `statistics`. The suite exposes editable `name`, `doc`, and `metadata`, and indexed iterable `suites` and `tests`. Tests expose editable `name`, `status`, `message`, `doc`, `tags`, and `body`. `tags` supports iteration, `add(tag)`, and list assignment. `body.clear()` and `body.create_message(message=..., level=...)` expose result edits.

Suite, test, and executable body items expose `start_time: datetime` and `elapsed_time: timedelta`. Error and message objects expose `level: str` and `message: str`. `statistics.total` exposes integer `passed`, `failed`, and `skipped` counts.

`visit(visitor)` accepts a result visitor. `save(path)` writes XML or JSON result content at the requested path.

## `velun.api.ResultVisitor`

`ResultVisitor()` is subclassable. Through `result.visit(visitor)`, callbacks `start_suite(suite)`, `visit_test(test)`, and `visit_message(message)` receive the public result objects. Message callbacks expose `level` and `message`; suite and test callbacks expose editable result fields.

## `velun.api.SuiteVisitor`

`SuiteVisitor()` is subclassable. The callback `start_suite(suite)` receives an executable suite with editable `name`, `metadata`, `suites`, and `tests`; test members expose editable `name`, `tags`, and `body`.

## `velun.api.ResultWriter`

`ResultWriter(result).write_results(outputdir=..., log=..., report=...)` accepts an execution result object, an output directory string, and HTML filenames. It writes the selected log and report files under that directory.

## `velun.api.deco`

The module `velun.api.deco` exposes `keyword` and `not_keyword`.

## `velun.api.deco.keyword`

`keyword` is usable as `@keyword`, `@keyword(<name>, tags=...)`, or `@keyword(types=...)`. It decorates a Python callable. The optional name is a string; tags are a sequence of strings; `types` is a parameter-name mapping to Python type hints, or `None`.

## `velun.api.deco.not_keyword`

`@not_keyword` decorates a Python callable in a library.

## `velun.api.types`

The module `velun.api.types` exposes `Secret`.

## `velun.api.types.Secret`

`Secret(value)` returns a secret value object. Its `value` attribute exposes the wrapped Python value. The class is usable as a Python parameter annotation and for `isinstance` checks.

## `velun.api.logger`

The module is importable with `from velun.api import logger`. It exposes `info(message)`, `warn(message)`, and `console(message)`. Messages accept caller text. Log records expose that text in the corresponding keyword's message carrier; `console` writes directly to `stdout`.

## `.velun`

Native files use the `.velun` extension and text table rows. Space tables separate cells with two or more spaces; pipe tables use `|` cell delimiters. `\` introduces escaping, `...` marks continuation rows, and `#` marks comments.

Section headers are `*** Settings ***`, `*** Variables ***`, `*** Test Cases ***`, `*** Tasks ***`, and `*** Keywords ***`. Declarations start in the first cell. Executable body rows are indented; a call row carries `<keyword>    <argument> ...`. A qualified call uses `<provider>.<keyword>`.

Settings are `Name`, `Documentation`, `Metadata`, `Library`, `Resource`, `Variables`, `Suite Setup`, `Suite Teardown`, `Test Setup`, `Test Teardown`, `Test Timeout`, `Test Template`, `Test Tags`, and `Default Tags`. `Metadata` carries a name and value. Import settings carry a name or path followed by arguments. Library aliases use `AS` or `WITH NAME` followed by the alias.

Per-test and per-keyword setting rows use `[Documentation]`, `[Tags]`, `[Setup]`, `[Teardown]`, `[Timeout]`, `[Template]`, and `[Arguments]`. Argument declarations use `${name}`, `${name}=<default>`, `${name: type}`, `@{name}`, `@{}`, and `&{name}`. Embedded keyword-name slots use `${argument}` or `${argument:pattern}`. A named call argument is `name=<value>`. `RETURN` is followed by value cells. Assignment places scalar targets and an optional list target before the call, optionally ending the assignment with `=`.

Variable references use `${name}`, `@{name}`, `&{name}`, or `%{name}`; optional environment lookup is `%{name=<replacement>}`. Indexed access is `${name}[<index-or-key>]`, slicing uses `[<start>:<end>]`, and attribute access is `${name.<attribute>}`. Typed declarations use `${name: type}`. `VAR` accepts a variable target, value cells, and named `scope` or `separator` cells. A mapping declaration uses `key=<value>` cells. Object references in expression cells use `$name`.

Automatic variable names are `${CURDIR}`, `${EXECDIR}`, `${TEMPDIR}`, `${/}`, `${:}`, `${\n}`, `${SPACE}`, `${EMPTY}`, `${True}`, `${False}`, `${None}`, `@{EMPTY}`, `&{EMPTY}`, `${SUITE NAME}`, `${SUITE DOCUMENTATION}`, `${SUITE METADATA}`, `${SUITE STATUS}`, `${SUITE MESSAGE}`, `${TEST NAME}`, `${TEST DOCUMENTATION}`, `${TEST TAGS}`, `${TEST STATUS}`, `${TEST MESSAGE}`, `${PREV TEST NAME}`, `${PREV TEST STATUS}`, `${PREV TEST MESSAGE}`, `${OUTPUT DIR}`, `${OUTPUT FILE}`. Numeric references have the form `${<number>}`.

Block syntax uses `IF <condition>`, `ELSE IF <condition>`, `ELSE`, and `END`. Inline `IF` has branch keyword and argument cells on its row, with optional assignment targets. Loops use `FOR <variable> ... IN <value> ...`, `IN RANGE`, `IN ENUMERATE` with an optional `start` cell, or `IN ZIP` with optional `mode` and `fill` cells, ending in `END`. `WHILE` accepts an optional condition and named `limit` and `on_limit` cells. `BREAK` and `CONTINUE` are standalone statements.

Failure-handler blocks use `TRY`, `EXCEPT <pattern> ...`, an optional `type=<match-type>` cell, optional `AS ${target}`, `ELSE`, `FINALLY`, and `END`. Group blocks use `GROUP [<name>]` and `END`.

Reserved tag names exchanged through `[Tags]` and tag options include `velun:private`, `velun:continue-on-failure`, `velun:recursive-continue-on-failure`, `velun:stop-on-failure`, `velun:recursive-stop-on-failure`.

Inline expressions use `${{<expression>}}`. Type-hint syntax uses type names, bracketed type parameters, and `|` between union members. Scope selector spellings are `LOCAL`, `TEST`, `TASK`, `SUITE`, and `GLOBAL`. Parallel-loop mode spellings are `SHORTEST`, `STRICT`, and `LONGEST`; disabled loop limits use `NONE`, and successful limit completion uses `on_limit=pass`. Failure-handler matching selectors are `GLOB`, `REGEXP`, and `START`.

`NONE` is the disabling spelling in fixture, template, and timeout cells. A test tag cell of the form `-<tag-pattern>` removes inherited matching tags. Variable-setting and optional-lookup keywords accept a variable name as `$<name>` or as a literal `${<name>}`; `\` escapes a variable reference when it must be passed literally.

Type declaration spellings include `int`, `float`, `Decimal`, `bool`, `str`, `bytes`, `bytearray`, `list`, `tuple`, `set`, `frozenset`, `dict`, `date`, `datetime`, `timedelta`, `Path`, `None`, `Secret`, `Any`, and `object`. Python library annotations additionally use `Sequence`, `Mapping`, `Literal`, enum classes, and `TypedDict` classes; `NotRequired` marks optional typed-dictionary entries. Fixed and repeated tuple forms are `tuple[T, U]` and `tuple[T, ...]`.

## `__init__.velun`

A directory initialization source is named `__init__.velun` within the suite directory. It uses native text sections and settings.

## `.resource`

A native resource file uses the `.resource` extension. Its text uses `*** Settings ***`, `*** Variables ***`, and `*** Keywords ***` sections, with the same cell, import, variable, and keyword-declaration forms as native suite files. `Resource <path>` is a Settings row with the path in its own cell.

## `.velun.rst`

A `.velun.rst` input is reStructuredText containing a `.. code:: velunexsuite` directive and an indented native table block beneath it.

## `.velun.md`

A `.velun.md` input is Markdown containing a fenced block opened with three backticks followed by `velunexsuite`, and closed with three backticks. The block contains native table text.

## `.rbt`

A `.rbt` input is a JSON object describing an executable suite. Suite keys are `name: str`, `doc: str`, `rpa: bool`, `metadata: object`, `tests: array`, `suites: array`, and `resource: object` when supplied. A test object has `name`, `doc`, `tags: array[str]`, and `body: array`. A keyword call has `name: str` and `args: array`. The resource's `keywords` array contains keyword objects with `name`, `args`, and `body`.

## `Variables`

The native import row is `Variables <path> [<argument> ...]` with separate table cells. Python variable files expose module attributes or `get_variables(*arguments)`, which returns a mapping from variable names to Python values. YAML and JSON variable files contain a top-level mapping with variable names as keys and values as data.

## `velun.libraries.BuiltIn.BuiltIn`

A standard keyword call can use the `BuiltIn.` prefix. Positional parameters below are table cells; bracketed parameters can be omitted. Named options use their parameter name followed by `=`. Assertion and control calls expose their outcome through execution status and diagnostic carriers.

| Keyword | Argument cells | Result carrier |
| --- | --- | --- |
| `Convert To Integer` | `item [base]` | int |
| `Convert To Number` | `item [precision]` | float |
| `Convert To Binary` | `item` | str |
| `Convert To Octal` | `item` | str |
| `Convert To Hex` | `item` | str |
| `Convert To String` | `item` | str |
| `Convert To Boolean` | `item` | bool |
| `Convert To Bytes` | `input [input_type]` | bytes |
| `Create List` | `*items` | list of supplied Python values |
| `Create Dictionary` | `*items` | mapping |
| `Should Be True` | `condition` | assertion outcome |
| `Should Not Be True` | `condition` | assertion outcome |
| `Should Be Equal` | `first second [msg] [values] [ignore_case] [strip_spaces] [collapse_spaces] [type] [types]` | assertion outcome |
| `Should Not Be Equal` | `first second` | assertion outcome |
| `Should Be Equal As Integers` | `first second` | assertion outcome |
| `Should Be Equal As Numbers` | `first second [precision]` | assertion outcome |
| `Should Be Equal As Strings` | `first second` | assertion outcome |
| `Should Be Empty` | `item` | assertion outcome |
| `Should Not Be Empty` | `item` | assertion outcome |
| `Length Should Be` | `item length` | assertion outcome |
| `Should Contain` | `container item` | assertion outcome |
| `Should Not Contain` | `container item` | assertion outcome |
| `Should Contain Any` | `container *items` | assertion outcome |
| `Should Not Contain Any` | `container *items` | assertion outcome |
| `Should Contain X Times` | `container item count` | assertion outcome |
| `Should Start With` | `str1 str2` | assertion outcome |
| `Should Not Start With` | `str1 str2` | assertion outcome |
| `Should End With` | `str1 str2` | assertion outcome |
| `Should Not End With` | `str1 str2` | assertion outcome |
| `Should Match` | `string pattern` | assertion outcome |
| `Should Not Match` | `string pattern` | assertion outcome |
| `Should Match Regexp` | `string pattern [flags]` | matched string, or list containing full match and capture values |
| `Should Not Match Regexp` | `string pattern` | assertion outcome |
| `Get Length` | `item` | int |
| `Get Count` | `container item` | int |
| `Set Variable` | `*values` | supplied object, or list of supplied objects |
| `Get Variable Value` | `name [default]` | Python value or None |
| `Get Variables` | `` | mapping from decorated variable names to Python values |
| `Variable Should Exist` | `name` | assertion outcome |
| `Variable Should Not Exist` | `name` | assertion outcome |
| `Set Test Variable` | `name *values` | variable assignment |
| `Set Suite Variable` | `name *values` | variable assignment; the named option `children` is accepted |
| `Set Global Variable` | `name *values` | variable assignment |
| `Evaluate` | `expression [modules] [namespace]` | Python expression result |
| `Call Method` | `object method_name *args **kwargs` | Python method result |
| `Run Keyword` | `name *args` | called keyword result |
| `Run Keyword And Return Status` | `name *args` | bool |
| `Run Keyword And Ignore Error` | `name *args` | two-item tuple (status, value-or-reason), status PASS or FAIL |
| `Run Keyword And Warn On Failure` | `name *args` | execution outcome and warning message carrier |
| `Run Keyword And Continue On Failure` | `name *args` | execution outcome |
| `Run Keyword And Expect Error` | `expected_error name *args` | caught diagnostic str |
| `Repeat Keyword` | `repeat name *args` | execution outcome |
| `Wait Until Keyword Succeeds` | `retry retry_interval name *args` | successful called result |
| `Regexp Escape` | `*strings` | escaped pattern str |
| `Catenate` | `*items` | str; optional first cell SEPARATOR=<text> |
| `Sleep` | `time_` | execution outcome |
| `No Operation` | `` | execution outcome |
| `Fail` | `msg` | failure outcome with caller message |
| `Fatal Error` | `msg` | fatal failure outcome with caller message |
| `Skip` | `msg` | skip outcome with caller message |
| `Pass Execution` | `message` | execution-control outcome with caller message |
| `Import Library` | `name *args` | library import |
| `Import Resource` | `path` | resource import |
| `Import Variables` | `path` | variable import |
| `Set Library Search Order` | `*search_order` | configuration outcome |
| `Keyword Should Exist` | `name` | assertion outcome |
| `Get Library Instance` | `[name] [all]` | active Python library object or mapping from import names to active objects |
| `Reload Library` | `name_or_instance` | library refresh outcome |
| `Set Test Documentation` | `doc` | documentation update |
| `Set Suite Documentation` | `doc` | documentation update |
| `Set Suite Metadata` | `name value` | metadata update |
| `Set Tags` | `*tags` | tag update |
| `Remove Tags` | `*tags` | tag update |
| `Set Test Message` | `message` | message update |
| `Log` | `message [level]` | message record |
| `Set Log Level` | `level` | previous threshold label str |
| `Reset Log Level` | `` | previous threshold label str |

`Run Keyword And Expect Error` accepts matcher prefixes `EQUALS:`, `STARTS:`, and `REGEXP:`. Regular-expression `flags` accepts `IGNORECASE`. Variable-listing keys have the form `${<name>}`.

The `strip_spaces` option accepts `LEADING` and `TRAILING` as selectors. The `type` option accepts the selector `AUTO`. The `Convert To Bytes` input-format selectors used in argument cells are `int`, `hex`, and `bin`.

`Repeat Keyword` count syntax is an integer optionally followed by `times`; duration syntax is a number followed by a time unit. Retry counts use an integer followed by `x` or `times`; elapsed retries use duration text. A strict retry interval has the form `strict: <duration>`.

## `velun.libraries.Collections.Collections`

The Library setting accepts `Collections`. Calls receive Python sequences, mappings, and element values through ordinary argument cells. Bracketed arguments are optional; options can be named.

| Keyword | Argument cells | Result carrier |
| --- | --- | --- |
| `Convert To List` | `item` | list |
| `Append To List` | `list_ *values` | list |
| `Insert Into List` | `list_ index value` | list |
| `Set List Value` | `list_ index value` | list |
| `Combine Lists` | `*lists` | list |
| `Remove Values From List` | `list_ *values` | list |
| `Remove From List` | `list_ index` | removed Python object |
| `Remove Duplicates` | `list_` | list |
| `Reverse List` | `list_` | list |
| `Sort List` | `list_` | list |
| `Get From List` | `list_ index` | Python object |
| `Get Slice From List` | `list_ [start] [end]` | list |
| `Get Index From List` | `list_ value [start] [end]` | int position |
| `Count Values In List` | `list_ value [start] [end]` | int count |
| `Copy List` | `list_ [deepcopy]` | sequence |
| `Get From Dictionary` | `dictionary key [default]` | Python value |
| `Set To Dictionary` | `dictionary *key_value_pairs **items` | mapping |
| `Remove From Dictionary` | `dictionary *keys` | mapping |
| `Pop From Dictionary` | `dictionary key [default]` | Python value |
| `Keep In Dictionary` | `dictionary *keys` | mapping |
| `Copy Dictionary` | `dictionary [deepcopy]` | mapping |
| `Get Dictionary Keys` | `dictionary [sort_keys]` | list of keys |
| `Get Dictionary Values` | `dictionary [sort_keys]` | list of values |
| `Get Dictionary Items` | `dictionary [sort_keys]` | flat list alternating key and value |
| `Lists Should Be Equal` | `list1 list2 [ignore_order] [ignore_case]` | assertion outcome |
| `List Should Contain Sub List` | `list1 list2` | assertion outcome |
| `List Should Contain Value` | `list_ value` | assertion outcome |
| `List Should Not Contain Value` | `list_ value` | assertion outcome |
| `List Should Not Contain Duplicates` | `list_` | assertion outcome |
| `Dictionaries Should Be Equal` | `dict1 dict2 [ignore_case] [ignore_keys]` | assertion outcome |
| `Dictionary Should Contain Sub Dictionary` | `dict1 dict2` | assertion outcome |
| `Dictionary Should Contain Key` | `dictionary key` | assertion outcome |
| `Dictionary Should Not Contain Key` | `dictionary key` | assertion outcome |
| `Dictionary Should Contain Item` | `dictionary key value` | assertion outcome |
| `Dictionary Should Contain Value` | `dictionary value` | assertion outcome |
| `Dictionary Should Not Contain Value` | `dictionary value` | assertion outcome |
| `Get Matches` | `list pattern [ignore_case] [ignore_whitespace]` | list of matching strings |
| `Get Match Count` | `list pattern` | int count |
| `Should Contain Match` | `list pattern` | assertion outcome |
| `Should Not Contain Match` | `list pattern` | assertion outcome |

Assertion failures use the keyword failure status and diagnostic message carriers. Pattern cells can use `regexp=<pattern>`.

Dictionary case-selection spellings are `KEYS` and `VALUES` for `ignore_case`.

## `velun.libraries.String.String`

The Library setting accepts `String`; qualified calls use `String.`. The Python class is importable as `velun.libraries.String.String`, with constructor `String()`. Its directly callable member is `generate_random_string(length=..., chars=...) -> str`; both arguments can be omitted. Keyword arguments below are cells and optional named cells.

| Keyword | Argument cells | Result carrier |
| --- | --- | --- |
| `Convert To Lower Case` | `string` | str or bytes |
| `Convert To Upper Case` | `string` | str or bytes |
| `Convert To Title Case` | `string [exclude=<patterns>]` | str or bytes |
| `Should Be Title Case` | `string [exclude=<patterns>]` | assertion outcome |
| `Strip String` | `string [mode=<selector>] [characters=<text>]` | str or bytes |
| `Split String To Characters` | `string` | list[str] |
| `Split String` | `string [separator] [max_split]` | list[str] |
| `Split String From Right` | `string [separator] [max_split]` | list[str] |
| `Get Substring` | `string start [end]` | str or bytes |
| `Split To Lines` | `string [start] [end]` | list[str] or list[bytes] |
| `Get Line` | `string line_number` | str or bytes |
| `Fetch From Left` | `string marker` | str or bytes |
| `Fetch From Right` | `string marker` | str or bytes |
| `Format String` | `template *positional **named` | str |
| `Replace String` | `string search_for replace_with [count]` | str or bytes |
| `Remove String` | `string *removables` | str or bytes |
| `Get Line Count` | `string` | int |
| `Get Lines Containing String` | `string pattern [ignore_case=<bool>]` | str |
| `Get Lines Matching Pattern` | `string pattern [ignore_case=<bool>]` | str |
| `Get Lines Matching Regexp` | `string pattern [partial_match] [flags]` | str |
| `Should Be String` | `item` | assertion outcome |
| `Should Not Be String` | `item` | assertion outcome |
| `Should Be Unicode String` | `item` | assertion outcome |
| `Should Be Byte String` | `item` | assertion outcome |
| `Should Be Lower Case` | `string` | assertion outcome |
| `Should Be Upper Case` | `string` | assertion outcome |
| `Encode String To Bytes` | `string encoding [errors]` | bytes |
| `Decode Bytes To String` | `bytes encoding [errors]` | str |
| `Generate Random String` | `[length] [chars]` | str |
| `Get Regexp Matches` | `string pattern *groups [flags]` | list[str] or list[tuple[str, ...]] |
| `Replace String Using Regexp` | `string pattern replace_with [count] [flags]` | str |
| `Remove String Using Regexp` | `string *patterns [flags]` | str |

Random-length syntax is `<lower>-<upper>`; character-group markers are `[LOWER]`, `[UPPER]`, `[LETTERS]`, `[NUMBERS]`, `[ARABIC]`, and `[POLISH]`. `exclude` accepts a comma-separated string or list of strings. Line-selection results use `\n` between lines. `flags` is a regular-expression flag-name string; capture selections are integers or names.

Trim-mode spellings are `both`, `left`, and `right`; the `flags` cell accepts `IGNORECASE`. Encoding error-policy spellings include `strict`, `replace`, and `ignore`.

## `velun.libraries.OperatingSystem.OperatingSystem`

The Library setting accepts `OperatingSystem`. Paths are string cells. File writes are observable at the supplied paths as text-encoded bytes or binary bytes. Environment names and values are strings. Bracketed cells are optional; named cells use the listed parameter names.

| Keyword | Argument cells | Result carrier |
| --- | --- | --- |
| `Get File` | `path [encoding]` | str |
| `Get Binary File` | `path` | bytes |
| `Grep File` | `path pattern [regexp]` | str containing newline-separated selected lines, without a trailing newline |
| `Create File` | `path [content] [encoding]` | filesystem write |
| `Create Binary File` | `path content` | filesystem write |
| `Append To File` | `path content [encoding]` | filesystem write |
| `Create Directory` | `path` | filesystem operation |
| `Copy File` | `source destination` | filesystem operation |
| `Move File` | `source destination` | filesystem operation |
| `Copy Files` | `*sources_and_destination` | filesystem operation |
| `Move Files` | `*sources_and_destination` | filesystem operation |
| `Copy Directory` | `source destination` | filesystem operation |
| `Move Directory` | `source destination` | filesystem operation |
| `Remove File` | `path` | filesystem operation |
| `Remove Files` | `*paths` | filesystem operation |
| `Remove Directory` | `path [recursive]` | filesystem operation |
| `Empty Directory` | `path` | filesystem operation |
| `Should Exist` | `path` | assertion outcome |
| `Should Not Exist` | `path` | assertion outcome |
| `File Should Exist` | `path` | assertion outcome |
| `File Should Not Exist` | `path` | assertion outcome |
| `Directory Should Exist` | `path` | assertion outcome |
| `Directory Should Not Exist` | `path` | assertion outcome |
| `File Should Be Empty` | `path` | assertion outcome |
| `File Should Not Be Empty` | `path` | assertion outcome |
| `Directory Should Be Empty` | `path` | assertion outcome |
| `Directory Should Not Be Empty` | `path` | assertion outcome |
| `List Directory` | `path [pattern] [absolute]` | list[str] of names or paths |
| `List Files In Directory` | `path [pattern] [absolute]` | list[str] of names or paths |
| `List Directories In Directory` | `path [pattern] [absolute]` | list[str] of names or paths |
| `Count Items In Directory` | `path [pattern]` | int |
| `Count Files In Directory` | `path [pattern]` | int |
| `Count Directories In Directory` | `path [pattern]` | int |
| `Wait Until Created` | `path [timeout]` | execution outcome |
| `Wait Until Removed` | `path [timeout]` | execution outcome |
| `Join Path` | `base *parts` | path str |
| `Join Paths` | `base *paths` | list[str] |
| `Normalize Path` | `path` | path str |
| `Split Path` | `path` | (directory, basename) tuple[str, str] |
| `Split Extension` | `path` | (stem, extension-without-dot) tuple[str, str] |
| `Get File Size` | `path` | int byte count |
| `Get Modified Time` | `path [format]` | int epoch seconds when format is epoch |
| `Set Modified Time` | `path mtime` | filesystem timestamp update |
| `Touch` | `path` | filesystem timestamp update |
| `Get Environment Variable` | `name [default]` | str or supplied default object |
| `Get Environment Variables` | `` | mapping[str, str] |
| `Set Environment Variable` | `name value` | environment update |
| `Append To Environment Variable` | `name *values [separator]` | environment update |
| `Remove Environment Variable` | `*names` | environment update |
| `Environment Variable Should Be Set` | `name` | assertion outcome |
| `Environment Variable Should Not Be Set` | `name` | assertion outcome |

## `velun.libraries.Process.Process`

The Library setting accepts `Process`. Command and argument cells carry strings or supplied Python objects. Optional process handles can be a returned reference or alias. Bracketed parameters are optional; configuration uses named cells.

| Keyword | Argument cells | Result carrier |
| --- | --- | --- |
| `Run Process` | `command *arguments [cwd] [env] [shell] [stdin] [stdout] [stderr] [output_encoding]` | process result |
| `Start Process` | `command *arguments [cwd] [env] [shell] [stdin] [stdout] [stderr] [output_encoding] [alias]` | process reference |
| `Wait For Process` | `[handle] [timeout] [on_timeout]` | process result or None |
| `Switch Process` | `handle` | selection outcome |
| `Get Process Id` | `[handle]` | int PID |
| `Is Process Running` | `[handle]` | bool |
| `Process Should Be Running` | `[handle]` | assertion outcome |
| `Process Should Be Stopped` | `[handle]` | assertion outcome |
| `Get Process Result` | `[handle]` | process result |
| `Terminate Process` | `[handle] [kill]` | process result |
| `Terminate All Processes` | `[kill]` | execution outcome |
| `Send Signal To Process` | `signal [handle]` | execution outcome |
| `Split Command Line` | `command [escaping]` | list[str] |
| `Join Command Line` | `*command` | str |

Process results expose `rc: int`, `stdout: str`, and `stderr: str`. Captured result text uses LF line endings and has one final newline removed when present. `env` accepts a mapping and per-entry configuration uses `env:<name>=<value>`. Redirection cells accept paths and the markers `STDOUT` and `DEVNULL`; `stdin` accepts text, a path, or a readable Python stream.

`on_timeout` selects `continue`, `terminate`, or `kill`. Signal names such as `USR1` are passed as string cells.

A `None` wait return denotes that no completed process result is available.

## `velun.libraries.DateTime`

The Library setting accepts `DateTime`. Date cells carry strings, numeric epoch values, Python date or datetime objects. Duration cells carry numbers, strings, or Python timedelta objects. Optional parameters can be named.

| Keyword | Argument cells | Result carrier |
| --- | --- | --- |
| `Convert Date` | `date [result_format] [exclude_millis] [date_format]` | formatted str, datetime.datetime, datetime.date, or float epoch seconds |
| `Convert Time` | `time [result_format] [exclude_millis]` | float seconds, str, or datetime.timedelta |
| `Get Current Date` | `[time_zone] [increment] [result_format]` | formatted str, datetime.datetime, or float epoch seconds |
| `Add Time To Date` | `date time [result_format]` | date result |
| `Subtract Time From Date` | `date time [result_format]` | date result |
| `Subtract Date From Date` | `date1 date2 [result_format]` | duration result |
| `Add Time To Time` | `time1 time2` | float seconds |
| `Subtract Time From Time` | `time1 time2 [result_format]` | float seconds or datetime.timedelta |

Timestamp text has the shape `YYYY-MM-DD HH:MM:SS.mmm`, or `YYYY-MM-DD HH:MM:SS` with fractional output excluded. Timer text is `[minus]HH:MM:SS.mmm` or `[minus]HH:MM:SS`, with hours allowed to occupy more than two digits. Verbose duration text is a space-separated sequence of `<number> <unit-name>` pairs; compact text is space-separated `<number><unit-symbol>` values. Unit symbols are `d`, `h`, `min`, `s`, and `ms`. Negative verbose and compact text starts with `- `; negative timer text starts with `-`. `result_format` is a format selector or custom calendar-format string.

Date `result_format` selectors are `timestamp`, `datetime`, `date`, and `epoch`; duration selectors are `number`, `verbose`, `compact`, `timer`, and `timedelta`. `time_zone` spellings are `local` and `UTC`. The inherited process environment can supply `TZ`.

Default calendar input syntax is `YYYY-MM-DD[ HH[:MM[:SS[.<fraction>]]]]`. Timer input syntax is `[minus][[<hours>:]<minutes>:]<seconds>[.<fraction>]`, with at most three colon-separated components. Duration input uses numeric seconds or space-separated number/unit pairs, optionally preceded by a minus sign. Unit names used by callers include singular and plural forms of `nanosecond`, `microsecond`, `millisecond`, `second`, `minute`, `hour`, `day`, and `week`; short forms include `ms` and `s`.

Verbose and compact output pairs appear in descending unit order: days, hours, minutes, seconds, milliseconds. Hours are below 24; minutes and seconds are below 60. Zero-valued units are omitted; zero duration is `0 seconds` or `0s`. Verbose names are `day`, `hour`, `minute`, `second`, and `millisecond`, with `s` appended for a count other than one.

## `velun.libraries.XML.XML`

The Library setting accepts `XML` and the named initialization cell `use_lxml=True`. Source cells carry an XML path, XML text, bytes, or a parsed element. Parsed elements expose `tag: str`, `text: str | None`, `tail: str | None`, `attrib: mapping[str, str]`, `get(name)`, ordered iteration over children, indexing, and child count. Qualified tags use `{<namespace URI>}<local name>`. Optional keyword cells can be named.

| Keyword | Argument cells | Result carrier |
| --- | --- | --- |
| `Parse Xml` | `source [keep_clark_notation] [strip_namespaces]` | element |
| `Get Element` | `source [xpath]` | element |
| `Get Elements` | `source xpath` | list of elements |
| `Get Child Elements` | `source xpath` | list of elements |
| `Get Element Count` | `source xpath` | int |
| `Element Should Exist` | `source xpath` | assertion outcome |
| `Element Should Not Exist` | `source xpath` | assertion outcome |
| `Get Element Text` | `source [xpath] [normalize_whitespace]` | str |
| `Get Elements Texts` | `source xpath` | list[str] |
| `Get Element Attributes` | `source` | mapping[str, str] |
| `Get Element Attribute` | `source name [default=<object>]` | str, None, or supplied default object |
| `Element Text Should Be` | `source expected` | assertion outcome |
| `Element Text Should Match` | `source pattern` | assertion outcome |
| `Element Attribute Should Be` | `source name expected` | assertion outcome |
| `Element Attribute Should Match` | `source name pattern` | assertion outcome |
| `Element Should Not Have Attribute` | `source name` | assertion outcome |
| `Elements Should Be Equal` | `source expected [exclude_children] [normalize_whitespace] [sort_children]` | assertion outcome |
| `Elements Should Match` | `source expected` | assertion outcome |
| `Set Element Tag` | `source tag [xpath]` | document root element |
| `Set Element Text` | `source [text] [tail] [xpath]` | document root element |
| `Set Element Attribute` | `source name value [xpath]` | document root element |
| `Remove Element Attribute` | `source name [xpath]` | document root element |
| `Add Element` | `source element [index]` | document root element |
| `Remove Element` | `source xpath [remove_tail]` | document root element |
| `Remove Elements` | `source xpath [remove_tail]` | document root element |
| `Clear Element` | `source xpath [clear_tail]` | document root element |
| `Copy Element` | `source` | element |
| `Element To String` | `source` | XML str |
| `Save XML` | `source path` | XML file at path |
| `Evaluate Xpath` | `source expression [context]` | float, bool, string-compatible scalar, list of strings, or list of elements |

Selection and assertion failures use keyword `FAIL` status and diagnostic text in `msg` elements with level `FAIL`. Saved documents and serialized strings are XML; element tags, text, tail, attributes, and children are the exchange format.

## `velun.libraries.Telnet.Telnet`

The Library setting accepts `Telnet`. Keyword results are assigned as native Python values. Session references returned by the connection operation and string aliases are accepted by selection calls. Host and port identify a TCP endpoint. Optional parameters can be named.

| Keyword | Argument cells | Result carrier |
| --- | --- | --- |
| `Open Connection` | `host [alias] [port] [timeout] [newline] [prompt] [prompt_is_regexp] [encoding] [window_size] [terminal_emulation] [connection_timeout]` | connection reference |
| `Switch Connection` | `index_or_alias` | session selection |
| `Close Connection` | `` | session closure |
| `Close All Connections` | `` | session closure |
| `Set Newline` | `newline` | session configuration |
| `Set Prompt` | `prompt [prompt_is_regexp]` | session configuration |
| `Set Encoding` | `[encoding] [errors=<policy>]` | session configuration |
| `Write` | `text` | str containing the written text and newline |
| `Write Bare` | `text` | network write |
| `Write Control Character` | `character` | network write |
| `Read` | `` | str or bytes |
| `Read Until` | `expected` | str or bytes |
| `Read Until Regexp` | `*expected` | str or bytes |
| `Read Until Prompt` | `[strip_prompt=<bool>]` | str or bytes |
| `Login` | `username password [login_prompt] [password_prompt] [login_timeout] [login_incorrect]` | str |
| `Execute Command` | `command [strip_prompt=<bool>]` | str |

`window_size` has the text form `<columns>x<rows>`. Literal and regular-expression read failures carry the awaited condition and received content in the diagnostic. Prompt-read failures carry the awaited prompt in the diagnostic and received content in a keyword `msg` with level `INFO`.

Newline selectors include `LF`. `Set Encoding` accepts `NONE` as the binary-mode selector and `strict` or `replace` as error-policy spellings. Control-name spellings are `BRK`, `IP`, `AO`, `AYT`, `EC`, `EL`, and `NOP`; control values can also be supplied numerically.

Control-message framing is two bytes: IAC (`255`) followed by the command byte. The named command bytes are `NOP` = `241`, `BRK` = `243`, `IP` = `244`, `AO` = `245`, `AYT` = `246`, `EC` = `247`, and `EL` = `248`.

Rendered screen content is text with the selected newline between rows. Screen padding at the right and bottom is omitted.

## `Library`

A caller-supplied Python library is selected by a `Library` setting containing a module name, class name, or Python source path, followed by initializer argument cells and an optional alias. Library functions and instance methods accept Python arguments and return Python objects. A raised `AssertionError` is exposed through the keyword failure carrier.

Library declarations expose `VELUN_AUTO_KEYWORDS`, `VELUN_LIBRARY_SCOPE`, `VELUN_LIBRARY_CONVERTERS`, `VELUN_LIBRARY_VERSION`. These carry, respectively, a Boolean exposure setting, a scope selector, a mapping from Python types to conversion callables, and a version string. Callable annotations carry type hints, and `velun_tags` is a keyword's tag sequence.

Hybrid libraries expose `get_keyword_names() -> list[str]` and named Python callables. Dynamic libraries expose `get_keyword_names()`, `get_keyword_arguments(name) -> list[str]`, `get_keyword_documentation(name) -> str`, `get_keyword_tags(name) -> list[str]`, `get_keyword_types(name) -> mapping`, and either `run_keyword(name, args) -> object` or `run_keyword(name, args, kwargs) -> object`. `args` is a positional-value list; `kwargs` maps argument names to Python values. Scope selector spellings are `SUITE` and `GLOBAL`. Argument specifications use `name`, `name=<default>`, `*name`, and `**name` strings.

## `velun.libraries.Remote.Remote`

`Remote(uri, timeout)` is importable from `velun.libraries.Remote`. The timeout argument can be omitted. `uri` is an HTTP XML-RPC endpoint string; timeout accepts a duration value.

`get_keyword_names()` returns a list of strings. `run_keyword(name, args, kwargs)` accepts a keyword name, positional argument list, and named argument mapping and returns the server's Python value. Remote-call failure is exposed as `RuntimeError` in direct Python calls.

The native Library setting is `Library Remote <uri> [<timeout>]`, with each item in a separate cell.

## `get_library_information`

Remote discovery uses the XML-RPC request `get_library_information()` to the configured URI. Its response is a mapping from keyword-name strings to metadata objects. Each object has `args: list[str]` and `doc: str`; the argument specifications carry ordinary names, defaulted names, and variable positional and named forms.

The discovery mapping can include `__intro__` and `__init__` objects whose `doc` field carries the library introduction and initialization documentation.

## `run_keyword`

The remote XML-RPC request is `run_keyword(name, args, kwargs)`. `name` is a string, `args` an array, and `kwargs` a structure with string keys. Transport values include strings, integers, floating-point values, Booleans, XML-RPC binary values, date-time values, arrays, and structures.

The response is a structure with `status: str` and outcome fields `return`, `output`, `error`, `continuable`, and `fatal`. `return` is a transported result value; `output` is log text; `error` is diagnostic text; `continuable` and `fatal` are Boolean flags. Status labels are `PASS` and `FAIL`. A log line can use `*INFO* <message>` to carry an information record.

Binary result carriers are Python `bytes`; mapping result carriers expose item and attribute access.

## `VELUN_LIBRARY_LISTENER`

Libraries expose listener objects through `VELUN_LIBRARY_LISTENER`, either a listener or a list of listeners. Command-line listeners are named by `--listener <module.class>[:<argument>...]`. Listener objects can expose numeric `VELUN_LISTENER_PRIORITY` and `VELUN_LISTENER_API_VERSION`.

Current callbacks are `start_suite(data, result)`, `end_suite(data, result)`, `start_test(data, result)`, `end_test(data, result)`, `start_keyword(data, result)`, `end_keyword(data, result)`, `start_for(data, result)`, `end_for(data, result)`, `start_for_iteration(data, result)`, `end_for_iteration(data, result)`, `start_if(data, result)`, `end_if(data, result)`, `start_if_branch(data, result)`, `end_if_branch(data, result)`, `start_while(data, result)`, `end_while(data, result)`, `start_try(data, result)`, `end_try(data, result)`, `start_try_branch(data, result)`, `end_try_branch(data, result)`, `start_group(data, result)`, and `end_group(data, result)`.

Data objects expose `name` and editable `body`; body members expose editable `name` and `args`. Result objects expose `type`, `name`, and `status`, and editable `metadata`, `tags`, `status`, and `message`. Suite, test, and keyword type labels are `SUITE`, `TEST`, and `KEYWORD`. Tags support `add(tag)`; metadata supports item assignment.

`log_message(message)` receives a message object with `level` and `message`. `output_file(path)`, `log_file(path)`, and `report_file(path)` receive artifact paths. `close()` is the closing callback.

With `VELUN_LISTENER_API_VERSION = 2`, `start_test(name, attrs)` receives a string name and mapping containing `tags`; `end_test(name, attrs)` receives a mapping containing `status`; `log_message(message)` receives a mapping containing `level` and `message`.

## `--parser`

A custom parser is named by `--parser <module.class>[:<argument>...]` or passed as an object through `custom_parsers`. It exposes `extension: str`, `parse(source, defaults) -> TestSuite`, and optionally `parse_init(source, defaults) -> TestSuite`. `source` is a `pathlib.Path`. A directory initialization source has the filename `__init__.<extension>`.

The defaults object exposes writable `tags`, `timeout`, `setup`, and `teardown`. Tags are string sequences; timeout is duration text; fixtures accept objects with `name` and `args` fields. `set_to(test)` accepts an executable test object.

## `--console`

`--console <module.class>` names a caller-provided console object. It accepts callbacks `start_suite(data, result)`, `end_test(data, result)`, `output_file(path)`, `log_file(path)`, `report_file(path)`, and `close()`. Suite and test data expose `name`; result objects expose `status`; artifact callbacks carry the selected paths. Text printed by the console object is visible on `stdout`.

## `output.xml`

The structured XML result is written at the selected `--output` path. Its root is `velun`, with `rpa="true"` or `rpa="false"`. It contains a top-level `suite`, `statistics`, and `errors`.

A suite has `name` and source-path `source` attributes, nested `suite` and `test` elements, `doc` text, `meta` elements with a `name` attribute and text value, fixture `kw` elements, and a direct `status`. A test has a `name` attribute, `doc`, `meta`, `tag` text elements, executable children, optional `timeout` with duration-text `value`, and a direct `status`.

Executable keyword elements are `kw` with a `name` attribute and an `owner` attribute when the provider is known; the latter may be omitted for keywords without a provider. Fixture kinds use `type="SETUP"` or `type="TEARDOWN"`. Keyword arguments are `arg` text children; documentation is `doc`; messages are `msg`. Nested execution uses `kw`, `for` with `iter` children, `while` with `iter` children, `if` with `branch` children, and `group` with a `name` attribute. Executable nodes have direct `status` children.

A `status` has a `status` attribute carrying `PASS`, `FAIL`, `SKIP`, or `NOT RUN`; its text carries the outcome message or diagnostic reason. Modern timing attributes are `start`, a local ISO date-time string with the form `YYYY-MM-DDTHH:MM:SS[.<fraction>]` (a space may replace `T`), and `elapsed`, numeric seconds. A `msg` has a `level` attribute and text content. Severity labels include `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, and `FAIL`. Execution issues are `velun/errors/msg` records.

Statistics use `statistics/total/stat`, `statistics/tag/stat`, and `statistics/suite/stat`. A `stat` has integer-text attributes `pass`, `fail`, and `skip`; text is its group label. Tag statistics can expose `doc` text and `links` containing the associated caller URL and label.

Termination-marked tests expose the tag `velun:exit`. Timeout diagnostics carry the category marker `Test timeout` or `Keyword timeout` followed by duration information. Timeout-configuration diagnostics carry the rejected duration.

Compatibility XML uses `starttime` and `endtime` timing attributes on `status`. Its suite/test hierarchy, status labels, and message elements use the same carriers described above.

Merged-result history is carried in status text prefixed with `*HTML*`. In that HTML fragment, `span.old-status` labels the previous status, its following status span carries the status value, and fragment text contains the previous reason.

## `output.json`

The JSON result path is selected by `--output <path.json>`. It contains an object with `rpa: bool` and `suite: object`. The suite exposes `name: str` and `tests: array`; each read test object has `name: str` and `status: str`. The same file can be supplied to `ExecutionResult` and to `velun.velunexmerge`.

## `xunit`

The `--xunit <path>` output is XML. Root attributes `tests`, `failures`, and `skipped` are integer counts. Each `testcase` has a `name` attribute; `failure` and `skipped` child elements carry the corresponding unsuccessful outcome categories.

## `debugfile`

The `--debugfile <path>` output is text. Timestamped lines carry the markers `START TEST: <name>` and `START KEYWORD: <name> [<arguments>]`. The placeholders contain the test or keyword name and argument information.

## `log.html`

The generated detailed log is an HTML file at the selected log path, conventionally `log.html`. Its document title includes `Log` and the suite identity.

Rendered `.suite` and `.test` elements have direct `.element-header` children. A header's `.name` carries the element name and `.label` carries its node kind and status class; a failed suite label has class `fail`. `a.expand` and clicks on element headers expose nested content. Nested keyword elements use `.keyword > .element-header > .name` and `.keyword > .element-header > .label`. Control-kind labels include `IF`.

Expanded test documentation is in `.metadata td.doc`; keyword and test message text is in `.messages td.message`. Test names can be addressed by fragment links `log.html#<element-id>`.

## `report.html`

The summary report is an HTML file at the selected report path, conventionally `report.html`. Its document title carries the suite identity. `a[href="#totals"]` opens the test detail table. `#test-details tbody tr` contains `.details-col-name` and `.details-col-status` cells. Ancestor-name prefixes are separate `.parent-name` descendants of the name cell; the remaining name-cell text is the test name. Status cells carry status words. Test links address `log.html#<element-id>`, and a log link can have `href="log.html"`.

`#total-stats tbody tr td.stats-col-stat` contains the total, passed, failed, and skipped counts in that column order. `#tag-stats tbody tr` and `#suite-stats tbody tr` contain grouped statistics. Tag rows display their tag label, a documentation tooltip in a `td`'s `title`, and links with caller-supplied link text and `href`.

The Summary table has a `th` labeled `Documentation:` and a `td.doc` carrying rendered suite documentation.

## `velun.velunexdocs`

`python -m velun.velunexdocs [options] <source> <output-path>` writes keyword documentation. `<source>` names a Python library, resource, suite or initialization source, or an existing JSON or XML documentation specification. Library initializer arguments are appended as `::<argument>` segments.

Options are `--specdocformat <format>`, `--docformat <format>`, `--language <language>`, and `--format <format>`. Documentation format selectors are `RAW` and `HTML` for specification documentation, and `VELUN`, `MARKDOWN`, `REST`, `HTML`, and `TEXT` for source formatting. Output paths use `.json`, `.xml`, `.md`, or `.html` extensions. HTML presentation language codes are `en` and `fi`.

Console invocations are `python -m velun.velunexdocs <source> list [<filter> ...]`, `python -m velun.velunexdocs <source> show [<filter> ...]`, and `python -m velun.velunexdocs <source> version`. `list` writes one keyword name per line on `stdout`; `show` writes Markdown; `version` writes the declared version followed by a newline on `stdout`.

Successful generation and queries exit `0`. Rejected documentation input exits `252` and emits a nonempty diagnostic on `stdout`. Individual keyword diagnostics use `stderr` with `[ ERROR ]`, the source path, keyword identity, and location expressed as `line <integer>:`.

## `velun.velunexdocs.velunexdocs`

`velunexdocs(library_or_resource, outfile, specdocformat=...)` is importable from `velun.velunexdocs`. Source and output are strings, and `specdocformat` is the specification-documentation format selector. The call writes the requested documentation file.

## `velun.velunexdocs.LibraryDocumentation`

`LibraryDocumentation(library_or_resource)` is importable from `velun.velunexdocs`. It accepts a source string and returns a documentation object with iterable `keywords`. Keyword members expose `name: str`, `doc: str`, iterable `tags`, and iterable `args`. Each argument exposes `name: str`, `default_repr: str`, and `type.name: str`.

## `keywordspec.json`

JSON keyword documentation is an object with `name: str`, `version: str`, `type: str`, `doc: str`, `docFormat: str`, `inits: array`, and `keywords: array`. Source-kind labels are `LIBRARY`, `RESOURCE`, and `SUITE`. `doc` carries source documentation text or rendered HTML; `docFormat` names that representation.

Initialization and keyword objects expose `name`, `doc`, `tags: array[str]`, and `args: array`. A documented argument exposes `name: str`, `required: bool`, `defaultValue: str | null`, `type: object | null`, and `kind: str`. Type objects expose `name: str`. Variable positional and variable named argument kind labels are `VAR_POSITIONAL` and `VAR_NAMED`.

Keyword objects expose `returnType: object | null` with type `name`, `private: bool` when private, `source: str` for the declaration path, and one-based `lineno: int`.

Keyword diagnostic text occupies `doc`; an argument-syntax diagnostic carries the affected `<argument-declaration>`.

## `keywordspec.xml`

XML keyword documentation has root `keywordspec` with a `name` attribute and children `version` and `doc`. Keyword entries are `keywords/kw` with a `name` attribute, `doc`, `tags/tag`, `arguments/arg`, and `returntype`.

Each `arg` has a `required` attribute spelled `true` or `false`, a `name` child, a `type` child with `name` attribute, and a `default` child for a declared default. `returntype` has a `name` attribute. Text nodes carry the documented version, documentation, tag, parameter name, or default representation.

## `keywordspec.md`

Markdown reader documentation is UTF-8 text. Its library heading is `# <library-name>` and each keyword heading is `### <keyword-name>`. Subsection labels are `#### Arguments`, `#### Documentation`, `#### Returns`, and `#### Tags`.

An argument bullet is an asterisk followed by a code span containing the argument name. Type and default information, when present, follow as `(type: <type-code-span>, default: <default-code-span>)`; a type without a default uses `(type: <type-code-span>)`. Return types and tags appear in code spans; a return entry uses an asterisk bullet. Documentation text appears in the Documentation subsection.

## `velunexdocs.html`

The interactive keyword reader is an HTML file. `#introduction-container .doc` carries the introduction. `.keyword-container .kw-name` carries each keyword name. Keyword containers have `id` equal to the keyword name; their rendered text carries documentation, tags, defaults, and argument information. `#keywords-container .arg-name`, `.arg-row`, and `.type` carry argument names, argument rows, and type names.

`#keyword-shortcuts-container a.match` carries currently displayed keyword names. `.search-input` accepts a search string and keyboard events; `.clear-search` is a clickable search-reset control. Keyword references have `href="#<percent-encoded keyword-name>"`; the location hash identifies the linked keyword.

A type link is `a.type[data-typedoc="<type-name>"]`. Its modal is `#modal-content #type-modal-<type-name>`, with `.dtdoc` for type documentation and `.enum-member` for enumeration members. `#modal-background` has positive opacity while the modal is visible. `.modal-close-button` is the close control.

Section heading IDs are `Introduction`, `Keywords`, and `Importing`. Their English labels are `Introduction`, `Keywords`, and `Importing`; Finnish labels are `Johdanto`, `Avainsanat`, and `Käyttöönotto`.

## `doc`

Rendered documentation is HTML markup carried in a specification's `doc` string or the reader document's documentation container. Heading elements are `h1`, `h2`, `h3`, or `h4`; paragraph blocks are `p`; strong and emphasized text use `b` or `strong` and `i` or `em`; inline code uses `code`; lists use `ul` and `li`; tables use `table`, `th`, and `td`; preformatted content uses `pre`. Links use `a` with `href`; images use `img` with `src`. Text content, URLs, and formatting input come from caller-authored documentation.

Native documentation input uses blank lines between paragraphs and line breaks within a paragraph. Paired `*` marks bold text, paired `_` marks emphasis, and paired double backticks mark inline code. A heading line surrounds its text with matching groups of one through three `=` characters, separated from the text by spaces. List item lines begin with `- `; indented lines continue an item. Table rows begin and end with `|`, with cells separated by spaced pipes; surrounding a cell with `=` marks a header. A preformatted line begins with `| ` without a closing row delimiter; that prefix is excluded from its content and remaining whitespace is retained. `[<URL>|<label>]` is link syntax; an image URL in that position produces an image with title text. A keyword name enclosed in single backticks is a keyword reference.

Markdown input uses ATX headings, paragraph breaks, hyphen list items, bracket-label/parenthesized-URL links, and fenced code blocks. reStructuredText input uses underline headings, paragraph breaks, hyphen list items, backtick-label/angle-URL links ending in an underscore, and indented literal blocks introduced by `::`. HTML input is markup; plain-text input is text content.

## `velun.velunexplan`

`python -m velun.velunexplan [options] <source> ... <output.html>` accepts one or more suite source paths followed by the output path. Options are `--suite <pattern>`, `--test <pattern>`, `--include <expression>`, `--exclude <expression>`, `--name <name>`, `--doc <text>`, `--metadata <name>:<value>`, `--settag <tag>`, and `--title <title>`.

Successful generation exits `0` and writes HTML at the selected path. Rejected documentation input exits `252` and emits a nonempty diagnostic on `stdout`.

## `velun.velunexplan.velunexplan`

`velunexplan(*arguments, name=...)` is importable from `velun.velunexplan`. Positional string arguments are the source paths followed by the output path. The named `name` option is a suite-name string. The call writes an HTML overview at the requested path.

## `velunexplan.html`

The generated suite overview is an HTML file at the caller's output path. The document title and `#header h1` carry its title. The top suite is `body > .suite`. Suite and test descendants use `.children > .suite` and `.children > .test`; the name is in `.element-header .name`. `a.expand` exposes descendant content.

Each suite and test has a direct `.children > table.metadata` whose rows carry a `th` label and `td` value. Documentation uses `Documentation:`; tags use `Tags:`; a metadata entry uses `<metadata-name>:`. Tag text is separated by comma followed by space.

Top-level keyword calls are direct `.children > .keyword` descendants. Their `.element-header .name` carries the call name and `.arg` carries arguments joined by comma followed by space. The argument text is empty for a call without arguments.

## `velun.libraries.String`

The module `velun.libraries.String` exposes the class `String`.

## `velun.libraries.Remote`

The module `velun.libraries.Remote` exposes the class `Remote`.
