# feature: F14
"""Five planned acceptance checks for secondary indexes and their consistency."""
from _helpers import run_command
from F01_helpers import run_native_client
from F14_helpers import index_client


def test_index_lifecycle_metadata_and_invalid_creation(index_client):
    run_native_client(index_client, "lifecycle")


def test_unique_existing_future_composite_null_and_drop(index_client, tmp_path):
    result = run_command([index_client, "uniqueness", tmp_path / "unique-database"],
                         cwd=index_client.parent, timeout=120)
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_indexed_predicates_mutations_visibility_and_checkpoint(index_client, tmp_path):
    for isolation in ("committed", "snapshot"):
        result = run_command([index_client, isolation, tmp_path / isolation],
                             cwd=index_client.parent, timeout=120)
        assert result.returncode == 0, (isolation, result.stdout, result.stderr)


def test_index_backup_reopen_and_renamed_column_association(index_client, tmp_path):
    path = tmp_path / "database"
    for phase in ("save", "reopen"):
        result = run_command([index_client, phase, path], cwd=index_client.parent, timeout=120)
        assert result.returncode == 0, (phase, result.stdout, result.stderr)


def test_incompatible_indexed_type_and_missing_drop_preserve_state(index_client):
    run_native_client(index_client, "schema_errors")
