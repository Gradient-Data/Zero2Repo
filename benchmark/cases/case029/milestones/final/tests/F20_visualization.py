# feature: F20
"""Acceptance checks for saved workflow content and identity-preserving graphs."""
from _helpers import read_dot
from F20_helpers import (
    graphviz_document, render_workflow, unique_label, workflow_observation, normalize_relationships,
)


def test_f20_t01(tmp_path):
    source = render_workflow("expansion", tmp_path)
    # Parse both carriers independently, not merely compare them with each other.
    saved = read_dot(tmp_path / "workflow.gv", parser=graphviz_document)
    saved_source = (tmp_path / "workflow.gv").read_text(encoding="utf-8")
    assert saved["directed"] is True
    for dot_source in (source, saved_source):
        nodes, edges = workflow_observation(dot_source)
        expected_labels = {
            "Intake", "Validate", "Directory", "Dispatcher", "Route", "Specialist",
            "Search", "Knowledge", "Archive", "Record", "Dynamic destination",
        }
        ids = {label: unique_label(nodes, label) for label in expected_labels}
        start = unique_label(nodes, "__start__")
        assert (start, ids["Intake"], "solid") in edges
        actual_labels = set(nodes.values()) - {"__start__", "__end__"}
        assert actual_labels == expected_labels
        expected = {
            ("Intake", "Dispatcher", "solid"),
            ("Intake", "Dynamic destination", "solid"),
            ("Dispatcher", "Specialist", "solid"),
            ("Specialist", "Archive", "solid"),
        }
        for agent, resource, style in (
            ("Intake", "Validate", "dotted"), ("Intake", "Directory", "dashed"),
            ("Dispatcher", "Route", "dotted"), ("Specialist", "Search", "dotted"),
            ("Specialist", "Knowledge", "dashed"), ("Archive", "Record", "dotted"),
        ):
            expected.update({(agent, resource, style), (resource, agent, style)})
        application_ids = set(ids.values())
        actual = {(nodes[a], nodes[b], style) for a, b, style in edges
                  if a in application_ids and b in application_ids}
        assert normalize_relationships(actual) == normalize_relationships(expected)


def test_f20_t02(tmp_path):
    nodes, edges = workflow_observation(render_workflow("identities", tmp_path))
    entry = unique_label(nodes, "Entry")
    first_leaf = unique_label(nodes, "First endpoint")
    second_leaf = unique_label(nodes, "Second endpoint")
    shared = {key for key, label in nodes.items() if label == "Shared"}
    assert len(shared) == 6
    agents = []
    for leaf in (first_leaf, second_leaf):
        candidates = {a for a, b, style in edges if b == leaf and style == "solid"}
        assert len(candidates) == 1
        agents.append(candidates.pop())
    first, second = agents
    assert first != second
    expected = {(entry, first, "solid"), (entry, second, "solid"),
                (first, second, "solid"), (second, first, "solid"),
                (first, first_leaf, "solid"), (second, second_leaf, "solid")}
    resource_ids = []
    for agent in agents:
        for style in ("dotted", "dashed"):
            targets = {b if a == agent else a for a, b, relation in edges
                       if agent in (a, b) and relation == style}
            assert len(targets) == 1
            target = targets.pop()
            assert target in shared
            resource_ids.append(target)
            expected.update({(agent, target, style), (target, agent, style)})
    assert set(agents + resource_ids) == shared
    assert len(set(resource_ids)) == 4
    application = shared | {entry, first_leaf, second_leaf}
    assert normalize_relationships({(a, b, style) for a, b, style in edges
            if a in application and b in application}) == normalize_relationships(expected)
    assert set(nodes.values()) - {"__start__", "__end__"} == {
        "Entry", "Shared", "First endpoint", "Second endpoint"}
