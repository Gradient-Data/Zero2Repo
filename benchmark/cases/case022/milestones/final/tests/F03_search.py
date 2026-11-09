# feature: F03
"""Acceptance checks for public dataset search and attached index lifecycle."""
import importlib.util
import socket

import faiss
import numpy as np
from velnora import Dataset, load_from_disk
from velnora.arrow_dataset import DatasetTransformationNotAllowedError
from velnora.search import MissingIndex

from _helpers import observe
from F01_helpers import assert_invalid
from F03_helpers import assert_ranked_examples, assert_ranked_hits


def test_vector_metrics_and_sources():
    vectors = np.array([[0, 0], [2, 0], [0, 3], [-1, 1], [4, -2]], dtype='float32')
    query = np.array([1, 1], dtype='float32')
    # Independent arithmetic: squared distances and dot products for the input.
    distances = dict(enumerate([2, 2, 5, 4, 18]))
    products = dict(enumerate([0, 2, 3, 0, 2]))
    for external in (False, True):
        for inner_product in (False, True):
            columns = {'id': list(range(5)), 'text': ['ash', 'elm', 'fir', 'oak', 'yew']}
            if not external:
                columns['vector'] = vectors.tolist()
            dataset = Dataset.from_dict(columns)
            options = {'metric_type': faiss.METRIC_INNER_PRODUCT} if inner_product else {}
            if external:
                dataset.add_faiss_index_from_external_arrays(vectors, index_name='lookup', **options)
            else:
                dataset.add_faiss_index('vector', index_name='lookup', **options)
            expected = products if inner_product else distances
            found = dataset.search('lookup', query, k=5)
            assert_ranked_hits(found.scores, found.indices, expected, 5, largest=inner_product)
            nearest = dataset.get_nearest_examples('lookup', query, k=3)
            assert_ranked_examples(nearest, list(dataset), expected, 3, largest=inner_product)


def test_counts_and_query_batches():
    coordinates = [8, -3, 5, 0, 12, 1, -7, 4, 10, -1, 3, 9, 6]
    dataset = Dataset.from_dict({'id': list(range(len(coordinates))),
                                 'vector': [[x, 0] for x in coordinates]})
    dataset.add_faiss_index('vector')
    rows = list(dataset)
    queries = np.array([[2, 0], [-6, 0], [11, 0]], dtype='float32')
    # Direct Euclidean arithmetic, not a round-trip or another product query.
    expected = [{i: (x - int(q[0])) ** 2 for i, x in enumerate(coordinates)} for q in queries]
    for options, count in (({}, 10), ({'k': 4}, 4), ({'k': 20}, len(rows))):
        for query, oracle in zip(queries, expected):
            result = dataset.get_nearest_examples('vector', query, **options)
            assert_ranked_examples(result, rows, oracle, count)
        batch = dataset.get_nearest_examples_batch('vector', queries, **options)
        assert len(batch.total_scores) == len(batch.total_examples) == len(queries)
        for scores, examples, oracle in zip(batch.total_scores, batch.total_examples, expected):
            assert_ranked_hits(scores, examples['id'], oracle, count)
            assert examples == {column: [rows[i][column] for i in examples['id']] for column in rows[0]}
    # Low-level searches have no out-of-range padding in these requests.
    single = dataset.search('vector', queries[0])
    assert_ranked_hits(single.scores, single.indices, expected[0], 10)
    batch = dataset.search_batch('vector', queries)
    assert len(batch.total_scores) == len(batch.total_indices) == len(queries)
    for scores, indices, oracle in zip(batch.total_scores, batch.total_indices, expected):
        assert_ranked_hits(scores, indices, oracle, 10)


def test_index_lifecycle_and_validation(tmp_path):
    columns = {'id': [0, 1, 2, 3], 'vector': [[0, 0], [3, 0], [-2, 0], [7, 0]]}
    dataset = Dataset.from_dict(columns)
    query = np.array([1, 0], dtype='float32')
    expected = {0: 1, 1: 4, 2: 9, 3: 36}
    assert dataset.list_indexes() == []
    assert_invalid(lambda: dataset.search('absent', query), (MissingIndex,))
    dataset.add_faiss_index('vector', index_name='primary')
    dataset.add_faiss_index_from_external_arrays(np.array(columns['vector'], dtype='float32'), index_name='secondary')
    assert set(dataset.list_indexes()) == {'primary', 'secondary'}
    assert_ranked_examples(dataset.get_nearest_examples('primary', query, k=3), list(dataset), expected, 3)
    assert_invalid(lambda: dataset.search('primary', np.zeros(3, dtype='float32')),
                   (ValueError, AssertionError))
    path = tmp_path / 'saved.index'
    dataset.save_faiss_index('primary', str(path))
    dataset.drop_index('primary')
    assert dataset.list_indexes() == ['secondary']
    assert_invalid(lambda: dataset.get_nearest_examples('primary', query), (MissingIndex,))
    dataset.drop_index('secondary')
    assert dataset.list_indexes() == []
    # Reload into a fresh dataset; the original index cannot supply the answer.
    restored = Dataset.from_dict(columns)
    restored.load_faiss_index('restored', str(path))
    assert restored.list_indexes() == ['restored']
    assert_ranked_examples(restored.get_nearest_examples('restored', query, k=4), list(restored), expected, 4)
    for size in (3, 5):
        incompatible = Dataset.from_dict({'id': list(range(size))})
        assert_invalid(lambda: incompatible.load_faiss_index('wrong', str(path)), (ValueError,))


def test_attached_indexes_restrict_operations(tmp_path):
    dataset = Dataset.from_dict({'id': [5, 1, 8, 3, 6, 2], 'vector': [[x, 0] for x in range(6)]})
    original = list(dataset)
    dataset.add_faiss_index('vector')
    operations = [
        lambda: dataset.select([4, 1]),
        lambda: dataset.filter(lambda row: row['id'] > 4),
        lambda: dataset.sort('id'),
        lambda: dataset.shuffle(seed=31),
        lambda: dataset.train_test_split(test_size=2, seed=31),
        lambda: dataset.shard(num_shards=2, index=1),
    ]
    for operation in operations:
        assert_invalid(operation, (DatasetTransformationNotAllowedError,))
    assert_invalid(lambda: dataset.save_to_disk(str(tmp_path / 'blocked')), (ValueError,))
    dataset.drop_index('vector')
    assert list(dataset.select([4, 1])) == [original[4], original[1]]
    assert list(dataset.filter(lambda row: row['id'] > 4)) == [row for row in original if row['id'] > 4]
    assert list(dataset.sort('id')) == sorted(original, key=lambda row: row['id'])
    shuffled = list(dataset.shuffle(seed=31))
    assert sorted(shuffled, key=lambda row: row['id']) == sorted(original, key=lambda row: row['id'])
    split = dataset.train_test_split(test_size=2, seed=31)
    assert len(split['test']) == 2 and len(split['train']) == 4
    assert sorted(list(split['train']) + list(split['test']), key=lambda row: row['id']) == sorted(original, key=lambda row: row['id'])
    assert list(dataset.shard(num_shards=2, index=1)) == original[3:]
    saved = tmp_path / 'allowed'
    dataset.save_to_disk(str(saved))
    assert list(load_from_disk(str(saved))) == original


def test_unavailable_search_support():
    dataset = Dataset.from_dict({'id': [0, 1], 'text': ['cedar', 'marble'], 'vector': [[0, 0], [4, 0]]})
    dataset.add_faiss_index('vector')
    assert_ranked_examples(dataset.get_nearest_examples('vector', np.array([1, 0], dtype='float32'), k=1),
                           list(dataset), {0: 1, 1: 9}, 1)
    errors = (ImportError,)
    if importlib.util.find_spec('elasticsearch') is not None:
        from elasticsearch.exceptions import ConnectionError as ElasticsearchConnectionError
        errors += (ElasticsearchConnectionError,)
    # Reserve an unlistened port: no service can appear there during the call.
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]

        def text_search():
            dataset.add_elasticsearch_index('text', host='127.0.0.1', port=port)
            return dataset.get_nearest_examples('text', 'cedar', k=1)

        result = observe(text_search, timeout=30)
    if result.error is not None:
        assert isinstance(result.error, errors), repr(result.error)
    else:
        # An implementation with independent built-in support may still work.
        assert result.value.examples['id'] == [0]
        assert result.value.examples['text'] == ['cedar']
        assert len(result.value.scores) == 1
        assert np.isfinite(result.value.scores[0])


def test_elasticsearch_matching_and_reattachment():
    from _helpers import run_python
    from F03_helpers import local_elasticsearch

    # A fresh interpreter makes the real optional client available before the
    # product import, even when preceding features already imported the product.
    source = r'''
import sys
import uuid
import numpy as np
from elasticsearch import Elasticsearch
from velnora import Dataset

client = Elasticsearch([sys.argv[1]], timeout=60)
name = 'acceptance-' + uuid.uuid4().hex
columns = {
    'id': [17, 43, 28, 61, 90],
    'text': ['orchard apple harvest', 'basalt mountain ridge',
             'orchard pear harvest', 'copper wire circuit', 'orchard plum harvest'],
    'tag': ['fruit-a', 'stone', 'fruit-b', 'metal', 'fruit-c'],
}
originals = {key: {column: values[i] for column, values in columns.items()}
             for i, key in enumerate(columns['id'])}
dataset = Dataset.from_dict(columns)
try:
    dataset.add_elasticsearch_index('text', index_name='words',
                                    es_client=client, es_index_name=name)
    client.indices.refresh(index=name)
    restored = Dataset.from_dict(columns)
    restored.load_elasticsearch_index('reattached', es_index_name=name, es_client=client)
    for query, matching in [('orchard', {17, 28, 90}), ('basalt', {43})]:
        # Match membership comes from the independently supplied texts. No
        # service document IDs, field layout or scoring formula are prescribed.
        for current, index in [(dataset, 'words'), (restored, 'reattached')]:
            for count in (1, 2, 8):
                result = current.get_nearest_examples(index, query, k=count)
                keys = list(result.examples['id'])
                assert len(keys) == len(result.scores) == min(count, len(matching))
                assert len(set(keys)) == len(keys)
                assert set(keys) <= matching
                assert result.examples == {
                    column: [originals[key][column] for key in keys] for column in columns
                }
                assert all(np.isfinite(score) for score in result.scores)
finally:
    # This process owns exactly one index; unexpected cleanup failures surface.
    if client.indices.exists(index=name):
        client.indices.delete(index=name)
    client.close()
'''
    with local_elasticsearch() as (endpoint, environment):
        result = run_python(source, args=(endpoint,), env=environment, timeout=180)
        assert result.returncode == 0, result.stdout + '\n' + result.stderr
