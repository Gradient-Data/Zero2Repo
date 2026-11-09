# feature: F02
"""Caller declarations and independent X.690 (2015) value vectors.

Scalar vectors use sections 8.2-8.9 and DER section 10. Bit payloads use
MSB-first order and an explicit unused-bit count (8.6.2). Text payloads use
Python's standard codecs; only short definite framing is needed here.
"""

from cobaltform.core import (
    BMPString, BitString, Boolean, CharacterString, Enumerated, GeneralString,
    GraphicString, IA5String, Integer, Null, NumericString, ObjectIdentifier, OctetString,
    PrintableString, TeletexString, UTF8String, UniversalString, VisibleString,
)


class NamedNumber(Integer):
    _map = {-7: 'below', 128: 'above'}


class NamedAlternative(Enumerated):
    _map = {0: 'idle', 128: 'active'}


class NamedIdentifier(ObjectIdentifier):
    _map = {'1.2.840.113549': 'organization', '2.999.16384.0.128': 'large'}


class SparseFlags(BitString):
    _map = {0: 'read', 3: 'write', 9: 'audit'}


def scalar_vectors():
    """Return independent (public class, input/native value, DER) vectors."""
    return (
        (Boolean, False, b'\x01\x01\x00'),
        (Boolean, True, b'\x01\x01\xff'),
        (Integer, 0, b'\x02\x01\x00'),
        (Integer, 127, b'\x02\x01\x7f'),
        (Integer, 128, b'\x02\x02\x00\x80'),
        (Integer, -128, b'\x02\x01\x80'),
        (Integer, -129, b'\x02\x02\xff\x7f'),
        (Integer, 18446744073709551616, b'\x02\x09\x01' + b'\x00' * 8),
        (Null, None, b'\x05\x00'),
        (ObjectIdentifier, '1.2.840.113549', b'\x06\x06\x2a\x86\x48\x86\xf7\x0d'),
        (BitString, (), b'\x03\x01\x00'),
        (BitString, (1, 0, 1, 0, 0), b'\x03\x02\x03\xa0'),
        (BitString, (0, 0, 0, 0, 0, 0, 0, 1, 1), b'\x03\x03\x07\x01\x80'),
        (OctetString, b'', b'\x04\x00'),
        (OctetString, b'\x00\x80\xff', b'\x04\x03\x00\x80\xff'),
    )


def text_vectors():
    """Return every promised text class with tag, text and codec payload."""
    rows = [
        (UTF8String, 12, 'Aé水😀', 'utf-8'),
        (NumericString, 18, '9 é!', 'latin-1'),
        (PrintableString, 19, 'Qé@', 'latin-1'),
        (TeletexString, 20, 'Az 09', 'ascii'),
        (IA5String, 22, 'Mail 09@', 'ascii'),
        (GraphicString, 25, 'Gé\xff', 'latin-1'),
        (VisibleString, 26, 'Vé\x01', 'latin-1'),
        (GeneralString, 27, 'Gé\x00', 'latin-1'),
        (UniversalString, 28, 'A水😀', 'utf-32-be'),
        (CharacterString, 29, 'Cé\xff', 'latin-1'),
        (BMPString, 30, 'Aé水', 'utf-16-be'),
    ]
    return tuple((cls, tag, text, text.encode(codec))
                 for cls, tag, text, codec in rows)


def short_primitive(tag, payload):
    """Frame independent payloads using X.690 short universal identifiers/lengths."""
    assert 0 <= tag < 31 and len(payload) < 128
    return bytes((tag, len(payload))) + payload


def nested_chunks(tag, chunks):
    """Frame supplied complete chunks as a two-level indefinite string."""
    assert len(chunks) >= 2
    start = bytes((tag | 0x20, 0x80))
    return start + chunks[0] + start + b''.join(chunks[1:]) + b'\x00\x00\x00\x00'
