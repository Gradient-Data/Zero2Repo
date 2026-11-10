# feature: F14
"""Real MCP protocol peer with application-owned files and configurable catalogs."""
import asyncio
import json
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from _helpers import bounded
from F01_helpers import RecordingModel, function_call, run_agent
from velmora import Agent
from velmora.mcp import MCPServerStdio, MCPServerSse, MCPServerStreamableHttp


class LocalCatalog:
    def __init__(self, directory, name="catalog", **settings):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config = self.directory / "config.json"
        self.effects = self.directory / "effects.jsonl"
        self.starts = self.directory / "starts.jsonl"
        self.effects.write_text("")
        self.starts.write_text("")
        self.settings = {"name": name, "pages": 3, "mode": "normal", "enabled": True,
                         "tools": ["write", "inspect", "erase"], **settings}
        self.save()

    def save(self):
        self.config.write_text(json.dumps(self.settings))

    def records(self, path):
        return [json.loads(line) for line in path.read_text().splitlines()]

    def client(self, **options):
        return MCPServerStdio(name=self.settings["name"], params={
            "command": sys.executable, "args": [str(Path(__file__).resolve()), str(self.config)]},
            **options)


def protocol_server(config_path):
    """Implement an external service, not the SDK's discovery or execution logic."""
    from mcp.server import Server
    from mcp import types

    config_path = Path(config_path)
    cfg = json.loads(config_path.read_text())
    root = config_path.parent
    if not cfg["enabled"]:
        raise RuntimeError("Application server is disabled.")
    with (root / "starts.jsonl").open("a") as stream:
        stream.write(json.dumps({"name": cfg["name"]}) + "\n")

    def page(params, kind):
        index = int(params.cursor) if params and params.cursor is not None else 0
        if cfg["mode"] == "fail" and index > 0:
            raise ValueError("Application catalog page unavailable.")
        cursor = str(index if cfg["mode"] == "repeat" else index + 1)
        if kind == "tools":
            names = cfg["tools"]
            entries = [dict(name=names[index], description="Application operation",
                            inputSchema={"type": "object", "properties": {
                                "value": {"type": "string"}}, "required": ["value"],
                                "additionalProperties": False})]
            total = len(names)
        elif kind == "prompts":
            entries = [dict(name=f"prompt_{index}", description=f"Prompt page {index}",
                            arguments=[dict(name="topic", required=True)])]
            total = cfg["pages"]
        elif kind == "resources":
            entries = [dict(uri=f"memo://page/{index}", name=f"memo_{index}",
                            description=f"Resource page {index}", mimeType="text/plain")]
            total = cfg["pages"]
        else:
            entries = [dict(uriTemplate=f"memo://template/{index}/{{key}}", name=f"template_{index}",
                            description=f"Template page {index}", mimeType="text/plain")]
            total = cfg["pages"]
        key = "resourceTemplates" if kind == "templates" else kind
        payload = {key: entries}
        if index + 1 < total:
            payload["nextCursor"] = cursor
        return payload

    async def tools(context, params):
        return types.ListToolsResult.model_validate(page(params, "tools"))

    async def prompts(context, params):
        return types.ListPromptsResult.model_validate(page(params, "prompts"))

    async def resources(context, params):
        return types.ListResourcesResult.model_validate(page(params, "resources"))

    async def templates(context, params):
        return types.ListResourceTemplatesResult.model_validate(page(params, "templates"))

    async def read(context, params):
        return types.ReadResourceResult.model_validate({"contents": [{
            "uri": str(params.uri), "mimeType": "text/plain",
            "text": (root / "resource.txt").read_text()}]})

    async def prompt(context, params):
        if params.name == "missing":
            raise ValueError("Application prompt unavailable.")
        return types.GetPromptResult.model_validate({"description": params.name,
            "messages": [{"role": "user", "content": {"type": "text",
                "text": (root / "prompt.txt").read_text() + params.arguments["topic"]}}]})

    async def call(context, params):
        if params.name not in cfg["tools"]:
            raise ValueError("Unknown application operation.")
        value = params.arguments["value"]
        if value == "fail":
            raise ValueError("Application operation failed.")
        with (root / "effects.jsonl").open("a") as stream:
            stream.write(json.dumps({"tool": params.name, "value": value, "server": cfg["name"]}) + "\n")
        if (root / "result.json").exists():
            return types.CallToolResult.model_validate(json.loads((root / "result.json").read_text()))
        return types.CallToolResult.model_validate({"content": [{"type": "text", "text":
            json.dumps({"server": cfg["name"], "tool": params.name, "reversed": value[::-1]})}]})

    return Server(cfg["name"], on_list_tools=tools, on_call_tool=call,
                  on_list_prompts=prompts, on_get_prompt=prompt, on_list_resources=resources,
                  on_list_resource_templates=templates, on_read_resource=read)


@asynccontextmanager
async def http_catalog(catalog, transport):
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from mcp.server.sse import SseServerTransport

    service = protocol_server(catalog.config)
    if transport == "http":
        app = service.streamable_http_app()
    else:
        sse = SseServerTransport("/messages/")

        async def endpoint(request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await service.run(*streams, service.create_initialization_options())
        app = Starlette(routes=[Route("/sse", endpoint), Mount("/messages/", app=sse.handle_post_message)])
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    worker = uvicorn.Server(uvicorn.Config(app, log_level="error", ws="none"))
    task = asyncio.create_task(worker.serve(sockets=[listener]))

    async def started():
        while not worker.started:
            if task.done():
                await task
                raise AssertionError("MCP HTTP service exited before startup.")
            await asyncio.sleep(0.01)
    try:
        await bounded(started(), timeout=10)
        cls = MCPServerStreamableHttp if transport == "http" else MCPServerSse
        yield cls(name=catalog.settings["name"], params={
            "url": f"http://127.0.0.1:{port}/{'mcp' if transport == 'http' else 'sse'}"})
    finally:
        worker.should_exit = True
        await bounded(task, timeout=10)
        listener.close()


async def mcp_turn(servers, *, name="write", value="payload", context=None, config=None):
    model = RecordingModel([function_call(name, {"value": value}, "remote")], "Finished.")
    agent = Agent(name="MCP application", model=model, mcp_servers=servers,
                  mcp_config=config or {})
    result = await run_agent(agent, context=context)
    return result, model


if __name__ == "__main__":
    from mcp.server.stdio import stdio_server

    async def main():
        service = protocol_server(sys.argv[1])
        async with stdio_server() as streams:
            await service.run(*streams, service.create_initialization_options())
    asyncio.run(main())
