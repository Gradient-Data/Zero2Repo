# Interface Contract

The Python package is importable as `velnora`. The executable is `velnora`; commands run from the caller’s working directory. `velnora.cli.main()` is also a process entry point. Command results use stdout and diagnostics use stderr, except the client-error status line described below.

The process exit status is `0` for a completed command, `1` for a client failure or an incomplete dry run, and `2` for argument conversion failure. A client failure writes `VelnoraClientError: <message>` to stdout. Argument conversion failure writes a diagnostic to stderr.

The import root contains `velnora/__init__.py`. The package attribute `velnora.__file__` identifies that package file.

## `velnora.task`

Import the decorator with `from velnora import task`. Declaration forms are `@task`, `@task()`, and `task(**options)(function)`. The wrapped function may be synchronous or asynchronous. Declaration keywords include `name: str`, `namespace: str`, `version: str`, `hash_includes: list`, `nout: int`, `config_args: list[str]`, `cache: bool`, `cache_scope: str`, `mode: str`, `priority: int`, and `tags: list[tuple[str, object]]`. Declaration failures are raised as `TypeError` or `ValueError`. An asynchronous reuse-policy refusal can also raise `KeyError`; a refusal of an adjusted task policy can raise `SchedulerError`.

The returned task exposes `name: str`, `namespace: str`, `fullname: str` (the qualified task name), `version: str | None`, and `func`, the authored Python callable. Qualified task selectors use `<namespace>.<name>`; unqualified selectors use `<name>`. Calling it with `(*args, **kwargs)` returns a deferred expression. Argument-binding failures raise `TypeError`, either on call or on execution.

The task attribute `hash: str` is its opaque task identifier, corresponding to the task's `value_hash` in history records.

Task methods are `options(**task_options_update)`, `export_options(**task_options_update)`, `update_context(context: dict)` or `update_context(**kwargs)`, and `partial(*args, **kwargs)`. Their returned task-like values remain callable; repeated partial binding and repeated context updates use the same method forms.

For `options` and exported options, the execution option names are `executor`, `mode`, `priority`, `cache`, `cache_scope`, `check_valid`, `prov`, `tags`, and `limits`. `executor` is a configured executor name; `mode` spells local execution selections as `thread` and `process`. `cache` and `prov` are booleans; `priority` is numeric; `tags` is a sequence of key/value pairs. `limits` is a list of resource names or a mapping from names to requested integer amounts.

`cache_scope` uses `BACKEND` for repository reuse, `CSE` for execution reuse, and `NONE` for disabled task-call reuse. `check_valid` uses `full` and `shallow` for the two validity-checking selections. `config_args` contains authored argument names; `hash_includes` contains authored dependency values.

The module `velnora.task` exposes the decorator `wraps_task`.

## `velnora.expression.Expression`

Deferred results support indexing with an integer or slice, attribute access, `+`, `-`, `*`, `/`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `&`, and `|`. Binary operators accept a deferred value on either side. They return deferred expressions. Operation failures surface as the underlying Python exception, including `ZeroDivisionError`, `TypeError`, `IndexError`, and `AttributeError`.

The arithmetic and comparison call forms also accept Python's `operator.add`, `operator.sub`, `operator.mul`, `operator.truediv`, `operator.eq`, `operator.ne`, `operator.lt`, `operator.le`, `operator.gt`, and `operator.ge`.

Iteration and unpacking expose deferred output expressions. Unsupported truth testing or iteration raises `TypeError`.

Inside an asynchronous task, `await expression` returns the concrete value and propagates an authored exception with its original `args`.

## `velnora.Scheduler`

Import with `from velnora import Scheduler`. Construction is `Scheduler()` or `Scheduler(config=Config(...))`; a configuration can also be passed positionally. `load()` opens the configured repository. `run(expression, cache=..., context=..., tags=...)` accepts Python values or deferred expressions and returns the resolved Python value. An unhandled authored exception is raised with its original class and `args`.

`config` accepts a `velnora.config.Config` object. `run` accepts `cache: bool`, `context: dict`, and `tags`, a sequence of key/value pairs. Configuration/execution failures are raised to the caller: `SchedulerError` identifies scheduler configuration or executor selection failure, `ValueError` identifies a rejected local mode, and `KeyError` identifies missing executor configuration. `load()` can raise `VelnoraVersionError` for incompatible repository data.

The public `backend` member supports `record_value(value) -> str`, returning an opaque saved-value identifier, and `get_value(value_hash) -> (value, present)`, where `present` is a boolean. Unavailable data is represented by `(None, False)`. Saving failure due to a value-size refusal raises `VelnoraDatabaseError`.

An asynchronous task rejected for its selected executor raises `SchedulerError`.

Remote script failures raise `ScriptError`. Execution-service failures raise an exception; its class and message wording are not fixed. Failed work is identified by the recorded `Job` task identifier and status, with diagnostic detail available through the job log.

## `velnora.namespace.namespace`

`from velnora.namespace import namespace`; `namespace(value)` accepts a namespace string or `None`. A workflow module can declare the string attribute `velnora_namespace`.

## `velnora.namespace.get_current_namespace`

`from velnora.namespace import get_current_namespace`; `get_current_namespace()` returns the current namespace as a string or `None`.

## `velnora.get_context`

`from velnora.context import get_context`; `get_context(var_path: str, default=...)` returns a deferred context lookup value. The path uses dot-separated mapping keys. It can be used as an authored task parameter’s default expression. The resolved value is a Python value; absence is represented by `None`.

## `velnora.scheduler.JobInfo`

`from velnora.scheduler import JobInfo`; authors place `JobInfo()` in a task parameter’s default. The value supplied to task code exposes `execution_id: str`, `job_id: str`, and `options: dict`, holding the execution identifier, job identifier, and effective options.

## `velnora.config.Config`

`from velnora.config import Config`; construction accepts no arguments or a mapping of section names to option mappings. `read_path(filename: str)` reads an INI file. The resulting object is accepted by `Scheduler(config=...)`.

## `velnora.value.get_type_registry`

`from velnora.value import get_type_registry`; `get_type_registry()` returns the value registry. Its methods are `get_type_name(raw_type: type) -> str`, `serialize(value) -> bytes`, `deserialize(type_name: str, data: bytes) -> object`, `get_hash(value) -> str`, and `is_valid(value) -> bool`. Type names and serialized bytes are exchanged through these methods; equivalence identifiers are opaque strings. Serialization failures include `TypeError` and `InvalidValueError`.

For Python `str` values, the registry type name is `builtins.str`.

For Python `int` values, the registry type name is `builtins.int`.

## `velnora.value.Value`

`from velnora.value import Value`; author subclasses declare `type_name: str`. Extension methods are `get_hash(self, data=None) -> str`, `serialize(self) -> bytes`, `@classmethod deserialize(cls, raw_type: type, data: bytes) -> object`, and `is_valid(self) -> bool`. The returned object is the represented Python value.

Additional extension methods are `@classmethod parse_arg(cls, raw_type: type, arg: str) -> object`, `preprocess(self, preprocess_args: dict) -> object`, and `postprocess(self, postprocess_args: dict) -> object`. The transformation dictionaries carry invocation context; a converter may raise `ValueError`.

## `velnora.value.ProxyValue`

`from velnora.value import ProxyValue`; an author subclass supplies `type`, the represented Python class, and `type_name: str`. Instance methods access the represented object through `self.instance`. It supports the `get_hash`, `serialize`, and classmethod `deserialize` extension signatures of `Value`.

## `velnora.value.InvalidValueError`

`from velnora.value import InvalidValueError`; this exception class identifies unsupported workflow values.

## `velnora.scheduler.SchedulerError`

`from velnora.scheduler import SchedulerError`; this exception class identifies scheduler configuration or execution-selection failures.

## `velnora.backends.db.VelnoraDatabaseError`

`from velnora.backends.db import VelnoraDatabaseError`; this exception class identifies repository value-saving failures.

## `velnora.backends.db.VelnoraVersionError`

`from velnora.backends.db import VelnoraVersionError`; this exception class identifies incompatible repository schema data.

## `velnora.file.File`

Import `File` from `velnora.file` or `velnora`. `File(path: str)` accepts a local path or storage URL and exposes `path: str`. File locations use local paths, `s3://<bucket>/<key>`, `gs://<bucket>/<key>`, `http://<host>/<path>`, and `https://<host>/<path>`.

`read(mode=..., encoding=...) -> str | bytes` and `write(data: str | bytes, mode=..., encoding=...)` expose text and binary I/O. `read()` and `read(encoding=...)` return `str`; `read("rb")` returns `bytes`. `write(text, encoding=...)` accepts `str`, and `write(data, mode="wb")` accepts `bytes`. Mode spellings used for binary I/O are `rb` and `wb`; `encoding` is a text encoding name. `exists() -> bool`, `size() -> int` (byte count), and `remove()` expose file state. Missing-data reads raise `FileNotFoundError`.

`copy_to(dest_file: File, skip_if_exists=...) -> File` returns a file whose `path` is the destination. `skip_if_exists` is a boolean. Copy failures for unavailable source data raise `FileNotFoundError`.

`get_hash() -> str` returns an opaque version identifier; `is_valid() -> bool` exposes validity. A file is a workflow value and can be passed through value serialization and restoration.

`stage(local: str)` returns a staging object with `stage() -> File` and `unstage() -> File`. The former result exposes the working `path`; the latter exposes the storage `path`.

For HTTPS access, the environment variable `SSL_CERT_FILE` names a certificate file used for TLS trust.

S3 locations are reached through the AWS SDK's standard configuration: `AWS_ENDPOINT_URL_S3` names the S3 service endpoint (path-style requests), with credentials from `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` and region `AWS_DEFAULT_REGION`. GCS locations are reached through the Google Cloud Storage JSON API at the endpoint named by `STORAGE_EMULATOR_HOST`, with application-default credentials from the service-account file named by `GOOGLE_APPLICATION_CREDENTIALS`. Objects written through these entries are ordinary objects of that service, visible to any client of it.

## `velnora.file.Dir`

Import `Dir` from `velnora.file` or `velnora`. `Dir(path: str)` exposes `path: str`; `exists() -> bool`, `mkdir()`, and `rmdir(recursive=...)` provide directory operations. `recursive` is a boolean; directory-removal failure is an `OSError`. Iteration yields `File` values. `copy_to(dest_dir: Dir) -> Dir` returns the destination directory with its `path` and transferred file tree.

`is_valid() -> bool` exposes collection validity. `stage(local: str)` returns an object with `stage() -> Dir` and `unstage() -> Dir`; each result exposes its destination `path`.

## `velnora.file.FileSet`

`from velnora.file import FileSet`; `FileSet(pattern: str)` accepts a wildcard path pattern. Iteration yields `File` values with a string `path`. `is_valid() -> bool` exposes collection validity. The collection can be serialized and restored through the value registry.

## `velnora.file.ContentFile`

`from velnora.file import ContentFile`; `ContentFile(path: str)` is the corresponding `File` workflow value variant. It supports value-registry serialization and restoration, `is_valid() -> bool`, `get_hash() -> str`, and `read() -> str`.

## `velnora.file.IFile`

`from velnora.file import IFile`; `IFile(path: str)` is the corresponding `File` workflow value variant. It supports value-registry serialization and restoration, `is_valid() -> bool`, `get_hash() -> str`, and `read() -> str`.

## `velnora.file.ContentFileSet`

`from velnora.file import ContentFileSet`; `ContentFileSet(pattern: str)` is the corresponding `FileSet` workflow value variant. It supports value-registry serialization and restoration, `is_valid() -> bool`, and iteration yielding file values with `read() -> str`.

## `velnora.file.ContentDir`

`from velnora.file import ContentDir`; `ContentDir(path: str)` is the corresponding `Dir` workflow value variant. It supports value-registry serialization and restoration, `is_valid() -> bool`, and iteration yielding file values with `read() -> str`.

## `velnora.file.IFileSet`

`from velnora.file import IFileSet`; `IFileSet(pattern: str)` is the corresponding `FileSet` workflow value variant. It supports value-registry serialization and restoration, `is_valid() -> bool`, and iteration yielding file values with `read() -> str`.

## `velnora.file.IDir`

`from velnora.file import IDir`; `IDir(path: str)` is the corresponding `Dir` workflow value variant. It supports value-registry serialization and restoration, `is_valid() -> bool`, and iteration yielding file values with `read() -> str`.

## `velnora.file.glob_file`

`from velnora.file import glob_file`; `glob_file(pattern: str)` returns an iterable of matching path strings.

## `velnora.Handle`

`from velnora import Handle`; authors subclass `Handle`, declare `type_name: str`, and construct their subclass as `Subclass(name: str, *args, **kwargs)`. The authored constructor receives the construction arguments and restored instances expose their authored methods. `fork(key: str)` returns a handle branch usable in task arguments.

## `velnora.merge_handles`

`from velnora import merge_handles`; `merge_handles(handles_expr)` accepts a list of handle values or expressions and returns a deferred merged handle value.

## `velnora.apply_tags`

`from velnora import apply_tags`; `apply_tags(value, tags=..., job_tags=..., execution_tags=...)` returns a deferred value. Each tag argument is a sequence of `(key: str, value: object)` pairs. The resolved result has the supplied value’s Python shape.

## `velnora.scheduler.cond`

`from velnora import cond`; `cond(cond_expr, then_expr, *rest)` accepts alternating predicate and branch expressions, followed by a final alternative. It returns a deferred result with the selected branch’s Python shape, or raises the propagated exception.

## `velnora.scheduler.catch`

Import `catch` from `velnora.scheduler` or `velnora`. `catch(expr, *catch_args)` accepts alternating exception-type selectors and recovery tasks. A selector is an exception class or tuple of exception classes. The deferred result has the resolved original or recovery value’s shape. Unmatched failures and recovery failures are raised with their original types. A recovery task receives the exception object.

## `velnora.scheduler.catch_all`

`from velnora.scheduler import catch_all`; `catch_all(exprs, error_class=..., recover=...)` accepts a nested Python collection and optional exception selector and recovery task. It returns a deferred collection or recovery result. A recovery task receives the original collection shape with each leaf represented by its value or exception object. The outward failure is a raised unmatched or recovery exception.

## `velnora.scheduler.fork_thread`

`from velnora.scheduler import fork_thread`; `fork_thread(expr)` returns a deferred reference value for use by other task calls.

## `velnora.scheduler.join_thread`

`from velnora.scheduler import join_thread`; `join_thread(thread)` accepts that reference and returns a deferred result with the referenced computation’s resolved Python shape, or raises its exception.

## `velnora.functools.seq`

`from velnora.functools import seq`; `seq(exprs)` accepts a sequence of expressions and returns a deferred list of resolved results.

## `velnora.functools.map_`

`from velnora.functools import map_`; `map_(a_task, values)` accepts a task and a list or list expression and returns a deferred list of mapped results.

## `velnora.functools.starmap`

`from velnora.functools import starmap`; `starmap(a_task, kwargs)` accepts a task and a list or list expression of keyword-argument dictionaries and returns a deferred list of mapped results.

## `velnora.functools.flatten`

`from velnora.functools import flatten`; `flatten(list_of_lists)` accepts nested lists or an expression yielding them and returns a deferred flat list.

## `velnora.functools.flat_map`

`from velnora.functools import flat_map`; `flat_map(a_task, values)` accepts a task and a list or list expression and returns a deferred flat list.

## `velnora.functools.compose`

`from velnora.functools import compose`; `compose(*tasks)` accepts task callables and returns a callable task whose calls return deferred results.

## `velnora.functools.delay`

`from velnora.functools import delay`; `delay(x)` accepts an expression and returns a deferred value that can be supplied as a task argument.

## `velnora.functools.force`

`from velnora.functools import force`; `force(x)` accepts the value returned by delay and returns a deferred result with the original computation’s Python shape.

## `velnora.functools.const`

`from velnora.functools import const`; `const(x, _)` accepts a chosen result and prerequisite expression and returns a deferred result with the chosen result’s Python shape.

## `velnora.functools.zip_`

`from velnora.functools import zip_`; `zip_(*lists)` accepts lists or list expressions and returns a deferred list of tuples.

## `velnora.functools.apply_func`

`from velnora.functools import apply_func`; `apply_func(func, *args, **kwargs)` accepts a Python function and positional and keyword input values or expressions and returns a deferred function result; authored exceptions are raised.

## `velnora.functools.eval_`

`from velnora.functools import eval_`; `eval_(code: str, *args, **kwargs)` accepts Python expression text, positional values, the keyword pos_args containing their names, and named input values and returns a deferred expression result; binding failure raises TypeError.

## `velnora.functools.no_prov`

`from velnora.functools import no_prov`; `no_prov(expr)` returns a deferred value with the enclosed expression’s resolved Python result shape.

## `velnora.task.wraps_task`

`from velnora.task import wraps_task`; `wraps_task(wrapper_hash_includes=..., use_wrapper_signature=...)` is a decorator for an authored function taking a task and returning a Python callable. `wrapper_hash_includes` is a list of dependency values; `use_wrapper_signature` is a boolean. The resulting wrapper accepts a task and returns a callable task. Its `func` member exposes the wrapped Python callable. Binding failures raise `TypeError`.

## `velnora.scripting.script`

`from velnora import script`; `script(command, inputs=..., outputs=..., tempdir=..., **task_options)` accepts script text or a list of command-argument strings. `inputs` and `outputs` accept nested Python structures containing file, directory, or staging values; `tempdir` is a boolean; `task_options` accepts the execution selector `executor` naming a configured executor. The call returns a deferred result: bytes for captured standard output, or the declared output structure containing `File` and `Dir` results. `File("-")` in an output structure denotes captured standard-output bytes. Output artifacts are available at the returned values’ `path` locations.

An explicit interpreter is supplied by a leading `#!<interpreter command>` line in the script text.

## `velnora.scripting.ScriptError`

`from velnora.scripting import ScriptError`; a failed script raises this exception. Its `message: str` exposes the failed script’s diagnostic output.

## `velnora.file.ShardedS3Dataset`

`from velnora import ShardedS3Dataset`; `ShardedS3Dataset(path: str, format=..., recurse=...)` exposes `path: str`, `format: str`, `recurse: bool`, and `filenames: list[str]`. `format` names the shard format and `recurse` selects recursive membership. Format names at this entry are spelled `avro`, `csv`, `ion`, `grokLog`, `json`, `orc`, `parquet`, and `xml`. `is_valid() -> bool` exposes validity; the dataset supports value-registry serialization and restoration. Constructor failure forms are `ValueError` and `AssertionError`.

`ShardedS3Dataset.from_files(files: list[File], allow_additional_files=...) -> ShardedS3Dataset` accepts an explicit file collection and a boolean inclusion option. The returned dataset exposes the same fields. Inference refusal raises `ValueError` and missing input raises `FileNotFoundError`. A location-consistency refusal raises an exception whose class is not fixed.

`load_pandas_shards(max_shards=...) -> list[pandas.DataFrame]` returns local tables; `load_pandas(max_shards=...) -> pandas.DataFrame` returns a combined table. The optional `max_shards` argument is an integer shard-selection limit. Table columns and row values are accessible through `itertuples(index=False, name=None)`. Local-load refusal raises `ValueError`.

`load_spark() -> pyspark.sql.DataFrame` and `save_spark(dataset: pyspark.sql.DataFrame)` expose distributed dataset access. A returned table exposes `selectExpr(*expressions: str) -> pyspark.sql.DataFrame` for SQL projections and `collect() -> list[pyspark.sql.Row]`; rows are indexed by column name. Missing Spark/Glue prerequisites raise `ValueError`.

## `velnora.glue.udf`

`from velnora.glue import udf`; `udf(function)` and `udf(return_type=...)(function)` return callable transformations. `return_type` accepts a Spark data type. Calls accept ordinary Python arguments or distributed columns; they expose an ordinary result or a Spark column. A column supports `alias(name)` and can be supplied to a table's `select`. The resulting table exposes `schema[<column_name>].dataType` and `collect()`, a list of rows accessible by authored column names.

## `velnora.glue.sql_query`

`from velnora.glue import sql_query`; `sql_query(dataset, query: str, dataset_alias=...) -> pyspark.sql.DataFrame` accepts a distributed table, query text, and a table-alias string. `collect()` returns a list of rows accessible by the query's column names.

## `velnora.scheduler.subrun`

`from velnora.scheduler import subrun`; `subrun(expr, executor: str, config=..., config_dir=..., new_execution=..., load_modules=..., **task_options)` returns a deferred subworkflow result. `config` is a section mapping; `config_dir` is a directory containing `velnora.ini`; `new_execution` is a boolean; `load_modules` is a list of module names. The additional task options accept `cache_scope`. The result has the authored subworkflow’s resolved Python shape or raises its exception. Conflicting configuration is represented by `AssertionError`.

## `velnora.federated_tasks.federated_task`

`from velnora.federated_tasks import federated_task`; `federated_task(entrypoint: str, *task_args, **task_kwargs)` returns a deferred published-task result with the authored Python shape. Invalid publication configuration is represented by `AssertionError`; an invalid executor selection is represented by `SchedulerError`. Positional and named arguments are the published task’s arguments.

## `velnora.federated_tasks.rest_federated_task`

`from velnora.federated_tasks import rest_federated_task`; `rest_federated_task(config_name: str, entrypoint: str, url: str, scratch_prefix: str, dryrun: bool, *task_args, cache=..., **task_kwargs)` returns a deferred pair `(execution_id: str, description: dict)`. The description fields are `config_name: str`, `entrypoint: str`, `input_path: str`, `execution_id: str`, and `cache: bool`. They identify the configuration, publication, saved argument path, requested execution, and reuse selection. `input_path` lies beneath the supplied `scratch_prefix`.

HTTP submission sends a `POST` request to `url` with form fields `config_name`, `entrypoint`, `input_path`, `execution_id`, and `cache`. Each field is the string representation of the corresponding description value. An HTTP rejection raises `requests.HTTPError`; `response.status_code` carries the endpoint’s integer status.

## `velnora.federated_tasks.lambda_federated_task`

`from velnora.federated_tasks import lambda_federated_task`; `lambda_federated_task(config_name: str, entrypoint: str, lambda_function_name: str, scratch_prefix: str, dryrun: bool, *task_args, cache=..., **task_kwargs)` returns a deferred pair `(execution_id: str, description: dict)`. The description fields are `config_name: str`, `entrypoint: str`, `input_path: str`, `execution_id: str`, and `cache: bool`. They identify the configuration, publication, saved argument path, requested execution, and reuse selection. `input_path` lies beneath the supplied `scratch_prefix`. When `dryrun` is false, the named function is invoked through the AWS SDK Lambda `Invoke` operation (the standard endpoint setting `AWS_ENDPOINT_URL_LAMBDA` and region `AWS_REGION` apply) with the description, as a JSON object, as the request payload.

## `velnora.federated_tasks.launch_federated_task`

`from velnora.federated_tasks import launch_federated_task`; the named-argument call form is `launch_federated_task(federated_config_path=..., entrypoint=..., input_path=..., execution_id=..., cache=...)`. The first four values are strings naming the publication configuration directory, entrypoint, saved argument path, and execution identifier; `cache` is a boolean reuse selection. The saved arguments use the delegated argument-file format.

## `velnora.ini`

Repository configuration is `<config_dir>/velnora.ini` in INI format. The implicit configuration location is `.velnora/velnora.ini` relative to the working directory. The `[backend]` section contains `db_uri`, a repository URI; SQLite URIs use `sqlite:///<path>`. PostgreSQL URIs use `postgresql://<user>@/<database>?host=<socket_directory>` for a Unix socket connection. Backend options include `value_store_path`, a directory for saved-value files, `value_store_min_size`, an external-placement option, `max_value_size`, a serialized-value size limit, and `automigrate`, a boolean string. Saved-value files are located beneath `value_store_path` and hold serialized value bytes.

`automigrate` is specified as `True` or `False` text in `[backend]`.

The `[scheduler]` section accepts `context`, inline JSON object text, or `context_file`, the path of a JSON object document. A configuration conflict is represented by `SchedulerError`.

Executor sections are named `executors.<name>`. A local executor uses `type = local` with `mode`, `max_workers`, and `start_method` options for state-isolation selection, worker capacity, and Python worker-start selection. Mode spellings are `thread` and `process`; `start_method` accepts `spawn`. An alias uses `type = alias` and `target`, the target executor’s name. Resource capacities are integer values in `[limits]` keyed by resource name.

Remote executor configuration uses `type = docker`, `type = aws_batch`, or `type = aws_glue`. The exchanged setting names are `image` (container image), `scratch` (working storage path), `queue` (submission queue), `s3_scratch` (S3 working storage), `aws_region` (service region), and `role` (role name; for `aws_batch`, `none` omits a job role). Missing executor configuration is represented by `KeyError`.

Further remote executor options: `vcpus` and `memory` (CPU count and memory in GB; also accepted as per-call task options alongside `image`), `job_monitor_interval` (seconds between status polls), and `code_package` (boolean string selecting remote code delivery), `code_includes` and `code_excludes` (shell-tokenized lists of relative wildcard file patterns). Docker accepts `include_aws_env` (boolean string). The forwarded environment names are `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, and `AWS_DEFAULT_REGION`; Docker environment arguments use `-e <name>`. AWS Batch accepts `num_nodes` (integer node count for multi-node work), `min_array_size` (integer array-grouping minimum) and `job_stale_time` (seconds a pending job waits for grouping).

The AWS Batch, STS, and CloudWatch Logs service endpoints are named by `AWS_ENDPOINT_URL_BATCH`, `AWS_ENDPOINT_URL_STS`, and `AWS_ENDPOINT_URL_CLOUDWATCH_LOGS` respectively. The task's working storage location is `s3_scratch`.

Publication sections are named `federated_tasks.<entrypoint>` and expose `namespace`, `task_name`, `load_module`, `executor`, and `config_dir` string options. `new_execution` is a boolean string. These fields name the published task, its module, its executor, its configuration directory, and its execution selection.

The built-in local executor configuration section is `executors.default`; its executor selector name is `default`.

## `velnora.cli.VelnoraClient`

`from velnora.cli import VelnoraClient`; construction accepts no arguments or `stdout=<text stream>`. `execute(argv: list[str])` accepts complete command arguments including initial `velnora`. A successful `run` returns the resolved Python task result directly. Failures are raised to the caller. Command display output is written to the supplied stdout stream.

## `velnora.cli.VelnoraClientError`

`from velnora.cli import VelnoraClientError`; this exception class identifies client invocation, selection, repository, or migration failures.

## `velnora.cli.main`

`from velnora.cli import main`; `main()` runs the command-line client using the process arguments. It is callable in a fresh Python interpreter and exposes process standard input, standard output, standard error, and exit status.

## `velnora`

Command prefix: `velnora [-c <config_dir> | --config <config_dir>] [--repo <name>] <command>`. The configuration argument names a directory; the repository argument names a registered repository.

`from velnora import task, Scheduler, File, Dir, Handle, apply_tags, catch, cond, script, ShardedS3Dataset, merge_handles` exposes the named Python entries; `from velnora.context import get_context` exposes the context lookup. `from velnora.glue import udf, sql_query` exposes the Spark integration callables.

## `velnora init`

`velnora [-c <config_dir>] init` or `velnora [--config <config_dir>] init` exposes configuration initialization. Its observable output is the repository configuration file described under `velnora.ini`.

## `velnora run`

`velnora [-c <config_dir> | --config <config_dir>] run <script> <task> [--<argument> <value> ...]` invokes a task from a Python source path. Task arguments also accept `--<argument>=<value>` syntax. Their option names are formed from the authored parameter names, with underscores replaced by hyphens. A list parameter accepts multiple following argument tokens. Successful command output on stdout is the Python representation of the resolved result. In-process client execution returns that Python result.

Context options are `--context-file <path>` and repeatable `--context <key>=<value>` entries. A context file is a JSON object document. Entry keys use dot-separated context paths.

`--input <path>` names a binary saved-argument file. `--rerun <script> <identifier>` exchanges a recorded job or execution identifier. Client selection failures raise `VelnoraClientError`; missing argument bindings raise `TypeError`; argument conversion failures raise `SystemExit` with code `2` and diagnostics on stderr.

`--dryrun` exposes diagnostics on stderr. An action line begins with `[velnora] <action><whitespace>Job <identifier>:<whitespace><qualified_task>(`, with action marker `Cached` or `Dryrun`. The task name identifies the work; the identifier is opaque.

An importable-function argument is expressed as `<module>.<function>`. File and directory arguments are path strings.

## `velnora launch`

`velnora -c <config_dir> launch --executor <name> --wait <command argv...>` accepts a command argument vector. Waited standard output is displayed on client stdout as a Python bytes literal. Failed command execution raises `ScriptError`; launch configuration failure raises `VelnoraClientError`.

Without `--wait`, `velnora -c <config_dir> launch --executor <name> <command argv...>` exposes a submission result. The diagnostic stream (stderr) names the identifier of the submitted Docker container or AWS Batch job, as reported by that service.

## `velnora log`

`velnora [--config <config_dir>] log [<selector>] [options]` accepts a record identifier, identifier prefix, or file path as selector. Options are `--all`, `--exec`, `--job`, `--task`, `--value`, `--file-path <path>`, `--format json`, and `--no-pager`. JSON results are JSON Lines on client stdout: one record object per line; a selection without records has zero record lines.

Filtering options are `--job-status <statuses>`, `--exec-status <statuses>`, repeatable `--task-name <name>`, repeatable `--task-hash <identifier>`, and repeatable `--tag <key>` or `--tag <key>=<value>`. Status alternatives are comma-separated tokens. Job status tokens are `RUNNING`, `FAILED`, `DONE`, and `CACHED`; execution status selectors use `RUNNING`, `FAILED`, and `DONE`.

Text value detail includes the section label `Upstream dataflow:` and a dataflow line of the form `<variable> <-- <<call_identifier_prefix>> <task_name>(<argument_names>)`. File detail carries `Produced by Job <job_identifier_prefix>` or `Consumed by Job <job_identifier_prefix>`. Displayed identifier prefixes in these forms are nonempty unambiguous prefixes of their identifiers. A displayed task name is its authored short name or its qualified name.

The JSON Lines records on log stdout use the `Execution`, `Job`, and `Value` record forms exposed by `export`.

Text job detail writes `Raised: <exception_class_name>(<repr_arguments>)` to client stdout, where the argument list uses Python literal representations for literal-valued exception arguments. Its detailed trace is introduced by a line labelled `Traceback:`. Trace frame lines have the form `File "<source_path>", line <line_number>, in <function_name>` or `Job <job_identifier_prefix>: File "<source_path>", line <line_number>, in <task_function_name>`; surrounding indentation is presentation whitespace. The detailed trace carries the recorded failure location.

## `velnora tag`

`velnora --config <config_dir> tag add <entity_id> <key>=<value> ...`, `tag update <entity_id> <key>=<value> ...`, and `tag rm <entity_id> [--] <key_or_association> ...` expose tag edits. Keys are strings; values use JSON syntax, with an unquoted text token also accepted as a string. A bare key names a key-presence or whole-key selection. `--` terminates option parsing.

## `velnora export`

`velnora --config <config_dir> export --file <path>` writes history records to the requested file as UTF-8 JSON Lines. Each line is a record object.

History JSON Lines use `_type` to identify record kinds. All identifiers are opaque strings. An `Execution` record exposes `id: str` (execution identifier) and `job_id: str | null` (root job). A `Job` record exposes `id: str`, `task_hash: str`, `call_hash: str | null`, `parent_id: str | null`, `execution_id: str`, and `children: list[str]`; these identify the job, task, call, parent, execution, and child jobs.

A `Job` record also exposes `status: str` and `cached: bool`, identifying its completion state and prior-result use. The status markers are `RUNNING`, `FAILED`, `DONE`, and `CACHED`.

A `CallNode` record exposes `call_hash: str` (call identifier), `task_name: str` (qualified task name), `task_hash: str` (task identifier), `value_hash: str` (result value identifier), `children: list[str]` (child call identifiers), and `args: dict`. Each `args` key is a decimal positional index string or authored argument name; its value exposes `value_hash: str` for the argument value and `upstream: list[str]` for its originating calls.

A `Value` record exposes `value_hash: str` (value identifier), `type: str` (registry type name), `data: str` (base64 serialized bytes), `subvalues: list[str]` (contained-value identifiers), and `subtype: object | null`. Serialized bytes are accepted by the public value registry with the record’s `type`. The external-placement carrier is empty decoded `data`; external value retrieval uses the repository’s value API.

A non-null `subtype` exposes `_type`. A `Task` subtype exposes `name: str`, `namespace: str`, and `source: str` (Python task source). A `File` subtype exposes `path: str`, its storage location. Restored task values expose their `version` and restored file values expose their `path`.

A `Tag` record exposes `tag_hash: str` (tag identifier), `entity_type: str` (entity-kind marker), `entity_id: str` (tagged entity identifier), `key: str`, and `value`, a JSON value. Entity-kind spellings are `Execution`, `Job`, `Task`, and `Value`.

## `velnora import`

`velnora --config <config_dir> import --file <path>` reads a history export file as JSON Lines. Completion is exposed by normal return from the command client.

## `velnora repo`

`velnora --config <config_dir> repo add <name> <config_dir>` and `repo list` expose repository registration and listing. Each displayed repository row is `  <name>: <config_dir>` on client stdout, with two leading spaces and colon-space as separator. Registration or selection refusal raises `VelnoraClientError`; a registration location lacking configuration raises `FileNotFoundError`.

The repository selector name `default` identifies the default repository.

## `velnora push`

`velnora --config <config_dir> push <name>` accepts a registered repository name. Completion is exposed by normal return from the command client.

## `velnora pull`

`velnora --config <config_dir> pull <name>` accepts a registered repository name. Completion is exposed by normal return from the command client.

## `velnora db`

`velnora --config <config_dir> db info` writes a stdout line beginning `db version: <revision>`, where the revision is the first space-delimited token after `db version: `. Its compatibility line is `CLI compatible with db: <boolean>`, with token `True` or `False`.

`db versions` writes a whitespace-separated table to client stdout. Each revision row has the revision token in its first column. `db upgrade <revision>` and `db downgrade <revision>` accept a revision token; `latest` names the latest revision. A migration refusal raises `VelnoraClientError`.

A SQLite repository records its schema revision in two tables: `alembic_version` (column `version_num`, the applied migration identifier) and `velnora_version` (columns `id`, `version` — the major revision number — and `timestamp`; the row with the latest `timestamp` is current). A repository written by a newer client carries a migration identifier this client does not know, under that client's major number; `db info` then shows the revision as `<major>.?`.

## `velnora repl`

`velnora --config <config_dir> repl <job_id>` accepts Python inspection input on stdin. `!<Python statement>` evaluates a supplied statement and `continue` exits the session. `obj` is the selected job. `obj.call_node.arguments[<position>].value.value_parsed` exposes a restored argument; `obj.call_node.value.value_parsed` exposes the restored result. Successful session completion has process status `0`.

## `velnora run --input`

The caller-selected path passed to `run --input` contains a binary Python pickle of `(args, kwargs)`: `args` is a positional-argument sequence and `kwargs` is a mapping from parameter names to Python values.

## `velnora.federated_tasks input_path`

The delegated argument file named by `input_path` is a binary Python pickle of `[task_args, task_kwargs]`, a two-element list whose first element is a positional-argument tuple and whose second is a keyword-argument dictionary.

## `velnora.console.app.VelnoraApp`

`from velnora.console.app import VelnoraApp`; `VelnoraApp(scheduler, args, extra_args, argv)` accepts a loaded scheduler, an `argparse.Namespace`, a route argument list, and a complete command argument list. An empty route selects the executions view. `run_test(size=(width, height))` is an asynchronous context manager returning a pilot with `pause()` and `press(*keys)` methods.

`export_screenshot()` returns SVG text. Rendered text is in SVG `text` elements with a `y` coordinate; text can contain nonbreaking spaces. View labels include ` executions `, `Jobs (<count>)`, `Result: <Python literal>`, `Task`, and `Value`. Job and task views carry qualified task names; the value view displays a scalar result on a separate line as a Python literal.

Pilot key names are `enter` for the selected record, `/` for the filter input, and `escape` for the previous view. Filter text accepts `--task <qualified_name>` and `--status <status>`; the active flags are displayed in the execution view. `run_action("screen.click_task")` follows the task link and `run_action("screen.click_value('<value_hash>')")` follows a value link.

## `velnora.file`

`velnora.file` exposes `FileSet`, `ContentFile`, `IFile`, `ContentFileSet`, `ContentDir`, `IFileSet`, `IDir`, `glob_file`.

## `velnora.value`

`velnora.value` exposes `Value`, `ProxyValue`, `InvalidValueError`, and `get_type_registry`.

## `velnora.cli`

`velnora.cli` exposes `VelnoraClient`, `VelnoraClientError`, and the process entry `main`.

## `velnora.config`

`velnora.config` exposes `Config`.

## `velnora.backends.db`

`velnora.backends.db` exposes `VelnoraDatabaseError` and `VelnoraVersionError`.

## `velnora.namespace`

`velnora.namespace` exposes `namespace` and `get_current_namespace`.

## `velnora.scheduler`

`velnora.scheduler` exposes `JobInfo`, `SchedulerError`, `catch`, `catch_all`, `cond`, `fork_thread`, `join_thread`, and `subrun`.

## `velnora.functools`

`velnora.functools` exposes `apply_func`, `compose`, `const`, `delay`, `eval_`, `flat_map`, `flatten`, `force`, `map_`, `no_prov`, `seq`, `starmap`, and `zip_`.

## `velnora.scripting`

`velnora.scripting` exposes `ScriptError` and `script`.

## `velnora.federated_tasks`

`velnora.federated_tasks` exposes `federated_task`, `lambda_federated_task`, `launch_federated_task`, and `rest_federated_task`.

## `velnora.glue`

`from velnora.glue import udf, sql_query` exposes the callable entries.

## `velnora.console.app`

`velnora.console.app` exposes `VelnoraApp`.

## `velnora.File`

`from velnora import File` exposes the `velnora.file.File` entry at the package root.

## `velnora.Dir`

`from velnora import Dir` exposes the `velnora.file.Dir` entry at the package root.

## `velnora.catch`

`from velnora import catch` exposes the `velnora.scheduler.catch` entry at the package root.

## `velnora.ShardedS3Dataset.from_files`

Stated under `velnora.file.ShardedS3Dataset`.

## `velnora.cond`

`from velnora import cond`; `cond(cond_expr, then_expr, *rest)` accepts alternating predicate and branch expressions, followed by a final alternative. It returns a deferred result with the selected branch’s Python shape, or raises the propagated exception.

## `velnora.script`

Stated under `velnora.scripting.script`.

## `velnora.ShardedS3Dataset`

Stated under `velnora.file.ShardedS3Dataset`.

## `velnora.context`

`velnora.context` exposes `get_context`.

## `docker`

The container runtime is the `docker` executable on `PATH`. Submission uses `docker run -d --memory=<memory>g --cpus=<vcpus> [-v <host>:<container>] [-e <name> ...] <image> <command...>`. The image is a string, the command is an argument vector, memory is expressed in GB, and CPU capacity is numeric. An environment argument names a variable to forward. Submission stdout contains the opaque container identifier on its own line.

The runtime also accepts `docker ps`, `docker logs <id>`, and `docker rm <id>`. The `ps` output has a header row followed by whitespace-separated rows whose first column contains container identifiers. The `logs` output carries the container's captured output.

## `/v1/registerjobdefinition`

AWS Batch job-definition registration uses `POST /v1/registerjobdefinition` with a JSON object. `jobDefinitionName: str` names the definition. A container definition exposes `containerProperties.image: str`, the requested image. A multi-node definition exposes `nodeProperties.numNodes: int`, the requested node count.

## `/v1/submitjob`

AWS Batch submission uses `POST /v1/submitjob` with a JSON object containing `jobName: str`, `jobQueue: str`, and `jobDefinition: str`, naming the submitted work, queue, and registered definition.

The command is an argument vector in `containerOverrides.command: list[str]`. Resource requests are `containerOverrides.resourceRequirements: list[object]`; each object contains `type: str` and `value: str`. The type markers are `VCPU` for CPU capacity and `MEMORY` for memory in MiB. `value` is the requested amount as numeric text.

An array submission carries `arrayProperties.size: int`, the number of array children. A multi-node submission carries `nodeOverrides.nodePropertyOverrides: list[object]`; each object has `targetNodes: str` and `containerOverrides.command: list[str]`. The main-node command has `targetNodes: "0"`; the worker command has a worker node-range string in AWS Batch syntax. Worker environment names are `AWS_BATCH_JOB_NODE_INDEX`, `AWS_BATCH_JOB_MAIN_NODE_INDEX`, and `AWS_BATCH_JOB_ARRAY_INDEX`, with zero-based decimal index strings; the main-node index is `"0"`.

## `/v1/describejobdefinitions`

AWS Batch definition lookup uses `POST /v1/describejobdefinitions` with a JSON object containing `jobDefinitionName: str`, the definition name.

## `/v1/describejobs`

AWS Batch job lookup uses `POST /v1/describejobs` with a JSON object containing `jobs: list[str]`, the service job identifiers being requested.

## `/v1/listjobs`

AWS Batch job listing uses `POST /v1/listjobs` with a JSON object. Queue selection uses `jobQueue: str` and `jobStatus: str`; array-child selection uses `arrayJobId: str`, the parent service job identifier.

## `velnora.context.get_context`

Stated under `velnora.get_context`.
