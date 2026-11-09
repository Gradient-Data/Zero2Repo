# feature: F17
"""Semantic SQL checks against verified offline model assets and independent inference."""
import shutil
from F01_helpers import run_native_client
from F00_environment import numerical_dependencies, openssl_environment
from F17_helpers import (
    embedding_disabled_client, embedding_enabled_client, embedding_cache,
    run_embedding_case, embedding_model_reference, read_embedding_components,
)


def test_embedding_components_normalization_repeatability_and_model_space(
        embedding_enabled_client, embedding_cache, tmp_path, numerical_dependencies):
    texts = [
        "A mechanic repairs a bicycle wheel.",
        "The telescope records distant stars.",
        "Fresh apples grow in the orchard.",
        "A cyclist adjusts the brakes before a ride.",
        "Caf\u00e9 visitors read quietly beside the window.",
    ]
    inputs = tmp_path / "texts.txt"
    output = tmp_path / "components.jsonl"
    inputs.write_text("\n".join(texts) + "\n", encoding="utf-8")
    run_embedding_case(embedding_enabled_client, embedding_cache,
                       "components", inputs, output)
    actual = read_embedding_components(output, len(texts))
    expected, tolerance = embedding_model_reference(texts)
    for text, observed, reference in zip(texts, actual, expected):
        error = max(abs(value - float(truth))
                    for value, truth in zip(observed, reference))
        assert error <= tolerance, (text, error, tolerance)


def test_embedding_insert_and_query_rank_by_independent_vector_distances(
        embedding_enabled_client, embedding_cache):
    run_embedding_case(embedding_enabled_client, embedding_cache, "retrieval")


def test_embedding_numeric_text_null_and_offline_execution(
        embedding_enabled_client, embedding_cache):
    run_embedding_case(embedding_enabled_client, embedding_cache, "coercion")


def test_disabled_embedding_rejects_queries_and_insert(
        embedding_disabled_client, embedding_enabled_client, embedding_cache, tmp_path):
    run_native_client(embedding_disabled_client, "disabled")
    # A fresh process avoids reusing a previously initialized model.
    configurations = list(embedding_cache.glob("hub/*/snapshots/*/config.json"))
    assert len(configurations) == 1
    configuration = configurations[0]
    original = configuration.read_bytes()
    try:
        configuration.write_text("invalid model configuration")
        run_embedding_case(embedding_enabled_client, embedding_cache, "unavailable")
    finally:
        configuration.write_bytes(original)
