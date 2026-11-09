# Workflow Framework Product Requirements

This Python workflow framework supports composing computations, executing them across local and remote environments, reusing prior work, and exploring data provenance.

### FP-01: Task definition and dynamic workflows

- Authors can define named Python tasks, distinguish identically named tasks by namespace, and compose calls without executing their bodies until the workflow is run. Running a workflow returns its fully resolved result.

- Tasks receive resolved argument values and may return further task calls, including recursive calls whose continuation depends on computed data.

- Expressions nested in lists, tuples, dictionaries, named tuples, dataclass instances, and sets whose resolved members are mutually orderable resolve into concrete values while preserving the surrounding structure.

- Indexing, attribute access, addition, subtraction, multiplication, true division, equality, inequality, and ordered comparisons on deferred results produce the corresponding operation's result after their operands resolve. Either operand of a binary operation may be deferred. Invalid operations on the resolved values fail with the underlying operation failure.

- Direct truth testing of an unresolved expression and iteration over an expression with unknown length are refused as unsupported uses of deferred values. A task with an explicitly declared nonnegative integer output count permits iteration and unpacking of that many deferred outputs, including zero outputs. Without an explicit count, a fixed-length tuple return annotation supplies the count; otherwise the length is unknown. Negative or noninteger declared counts are refused as invalid task declarations.

- Calls honor declared argument defaults and positional and named argument binding. Missing required arguments, duplicate assignments to one argument, and arguments not accepted by the task cause argument-binding failure.

- An unhandled task failure propagates through work requiring its result, and the workflow exposes that failure instead of returning a successful result.

- Omitting a task name or supplying an empty name uses the name of the authored computation. An explicit namespace takes precedence over a namespace declared for its source module, which takes precedence over the current author-selected namespace; no namespace is also permitted. For ordinary single-line declarations, names and nonempty namespaces begin with an ASCII letter or underscore and continue with ASCII letters, digits, or underscores; namespaces additionally permit dots after the first character. Other ordinary single-line names are refused as invalid task declarations. Validation of names or namespaces containing line terminators is outside this guarantee.

- For a deferred list result, a caller can select a range with a nonnegative start, an explicit nonnegative exclusive stop no greater than the eventual list length, and a positive step. The result contains the selected elements in order; the default start is zero and the default step is one.

- Deferred boolean conjunction and disjunction return the conjunction or disjunction of their resolved boolean operands. Both operands are resolved; an operand failure propagates even if the other boolean alone would determine the answer.

### FP-02: Extensible workflow values

- Serializable Python values, with set values limited to mutually orderable members, can be passed as task arguments and returned as results without a custom adaptation. Saving and restoring a value preserves the data needed for subsequent task use; values that cannot be serialized fail as unsupported values.

- Authors can define value equivalence and saving and restoration behavior for their own types, including adaptations of existing types. Task code receives the represented value, and equivalent values remain equivalent after restoration.

- Authors can supply a validity rule for values representing external state. A restored value is valid only while its declared rule accepts the current state.

- Authors can define conversion from command-line text for custom value types. Valid text produces the custom value, and conversion failures are exposed as invalid arguments.

- Author-defined input and output transformations are applied to custom values crossing task boundaries, and subsequent task code observes the transformed values.

- Importable functions defined at module scope can be passed as values and restored for later calls. Functions defined inside another function are refused as unsupported workflow values. A restored function whose source module or named function is no longer available is invalid for reuse.

### FP-03: Files, directories, and storage transfer

- Users can read, write, copy, inspect existence, and remove files on local storage, S3, and GCS when the selected service is accessible. Text operations preserve text under the selected encoding, and binary operations preserve bytes; on object storage the text guarantee covers encodings that do not begin their output with a byte-order mark. Reading a missing file fails as missing data.

- Users can create directories, enumerate files by a directory or wildcard selection, and copy directory contents while preserving relative locations. Removing a nonempty local directory without recursive removal is refused.

- File version tracking distinguishes local files by path, size, and modification time, S3 objects by path and object entity tag, and GCS files by path and size. A file tracked while it exists becomes invalid if it is removed or its tracked version changes.

- Content-sensitive files distinguish changed contents at the same location and treat equal contents at that location as equivalent despite changes in modification time. Explicitly immutable files are identified by location and remain valid despite later changes or removal of the underlying file.

- Ordinary directory and file-set validity includes both selected membership and the tracked versions of constituent files. Content-sensitive file sets use the content-sensitive file rule. For content-sensitive directories, the guarantee covers directory membership and ordinary tracked file versions; ignoring modification-time changes and detecting same-size content changes with unchanged modification times are outside this guarantee. Explicitly immutable collections remain valid despite membership or content changes.

- Input staging makes a file or directory available at a chosen working location; output staging transfers generated files or directories to their designated storage locations. Returned staged values refer to the destination data and preserve their enclosing collection structure.

- Users can read remote files over HTTP and HTTPS and copy their contents into writable storage. Unavailable remote data produces a transfer failure.

- Directory enumeration includes files in nested directories. Local file operations expose size in bytes, create missing parent directories when writing a file, and permit removing an already absent file. A copy replaces an existing destination by default; a caller can instead preserve an existing destination, in which case its contents remain unchanged.

### FP-04: Scoped task options and context

- Task options can be supplied through executor configuration, task definition, exported parent options, individual calls, and execution-wide constraints. For a conflicting option, these sources take precedence in that order from lowest to highest.

- Exported options affect descendant calls in the chosen subworkflow. An override on one call does not alter an unrelated sibling's options. Options expressed as task computations use their resolved values.

- A workflow context provides nested named values to tasks without requiring intermediate tasks to pass those values as arguments. Looking up a missing path, or a path continuing through a nonmapping value, returns the supplied default; without a supplied default it returns an absent value.

- A subworkflow can override context values for itself and its descendants. Nested mappings are merged, overridden leaves use the new values, and unrelated leaves and sibling contexts are preserved.

- Context can be supplied inline in configuration or in a separate file, and updated for a workflow run. Supplying both inline context and a context file in the same scheduler configuration is refused as conflicting configuration.

- Run-level context updates override configured context. For command-line runs, a supplied run context file overrides configured values, explicit context entries override that file, and a subworkflow context override takes precedence within its scope. These updates preserve unrelated nested values.

### FP-05: Local execution and resource limits

- Local tasks share the calling program's process-local state by default. Callers can instead select isolated local execution, in which task changes to that state do not change it in the calling program; returned values and task failures remain available to the workflow. An unknown local execution mode or executor is refused as invalid execution configuration.

- Independent ready tasks can make progress while another task is waiting for external input or output, subject to the configured execution capacity. A task requiring another task's result starts its body only after that result is available.

- The configurable local execution capacity limits the number of simultaneously executing synchronous task bodies for each local state-sharing or isolated execution mode of an executor; its default is 20. Alias executors targeting the same executor share that capacity.

- For each declared resource, the sum of resource amounts assigned to executing synchronous task bodies does not exceed its configured capacity. A task may require several resources and more than one unit of each. A listed resource without an explicit amount costs one unit, and a resource without a configured capacity has capacity one. Resource amounts and capacities in this guarantee are positive integers, and each task's request fits the capacity of each resource it uses.

- Work waiting for resource capacity can proceed when earlier task bodies return or fail and release sufficient capacity. Returning further workflow expressions does not retain the returning task body's resource allocation while that further work resolves.

### FP-06: Durable execution history

- A workflow repository persists completed execution history across client restarts. SQLite is the default repository service; PostgreSQL is also supported. Reopening the same repository makes its recorded work available again.

- With provenance recording enabled, which is the default, executions retain their jobs, task identities and versions, task source, argument and result values, parent-child calls, and value derivations. Separate executions remain distinguishable even when they perform equivalent work.

- Recorded jobs distinguish successful execution from failed execution. A recorded task failure retains the cause and the workflow task trace needed to identify where it arose.

- Users can configure an external value store to hold saved values and recover them for later use through the repository, including selection of a zero minimum placement size, which places all saved values there. Missing external value data is not treated as a recovered successful value.

- Saving a single serialized value larger than the configured size limit is refused as too large. The default limit is 1,000,000,000 bytes, measured as the length of that value's serialized representation.

- A task can request information about its current execution and job. Executing tasks receive identifiers corresponding to their recorded execution and individual job, and can inspect their effective task options.

### FP-07: Provenance tags

- Users can attach metadata tags to executions, jobs, tasks, and values. Tag values support numbers, strings, booleans, absence, lists, and mappings; multiple distinct values may coexist under one key.

- Jobs use their effective tag options, with task-defined tags subject to the option precedence rules. Tags may also be attached during workflow execution, and attaching a tag to a value returns the value unchanged.

- Users can add, replace, and remove tags on recorded executions, jobs, and non-task values after execution when the selected identifier resolves unambiguously. Editing a recorded task through its shared task/value identifier is outside this guarantee. Adding an association preserves other values under its key; replacing a key supersedes its previous associations with the supplied values. Removal can target an exact key and value or all values under a key. Current tag queries reflect these changes while tag history retains the superseded associations.

- Users can select recorded entities by tag-key presence or by a key and value together. With SQLite, exact selection of an absent tag value is outside this guarantee; storing that value and selecting by its key remain supported. When several tag restrictions are supplied, an entity must satisfy every restriction. Results distinguish entities with the requested associations from entities without them.

### FP-08: Incremental execution and prior-result reuse

- By default, calls to the same task with the same positional and named argument arrangement and equivalent resolved argument values share their result within an execution, including calls whose arguments came from different computations and calls requested while equivalent work remains unfinished. Repeated references to the same expression obtain one evaluation's result.

- By default, a successful call recorded in the same repository can satisfy a later equivalent call without executing the task body again, provided the task and its recorded dependent tasks remain current and the relevant saved values remain valid. This applies across workflow executions and client restarts. Recorded jobs distinguish results obtained from prior work from newly executed results.

- Changes to a task's source, name, namespace, or meaningful arguments make the affected call require new work.

- Authors can assign an explicit task version that replaces source changes as the task's version criterion. Equal explicit versions are treated as the same version regardless of their spelling's apparent ordering; changing an explicitly included code or data dependency still changes task identity.

- Arguments declared to be configuration-only do not distinguish reusable calls. All other bound arguments, including their defaults, participate in distinguishing calls.

- Full validity checking is the default and requires invalid intermediate and final values to be regenerated. Selecting shallow checking instead permits reuse without restoring invalid intermediate values when final values remain valid and the recorded called tasks remain current.

- Users can select reuse across recorded executions, reuse only within the current execution, or no task-call result reuse. Disabling task-call reuse does not disable shared-expression evaluation within a returned expression structure. Disabling reads of prior results still records successful work for later executions when provenance remains enabled.

- An unhandled failure recorded in a previous execution does not prevent a fresh attempt at that task in a later execution. A successfully recovered computation may instead reuse its recovered result; changes to the recovery task require reevaluation of the affected recovery. After successful recovery, changing only the previously failing task source is outside this invalidation guarantee.

- Context-dependent work uses the context of its call. Work under different contexts must return the appropriate context-dependent result rather than a result belonging to another context, under both full and shallow checking.

- Disabling provenance for a subworkflow suppresses its descendant job history and disables prior-result use inside that scope. Users can separately retain and reuse the subworkflow's final result through an enclosing recorded call while omitting its internal provenance.

### FP-09: Stateful handles

- Authors can pass handles representing ephemeral resources between tasks. After saving a handle and restarting the client, subsequent tasks can use the represented resource without rerunning the task that originally supplied the handle.

- A task receiving and returning a stateful handle establishes a state transition. Unchanged valid transitions may be reused; changed task code or inputs cause the affected transition and dependent transitions to execute again.

- When a new transition supersedes a previously recorded state, reverting to the earlier task version does not silently restore that earlier state: the corresponding work executes again to establish it.

- Authors can fork handles into independent branches and merge resulting handles before dependent work. When the changed branch supplies the resulting merged handle, it invalidates dependent transitions without requiring an unchanged independent branch to execute again. Invalidation and independent reuse after changes to other merge participants are outside this guarantee.

### FP-10: Workflow control, composition, and recovery

- Given ordered predicate-and-branch pairs and a final alternative, a conditional evaluates predicates in their declared order and resolves only the first branch with a truthy predicate, or the final alternative when no predicate succeeds. Work used solely by an unselected branch is not executed. Failure of an evaluated predicate propagates.

- Recovery returns a successful computation unchanged without invoking a handler. For a failing computation it selects the first handler accepting the failure's type or a parent type, and passes the failure to that handler. A handler can accept several error types. The handler's resolved result becomes the recovered result; unmatched failures and failures raised by the handler propagate.

- Group recovery waits for all computations in a nested collection to settle. With no failures, it returns the resolved collection without invoking a handler. With failures, when every encountered failure matches the accepted error types, the handler receives the collection with successes and failures in their original positions, and its resolved result becomes the result. An unmatched failure, failure without a supplied handler, or handler failure causes group recovery to fail.

- Authors can require computations to execute sequentially in the declared order and receive their ordered results.

- Tasks can be supplied as arguments, returned as values, and partially bound for later invocation. Later positional arguments follow earlier partial positional bindings, and later named arguments override earlier partial named bindings. Partial binding can be repeated; invalid completed argument binding fails.

- Mapping a task over a resolved collection returns the corresponding results in input order. Mapping rows of named arguments supplies each row to the task as named inputs.

- Flattening concatenates nested lists in their existing order; flat mapping concatenates the lists returned by mapping. Task composition applies the last supplied task first and passes each result into the preceding task.

- Authors can carry a deferred computation as a value without executing it and later explicitly request its evaluation. A dependency barrier returns its chosen result only after its additional prerequisite work completes successfully.

- Combining resolved input sequences position by position returns ordered tuples containing one item from each sequence, ending at the shortest input.

- Authors can apply an importable Python function to resolved positional and named inputs as workflow work, returning its result or propagating its failure. They can also evaluate a supplied Python expression using resolved named values and positional values assigned to caller-supplied names. The number of positional values must equal the number of supplied names; a mismatch is refused as invalid binding.

- Authors can wrap tasks with additional computation and compose multiple wrappers. Calls use the innermost task's argument declaration by default, or the wrapper's declaration when selected, and return the wrapped computation's resolved result. Changes to the wrapped task, wrapper, or explicitly included wrapper dependencies invalidate prior results.

- Authors can start a computation and pass a reference to it to subsequent tasks without waiting for its result. Explicitly joining that reference returns the computation's resolved result or propagates its failure. Multiple joins can retrieve the result, and unrelated work can progress before the computation completes.

### FP-11: Eager evaluation inside asynchronous tasks

- An asynchronous task using local execution without state isolation can wait for task expressions and then use their concrete results in ordinary Python control flow. The awaited work may be synchronous or asynchronous, and a synchronous workflow can call an asynchronous task.

- Failures from awaited work are delivered to the waiting task for ordinary error handling; failures it does not handle propagate to its caller.

- Asynchronous tasks requiring eager evaluation are refused when a remote execution environment is selected. Authors must explicitly select disabled prior-result reuse or enabled reuse with shallow validity checking; omitting this choice or enabling reuse with full validity checking is refused.

### FP-12: Script tasks and staged outputs

- Authors can execute a supplied script as workflow work and receive its standard output when no output values are specified. A script may be supplied as text or as a command and ordered arguments; the latter preserves each argument as one argument, including embedded spaces. With declared output files or directories, execution that produces those artifacts returns them in the declared enclosing structure.

- Script tasks can stage input data into their working location and publish generated output data to designated storage locations. Selecting an isolated working directory keeps intermediate files from separate invocations from colliding at the same relative name.

- Scripts without an explicit interpreter use Bash. In the default script mode, failure of an unhandled standalone command or a pipeline causes script failure and prevents subsequent standalone commands from running; the workflow exposes diagnostic output from the failed script. A command used by the script as a condition does not by itself fail the script when its condition is false. An explicit interpreter runs the supplied script under that interpreter.

### FP-13: Container and cloud task execution

- Users can run task computations in Docker and AWS Batch with the corresponding configured service, execution environment, credentials, and shared storage available. Work executes in the selected environment using the supplied arguments, and its completed result becomes available to dependent workflow work.

- With remote code delivery enabled, files matching caller-supplied inclusion patterns relative to the working directory are made available to remote tasks, except files matching any exclusion pattern. With delivery disabled, tasks use code already available in their execution environment. Container tasks use the selected image, and requested compute resources are passed to the selected execution service. For Docker execution from a client outside EC2, callers can request forwarding of their AWS credentials and region to the container; disabling forwarding does not pass these caller values to the container.

- Remote task exceptions, failed scripts, and execution-service failures that prevent successful task completion cause workflow failure with information identifying the failed work. Docker requires an image and shared working storage; AWS Batch requires an image, a job queue, and S3 working storage; AWS Glue requires S3 working storage. Omitting these required settings is refused as incomplete configuration.

- Following an interrupted workflow client, AWS Batch execution can reconnect to matching work still submitted or running in the same configured service, for the same task and arguments, when cross-execution reuse is enabled and the service still exposes the job. Reconnection returns that job's outcome without a second submission.

- For AWS Batch array submission, callers can choose a minimum pending-call count; simultaneously pending calls to the same task with matching effective options are grouped when they meet that minimum. AWS Batch multi-node work runs the task with the same arguments on each requested node and returns the main node's Python result to the workflow. Combining multi-node work with array submission is refused as an incompatible execution request.

### FP-14: Sharded datasets and Spark data processing

- Users can represent an S3 dataset by a location, data format, and recursive membership choice. Recognized formats are Avro, CSV, Ion, Grok logs, JSON, ORC, Parquet, and XML; the defaults are Parquet and recursive membership. Membership selects files whose filename extension denotes the selected format, either directly under the location or also in nested locations when recursion is selected. Other formats and locations outside S3 are refused.

- Dataset validity tracks shard membership: added, removed, or renamed matching shards invalidate a prior dataset. Rewriting an existing shard without changing membership does not itself invalidate this dataset representation.

- Creating a dataset by inferring its format from an explicit file collection requires a nonempty collection of existing S3 files in one bucket with the same recognized filename extension. The dataset location is their deepest common containing directory, and matching files beneath it are included recursively. Missing files, non-S3 files, and mixed inferred formats are refused. Additional matching files under the inferred location are refused unless the caller explicitly allows their inclusion.

- CSV, Parquet, JSON, and ORC datasets can be read as individual local tables or, for a nonempty selection, combined into one table containing the selected shards' rows in selection order. All shards are loaded by default; a caller can select a positive maximum number, with shards selected in lexicographic filename order. Other dataset formats are refused for local table loading.

- In an AWS Glue Spark environment, users can load an S3 dataset as a distributed table and save a distributed table as dataset shards at the chosen S3 location. Without an available Glue context, distributed dataset access fails as a missing execution prerequisite and leaves no dataset shards at the target.

- In a Spark environment, authors can apply a supplied row transformation to distributed columns with a declared result type. Without an active Spark context, the same authored transformation can be called as an ordinary Python function and returns its ordinary result.

- In a Spark environment, authors can run a supplied SQL query against a distributed table under a chosen table alias and receive the query result as a distributed table.

### FP-15: Subworkflows and federated execution

- Authors can execute a whole subworkflow in a selected execution environment with its own configuration. The calling workflow receives the subworkflow's fully resolved result or its failure, rather than unresolved remote work.

- A subworkflow retains its job relationships beneath the parent execution by default, or can create a separately identifiable execution. Context and exported options supplied by the parent remain available within the subworkflow. If the parent is not recording provenance, the subworkflow creates a separate execution even when continuation of the parent execution was requested; with SQLite this guarantee requires a separate repository for the subworkflow.

- A caller can invoke a published federated task using its entrypoint configuration and arguments without having the task's source available for local import. The configured remote code runs and returns its result to the caller.

- A federated publication specifies the remote task name, namespace, source to load, executor, and remote configuration location. Requests with an unknown published entrypoint, omission of any of these publication settings, or an unknown configured executor fail as invalid federation configuration.

- Users can launch a workflow command in a selected executor and wait for its completion, receiving its output or failure. Docker and AWS Batch also support submission without waiting for workflow completion, identify the submitted container or service job, and let submitted work continue after the client exits. Successful submission does not promise a successful workflow result. Omitting the executor is refused as incomplete launch configuration.

- A subworkflow inherits the parent's configuration when no separate configuration is supplied. Supplying both a nonempty explicit configuration and a configuration location is refused as conflicting configuration. The enclosing subworkflow call defaults to cross-execution reuse and shallow validity checking; work inside the subworkflow follows its own configured reuse policy. A federated invocation instead limits reuse of its enclosing subworkflow call to the current execution.

- A caller can delegate a federated launch request to an HTTP endpoint or AWS Lambda function, supplying the publication configuration, entrypoint, arguments, and a shared location for those arguments. The returned submission description identifies the requested execution and retains the inputs needed to launch it; it does not return the workflow result. Previewing such a request saves the argument data and returns the submission description without contacting the endpoint or Lambda function. An HTTP request rejected by the endpoint fails as a submission failure.

### FP-16: Command-line workflow lifecycle

- Users can initialize a workflow configuration and run a selected task from a workflow source with typed arguments and declared defaults. Missing tasks, missing required arguments, and values that cannot be converted to their declared argument types are refused as invalid invocations.

- Workflow positional and named arguments can be loaded from a saved argument file. Explicitly supplied command-line arguments override corresponding loaded named arguments. Loaded positional arguments retain their positions.

- Users can rerun a recorded job or execution using its recorded arguments, with optional changes to recorded named arguments, against the available task definitions. Selecting nonexistent recorded work fails as missing history; a recorded argument that can no longer be restored prevents the rerun.

- A dry run identifies reusable work and work requiring execution without executing new user task bodies. Work that would only be discovered by running new task bodies is not presented as a fully known future workflow.

- With no command-line configuration selection, a missing default configuration is initialized for use. For execution and history operations, a configuration directory explicitly selected on the command line that does not exist is refused as missing configuration. Initialization itself can create an explicitly selected directory.

- Command-line arguments without type annotations are text. Built-in conversion supports text, integers, real numbers, booleans, enumeration members, file and directory locations, calendar date-times with a fully specified date and optional time and UTC offset, and importable functions. Booleans accept the words true and false; enumerations select declared members by member name, optionally qualified by the enumeration name. Missing function sources or names and unknown enumeration members fail as invalid arguments.

- List arguments accept one or more supplied items and convert each to the declared element type; a list without an element type uses text. Optional scalar arguments with an absent default retain absence when omitted and use the scalar conversion when supplied.

### FP-17: History search and interactive exploration

- Users can find recorded executions, jobs, tasks, values, and files, and inspect a record selected by its identifier or an unambiguous identifier prefix. A selector with no matching record produces a missing-record result.

- History searches can restrict executions by running, failed, or successful status, and jobs by running, failed, newly successful, or reused-result status. Job and task searches can restrict by task name or version; an unqualified task name matches that name across namespaces, while a qualified name selects its namespace. Executions, jobs, tasks, and values can be restricted by tags. Multiple alternatives within a status or task selection are alternatives; different filter categories must all hold.

- Inspecting a job exposes its arguments, result or failure, task version and recorded source, and relationships to its execution, parent, and children. Inspecting a file distinguishes producing jobs from jobs consuming it; upstream dataflow identifies the recorded values and calls from which a result derives.

- The interactive terminal interface supports navigation from executions to jobs and onward to tasks and values, returning to previous views, and filtering a freshly opened execution job view by task and status. Repeated filter changes in the same view after an empty result are outside this guarantee. Selecting a different record displays that record's history.

- Users can open an interactive Python inspection session for selected recorded work and evaluate expressions over its restored arguments and result when their value types are available in the inspection environment.

### FP-18: Repository sharing and schema management

- Users can register named workflow repositories, list their configured locations, and select one for history operations. Registering an already used name or the name designating the default repository is refused; selecting an unknown repository or a location without repository configuration fails as missing configuration.

- Exporting recorded history and importing it into another compatible repository preserves the transferred executions, jobs, tasks, values, tags, and their recorded relationships. Reimporting the same records does not create duplicate history.

- Users can push or pull recorded execution history between configured repositories. The destination receives records it lacks while retaining its existing history, and repeating an already completed transfer adds no duplicate records.

- Users can inspect repository schema compatibility and request upgrades or downgrades to revisions 1.0, 2.0, 2.1, 2.2, 2.3, 3.0, 3.1, 3.2, 3.3, 3.4, and 3.5. The latest revision is 3.5. Unknown target revisions are refused as invalid migration requests.

- Repository use requires a schema revision from 3.5 through 3.99 inclusive. Opening an incompatible schema without a permitted upgrade fails as incompatible repository data. Automatic upgrades are enabled by default for SQLite repositories and disabled by default for PostgreSQL repositories; automatic migration never downgrades a repository.
