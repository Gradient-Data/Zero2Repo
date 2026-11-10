# feature: F04
"""Importable authored tasks for scoped option and context observations."""
from velnora import task
from velnora.context import get_context
from velnora.scheduler import JobInfo


execution_state = []


@task(namespace="f04.options")
def execution_place(value):
    execution_state.append(value)
    return value * 7


@task(namespace="f04.options", mode="thread")
def declared_place(value):
    execution_state.append(value)
    return value * 7


@task(namespace="f04.options", priority=11)
def option_value(value, info=JobInfo()):
    priority = info.options["priority"]
    return priority, value * priority


@task(namespace="f04.context")
def context_leaf(value=get_context("tool")):
    return value


@task(namespace="f04.context")
def context_branch(value=get_context("tool")):
    return {"self": value, "child": context_leaf()}
