# Interface Contract

The product is the embedded `velnora` package. Native Rust callers import `velnora`; C callers include `include/velnora.h` and link `target/release/libvelnora.so`. The executable is `target/release/velnora`, invoked as `velnora` from a caller-selected working directory. WebAssembly hosts import `docs/assets/wasm/velnora.js` and initialize it with `docs/assets/wasm/velnora_bg.wasm`.

SQL source, text cells, SQL files and textual process output use UTF-8. SQL keywords and function names are case-insensitive; Rust, C and JavaScript names are case-sensitive. SQL string literals use single quotes, with doubled single quotes inside; identifiers may be double-quoted. Positional bindings use `$1`, `$2`, and subsequent one-based positions. Named bindings use `:name`. SQL comments use `--` through line end or `/* ... */`; statements use `;` separators.

Native calls return results through their API and emit no stdout. Rust failure uses `Err(Error)`; C failure uses its status return. Error Display/Debug text is diagnostic text. Native diagnostics may appear on stderr and carry the failed operation and its cause; wording is free. The command page specifies process channels and statuses.

Result cells occupy projection order. Supplied aliases are column names; ordinary selected columns use their declared names. Empty results retain column metadata. Each host uses its specified cell representation and success/failure carrier.

Non-row execution returns an integer affected-row count. Diagnostic prose must not masquerade as a structured result.

A file database occupies the caller-selected `file://` directory.

The required build provides the Rust link artifact `target/release/libvelnora.rlib` and its dependency search directory `target/release/deps`. Relative to an explicitly selected Cargo target directory, these are `release/libvelnora.rlib` and `release/deps`. External Rust clients use edition 2021 and aborting panic compatibility.

## `velnora`

Rust package and import root: `velnora`. Caller-facing exports are `Database`, `Rows`, `ResultRow`, `Statement`, `FromRow`, `FromValue`, `Params`, `NamedParams`, `Value`, `DataType`, `IsolationLevel`, `Result`, `Error`, `SmartString`, and `named_params!`. The application transaction type is `velnora::api::Transaction`, also exported as `ApiTransaction`.

Cargo feature names `ffi`, `heap-profile`, and `semantic` are accepted. `ffi` exposes the C API; `semantic` enables the optional embedding operation. Feature selection uses dependency features. Selecting `heap-profile` imposes no required profiling output. Unavailable SQL operations use the ordinary failure carrier.

## `Database`

Rust `velnora::Database` exposes the following signatures, with no omitted Rust arguments:

```rust
pub fn open(dsn: &str) -> Result<Self>;
pub fn open_in_memory() -> Result<Self>;
pub fn execute<P: Params>(&self, sql: &str, params: P) -> Result<i64>;
pub fn query<P: Params>(&self, sql: &str, params: P) -> Result<Rows>;
pub fn query_one<T: FromValue, P: Params>(&self, sql: &str, params: P) -> Result<T>;
pub fn query_opt<T: FromValue, P: Params>(&self, sql: &str, params: P) -> Result<Option<T>>;
pub fn execute_named(&self, sql: &str, params: NamedParams) -> Result<i64>;
pub fn query_named(&self, sql: &str, params: NamedParams) -> Result<Rows>;
pub fn query_as<T: FromRow, P: Params>(&self, sql: &str, params: P) -> Result<Vec<T>>;
pub fn query_with_timeout<P: Params>(&self, sql: &str, params: P, timeout_ms: u64) -> Result<Rows>;
pub fn prepare(&self, sql: &str) -> Result<Statement>;
pub fn begin(&self) -> Result<velnora::api::Transaction>;
pub fn begin_with_isolation(&self, isolation: IsolationLevel) -> Result<velnora::api::Transaction>;
pub fn dsn(&self) -> &str;
pub fn close(&self) -> Result<()>;
```

Execution returns the affected-row count. Queries return typed rows, with failure possible during invocation or consumption. Scalar success carries the requested Rust type. Optional scalar success has an outer `Option` for row presence; an inner `Option` in `T` represents SQL NULL. Mapped queries return records in row order. Preparation and transaction entry return handles. Close returns unit. `dsn()` returns a connection string suitable for opening another session on the same database. Dropping a database releases its handle and has no return value.

`timeout_ms` is unsigned integer milliseconds. Cancellation returns `Error::QueryCancelled`.

Connection forms are `memory://`, `memory://<name>`, and `file://<directory>`. Options follow `?` and are separated by `&`: `sync_mode=none|normal|full`, `checkpoint_interval=<integer seconds>`, `checkpoint_on_close=on|off`, `wal_flush_trigger=<integer bytes>`, and `keep_snapshots=<integer count>`. File operations can create and modify the selected database directory. Persistent storage occupies that directory and may include nested directories and regular files; their names and file contents are opaque.

## `Rows`

Rust `velnora::Rows` exposes:

```rust
pub fn columns(&self) -> &[String];
pub fn collect_vec(self) -> Result<Vec<ResultRow>>;
```

`columns()` returns ordered column names. `collect_vec()` consumes the result into all its rows or an error; empty success is an empty vector. `Rows` also implements `Iterator<Item = Result<ResultRow>>`: a row is `Some(Ok(row))`, failure is `Some(Err(error))`, and exhaustion is `None`. There is no printed result output.

## `ResultRow`

Rust `velnora::ResultRow` exposes:

```rust
pub fn get<T: FromValue>(&self, index: usize) -> Result<T>;
pub fn get_by_name<T: FromValue>(&self, name: &str) -> Result<T>;
pub fn get_value(&self, index: usize) -> Option<&Value>;
pub fn len(&self) -> usize;
```

Positions are zero-based. `len()` counts cells; `get_value()` returns a borrowed cell or `None` for an absent position. Typed access returns `Ok(T)` or `Err(Error)`; `Option<T>` represents SQL NULL with `None`. Names are the exposed column-name strings. These reads do not modify rows. The type supports `Clone` and `Debug`.

## `FromRow`

Rust trait `velnora::FromRow`:

```rust
pub trait FromRow: Sized {
    fn from_row(row: &ResultRow) -> Result<Self>;
}
```

Applications implement the callback for their record type. It returns a record or error; mapped queries carry the records in a vector. Record fields and callback side effects are caller-defined.

## `FromValue`

Rust conversion trait `velnora::FromValue`:

```rust
pub trait FromValue: Sized {
    fn from_value(value: &Value) -> Result<Self>;
}
```

Typed reads support `i64`, `f64`, `bool`, `String`, and `Option<T>` for these types. Success carries the converted value; failure carries `Error`. `Option<T>` represents SQL NULL with `None`. Error prose is free.

## `Params`

`velnora::Params` is the parameter bound on database and prepared calls. Accepted argument forms include `()`, tuples of supported scalar parameters, `Vec<Value>`, `&[Value]`, and `[Value; N]`. Scalar parameters include signed integers, floating-point values, `bool`, `&str`, `String`, `Value`, and optional scalar values. The sequence occupies one-based SQL binding positions in order. `()` supplies no bindings. No Rust call arguments are optional.

## `NamedParams`

`velnora::NamedParams` is the named-binding argument type for `execute_named` and `query_named`. Names are strings without the SQL `:` prefix; values are supported scalar parameters. `named_params!` constructs this argument.

## `named_params`

The exported Rust macro `velnora::named_params!` accepts `named_params! { name: value, ... }`, including an optional trailing comma, and yields `NamedParams`. Names are Rust identifiers corresponding to SQL `:name` bindings; values are supported parameter expressions. It prints nothing.

## `Statement`

Rust `velnora::Statement`, returned by `Database::prepare`, exposes:

```rust
pub fn execute<P: Params>(&self, params: P) -> Result<i64>;
pub fn query<P: Params>(&self, params: P) -> Result<Rows>;
pub fn query_one<T: FromValue, P: Params>(&self, params: P) -> Result<T>;
```

Success carries an affected-row count or ordinary query rows; the single-value method returns the requested application type. Failure carries `Error`. Parameters use the same accepted argument forms as database calls. The handle is reusable; dropping it has no return value. Calls have the SQL statement's database side effects and no separate printed format.

## `velnora::api::Transaction`

Application transaction type `velnora::api::Transaction` exposes:

```rust
pub fn execute<P: Params>(&mut self, sql: &str, params: P) -> Result<i64>;
pub fn query<P: Params>(&mut self, sql: &str, params: P) -> Result<Rows>;
pub fn commit(&mut self) -> Result<()>;
pub fn rollback(&mut self) -> Result<()>;
```

SQL methods return the usual affected count or row handle. Completion returns unit on success and `Error` on failure. Drop has no return value.

## `IsolationLevel`

Rust `velnora::IsolationLevel` exposes selectable variants `ReadCommitted` and `SnapshotIsolation` for `begin_with_isolation`. It supports `Copy`, `Clone`, `Debug`, and equality.

## `Result`

`velnora::Result<T>` is `std::result::Result<T, Error>`. `Ok(T)` carries success; `Err(Error)` carries failure. An error is distinct from an empty successful row vector. Standard Rust result matching and methods are available.

## `Error`

Rust `velnora::Error` carries native API failure. Cancellation has the public unit variant `Error::QueryCancelled`. The type supports `Debug`, `Display`, and `std::error::Error`; diagnostic text is free text, the implementer's choice. Failure may arise during invocation or complete row consumption.

## `Value`

Rust `velnora::Value` has matchable variants `Null(DataType)`, `Integer(i64)`, `Float(f64)`, `Boolean(bool)`, `Text(SmartString)`, `Timestamp(DateTime<Utc>)`, and `Extension(_)`. `Null` carries SQL NULL with a type hint. `Text` carries UTF-8 text. `Timestamp` carries a chrono `DateTime<Utc>`. `Extension(_)` is an opaque JSON or vector payload.

```rust
pub fn null_unknown() -> Self;
pub fn vector(data: Vec<f32>) -> Self;
pub fn data_type(&self) -> DataType;
pub fn is_null(&self) -> bool;
pub fn as_json(&self) -> Option<&str>;
pub fn as_vector_f32(&self) -> Option<Vec<f32>>;
```

`Value::from` accepts `i64`, `i32`, `f64`, `f32`, `bool`, `String`, and `&str`. The type supports `Clone`, `Debug`, and equality. `as_json()` exposes JSON text. `as_vector_f32()` exposes ordered components. These accessors return `None` for other value families. `is_null()` returns a nullness boolean; `data_type()` returns a public tag. SQL NULL is not text or a numeric sentinel.

Timestamp payloads expose `to_rfc3339() -> String` in the form `YYYY-MM-DDTHH:MM:SS[.fraction]+00:00`: at most nine fractional digits, with the fraction omitted for whole seconds. Text payloads support `as_str() -> &str`.

## `DataType`

Rust `velnora::DataType` variants are `Null`, `Integer`, `Float`, `Text`, `Boolean`, `Timestamp`, `Json`, and `Vector`. It supports `Copy`, `Clone`, `Debug`, and equality. This is the result tag from `Value::data_type()` and the type hint in `Value::Null`.

## `SmartString`

Rust `velnora::SmartString`, the `Value::Text` payload, exposes `pub fn as_str(&self) -> &str`. This returns borrowed UTF-8 text.

## `velnora.h`

C declarations are in `include/velnora.h`, included as `#include "velnora.h"`. Link with `target/release/libvelnora.so`. Functions use the C ABI and fixed-width integer types from `<stdint.h>`.

`VelnoraDB`, `VelnoraStmt`, `VelnoraTx`, and `VelnoraRows` are opaque handles. SQL arguments are NUL-terminated UTF-8. Column positions are zero-based. Out-handle pointers receive handles on success. Operation status uses `VELNORA_OK` or `VELNORA_ERROR`; row advancement has separate statuses. Counts are signed 64-bit integers. Returned pointers are borrowed unless ownership is explicitly transferred.

Database and statement handles must not be used concurrently. Row and transaction handles stay on their creating thread. Error prose is free. There are no required printed C result records.

## `VelnoraValue`

C `VelnoraValue` is the parameter struct in `velnora.h`. The used fields are `int32_t value_type` and union `v`. Integer parameters set `VELNORA_TYPE_INTEGER` and `v.integer` (`int64_t`). Text parameters set `VELNORA_TYPE_TEXT`, `v.text.ptr` (`const char*`) and `v.text.len` (`int64_t`, UTF-8 byte length). Floating-point parameters set `VELNORA_TYPE_FLOAT` and `v.float64` (`double`). Boolean parameters set `VELNORA_TYPE_BOOLEAN` and `v.boolean` (`int32_t`, `0` for false or `1` for true). Input storage remains valid during the call. Zero initialization with `{0}` is accepted. The header supplies the complete struct; unused members and padding are not caller data.

## `velnora.js`

The ES module `docs/assets/wasm/velnora.js` exports `VelnoraDB` and a default asynchronous initializer. Use `await api.default({module_or_path: bytes})`, where `bytes` contains `docs/assets/wasm/velnora_bg.wasm`. Initialize before constructing a database. Initialization failure rejects the promise.

The JavaScript host provides standard ECMAScript globals and ES modules, including relative module imports, together with `WebAssembly`, `TextEncoder`, `TextDecoder`, `URL`, `URLSearchParams`, `crypto`, `performance`, `console`, `setTimeout`, `clearTimeout`, `setInterval`, `clearInterval`, `queueMicrotask`, `atob`, and `btoa`. The initializer receives a `Uint8Array` containing the module bytes; no DOM APIs are required.

## `VelnoraDB`

### JavaScript

Exported by `velnora.js`:

```typescript
constructor();
execute(sql: string): string;
execute_batch(sql: string): string;
free(): void;
```

Execution returns a string containing exactly one of these JSON object shapes:

```text
{"type":"rows","columns":[<string>,...],"rows":[[<cell>,...],...],"count":<integer>}
{"type":"affected","affected":<integer>}
{"type":"error","message":<string>}
```

`columns` is the ordered column-name array; `rows` contains cell arrays; `count` is the returned row count; `affected` is the affected-row count. Cells carry JSON numbers, booleans, strings, null or structured JSON values as appropriate. These result objects have no extra fields. `message` is free diagnostic text. The batch input is semicolon-separated SQL source. `free()` releases the object and returns no value. Methods do not print result records.

### C

`typedef struct VelnoraDB VelnoraDB;` declares a separate opaque C handle in `velnora.h`, passed as `VelnoraDB*`. It has no public fields and is accessed through C functions.

## `VELNORA_OK`

C macro: `#define VELNORA_OK 0` in `velnora.h`. The integer denotes successful operation.

## `VELNORA_ERROR`

C macro: `#define VELNORA_ERROR 1` in `velnora.h`. The integer denotes failed operation.

## `VELNORA_ROW`

C macro: `#define VELNORA_ROW 100` in `velnora.h`. The integer denotes available current row.

## `VELNORA_DONE`

C macro: `#define VELNORA_DONE 101` in `velnora.h`. The integer denotes exhausted result.

## `VELNORA_TYPE_NULL`

C macro: `#define VELNORA_TYPE_NULL 0` in `velnora.h`. The integer denotes SQL NULL.

## `VELNORA_TYPE_INTEGER`

C macro: `#define VELNORA_TYPE_INTEGER 1` in `velnora.h`. The integer denotes integer.

## `VELNORA_TYPE_TEXT`

C macro: `#define VELNORA_TYPE_TEXT 3` in `velnora.h`. The integer denotes text.

## `VELNORA_ISOLATION_READ_COMMITTED`

C macro: `#define VELNORA_ISOLATION_READ_COMMITTED 0` in `velnora.h`. The integer denotes read-committed isolation selection.

## `VELNORA_ISOLATION_SNAPSHOT`

C macro: `#define VELNORA_ISOLATION_SNAPSHOT 1` in `velnora.h`. The integer denotes snapshot isolation selection.

## `VelnoraStmt`

`typedef struct VelnoraStmt VelnoraStmt;` in `velnora.h` declares an opaque C handle, passed as `VelnoraStmt*`. No fields or binary layout are public.

## `VelnoraTx`

`typedef struct VelnoraTx VelnoraTx;` in `velnora.h` declares an opaque C handle, passed as `VelnoraTx*`. No fields or binary layout are public.

## `VelnoraRows`

`typedef struct VelnoraRows VelnoraRows;` in `velnora.h` declares an opaque C handle, passed as `VelnoraRows*`. No fields or binary layout are public.

## `velnora_open_in_memory`

```c
int32_t velnora_open_in_memory(VelnoraDB** out_db);
```

Writes a database handle to `out_db` on success. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_clone`

```c
int32_t velnora_clone(const VelnoraDB* db, VelnoraDB** out_db);
```

Writes another database handle to `out_db`; each handle is closed independently. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_close`

```c
int32_t velnora_close(VelnoraDB* db);
```

Consumes the database handle; the pointer is invalid after closing. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_exec`

```c
int32_t velnora_exec(VelnoraDB* db, const char* sql, int64_t* rows_affected);
```

The count pointer may be NULL; otherwise success writes the affected-row count. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_query`

```c
int32_t velnora_query(VelnoraDB* db, const char* sql, VelnoraRows** out_rows);
```

Success writes a result handle, released with `velnora_rows_close`. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_prepare`

```c
int32_t velnora_prepare(VelnoraDB* db, const char* sql, VelnoraStmt** out_stmt);
```

Success writes a prepared handle, released with `velnora_stmt_finalize`. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_stmt_exec`

```c
int32_t velnora_stmt_exec(VelnoraStmt* stmt, const VelnoraValue* params, int32_t params_len, int64_t* rows_affected);
```

The parameter pointer addresses `params_len` values and may be NULL for zero parameters. The count pointer may be NULL; otherwise success writes the affected-row count. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_stmt_query`

```c
int32_t velnora_stmt_query(VelnoraStmt* stmt, const VelnoraValue* params, int32_t params_len, VelnoraRows** out_rows);
```

The parameter pointer addresses `params_len` values and may be NULL for zero parameters. Success writes a result handle. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_begin`

```c
int32_t velnora_begin(VelnoraDB* db, VelnoraTx** out_tx);
```

Success writes a transaction handle. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_begin_with_isolation`

```c
int32_t velnora_begin_with_isolation(VelnoraDB* db, int32_t isolation, VelnoraTx** out_tx);
```

Isolation is `VELNORA_ISOLATION_READ_COMMITTED` or `VELNORA_ISOLATION_SNAPSHOT`. Success writes a transaction handle. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_tx_exec`

```c
int32_t velnora_tx_exec(VelnoraTx* tx, const char* sql, int64_t* rows_affected);
```

The count pointer may be NULL; otherwise success writes the affected-row count. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_tx_query`

```c
int32_t velnora_tx_query(VelnoraTx* tx, const char* sql, VelnoraRows** out_rows);
```

Success writes a result handle. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_tx_commit`

```c
int32_t velnora_tx_commit(VelnoraTx* tx);
```

Consumes the transaction handle regardless of status. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_tx_rollback`

```c
int32_t velnora_tx_rollback(VelnoraTx* tx);
```

Consumes the transaction handle regardless of status. Returns `VELNORA_OK` on success and `VELNORA_ERROR` on failure. No required printed output.

## `velnora_rows_next`

```c
int32_t velnora_rows_next(VelnoraRows* rows);
```

Returns `VELNORA_ROW`, `VELNORA_DONE`, or `VELNORA_ERROR`. Row status makes the current row available to column accessors.

## `velnora_rows_column_count`

```c
int32_t velnora_rows_column_count(const VelnoraRows* rows);
```

Returns the result column count, including before advancement.

## `velnora_rows_column_name`

```c
const char* velnora_rows_column_name(const VelnoraRows* rows, int32_t index);
```

Returns a NUL-terminated name at the zero-based index, valid until result close, or NULL for an absent position.

## `velnora_rows_column_type`

```c
int32_t velnora_rows_column_type(const VelnoraRows* rows, int32_t index);
```

Returns the public `VELNORA_TYPE_*` tag of the current cell after successful row advancement.

## `velnora_rows_column_int64`

```c
int64_t velnora_rows_column_int64(const VelnoraRows* rows, int32_t index);
```

Returns the integer cell value. Nullness and type have separate accessors.

## `velnora_rows_column_text`

```c
const char* velnora_rows_column_text(VelnoraRows* rows, int32_t index, int64_t* out_len);
```

Returns borrowed UTF-8 text valid until the next advancement. A non-NULL length pointer receives the byte count excluding the terminating NUL. SQL NULL returns NULL; empty text returns a non-NULL pointer and zero length.

## `velnora_rows_column_is_null`

```c
int32_t velnora_rows_column_is_null(const VelnoraRows* rows, int32_t index);
```

Returns `1` for SQL NULL and `0` for a present cell.

## `velnora_rows_close`

```c
void velnora_rows_close(VelnoraRows* rows);
```

Releases the handle and borrowed pointers. Call after exhaustion as well. No return value.

## `velnora_stmt_finalize`

```c
void velnora_stmt_finalize(VelnoraStmt* stmt);
```

Releases the statement handle. No return value.

## `target/release/velnora`

Command `velnora` is available at `target/release/velnora`; its path relative to the build target directory is `release/velnora`. Relative paths use the invoking working directory.

| Option | Argument and outward meaning |
| --- | --- |
| `-d`, `--db` | Connection string |
| `-q`, `--quiet` | No argument; suppress connection messages |
| `-j`, `--json` | No argument; select JSON presentation |
| `-l`, `--limit` | Nonnegative integer display cap |
| `-e`, `--execute` | One SQL source argument |
| `-f`, `--file` | UTF-8 SQL file path |
| `--snapshot` | No argument; request a backup and exit |
| `--restore` | Optional `YYYYMMDD-HHMMSS.fff` timestamp |

Without `-e` or `-f`, redirected stdin carries UTF-8 SQL. Terminal stdin selects interactive input. Commands include `BEGIN`, `COMMIT`, `ROLLBACK`, and `exit`; transaction commands may omit the trailing semicolon. SQL statements may span lines and terminate with `;`.

With `-q -j`, noninteractive stdout contains only newline-terminated JSON records, one per successful statement. Query objects have `columns: string[]`, `rows: array<array<JSON cell>>`, and `count: integer` (returned row count). Mutation objects have exactly `{"rows_affected":<integer>}`. Cells preserve numbers, booleans, strings and null. A failed statement emits no result record.

Without `-j`, table headers and data lines use the delimiter ` | `. Header fields are column names; data fields are cell text. Integer fields are signed decimal; text is the cell text. Decorations have no ` | ` fields. Without `-q`, noninteractive non-JSON mutation stdout contains a line `<signed decimal integer> rows affected`; the integer is the affected-row count.

Interactive JSON objects occupy a stdout line suffix, from opening `{` to line end, optionally preceded by prompt text. The query and mutation object shapes above are reserved for results. Interactive errors appear on stderr as `Error: <nonempty free diagnostic>`, optionally ANSI SGR styled. Blank lines and `Warning: <free diagnostic>` may accompany exit. Normal interactive exit has status `0`.

Successful noninteractive execution exits `0`; quiet success has empty stderr. Failed one-command SQL or input-file opening exits `1` with stderr `Error: <nonempty free diagnostic>`. Database-open failure exits `1` with stderr `Error opening database: <nonempty free diagnostic>`. SQL errors in file or redirected-input execution emit stderr `Error: <nonempty free diagnostic>` while the process exits `0`. With `-q -j`, failed statements have no stdout record. Other diagnostic text is free and must not be a result record.

Successful backup and restore exit `0`, return control, and have empty stderr with `-q`. File-backed calls may modify the selected database directory; backup file contents and other persistent formats are opaque.

## `SELECT`

SQL request form:

```sql
SELECT [DISTINCT | DISTINCT ON (<expressions>)] <projection>
[FROM <source> [<join> ...]]
[WHERE <predicate>]
[GROUP BY <grouping>]
[HAVING <predicate>]
[WINDOW <name> AS (<window specification>)]
[ORDER BY <expression> [ASC|DESC] [NULLS FIRST|NULLS LAST] [, ...]]
[LIMIT <count>] [OFFSET <count>]
```

A projection is a comma-separated list of expressions, optionally `AS <alias>`, or `*` or `<source>.*`. Sources include a table or view with an optional `AS <alias>`, a parenthesized query with an alias, `(VALUES (<expressions>), ...) AS <alias>(<column names>)`, or a table-valued function. Numeric limits and offsets are nonnegative integers.

Join forms are `[INNER|LEFT|RIGHT|FULL OUTER] JOIN <source> ON <predicate>`, the corresponding `USING (<columns>)` forms, `NATURAL JOIN <source>`, and `CROSS JOIN <source>`. In a `SELECT *` result using `USING` or `NATURAL`, shared column names are `<column>` and nonshared names are `<source>.<column>`. Each result's ordered column metadata identifies the positions in that result's rows. Explicitly selected derived-table columns use unqualified output names.

Grouping syntax accepts comma-separated expressions, `ROLLUP(<expressions>)`, `CUBE(<expressions>)`, or `GROUPING SETS (<grouping set> [, ...])`, where each grouping set is `(<expressions>)` or `()`. Window syntax is `OVER (<window specification>)`, `OVER <name>`, or `OVER (<name> ROWS|RANGE BETWEEN <bound> AND <bound>)`. A specification accepts `PARTITION BY <expressions>`, `ORDER BY <expressions>`, and either `ROWS|RANGE BETWEEN <bound> AND <bound>` or `ROWS <bound>`. Each part may be omitted, including all parts in `OVER ()`. Bounds are `UNBOUNDED PRECEDING`, `UNBOUNDED FOLLOWING`, `CURRENT ROW`, or `<nonnegative offset> PRECEDING|FOLLOWING`.

Subquery expression forms are `(<query>)`, `EXISTS (<query>)`, `NOT EXISTS (<query>)`, `<expr> IN (<query>)`, `<expr> NOT IN (<query>)`, and `<expr> <comparison> ANY|ALL (<query>)`. Their cells use ordinary scalar or SQL NULL representations.

A historical table source adds `AS OF TRANSACTION <integer identifier>` or `AS OF TIMESTAMP <timestamp selector>` before its alias. A timestamp selector may be an integer Unix nanosecond timestamp or timestamp text in a SQL string. This selector is input syntax; result metadata and cell forms are unchanged.

Success returns ordinary projected typed rows and ordered column metadata; failures use the host error carrier.

Expression operator spellings are `+`, `-`, `*`, `/`, `%`, unary `-`, `&`, `|`, `^`, `~`, `<<`, `>>`, `=`, `<>`, `<`, `<=`, `>`, `>=`, `AND`, `OR`, `XOR`, `NOT`, `BETWEEN ... AND ...`, `[NOT] IN (...)`, `IS NULL`, `IS NOT NULL`, and `IS NOT DISTINCT FROM`. Pattern forms are `<text> LIKE|ILIKE <pattern> [ESCAPE <character>]`, `<text> GLOB <pattern>`, and `<text> REGEXP <pattern>`. SQL-pattern metacharacters are `%` and `_`; shell patterns use `*`, `?`, and bracketed character sets or ranges. Regular-expression source is a text argument. Predicates expose Boolean or SQL NULL cells. Arithmetic and bitwise expressions expose numeric or SQL NULL cells.

Timestamp arithmetic accepts `<timestamp> +|- INTERVAL '<count> <unit>'`, using unit spellings `second`, `minute`, `hour`, `day`, `week`, `month`, and `year`. JSON extraction operators are `<json> -> <key or index>` and `<json> ->> <key or index>`; object keys are text and array indices are zero-based integers. JSON-valued extraction uses a JSON value, text-valued extraction uses text, and absent SQL values use SQL NULL.

## `WITH`

SQL prefix syntax is `WITH [RECURSIVE] <name> [(<column names>)] AS (<query>) [, ...] <statement>`. The following statement may be `SELECT`, `INSERT`, `UPDATE`, or `DELETE`. A recursive definition accepts `<query> UNION ALL <query> [UNION ALL <query> ...]` inside its parentheses. Aliases are caller-supplied identifiers. Results and errors have the following statement's ordinary host form; there is no separate WITH result envelope.

## `CREATE TABLE`

SQL: `CREATE TABLE [IF NOT EXISTS] <table> (<definitions>)` or `CREATE TABLE <table> AS <query>`.

A column definition is `<column> <type> [<constraints>]`. Type spellings include `INTEGER`, `FLOAT`, `TEXT`, `BOOLEAN`, `TIMESTAMP`, `JSON`, and `VECTOR(<dimension>)`, where dimension is a positive integer. Scalar literals use signed decimal integers, decimal/exponent floating-point numbers, single-quoted text, `TRUE`, `FALSE`, and `NULL`. Timestamp text accepts a date or date/time with an optional fractional second and offset, including RFC3339. Vector text is a bracketed comma-separated list of numeric components.

Column constraints have spellings `PRIMARY KEY`, `AUTO_INCREMENT`, `UNIQUE`, `NOT NULL`, `DEFAULT <expression>`, `CHECK (<predicate>)`, and `REFERENCES <table>(<column>) [ON DELETE <action>] [ON UPDATE <action>]`. Actions are `RESTRICT`, `NO ACTION`, `CASCADE`, and `SET NULL`. Table constraints include `PRIMARY KEY (<columns>)` and `UNIQUE (<columns>)`. Definitions and column lists are comma-separated. Defaults may be literals or `CURRENT_TIMESTAMP`.

Execution success returns the native affected-count carrier, with no prescribed DDL count. Failure uses the ordinary error carrier. The resulting schema is inspected through SQL metadata results; no schema file format is prescribed.

## `ALTER TABLE`

SQL forms:

```sql
ALTER TABLE <table> ADD COLUMN <column> <type> [<constraints>]
ALTER TABLE <table> DROP COLUMN <column>
ALTER TABLE <table> RENAME COLUMN <old> TO <new>
ALTER TABLE <table> RENAME TO <new>
ALTER TABLE <table> MODIFY COLUMN <column> <type> [NOT NULL]
```

Names, types and column constraints use the ordinary SQL forms. Execution returns an affected-count success carrier, or the host error carrier.

After a vector-to-TEXT conversion, nonmissing cells carry text `[<number>, ...]` containing the ordered numeric components.

## `DROP TABLE`

SQL: `DROP TABLE [IF EXISTS] <table>`. Success uses the affected-count carrier. Failure uses the ordinary host error carrier.

## `DESCRIBE`

SQL: `DESCRIBE <table>`. Query output has columns `Field`, `Type`, `Null`, `Key`, `Default`, `Extra`, in that order, with one row per declared column in declaration order. Each cell is text. `Field` is the column name. `Type` uses `Integer`, `Float`, `Text`, `Boolean`, `Timestamp`, `Json`, or `Vector` for the corresponding declared family. `Null` uses `YES` for nullable and `NO` for nonnullable.

`Key`, `Default`, and `Extra` contain constraint, default-expression and additional-column descriptions respectively. Failure uses the ordinary host error carrier.

## `SHOW TABLES`

SQL: `SHOW TABLES`. Output has one text column `table_name`, containing table names. An empty catalog is an empty row sequence with this metadata. Failure uses the host error carrier.

## `SHOW CREATE TABLE`

SQL: `SHOW CREATE TABLE <table>`. Output is one row with ordered text fields `Table` (table name) and `Create Table` (an executable CREATE TABLE definition). Failure uses the host error carrier.

## `INSERT`

SQL forms:

```sql
INSERT INTO <table> [(<columns>)] VALUES (<expressions>) [, ...]
INSERT INTO <table> [(<columns>)] <query>
```

Either form may be followed by `ON CONFLICT [(<columns>)] DO NOTHING` or `ON CONFLICT [(<columns>)] DO UPDATE SET <column>=<expression> [, ...] [WHERE <predicate>]`. In conflict expressions, `excluded.<column>` names a proposed value and `<table>.<column>` names a target value. An optional `RETURNING <projection>` follows the statement; its projection accepts expressions or `*`.

Execution exposes the affected-row count as an integer. A query call with RETURNING exposes typed projected cells in ordinary rows. Failure uses the ordinary host carrier. No returned row identifiers or additional status fields are implicit.

## `UPDATE`

SQL: `UPDATE <table> SET <column>=<expression|DEFAULT> [, ...] [WHERE <predicate>] [RETURNING <projection>]`. Execution exposes an integer affected-row count. RETURNING through a query call exposes ordinary typed projected rows. Failure uses the host error carrier.

## `DELETE`

SQL: `DELETE FROM <table> [WHERE <predicate>] [RETURNING <projection>]`. Execution exposes an integer affected-row count. RETURNING through a query call exposes ordinary typed projected rows. Failure uses the host error carrier.

## `TRUNCATE TABLE`

SQL: `TRUNCATE TABLE <table>`. Execution returns an affected-count success carrier, or the ordinary host error carrier. Schema inspection uses the ordinary metadata commands.

## `BEGIN`

SQL: `BEGIN` or `BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED` or `BEGIN TRANSACTION ISOLATION LEVEL SNAPSHOT`. Input is SQL source through the ordinary execution entry. Success and failure use ordinary native result carriers; no affected count or query-result fields are fixed for this command. Interactive command presentation is specified on the CLI page.

## `COMMIT`

SQL: `COMMIT`. Success and failure use ordinary host carriers; no affected count or query-result fields are fixed. Interactive command presentation is specified on the CLI page.

## `ROLLBACK`

SQL: `ROLLBACK` or `ROLLBACK TO SAVEPOINT <name>`. The savepoint name is an SQL identifier. Success and failure use ordinary host carriers; no affected count or query-result fields are fixed. Interactive command presentation is specified on the CLI page.

## `SAVEPOINT`

SQL: `SAVEPOINT <name>`. The name is an SQL identifier. Success and failure use ordinary host carriers; no affected count or query-result fields are fixed.

## `RELEASE SAVEPOINT`

SQL: `RELEASE SAVEPOINT <name>`. The name is an SQL identifier. Success and failure use ordinary host carriers; no affected count or query-result fields are fixed.

## `SET ISOLATION_LEVEL`

SQL: `SET ISOLATION_LEVEL = 'READ COMMITTED'` or `SET ISOLATION_LEVEL = 'SNAPSHOT'`. Success and failure use ordinary host carriers; no affected count or query-result fields are fixed.

## `CREATE VIEW`

SQL: `CREATE VIEW [IF NOT EXISTS] <name> [(<column aliases>)] AS <query>`. Names and aliases are SQL identifiers. Success uses the affected-count carrier; failure uses the host error carrier. Definition inspection uses SQL metadata.

## `DROP VIEW`

SQL: `DROP VIEW <name>`. Success uses an affected-count carrier; failure uses the ordinary error carrier.

## `SHOW VIEWS`

SQL: `SHOW VIEWS`. Output has one text column `view_name` containing view names. Empty success is an empty row sequence. Failure uses the host error carrier.

## `SHOW CREATE VIEW`

SQL: `SHOW CREATE VIEW <name>`. Output is one row with text columns `View` (view name) and `Create View` (executable CREATE VIEW definition). Failure uses the host error carrier.

## `CREATE INDEX`

SQL: `CREATE [UNIQUE] INDEX <name> ON <table>(<columns>) [USING <category>] [WITH (<options>)]`. Categories include `BTREE`, `HASH`, `BITMAP`, and `HNSW`. Options are comma-separated `name=value` assignments. For `HNSW`, public option names are `metric`, `m`, `ef_construction`, and `ef_search`; metric values are single-quoted `l2`, `cosine`, or `ip`, and the other values are positive integers.

Execution success uses an affected-count carrier. Failure uses the ordinary error carrier. Catalog results have the SHOW INDEXES form.

A product distribution may include UTF-8 `vector_search.json` at its root to publish its selected operating configuration for approximate Euclidean search. The file is a JSON object whose optional keys are `m`, `ef_construction`, and `ef_search`, with the positive integer values accepted by the corresponding SQL options. Callers pass the declared entries to `CREATE INDEX ... USING HNSW WITH (...)`. An absent file or an empty object selects the product's default index options; omitted keys leave those options unspecified. No other keys are accepted. An unreadable or invalid declaration is an error, not a request to use defaults.

## `DROP INDEX`

SQL: `DROP INDEX <name> ON <table>`. Success uses an affected-count carrier; failure uses the host error carrier.

## `SHOW INDEXES`

SQL: `SHOW INDEXES FROM <table>`. Named result columns are:

| Column | Type and meaning |
| --- | --- |
| `table_name` | Text, owning table |
| `index_name` | Text, index name |
| `column_name` | Text, one column name or `(<column>, <column>, ...)`, in declared column order |
| `index_type` | Text category label: `BTREE`, `HASH`, `BITMAP`, `MULTICOLUMN`, or `HNSW` |
| `is_unique` | Boolean uniqueness marker |
| `options` | Text containing index options |

For HNSW, `options` contains comma-separated `key=value` pairs, including `metric=<metric>`, `m=<integer>`, and `ef_construction=<integer>`. Metric is `l2`, `cosine`, or `ip`. Errors use the ordinary host carrier.

## `PRAGMA`

SQL forms:

```sql
PRAGMA CHECKPOINT
PRAGMA SNAPSHOT
PRAGMA RESTORE
PRAGMA RESTORE = '<timestamp>'
PRAGMA checkpoint_interval
PRAGMA keep_snapshots [= <nonnegative integer>]
PRAGMA sync_mode
PRAGMA wal_flush_trigger
```

The restore selector is `YYYYMMDD-HHMMSS.fff`. Maintenance success uses the ordinary native result carrier; query output, when provided, has a text `result` column carrying free human-readable status.

Setting queries and successful assignments return one integer cell, in one row, with the column named exactly `checkpoint_interval`, `keep_snapshots`, `sync_mode`, or `wal_flush_trigger`. Units are seconds, snapshot count, mode code, and bytes respectively. Mode codes are `0` for `none`, `1` for `normal`, `2` for `full`. Other setting values are the selected integer values. Rejected operations use the ordinary host error carrier.

Backup identities are exposed as files under `<database directory>/snapshots/<table>/snapshot-<timestamp>.bin`, where `<timestamp>` has form `YYYYMMDD-HHMMSS.fff` and is accepted as the restore selector. The backup file contents are opaque. Directory entries other than that filename form carry no backup identity.

## `COPY`

SQL input:

```sql
COPY <table> [(<target columns>)] FROM '<file path>'
WITH (FORMAT CSV|JSON [, HEADER true|false] [, DELIMITER '<character>'] [, NULL '<marker>'])
```

The file path names a local input file; its contents are read using the process's filesystem access. CSV input is UTF-8 delimited records with double-quoted fields, doubled internal quotes and line-separated records; quoted fields may contain delimiters and newlines. `HEADER` selects a header record, `DELIMITER` supplies the field separator, and `NULL` supplies a text marker. Target columns are an ordered SQL identifier list.

JSON input is either a UTF-8 JSON array of objects or JSON Lines with one object per line. Member names are strings naming destination columns; values may be JSON null, booleans, numbers, strings, arrays or objects. CSV field strings and JSON values are the file's cell representation, not SQL source.

Success returns the inserted-row count through the execution API's integer result. Failure uses the ordinary host error carrier. The input file is read, not an output report; database writes use the selected database's private storage format.

## `EXPLAIN`

SQL: `EXPLAIN <statement>` or `EXPLAIN ANALYZE <statement>`. Result rows have one text column `plan`, one plan line per row.

The following labelled carriers are fixed; all angle-bracketed content is supplied for the submitted statement:

```text
-> <free access description> on <table> [<free details>]
Join Cond: (<left expression> <operator> <right expression>)
Filter: (<left expression> <operator> <right expression>)
Group By: <SQL expressions>
Order By: <SQL expressions with ASC or DESC>
Limit: <integer>
<statement header> (actual time=<number><unit>, rows=<integer>)
<free join description> (cost=<number> rows=<integer>)
```

An execution header is `SELECT`, `SELECT DISTINCT` for a distinct selection, or `UPDATE <table>` for UPDATE. Its `actual time` is a finite nonnegative decimal duration with unit `µs`, `ms`, or `s`. `rows` on that header is the actual result-row count. The `cost` and `rows` values in the separate join suffix are estimates. A source line names the source table after ` on `. Predicate text uses SQL identifiers (qualified when supplied), spaces around binary operators and single-quoted string literals. Group and order carriers contain SQL expressions; Limit uses unsigned decimal text. A labelled field has one carrier for the operation it describes, not competing alternative values. Rejection uses the host error carrier.

## `ANALYZE`

SQL: `ANALYZE [<table>]`. Success returns one row with an integer `tables_analyzed` column, the number of analyzed tables. A diagnostic warning uses a stderr line `Warning: <free diagnostic>`. Error prose is unrestricted. The result's success/failure carrier and any warning are distinct outward channels.

## `VACUUM`

SQL: `VACUUM [<table>]`. Completion uses the native success carrier; rejection uses the host error carrier.

## `_sys_table_stats`

SQL-readable relation `_sys_table_stats` exposes `table_name` (text identifying a table) and `row_count` (integer analyzed row count).

## `_sys_column_stats`

SQL-readable relation `_sys_column_stats` exposes `table_name` and `column_name` (text identifiers), `null_count` and `distinct_count` (integer counts), and `min_value` and `max_value` (nullable text containing extrema). Integer extrema use signed decimal text; floating-point extrema use signed decimal text with an optional fractional part and exponent; text extrema carry their text. Boolean extrema are `true` or `false`, without fixed letter case.

## `CASE`

SQL expression forms are `CASE WHEN <predicate> THEN <expression> [WHEN ...] [ELSE <expression>] END` and `CASE <expression> WHEN <expression> THEN <expression> [WHEN ...] [ELSE <expression>] END`. Output is one ordinary scalar cell, including SQL NULL; there is no separate wrapper or diagnostic text on success.

## `CAST`

SQL: `CAST(<expression> AS <type>)`. Type spellings are `INTEGER`, `FLOAT`, `TEXT`, `BOOLEAN`, `TIMESTAMP`, and `JSON`. Output is a scalar cell in the selected value family or SQL NULL. Integer-to-text output is signed decimal text. Boolean-to-text output is `true` or `false`, without fixed letter case. Timestamp-to-text output is an ISO 8601 date-time with an explicit UTC offset. Failure uses the ordinary host carrier; there is no separate conversion status field.

## `~/.cache/huggingface/hub`

Local model-cache input files, relative to the process user's home directory, are `.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/refs/main` (UTF-8 revision identifier) and `.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/<revision>/config.json`, `tokenizer.json`, and `model.safetensors`, using the published model asset formats. `HOME` selects that home directory for the process.

## `UNION`

SQL: `<query> UNION [ALL] <query>`, with optional final `ORDER BY`, `LIMIT`, and `OFFSET` clauses. Output is ordinary typed rows; column metadata takes names from the left query. Explicit aliases are preserved. Failure uses the ordinary host carrier.

## `INTERSECT`

SQL: `<query> INTERSECT [ALL] <query>`, with optional final `ORDER BY`, `LIMIT`, and `OFFSET` clauses. Output is ordinary typed rows; column metadata takes names from the left query. Explicit aliases are preserved. Failure uses the ordinary host carrier.

## `EXCEPT`

SQL: `<query> EXCEPT [ALL] <query>`, with optional final `ORDER BY`, `LIMIT`, and `OFFSET` clauses. Output is ordinary typed rows; column metadata takes names from the left query. Explicit aliases are preserved. Failure uses the ordinary host carrier.

## `UPPER`

SQL expression: `UPPER(<text>)`. The argument is a text expression.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LOWER`

SQL expression: `LOWER(<text>)`. The argument is a text expression.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `REVERSE`

SQL expression: `REVERSE(<text>)`. The argument is a text expression.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LENGTH`

SQL expression: `LENGTH(<text>)`. The argument is a text expression.

Output is an integer character-count cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `CHAR`

SQL expression: `CHAR(<code>)`. The argument is an integer Unicode code point.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `SUBSTRING`

SQL expression: `SUBSTRING(<text>, <position> [, <length>])`. The first argument is text; position and optional length are signed integers. Positive character positions are one-based.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LEFT`

SQL expression: `LEFT(<text>, <count>)`. Arguments are text and an integer count.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `RIGHT`

SQL expression: `RIGHT(<text>, <count>)`. Arguments are text and an integer count.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `REPEAT`

SQL expression: `REPEAT(<text>, <count>)`. Arguments are text and an integer count.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `CONCAT`

SQL expression: `CONCAT(<value>, <value>, ...)`. Arguments are scalar expressions in caller order.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `CONCAT_WS`

SQL expression: `CONCAT_WS(<separator>, <value>, ...)`. The separator is text; remaining arguments are scalar expressions.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `TRIM`

SQL expression: `TRIM(<text> [, <characters>])`. Arguments are text expressions; the optional second argument supplies a character set.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LTRIM`

SQL expression: `LTRIM(<text> [, <characters>])`. Arguments are text expressions; the optional second argument supplies a character set.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `RTRIM`

SQL expression: `RTRIM(<text> [, <characters>])`. Arguments are text expressions; the optional second argument supplies a character set.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `REPLACE`

SQL expression: `REPLACE(<text>, <search>, <replacement>)`. All arguments are text expressions.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `SPLIT_PART`

SQL expression: `SPLIT_PART(<text>, <delimiter>, <part>)`. Text and delimiter are text expressions; part is a one-based integer part number.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LOCATE`

SQL expression: `LOCATE(<search>, <text> [, <start>])`. Search and text are text expressions. The optional integer start is a one-based character position.

Output is an integer character position; zero is the no-match marker. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LPAD`

SQL expression: `LPAD(<text>, <length>, <padding>)`. Text and padding are text; target length is an integer character count.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `RPAD`

SQL expression: `RPAD(<text>, <length>, <padding>)`. Text and padding are text; target length is an integer character count.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `STARTS_WITH`

SQL expression: `STARTS_WITH(<text>, <prefix>)`. Both arguments are text expressions.

Output is a Boolean predicate cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `ENDS_WITH`

SQL expression: `ENDS_WITH(<text>, <suffix>)`. Both arguments are text expressions.

Output is a Boolean predicate cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `CONTAINS`

SQL expression: `CONTAINS(<text>, <search>)`. Both arguments are text expressions.

Output is a Boolean predicate cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `COALESCE`

SQL expression: `COALESCE(<value>, <value>, ...)`. Arguments are scalar expressions.

Output is an ordinary scalar cell in the result value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `GREATEST`

SQL expression: `GREATEST(<value>, <value>, ...)`. Arguments are scalar expressions.

Output is an ordinary scalar cell in the result value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LEAST`

SQL expression: `LEAST(<value>, <value>, ...)`. Arguments are scalar expressions.

Output is an ordinary scalar cell in the result value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `NULLIF`

SQL expression: `NULLIF(<left>, <right>)`. Both arguments are scalar expressions.

Output is an ordinary scalar cell in the result value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `COLLATE`

SQL expression: `COLLATE(<text>, <collation>)`. Arguments are text expressions; collation selections are `BINARY`, `NOCASE`, or `NOACCENT`.

Output is a text-valued expression for comparison. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `TYPEOF`

SQL expression: `TYPEOF(<value>)`. The argument is a scalar expression.

Output is a text type label. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. Labels are `INTEGER`, `FLOAT`, `TEXT`, `BOOLEAN`, `TIMESTAMP`, `JSON`, `VECTOR`, and `NULL`. These label spellings differ from the schema-description labels.

## `ABS`

SQL expression: `ABS(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `FLOOR`

SQL expression: `FLOOR(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `CEILING`

SQL expression: `CEILING(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `SQRT`

SQL expression: `SQRT(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LOG10`

SQL expression: `LOG10(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LOG2`

SQL expression: `LOG2(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LN`

SQL expression: `LN(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `EXP`

SQL expression: `EXP(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `SIGN`

SQL expression: `SIGN(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `SIN`

SQL expression: `SIN(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `COS`

SQL expression: `COS(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `TAN`

SQL expression: `TAN(<number>)`. The argument is numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `ROUND`

SQL expression: `ROUND(<number> [, <decimals>])`. The first argument is numeric; the optional decimal-place count is a signed integer.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `TRUNCATE`

SQL expression: `TRUNCATE(<number>, <decimals>)`. The first argument is numeric and the decimal-place count is a signed integer.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `MOD`

SQL expression: `MOD(<left>, <right>)`. Both arguments are numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `POWER`

SQL expression: `POWER(<base>, <exponent>)`. Both arguments are numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LOG`

SQL expression: `LOG(<number>) or LOG(<base>, <number>)`. Arguments are numeric.

Output is a numeric cell (Integer or Float). SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `PI`

SQL expression: `PI()`. There are no arguments.

Output is a floating-point cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `RANDOM`

SQL expression: `RANDOM()`. There are no arguments.

Output is a floating-point sample cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `CURRENT_DATE`

SQL expression: `CURRENT_DATE`. This expression takes no arguments.

Output is a Timestamp cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `CURRENT_TIME`

SQL expression: `CURRENT_TIME`. This expression takes no arguments.

Output is text in `HH:MM:SS` form, with zero-padded fields. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `CURRENT_TIMESTAMP`

SQL expression: `CURRENT_TIMESTAMP`. This expression takes no arguments.

Output is a Timestamp cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `EXTRACT`

SQL expression: `EXTRACT(<field> FROM <timestamp>)`. The field is an unquoted selector: `YEAR`, `QUARTER`, `MONTH`, `WEEK`, `DAY`, `DOW`, `ISODOW`, `DOY`, `HOUR`, `MINUTE`, `SECOND`, `MILLISECONDS`, `MICROSECONDS`, or `EPOCH`. The second argument is a timestamp expression.

Output is an integer component cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `DOW` uses Sunday=0 through Saturday=6; `ISODOW` uses Monday=1 through Sunday=7. `DOY` and `QUARTER` are one-based labels.

## `DATE_TRUNC`

SQL expression: `DATE_TRUNC(<unit>, <timestamp>)`. Unit is text: `year`, `quarter`, `month`, `week`, `day`, `hour`, `minute`, or `second`. The second argument is a timestamp expression.

Output is a Timestamp cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `TIME_TRUNC`

SQL expression: `TIME_TRUNC(<duration>, <timestamp>)`. Duration is text comprising integer counts followed by `h`, `m`, `s`, `ms`, `us`, or `ns`, optionally concatenated. The second argument is a timestamp expression.

Output is a Timestamp cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `DATE_ADD`

SQL expression: `DATE_ADD(<timestamp>, <count>, <unit>)`. The timestamp argument is timestamp text or a timestamp expression; count is an integer; unit is text `year`, `month`, `week`, `day`, `hour`, `minute`, or `second`.

Output is a Timestamp cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `DATE_SUB`

SQL expression: `DATE_SUB(<timestamp>, <count>, <unit>)`. The timestamp argument is timestamp text or a timestamp expression; count is an integer; unit is text `year`, `month`, `week`, `day`, `hour`, `minute`, or `second`.

Output is a Timestamp cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `DATEDIFF`

SQL expression: `DATEDIFF(<first date>, <second date>)`. Arguments are timestamp text or timestamp expressions.

Output is an integer day-count cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `TO_CHAR`

SQL expression: `TO_CHAR(<value>, <format>)`. Value is numeric or timestamp text/a timestamp expression; format is text.

Output is a text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. Numeric `9` placeholders after `.` select printed decimal places; `,` requests thousands grouping. Calendar format tokens are `YYYY`, `MM`, `DD`, `HH24`, `HH12`, `MI`, `SS`, `MS`, `MON`, `MONTH`, `DAY`, `DY`, and `AM`. Numeric calendar fields are zero-padded to their token widths; `MS` is three digits. Name tokens use uppercase English full or three-letter names; `AM` yields `AM` or `PM`. Other punctuation is literal.

## `JSON_ARRAY`

SQL expression: `JSON_ARRAY(<value>, ...)`. Arguments are scalar expressions.

Output is a JSON document cell carrying an array. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `JSON_OBJECT`

SQL expression: `JSON_OBJECT(<key>, <value> [, <key>, <value> ...])`. Keys are text expressions and values are scalar expressions.

Output is a JSON document cell carrying an object. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `JSON_EXTRACT`

SQL expression: `JSON_EXTRACT(<json>, <path>)`. JSON is document text or a JSON expression. A path is text using `$` for the root, `.<key>` for object members and `[<index>]` for zero-based array indices.

Output is a scalar cell or JSON text for an object or array. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `JSON_ARRAY_LENGTH`

SQL expression: `JSON_ARRAY_LENGTH(<json> [, <path>])`. JSON is document text or a JSON expression. A path is text using `$` for the root, `.<key>` for object members and `[<index>]` for zero-based array indices.

Output is an integer length cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `JSON_KEYS`

SQL expression: `JSON_KEYS(<json>)`. The argument is document text or a JSON expression.

Output is a text cell containing a JSON array of key strings. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `JSON_TYPE`

SQL expression: `JSON_TYPE(<json>, <path>)`. JSON is document text or a JSON expression. A path is text using `$` for the root, `.<key>` for object members and `[<index>]` for zero-based array indices.

Output is a text label: `object`, `array`, `string`, `number`, `boolean`, or `null`. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `JSON_VALID`

SQL expression: `JSON_VALID(<text>)`. The argument is text.

Output is an integer validity marker: `1` denotes valid JSON and `0` denotes invalid JSON. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `MD5`

SQL expression: `MD5(<text>)`. The argument is text. 

Output is a lowercase hexadecimal text digest of exactly 32 characters. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `SHA1`

SQL expression: `SHA1(<text>)`. The argument is text. 

Output is a lowercase hexadecimal text digest of exactly 40 characters. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `SHA256`

SQL expression: `SHA256(<text>)`. The argument is text. 

Output is a lowercase hexadecimal text digest of exactly 64 characters. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `SHA384`

SQL expression: `SHA384(<text>)`. The argument is text. 

Output is a lowercase hexadecimal text digest of exactly 96 characters. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `SHA512`

SQL expression: `SHA512(<text>)`. The argument is text. 

Output is a lowercase hexadecimal text digest of exactly 128 characters. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `CRC32`

SQL expression: `CRC32(<text>)`. The argument is text.

Output is an unsigned 32-bit checksum value carried in an integer cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `VEC_DISTANCE_L2`

SQL expression: `VEC_DISTANCE_L2(<left vector>, <right vector>)`. Each argument is a native vector or bracketed comma-separated numeric vector text.

Output is a floating-point distance cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `VEC_DISTANCE_COSINE`

SQL expression: `VEC_DISTANCE_COSINE(<left vector>, <right vector>)`. Each argument is a native vector or bracketed comma-separated numeric vector text.

Output is a floating-point distance cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `VEC_DISTANCE_IP`

SQL expression: `VEC_DISTANCE_IP(<left vector>, <right vector>)`. Each argument is a native vector or bracketed comma-separated numeric vector text.

Output is a floating-point distance cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `VEC_DIMS`

SQL expression: `VEC_DIMS(<vector>)`. The argument is a native vector or vector text.

Output is an integer dimension-count cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `VEC_NORM`

SQL expression: `VEC_NORM(<vector>)`. The argument is a native vector or vector text.

Output is a floating-point magnitude cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `VEC_TO_TEXT`

SQL expression: `VEC_TO_TEXT(<vector>)`. The argument is a native vector or vector text.

Output is text `[<number>, ...]` containing components in order. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `EMBED`

SQL expression: `EMBED(<value>)`. The argument is text, an integer, a floating-point value or SQL NULL. The optional `semantic` build exposes this expression.

Output is a native vector cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. Model loading failure may instead return a SQL NULL cell. The embedding has no required printed form.

## `CURRENT_TRANSACTION_ID`

SQL expression: `CURRENT_TRANSACTION_ID()`. There are no arguments.

Output is an integer transaction-identity cell or SQL NULL. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `generate_series`

SQL expression: `generate_series(<start>, <stop> [, <step>])`. The two-argument form is provided for numeric endpoints. Start and stop are integer, floating-point or timestamp expressions; step is numeric for numeric endpoints or text `<count> <unit>` for timestamp endpoints. Time units are `years`, `months`, `weeks`, `days`, `hours`, `minutes`, `seconds`, `milliseconds`, and `microseconds`, also in singular form.

Output is a relation or a scalar text cell, according to invocation context. Rejected operations use the host error carrier; error prose is free. In `FROM`, output has one column named `value` with Integer, Float or Timestamp cells, and accepts `AS <alias>(<column>)`. In a scalar projection, the output is text containing a JSON array with numeric elements or RFC3339 timestamp strings.

## `COUNT`

SQL expression: `COUNT(*) or COUNT([DISTINCT] <expression>)`.

Output is an Integer count cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. The call also accepts `OVER (<window specification>)` or `OVER <name>`.

## `SUM`

SQL expression: `SUM([DISTINCT] <expression>)`.

Output is a numeric cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. The call also accepts `OVER (<window specification>)` or `OVER <name>`. Numeric cells are Integer or Float.

## `AVG`

SQL expression: `AVG([DISTINCT] <expression>)`.

Output is a numeric cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. The call also accepts `OVER (<window specification>)` or `OVER <name>`. Aggregate mean output is Float.

## `MIN`

SQL expression: `MIN([DISTINCT] <expression>)`.

Output is a scalar cell in the selected value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. The call also accepts `OVER (<window specification>)` or `OVER <name>`.

## `MAX`

SQL expression: `MAX([DISTINCT] <expression>)`.

Output is a scalar cell in the selected value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. The call also accepts `OVER (<window specification>)` or `OVER <name>`.

## `MEDIAN`

SQL expression: `MEDIAN([DISTINCT] <expression>)`.

Output is a numeric cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `VAR_SAMP`

SQL expression: `VAR_SAMP([DISTINCT] <expression>)`.

Output is a numeric cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `VAR_POP`

SQL expression: `VAR_POP([DISTINCT] <expression>)`.

Output is a numeric cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `STDDEV_SAMP`

SQL expression: `STDDEV_SAMP([DISTINCT] <expression>)`.

Output is a numeric cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `STDDEV_POP`

SQL expression: `STDDEV_POP([DISTINCT] <expression>)`.

Output is a numeric cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `FIRST`

SQL expression: `FIRST([DISTINCT] <expression>)`.

Output is a scalar cell in the selected value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `LAST`

SQL expression: `LAST([DISTINCT] <expression>)`.

Output is a scalar cell in the selected value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `STRING_AGG`

SQL expression: `STRING_AGG([DISTINCT] <expression>, <separator> [ORDER BY <expressions>])`.

Output is a Text cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `ARRAY_AGG`

SQL expression: `ARRAY_AGG([DISTINCT] <expression> [ORDER BY <expressions>])`.

Output is a Text cell containing a JSON array. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. Array elements retain their JSON types.

## `GROUPING`

SQL expression: `GROUPING(<expression>)`.

Output is an Integer marker, `1` for an omitted grouping dimension and `0` for a participating dimension. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free.

## `ROW_NUMBER`

SQL expression: `ROW_NUMBER() OVER (<window specification>)`. The window specification is SQL window syntax.

Output is an Integer cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted.

## `RANK`

SQL expression: `RANK() OVER (<window specification>)`. The window specification is SQL window syntax.

Output is an Integer cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted.

## `DENSE_RANK`

SQL expression: `DENSE_RANK() OVER (<window specification>)`. The window specification is SQL window syntax.

Output is an Integer cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted.

## `PERCENT_RANK`

SQL expression: `PERCENT_RANK() OVER (<window specification>)`. The window specification is SQL window syntax.

Output is a Float cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted.

## `CUME_DIST`

SQL expression: `CUME_DIST() OVER (<window specification>)`. The window specification is SQL window syntax.

Output is a Float cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted.

## `NTILE`

SQL expression: `NTILE(<buckets>) OVER (<window specification>)`. The window specification is SQL window syntax.

Output is an Integer cell. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted. Buckets is a positive integer.

## `LEAD`

SQL expression: `LEAD(<expression> [, <offset> [, <replacement>]]) OVER (<window specification>)`. The window specification is SQL window syntax.

Output is a cell of the input expression value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted. Offset is an integer.

## `LAG`

SQL expression: `LAG(<expression> [, <offset> [, <replacement>]]) OVER (<window specification>)`. The window specification is SQL window syntax.

Output is a cell of the input expression value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted. Offset is an integer.

## `FIRST_VALUE`

SQL expression: `FIRST_VALUE(<expression>) OVER (<window specification>)`. The window specification is SQL window syntax.

Output is a cell of the input expression value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted.

## `LAST_VALUE`

SQL expression: `LAST_VALUE(<expression>) OVER (<window specification>)`. The window specification is SQL window syntax.

Output is a cell of the input expression value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted.

## `NTH_VALUE`

SQL expression: `NTH_VALUE(<expression>, <ordinal>) OVER (<window specification>)`. The window specification is SQL window syntax.

Output is a cell of the input expression value family. SQL NULL uses the ordinary missing-value cell. Rejected operations use the host error carrier; error prose is free. `OVER <name>` is also accepted. Ordinal is a one-based positive integer.

## `velnora_open`

```c
int32_t velnora_open(const char* dsn, VelnoraDB** out_db);
```

The input is a NUL-terminated database location string; named memory locations use `memory://<name>`. On success, `out_db` receives a handle and the return is `VELNORA_OK`; failure returns `VELNORA_ERROR`.

## `velnora_rows_column_double`

```c
double velnora_rows_column_double(const VelnoraRows* rows, int32_t index);
```

Returns the floating-point value of the current row at a zero-based column position. Type and nullness are available through their separate accessors.

## `velnora_rows_column_bool`

```c
int32_t velnora_rows_column_bool(const VelnoraRows* rows, int32_t index);
```

Returns the Boolean value of the current row at a zero-based column position: `0` for false and `1` for true. Type and nullness are available through their separate accessors.

## `VELNORA_TYPE_FLOAT`

C macro: `#define VELNORA_TYPE_FLOAT 2` in `velnora.h`. This value denotes a floating-point cell.

## `VELNORA_TYPE_BOOLEAN`

C macro: `#define VELNORA_TYPE_BOOLEAN 4` in `velnora.h`. This value denotes a Boolean cell.
