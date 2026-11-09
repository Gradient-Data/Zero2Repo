# feature: F02
"""Datatype acceptance vectors from XSD Datatypes and XPath F&O.

Expected numbers, byte vectors and calendar fields are independent of product
round trips. Float checks use the PRD tolerance, not reference bit patterns.
"""
import base64
import math
from datetime import timedelta
from decimal import Decimal, localcontext

from velunara import (XPath2Parser, XPathContext, VelunaraValueError,
                         VelunaraTypeError, VelunaraZeroDivisionError)
from velunara import datatypes as dt
from F02_helpers import datatype_expression as value, datatype_failure as failure
from F02_helpers import datatype_rejection as reject


def test_numeric_construction_validation_and_lexical_errors():
    vectors = [(dt.StringProxy, 'string', ' words ', ' words ', None),
               (dt.BooleanProxy, 'boolean', 'false', False, 'yes'),
               (dt.DecimalProxy, 'decimal', '-12.375', Decimal('-12.375'), '1e2'),
               (dt.Float, 'float', '1.25E2', 125.0, 'twelve'),
               (dt.DoubleProxy10, 'double', '-2.5E1', -25.0, 'twelve'),
               (dt.Integer, 'integer', '+00037', 37, '3.5')]
    for factory, name, lexical, expected, invalid in vectors:
        assert factory(lexical) == expected
        factory.validate(factory(lexical))
        if factory is not dt.Float:
            factory.validate(lexical)
        assert value(f'xs:{name}("{lexical}")') == expected
        if invalid is not None:
            reject(factory, invalid)
            reject(factory.validate, invalid)
            failure(f'xs:{name}("{invalid}")', VelunaraValueError, 'FORG0001')
    for lexical, expected in [('true', True), ('1', True), ('0', False)]:
        assert dt.BooleanProxy(lexical) is expected
        assert value(f'xs:boolean("{lexical}")') is expected
    # XSD boolean literals are case-sensitive: only true/false/1/0.
    for invalid in ('TRUE', 'False'):
        reject(dt.BooleanProxy, invalid)
        reject(dt.BooleanProxy.validate, invalid)
        failure(f'xs:boolean("{invalid}")', VelunaraValueError, 'FORG0001')
    assert value('xs:integer(xs:decimal("-9.75"))') == -9
    assert value('xs:decimal(true())') == Decimal(1)


def test_restricted_integer_boundaries():
    # XSD Part 2 integer-derived value spaces; no machine-word assumption.
    bounds = [(dt.NonPositiveInteger, 'nonPositiveInteger', None, 0),
              (dt.NegativeInteger, 'negativeInteger', None, -1),
              (dt.NonNegativeInteger, 'nonNegativeInteger', 0, None),
              (dt.PositiveInteger, 'positiveInteger', 1, None)]
    for signed, signed_name, unsigned, unsigned_name, bits in [
            (dt.Byte, 'byte', dt.UnsignedByte, 'unsignedByte', 8),
            (dt.Short, 'short', dt.UnsignedShort, 'unsignedShort', 16),
            (dt.Int, 'int', dt.UnsignedInt, 'unsignedInt', 32),
            (dt.Long, 'long', dt.UnsignedLong, 'unsignedLong', 64)]:
        bounds.extend([(signed, signed_name, -(2 ** (bits - 1)), 2 ** (bits - 1) - 1),
                       (unsigned, unsigned_name, 0, 2 ** bits - 1)])
    for factory, name, lower, upper in bounds:
        for boundary, outside in [(lower, None if lower is None else lower - 1),
                                  (upper, None if upper is None else upper + 1)]:
            if boundary is None:
                continue
            assert factory(str(boundary)) == boundary
            factory.validate(factory(str(boundary)))
            assert value(f'xs:{name}("{boundary}")') == boundary
            # Casting an integer item (not text) must enforce the same range.
            assert value(f'xs:{name}({boundary})') == boundary
            reject(factory, str(outside))
            reject(factory.validate, "not-an-integer")
            failure(f'xs:{name}("{outside}")', VelunaraValueError, 'FORG0001')
            failure(f'xs:{name}({outside})', VelunaraValueError, 'FORG0001')
    assert dt.Integer('123456789012345678901234567890') == 123456789012345678901234567890


def test_exact_integer_decimal_arithmetic_and_ordering():
    assert value('123456789012345678901234567890 + 13') == 123456789012345678901234567903
    assert value('1234567890123456789 * 9') == 11111111011111111101
    assert value('(-17 idiv 5, -17 mod 5)') == [-3, -2]
    # idiv truncates toward zero for decimal operands too (F&O op:numeric-integer-divide).
    assert value('(xs:decimal("-17.5") idiv 5, xs:decimal("17.5") idiv -5)') == [-3, -3]
    # integer div integer is an exact xs:decimal (18 significant digits here).
    assert value('123456789012345678 div 4') == Decimal('30864197253086419.5')
    assert value('xs:decimal("123456789012345.67") + xs:decimal("0.08")') == Decimal('123456789012345.75')
    assert value('xs:decimal("1.25") * xs:decimal("0.08")') == Decimal('0.1')
    assert value('xs:decimal("1") div xs:decimal("8")') == Decimal('0.125')
    actual = value('xs:decimal("1") div xs:decimal("7")')
    with localcontext() as ctx:
        ctx.prec = 60
        expected = Decimal(1) / Decimal(7)
        # One unit in the eighteenth significant digit accepts truncation too.
        assert abs(actual - expected) <= Decimal('1e-18')
    assert value('(xs:integer("9") lt xs:decimal("9.5"), '
                 'xs:decimal("9.5") lt xs:double("10"), '
                 'xs:float("10") eq xs:integer("10"))') == [True, True, True]


def test_schema_datatype_version_selection():
    import xmlschema
    for options, valid in [({}, False), ({'xsd_version': '1.0'}, False),
                           ({'xsd_version': '1.1'}, True)]:
        parser = XPath2Parser(**options)
        if valid:
            assert value('xs:double("+INF")', parser=parser) == math.inf
            assert value('xs:float("+INF")', parser=parser) == math.inf
            assert value('day-from-date(xs:date("0000-02-29"))', parser=parser) == 29
        else:
            failure('xs:double("+INF")', VelunaraValueError, 'FORG0001', parser=parser)
            failure('xs:float("+INF")', VelunaraValueError, 'FORG0001', parser=parser)
            failure('xs:date("0000-02-29")', VelunaraValueError, 'FORG0001', parser=parser)
    for factory, version, accepts in [(xmlschema.XMLSchema10, '1.1', False),
                                       (xmlschema.XMLSchema11, '1.0', True)]:
        schema = factory('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>')
        parser = XPath2Parser(xsd_version=version, schema=xmlschema.xpath.XMLSchemaProxy(schema))
        if accepts:
            assert value('xs:double("+INF")', parser=parser) == math.inf
        else:
            failure('xs:double("+INF")', VelunaraValueError, 'FORG0001', parser=parser)


def test_finite_floating_arithmetic_and_comparisons():
    # All operands/results are normal; single precision stays above 1e-37.
    for factory, name in [(dt.Float10, 'float'), (dt.DoubleProxy10, 'double')]:
        for left, right in [('1.2345', '3.25'), ('-42000', '8'), ('1e-30', '2')]:
            a, b = float(left), float(right)
            assert math.isclose(float(factory(left)), a, rel_tol=1e-6, abs_tol=0)
            for op, expected in [('+', a+b), ('-', a-b), ('*', a*b), ('div', a/b)]:
                actual = value(f'xs:{name}("{left}") {op} xs:{name}("{right}")')
                assert math.isclose(actual, expected, rel_tol=1e-6, abs_tol=0)
        assert value(f'xs:{name}("2.5") - xs:{name}("2.5")') == 0
        assert value(f'(xs:{name}("1e-30") lt xs:{name}("2e-30"), '
                     f'xs:{name}("-4") lt xs:{name}("0"), '
                     f'xs:{name}("3") eq xs:{name}("5"))') == [True, True, False]
        # Separated by about 1e-4 of the magnitude (> 1e-6): distinct values.
        assert value(f'(xs:{name}("1.0001") eq xs:{name}("1.0002"), '
                     f'xs:{name}("1.0001") ne xs:{name}("1.0002"), '
                     f'xs:{name}("1.0001") lt xs:{name}("1.0002"))') == [False, True, True]


def test_nonfinite_numbers_and_distinct_failures():
    assert value('12 div 3') == 4
    for name in ('float', 'double'):
        assert value(f'xs:{name}("1") div xs:{name}("0")') == math.inf
        assert value(f'xs:{name}("-1") div xs:{name}("0")') == -math.inf
        assert math.isnan(value(f'xs:{name}("0") div xs:{name}("0")'))
        assert math.isnan(value(f'xs:{name}("NaN")'))
    for expression in ('1 div 0', '1 idiv 0', 'xs:decimal("2") div 0', '5 mod 0',
                       'xs:decimal("5") mod 0'):
        failure(expression, VelunaraZeroDivisionError, 'FOAR0001')
    failure('xs:integer("not-number")', VelunaraValueError, 'FORG0001')
    failure('xs:decimal("1") + xs:date("2020-01-01")', VelunaraTypeError, 'XPTY0004')


def test_text_derived_and_list_values():
    assert dt.NormalizedString('a\tb\nc\rd') == 'a b c d'
    dt.NormalizedString.validate('a b')
    reject(dt.NormalizedString.validate, 'a\tb')
    assert dt.XsdToken('  a\t b\n c  ') == 'a b c'
    dt.XsdToken.validate('a b c')
    reject(dt.XsdToken.validate, 'a  b')
    vectors = [(dt.Language, 'en-GB', 'en_GB'), (dt.Name, 'p:leaf', '9leaf'),
               (dt.NCName, 'leaf_1', 'p:leaf'), (dt.NMToken, '9:p-leaf', 'a b'),
               (dt.Id, 'key_1', 'p:key'), (dt.Idref, 'ref_2', '2ref'),
               (dt.Entity, 'entity_3', 'p:entity')]
    for factory, valid, invalid in vectors:
        assert str(factory(valid)) == valid
        factory.validate(valid)
        reject(factory, invalid)
        reject(factory.validate, invalid)
    # language subtags are 1-8 characters.
    for invalid in ('abcdefghi', 'en-abcdefghi'):
        reject(dt.Language, invalid)
        reject(dt.Language.validate, invalid)
    for factory in (dt.NMTokens, dt.Idrefs, dt.Entities):
        # The built-in list types have minLength 1: an empty list is refused
        # when decoding or, at the latest, when validating the decoded list.
        try:
            empty = factory.decode('   ')
        except ValueError:
            pass
        else:
            reject(factory.validate, empty)
        decoded = factory.decode(' alpha\t beta_2\nalpha ')
        assert list(map(str, decoded)) == ['alpha', 'beta_2', 'alpha']
        factory.validate(decoded)
        assert list(map(str, factory(decoded))) == ['alpha', 'beta_2', 'alpha']
        reject(factory.decode, 'alpha bad!')
        reject(factory.validate, [factory.item_type('alpha'), 'bad!'])


def test_qualified_names_and_notation_validation():
    first = dt.QName('urn:parts', 'a:wheel')
    assert first.namespace == 'urn:parts'
    assert first.local_name == 'wheel'
    assert first == dt.QName('urn:parts', 'b:wheel')
    assert first != dt.QName('urn:other', 'a:wheel')
    assert first != dt.QName('urn:parts', 'a:axle')
    assert dt.QName(None, 'wheel').local_name == 'wheel'
    for uri, lexical in [(None, 'p:wheel'), ('', 'p:wheel'), ('urn:p', 'p:a:b')]:
        reject(dt.QName, uri, lexical)
    dt.Notation.validate('p:mark')
    dt.Notation.validate('mark')
    reject(dt.Notation.validate, 'p:a:b')
    # Built-in NOTATION is abstract; use a real declared derived type.
    import xmlschema
    schema = xmlschema.XMLSchema10('''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
        xmlns:t="urn:notation" targetNamespace="urn:notation">
        <xs:notation name="jpeg" public="image/jpeg"/>
        <xs:notation name="png" public="image/png"/>
        <xs:simpleType name="Mark"><xs:restriction base="xs:NOTATION">
        <xs:enumeration value="t:jpeg"/></xs:restriction></xs:simpleType>
    </xs:schema>''')
    parser = XPath2Parser(namespaces={'t': 'urn:notation'},
                          schema=xmlschema.xpath.XMLSchemaProxy(schema))
    parser.schema_constructor('{urn:notation}Mark')
    assert value('t:Mark("t:jpeg")', parser=parser) == 't:jpeg'
    failure('t:Mark("t:png")', VelunaraValueError, 'FORG0001', parser=parser)


def test_binary_and_uri_values():
    raw = b'\x00\x01\x7f\x80\xffXML'
    for factory, lexical in [(dt.Base64Binary, base64.b64encode(raw)),
                              (dt.HexBinary, raw.hex().encode('ascii')),
                              (dt.HexBinary, raw.hex().upper().encode('ascii'))]:
        instance = factory(lexical)
        assert instance.decode() == raw
        factory.validate(lexical)
        encoded = factory.encoder(raw)
        independent = base64.b64decode(encoded) if factory is dt.Base64Binary else bytes.fromhex(encoded.decode('ascii'))
        assert independent == raw
        assert dt.Base64Binary(instance).decode() == raw
        assert dt.HexBinary(instance).decode() == raw
        reject(factory, '!?')
        reject(factory.validate, '!?')
    # hexBinary encodes whole octets, so an odd digit count is not a lexical form.
    reject(dt.HexBinary, 'abc')
    reject(dt.HexBinary.validate, 'abc')
    # base64 needs whole 4-character groups with padding only at the end.
    for lexical in ('QUJ', 'QU=J'):
        reject(dt.Base64Binary, lexical)
        reject(dt.Base64Binary.validate, lexical)
    for lexical in ('https://example.org/a%20b?q=x#part', '../assets/item', ''):
        assert str(dt.AnyURI(lexical)) == lexical
        dt.AnyURI.validate(lexical)
    for lexical in ('https://example.org/%GG', 'https://example.org/a%2',
                    'https://example.org/a#b#c'):
        reject(dt.AnyURI, lexical)
        reject(dt.AnyURI.validate, lexical)


def test_calendar_types_timezone_and_microseconds():
    vectors = [(dt.Date, '2024-02-29Z', {'year': 2024, 'month': 2, 'day': 29}),
               (dt.Time, '13:14:15.123456+05:30', {'hour': 13, 'minute': 14, 'second': 15, 'microsecond': 123456}),
               (dt.DateTime, '2024-02-29T13:14:15.654321Z', {'year': 2024, 'month': 2, 'day': 29, 'hour': 13, 'minute': 14, 'second': 15, 'microsecond': 654321}),
               (dt.DateTimeStamp, '2024-02-29T13:14:15Z', {'year': 2024, 'month': 2, 'day': 29, 'hour': 13, 'minute': 14, 'second': 15}),
               (dt.GregorianYear, '2024Z', {'year': 2024}),
               (dt.GregorianYearMonth, '2024-02Z', {'year': 2024, 'month': 2}),
               (dt.GregorianMonth, '--02Z', {'month': 2}),
               (dt.GregorianMonthDay, '--02-29Z', {'month': 2, 'day': 29}),
               (dt.GregorianDay, '---29Z', {'day': 29})]
    for factory, lexical, fields in vectors:
        instance = factory.fromstring(lexical)
        for field, expected in fields.items():
            assert getattr(instance, field) == expected
        expected_offset = timedelta(hours=5, minutes=30) if factory is dt.Time else timedelta(0)
        assert instance.tzinfo.utcoffset(None) == expected_offset
    assert value('seconds-from-dateTime(xs:dateTime("2024-02-29T13:14:15.123456Z"))') == Decimal('15.123456')
    # A short fraction is a fraction of a second, not a microsecond count.
    assert dt.Time.fromstring('08:00:00.5').microsecond == 500000
    assert dt.DateTime.fromstring('2024-01-01T00:00:00.25Z').microsecond == 250000
    lexical = '2024-02-29T13:14:15'
    assert dt.DateTime.fromstring(lexical).hour == 13
    reject(dt.DateTimeStamp.fromstring, lexical)


def test_calendar_duration_arithmetic_comparison_and_implicit_timezone():
    date = dt.Date.fromstring('2024-01-31') + dt.YearMonthDuration.fromstring('P1M')
    assert (date.year, date.month, date.day) == (2024, 2, 29)
    # End-of-month adjustment uses the target month length and target year.
    for start, months, expected in [('2024-03-31', 1, (2024, 4, 30)),
                                    ('2023-01-31', 1, (2023, 2, 28)),
                                    ('2023-11-30', 3, (2024, 2, 29)),
                                    ('2100-01-31', 1, (2100, 2, 28)),
                                    ('2024-03-31', -1, (2024, 2, 29))]:
        date = dt.Date.fromstring(start) + dt.YearMonthDuration(months)
        assert (date.year, date.month, date.day) == expected
    result = dt.DateTime.fromstring('2024-02-28T23:59:59.999999Z') + dt.DayTimeDuration.fromstring('PT0.000002S')
    assert (result.year, result.month, result.day, result.hour, result.minute,
            result.second, result.microsecond) == (2024, 2, 29, 0, 0, 0, 1)
    assert dt.Duration.fromstring('P1Y2M3DT4S').months == 14
    assert dt.Duration.fromstring('P1Y2M3DT4S').seconds == 259204
    assert dt.Duration.fromstring('P1DT2H3M4.5S').seconds == 86400 + 2 * 3600 + 3 * 60 + Decimal('4.5')
    negative = dt.Duration.fromstring('-P1Y2M3DT4H5M6.5S')
    assert (negative.months, negative.seconds) == (-14, -(3 * 86400 + 4 * 3600 + 5 * 60 + Decimal('6.5')))
    assert dt.Duration.fromstring('P1Y') == dt.Duration.fromstring('P12M')
    assert dt.Duration.fromstring('P1D') < dt.Duration.fromstring('P2D')
    # Year vs days is determinate: 365/366 days lie strictly within (364, 367).
    assert dt.Duration.fromstring('P1Y') > dt.Duration.fromstring('P364D')
    assert dt.Duration.fromstring('P1Y') < dt.Duration.fromstring('P367D')
    assert (dt.YearMonthDuration(14) + dt.YearMonthDuration(3)).months == 17
    assert (dt.YearMonthDuration(14) * 2).months == 28
    # Months results are fn:round()ed: halves round toward positive infinity.
    assert (dt.YearMonthDuration(1) * Decimal('1.5')).months == 2
    assert value('(xs:yearMonthDuration("P5M") div 2 eq xs:yearMonthDuration("P3M"), '
                 'xs:yearMonthDuration("-P3M") div 2 eq xs:yearMonthDuration("-P1M"), '
                 'xs:dayTimeDuration("PT10S") div 4 eq xs:dayTimeDuration("PT2.5S"), '
                 'xs:yearMonthDuration("P3M") div xs:yearMonthDuration("P2M") eq 1.5, '
                 # op:duration-equal compares (months, seconds) across duration subtypes.
                 'xs:duration("P1M") eq xs:yearMonthDuration("P1M"), '
                 'xs:dayTimeDuration("PT0S") eq xs:yearMonthDuration("P0M"), '
                 # op:add-dayTimeDuration-to-time wraps around midnight.
                 'xs:time("23:00:00") + xs:dayTimeDuration("PT2H") eq xs:time("01:00:00"))') == [
        True, True, True, True, True, True, True]
    assert (dt.DayTimeDuration(Decimal('1.25')) * 2).seconds == Decimal('2.5')
    assert (dt.DayTimeDuration(10) * 1.5).seconds == 15
    assert (dt.DayTimeDuration(10) / dt.DayTimeDuration(4)) == Decimal('2.5')
    # Ordering compares instants: local field order is the opposite in the
    # two timezone pairs below, so a comparison ignoring offsets is refuted.
    assert value('(xs:dateTime("2024-01-01T10:00:00+02:00") eq xs:dateTime("2024-01-01T08:00:00Z"), '
                 'xs:yearMonthDuration("P2Y") gt xs:yearMonthDuration("P13M"), '
                 'xs:dateTime("2024-01-01T10:30:00+02:00") lt xs:dateTime("2024-01-01T09:15:00Z"), '
                 'xs:dateTime("2024-01-01T23:30:00-02:00") gt xs:dateTime("2024-01-02T00:15:00Z"), '
                 'xs:time("10:00:00+02:00") lt xs:time("09:00:00Z"), '
                 'xs:date("2024-02-29") lt xs:date("2024-03-01"), '
                 'xs:date("2024-03-01") le xs:date("2024-02-29"), '
                 'xs:time("23:00:00") gt xs:time("09:30:00"), '
                 'xs:date("12000-01-01") gt xs:date("2024-06-30"), '
                 'xs:date("-0001-06-01") lt xs:date("0001-01-01"))') == [
        True, True, True, True, True, True, False, True, True, True]
    # XSD 1.0: -0001 is 1 BCE (no year zero); XSD 1.1: -0001 is 2 BCE and 0000 is a leap year.
    expression = 'xs:date("0001-01-01") - xs:date("-0001-12-31")'
    for options, days in [({}, 1), ({'xsd_version': '1.1'}, 367)]:
        assert value(expression, parser=XPath2Parser(**options)).seconds == days * 86400
    # Gregorian leap rule beyond four-digit years: 12000 is a leap year, 12100 is not.
    assert [d.seconds for d in value('(xs:date("12000-03-01") - xs:date("12000-02-28"), '
                                     'xs:date("12100-03-01") - xs:date("12100-02-28"), '
                                     'xs:date("12001-01-01") - xs:date("12000-01-01"))')] == [
        2 * 86400, 86400, 366 * 86400]
    expression = 'xs:dateTime("2024-01-01T10:00:00") - xs:dateTime("2024-01-01T08:00:00Z")'
    for timezone, expected in [('+02:00', 0), ('Z', 7200)]:
        context = XPathContext(item=1, timezone=timezone)
        assert value(expression, context=context).seconds == expected
    failure('xs:yearMonthDuration("P1M") + xs:dayTimeDuration("P1D")', VelunaraTypeError, 'XPTY0004')


def test_calendar_duration_and_timezone_limits_and_invalid_fields():
    assert dt.Date.fromstring('2024-02-29').day == 29
    # Gregorian leap rule: centuries are leap years only when divisible by 400.
    assert dt.Date.fromstring('2000-02-29').day == 29
    for factory, lexical in [(dt.Date, '2023-02-29'), (dt.Date, '1900-02-29'),
                              (dt.DateTime, '2100-02-29T00:00:00'), (dt.Date, '2024-13-01'),
                              (dt.Date, '2024-01-00'), (dt.Time, '25:00:00'),
                              (dt.Time, '12:60:00'), (dt.Time, '12:00:60')]:
        reject(factory.fromstring, lexical)
    # The century rule also holds beyond four-digit years (XSD 1.0 default).
    failure('xs:date("10100-02-29")', VelunaraValueError, 'FORG0001')
    for sign in (-1, 1):
        assert dt.Date(sign * 2147483648, 1, 1).year == sign * 2147483648
        reject(dt.Date, sign * 2147483649, 1, 1, error_class=OverflowError)
        assert dt.Duration(sign * 2147483648, 0).months == sign * 2147483648
        assert dt.Duration(0, sign * 9223372036854775808).seconds == sign * 9223372036854775808
        reject(dt.Duration, sign * 2147483649, 0, error_class=OverflowError)
        reject(dt.Duration, 0, sign * 9223372036854775809, error_class=OverflowError)
        offset = timedelta(hours=sign * 14)
        assert dt.Timezone(offset).utcoffset(None) == offset
        reject(dt.Timezone, offset + timedelta(minutes=sign))
    reject(dt.Duration, 1, -1)
    reject(dt.Duration, -1, 1)
    # Lexical: at least one component, T only with a time component, units per subtype.
    for factory, lexical in [(dt.Duration, 'P'), (dt.Duration, 'PT'), (dt.Duration, 'P1DT'),
                              (dt.DayTimeDuration, 'P1M'), (dt.YearMonthDuration, 'P1D'),
                              (dt.YearMonthDuration, 'PT1H')]:
        reject(factory.fromstring, lexical)


def test_untyped_atomic_conversion_comparison_and_bound_arithmetic():
    lexical = dt.UntypedAtomic(' 12.5 ')
    assert lexical.value == ' 12.5 '
    assert str(lexical) == ' 12.5 '
    assert float(lexical) == 12.5
    assert lexical + 2 == 14.5
    assert 20 - lexical == 7.5
    assert dt.UntypedAtomic('9') < 10
    # Against a number the untyped value is cast to xs:double, so NaN is unordered.
    assert not dt.UntypedAtomic('NaN') < 1 and not dt.UntypedAtomic('NaN') > 1
    assert dt.UntypedAtomic('9') > '10'
    assert dt.UntypedAtomic('true') == True
    # Two untyped operands compare as strings; a numeric operand forces a number.
    assert not dt.UntypedAtomic('1.0') == dt.UntypedAtomic('1')
    assert value('(xs:untypedAtomic("1.0") = xs:untypedAtomic("1"), '
                 'xs:untypedAtomic("10") lt xs:untypedAtomic("9"), '
                 'xs:untypedAtomic("1.0") = 1)') == [False, True, True]
    assert int(dt.UntypedAtomic('17')) == 17
    context = XPathContext(item=1, variables={'u': lexical})
    assert value('($u + 2, $u * 4, $u = xs:decimal("12.5"))', context=context) == [14.5, 50, True]
    assert value('xs:string($u)', context=context) == ' 12.5 '
    reject(float, dt.UntypedAtomic('not-a-number'))
    context = XPathContext(item=1, variables={'u': dt.UntypedAtomic('not-a-number')})
    failure('$u + 2', VelunaraValueError, 'FORG0001', context=context)
