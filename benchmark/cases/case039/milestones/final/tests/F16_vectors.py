# feature: F16
"""Vector acceptance checks through native SQL and the complete public recall corpus."""
from _helpers import run_command
from F01_helpers import run_native_client
from F00_environment import numerical_dependencies
from F16_helpers import vector_client, fashion_inputs, measure_fashion_recall


def test_vector_storage_components_properties_and_text(vector_client):
    run_native_client(vector_client, "storage")


def test_vector_distances_and_magnitudes_within_error_bound(vector_client):
    run_native_client(vector_client, "metrics")


def test_exact_nearest_filter_limit_ties_and_missing_order(vector_client):
    run_native_client(vector_client, "exact")


def test_index_candidates_distances_filters_and_requested_metric(vector_client):
    run_native_client(vector_client, "indexed")


def test_full_fashion_mnist_recall_with_predeclared_configuration(vector_client, tmp_path, numerical_dependencies):
    train, queries, options = fashion_inputs(tmp_path)
    report = measure_fashion_recall(vector_client, tmp_path, train, queries, options)
    print(report)


def test_vector_index_persistence_mutation_and_snapshot(vector_client, tmp_path):
    path = tmp_path / "database"
    for phase in ("seed", "index", "change", "reopen"):
        result = run_command([vector_client, phase, path], cwd=vector_client.parent, timeout=120)
        assert result.returncode == 0, (phase, result.stdout, result.stderr)


def test_vector_invalid_dimensions_text_schema_and_index_preserve_data(vector_client):
    run_native_client(vector_client, "errors")
