# feature: F05
"""Read PEM encoding with the standard Base64 decoder, independently of PEM APIs."""

from _helpers import standard_tools


def read_armored_block(encoded):
    """Return (identity, headers, payload) from a single emitted PEM block.

    Boundary lines and colon-separated header fields are the public wire form.
    Neither header ordering nor Base64 line width is prescribed here.
    Invalid output raises; it is never reported as a missing block.
    """
    assert isinstance(encoded, bytes), 'PEM encoding must return bytes'
    lines = encoded.decode('ascii').splitlines()
    assert len(lines) >= 2, 'PEM encoding must include both boundaries'
    assert lines[0].startswith('-----BEGIN ') and lines[0].endswith('-----')
    identity = lines[0][len('-----BEGIN '):-len('-----')]
    assert lines[-1] == '-----END ' + identity + '-----'
    headers = {}
    body = []
    in_headers = True
    for line in lines[1:-1]:
        if not line:
            continue
        if in_headers and ':' in line:
            name, value = line.split(':', 1)
            assert name not in headers, 'Duplicate emitted header'
            headers[name] = value.strip()
        else:
            in_headers = False
            body.append(line)
    payload = standard_tools().base64.b64decode(''.join(body), validate=True)
    return identity, headers, payload
