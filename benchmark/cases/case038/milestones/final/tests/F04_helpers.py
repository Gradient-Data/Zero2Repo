# feature: F04
"""Bounded consumption of public expression result iterators."""
from velunara import XPath2Parser
from _helpers import observe, evaluate_expression


def context_results(expression, *, parser=None, context=None):
    """Return public selected items, preserving source objects and sequences."""
    return observe(evaluate_expression, XPath2Parser() if parser is None else parser,
                   expression, context=context, result_method='select_results',
                   consume=True).value
