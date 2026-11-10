# feature: F11
"""Aggregation scenarios using the existing public SQL transport."""
from F03_helpers import schema_run
from F02_helpers import scalar_rows

AGGREGATE_SETUP = {
    'create': ('E', 'CREATE TABLE a (seq INTEGER, g TEXT, h INTEGER, v INTEGER, s TEXT)'),
    'insert': ('E', "INSERT INTO a VALUES (1,'A',1,NULL,NULL),(2,'A',1,2,'pear'),(3,'A',2,2,'pear'),(4,'B',1,8,'apple'),(5,NULL,1,14,'plum'),(6,NULL,1,NULL,NULL)"),
}


def aggregate_queries(binary, queries, extra=None):
    actions = {**AGGREGATE_SETUP, **({} if extra is None else extra)}
    actions.update({name: ('Q', sql) for name, sql in queries.items()})
    observations = schema_run(binary, actions)
    return {name: scalar_rows(observations[name]) for name in queries}


def aggregate_rows_equal(actual, expected, *, numeric_columns, ordered):
    """Compare selected numeric results by exact value, retaining all other types."""
    from fractions import Fraction
    from _helpers import rows_equal
    def normalize(rows):
        result = []
        for row in rows:
            row = list(row)
            for index in numeric_columns:
                value = row[index]
                if value is not None:
                    assert type(value) in (int, float), (index, value)
                    row[index] = Fraction(value)
            result.append(row)
        return result
    return rows_equal(normalize(actual), normalize(expected), ordered=ordered)
