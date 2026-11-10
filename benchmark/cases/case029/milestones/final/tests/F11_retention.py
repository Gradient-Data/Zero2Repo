# feature: F11
"""Acceptance tests for conversation retention, branching and protection."""
import copy

import pytest

from F01_helpers import RecordingModel, function_call, text_message
from F02_helpers import AttemptModel
from F07_helpers import ApplicationSession, session_user_item
from F11_helpers import (compaction_peer, retention_run, advanced_store,
                         build_application_clock, encrypted_success, RetentionUsageModel,
                         IdentityModel)
from velmora import SQLiteSession
from velmora import OpenAIResponsesCompactionSession
from velmora.extensions.memory.encrypt_session import EncryptedSession


@pytest.mark.asyncio
async def test_compaction_triggers_and_later_history(tmp_path):
    summary = [{"type": "compaction", "id": "cmp_kept", "encrypted_content": "provider-summary"}]
    with compaction_peer(summary) as (client, requests):
        store = SQLiteSession(session_id="threshold", db_path=tmp_path / "threshold.db")
        session = OpenAIResponsesCompactionSession(session_id="threshold", underlying_session=store, client=client)
        try:
            # Neither user messages nor existing compaction entries count toward ten.
            await session.add_items([session_user_item("question")] * 12 + summary + [
                function_call("retained_lookup", {}, "retained_call").model_dump(),
                {"type": "function_call_output", "call_id": "retained_call", "output": "retained result"},
            ])
            # Tool calls and their outputs are eligible alongside assistant messages.
            for index in range(7):
                result = await retention_run(AttemptModel(f"answer {index}"), session)
                assert result.final_output == f"answer {index}"
            assert requests == []
            before = await store.get_items()
            model = AttemptModel("tenth answer", "after compression")
            await retention_run(model, session)
            assert len(requests) == 1
            assert requests[0]["path"] == "/v1/responses/compact"
            assert requests[0]["body"]["input"][:len(before)] == before
            assert await store.get_items() == summary
            await retention_run(model, session, "next question")
            assert model.requests[1]["input"] == summary + [session_user_item("next question")]
        finally:
            store.close()
        for decision in (False, True):
            store = SQLiteSession(session_id=str(decision))
            session = OpenAIResponsesCompactionSession(session_id=str(decision), underlying_session=store, client=client,
                                                       should_trigger_compaction=lambda _, d=decision: d)
            try:
                count = len(requests)
                await retention_run(AttemptModel("custom answer"), session)
                assert len(requests) == count + int(decision)
                if decision:
                    assert await store.get_items() == summary
                else:
                    assert len(await store.get_items()) == 2
                    await session.run_compaction({"force": True})
                    assert len(requests) == count + 1
                    assert await store.get_items() == summary
            finally:
                store.close()


@pytest.mark.asyncio
async def test_compaction_continuation_selection():
    summary = [session_user_item("compacted context")]
    with compaction_peer(summary) as (client, requests):
        # Automatic mode must also remember that the last run explicitly disabled storage,
        # both for run-triggered compaction and for a later explicit request after the
        # run's automatic decision declined.
        cases = [(identity, stored, explicit)
                 for identity, stored in (("resp_saved", True), ("resp_unsaved", False))
                 for explicit in (False, True)] + [(None, True, False), ("", True, False)]
        for identity, stored, explicit in cases:
            store = SQLiteSession(session_id="selection")
            session = OpenAIResponsesCompactionSession(session_id="selection", underlying_session=store, client=client,
                                                       should_trigger_compaction=lambda _, e=explicit: not e)
            try:
                if not identity:
                    # Missing and empty response identities both prevent run-triggered work.
                    model = IdentityModel(identity, "completed")
                else:
                    model = AttemptModel("completed")
                from velmora import ModelSettings, Agent, Runner, RunConfig
                count_before = len(requests)
                await Runner.run(Agent(name="Selection", model=model,
                                       model_settings=ModelSettings(store=stored)),
                                 "selection question", session=session,
                                 run_config=RunConfig(tracing_disabled=True))
                if not identity or explicit:
                    assert len(requests) == count_before
                    await session.run_compaction({"force": True})
                assert len(requests) == count_before + 1
                body = requests[-1]["body"]
                if identity and stored:
                    assert body["previous_response_id"] == "resp_app"
                    assert "input" not in body
                else:
                    assert "previous_response_id" not in body
                    assert body["input"][0] == session_user_item("selection question")
                    assert body["input"][-1]["content"][0]["text"] == "completed"
                assert await store.get_items() == summary
            finally:
                store.close()


@pytest.mark.asyncio
async def test_compaction_visibility_and_concurrent_history(tmp_path):
    summary = [session_user_item("approved condensed context")]
    hidden = session_user_item("private omitted history")
    with compaction_peer(summary) as (client, requests):
        for custom in (False, True):
            store = (ApplicationSession("visibility", tmp_path / "custom.db") if custom
                     else SQLiteSession(session_id="visibility", db_path=tmp_path / "native.db"))
            session = OpenAIResponsesCompactionSession(session_id="visibility", underlying_session=store, client=client,
                compaction_mode="input", should_trigger_compaction=lambda _: True)
            try:
                await store.add_items([hidden, session_user_item("visible tail")])
                model = AttemptModel("filtered answer", "fully visible answer")
                count = len(requests)
                await retention_run(model, session, session_input_callback=lambda h, n: h[1:] + n)
                assert hidden not in model.requests[0]["input"]
                retained = await store.get_items()
                assert retained[0] == hidden
                if custom:
                    assert retained[-1]["content"][0]["text"] == "filtered answer"
                    assert len(requests) == count
                else:
                    assert len(requests) == count + 1
                    assert hidden not in requests[-1]["body"]["input"]
                    assert retained == [hidden] + summary
                await retention_run(model, session)
                assert hidden in model.requests[1]["input"]
                assert hidden in requests[-1]["body"]["input"]
                assert await store.get_items() == summary
            finally:
                store.close()
        store = SQLiteSession(session_id="concurrent", db_path=tmp_path / "concurrent.db")
        session = OpenAIResponsesCompactionSession(session_id="concurrent", underlying_session=store, client=client,
            compaction_mode="input", should_trigger_compaction=lambda _: True)
        newer = session_user_item("concurrent contribution")
        async def concurrent_exchange():
            # A different writer appends after the model received its history.
            other = SQLiteSession(session_id="concurrent", db_path=tmp_path / "concurrent.db")
            try:
                await other.add_items([newer])
            finally:
                other.close()
            return [text_message("finished exchange")]
        try:
            await store.add_items([session_user_item("old contribution")])
            count = len(requests)
            model = AttemptModel(concurrent_exchange)
            await retention_run(model, session)
            assert newer not in model.requests[0]["input"]
            retained = await store.get_items()
            assert len(retained) == 4
            assert retained[0] == session_user_item("old contribution")
            assert retained.count(newer) == 1
            assert retained.count(session_user_item("Continue.")) == 1
            assert retained[-1]["content"][0]["text"] == "finished exchange"
            if len(requests) > count:
                assert newer not in requests[-1]["body"]["input"]
        finally:
            store.close()


@pytest.mark.asyncio
async def test_branch_prefix_independence_and_deletion(tmp_path):
    session = advanced_store(tmp_path / "branches.db")
    history = [session_user_item("first"), {"role": "assistant", "content": "first answer"},
               session_user_item("second"), {"role": "assistant", "content": "second answer"}]
    try:
        await session.add_items(history)
        initial = next(b["branch_id"] for b in await session.list_branches() if b["is_current"])
        branch = await session.create_branch_from_turn(2, "alternative")
        assert branch == "alternative"
        assert await session.get_items() == history[:2]
        await session.add_items([session_user_item("alternative continuation")])
        branches = {b["branch_id"]: b for b in await session.list_branches()}
        assert branches[branch]["is_current"] is True
        assert branches[branch]["message_count"] == 3
        assert branches[initial]["user_turns"] == 2
        await session.switch_to_branch(initial)
        assert await session.get_items() == history
        await session.add_items([session_user_item("initial continuation")])
        await session.switch_to_branch(branch)
        assert await session.get_items() == history[:2] + [session_user_item("alternative continuation")]
        await session.switch_to_branch(initial)
        await session.delete_branch(branch)
        assert await session.get_items() == history + [session_user_item("initial continuation")]
        assert {b["branch_id"] for b in await session.list_branches()} == {initial}
    finally:
        session.close()


@pytest.mark.asyncio
async def test_branch_rejections_and_reserved_identities(tmp_path):
    session = advanced_store(tmp_path / "rejections.db")
    try:
        await session.add_items([{"role": "assistant", "content": "preamble"}])
        with pytest.raises(ValueError):
            await session.create_branch_from_turn(1, "no-user")
        await session.add_items([session_user_item("first"), session_user_item("second")])
        initial = next(b["branch_id"] for b in await session.list_branches() if b["is_current"])
        for turn, name in ((2, "   "), (999, "missing-turn")):
            with pytest.raises(ValueError):
                await session.create_branch_from_turn(turn, name)
        with pytest.raises(ValueError):
            await session.delete_branch(initial, force=True)
        assert await session.get_conversation_turns(branch_id="unknown-branch") == []
        for entry in (session.switch_to_branch, session.delete_branch):
            with pytest.raises(ValueError):
                await entry("unknown-branch")
        branch = await session.create_branch_from_turn(2, "reserved")
        await session.add_items([session_user_item("alternative")])
        with pytest.raises(ValueError):
            await session.create_branch_from_turn(2, branch)
        with pytest.raises(ValueError):
            await session.delete_branch(branch)
        assert next(b["branch_id"] for b in await session.list_branches() if b["is_current"]) == branch
        await session.delete_branch(branch, force=True)
        assert next(b["branch_id"] for b in await session.list_branches() if b["is_current"]) == initial
        with pytest.raises(ValueError):
            await session.create_branch_from_turn(2, branch)
        await session.clear_session()
        await session.add_items([session_user_item("after clearing")])
        with pytest.raises(ValueError):
            await session.create_branch_from_turn(1, branch)
        assert await session.get_items() == [session_user_item("after clearing")]
        session.close()
        session = advanced_store(tmp_path / "rejections.db")
        with pytest.raises(ValueError):
            await session.create_branch_from_turn(1, branch)
        assert await session.get_items() == [session_user_item("after clearing")]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_turn_content_tool_and_explicit_usage_analytics(tmp_path):
    session = advanced_store(tmp_path / "analytics.db")
    try:
        await session.add_items([session_user_item("ordinary prefix 30XXQ target")])
        initial = (await session.list_branches())[0]["branch_id"]
        call_a = function_call("lookup", {"key": "a"}, "call_a").model_dump()
        call_b = function_call("lookup", {"key": "b"}, "call_b").model_dump()
        await session.add_items([session_user_item("literal 30%_ target"), call_a,
                                {"type": "function_call_output", "call_id": "call_a", "output": "a"},
                                call_b, {"type": "function_call_output", "call_id": "call_b", "output": "b"}])
        await session.add_items([session_user_item("another 30%_ target"),
                                function_call("render", {}, "call_c").model_dump(),
                                {"type": "function_call_output", "call_id": "call_c", "output": "rendered"}])
        turns = await session.get_conversation_turns()
        assert [(t["turn"], t["full_content"]) for t in turns] == [
            (1, "ordinary prefix 30XXQ target"), (2, "literal 30%_ target"), (3, "another 30%_ target")]
        assert [t["turn"] for t in await session.find_turns_by_content("30%_")] == [2, 3]
        assert await session.find_turns_by_content("30ZZ target") == []
        assert set(await session.get_tool_usage()) == {("lookup", 2, 2), ("render", 1, 3)}
        grouped = await session.get_conversation_by_turns()
        assert {turn: len(messages) for turn, messages in grouped.items()} == {1: 1, 2: 5, 3: 3}
        assert [message["tool_name"] for message in grouped[2]].count("lookup") == 2
        assert [message["tool_name"] for message in grouped[3]].count("render") == 1
        assert await session.get_turn_usage(3) == {}
        with pytest.raises(ValueError):
            await session.create_branch_from_content("absent literal", "no-match")
        branch = await session.create_branch_from_content("30%_", "earliest")
        assert await session.get_items() == [session_user_item("ordinary prefix 30XXQ target")]
        result = await retention_run(RetentionUsageModel("branch result"), session, "branch question")
        assert await session.get_turn_usage(2) == {}
        await session.store_run_usage(result)
        usage = await session.get_turn_usage(2)
        assert {k: usage[k] for k in ("requests", "input_tokens", "output_tokens", "total_tokens")} == {
            "requests": 2, "input_tokens": 23, "output_tokens": 7, "total_tokens": 30}
        aggregate = await session.get_session_usage()
        assert aggregate["input_tokens"] == 23 and aggregate["output_tokens"] == 7
        assert await session.get_tool_usage() == []
        assert set(await session.get_tool_usage(initial)) == {("lookup", 2, 2), ("render", 1, 3)}
        # Explicitly selected branches are honoured by every turn analytic.
        assert [t["turn"] for t in await session.find_turns_by_content("30%_", initial)] == [2, 3]
        assert [t["turn"] for t in await session.find_turns_by_content("30%_")] == []
        assert {turn: len(messages) for turn, messages in
                (await session.get_conversation_by_turns(initial)).items()} == {1: 1, 2: 5, 3: 3}
        assert [t["full_content"] for t in await session.get_conversation_turns()] == [
            "ordinary prefix 30XXQ target", "branch question"]
        assert await session.get_turn_usage(2, initial) == {}
        await session.switch_to_branch(initial)
        assert await session.get_turn_usage(2) == {}
        assert (await session.get_turn_usage(2, branch))["total_tokens"] == 30
    finally:
        session.close()


def test_encrypted_durability_secret_and_identity_isolation(tmp_path):
    path = tmp_path / "protected.db"
    items = [session_user_item("confidential persistence marker 3917"),
             {"role": "assistant", "content": "private response 8426"}]
    encrypted_success(path, "write", items=items)
    # The writing interpreter has exited before any read is started.
    assert b"confidential persistence marker 3917" not in path.read_bytes()
    assert b"private response 8426" not in path.read_bytes()
    assert encrypted_success(path, "read") == items
    assert encrypted_success(path, "read", encryption_key="different-application-secret") == []
    assert encrypted_success(path, "read", session_id="different-identity") == []
    assert encrypted_success(path, "read") == items


@pytest.mark.asyncio
async def test_encrypted_records_require_authentication(tmp_path):
    store = SQLiteSession(session_id="raw", db_path=tmp_path / "authentication.db")
    wrapper = EncryptedSession(session_id="protected", underlying_session=store, encryption_key="authentication-secret")
    good = session_user_item("authenticated content")
    try:
        await wrapper.add_items([good])
        envelope = (await store.get_items())[0]
        # Envelope contents remain opaque: truncate/remove fields without choosing an algorithm.
        incomplete = copy.deepcopy(envelope)
        incomplete.pop("payload")
        corrupted = copy.deepcopy(envelope)
        corrupted["payload"] = corrupted["payload"][:-12]
        await store.add_items([session_user_item("untrusted plaintext"), incomplete, corrupted])
        assert await wrapper.get_items() == [good]
        tampered = []
        for index in range(8, len(envelope["payload"]) - 16):
            changed = copy.deepcopy(envelope)
            token = changed["payload"]
            replacement = "A" if token[index] != "A" else "B"
            changed["payload"] = token[:index] + replacement + token[index + 1:]
            tampered.append(changed)
        await store.add_items(tampered)
        recovered = await wrapper.get_items()
        assert recovered[0] == good
        # Equivalent encodings may authenticate the same original content; altered
        # plaintext from unauthenticated encoding must never become trusted history.
        assert all(item == good for item in recovered)
        with pytest.raises(ValueError):
            EncryptedSession(session_id="protected", underlying_session=store, encryption_key="")
    finally:
        store.close()


def test_encrypted_expiry_and_limited_backfill(tmp_path):
    clock = build_application_clock(tmp_path)
    item = session_user_item("expires from encryption time")
    for ttl in (None, 40):
        path = tmp_path / f"expiry-{ttl}.db"
        options = {} if ttl is None else {"ttl": ttl}
        lifetime = 600 if ttl is None else ttl
        encrypted_success(path, "write", clock=clock, items=[item], **options)
        assert encrypted_success(path, "read", clock=clock, now=2000000000 + lifetime - 2,
                                 **options) == [item]
        assert encrypted_success(path, "read", clock=clock, now=2000000000 + lifetime + 2,
                                 **options) == []
    path = tmp_path / "backfill.db"
    # Older storage order need not mean older encryption time (e.g. imported records).
    live = [session_user_item("older valid first"), session_user_item("older valid second"),
            session_user_item("older valid third")]
    encrypted_success(path, "write", clock=clock, now=2000001000, items=live)
    encrypted_success(path, "write", clock=clock, now=2000000000,
                      items=[session_user_item("expired newer record")])
    import asyncio
    async def append_unreadable():
        store = SQLiteSession(session_id="backing", db_path=path)
        try:
            await store.add_items([session_user_item("unreadable newer record")] * 2)
        finally:
            store.close()
    asyncio.run(append_unreadable())
    assert encrypted_success(path, "read", clock=clock, now=2000001000, limit=2) == live[-2:]


@pytest.mark.asyncio
async def test_encrypted_read_budget_requires_complete_result(tmp_path):
    store = SQLiteSession(session_id="budget", db_path=tmp_path / "budget.db")
    items = [session_user_item("first valid"), session_user_item("second valid")]
    try:
        wrapper = EncryptedSession(session_id="budget", underlying_session=store, encryption_key="read-budget-secret")
        await wrapper.add_items(items)
        await store.add_items([session_user_item("unreadable newer")] * 12)
        assert await wrapper.get_items(2) == items
        generous = EncryptedSession(session_id="budget", underlying_session=store, encryption_key="read-budget-secret", max_scan_items=100)
        assert await generous.get_items(2) == items
        assert await generous.get_items() == items
        bounded = EncryptedSession(session_id="budget", underlying_session=store, encryption_key="read-budget-secret", max_scan_items=3)
        with pytest.raises(RuntimeError):
            await bounded.get_items(2)
        with pytest.raises(RuntimeError):
            await bounded.get_items()
        assert await wrapper.get_items() == items
    finally:
        store.close()
