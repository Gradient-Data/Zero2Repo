# feature: F10
"""Public XPath 3.1 projections; no inspection of collection internals."""
import xml.etree.ElementTree as ET
from velunara import XPathContext, VelunaraError
from velunara.xpath31 import XPath31Parser
from _helpers import observe, evaluate_expression
from F04_helpers import context_results


def xpath31_items(expression, *, parser=None, context=None):
    return context_results(expression,
                           parser=XPath31Parser() if parser is None else parser,
                           context=XPathContext(ET.Element('r')) if context is None else context)


def xpath31_error(expression, code, *, parser=None, context=None):
    outcome = observe(evaluate_expression,
                      XPath31Parser() if parser is None else parser, expression,
                      context=XPathContext(ET.Element('r')) if context is None else context,
                      result_method='select_results', consume=True,
                      exceptions=(VelunaraError,))
    assert isinstance(outcome.error, VelunaraError), outcome
    assert outcome.error.code == 'err:' + code, outcome.error


def xpath31_cases(cases):
    for expression, expected in cases:
        assert xpath31_items(expression) == expected, expression


def continued_random_numbers(seed, count):
    """Chain opaque generator values and project numbers through XPath only."""
    parser = XPath31Parser()
    initial = parser.parse('random-number-generator($seed)')
    advance = parser.parse('$g?next()')
    number = parser.parse('$g?number')
    states = list(initial.select_results(XPathContext(item=1, variables={'seed': seed})))
    assert len(states) == 1
    state = states[0]
    for _ in range(count):
        states = list(advance.select_results(XPathContext(item=1, variables={'g': state})))
        assert len(states) == 1
        state = states[0]
        values = list(number.select_results(XPathContext(item=1, variables={'g': state})))
        assert len(values) == 1
        yield values[0]


def continued_random_permutations(seed, members, count):
    """Advance opaque generator states and select each permutation through XPath."""
    members_snapshot = tuple(members)
    parser = XPath31Parser()
    initial = parser.parse('random-number-generator($seed)')
    advance = parser.parse('$g?next()')
    permute = parser.parse('$g?permute($members)')
    states = list(initial.select_results(XPathContext(item=1, variables={'seed': seed})))
    assert len(states) == 1
    state = states[0]
    for _ in range(count):
        states = list(advance.select_results(XPathContext(item=1, variables={'g': state})))
        assert len(states) == 1
        state = states[0]
        yield list(permute.select_results(XPathContext(
            item=1, variables={'g': state, 'members': list(members_snapshot)})))
