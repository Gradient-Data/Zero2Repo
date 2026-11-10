# feature: F12
"""Hosted protocol scenarios driven through real HTTP and WebSocket clients."""
import json
from contextlib import asynccontextmanager

from F01_helpers import text_message, function_call
from F02_helpers import model_peer, response_payload
from F03_helpers import tool_outputs
from F04_helpers import execution_run
from _helpers import bounded, consume
from velmora import Agent, OpenAIResponsesModel, ProgrammaticToolCallingTool, Runner, RunConfig
from openai import AsyncOpenAI
from openai.types.responses.response_output_item import Program, ProgramOutput
from openai.types.responses.response_function_tool_call import CallerProgram


def hosted_payload(*items):
    payload = response_payload("")
    payload["output"] = [item if isinstance(item, dict) else item.model_dump(exclude_none=True)
                         for item in items]
    return payload


@asynccontextmanager
async def hosted_http(outputs):
    replies = [(200, hosted_payload(*output), {}) for output in outputs]
    with model_peer(replies=replies) as (url, requests):
        async with AsyncOpenAI(api_key="local-protocol-peer", base_url=url, max_retries=0) as client:
            yield OpenAIResponsesModel(model="hosted-capable", openai_client=client), requests


async def hosted_run(tools, outputs=None, *, settings=None, prompt=None):
    async with hosted_http([[text_message("Hosted response.")]] if outputs is None else outputs) as (model, requests):
        agent = Agent(name="Hosted application", model=model, tools=tools,
                      prompt=prompt, **({"model_settings": settings} if settings is not None else {}))
        result = await execution_run(agent)
        return result, requests


def raw_dict(item):
    return item if isinstance(item, dict) else item.model_dump(exclude_none=True)


def raw_items(result):
    return [raw_dict(item.raw_item) for item in result.new_items]


def program_start():
    return Program(id="program-item", call_id="program-call", code="await child()",
                   fingerprint="service-fingerprint", type="program")


def program_end():
    return ProgramOutput(id="program-result", call_id="program-call", type="program_output",
                         status="completed", result='{"complete":true}')


def program_child(name, arguments):
    return function_call(name, arguments, "child-call").model_copy(update={
        "caller": CallerProgram(type="program", caller_id="program-call")})


async def program_run(tool, *, arguments=None):
    return await hosted_run([ProgrammaticToolCallingTool(), tool], [
        [program_start(), program_child(tool.name, {} if arguments is None else arguments)],
        [program_end(), text_message("Program finished.")],
    ])


def child_output(requests, *, kind="function_call_output"):
    outputs = tool_outputs(requests[-1]["body"], kind=kind)
    assert set(outputs) == {"child-call"}
    return outputs["child-call"]


def mcp_request(identity, server, name="lookup"):
    return {"id": identity, "type": "mcp_approval_request", "server_label": server,
            "name": name, "arguments": '{}'}


def hosted_message(text, caller="/root", phase="final_answer"):
    item = text_message(text).model_dump()
    item.update(id="message-" + caller, agent={"agent_name": caller}, phase=phase)
    return item


@asynccontextmanager
async def hosted_socket(*, calls, final_items):
    """A service-side peer; wait for real result injection before completing work."""
    from websockets.asyncio.server import serve
    from velmora.extensions.experimental.hosted_multi_agent import OpenAIHostedMultiAgentModel
    requests, connections, failures = [], [], []

    async def handle(connection):
        connections.append(connection.request.path)
        try:
            request = json.loads(await connection.recv())
            requests.append(request)
            assert request["type"] == "response.create"
            seq = 1
            await connection.send(json.dumps({"type": "response.created", "sequence_number": seq,
                                             "response": {"id": "hosted-live", "output": [], "usage": None}}))
            activity = {"id": "spawn", "type": "multi_agent_call", "call_id": "spawn-call",
                        "action": "spawn_agent", "arguments": "{}", "agent": {"agent_name": "/root"}}
            for index, item in enumerate([activity, *calls]):
                seq += 1
                await connection.send(json.dumps({"type": "response.output_item.done",
                    "sequence_number": seq, "output_index": index, "item": item, "agent": item["agent"]}))
            pending = {item["call_id"] for item in calls}
            while pending:
                inject = json.loads(await connection.recv())
                requests.append(inject)
                assert inject["type"] == "response.inject"
                assert inject["response_id"] == "hosted-live"
                for output in inject["input"]:
                    pending.remove(output["call_id"])
                seq += 1
                await connection.send(json.dumps({"type": "response.inject.created", "sequence_number": seq,
                                                 "response_id": "hosted-live"}))
            for index, item in enumerate(final_items, len(calls) + 1):
                seq += 1
                await connection.send(json.dumps({"type": "response.output_item.done", "sequence_number": seq,
                    "output_index": index, "item": item, "agent": item["agent"]}))
            seq += 1
            await connection.send(json.dumps({"type": "response.completed", "sequence_number": seq,
                "response": {"id": "hosted-live", "output": [activity, *calls, *final_items], "usage": None}}))
            await connection.wait_closed()
        except BaseException as error:
            failures.append(error)
            raise

    async with serve(handle, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        async with AsyncOpenAI(api_key="local-peer", base_url=f"http://127.0.0.1:{port}/v1",
                               websocket_base_url=f"ws://127.0.0.1:{port}/v1", max_retries=0) as client:
            model = OpenAIHostedMultiAgentModel(model="hosted-capable", openai_client=client)
            try:
                yield model, requests, connections
            finally:
                await model.close()
    if failures:
        raise failures[0]


async def hosted_agent_run(agent, *, stream=False):
    if not stream:
        return await execution_run(agent), []
    result = Runner.run_streamed(agent, "Proceed.", run_config=RunConfig(tracing_disabled=True))
    events = await consume(result.stream_events(), timeout=15)
    return result, events
