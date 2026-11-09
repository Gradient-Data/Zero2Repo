# feature: F02
"""Bounded observations of public datatype and XPath entries."""
from velunara import XPath2Parser, VelunaraError
from _helpers import observe, evaluate_expression


def datatype_expression(expression, *, parser=None, context=None):
    outcome = observe(evaluate_expression,
                      XPath2Parser() if parser is None else parser,
                      expression, context=context, exceptions=(VelunaraError,))
    if outcome.error is not None:
        raise outcome.error
    return outcome.value


def datatype_failure(expression, error_class, code, *, parser=None, context=None):
    outcome = observe(evaluate_expression,
                      XPath2Parser() if parser is None else parser,
                      expression, context=context, exceptions=(VelunaraError,))
    assert isinstance(outcome.error, error_class), outcome
    assert outcome.error.code == 'err:' + code


def datatype_rejection(call, *args, error_class=ValueError, **kwargs):
    outcome = observe(call, *args, exceptions=(error_class,), **kwargs)
    assert isinstance(outcome.error, error_class), outcome
