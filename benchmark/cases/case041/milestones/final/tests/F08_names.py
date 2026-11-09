# feature: F08
"""Acceptance of public X.509 name/address behavior, without crypto operations."""
import unittest
import ast
from collections import Counter
from cobaltform.core import UTF8String
from cobaltform.util import iri_to_uri, uri_to_iri
from cobaltform.x509 import (
    DNSName, DirectoryString, EmailAddress, GeneralName, Name, URI, strict_teletex,
)
from _helpers import observe, standard_tools
from F02_helpers import short_primitive
from F08_helpers import (NAME_ATTRIBUTES, NAME_DISPLAY_LABELS, grouped_name, name_groups, name_vector,
                         readable_name_fields, uri_escape_case)


class TestNameAddress(unittest.TestCase):
    def test_f08_t01(self):
        groups = [[('2.5.4.3', 'Ada'), ('2.5.4.3', 'Bela')],
                  [('2.5.4.10', 'Laboratory')], [('2.5.4.3', 'Cora')],
                  [('2.5.4.45', b'\x00\x80\xff')]]
        for name in (grouped_name(groups), Name.load(name_vector('grouped'))):
            self.assertEqual(name_groups(name), [sorted(g) for g in groups])
            native = name.native
            self.assertEqual(set(native), {'common_name', 'organization_name', 'unique_identifier'})
            self.assertIsInstance(native['common_name'], list)
            self.assertEqual(Counter(native['common_name']), Counter(['Ada', 'Bela', 'Cora']))
            self.assertEqual(native['organization_name'], 'Laboratory')
            self.assertEqual(native['unique_identifier'], b'\x00\x80\xff')
            self.assertEqual(name.dump(force=True), name_vector('grouped'))
            # Locate the member by its semantic value, not incidental SET order.
            member = next(m for m in name.chosen[0] if m['value'].native == 'Ada')
            member['value'] = DirectoryString(('utf8_string', 'Grace'))
            self.assertEqual(name.dump(force=True), name_vector('modified'))
            changed = [[('2.5.4.3', 'Grace'), ('2.5.4.3', 'Bela')]] + groups[1:]
            self.assertEqual(name_groups(Name.load(name.dump())), [sorted(g) for g in changed])
        empty = Name.load(name_vector('empty'))
        self.assertEqual(name_groups(empty), [])
        self.assertEqual(empty.dump(force=True), name_vector('empty'))

    def test_f08_t02(self):
        # Separate default behavior, text selection and numeric spelling; no
        # cross-product with independently covered representation choices.
        for printable, numeric in ((False, False), (True, False), (False, True)):
            # Reverse insertion prevents insertion order from satisfying the rule.
            fields = {identity if numeric else name: value
                      for name, identity, kind, value in reversed(NAME_ATTRIBUTES)}
            name = Name.build(fields, use_printable=printable)
            self.assertEqual(len(name.chosen), len(NAME_ATTRIBUTES))
            for rdn, (label, identity, kind, value) in zip(name.chosen, NAME_ATTRIBUTES):
                self.assertEqual(len(rdn), 1)
                self.assertEqual(rdn[0]['type'].dotted, identity)
                self.assertEqual(rdn[0]['value'].native, value)
                if kind in ('directory', 'printable'):
                    expected = 'printable_string' if printable or kind == 'printable' else 'utf8_string'
                    self.assertEqual(rdn[0]['value'].name, expected)
            self.assertEqual(name.dump(), name_vector('build_printable' if printable else 'build_utf8'))
        # The omitted text-selection argument has the promised UTF-8 default.
        default = Name.build({'common_name': 'Élodie'})
        self.assertEqual(default.chosen[0][0]['value'].name, 'utf8_string')
        self.assertEqual(default.chosen[0][0]['value'].native, 'Élodie')
        result = observe(lambda: Name.build({'1.3.6.1.4.1.55555.812': 'Unknown'}),
                         consumers=(lambda n: n.dump(),), expected_exceptions=(ValueError,))
        self.assertIsInstance(result.error, ValueError)

    def test_f08_t03(self):
        # RFC 4518 mapping, case folding, NFKC and insignificant spacing.
        for left, right in (
            ('  Alice  Smith ', 'alice smith'), ('Alice\tSmith', 'alice smith'),
            ('Straße', 'STRASSE'), ('Ａlice', 'alice'), ('Cafe\u0301', 'CAFÉ'),
            ('Al\u00adice', 'Alice'), ('Alice\u200b', 'alice'), ('Alice\u00a0Smith', 'alice smith'),
            # Mappings that compatibility normalization alone does not perform.
            ('Alice\u1680Smith', 'alice smith'), ('Alice\u200e', 'alice'), ('Alice\U000E0041', 'alice'),
            ('אב', 'אב'),
        ):
            a = grouped_name([[('2.5.4.3', left)]])
            b = grouped_name([[('2.5.4.3', right)]])
            self.assertTrue(a == b, (left, right))
            self.assertFalse(a != b)
        groups = [[('2.5.4.3', 'Alice'), ('2.5.4.10', 'Lab')], [('2.5.4.6', 'US')]]
        a = grouped_name(groups)
        self.assertTrue(a == grouped_name([list(reversed(groups[0])), groups[1]]))
        for different in (
            list(reversed(groups)),
            [[('2.5.4.3', 'Alice')], [('2.5.4.10', 'Lab')], [('2.5.4.6', 'US')]],
            [[('2.5.4.4', 'Alice'), ('2.5.4.10', 'Lab')], groups[1]],
            [[('2.5.4.3', 'Alicia'), ('2.5.4.10', 'Lab')], groups[1]],
            [groups[0]],
        ):
            self.assertFalse(a == grouped_name(different))
            self.assertTrue(a != grouped_name(different))
        for invalid in ('\ue000', '\ufdd0', '\ufffd', '\u0378', 'אaב', '1אב', 'אב1'):
            result = observe(lambda: grouped_name([[('2.5.4.3', invalid)]]) ==
                             grouped_name([[('2.5.4.3', 'Valid')]]),
                             expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError, repr(invalid))

    def test_f08_t04(self):
        structured = (
            ('other_name', {'type_id': '1.2.3.4', 'value': UTF8String('External identity', explicit=0)}),
            ('x400_address', {'built_in_standard_attributes': {'organization_name': 'Org X'}}),
            ('directory_name', grouped_name([[('2.5.4.3', 'Directory Person')]])),
            ('registered_id', '1.2.3.401'),
        )
        for alternative, fields in structured:
            for value in (GeneralName((alternative, fields)),
                          GeneralName.load(name_vector(alternative))):
                self.assertEqual(value.name, alternative)
                if alternative == 'other_name':
                    self.assertEqual(value.chosen['type_id'].dotted, '1.2.3.4')
                    self.assertEqual(value.chosen['value'].native, 'External identity')
                elif alternative == 'x400_address':
                    self.assertEqual(value.chosen['built_in_standard_attributes']['organization_name'].native, 'Org X')
                elif alternative == 'directory_name':
                    self.assertEqual(value.native, {'common_name': 'Directory Person'})
                else:
                    self.assertEqual(value.chosen.dotted, '1.2.3.401')
                self.assertEqual(value.dump(force=True), name_vector(alternative))
        # EDI support covers its alternative identity and opaque encoding.
        edi_wire = name_vector('edi_party_name')
        edi = GeneralName.load(edi_wire)
        self.assertEqual(edi.name, 'edi_party_name')
        self.assertEqual(edi.dump(), edi_wire)
        for alternative, text, ascii_text, context_tag in (
            ('dns_name', 'bücher.example', b'xn--bcher-kva.example', 0x82),
            ('rfc822_name', 'Nora@bücher.example', b'Nora@xn--bcher-kva.example', 0x81),
            ('uniform_resource_identifier', 'https://bücher.example/é?q=水#fin',
             b'https://xn--bcher-kva.example/%C3%A9?q=%E6%B0%B4#fin', 0x86),
        ):
            wire = bytes((context_tag, len(ascii_text))) + ascii_text
            for value in (GeneralName((alternative, text)), GeneralName.load(wire)):
                self.assertEqual(value.name, alternative)
                self.assertEqual(value.native, text)
                self.assertEqual(value.chosen.native, text)
                self.assertEqual(uri_escape_case(value.dump()), uri_escape_case(wire))
        ip = standard_tools().ipaddress
        # Every prefix is a different promised accepted range, tested without
        # multiplying it by unrelated GeneralName alternatives or spellings.
        for address, width in (('192.0.2.129', 32), ('2001:db8::1234', 128)):
            packed = ip.ip_address(address).packed
            for prefix in (None, *range(width + 1)):
                text = address if prefix is None else '%s/%d' % (address, prefix)
                mask = b'' if prefix is None else ip.ip_network('0.0.0.0/%d' % prefix if width == 32
                    else '::/%d' % prefix).netmask.packed
                wire = bytes((0x87, len(packed + mask))) + packed + mask
                for value in (GeneralName(('ip_address', text)), GeneralName.load(wire)):
                    self.assertEqual(value.name, 'ip_address')
                    native = value.native.split('/')
                    self.assertEqual(ip.ip_address(native[0]), ip.ip_address(address))
                    self.assertEqual(native[1:], [] if prefix is None else [str(prefix)])
                    self.assertEqual(value.dump(), wire)
        for invalid in ('300.1.2.3', '2001:db8::gg', '192.0.2.1/-1',
                        '192.0.2.1/33', '2001:db8::1/-1', '2001:db8::1/129'):
            errors = (ValueError,) if '/' in invalid else (ValueError, OSError)
            result = observe(lambda: GeneralName(('ip_address', invalid)),
                consumers=(lambda v: (v.native, v.dump()),), expected_exceptions=errors)
            self.assertIsInstance(result.error, errors)

    def test_f08_t05(self):
        vectors = (
            ('https://usér:páss@bücher.example:8443/été/@:x?q=水&mode=a/b?#finé',
             b'https://us%C3%A9r:p%C3%A1ss@xn--bcher-kva.example:8443/%C3%A9t%C3%A9/@:x?q=%E6%B0%B4&mode=a/b?#fin%C3%A9'),
            ('http://example.org:80/a%2Fb?q=a%26b%3Dc#x',
             b'http://example.org:80/a%2Fb?q=a%26b%3Dc#x'),
            ('https://example.org:443/', b'https://example.org:443/'),
        )
        for iri, uri in vectors:
            actual = iri_to_uri(iri)
            self.assertIsInstance(actual, bytes)
            self.assertEqual(uri_escape_case(actual), uri_escape_case(uri))
            restored = uri_to_iri(uri)
            self.assertIsInstance(restored, str)
            self.assertEqual(uri_escape_case(restored), uri_escape_case(iri))
        for scheme, port in (('http', 80), ('https', 443)):
            iri = '%s://bücher.example:%d/résumé?q=1#part' % (scheme, port)
            ordinary = ('%s://xn--bcher-kva.example:%d/r%%C3%%A9sum%%C3%%A9?q=1#part' % (scheme, port)).encode('ascii')
            normalized = ('%s://xn--bcher-kva.example/r%%C3%%A9sum%%C3%%A9?q=1#part' % scheme).encode('ascii')
            self.assertEqual(uri_escape_case(iri_to_uri(iri)), uri_escape_case(ordinary))
            self.assertEqual(uri_escape_case(iri_to_uri(iri, normalize=True)), uri_escape_case(normalized))
        for url in ('https://example.org:8443/a', 'https://example.org:80/a', 'http://example.org:443/a'):
            # Only the scheme's own default port is removed.
            self.assertEqual(iri_to_uri(url, normalize=True), url.encode('ascii'))
        for entry, wrong in ((iri_to_uri, b'http://example.org'), (iri_to_uri, 7),
                             (uri_to_iri, 'http://example.org'), (uri_to_iri, None)):
            result = observe(lambda: entry(wrong), expected_exceptions=(TypeError,))
            self.assertIsInstance(result.error, TypeError)

    def test_f08_t06(self):
        # T.61 (1992) single-octet assignments differ from Windows-1252 here.
        wire = b'\x14\x04A\xa4\xa6\xe0'
        self.assertEqual(DirectoryString.load(wire).native, 'A¤¦à')
        self.assertEqual(DirectoryString.load(b'\x14\x01\x80').native, '€')
        with strict_teletex():
            self.assertEqual(DirectoryString.load(wire).native, 'A$#Ω')
            for payload in (b'{', b'\xd0'):
                result = observe(lambda: DirectoryString.load(short_primitive(20, payload)),
                    consumers=(lambda v: v.native,), expected_exceptions=(UnicodeDecodeError,))
                self.assertIsInstance(result.error, UnicodeDecodeError)
        self.assertEqual(DirectoryString.load(wire).native, 'A¤¦à')
        self.assertEqual(DirectoryString.load(b'\x14\x01{').native, '{')

    def test_f08_t07(self):
        for label in ('empty', 'digest_a', 'digest_b'):
            wire = name_vector(label)
            loaded = Name.load(wire)
            groups = {'empty': [], 'digest_a': [[('2.5.4.3', 'Digest Name')]],
                'digest_b': [[('2.5.4.6', 'GB')], [('2.5.4.10', 'Independent Laboratory'),
                                                ('2.5.4.3', 'Delta')], [('2.5.4.45', b'\x00\x80\xff')]]}[label]
            created = grouped_name(groups)
            # Constructed country text here is UTF-8; the independent digest_b
            # vector intentionally uses PrintableString, as real names may.
            if label == 'digest_b':
                created.chosen[0][0]['value'] = DirectoryString(('printable_string', 'GB'))
            for name in (loaded, created):
                self.assertEqual(name.dump(force=True), wire)
                self.assertEqual(name.sha1, standard_tools().hashlib.sha1(wire).digest())
                self.assertEqual(name.sha256, standard_tools().hashlib.sha256(wire).digest())

    def test_f08_t08(self):
        for groups, expected in (
            ([[('2.5.4.3', 'Mira')], [('2.5.4.10', 'Optics')], [('2.5.4.6', 'GB')]],
             {'Common Name': ['Mira'], 'Organization': ['Optics'], 'Country': ['GB']}),
            ([[('2.5.4.3', 'Mira'), ('2.5.4.11', 'Imaging')], [('2.5.4.3', 'Ren')],
              [('2.5.4.3', 'Mira')], [('2.5.4.10', 'Optics')]],
             {'Common Name': ['Mira', 'Ren', 'Mira'], 'Organizational Unit': ['Imaging'], 'Organization': ['Optics']}),
        ):
            fields = readable_name_fields(grouped_name(groups).human_friendly)
            self.assertEqual(set(fields), set(expected))
            for label, values in expected.items():
                self.assertEqual(Counter(fields[label]), Counter(values))

        all_text = Name.build({name: value for name, identity, kind, value in NAME_ATTRIBUTES
                                    if kind != 'binary'})
        fields = readable_name_fields(all_text.human_friendly)
        expected = {label: [row[3]] for label, row in zip(NAME_DISPLAY_LABELS, NAME_ATTRIBUTES[:-1])}
        self.assertEqual(fields, expected)

        binary = Name.build({'common_name': 'Spectra', 'unique_identifier': b'\x00\x80\xff'})
        fields = readable_name_fields(binary.human_friendly)
        self.assertEqual(set(fields), {'Common Name', 'Unique Identifier'})
        self.assertEqual(fields['Common Name'], ['Spectra'])
        self.assertEqual(len(fields['Unique Identifier']), 1)
        self.assertEqual(ast.literal_eval(fields['Unique Identifier'][0]), b'\x00\x80\xff')

    def test_f08_t09(self):
        pairs = (
            ('dns_name', 'Mail.Example', 'mail.example', True),
            ('dns_name', 'mail.example', 'other.example', False),
            ('rfc822_name', 'Nora@Mail.Example', 'Nora@mail.example', True),
            ('rfc822_name', 'Nora@mail.example', 'nora@mail.example', False),
            ('rfc822_name', 'Nora@mail.example', 'Nora@other.example', False),
            ('ip_address', '2001:db8::1', '2001:0db8:0:0:0:0:0:1', True),
            ('ip_address', '192.0.2.1', '192.0.2.2', False),
            ('ip_address', '192.0.2.1', '::ffff:192.0.2.1', False),
            ('ip_address', '192.0.2.1', '192.0.2.1/32', False),
            ('ip_address', '192.0.2.1/24', '192.0.2.1/25', False),
            ('ip_address', '2001:db8::1/64', '2001:0db8::1/64', True),
            ('registered_id', '1.2.3.400', '1.2.3.400', True),
            ('registered_id', '1.2.3.400', '1.2.3.401', False),
            ('directory_name', grouped_name([[('2.5.4.3', 'Nora')]]),
             grouped_name([[('2.5.4.3', ' nora ')]]), True),
            ('directory_name', grouped_name([[('2.5.4.3', 'Nora')]]),
             grouped_name([[('2.5.4.4', 'Nora')]]), False),
        )
        for alternative, left, right, equal in pairs:
            a, b = GeneralName((alternative, left)), GeneralName((alternative, right))
            self.assertEqual(a == b, equal, (alternative, left, right))
            self.assertEqual(a.chosen == b.chosen, equal)
            self.assertEqual(a != b, not equal)
        # Decoded addresses keep the same rule: domain case is insignificant,
        # local-part case is significant.
        loaded = lambda text: EmailAddress.load(short_primitive(22, text))
        for left, right, equal in ((b'Nora@Mail.EXAMPLE', 'Nora@mail.example', True),
                                   (b'nora@mail.example', 'Nora@mail.example', False)):
            self.assertIs(loaded(left) == EmailAddress(right), equal)
            self.assertIs(loaded(left) == loaded(right.encode('ascii')), equal)
        for alternative, cls, text, ascii_text in (
            ('dns_name', DNSName, 'Bücher.example', b'xn--bcher-kva.example'),
            ('rfc822_name', EmailAddress, 'Nora@Bücher.example', b'Nora@xn--bcher-kva.example'),
        ):
            # A-label input is decoded, not a newly constructed mixed DNS value.
            a, b = cls(text), cls.load(short_primitive(22, ascii_text))
            self.assertTrue(a == b)
            self.assertTrue(GeneralName((alternative, a)) == GeneralName((alternative, b)))
        self.assertFalse(GeneralName(('dns_name', 'same.example')) ==
                         GeneralName(('rfc822_name', 'Nora@same.example')))
        supported = GeneralName(('dns_name', 'working.example'))
        for alternative in ('other_name', 'x400_address', 'edi_party_name'):
            # These names are independently encoded; comparison must refuse
            # before decoding unsupported values or testing alternative inequality.
            unsupported = GeneralName.load(name_vector(alternative))
            for a, b in ((unsupported, supported), (supported, unsupported), (unsupported, unsupported)):
                result = observe(lambda: a == b, expected_exceptions=(ValueError,))
                self.assertIsInstance(result.error, ValueError)

    def test_f08_t10(self):
        for left, right, equal in (
            ('HTTP://Example.org/a', 'http://example.org/a', True),
            ('https://bücher.example/a', 'https://xn--bcher-kva.example/a', True),
            ('http://example.org:80/a', 'http://example.org/a', True),
            ('https://example.org:443/a', 'https://example.org/a', True),
            ('http://example.org/%41%7E%2D%2E%5F', 'http://example.org/A~-._', True),
            ('http://example.org', 'http://example.org/', True),
            ('https://example.org', 'https://example.org/', True),
            ('http://example.org/Path', 'http://example.org/path', False),
            ('http://example.org/a/b', 'http://example.org/a%2Fb', False),
            ('https://example.org:444/a', 'https://example.org/a', False),
        ):
            self.assertEqual(URI(left) == URI(right), equal, (left, right))
            self.assertEqual(GeneralName(('uniform_resource_identifier', left)) ==
                             GeneralName(('uniform_resource_identifier', right)), equal)
