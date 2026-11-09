# feature: F20
"""Workflow inputs and independent Graphviz observations."""
import os
from pathlib import Path

from _helpers import parse_dot, parse_json, require_executable, run_process, run_python
from F14_helpers import LocalCatalog
from velmora import Agent, function_tool, handoff
from velmora import Handoff
from velmora.extensions.visualization import draw_graph


def workflow_tool(name):
    def operation(value: str) -> str:
        return value.upper()
    return function_tool(operation, name_override=name)


def workflow_source(kind, directory):
    """Call the public renderer on real definitions; no workflow execution is needed."""
    directory = Path(directory)
    if kind == "expansion":
        leaf = Agent(name="Archive", tools=[workflow_tool("Record")])
        expert = Agent(name="Specialist", tools=[workflow_tool("Search")],
                       mcp_servers=[LocalCatalog(directory / "expert", name="Knowledge").client()],
                       handoffs=[leaf])
        direct = Agent(name="Dispatcher", tools=[workflow_tool("Route")], handoffs=[handoff(expert)])

        async def resolve(context, arguments):
            return Agent(name="Runtime only", tools=[workflow_tool("Hidden resource")])

        custom = Handoff(tool_name="dynamic_route", tool_description="Runtime destination",
                         input_json_schema={"type": "object", "properties": {}},
                         on_invoke_handoff=resolve, agent_name="Dynamic destination")
        root = Agent(name="Intake", tools=[workflow_tool("Validate")],
                     mcp_servers=[LocalCatalog(directory / "root", name="Directory").client()],
                     handoffs=[direct, custom])
    elif kind == "identities":
        first = Agent(name="Shared", tools=[workflow_tool("Shared")],
                      mcp_servers=[LocalCatalog(directory / "first", name="Shared").client()])
        second = Agent(name="Shared", tools=[workflow_tool("Shared")],
                       mcp_servers=[LocalCatalog(directory / "second", name="Shared").client()])
        first.handoffs = [second, Agent(name="First endpoint")]
        second.handoffs = [handoff(first), Agent(name="Second endpoint")]
        root = Agent(name="Entry", handoffs=[first, handoff(second)])
    else:
        raise ValueError(f"Unknown workflow: {kind}")
    graph = draw_graph(root)
    if kind == "expansion":
        graph.save(filename=str(directory / "workflow.gv"))
    return graph.source


def render_workflow(kind, directory):
    """Bound synchronous traversal in a fresh interpreter, retaining real errors."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(Path(__file__).parent), env.get("PYTHONPATH", "")])
    result = run_python(
        "import json, sys; from F20_helpers import workflow_source; "
        "print(json.dumps(workflow_source(sys.argv[1], sys.argv[2])))",
        args=[kind, str(directory)], env=env, timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode()
    return parse_json(result.stdout)


def graphviz_document(source):
    """Graphviz parses and lays out DOT independently of the product."""
    result = run_process([require_executable("dot"), "-Tjson"],
                         input=source.encode("utf-8"), timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    document = parse_json(result.stdout)
    assert document["directed"] is True
    return document


def workflow_observation(source):
    document = parse_dot(source, parser=graphviz_document)
    nodes = {node["_gvid"]: node["label"] for node in document["objects"]}
    edges = {(edge["tail"], edge["head"], edge.get("style", "solid"))
             for edge in document["edges"]}
    return nodes, edges


def normalize_relationships(edges):
    """Resource attachment has no directional promise; handoffs remain directed."""
    return {(min(a, b), max(a, b), style) if style in ("dotted", "dashed")
            else (a, b, style) for a, b, style in edges}


def unique_label(nodes, label):
    matches = [key for key, value in nodes.items() if value == label]
    assert len(matches) == 1, (label, nodes)
    return matches[0]
