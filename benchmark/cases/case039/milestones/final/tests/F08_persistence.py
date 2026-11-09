# feature: F08
"""Eight planned persistence checks, each through an independent native client."""
import os
import shutil

from _helpers import isolated_directory
from F08_helpers import (persistence_client, persistence_run, persistence_process,
                         persistence_limit)


def test_committed_state_survives_reopen(persistence_client, tmp_path):
    path = tmp_path / "database"
    persistence_run(persistence_client, "persist_create", path)
    for phase in ("persist_read", "persist_again"):
        persistence_run(persistence_client, phase, path)


def test_acknowledged_commits_survive_abrupt_termination(persistence_client, tmp_path):
    path = tmp_path / "database"
    with persistence_process(persistence_client, "crash_writer", path) as child:
        child.wait_for("ready_to_kill")
        child.crash()
    persistence_run(persistence_client, "committed_read", path)


def test_checkpoint_recovers_all_synchronization_modes(persistence_client, tmp_path):
    # These are the three published choices, not a Cartesian parameter expansion.
    for mode in ("none", "normal", "full"):
        path = tmp_path / mode
        with persistence_process(persistence_client, "checkpoint_writer", path, mode) as child:
            child.wait_for("ready_to_kill")
            child.crash()
        persistence_run(persistence_client, "committed_read", path, mode)


def test_earlier_checkpoint_rows_and_schema_evolution(persistence_client, tmp_path):
    path = tmp_path / "database"
    for phase in ("schema_create", "schema_read", "schema_again"):
        persistence_run(persistence_client, phase, path)


def test_backup_committed_state_latest_restore_and_missing_selection(persistence_client, tmp_path):
    # Both selected and latest recovery use the documented backup identities.
    path = tmp_path / "database"
    for phase in ("backup_create", "backup_read"):
        persistence_run(persistence_client, phase, path)


def test_exclusive_process_access_and_release(persistence_client, tmp_path):
    path = tmp_path / "database"
    with persistence_process(persistence_client, "lock_owner", path) as owner:
        owner.wait_for("owns_database")
        persistence_run(persistence_client, "open_rejected", path)
        owner.proceed()
        owner.wait_for("done")
        owner.finish()
    persistence_run(persistence_client, "plain_read", path)


def test_unreadable_storage_fails_visibly(persistence_client):
    # Always use a real unprivileged caller; root cannot establish a mode-bit fault.
    with isolated_directory(parent="/tmp", prefix="f08-permissions-") as directory:
        directory.chmod(0o777)
        binary = directory / "client"
        shutil.copy2(persistence_client, binary)
        binary.chmod(0o755)
        path = directory / "database"
        persistence_run(binary, "plain_create", path, demote=True)
        persistence_run(binary, "plain_read", path, demote=True)
        saved_mode = path.stat().st_mode & 0o777
        try:
            path.chmod(0)
            persistence_run(binary, "unreadable_directory", path, demote=True)
        finally:
            path.chmod(saved_mode)
        persistence_run(binary, "plain_read", path, demote=True)

        # Save one closed, verified database. Every directory fault starts from this
        # same state and location, independent of any earlier recovery attempt.
        owner = (path.stat().st_uid, path.stat().st_gid)
        saved = directory / "healthy-storage"
        shutil.copytree(path, saved)
        directories = [entry.relative_to(saved) for entry in saved.rglob("*")
                       if entry.is_dir()]

        def restore_storage():
            shutil.rmtree(path)
            shutil.copytree(saved, path)
            if os.geteuid() == 0:
                # The native client may run as an unprivileged uid while the
                # coordinating pytest process is root. Preserve its ownership.
                for entry in [path, *path.rglob("*")]:
                    os.chown(entry, *owner)

        for relative in directories:
            restore_storage()
            fault_directory = path / relative
            directory_mode = fault_directory.stat().st_mode & 0o777
            fault_directory.chmod(0)
            try:
                persistence_run(binary, "unreadable_subdirectory", path, demote=True,
                                fault_path=fault_directory)
            finally:
                fault_directory.chmod(directory_mode)
                restore_storage()
            persistence_run(binary, "plain_read", path, demote=True)


def test_durable_write_failure_poisoning_requires_reopen(persistence_client, tmp_path):
    path = tmp_path / "database"
    with persistence_process(persistence_client, "io_writer", path) as child:
        child.wait_for("limit_ready")
        previous = persistence_limit(child, 0)
        child.proceed()
        child.wait_for("fault_observed")
        persistence_limit(child, previous)
        child.proceed()
        child.wait_for("done")
        child.finish()
    persistence_run(persistence_client, "io_reopen", path)
