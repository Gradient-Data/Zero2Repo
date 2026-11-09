# feature: F09
"""Real SQLite resources and independent observations for handle workflows."""
import sqlite3

from velnora import Handle, task
from F08_helpers import audit


class DatabaseHandle(Handle):
    type_name = 'f09.DatabaseHandle'

    def __init__(self, name, path):
        self.connection = sqlite3.connect(path, check_same_thread=False, timeout=20)

    def put(self, key, value):
        with self.connection:
            self.connection.execute('INSERT OR REPLACE INTO state VALUES (?, ?)', (key, value))
            self.connection.execute('INSERT INTO effects(label, value) VALUES (?, ?)', (key, value))

    def get(self, key):
        row = self.connection.execute('SELECT value FROM state WHERE label = ?', (key,)).fetchone()
        if row is None:
            raise LookupError(key)
        return row[0]


def create_resource(path):
    """Create an author-owned external resource, independently of the product."""
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE state(label TEXT PRIMARY KEY, value INTEGER)')
        connection.execute('CREATE TABLE effects(sequence INTEGER PRIMARY KEY, label TEXT, value INTEGER)')


def resource_snapshot(path):
    """Read committed resource state and effects; every query failure propagates."""
    with sqlite3.connect(path) as connection:
        state = dict(connection.execute('SELECT label, value FROM state'))
        effects = list(connection.execute('SELECT label, value FROM effects ORDER BY sequence'))
    return state, effects


@task(namespace='f09.restore')
def open_resource(path, audit_path):
    audit(audit_path, 'open')
    handle = DatabaseHandle('resource', path)
    handle.put('seed', 31)
    return handle


@task(namespace='f09.restore', cache_scope='NONE')
def use_resource(handle, increment):
    value = handle.get('seed') + increment
    handle.put('used', value)
    return value


def transition_first(handle, factor):
    handle.put('changed', handle.get('seed') * factor)
    return handle


def transition_second(handle, factor):
    handle.put('changed', handle.get('seed') * factor + 7)
    return handle
