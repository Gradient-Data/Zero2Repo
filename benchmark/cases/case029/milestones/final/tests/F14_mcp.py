# feature: F14
"""Acceptance of local MCP capabilities through real protocol connections."""
import json

import pytest

from _helpers import invoke
from mcp.shared.exceptions import MCPError
from F01_helpers import RecordingModel, function_call, run_agent
from F03_helpers import tool_outputs
from F04_helpers import execution_run
from F08_helpers import pending_calls
from F14_helpers import LocalCatalog, http_catalog, mcp_turn
from velmora import Agent, UserError
from velmora import ToolInputGuardrailTripwireTriggered, ToolOutputGuardrailTripwireTriggered
from velmora.mcp import MCPServerManager, create_static_tool_filter
from velmora import ToolGuardrailFunctionOutput, ToolInputGuardrail, ToolOutputGuardrail


@pytest.mark.asyncio
async def test_f14_t01(tmp_path):
    for transport in ("stdio", "sse", "http"):
        catalog = LocalCatalog(tmp_path / transport)

        async def exercise(server):
            with pytest.raises(UserError):
                await invoke(server.call_tool, "write", {"value": "before"})
            async with server:
                result, model = await mcp_turn([server], value="transport-value")
                assert result.final_output == "Finished."
                output = tool_outputs(model.requests[1])["remote"]
                assert json.loads(output[0]["text"]) == {
                    "server": "catalog", "tool": "write", "reversed": "eulav-tropsnart"}
                assert catalog.records(catalog.effects) == [
                    {"server": "catalog", "tool": "write", "value": "transport-value"}]
                # The application's selected formatter is an observable error policy.
                _, failed = await mcp_turn([server], value="fail", config={
                    "failure_error_function": lambda context, error: "Application failure."})
                assert tool_outputs(failed.requests[1])["remote"] == "Application failure."
                with pytest.raises(UserError):
                    await mcp_turn([server], value="fail", config={"failure_error_function": None})
            with pytest.raises(UserError):
                await invoke(server.call_tool, "write", {"value": "after"})
        if transport == "stdio":
            await exercise(catalog.client())
        else:
            async with http_catalog(catalog, transport) as server:
                await exercise(server)


@pytest.mark.asyncio
async def test_f14_t02(tmp_path):
    # Prompts span many pages: no default page limit, and a limit equal to the page count suffices.
    catalog = LocalCatalog(tmp_path, pages=24)
    for limit in (None, 3, 24):
        options = {} if limit is None else {"max_list_pages": limit}
        async with catalog.client(**options) as server:
            assert {t.name for t in await invoke(server.list_tools)} == {"write", "inspect", "erase"}
            if limit == 3:
                continue
            prompts = await invoke(server.list_prompts)
            assert {p.name for p in prompts.prompts} == {f"prompt_{i}" for i in range(24)}
            assert prompts.next_cursor is None
    for mode, options in (("normal", {"max_list_pages": 2}), ("repeat", {}), ("fail", {})):
        catalog.settings["mode"] = mode
        catalog.save()
        async with catalog.client(**options) as server:
            with pytest.raises(UserError):
                await invoke(server.list_tools)
            with pytest.raises(UserError):
                await invoke(server.list_prompts)


@pytest.mark.asyncio
async def test_f14_t03(tmp_path):
    catalog = LocalCatalog(tmp_path)
    (tmp_path / "resource.txt").write_text("Server-owned resource body.\nSecond line.")
    async with catalog.client() as server:
        for method, field, prefix in ((server.list_resources, "resources", "memo"),
                                       (server.list_resource_templates, "resource_templates", "template")):
            first = await invoke(method)
            assert [r.name for r in getattr(first, field)] == [f"{prefix}_0"]
            assert first.next_cursor == "1"
            second = await invoke(method, cursor=first.next_cursor)
            assert [r.name for r in getattr(second, field)] == [f"{prefix}_1"]
            assert second.next_cursor == "2"
            last = await invoke(method, cursor=second.next_cursor)
            assert [r.name for r in getattr(last, field)] == [f"{prefix}_2"]
            assert last.next_cursor is None
            assert getattr(second, field)[0].description == (
                "Resource page 1" if prefix == "memo" else "Template page 1")
        resource = await invoke(server.read_resource, "memo://page/1")
        assert [(str(c.uri), c.text) for c in resource.contents] == [
            ("memo://page/1", "Server-owned resource body.\nSecond line.")]


@pytest.mark.asyncio
async def test_f14_t04(tmp_path):
    catalog = LocalCatalog(tmp_path / "filter")
    async with catalog.client(tool_filter=create_static_tool_filter(
            allowed_tool_names=["write", "inspect"], blocked_tool_names=["inspect"])) as server:
        _, model = await mcp_turn([server])
        assert {t.name for t in model.requests[0]["tools"]} == {"write"}
    seen = []

    async def choose(ctx, tool):
        seen.append((ctx.agent.name, ctx.run_context.context, tool.name))
        return tool.name == ctx.run_context.context["selected"]

    async with catalog.client(tool_filter=choose) as server:
        for selected in ("inspect", "erase"):
            _, model = await mcp_turn([server], name=selected, context={"selected": selected})
            assert {t.name for t in model.requests[0]["tools"]} == {selected}
        assert {name for _, _, name in seen} == {"write", "inspect", "erase"}
        assert all(agent == "MCP application" for agent, _, _ in seen)
        assert {ctx["selected"] for _, ctx, _ in seen} == {"inspect", "erase"}
    left, right = LocalCatalog(tmp_path / "left", name="left"), LocalCatalog(tmp_path / "right", name="right")
    async with left.client() as a, right.client() as b:
        for owner in ("left", "right"):
            _, model = await mcp_turn([a, b], name=f"mcp_{owner}__write", value=owner,
                                     config={"include_server_in_tool_names": True})
            assert {t.name for t in model.requests[0]["tools"]} == {
                f"mcp_{s}__{t}" for s in ("left", "right") for t in ("write", "inspect", "erase")}
            assert json.loads(tool_outputs(model.requests[1])["remote"][0]["text"]) == {
                "server": owner, "tool": "write", "reversed": owner[::-1]}
    for peer in (left, right):
        assert peer.records(peer.effects) == [{"server": peer.settings["name"], "tool": "write",
                                               "value": peer.settings["name"]}]


@pytest.mark.asyncio
async def test_f14_t05(tmp_path):
    catalog = LocalCatalog(tmp_path)
    # A valid transparent PNG is carried as usable model image input.
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    blocks = [{"type": "text", "text": "Remote text."},
              {"type": "image", "data": png, "mimeType": "image/png"},
              {"type": "resource", "resource": {"uri": "memo://embedded", "text": "Embedded body."}}]
    for prefer, structured, is_error in ((False, None, False), (False, {"answer": [7, 11]}, False), (True, {"answer": [7, 11]}, False),
                                          (True, {}, False), (True, {"answer": "ignored"}, True)):
        response = {"content": blocks, "isError": is_error}
        if structured is not None:
            response["structuredContent"] = structured
        (tmp_path / "result.json").write_text(json.dumps(response))
        async with catalog.client(use_structured_content=prefer) as server:
            _, model = await mcp_turn([server])
        output = tool_outputs(model.requests[1])["remote"]
        if prefer and structured and not is_error:
            assert json.loads(output) == structured
        else:
            assert output[0] == {"type": "input_text", "text": "Remote text."}
            assert output[1] == {"type": "input_image", "image_url": f"data:image/png;base64,{png}"}
            embedded = json.loads(output[2]["text"])
            assert embedded["type"] == "resource"
            assert embedded["resource"]["text"] == "Embedded body."
            assert embedded["resource"]["uri"] == "memo://embedded"


@pytest.mark.asyncio
async def test_f14_t06(tmp_path):
    for policy in ("always", {"write": "always", "inspect": "never"},
                   lambda context, agent, tool: tool.name == "write"):
        catalog = LocalCatalog(tmp_path / f"approval-{len(list(tmp_path.iterdir()))}")
        async with catalog.client(require_approval=policy) as server:
            model = RecordingModel([function_call("write", {"value": "approved"}, "approval"),
                                     function_call("inspect", {"value": "free"}, "free")], "Finished.")
            agent = Agent(name="Approval owner", model=model, mcp_servers=[server])
            first = await run_agent(agent)
            pending = pending_calls(first)
            assert set(pending) == ({"approval", "free"} if policy == "always" else {"approval"})
            assert catalog.records(catalog.effects) == ([] if policy == "always" else [
                {"server": "catalog", "tool": "inspect", "value": "free"}])
            state = first.to_state()
            for item in pending.values():
                state.approve(item)
            assert (await execution_run(agent, state)).final_output == "Finished."
            assert {r["value"] for r in catalog.records(catalog.effects)} == {"approved", "free"}
    for kind, action in (("input", "allow"), ("input", "stop"),
                         ("output", "replace"), ("output", "stop")):
        catalog = LocalCatalog(tmp_path / f"{kind}-{action}")
        seen = []
        value = f"{kind}{action}"

        def review(data):
            # Guardrails review the actual call: arguments before, server output after.
            if kind == "input":
                assert json.loads(data.context.tool_arguments) == {"value": value}
            else:
                assert data.output["type"] == "text"
                assert json.loads(data.output["text"]) == {
                    "server": "catalog", "tool": "write", "reversed": value[::-1]}
            seen.append(data)
            if action == "allow":
                return ToolGuardrailFunctionOutput.allow()
            if action == "replace":
                return ToolGuardrailFunctionOutput.reject_content("Reviewed replacement.")
            return ToolGuardrailFunctionOutput.raise_exception()
        options = {f"tool_{kind}_guardrails": [
            ToolInputGuardrail(review) if kind == "input" else ToolOutputGuardrail(review)]}
        async with catalog.client(**options) as server:
            if action == "stop":
                error = (ToolInputGuardrailTripwireTriggered if kind == "input"
                         else ToolOutputGuardrailTripwireTriggered)
                with pytest.raises(error):
                    await mcp_turn([server], value=value)
            else:
                _, model = await mcp_turn([server], value=value)
                output = tool_outputs(model.requests[1])["remote"]
                if action == "replace":
                    assert output == "Reviewed replacement."
                else:
                    assert json.loads(output[0]["text"])["reversed"] == value[::-1]
        assert len(seen) == 1
        assert catalog.records(catalog.effects) == ([] if kind == "input" and action == "stop" else [
            {"server": "catalog", "tool": "write", "value": value}])
    catalog = LocalCatalog(tmp_path / "formatter")
    async with catalog.client(failure_error_function=lambda ctx, err: "Server policy.") as server:
        _, model = await mcp_turn([server], value="fail", config={
            "failure_error_function": lambda ctx, err: "Agent policy."})
        assert tool_outputs(model.requests[1])["remote"] == "Server policy."


@pytest.mark.asyncio
async def test_f14_t07(tmp_path):
    catalog = LocalCatalog(tmp_path)
    (tmp_path / "prompt.txt").write_text("Discuss this supplied topic: ")
    async with catalog.client() as server:
        listing = await invoke(server.list_prompts)
        assert {p.name for p in listing.prompts} == {"prompt_0", "prompt_1", "prompt_2"}
        for topic in ("ocean tides", "volcanic rock"):
            prompt = await invoke(server.get_prompt, "prompt_2", {"topic": topic})
            assert [(m.role, m.content.type, m.content.text) for m in prompt.messages] == [
                ("user", "text", "Discuss this supplied topic: " + topic)]
        with pytest.raises(MCPError):
            await invoke(server.get_prompt, "missing", {"topic": "absent"})
    with pytest.raises(UserError):
        await invoke(server.get_prompt, "prompt_2", {"topic": "disconnected"})


@pytest.mark.asyncio
async def test_f14_t08(tmp_path):
    good = LocalCatalog(tmp_path / "good", name="good")
    failing = LocalCatalog(tmp_path / "bad", name="bad", enabled=False)
    a, b = good.client(), failing.client()
    async with MCPServerManager(servers=[a, b, a]) as manager:
        assert manager.active_servers == [a]
        assert manager.failed_servers == [b]
        assert set(manager.errors) == {b}
        assert isinstance(manager.errors[b], BaseException)
        _, model = await mcp_turn(manager.active_servers, value="managed")
        assert json.loads(tool_outputs(model.requests[1])["remote"][0]["text"])["server"] == "good"
        assert len(good.records(good.starts)) == 1
        failing.settings["enabled"] = True
        failing.save()
        assert set(await invoke(manager.reconnect)) == {a, b}
        assert manager.failed_servers == [] and manager.errors == {}
        assert len(good.records(good.starts)) == 1
        assert len(failing.records(failing.starts)) == 1
        assert set(await invoke(manager.reconnect, failed_only=False)) == {a, b}
        assert len(good.records(good.starts)) == 2
        assert len(failing.records(failing.starts)) == 2
        for server, catalog in ((a, good), (b, failing)):
            _, model = await mcp_turn([server], value="reconnected")
            assert json.loads(tool_outputs(model.requests[1])["remote"][0]["text"])["server"] == catalog.settings["name"]
    failing.settings["enabled"] = False
    failing.save()
    strict = MCPServerManager(servers=[failing.client(), good.client()], strict=True)
    with pytest.raises(Exception) as caught:
        async with strict:
            pytest.fail("Strict manager accepted a failed connection.")
    assert not isinstance(caught.value, AssertionError)
    assert strict.failed_servers
