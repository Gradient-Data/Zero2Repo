# feature: F12
"""Acceptance of hosted requests, discovery, program children and live orchestration."""
import asyncio
import base64
import io
import json
import zipfile

import pytest
from pydantic import BaseModel
from F01_helpers import RecordingModel, text_message, function_call
from F02_helpers import retry_settings
from F04_helpers import execution_run
from F08_helpers import pending_calls
from F12_helpers import (
    hosted_http, hosted_run, raw_dict, raw_items, program_start, program_end,
    program_child, program_run, child_output, mcp_request, hosted_message,
    hosted_socket, hosted_agent_run,
)
from _helpers import bounded
from velmora import (
    Agent, ApplyPatchTool, CodeInterpreterTool, CustomTool, FileSearchTool,
    HostedMCPTool, ImageGenerationTool, ModelSettings, OpenAIChatCompletionsModel,
    ProgrammaticToolCallingTool, RunState, ShellTool, ToolSearchTool, UserError,
    WebSearchTool, function_tool, tool_namespace, ToolGuardrailFunctionOutput,
    tool_input_guardrail, tool_output_guardrail,
)
from velmora import ModelBehaviorError
from velmora import ModelRetryAdvice
from velmora.tool_context import ToolContext
from openai import AsyncOpenAI


@pytest.mark.asyncio
async def test_f12_t01():
    tools = [WebSearchTool(), FileSearchTool(vector_store_ids=["store-reference"]),
             CodeInterpreterTool(tool_config={"type": "code_interpreter", "container": "auto"}),
             ImageGenerationTool(tool_config={"type": "image_generation", "quality": "low"}),
             HostedMCPTool(tool_config={"type": "mcp", "server_label": "remote",
                                       "server_url": "https://remote.example/mcp", "require_approval": "never"}),
             ShellTool(environment={"type": "container_auto"})]
    activity = [
        {"id": "web", "type": "web_search_call", "status": "completed",
         "action": {"type": "search", "query": "habitat"}},
        {"id": "file", "type": "file_search_call", "status": "completed", "queries": ["habitat"],
         "results": [{"file_id": "file-reference", "filename": "notes.txt", "score": 0.8, "text": "River habitat."}]},
        {"id": "code", "type": "code_interpreter_call", "status": "completed", "container_id": "container-reference",
         "code": "print(7)", "outputs": [{"type": "logs", "logs": "7"}]},
        {"id": "image", "type": "image_generation_call", "status": "completed", "result": "cGl4ZWxz"},
        {"id": "mcp", "type": "mcp_call", "name": "lookup", "arguments": "{}",
         "server_label": "remote", "output": "Remote habitat.", "error": None},
        {"id": "shell", "type": "shell_call", "call_id": "hosted-shell", "status": "completed",
         "action": {"commands": ["pwd"]}, "environment": {"type": "container_reference", "container_id": "container-reference"}},
        {"id": "shell-output", "type": "shell_call_output", "call_id": "hosted-shell",
         "output": [{"stdout": "/workspace", "stderr": "", "outcome": {"type": "exit", "exit_code": 0}}]},
    ]
    result, requests = await hosted_run(tools, [[*activity, text_message("Hosted work returned.")]])
    payloads = {tool["type"]: tool for tool in requests[0]["body"]["tools"]}
    assert set(payloads) == {"web_search", "file_search", "code_interpreter", "image_generation", "mcp", "shell"}
    assert payloads["file_search"]["vector_store_ids"] == ["store-reference"]
    assert payloads["code_interpreter"]["container"] == "auto"
    assert payloads["image_generation"]["quality"] == "low"
    assert payloads["mcp"]["server_url"] == "https://remote.example/mcp"
    assert payloads["shell"]["environment"]["type"] == "container_auto"
    observed = {item["id"]: item for item in raw_items(result) if "id" in item}
    raw = {item.id: raw_dict(item) for item in result.raw_responses[0].output}
    for item in activity:
        assert item["id"] in observed and item["id"] in raw
        for key, value in item.items():
            if value is None:
                continue
            assert observed[item["id"]][key] == value
            assert raw[item["id"]][key] == value
    assert result.final_output == "Hosted work returned."


@pytest.mark.asyncio
async def test_f12_t02():
    filters = {"type": "eq", "key": "category", "value": "research"}
    ranking = {"ranker": "auto", "score_threshold": 0.4}
    for count in (None, 0, 1, 23, 50):
        result, requests = await hosted_run([FileSearchTool(vector_store_ids=["store-one", "store-two"],
            max_num_results=count, filters=filters, ranking_options=ranking, include_search_results=True)])
        body = requests[0]["body"]
        tool = body["tools"][0]
        assert tool["vector_store_ids"] == ["store-one", "store-two"]
        assert tool["filters"] == filters and tool["ranking_options"] == ranking
        if count in (None, 0):
            assert "max_num_results" not in tool
        else:
            assert tool["max_num_results"] == count
        assert "file_search_call.results" in body["include"]
        assert result.final_output == "Hosted response."
    for count in (-1, 51, 1.5, True):
        with pytest.raises(UserError):
            await hosted_run([FileSearchTool(vector_store_ids=["store-one"], max_num_results=count)])
    image = {"type": "image", "image_url": "https://images.example/river.png", "caption": "River bank"}
    activity = {"id": "image-search", "type": "web_search_call", "status": "completed",
                "action": {"type": "search", "query": "river"}, "results": [image]}
    result, requests = await hosted_run([WebSearchTool(
        filters={"allowed_domains": ["images.example"]}, search_context_size="high",
        external_web_access=False, user_location={"type": "approximate", "country": "SG"},
        search_content_types=["text", "image"], image_settings={"max_results": 3, "caption": True})],
        [[activity, text_message("A river.")]])
    tool = requests[0]["body"]["tools"][0]
    assert tool["filters"] == {"allowed_domains": ["images.example"]}
    assert tool["search_context_size"] == "high" and tool["external_web_access"] is False
    assert tool["user_location"]["country"] == "SG"
    assert tool["search_content_types"] == ["text", "image"]
    assert tool["image_settings"] == {"max_results": 3, "caption": True}
    search = next(item for item in raw_items(result) if item["type"] == "web_search_call")
    assert search["results"] == [image]
    assert "web_search_call.results" in requests[0]["body"]["include"]
    assert result.final_output == "A river."


@pytest.mark.asyncio
async def test_f12_t03():
    effects = []

    @function_tool(defer_loading=True)
    def delayed(value: str) -> str:
        effects.append(("deferred", value))
        return "deferred:" + value

    @function_tool
    def ready(value: str) -> str:
        effects.append(("immediate", value))
        return "immediate:" + value

    @function_tool(defer_loading=True)
    def standalone(value: str) -> str:
        effects.append(("standalone", value))
        return "standalone:" + value

    tools = [ToolSearchTool(), standalone, *tool_namespace(name="records", description="Record lookups", tools=[delayed, ready]),
             HostedMCPTool(tool_config={"type": "mcp", "server_label": "remote", "server_url": "https://remote.example/mcp",
                                       "defer_loading": True, "require_approval": "never"})]
    search = {"id": "search-call", "type": "tool_search_call", "execution": "server", "status": "completed",
              "arguments": {"query": "records"}}
    found = {"id": "search-output", "type": "tool_search_output", "execution": "server", "status": "completed",
             "tools": [{"type": "function", "name": "delayed", "namespace": "records", "description": "Record lookup",
                        "parameters": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}}]}
    deferred_call = function_call("delayed", {"value": "archive"}, "deferred-call").model_copy(update={"namespace": "records"})
    immediate_call = function_call("ready", {"value": "current"}, "ready-call").model_copy(update={"namespace": "records"})
    remote = {"id": "remote-call", "type": "mcp_call", "name": "remote_lookup", "arguments": "{}", "server_label": "remote",
              "output": "Remote record.", "error": None}
    found["tools"].append({"type": "mcp", "server_label": "remote", "server_url": "https://remote.example/mcp"})
    standalone_call = function_call("standalone", {"value": "separate"}, "standalone-call").model_copy(update={"namespace": "standalone"})
    result, requests = await hosted_run(tools, [[search, found, deferred_call, immediate_call, standalone_call, remote], [text_message("Records returned.")]])
    assert set(effects) == {("deferred", "archive"), ("immediate", "current"), ("standalone", "separate")}
    from F03_helpers import tool_outputs
    assert tool_outputs(requests[-1]["body"]) == {"deferred-call": "deferred:archive", "ready-call": "immediate:current", "standalone-call": "standalone:separate"}
    declarations = requests[0]["body"]["tools"]
    namespace = next(item for item in declarations if item["type"] == "namespace")
    members = {item["name"]: item for item in namespace["tools"]}
    assert members["delayed"]["defer_loading"] is True
    assert not members["ready"].get("defer_loading", False)
    assert next(item for item in declarations if item["type"] == "mcp")["defer_loading"] is True
    observed = {item["id"]: item for item in raw_items(result) if "id" in item}
    assert observed["search-call"]["arguments"] == search["arguments"]
    assert observed["search-output"]["tools"] == found["tools"]
    assert observed["remote-call"]["output"] == "Remote record."
    assert result.final_output == "Records returned."


@pytest.mark.asyncio
async def test_f12_t04():
    @function_tool(defer_loading=True)
    def deferred() -> str:
        return "available"

    @function_tool
    def immediate() -> str:
        return "ready"

    result, _ = await hosted_run([ToolSearchTool(), deferred])
    assert result.final_output == "Hosted response."
    # Forcing an immediately available tool alongside discovery remains a valid choice.
    result, requests = await hosted_run([ToolSearchTool(), deferred, immediate],
                                        settings=ModelSettings(tool_choice="immediate"))
    assert result.final_output == "Hosted response."
    assert requests[0]["body"]["tool_choice"] == {"type": "function", "name": "immediate"}
    for tools, choice in [([deferred], None),
                          (tool_namespace(name="records", description="Lookup", tools=[deferred]), None),
                          ([HostedMCPTool(tool_config={"type": "mcp", "server_label": "remote",
                              "server_url": "https://remote.example/mcp", "defer_loading": True})], None),
                          ([ToolSearchTool(), ToolSearchTool(), deferred], None),
                          ([ToolSearchTool(), deferred], "deferred"),
                          ([ToolSearchTool(), *tool_namespace(name="records", description="Lookup", tools=[deferred])], "records")]:
        with pytest.raises(UserError):
            await hosted_run(tools, settings=ModelSettings(tool_choice=choice))
    with pytest.raises(ModelBehaviorError):
        await hosted_run([ToolSearchTool(execution="client"), deferred], [[{
            "id": "client-search", "type": "tool_search_call", "execution": "client", "status": "completed",
            "call_id": "search-client-call", "arguments": {"query": "deferred"}}]])


@pytest.mark.asyncio
async def test_f12_t05():
    for permission, direct, program in [(None, True, False), (["programmatic"], False, True),
                                         (["direct", "programmatic"], True, True)]:
        effects = []

        def record(value: str) -> str:
            effects.append(value)
            return "recorded:" + value

        tool = function_tool(record, **({"allowed_callers": permission} if permission is not None else {}))
        for is_program, allowed in [(False, direct), (True, program)]:
            effects.clear()
            call = program_child(tool.name, {"value": "request"}) if is_program else function_call(tool.name, {"value": "request"}, "child-call")
            outputs = [[program_start(), call] if is_program else [call], ([program_end(), text_message("Accepted.")] if is_program else [text_message("Accepted.")])]
            if allowed:
                result, requests = await hosted_run([ProgrammaticToolCallingTool(), tool,
                    CodeInterpreterTool(tool_config={"type": "code_interpreter", "container": "auto", "allowed_callers": ["programmatic"]})], outputs)
                assert effects == ["request"] and child_output(requests) == "recorded:request"
                assert result.final_output == "Accepted."
                if is_program:
                    returned = next(item for item in raw_items(result) if item["type"] == "function_call_output")
                    assert raw_dict(returned["caller"]) == {"type": "program", "caller_id": "program-call"}
                    assert any(item["type"] == "program_output" and item["result"] == '{"complete":true}' for item in raw_items(result))
            else:
                with pytest.raises(ModelBehaviorError):
                    await hosted_run([ProgrammaticToolCallingTool(), tool,
                        CodeInterpreterTool(tool_config={"type": "code_interpreter", "container": "auto", "allowed_callers": ["programmatic"]})], outputs)
                assert effects == []
    effects = []

    async def shell(request):
        effects.append(("shell", request.data.action.commands))
        return "shell result"

    def custom(context, value):
        effects.append(("custom", value))
        return "custom result"

    class Editor:
        def create_file(self, operation):
            effects.append(("patch", operation.path, operation.diff))
            return "patch result"

    caller = {"type": "program", "caller_id": "program-call"}
    tools = [ProgrammaticToolCallingTool(), ShellTool(executor=shell, allowed_callers=["programmatic"]),
             CustomTool(name="custom", description="Process text", on_invoke_tool=custom, allowed_callers=["programmatic"]),
             ApplyPatchTool(editor=Editor(), allowed_callers=["programmatic"]),
             HostedMCPTool(tool_config={"type": "mcp", "server_label": "remote", "server_url": "https://remote.example/mcp",
                                       "allowed_callers": ["programmatic"], "require_approval": "never"}),
             CodeInterpreterTool(tool_config={"type": "code_interpreter", "container": "auto", "allowed_callers": ["programmatic"]})]
    calls = [
        {"id": "shell", "call_id": "shell-child", "type": "shell_call", "status": "completed", "action": {"commands": ["pwd"]}, "caller": caller},
        {"id": "custom", "call_id": "custom-child", "type": "custom_tool_call", "name": "custom", "input": "sample", "caller": caller},
        {"id": "patch", "call_id": "patch-child", "type": "apply_patch_call", "status": "completed",
         "operation": {"type": "create_file", "path": "note.txt", "diff": "+entry"}, "caller": caller},
        {"id": "remote", "type": "mcp_call", "server_label": "remote", "name": "lookup", "arguments": "{}", "output": "remote result", "caller": caller},
        {"id": "code", "type": "code_interpreter_call", "container_id": "service-container", "status": "completed", "code": "print(3)",
         "outputs": [{"type": "logs", "logs": "3"}], "caller": caller},
    ]
    result, requests = await hosted_run(tools, [[program_start(), *calls], [program_end(), text_message("All children returned.")]])
    assert ("shell", ["pwd"]) in effects and ("custom", "sample") in effects
    assert ("patch", "note.txt", "+entry") in effects
    outputs = {item["call_id"]: item for item in requests[-1]["body"]["input"] if item.get("type") in
               ("shell_call_output", "custom_tool_call_output", "apply_patch_call_output")}
    assert set(outputs) == {"shell-child", "custom-child", "patch-child"}
    assert outputs["custom-child"]["output"] == "custom result"
    assert outputs["patch-child"]["status"] == "completed"
    assert outputs["patch-child"]["output"] == "patch result"
    assert outputs["shell-child"]["output"][0]["stdout"] == "shell result"
    for output in outputs.values():
        assert output["caller"] == caller
    for declaration in requests[0]["body"]["tools"]:
        if declaration["type"] != "programmatic_tool_calling":
            assert declaration["allowed_callers"] == ["programmatic"]
    observed = {item["id"]: item for item in raw_items(result) if "id" in item}
    assert observed["remote"]["caller"] == caller
    assert observed["code"]["caller"] == caller
    assert observed["remote"]["output"] == "remote result"
    assert observed["code"]["outputs"] == [{"type": "logs", "logs": "3"}]
    assert result.final_output == "All children returned."


@pytest.mark.asyncio
async def test_f12_t06():
    @function_tool(allowed_callers=["programmatic"])
    def child() -> str:
        return "child result"

    @function_tool(defer_loading=True)
    def deferred() -> str:
        return "discoverable"

    for tools, prompt in [([ProgrammaticToolCallingTool(), child], None),
                          ([ProgrammaticToolCallingTool(), ToolSearchTool(), deferred], None),
                          ([ProgrammaticToolCallingTool(), ToolSearchTool()], {"id": "managed-prompt"})]:
        result, requests = await hosted_run(tools, prompt=prompt)
        assert result.final_output == "Hosted response."
        assert any(tool["type"] == "programmatic_tool_calling" for tool in requests[0]["body"]["tools"])
        if prompt:
            assert requests[0]["body"]["prompt"]["id"] == prompt["id"]
    @function_tool
    def direct_only() -> str:
        return "direct"

    # A tool that does not permit program callers is not an eligible callable surface.
    for tools in ([ProgrammaticToolCallingTool(), ProgrammaticToolCallingTool(), child],
                  [ProgrammaticToolCallingTool()], [ProgrammaticToolCallingTool(), ToolSearchTool()],
                  [ProgrammaticToolCallingTool(), direct_only]):
        with pytest.raises(UserError):
            await hosted_run(tools)


@pytest.mark.asyncio
async def test_f12_t07():
    class Output(BaseModel):
        value: str

    effects = []

    @function_tool(allowed_callers=["programmatic"], needs_approval=True)
    def protected(value: str) -> Output:
        effects.append(value)
        return Output(value="approved:" + value)

    async with hosted_http([[program_start(), program_child(protected.name, {"value": "entry"})],
                            [program_end(), text_message("Approved program.")]]) as (model, requests):
        agent = Agent(name="Protected program", model=model, tools=[ProgrammaticToolCallingTool(), protected])
        first = await execution_run(agent)
        assert set(pending_calls(first)) == {"child-call"}
        assert effects == []
        state = await RunState.from_json(agent, first.to_state().to_json())
        state.approve(state.get_interruptions()[0])
        result = await execution_run(agent, state)
        assert effects == ["entry"] and result.final_output == "Approved program."
        assert json.loads(child_output(requests)) == {"value": "approved:entry"}

    @tool_input_guardrail
    def block_input(data):
        return ToolGuardrailFunctionOutput.reject_content("input blocked by application")

    @tool_output_guardrail
    def block_output(data):
        return ToolGuardrailFunctionOutput.reject_content("output blocked by application")

    for direction in ("input", "output"):
        effects.clear()

        def guarded(value: str) -> Output:
            effects.append(value)
            return Output(value="private result")

        tool = function_tool(guarded, allowed_callers=["programmatic"],
            **({"tool_input_guardrails": [block_input]} if direction == "input" else {"tool_output_guardrails": [block_output]}))
        result, requests = await program_run(tool, arguments={"value": "entry"})
        assert effects == ([] if direction == "input" else ["entry"])
        # The guardrail's replacement content, not the rejected content, reaches the program.
        delivered = child_output(requests)
        assert json.loads(delivered) == {"error": direction + " blocked by application"}
        assert result.final_output == "Program finished."

    stopped = asyncio.Event()
    started = asyncio.Event()
    timeout_errors = []

    def timeout_output(context, error):
        timeout_errors.append(error)
        return json.dumps({"value": "application timeout"})

    @function_tool(allowed_callers=["programmatic"], timeout=0.02, timeout_error_function=timeout_output)
    async def slow() -> Output:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
        return Output(value="unreachable")

    result, requests = await program_run(slow)
    assert started.is_set() and stopped.is_set() and len(timeout_errors) == 1
    assert json.loads(child_output(requests)) == {"value": "application timeout"}
    assert result.final_output == "Program finished."

    @function_tool(allowed_callers=["programmatic"])
    def invalid() -> Output:
        return {"different": "invalid"}

    with pytest.raises(UserError):
        await program_run(invalid)


@pytest.mark.asyncio
async def test_f12_t08():
    from velmora import OpenAIResponsesModel
    from openai import InternalServerError
    from F02_helpers import model_peer
    from F12_helpers import hosted_payload

    class ReplayAdviceModel(OpenAIResponsesModel):
        def __init__(self, client, safety):
            super().__init__(model="hosted-capable", openai_client=client)
            self.safety = safety

        def get_retry_advice(self, request):
            return ModelRetryAdvice(suggested=True, replay_safety=self.safety)

    for safety in (None, "safe"):
        effects = []

        @function_tool(allowed_callers=["programmatic"])
        def write(value: str) -> str:
            effects.append(value)
            return "saved:" + value

        replies = [(200, hosted_payload(program_start(), program_child(write.name, {"value": "committed"})), {}),
                   (503, {"error": {"message": "Service interrupted", "type": "server_error"}}, {}),
                   (200, hosted_payload(program_end(), text_message("Replay completed.")), {})]
        with model_peer(replies=replies) as (url, requests):
            async with AsyncOpenAI(api_key="local-peer", base_url=url, max_retries=0) as client:
                model = ReplayAdviceModel(client, safety)
                agent = Agent(name="Replay boundary", model=model, tools=[ProgrammaticToolCallingTool(), write],
                              model_settings=retry_settings(lambda context: True))
                if safety == "safe":
                    result = await execution_run(agent)
                    assert result.final_output == "Replay completed."
                    assert len(requests) == 3
                    assert requests[1]["body"]["input"] == requests[2]["body"]["input"]
                else:
                    with pytest.raises(InternalServerError):
                        await execution_run(agent)
                    assert len(requests) == 2
                assert effects == ["committed"]
                assert child_output(requests) == "saved:committed"


@pytest.mark.asyncio
async def test_f12_t09():
    class Output(BaseModel):
        value: str

    failure = RuntimeError("Application execution failed")
    effects = []

    @function_tool(allowed_callers=["programmatic"])
    def failing(value: str) -> Output:
        effects.append(value)
        raise failure

    with pytest.raises(UserError) as caught:
        await program_run(failing, arguments={"value": "accepted argument"})
    assert caught.value.__cause__ is failure and effects == ["accepted argument"]
    effects.clear()
    with pytest.raises(ModelBehaviorError):
        await program_run(failing, arguments={"unknown": "invalid argument"})
    assert effects == []

    formatted = []

    def replace(context, error):
        formatted.append(error)
        return json.dumps({"value": "application replacement"})

    def broken(value: str) -> Output:
        raise failure

    tool = function_tool(broken, allowed_callers=["programmatic"], failure_error_function=replace)
    result, requests = await program_run(tool, arguments={"value": "entry"})
    assert formatted == [failure]
    assert json.loads(child_output(requests)) == {"value": "application replacement"}
    assert result.final_output == "Program finished."
    formatted.clear()
    result, requests = await program_run(tool, arguments={"unknown": "invalid argument"})
    assert len(formatted) == 1 and isinstance(formatted[0], ModelBehaviorError)
    assert json.loads(child_output(requests)) == {"value": "application replacement"}
    assert result.final_output == "Program finished."
    for replacement in ("unstructured", '{"wrong":"field"}'):
        tool = function_tool(broken, allowed_callers=["programmatic"],
                             failure_error_function=lambda context, error: replacement)
        with pytest.raises(UserError):
            await program_run(tool, arguments={"value": "entry"})


@pytest.mark.asyncio
async def test_f12_t10():
    from F02_helpers import model_peer
    from velmora.extensions.models.litellm_model import LitellmModel

    @function_tool(defer_loading=True)
    def deferred() -> str:
        return "discovered"

    @function_tool(allowed_callers=["programmatic"])
    def child() -> str:
        return "child"

    for tools in ([ToolSearchTool(), deferred], [ProgrammaticToolCallingTool(), child]):
        result, _ = await hosted_run(tools)
        assert result.final_output == "Hosted response."
        with model_peer() as (url, requests):
            async with AsyncOpenAI(api_key="local-peer", base_url=url, max_retries=0) as client:
                model = OpenAIChatCompletionsModel(model="chat-model", openai_client=client)
                with pytest.raises(UserError):
                    await execution_run(Agent(name="Unsupported chat", model=model, tools=tools))
        with pytest.raises(UserError):
            await execution_run(Agent(name="Unsupported model", model=LitellmModel(model="anthropic/claude-sonnet-4", api_key="local-peer"), tools=tools))
    result = await execution_run(Agent(name="Ordinary model", model=RecordingModel("Ordinary answer.")))
    assert result.final_output == "Ordinary answer."


@pytest.mark.asyncio
async def test_f12_t11():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("SKILL.md", "# Example\nRead the input document.\n")
    skills = [{"type": "skill_reference", "skill_id": "skill-reference", "version": "2"},
              {"type": "inline", "name": "document", "description": "Read a document",
               "source": {"type": "base64", "media_type": "application/zip",
                          "data": base64.b64encode(archive.getvalue()).decode()}}]
    for environment in ({"type": "container_auto", "skills": skills},
                        {"type": "container_reference", "container_id": "existing-container"}):
        result, requests = await hosted_run([ShellTool(environment=environment)])
        assert requests[0]["body"]["tools"][0]["environment"] == environment
        assert result.final_output == "Hosted response."
    for options in ({"executor": lambda request: "local"}, {"needs_approval": True},
                    {"on_approval": lambda context, request: {"approve": True}}):
        with pytest.raises(UserError):
            ShellTool(environment={"type": "container_auto"}, **options)


@pytest.mark.asyncio
async def test_f12_t12():
    decisions = []

    async def approve(request):
        decisions.append((request.data.server_label, request.data.name))
        return {"approve": True}

    config = {"type": "mcp", "server_label": "server-a", "server_url": "https://a.example/mcp"}
    result, requests = await hosted_run([HostedMCPTool(tool_config=config, on_approval_request=approve)],
        [[mcp_request("auto", "server-a")], [text_message("Callback continued.")]])
    assert decisions == [("server-a", "lookup")]
    approvals = [item for item in requests[-1]["body"]["input"] if item.get("type") == "mcp_approval_response"]
    assert approvals == [{"type": "mcp_approval_response", "approval_request_id": "auto", "approve": True}]
    assert result.final_output == "Callback continued."

    tools = [HostedMCPTool(tool_config=config), HostedMCPTool(tool_config={
        "type": "mcp", "server_label": "server-b", "server_url": "https://b.example/mcp"})]
    outputs = [[mcp_request("first", "server-a")],
               [mcp_request("same", "server-a")],
               [mcp_request("other-tool", "server-a", "write")],
               [mcp_request("same-rejected", "server-a", "write")],
               [mcp_request("other-server", "server-b")], [text_message("Manual continuation.")]]
    async with hosted_http(outputs) as (model, requests):
        agent = Agent(name="Scoped approvals", model=model, tools=tools)
        first = await execution_run(agent)
        assert len(first.interruptions) == 1
        assert first.interruptions[0].raw_item.id == "first"
        state = first.to_state()
        state.approve(first.interruptions[0], always_approve=True)
        state = await RunState.from_json(agent, state.to_json())
        second = await execution_run(agent, state)
        assert len(second.interruptions) == 1
        assert second.interruptions[0].raw_item.id == "other-tool"
        state = second.to_state()
        state.reject(second.interruptions[0], always_reject=True)
        third = await execution_run(agent, state)
        assert len(third.interruptions) == 1
        assert third.interruptions[0].raw_item.id == "other-server"
        state = third.to_state()
        state.reject(third.interruptions[0])
        final = await execution_run(agent, state)
        assert final.final_output == "Manual continuation."
        approvals = {item["approval_request_id"]: item["approve"] for item in requests[-1]["body"]["input"]
                     if item.get("type") == "mcp_approval_response"}
        assert approvals == {"first": True, "same": True, "other-tool": False, "same-rejected": False, "other-server": False}


@pytest.mark.asyncio
async def test_f12_t13():
    from velmora.extensions.experimental.hosted_multi_agent import get_hosted_agent_metadata
    for stream in (False, True):
        callers = []

        @function_tool
        def lookup(context: ToolContext, value: str) -> str:
            metadata = get_hosted_agent_metadata(context)
            assert metadata is not None
            callers.append((metadata.agent_name, value))
            return "record:" + value

        calls = [dict(function_call("lookup", {"value": value}, identity).model_dump(exclude_none=True),
                      agent={"agent_name": caller}, status="completed")
                 for value, identity, caller in [("alpha", "research-call", "/root/researcher"),
                                                  ("beta", "review-call", "/root/reviewer")]]
        final_items = [hosted_message("Specialist commentary.", "/root/researcher", "commentary"),
                       hosted_message("Root conclusion."),
                       hosted_message("Specialist final.", "/root/reviewer", "final_answer"),
                       hosted_message("Root progress note.", "/root", "commentary")]
        async with hosted_socket(calls=calls, final_items=final_items) as (model, requests, connections):
            result, events = await hosted_agent_run(Agent(name="Local root", model=model, tools=[lookup]), stream=stream)
            assert result.final_output == "Root conclusion."
            assert set(callers) == {("/root/researcher", "alpha"), ("/root/reviewer", "beta")}
            injected = {item["call_id"]: item["output"] for request in requests if request["type"] == "response.inject"
                        for item in request["input"]}
            assert injected == {"research-call": "record:alpha", "review-call": "record:beta"}
            assert len(connections) == 1
            if stream:
                raw = [event.data for event in events if event.type == "raw_response_event"]
                activities = [raw_dict(event.item) for event in raw if event.type == "response.output_item.done"]
                assert any(item["type"] == "multi_agent_call" for item in activities)
                assert any(item.get("agent", {}).get("agent_name") == "/root/reviewer" and
                           item.get("content", [{}])[0].get("text") == "Specialist final." for item in activities)


@pytest.mark.asyncio
async def test_f12_t14():
    from velmora.extensions.experimental.hosted_multi_agent import OpenAIHostedMultiAgentModel
    from velmora import RunContextWrapper
    started, release = asyncio.Event(), asyncio.Event()

    @function_tool
    async def wait_for_application(value: str) -> str:
        started.set()
        await release.wait()
        return "continued:" + value

    call = dict(function_call(wait_for_application.name, {"value": "entry"}, "live-call").model_dump(exclude_none=True),
                agent={"agent_name": "/root/researcher"}, status="completed")
    async with hosted_socket(calls=[call], final_items=[hosted_message("Live work finished.")]) as (model, requests, connections):
        agent = Agent(name="Active root", model=model, tools=[wait_for_application])
        context = RunContextWrapper(context=None)
        first = asyncio.create_task(execution_run(agent, context=context))
        try:
            await bounded(started.wait(), timeout=10)
            with pytest.raises(UserError):
                await execution_run(agent, context=context)
        finally:
            release.set()
        result = await bounded(first, timeout=15)
        assert result.final_output == "Live work finished."
        assert len(connections) == 1
        assert [item["type"] for item in requests] == ["response.create", "response.inject"]
        assert requests[1]["input"] == [{"type": "function_call_output", "call_id": "live-call", "output": "continued:entry"}]

    @function_tool(needs_approval=True)
    def approval() -> str:
        return "protected"

    async def dynamic(context, parameters, identity):
        return False

    @function_tool(needs_approval=dynamic)
    def dynamic_approval() -> str:
        return "protected"

    for tools, handoffs in [([], [Agent(name="Local handoff")]), ([approval], []), ([dynamic_approval], [])]:
        async with AsyncOpenAI(api_key="local-peer", base_url="http://127.0.0.1:1/v1", max_retries=0) as client:
            model = OpenAIHostedMultiAgentModel(model="hosted-capable", openai_client=client)
            try:
                with pytest.raises(UserError):
                    await execution_run(Agent(name="Invalid root", model=model, tools=tools, handoffs=handoffs))
            finally:
                await model.close()
