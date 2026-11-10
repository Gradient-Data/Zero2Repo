# feature: F03
"""Acceptance tests for host trust and authorized identity restrictions."""
import velnora
import pytest

from _helpers import run_command, run_async
from F02_helpers import certificate_identity
from F03_helpers import (authorized_line, host_line, matched_trust,
                         authenticated_options)


def test_host_patterns(tmp_path):
    """F03.T01: text/file loading and inclusion, exclusion, hashes and networks."""
    key, _ = certificate_identity()
    public = key.convert_to_public()
    scenarios = [
        ('node.example', 'node.example', '192.0.2.17', True),
        ('node.example', 'other.example', '192.0.2.17', False),
        ('192.0.2.17', 'other.example', '192.0.2.17', True),
        ('*.example,!blocked.example', 'node.example', '192.0.2.17', True),
        ('*.example,!blocked.example', 'blocked.example', '192.0.2.17', False),
        ('*.example,!blocked.example', 'node.invalid', '192.0.2.17', False),
        ('192.0.2.0/24,!192.0.2.19', 'node.invalid', '192.0.2.17', True),
        ('192.0.2.0/24,!192.0.2.19', 'node.invalid', '192.0.2.19', False),
        ('192.0.2.0/24,!192.0.2.19', 'node.invalid', '198.51.100.17', False),
    ]
    # OpenSSH supplies hashed input independently of the product's matcher.
    for token in ('node.example', '192.0.2.17'):
        path = tmp_path / ('hashed-' + token)
        path.write_text(host_line(token, key))
        result = run_command(['ssh-keygen', '-H', '-f', path])
        assert result.returncode == 0, result.stderr
        hashed = path.read_text().split()[0]
        assert hashed.startswith('|1|')
        scenarios.extend([(hashed, 'node.example', '192.0.2.17', True),
                          (hashed, 'other.invalid', '198.51.100.17', False)])
    for pattern, host, addr, eligible in scenarios:
        text = '# Host trust\n\n' + host_line(pattern, key)
        path = tmp_path / 'known_hosts'
        path.write_text(text)
        for source in (velnora.import_known_hosts(text), velnora.read_known_hosts(str(path))):
            result = velnora.match_known_hosts(source, host, addr, None)
            assert tuple(set(part) for part in result) == (
                {public} if eligible else set(), set(), set(), set(), set(), set(), set())


def test_port_selection():
    """F03.T02: qualified matches, conditional retry and same-pass revocation."""
    plain, _ = certificate_identity()
    qualified, _ = certificate_identity()
    cert = qualified.generate_x509_host_certificate(qualified, 'CN=Port')
    base = host_line('node.example', plain)
    direct = host_line('[node.example]:2407', qualified)
    assert set(matched_trust(base + direct, port=2407)[0]) == {qualified.convert_to_public()}
    assert set(matched_trust(base + direct, port=2408)[0]) == {plain.convert_to_public()}
    assert not any(matched_trust(direct, port=2408))
    assert not any(matched_trust(direct, port=None))
    assert set(matched_trust(base, port=2407)[0]) == {plain.convert_to_public()}
    # Each trusted category independently prevents the unqualified retry.
    for line, slot, expected in (
            (direct, 0, qualified.convert_to_public()),
            (host_line('[node.example]:2407', qualified, '@cert-authority'), 1,
             qualified.convert_to_public()),
            (host_line('[node.example]:2407', cert), 3, cert)):
        result = matched_trust(base + line, port=2407)
        assert set(result[slot]) == {expected}
        if slot != 0:
            assert result[0] == []
    result = matched_trust(base + '[node.example]:2407 x509v3-ssh-rsa subject=CN=Port\n', port=2407)
    assert result[0] == []
    assert len(result[5]) == 1 and result[5][0].matches(cert.subject)
    revoked = host_line('[node.example]:2407', qualified, '@revoked')
    result = matched_trust(direct + revoked, port=2407)
    assert set(result[0]) == set(result[2]) == {qualified.convert_to_public()}
    # A revocation alone is not a trusted category; do not pin cross-pass merging.
    assert set(matched_trust(base + revoked, port=2407)[0]) == {plain.convert_to_public()}


def test_trust_categories():
    """F03.T03: independently visible key, certificate and subject categories."""
    key, _ = certificate_identity()
    ca, _ = certificate_identity()
    revoked_key, _ = certificate_identity()
    cert = key.generate_x509_host_certificate(key, 'O=Example,CN=Service')
    other = key.generate_x509_host_certificate(key, 'O=Other,CN=Service')
    text = (host_line('node.example', key) +
            host_line('node.example', ca, '@cert-authority') +
            host_line('node.example', key, '@revoked') +
            host_line('node.example', revoked_key, '@revoked') +
            host_line('node.example', cert) +
            host_line('node.example', cert, '@revoked') +
            host_line('node.example', other, '@revoked') +
            'node.example x509v3-ssh-rsa subject=O=Example,CN=Service\n' +
            '@revoked node.example x509v3-ssh-rsa subject=O=Example,*\n')
    result = matched_trust(text)
    for slot, expected in enumerate(({key.convert_to_public()}, {ca.convert_to_public()},
                                     {key.convert_to_public(), revoked_key.convert_to_public()},
                                     {cert}, {cert, other})):
        assert set(result[slot]) == expected
    extended = key.generate_x509_host_certificate(key, 'O=Example,CN=Another')
    assert len(result[5]) == len(result[6]) == 1
    assert result[5][0].matches(cert.subject)
    assert not result[5][0].matches(extended.subject)
    assert not result[5][0].matches(other.subject)
    assert result[6][0].matches(cert.subject)
    assert result[6][0].matches(extended.subject)
    assert not result[6][0].matches(other.subject)
    assert not any(matched_trust(text, host='unrelated.invalid', addr='198.51.100.9'))


def test_authorized_keys(tmp_path):
    """F03.T04: conjunction, exclusions, CA role and first eligible restrictions."""
    key, _ = certificate_identity()
    stranger, _ = certificate_identity()
    public = key.convert_to_public()
    options = ('from="*.example,!blocked.example",from="192.0.2.0/24,!192.0.2.19",'
               'principals="team-*,!team-banned",principals="*-reader"')
    for ca in (False, True):
        prefix = 'cert-authority,' if ca else ''
        text = (authorized_line(key, prefix + 'from="unreachable.example",command="ineligible"') +
                authorized_line(key, prefix + options + ',command="first eligible"') +
                authorized_line(key, prefix + options + ',command="later eligible"'))
        path = tmp_path / 'authorized_keys'
        path.write_text(text)
        for auth in (velnora.import_authorized_keys(text), velnora.read_authorized_keys(path)):
            for host, addr, principals, eligible in (
                    ('node.example', '192.0.2.17', ['team-writer', 'guest-reader'], True),
                    ('blocked.example', '192.0.2.17', ['team-reader'], False),
                    ('node.example', '192.0.2.19', ['team-reader'], False),
                    ('node.invalid', '192.0.2.17', ['team-reader'], False),
                    ('node.example', '198.51.100.17', ['team-reader'], False),
                    ('node.example', '192.0.2.17', ['team-writer'], False),
                    ('node.example', '192.0.2.17', ['guest-reader'], False),
                    ('node.example', '192.0.2.17', ['team-banned', 'guest-reader'], False),
                    ('node.example', '192.0.2.17', [], False)):
                result = auth.validate(public, host, addr, principals, ca)
                if eligible:
                    assert result is not None
                    assert result['command'] == 'first eligible'
                else:
                    assert result is None
            assert auth.validate(public, 'node.example', '192.0.2.17', ['team-reader'], not ca) is None
            assert auth.validate(stranger.convert_to_public(), 'node.example', '192.0.2.17',
                                 ['team-reader'], ca) is None
            # Without supplied principals, principal restrictions do not reject a key.
            assert auth.validate(public, 'node.example', '192.0.2.17', None, ca)['command'] == 'first eligible'


def test_x509_authorization():
    """F03.T05: public key/subject identity and full/prefix subject restrictions."""
    key, _ = certificate_identity()
    stranger, _ = certificate_identity()
    cert = key.generate_x509_user_certificate(key, 'O=Example,CN=Member', principals=['member'])
    wrong_key = stranger.generate_x509_user_certificate(stranger, 'O=Example,CN=Member', principals=['member'])
    wrong_subject = key.generate_x509_user_certificate(key, 'O=Other,CN=Member', principals=['member'])
    wrong_principal = key.generate_x509_user_certificate(key, 'O=Example,CN=Member', principals=['outsider'])
    extended = key.generate_x509_user_certificate(key, 'O=Example,CN=Another', principals=['member'])
    restrictions = 'from="192.0.2.0/24,!192.0.2.19",principals="member",command="accepted" '
    materials = (cert.export_certificate('openssh').decode(),
                 'x509v3-ssh-rsa subject=O=Example,CN=Member\n',
                 'x509v3-ssh-rsa subject=O=Example,*\n')
    for index, material in enumerate(materials):
        auth = velnora.import_authorized_keys(restrictions + material)
        result, trusted = auth.validate_x509(cert, 'node.example', '192.0.2.17')
        assert result is not None and result['command'] == 'accepted'
        assert trusted == (cert if index == 0 else None)
        for candidate, addr, eligible in (
                (wrong_key, '192.0.2.17', index != 0),
                (wrong_subject, '192.0.2.17', False),
                (wrong_principal, '192.0.2.17', False),
                (extended, '192.0.2.17', index == 2),
                (cert, '192.0.2.19', False),
                (cert, '198.51.100.17', False)):
            result, trusted = auth.validate_x509(candidate, 'node.example', addr)
            if eligible:
                assert result is not None and result['command'] == 'accepted'
            else:
                assert (result, trusted) == (None, None)
    auth = velnora.import_authorized_keys('subject="O=Example,*" ' + materials[0])
    assert auth.validate_x509(cert, 'node.example', '192.0.2.17')[0] is not None
    auth = velnora.import_authorized_keys('subject="O=Other,*" ' + materials[0])
    assert auth.validate_x509(cert, 'node.example', '192.0.2.17') == (None, None)


def test_authenticated_restrictions():
    """F03.T06: authorization restrictions survive real login; invalid data fails."""
    key, _ = certificate_identity()
    host, _ = certificate_identity()
    permissions = ('pty', 'X11-forwarding', 'agent-forwarding', 'port-forwarding')
    options = ('command="echo forced",environment="ROLE=reader",'
               'environment="NOTE=two words",permitopen="db.example:5432",'
               'permitopen="[2001:db8::7]:443",permitopen="cache.example:*"')
    for disabled in ((), *((name,) for name in permissions), permissions):
        text = authorized_line(key, ','.join([options, *('no-' + name for name in disabled)]))
        auth = velnora.import_authorized_keys(text)
        allowed, values = run_async(authenticated_options(key, host, auth, permissions))
        assert allowed == {name: name not in disabled for name in permissions}
        assert values == {'command': 'echo forced',
                          'environment': {'ROLE': 'reader', 'NOTE': 'two words'},
                          'permitopen': {('db.example', 5432), ('2001:db8::7', 443),
                                         ('cache.example', None)}}
    for malformed in ('command="unterminated', '=missing', 'environment="ROLE"',
                      'environment="=value"', 'permitopen="db.example"',
                      'permitopen="db.example:invalid"'):
        with pytest.raises(ValueError):
            velnora.import_authorized_keys(authorized_line(key, malformed))
