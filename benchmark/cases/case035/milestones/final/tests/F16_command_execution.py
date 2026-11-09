# feature: F16
"""Acceptance tests for execution in a selected project environment."""
from pathlib import Path

from _helpers import make_environment, parse_json, run_cli
from F01_helpers import project_cli, project_environment, refused, succeeded
from F04_helpers import DistributionFactory
from F09_helpers import reported_environment
from F11_helpers import installation_python, seed_installation
from F16_helpers import CONSOLE_APPLICATION, EXECUTION_PROBE, execution_project


def test_commands_and_python_scripts_use_environment_and_forward_arguments(tmp_path):
    env = project_environment(tmp_path / "settings")
    project = execution_project(tmp_path / "project")
    factory = DistributionFactory(tmp_path / "build")
    wheel = factory.create("execution-dependency", "3.2")[1]
    seed_installation(project, env, [wheel])
    selected = reported_environment(project, env)
    script = project / "application with spaces.py"
    script.write_text(EXECUTION_PROBE, encoding="utf-8")
    arguments = ["--help", "--version", "--project=elsewhere", "two words", "", "quotes'\"", "$HOME;*", "--", "tail"]
    # A real non-Python executable resolves Python through the environment PATH.
    # The other arm invokes a Python script directly through the selected Python.
    for command in [
        ("/bin/sh", "-c", 'exec python "$@"', "launcher", "-B", "-c", EXECUTION_PROBE),
        ("python", "-B", str(script)),
    ]:
        for status in (0, 23):
            result = project_cli(project, env, "run", "--", *command, str(status), *arguments)
            assert result.returncode == status, result
            observed = parse_json(result.stdout)
            assert Path(observed["prefix"]) == selected
            assert observed["dependency"] == "execution-dependency:3.2"
            assert observed["argv"] == arguments
            assert result.stderr == "application stderr\n", result


def test_installed_console_scripts_reinstall_and_execution_failures(tmp_path):
    env = project_environment(tmp_path / "settings")
    project = execution_project(tmp_path / "project", scripts='''
[project.scripts]
calculate = "execution_subject:add"
''')
    (project / "execution_subject" / "__init__.py").write_text(CONSOLE_APPLICATION, encoding="utf-8")
    succeeded(project_cli(project, env, "install"))
    selected = reported_environment(project, env)
    clean = make_environment(env, remove=("PYTHONPATH",))
    bin_dir = installation_python(project, env).parent
    # Execute outside the source tree too: parsing the declaration without
    # installing a usable entry point cannot satisfy this observation.
    for command, operation, value in [("calculate", "sum", 15), ("calculate-new", "product", 56)]:
        if command == "calculate-new":
            declaration = project / "pyproject.toml"
            declaration.write_text(declaration.read_text().replace(
                'calculate = "execution_subject:add"',
                'calculate-new = "execution_subject:multiply"'), encoding="utf-8")
            succeeded(project_cli(project, env, "install"))
        for status in (0, 19):
            arguments = (str(status), "7", "8")
            results = [
                project_cli(project, env, "run", command, *arguments),
                run_cli((str(bin_dir / command),), arguments, cwd=tmp_path, env=clean),
            ]
            for result in results:
                assert result.returncode == status, result
                observed = parse_json(result.stdout)
                assert observed == {"operation": operation, "value": value,
                    "argv": ["7", "8"], "prefix": str(selected)}
                assert result.stderr == "console stderr\n", result
    missing = "unavailable-execution-command-f16"
    refused(project_cli(project, env, "run", missing), missing)
