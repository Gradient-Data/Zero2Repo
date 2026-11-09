# feature: F18
"""Acceptance checks through the publication command and actual repositories."""
from F00_documents import legacy_document
import shutil
import re

from packaging.version import Version
from packaging.utils import canonicalize_name
from _helpers import make_environment

from F01_helpers import refused, succeeded
from F03_helpers import (certificate_material, configuration_call,
    configuration_environment, package_repository, repository_tls, save_setting)
from F10_helpers import build_archives, build_project
from F18_helpers import (distribution_identity, publication_store, publish_call,
    publishing_target, received_artifacts, versioned_artifacts)


def test_highest_artifact_version_for_current_name(tmp_path):
    env = configuration_environment(tmp_path / "state")
    project = build_project(tmp_path / "project")
    artifacts = []
    for version in ("1.9", "1.10rc1", "1.10"):
        artifacts.extend(versioned_artifacts(tmp_path / ("v-" + version), env,
                                            project / "dist", version))
    artifacts.extend(versioned_artifacts(tmp_path / "foreign", env,
        project / "dist", "99.0", name="foreign-subject"))
    identities = {path: distribution_identity(path) for path in artifacts}
    latest = max(version for name, version in identities.values()
                 if name == "build-subject")
    expected = [path for path, (name, version) in identities.items()
                if name == "build-subject" and version == latest]
    assert len(expected) == 2
    with package_repository(expected[0]) as repository:
        publishing_target(project, env, repository)
        succeeded(publish_call(project, env, "--repository", "private"))
        received_artifacts(repository, expected)


def test_destinations_and_selected_distribution_directory(tmp_path):
    env = configuration_environment(tmp_path / "state")
    project = build_project(tmp_path / "project")
    artifacts = build_archives(project, env, "--output", "release-files",
                               output=project / "release-files")
    # Route the real default HTTPS destination to an isolated recording proxy.
    material = certificate_material(tmp_path / 'default-certificates', env,
                                    server_names=('upload.pypi.org',))
    with package_repository(artifacts['wheel'], tls=repository_tls(material),
                            proxy_host='upload.pypi.org') as repository:
        proxied = make_environment(env, updates={'HTTPS_PROXY': repository['url'],
            'REQUESTS_CA_BUNDLE': str(material / 'trusted.pem')})
        succeeded(publish_call(project, proxied, '--dist-dir', 'release-files'))
        received_artifacts(repository, artifacts.values())
        assert set(repository['tunnels']) == {'upload.pypi.org:443'}
        assert {request['path'] for request in repository['requests']} == {'/legacy/'}
    with package_repository(artifacts["wheel"]) as repository:
        # An explicit publication destination overrides a same-name dependency source.
        document = project / "pyproject.toml"
        document.write_text(legacy_document(document.read_text() + '\n[[tool.<legacy>.source]]\n'
            'name = "private"\nurl = "' + repository["url"] + '/simple/"\npriority = "primary"\n'))
        refused(publish_call(project, env, "--repository", "unknown", "--dist-dir", "release-files"))
        assert repository["uploads"] == []
        # The baseline deliberately reuses a source if no explicit destination exists.
        succeeded(publish_call(project, env, "--repository", "private", "--dist-dir", "release-files"))
        received_artifacts(repository, artifacts.values())
        assert {request["path"] for request in repository["requests"]} == {"/simple/"}
        with package_repository(artifacts["wheel"]) as destination:
            publishing_target(project, env, destination)
            refused(publish_call(project, env, "--repository", "private"))
            assert destination["uploads"] == []
            succeeded(publish_call(project, env, "--repository", "private", "--dist-dir", "release-files"))
            received_artifacts(destination, artifacts.values())
            assert {request["path"] for request in destination["requests"]} == {"/legacy/"}
            received_artifacts(repository, artifacts.values())


def test_build_before_publish_and_preview_without_upload(tmp_path):
    env = configuration_environment(tmp_path / "state")
    seed = build_project(tmp_path / "seed", header='[project]\nname = "build-subject"\n'
        'version = "9.0"\nrequires-python = ">=3.9,<4"\n')
    wheel = build_archives(seed, env)["wheel"]
    # Live and preview start with identical project contents and no artifacts.
    for mode in ("live", "preview", "broken"):
        project = build_project(tmp_path / mode)
        if mode == "broken":
            # A build failure must block even otherwise publishable old artifacts.
            shutil.copytree(seed / "dist", project / "dist")
            shutil.rmtree(project / "build_subject")
        with package_repository(wheel) as repository:
            publishing_target(project, env, repository)
            options = ("--dry-run",) if mode == "preview" else ()
            result = publish_call(project, env, "--repository", "private", "--build", *options)
            if mode == "broken":
                refused(result)
                assert repository["uploads"] == []
            else:
                succeeded(result)
                artifacts = list((project / "dist").iterdir())
                assert {artifact.suffix for artifact in artifacts} == {".whl", ".gz"}
                assert all(distribution_identity(artifact) == ("build-subject", Version("2.3.1"))
                           for artifact in artifacts)
                if mode == "live":
                    received_artifacts(repository, artifacts)
                else:
                    preparation = [match for line in result.stdout.splitlines()
                                   if (match := re.fullmatch(r"Publishing (\S+) \(([^)]+)\) to (.+)", line))]
                    assert len(preparation) == 1, result.stdout
                    record, = preparation
                    assert canonicalize_name(record[1]) == "build-subject"
                    assert Version(record[2]) == Version("2.3.1")
                    assert record[3] == "private"
                    for artifact in artifacts:
                        assert "Uploading " + artifact.name in result.stderr
                    assert repository["uploads"] == []


def test_credentials_certificates_and_publication_failures(tmp_path):
    env = configuration_environment(tmp_path / "state")
    project = build_project(tmp_path / "project")
    artifacts = build_archives(project, env)
    wheel = artifacts["wheel"]
    with package_repository(wheel) as repository:
        publishing_target(project, env, repository)
        save_setting(project, env, "http-basic.private", "configured", "password")
        save_setting(project, env, "pypi-token.private", "repository-token")
        repository["credentials"] = ("explicit", "explicit-password")
        succeeded(publish_call(project, env, "--repository", "private", "--username", "explicit",
                               "--password", "explicit-password"))
        received_artifacts(repository, artifacts.values())
        repository["uploads"].clear()
        repository["credentials"] = ("__token__", "repository-token")
        succeeded(publish_call(project, env, "--repository", "private", "--username", "incomplete"))
        received_artifacts(repository, artifacts.values())
        repository["uploads"].clear()
        succeeded(configuration_call(project, env, "--unset", "pypi-token.private"))
        repository["credentials"] = ("configured", "password")
        succeeded(publish_call(project, env, "--repository", "private"))
        received_artifacts(repository, artifacts.values())
        repository["uploads"].clear()
        repository["credentials"] = ("different", "credentials")
        refused(publish_call(project, env, "--repository", "private"))
        assert repository["uploads"] == []
        assert repository["requests"][-1]["accepted"] is False
    # The now-closed loopback listener produces a real connection refusal.
    refused(publish_call(project, env, "--repository", "private"))
    material = certificate_material(tmp_path / "certificates", env)
    (material / "server-combined.pem").write_bytes(
        (material / "server.pem").read_bytes() + (material / "server.key").read_bytes())
    save_setting(project, env, "certificates.private.cert", str(material / "other.pem"))
    save_setting(project, env, "certificates.private.client-cert", str(material / "server-combined.pem"))
    with package_repository(wheel, tls=repository_tls(material, client_required=True)) as repository:
        publishing_target(project, env, repository)
        # Both certificate overrides must reach the actual TLS handshake.
        succeeded(publish_call(project, env, "--repository", "private", "--cert",
            str(material / "trusted.pem"), "--client-cert", str(material / "client-combined.pem")))
        received_artifacts(repository, artifacts.values())
        assert all(request["peer"] for request in repository["requests"])
        repository["uploads"].clear()
        refused(publish_call(project, env, "--repository", "private"))
        assert repository["uploads"] == []
        # Prove the configured materials also work, then isolate each override.
        save_setting(project, env, "certificates.private.cert", str(material / "trusted.pem"))
        save_setting(project, env, "certificates.private.client-cert", str(material / "client-combined.pem"))
        succeeded(publish_call(project, env, "--repository", "private"))
        received_artifacts(repository, artifacts.values())
        repository["uploads"].clear()
        refused(publish_call(project, env, "--repository", "private", "--cert", str(material / "other.pem")))
        assert repository["uploads"] == []
        refused(publish_call(project, env, "--repository", "private", "--client-cert", str(material / "server-combined.pem")))
        assert repository["uploads"] == []


def test_skip_existing_continues_but_does_not_hide_other_failures(tmp_path):
    env = configuration_environment(tmp_path / "state")
    project = build_project(tmp_path / "project")
    artifacts = list(build_archives(project, env).values())
    expected = {artifact.name: artifact.read_bytes() for artifact in artifacts}
    with publication_store(tmp_path / "baseline") as repository:
        publishing_target(project, env, repository)
        succeeded(publish_call(project, env, "--repository", "private"))
        assert {path.name: path.read_bytes() for path in (tmp_path / "baseline").iterdir()} == expected
        # Use the observed first upload; the feature does not specify ordering.
        first = repository["attempts"][0][1]
    for mode in ("ordinary", "skip"):
        storage = tmp_path / mode
        with publication_store(storage) as repository:
            (storage / first).write_bytes(expected[first])
            publishing_target(project, env, repository)
            options = ("--skip-existing",) if mode == "skip" else ()
            result = publish_call(project, env, "--repository", "private", *options)
            if mode == "ordinary":
                refused(result)
                assert (storage / first).read_bytes() == expected[first]
            else:
                succeeded(result)
                assert {path.name: path.read_bytes() for path in storage.iterdir()} == expected
                assert {name for _, name in repository["attempts"]} == set(expected)
    with publication_store(tmp_path / "readonly") as repository:
        publishing_target(project, env, repository, endpoint="/readonly/")
        refused(publish_call(project, env, "--repository", "private", "--skip-existing"))
        assert repository["attempts"]
        assert list((tmp_path / "readonly").iterdir()) == []
