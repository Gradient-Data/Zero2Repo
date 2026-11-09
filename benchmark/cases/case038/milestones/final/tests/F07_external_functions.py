# feature: F07
"""Acceptance coverage for caller-defined XPath functions."""
import xml.etree.ElementTree as ET

from velunara import XPath2Parser, XPathContext, VelunaraTypeError
from velunara.xpath30 import XPath30Parser
from velunara.xpath31 import XPath31Parser

from F02_helpers import datatype_failure, datatype_rejection
from F04_helpers import context_results


def test_external_function_invocation_namespaces_and_isolation():
    for factory in (XPath2Parser, XPath30Parser, XPath31Parser):
        bindings = {'a': 'urn:caller:a', 'alias': 'urn:caller:a', 'b': 'urn:caller:b'}
        parser = factory(namespaces=bindings)

        def caller_calc(x):
            return x * 3 - 2

        def other(x):
            return x + 11

        parser.external_function(caller_calc)
        parser.external_function(other, name='caller_calc', prefix='a')
        parser.external_function(lambda x: x * x, name='caller_calc', prefix='b')
        for expression, expected in (
            ('caller_calc(5)', [13]), ('fn:caller_calc(-2)', [-8]),
            ('caller_calc(2 + 3) + caller_calc(4)', [23]),
            ('a:caller_calc(5)', [16]), ('alias:caller_calc(2)', [13]),
            ('b:caller_calc(5)', [25]),
        ):
            assert context_results(expression, parser=parser) == expected
        fresh = factory(namespaces=bindings)
        assert context_results('abs(-7)', parser=fresh) == [7]
        for expression in ('caller_calc(5)', 'a:caller_calc(5)', 'b:caller_calc(5)'):
            datatype_failure(expression, VelunaraTypeError, 'XPST0017', parser=fresh)
        fresh.external_function(lambda x: x - 10, name='caller_calc')
        assert context_results('caller_calc(5)', parser=fresh) == [-5]
        assert context_results('caller_calc(5)', parser=parser) == [13]


def test_external_function_positional_default_and_variadic_arity():
    parser = XPath2Parser()

    def fixed(x, y):
        return x * 10 + y

    def defaulted(x, y=4, z=7):
        return x * 100 + y * 10 + z

    def all_defaulted(x=3, y=8):
        return x * 10 + y

    def variadic(x, *items):
        return x + sum(items)

    def zero():
        return 'ready'

    def spread(first, second, *rest):
        return [first, second, *rest]

    for callback in (fixed, defaulted, all_defaulted, variadic, zero, spread):
        parser.external_function(callback)
    for expression, expected in (
        ('fixed(2, 9)', [29]), ('defaulted(2)', [247]),
        ('defaulted(2, 6)', [267]), ('defaulted(2, 6, 9)', [269]),
        ('all_defaulted()', [38]), ('all_defaulted(5)', [58]),
        ('all_defaulted(5, 1)', [51]), ('variadic(6)', [6]),
        ('variadic(6, 2)', [8]), ('variadic(6, 2, 4, 8, 10)', [30]),
        ('zero()', ['ready']),
        # Two required positionals before the variadic tail; a returned list
        # is the complete result sequence.
        ('spread(4, 5)', [4, 5]), ('spread(4, 5, 6, 7)', [4, 5, 6, 7]),
        ('count(spread(4, 5, 6))', [3]),
    ):
        assert context_results(expression, parser=parser) == expected
    for expression in ('fixed()', 'fixed(2)', 'fixed(1, 2, 3)',
                       'defaulted()', 'defaulted(1, 2, 3, 4)',
                       'all_defaulted(1, 2, 3)', 'variadic()', 'zero(1)',
                       'spread()', 'spread(4)'):
        datatype_failure(expression, VelunaraTypeError, 'XPST0017', parser=parser)


def test_external_function_sequence_argument_and_result_types():
    parser = XPath2Parser()

    def weighted(items):
        return sum((index + 1) * value for index, value in enumerate(items))

    parser.external_function(weighted, sequence_types=('xs:integer*', 'xs:integer'))
    for expression, expected in (('weighted(())', [0]),
                                 ('weighted((2, 5, 9))', [39])):
        assert context_results(expression, parser=parser) == expected
    datatype_failure('weighted((2, "wrong", 9))', VelunaraTypeError,
                     'XPTY0004', parser=parser)

    def identity(value):
        return value

    # Every declared argument type is enforced, not only the first one.
    parser.external_function(lambda label, number: label + str(number), name='label',
                             sequence_types=('xs:string', 'xs:integer', 'xs:string'))
    assert context_results('label("n", 3)', parser=parser) == ['n3']
    for expression in ('label("n", "3")', 'label(3, 3)', 'label("n", (3, 4))'):
        datatype_failure(expression, VelunaraTypeError, 'XPTY0004', parser=parser)

    parser.external_function(identity, name='single',
                             sequence_types=('xs:integer', 'xs:integer'))
    assert context_results('single(8)', parser=parser) == [8]
    for expression in ('single(())', 'single((2, 3))', 'single("wrong")'):
        datatype_failure(expression, VelunaraTypeError, 'XPTY0004', parser=parser)

    # The host controls the return value; XPath must validate it after the call.
    parser.external_function(identity, name='checked-result',
                             sequence_types=('item()*', 'xs:integer+'))
    assert context_results('checked-result((3, 7))', parser=parser) == [3, 7]
    for expression in ('checked-result(())', 'checked-result((3, "wrong"))'):
        datatype_failure(expression, VelunaraTypeError, 'XPTY0004', parser=parser)
    parser.external_function(identity, name='one-result',
                             sequence_types=('item()*', 'xs:integer'))
    assert context_results('one-result(6)', parser=parser) == [6]
    datatype_failure('one-result((6, 7))', VelunaraTypeError, 'XPTY0004', parser=parser)

    parser.external_function(lambda nodes: nodes[-1], name='last-node',
                             sequence_types=('element()+', 'element()'))
    root = ET.fromstring('<r><v/><v/><v/></r>')
    assert context_results('last-node(v)', parser=parser,
                           context=XPathContext(root)) == [root[2]]
    datatype_failure('last-node(())', VelunaraTypeError, 'XPTY0004', parser=parser)


def test_external_function_registration_names_prefixes_and_constructs():
    # Reserved names are version specific (XPath 2.0/3.0/3.1 appendix A.3):
    # a name reserved only by a later version remains usable in earlier ones.
    for factory, reserved, unreserved in (
            (XPath2Parser, ('element', 'if'), ('function', 'switch', 'namespace-node')),
            (XPath30Parser, ('element', 'function', 'switch', 'namespace-node'), ('map', 'array')),
            (XPath31Parser, ('element', 'function', 'switch', 'namespace-node', 'map', 'array'),
             ())):
        for name in ('名字', 'écho', '_local', 'a-b', 'b.c', 'a·b'):
            parser = factory(namespaces={'u': 'urn:caller:names'})
            parser.external_function(lambda x: x + 2, name=name, prefix='u')
            assert context_results('u:' + name + '(5)', parser=parser) == [7]
        for name in unreserved:
            parser = factory()
            parser.external_function(lambda x: x + 3, name=name)
            assert context_results(name + '(5)', parser=parser) == [8]
        # NCName rules apply to every character, not only the first one.
        for name in ('1bad', 'a:b', 'a b', 'a/b', '-lead', '.lead', '·lead', 'a×b',
                     *reserved, 'some'):
            parser = factory()
            datatype_rejection(parser.external_function, lambda x: x, name=name,
                               error_class=ValueError)
            assert context_results('abs(-5)', parser=parser) == [5]
        parser = factory()
        datatype_rejection(parser.external_function, lambda x: x, name='unbound',
                           prefix='missing', error_class=KeyError)
        parser.external_function(lambda x: x + 1, name='bound')
        assert context_results('bound(5)', parser=parser) == [6]


def test_external_function_duplicate_rejection_preserves_original():
    for factory in (XPath2Parser, XPath30Parser, XPath31Parser):
        parser = factory(namespaces={'a': 'urn:caller:duplicates',
                                     'alias': 'urn:caller:duplicates'})
        parser.external_function(lambda x: x * 4, name='preserved', prefix='a')
        assert context_results('a:preserved(3)', parser=parser) == [12]
        for prefix in ('a', 'alias'):
            datatype_rejection(parser.external_function, lambda x: x - 100,
                               name='preserved', prefix=prefix, error_class=ValueError)
            assert context_results('a:preserved(3)', parser=parser) == [12]
        parser.external_function(lambda x: x + 6, name='preserved')
        datatype_rejection(parser.external_function, lambda x: x - 100,
                           name='preserved', error_class=ValueError)
        assert context_results('preserved(3)', parser=parser) == [9]
        # Registration order is irrelevant: once the same local name exists in
        # the function namespace, a second prefixed registration is still a
        # duplicate under either bound prefix.
        parser.external_function(lambda x: x + 1, name='kept')
        parser.external_function(lambda x: x * 5, name='kept', prefix='a')
        for prefix in ('a', 'alias', None, 'fn'):
            datatype_rejection(parser.external_function, lambda x: x - 100,
                               name='kept', prefix=prefix, error_class=ValueError)
            assert context_results('alias:kept(3)', parser=parser) == [15]
            assert context_results('kept(3)', parser=parser) == [4]
        for prefix in (None, 'fn'):
            datatype_rejection(parser.external_function, lambda *args: 'replacement',
                               name='concat', prefix=prefix, error_class=ValueError)
            assert context_results('concat("ab", "cd")', parser=parser) == ['abcd']
