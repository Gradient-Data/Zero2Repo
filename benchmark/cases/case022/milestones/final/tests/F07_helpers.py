# feature: F07
"""Real media sources and isolated public dataset observations."""
import functools
from pathlib import Path
import wave

import numpy as np

from _helpers import run_python, run_command
from F01_helpers import typed_dataset


def media_source_test(function):
    """Select the mounted product before importing any product module."""
    @functools.wraps(function)
    def execute(tmp_path):
        source = """
import sys
from pathlib import Path
sys.path.insert(0, '/app/src')
sys.path.insert(0, sys.argv[1])
from F07_media import FUNCTION
FUNCTION.__wrapped__(Path(sys.argv[2]))
""".replace('FUNCTION', function.__name__)
        result = run_python(source, timeout=150,
                            args=(str(Path(__file__).parent), str(tmp_path)))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def media_value(value, feature):
    return typed_dataset([value], feature)[0]['value']


def assert_raw_media(path, feature):
    """Read both reference and embedded content without decoding."""
    content = path.read_bytes()
    raw = media_value(str(path), feature(decode=False))
    assert raw == {'path': str(path), 'bytes': None}
    reference = 'embedded' + ''.join(path.suffixes)
    raw = media_value({'path': reference, 'bytes': content}, feature(decode=False))
    assert raw == {'path': reference, 'bytes': content}


def audio_source(root):
    rate = 16000
    time = np.arange(rate // 4) / rate
    samples = np.stack([0.5 * np.sin(2 * np.pi * 320 * time),
                        0.25 * np.sin(2 * np.pi * 720 * time)])
    pcm = (samples * 32767).astype('<i2')
    path = root / 'signal.wav'
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(pcm.T.tobytes())
    return path, pcm.astype(float) / 32768, rate


def video_source(root):
    frames = np.zeros((5, 12, 16, 3), dtype=np.uint8)
    for index in range(len(frames)):
        frames[index] = (20 + index * 35, 180 - index * 20, 40 + index * 15)
    paths = []
    for index, values in enumerate((frames, frames[..., ::-1].copy())):
        path = root / f'frames{index}.rgb'
        path.write_bytes(values.tobytes())
        paths.append(path)
    output = root / 'streams.mkv'
    result = run_command(['ffmpeg', '-v', 'error', '-y',
                          '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '16x12', '-framerate', '5', '-i', paths[0],
                          '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '16x12', '-framerate', '5', '-i', paths[1],
                          '-map', '0:v', '-map', '1:v', '-c:v', 'ffv1', output], timeout=30)
    assert result.returncode == 0, result.stderr
    return output, frames


def pdf_source(root):
    """Write a small standards-shaped PDF with independently specified page text."""
    texts = ['Cedar river', 'Quartz meadow']
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>']
    for index, text in enumerate(texts):
        content = f'BT /F1 18 Tf 30 100 Td ({text}) Tj ET'.encode('ascii')
        objects.extend([f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 7 0 R >> >> /Contents {4 + 2 * index} 0 R >>'.encode(),
                        f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'\nendstream'])
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    data = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    path = root / 'pages.pdf'
    path.write_bytes(data)
    return path, texts


def mesh_triangles(decoded):
    """Collect faces without fixing vertex numbering, face order or winding."""
    parts = list(decoded.geometry.values()) if hasattr(decoded, 'geometry') else [decoded]
    return [triangle for part in parts
            for triangle in np.asarray(part.vertices)[np.asarray(part.faces)]]


def assert_mesh_geometry(actual, expected):
    """Require a one-to-one face match within the public coordinate accuracy."""
    from itertools import permutations
    from scipy.optimize import linear_sum_assignment
    actual, expected = np.asarray(actual), np.asarray(expected)
    assert actual.shape == expected.shape
    # A bipartite match preserves duplicate faces and accepts every vertex order.
    errors = np.full((len(actual), len(expected)), np.inf)
    for order in permutations(range(3)):
        differences = np.abs(actual[:, None, list(order), :] - expected[None, :, :, :])
        errors = np.minimum(errors, differences.max(axis=(2, 3)))
    rows, columns = linear_sum_assignment(errors)
    assert np.all(errors[rows, columns] <= 1e-5), errors
