# feature: F08
"""Acceptance tests for media directories, metadata, ZIP and TAR samples."""
import json
import zipfile

import numpy as np
from velnora import load_dataset
from velnora.features import Audio, Image, Mesh, Nifti, Pdf, Video
from velnora.exceptions import DatasetGenerationError

from F01_helpers import assert_invalid
from F07_helpers import audio_source, video_source, pdf_source
from F08_helpers import (collection_source_test, collection_image, collection_metadata,
                         load_collection, collection_bytes, collection_tar)


@collection_source_test
def test_media_directory_discovery(tmp_path):
    import nibabel as nib
    import trimesh

    sources = tmp_path / 'sources'
    sources.mkdir()
    images = [collection_image(sources, 'one.png', 'red'),
              collection_image(sources, 'two.bmp', 'blue')]
    audio, _, _ = audio_source(sources)
    video, _ = video_source(sources)
    pdf, _ = pdf_source(sources)
    volumes = []
    for suffix in ('.nii', '.nii.gz'):
        path = sources / ('volume' + suffix)
        nib.save(nib.Nifti1Image(np.arange(8, dtype=np.int16).reshape(2, 2, 2), np.eye(4)), path)
        volumes.append(path)
    meshes = []
    for extension in ('ply', 'stl'):
        path = sources / ('solid.' + extension)
        trimesh.creation.box().export(path)
        meshes.append(path)
    for column, feature, paths in (('image', Image, images), ('audio', Audio, [audio]),
                                    ('video', Video, [video]), ('pdf', Pdf, [pdf]),
                                    ('nifti', Nifti, volumes), ('mesh', Mesh, meshes)):
        root = tmp_path / column
        root.mkdir()
        expected = []
        for index, path in enumerate(paths):
            content = path.read_bytes()
            (root / (str(index) + ''.join(path.suffixes))).write_bytes(content)
            expected.append(content)
        (root / 'notes.txt').write_text('Not a media sample', encoding='utf-8')
        data = load_collection(root, column + 'folder')
        assert isinstance(data.features[column], feature)
        raw = data.cast_column(column, feature(decode=False))
        assert sorted(collection_bytes(row[column]) for row in raw) == sorted(expected)


@collection_source_test
def test_directory_labels_and_metadata_precedence(tmp_path):
    root = tmp_path / 'classified'
    first = collection_image(root, 'zebra/one.png', 'red')
    second = collection_image(root, 'ant/two.png', 'blue')
    expected = {first.read_bytes(): 'zebra', second.read_bytes(): 'ant'}
    for options in ({}, {'drop_labels': False}):
        data = load_collection(root, **options).cast_column('image', Image(decode=False))
        assert data.features['label'].names == ['ant', 'zebra']
        assert {collection_bytes(row['image']): data.features['label'].int2str(row['label'])
                for row in data} == expected
    omitted = load_collection(root, drop_labels=True).cast_column('image', Image(decode=False))
    assert set(omitted.column_names) == {'image'}
    assert {collection_bytes(row['image']) for row in omitted} == set(expected)
    for name, relatives in (('single', ['only/a.png', 'only/b.png']),
                            ('uneven', ['ant/a.png', 'deep/zebra/b.png'])):
        directory = tmp_path / name
        paths = [collection_image(directory, relative, color)
                 for relative, color in zip(relatives, ('red', 'blue'))]
        data = load_collection(directory).cast_column('image', Image(decode=False))
        assert set(data.column_names) == {'image'}
        assert {collection_bytes(row['image']) for row in data} == {p.read_bytes() for p in paths}
        retained = load_collection(directory, drop_labels=False).cast_column('image', Image(decode=False))
        assert set(retained.features['label'].names) == {p.parent.name for p in paths}
        assert {collection_bytes(row['image']): retained.features['label'].int2str(row['label'])
                for row in retained} == {p.read_bytes(): p.parent.name for p in paths}
    collection_metadata(root, 'jsonl', [{'file_name': 'ant/two.png', 'caption': 'chosen'},
                                         {'file_name': 'ant/two.png', 'caption': 'repeated'}])
    for options in ({}, {'drop_labels': False}):
        data = load_collection(root, **options).cast_column('image', Image(decode=False))
        assert set(data.column_names) == {'image', 'caption'}
        assert [(row['caption'], collection_bytes(row['image'])) for row in data] == [
            ('chosen', second.read_bytes()), ('repeated', second.read_bytes())]


@collection_source_test
def test_metadata_formats_and_media_references(tmp_path):
    for extension in ('csv', 'jsonl', 'parquet'):
        root = tmp_path / extension
        a = collection_image(root, 'assets/a.png', 'red').read_bytes()
        b = collection_image(root, 'assets/b.bmp', 'blue').read_bytes()
        rows = [{'file_name': 'assets/b.bmp', 'left_file_name': 'assets/a.png',
                 'right_file_name': 'assets/b.bmp', 'caption': 'second', 'score': 7},
                {'file_name': 'assets/a.png', 'left_file_name': 'assets/b.bmp',
                 'right_file_name': 'assets/a.png', 'caption': 'first', 'score': 3}]
        if extension != 'csv':
            rows[0].update(file_names=['assets/b.bmp', 'assets/a.png'], pair_file_names=['assets/a.png'])
            rows[1].update(file_names=['assets/a.png'], pair_file_names=['assets/b.bmp', 'assets/a.png'])
        collection_metadata(root, extension, rows)
        data = load_collection(root)
        for column in ('image', 'left', 'right'):
            assert isinstance(data.features[column], Image)
            data = data.cast_column(column, Image(decode=False))
        if extension != 'csv':
            from velnora.features import List
            for column in ('images', 'pair'):
                assert isinstance(data.features[column].feature, Image)
                data = data.cast_column(column, List(Image(decode=False)))
        actual = list(data)
        assert [(r['caption'], r['score']) for r in actual] == [('second', 7), ('first', 3)]
        assert [(collection_bytes(r['image']), collection_bytes(r['left']), collection_bytes(r['right']))
                for r in actual] == [(b, a, b), (a, b, a)]
        if extension != 'csv':
            assert [[collection_bytes(v) for v in r['images']] for r in actual] == [[b, a], [a]]
            assert [[collection_bytes(v) for v in r['pair']] for r in actual] == [[a], [b, a]]


@collection_source_test
def test_metadata_rejections(tmp_path):
    valid = tmp_path / 'valid'
    image = collection_image(valid, 'a.png', 'green')
    collection_metadata(valid, 'jsonl', [{'file_name': 'a.png', 'caption': 'works'}])
    data = load_collection(valid).cast_column('image', Image(decode=False))
    assert [(r['caption'], collection_bytes(r['image'])) for r in data] == [('works', image.read_bytes())]
    for name, row in (('missing', {'caption': 'unusable'}),
                       ('numeric', {'file_name': 12, 'caption': 'unusable'})):
        root = tmp_path / name
        collection_image(root, 'a.png', 'red')
        collection_metadata(root, 'jsonl', [row])
        assert_invalid(lambda: list(load_collection(root)), (ValueError,))
    compatible, expected = {}, {}
    for split, color, score in (('train', 'red', 1), ('test', 'blue', 2)):
        root = tmp_path / 'compatible' / split
        image = collection_image(root, 'a.png', color)
        metadata = collection_metadata(root, 'jsonl', [{'file_name': 'a.png', 'score': score}])
        compatible[split] = [str(image), str(metadata)]
        expected[split] = [(score, image.read_bytes())]
    loaded = load_dataset('imagefolder', data_files=compatible)
    assert set(loaded) == set(expected)
    for split, data in loaded.items():
        raw = data.cast_column('image', Image(decode=False))
        assert [(row['score'], collection_bytes(row['image'])) for row in raw] == expected[split]
    for name, extension, score in (('formats', 'csv', 2), ('types', 'jsonl', 'text')):
        files = {}
        for split, ext, value in (('train', 'jsonl', 1), ('test', extension, score)):
            root = tmp_path / name / split
            image = collection_image(root, 'a.png', 'blue')
            metadata = collection_metadata(root, ext, [{'file_name': 'a.png', 'score': value}])
            files[split] = [str(image), str(metadata)]
        assert_invalid(lambda: {k: list(v) for k, v in load_dataset('imagefolder', data_files=files).items()},
                       (ValueError,))


@collection_source_test
def test_zip_media_splits(tmp_path):
    from PIL import Image as PILImage
    files, expected = {}, {}
    convention = tmp_path / 'convention'
    convention.mkdir()
    for split, color in (('train', 'red'), ('test', 'blue')):
        root = tmp_path / ('source_' + split)
        image = collection_image(root, 'assets/item.png', color)
        metadata = collection_metadata(root, 'jsonl', [{'file_name': 'assets/item.png', 'caption': split}])
        archive = convention / (split + '.zip')
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.write(image, 'assets/item.png')
            stream.write(metadata, 'metadata.jsonl')
        files[split] = str(archive)
        with PILImage.open(image) as decoded:
            expected[split] = [(split, decoded.tobytes())]
    for data in (load_dataset('imagefolder', data_files=files), load_dataset(str(convention))):
        assert set(data) == set(expected)
        for split in expected:
            raw = data[split]
            assert [(row['caption'], row['image'].tobytes()) for row in raw] == expected[split]
    selected = load_dataset('imagefolder', data_files=files, split='test')
    assert [(row['caption'], row['image'].tobytes()) for row in selected] == expected['test']


@collection_source_test
def test_webdataset_components_and_duplicates(tmp_path):
    import trimesh
    sources = tmp_path / 'sources'
    sources.mkdir()
    image = collection_image(sources, 'a.png', 'purple')
    audio, _, _ = audio_source(sources)
    video, _ = video_source(sources)
    mesh = sources / 'solid.ply'
    trimesh.creation.box().export(mesh)
    media = {'png': (Image, image.read_bytes()), 'wav': (Audio, audio.read_bytes()),
             'mkv': (Video, video.read_bytes()), 'ply': (Mesh, mesh.read_bytes())}
    archives, expected = [], []
    for archive_index, identities in enumerate((['same', 'other', 'same'], ['last', 'same'])):
        entries = []
        for index, identity in enumerate(identities):
            caption = f'archive {archive_index} row {index} — text'
            annotation = {'index': index, 'archive': archive_index}
            entries.extend([(identity + '.txt', caption.encode()),
                            (identity + '.json', json.dumps(annotation).encode())])
            picture = collection_image(sources, f'sample{archive_index}_{index}.png',
                                       (40 + 80 * archive_index, 30 + 60 * index, 90))
            geometry = sources / f'sample{archive_index}_{index}.ply'
            trimesh.creation.box(extents=(index + 1, archive_index + 1, 2)).export(geometry)
            contents = {extension: content for extension, (_, content) in media.items()}
            contents.update(png=picture.read_bytes(), ply=geometry.read_bytes())
            entries.extend((identity + '.' + extension, content) for extension, content in contents.items())
            expected.append((caption, annotation, contents))
        archives.append(str(collection_tar(tmp_path / f'part{archive_index}.tar', entries)))
    for streaming in (False, True):
        data = load_dataset('webdataset', data_files={'train': archives}, split='train', streaming=streaming)
        for extension, (feature, _) in media.items():
            assert isinstance(data.features[extension], feature)
            data = data.cast_column(extension, feature(decode=False))
        rows = list(data)
        assert [(r['txt'], r['json']) for r in rows] == [(text, annotation) for text, annotation, _ in expected]
        for row, (_, _, contents) in zip(rows, expected):
            for extension, content in contents.items():
                assert collection_bytes(row[extension]) == content
        duplicate = collection_tar(tmp_path / f'duplicate{streaming}.tar',
                                   [('item.txt', b'first'), ('item.txt', b'second')])
        assert_invalid(lambda: list(load_dataset('webdataset', data_files=str(duplicate),
                                                 split='train', streaming=streaming)),
                       (ValueError, DatasetGenerationError))
