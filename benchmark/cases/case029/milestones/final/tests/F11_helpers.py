# feature: F11
"""Retention test drivers using public entries and independent application clocks."""
import json
import os
from contextlib import contextmanager

from F02_helpers import model_peer
from F01_helpers import RecordingModel
from _helpers import run_python, run_process, invoke
from openai import AsyncOpenAI
from velmora import Agent, RunConfig, Runner, ModelSettings, Usage
from velmora.extensions.memory.advanced_sqlite_session import AdvancedSQLiteSession


@contextmanager
def compaction_peer(output):
    payload = {"id": "compact_peer", "object": "response.compaction", "created_at": 1,
               "output": output, "usage": {"input_tokens": 2, "output_tokens": 1,
                                           "total_tokens": 3}}
    with model_peer(replies=[(200, payload, {})] * 30) as (url, requests):
        yield AsyncOpenAI(base_url=url, api_key="offline", max_retries=0), requests


async def retention_run(model, session, prompt="Continue.", **config):
    agent = Agent(name="Retention", model=model, model_settings=ModelSettings(store=False))
    return await invoke(Runner.run, agent, prompt, session=session, timeout=15,
                        run_config=RunConfig(tracing_disabled=True, **config))


def advanced_store(path):
    return AdvancedSQLiteSession(session_id="branches", db_path=path, create_tables=True)


CLOCK_SOURCE = r'''
#include <time.h>
#include <stdlib.h>
#include <dlfcn.h>
time_t time(time_t *target) {
    time_t result = (time_t)atoll(getenv("RETENTION_CLOCK"));
    if (target) *target = result;
    return result;
}
int clock_gettime(clockid_t clock_id, struct timespec *target) {
    if (clock_id == CLOCK_REALTIME) {
        target->tv_sec = (time_t)atoll(getenv("RETENTION_CLOCK"));
        target->tv_nsec = 0;
        return 0;
    }
    int (*original)(clockid_t, struct timespec *) = dlsym(RTLD_NEXT, "clock_gettime");
    return original(clock_id, target);
}
'''

ENCRYPTED_PROCESS = r'''
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))
from velmora import SQLiteSession
from velmora.extensions.memory.encrypt_session import EncryptedSession
async def main():
    options = json.load(sys.stdin)
    store = SQLiteSession(session_id="backing", db_path=options.pop("path"))
    operation = options.pop("operation")
    items = options.pop("items", None)
    limit = options.pop("limit", None)
    wrapper = EncryptedSession(underlying_session=store, **options)
    try:
        if operation == "write":
            await wrapper.add_items(items)
        elif operation == "read":
            print(json.dumps(await wrapper.get_items(limit)))
        else:
            raise ValueError("Unknown encrypted operation")
    finally:
        store.close()
asyncio.run(main())
'''


def build_application_clock(directory):
    source = directory / "wall_clock.c"
    library = directory / "wall_clock.so"
    source.write_text(CLOCK_SOURCE)
    result = run_process(["cc", "-shared", "-fPIC", str(source), "-o", str(library)])
    assert result.returncode == 0, result.stderr.decode()
    return library


def encrypted_process(path, operation, *, clock=None, now=2000000000, **options):
    env = os.environ.copy()
    if clock is not None:
        env.update(LD_PRELOAD=str(clock), RETENTION_CLOCK=str(now))
    return run_python(ENCRYPTED_PROCESS, env=env, input=json.dumps({
        "path": str(path), "operation": operation, "session_id": "protected",
        "encryption_key": "application-secret-with-entropy-3917", **options,
    }).encode())


def encrypted_success(path, operation, **options):
    result = encrypted_process(path, operation, **options)
    assert result.returncode == 0, result.stderr.decode()
    return json.loads(result.stdout) if operation == "read" else None


class RetentionUsageModel(RecordingModel):
    """Application provider reports known usage through the public model response."""
    async def get_response(self, *args, **kwargs):
        response = await super().get_response(*args, **kwargs)
        response.usage = Usage(requests=2, input_tokens=23, output_tokens=7, total_tokens=30)
        return response


class IdentityModel(RecordingModel):
    """Application provider reporting a caller-chosen response identity."""
    def __init__(self, identity, *outputs):
        super().__init__(*outputs)
        self.identity = identity

    async def get_response(self, *args, **kwargs):
        response = await super().get_response(*args, **kwargs)
        response.response_id = self.identity
        return response
