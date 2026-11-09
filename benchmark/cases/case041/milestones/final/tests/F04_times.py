# feature: F04
"""Acceptance tests for ASN.1 time values and extended calendar dates."""

import unittest
from datetime import datetime, timedelta, timezone
from fractions import Fraction

from cobaltform.core import GeneralizedTime, UTCTime
from cobaltform.util import extended_date, extended_datetime


class TestTime(unittest.TestCase):
    def test_f04_t01(self):
        cases = (
            ("4901010000Z", 2049, 1, 1, 0, 0, 0, timezone.utc),
            ("5001010000Z", 1950, 1, 1, 0, 0, 0, timezone.utc),
            ("240229123456+0530", 2024, 2, 29, 12, 34, 56, timedelta(hours=5, minutes=30)),
            ("240229123400-0400", 2024, 2, 29, 12, 34, 0, timedelta(hours=-4)),
        )
        for text, year, month, day, hour, minute, second, offset in cases:
            value = UTCTime.load(b"\x17" + bytes([len(text)]) + text.encode("ascii"))
            native = value.native
            self.assertEqual((native.year, native.month, native.day,
                              native.hour, native.minute, native.second),
                             (year, month, day, hour, minute, second), msg=('text=%r' % (text,),))
            self.assertEqual(native.utcoffset(),
                             offset.utcoffset(None) if hasattr(offset, "utcoffset") else offset, msg=('text=%r' % (text,),))
        for text in ("2402301200Z", "24010112Z", "240101120000+2460"):
            with self.assertRaises(ValueError):
                UTCTime(text).native

    def test_f04_t02(self):
        cases = (
            ("2024022912.125Z", 12, 7, 30, 0, timedelta(0)),
            ("202402291234,125+05", 12, 34, 7, 500000, timedelta(hours=5)),
            ("20240229123456.1234564-0330", 12, 34, 56, Fraction(1234564, 10), -timedelta(hours=3, minutes=30)),
            ("20240229123456.1234565Z", 12, 34, 56, Fraction(246913, 2), timedelta(0)),
            ("199912312359-0001", 23, 59, 0, 0, -timedelta(minutes=1)),
        )
        for text, hour, minute, second, microsecond, offset in cases:
            native = GeneralizedTime(text).native
            self.assertEqual((native.year, native.month, native.day),
                             (int(text[:4]), int(text[4:6]), int(text[6:8])), msg=('text=%r' % (text,),))
            self.assertEqual((native.hour, native.minute, native.second),
                             (hour, minute, second), msg=('text=%r' % (text,),))
            self.assertLessEqual(abs(native.microsecond - microsecond), Fraction(1, 2), msg=('text=%r' % (text,),))
            self.assertEqual(native.utcoffset(), offset, msg=('text=%r' % (text,),))
        offsetless = GeneralizedTime("20240229123456.5").native
        self.assertIsNone(offsetless.tzinfo)
        for text in ("202402300000Z", "202402291234xZ", "2024022912.Z"):
            with self.assertRaises(ValueError):
                GeneralizedTime(text).native

    def test_f04_t03(self):
        plus = timezone(timedelta(hours=5, minutes=30))
        aware = datetime(2024, 2, 29, 23, 59, 59, 987654, plus)
        utc_value = UTCTime(aware)
        self.assertEqual(utc_value.dump(), b"\x17\x0d240229182959Z")
        self.assertEqual(utc_value.native, datetime(2024, 2, 29, 18, 29, 59, tzinfo=timezone.utc))

        generalized = GeneralizedTime(aware)
        self.assertEqual(generalized.dump(), b"\x18\x16" + b"20240229182959.987654Z")
        self.assertEqual(generalized.native, datetime(2024, 2, 29, 18, 29, 59, 987654, tzinfo=timezone.utc))

        with self.assertRaises(ValueError):
            UTCTime(datetime(2024, 1, 1))
        with self.assertRaises(ValueError):
            GeneralizedTime(datetime(2024, 1, 1))
        with self.assertRaises(ValueError):
            UTCTime(datetime(2050, 1, 1, tzinfo=timezone.utc))
        # The UTC time range is judged after conversion to UTC, at both ends.
        plus_one = timezone(timedelta(hours=1))
        for value, encoded in ((datetime(1950, 1, 1, tzinfo=timezone.utc), b"500101000000Z"),
                               (datetime(2049, 12, 31, 23, 59, 59, tzinfo=timezone.utc), b"491231235959Z"),
                               (datetime(2050, 1, 1, 0, 30, tzinfo=plus_one), b"491231233000Z")):
            self.assertEqual(UTCTime(value).dump(), b"\x17\x0d" + encoded)
        for value in (datetime(1949, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
                      datetime(1950, 1, 1, 0, 30, tzinfo=plus_one)):
            with self.assertRaises(ValueError):
                UTCTime(value)

    def test_f04_t04(self):
        zero = GeneralizedTime("00000229123456Z").native
        self.assertEqual((zero.year, zero.month, zero.day), (0, 2, 29))
        self.assertEqual(zero.strftime("%Y-%m-%d"), "0000-02-29")
        self.assertEqual(zero.replace(day=28).isoformat(), "0000-02-28T12:34:56+00:00")
        self.assertTrue(zero < datetime(1, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(zero + timedelta(seconds=1), extended_datetime(0, 2, 29, 12, 34, 57, tzinfo=timezone.utc))
        self.assertEqual(zero + timedelta(days=307), datetime(1, 1, 1, 12, 34, 56, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            extended_date(0, 2, 30)
        # Offsets and fractions take part in year-zero comparison and arithmetic.
        utc = timezone.utc
        late = GeneralizedTime("00001231230000-0200").native
        self.assertEqual((late.year, late.month, late.day, late.hour), (0, 12, 31, 23))
        self.assertEqual(late.utcoffset(), -timedelta(hours=2))
        self.assertFalse(late < datetime(1, 1, 1, 0, 30, tzinfo=utc))
        self.assertTrue(late < datetime(1, 1, 1, 1, 30, tzinfo=utc))
        self.assertEqual(late + timedelta(hours=1), datetime(1, 1, 1, 2, 0, tzinfo=utc))
        fraction = GeneralizedTime("00000229123456.25Z").native
        self.assertEqual(fraction.microsecond, 250000)
        self.assertEqual(fraction.isoformat(), "0000-02-29T12:34:56.250000+00:00")
        self.assertEqual(fraction, zero + timedelta(microseconds=250000))
        self.assertTrue(zero < fraction)
        self.assertFalse(fraction < zero)
        self.assertFalse(zero < zero)
