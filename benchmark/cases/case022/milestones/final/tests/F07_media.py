# feature: F07
"""Acceptance checks for typed media access and decoding choices."""
import numpy as np
from velnora.features import Audio, Image, Mesh, Nifti, Pdf, Video
from PIL import Image as PILImage

from F01_helpers import assert_invalid
from F07_helpers import (media_source_test, media_value, assert_raw_media, audio_source,
                         video_source, pdf_source, mesh_triangles, assert_mesh_geometry)


@media_source_test
def test_image_pixels_modes_and_raw(tmp_path):
    pixels = np.array([[0, 47, 255], [120, 8, 201]], dtype=np.uint8)
    path = tmp_path / 'gray.png'
    PILImage.fromarray(pixels).save(path)
    for source in (str(path), path.read_bytes(), pixels):
        decoded = media_value(source, Image())
        assert decoded.size == (3, 2)
        assert decoded.mode == 'L'
        np.testing.assert_array_equal(np.asarray(decoded), pixels)
        converted = media_value(source, Image(mode='RGB'))
        assert converted.mode == 'RGB'
        np.testing.assert_array_equal(np.asarray(converted), np.repeat(pixels[..., None], 3, axis=2))
    assert media_value(None, Image()) is None
    assert_raw_media(path, Image)


@media_source_test
def test_audio_sources_and_raw(tmp_path):
    path, expected, rate = audio_source(tmp_path)
    for source in (str(path), path.read_bytes(), {'array': expected.astype('float32'), 'sampling_rate': rate}):
        decoded = media_value(source, Audio()).get_all_samples()
        assert decoded.sample_rate == rate
        np.testing.assert_allclose(np.asarray(decoded.data), expected, atol=1e-4, rtol=0)
    assert_raw_media(path, Audio)


@media_source_test
def test_audio_rate_and_channel_conversion(tmp_path):
    path, expected, rate = audio_source(tmp_path)
    for channels in (1, 2):
        target = 8000
        decoded = media_value(str(path), Audio(sampling_rate=target, num_channels=channels)).get_all_samples()
        values = np.asarray(decoded.data)
        assert decoded.sample_rate == target
        assert values.ndim == 2 and values.shape[0] == channels
        assert abs(values.shape[1] - expected.shape[1] * target / rate) <= 1
        # Compare the physical signal away from filter transients. Mono mixing
        # gains differ across valid backends; both original tones must survive.
        time = np.arange(values.shape[1]) / target
        for channel in range(channels):
            frequencies = (320, 720) if channels == 1 else ((320,) if channel == 0 else (720,))
            for frequency in frequencies:
                basis = np.exp(-2j * np.pi * frequency * time[40:-40])
                amplitude = abs(np.mean(values[channel, 40:-40] * basis)) * 2
                source_amplitude = 0.5 if frequency == 320 else 0.25
                assert 0.28 * source_amplitude < amplitude < 1.3 * source_amplitude
            residual = values[channel, 40:-40].copy()
            for frequency in frequencies:
                for basis in (np.sin(2 * np.pi * frequency * time[40:-40]),
                              np.cos(2 * np.pi * frequency * time[40:-40])):
                    residual -= np.dot(residual, basis) / np.dot(basis, basis) * basis
            assert np.sqrt(np.mean(residual ** 2)) < 0.02


@media_source_test
def test_video_frames_streams_and_raw(tmp_path):
    path, frames = video_source(tmp_path)
    for source, stream in ((str(path), None), (path.read_bytes(), None), (str(path), 1)):
        feature = Video() if stream is None else Video(stream_index=stream)
        decoded = media_value(source, feature)
        for index in (3, 0, 4, 1):
            frame = decoded.get_frame_at(index)
            expected = frames[index] if stream is None else frames[index, ..., ::-1]
            np.testing.assert_array_equal(np.asarray(frame.data), expected.transpose(2, 0, 1))
            assert abs(frame.pts_seconds - index / 5) < 1e-6
    assert_raw_media(path, Video)


@media_source_test
def test_pdf_pages_text_and_raw(tmp_path):
    path, texts = pdf_source(tmp_path)
    for source in (str(path), path.read_bytes()):
        decoded = media_value(source, Pdf())
        assert len(decoded.pages) == len(texts)
        assert [page.extract_text().split() for page in decoded.pages] == [text.split() for text in texts]
        decoded.close()
    assert_raw_media(path, Pdf)


@media_source_test
def test_nifti_voxels_space_and_raw(tmp_path):
    import nibabel as nib
    voxels = np.arange(24, dtype=np.int16).reshape(2, 3, 4) - 9
    affine = np.array([[2, 0, 0, 11], [0, 3, 0, -7], [0, 0, 4, 5], [0, 0, 0, 1]], dtype=float)
    for suffix in ('.nii', '.nii.gz'):
        path = tmp_path / ('volume' + suffix)
        nib.save(nib.Nifti1Image(voxels, affine), path)
        for source in (str(path), path.read_bytes()):
            decoded = media_value(source, Nifti())
            np.testing.assert_array_equal(decoded.get_fdata(), voxels)
            np.testing.assert_allclose(decoded.affine, affine, rtol=1e-7, atol=0)
            np.testing.assert_allclose(decoded.header.get_zooms(), (2, 3, 4), rtol=1e-7, atol=0)
        assert_raw_media(path, Nifti)


@media_source_test
def test_mesh_formats_geometry_and_raw(tmp_path):
    import trimesh
    vertices = np.array([[0, 0, 0], [2, 0, 0], [0, 3, 0], [0, 0, 4]], dtype=float)
    faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    expected = mesh_triangles(mesh)
    for extension in ('glb', 'ply', 'stl'):
        path = tmp_path / ('geometry.' + extension)
        mesh.export(path, file_type=extension)
        for source in (str(path), {'path': 'embedded.' + extension, 'bytes': path.read_bytes()}):
            assert_mesh_geometry(mesh_triangles(media_value(source, Mesh())), expected)
        assert_raw_media(path, Mesh)


@media_source_test
def test_invalid_media_fails(tmp_path):
    # Keep positive baselines in this test so blanket rejection cannot pass.
    for check in (test_image_pixels_modes_and_raw, test_audio_sources_and_raw,
                  test_video_frames_streams_and_raw, test_pdf_pages_text_and_raw,
                  test_nifti_voxels_space_and_raw, test_mesh_formats_geometry_and_raw):
        check.__wrapped__(tmp_path)

    # Construction and lazy consumption share the exception capture.
    # A silent null must not become an observation-code exception.
    def consume(feature, source):
        value = media_value(source, feature())
        if value is None:
            return None
        if feature is Audio:
            return value.get_all_samples()
        if feature is Video:
            return value.get_frame_at(0)
        if feature is Pdf:
            return [page.extract_text() for page in value.pages]
        if feature is Nifti:
            return value.get_fdata()
        if feature is Mesh:
            return value
        return np.asarray(value)

    for feature, extension in ((Image, 'png'), (Audio, 'wav'), (Video, 'mkv'),
                               (Pdf, 'pdf'), (Nifti, 'nii'), (Mesh, 'ply')):
        for source in ({'path': None, 'bytes': None},
                       str(tmp_path / ('missing.' + extension)),
                       {'path': 'unreadable.' + extension, 'bytes': b'not a media file'}):
            assert_invalid(lambda: consume(feature, source), (Exception,))

    from F00_minimal_runtime import minimal_runtime_python
    minimal_runtime_python(r''' 
from itertools import permutations
import sys
from pathlib import Path
import numpy as np
from velnora import Dataset
from velnora.features import Features, Value, Image, Audio, Video, Pdf, Nifti, Mesh
root = Path(sys.argv[1])
control = Dataset.from_dict({'x': [17, -4]}, features=Features({'x': Value('int64')}))
assert list(control) == [{'x': 17}, {'x': -4}]

def triangles(value):
    parts = value.geometry.values() if hasattr(value, 'geometry') else [value]
    return np.asarray([face for part in parts for face in np.asarray(part.vertices)[np.asarray(part.faces)]])

def geometry_equal(actual, expected):
    assert actual.shape == expected.shape
    errors = np.full((len(actual), len(expected)), np.inf)
    for order in permutations(range(3)):
        errors = np.minimum(errors, np.abs(actual[:, None, list(order), :] - expected[None]).max(axis=(2, 3)))
    assigned = {}
    def augment(row, visited):
        for column in range(len(expected)):
            if errors[row, column] <= 1e-5 and column not in visited:
                visited.add(column)
                if column not in assigned or augment(assigned[column], visited):
                    assigned[column] = row
                    return True
        return False
    assert all(augment(row, set()) for row in range(len(actual))), errors

for feature, filename in [(Image, 'gray.png'), (Audio, 'signal.wav'), (Video, 'streams.mkv'),
                           (Pdf, 'pages.pdf'), (Nifti, 'volume.nii'), (Mesh, 'geometry.ply')]:
    path = root / filename
    encoded = Dataset.from_dict({'media': [{'path': str(path), 'bytes': None}]})
    raw = encoded.cast_column('media', feature(decode=False))
    assert raw[0]['media'] == {'path': str(path), 'bytes': None}
    # Include lazy consumption within the prerequisite observation, but keep
    # the independent success oracle outside it so assertion errors propagate.
    try:
        result = encoded.cast_column('media', feature())[0]['media']
        if feature is Audio:
            result = result.get_all_samples()
        elif feature is Video:
            result = result.get_frame_at(3)
        elif feature is Pdf:
            document = result
            result = [page.extract_text() for page in document.pages]
            document.close()
        elif feature is Nifti:
            result = (result.get_fdata(), result.affine, result.header.get_zooms())
        elif feature is Mesh:
            result = triangles(result)
        else:
            result = np.asarray(result)
    except ImportError:
        print(feature.__name__, 'prerequisite-unavailable')
        continue
    if feature is Image:
        np.testing.assert_array_equal(result, [[0, 47, 255], [120, 8, 201]])
    elif feature is Audio:
        import wave
        with wave.open(str(path), 'rb') as stream:
            expected = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').reshape(-1, 2).T / 32768
        assert result.sample_rate == 16000
        np.testing.assert_allclose(np.asarray(result.data), expected, atol=1e-4, rtol=0)
    elif feature is Video:
        expected = np.empty((3, 12, 16), dtype=np.uint8)
        expected[:] = np.asarray([125, 120, 85])[:, None, None]
        np.testing.assert_array_equal(np.asarray(result.data), expected)
        assert abs(result.pts_seconds - 0.6) < 1e-6
    elif feature is Pdf:
        assert [text.split() for text in result] == [text.split() for text in ['Cedar river', 'Quartz meadow']]
    elif feature is Nifti:
        np.testing.assert_array_equal(result[0], np.arange(24).reshape(2, 3, 4) - 9)
        np.testing.assert_allclose(result[1], [[2, 0, 0, 11], [0, 3, 0, -7], [0, 0, 4, 5], [0, 0, 0, 1]], rtol=1e-7, atol=0)
        np.testing.assert_allclose(result[2], (2, 3, 4), rtol=1e-7, atol=0)
    else:
        vertices = np.asarray([[0, 0, 0], [2, 0, 0], [0, 3, 0], [0, 0, 4]])
        expected = vertices[np.asarray([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])]
        geometry_equal(result, expected)
    print(feature.__name__, 'decoded-correctly')
''', args=(tmp_path,))
