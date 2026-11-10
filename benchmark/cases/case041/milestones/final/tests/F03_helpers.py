# feature: F03
"""Caller-defined schemas and readers for structured ASN.1 acceptance tests."""

from cobaltform.core import (
    Any, Boolean, Choice, Concat, Integer, Null, ObjectIdentifier, OctetString,
    ParsableOctetBitString, ParsableOctetString, Sequence, SequenceOf, Set, SetOf,
    UTF8String,
)


class PairRecord(Sequence):
    _fields = [('number', Integer), ('label', UTF8String)]


class UnorderedRecord(Set):
    _fields = [('number', Integer, {'implicit': 2}),
               ('label', UTF8String, {'implicit': 0})]


class IntegerList(SequenceOf):
    _child_spec = Integer


class IntegerBag(SetOf):
    _child_spec = Integer


class TextOrNumber(Choice):
    _alternatives = [('number', Integer), ('text', UTF8String)]


class RecursiveRecord(Sequence):
    pass


RecursiveRecord._fields = [('child', RecursiveRecord, {'optional': True}),
                           ('number', Integer)]


class PresenceRecord(Sequence):
    _fields = [('number', Integer),
               ('extra', OctetString, {'optional': True, 'implicit': 0}),
               ('enabled', Boolean, {'default': True}),
               ('nothing', Null, {'optional': True, 'implicit': 1})]


class ChoiceRecord(Sequence):
    _fields = [('value', TextOrNumber)]


class EditableRecord(Sequence):
    _fields = [('pair', PairRecord), ('numbers', IntegerList),
               ('note', UTF8String, {'optional': True, 'explicit': 0})]


class TaggedRecord(Sequence):
    _fields = [('number', Integer, {'explicit': (1, 3)}),
               ('label', UTF8String, {'implicit': (3, 4)})]


class OpenRecord(Sequence):
    _fields = [('kind', ObjectIdentifier), ('payload', Any)]


class AssociatedOpenRecord(OpenRecord):
    _oid_pair = ('kind', 'payload')
    _oid_specs = {'1.2.3': PairRecord}


class EmbeddedOctets(Sequence):
    _fields = [('kind', ObjectIdentifier), ('payload', ParsableOctetString)]
    _oid_pair = ('kind', 'payload')
    _oid_specs = {'1.2.3': PairRecord}


class EmbeddedBits(Sequence):
    _fields = [('kind', ObjectIdentifier), ('payload', ParsableOctetBitString)]
    _oid_pair = ('kind', 'payload')
    _oid_specs = {'1.2.3': PairRecord}


class MixedConcat(Concat):
    _child_specs = [PairRecord, OctetString, Integer]


class DiagnosticRecord(Sequence):
    _fields = [('count', Integer, {'explicit': 2}),
               ('payload', ParsableOctetString)]


def diagnostic_fields(output):
    """Read the labelled field subtrees, preserving relative indentation.

    Field labels and Header/Data/Native/tag lines are the public diagnostic
    shell. Object addresses and implementation class names are never read.
    """
    fields = {}
    current = None
    for line in output.splitlines():
        text = line.lstrip()
        indent = len(line) - len(text)
        if text.startswith('Field "') and text.endswith('"'):
            name = text[len('Field "'):-1]
            if name in fields:
                raise AssertionError('Duplicate diagnostic field label: %s' % name)
            current = []
            fields[name] = current
        elif current is not None:
            for label in ('Header: 0x', 'Data: 0x'):
                if text.startswith(label):
                    text = label + bytes.fromhex(text[len(label):]).hex()
                    break
            current.append((indent, text))
    return fields


def check_diagnostic_headers(lines, physical_headers):
    """Check real framing bytes without prescribing stacked-header grouping.

    A diagnostic may show an individual header or concatenate consecutive
    headers of an explicitly tagged value. The caller supplies independent
    physical headers; no product serialization supplies the expected bytes.
    """
    prefix = 'Header: 0x'
    reported = [bytes.fromhex(line[len(prefix):]) for line in lines
                if line.startswith(prefix)]
    if not reported:
        raise AssertionError('Missing diagnostic header')
    allowed = {b''.join(physical_headers[start:end])
               for start in range(len(physical_headers))
               for end in range(start + 1, len(physical_headers) + 1)}
    if any(not header or header not in allowed for header in reported):
        raise AssertionError('Diagnostic header does not match the value framing')
