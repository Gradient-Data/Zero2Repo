# feature: F09
"""Text acceptance tests through String keywords and its public random entry."""
from itertools import product, combinations
from collections import Counter
import re
import string

from _helpers import call_public, require_python
from F09_helpers import (StringWorkflow, frequency_cells, assert_frequency_budget,
                         CHARACTER_COLLECTIONS)


def test_case_split_slice_delimiter_and_format():
    require_python((3, 13))
    w = StringWorkflow()
    for source in ('Café aZ', b'\xc9aZ'):
        w.operation('Convert To Lower Case', source, expected=source.lower())
        w.operation('Convert To Upper Case', source, expected=source.upper())
    for mode, expected in [('both','elm'), ('left','elmxy'), ('right','xyelm')]:
        w.operation('Strip String', 'xyelmxy', mode=mode, characters='xy', expected=expected)
    w.operation('Strip String', ' \t elm \n', expected='elm')
    w.operation('Split String To Characters', 'aé!', expected=['a','é','!'])
    w.operation('Split String', ' \t oak  elm\nash ', expected=['oak','elm','ash'])
    w.operation('Split String', 'oak::elm::::ash', '::', expected=['oak','elm','','ash'])
    w.operation('Split String', 'a::b::c', '::', 1, expected=['a','b::c'])
    w.operation('Split String From Right', 'a::b::c', '::', 1, expected=['a::b','c'])
    # A limit above one distinguishes a counted limit from a split-once flag.
    w.operation('Split String', 'a::b::c::d', '::', 2, expected='a::b::c::d'.split('::', 2))
    w.operation('Split String From Right', 'a::b::c::d', '::', 2, expected='a::b::c::d'.rsplit('::', 2))
    w.operation('Get Substring', 'abcdef', 1, -1, expected='bcde')
    w.operation('Get Substring', 'abcdef', -2, expected='ef')
    w.operation('Split To Lines', 'oak\nelm\nash\n', 1, -1, expected=['elm'])
    w.operation('Get Line', 'oak\nelm\nash\n', -1, expected='ash')
    w.operation('Get Line', 'oak\nelm\nash\n', 1, expected='elm')
    for keyword, expected in [('Fetch From Left','oak'), ('Fetch From Right','ash')]:
        w.operation(keyword, 'oak/elm/ash', '/', expected=expected)
        w.operation(keyword, 'oak/elm/ash', '?', expected='oak/elm/ash')
    w.operation('Split To Lines', b'a\nb\n', expected=[b'a',b'b'])
    # Byte sources stay bytes through every operation the Contract lists as str or bytes.
    w.operation('Strip String', b'xyelmxy', mode='left', characters=b'xy', expected=b'elmxy')
    w.operation('Get Substring', b'abcdef', 1, -1, expected=b'bcde')
    w.operation('Get Line', b'a\nb\n', 1, expected=b'b')
    w.operation('Fetch From Left', b'oak/elm/ash', b'/', expected=b'oak')
    w.operation('Fetch From Right', b'oak/elm/ash', b'/', expected=b'ash')
    fmt = '{0:04d}/{name!r}/{1:.2f}'
    w.operation('Format String', fmt, 17, 2.375, name='elm', expected=fmt.format(17,2.375,name='elm'))
    for fmt, args in [('{missing}', ()), ('{2}', ('a',)), ('{0:invalid}', (17,))]:
        w.operation('Format String', fmt, *args, reject=True)
    w.run_and_verify()


def test_literal_replacement_limits_and_source():
    w = StringWorkflow()
    for source, old, new in [('oak-oak-oak','oak','elm'), (b'ab-ab-ab',b'ab',b'X')]:
        for count in (-7, 0, 1, 2):
            w.operation('Replace String', source, old, new, count, expected=source.replace(old,new,count))
        w.operation('Replace String', source, old, new, expected=source.replace(old,new))
    w.operation('Remove String', 'red/green/red/blue', 'red', '/blue', expected='/green/')
    w.operation('Remove String', b'abc-abc', b'ab', expected=b'c-c')
    w.run_and_verify()


def test_line_selection_count_and_properties():
    w = StringWorkflow()
    source = 'ab7\nxab7\nab7 tail\nAB7\nnone\n'
    w.operation('Get Line Count', source, expected=5)
    w.operation('Get Line Count', '', expected=0)
    w.operation('Get Line Count', 'oak\nelm', expected=2)
    w.operation('Get Lines Containing String', source, 'ab7', expected='ab7\nxab7\nab7 tail')
    w.operation('Get Lines Containing String', source, 'ab7', ignore_case=True, expected='ab7\nxab7\nab7 tail\nAB7')
    w.operation('Get Lines Matching Pattern', source, 'ab?', expected='ab7')
    w.operation('Get Lines Matching Pattern', source, 'ab?', ignore_case=True, expected='ab7\nAB7')
    w.operation('Get Lines Matching Regexp', source, 'ab[0-9]', expected='ab7')
    w.operation('Get Lines Matching Regexp', source, 'ab[0-9]', partial_match=True, expected='ab7\nxab7\nab7 tail')
    w.operation('Get Lines Matching Regexp', source, 'ab[0-9]', flags='IGNORECASE', expected='ab7\nAB7')
    w.operation('Get Lines Matching Pattern', source, 'missing*', expected='')
    for keyword, good, bad in [
        ('Should Be String','text',b'text'), ('Should Not Be String',b'text','text'),
        ('Should Be Unicode String','é',b'x'), ('Should Be Byte String',b'text','text'),
        ('Should Be Lower Case','é abc 12','aBc'), ('Should Be Upper Case','É ABC 12','ABc')]:
        w.operation(keyword, good)
        # Negative paths are separate Velun tests so their positive FAIL carrier is read.
    for keyword, bad in [('Should Be String',b'x'), ('Should Not Be String','x'),
                         ('Should Be Unicode String',b'x'), ('Should Be Byte String','x'),
                         ('Should Be Lower Case','aBc'), ('Should Be Upper Case','ABc'),
                         ('Should Be Lower Case','123 !'), ('Should Be Upper Case','123 !')]:
        w.operation(keyword, bad, reject=True)
    w.run_and_verify()


def test_encoding_policies_and_independent_bytes():
    require_python((3, 13))
    w = StringWorkflow()
    for encoding in ('utf-8', 'utf-16-le', 'iso-8859-1'):
        text = 'Café £'
        encoded = text.encode(encoding)
        w.operation('Encode String To Bytes', text, encoding, expected=encoded)
        w.operation('Decode Bytes To String', encoded, encoding, expected=text)
    for policy in ('replace','ignore'):
        w.operation('Encode String To Bytes', 'é-A', 'ascii', policy, expected='é-A'.encode('ascii',policy))
        w.operation('Decode Bytes To String', b'\xff-A', 'utf-8', policy, expected=b'\xff-A'.decode('utf-8',policy))
    for keyword, source, encoding in [('Encode String To Bytes','é','ascii'),
                                     ('Decode Bytes To String',b'\xff','utf-8'),
                                     ('Encode String To Bytes','a','not-an-encoding'),
                                     ('Decode Bytes To String',b'a','not-an-encoding')]:
        w.operation(keyword, source, encoding, reject=True)
    w.run_and_verify()


def test_random_populations_lengths_and_invalid_requests():
    from velun.libraries.String import String
    generator = String().generate_random_string
    value = call_public(generator).value
    assert type(value) is str and len(value) == 8
    assert set(value) <= set(string.ascii_letters+string.digits)
    for marker, population in CHARACTER_COLLECTIONS.items():
        value = call_public(generator, 16384, marker).value
        assert type(value) is str and len(value) == 16384
        assert set(value) == set(population)
    for length in (0,-3):
        assert call_public(generator, length, 'xy').value == ''
    for bounds in ('3-3','2-5'):
        for _ in range(128):
            value = call_public(generator, bounds, 'xy').value
            low, high = map(int,bounds.split('-'))
            assert low <= len(value) <= high and set(value) <= {'x','y'}
    w = StringWorkflow()
    w.operation('Generate Random String', 3, 'x', expected='xxx')
    for length, chars in [(3,''), ('5-2','xy'), ('not-length','xy')]:
        w.operation('Generate Random String', length, chars, reject=True)
    w.run_and_verify()


def test_random_independent_joint_weight_and_length_distributions():
    from velun.libraries.String import String
    generator = String().generate_random_string
    # 65536 eight-bit samples give 256 expected observations per full joint
    # cell: the Bernstein margin is below the deficit of a missing cell.
    def sample():
        return [generator(8, '01') for _ in range(65536)]
    samples = call_public(sample, timeout=120).value
    assert all(type(v) is str and len(v) == 8 and set(v) <= {'0','1'} for v in samples)
    cells = frequency_cells(samples, {''.join(bits):1/256 for bits in product('01',repeat=8)})
    for position in range(8):
        cells += frequency_cells([v[position] for v in samples], {'0':.5,'1':.5})
    for a,b in combinations(range(8),2):
        cells += frequency_cells([v[a]+v[b] for v in samples], {''.join(bits):.25 for bits in product('01',repeat=2)})
    for marker, population in CHARACTER_COLLECTIONS.items():
        values = call_public(generator, 65536, marker).value
        assert type(values) is str and len(values) == 65536
        cells += frequency_cells(values, {char: count / len(population)
                                          for char, count in Counter(population).items()})
    defaults = call_public(lambda: [generator() for _ in range(8192)]).value
    assert all(type(v) is str and len(v) == 8 for v in defaults)
    cells += frequency_cells(''.join(defaults), {c: 1/62 for c in string.ascii_letters+string.digits})
    weighted = call_public(generator, 65536, 'aaabc').value
    assert len(weighted) == 65536
    cells += frequency_cells(weighted, {'a':.6,'b':.2,'c':.2})
    # Overlapping groups keep every occurrence: lowercase letters twice, 'a' three times.
    overlap = string.ascii_lowercase + string.ascii_letters + 'a'
    combined = call_public(generator, 65536, '[LOWER][LETTERS]a').value
    assert type(combined) is str and len(combined) == 65536
    cells += frequency_cells(combined, {char: count / len(overlap) for char, count in Counter(overlap).items()})
    # Long strings: positions stay independent and identically distributed
    # beyond the eight-position joint. Every check below uses disjoint
    # position sets so each cell is binomial under the PRD distribution.
    size = 2 ** 18
    bits = call_public(generator, size, '01').value
    assert type(bits) is str and len(bits) == size and set(bits) <= {'0','1'}
    cells += frequency_cells([bits[i:i+4] for i in range(0, size, 4)],
                             {''.join(b): 1/16 for b in product('01', repeat=4)})
    segment = size // 16
    for start in range(0, size, segment):
        cells += frequency_cells(bits[start:start+segment], {'0':.5,'1':.5})
    # Evenly spaced triples catch dependence that pairs cannot see (e.g. parity).
    triple_cells = {''.join(b): 1/8 for b in product('01', repeat=3)}
    for gap in range(1, 17):
        triples = [bits[b+j] + bits[b+j+gap] + bits[b+j+2*gap]
                   for b in range(0, size - 3*gap + 1, 3*gap) for j in range(gap)]
        cells += frequency_cells(triples, triple_cells)
    pair_cells = {''.join(b): .25 for b in product('01', repeat=2)}
    for lag in (61, size // 2):
        pairs = [bits[b+j] + bits[b+j+lag] for b in range(0, size - 2*lag + 1, 2*lag) for j in range(lag)]
        cells += frequency_cells(pairs, pair_cells)
    cells += frequency_cells([bits[i] + bits[size-1-i] for i in range(size // 2)], pair_cells)
    # Lengths between the short and the very long samples, with default characters,
    # and the default length with caller characters.
    middle = call_public(lambda: [generator(32) for _ in range(8192)]).value
    assert all(type(v) is str and len(v) == 32 for v in middle)
    cells += frequency_cells(''.join(middle), {c: 1/62 for c in string.ascii_letters+string.digits})
    for position in (0, 8, 31):
        cells += frequency_cells([v[position] for v in middle], {c: 1/62 for c in string.ascii_letters+string.digits})
    named = call_public(lambda: [generator(chars='xy') for _ in range(4096)]).value
    assert all(type(v) is str and len(v) == 8 for v in named)
    cells += frequency_cells(''.join(named), {'x':.5,'y':.5})
    # Ranged lengths: uniform inclusive lengths, and their characters are
    # still drawn uniformly from a large collection in short strings.
    polish = CHARACTER_COLLECTIONS['[POLISH]']
    ranged = call_public(lambda: [generator('2-5','[POLISH]') for _ in range(16384)]).value
    assert all(type(v) is str for v in ranged)
    cells += frequency_cells([len(v) for v in ranged], {n:.25 for n in range(2,6)})
    cells += frequency_cells(''.join(ranged), {c: 1/len(polish) for c in polish})
    assert_frequency_budget(cells)


def test_title_conversion_preservation_and_exclusions():
    w = StringWorkflow()
    source = "  it's\tan OK iPhone\n42hello -world the theme  "
    expected = "  It's\tan OK iPhone\n42Hello -World the Theme  "
    w.operation('Convert To Title Case', source, exclude='an,the', expected=expected)
    w.operation('Should Be Title Case', expected, exclude='an,the')
    w.operation('Convert To Title Case', 'the theme km. kmx', exclude=['the','km[.]'], expected='the Theme km. Kmx')
    w.operation('Convert To Title Case', b'\xe9hello OK', expected=b'\xe9Hello OK')
    # The first alphabetic character of text need not be ASCII.
    w.operation('Convert To Title Case', 'élan 1ère', expected='Élan 1Ère')
    w.operation('Should Be Title Case', 'OK iPhone 123')
    w.operation('Should Be Title Case', 'lower Word', reject=True)
    w.operation('Should Be Title Case', 'the Theme', reject=True)
    w.operation('Should Be Title Case', 'the theme', exclude='the', reject=True)
    w.run_and_verify()


def test_regexp_groups_replacement_flags_and_failures():
    require_python((3, 13))
    w = StringWorkflow()
    source = 'ab12 AB34 ab56'
    pattern = r'(?P<word>ab)([0-9]+)'
    matches = list(re.finditer(pattern,source,re.I))
    w.operation('Get Regexp Matches', source, pattern, flags='IGNORECASE', expected=[m.group() for m in matches])
    w.operation('Get Regexp Matches', source, pattern, 'word', flags='IGNORECASE', expected=[m.group('word') for m in matches])
    w.operation('Get Regexp Matches', source, pattern, 2, 'word', flags='IGNORECASE', expected=[m.group(2,'word') for m in matches])
    w.operation('Get Regexp Matches', 'ababa', 'aba', expected=['aba'])
    w.operation('Get Regexp Matches', source, 'absent', expected=[])
    w.operation('Get Regexp Matches', source, pattern, expected=[m.group() for m in re.finditer(pattern,source)])
    replacement = r'\2/\g<word>'
    for count in (-4,0,1,2):
        expected = source if count == 0 else re.sub(pattern,replacement,source,count=max(count,0),flags=re.I)
        w.operation('Replace String Using Regexp', source, pattern, replacement, count, flags='IGNORECASE', expected=expected)
    # Without a count every match is replaced, and matching is case-sensitive.
    w.operation('Replace String Using Regexp', source, pattern, replacement, expected=re.sub(pattern,replacement,source))
    w.operation('Remove String Using Regexp', source, 'ab[0-9]+', flags='IGNORECASE', expected='  ')
    w.operation('Remove String Using Regexp', 'a1b2c', '[0-9]', 'b', expected='ac')
    for keyword, args in [('Get Regexp Matches',(source,'[')),
                          ('Get Regexp Matches',(source,pattern,9)),
                          ('Get Regexp Matches',(source,pattern,'missing')),
                          ('Replace String Using Regexp',(source,'[','x')),
                          ('Replace String Using Regexp',(source,pattern,r'\g<missing>')),
                          ('Remove String Using Regexp',(source,'['))]:
        w.operation(keyword,*args,reject=True)
    w.run_and_verify()
