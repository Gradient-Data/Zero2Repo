# feature: F11
"""Authored asynchronous workloads using real workflow expressions."""
from velnora import task

from F01_helpers import AuthoredFailure, fail, identity
from F08_helpers import audit


@task(namespace='f11.eager', cache=False)
async def double(value):
    return value * 2


@task(namespace='f11.eager', cache=False)
async def branch_and_iterate(values):
    items = await identity(values)
    total, selected = 0, []
    for item in items:
        value = await double(item)
        if await identity(value > 5):
            selected.append(value)
            total += value
        else:
            total -= value
    return {'total': await (identity(total) + 3), 'selected': selected}


@task(namespace='f11.eager', cache=False)
def synchronous_entry(values):
    return branch_and_iterate(values)


@task(namespace='f11.errors', cache=False)
async def async_failure(message):
    raise AuthoredFailure(message)


@task(namespace='f11.errors', cache=False)
async def await_failure(kind, message, handle):
    try:
        if kind == 'sync':
            return await fail(message)
        return await async_failure(message)
    except AuthoredFailure as error:
        if not handle:
            raise
        return await identity(('recovered', error.args[0]))


@task(namespace='f11.errors', cache=False)
def failure_entry(kind, message, handle):
    return await_failure(kind, message, handle)


async def policy_body(value):
    resolved = await identity(value)
    return resolved * 3 + 2


async def audited_body(value, path):
    audit(path, 'body')
    resolved = await identity(value)
    return resolved * 3 + 2
