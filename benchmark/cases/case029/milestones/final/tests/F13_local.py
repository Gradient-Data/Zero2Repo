# feature: F13
"""Acceptance of computer actions, shell execution, edits and local approvals."""
import pytest

from F08_helpers import pending_calls

from F01_helpers import function_call
from F03_helpers import tool_outputs
from F04_helpers import execution_run
from F12_helpers import raw_dict
from F13_helpers import (
    CanvasComputer, DirectoryExecutor, DirectoryEditor, computer_call, shell_call,
    patch_call, local_turn, local_output, local_model_output,
)
from velmora import ComputerTool, ShellTool, ApplyPatchTool, ModelBehaviorError, UserError, apply_diff
from openai.types.responses.response_computer_tool_call import PendingSafetyCheck


@pytest.mark.asyncio
async def test_f13_t01():
    computer = CanvasComputer()
    initial = computer.render()
    actions = [
        {"type": "click", "x": 2, "y": 3, "button": "right"},
        {"type": "type", "text": "discard"},
        {"type": "double_click", "x": 4, "y": 5},
        {"type": "type", "text": "local!"},
        {"type": "keypress", "keys": ["BACKSPACE"]},
        {"type": "scroll", "x": 6, "y": 7, "scroll_x": 3, "scroll_y": 9},
        {"type": "move", "x": 8, "y": 9},
        {"type": "drag", "path": [{"x": 10, "y": 11}, {"x": 12, "y": 13}]},
        {"type": "wait"}, {"type": "screenshot"},
    ]
    _, model, result = await local_turn(ComputerTool(computer=computer), computer_call(actions))
    assert result.final_output == "Local turn complete."
    assert computer.text == "local" and computer.offset == (3, 9)
    assert computer.pointer == (12, 13) and computer.ready
    assert [computer.pixels[y*32+x] for x, y in [(2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13)]] == [120, 160, 200, 40, 240, 240]
    image = tool_outputs(model.requests[-1], kind="computer_call_output")["local-call"]
    assert image["type"] == "computer_screenshot"
    assert image["image_url"] == "data:image/png;base64," + computer.render()
    assert computer.render() != initial
    # A batch without an explicit screenshot must also return its resulting display.
    _, model, _ = await local_turn(ComputerTool(computer=computer), computer_call([
        {"type": "click", "x": 15, "y": 16, "button": "left"},
        {"type": "type", "text": " next"}]))
    assert computer.text == "local next" and computer.pixels[16*32+15] == 80
    assert tool_outputs(model.requests[-1], kind="computer_call_output")["local-call"]["image_url"] == "data:image/png;base64," + computer.render()


@pytest.mark.asyncio
async def test_f13_t02():
    checks = [PendingSafetyCheck(id="review-a", code="sensitive", message="Review the target"),
              PendingSafetyCheck(id="review-b", code="external", message="Review the action")]
    for mode in ("accept", "reject-first", "reject-second", "unreviewed"):
        computer, seen = CanvasComputer(), []
        context = {"operator": mode}
        call = computer_call([{"type": "type", "text": "reviewed"}], checks)
        def review(data):
            assert computer.text == "" and computer.captures == 0
            assert data.ctx_wrapper.context is context
            assert data.agent.name == "Local application"
            assert data.tool_call.call_id == call.call_id
            seen.append(data.safety_check.model_dump())
            return data.safety_check.id != {"reject-first": "review-a", "reject-second": "review-b"}.get(mode)
        tool = ComputerTool(computer=computer, on_safety_check=None if mode == "unreviewed" else review)
        if mode.startswith("reject"):
            with pytest.raises(UserError):
                await local_turn(tool, call, context=context)
            assert computer.text == "" and computer.captures == 0
            reviewed = {check["id"]: check for check in seen}
            expected_checks = {check.id: check.model_dump() for check in checks}
            rejected_id = "review-a" if mode == "reject-first" else "review-b"
            assert rejected_id in reviewed
            assert reviewed.keys() <= expected_checks.keys()
            assert all(check == expected_checks[key] for key, check in reviewed.items())
        else:
            _, model, result = await local_turn(tool, call, context=context)
            assert not result.interruptions and result.final_output == "Local turn complete."
            assert computer.text == "reviewed"
            assert sorted(seen, key=lambda check: check["id"]) == ([] if mode == "unreviewed" else sorted(
                [check.model_dump() for check in checks], key=lambda check: check["id"]))
            output = local_output(result, "computer_call_output")
            acknowledged = output.get("acknowledged_safety_checks")
            if mode == "unreviewed":
                assert acknowledged is None
            else:
                assert sorted(acknowledged, key=lambda check: check["id"]) == sorted(
                    [check.model_dump() for check in checks], key=lambda check: check["id"])
            assert tool_outputs(model.requests[-1], kind="computer_call_output")["local-call"]["image_url"] == "data:image/png;base64," + computer.render()


@pytest.mark.asyncio
async def test_f13_t03(tmp_path):
    commands = ["printf 'from workspace' > artifact; cat artifact", "printf 'diagnostic' >&2; exit 7"]
    for timeout, length in ((2500, None), (None, None), (0, None), (2500, 0)):
        executor = DirectoryExecutor(tmp_path)
        constraints = {} if timeout is None else {"timeout_ms": timeout}
        if length is not None:
            constraints["max_output_length"] = length
        _, model, result = await local_turn(ShellTool(executor=executor), shell_call(commands, **constraints))
        assert result.final_output == "Local turn complete." and not result.interruptions
        assert len(executor.requests) == 1
        request = executor.requests[0].data.action
        assert request.commands == commands
        if timeout in (None, 0):
            assert request.timeout_ms is None or (type(request.timeout_ms) is int and request.timeout_ms == 0)
        else:
            assert request.timeout_ms == timeout
        assert request.max_output_length == length
        assert (tmp_path / "artifact").read_text() == "from workspace"
        output = tool_outputs(model.requests[-1], kind="shell_call_output")["local-call"]
        assert output == [
            {"stdout": "" if length == 0 else "from workspace", "stderr": "", "outcome": {"type": "exit", "exit_code": 0}},
            {"stdout": "", "stderr": "" if length == 0 else "diagnostic", "outcome": {"type": "exit", "exit_code": 7}},
        ]
    for timeout in (-1, 1.5, True, "2500"):
        executor = DirectoryExecutor(tmp_path)
        with pytest.raises(ModelBehaviorError):
            await local_turn(ShellTool(executor=executor), shell_call(["touch forbidden"], timeout_ms=timeout))
        assert executor.requests == [] and not (tmp_path / "forbidden").exists()


@pytest.mark.asyncio
async def test_f13_t04(tmp_path):
    editor = DirectoryEditor(tmp_path)
    tool = ApplyPatchTool(editor=editor)
    for kind, diff, expected in (
        ("create_file", "+header\n+old\n+footer\n+", "header\nold\nfooter\n"),
        ("update_file", "@@\n header\n-old\n+new\n footer", "header\nnew\nfooter\n"),
        ("delete_file", None, None),
    ):
        _, model, result = await local_turn(tool, patch_call(kind, "document", diff))
        assert result.final_output == "Local turn complete." and not result.interruptions
        assert len(editor.operations) > 0
        assert editor.operations[-1].type == kind and editor.operations[-1].path == "document"
        assert editor.operations[-1].diff == diff
        output = local_output(result, "apply_patch_call_output")
        assert output["status"] == "completed"
        sent = local_model_output(model, "apply_patch_call_output")
        assert sent["status"] == "completed"
        if expected is None:
            assert not (tmp_path / "document").exists()
        else:
            assert (tmp_path / "document").read_text() == expected
            assert output["output"] == expected
            assert sent["output"] == expected
    (tmp_path / "document").write_text("retained\n")
    for kind, diff in (("update_file", "@@\n-not present\n+changed"), ("create_file", "+collision")):
        _, model, result = await local_turn(tool, patch_call(kind, "document", diff))
        assert result.final_output == "Local turn complete."
        assert local_output(result, "apply_patch_call_output")["status"] == "failed"
        assert local_model_output(model, "apply_patch_call_output")["status"] == "failed"
        assert (tmp_path / "document").read_text() == "retained\n"


def test_f13_t05():
    before = "prologue\nred\ngreen\nblue\nepilogue\n"
    diff = "@@\n red\n-green\n+violet\n+orange\n blue"
    assert apply_diff(before, diff) == "prologue\nred\nviolet\norange\nblue\nepilogue\n"
    assert apply_diff("", "+first\n+second\n+", mode="create") == "first\nsecond\n"
    # Context selects which of several identical lines changes, and every hunk applies.
    repeated = "alpha\nitem\nbeta\nitem\ngamma\nitem\nomega\n"
    assert apply_diff(repeated, "@@\n beta\n-item\n+second\n@@\n gamma\n-item\n+third\n+extra") == (
        "alpha\nitem\nbeta\nsecond\ngamma\nthird\nextra\nomega\n")
    assert apply_diff(repeated, "@@\n gamma\n-item\n omega\n+tail") == "alpha\nitem\nbeta\nitem\ngamma\nomega\ntail\n"
    with pytest.raises(ValueError):
        apply_diff(repeated, "@@\n delta\n-item\n+replacement")
    for invalid in ("not a patch", "@@\n-absent context\n+replacement"):
        with pytest.raises(ValueError):
            apply_diff(before, invalid)
    with pytest.raises(ValueError):
        apply_diff("", "unprefixed", mode="create")


@pytest.mark.asyncio
async def test_f13_t06(tmp_path):
    for kind in ("shell", "patch"):
        def make(directory, **options):
            directory.mkdir(exist_ok=True)
            if kind == "shell":
                return ShellTool(executor=DirectoryExecutor(directory), **options)
            return ApplyPatchTool(editor=DirectoryEditor(directory), **options)
        def call():
            return (shell_call(["printf authorized >> effect"]) if kind == "shell" else
                    patch_call("create_file", "effect", "+authorized"))
        output_kind = "shell_call_output" if kind == "shell" else "apply_patch_call_output"
        for mode in ("default", "auto-allow", "auto-deny", "manual-allow", "manual-deny"):
            directory = tmp_path / (kind + mode)
            reviews = []
            def decide(context, item):
                reviews.append(raw_dict(item.raw_item)["call_id"])
                return {"approve": mode == "auto-allow", "reason": "Application decision"}
            options = {} if mode == "default" else {"needs_approval": True}
            if mode.startswith("auto"):
                options["on_approval"] = decide
            agent, model, result = await local_turn(make(directory, **options), call())
            if mode.startswith("manual"):
                assert set(pending_calls(result)) == {"local-call"}
                assert result.final_output is None and not (directory / "effect").exists()
                state = result.to_state()
                item = pending_calls(state)["local-call"]
                if mode == "manual-allow":
                    state.approve(item)
                else:
                    state.reject(item)
                result = await execution_run(agent, state)
            assert result.final_output == "Local turn complete." and not result.interruptions
            assert reviews == (["local-call"] if mode.startswith("auto") else [])
            output = local_output(result, output_kind)
            if kind == "shell" and mode.endswith("deny"):
                assert output["output"][0]["outcome"] == {"type": "exit", "exit_code": 1}
                assert output["output"][0]["stderr"]
            else:
                assert output["status"] == ("failed" if mode.endswith("deny") else "completed")
            if mode.endswith("deny"):
                assert not (directory / "effect").exists()
            else:
                assert (directory / "effect").read_text() == "authorized"
        # Persistent decisions are shared by kind/name across owners and new environments.
        for approved in (True, False):
            first = tmp_path / f"{kind}-sticky-{approved}"
            agent, _, result = await local_turn(make(first, needs_approval=True), call(), context={"tenant": "first"})
            state = result.to_state()
            item = pending_calls(state)["local-call"]
            if approved:
                state.approve(item, always_approve=True)
            else:
                state.reject(item, always_reject=True)
            result = await execution_run(agent, state)
            if kind == "shell" and not approved:
                assert local_output(result, output_kind)["output"][0]["outcome"] == {"type": "exit", "exit_code": 1}
                assert local_output(result, output_kind)["output"][0]["stderr"]
            else:
                assert local_output(result, output_kind)["status"] == ("completed" if approved else "failed")
            wrapper = result.context_wrapper
            wrapper.context = {"tenant": "replacement"}
            second = tmp_path / f"{kind}-replacement-{approved}"
            _, _, later = await local_turn(make(second, needs_approval=True), call().model_copy(update={"call_id": "later-call"}), context=wrapper, owner="Another application")
            assert later.final_output == "Local turn complete." and not later.interruptions
            if kind == "shell" and not approved:
                assert local_output(later, output_kind)["output"][0]["outcome"] == {"type": "exit", "exit_code": 1}
                assert local_output(later, output_kind)["output"][0]["stderr"]
            else:
                assert local_output(later, output_kind)["status"] == ("completed" if approved else "failed")
            if approved:
                assert (second / "effect").read_text() == "authorized"
            else:
                assert not (second / "effect").exists()
            # A different name must not inherit the previous tool's permission.
            other = tmp_path / f"{kind}-other-{approved}"
            _, _, pending = await local_turn(make(other, name="other-local-tool", needs_approval=True), call().model_copy(update={"call_id": "other-call"}), context=wrapper)
            assert set(pending_calls(pending)) == {"other-call"}
            assert pending.final_output is None and not (other / "effect").exists()
