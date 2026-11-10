# Interface Contract

The Python package is `velmora`, provided under `src/velmora` relative to the project root. Add `src` to the Python import path when using the source tree.

Configuration environment names are `OPENAI_DEFAULT_MODEL` for model selection, `OPENAI_API_KEY` for authentication, and `OPENAI_BASE_URL` for the service endpoint. API-key values and endpoints are strings. Application calls return Python objects or asynchronous event streams.

## `velmora.Agent`

Import `Agent` with `from velmora import Agent`.

Construction accepts `handoffs: list[Agent[Any] | Handoff[TContext, Any]]`, `hooks: AgentHooks[TContext] | None`, `input_guardrails: list[InputGuardrail[TContext]]`, `instructions: str | Callable[[RunContextWrapper[TContext], Agent[TContext]], MaybeAwaitable[str]] | None`, `mcp_config: MCPConfig`, `mcp_servers: list[MCPServer]`, `model: str | Model | None`, `model_settings: ModelSettings`, `name: str`, `output_guardrails: list[OutputGuardrail[TContext]]`, `output_type: type[Any] | AgentOutputSchemaBase | None`, `prompt: Prompt | DynamicPromptFunction | None`, `reset_tool_choice: bool`, `tool_use_behavior: Literal['run_llm_again', 'stop_on_first_tool'] | StopAtTools | ToolsToFinalOutputFunction`, `tools: list[Tool]`.

The constructor fields are readable and writable attributes. `instructions` is text or a synchronous/asynchronous callback `(context, agent) -> str`; the context has `.context`. `prompt` is a mapping with `id: str`, `version: str`, `variables: dict`, or a synchronous/asynchronous callback receiving `.agent` and `.context.context` and returning that mapping.

`clone(**kwargs) -> Agent` accepts replacements for `name`, `instructions`, and `tools`; its result exposes `name`, `instructions`, `model`, `output_type`, `tools`, `handoffs`, `mcp_servers`, `input_guardrails`, and `output_guardrails`.

`as_tool(tool_name, tool_description, *, custom_output_extractor, parameters, input_builder, max_turns, run_config, failure_error_function, needs_approval) -> FunctionTool` accepts the supplied options independently. `parameters` is an application record type. `input_builder(options)` can be asynchronous and receives `options["params"]` as parsed arguments, returning text or input-item dictionaries. `custom_output_extractor(result)` can be asynchronous and returns tool-result text. Without an application parameter declaration, the tool argument object has `input: str`.

Completion selection uses `tool_use_behavior` with `run_llm_again`, `stop_on_first_tool`, a mapping with `stop_at_tool_names: list[str]`, or callback `(context, results) -> ToolsToFinalOutputResult`; callback result entries expose `.output`. `mcp_config` accepts `failure_error_function` and `include_server_in_tool_names`.

## `velmora.AgentOutputSchema`

Import `AgentOutputSchema` with `from velmora import AgentOutputSchema`.

Construction accepts `output_type: type[Any]`, `strict_json_schema: bool`.

`is_plain_text() -> bool` identifies the output carrier kind. Structured model text is a JSON object for an object declaration; a non-object declaration uses `{"response": <declared value>}`. Output validation failures use `ModelBehaviorError`; declaration configuration failures use `UserError`.

## `velmora.ApplyPatchTool`

Import `ApplyPatchTool` with `from velmora import ApplyPatchTool`.

Construction accepts `name: str`, `allowed_callers: list[ToolCaller] | None`, `editor: ApplyPatchEditor`.

Construction additionally accepts `needs_approval` and `on_approval` with the local-tool approval callback shape. The supplied editor provides `create_file(operation)`, `update_file(operation)`, and `delete_file(operation)`. Operation attributes are `type`, `path`, and `diff`; the type spells the selected editor method, the path is text, and the diff is text or `None`. Editor methods return `ApplyPatchResult` or text.

## `velmora.CodeInterpreterTool`

Import `CodeInterpreterTool` with `from velmora import CodeInterpreterTool`.

Construction accepts `tool_config: CodeInterpreter`.

`tool_config` is a mapping with `type="code_interpreter"`, `container`, and `allowed_callers: list[str]` when supplied.

## `velmora.Computer`

Import `Computer` with `from velmora import Computer`.

Subclassable controller with `environment` and `dimensions` properties. The controller methods reached through `ComputerTool` are `click(x, y, button)`, `double_click(x, y)`, `scroll(x, y, scroll_x, scroll_y)`, `type(text)`, `wait()`, `move(x, y)`, `keypress(keys)`, `drag(path)`, and `screenshot()`. Coordinates are integers, `keys` is a string list, and `path` is a list of coordinate pairs. `screenshot()` returns base64 image text.

## `velmora.ComputerTool`

Import `ComputerTool` with `from velmora import ComputerTool`.

Construction accepts `computer: ComputerT | ComputerCreate[ComputerT] | ComputerProvider[ComputerT]`, `on_safety_check: Callable[[ComputerToolSafetyCheckData], MaybeAwaitable[bool]] | None`.

`on_safety_check(data)` returns a boolean synchronously or asynchronously. The data exposes `.ctx_wrapper.context`, `.agent`, `.tool_call.call_id`, and `.safety_check` with `id`, `code`, and `message`. Review rejection uses `UserError`.

Computer results use `type="computer_call_output"`, `call_id: str`, and `output` with `type="computer_screenshot"` and `image_url` in the form `data:image/png;base64,<image content>`. `acknowledged_safety_checks` is omitted, `None`, or a list of mappings with `id`, `code`, and `message`.

## `velmora.CustomTool`

Import `CustomTool` with `from velmora import CustomTool`.

Construction accepts `allowed_callers: list[ToolCaller] | None`, `description: str`, `format: object | None`, `name: str`, `needs_approval: bool | CustomToolApprovalFunction`, `on_approval: CustomToolOnApprovalFunction | None`, `on_invoke_tool: CustomToolExecutor`.

`name`, `description`, and `format` are readable attributes. `on_invoke_tool(context, input)` accepts raw text and returns content, synchronously or asynchronously. `format` is `None`, `{"type":"text"}`, or a grammar declaration with `type="grammar"`, `syntax`, and `definition` strings.

`on_approval(context, item)` receives `ToolApprovalItem` and returns a decision mapping containing `approve: bool` and `reason: str`, synchronously or asynchronously.

## `velmora.FileSearchTool`

Import `FileSearchTool` with `from velmora import FileSearchTool`.

Construction accepts `filters: Filters | None`, `include_search_results: bool`, `max_num_results: int | None`, `ranking_options: RankingOptions | None`, `vector_store_ids: list[str]`.

The construction fields are public configuration: storage identities, filters, ranking configuration, and result selection. Rejected configuration uses `UserError`.

## `velmora.FunctionTool`

Import `FunctionTool` with `from velmora import FunctionTool`.

Construction accepts `description: str`, `name: str`, `needs_approval: bool | Callable[[RunContextWrapper[Any], dict[str, Any], str], Awaitable[bool]]`, `on_invoke_tool: Callable[[ToolContext[Any], str], Awaitable[Any]]`, `params_json_schema: dict[str, Any]`.

Readable and writable fields include `name`, `description`, `params_json_schema`, `needs_approval`, `tool_input_guardrails`, and `tool_output_guardrails`. `on_invoke_tool(context, arguments)` is asynchronous, receives tool context and a JSON argument string, and returns application tool content.

## `velmora.GuardrailFunctionOutput`

Import `GuardrailFunctionOutput` with `from velmora import GuardrailFunctionOutput`.

Construction accepts `output_info: Any`, `tripwire_triggered: bool`.

`output_info` carries application data and `tripwire_triggered: bool` carries the verdict; both are readable attributes. Construction accepts those fields positionally or by keyword.

## `velmora.HandoffOutputItem`

Import `HandoffOutputItem` with `from velmora import HandoffOutputItem`.

`.raw_item` is a dictionary with `call_id` and `output`.

`.source_agent` and `.target_agent` identify the source and destination; `.agent` identifies the item’s associated agent.

## `velmora.HostedMCPTool`

Import `HostedMCPTool` with `from velmora import HostedMCPTool`.

Construction accepts `on_approval_request: MCPToolApprovalFunction | None`, `tool_config: Mcp`.

`tool_config` is a mapping with `type="mcp"`, `server_label`, `server_url`, `require_approval`, `defer_loading`, and `allowed_callers` when supplied. `on_approval_request(request)` can be asynchronous, receives `.data.server_label` and `.data.name`, and returns `{"approve": <bool>}`.

## `velmora.ImageGenerationTool`

Import `ImageGenerationTool` with `from velmora import ImageGenerationTool`. Construction accepts `tool_config: dict` with `type="image_generation"` and `quality: str`.

## `velmora.InputGuardrail`

Import `InputGuardrail` with `from velmora import InputGuardrail`.

Construction accepts `guardrail_function: Callable[[RunContextWrapper[TContext], Agent[Any], str | list[dict]], MaybeAwaitable[GuardrailFunctionOutput]]`, `name: str | None`, `run_in_parallel: bool`.

`guardrail_function(context, agent, input)` returns `GuardrailFunctionOutput` synchronously or asynchronously. `input` is original text or an input-item list. `name` is a string; `run_in_parallel` is a boolean.

`get_name() -> str` supplies the guardrail name.

## `velmora.InputGuardrailTripwireTriggered`

`InputGuardrailTripwireTriggered` is a public guardrail rejection exception. `.guardrail_result` exposes `.guardrail` and `.output`; `.output` has `.output_info` and `.tripwire_triggered`.

## `velmora.MaxTurnsExceeded`

`MaxTurnsExceeded` is the public exception class carrying turn-limit failure.

## `velmora.Model`

Import `Model` with `from velmora import Model`.

A caller can subclass `Model`. Implement `async get_response(system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, *, previous_response_id, conversation_id, prompt) -> ModelResponse` and `stream_response` with the same arguments as an asynchronous iterator of Responses events. `system_instructions` is text or `None`; `input` is text or a list of Responses input dictionaries; `model_settings` is `ModelSettings`; `tools` and `handoffs` are lists of public declarations; `output_schema` is an output declaration or `None`; `tracing` is `ModelTracing`. Continuation fields are strings or `None`, and `prompt` is a prompt-template mapping or `None`.

`get_retry_advice(request) -> ModelRetryAdvice | None` is a synchronous application callback. Its request exposes `.error`, `.attempt`, `.stream`, `.previous_response_id`, and `.conversation_id`.

## `velmora.ModelBehaviorError`

`ModelBehaviorError` is the public exception class carrying invalid model output or requested work.

## `velmora.ModelProvider`

Import `ModelProvider` with `from velmora import ModelProvider`.

A caller can subclass `ModelProvider` and implement `get_model(model_name: str | None) -> Model`.

## `velmora.ModelRefusalError`

`ModelRefusalError` is the public exception class carrying model refusal.

`.refusal: str` carries the model-provided refusal text.

## `velmora.ModelResponse`

Import `ModelResponse` with `from velmora import ModelResponse`.

Construction accepts `output: list`, `response_id: str | None`, `usage: Usage`.

Readable fields are `output: list` of typed Responses output items, `usage: Usage`, `response_id: str | None`, and `raw_usage: dict | None` for the provider usage carrier.

## `velmora.ModelSettings`

Import `ModelSettings` with `from velmora import ModelSettings`.

Construction accepts `extra_args: dict[str, Any] | None`, `max_tokens: int | None`, `preserve_raw_usage: bool | None`, `reasoning: Reasoning | None`, `retry: ModelRetrySettings | None`, `store: bool | None`, `temperature: float | None`, `timeout: float | None`, `tool_choice: ToolChoice | None`, `top_p: float | None`, `verbosity: str | None`.

The construction fields are readable and writable attributes. `extra_args` is a provider-argument mapping; `reasoning` accepts an object with `effort`; `retry` accepts `ModelRetrySettings`. Timeout configuration failures use `pydantic.ValidationError`.

## `velmora.OpenAIChatCompletionsModel`

Import `OpenAIChatCompletionsModel` with `from velmora import OpenAIChatCompletionsModel`.

Construction accepts `model: str`, `openai_client: AsyncOpenAI`.

Supports `get_response` with the public `Model` argument surface and returns `ModelResponse`. Unsupported feature configuration uses `UserError`; model-output failures use `ModelBehaviorError` or `ModelRefusalError`.

## `velmora.OpenAIResponsesModel`

Import `OpenAIResponsesModel` with `from velmora import OpenAIResponsesModel`.

Construction accepts `model: str`, `openai_client: AsyncOpenAI`.

Supports `get_response` with the public `Model` argument surface and returns `ModelResponse`. Its configured client supplies HTTP endpoint and account settings.

## `velmora.OutputGuardrail`

Import `OutputGuardrail` with `from velmora import OutputGuardrail`.

Construction accepts `guardrail_function: Callable[[RunContextWrapper[TContext], Agent[Any], Any], MaybeAwaitable[GuardrailFunctionOutput]]`, `name: str | None`.

`guardrail_function(context, agent, output)` returns `GuardrailFunctionOutput` synchronously or asynchronously. `output` is the final application value. `get_name() -> str` supplies the check's name.

## `velmora.OutputGuardrailTripwireTriggered`

`OutputGuardrailTripwireTriggered` is a public guardrail rejection exception. `.guardrail_result` exposes `.guardrail` and `.output`; `.output` has `.output_info` and `.tripwire_triggered`.

`.guardrail_result.agent_output` is the candidate-output diagnostic carrier.

## `velmora.ProgrammaticToolCallingTool`

Import `ProgrammaticToolCallingTool` with `from velmora import ProgrammaticToolCallingTool`.

Construction: `ProgrammaticToolCallingTool()`.

## `velmora.RunConfig`

Import `RunConfig` with `from velmora import RunConfig`.

Construction accepts `call_model_input_filter: CallModelInputFilter | None`, `group_id: str | None`, `handoff_history_mapper: HandoffHistoryMapper | None`, `handoff_input_filter: HandoffInputFilter | None`, `input_guardrails: list[InputGuardrail[Any]] | None`, `model: str | Model | None`, `model_provider: ModelProvider`, `model_settings: ModelSettings | None`, `nest_handoff_history: bool`, `output_guardrails: list[OutputGuardrail[Any]] | None`, `sandbox: SandboxRunConfig | None`, `session_input_callback: SessionInputCallback | None`, `session_settings: SessionSettings | None`, `tool_error_formatter: ToolErrorFormatter | None`, `tool_name_collision_policy: ToolNameCollisionPolicy`, `tool_not_found_behavior: ToolNotFoundBehavior`, `trace_include_sensitive_data: bool`, `trace_metadata: dict[str, Any] | None`, `tracing_disabled: bool`, `workflow_name: str`.

`call_model_input_filter(data)` receives `.model_data.input` and returns `ModelInputData`, synchronously or asynchronously. `session_input_callback(history, new_input)` receives two input-item lists and returns an input-item list, synchronously or asynchronously. `handoff_input_filter` receives `HandoffInputData`; `handoff_history_mapper(items)` receives and returns an input-item list.

`tool_error_formatter(data)` returns replacement text. `tool_not_found_behavior` accepts `return_error_to_model`; `tool_name_collision_policy` accepts `error`.

## `velmora.RunContextWrapper`

Import `RunContextWrapper` with `from velmora import RunContextWrapper`.

Construction accepts `context: TContext`.

The wrapper supports type subscription, such as `RunContextWrapper[dict]`. `.context` holds the application context; `.usage` holds `Usage`.

`reject_tool(approval_item, *, rejection_message)` records a decision and returns `None`.

## `velmora.RunErrorHandlerResult`

Import `RunErrorHandlerResult` with `from velmora import RunErrorHandlerResult`.

Construction accepts `include_in_history: bool`.

Construction also accepts the replacement output as the leading positional argument `final_output`. Its readable fields are `final_output` and `include_in_history: bool`.

## `velmora.RunState`

Import `RunState` with `from velmora import RunState`.

`get_interruptions() -> list[ToolApprovalItem]` exposes pending decisions. `approve(approval_item, *, always_approve: bool)` and `reject(approval_item, *, always_reject: bool, rejection_message: str | None)` return `None`; keyword options can be omitted.

`add_input(input: str | list[dict]) -> None` submits additional user input. `pending_input` is a list of dictionaries with `role="user"` and `content: str`. `clear_pending_input() -> None` clears that carrier.

`to_json(*, strict_context, context_serializer) -> dict` returns JSON-compatible checkpoint data. The keyword options can be omitted. The public version carrier is `$schemaVersion`; checkpoint content is exchanged as the returned mapping. `context_serializer(context)` returns a JSON-compatible application value.

`await RunState.from_json(initial_agent, state_json, *, strict_context, context_override, context_deserializer) -> RunState` restores from a checkpoint mapping, accepting the supplied options independently. `context_override` is an application object; `context_deserializer(data)` returns one. Checkpoint, binding, and context-serialization configuration failures use `UserError`.

## `velmora.Runner`

Import `Runner` with `from velmora import Runner`.

`await Runner.run(starting_agent, input, *, context, max_turns, hooks, run_config, error_handlers, previous_response_id, auto_previous_response_id, conversation_id, session) -> RunResult` accepts the supplied keyword options independently. `starting_agent` is an agent. `input` is text, a list of Responses input-item dictionaries, or `RunState`. `context` is an application object or `RunContextWrapper`. `max_turns` is an integer or `None`. `run_config` accepts `RunConfig` or a mapping. Continuation identities are strings; automatic continuation is a boolean; `session` supplies the session methods.

`Runner.run_sync` has the same calling surface and returns `RunResult` synchronously. `Runner.run_streamed` has that calling surface and synchronously returns `RunResultStreaming`.

`error_handlers` is a mapping with `max_turns`, `model_refusal`, and `invalid_final_output` callback entries. Each callback receives an object with `.error` holding the public exception and returns replacement output, `RunErrorHandlerResult`, or `None`.

Public failure carriers are `MaxTurnsExceeded` for turn exhaustion, `ModelRefusalError` for refusal, `ModelBehaviorError` for invalid model work or output, `ModelTimeoutError` for model timeout, `ToolTimeoutError` for raised tool timeout, and `UserError` for invalid configuration or a propagated tool failure. A tool failure retains the application exception as `__cause__`. Guardrail failures use their corresponding tripwire exception classes; application callback and storage failures propagate as exceptions.

## `velmora.SQLiteSession`

Import `SQLiteSession` with `from velmora import SQLiteSession`.

Construction accepts `session_id: str`, `db_path: str | Path`, `session_settings: SessionSettings | dict[str, Any] | None`.

The session exposes `session_id: str`. Asynchronous methods are `get_items(limit=None) -> list[dict]`, `add_items(items: list[dict]) -> None`, `pop_item() -> dict | None`, and `clear_session() -> None`. Items are Responses input-item dictionaries. `limit` accepts an integer or `None`.

`db_path` accepts a string or path object; it can be omitted. `close() -> None` closes the session synchronously.

## `velmora.ShellCallOutcome`

Import `ShellCallOutcome` with `from velmora import ShellCallOutcome`.

Construction accepts `exit_code: int | None`, `type: str`.

`.type` is the status-kind string; completed command outcomes use `type="exit"` with `.exit_code: int`.

## `velmora.ShellCommandOutput`

Import `ShellCommandOutput` with `from velmora import ShellCommandOutput`.

Construction accepts `command: str | None`, `outcome: ShellCallOutcome`, `stderr: str`, `stdout: str`.

`.command`, `.stdout`, and `.stderr` are strings; `.outcome` is `ShellCallOutcome`.

## `velmora.ShellResult`

Import `ShellResult` with `from velmora import ShellResult`.

Construction accepts `output: list[ShellCommandOutput]`.

`.output` is a list of `ShellCommandOutput`.

## `velmora.ShellTool`

Import `ShellTool` with `from velmora import ShellTool`.

Construction accepts `name: str`, `allowed_callers: list[ToolCaller] | None`, `environment: ShellToolEnvironment | None`, `executor: ShellExecutor | None`, `needs_approval: bool | ShellApprovalFunction`, `on_approval: ShellOnApprovalFunction | None`.

The constructor additionally accepts `needs_approval` and `on_approval`. Local `executor(request)` is synchronous or asynchronous; `request.data.action` has `commands: list[str]`, `timeout_ms: int | None`, and `max_output_length: int | None`. It returns `ShellResult` or text. Approval callback `(context, item)` returns `{"approve": <bool>, "reason": <text>}`.

Hosted `environment` is a mapping with `type="container_reference"` and `container_id: str`, or `type="container_auto"` and a `skills` list. Skill entries use `type="skill_reference"`, `skill_id`, `version`, or `type="inline"`, `name`, `description`, `source`. Inline `source` has `type="base64"`, `media_type="application/zip"`, and `data` containing the encoded archive. Configuration failures use `UserError`; invalid model action arguments use `ModelBehaviorError`.

## `velmora.ToolApprovalItem`

Import `ToolApprovalItem` with `from velmora import ToolApprovalItem`.

Construction accepts `agent: Agent[Any]`, `raw_item: ToolApprovalRawItem`, `tool_name: str | None`.

`.agent` identifies the owner, `.tool_name` identifies the tool, and `.raw_item` carries the proposed provider call. Function calls expose `.call_id`, `.name`, and `.arguments`; custom calls expose `.call_id`, `.name`, and `.input`. Shell and patch raw items can be typed call objects or dictionaries with `call_id`. Hosted MCP requests expose `.id`, `.name`, and `.server_label`.

## `velmora.ToolCallOutputItem`

Import `ToolCallOutputItem` with `from velmora import ToolCallOutputItem`.

`.type` is `tool_call_output_item`; `.agent` is the originating agent; `.raw_item` is the output dictionary with `call_id` and `output`; `.output` is the tool result; `.custom_data` carries application metadata.

## `velmora.ToolGuardrailFunctionOutput`

Import `ToolGuardrailFunctionOutput` with `from velmora import ToolGuardrailFunctionOutput`.

Class methods `allow(output_info=None)`, `reject_content(message, output_info=None)`, and `raise_exception(output_info=None)` return tool verdicts. `output_info` is application data; `message` is replacement content.

## `velmora.ToolOutputFileContent`

Import `ToolOutputFileContent` with `from velmora import ToolOutputFileContent`.

Construction accepts `file_data: str | None`, `filename: str | None`.

The constructor content fields `file_data: str` and `filename: str` are readable attributes.

## `velmora.ToolOutputImage`

Import `ToolOutputImage` with `from velmora import ToolOutputImage`.

Construction accepts `detail: str | None`, `image_url: str | None`.

The constructor content fields `image_url: str` and `detail: str` are readable attributes.

## `velmora.ToolOutputText`

Import `ToolOutputText` with `from velmora import ToolOutputText`.

Construction accepts `text: str`.

The constructor content fields `text: str` are readable attributes.

## `velmora.ToolSearchTool`

Import `ToolSearchTool` with `from velmora import ToolSearchTool`.

Construction accepts `execution: str | None`.

`execution` is a string selection; model work exposes `tool_search_call` and `tool_search_output` in the raw output carrier. Configuration failures use `UserError`; unsupported requested work uses `ModelBehaviorError`.

## `velmora.ToolTimeoutError`

`ToolTimeoutError` is the public exception class carrying tool invocation timeout.

## `velmora.Usage`

Import `Usage` with `from velmora import Usage`.

Construction accepts `input_tokens: int`, `input_tokens_details: object`, `output_tokens: int`, `output_tokens_details: object`, `requests: int`, `total_tokens: int`.

The construction fields are readable attributes. `input_tokens_details` exposes `cached_tokens: int` and `cache_write_tokens: int`; `output_tokens_details` exposes `reasoning_tokens: int`. `request_usage_entries` is a list of records with `input_tokens`, `output_tokens`, `total_tokens`, `input_tokens_details`, and `output_tokens_details` in those same carriers. Token fields and `requests` are integers.

## `velmora.UserError`

`UserError` is the public exception class carrying application configuration or tool execution failure.

## `velmora.WebSearchTool`

Import `WebSearchTool` with `from velmora import WebSearchTool`.

Construction accepts `external_web_access: bool | None`, `filters: WebSearchToolFilters | None`, `image_settings: WebSearchToolImageSettings | None`, `search_content_types: list[str] | None`, `search_context_size: str`, `user_location: UserLocation | None`.

## `velmora.apply_diff`

Import `apply_diff` with `from velmora import apply_diff`.

`apply_diff(input: str, diff: str, mode: str) -> str` accepts the source text and diff positionally; `mode` can be omitted or supplied as `mode="create"`. The diff text uses `+` for additions, `-` for removals, a leading space for context, and `@@` for an update hunk. The return carrier is edited text; rejection raises `ValueError`.

## `velmora.function_tool`

Import `function_tool` with `from velmora import function_tool`.

Call: `function_tool(func: Callable | None, name_override: str | None, failure_error_function: ToolErrorFunction | None | object, is_enabled: bool | Callable[[RunContextWrapper[Any], AgentBase], MaybeAwaitable[bool]], needs_approval: bool | Callable[[RunContextWrapper[Any], dict[str, Any], str], Awaitable[bool]], tool_input_guardrails: list[ToolInputGuardrail[Any]] | None, tool_output_guardrails: list[ToolOutputGuardrail[Any]] | None, timeout: float | None, timeout_behavior: ToolTimeoutBehavior, timeout_error_function: ToolErrorFunction | None, defer_loading: bool, custom_data_extractor: FunctionToolCustomDataExtractor | None, allowed_callers: list[ToolCaller] | None)` returns `FunctionTool or decorator`.

The decorator can be used as `@function_tool`, `@function_tool(...)`, or `function_tool(callable, ...)`. The resulting `FunctionTool` exposes `name: str`, `description: str`, and `params_json_schema: dict` in JSON Schema form, including `properties`, `required`, and property `type`.

An application function accepts its declared arguments and can have a leading context parameter annotated `RunContextWrapper[...]` or `ToolContext`. `is_enabled` is a boolean or synchronous/asynchronous `(context, agent) -> bool` callback. Callable `needs_approval(context, arguments, call_id)` receives parsed argument mappings and a string correlation identity and returns a boolean or awaitable boolean.

`failure_error_function(context, error)` and `timeout_error_function(context, error)` accept the exception and return model-visible replacement content synchronously or asynchronously. `None` is accepted for `failure_error_function`. The raised-timeout selection is `timeout_behavior="raise_exception"`; the result carrier selection is `"error_as_result"`.

`custom_data_extractor(data)` receives `.output` and `.raw_item`, with `raw_item["call_id"]`, and returns application-only metadata. `allowed_callers` is a list of caller-permission strings; `tool_input_guardrails` and `tool_output_guardrails` are guardrail lists.

`tool` is the public decorator spelling for `function_tool`. It supports direct decorator use and keyword options `needs_approval`, `strict_mode`, and `failure_error_function`, returning `FunctionTool`.

Tool timeout configuration rejection raises `ValueError`.

## `velmora.handoff`

Import `handoff` with `from velmora import handoff`.

Call: `handoff(agent: Agent[TContext], tool_name_override: str | None, on_handoff: OnHandoffWithInput[THandoffInput] | OnHandoffWithoutInput | None, input_type: type[THandoffInput] | None, input_filter: Callable[[HandoffInputData], HandoffInputData] | None, is_enabled: bool | Callable[[RunContextWrapper[Any], Agent[TContext]], MaybeAwaitable[bool]])` returns `Handoff[TContext, Agent[TContext]]`.

Returns a `Handoff`. `input_type` is an application record type; `on_handoff(context, payload)` receives the declared value, or `on_handoff(context)` is used without a payload declaration. Callbacks may be asynchronous. `input_filter(data)` receives `HandoffInputData`. The additional keyword `nest_handoff_history: bool` is accepted.

## `velmora.output_guardrail`

Import `output_guardrail` with `from velmora import output_guardrail`.

Supports direct decorator use on a synchronous or asynchronous `(context, agent, output)` callable returning `GuardrailFunctionOutput`; returns an `OutputGuardrail`.

## `velmora.set_default_openai_client`

Import `set_default_openai_client` with `from velmora import set_default_openai_client`.

Call: `set_default_openai_client(client: AsyncOpenAI, use_for_tracing: bool)` returns `None`.

Accepts an `AsyncOpenAI` client or `None`, plus `use_for_tracing: bool`; returns `None`.

## `velmora.set_default_openai_key`

Import `set_default_openai_key` with `from velmora import set_default_openai_key`.

Call: `set_default_openai_key(key: str, use_for_tracing: bool)` returns `None`.

Accepts an API-key string or `None`, plus `use_for_tracing: bool`; returns `None`.

## `velmora.set_default_openai_responses_transport`

Import `set_default_openai_responses_transport` with `from velmora import set_default_openai_responses_transport`.

Call: `set_default_openai_responses_transport(transport: Literal['http', 'websocket'])` returns `None`.

The transport argument uses `http` or `websocket`; returns `None`.

## `velmora.tool_input_guardrail`

Import `tool_input_guardrail` with `from velmora import tool_input_guardrail`.

Supports direct decorator use on a synchronous or asynchronous tool-guardrail callback, returning the corresponding tool guardrail declaration.

## `velmora.tool_namespace`

Import `tool_namespace` with `from velmora import tool_namespace`.

Call: `tool_namespace(name: str, description: str | None, tools: list[FunctionTool])` returns `list[FunctionTool]`.

Returns a list accepted in `Agent.tools`. Each member is declared under the supplied `name: str`, `description: str`, and `tools: list[FunctionTool]`.

## `velmora.tool_output_guardrail`

Import `tool_output_guardrail` with `from velmora import tool_output_guardrail`.

Supports direct decorator use on a synchronous or asynchronous tool-guardrail callback, returning the corresponding tool guardrail declaration.

## `velmora.ToolsToFinalOutputResult`

Import `ToolsToFinalOutputResult` with `from velmora import ToolsToFinalOutputResult`.

Construction accepts `is_final_output: bool`, `final_output: Any | None`.

The constructor accepts positional `(is_final_output: bool, final_output)`; these are readable attributes.

## `velmora.decorators.tool`

Stated under `velmora.function_tool`.

## `velmora.ApplyPatchResult`

Import `ApplyPatchResult` with `from velmora import ApplyPatchResult`.

Construction accepts `output: str | None`, `status: str | None`.

`.status` uses `completed` or `failed`; `.output` carries editor result text.

## `velmora.AgentsException`

`AgentsException` is the public exception class carrying base SDK failure.

## `velmora.ModelTimeoutError`

`ModelTimeoutError` is the public exception class carrying model attempt timeout.

## `velmora.ToolInputGuardrailTripwireTriggered`

`ToolInputGuardrailTripwireTriggered` is a public tool-guardrail rejection exception. `.guardrail` identifies the check; `.output.output_info` holds callback information.

## `velmora.ToolOutputGuardrailTripwireTriggered`

`ToolOutputGuardrailTripwireTriggered` is a public tool-guardrail rejection exception. `.guardrail` identifies the check; `.output.output_info` holds callback information.

## `velmora.extensions.experimental.hosted_multi_agent.OpenAIHostedMultiAgentModel`

Import `OpenAIHostedMultiAgentModel` with `from velmora.extensions.experimental.hosted_multi_agent import OpenAIHostedMultiAgentModel`.

Construction accepts `model: str`, `openai_client: AsyncOpenAI | None`.

Supports the public `Model` argument surface. `await close() -> None` releases the live model connection. Unsupported configuration or overlapping use raises `UserError`.

## `velmora.extensions.experimental.hosted_multi_agent.get_hosted_agent_metadata`

Import `get_hosted_agent_metadata` with `from velmora.extensions.experimental.hosted_multi_agent import get_hosted_agent_metadata`.

Call: `get_hosted_agent_metadata(context: ToolContext)` returns `HostedAgentMetadata | None`.

Accepts `ToolContext` and returns metadata or `None`; metadata exposes `.agent_name: str` as the hosted caller identity.

## `velmora.extensions.memory.advanced_sqlite_session.AdvancedSQLiteSession`

Import `AdvancedSQLiteSession` with `from velmora.extensions.memory.advanced_sqlite_session import AdvancedSQLiteSession`.

Construction accepts `create_tables: bool`, `db_path: str | Path`, `session_id: str`.

The session exposes `session_id: str`. Asynchronous methods are `get_items(limit=None) -> list[dict]`, `add_items(items: list[dict]) -> None`, `pop_item() -> dict | None`, and `clear_session() -> None`. Items are Responses input-item dictionaries. `limit` accepts an integer or `None`.

`close() -> None` is synchronous. Asynchronous branch operations are `create_branch_from_turn(turn_number, branch_name) -> str`, `create_branch_from_content(search_term, branch_name) -> str`, `switch_to_branch(branch_id) -> None`, and `delete_branch(branch_id, force=<bool>) -> None`. A branch identity and name are strings; a turn number is an integer. Rejected branch mutations use `ValueError`.

`list_branches() -> list[dict]` exposes `branch_id: str`, `is_current: bool`, `message_count: int`, and `user_turns: int`.

`get_conversation_turns(branch_id=None)` and `find_turns_by_content(search_term, branch_id=None)` return lists of dictionaries with `turn: int` and `full_content` holding original user content. `get_conversation_by_turns(branch_id=None)` returns a mapping from integer turns to lists of message records with `type: str` and `tool_name: str | None`.

`get_tool_usage(branch_id=None)` returns a list of `(tool_name: str, call_count: int, user_turn: int)` tuples. `store_run_usage(result) -> None`, `get_turn_usage(user_turn_number, branch_id=None) -> dict`, and `get_session_usage(branch_id=None) -> dict` are asynchronous. Usage mappings expose `requests`, `input_tokens`, `output_tokens`, and `total_tokens` as integers; the missing-usage carrier is `{}`.

## `velmora.extensions.memory.async_sqlite_session.AsyncSQLiteSession`

Import `AsyncSQLiteSession` with `from velmora.extensions.memory.async_sqlite_session import AsyncSQLiteSession`.

Construction accepts `session_id: str`, `db_path: str | Path`.

The session exposes `session_id: str`. Asynchronous methods are `get_items(limit=None) -> list[dict]`, `add_items(items: list[dict]) -> None`, `pop_item() -> dict | None`, and `clear_session() -> None`. Items are Responses input-item dictionaries. `limit` accepts an integer or `None`.

Construction takes `(session_id, db_path)`. `await close() -> None` closes the session.

## `velmora.extensions.memory.encrypt_session.EncryptedSession`

Import `EncryptedSession` with `from velmora.extensions.memory.encrypt_session import EncryptedSession`.

Construction accepts `session_id: str`, `underlying_session: SessionABC`, `encryption_key: str`, `max_scan_items: int | None`, `ttl: int`.

The session exposes `session_id: str`. Asynchronous methods are `get_items(limit=None) -> list[dict]`, `add_items(items: list[dict]) -> None`, `pop_item() -> dict | None`, and `clear_session() -> None`. Items are Responses input-item dictionaries. `limit` accepts an integer or `None`.

The `ttl` construction argument is an integer duration in seconds. `underlying_session` is a session object. Backing-store records are JSON-compatible encrypted envelopes with `payload: str` as their opaque encoded carrier. Key configuration failures use `ValueError`; incomplete retrieval due to the configured scan budget uses `RuntimeError`.

## `velmora.extensions.memory.sqlalchemy_session.SQLAlchemySession`

Import `SQLAlchemySession` with `from velmora.extensions.memory.sqlalchemy_session import SQLAlchemySession`.

Construction accepts `session_id: str`, `create_tables: bool`, `engine: AsyncEngine`.

The session exposes `session_id: str`. Asynchronous methods are `get_items(limit=None) -> list[dict]`, `add_items(items: list[dict]) -> None`, `pop_item() -> dict | None`, and `clear_session() -> None`. Items are Responses input-item dictionaries. `limit` accepts an integer or `None`.

Construction takes `(session_id, *, engine, create_tables)`, with a caller-supplied asynchronous SQLAlchemy engine.

## `velmora.extensions.models.any_llm_model.AnyLLMModel`

Import `AnyLLMModel` with `from velmora.extensions.models.any_llm_model import AnyLLMModel`.

Construction accepts `model: str`, `api: Literal['responses', 'chat_completions'] | None`, `api_key: str | None`, `base_url: str | None`.

Construction accepts a provider-qualified model string as its leading argument. `await close() -> None` releases adapter resources. Model calls use the public `Model` argument surface.

## `velmora.extensions.models.litellm_model.LitellmModel`

Import `LitellmModel` with `from velmora.extensions.models.litellm_model import LitellmModel`.

Construction accepts `model: str`, `api_key: str | None`, `base_url: str | None`.

Construction accepts the model string positionally or by keyword. Model calls use the public `Model` argument surface.

## `velmora.extensions.visualization.draw_graph`

Import `draw_graph` with `from velmora.extensions.visualization import draw_graph`.

Call: `draw_graph(agent: Agent)` returns `graphviz.Source`.

Returns a graph object exposing `.source: str` as directed DOT text and `.save(filename=<path>)` as a file-writing entry. Saved text is UTF-8 DOT. Node identifiers are opaque; `label` carries display text. Directed edges carry endpoint identities and relationship style: handoffs use `solid` or an omitted style, tools use `dotted`, and MCP servers use `dashed`. Boundary-node labels are `__start__` and `__end__`.

## `velmora.Handoff`

Import `Handoff` with `from velmora import Handoff`.

Construction accepts `agent_name: str`, `input_json_schema: dict[str, Any]`, `on_invoke_handoff: Callable[[RunContextWrapper[Any], str], Awaitable[TAgent]]`, `tool_description: str`, `tool_name: str`.

`.tool_name: str` identifies the callable declaration. `on_invoke_handoff(context, arguments)` accepts context and a JSON string asynchronously and returns the destination agent. `agent_name` is the destination display name.

## `velmora.mcp.MCPServerManager`

Import `MCPServerManager` with `from velmora.mcp import MCPServerManager`.

Construction accepts `servers: Iterable[MCPServer]`, `strict: bool`.

An asynchronous context manager exposing `active_servers: list`, `failed_servers: list`, and `errors: dict` keyed by server object with exception values. `await reconnect(failed_only=<bool>) -> list` returns active server objects; the option can be omitted. Strict connection failures are raised exceptions.

## `velmora.mcp.MCPServerSse`

Import `MCPServerSse` with `from velmora.mcp import MCPServerSse`.

Construction takes `name: str` and `params` with `url: str`. Instances are asynchronous context managers. `await call_tool(tool_name: str, arguments: dict)` is the direct invocation entry. Disconnected calls raise `UserError`.

Agent model requests expose server tool declarations with `.name`. Tool results are correlated `function_call_output` mappings whose `output` contains a list of `input_text` blocks with `text`, or the application's replacement error text. Configured `failure_error_function(context, error)` returns replacement text; `None` selects a raised `UserError`.

## `velmora.mcp.MCPServerStdio`

Import `MCPServerStdio` with `from velmora.mcp import MCPServerStdio`.

Construction accepts `failure_error_function: ToolErrorFunction | None`, `max_list_pages: int | None`, `name: str | None`, `params: MCPServerStdioParams`, `require_approval: RequireApprovalSetting`, `tool_filter: ToolFilter`, `use_structured_content: bool`.

Instances are asynchronous context managers. Asynchronous calls are `call_tool(tool_name: str, arguments: dict)`, `list_tools()`, `list_prompts()`, `list_resources(cursor=None)`, `list_resource_templates(cursor=None)`, `read_resource(uri: str)`, and `get_prompt(name: str, arguments: dict)`.

`list_tools()` returns a list of declarations exposing `.name`. `list_prompts()` returns `.prompts` containing declarations with `.name`, and `.next_cursor: str | None`. Resource listings expose `.resources` or `.resource_templates`, whose entries have `.name` and `.description`, and `.next_cursor: str | None`. `read_resource()` returns `.contents` with `.uri` and `.text`; `get_prompt()` returns `.messages` with `.role` and `.content.type` and `.content.text`.

Construction accepts `tool_filter`, `use_structured_content`, `max_list_pages`, `require_approval`, `failure_error_function`. `tool_filter(context, tool)` can be asynchronous; context exposes `.agent` and `.run_context.context`, and tool exposes `.name`. `require_approval` accepts a policy string, a mapping from tool name to policy string, or `(context, agent, tool) -> bool`. Policy spellings are `always` and `never`.

Connection, disconnected-operation, and incomplete-listing failures use `UserError`. Prompt-service failures use `mcp.shared.exceptions.MCPError`.

`params` is a mapping with `command: str` and `args: list[str]`; `name` is a display string.

## `velmora.mcp.MCPServerStreamableHttp`

Import `MCPServerStreamableHttp` with `from velmora.mcp import MCPServerStreamableHttp`.

Construction takes `name: str` and `params` with `url: str`. Instances are asynchronous context managers. `await call_tool(tool_name: str, arguments: dict)` is the direct invocation entry. Disconnected calls raise `UserError`.

Agent model requests expose server tool declarations with `.name`. Tool results are correlated `function_call_output` mappings whose `output` contains a list of `input_text` blocks with `text`, or the application's replacement error text. Configured `failure_error_function(context, error)` returns replacement text; `None` selects a raised `UserError`.

## `velmora.mcp.create_static_tool_filter`

Import `create_static_tool_filter` with `from velmora.mcp import create_static_tool_filter`.

Call: `create_static_tool_filter(allowed_tool_names: list[str] | None, blocked_tool_names: list[str] | None)` returns `ToolFilterStatic | None`.

Returns the tool filter accepted by MCP server constructors; its two construction arguments are lists of tool-name strings.

## `velmora.OpenAIResponsesCompactionSession`

Import `OpenAIResponsesCompactionSession` with `from velmora import OpenAIResponsesCompactionSession`.

Construction accepts `session_id: str`, `underlying_session: Session`, `client: AsyncOpenAI | None`, `compaction_mode: OpenAIResponsesCompactionMode`, `should_trigger_compaction: Callable[[dict[str, Any]], bool] | None`.

The session exposes `session_id: str`. Asynchronous methods are `get_items(limit=None) -> list[dict]`, `add_items(items: list[dict]) -> None`, `pop_item() -> dict | None`, and `clear_session() -> None`. Items are Responses input-item dictionaries. `limit` accepts an integer or `None`.

`run_compaction({"force": <bool>})` is asynchronous. `should_trigger_compaction(data)` returns a boolean. `compaction_mode` accepts `input`.

## `velmora.SessionSettings`

Import `SessionSettings` with `from velmora import SessionSettings`.

Construction accepts `limit: int | None`.

`limit: int | None` is the history-retrieval setting.

## `velmora.ModelTracing`

Import `ModelTracing` with `from velmora import ModelTracing`.

`ModelTracing.DISABLED` is the disabled-tracing enum member supplied to model calls.

## `velmora.MultiProvider`

Import `MultiProvider` with `from velmora import MultiProvider`.

Construction accepts `openai_api_key: str | None`, `openai_base_url: str | None`, `openai_prefix_mode: MultiProviderOpenAIPrefixMode`, `provider_map: MultiProviderMap | None`, `unknown_prefix_mode: MultiProviderUnknownPrefixMode`.

`get_model(model_name: str | None) -> Model` accepts provider-qualified model names of the form `<prefix>/<model>`. The built-in route prefixes are `openai`, `litellm`, and `any-llm`. `openai_prefix_mode` and `unknown_prefix_mode` accept `model_id`. Route configuration failures use `UserError`; adapter dependency failures use `ImportError`.

## `velmora.models.multi_provider.MultiProviderMap`

Import `MultiProviderMap` with `from velmora.models.multi_provider import MultiProviderMap`.

Construction: `MultiProviderMap()`.

`add_provider(prefix: str, provider: ModelProvider) -> None` registers a route.

## `velmora.OpenAIProvider`

Import `OpenAIProvider` with `from velmora import OpenAIProvider`.

Construction accepts `api_key: str | None`, `base_url: str | None`, `openai_client: AsyncOpenAI | None`, `organization: str | None`, `project: str | None`, `strict_feature_validation: bool`, `use_responses: bool | None`, `use_responses_websocket: bool | None`, `websocket_base_url: str | None`.

`get_model(model_name: str | None) -> Model` supplies a concrete model. `await aclose() -> None` closes provider resources. Conflicting connection configuration uses `UserError`.

## `velmora.OpenAIResponsesWSModel`

Import `OpenAIResponsesWSModel` with `from velmora import OpenAIResponsesWSModel`.

Construction accepts `model: str`, `openai_client: AsyncOpenAI`.

`await close() -> None` releases the model connection. Model calls accept the public `Model` argument surface.

## `velmora.realtime.RealtimeAgent`

Import `RealtimeAgent` with `from velmora.realtime import RealtimeAgent`.

Construction accepts `handoffs: list[RealtimeAgent[Any] | Handoff[TContext, RealtimeAgent[Any]]]`, `instructions: str | Callable[[RunContextWrapper[TContext], RealtimeAgent[TContext]], MaybeAwaitable[str]] | None`, `name: str`, `output_guardrails: list[OutputGuardrail[TContext]]`, `tools: list[Tool]`.

Construction accepts `name: str`, `instructions`, `tools: list`, `handoffs: list`, and `output_guardrails: list`. An unsupported `output_type` declaration fails with `TypeError` or `UserError`.

## `velmora.realtime.RealtimeRunner`

Import `RealtimeRunner` with `from velmora.realtime import RealtimeRunner`.

Construction accepts `starting_agent: RealtimeAgent`, `config: RealtimeRunConfig | None`, `model: RealtimeModel | None`.

`await run(*, model_config: dict) -> RealtimeSession` opens a session. `config` accepts `tracing_disabled: bool`, `async_tool_calls: bool`, and `guardrails_settings` containing `debounce_text_length: int`. `model_config` accepts `url: str`, `headers: dict`, `initial_model_settings: dict`, `playback_tracker`, and `call_id: str`.

`initial_model_settings` accepts `model_name`, `voice`, `input_audio_format`, `output_audio_format`, and `turn_detection`. Audio-format selection spellings include `pcm16`, `g711_ulaw`, and `g711_alaw`; `turn_detection` is a mapping or `None`.

## `velmora.realtime.realtime_handoff`

Import `realtime_handoff` with `from velmora.realtime import realtime_handoff`.

Call: `realtime_handoff(agent: RealtimeAgent[TContext], tool_name_override: str | None, on_handoff: OnHandoffWithInput[THandoffInput] | OnHandoffWithoutInput | None, input_type: type[THandoffInput] | None)` returns `Handoff[TContext, RealtimeAgent[TContext]]`.

Returns a handoff accepted by `RealtimeAgent.handoffs`. `input_type` is an application record type; `on_handoff(context, payload)` receives the declared value synchronously or asynchronously. `.tool_name` is the callable identity. Invalid model arguments use `ModelBehaviorError`; an unsupported `input_filter` argument uses `TypeError`.

## `velmora.realtime.model.RealtimePlaybackTracker`

Import `RealtimePlaybackTracker` with `from velmora.realtime.model import RealtimePlaybackTracker`.

Construction: `RealtimePlaybackTracker()`.

`on_play_ms(item_id: str, content_index: int, milliseconds: float) -> None` supplies playback progress.

## `velmora.realtime.model_inputs.RealtimeModelSendRawMessage`

Import `RealtimeModelSendRawMessage` with `from velmora.realtime.model_inputs import RealtimeModelSendRawMessage`.

Construction accepts `message: RealtimeModelRawClientMessage`.

`message` is a protocol-message mapping with `type` and message fields.

## `velmora.realtime.openai_realtime.OpenAIRealtimeSIPModel`

Import `OpenAIRealtimeSIPModel` with `from velmora.realtime.openai_realtime import OpenAIRealtimeSIPModel`.

Construction: `OpenAIRealtimeSIPModel()`.

Construction takes no required arguments. Connection configuration supplies `call_id` as the existing call identity and `url` as the endpoint.

## `velmora.realtime.openai_realtime.OpenAIRealtimeWebSocketModel`

Import `OpenAIRealtimeWebSocketModel` with `from velmora.realtime.openai_realtime import OpenAIRealtimeWebSocketModel`.

Construction: `OpenAIRealtimeWebSocketModel()`.

Construction takes no required arguments. `await send_event(event) -> None` accepts `RealtimeModelSendRawMessage`. Connection settings are supplied through `RealtimeRunner.run(model_config=...)`.

## `velmora.ModelRetryAdvice`

Import `ModelRetryAdvice` with `from velmora import ModelRetryAdvice`.

Construction accepts `normalized: ModelRetryNormalizedError | None`, `replay_safety: str | None`, `retry_after: float | None`, `suggested: bool | None`.

The constructor fields are readable attributes: `suggested: bool | None`, `retry_after: float | None` in seconds, `replay_safety: str | None`, and `normalized: ModelRetryNormalizedError | None`. Replay classification uses `safe` and `unsafe`.

## `velmora.ModelRetryNormalizedError`

Import `ModelRetryNormalizedError` with `from velmora import ModelRetryNormalizedError`.

Construction accepts `status_code: int | None`.

`status_code: int | None` carries the provider HTTP status.

## `velmora.ModelRetrySettings`

Import `ModelRetrySettings` with `from velmora import ModelRetrySettings`.

Construction accepts `backoff: ModelRetryBackoffInput | None`, `max_retries: int | None`, `policy: Callable[..., Any] | None`.

`backoff` accepts a mapping with `initial_delay` in seconds and `jitter: bool`. `policy(context)` is a synchronous/asynchronous callback returning `bool` or `RetryDecision`.

## `velmora.RetryDecision`

Import `RetryDecision` with `from velmora import RetryDecision`.

Construction accepts `approve_unsafe_replay: bool`, `retry: bool`.

`retry: bool` and `approve_unsafe_replay: bool` are decision fields.

## `velmora.retry_policies`

Import `retry_policies` from `velmora.retry`. It exposes `never()`, `provider_suggested()`, `network_error()`, `retry_after()`, `http_status(statuses)`, `any(*policies)`, and `all(*policies)`. `statuses` is an iterable of integer HTTP statuses. Each method returns a retry-policy callable accepted by `ModelRetrySettings`.

## `velmora.run.ModelInputData`

Import `ModelInputData` with `from velmora.run import ModelInputData`.

Construction accepts `input: list[dict]`, `instructions: str | None`.

The constructor fields `input` and `instructions` are readable attributes: a Responses input-item list and instruction text or `None`, respectively.

## `velmora.sandbox.LocalSnapshotSpec`

Import `LocalSnapshotSpec` with `from velmora.sandbox import LocalSnapshotSpec`.

Construction accepts `base_path: Path`.

`base_path` accepts a path object naming the snapshot storage directory.

## `velmora.sandbox.Manifest`

Import `Manifest` with `from velmora.sandbox import Manifest`.

Construction accepts `entries: dict[str | Path, BaseEntry]`, `environment: Environment`, `extra_path_grants: tuple[SandboxPathGrant, ...]`, `root: str`, `users: list[{name: str}]`, `groups: list[{name: str, users: list[{name: str}]}]`.

Readable fields are `root: str`, `entries: dict`, `environment`, and `extra_path_grants`. Entry keys are destination path strings or path objects; values are entry declarations.

`with_in_container_mount_credential_exposure_acknowledged(*mount_paths)` and `with_in_container_mount_broad_credential_exposure_acknowledged(*mount_paths)` accept mount-path strings and return a `Manifest`.

`model_dump_json() -> str` supplies manifest JSON; `Manifest.model_validate_json(text) -> Manifest` accepts it. `model_copy(update={"root": <path>}) -> Manifest` accepts a replacement root; `model_copy(update={"entries": <entry mapping>}) -> Manifest` accepts a replacement entry mapping.

## `velmora.sandbox.MemoryGenerateConfig`

Import `MemoryGenerateConfig` with `from velmora.sandbox import MemoryGenerateConfig`.

Construction accepts `phase_one_model: str | Model`, `phase_two_model: str | Model`.

`phase_one_model` and `phase_two_model` accept model names or caller-supplied `Model` objects. The extraction response text is JSON with `rollout_slug: str`, `rollout_summary: str`, and `raw_memory: str`.

## `velmora.sandbox.MemoryLayoutConfig`

Import `MemoryLayoutConfig` with `from velmora.sandbox import MemoryLayoutConfig`.

Construction accepts `memories_dir: str`, `sessions_dir: str`.

`memories_dir` and `sessions_dir` name workspace-relative artifact directories.

## `velmora.sandbox.MemoryReadConfig`

Import `MemoryReadConfig` with `from velmora.sandbox import MemoryReadConfig`.

Construction accepts `live_update: bool`.

`live_update` is a boolean.

## `velmora.sandbox.Permissions`

Import `Permissions` with `from velmora.sandbox import Permissions`.

Construction accepts `group: int`, `other: int`, `owner: int`.

Construction fields `owner`, `group`, and `other` accept integer access masks.

## `velmora.sandbox.SandboxAgent`

Import `SandboxAgent` with `from velmora.sandbox import SandboxAgent`.

Construction accepts `capabilities: Sequence[Capability]`, `default_manifest: Manifest | None`, `model: str | Model | None`, `name: str`, `tools: list[Tool]`.

Accepts the agent construction fields `name`, `model`, and `tools`, plus `default_manifest: Manifest` and `capabilities: list`. It is passed to `Runner` through the agent entry.

## `velmora.sandbox.SandboxError`

`SandboxError` is the public exception class carrying sandbox operation failure.

## `velmora.sandbox.SandboxPathGrant`

Import `SandboxPathGrant` with `from velmora.sandbox import SandboxPathGrant`.

Construction accepts `host_path: str | None`, `path: str`, `read_only: bool`.

`path` and `host_path` are path strings, and `read_only` is a boolean. The optional host path and access flag can be omitted.

## `velmora.sandbox.SandboxRunConfig`

Import `SandboxRunConfig` with `from velmora.sandbox import SandboxRunConfig`.

Construction accepts `client: BaseSandboxClient[Any] | None`, `options: DockerSandboxClientOptions | None`, `cwd: str | PurePath | None`, `manifest: Manifest | None`, `session: BaseSandboxSession | None`, `session_state: SandboxSessionState | None`, `snapshot: SnapshotSpec | SnapshotBase | None`.

`cwd` is a workspace working-directory selection string or path. Selection syntax failures use `ValueError`; selected-directory access failures use `UserError`.

## `velmora.sandbox.capabilities.Compaction`

Import `Compaction` with `from velmora.sandbox.capabilities import Compaction`.

Construction: `Compaction()`.

`Compaction()` is accepted in the sandbox capability list.

## `velmora.sandbox.capabilities.Filesystem`

Import `Filesystem` with `from velmora.sandbox.capabilities import Filesystem`.

Construction: `Filesystem()`.

`Filesystem()` is accepted in the sandbox capability list.

## `velmora.sandbox.capabilities.LocalDirLazySkillSource`

Import `LocalDirLazySkillSource` with `from velmora.sandbox.capabilities import LocalDirLazySkillSource`.

Construction accepts `source: LocalDir`.

`source` is a `LocalDir` declaration.

## `velmora.sandbox.capabilities.Memory`

Import `Memory` with `from velmora.sandbox.capabilities import Memory`.

Construction accepts `generate: MemoryGenerateConfig | None`, `layout: MemoryLayoutConfig`, `read: MemoryReadConfig | None`.

`read` accepts `MemoryReadConfig`, a mapping with `live_update: bool`, or `None`; `generate` accepts `MemoryGenerateConfig` or `None`; `layout` is `MemoryLayoutConfig`. `.layout.memories_dir` and `.layout.sessions_dir` are readable strings.

## `velmora.sandbox.capabilities.Shell`

Import `Shell` with `from velmora.sandbox.capabilities import Shell`.

Construction accepts `configure_tools: ShellToolConfigurator | None`.

`configure_tools(tools)` receives a tool-set object exposing `.exec_command.session` as the sandbox session.

## `velmora.sandbox.capabilities.Skills`

Import `Skills` with `from velmora.sandbox.capabilities import Skills`.

Construction accepts `from_: BaseEntry | None`, `lazy_from: LazySkillSource | None`.

`from_` accepts `LocalDir` or `GitRepo`; `lazy_from` accepts `LocalDirLazySkillSource`. Skill selection is exposed as the function tool `load_skill` with JSON arguments `{"skill_name": <str>}`. Configuration failures use `UserError`; local source read failures use `LocalDirReadError`.

## `velmora.sandbox.entries.AzureBlobMount`

Import `AzureBlobMount` with `from velmora.sandbox.entries import AzureBlobMount`.

Construction accepts `account: str`, `account_key: str | None`, `container: str`, `endpoint: str | None`, `read_only: bool`, `mount_strategy: MountStrategy`.

`mount_strategy` accepts a mount strategy declaration. Rejected mount declarations raise `MountConfigError`.

The in-container construction form accepts `mount_strategy: InContainerMountStrategy` with `pattern: FuseMountPattern`.

## `velmora.sandbox.entries.Dir`

Import `Dir` with `from velmora.sandbox.entries import Dir`.

Construction accepts `children: dict[str | Path, BaseEntry]`.

`children` is a mapping from relative paths to entry declarations.

## `velmora.sandbox.entries.File`

Import `File` with `from velmora.sandbox.entries import File`.

Construction accepts `content: bytes`, `ephemeral: bool`, `permissions: Permissions`.

`content` accepts file bytes; `ephemeral` is a boolean; `permissions` is `Permissions`.

## `velmora.sandbox.entries.FuseMountPattern`

Import `FuseMountPattern` with `from velmora.sandbox.entries import FuseMountPattern`.

Construction: `FuseMountPattern()`.

## `velmora.sandbox.entries.GitRepo`

Import `GitRepo` with `from velmora.sandbox.entries import GitRepo`.

Construction accepts `host: str`, `ref: str`, `repo: str`.

`host`, `repo`, and `ref` are strings naming the repository host, repository location, and revision. `repo` also accepts a local repository path.

## `velmora.sandbox.entries.InContainerMountStrategy`

Import `InContainerMountStrategy` with `from velmora.sandbox.entries import InContainerMountStrategy`.

Construction accepts `pattern: MountPattern`.

`pattern` accepts `FuseMountPattern` or `MountpointMountPattern`.

## `velmora.sandbox.entries.LocalDir`

Import `LocalDir` with `from velmora.sandbox.entries import LocalDir`.

Construction accepts `src: Path | None`.

`src` accepts a local path string or path object.

## `velmora.sandbox.entries.LocalFile`

Import `LocalFile` with `from velmora.sandbox.entries import LocalFile`.

Construction accepts `src: Path`.

`src` accepts a local path string or path object.

## `velmora.sandbox.entries.MountpointMountPattern`

Import `MountpointMountPattern` with `from velmora.sandbox.entries import MountpointMountPattern`.

Construction: `MountpointMountPattern()`.

## `velmora.sandbox.entries.S3Mount`

Import `S3Mount` with `from velmora.sandbox.entries import S3Mount`.

Construction accepts `access_key_id: str | None`, `bucket: str`, `endpoint_url: str | None`, `read_only: bool`, `mount_strategy: MountStrategy`, `secret_access_key: str | None`.

`mount_strategy` accepts a mount strategy declaration. Rejected mount declarations raise `MountConfigError`.

`bucket` is the storage identity string; `access_key_id` and `secret_access_key` are credential strings or `None`. `.bucket` is readable. `model_copy(update={"bucket": <str>})` returns a declaration.

The in-container construction form accepts `mount_strategy: InContainerMountStrategy` with `pattern: MountpointMountPattern`.

## `velmora.sandbox.errors.LocalDirReadError`

`LocalDirReadError` is the public exception class carrying local directory source read failure.

## `velmora.sandbox.errors.MountConfigError`

`MountConfigError` is the public exception class carrying mount configuration failure.

## `velmora.sandbox.errors.WorkspaceReadNotFoundError`

`WorkspaceReadNotFoundError` is the public exception class carrying missing workspace file.

## `velmora.sandbox.manifest.Environment`

Import `Environment` with `from velmora.sandbox.manifest import Environment`.

Construction accepts `value: dict[str, str]`.

`value` is a mapping from environment-variable name strings to value strings.

## `velmora.sandbox.sandboxes.docker.DockerSandboxClient`

Import `DockerSandboxClient` with `from velmora.sandbox.sandboxes.docker import DockerSandboxClient`.

Construction: `DockerSandboxClient(client)`.

Construction takes the caller's Docker client. `await create(manifest=<Manifest>, options=<DockerSandboxClientOptions>)` supplies a session. Connection failure uses `requests.exceptions.ConnectionError`.

## `velmora.sandbox.sandboxes.docker.DockerSandboxClientOptions`

Import `DockerSandboxClientOptions` with `from velmora.sandbox.sandboxes.docker import DockerSandboxClientOptions`.

Construction accepts `exposed_ports: tuple[int, ...]`, `image: str`, `network_mode: Literal['none'] | None`.

`image` is an image-name string, `network_mode` is a networking selection string, and `exposed_ports` is a tuple of integers. The disabled-network spelling is `none`. Rejected option combinations raise `ValueError`.

## `velmora.sandbox.sandboxes.unix_local.UnixLocalSandboxClient`

Import `UnixLocalSandboxClient` with `from velmora.sandbox.sandboxes.unix_local import UnixLocalSandboxClient`.

Construction accepts `dependencies: Dependencies | None`, `host_environment_allowlist: Collection[str] | None`, `inherit_host_environment: bool`.

`backend_id: str` identifies the backend. Asynchronous calls are `create(*, manifest, snapshot) -> SandboxSession`, `resume(state) -> SandboxSession`, and `delete(session)`. `snapshot` is optional and accepts a snapshot specification or snapshot object.

`serialize_session_state(state) -> dict` and `deserialize_session_state(payload: dict) -> state` exchange JSON-compatible connection state. Its public `manifest.entries` mapping contains entry declarations and their credential carriers `access_key_id`, `secret_access_key`, and `account_key`, whose redacted form is `None`.

Provisioning or file-access rejection uses `SandboxError` or its public subclasses. Rejected account-declaration or path-remapping configuration uses `ValueError`; invalid saved authority uses `ValueError` or `MountConfigError`.

An application subclass may override `async create(*, manifest, snapshot=None, options=None) -> SandboxSession`; it can be supplied through `SandboxRunConfig.client`. The base creation method accepts these same arguments.

## `velmora.sandbox.session.dependencies.Dependencies`

Import `Dependencies` with `from velmora.sandbox.session.dependencies import Dependencies`.

`Dependencies.with_values(values: dict) -> Dependencies` accepts dependency-name strings mapped to application objects.

## `velmora.sandbox.snapshot.LocalSnapshotSpec`

Import `LocalSnapshotSpec` with `from velmora.sandbox import LocalSnapshotSpec`.

Construction accepts `base_path: Path`.

`base_path` accepts a path object naming the snapshot storage directory.

## `velmora.sandbox.snapshot.RemoteSnapshotSpec`

Import `RemoteSnapshotSpec` with `from velmora.sandbox.snapshot import RemoteSnapshotSpec`.

Construction accepts `client_dependency_key: str`.

`client_dependency_key` is a string identifying application-supplied snapshot storage. The supplied storage implements synchronous `upload(identity: str, data: IOBase)`, `download(identity: str) -> IOBase`, and `exists(identity: str) -> bool`.

## `velmora.tool_context.ToolContext`

Import `ToolContext` with `from velmora.tool_context import ToolContext`.

Tool callbacks receive `.context` for application state, `.tool_call_id: str` for invocation correlation and `.tool_arguments: str` for JSON arguments. `ToolContext` can be used as a function-tool context annotation.

## `velmora.ToolInputGuardrail`

Import `ToolInputGuardrail` with `from velmora import ToolInputGuardrail`.

Construction accepts `guardrail_function: Callable[[ToolInputGuardrailData], MaybeAwaitable[ToolGuardrailFunctionOutput]]`, `name: str | None`.

Construction takes a leading callback and optional `name` string. The callback receives tool guardrail data and returns `ToolGuardrailFunctionOutput`, synchronously or asynchronously.

The callback data exposes `.context.tool_arguments` as the JSON argument string.

## `velmora.ToolOutputGuardrail`

Import `ToolOutputGuardrail` with `from velmora import ToolOutputGuardrail`.

Construction accepts `guardrail_function: Callable[[ToolOutputGuardrailData], MaybeAwaitable[ToolGuardrailFunctionOutput]]`, `name: str | None`.

Construction takes a leading callback and optional `name` string. The callback receives tool guardrail data and returns `ToolGuardrailFunctionOutput`, synchronously or asynchronously.

The callback data exposes `.output` as the actual tool output. An MCP text block in this carrier is a mapping with `type="text"` and `text: str`.

## `velmora.TracingProcessor`

Import `TracingProcessor` with `from velmora import TracingProcessor`.

Subclassable synchronous observer with `on_trace_start(trace)`, `on_trace_end(trace)`, `on_span_start(span)`, `on_span_end(span)`, `shutdown()`, and `force_flush()`. Trace and span arguments expose `export()` returning their public mapping.

## `velmora.add_trace_processor`

Import `add_trace_processor` with `from velmora import add_trace_processor`.

Call: `add_trace_processor(processor: TracingProcessor)` returns `None`.

This synchronous function returns `None`.

## `velmora.custom_span`

Import `custom_span` with `from velmora import custom_span`.

Call: `custom_span(name: str, data: dict[str, Any] | None)` returns `Span[CustomSpanData]`.

A synchronous context manager returning a span with `.span_id: str` and `.export() -> dict`. Span export has `object="trace.span"`, `id: str`, `trace_id: str`, `parent_id: str | None`, `started_at` and `ended_at` as ISO timestamp strings, `error: dict | None`, and `span_data: dict`.

`span_data` uses `type` as its discriminator: `custom` has `name` and `data`; `agent` has `name`; `function` has `name`, `input`, and `output`; `generation` has `model`, `input`, and `output`; `handoff` has `from_agent` and `to_agent`; `guardrail` has `name` and `triggered`. Content carriers are text, JSON-compatible content, or `None`. Error mappings expose `message: str` and `data: dict`.

Speech records use `type="transcription"` with `input.data` carrying base64 PCM, `output` carrying text or an empty/null value, and `model_config.prompt`; `type="speech"` with text `input`, base64 PCM in `output.data`, and `model_config.instructions`; and `type="speech_group"` with text or empty/null `input`. Excluded audio uses an empty data string; excluded model configuration content uses `None`.

## `velmora.flush_traces`

Import `flush_traces` with `from velmora import flush_traces`.

Call: `flush_traces()` returns `None`.

This synchronous function returns `None`.

## `velmora.tracing.get_trace_provider`

Import `get_trace_provider` with `from velmora.tracing import get_trace_provider`.

Call: `get_trace_provider()` returns `TraceProvider`.

Returns the currently configured trace provider.

## `velmora.set_trace_processors`

Import `set_trace_processors` with `from velmora import set_trace_processors`.

Call: `set_trace_processors(processors: list[TracingProcessor])` returns `None`.

This synchronous function returns `None`.

## `velmora.set_trace_provider`

Import `set_trace_provider` with `from velmora import set_trace_provider`.

Call: `set_trace_provider(provider: TraceProvider)` returns `None`.

This synchronous function returns `None`.

## `velmora.set_tracing_disabled`

Import `set_tracing_disabled` with `from velmora import set_tracing_disabled`.

Call: `set_tracing_disabled(disabled: bool)` returns `None`.

This synchronous function returns `None`.

## `velmora.trace`

Import `trace` with `from velmora import trace`.

Call: `trace(workflow_name: str, group_id: str | None, metadata: dict[str, Any] | None)` returns `Trace`.

A synchronous context manager returning a trace with `.trace_id: str` and `.export() -> dict`. The export has `object="trace"`, `id: str`, `workflow_name: str`, `group_id: str | None`, and `metadata: dict | None`.

## `velmora.tracing.processor_interface.TracingExporter`

Import `TracingExporter` with `from velmora.tracing.processor_interface import TracingExporter`.

Subclassable exporter with `export(items)` receiving a sequence of trace and span objects, each exposing `export() -> dict`.

## `velmora.tracing.processors.BatchTraceProcessor`

Import `BatchTraceProcessor` with `from velmora.tracing.processors import BatchTraceProcessor`.

Construction accepts `exporter: TracingExporter`, `schedule_delay: float`.

Construction takes an exporter as its first argument and `schedule_delay` in seconds. `shutdown()` is synchronous.

## `velmora.tracing.provider.DefaultTraceProvider`

Import `DefaultTraceProvider` with `from velmora.tracing.provider import DefaultTraceProvider`.

Construction: `DefaultTraceProvider()`.

`set_processors(processors)` accepts a list of processors. `shutdown()` is synchronous.

## `velmora.voice.AudioInput`

Import `AudioInput` with `from velmora.voice import AudioInput`.

Construction accepts `buffer: npt.NDArray[np.int16 | np.float32]`.

Construction accepts a NumPy sample array as its positional `buffer` argument.

## `velmora.voice.STTModel`

Import `STTModel` with `from velmora.voice import STTModel`.

Subclassable speech-recognition interface. `model_name: str` is a property. `await transcribe(input, settings, trace_include_sensitive_data, trace_include_sensitive_audio_data) -> str` accepts `AudioInput` and `STTModelSettings`. `await create_session(input, settings, trace_include_sensitive_data, trace_include_sensitive_audio_data)` accepts `StreamedAudioInput` and returns `StreamedTranscriptionSession`.

## `velmora.voice.STTModelSettings`

Import `STTModelSettings` with `from velmora.voice import STTModelSettings`.

Construction accepts `keywords: list[str] | None`, `language: str | None`, `languages: list[str] | None`, `prompt: str | None`.

`language` and `prompt` are strings or `None`; `languages` and `keywords` are lists of strings or `None`.

## `velmora.voice.SingleAgentVoiceWorkflow`

Import `SingleAgentVoiceWorkflow` with `from velmora.voice import SingleAgentVoiceWorkflow`.

Construction accepts `agent: Agent[TContext]`, `callbacks: SingleAgentWorkflowCallbacks | None`, `context: TContext | None`.

Construction takes an agent and an optional callbacks object positionally, plus keyword `context`. `run(transcription: str)` yields text asynchronously. The callbacks object provides `on_run(workflow, transcription)`.

## `velmora.voice.StreamedAudioInput`

Import `StreamedAudioInput` with `from velmora.voice import StreamedAudioInput`.

Construction: `StreamedAudioInput()`.

Construction takes no required arguments. `await add_audio(audio)` accepts a NumPy sample array or `None`, the input-end marker.

## `velmora.voice.StreamedTranscriptionSession`

Import `StreamedTranscriptionSession` with `from velmora.voice import StreamedTranscriptionSession`.

Subclassable transcription session with `transcribe_turns()` as an asynchronous iterator of recognized strings, and `await close() -> None`.

## `velmora.voice.TTSModel`

Import `TTSModel` with `from velmora.voice import TTSModel`.

Subclassable synthesis interface. `model_name: str` is a property; `run(text: str, settings: TTSModelSettings)` is an asynchronous iterator of PCM byte chunks.

## `velmora.voice.TTSModelSettings`

Import `TTSModelSettings` with `from velmora.voice import TTSModelSettings`.

Construction accepts `buffer_size: int`, `dtype: npt.DTypeLike`, `instructions: str`, `voice: TTSVoice | None`.

`voice` accepts a string or `{"id": <voice identity>}`; `dtype` accepts NumPy dtype-like values; `instructions` is text and `buffer_size` is an integer. Audio configuration rejection uses `UserError`.

## `velmora.voice.VoiceModelProvider`

Import `VoiceModelProvider` with `from velmora.voice import VoiceModelProvider`.

Subclassable provider implementing synchronous `get_stt_model(model_name: str | None) -> STTModel` and `get_tts_model(model_name: str | None) -> TTSModel`.

## `velmora.voice.VoicePipeline`

Import `VoicePipeline` with `from velmora.voice import VoicePipeline`.

Construction accepts `config: VoicePipelineConfig | dict[str, Any] | None`, `stt_model: STTModel | str | None`, `tts_model: TTSModel | str | None`, `workflow: VoiceWorkflowBase`.

`await run(audio_input: AudioInput | StreamedAudioInput)` returns an audio result exposing `stream()` as an asynchronous event iterator. `stt_model` and `tts_model` accept model names, supplied model objects, or omission. `config` accepts `VoicePipelineConfig`.

Audio events have `type="voice_stream_event_audio"` and `.data` as a NumPy array of playback samples, in a one-dimensional or single-column carrier. Lifecycle events have `type="voice_stream_event_lifecycle"` and `.event` using `turn_started`, `turn_ended`, or `session_ended`. The event iterator is the exception-delivery channel. Unsupported audio configuration uses `UserError`.

## `velmora.voice.VoicePipelineConfig`

Import `VoicePipelineConfig` with `from velmora.voice import VoicePipelineConfig`.

Construction accepts `model_provider: VoiceModelProvider`, `stt_settings: STTModelSettings`, `trace_include_sensitive_audio_data: bool`, `trace_include_sensitive_data: bool`, `tracing_disabled: bool`, `tts_settings: TTSModelSettings`.

The constructor fields are readable settings: `model_provider` supplies a voice provider, `stt_settings` and `tts_settings` supply model settings, and `tracing_disabled`, `trace_include_sensitive_data`, and `trace_include_sensitive_audio_data` are booleans.

## `velmora.voice.VoiceWorkflowBase`

Import `VoiceWorkflowBase` with `from velmora.voice import VoiceWorkflowBase`.

Subclassable workflow interface: `run(transcription: str)` is an asynchronous iterator yielding speech text strings.

## `velmora.voice.models.openai_model_provider.OpenAIVoiceModelProvider`

Import `OpenAIVoiceModelProvider` with `from velmora.voice.models.openai_model_provider import OpenAIVoiceModelProvider`.

Construction accepts `openai_client: AsyncOpenAI | None`.

`get_stt_model(model_name: str | None) -> STTModel` and `get_tts_model(model_name: str | None) -> TTSModel` select speech models.

## `velmora`

The Python module `velmora` exposes `Agent`, `AgentOutputSchema`, `ApplyPatchTool`, `CodeInterpreterTool`, `Computer`, `ComputerTool`, `CustomTool`, `FileSearchTool`, `FunctionTool`, `GuardrailFunctionOutput`, `HandoffOutputItem`, `HostedMCPTool`, `ImageGenerationTool`, `InputGuardrail`, `InputGuardrailTripwireTriggered`, `MaxTurnsExceeded`, `Model`, `ModelBehaviorError`, `ModelProvider`, `ModelRefusalError`, `ModelResponse`, `ModelSettings`, `OpenAIChatCompletionsModel`, `OpenAIResponsesModel`, `OutputGuardrail`, `OutputGuardrailTripwireTriggered`, `ProgrammaticToolCallingTool`, `RunConfig`, `RunContextWrapper`, `RunErrorHandlerResult`, `RunState`, `Runner`, `SQLiteSession`, `ShellCallOutcome`, `ShellCommandOutput`, `ShellResult`, `ShellTool`, `ToolApprovalItem`, `ToolCallOutputItem`, `ToolGuardrailFunctionOutput`, `ToolOutputFileContent`, `ToolOutputImage`, `ToolOutputText`, `ToolSearchTool`, `ToolTimeoutError`, `Usage`, `UserError`, `WebSearchTool`, `apply_diff`, `function_tool`, `handoff`, `output_guardrail`, `set_default_openai_client`, `set_default_openai_key`, `set_default_openai_responses_transport`, `tool_input_guardrail`, `tool_namespace`, `tool_output_guardrail`.

`AgentHooks` and `RunHooks` are also exported from `velmora`.

## `velmora.decorators`

The Python module `velmora.decorators` exposes `tool`.

## `velmora.extensions.experimental.hosted_multi_agent`

The Python module `velmora.extensions.experimental.hosted_multi_agent` exposes `OpenAIHostedMultiAgentModel`, `get_hosted_agent_metadata`.

## `velmora.extensions.memory.advanced_sqlite_session`

The Python module `velmora.extensions.memory.advanced_sqlite_session` exposes `AdvancedSQLiteSession`.

## `velmora.extensions.memory.async_sqlite_session`

The Python module `velmora.extensions.memory.async_sqlite_session` exposes `AsyncSQLiteSession`.

## `velmora.extensions.memory.encrypt_session`

The Python module `velmora.extensions.memory.encrypt_session` exposes `EncryptedSession`.

## `velmora.extensions.memory.sqlalchemy_session`

The Python module `velmora.extensions.memory.sqlalchemy_session` exposes `SQLAlchemySession`.

## `velmora.extensions.models.any_llm_model`

The Python module `velmora.extensions.models.any_llm_model` exposes `AnyLLMModel`.

## `velmora.extensions.models.litellm_model`

The Python module `velmora.extensions.models.litellm_model` exposes `LitellmModel`.

## `velmora.extensions.visualization`

The Python module `velmora.extensions.visualization` exposes `draw_graph`.

## `velmora.mcp`

The Python module `velmora.mcp` exposes `MCPServerManager`, `MCPServerSse`, `MCPServerStdio`, `MCPServerStreamableHttp`, `create_static_tool_filter`.

## `velmora.models.multi_provider`

The Python module `velmora.models.multi_provider` exposes `MultiProvider`, `MultiProviderMap`.

## `velmora.realtime`

The Python module `velmora.realtime` exposes `RealtimeAgent`, `RealtimeRunner`, `realtime_handoff`.

## `velmora.realtime.model`

The Python module `velmora.realtime.model` exposes `RealtimePlaybackTracker`.

## `velmora.realtime.model_inputs`

The Python module `velmora.realtime.model_inputs` exposes `RealtimeModelSendRawMessage`.

## `velmora.realtime.openai_realtime`

The Python module `velmora.realtime.openai_realtime` exposes `OpenAIRealtimeSIPModel`, `OpenAIRealtimeWebSocketModel`.

## `velmora.run`

The Python module `velmora.run` exposes `ModelInputData`.

The execution entry is `Runner.run`; its keyword carriers include `conversation_id`, `run_config`, and `session`.

## `velmora.sandbox`

The Python module `velmora.sandbox` exposes `LocalSnapshotSpec`, `Manifest`, `MemoryGenerateConfig`, `MemoryLayoutConfig`, `MemoryReadConfig`, `Permissions`, `SandboxAgent`, `SandboxError`, `SandboxPathGrant`, `SandboxRunConfig`.

## `velmora.sandbox.capabilities`

The Python module `velmora.sandbox.capabilities` exposes `Compaction`, `Filesystem`, `LocalDirLazySkillSource`, `Memory`, `Shell`, `Skills`.

## `velmora.sandbox.entries`

The Python module `velmora.sandbox.entries` exposes `AzureBlobMount`, `Dir`, `File`, `FuseMountPattern`, `GitRepo`, `GCSMount`, `R2Mount`, `RcloneMountPattern`, `InContainerMountStrategy`, `LocalDir`, `LocalFile`, `MountpointMountPattern`, `S3Mount`.

## `velmora.sandbox.errors`

The Python module `velmora.sandbox.errors` exposes `LocalDirReadError`, `MountConfigError`, `WorkspaceReadNotFoundError`.

## `velmora.sandbox.manifest`

The Python module `velmora.sandbox.manifest` exposes `Environment`.

## `velmora.sandbox.sandboxes.docker`

The Python module `velmora.sandbox.sandboxes.docker` exposes `DockerSandboxClient`, `DockerSandboxClientOptions`.

## `velmora.sandbox.sandboxes.unix_local`

The Python module `velmora.sandbox.sandboxes.unix_local` exposes `UnixLocalSandboxClient`.

## `velmora.sandbox.session.dependencies`

The Python module `velmora.sandbox.session.dependencies` exposes `Dependencies`.

## `velmora.sandbox.snapshot`

The Python module `velmora.sandbox.snapshot` exposes `LocalSnapshotSpec`, `RemoteSnapshotSpec`.

## `velmora.tool_context`

The Python module `velmora.tool_context` exposes `ToolContext`.

## `velmora.tracing`

The Python module `velmora.tracing` exposes `TracingProcessor`, `add_trace_processor`, `custom_span`, `flush_traces`, `get_trace_provider`, `set_trace_processors`, `set_trace_provider`, `set_tracing_disabled`, `trace`.

## `velmora.tracing.processor_interface`

The Python module `velmora.tracing.processor_interface` exposes `TracingExporter`.

## `velmora.tracing.processors`

The Python module `velmora.tracing.processors` exposes `BatchTraceProcessor`.

## `velmora.tracing.provider`

The Python module `velmora.tracing.provider` exposes `DefaultTraceProvider`.

## `velmora.voice`

The Python module `velmora.voice` exposes `AudioInput`, `STTModel`, `STTModelSettings`, `SingleAgentVoiceWorkflow`, `StreamedAudioInput`, `StreamedTranscriptionSession`, `TTSModel`, `TTSModelSettings`, `VoiceModelProvider`, `VoicePipeline`, `VoicePipelineConfig`, `VoiceWorkflowBase`.

## `velmora.voice.models.openai_model_provider`

The Python module `velmora.voice.models.openai_model_provider` exposes `OpenAIVoiceModelProvider`.

## `velmora.run_sync`

Stated under `velmora.Runner`.

## `velmora.run_streamed`

Stated under `velmora.Runner`.

## `velmora.from_json`

Stated under `velmora.RunState`.

## `velmora.sandbox.model_validate_json`

Stated under `velmora.sandbox.Manifest`.

## `velmora.models.interface.DISABLED`

Import `ModelTracing` with `from velmora import ModelTracing`.

`ModelTracing.DISABLED` is the disabled-tracing enum member supplied to model calls.

## `velmora.retry.all`

Stated under `velmora.retry_policies`.

## `velmora.retry.any`

Stated under `velmora.retry_policies`.

## `velmora.retry.http_status`

Stated under `velmora.retry_policies`.

## `velmora.retry.network_error`

Stated under `velmora.retry_policies`.

## `velmora.retry.never`

Stated under `velmora.retry_policies`.

## `velmora.retry.provider_suggested`

Stated under `velmora.retry_policies`.

## `velmora.retry.retry_after`

Stated under `velmora.retry_policies`.

## `velmora.RunResult`

A result returned by `Runner.run` or `Runner.run_sync` exposes `final_output` as the application value or `None`, `last_agent` as an agent, `new_items` as a list of typed run items, `raw_responses` as a list of `ModelResponse`, `context_wrapper` as `RunContextWrapper`, and `interruptions` as a list of `ToolApprovalItem`.

`input_guardrail_results` and `output_guardrail_results` are lists of verdict records. Each has `guardrail` and `output`; an output verdict additionally has `agent` and `agent_output`. Verdict `output` has `output_info` and `tripwire_triggered`.

`to_input_list() -> list[dict]` supplies Responses conversation input items. `to_state() -> RunState` supplies a checkpoint.

## `velmora.RunResultStreaming`

`Runner.run_streamed` returns this object. It exposes `is_complete: bool`, `final_output`, `last_agent`, `interruptions`, and `context_wrapper` in the same result carriers as an awaited run. `to_state() -> RunState` supplies a checkpoint.

`stream_events()` is an asynchronous iterator. Events have these discriminated shapes: `type="raw_response_event"` with `data` holding the provider event, including `data.type` and text `data.delta`; `type="run_item_stream_event"` with `name: str` and `item`; `type="agent_updated_stream_event"` with `new_agent`. Item event names are `message_output_created`, `reasoning_item_created`, `tool_called`, `tool_output`, `handoff_requested`, and `handoff_occured`.

`cancel()` and `cancel(mode="after_turn")` return `None`. Event iteration is the exception-delivery channel.

## `velmora.AgentHooks`

Import `AgentHooks` from `velmora`. It is subclassable. Asynchronous callbacks are `on_start(context, agent)`, `on_end(context, agent, output)`, `on_llm_start(context, agent, system_prompt, input_items)`, `on_llm_end(context, agent, response)`, `on_tool_start(context, agent, tool)`, `on_tool_end(context, agent, tool, result)`, and `on_handoff(context, agent, source)`. `response` is `ModelResponse`; model input is a Responses input-item list; tool callbacks receive tool context.

## `velmora.RunHooks`

Import `RunHooks` from `velmora`. It is subclassable. Asynchronous callbacks are `on_agent_start(context, agent)`, `on_agent_end(context, agent, output)`, `on_llm_start(context, agent, system_prompt, input_items)`, `on_llm_end(context, agent, response)`, `on_tool_start(context, agent, tool)`, `on_tool_end(context, agent, tool, result)`, and `on_handoff(context, from_agent, to_agent)`. `response` is `ModelResponse`; model input is a Responses input-item list; tool callbacks receive tool context.

## `velmora.HandoffInputData`

A handoff filter receives this object and returns `data.clone(input_history=..., pre_handoff_items=..., new_items=...)`. `input_history` is a tuple of input-item dictionaries; `pre_handoff_items` and `new_items` are tuples of run items.

## `velmora.SandboxSession`

A session returned by a sandbox client exposes `.state` and `.dependencies`. Asynchronous lifecycle methods are `start()`, `stop()`, `aclose()`, and `running() -> bool`.

`await read(path, *, user) -> IOBase` returns a closable binary stream; `await write(path, data: IOBase, *, user) -> None` accepts binary content. The `user` option can be omitted. Missing file access raises `WorkspaceReadNotFoundError`; denied file access raises `SandboxError`.

`await exec(*command, timeout=<seconds>, shell=<bool>, user=<identity>)` returns an object exposing `stdout: bytes`, `stderr: bytes`, and `exit_code: int`. `command` accepts separate executable and argument strings or command text; the supplied keyword options can be omitted.

`await mkdir(path: Path | str, *, parents: bool = False) -> None` is the directory-creation entry.

`supports_pty() -> bool` reports the interactive-process surface. `await pty_exec_start(*command, shell=<bool>, tty=<bool>, yield_time_s=<seconds>)` and `await pty_write_stdin(session_id=<int>, chars=<str>, yield_time_s=<seconds>)` return updates with `process_id: int | None`, `output: bytes`, and `exit_code: int | None`.

## `velmora.SandboxSessionState`

`.manifest` exposes the workspace manifest and `.snapshot` exposes its snapshot object. `rebind_persisted_mount_authority(trusted_manifest, *, provider_backend_id: str)` returns a session-state object; rejected authority binding uses `ValueError` or `MountConfigError`.

## `velmora.SnapshotBase`

A snapshot object exposed through session state supplies `await restorable(dependencies=<Dependencies>) -> bool`.

## `velmora.exec_command`

The sandbox shell tool is named `exec_command`. Function-call arguments are a JSON object with `cmd: str` and `login: bool`.

A completed tool result is text with a line `Process exited with code <integer>` and a section delimiter `\nOutput:\n`; all text following that delimiter is captured command output. It is carried in the correlated `function_call_output.output` string.

## `velmora.apply_patch`

The sandbox custom tool is named `apply_patch`. Its input is patch text. The full patch carrier uses `*** Begin Patch`, `*** Add File: <path>`, `*** Update File: <path>`, `*** Delete File: <path>`, and `*** End Patch`; hunk text uses `@@` and the line prefixes `+`, `-`, and space. The alternate operation carrier is JSON text with `type`, `path`, and `diff` for `update_file`. Results are text in `custom_tool_call_output.output`.

## `velmora.view_image`

The sandbox function tool is named `view_image`. Arguments are `{"path": <workspace path string>}`. Image results are a list containing `{"type":"input_image", "image_url":"data:<image MIME>;base64,<encoded content>"}`, where `<image MIME>` is the media type of the recognised content format: `image/png`, `image/jpeg`, `image/gif`, `image/webp`, `image/bmp`, `image/tiff` or `image/svg+xml`. Tool failures use nonempty result text.

## `velmora.SKILL.md`

A skill directory contains `SKILL.md` in UTF-8. Its front matter is enclosed by `---` lines and carries `name` and `description`; the remaining text is the skill content. Workspace skill paths have the form `.agents/<skill>/SKILL.md`; supporting resource paths use `.agents/<skill>/references/<resource>`.

## `velmora.MEMORY.md`

Memory artifacts are workspace files under the configured `memories_dir`: `MEMORY.md`, `memory_summary.md`, `raw_memories.md`, `raw_memories/<identity>.md`, and `rollout_summaries/<identity>_<slug>.md`. These files contain UTF-8 memory text. Contributions are JSON Lines at `<sessions_dir>/<identity>.jsonl`, with each object exposing `input` as a list of messages carrying `role` and `content`.

## `velmora.RealtimeSession`

A session is an asynchronous context manager and asynchronous iterator of session events. `await send_message(message)` accepts text or a message mapping with `type="message"`, `role="user"`, and `content` containing input parts. Image parts use `type="input_image"` and `image_url`.

`await send_audio(audio: bytes, commit=<bool>)`, `await interrupt()`, `await approve_tool_call(call_id: str)`, and `await reject_tool_call(call_id: str, rejection_message=<str>)` return `None`.

Events use `.type` as discriminator. `audio` carries `.audio.data: bytes`, `.audio.response_id: str`, `.item_id: str`, and `.content_index: int`; `audio_end` and `audio_interrupted` carry `.item_id` and `.content_index`; `history_added` carries `.item`; `history_updated` carries `.history: list` of items. History items expose `.item_id` and `.content` parts with `.text` or `.transcript`.

`tool_approval_required` carries `.call_id` and `.arguments` as JSON text; `tool_start` carries `.tool.name` and `.arguments`; `tool_end` carries `.tool.name` and `.output`; `handoff` carries `.from_agent` and `.to_agent`; `guardrail_tripped` carries `.message` and `.guardrail_results` whose entries expose `.guardrail.get_name()` and `.output.tripwire_triggered`; `error` carries `.error` with provider `code`; `agent_end` carries `.info.context.usage`.

`raw_model_event` carries `.data`: a `usage` model event with `.usage`, or a `raw_server_event` with `.data` as the provider event mapping, including `type`, `event_id`, and provider fields. `history_updated` also carries `.info.context.usage`. Usage exposes `requests`, `input_tokens`, `output_tokens`, and `total_tokens` as integers. Unexpected connection closure raises `websockets.exceptions.ConnectionClosedError` during iteration.

## `Responses items`

Responses conversation input is a list of dictionaries. User messages have `role="user"` and `content` containing text or input parts. Assistant messages have `type="message"`, `role="assistant"`, and `content` containing `{"type":"output_text", "text": <text>}` parts. Refusal parts carry `type="refusal"` and `refusal: str`. Reasoning items have `type="reasoning"`, `id: str`, and `summary` containing `{"type":"summary_text", "text": <text>}` parts.

Function calls have `type="function_call"`, `name: str`, `call_id: str`, and `arguments: str` containing a JSON object. Namespaced calls also carry `namespace: str`. Their result mappings have `type="function_call_output"`, `call_id: str`, and `output` containing text or a list of content parts. Custom calls have `type="custom_tool_call"`, `name`, `call_id`, and raw text `input`; their results use `type="custom_tool_call_output"`, `call_id`, and `output`.

Rich output parts use `type="input_text"` with `text: str`, `type="input_image"` with `image_url: str` and, only when a detail level is set, `detail: str`, or `type="input_file"` with `file_data: str` and `filename: str`.

Run items expose `type`, `agent`, and `raw_item`. The run-item discriminators are `message_output_item`, `reasoning_item`, `tool_call_item`, `tool_call_output_item`, `handoff_call_item`, and `handoff_output_item`. Tool result items additionally expose `output` as the application value. `raw_item` is the corresponding provider item, as a typed object or dictionary; typed objects support `model_dump()`.

Typed message items also carry `id: str`, `status: str`, and text-part `annotations: list`.

Program-owned function results carry `output` as JSON text for the application’s declared result type. A guardrail replacement uses JSON text with an `error: str` field.

## `POST /v1/responses`

The Responses HTTP endpoint is `POST /v1/responses`, relative to the configured server origin. The request body is JSON. Its fields are `model: str`, `input: list` of conversation items, `tools: list` of tool declarations, and supplied settings `temperature: float`, `top_p: float`, `max_output_tokens: int`, `metadata: dict`, `service_tier: str`, `reasoning: {"effort": <str>}`, and `text: {"verbosity": <str>}`. Prompt-template requests carry `prompt` with `id`, `version`, and `variables`. Named function selection is carried by `tool_choice: {"type": "function", "name": <str>}`. Continuation carriers are `previous_response_id: str` and `conversation: str`.

Account headers are case-insensitive: `authorization` has the form `Bearer <API key>`, `openai-organization` carries the organization identity, and `openai-project` carries the project identity.

Tool declarations use `type` as discriminator. `function` carries `name`, `description`, `parameters` as JSON Schema, `strict: bool`, `defer_loading: bool`, and `allowed_callers: list[str]` when supplied. `namespace` carries `name`, `description`, and `tools` containing function declarations. The program caller permission spelling is `programmatic`; the program tool type is `programmatic_tool_calling`. Discovery uses `tool_search` with `execution: str`.

Hosted declarations use `web_search`, `file_search`, `code_interpreter`, `image_generation`, `mcp`, and `shell`. File search carries `vector_store_ids: list[str]`, `max_num_results: int`, `filters` with `type`, `key`, and `value`, and `ranking_options` with `ranker` and `score_threshold`. Web search carries `filters.allowed_domains: list[str]`, `search_context_size: str`, `external_web_access: bool`, `user_location` with `type` and `country`, `search_content_types: list[str]`, and `image_settings` with `max_results: int` and `caption: bool`. Result selectors are strings in `include`, including `file_search_call.results` and `web_search_call.results`. Code interpreter carries `container`; image generation carries `quality`; MCP carries `server_label`, `server_url`, `require_approval`, and `defer_loading`; shell carries `environment`. Eligible declarations carry `allowed_callers`.

A response is a JSON object with `id: str`, `output: list` of typed output items, and `usage` containing `input_tokens`, `output_tokens`, and `total_tokens`. Provider errors have an `error` object with `message` and `type`; server failure is exposed as `openai.InternalServerError`.

Provider usage detail mappings are `input_tokens_details` and `output_tokens_details`. The `raw_usage` return carrier is a provider usage mapping or `None`.

## `POST /v1/chat/completions`

The Chat Completions HTTP endpoint is `POST /v1/chat/completions`, relative to the configured server origin. The JSON request's `model: str` carries the selected model name. The adapter returns `ModelResponse`; its `output` exposes assistant message items and function-call items with `name`, `call_id`, and JSON text `arguments`.

The JSON request carries `messages: list` of message mappings. Tool messages have `role="tool"` and `content: str` containing the tool result. Provider usage mappings carry `prompt_tokens`, `completion_tokens`, `total_tokens`, `prompt_tokens_details`, and `completion_tokens_details`.

## `POST /v1/responses/compact`

Compaction uses `POST /v1/responses/compact`. The JSON request carries conversation items in `input`, or a continuation identity in `previous_response_id`. The response's `output` is a list of conversation items; a compaction item uses `type="compaction"`, `id: str`, and `encrypted_content: str` as an opaque content carrier.

## `response.create`

Responses WebSocket connections use `/v1/responses`. Outbound JSON frames have `type="response.create"` and `model: str`, with the Responses request fields. Incoming completion frames have `type="response.completed"` and `response` carrying `id`, `output`, and `usage`.

Hosted multi-agent connections also receive `response.created` with `response.id`, `response.output_item.done` with `item`, `output_index`, and `sequence_number`, and `response.inject.created` with `response_id: str` and `sequence_number`. Hosted message items carry `type="message"`, `agent` with `agent_name: str`, `phase: str`, and `content` parts with `type="output_text"` and `text: str`.

## `response.inject`

The hosted Responses WebSocket sends JSON frames with `type="response.inject"`, `response_id: str`, and `input: list` containing function results with `type="function_call_output"`, `call_id: str`, and `output: str`.

## `Hosted activity items`

Hosted output records expose `id` and `type`. `web_search_call` carries `status`, `action` with `type` and `query`, and `results` containing image records with `type`, `image_url`, and `caption`. `file_search_call` carries `status`, `queries`, and `results` containing `file_id`, `filename`, `score`, and `text`. `code_interpreter_call` carries `status`, `container_id`, `code`, and `outputs` containing `type="logs"` and `logs: str`. `image_generation_call` carries `status` and `result: str`. `mcp_call` carries `name`, `arguments`, `server_label`, `output`, and `error`.

`shell_call` carries `call_id`, `status`, `action.commands`, and `environment` with `type` and `container_id`; `shell_call_output` carries `call_id` and an `output` list with `stdout`, `stderr`, and `outcome` containing `type` and `exit_code`. `apply_patch_call_output` carries `call_id`, `status`, and `output`.

`tool_search_call` carries `arguments`, `execution`, `status`, and `call_id`; `tool_search_output` carries `tools`. `program` carries `call_id`, `code`, and `fingerprint`; `program_output` carries `call_id`, `status`, and `result`. Child call and result records carry `caller` with `type="program"` and `caller_id: str`.

MCP approval requests have `type="mcp_approval_request"`, `id`, `server_label`, `name`, and JSON text `arguments`. Decision input mappings have `type="mcp_approval_response"`, `approval_request_id: str`, and `approve: bool`.

## `Realtime WebSocket`

The configured Realtime WebSocket exchanges JSON objects discriminated by `type`. Client session configuration uses `session.update` with `session` containing `model`, `instructions`, `tools` with function `name`, and `audio`. The `audio.input` mapping carries `format` and `turn_detection`; `audio.output` carries `voice` and `format`. PCM format objects carry `type="audio/pcm"` and `rate: int`; telephony formats use `audio/pcmu` or `audio/pcma`.

`conversation.item.create` carries `item` with `type="message"`, `role="user"`, and `content` parts with `type="input_text"`, `text: str`, or `type="input_image"`, `image_url: str`. Function results use item `type="function_call_output"`, `call_id`, and `output`. `input_audio_buffer.append` carries base64 `audio: str`; `input_audio_buffer.commit` and `response.create` carry their event discriminator. `response.cancel` carries `response_id: str`. `conversation.item.truncate` carries `item_id: str`, `content_index: int`, and `audio_end_ms: int`; `conversation.item.retrieve` carries `item_id: str`.

Server session acknowledgements use `session.updated` with `session`. Server event dictionaries carry `type` and `event_id`. Audio deltas use `response.output_audio.delta` with `response_id`, `item_id`, `content_index`, and base64 `delta`; transcript deltas use `response.output_audio_transcript.delta` with text `delta`; text deltas use `response.output_text.delta` with text `delta`. Completed items use `response.output_item.done` with `item`, whose `id`, `type`, `role`, and `content` carry message history or whose `name`, `call_id`, and `arguments` carry a function call. Message content uses `output_text` with `text` or `output_audio` with `transcript`.

`response.created` and `response.done` carry `response` with `id`, `status`, and `output`; response `usage` has `input_tokens`, `output_tokens`, and `total_tokens`. `conversation.item.retrieved` carries `item`; `conversation.item.truncated` carries `item_id`, `content_index`, and `audio_end_ms`. `rate_limits.updated` carries `rate_limits`; provider `error` events carry `error.code`.

## `POST /v1/audio/transcriptions`

Speech recognition uses `POST /v1/audio/transcriptions` with multipart form fields. `file` contains a WAV file with signed 16-bit little-endian PCM samples. `model`, `prompt`, and `language` are text fields; multiple language declarations use `languages[]`. A `gpt-transcribe` request sends a single language hint as `languages[]` instead of `language`. The JSON response carries recognized text in `text: str`.

## `POST /v1/audio/speech`

Speech synthesis uses `POST /v1/audio/speech` with a JSON body containing `model: str`, `input: str`, and `voice` as a string or `{"id": <voice identity>}`. The response body is signed 16-bit little-endian PCM bytes. The configured client's base URL selects the server origin.

## `Transcription WebSocket`

Streamed speech recognition exchanges JSON WebSocket events. The outbound `session.update` contains `session.audio.input.transcription` with `model: str`, `languages: list[str]`, `prompt: str`, and `keywords: list[str]` when supplied. `input_audio_buffer.append` carries base64 `audio: str`. Input closure uses `input_audio_buffer.clear`.

Inbound events use `session.created`, `session.updated`, `input_audio_buffer.committed` with `item_id`, `conversation.item.input_audio_transcription.completed` with `item_id` and `transcript: str`, and `input_audio_buffer.cleared`.

## `velmora.reject_content`

Stated under `velmora.ToolGuardrailFunctionOutput`.

## `velmora.tool_guardrails.allow`

Stated under `velmora.ToolGuardrailFunctionOutput`.

## `velmora.tool_guardrails.raise_exception`

Stated under `velmora.ToolGuardrailFunctionOutput`.

## `velmora.tool_guardrails.reject_content`

Stated under `velmora.ToolGuardrailFunctionOutput`.

## `velmora.sandbox.session.dependencies.with_values`

Import `Dependencies` with `from velmora.sandbox.session.dependencies import Dependencies`.

`Dependencies.with_values(values: dict) -> Dependencies` accepts dependency-name strings mapped to application objects.

## `openai.AsyncOpenAI`

Applications can supply the installed OpenAI Python client's `openai.AsyncOpenAI` through an `openai_client` or `client` parameter. Its constructor accepts `base_url: str`, `websocket_base_url: str`, `api_key: str`, `max_retries: int`, `organization: str | None` and `project: str | None`; the client supports an asynchronous context manager. These URL parameters identify the HTTP and WebSocket service origins.

Application model responses use the following typed carriers from `openai.types.responses`. Their listed fields are readable attributes and keyword construction fields. Conversation mappings use the corresponding field names.

| Carrier | Fields |
| --- | --- |
| `ResponseOutputMessage` | `id: str`, `type: "message"`, `role: "assistant"`, `status: str`, `content: list` of output-text or refusal carriers |
| `ResponseOutputText` | `type: "output_text"`, `text: str`, `annotations: list` |
| `ResponseOutputRefusal` | `type: "refusal"`, `refusal: str` |
| `ResponseReasoningItem` | `id: str`, `type: "reasoning"`, `summary: list` of mappings containing `type: "summary_text"` and `text: str` |
| `ResponseFunctionToolCall` | `type: "function_call"`, `name: str`, `arguments: str` containing JSON, `call_id: str`, optional `caller` |
| `ResponseCustomToolCall` | `type: "custom_tool_call"`, `name: str`, `input: str`, `call_id: str` |
| `ResponseComputerToolCall` | `id: str`, `type: "computer_call"`, `call_id: str`, `status: str`, `actions: list` of action mappings, `pending_safety_checks: list` |
| `ResponseFunctionShellToolCall` | `id: str`, `type: "shell_call"`, `call_id: str`, `status: str`, `action` with `commands: list[str]`, optional `timeout_ms` and `max_output_length` |
| `ResponseApplyPatchToolCall` | `id: str`, `type: "apply_patch_call"`, `call_id: str`, `status: str`, `operation` with `type: str`, `path: str` and, for textual edits, `diff: str` |
| `Response` | `id: str`, `output: list` of output carriers, `usage` containing integer token counts |
| `ResponseTextDeltaEvent` | `type: "response.output_text.delta"`, `delta: str`, `item_id: str`, `output_index: int`, `content_index: int`, `sequence_number: int`, `logprobs: list` |
| `ResponseCompletedEvent` | `type: "response.completed"`, `response: Response`, `sequence_number: int` |

`ResponseApplyPatchToolCall` is also importable from `openai.types.responses.response_output_item`. `ResponseCustomToolCall` is also importable from `openai.types.responses.response_custom_tool_call`. `PendingSafetyCheck` from `openai.types.responses.response_computer_tool_call` has `id: str`, `code: str` and `message: str`.

Program carriers come from `openai.types.responses.response_output_item`: `Program` has `id: str`, `call_id: str`, `type: "program"`, `code: str` and `fingerprint: str`; `ProgramOutput` has `id: str`, `call_id: str`, `type: "program_output"`, `status: str` and `result`. `CallerProgram` from `openai.types.responses.response_function_tool_call` has `type: "program"` and `caller_id: str` and is accepted as a function call's `caller` value.

`ModelSettings.reasoning` accepts `openai.types.shared.Reasoning(effort=<str>)`. Application-declared structured argument and output schemas can subclass `pydantic.BaseModel`, declare constrained fields with `pydantic.Field(ge=<number>)` or `Field(gt=<number>)`, select additional-field handling with `pydantic.ConfigDict(extra=<str>)` as `model_config`, and attach `pydantic.field_validator(<field name>)` decorators to field-validation methods. Model instances expose their declared fields as attributes.

A model callback can raise `openai.APIConnectionError(request=<HTTP request>)` as a connection failure. HTTP service errors use `openai.InternalServerError`; invalid model settings use `pydantic.ValidationError`.

## `openai.types.responses.ResponseOutputMessage`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.ResponseOutputText`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.ResponseOutputRefusal`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.ResponseReasoningItem`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.ResponseFunctionToolCall`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.ResponseCustomToolCall`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.ResponseComputerToolCall`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.ResponseFunctionShellToolCall`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.Response`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.ResponseTextDeltaEvent`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.ResponseCompletedEvent`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.response_computer_tool_call.PendingSafetyCheck`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.response_output_item.Program`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.response_output_item.ProgramOutput`

Stated under `openai.AsyncOpenAI`.

## `openai.types.responses.response_function_tool_call.CallerProgram`

Stated under `openai.AsyncOpenAI`.

## `openai.types.shared.Reasoning`

Stated under `openai.AsyncOpenAI`.

## `pydantic.BaseModel`

Stated under `openai.AsyncOpenAI`.

## `pydantic.ConfigDict`

Stated under `openai.AsyncOpenAI`.

## `pydantic.Field`

Stated under `openai.AsyncOpenAI`.

## `pydantic.field_validator`

Stated under `openai.AsyncOpenAI`.

## `openai.APIConnectionError`

Stated under `openai.AsyncOpenAI`.

## `openai.InternalServerError`

Stated under `POST /v1/responses`.

## `pydantic.ValidationError`

Stated under `velmora.ModelSettings`.

## `websockets.exceptions.ConnectionClosedError`

Stated under `velmora.RealtimeSession`.

## `mcp.shared.exceptions.MCPError`

Stated under `velmora.mcp.MCPServerStdio`.

## `requests.exceptions.ConnectionError`

Stated under `velmora.sandbox.sandboxes.docker.DockerSandboxClient`.

## `docker.DockerClient`

`velmora.sandbox.sandboxes.docker.DockerSandboxClient` accepts an installed `docker.DockerClient`. The Docker client constructor accepts `base_url: str` naming the service endpoint and `version: str` identifying the Docker API version. `close() -> None` releases the client connection. Connection failure from sandbox creation is exposed as `requests.exceptions.ConnectionError`.

## `openai.types.responses.response_output_item.ResponseApplyPatchToolCall`

Stated under `openai.AsyncOpenAI`.

## `velmora.sandbox.entries.GCSMount`

Import `GCSMount` with `from velmora.sandbox.entries import GCSMount`.

Construction accepts `bucket: str`, `access_id: str | None`, `secret_access_key: str | None`, `endpoint_url: str | None`, `read_only: bool`, and `mount_strategy: InContainerMountStrategy`. The strategy accepts `MountpointMountPattern` or `RcloneMountPattern`. Rejected declarations use `MountConfigError`.

## `velmora.sandbox.entries.R2Mount`

Import `R2Mount` with `from velmora.sandbox.entries import R2Mount`.

Construction accepts `bucket: str`, `account_id: str`, `access_key_id: str | None`, `secret_access_key: str | None`, `custom_domain: str | None`, `read_only: bool`, and `mount_strategy: InContainerMountStrategy` with `pattern: RcloneMountPattern`. Rejected declarations use `MountConfigError`.

## `velmora.sandbox.entries.RcloneMountPattern`

Import `RcloneMountPattern` with `from velmora.sandbox.entries import RcloneMountPattern`.

Construction: `RcloneMountPattern()`.
