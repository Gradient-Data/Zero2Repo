# feature: F03
"""Acceptance checks for persistent configuration and repository access."""
import json
from pathlib import Path
import sys

from _helpers import make_environment, parse_json, read_toml, run_cli, snapshot_toml
from F01_helpers import project_cli, refused, succeeded, write_project
from F03_helpers import (
    certificate_material, configuration_call, configuration_environment,
    fetch_repository, isolated_keyring, keyring_snapshot, listed_settings, package_repository, publish_repository,
    query_setting, repository_tls, repository_wheel, save_setting, stored_value,
)


PROJECT = '[project]\nname = "config-project"\nversion = "1.0.0"\n'


def test_scoped_functional_settings_persist(tmp_path):
    env = configuration_environment(tmp_path / "state")
    project = write_project(tmp_path / "project", PROJECT)
    # Each member of the functional-setting catalogue is independently read back.
    settings = [
        ("cache-dir", str(tmp_path / "repository-cache"), str(tmp_path / "repository-cache")),
        ("data-dir", str(tmp_path / "managed-data"), str(tmp_path / "managed-data")),
        ("python.installation-dir", str(tmp_path / "interpreters"), str(tmp_path / "interpreters")),
        ("virtualenvs.path", str(tmp_path / "environments"), str(tmp_path / "environments")),
        ("virtualenvs.create", "false", False),
        ("virtualenvs.in-project", "true", True),
        ("virtualenvs.use-velnora-python", "true", True),
        ("virtualenvs.options.system-site-packages", "true", True),
        ("virtualenvs.options.no-pip", "true", True),
        ("installer.no-binary", "access-addon,build-addon", ["access-addon", "build-addon"]),
        ("installer.only-binary", "wheel-addon", ["wheel-addon"]),
        ("installer.build-config-settings.build-addon", '{"flavor":"optimized","flags":["one","two"]}',
         {"flavor": "optimized", "flags": ["one", "two"]}),
        ("solver.min-release-age", "9", 9),
        ("solver.min-release-age-exclude", "early-addon,local-addon", ["early-addon", "local-addon"]),
        ("solver.min-release-age-exclude-source", "internal,https://packages.example.org/simple/",
         ["internal", "https://packages.example.org/simple/"]),
        ("repositories.release.url", "https://publish.example.org/legacy/", "https://publish.example.org/legacy/"),
        ("keyring.enabled", "false", False),
    ]
    for local in (False, True):
        for key, argument, expected in settings:
            save_setting(project, env, key, argument, local=local)
        location = project / "velnora.toml" if local else Path(env["VELNORA_CONFIG_DIR"]) / "config.toml"
        document = read_toml(location)
        fields, _ = listed_settings(project, env)
        for key, _, expected in settings:
            persisted = stored_value(document, key)
            observed = query_setting(project, env, key, structured=not isinstance(expected, str))
            if isinstance(expected, list):
                # Package/source policies are membership sets, not ordered arguments.
                assert set(persisted) == set(expected), key
                assert set(observed) == set(expected), key
            else:
                assert persisted == expected, key
                assert observed == expected, key
            if isinstance(expected, dict):
                for member in expected:
                    assert key + "." + member in fields
            else:
                assert key in fields
                if not isinstance(expected, list):
                    assert parse_json(fields[key]) == expected, key
        for key, _, _ in settings:
            succeeded(configuration_call(project, env, *(('--local',) if local else ()), "--unset", key))
        document = read_toml(location)
        for key, _, _ in settings:
            parent = document
            for part in key.split(".")[:-1]:
                if part not in parent:
                    break
                parent = parent[part]
            else:
                assert key.split(".")[-1] not in parent, key


def test_effective_precedence_removal_and_project_isolation(tmp_path):
    env = configuration_environment(tmp_path / "state")
    first = write_project(tmp_path / "first", PROJECT)
    second = write_project(tmp_path / "second", PROJECT)
    default = query_setting(first, env, "virtualenvs.path")
    global_path = str(tmp_path / "global-environments")
    local_path = str(tmp_path / "local-environments")
    environment_path = str(tmp_path / "environment-environments")
    save_setting(first, env, "virtualenvs.in-project", "false")
    save_setting(first, env, "virtualenvs.path", global_path)
    save_setting(first, env, "virtualenvs.path", local_path, local=True)
    override = make_environment(env, updates={"VELNORA_VIRTUALENVS_PATH": environment_path})
    assert query_setting(first, override, "virtualenvs.path") == environment_path
    assert query_setting(first, env, "virtualenvs.path") == local_path
    assert query_setting(second, env, "virtualenvs.path") == global_path
    # Environment overrides apply to every setting, including a project-local Boolean.
    save_setting(first, env, "virtualenvs.in-project", "false", local=True)
    boolean_override = make_environment(env, updates={"VELNORA_VIRTUALENVS_IN_PROJECT": "true"})
    assert query_setting(first, boolean_override, "virtualenvs.in-project", structured=True) is True
    assert query_setting(first, env, "virtualenvs.in-project", structured=True) is False
    succeeded(configuration_call(first, env, "--local", "--unset", "virtualenvs.in-project"))
    # Ordinary environment creation must consume the same effective location.
    for path, active, expected in ((first, env, local_path), (first, override, environment_path), (second, env, global_path)):
        succeeded(project_cli(path, active, "env", "use", sys.executable))
        actual = succeeded(project_cli(path, active, "env", "info", "--path")).stdout.strip()
        assert Path(actual).parent == Path(expected)
        assert Path(actual).is_dir()
    succeeded(configuration_call(first, env, "--local", "--unset", "virtualenvs.path"))
    assert query_setting(first, env, "virtualenvs.path") == global_path
    assert query_setting(second, env, "virtualenvs.path") == global_path
    succeeded(configuration_call(first, env, "--unset", "virtualenvs.path"))
    assert query_setting(first, env, "virtualenvs.path") == default
    assert query_setting(second, env, "virtualenvs.path") == default
    assert query_setting(first, override, "virtualenvs.path") == environment_path


def test_configuration_validation_and_interactive_credentials(tmp_path):
    env = configuration_environment(tmp_path / "state")
    path = write_project(tmp_path / "project", PROJECT)
    save_setting(path, env, "keyring.enabled", "false")
    for spelling, value in (("true", True), ("false", False), ("1", True), ("0", False)):
        save_setting(path, env, "virtualenvs.create", spelling)
        assert query_setting(path, env, "virtualenvs.create", structured=True) is value
    for age in ("0", "17"):
        save_setting(path, env, "solver.min-release-age", age)
        assert query_setting(path, env, "solver.min-release-age", structured=True) == int(age)
    valid = {"mode": "", "options": ["--fast", "text with spaces"], "empty": []}
    save_setting(path, env, "installer.build-config-settings.build-addon", json.dumps(valid))
    assert query_setting(path, env, "installer.build-config-settings.build-addon", structured=True) == valid
    save_setting(path, env, "installer.build-config-settings.build-addon", '{"mode":"replacement"}')
    valid["mode"] = "replacement"
    assert query_setting(path, env, "installer.build-config-settings.build-addon", structured=True) == valid
    save_setting(path, env, "http-basic.private", "reader", "paired-password")
    save_setting(path, env, "pypi-token.release", "publishing-token")
    prompt_env = make_environment(env, remove=("VELNORA_NO_INTERACTION",))
    succeeded(configuration_call(path, prompt_env, "http-basic.prompted", "prompt-user", stdin="prompted-password\n"))
    auth = read_toml(Path(env["VELNORA_CONFIG_DIR"]) / "auth.toml")
    assert auth["http-basic"]["private"] == {"username": "reader", "password": "paired-password"}
    assert auth["http-basic"]["prompted"] == {"username": "prompt-user", "password": "prompted-password"}
    assert auth["pypi-token"]["release"] == "publishing-token"
    invalid = [
        ("unrecognized-setting", "value"),
        ("virtualenvs.create", "perhaps"),
        ("virtualenvs.create", "true", "false"),
        ("solver.min-release-age", "--", "-1"),
        ("solver.min-release-age", "1.5"),
        ("cache-dir", "/one", "/two"),
        ("data-dir", "/one", "/two"),
        ("python.installation-dir", "/one", "/two"),
        ("virtualenvs.path", "/one", "/two"),
        ("repositories.release", "https://one.example/", "https://two.example/"),
        ("http-basic.private", "one", "two", "three"),
        ("pypi-token.release", "one", "two"),
        ("--unset", "virtualenvs.create", "true"),
    ]
    invalid.extend(("installer.build-config-settings.build-addon", value) for value in (
        '{"mode":3}', '{"mode":true}', '{"mode":null}', '{"mode":{}}',
        '{"mode":["text",2]}', '["text"]', 'not-json'))
    stored = [Path(env["VELNORA_CONFIG_DIR"]) / "config.toml",
              Path(env["VELNORA_CONFIG_DIR"]) / "auth.toml", path / "velnora.toml"]
    before = snapshot_toml(stored)
    for arguments in invalid:
        refused(configuration_call(path, env, *arguments))
        # Preserve every stored value without grading TOML serialization.
        assert snapshot_toml(stored) == before, arguments
    # Refusal cannot masquerade as a successful replacement or secret deletion.
    assert query_setting(path, env, "virtualenvs.create", structured=True) is False
    assert query_setting(path, env, "solver.min-release-age", structured=True) == 17
    assert query_setting(path, env, "installer.build-config-settings.build-addon", structured=True) == valid
    assert read_toml(Path(env["VELNORA_CONFIG_DIR"]) / "auth.toml") == auth


def test_repository_passwords_tokens_and_environment_override(tmp_path):
    env = configuration_environment(tmp_path / "state")
    save_setting(tmp_path, env, "keyring.enabled", "false")
    package, wheel = repository_wheel(tmp_path, env)
    with package_repository(wheel) as repository:
        save_setting(package, env, "repositories.private", repository["url"] + "/legacy/")
        repository["credentials"] = ("reader", "first-password")
        save_setting(package, env, "http-basic.private", *repository["credentials"], local=True)
        fetch_repository(tmp_path / "initial", env, repository)
        # Project-local storage was requested, but credentials are stored globally.
        local_document = package / "velnora.toml"
        assert not local_document.exists() or b"first-password" not in local_document.read_bytes()
        assert read_toml(Path(env["VELNORA_CONFIG_DIR"]) / "auth.toml")["http-basic"]["private"] == {
            "username": "reader", "password": "first-password"}
        repository["credentials"] = ("replacement-reader", "replaced-password")
        save_setting(package, env, "http-basic.private", *repository["credentials"], local=True)
        fetch_repository(tmp_path / "replaced", env, repository)
        publish_repository(package, env, repository, wheel)
        # Credentials must not attach to an unrelated source on the same server.
        fetch_repository(tmp_path / "other-source", env, repository, name="other", accepted=False)
        override = make_environment(env, updates={
            "VELNORA_HTTP_BASIC_PRIVATE_USERNAME": "environment-reader",
            "VELNORA_HTTP_BASIC_PRIVATE_PASSWORD": "environment-password"})
        repository["credentials"] = ("environment-reader", "environment-password")
        fetch_repository(tmp_path / "override", override, repository)
        publish_repository(package, override, repository, wheel)
        fetch_repository(tmp_path / "stored-is-shadowed", env, repository, accepted=False)
        succeeded(configuration_call(package, env, "--unset", "http-basic.private"))
        repository["credentials"] = ("replacement-reader", "replaced-password")
        fetch_repository(tmp_path / "removed", env, repository, accepted=False)
        publish_repository(package, env, repository, wheel, accepted=False)
        for token in ("first-token", "replacement-token"):
            repository["credentials"] = ("__token__", token)
            save_setting(package, env, "pypi-token.private", token)
            publish_repository(package, env, repository, wheel)
        save_setting(package, env, "repositories.other", repository["url"] + "/legacy/")
        publish_repository(package, env, repository, wheel, name="other", accepted=False)
        token_env = make_environment(env, updates={"VELNORA_PYPI_TOKEN_PRIVATE": "environment-token"})
        repository["credentials"] = ("__token__", "environment-token")
        publish_repository(package, token_env, repository, wheel)
        publish_repository(package, env, repository, wheel, accepted=False)
        succeeded(configuration_call(package, env, "--unset", "pypi-token.private"))
        repository["credentials"] = ("__token__", "replacement-token")
        publish_repository(package, env, repository, wheel, accepted=False)
        assert any(not request["accepted"] for request in repository["requests"])
    auth = read_toml(Path(env["VELNORA_CONFIG_DIR"]) / "auth.toml")
    assert "private" not in auth.get("http-basic", {})
    assert "private" not in auth.get("pypi-token", {})


def test_repository_certificate_trust_and_client_authentication(tmp_path):
    env = configuration_environment(tmp_path / "state")
    save_setting(tmp_path, env, "keyring.enabled", "false")
    _, wheel = repository_wheel(tmp_path, env)
    material = certificate_material(tmp_path / "certificates", env)
    with package_repository(wheel, tls=repository_tls(material)) as repository:
        fetch_repository(tmp_path / "default-untrusted", env, repository, accepted=False)
        save_setting(wheel.parent.parent, env, "certificates.private.cert", str(material / "trusted.pem"), local=True)
        fetch_repository(tmp_path / "custom-ca", env, repository)
        save_setting(tmp_path, env, "certificates.private.cert", str(material / "other.pem"))
        fetch_repository(tmp_path / "wrong-ca", env, repository, accepted=False)
        save_setting(tmp_path, env, "certificates.private.cert", "false")
        fetch_repository(tmp_path / "verification-disabled", env, repository)
        fetch_repository(tmp_path / "other-repository", env, repository, name="other", accepted=False)
        repository["credentials"] = ("required-reader", "required-password")
        fetch_repository(tmp_path / "auth-denied-with-verification-disabled", env, repository, accepted=False)
        assert any(not request["accepted"] for request in repository["requests"])
    save_setting(tmp_path, env, "certificates.private.cert", str(material / "trusted.pem"))
    with package_repository(wheel, tls=repository_tls(material, client_required=True)) as repository:
        fetch_repository(tmp_path / "client-missing", env, repository, accepted=False)
        save_setting(tmp_path, env, "certificates.private.client-cert", str(material / "client-combined.pem"))
        fetch_repository(tmp_path / "client-present", env, repository)
        peers = [request["peer"] for request in repository["requests"] if request["accepted"]]
        assert peers and all(peer for peer in peers)
        expected = ((('commonName', 'client'),),)
        assert all(peer["subject"] == expected for peer in peers)
    auth_path = Path(env["VELNORA_CONFIG_DIR"]) / "auth.toml"
    assert read_toml(auth_path)["certificates"]["private"] == {
        "cert": str(material / "trusted.pem"), "client-cert": str(material / "client-combined.pem")}
    for key in ("certificates.private.cert", "certificates.private.client-cert"):
        succeeded(configuration_call(tmp_path, env, "--unset", key))
    assert not read_toml(auth_path).get("certificates", {}).get("private", {})


def test_general_listing_hides_live_repository_secrets(tmp_path):
    env = configuration_environment(tmp_path / "state")
    save_setting(tmp_path, env, "keyring.enabled", "false")
    package, wheel = repository_wheel(tmp_path, env)
    password, token = "secret-password-for-listing", "secret-token-for-listing"
    ordinary = str(tmp_path / "visible-cache-location")
    save_setting(package, env, "cache-dir", ordinary)
    with package_repository(wheel) as repository:
        save_setting(package, env, "repositories.private", repository["url"] + "/legacy/")
        save_setting(package, env, "http-basic.private", "listing-reader", password)
        repository["credentials"] = ("listing-reader", password)
        fetch_repository(tmp_path / "consumer", env, repository)
        save_setting(package, env, "pypi-token.private", token)
        repository["credentials"] = ("__token__", token)
        publish_repository(package, env, repository, wheel)
        fields, result = listed_settings(package, env)
        assert parse_json(fields["cache-dir"]) == ordinary
        assert parse_json(fields["repositories.private.url"]) == repository["url"] + "/legacy/"
        assert query_setting(package, env, "cache-dir") == ordinary
        for secret in (password, token):
            assert secret not in result.stdout
            assert secret not in result.stderr



def test_keyring_default_storage_retrieval_deletion_and_disabling(tmp_path):
    env = configuration_environment(tmp_path / "state")
    assert query_setting(tmp_path, env, "keyring.enabled", structured=True) is True
    with isolated_keyring(env) as active:
        initial = keyring_snapshot(tmp_path, active)
        package, wheel = repository_wheel(tmp_path, active)
        with package_repository(wheel) as repository:
            save_setting(package, active, "repositories.private", repository["url"] + "/legacy/")
            password, token = "keyring-reader-password", "keyring-publishing-token"
            save_setting(package, active, "http-basic.private", "keyring-reader", password)
            password_items = keyring_snapshot(tmp_path, active)
            created_passwords = {item for item in password_items.keys() - initial.keys()
                                 if password_items[item] == password}
            assert created_passwords, password_items
            repository["credentials"] = ("keyring-reader", password)
            fetch_repository(tmp_path / "from-keyring", active, repository)
            save_setting(package, active, "pypi-token.private", token)
            token_items = keyring_snapshot(tmp_path, active)
            created_tokens = {item for item in token_items.keys() - password_items.keys()
                              if token_items[item] == token}
            assert created_tokens, token_items
            repository["credentials"] = ("__token__", token)
            publish_repository(package, active, repository, wheel)

            succeeded(configuration_call(package, active, "--unset", "http-basic.private"))
            after_password_removal = keyring_snapshot(tmp_path, active)
            assert created_passwords.isdisjoint(after_password_removal)
            assert password not in after_password_removal.values()
            repository["credentials"] = ("keyring-reader", password)
            fetch_repository(tmp_path / "keyring-password-removed", active, repository, accepted=False)
            succeeded(configuration_call(package, active, "--unset", "pypi-token.private"))
            after_token_removal = keyring_snapshot(tmp_path, active)
            assert created_tokens.isdisjoint(after_token_removal)
            assert token not in after_token_removal.values()
            repository["credentials"] = ("__token__", token)
            publish_repository(package, active, repository, wheel, accepted=False)

            # Explicit disabling changes the actual storage destination while the
            # same real Secret Service remains available throughout both arms.
            save_setting(package, active, "keyring.enabled", "false")
            assert query_setting(package, active, "keyring.enabled", structured=True) is False
            before_configuration_storage = keyring_snapshot(tmp_path, active)
            configuration_password = "configuration-reader-password"
            configuration_token = "configuration-publishing-token"
            save_setting(package, active, "http-basic.private", "configuration-reader", configuration_password)
            save_setting(package, active, "pypi-token.private", configuration_token)
            auth_path = Path(active["VELNORA_CONFIG_DIR"]) / "auth.toml"
            auth = read_toml(auth_path)
            assert auth["http-basic"]["private"] == {
                "username": "configuration-reader", "password": configuration_password}
            assert auth["pypi-token"]["private"] == configuration_token
            assert keyring_snapshot(tmp_path, active) == before_configuration_storage
            repository["credentials"] = ("configuration-reader", configuration_password)
            fetch_repository(tmp_path / "from-configuration", active, repository)
            repository["credentials"] = ("__token__", configuration_token)
            publish_repository(package, active, repository, wheel)
            for setting in ("http-basic.private", "pypi-token.private"):
                succeeded(configuration_call(package, active, "--unset", setting))
            remaining = read_toml(auth_path)
            assert "private" not in remaining.get("http-basic", {})
            assert "private" not in remaining.get("pypi-token", {})
            assert keyring_snapshot(tmp_path, active) == before_configuration_storage
            repository["credentials"] = ("configuration-reader", configuration_password)
            fetch_repository(tmp_path / "configuration-password-removed", active, repository, accepted=False)
            repository["credentials"] = ("__token__", configuration_token)
            publish_repository(package, active, repository, wheel, accepted=False)
