# feature: F11
"""Public editable-model drivers and labelled aggregate readers."""
from _helpers import invoke


def solve_edited_model(n, expected=('ok', 'optimal')):
    result = invoke(n.optimize.solve_model, kwargs={
        'solver_name': 'highs', 'solver_options': {'threads': 1}})
    assert result.value == expected, result


def aggregate_cell(expression, component, carrier, bus):
    return expression.unstack('group').sel(
        component=component, carrier=carrier, bus=bus)
