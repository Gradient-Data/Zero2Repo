# feature: F02
"""Acceptance tests for provider access, connection controls and safe attempts."""
import asyncio

import pytest
import httpx2
from openai import AsyncOpenAI, APIConnectionError
from openai.types.shared import Reasoning
from openai.types.responses import ResponseTextDeltaEvent
from pydantic import ValidationError

from F01_helpers import RecordingModel, function_call, responses_peer
from F02_helpers import (AttemptModel, SelectedProvider, model_peer, model_run,
                         websocket_peer, retry_settings)
from _helpers import bounded, environment, run_python
from velmora import (Agent, ModelBehaviorError, ModelSettings, RunConfig, Runner,
                    UserError, function_tool, set_default_openai_client,
                    set_default_openai_key,
                    set_default_openai_responses_transport)
from velmora import AgentsException, ModelTimeoutError, ModelRefusalError
from velmora import ModelTracing
from velmora import MultiProvider
from velmora.models.multi_provider import MultiProviderMap
from velmora import OpenAIProvider
from velmora import OpenAIResponsesModel, OpenAIResponsesWSModel
from velmora import ModelRetryAdvice, ModelRetryNormalizedError, ModelRetrySettings, RetryDecision
from velmora.retry import retry_policies
from velmora import ProgrammaticToolCallingTool



@pytest.mark.asyncio
async def test_f02_t01():
    for responses in (None, True, False):
        answer = f"Protocol answer {responses}."
        with model_peer(text=answer) as (url, requests):
            async with AsyncOpenAI(base_url=url, api_key="local-key", max_retries=0) as client:
                provider = OpenAIProvider(openai_client=client, use_responses=responses)
                result = await model_run("application-model", provider=provider)
                assert result.final_output == answer
                assert requests[0]["path"] == ("/v1/chat/completions" if responses is False else "/v1/responses")
                assert requests[0]["body"]["model"] == "application-model"
    direct = RecordingModel("Direct application output.")
    assert (await model_run(direct)).final_output == "Direct application output."
    provider = SelectedProvider(RecordingModel("Provider application output."))
    assert (await model_run("chosen-model", provider=provider)).final_output == "Provider application output."
    assert provider.names == ["chosen-model"]


@pytest.mark.asyncio
async def test_f02_t02():
    with model_peer(text="HTTP transport.") as (url, http_requests):
        async with websocket_peer("WebSocket transport.") as (ws_url, ws_requests):
            async with AsyncOpenAI(base_url=url, websocket_base_url=ws_url,
                                   api_key="local-key", max_retries=0) as client:
                set_default_openai_client(client, use_for_tracing=False)
                try:
                    set_default_openai_responses_transport("http")
                    assert (await model_run("wire-model")).final_output == "HTTP transport."
                    provider = OpenAIProvider(openai_client=client, use_responses_websocket=True)
                    try:
                        assert (await model_run("wire-model", provider=provider)).final_output == "WebSocket transport."
                    finally:
                        await provider.aclose()
                    concrete = OpenAIResponsesWSModel(model="wire-model", openai_client=client)
                    try:
                        assert (await model_run(concrete)).final_output == "WebSocket transport."
                    finally:
                        await concrete.close()
                    explicit = OpenAIProvider(openai_client=client, use_responses_websocket=False)
                    set_default_openai_responses_transport("websocket")
                    assert (await model_run("wire-model")).final_output == "WebSocket transport."
                    assert (await model_run("wire-model", provider=explicit)).final_output == "HTTP transport."
                    assert (await model_run(OpenAIResponsesModel(model="wire-model", openai_client=client))).final_output == "HTTP transport."
                    assert len(http_requests) == 3
                    assert len(ws_requests) == 3
                    for request in ws_requests:
                        assert request["path"] == "/v1/responses"
                        assert request["body"]["type"] == "response.create"
                        assert request["body"]["model"] == "wire-model"
                finally:
                    set_default_openai_responses_transport("http")
                    set_default_openai_client(None, use_for_tracing=False)


@pytest.mark.asyncio
async def test_f02_t03():
    with responses_peer() as (url, requests):
        async with AsyncOpenAI(base_url=url, api_key="local-key", max_retries=0) as client:
            provider = OpenAIProvider(openai_client=client)
            with environment({"OPENAI_DEFAULT_MODEL": None}):
                assert (await model_run(provider=provider)).final_output == "Template response."
                body = requests[-1]["body"]
                assert body["model"] == "gpt-5.6-luna"
                assert body["reasoning"]["effort"] == "none"
                assert body["text"]["verbosity"] == "low"
            with environment({"OPENAI_DEFAULT_MODEL": "configured-model"}):
                for agent_model, run_model, expected in ((None, None, "configured-model"),
                        ("agent-model", None, "agent-model"),
                        ("agent-model", "run-model", "run-model")):
                    await model_run(agent_model, provider=provider, run_model=run_model)
                    assert requests[-1]["body"]["model"] == expected
                await model_run(provider=provider, settings=ModelSettings(
                    reasoning=Reasoning(effort="high"), verbosity="high"))
                assert requests[-1]["body"]["reasoning"]["effort"] == "high"
                assert requests[-1]["body"]["text"]["verbosity"] == "high"


@pytest.mark.asyncio
async def test_f02_t04():
    with model_peer(text="Merged settings.") as (url, requests):
        async with AsyncOpenAI(base_url=url, api_key="local-key", max_retries=0) as client:
            result = await model_run("merge-model", provider=OpenAIProvider(openai_client=client),
                settings=ModelSettings(temperature=0.2, top_p=0.7, max_tokens=91,
                                       extra_args={"metadata": {"region": "west"}, "service_tier": "auto"}),
                run_settings=ModelSettings(temperature=0.8, extra_args={"service_tier": "default"}))
            assert result.final_output == "Merged settings."
            body = requests[-1]["body"]
            assert body["temperature"] == 0.8
            assert body["top_p"] == 0.7
            assert body["max_output_tokens"] == 91
            assert body["metadata"] == {"region": "west"}
            assert body["service_tier"] == "default"
    model = AttemptModel(ValueError("first"), ValueError("second"), "Merged retry.")
    # The run overrides another backoff field only; the agent's initial delay must survive the merge.
    result = await model_run(model, settings=retry_settings(lambda ctx: True, 1, 0.5),
                            run_settings=ModelSettings(retry=ModelRetrySettings(max_retries=2,
                                backoff={"jitter": False})))
    assert result.final_output == "Merged retry."
    assert len(model.requests) == 3
    assert model.times[1] - model.times[0] >= 0.45
    assert model.times[2] - model.times[1] >= 0.45


@pytest.mark.asyncio
async def test_f02_t05():
    selected = SelectedProvider(RecordingModel("Custom route."))
    mapping = MultiProviderMap()
    mapping.add_provider("custom", selected)
    with model_peer(text="Built-in route.") as (url, requests):
        router = MultiProvider(provider_map=mapping, openai_api_key="local-key", openai_base_url=url)
        assert (await model_run("custom/nested/model", provider=router)).final_output == "Custom route."
        assert selected.names == ["nested/model"]
        assert (await model_run("openai/routed-model", provider=router)).final_output == "Built-in route."
        assert requests[-1]["body"]["model"] == "routed-model"
        with pytest.raises(UserError):
            await model_run("unknown/model", provider=router)
        literal = MultiProvider(openai_api_key="local-key", openai_base_url=url,
                                unknown_prefix_mode="model_id", openai_prefix_mode="model_id")
        for designation in ("unknown/nested/model", "openai/literal-model"):
            assert (await model_run(designation, provider=literal)).final_output == "Built-in route."
            assert requests[-1]["body"]["model"] == designation
        with environment({"OPENAI_API_KEY": "local-key", "OPENAI_BASE_URL": url,
                          "LITELLM_LOCAL_MODEL_COST_MAP": "True"}):
            for route in ("litellm/openai/adapter-model", "any-llm/openai/adapter-model"):
                # The first adapter route imports a third-party adapter package cold.
                assert (await model_run(route, provider=router, timeout=60)).final_output == "Built-in route."
                assert requests[-1]["path"] in ("/v1/responses", "/v1/chat/completions")
                assert requests[-1]["body"]["model"] == "adapter-model"
    # Dependency refusal is exercised in a fresh interpreter; no SDK internals are replaced.
    for dependency, route in (("litellm", "litellm/model"), ("any_llm", "any-llm/openai/model")):
        source = f'''import sys, importlib.abc
sys.path.insert(0, "src")
class Unavailable(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == {dependency!r} or fullname.startswith({dependency!r} + "."):
            raise ModuleNotFoundError("Dependency intentionally unavailable", name=fullname)
sys.meta_path.insert(0, Unavailable())
from velmora.models.multi_provider import MultiProvider
try:
    MultiProvider(openai_api_key="local-key").get_model({route!r})
except ImportError:
    print("dependency-refused")
else:
    raise AssertionError("Missing adapter dependency was accepted")
'''
        result = run_python(source)
        assert result.returncode == 0, result.stderr.decode()
        assert result.stdout.strip() == b"dependency-refused"


@pytest.mark.asyncio
async def test_f02_t06():
    with model_peer(text="Global connection.") as (global_url, global_requests):
        with model_peer(text="Provider connection.") as (provider_url, provider_requests):
            async with AsyncOpenAI(base_url=global_url, api_key="global-key",
                                   organization="client-org", project="client-project", max_retries=0) as client:
                set_default_openai_client(client, use_for_tracing=False)
                set_default_openai_key("configured-key", use_for_tracing=False)
                try:
                    assert (await model_run("connection-model", provider=OpenAIProvider())).final_output == "Global connection."
                    headers = global_requests[-1]["headers"]
                    assert headers["authorization"] == "Bearer global-key"
                    assert headers["openai-organization"] == "client-org"
                    assert headers["openai-project"] == "client-project"
                    explicit = OpenAIProvider(base_url=provider_url, api_key="provider-key",
                                              organization="provider-org", project="provider-project")
                    assert (await model_run("connection-model", provider=explicit)).final_output == "Provider connection."
                    headers = provider_requests[-1]["headers"]
                    assert headers["authorization"] == "Bearer provider-key"
                    assert headers["openai-organization"] == "provider-org"
                    assert headers["openai-project"] == "provider-project"
                    assert len(global_requests) == 1
                    for conflict in ({"api_key": "other"}, {"base_url": provider_url},
                                     {"websocket_base_url": "ws://127.0.0.1:1"},
                                     {"organization": "other"}, {"project": "other"}):
                        with pytest.raises(UserError):
                            OpenAIProvider(openai_client=client, **conflict)
                    set_default_openai_client(None, use_for_tracing=False)
                    with environment({"OPENAI_BASE_URL": provider_url}):
                        assert (await model_run("connection-model", provider=OpenAIProvider())).final_output == "Provider connection."
                        assert provider_requests[-1]["headers"]["authorization"] == "Bearer configured-key"
                finally:
                    set_default_openai_client(None, use_for_tracing=False)
                    set_default_openai_key(None, use_for_tracing=False)


@pytest.mark.asyncio
async def test_f02_t07():
    with model_peer(text="Chat baseline.") as (url, requests):
        async with AsyncOpenAI(base_url=url, api_key="local-key", max_retries=0) as client:
            model = OpenAIProvider(openai_client=client, use_responses=False,
                                   strict_feature_validation=True).get_model("chat-model")
            assert (await model_run(model)).final_output == "Chat baseline."
            base = dict(system_instructions=None, input="Hello", model_settings=ModelSettings(),
                        tools=[], output_schema=None, handoffs=[], tracing=ModelTracing.DISABLED,
                        previous_response_id=None, conversation_id=None, prompt=None)
            invalid = ({"previous_response_id": "resp_prior"}, {"conversation_id": "conv_prior"},
                       {"prompt": {"id": "template"}},
                       {"input": [{"type": "function_call_output", "call_id": "image-call",
                                   "output": [{"type": "input_image", "image_url": "https://example.invalid/image.png"}]}]})
            for override in invalid:
                with pytest.raises(UserError):
                    await bounded(model.get_response(**(base | override)))
            assert len(requests) == 1
    with model_peer(chat_message={"role": "assistant", "content": None,
                                 "audio": {"id": "audio", "data": "AA==", "expires_at": 1,
                                           "transcript": "Spoken"}}) as (url, requests):
        async with AsyncOpenAI(base_url=url, api_key="local-key", max_retries=0) as client:
            with pytest.raises(AgentsException):
                await model_run("chat-model", provider=OpenAIProvider(openai_client=client, use_responses=False))
            assert len(requests) == 1


@pytest.mark.asyncio
async def test_f02_t08():
    for message, finish, outcome in (({"role": "assistant", "content": None}, "length", "error"),
            ({"role": "assistant", "content": "Partial usable answer."}, "length", "text"),
            ({"role": "assistant", "content": None, "refusal": "Provider declined."}, "length", "refusal")):
        with model_peer(chat_message=message, finish_reason=finish) as (url, requests):
            async with AsyncOpenAI(base_url=url, api_key="local-key", max_retries=0) as client:
                provider = OpenAIProvider(openai_client=client, use_responses=False)
                if outcome == "error":
                    with pytest.raises(ModelBehaviorError):
                        await model_run("chat-model", provider=provider)
                elif outcome == "text":
                    result = await model_run("chat-model", provider=provider)
                    assert result.final_output == message["content"]
                else:
                    with pytest.raises(ModelRefusalError) as caught:
                        await model_run("chat-model", provider=provider)
                    assert caught.value.refusal == message["refusal"]
                assert len(requests) == 1
    @function_tool
    def calculate() -> str:
        return "Actual tool result."
    tool_message = {"role": "assistant", "content": None, "tool_calls": [{"id": "call_calc",
                    "type": "function", "function": {"name": "calculate", "arguments": "{}"}}]}
    # A usable tool call at the budget boundary must survive conversion.
    with model_peer(chat_message=tool_message, finish_reason="length") as (url, requests):
        async with AsyncOpenAI(base_url=url, api_key="local-key", max_retries=0) as client:
            model = OpenAIProvider(openai_client=client, use_responses=False).get_model("chat-model")
            response = await bounded(model.get_response(None, "Hello", ModelSettings(), [calculate],
                None, [], ModelTracing.DISABLED, previous_response_id=None, conversation_id=None, prompt=None))
            assert [(item.name, item.call_id, item.arguments) for item in response.output
                    if item.type == "function_call"] == [("calculate", "call_calc", "{}")]


@pytest.mark.asyncio
async def test_f02_t09():
    for invalid in (0, -1, float("inf"), float("-inf"), float("nan")):
        with pytest.raises(ValidationError):
            ModelSettings(timeout=invalid)
    for streamed in (False, True):
        waiting = asyncio.Event()
        async def released_response():
            await waiting.wait()
            return "Attempt completed after the configured deadline."
        model = AttemptModel(released_response)
        # A generous release margin checks the chosen deadline without grading throughput.
        release = asyncio.get_running_loop().call_later(0.9, waiting.set)
        try:
            with pytest.raises(ModelTimeoutError):
                await model_run(model, settings=ModelSettings(timeout=0.3), stream=streamed)
        finally:
            release.cancel()
        assert len(model.requests) == 1
    @function_tool(failure_error_function=None)
    async def slow_tool() -> str:
        await asyncio.sleep(0.6)
        return "Tool finished beyond attempt deadline."
    model = AttemptModel([function_call("slow_tool", {}, "slow-1")], "After tool.")
    assert (await model_run(model, tools=[slow_tool], settings=ModelSettings(timeout=0.3))).final_output == "After tool."
    outputs = [item for item in model.requests[1]["input"] if item.get("type") == "function_call_output"]
    assert outputs[0]["output"] == "Tool finished beyond attempt deadline."
    async def delayed():
        await asyncio.sleep(0.05)
        return "Fresh deadline."
    model = AttemptModel(delayed, delayed)
    # First attempt times out; the second gets its own full budget after retry delay.
    async def blocked():
        await asyncio.Event().wait()
    model.actions[0] = blocked
    settings = retry_settings(retry_policies.network_error(), 1, 0.6)
    settings.timeout = 0.3
    assert (await model_run(model, settings=settings)).final_output == "Fresh deadline."
    assert len(model.requests) == 2
    assert model.times[1] - model.times[0] >= 0.85


@pytest.mark.asyncio
async def test_f02_t10():
    cases = [
        (retry_policies.never(), ValueError("decline"), None, False),
        (retry_policies.provider_suggested(), ValueError("advised"), ModelRetryAdvice(suggested=True), True),
        (retry_policies.provider_suggested(), ValueError("not advised"), ModelRetryAdvice(suggested=False), False),
        (retry_policies.provider_suggested(), ValueError("no advice"), None, False),
        (retry_policies.network_error(), APIConnectionError(request=httpx2.Request("POST", "http://127.0.0.1/provider")), None, True),
        (retry_policies.network_error(), TimeoutError("deadline"), None, True),
        (retry_policies.network_error(), ValueError("invalid"), None, False),
        (retry_policies.http_status([429, 503]), ValueError("status"),
         ModelRetryAdvice(normalized=ModelRetryNormalizedError(status_code=503)), True),
        (retry_policies.http_status([429, 503]), ValueError("other status"),
         ModelRetryAdvice(normalized=ModelRetryNormalizedError(status_code=400)), False),
        (retry_policies.retry_after(), ValueError("delay"), ModelRetryAdvice(retry_after=0.12), True),
        (retry_policies.retry_after(), ValueError("no delay advice"), None, False),
        (retry_policies.any(retry_policies.never(), retry_policies.network_error()), TimeoutError(), None, True),
        (retry_policies.any(retry_policies.never(), retry_policies.network_error()), ValueError(), None, False),
        (retry_policies.all(retry_policies.provider_suggested(), retry_policies.network_error()),
         TimeoutError(), ModelRetryAdvice(suggested=True), True),
        (retry_policies.all(retry_policies.provider_suggested(), retry_policies.network_error()),
         ValueError(), ModelRetryAdvice(suggested=True), False),
    ]
    for policy, error, advice, retries in cases:
        model = AttemptModel(error, "Recovered output.", advice=advice)
        if retries:
            assert (await model_run(model, settings=retry_settings(policy))).final_output == "Recovered output."
            assert len(model.requests) == 2
            if advice is not None and advice.retry_after is not None:
                assert model.times[1] - model.times[0] >= advice.retry_after - 0.01
        else:
            with pytest.raises(type(error)) as caught:
                await model_run(model, settings=retry_settings(policy))
            assert caught.value is error
            assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_f02_t11():
    for allowance, policy, attempts in ((None, lambda ctx: True, 1), (2, None, 1),
                                      (0, lambda ctx: True, 1), (-2, lambda ctx: True, 1),
                                      (1, lambda ctx: True, 2), (3, lambda ctx: True, 4)):
        failures = [ValueError(f"Attempt {i}") for i in range(attempts)]
        model = AttemptModel(*failures)
        with pytest.raises(ValueError) as caught:
            await model_run(model, settings=retry_settings(policy, allowance))
        assert caught.value is failures[-1]
        assert len(model.requests) == attempts
    model = AttemptModel(ValueError("one"), ValueError("two"), "Third attempt result.")
    assert (await model_run(model, settings=retry_settings(lambda ctx: True, 2))).final_output == "Third attempt result."
    assert len(model.requests) == 3


@pytest.mark.asyncio
async def test_f02_t12():
    settings = retry_settings(lambda ctx: RetryDecision(retry=True, approve_unsafe_replay=True))
    # Prove the same policy actually replays a pre-output failure.
    safe = AttemptModel(ValueError("before output"), "Stream recovered.")
    result, events = await model_run(safe, settings=settings, stream=True)
    assert result.final_output == "Stream recovered."
    assert len(safe.requests) == 2
    delta = ResponseTextDeltaEvent(type="response.output_text.delta", sequence_number=1,
                                  item_id="message", output_index=0, content_index=0,
                                  delta="Already delivered.", logprobs=[])
    failure = ValueError("after output")
    model = AttemptModel([delta, failure], "Must not replay.")
    result = Runner.run_streamed(Agent(name="Stream", model=model, model_settings=settings),
                                 "Request", run_config=RunConfig(tracing_disabled=True))
    delivered = []
    async def drain():
        async for event in result.stream_events():
            delivered.append(event)
    with pytest.raises(ValueError) as caught:
        await bounded(drain())
    assert caught.value is failure
    assert any(event.type == "raw_response_event" and event.data.type == "response.output_text.delta"
               and event.data.delta == "Already delivered." for event in delivered)
    assert len(model.requests) == 1
    # Accepting provider-declared replay risk applies to non-streaming requests only.
    unsafe = ModelRetryAdvice(suggested=False, replay_safety="unsafe")
    for streamed, attempts in ((False, 2), (True, 1)):
        failure = ValueError("provider-declared unsafe")
        model = AttemptModel(failure, "Accepted replay.", advice=unsafe)
        if streamed:
            with pytest.raises(ValueError) as caught:
                await model_run(model, settings=settings, stream=True)
            assert caught.value is failure
        else:
            assert (await model_run(model, settings=settings)).final_output == "Accepted replay."
        assert len(model.requests) == attempts
    for streamed in (False, True):
        cancelled = asyncio.CancelledError()
        model = AttemptModel(cancelled, "Must not replay.")
        if streamed:
            result, events = await model_run(model, settings=settings, stream=True)
            assert result.is_complete is True
            assert result.final_output is None
        else:
            with pytest.raises(asyncio.CancelledError):
                await model_run(model, settings=settings)
        assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_f02_t13():
    # Both server-side continuation forms make the request stateful.
    for continuation in ({"previous_response_id": "resp_prior"}, {"conversation_id": "conv_prior"}):
        (key, value), = continuation.items()
        for advice, approval, should_retry in ((None, False, False),
                (ModelRetryAdvice(suggested=True, replay_safety="safe"), False, True),
                (ModelRetryAdvice(suggested=False, replay_safety="unsafe"), False, False),
                (ModelRetryAdvice(suggested=False, replay_safety="unsafe"), True, True),
                (None, True, False)):
            failure = ValueError("Stateful failure")
            model = AttemptModel(failure, "Stateful recovered.", advice=advice)
            settings = retry_settings(lambda ctx: RetryDecision(retry=True, approve_unsafe_replay=approval))
            if should_retry:
                assert (await model_run(model, settings=settings, **continuation)).final_output == "Stateful recovered."
                assert len(model.requests) == 2
                assert all(request[key] == value for request in model.requests)
            else:
                with pytest.raises(ValueError) as caught:
                    await model_run(model, settings=settings, **continuation)
                assert caught.value is failure
                assert len(model.requests) == 1
    # The local application effect really happens before the provider fails.
    effects = []
    async def local_effect():
        effects.append("applied")
        raise ValueError("Failed after local effect")
    model = AttemptModel(local_effect, "Must not repeat local work.",
                         advice=ModelRetryAdvice(suggested=False, replay_safety="unsafe"))
    with pytest.raises(ValueError):
        await model_run(model, tools=[ProgrammaticToolCallingTool()],
                        settings=retry_settings(lambda ctx: RetryDecision(retry=True, approve_unsafe_replay=True)))
    assert effects == ["applied"]
    assert len(model.requests) == 1
