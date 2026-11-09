# feature: F09
"""Public lockfile JSON and command observations."""
from _helpers import read_json
from F01_helpers import cli_success


LOCK_CATEGORIES = ('requires', 'build_requires', 'python_requires', 'config_requires')


def lock_records(path, category):
    """Read explicit reference strings and optional recorded timestamps."""
    assert category in LOCK_CATEGORIES
    values = read_json(path)[category]
    result = {}
    for value in values:
        reference, separator, timestamp = value.partition('%')
        result[reference] = float(timestamp) if separator else None
    return result


def capture_lock(client, consumer, output, *args):
    cli_success(client, 'lock', 'create', consumer, '-nr', '--lockfile-out', output, *args)
    return output


def edit_lock(client, operation, source, output, *args):
    cli_success(client, 'lock', operation, '--lockfile', source, '--lockfile-out', output, *args)
    return output
