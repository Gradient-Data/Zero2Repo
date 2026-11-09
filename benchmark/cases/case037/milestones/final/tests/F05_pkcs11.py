# feature: F05
"""Acceptance through a real offline PKCS#11 software token provider."""
import gc

import velnora
import pkcs11
import pytest
from cryptography import x509

from F01_helpers import WireReader, identity, read_public_blob
from F05_helpers import token_provider, verify_agent_signature


def test_pkcs11_identities_certificates_selectors_and_failures(tmp_path):
    """F05.T05: real RSA/EC signing, X.509 association, selectors and refusal."""
    with token_provider(tmp_path) as (provider, pin, materials):
        # Exercise refused access before opening any successful product session;
        # an existing authenticated session must not make a wrong PIN look valid.
        with pytest.raises(pkcs11.PinIncorrect):
            velnora.load_pkcs11_keys(provider, 'incorrect PIN', token_label='alpha')
        with pytest.raises(pkcs11.PKCS11Error):
            velnora.load_pkcs11_keys(str(tmp_path / 'unavailable-provider.so'), pin)

        def check(selection, expected, load_certs=True):
            gc.collect()
            keys = velnora.load_pkcs11_keys(provider, pin, load_certs=load_certs, **selection)
            expected_by_identity = {identity(item['external']): item for item in expected}
            observed = []
            for key in keys:
                if key.has_cert:
                    packet = WireReader(key.public_data)
                    packet.string()  # The certificate algorithm names the carrier.
                    certs = [packet.string() for _ in range(packet.uint32())]
                    for _ in range(packet.uint32()):
                        packet.string()  # Optional OCSP responses.
                    packet.finish()
                    assert len(certs) == 1
                    public = x509.load_der_x509_certificate(certs[0]).public_key()
                    assert identity(public) in expected_by_identity, 'Token returned an identity outside the supplied selectors'
                    expected_material = expected_by_identity[identity(public)]
                    assert certs == [expected_material['certificate']]
                    observed.append((expected_material['blob'], True))
                else:
                    public = read_public_blob(key.public_data)
                    assert identity(public) in expected_by_identity, 'Token returned an identity outside the supplied selectors'
                    expected_material = expected_by_identity[identity(public)]
                    assert key.public_data == expected_material['blob']
                    observed.append((key.public_data, False))
                # Verify the selected identity actually signs independent data,
                # including its certificate-bearing form, using external crypto.
                algorithm = expected_material['algorithm']
                key.set_sig_algorithm(b'rsa-sha2-256' if algorithm == 'ssh-rsa'
                                      else algorithm.encode())
                for message in (b'token signature proof\x00', b'second independent challenge\xff'):
                    verify_agent_signature(key.sign(message), public, algorithm, message)
            wanted = {item['blob'] for item in expected}
            assert {blob for blob, certified in observed} == wanted
            if load_certs:
                assert {blob for blob, certified in observed if certified} == wanted
            else:
                assert all(not certified for blob, certified in observed)

        alpha = [item for item in materials if item['token'] == 'alpha']
        beta = [item for item in materials if item['token'] == 'beta']
        check({'token_label': 'alpha'}, alpha)
        check({'token_label': 'alpha'}, alpha, load_certs=False)
        check({'token_serial': beta[0]['serial']}, beta)
        check({'token_serial': alpha[0]['serial'].decode()}, alpha)
        check({'token_label': 'alpha', 'key_label': 'shared'}, [materials[0]])
        check({'token_label': 'alpha', 'token_serial': alpha[0]['serial'],
               'key_label': 'curve'}, [materials[1]])
        # Each selector must intersect with the others; neither union nor
        # applying only the first supplied selector may expose an identity.
        check({'token_label': 'alpha', 'token_serial': beta[0]['serial']}, [])
        check({'token_label': 'absent token'}, [])
        check({'token_label': 'alpha', 'key_label': 'absent key'}, [])
