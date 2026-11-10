# feature: F10
"""Certificate identity selection and matching through public entries."""
import unittest
from _helpers import standard_tools
from F10_helpers import identity_certificates


class TestCertificateIdentity(unittest.TestCase):
    def test_f10_t01(self):
        accepted = ['a.co', '7.net', 'A-9.Example.ORG', '*.example.org',
                    'ab--cd.example.org']
        rejected = ['localhost', 'example.c', 'example.12', '-a.example.org',
                    'a-.example.org', 'a_b.example.org', 'a..example.org',
                    '.example.org', 'example.org.', 'f*.example.org',
                    'www.*.example.org', 'two words.example.org', '192.0.2.9']
        # Absent and explicitly empty SAN both permit the scoped CN grammar.
        for alternatives in (None, []):
            for cert in identity_certificates(accepted + rejected, alternatives):
                self.assertCountEqual(cert.valid_domains, accepted, msg=('alternatives=%r' % (alternatives,),))
            for cert in identity_certificates((), alternatives):
                self.assertEqual(cert.valid_domains, [])
        alternatives = [('dns_name', 'first.example.org'),
                        ('uniform_resource_identifier', 'https://uri.example.org/'),
                        ('dns_name', 'second.example.org'),
                        ('dns_name', 'first.example.org')]
        for cert in identity_certificates(['cn.example.org'], alternatives):
            self.assertCountEqual(cert.valid_domains,
                                  ['first.example.org', 'second.example.org'])
        for alternatives in ([('rfc822_name', 'person@example.org')],
                             [('ip_address', '192.0.2.9')]):
            for cert in identity_certificates(['cn.example.org'], alternatives):
                self.assertEqual(cert.valid_domains, [])

    def test_f10_t02(self):
        # Each row isolates a necessary matching rule; no private matcher is used.
        rows = [
            (['MiXeD.Example.ORG'], [('mixed.example.org', True),
                                     ('MIXED.EXAMPLE.ORG', True),
                                     ('other.example.org', False),
                                     ('mixed.other.org', False),
                                     ('sub.mixed.example.org', False),
                                     ('example.org', False)]),
            (['xn--bcher-kva.example'], [('bücher.example', True),
                                         ('XN--BCHER-KVA.EXAMPLE', True),
                                         ('bucher.example', False)]),
            (['bücher.example'], [('xn--bcher-kva.example', True),
                                  ('BÜCHER.EXAMPLE', True)]),
            # RFC 3490 nameprep, as distinct from IDNA 2008, maps sharp s.
            (['faß.example'], [('fass.example', True), ('fas.example', False)]),
            (['*.example.org'], [('api.example.org', True),
                                  ('xn--bcher-kva.example.org', True),
                                  ('example.org', False),
                                  ('a.b.example.org', False),
                                  ('api.example.net', False)]),
            (['pre*post.example.org'], [('prepost.example.org', True),
                                         ('pre-middle-post.example.org', True),
                                         ('pre.example.org', False),
                                         ('post.example.org', False),
                                         ('xprepost.example.org', False),
                                         ('prepostx.example.org', False)]),
            (['*tail.example.org'], [('tail.example.org', True),
                                     ('longtail.example.org', True),
                                     ('tails.example.org', False)]),
            (['head*.example.org'], [('head.example.org', True),
                                     ('headlong.example.org', True),
                                     ('ahead.example.org', False)]),
            (['a**b.example.org'], [('ab.example.org', False),
                                    ('axxb.example.org', False)]),
            (['www.*.org'], [('www.example.org', False)]),
            (['*.exam*ple.org'], [('api.example.org', False)]),
            # These are round-trippable IDNA labels. A wildcard matcher that
            # ignores the A-label restriction would accept the second label.
            (['b*ücher.example'], [('baücher.example', False)]),
            (['no.example.org', 'yes.example.org'], [('yes.example.org', True),
                                                    ('none.example.org', False)]),
            ([], [('absent.example.org', False)]),
        ]
        for identities, queries in rows:
            alternatives = [('dns_name', name) for name in identities]
            for cert in identity_certificates(['ignored.example.org'], alternatives):
                # Empty SAN falls back to this CN, which still cannot match queries.
                for query, expected in queries:
                    self.assertIs(cert.is_valid_domain_ip(query), expected, msg=('identities=%r' % (identities,), 'query=%r' % (query,),))
        # Matching must use the selected identities, including SAN precedence.
        for alternatives, expected in ((None, True), ([], True),
                                       ([('rfc822_name', 'person@example.org')], False),
                                       ([('dns_name', 'different.example.org')], False)):
            for cert in identity_certificates(['cn.example.org'], alternatives):
                self.assertIs(cert.is_valid_domain_ip('cn.example.org'), expected)

    def test_f10_t03(self):
        addresses = ['192.0.2.37', '2001:db8::5:9']
        ip = standard_tools().ipaddress.ip_address
        alternatives = [('dns_name', 'identity.example.org')]
        alternatives += [('ip_address', address) for address in addresses]
        queries = [('192.0.2.37', True), ('192.0.2.38', False),
                   ('2001:db8::5:9', True),
                   ('2001:0DB8:0000:0000:0000:0000:0005:0009', True),
                   ('2001:db8::5:a', False), ('::ffff:192.0.2.37', False)]
        for cert in identity_certificates(['198.51.100.7'], alternatives):
            self.assertCountEqual([ip(value).packed for value in cert.valid_ips],
                                  [ip(value).packed for value in addresses])
            self.assertIs(cert.is_valid_domain_ip('identity.example.org'), True)
            for query, expected in queries:
                self.assertIs(cert.is_valid_domain_ip(query), expected, msg=('query=%r' % (query,),))
            for invalid in (None, b'192.0.2.37', 123, ['192.0.2.37']):
                with self.assertRaises(TypeError, msg=('non_text=%r' % (invalid,),)):
                    cert.is_valid_domain_ip(invalid)
        # Neither a CN nor a DNS SAN can supply either address family.
        for address in addresses:
            for alternatives in (None, [], [('dns_name', address)]):
                for cert in identity_certificates([address], alternatives):
                    self.assertEqual(cert.valid_ips, [])
                    self.assertIs(cert.is_valid_domain_ip(address), False)
