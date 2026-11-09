# feature: F07
"""Application-owned session boundary and fresh-process durable-store driver."""
import copy
import json

from _helpers import run_python

from F01_helpers import RecordingModel  # Establish the delivered source import path.
from velmora import SQLiteSession


class ApplicationSession:
    """A caller-owned session adapter backed by a real SQLite session."""

    def __init__(self, session_id, path):
        self.session_id = session_id
        self.store = SQLiteSession(session_id=session_id, db_path=path)
        self.write_error = None
        self.failed_items = None

    async def get_items(self, limit=None):
        return await self.store.get_items(limit=limit)

    async def add_items(self, items):
        if self.write_error is not None:
            self.failed_items = copy.deepcopy(items)
            raise self.write_error
        await self.store.add_items(items)

    async def pop_item(self):
        return await self.store.pop_item()

    async def clear_session(self):
        await self.store.clear_session()

    def close(self):
        self.store.close()


DURABLE_SESSION_PROCESS = r'''
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))

async def main():
    kind, path, identity, operation = sys.argv[1:]
    engine = None
    if kind == "sqlite":
        from velmora import SQLiteSession
        session = SQLiteSession(session_id=identity, db_path=path)
    elif kind == "async_sqlite":
        from velmora.extensions.memory.async_sqlite_session import AsyncSQLiteSession
        session = AsyncSQLiteSession(identity, path)
    elif kind == "sqlalchemy":
        from sqlalchemy.ext.asyncio import create_async_engine
        from velmora.extensions.memory.sqlalchemy_session import SQLAlchemySession
        engine = create_async_engine("sqlite+aiosqlite:///" + path)
        session = SQLAlchemySession(identity, engine=engine, create_tables=True)
    else:
        raise ValueError("Unknown durable backend")
    try:
        if operation == "write":
            await session.add_items(json.load(sys.stdin))
        elif operation == "read":
            print(json.dumps(await session.get_items()))
        elif operation == "pop":
            print(json.dumps(await session.pop_item()))
        elif operation == "clear":
            await session.clear_session()
        else:
            raise ValueError("Unknown history operation")
    finally:
        if kind == "sqlite":
            session.close()
        elif kind == "async_sqlite":
            await session.close()
        if engine is not None:
            await engine.dispose()

asyncio.run(main())
'''


def session_user_item(text):
    return {"role": "user", "content": text}


def durable_session_operation(kind, path, operation, *, identity="durable", items=None):
    result = run_python(DURABLE_SESSION_PROCESS,
        args=(kind, str(path), identity, operation),
        input=None if items is None else json.dumps(items).encode())
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout
