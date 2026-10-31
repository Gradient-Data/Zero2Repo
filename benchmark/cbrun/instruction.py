"""Agent instruction assembly for cbrun.

The prompt states only what the benchmark defines: the context the agent has,
what it must build, what it must not do, how to submit, and how it is scored.
It does not prescribe a way of working. Nothing about the hidden acceptance
tests leaks. Specification bodies (PRD, Interface Contract, optional hardware)
stay on disk at fixed container paths; the prompt only names those paths so it
stays well under the Linux per-argument size limit.
"""

from __future__ import annotations

from coding_bench_harbor.adapter import build_contract_notes

from .submit import CONTAINER_SUBMIT_PATH, SUBMIT_TOKEN

__all__ = ["build_instruction"]

# Where the deliverable image exposes the public spec and the agent workspace.
PRD_CONTAINER_PATH = "/environment/prd/Full_PRD.md"
CONTRACT_CONTAINER_PATH = "/environment/Interface_Contract.md"
HARDWARE_CONTAINER_PATH = "/environment/Hardware_Requirements.md"
WORKSPACE_CONTAINER_PATH = "/app"

_INSTRUCTION_PREAMBLE = f"""\
# Task

Build the project specified in the files below, from scratch, in `{WORKSPACE_CONTAINER_PATH}`.

"""


def _format_budget(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{minutes} minutes"


def _environment_notes(*, has_hardware: bool, agent_timeout_sec: float) -> str:
    hardware_line = ""
    if has_hardware:
        hardware_line = (
            f"* Hardware requirements: `{HARDWARE_CONTAINER_PATH}`.\n"
        )
    return f"""\
## Context

* Workspace: `{WORKSPACE_CONTAINER_PATH}`, your current working directory. It starts empty.
* Specification: the PRD at `{PRD_CONTAINER_PATH}` and the Interface Contract at
  `{CONTRACT_CONTAINER_PATH}`.
{hardware_line}* Language runtimes and dependencies the project needs are installed.
* The only limit is a wall-clock budget of {_format_budget(agent_timeout_sec)} for the whole session; if
  you have not submitted when it runs out, the session is stopped and the hidden
  tests run against `{WORKSPACE_CONTAINER_PATH}` as it stands.
* GitHub and other code-hosting sites are not reachable from this environment.

## Rules

* The product behavior must be your own code. Do not download, clone, vendor,
  copy, or install an existing implementation of the product (for example via
  `pip install`, `npm install`, or `cargo add`). General-purpose libraries and
  tools are allowed.
* Do not use a runtime- or toolchain-bundled implementation of the same kind of
  product as a dependency or an oracle, and do not read, copy, disassemble, or
  decompile one. This covers every copy already in this environment: standard
  library modules, packages vendored inside other tools, and packages the
  agent tooling itself installed. Package managers and build tools may load
  them for their own work.
* File access to such implementations is monitored for the whole session, by
  file opens, whatever tool or language performs them. Do not interfere with
  the monitoring: do not stop or pause its processes, change or remove its
  files, or hide or disguise an access.
* A first violation stops your session; you are told what was observed and
  get one more session to continue. A second violation fails the attempt.
* Hidden acceptance tests are not in this container. Do not look for them and
  do not special-case any test.

## Submit

* Write exactly one line to `{CONTAINER_SUBMIT_PATH}`: `{SUBMIT_TOKEN}`.
* Ending the session is not a submission. Ending it before the time budget runs
  out without a valid submit file fails this attempt, and the hidden tests do
  not run.

## Scoring

* After a valid submit, or when the time budget runs out, the hidden acceptance
  tests run against your final `{WORKSPACE_CONTAINER_PATH}` and give a binary
  pass/fail reward.
"""


def build_instruction(
    *,
    has_hardware: bool = False,
    agent_timeout_sec: float,
    build_command: str = "",
    workdir: str = ".",
    test_env: dict[str, str] | None = None,
) -> str:
    """Assemble the agent prompt: preamble, environment notes, build contract.

    Specification bodies are not inlined. The agent must read the files at
    ``PRD_CONTAINER_PATH``, ``CONTRACT_CONTAINER_PATH``, and (when present)
    ``HARDWARE_CONTAINER_PATH``. No hidden-test content is included.
    """
    parts: list[str] = [_INSTRUCTION_PREAMBLE.rstrip(), "\n\n"]
    parts.append(_environment_notes(has_hardware=has_hardware, agent_timeout_sec=agent_timeout_sec).rstrip())
    parts.append("\n\n")
    parts.append(build_contract_notes(build_command, workdir, test_env).rstrip())
    parts.append("\n")
    return "".join(parts)
