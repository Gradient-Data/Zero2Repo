# feature: F01
"""Acceptance checks through public expression and solver interfaces."""
import operator
import pytest
from _helpers import capture_call
from F01_helpers import expression_api, fresh_state, ieee_bits, ieee_operation


def test_arithmetic_wraps():
    _, c = expression_api()
    for width, a, b in [(8, 249, 19), (16, 40001, 257), (32, 0xfffffff1, 31)]:
        state = fresh_state()
        s = state.solver
        x, y = c.BVS("arith_x", width), c.BVS("arith_y", width)
        s.add(x == a, y == b)
        mask = (1 << width) - 1
        for expr, expected in [(x+y, a+b), (x-y, a-b), (x*y, a*b), (-x, -a)]:
            assert s.eval(expr) == expected & mask
        assert s.eval(c.BVV(a, width) + c.BVV(b, width)) == (a+b) & mask


def test_division_and_remainder():
    _, c = expression_api()
    for a, b in [(-29, 6), (29, -6), (-29, -6)]:
        state = fresh_state()
        s = state.solver
        x, y = c.BVS("div_x", 16), c.BVS("div_y", 16)
        s.add(x == (a & 65535), y == (b & 65535))
        quotient = (abs(a)//abs(b)) * (-1 if (a < 0) != (b < 0) else 1)
        for expr, expected in [(x/y, (a & 65535)//(b & 65535)),
                               (x % y, (a & 65535) % (b & 65535)),
                               (x.SDiv(y), quotient), (x.SMod(y), a-quotient*b)]:
            assert s.eval(expr) == expected & 65535


def test_bits_shifts_rotations():
    _, c = expression_api()
    state = fresh_state()
    s = state.solver
    x, y = c.BVS("bits_x", 16), c.BVS("bits_y", 16)
    a, b, n = 0x93a5, 0x5c37, 3
    s.add(x == a, y == b)
    checks = [(x & y, a & b), (x | y, a | b), (x ^ y, a ^ b), (~x, ~a),
              (x << n, a << n), (x >> n, (a-65536) >> n), (c.LShR(x, n), a >> n),
              (c.RotateLeft(x, c.BVV(n, 16)), (a << n) | (a >> (16-n))),
              (c.RotateRight(x, c.BVV(n, 16)), (a >> n) | (a << (16-n)))]
    for expr, expected in checks:
        assert s.eval(expr) == expected & 65535


def test_booleans_comparisons_selection():
    _, c = expression_api()
    for a, b in [(0xf1, 7), (7, 0xf1), (7, 7)]:
        state = fresh_state()
        s = state.solver
        x, y = c.BVS("cmp_x", 8), c.BVS("cmp_y", 8)
        p, q = c.BoolS("p"), c.BoolS("q")
        s.add(x == a, y == b, p == (a == b), q == (a < b))
        sa, sb = a if a < 128 else a-256, b if b < 128 else b-256
        checks = [(x == y, a == b), (x != y, a != b),
                  (x < y, a < b), (x <= y, a <= b), (x > y, a > b), (x >= y, a >= b),
                  (x.SLT(y), sa < sb), (x.SLE(y), sa <= sb),
                  (x.SGT(y), sa > sb), (x.SGE(y), sa >= sb),
                  (c.And(p, q), (a == b) and (a < b)),
                  (c.Or(p, q), (a == b) or (a < b)), (c.Not(p), a != b)]
        for expr, expected in checks:
            assert s.eval(expr) == expected
        assert s.eval(c.If(q, x, y)) == (a if a < b else b)
        assert s.eval(c.BoolV(True)) is True
        assert s.eval(c.BoolV(False)) is False


def test_width_transforms_and_mismatch():
    _, c = expression_api()
    state = fresh_state()
    s = state.solver
    x = c.BVS("width_x", 16)
    s.add(x == 0x92ab)
    checks = [(c.Concat(c.BVV(0x37, 8), x), 24, 0x3792ab),
              (c.Extract(11, 4, x), 8, 0x2a), (c.Reverse(x), 16, 0xab92),
              (c.ZeroExt(8, x), 24, 0x0092ab), (c.SignExt(8, x), 24, 0xff92ab)]
    for expr, width, expected in checks:
        assert expr.size() == width
        assert s.eval(expr) == expected
    with pytest.raises(c.ClaripyError):
        operator.add(x, c.BVS("wrong_width", 8))


def test_constraints_and_unsatisfiability():
    velnora, c = expression_api()
    state = fresh_state()
    s = state.solver
    x, y = c.BVS("solve_x", 16), c.BVS("solve_y", 16)
    s.add(x >= 2, x <= 30, y >= 1, y <= 30, x + y == 31, x == y*2+1)
    assert s.satisfiable() is True
    assert (s.eval(x), s.eval(y)) == (21, 10)
    s.add(x < y)
    assert s.satisfiable() is False
    result = capture_call(s.eval, x)
    assert isinstance(result.exception, velnora.errors.SimUnsatError)


def test_cardinality_requests():
    velnora, c = expression_api()
    state = fresh_state()
    s = state.solver
    x = c.BVS("card_x", 8)
    allowed = {3, 17, 201}
    s.add(c.Or(*(x == v for v in allowed)))
    assert s.eval(x) in allowed
    for n in (1, 2, 3, 5):
        values = s.eval_upto(x, n)
        assert len(values) == len(set(values)) == min(n, len(allowed))
        assert set(values) <= allowed
    for n in (1, 3):
        values = s.eval_atleast(x, n)
        assert len(values) == len(set(values)) == n
        assert set(values) <= allowed
    assert set(s.eval_exact(x, 3)) == allowed
    for call, args in [(s.eval_one, (x,)), (s.eval_atleast, (x, 4)),
                       (s.eval_exact, (x, 2)), (s.eval_exact, (x, 4))]:
        with pytest.raises(velnora.errors.SimValueError):
            call(*args)
    s.add(x == 17)
    assert s.eval_one(x) == 17
    assert s.eval_exact(x, 1) == [17]


def test_signed_and_unsigned_extrema():
    _, c = expression_api()
    state = fresh_state()
    s = state.solver
    x = c.BVS("extreme_x", 8)
    s.add(c.Or(x == 5, x == 120, x == 130, x == 251))
    assert s.min(x) == 5
    assert s.max(x) == 251
    assert s.min(x, signed=False) == 5
    assert s.max(x, signed=False) == 251
    assert s.min(x, signed=True) == 130
    assert s.max(x, signed=True) == 120


def test_joint_assignments():
    _, c = expression_api()
    s = c.Solver()
    x, y = c.BVS("joint_x", 8), c.BVS("joint_y", 8)
    s.add([x >= 2, x <= 5, y == 19-x*3])
    rows = s.batch_eval([x, y, x+y], 10)
    assert len(rows) == len(set(rows)) == 4
    assert set(rows) == {(a, 19-3*a, 19-2*a) for a in range(2, 6)}


def test_temporary_constraints_and_branches():
    _, c = expression_api()
    s = c.Solver()
    x = c.BVS("context_x", 8)
    s.add([x >= 2, x <= 6])
    assert set(s.eval(x, 10)) == {2, 3, 4, 5, 6}
    assert set(s.eval(x, 10, extra_constraints=[x >= 5])) == {5, 6}
    assert s.satisfiable(extra_constraints=[x == 1]) is False
    assert set(s.eval(x, 10)) == {2, 3, 4, 5, 6}
    child = s.branch()
    child.add([x <= 3])
    assert set(child.eval(x, 10)) == {2, 3}
    assert set(s.eval(x, 10)) == {2, 3, 4, 5, 6}
    s.add([x >= 5])
    assert set(s.eval(x, 10)) == {5, 6}
    assert set(child.eval(x, 10)) == {2, 3}


def test_string_relations_and_substrings():
    _, c = expression_api()
    state = fresh_state()
    s = state.solver
    x = c.StringS("text")
    text = "héλlo"
    s.add(x == c.StringV(text), c.StrLen(x) == 5,
          c.StrContains(x, c.StringV("éλ")), c.StrPrefixOf(c.StringV("hé"), x),
          c.StrSuffixOf(c.StringV("lo"), x))
    assert s.satisfiable() is True
    assert s.eval(x) == text
    assert s.eval(c.StrLen(x)) == len(text)
    assert s.eval(c.StrConcat(c.StrConcat(c.StringV("["), x), c.StringV("]"))) == "["+text+"]"
    for start, length in [(1, 2), (3, 9), (5, 2), (9, 2), (1, 0)]:
        assert s.eval(c.StrSubstr(c.BVV(start, 64), c.BVV(length, 64), x)) == text[start:start+length]
    for relation in [c.StrContains(x, c.StringV("missing")),
                     c.StrPrefixOf(c.StringV("lo"), x), c.StrSuffixOf(c.StringV("hé"), x),
                     x == c.StringV("other"), c.StrLen(x) == 6]:
        assert s.satisfiable(extra_constraints=[relation]) is False
    other_state = fresh_state()
    t = other_state.solver
    middle = c.StringS("middle")
    t.add(c.StrConcat(c.StrConcat(c.StringV("a"), middle), c.StringV("z")) == c.StringV("abcéz"))
    assert t.eval(middle) == "bcé"


def test_ieee_arithmetic_and_comparisons():
    _, c = expression_api()
    for width, sort in [(32, c.FSORT_FLOAT), (64, c.FSORT_DOUBLE)]:
        state = fresh_state()
        s = state.solver
        x = c.FPS("fp_x", sort)
        s.add(x == c.FPV(1.5, sort))
        y = c.FPV(2.75, sort)
        for name, expr in [("add", x+y), ("sub", x-y), ("mul", x*y), ("div", x/y)]:
            assert s.eval(expr.raw_to_bv()) == ieee_operation(name, 1.5, 2.75, width)
        assert s.eval(x) == 1.5
        for expr, expected in [(x < y, True), (x <= y, True), (x > y, False),
                               (x >= y, False), (x == y, False), (x != y, True)]:
            assert s.eval(expr) == expected
        assert s.satisfiable(extra_constraints=[x > y]) is False
        # Exact halfway additions distinguish ties-to-even in both directions.
        delta = 2.0 ** (-24 if width == 32 else -53)
        for left in (1.0, 1.0+2*delta):
            expr = c.FPV(left, sort) + c.FPV(delta, sort)
            assert s.eval(expr.raw_to_bv()) == ieee_operation("add", left, delta, width)
        large = c.FPV(2.0 ** (24 if width == 32 else 53), sort)
        one = c.FPV(1.0, sort)
        offset = large-c.FPV(2.0, sort)
        assert s.eval(((large+one)-offset).raw_to_bv()) == ieee_bits(2.0, width)
        assert s.eval((large+(one-offset)).raw_to_bv()) == ieee_bits(3.0, width)


def test_ieee_reinterpretation_and_conversion():
    _, c = expression_api()
    state = fresh_state()
    s = state.solver
    for width, sort in [(32, c.FSORT_FLOAT), (64, c.FSORT_DOUBLE)]:
        for value in (-13.5, 6.25):
            bits = ieee_bits(value, width)
            assert s.eval(c.FPV(value, sort).raw_to_bv()) == bits
            assert s.eval(c.BVV(bits, width).raw_to_fp()) == value
        for signed in (False, True):
            integer = c.BVV(0xfffffff9, 32)
            expected = -7.0 if signed else 4294967289.0
            assert s.eval(integer.val_to_fp(sort, signed=signed).raw_to_bv()) == ieee_bits(expected, width)
        for value, signed, expected in [(6.5, False, 6), (7.5, False, 8), (-6.5, True, -6), (-7.5, True, -8)]:
            assert s.eval(c.FPV(value, sort).val_to_bv(16, signed=signed)) == expected & 65535
    source = c.FPV(1.0 + 2.0**-24, c.FSORT_DOUBLE)
    assert s.eval(source.to_fp(c.FSORT_FLOAT).raw_to_bv()) == ieee_bits(1.0, 32)
    assert s.eval(c.FPV(-13.5, c.FSORT_FLOAT).to_fp(c.FSORT_DOUBLE).raw_to_bv()) == ieee_bits(-13.5, 64)
