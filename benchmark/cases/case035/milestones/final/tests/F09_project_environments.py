# feature: F09
"""Acceptance checks of environment selection, isolation, management and activation."""
from pathlib import Path
import shlex
import sys

from _helpers import make_environment, parse_json, run_cli
from F01_helpers import project_cli, refused, succeeded
from F03_helpers import repository_wheel, save_setting
from F08_helpers import install_release, python_rows, standalone_proxy, standalone_releases
from F09_helpers import (
    ENVIRONMENT_PROBE, direct_observation, environment_listing, environment_project,
    environment_report, environment_settings, external_environment, project_observation,
    reported_environment, with_external,
)


def test_default_reuse_compatibility_and_project_isolation(tmp_path):
    env, storage = environment_settings(tmp_path)
    a = environment_project(tmp_path / "first")
    b = environment_project(tmp_path / "second")
    external = external_environment(tmp_path / "external", env)
    active = with_external(env, external)
    # Pre-populate the real external environment with an independently built package.
    _, wheel = repository_wheel(tmp_path, env)
    succeeded(run_cli((sys.executable,), ("-m", "pip", "--python",
        str(external / "bin/python"), "install", "--no-index", "--no-deps", str(wheel)),
        cwd=a, env=env))
    succeeded(project_cli(a, active, "install"))
    assert Path(project_observation(a, active)["prefix"]) == external
    assert reported_environment(a, active) == external
    assert project_observation(a, active)["packages"]["access-addon"] == "1.2.3"
    imported = succeeded(project_cli(a, active, "run", "python", "-c",
        "import access_addon; print(access_addon.value())"))
    assert imported.stdout.strip() == "downloaded repository contents"
    # The same real external interpreter is excluded only when it is Conda base.
    conda = make_environment(env, updates={"CONDA_PREFIX": str(external),
        "CONDA_DEFAULT_ENV": "project-session"})
    assert Path(project_observation(a, conda)["prefix"]) == external
    conda = make_environment(conda, updates={"CONDA_DEFAULT_ENV": "base"})
    succeeded(project_cli(a, conda, "install"))
    own = reported_environment(a, conda)
    assert own != external and own.is_relative_to(storage)
    assert Path(project_observation(a, conda)["prefix"]) == own
    assert reported_environment(a, env) == own
    first_python = succeeded(project_cli(a, env, "env", "info", "--executable")).stdout.strip()
    assert Path(direct_observation(first_python, a, env)["prefix"]) == own
    succeeded(project_cli(b, env, "install"))
    other = reported_environment(b, env)
    assert other != own and other.is_relative_to(storage)
    assert Path(project_observation(b, env)["prefix"]) == other
    incompatible = environment_project(tmp_path / "incompatible", ">=99")
    refused(project_cli(incompatible, active, "install"), ">=99")
    assert direct_observation(external / "bin/python", a, env)["version"] == direct_observation(sys.executable, a, env)["version"]


def test_interpreter_selection_auto_search_and_no_implicit_download(tmp_path):
    env, storage = environment_settings(tmp_path)
    releases = standalone_releases()
    with standalone_proxy(tmp_path / "proxy", env, releases) as (env, state):
        alternate = install_release(tmp_path, env, releases[0])
        assert state["requests"], "Explicit installation must demonstrate a reachable release service"
        project = environment_project(tmp_path / "selected")
        succeeded(project_cli(project, env, "env", "use", str(alternate)))
        assert project_observation(project, env)["version"] == releases[0]["version"]
        selected = reported_environment(project, env)
        succeeded(project_cli(project, env, "env", "use", "system"))
        assert project_observation(project, env)["version"] == direct_observation(sys.executable, project, env)["version"]
        assert reported_environment(project, env) != selected
        refused(project_cli(project, env, "env", "use", str(tmp_path / "missing-python")), "missing-python")
        restricted = environment_project(tmp_path / "restricted", ">=3.12,<3.13")
        refused(project_cli(restricted, env, "env", "use", sys.executable), ">=3.12,<3.13")
        succeeded(project_cli(restricted, env, "install"))
        assert project_observation(restricted, env)["version"].startswith("3.12.")
        # Remove the proven reachable release. Its archive remains served unchanged.
        succeeded(project_cli(tmp_path, env, "python", "remove", releases[0]["version"]))
        before = python_rows(tmp_path, env, "--managed")
        downloads = (list(state["requests"]), list(state["redirects"]))
        impossible = environment_project(tmp_path / "not-installed", "==3.12.8")
        refused(project_cli(impossible, env, "install"), "3.12.8")
        # No interpreter distribution was fetched, by exact or by equivalent address.
        assert (state["requests"], state["redirects"]) == downloads
        assert python_rows(tmp_path, env, "--managed") == before


def test_interpreter_preferences_and_environment_locations(tmp_path):
    env, storage = environment_settings(tmp_path)
    releases = standalone_releases()
    with standalone_proxy(tmp_path / "proxy", env, releases) as (env, state):
        alternate = install_release(tmp_path, env, releases[0])
        # PATH supplies the active interpreter without selecting an external venv.
        active = make_environment(env, updates={"PATH": str(alternate.parent) + ":" + env["PATH"]})
        # None leaves the preference unset, so it observes the default choice.
        for product_python in (None, False, True):
            if product_python is not None:
                save_setting(tmp_path, active, "virtualenvs.use-velnora-python", str(product_python).lower())
            project = environment_project(tmp_path / {None: "default", False: "active", True: "product"}[product_python])
            succeeded(project_cli(project, active, "install"))
            expected = direct_observation(env['F01_PRODUCT_PYTHON'] if product_python else alternate, project, active)
            actual = project_observation(project, active)
            assert actual["version"] == expected["version"]
            assert actual["implementation"] == expected["implementation"]
            assert reported_environment(project, active).is_relative_to(storage)
    local = environment_project(tmp_path / "local")
    save_setting(local, env, "virtualenvs.in-project", "true", local=True)
    succeeded(project_cli(local, env, "install"))
    assert reported_environment(local, env) == local / ".venv"
    assert Path(project_observation(local, env)["prefix"]) == local / ".venv"
    save_setting(local, env, "virtualenvs.in-project", "--unset", local=True)
    assert reported_environment(local, env) == local / ".venv"
    save_setting(local, env, "virtualenvs.in-project", "false", local=True)
    succeeded(project_cli(local, env, "install"))
    shared = reported_environment(local, env)
    assert shared.is_relative_to(storage) and shared != local / ".venv"
    assert Path(project_observation(local, env)["prefix"]) == shared


def test_disabled_creation_selection_precedence(tmp_path):
    env, storage = environment_settings(tmp_path)
    project = environment_project(tmp_path / "project")
    save_setting(project, env, "virtualenvs.in-project", "true", local=True)
    succeeded(project_cli(project, env, "env", "use", sys.executable))
    local = reported_environment(project, env)
    external = external_environment(tmp_path / "external", env)
    active = with_external(env, external)
    override = environment_project(tmp_path / "explicit-selection")
    succeeded(project_cli(override, env, "env", "use", sys.executable))
    save_setting(project, env, "virtualenvs.create", "false")
    assert Path(project_observation(project, active)["prefix"]) == external
    assert Path(project_observation(project, env)["prefix"]) == local
    save_setting(project, env, "virtualenvs.in-project", "false", local=True)
    system = direct_observation(sys.executable, project, env)
    assert project_observation(project, env)["prefix"] == system["prefix"]
    overridden = project_observation(override, active)
    assert Path(overridden["prefix"]) != external
    assert overridden["version"] == system["version"]
    assert not storage.exists() or environment_listing(project, env) == {}
    incompatible = environment_project(tmp_path / "incompatible", ">=99")
    refused(project_cli(incompatible, active, "install"), ">=99")
    refused(project_cli(incompatible, env, "install"), ">=99")


def test_package_visibility_and_omitted_installer(tmp_path):
    env, storage = environment_settings(tmp_path)
    system = direct_observation(sys.executable, tmp_path, env)
    assert system["packaging_importable"] and "packaging" in system["packages"]
    # The first arm leaves both settings unset, so it observes the defaults.
    for expose, omit, explicit in ((False, False, False), (False, False, True), (True, False, True), (False, True, True)):
        project = environment_project(tmp_path / f"visibility-{expose}-{omit}-{explicit}")
        if explicit:
            save_setting(project, env, "virtualenvs.options.system-site-packages", str(expose).lower(), local=True)
            save_setting(project, env, "virtualenvs.options.no-pip", str(omit).lower(), local=True)
        succeeded(project_cli(project, env, "install"))
        actual = project_observation(project, env)
        assert actual["packaging_importable"] == expose
        assert ("packaging" in actual["packages"]) == expose
        if expose:
            imported = succeeded(project_cli(project, env, "run", "python", "-c",
                'import packaging; print(packaging.__version__)')).stdout.strip()
            assert imported == system["packages"]["packaging"]
        assert ("pip" in actual["packages"]) == (not omit)
        assert Path(actual["prefix"]) == reported_environment(project, env)


def test_inspection_listing_removal_and_project_ownership(tmp_path):
    env, storage = environment_settings(tmp_path)
    releases = standalone_releases()
    with standalone_proxy(tmp_path / "proxy", env, releases) as (env, state):
        alternate = install_release(tmp_path, env, releases[0])
        project = environment_project(tmp_path / "project")
        other = environment_project(tmp_path / "other")
        succeeded(project_cli(project, env, "env", "use", sys.executable))
        first = reported_environment(project, env)
        succeeded(project_cli(project, env, "env", "use", str(alternate)))
        second = reported_environment(project, env)
        actual = project_observation(project, env)
        info = environment_report(project, env)["Virtualenv"]
        assert info["Python"] == actual["version"]
        assert info["Implementation"] == actual["implementation"]
        assert Path(info["Path"]) == second
        assert Path(info["Executable"]) == Path(actual["executable"])
        assert info["Valid"] == "True"
        assert environment_listing(project, env) == {first: False, second: True}
        succeeded(project_cli(other, env, "env", "use", str(alternate)))
        foreign = reported_environment(other, env)
        refused(project_cli(project, env, "env", "remove", foreign.name), foreign.name)
        assert Path(project_observation(other, env)["prefix"]) == foreign
        assert environment_listing(project, env) == {first: False, second: True}
        succeeded(project_cli(project, env, "env", "remove", second.name))
        assert not second.exists()
        assert environment_listing(project, env) == {first: True}
        assert Path(project_observation(project, env)["prefix"]) == first
        succeeded(project_cli(project, env, "env", "use", str(alternate)))
        assert reported_environment(project, env) == second
        succeeded(project_cli(project, env, "env", "remove", "--all"))
        assert environment_listing(project, env) == {}
        assert not first.exists() and not second.exists()
        assert Path(project_observation(other, env)["prefix"]) == foreign
        # A new ordinary operation must be able to create a usable environment.
        succeeded(project_cli(project, env, "install"))
        assert project_observation(project, env)["prefix"] != str(foreign)


def test_activation_command_execution_and_missing_file(tmp_path, current_product_wheel):
    env, storage = environment_settings(tmp_path)
    project = environment_project(tmp_path / "project with spaces")
    succeeded(project_cli(project, env, "install"))
    selected = reported_environment(project, env)
    from F09_helpers import activation_shells
    binaries, shell_env = activation_shells(tmp_path / 'shells', env)
    for shell in ("sh", "bash", "zsh", "mksh"):
        # Keep the real shell as a live parent while shell detection runs.
        script = '''before=$(python -c 'import sys; print(sys.prefix)')
velnora --no-ansi env activate > activation-command
activation_status=$?
[ "$activation_status" -eq 0 ] || exit "$activation_status"
after=$(python -c 'import sys; print(sys.prefix)')
[ "$before" = "$after" ] || exit 91
command=$(cat activation-command)
eval "$command"
python -B -c ''' + shlex.quote(ENVIRONMENT_PROBE)
        result = succeeded(run_cli((str(binaries.get(shell, shell)),), ("-c", script), cwd=project, env=shell_env))
        actual = parse_json(result.stdout)
        assert Path(actual["prefix"]) == selected
        assert actual["version"] == project_observation(project, env)["version"]
    (project / 'activation-probe.py').write_text(ENVIRONMENT_PROBE)
    probe = 'python -B activation-probe.py'
    scripts = {
        'csh': 'velnora --no-ansi env activate > activation-command\nif ($status != 0) exit 92\nset command = "`cat activation-command`"\neval "$command"\n' + probe,
        'tcsh': 'velnora --no-ansi env activate > activation-command\nif ($status != 0) exit 92\nset command = "`cat activation-command`"\neval "$command"\n' + probe,
        'fish': 'velnora --no-ansi env activate > activation-command; or exit $status; eval (cat activation-command); ' + probe,
    }
    command = succeeded(run_cli((str(binaries['nu']),), ('-c', 'velnora --no-ansi env activate'), cwd=project, env=shell_env)).stdout.strip()
    scripts['nu'] = command + '; ' + probe
    command = succeeded(run_cli((str(binaries['pwsh']),), ('-NoLogo', '-NoProfile', '-Command', 'velnora --no-ansi env activate'), cwd=project, env=shell_env)).stdout.strip()
    result = succeeded(run_cli((str(binaries['pwsh']),), ('-NoLogo', '-NoProfile', '-Command', command + '; ' + probe), cwd=project, env=shell_env))
    assert Path(parse_json(result.stdout)['prefix']) == selected
    for shell, script in scripts.items():
        result = succeeded(run_cli((str(binaries[shell]),), ('-c', script), cwd=project, env=shell_env))
        assert Path(parse_json(result.stdout)['prefix']) == selected
    for shell, filename in [('fish', 'activate.fish'), ('csh', 'activate.csh'), ('nu', 'activate.nu')]:
        activation = selected / 'bin' / filename
        original = activation.read_bytes()
        activation.unlink()
        try:
            refused(run_cli((str(binaries[shell]),), ('-c', 'velnora --no-ansi env activate'), cwd=project, env=shell_env))
        finally:
            activation.write_bytes(original)
    activation = selected / 'bin/activate.ps1'
    activation.unlink()
    refused(run_cli((str(binaries['pwsh']),), ('-NoLogo', '-NoProfile', '-Command', 'velnora --no-ansi env activate; exit $LASTEXITCODE'), cwd=project, env=shell_env))
    (selected / "bin/activate").unlink()
    failed = run_cli(("bash",), ("-c", "velnora --no-ansi env activate; activation_status=$?; exit $activation_status"),
                     cwd=project, env=env)
    refused(failed)
    from F09_windows import windows_activation
    windows_activation(tmp_path / "windows", env, current_product_wheel)
