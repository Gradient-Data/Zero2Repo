# Interface Contract

The Go module root contains `go.mod` with module path `github.com/zelviro-sh/zelviro` and is buildable with Go 1.26. Build the root command from `.` using `go build -o <executable> .`; its command name is `zelviro`. Run it in the caller's working directory. Embedding imports are `github.com/zelviro-sh/zelviro/interp`, `github.com/zelviro-sh/zelviro/lang/golang`, `github.com/zelviro-sh/zelviro/goparser`, `github.com/zelviro-sh/zelviro/scan`, `github.com/zelviro-sh/zelviro/stdlib`, `github.com/zelviro-sh/zelviro/stdlib/all`, `github.com/zelviro-sh/zelviro/modfs`, and `github.com/zelviro-sh/zelviro/stdlib/stdmod`.

Source text and text streams use UTF-8. Program input is `stdin`; program output is `stdout`; command diagnostics are `stderr`. Source-directed files use the paths and contents supplied by the program. Go embedding uses its supplied input reader and output/diagnostic writers.

## Runtime diagnostics

An evaluation runtime error exposes text through `error.Error()`; the run command writes it to stderr. The first line is `panic: <cause>`, followed by an indented `at <function> (<source>:<line>:<column>)` line. A `zelviro stack:` section contains indented `<source>:<line>:<column> <function>` rows. Decimal line and column positions are one-based. Source identifies the source label or file, and function identifies the interpreted function. Native boundary records have the form `-- via <name> [native] --`. A goroutine diagnostic on the diagnostic writer is introduced by `-- panic in goroutine --` and contains the runtime diagnostic.

## `interp.NewInterpreter`

`func NewInterpreter(s *lang.Spec) *Interp` in package `interp` is called as `interp.NewInterpreter(golang.GoSpec)` and returns an `*interp.Interp` handle.

## `golang.GoSpec`

`golang.GoSpec` is exported by `github.com/zelviro-sh/zelviro/lang/golang` with type `*lang.Spec`, for the language-specification argument to interpreter construction.

## `interp.Interp`

The `*interp.Interp` handle exposes:

```go
Eval(name, src string) (reflect.Value, error)
Close()
SetIO(in io.Reader, out, err io.Writer)
UseHostStdio()
ImportPackageValues(m map[string]map[string]reflect.Value)
ImportPackageConsts(m map[string]map[string]string)
AutoImportPackages()
SetPkgfs(pkgPath string)
SetStdlibFS(fsys fs.FS)
SetRemoteFS(fsys fs.FS)
SetBuildContext(goos, goarch string)
AddBuildTags(tags ...string)
```

`Eval` takes a source label and source text. Its first result is a reflection value: `IsValid()` indicates value presence, `Type().String()` gives the Go type spelling, and `Interface()` gives the typed value. Complex results also support `Kind()` and `Complex()`. Success uses a nil error; failure uses a non-nil error. `Close` releases the handle.

`SetIO` receives an input reader, program-output writer and diagnostic writer. `UseHostStdio` selects process standard-stream access. `AutoImportPackages` is the automatic-import entry.

The outer keys of `ImportPackageValues` are import paths and inner keys are exported declaration names. Values carry native functions, channels and ordinary values; mutable-variable bindings carry pointers to host storage, and type bindings carry typed nil pointers. `ImportPackageConsts` uses the same keys with exact rational strings of the form `<numerator>/<denominator>`.

`SetPkgfs` accepts a directory path. `SetStdlibFS` and `SetRemoteFS` accept `io/fs.FS` filesystems. Package sources are addressed as `<import-path>/<source-basename>.go`. `SetBuildContext` takes operating-system and architecture strings; `AddBuildTags` takes additional build-tag strings.

## `goparser.ErrUndefined`

`goparser.ErrUndefined` implements `error` and is accessible with `errors.As(err, &target)`, where `target` has type `goparser.ErrUndefined`. Its `Loc string` field is `<source-label>:<line>:<column>`, with one-based decimal positions, identifying the source location of an undefined-name failure.

## `scan.ErrBlock`

`scan.ErrBlock` is an exported error sentinel identifying unfinished delimited input, read with `errors.Is(err, scan.ErrBlock)`.

## `goparser.ErrPkgNotFound`

`goparser.ErrPkgNotFound` is an exported error sentinel identifying an unavailable package, read with `errors.Is(err, goparser.ErrPkgNotFound)` on the evaluation error.

## `interp.ExitError`

`*interp.ExitError` implements `error`. Use `errors.As(err, &target)`, with `target` declared as `*interp.ExitError`. Its exported `Code int` field carries the interpreted exit status.

## `stdlib.Values`

`stdlib.Values` has type `map[string]map[string]reflect.Value`: import path → exported name → native value. It is accepted by `ImportPackageValues`.

## `stdlib/all`

A blank import of `github.com/zelviro-sh/zelviro/stdlib/all` exposes bundled package registrations through `stdlib.Values`.

## `modfs.Options`

`modfs.Options` is the configuration struct accepted by `modfs.New`.

| Field | Type | Input |
| --- | --- | --- |
| `Proxy` | `string` | Module-proxy base URL. |
| `Client` | `*http.Client` | HTTP client for proxy requests. |
| `Offline` | `bool` | Offline-mode selection. |
| `CacheDir` | `string` | Writable module storage directory. |
| `ReadDirs` | `[]string` | Read-only module download roots. |

## `modfs.New`

`func New(opts Options) *FS` is called as `modfs.New(modfs.Options{...})` and returns a `*modfs.FS` filesystem.

## `modfs.FS`

`*modfs.FS` implements `io/fs.FS` and exposes:

```go
Open(name string) (fs.File, error)
ReadDir(name string) ([]fs.DirEntry, error)
Inject(modPath, version string, zipBytes []byte) error
CloseIdleConnections()
```

Names are slash-separated import paths followed by a package-relative file or directory. `fs.ReadFile` returns file contents as `[]byte`. Directory entries expose `Name() string` and `IsDir() bool`. Successful operations return nil errors; an unavailable path has an error matching `fs.ErrNotExist` through `errors.Is`.

`Inject` accepts module identity, version and ZIP bytes. Its error is nil on success and non-nil on refusal. Archive member names are `<module>@<version>/<relative-path>`. `CloseIdleConnections` takes no arguments and returns no result.

## `stdlib.EmbeddedStd`

`stdlib.EmbeddedStd` has signature `func EmbeddedStd() []byte` in package `stdlib` returns bundled module ZIP bytes, accepted by `Inject`.

## `stdmod.ModulePath`

`stdmod.ModulePath` is a string constant exported by `github.com/zelviro-sh/zelviro/stdlib/stdmod`, identifying the bundled archive's module path for `Inject`.

## `stdmod.Version`

`stdmod.Version` is a string constant identifying the bundled archive's version for `Inject`.

## `stdmod.FS`

`stdmod.FS` has signature `func FS(backing *modfs.FS) fs.FS` in package `stdmod` returns the bundled-source filesystem passed to `SetStdlibFS`.

## `GOPROXY`

`GOPROXY` is the command environment variable for proxy configuration. Its syntax is a URL or a list of entries separated by `,` or `|`; entries are URL or mode-selection strings.

The module-proxy protocol uses HTTP `GET`. A request to `<proxy>/<module>/@latest` consumes a JSON object with `Version` as a string. A request to `<proxy>/<module>/@v/<version>.zip` consumes ZIP bytes. Archive members use `<module>@<version>/<relative-path>` names, including `go.mod` and package source files. HTTP status carries request success or failure.

## `ZELVIROCACHE`

`ZELVIROCACHE` is a string selecting a module-storage directory or storage mode. On Linux the conventional product storage path is `<XDG_CACHE_HOME>/zelviro/download`.

`GOMODCACHE` supplies the Go module-cache root. Download archives below it have the layout `cache/download/<module>/@v/<version>.zip`. These paths are directory inputs to the command; a `CacheDir` can name the same product storage directory for filesystem access.

## `zelviro`

Interactive entry syntax is `zelviro` or `zelviro run`, with source lines supplied on stdin.

All interactive response text is on stdout. The primary prompt is `> ` and the continuation prompt is `>> `, each without a trailing newline. Input sent through pipes is not echoed. A displayed value is a line `:  <value>\n`: a colon, two spaces, the printable value, and newline. Scalar integers use decimal text and strings use their unquoted contents. A failure response begins `Error: <diagnostic>` and can occupy several lines. Response lines precede the next prompt; the prompt begins the response or an output line. EOF closes the session with status `0`.

## `-x`

The `-x` option on `zelviro run` and `zelviro test` writes source trace records to stderr:

```text
+ <indent><source>:<line>: <source-text>
```

`<indent>` consists of spaces indicating call depth. `<source>` is the supplied source filename, `<line>` is a one-based decimal line number, and `<source-text>` carries the corresponding source line.

## `SIGINT`

`SIGINT` is the command's interrupt input. An execution-state report goes to stderr. It begins `=== zelviro execution state (<metadata>) ===\n`; the following line is `  at <function> (<source>:<line>:<column>)\n`. The metadata is an opaque header field; source is the supplied source filename and positions are one-based decimal numbers. Interrupt termination uses exit status `130`.

## `-stat`

The `-stat` option on `zelviro run` and `zelviro test` emits these stderr records, with leading indentation and spaces after the labels:

```text
network: <requests> requests, <size> <unit> in <elapsed>
cache: <hits> hits, <size> <unit> served, <stored> stored
cache: <hits> hits (<count> via go cache), <size> <unit> served, <stored> stored
```

There is one `network:` record and one of the `cache:` record forms. Counts are decimal integers. Network size carries the received-byte quantity; cache size carries the served-byte quantity. The hit and stored fields carry archive-reuse and archive-persistence counts. The optional parenthesized count identifies Go-cache hits. Elapsed is nonempty duration text.

Size units are `B`, `KiB`, `MiB`, or `GiB`, with binary unit scales. A `B` size is a decimal integer; a size in another unit is decimal text with two fractional digits.

Phase records on stderr are:

```text
compile: <duration>
execute: <duration>
```

There is one record of each kind. Duration is a nonnegative duration in Go `time.Duration.String` syntax: numeric components with units `h`, `m`, `s`, `ms`, `µs`, or `ns`. Fractional decimal components are supported. The representation has nanosecond resolution. The labels identify source-processing and execution durations respectively.

## `extract`

Build the `extract` command from `./cmd/extract`.

```text
extract [-o <file>] [-pkg <package>] [-goos <os>] [-goarch <arch>] <selection> [source-directory]
extract -list [-o <file>] [-goos <os>] [-goarch <arch>] <directory>
```

Selection is an import path or local package selection. `-o` names the output file; without it, output goes to stdout. `-pkg` names the generated package. `-goos` and `-goarch` take target operating-system and architecture strings.

Binding output is compilable Go source declaring `<declared-package-name>Values` with type `map[string]map[string]reflect.Value`. The enclosing package is the supplied `-pkg` value, or `main`. Outer keys are canonical import paths; inner keys are exported declaration names. Functions and constants are reflection values of the native declarations; variables are pointers to native storage, and type descriptors are typed nil pointers.

Inventory output consists of newline-terminated `<kind> <name>` records. The kind tokens are `const`, `var`, `type` and `func`; name is the exported declaration name.

Success exits `0`. Failure exits `1` and emits a stderr line `error: <diagnostic>`. A selection or output failure's diagnostic carries the supplied selection or destination.

## `libzelviro.h`

Build the C embedding archive from `./examples/c/shim` using `go build -buildmode=c-archive -o <directory>/libzelviro.a ./examples/c/shim`. The generated `libzelviro.h` is the C include header; `libzelviro.a` is the archive linked by the host.

## `ZelviroNew`

`uintptr_t ZelviroNew(void);` returns an opaque interpreter handle.

## `ZelviroEval`

```c
int ZelviroEval(uintptr_t h, char *name, char *src, char **outResult, char **outError);
```

The handle, source label and source text are inputs; label and source are NUL-terminated strings. The caller supplies output pointers initially set to `NULL`. On success, status is `0`, `outResult` points to a NUL-terminated printable result, and `outError` remains `NULL`. Integer results use decimal text and string results contain unquoted text. A valueless result is an empty NUL-terminated string. On evaluation failure, status is `-1`, `outError` points to nonempty diagnostic text, and `outResult` remains `NULL`.

## `ZelviroFreeString`

`void ZelviroFreeString(char *s);` releases a string returned through an evaluation output parameter.

## `ZelviroFree`

`void ZelviroFree(uintptr_t h);` releases an interpreter handle and returns control to the C host.

## `zelviro run`

Command syntax:

```text
zelviro run [options] [target] [arguments]
zelviro [options] [target] [arguments]
zelviro run [options] <file.go> [<file.go> ...] [arguments]
```

Options precede the target. `-e <source>` supplies inline text, including the empty string; `-x` requests source tracing; `-stat` requests statistics. A target is a local source path or import path. Initial consecutive `.go` arguments name source files. Program arguments are exposed through `os.Args[1:]`.

Program output is on stdout. An inline displayed result is an unlabelled printable value followed by newline; integer values use decimal text. The no-entry-function report is one stderr line beginning `zelviro run: <target> `, followed by explanatory text.

Successful execution exits `0`. An ordinary execution or loading failure exits `1` with a nonempty stderr diagnostic. An interpreted process-exit request supplies the process exit status.

## `zelviro test`

Command syntax is `zelviro test [-x] [-stat] [target] [testing-options]`. A target is a local directory or import path; `.` names the current directory. The `-x` and `-stat` options precede the target and testing options. Testing options can appear before or after the target:

| Option | Argument form |
| --- | --- |
| `-v` | Verbose reporting. |
| `-run=<pattern>` | Name-selection regular expression. |
| `-skip=<pattern>` | Name-exclusion regular expression. |
| `-bench=<pattern>` | Benchmark-selection regular expression. |
| `-benchtime=<count>x` | Decimal iteration count followed by `x`. |
| `-count=<count>` | Decimal repetition count. |
| `-short`, `-short=<boolean>` | Short-mode switch. |
| `-shuffle=<mode>` | Order-randomization switch. |
| `-timeout=<duration>` | Go duration text. |

Source files use `_test.go`. Case declarations have the Go forms `Test<Name>(t *testing.T)`, `Benchmark<Name>(b *testing.B)`, and `Example<Name>()`; the package driver is `TestMain(m *testing.M)`. Example expectations use `// Output:` or `// Unordered output:`.

Stdout uses Go testing's text record format: `=== RUN   <name>`, `--- PASS: <name> (<duration>)`, `--- FAIL: <name> (<duration>)`, and `--- SKIP: <name> (<duration>)`, with indented subtest records and slash-qualified subtest names. The labels identify run, pass, fail and skip outcomes; each record carries its case name. Program output is also carried on stdout.

Successful suites exit `0`; refused targets and failed assertions, examples or benchmarks exit `1`. Timeout and unrecovered goroutine-panic outcomes exit `2`. The package driver can supply an explicit process exit status.

An empty runnable selection has a stderr report `testing: warning: <diagnostic>`, with nonempty explanatory text. A target-load failure has a nonempty stderr diagnostic carrying the target. An omitted file has a stderr record beginning `zelviro test: skipping <qualified-file> (<reason>`, with possible continuation lines. A timeout has a stderr header `panic: test timed out after <duration>\n`. An unrecovered goroutine panic carries a stderr `panic: <cause>\n` line.

The timeout header's duration uses the Go `time.Duration.String` text representation.

## `fmt`

Import path: `fmt`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`fmt.Sprintf`:

```go
func Sprintf(format string, a ...any) string
```

`fmt.Sscanf`:

```go
func Sscanf(str string, format string, a ...any) (n int, err error)
```

`fmt.Sprint`:

```go
func Sprint(a ...any) string
```

`fmt.Println`:

```go
func Println(a ...any) (n int, err error)
```

`fmt.Printf`:

```go
func Printf(format string, a ...any) (n int, err error)
```

`fmt.Fprintln`:

```go
func Fprintln(w io.Writer, a ...any) (n int, err error)
```

`fmt.Errorf`:

```go
func Errorf(format string, a ...any) (err error)
```

`fmt.Fprintf`:

```go
func Fprintf(w io.Writer, format string, a ...any) (n int, err error)
```

`fmt.Fscan`:

```go
func Fscan(r io.Reader, a ...any) (n int, err error)
```

Public named type: `fmt.State`.

Interpreted formatting receivers expose `String() string` or `Format(s fmt.State, verb rune)`. `fmt.State` is writable with `Write(p []byte) (n int, err error)`.

## `strings`

Import path: `strings`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`strings.Index`:

```go
func Index(s, substr string) int
```

`strings.Contains`:

```go
func Contains(s, substr string) bool
```

`strings.Compare`:

```go
func Compare(a, b string) int
```

`strings.Split`:

```go
func Split(s, sep string) []string
```

`strings.Join`:

```go
func Join(elems []string, sep string) string
```

`strings.ReplaceAll`:

```go
func ReplaceAll(s, old, new string) string
```

`strings.Trim`:

```go
func Trim(s, cutset string) string
```

`strings.ToUpper`:

```go
func ToUpper(s string) string
```

`strings.ToLower`:

```go
func ToLower(s string) string
```

`strings.NewReader`:

```go
func NewReader(s string) *Reader
```

`strings.EqualFold`:

```go
func EqualFold(s, t string) bool
```

## `bytes`

Import path: `bytes`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`bytes.Index`:

```go
func Index(s, sep []byte) int
```

`bytes.Equal`:

```go
func Equal(a, b []byte) bool
```

`bytes.Compare`:

```go
func Compare(a, b []byte) int
```

`bytes.Split`:

```go
func Split(s, sep []byte) [][]byte
```

`bytes.Join`:

```go
func Join(s [][]byte, sep []byte) []byte
```

`bytes.ReplaceAll`:

```go
func ReplaceAll(s, old, new []byte) []byte
```

`bytes.TrimSpace`:

```go
func TrimSpace(s []byte) []byte
```

`bytes.ToUpper`:

```go
func ToUpper(s []byte) []byte
```

`bytes.ToLower`:

```go
func ToLower(s []byte) []byte
```

`bytes.NewReader`:

```go
func NewReader(b []byte) *Reader
```

`bytes.Repeat`:

```go
func Repeat(b []byte, count int) []byte
```

`bytes.Buffer.String`:

```go
func (b *Buffer) String() string
```

`bytes.Buffer.Bytes`:

```go
func (b *Buffer) Bytes() []byte
```

`bytes.Buffer.Write`:

```go
func (b *Buffer) Write(p []byte) (n int, err error)
```

`bytes.Buffer.WriteString`:

```go
func (b *Buffer) WriteString(s string) (n int, err error)
```

`bytes.Buffer.Reset`:

```go
func (b *Buffer) Reset()
```

Public named type: `bytes.Buffer`.

## `unicode`

Import path: `unicode`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`unicode.IsLetter`:

```go
func IsLetter(r rune) bool
```

`unicode.IsDigit`:

```go
func IsDigit(r rune) bool
```

`unicode.IsSpace`:

```go
func IsSpace(r rune) bool
```

`unicode.IsUpper`:

```go
func IsUpper(r rune) bool
```

## `unicode/utf8`

Import path: `unicode/utf8`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`utf8.DecodeRuneInString`:

```go
func DecodeRuneInString(s string) (r rune, size int)
```

`utf8.RuneCountInString`:

```go
func RuneCountInString(s string) (n int)
```

`utf8.ValidString`:

```go
func ValidString(s string) bool
```

## `unicode/utf16`

Import path: `unicode/utf16`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`utf16.Encode`:

```go
func Encode(s []rune) []uint16
```

`utf16.Decode`:

```go
func Decode(s []uint16) []rune
```

## `strconv`

Import path: `strconv`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`strconv.ParseInt`:

```go
func ParseInt(s string, base int, bitSize int) (i int64, err error)
```

`strconv.ParseUint`:

```go
func ParseUint(s string, base int, bitSize int) (uint64, error)
```

`strconv.ParseFloat`:

```go
func ParseFloat(s string, bitSize int) (float64, error)
```

`strconv.ParseBool`:

```go
func ParseBool(str string) (bool, error)
```

`strconv.Quote`:

```go
func Quote(s string) string
```

`strconv.Unquote`:

```go
func Unquote(s string) (string, error)
```

`strconv.FormatInt`:

```go
func FormatInt(i int64, base int) string
```

`strconv.FormatUint`:

```go
func FormatUint(i uint64, base int) string
```

`strconv.FormatFloat`:

```go
func FormatFloat(f float64, fmt byte, prec, bitSize int) string
```

`strconv.FormatBool`:

```go
func FormatBool(b bool) string
```

## `regexp`

Import path: `regexp`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`regexp.Compile`:

```go
func Compile(expr string) (*Regexp, error)
```

`regexp.Regexp.MatchString`:

```go
func (re *Regexp) MatchString(s string) bool
```

`regexp.Regexp.FindStringSubmatch`:

```go
func (re *Regexp) FindStringSubmatch(s string) []string
```

`regexp.Regexp.FindAllString`:

```go
func (re *Regexp) FindAllString(s string, n int) []string
```

`regexp.Regexp.ReplaceAllString`:

```go
func (re *Regexp) ReplaceAllString(src, repl string) string
```

`regexp.Regexp.FindStringIndex`:

```go
func (re *Regexp) FindStringIndex(s string) (loc []int)
```

## `math`

Import path: `math`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`math.Sqrt`:

```go
func Sqrt(x float64) float64
```

`math.Abs`:

```go
func Abs(x float64) float64
```

`math.Floor`:

```go
func Floor(x float64) float64
```

`math.Ceil`:

```go
func Ceil(x float64) float64
```

`math.Pow`:

```go
func Pow(x, y float64) float64
```

`math.Mod`:

```go
func Mod(x, y float64) float64
```

## `math/cmplx`

Import path: `math/cmplx`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`cmplx.Conj`:

```go
func Conj(x complex128) complex128
```

`cmplx.Abs`:

```go
func Abs(x complex128) float64
```

## `math/big`

Import path: `math/big`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`big.NewInt`:

```go
func NewInt(x int64) *Int
```

`big.NewRat`:

```go
func NewRat(a, b int64) *Rat
```

`big.NewFloat`:

```go
func NewFloat(x float64) *Float
```

`big.Int.SetString`:

```go
func (z *Int) SetString(s string, base int) (*Int, bool)
```

`big.Int.Mul`:

```go
func (z *Int) Mul(x, y *Int) *Int
```

`big.Int.Mod`:

```go
func (z *Int) Mod(x, y *Int) *Int
```

`big.Int.String`:

```go
func (x *Int) String() string
```

`big.Rat.Add`:

```go
func (z *Rat) Add(x, y *Rat) *Rat
```

`big.Rat.RatString`:

```go
func (x *Rat) RatString() string
```

`big.Float.SetPrec`:

```go
func (z *Float) SetPrec(prec uint) *Float
```

`big.Float.Quo`:

```go
func (z *Float) Quo(x, y *Float) *Float
```

`big.Float.Text`:

```go
func (x *Float) Text(format byte, prec int) string
```

Public named type: `big.Int`.

Public named type: `big.Rat`.

Public named type: `big.Float`.

## `sort`

Import path: `sort`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`sort.Ints`:

```go
func Ints(x []int)
```

`sort.SearchInts`:

```go
func SearchInts(a []int, x int) int
```

`sort.IntsAreSorted`:

```go
func IntsAreSorted(x []int) bool
```

`sort.Slice`:

```go
func Slice(x any, less func(i, j int) bool)
```

`sort.Sort`:

```go
func Sort(data Interface)
```

Public named type: `sort.Interface`.

The argument to `Sort` exposes `Len() int`, `Less(i, j int) bool` and `Swap(i, j int)`.

## `container/heap`

Import path: `container/heap`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`heap.Init`:

```go
func Init(h Interface)
```

`heap.Push`:

```go
func Push(h Interface, x any)
```

`heap.Pop`:

```go
func Pop(h Interface) any
```

`heap.Fix`:

```go
func Fix(h Interface, i int)
```

`heap.Remove`:

```go
func Remove(h Interface, i int) any
```

Public named type: `heap.Interface`.

The collection argument exposes `Len() int`, `Less(i, j int) bool`, `Swap(i, j int)`, `Push(x any)` and `Pop() any`.

## `container/list`

Import path: `container/list`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`list.New`:

```go
func New() *List
```

`list.List.PushFront`:

```go
func (l *List) PushFront(v any) *Element
```

`list.List.PushBack`:

```go
func (l *List) PushBack(v any) *Element
```

`list.List.InsertBefore`:

```go
func (l *List) InsertBefore(v any, mark *Element) *Element
```

`list.List.MoveToBack`:

```go
func (l *List) MoveToBack(e *Element)
```

`list.List.Remove`:

```go
func (l *List) Remove(e *Element) any
```

`list.List.Front`:

```go
func (l *List) Front() *Element
```

`list.List.Back`:

```go
func (l *List) Back() *Element
```

`list.List.Len`:

```go
func (l *List) Len() int
```

`list.Element.Next`:

```go
func (e *Element) Next() *Element
```

`list.Element.Prev`:

```go
func (e *Element) Prev() *Element
```

Public fields (qualified by their containing type):

- `Element.Value`: `any`.

## `container/ring`

Import path: `container/ring`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`ring.New`:

```go
func New(n int) *Ring
```

`ring.Ring.Next`:

```go
func (r *Ring) Next() *Ring
```

`ring.Ring.Move`:

```go
func (r *Ring) Move(n int) *Ring
```

`ring.Ring.Do`:

```go
func (r *Ring) Do(f func(any))
```

`ring.Ring.Unlink`:

```go
func (r *Ring) Unlink(n int) *Ring
```

`ring.Ring.Len`:

```go
func (r *Ring) Len() int
```

`ring.Ring.Prev`:

```go
func (r *Ring) Prev() *Ring
```

Public fields (qualified by their containing type):

- `Ring.Value`: `any`.

## `cmp`

Import path: `cmp`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`cmp.Compare`:

```go
func Compare[T Ordered](x, y T) int
```

`cmp.Or`:

```go
func Or[T comparable](vals ...T) T
```

## `slices`

Import path: `slices`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`slices.Clone`:

```go
func Clone[S ~[]E, E any](s S) S
```

`slices.Equal`:

```go
func Equal[S ~[]E, E comparable](s1, s2 S) bool
```

`slices.Compare`:

```go
func Compare[S ~[]E, E cmp.Ordered](s1, s2 S) int
```

`slices.EqualFunc`:

```go
func EqualFunc[S1 ~[]E1, S2 ~[]E2, E1, E2 any](s1 S1, s2 S2, eq func(E1, E2) bool) bool
```

`slices.CompareFunc`:

```go
func CompareFunc[S1 ~[]E1, S2 ~[]E2, E1, E2 any](s1 S1, s2 S2, cmp func(E1, E2) int) int
```

`slices.BinarySearch`:

```go
func BinarySearch[S ~[]E, E cmp.Ordered](x S, target E) (int, bool)
```

`slices.BinarySearchFunc`:

```go
func BinarySearchFunc[S ~[]E, E, T any](x S, target T, cmp func(E, T) int) (int, bool)
```

`slices.Index`:

```go
func Index[S ~[]E, E comparable](s S, v E) int
```

`slices.IndexFunc`:

```go
func IndexFunc[S ~[]E, E any](s S, f func(E) bool) int
```

`slices.Contains`:

```go
func Contains[S ~[]E, E comparable](s S, v E) bool
```

`slices.ContainsFunc`:

```go
func ContainsFunc[S ~[]E, E any](s S, f func(E) bool) bool
```

`slices.Insert`:

```go
func Insert[S ~[]E, E any](s S, i int, v ...E) S
```

`slices.Delete`:

```go
func Delete[S ~[]E, E any](s S, i, j int) S
```

`slices.DeleteFunc`:

```go
func DeleteFunc[S ~[]E, E any](s S, del func(E) bool) S
```

`slices.Replace`:

```go
func Replace[S ~[]E, E any](s S, i, j int, v ...E) S
```

`slices.Compact`:

```go
func Compact[S ~[]E, E comparable](s S) S
```

`slices.CompactFunc`:

```go
func CompactFunc[S ~[]E, E any](s S, eq func(E, E) bool) S
```

`slices.Grow`:

```go
func Grow[S ~[]E, E any](s S, n int) S
```

`slices.Clip`:

```go
func Clip[S ~[]E, E any](s S) S
```

`slices.Concat`:

```go
func Concat[S ~[]E, E any](slices ...S) S
```

`slices.Repeat`:

```go
func Repeat[S ~[]E, E any](x S, count int) S
```

`slices.Reverse`:

```go
func Reverse[S ~[]E, E any](s S)
```

`slices.IsSorted`:

```go
func IsSorted[S ~[]E, E cmp.Ordered](x S) bool
```

`slices.Sort`:

```go
func Sort[S ~[]E, E cmp.Ordered](x S)
```

`slices.Min`:

```go
func Min[S ~[]E, E cmp.Ordered](x S) E
```

`slices.Max`:

```go
func Max[S ~[]E, E cmp.Ordered](x S) E
```

`slices.IsSortedFunc`:

```go
func IsSortedFunc[S ~[]E, E any](x S, cmp func(a, b E) int) bool
```

`slices.SortFunc`:

```go
func SortFunc[S ~[]E, E any](x S, cmp func(a, b E) int)
```

`slices.MinFunc`:

```go
func MinFunc[S ~[]E, E any](x S, cmp func(a, b E) int) E
```

`slices.MaxFunc`:

```go
func MaxFunc[S ~[]E, E any](x S, cmp func(a, b E) int) E
```

`slices.SortStableFunc`:

```go
func SortStableFunc[S ~[]E, E any](x S, cmp func(a, b E) int)
```

`slices.Collect`:

```go
func Collect[E any](seq iter.Seq[E]) []E
```

`slices.AppendSeq`:

```go
func AppendSeq[Slice ~[]E, E any](s Slice, seq iter.Seq[E]) Slice
```

`slices.Sorted`:

```go
func Sorted[E cmp.Ordered](seq iter.Seq[E]) []E
```

`slices.SortedFunc`:

```go
func SortedFunc[E any](seq iter.Seq[E], cmp func(E, E) int) []E
```

`slices.SortedStableFunc`:

```go
func SortedStableFunc[E any](seq iter.Seq[E], cmp func(E, E) int) []E
```

`slices.Values`:

```go
func Values[Slice ~[]E, E any](s Slice) iter.Seq[E]
```

`slices.All`:

```go
func All[Slice ~[]E, E any](s Slice) iter.Seq2[int, E]
```

`slices.Backward`:

```go
func Backward[Slice ~[]E, E any](s Slice) iter.Seq2[int, E]
```

`slices.Chunk`:

```go
func Chunk[Slice ~[]E, E any](s Slice, n int) iter.Seq[Slice]
```

## `maps`

Import path: `maps`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`maps.Equal`:

```go
func Equal[M1, M2 ~map[K]V, K, V comparable](m1 M1, m2 M2) bool
```

`maps.EqualFunc`:

```go
func EqualFunc[M1 ~map[K]V1, M2 ~map[K]V2, K comparable, V1, V2 any](m1 M1, m2 M2, eq func(V1, V2) bool) bool
```

`maps.Clone`:

```go
func Clone[M ~map[K]V, K comparable, V any](m M) M
```

`maps.Copy`:

```go
func Copy[M1 ~map[K]V, M2 ~map[K]V, K comparable, V any](dst M1, src M2)
```

`maps.DeleteFunc`:

```go
func DeleteFunc[M ~map[K]V, K comparable, V any](m M, del func(K, V) bool)
```

`maps.Collect`:

```go
func Collect[K comparable, V any](seq iter.Seq2[K, V]) map[K]V
```

`maps.Insert`:

```go
func Insert[Map ~map[K]V, K comparable, V any](m Map, seq iter.Seq2[K, V])
```

`maps.Keys`:

```go
func Keys[Map ~map[K]V, K comparable, V any](m Map) iter.Seq[K]
```

`maps.Values`:

```go
func Values[Map ~map[K]V, K comparable, V any](m Map) iter.Seq[V]
```

`maps.All`:

```go
func All[Map ~map[K]V, K comparable, V any](m Map) iter.Seq2[K, V]
```

## `iter`

Import path: `iter`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

```go
type Seq[V any] func(yield func(V) bool)
```

```go
type Seq2[K, V any] func(yield func(K, V) bool)
```

Qualified type names: `iter.Seq`, `iter.Seq2`.

## `bufio`

Import path: `bufio`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`bufio.NewWriter`:

```go
func NewWriter(w io.Writer) *Writer
```

`bufio.NewReader`:

```go
func NewReader(rd io.Reader) *Reader
```

`bufio.NewScanner`:

```go
func NewScanner(r io.Reader) *Scanner
```

`bufio.ScanWords`:

```go
func ScanWords(data []byte, atEOF bool) (advance int, token []byte, err error)
```

`bufio.Writer.WriteString`:

```go
func (b *Writer) WriteString(s string) (int, error)
```

`bufio.Writer.Flush`:

```go
func (b *Writer) Flush() error
```

`bufio.Reader.ReadString`:

```go
func (b *Reader) ReadString(delim byte) (string, error)
```

`bufio.Scanner.Split`:

```go
func (s *Scanner) Split(split SplitFunc)
```

`bufio.Scanner.Scan`:

```go
func (s *Scanner) Scan() bool
```

`bufio.Scanner.Text`:

```go
func (s *Scanner) Text() string
```

`bufio.Scanner.Err`:

```go
func (s *Scanner) Err() error
```

## `io`

Import path: `io`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`io.ReadAll`:

```go
func ReadAll(r Reader) ([]byte, error)
```

`io.Copy`:

```go
func Copy(dst Writer, src Reader) (written int64, err error)
```

`io.WriteString`:

```go
func WriteString(w Writer, s string) (n int, err error)
```

- `io.EOF`: error.

- `io.Discard`: io.Writer.

Public named type: `io.Reader`.

Public named type: `io.Writer`.

Public named type: `io.ReadCloser`.

Public named type: `io.WriteCloser`.

Reader and writer interfaces use `Read(p []byte) (n int, err error)` and `Write(p []byte) (n int, err error)`. Closeable streams also expose `Close() error`. Counts are bytes read or written. `io.EOF` identifies end of input.

## `os`

Import path: `os`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`os.MkdirTemp`:

```go
func MkdirTemp(dir, pattern string) (string, error)
```

`os.RemoveAll`:

```go
func RemoveAll(path string) error
```

`os.Mkdir`:

```go
func Mkdir(name string, perm FileMode) error
```

`os.WriteFile`:

```go
func WriteFile(name string, data []byte, perm FileMode) error
```

`os.ReadFile`:

```go
func ReadFile(name string) ([]byte, error)
```

`os.Stat`:

```go
func Stat(name string) (FileInfo, error)
```

`os.ReadDir`:

```go
func ReadDir(name string) ([]DirEntry, error)
```

`os.OpenFile`:

```go
func OpenFile(name string, flag int, perm FileMode) (*File, error)
```

`os.Remove`:

```go
func Remove(name string) error
```

`os.Getenv`:

```go
func Getenv(key string) string
```

`os.Exit`:

```go
func Exit(code int)
```

`os.File.WriteString`:

```go
func (f *File) WriteString(s string) (n int, err error)
```

`os.File.Close`:

```go
func (f *File) Close() error
```

`os.File.Read`:

```go
func (f *File) Read(b []byte) (n int, err error)
```

- `os.O_APPEND`: int constant.

- `os.O_WRONLY`: int constant.

- `os.ErrNotExist`: error.

- `os.Args`: []string.

- `os.Stdin`: *os.File.

- `os.Stdout`: *os.File.

- `os.Stderr`: *os.File.

File metadata returned by `Stat` exposes `Name() string`, `Size() int64` and `IsDir() bool`. Directory entries returned by `ReadDir` expose `Name() string`.

## `path`

Import path: `path`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`path.Clean`:

```go
func Clean(path string) string
```

`path.Join`:

```go
func Join(elem ...string) string
```

`path.Base`:

```go
func Base(path string) string
```

`path.Dir`:

```go
func Dir(path string) string
```

`path.Ext`:

```go
func Ext(path string) string
```

## `path/filepath`

Import path: `path/filepath`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`filepath.Rel`:

```go
func Rel(basePath, targPath string) (string, error)
```

`filepath.Join`:

```go
func Join(elem ...string) string
```

`filepath.Clean`:

```go
func Clean(path string) string
```

`filepath.Base`:

```go
func Base(path string) string
```

`filepath.Ext`:

```go
func Ext(path string) string
```

## `errors`

Import path: `errors`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`errors.New`:

```go
func New(text string) error
```

`errors.Is`:

```go
func Is(err, target error) bool
```

`errors.As`:

```go
func As(err error, target any) bool
```

`errors.Unwrap`:

```go
func Unwrap(err error) error
```

`errors.Join`:

```go
func Join(errs ...error) error
```

## `flag`

Import path: `flag`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`flag.NewFlagSet`:

```go
func NewFlagSet(name string, errorHandling ErrorHandling) *FlagSet
```

`flag.FlagSet.SetOutput`:

```go
func (f *FlagSet) SetOutput(output io.Writer)
```

`flag.FlagSet.Int`:

```go
func (f *FlagSet) Int(name string, value int, usage string) *int
```

`flag.FlagSet.Bool`:

```go
func (f *FlagSet) Bool(name string, value bool, usage string) *bool
```

`flag.FlagSet.String`:

```go
func (f *FlagSet) String(name string, value string, usage string) *string
```

`flag.FlagSet.Parse`:

```go
func (f *FlagSet) Parse(arguments []string) error
```

`flag.FlagSet.Args`:

```go
func (f *FlagSet) Args() []string
```

- `flag.ContinueOnError`: flag.ErrorHandling constant.

## `log`

Import path: `log`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`log.New`:

```go
func New(out io.Writer, prefix string, flag int) *Logger
```

`log.Fatal`:

```go
func Fatal(v ...any)
```

`log.Fatalf`:

```go
func Fatalf(format string, v ...any)
```

`log.SetOutput`:

```go
func SetOutput(w io.Writer)
```

`log.SetFlags`:

```go
func SetFlags(flag int)
```

`log.Logger.Printf`:

```go
func (l *Logger) Printf(format string, v ...any)
```

## `log/slog`

Import path: `log/slog`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`slog.New`:

```go
func New(h Handler) *Logger
```

`slog.NewJSONHandler`:

```go
func NewJSONHandler(w io.Writer, opts *HandlerOptions) *JSONHandler
```

`slog.Logger.With`:

```go
func (l *Logger) With(args ...any) *Logger
```

`slog.Logger.Warn`:

```go
func (l *Logger) Warn(msg string, args ...any)
```

- `slog.TimeKey`: string constant.

Public fields (qualified by their containing type):

- `Attr.Key`: `string`.
- `HandlerOptions.ReplaceAttr`: `func(groups []string, a Attr) Attr`.

`NewJSONHandler` writes JSON objects with `level` and `msg` string fields and caller-supplied attribute names and values. The callback's `Attr.Key` identifies the attribute.

Qualified public type: `slog.Attr`.

Qualified public type: `slog.HandlerOptions`.

## `time`

Import path: `time`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`time.Parse`:

```go
func Parse(layout, value string) (Time, error)
```

`time.ParseDuration`:

```go
func ParseDuration(s string) (Duration, error)
```

`time.Now`:

```go
func Now() Time
```

`time.Sleep`:

```go
func Sleep(d Duration)
```

`time.Since`:

```go
func Since(t Time) Duration
```

`time.NewTimer`:

```go
func NewTimer(d Duration) *Timer
```

`time.Unix`:

```go
func Unix(sec int64, nsec int64) Time
```

`time.Time.Year`:

```go
func (t Time) Year() int
```

`time.Time.Month`:

```go
func (t Time) Month() Month
```

`time.Time.Day`:

```go
func (t Time) Day() int
```

`time.Time.Unix`:

```go
func (t Time) Unix() int64
```

`time.Time.Add`:

```go
func (t Time) Add(d Duration) Time
```

`time.Time.Format`:

```go
func (t Time) Format(layout string) string
```

`time.Time.Before`:

```go
func (t Time) Before(u Time) bool
```

`time.Duration.String`:

```go
func (d Duration) String() string
```

`time.Duration.Seconds`:

```go
func (d Duration) Seconds() float64
```

- `time.RFC3339`: string constant.

- `time.Millisecond`: time.Duration constant.

- `time.Second`: time.Duration constant.

```go
type Duration int64
```

Public fields (qualified by their containing type):

- `Timer.C`: `<-chan Time`.

## `context`

Import path: `context`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`context.WithCancel`:

```go
func WithCancel(parent Context) (ctx Context, cancel CancelFunc)
```

`context.Background`:

```go
func Background() Context
```

`context.WithTimeout`:

```go
func WithTimeout(parent Context, timeout time.Duration) (Context, CancelFunc)
```

`context.Context.Err`:

```go
Err() error
```

`context.Context.Done`:

```go
Done() <-chan struct{}
```

- `context.Canceled`: error.

- `context.DeadlineExceeded`: error.

```go
type CancelFunc func()
```

## `sync`

Import path: `sync`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`sync.Mutex.Lock`:

```go
func (m *Mutex) Lock()
```

`sync.Mutex.Unlock`:

```go
func (m *Mutex) Unlock()
```

`sync.RWMutex.Lock`:

```go
func (rw *RWMutex) Lock()
```

`sync.RWMutex.Unlock`:

```go
func (rw *RWMutex) Unlock()
```

`sync.RWMutex.RLock`:

```go
func (rw *RWMutex) RLock()
```

`sync.RWMutex.RUnlock`:

```go
func (rw *RWMutex) RUnlock()
```

`sync.WaitGroup.Add`:

```go
func (wg *WaitGroup) Add(delta int)
```

`sync.WaitGroup.Done`:

```go
func (wg *WaitGroup) Done()
```

`sync.WaitGroup.Wait`:

```go
func (wg *WaitGroup) Wait()
```

`sync.Once.Do`:

```go
func (o *Once) Do(f func())
```

Public named type: `sync.Mutex`.

Public named type: `sync.RWMutex`.

Public named type: `sync.WaitGroup`.

Public named type: `sync.Once`.

## `sync/atomic`

Import path: `sync/atomic`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`atomic.StoreInt64`:

```go
func StoreInt64(addr *int64, val int64)
```

`atomic.AddInt64`:

```go
func AddInt64(addr *int64, delta int64) (new int64)
```

`atomic.SwapInt64`:

```go
func SwapInt64(addr *int64, new int64) (old int64)
```

`atomic.CompareAndSwapInt64`:

```go
func CompareAndSwapInt64(addr *int64, old, new int64) (swapped bool)
```

`atomic.LoadInt64`:

```go
func LoadInt64(addr *int64) (val int64)
```

## `encoding/json`

Import path: `encoding/json`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`json.Marshal`:

```go
func Marshal(v any) ([]byte, error)
```

`json.Unmarshal`:

```go
func Unmarshal(data []byte, v any) error
```

`json.NewEncoder`:

```go
func NewEncoder(w io.Writer) *Encoder
```

`json.NewDecoder`:

```go
func NewDecoder(r io.Reader) *Decoder
```

`json.Encoder.Encode`:

```go
func (enc *Encoder) Encode(v any) error
```

`json.Decoder.Decode`:

```go
func (dec *Decoder) Decode(v any) error
```

`json.Decoder.DisallowUnknownFields`:

```go
func (dec *Decoder) DisallowUnknownFields()
```

Data carrier: JSON bytes or writer output; decoded values populate the caller's destination.

Customization uses `MarshalJSON() ([]byte, error)` and `UnmarshalJSON([]byte) error` on the supplied value or destination.

## `encoding/xml`

Import path: `encoding/xml`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`xml.Marshal`:

```go
func Marshal(v any) ([]byte, error)
```

`xml.Unmarshal`:

```go
func Unmarshal(data []byte, v any) error
```

`xml.Encoder.EncodeElement`:

```go
func (enc *Encoder) EncodeElement(v any, start StartElement) error
```

`xml.Decoder.DecodeElement`:

```go
func (d *Decoder) DecodeElement(v any, start *StartElement) error
```

Public fields (qualified by their containing type):

- `Name.Local`: `string`.
- `StartElement.Name`: `Name`.

Data carrier: XML bytes; decoded values populate the caller's destination.

Customization uses `MarshalXML(e *xml.Encoder, start xml.StartElement) error` and `UnmarshalXML(d *xml.Decoder, start xml.StartElement) error`.

Qualified public type: `xml.Name`.

## `encoding/gob`

Import path: `encoding/gob`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`gob.NewEncoder`:

```go
func NewEncoder(w io.Writer) *Encoder
```

`gob.NewDecoder`:

```go
func NewDecoder(r io.Reader) *Decoder
```

`gob.Encoder.Encode`:

```go
func (enc *Encoder) Encode(e any) error
```

`gob.Decoder.Decode`:

```go
func (dec *Decoder) Decode(e any) error
```

Data carrier: Gob stream bytes.

## `encoding/csv`

Import path: `encoding/csv`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`csv.NewWriter`:

```go
func NewWriter(w io.Writer) *Writer
```

`csv.NewReader`:

```go
func NewReader(r io.Reader) *Reader
```

`csv.Writer.Write`:

```go
func (w *Writer) Write(record []string) error
```

`csv.Writer.Flush`:

```go
func (w *Writer) Flush()
```

`csv.Writer.Error`:

```go
func (w *Writer) Error() error
```

`csv.Reader.ReadAll`:

```go
func (r *Reader) ReadAll() (records [][]string, err error)
```

Public fields (qualified by their containing type):

- `Writer.Comma`: `rune`.
- `Reader.Comma`: `rune`.

Data carrier: CSV stream text.

## `encoding/ascii85`

Import path: `encoding/ascii85`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`ascii85.MaxEncodedLen`:

```go
func MaxEncodedLen(n int) int
```

`ascii85.Encode`:

```go
func Encode(dst, src []byte) int
```

`ascii85.Decode`:

```go
func Decode(dst, src []byte, flush bool) (ndst, nsrc int, err error)
```

Data carrier: ASCII85 bytes.

## `encoding/base32`

Import path: `encoding/base32`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`base32.Encoding.WithPadding`:

```go
func (enc Encoding) WithPadding(padding rune) *Encoding
```

`base32.Encoding.EncodeToString`:

```go
func (enc *Encoding) EncodeToString(src []byte) string
```

`base32.Encoding.DecodeString`:

```go
func (enc *Encoding) DecodeString(s string) ([]byte, error)
```

- `base32.NoPadding`: rune constant.

- `base32.StdEncoding`: *base32.Encoding.

Data carrier: Base32 text.

## `encoding/base64`

Import path: `encoding/base64`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`base64.Encoding.EncodeToString`:

```go
func (enc *Encoding) EncodeToString(src []byte) string
```

`base64.Encoding.DecodeString`:

```go
func (enc *Encoding) DecodeString(s string) ([]byte, error)
```

- `base64.RawURLEncoding`: *base64.Encoding.

- `base64.StdEncoding`: *base64.Encoding.

Data carrier: Base64 text.

## `encoding/hex`

Import path: `encoding/hex`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`hex.EncodeToString`:

```go
func EncodeToString(src []byte) string
```

`hex.DecodeString`:

```go
func DecodeString(s string) ([]byte, error)
```

Data carrier: Hexadecimal text.

## `encoding/binary`

Import path: `encoding/binary`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`binary.Write`:

```go
func Write(w io.Writer, order ByteOrder, data any) error
```

`binary.Read`:

```go
func Read(r io.Reader, order ByteOrder, data any) error
```

- `binary.BigEndian`: binary.ByteOrder.

- `binary.LittleEndian`: binary.ByteOrder.

Data carrier: Binary data using the supplied byte-order value.

## `encoding/asn1`

Import path: `encoding/asn1`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`asn1.Marshal`:

```go
func Marshal(val any) ([]byte, error)
```

`asn1.Unmarshal`:

```go
func Unmarshal(b []byte, val any) (rest []byte, err error)
```

Data carrier: ASN.1 bytes and unconsumed input.

## `encoding/pem`

Import path: `encoding/pem`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`pem.EncodeToMemory`:

```go
func EncodeToMemory(b *Block) []byte
```

`pem.Decode`:

```go
func Decode(data []byte) (p *Block, rest []byte)
```

Public fields (qualified by their containing type):

- `Block.Type`: `string`.
- `Block.Headers`: `map[string]string`.
- `Block.Bytes`: `[]byte`.

Data carrier: PEM bytes; Decode returns a nullable block and remaining input.

Qualified public type: `pem.Block`.

## `text/template`

Import path: `text/template`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`template.New`:

```go
func New(name string) *Template
```

`template.Template.Parse`:

```go
func (t *Template) Parse(text string) (*Template, error)
```

`template.Template.Execute`:

```go
func (t *Template) Execute(wr io.Writer, data any) error
```

`template.Template.Option`:

```go
func (t *Template) Option(opt ...string) *Template
```

## `html/template`

Import path: `html/template`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`template.New`:

```go
func New(name string) *Template
```

`template.Template.Parse`:

```go
func (t *Template) Parse(text string) (*Template, error)
```

`template.Template.Execute`:

```go
func (t *Template) Execute(wr io.Writer, data any) error
```

## `compress/flate`

Import path: `compress/flate`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`flate.NewWriter`:

```go
func NewWriter(w io.Writer, level int) (*Writer, error)
```

`flate.NewReader`:

```go
func NewReader(r io.Reader) io.ReadCloser
```

`flate.Writer.Write`:

```go
func (w *Writer) Write(data []byte) (n int, err error)
```

`flate.Writer.Close`:

```go
func (w *Writer) Close() error
```

- `flate.BestSpeed`: int constant.

Data carrier: DEFLATE bytes.

## `compress/gzip`

Import path: `compress/gzip`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`gzip.NewWriterLevel`:

```go
func NewWriterLevel(w io.Writer, level int) (*Writer, error)
```

`gzip.NewReader`:

```go
func NewReader(r io.Reader) (*Reader, error)
```

`gzip.Writer.Write`:

```go
func (z *Writer) Write(p []byte) (int, error)
```

`gzip.Writer.Close`:

```go
func (z *Writer) Close() error
```

`gzip.Reader.Close`:

```go
func (z *Reader) Close() error
```

- `gzip.BestCompression`: int constant.

Data carrier: gzip bytes.

## `compress/zlib`

Import path: `compress/zlib`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`zlib.NewWriterLevel`:

```go
func NewWriterLevel(w io.Writer, level int) (*Writer, error)
```

`zlib.NewReader`:

```go
func NewReader(r io.Reader) (io.ReadCloser, error)
```

`zlib.Writer.Write`:

```go
func (z *Writer) Write(p []byte) (n int, err error)
```

`zlib.Writer.Close`:

```go
func (z *Writer) Close() error
```

- `zlib.DefaultCompression`: int constant.

Data carrier: zlib bytes.

## `compress/lzw`

Import path: `compress/lzw`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`lzw.NewWriter`:

```go
func NewWriter(w io.Writer, order Order, litWidth int) io.WriteCloser
```

`lzw.NewReader`:

```go
func NewReader(r io.Reader, order Order, litWidth int) io.ReadCloser
```

- `lzw.LSB`: lzw.Order constant.

- `lzw.MSB`: lzw.Order constant.

```go
type Order int
```

Data carrier: LZW bytes using the supplied Order and literal width.

## `compress/bzip2`

Import path: `compress/bzip2`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`bzip2.NewReader`:

```go
func NewReader(r io.Reader) io.Reader
```

Data carrier: bzip2 input bytes.

## `archive/tar`

Import path: `archive/tar`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`tar.NewWriter`:

```go
func NewWriter(w io.Writer) *Writer
```

`tar.NewReader`:

```go
func NewReader(r io.Reader) *Reader
```

`tar.Writer.WriteHeader`:

```go
func (tw *Writer) WriteHeader(hdr *Header) error
```

`tar.Writer.Write`:

```go
func (tw *Writer) Write(b []byte) (int, error)
```

`tar.Writer.Close`:

```go
func (tw *Writer) Close() error
```

`tar.Reader.Next`:

```go
func (tr *Reader) Next() (*Header, error)
```

Public fields (qualified by their containing type):

- `Header.Name`: `string`.
- `Header.Mode`: `int64`.
- `Header.Size`: `int64`.
- `Header.ModTime`: `time.Time`.

Data carrier: tar archive bytes; Reader.Next returns a header or io.EOF.

Qualified public type: `tar.Header`.

## `archive/zip`

Import path: `archive/zip`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`zip.NewWriter`:

```go
func NewWriter(w io.Writer) *Writer
```

`zip.NewReader`:

```go
func NewReader(r io.ReaderAt, size int64) (*Reader, error)
```

`zip.Writer.CreateHeader`:

```go
func (w *Writer) CreateHeader(fh *FileHeader) (io.Writer, error)
```

`zip.Writer.Close`:

```go
func (w *Writer) Close() error
```

`zip.FileHeader.SetMode`:

```go
func (h *FileHeader) SetMode(mode fs.FileMode)
```

`zip.FileHeader.SetModTime`:

```go
func (h *FileHeader) SetModTime(t time.Time)
```

`zip.FileHeader.Mode`:

```go
func (h *FileHeader) Mode() (mode fs.FileMode)
```

`zip.File.Open`:

```go
func (f *File) Open() (io.ReadCloser, error)
```

- `zip.Deflate`: uint16 constant.

Public fields (qualified by their containing type):

- `FileHeader.Name`: `string`.
- `FileHeader.Method`: `uint16`.
- `FileHeader.UncompressedSize64`: `uint64`.
- `FileHeader.Modified`: `time.Time`.
- `Reader.File`: `[]*File`.

Data carrier: ZIP archive bytes; File exposes the FileHeader fields.

The file mode returned by `Mode()` exposes `Perm() fs.FileMode` for the permission bits.

## `net`

Import path: `net`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`net.SplitHostPort`:

```go
func SplitHostPort(hostport string) (host, port string, err error)
```

`net.JoinHostPort`:

```go
func JoinHostPort(host, port string) string
```

`net.ParseIP`:

```go
func ParseIP(s string) IP
```

`net.IP.String`:

```go
func (ip IP) String() string
```

## `net/netip`

Import path: `net/netip`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`netip.ParseAddr`:

```go
func ParseAddr(s string) (Addr, error)
```

`netip.Addr.String`:

```go
func (ip Addr) String() string
```

`netip.Addr.Is6`:

```go
func (ip Addr) Is6() bool
```

## `net/url`

Import path: `net/url`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`url.Parse`:

```go
func Parse(rawURL string) (*URL, error)
```

`url.QueryEscape`:

```go
func QueryEscape(s string) string
```

`url.URL.Hostname`:

```go
func (u *URL) Hostname() string
```

`url.URL.Port`:

```go
func (u *URL) Port() string
```

`url.URL.Query`:

```go
func (u *URL) Query() Values
```

`url.URL.ResolveReference`:

```go
func (u *URL) ResolveReference(ref *URL) *URL
```

`url.URL.String`:

```go
func (u *URL) String() string
```

`url.URL.RequestURI`:

```go
func (u *URL) RequestURI() string
```

`url.Values.Encode`:

```go
func (v Values) Encode() string
```

`url.Values.Get`:

```go
func (v Values) Get(key string) string
```

```go
type Values map[string][]string
```

Public fields (qualified by their containing type):

- `URL.Scheme`: `string`.
- `URL.Host`: `string`.
- `URL.Path`: `string`.
- `URL.RawQuery`: `string`.
- `URL.Fragment`: `string`.

## `net/http`

Import path: `net/http`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`http.ReadRequest`:

```go
func ReadRequest(b *bufio.Reader) (*Request, error)
```

`http.ReadResponse`:

```go
func ReadResponse(r *bufio.Reader, req *Request) (*Response, error)
```

`http.NewRequest`:

```go
func NewRequest(method, url string, body io.Reader) (*Request, error)
```

`http.Client.Do`:

```go
func (c *Client) Do(req *Request) (*Response, error)
```

`http.Header.Get`:

```go
func (h Header) Get(key string) string
```

`http.Header.Set`:

```go
func (h Header) Set(key, value string)
```

```go
type HandlerFunc func(ResponseWriter, *Request)
```

Public named type: `http.ResponseWriter`.

Public named type: `http.Handler`.

Public fields (qualified by their containing type):

- `Client.Timeout`: `time.Duration`.
- `Request.Method`: `string`.
- `Request.URL`: `*url.URL`.
- `Request.Host`: `string`.
- `Request.Header`: `Header`.
- `Request.Body`: `io.ReadCloser`.
- `Request.ContentLength`: `int64`.
- `Response.StatusCode`: `int`.
- `Response.Header`: `Header`.
- `Response.Body`: `io.ReadCloser`.

Data carrier: HTTP requests/responses use HTTP message syntax; bodies are readable streams and headers map names to string values.

`ResponseWriter` exposes `Header() Header`, `Write([]byte) (int, error)` and `WriteHeader(statusCode int)`. A handler exposes `ServeHTTP(ResponseWriter, *Request)`. Request/response headers carry string names and values; body readers also expose `Close() error`.

Qualified type names: `http.HandlerFunc`.

Qualified public type: `http.Request`.

## `net/http/httptest`

Import path: `net/http/httptest`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`httptest.NewServer`:

```go
func NewServer(handler http.Handler) *Server
```

`httptest.Server.Close`:

```go
func (s *Server) Close()
```

Public fields (qualified by their containing type):

- `Server.URL`: `string`.

## `crypto/sha256`

Import path: `crypto/sha256`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`sha256.Sum256`:

```go
func Sum256(data []byte) [Size]byte
```

`sha256.New`:

```go
func New() hash.Hash
```

## `crypto/sha512`

Import path: `crypto/sha512`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`sha512.New`:

```go
func New() hash.Hash
```

## `crypto/hmac`

Import path: `crypto/hmac`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`hmac.New`:

```go
func New(h func() hash.Hash, key []byte) hash.Hash
```

## `crypto/aes`

Import path: `crypto/aes`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`aes.NewCipher`:

```go
func NewCipher(key []byte) (cipher.Block, error)
```

## `crypto/cipher`

Import path: `crypto/cipher`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`cipher.NewCTR`:

```go
func NewCTR(block Block, iv []byte) Stream
```

`cipher.Stream.XORKeyStream`:

```go
XORKeyStream(dst, src []byte)
```

Public named type: `cipher.Block`.

## `crypto/ed25519`

Import path: `crypto/ed25519`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`ed25519.NewKeyFromSeed`:

```go
func NewKeyFromSeed(seed []byte) PrivateKey
```

`ed25519.Sign`:

```go
func Sign(privateKey PrivateKey, message []byte) []byte
```

`ed25519.Verify`:

```go
func Verify(publicKey PublicKey, message, sig []byte) bool
```

`ed25519.PrivateKey.Public`:

```go
func (priv PrivateKey) Public() crypto.PublicKey
```

- `ed25519.SeedSize`: int constant.

```go
type PublicKey []byte
```

Qualified type names: `ed25519.PublicKey`.

## `hash`

Import path: `hash`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`hash.Hash.Write`:

```go
Write(p []byte) (n int, err error)
```

`hash.Hash.Sum`:

```go
Sum(b []byte) []byte
```

Public named type: `hash.Hash`.

## `hash/crc32`

Import path: `hash/crc32`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`crc32.ChecksumIEEE`:

```go
func ChecksumIEEE(data []byte) uint32
```

`crc32.Checksum`:

```go
func Checksum(data []byte, tab *Table) uint32
```

`crc32.MakeTable`:

```go
func MakeTable(poly uint32) *Table
```

- `crc32.Castagnoli`: untyped integer constant.

## `hash/fnv`

Import path: `hash/fnv`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`fnv.New32`:

```go
func New32() hash.Hash32
```

`fnv.New32a`:

```go
func New32a() hash.Hash32
```

`fnv.New64`:

```go
func New64() hash.Hash64
```

`fnv.New64a`:

```go
func New64a() hash.Hash64
```

`fnv.New128`:

```go
func New128() hash.Hash
```

`fnv.New128a`:

```go
func New128a() hash.Hash
```

## `image`

Import path: `image`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`image.NewRGBA`:

```go
func NewRGBA(r Rectangle) *RGBA
```

`image.Rect`:

```go
func Rect(x0, y0, x1, y1 int) Rectangle
```

`image.NewUniform`:

```go
func NewUniform(c color.Color) *Uniform
```

`image.DecodeConfig`:

```go
func DecodeConfig(r io.Reader) (Config, string, error)
```

`image.RGBA.Bounds`:

```go
func (p *RGBA) Bounds() Rectangle
```

`image.RGBA.Set`:

```go
func (p *RGBA) Set(x, y int, c color.Color)
```

Public named type: `image.Image`.

Public fields (qualified by their containing type):

- `Point.X`: `int`.
- `Point.Y`: `int`.
- `Rectangle.Min`: `Point`.
- `Rectangle.Max`: `Point`.
- `Config.Width`: `int`.
- `Config.Height`: `int`.

An image exposes `Bounds() Rectangle` and `At(x, y int) color.Color`. `Min` and `Max` carry rectangle coordinates; `Width` and `Height` carry decoded dimensions.

Qualified public type: `image.Point`.

## `image/color`

Import path: `image/color`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`color.Color.RGBA`:

```go
RGBA() (r, g, b, a uint32)
```

Public fields (qualified by their containing type):

- `RGBA.R`: `uint8`.
- `RGBA.G`: `uint8`.
- `RGBA.B`: `uint8`.
- `RGBA.A`: `uint8`.

Qualified public type: `color.RGBA`.

## `image/draw`

Import path: `image/draw`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`draw.Draw`:

```go
func Draw(dst Image, r image.Rectangle, src image.Image, sp image.Point, op Op)
```

- `draw.Src`: draw.Op constant.

- `draw.Over`: draw.Op constant.

## `image/png`

Import path: `image/png`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`png.Encode`:

```go
func Encode(w io.Writer, m image.Image) error
```

`png.Decode`:

```go
func Decode(r io.Reader) (image.Image, error)
```

Data carrier: PNG bytes.

## `image/jpeg`

Import path: `image/jpeg`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`jpeg.Encode`:

```go
func Encode(w io.Writer, m image.Image, o *Options) error
```

`jpeg.Decode`:

```go
func Decode(r io.Reader) (image.Image, error)
```

Public fields (qualified by their containing type):

- `Options.Quality`: `int`.

Data carrier: JPEG bytes.

Qualified public type: `jpeg.Options`.

## `image/gif`

Import path: `image/gif`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`gif.Encode`:

```go
func Encode(w io.Writer, m image.Image, o *Options) error
```

`gif.Decode`:

```go
func Decode(r io.Reader) (image.Image, error)
```

Public fields (qualified by their containing type):

- `Options.NumColors`: `int`.

Data carrier: GIF bytes.

Qualified public type: `gif.Options`.

## `math/rand`

Import path: `math/rand`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`rand.New`:

```go
func New(src Source) *Rand
```

`rand.NewSource`:

```go
func NewSource(seed int64) Source
```

`rand.Rand.Intn`:

```go
func (r *Rand) Intn(n int) int
```

## `text/scanner`

Import path: `text/scanner`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`scanner.Scanner.Init`:

```go
func (s *Scanner) Init(src io.Reader) *Scanner
```

`scanner.Scanner.Scan`:

```go
func (s *Scanner) Scan() rune
```

`scanner.Scanner.TokenText`:

```go
func (s *Scanner) TokenText() string
```

Public named type: `scanner.Scanner`.

## `runtime/pprof`

Import path: `runtime/pprof`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`pprof.Lookup`:

```go
func Lookup(name string) *Profile
```

## `runtime`

Import path: `runtime`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`runtime.Caller`:

```go
func Caller(skip int) (pc uintptr, file string, line int, ok bool)
```

`runtime.FuncForPC`:

```go
func FuncForPC(pc uintptr) *Func
```

`runtime.Callers`:

```go
func Callers(skip int, pc []uintptr) int
```

`runtime.CallersFrames`:

```go
func CallersFrames(callers []uintptr) *Frames
```

`runtime.Goexit`:

```go
func Goexit()
```

`runtime.Func.Name`:

```go
func (f *Func) Name() string
```

`runtime.Func.FileLine`:

```go
func (f *Func) FileLine(pc uintptr) (file string, line int)
```

`runtime.Frames.Next`:

```go
func (ci *Frames) Next() (frame Frame, more bool)
```

Public fields (qualified by their containing type):

- `Frame.Function`: `string`.
- `Frame.File`: `string`.
- `Frame.Line`: `int`.

## `reflect`

Import path: `reflect`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`reflect.TypeOf`:

```go
func TypeOf(i any) Type
```

`reflect.ValueOf`:

```go
func ValueOf(i any) Value
```

`reflect.Value.IsValid`:

```go
func (v Value) IsValid() bool
```

`reflect.Value.Type`:

```go
func (v Value) Type() Type
```

`reflect.Value.Interface`:

```go
func (v Value) Interface() (i any)
```

`reflect.Value.Kind`:

```go
func (v Value) Kind() Kind
```

`reflect.Value.Complex`:

```go
func (v Value) Complex() complex128
```

`reflect.Value.Elem`:

```go
func (v Value) Elem() Value
```

`reflect.Value.FieldByName`:

```go
func (v Value) FieldByName(name string) Value
```

`reflect.Value.Index`:

```go
func (v Value) Index(i int) Value
```

`reflect.Value.CanSet`:

```go
func (v Value) CanSet() bool
```

`reflect.Value.String`:

```go
func (v Value) String() string
```

`reflect.Value.Int`:

```go
func (v Value) Int() int64
```

`reflect.Value.SetString`:

```go
func (v Value) SetString(x string)
```

`reflect.Value.SetInt`:

```go
func (v Value) SetInt(x int64)
```

`reflect.Value.MethodByName`:

```go
func (v Value) MethodByName(name string) Value
```

`reflect.Value.Call`:

```go
func (v Value) Call(in []Value) []Value
```

`reflect.Kind.String`:

```go
func (k Kind) String() string
```

`reflect.Type.Kind`:

```go
Kind() Kind
```

`reflect.Type.Name`:

```go
Name() string
```

`reflect.Type.PkgPath`:

```go
PkgPath() string
```

`reflect.Type.NumField`:

```go
NumField() int
```

`reflect.Type.Field`:

```go
Field(i int) StructField
```

`reflect.Type.FieldByName`:

```go
FieldByName(name string) (StructField, bool)
```

`reflect.Type.Elem`:

```go
Elem() Type
```

`reflect.Type.Implements`:

```go
Implements(u Type) bool
```

`reflect.Type.NumMethod`:

```go
NumMethod() int
```

`reflect.Type.MethodByName`:

```go
MethodByName(string) (Method, bool)
```

`reflect.Type.NumIn`:

```go
NumIn() int
```

`reflect.Type.NumOut`:

```go
NumOut() int
```

`reflect.Type.String`:

```go
String() string
```

`reflect.StructTag.Get`:

```go
func (tag StructTag) Get(key string) string
```

- `reflect.Complex64`: reflect.Kind constant.

- `reflect.Complex128`: reflect.Kind constant.

Public named type: `reflect.Value`.

Public fields (qualified by their containing type):

- `StructField.Name`: `string`.
- `StructField.Type`: `Type`.
- `StructField.Tag`: `StructTag`.
- `Method.Name`: `string`.
- `Method.Type`: `Type`.

## `unsafe`

Import path: `unsafe`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`unsafe.Sizeof`:

```go
func Sizeof(x ArbitraryType) uintptr
```

`unsafe.Alignof`:

```go
func Alignof(x ArbitraryType) uintptr
```

`unsafe.Offsetof`:

```go
func Offsetof(x ArbitraryType) uintptr
```

`unsafe.Slice`:

```go
func Slice(ptr *ArbitraryType, len IntegerType) []ArbitraryType
```

`unsafe.SliceData`:

```go
func SliceData(slice []ArbitraryType) *ArbitraryType
```

`unsafe.String`:

```go
func String(ptr *byte, len IntegerType) string
```

`unsafe.StringData`:

```go
func StringData(str string) *byte
```

`unsafe.Add`:

```go
func Add(ptr Pointer, len IntegerType) Pointer
```

```go
type Pointer *ArbitraryType
```

Qualified type names: `unsafe.Pointer`.

## `testing`

Import path: `testing`. These are the public Go call and value forms available to source programs. Signatures use Go 1.26 public types. Error results carry success as `nil` and failure as a non-nil `error`.

`testing.Short`:

```go
func Short() bool
```

`testing.T.Deadline`:

```go
func (t *T) Deadline() (deadline time.Time, ok bool)
```

`testing.T.Run`:

```go
func (t *T) Run(name string, f func(t *T)) bool
```

`testing.T.Skip`:

```go
func (c *T) Skip(args ...any)
```

`testing.T.Error`:

```go
func (c *T) Error(args ...any)
```

`testing.T.Fatal`:

```go
func (c *T) Fatal(args ...any)
```

`testing.B.Fatal`:

```go
func (c *B) Fatal(args ...any)
```

`testing.M.Run`:

```go
func (m *M) Run() (code int)
```

Public named type: `testing.T`.

Public named type: `testing.B`.

Public named type: `testing.M`.

Public fields (qualified by their containing type):

- `B.N`: `int`.

## `.go`

Source files carry Go source text. Source packages occupy `<root>/<import-path>/` with `.go` source files and package-relative assets. Target-suffixed source filenames have the forms `<name>_<GOOS>.go`, `<name>_<GOARCH>.go`, and `<name>_<GOOS>_<GOARCH>.go`. Build-constraint syntax is `//go:build <expression>` or `// +build <terms>`. A file-embedding directive is `//go:embed <relative-file>`, associated with its variable declaration. Package test sources use the suffix `_test.go`.

## `builtin`

Go source uses its predeclared types and identifiers. The following call notation uses type placeholders, not additional declarations:

| Name | Arguments | Result carrier |
| --- | --- | --- |
| `len`, `cap` | One Go value. | `int`. |
| `append` | Slice and variadic elements, or an expanded slice. | Slice of the input slice's type. |
| `copy` | Destination slice and source slice or string. | `int` copied-element count. |
| `make` | Slice, map or channel type, with size arguments. | Value of that type. |
| `new` | A type. | Pointer to that type. |
| `delete` | Map and key. | No value. |
| `clear` | Map or slice. | No value. |
| `close` | Channel. | No value. |
| `min`, `max` | Ordered scalar operands. | Scalar of the expression's Go result type. |
| `complex` | Real and imaginary operands. | Complex scalar. |
| `real`, `imag` | Complex operand. | Floating component. |
| `panic` | Panic value. | No ordinary result. |
| `recover` | No arguments. | `any` recovered value. |
| `print`, `println` | Variadic printable values. | No value; bytes on program output. |

`print` writes displayed text without adding a newline. `println` separates displayed operands with spaces and ends with newline.

## `trap`

The Go builtin call `trap()` has no arguments or result. Debugger input is newline-delimited on stdin. The commands used are `stack` and `cont`; input also ends through stdin EOF. Debugger output is on stderr.

A stop emits `trap at ip=<opaque> (<source>:<line>:<column>)` followed by the prompt `debug> `. Source line and column are one-based decimal integers. An unrecognized command emits a line beginning `unknown command:` followed by another prompt.

The stack report begins `=== Call Stack ===`. Each call group begins `--- Frame <metadata> ---`; its rows have this form:

```text
  mem[<id>] <role>  <type>  <value>[ // <annotation>][ <markers>]
```

The id is decimal; the role, frame metadata, annotations and markers are opaque text. Spaces may pad the id inside the brackets. The role contains words separated by single spaces; at least two spaces separate the role from the type and the type from the value. Integer rows have type `int` and a signed decimal value ending at the next space or end of line. Any remaining annotation or marker text is opaque. Group boundaries delimit the current call followed by its callers. The current call is the first group. A subsequent `--- Globals ---` header ends the call groups. The prompt terminates the report.
