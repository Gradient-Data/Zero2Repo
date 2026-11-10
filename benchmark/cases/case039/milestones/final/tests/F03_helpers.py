# feature: F03
"""Named SQL observations for schema scenarios; reuse the native scalar transport."""
from F02_helpers import scalar_batch


def schema_run(binary, actions):
    """Run one fresh database, checking success/error before returning observations.

    E executes, Q fully consumes a query, X requires a query/consumption error.
    Error prose is diagnostic only, never an oracle for error classification.
    """
    results = scalar_batch(binary, [('Q' if mode == 'X' else mode, sql, ())
                                   for mode, sql in actions.values()])
    observed = dict(zip(actions, results))
    for name, (mode, sql) in actions.items():
        result = observed[name]
        if mode == 'X':
            assert 'error' in result, (name, sql, result)
        else:
            assert ('affected' if mode == 'E' else 'rows') in result, (name, sql, result)
    return observed
