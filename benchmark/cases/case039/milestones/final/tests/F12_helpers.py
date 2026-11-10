# feature: F12
"""Window scenarios using the existing, fully consumed Rust SQL transport."""
from F03_helpers import schema_run
from F02_helpers import scalar_rows

WINDOW_SETUP = {
    'create': ('E', 'CREATE TABLE w (id INTEGER, g TEXT, k INTEGER, h INTEGER, v INTEGER)'),
    'insert': ('E', "INSERT INTO w VALUES (4,'A',30,1,4),(8,NULL,4,1,10),(1,'A',10,1,8),(6,'B',5,1,20),(3,'A',10,2,12),(9,NULL,9,1,18),(2,'A',10,1,2),(5,'A',30,1,14),(7,NULL,4,1,6)"),
}


def window_queries(binary, queries, setup=WINDOW_SETUP):
    """Return successful rows; rejected queries remain assertion failures."""
    observed = schema_run(binary, {**setup, **{name: ('Q', sql) for name, sql in queries.items()}})
    return {name: scalar_rows(observed[name]) for name in queries}
