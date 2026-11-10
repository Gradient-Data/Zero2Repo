# feature: F07
"""Acceptance coverage for conversation history and continuation ownership."""
import json

import pytest
from openai import AsyncOpenAI

from F01_helpers import RecordingModel, function_call
from F02_helpers import model_peer, response_payload
from F04_helpers import execution_run, execution_tool, conversation_text
from F07_helpers import ApplicationSession, durable_session_operation, session_user_item
from _helpers import parse_json, consume
from velmora import (Agent, SQLiteSession, RunConfig, OutputGuardrail, Runner,
                    GuardrailFunctionOutput, OutputGuardrailTripwireTriggered,
                    OpenAIResponsesModel, UserError)
from velmora import SessionSettings


@pytest.mark.asyncio
async def test_session_operations_and_identity(tmp_path):
    path = tmp_path / "history.db"
    left = SQLiteSession(session_id="left", db_path=path)
    same = SQLiteSession(session_id="left", db_path=path)
    right = SQLiteSession(session_id="right", db_path=path)
    try:
        history = [session_user_item("first"), session_user_item("second"), session_user_item("first")]
        await left.add_items(history[:2])
        await left.add_items(history[2:])
        await right.add_items([session_user_item("separate")])
        assert await same.get_items() == history
        assert await right.get_items() == [session_user_item("separate")]
        assert await same.pop_item() == history[-1]
        assert await left.get_items() == history[:-1]
        for name, session, prompt, answer in [
            ("one", left, "new turn", "first answer"),
            ("two", same, "next turn", "second answer"),
        ]:
            before = await session.get_items()
            model = RecordingModel(answer)
            result = await execution_run(Agent(name=name, model=model), prompt, session=session)
            assert result.final_output == answer
            assert model.requests[0]["input"] == before + [session_user_item(prompt)]
        assert conversation_text(await left.get_items()) == ["first answer", "second answer"]
        await same.clear_session()
        assert await left.get_items() == []
        assert await left.pop_item() is None
        assert await right.get_items() == [session_user_item("separate")]
    finally:
        left.close()
        same.close()
        right.close()


@pytest.mark.asyncio
async def test_run_history_merge_and_occurrences(tmp_path):
    session = SQLiteSession(session_id="merge", db_path=tmp_path / "merge.db")
    try:
        history = [session_user_item("same content"), session_user_item("older context"), session_user_item("drop from model")]
        await session.add_items(history)
        model = RecordingModel("ordinary answer", "merged answer")
        agent = Agent(name="merge", model=model)
        await execution_run(agent, "ordinary", session=session)
        assert model.requests[0]["input"] == history + [session_user_item("ordinary")]
        before = await session.get_items()
        assert before[:4] == history + [session_user_item("ordinary")]
        assert conversation_text(before) == ["ordinary answer"]
        observed = []

        async def merge(old, new):
            observed.append((old, new))
            return [new[1], old[1], old[0], old[0], new[0]]

        incoming = [session_user_item("same content"), session_user_item("new selection"), session_user_item("discard new")]
        result = await execution_run(agent, incoming, session=session,
            config=RunConfig(tracing_disabled=True, session_input_callback=merge))
        assert observed == [(before, incoming)]
        assert model.requests[1]["input"] == [incoming[1], history[1], history[0], history[0], incoming[0]]
        assert result.final_output == "merged answer"
        saved = await session.get_items()
        assert saved[:-1] == before + [incoming[1], incoming[0]]
        assert conversation_text(saved[-1:]) == ["merged answer"]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_history_limits_and_run_override(tmp_path):
    path = tmp_path / "limits.db"
    history = [session_user_item(f"context {i}") for i in range(5)]
    session = SQLiteSession(session_id="limits", db_path=path)
    limited = SQLiteSession(session_id="limits", db_path=path, session_settings=SessionSettings(limit=2))
    try:
        await session.add_items(history)
        assert await session.get_items() == history
        assert await session.get_items(limit=3) == history[-3:]
        assert await session.get_items(limit=20) == history
        assert await session.get_items(limit=0) == []
        assert await limited.get_items() == history[-2:]
        for limit, selected in [(None, history[-2:]), (4, history[-4:]), (0, [])]:
            # Restore identical stored state so only retrieval policy varies.
            await session.clear_session()
            await session.add_items(history)
            model = RecordingModel("answer")
            config = RunConfig(tracing_disabled=True, session_settings=SessionSettings(limit=limit))
            result = await execution_run(Agent(name="limits", model=model), "current",
                                         session=limited, config=config)
            assert result.final_output == "answer"
            assert model.requests[0]["input"] == selected + [session_user_item("current")]
            assert (await session.get_items())[:-1] == history + [session_user_item("current")]
    finally:
        session.close()
        limited.close()

    # Application sessions predating retrieval settings remain usable by runs.
    legacy = ApplicationSession("legacy", tmp_path / "legacy.db")
    try:
        await legacy.add_items(history)
        model = RecordingModel("legacy answer")
        result = await execution_run(Agent(name="legacy", model=model), "current", session=legacy,
            config=RunConfig(tracing_disabled=True, session_settings=SessionSettings(limit=2)))
        assert result.final_output == "legacy answer"
        assert model.requests[0]["input"] == history[-2:] + [session_user_item("current")]
        assert (await legacy.get_items())[:-1] == history + [session_user_item("current")]
    finally:
        legacy.close()


@pytest.mark.asyncio
async def test_durable_backends_and_application_session(tmp_path):
    original = [session_user_item("persisted α"), session_user_item("second"), session_user_item("persisted α")]
    for kind in ("sqlite", "async_sqlite", "sqlalchemy"):
        path = str(tmp_path / f"{kind}.db")

        durable_session_operation(kind, path, "write", items=original[:2])
        durable_session_operation(kind, path, "write", items=original[2:])
        assert parse_json(durable_session_operation(kind, path, "read")) == original
        assert parse_json(durable_session_operation(kind, path, "read", identity="different")) == []
        isolated = [session_user_item("independent conversation")]
        durable_session_operation(kind, path, "write", identity="different", items=isolated)
        assert parse_json(durable_session_operation(kind, path, "pop")) == original[-1]
        assert parse_json(durable_session_operation(kind, path, "read")) == original[:-1]
        durable_session_operation(kind, path, "clear")
        assert parse_json(durable_session_operation(kind, path, "read")) == []
        assert parse_json(durable_session_operation(kind, path, "pop")) is None
        assert parse_json(durable_session_operation(kind, path, "read", identity="different")) == isolated

    session = ApplicationSession("application", tmp_path / "application.db")
    try:
        model = RecordingModel("saved answer", "continued answer")
        agent = Agent(name="custom backend", model=model)
        await execution_run(agent, "saved input", session=session)
        stored = await session.get_items()
        assert stored[0] == session_user_item("saved input")
        assert conversation_text(stored) == ["saved answer"]
        result = await execution_run(agent, "continue", session=session)
        assert result.final_output == "continued answer"
        assert model.requests[1]["input"] == stored + [session_user_item("continue")]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_responses_server_continuation():
    for options in ({"conversation_id": "conv_owned"},
                    {"previous_response_id": "resp_before"},
                    {"auto_previous_response_id": True}):
        first = response_payload("unused")
        first["id"] = "resp_tool_turn"
        first["output"] = [function_call("record", {"value": "continuation"}, "call_continue").model_dump()]
        last = response_payload("server answer")
        effects = []
        with model_peer(replies=[(200, first, {}), (200, last, {})]) as (url, requests):
            async with AsyncOpenAI(base_url=url, api_key="local", max_retries=0) as client:
                agent = Agent(name="server", model=OpenAIResponsesModel(model="peer-model", openai_client=client),
                              tools=[execution_tool(effects)])
                result = await execution_run(agent, "new request", **options)
        assert result.final_output == "server answer"
        assert effects == ["continuation"]
        assert len(requests) == 2
        initial, following = [request["body"] for request in requests]
        assert initial["input"] == [session_user_item("new request")]
        assert following["input"] == [{"type": "function_call_output", "call_id": "call_continue",
                                        "output": "recorded:continuation"}]
        if "conversation_id" in options:
            assert initial["conversation"] == "conv_owned"
            assert following["conversation"] == "conv_owned"
        else:
            assert initial.get("previous_response_id") == options.get("previous_response_id")
            assert following["previous_response_id"] == "resp_tool_turn"


@pytest.mark.asyncio
async def test_session_rejects_server_history_ownership(tmp_path):
    session = SQLiteSession(session_id="ownership", db_path=tmp_path / "ownership.db")
    try:
        for options in ({"conversation_id": "conv_history"},
                        {"previous_response_id": "resp_history"},
                        {"auto_previous_response_id": True}):
            for use_session, continuation in [(True, {}), (False, options)]:
                model = RecordingModel("valid")
                result = await execution_run(Agent(name="valid", model=model), "input",
                    **({"session": session} if use_session else {}), **continuation)
                assert result.final_output == "valid"
            before = await session.get_items()
            with pytest.raises(UserError):
                await execution_run(Agent(name="conflict", model=RecordingModel("unused")),
                                    "input", session=session, **options)
            assert await session.get_items() == before
            # Streamed runs have the same ownership rule; the rejection may surface
            # when the run is started or while its events are consumed.
            unused = RecordingModel("unused")
            with pytest.raises(UserError):
                streamed = Runner.run_streamed(Agent(name="conflict", model=unused), "input",
                    run_config=RunConfig(tracing_disabled=True), session=session, **options)
                await consume(streamed.stream_events(), timeout=10)
            assert unused.requests == []
            assert await session.get_items() == before
    finally:
        session.close()


@pytest.mark.asyncio
async def test_guardrail_rejection_retains_completed_tools(tmp_path):
    session = SQLiteSession(session_id="reject", db_path=tmp_path / "reject.db")
    effects = []

    def reject(context, agent, output):
        return GuardrailFunctionOutput(output_info="application verdict", tripwire_triggered=True)

    try:
        model = RecordingModel([function_call("record", {"value": "kept"}, "call_kept")],
                               "rejected candidate")
        agent = Agent(name="reject", model=model, tools=[execution_tool(effects)],
                      output_guardrails=[OutputGuardrail(guardrail_function=reject)])
        with pytest.raises(OutputGuardrailTripwireTriggered):
            await execution_run(agent, "do work", session=session)
        stored = await session.get_items()
        assert effects == ["kept"]
        assert stored[0] == session_user_item("do work")
        assert [item.get("type") for item in stored[1:]] == ["function_call", "function_call_output"]
        assert stored[1]["call_id"] == stored[2]["call_id"] == "call_kept"
        assert stored[1]["name"] == "record"
        assert json.loads(stored[1]["arguments"]) == {"value": "kept"}
        assert stored[2]["output"] == "recorded:kept"
        resumed = RecordingModel("accepted continuation")
        result = await execution_run(Agent(name="next", model=resumed), "continue", session=session)
        assert resumed.requests[0]["input"] == stored + [session_user_item("continue")]
        assert result.final_output == "accepted continuation"
        assert conversation_text(await session.get_items()) == ["accepted continuation"]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_guardrail_callback_failure_and_save_precedence(tmp_path):
    for fail_save in (False, True):
        session = ApplicationSession("callback", tmp_path / f"callback-{fail_save}.db")
        callback_error = RuntimeError("Application guardrail failed")
        save_error = OSError("Application store refused write")

        def fail(context, agent, output):
            if fail_save:
                session.write_error = save_error
            raise callback_error

        try:
            model = RecordingModel("completed final answer")
            agent = Agent(name="callback", model=model,
                          output_guardrails=[OutputGuardrail(guardrail_function=fail)])
            expected = save_error if fail_save else callback_error
            with pytest.raises(type(expected)) as caught:
                await execution_run(agent, "candidate request", session=session)
            assert caught.value is expected
            if fail_save:
                assert conversation_text(session.failed_items) == ["completed final answer"]
            else:
                stored = await session.get_items()
                assert stored[0] == session_user_item("candidate request")
                assert conversation_text(stored) == ["completed final answer"]
                resumed = RecordingModel("next answer")
                result = await execution_run(Agent(name="next", model=resumed), "continue", session=session)
                assert result.final_output == "next answer"
                assert resumed.requests[0]["input"] == stored + [session_user_item("continue")]
        finally:
            session.close()
