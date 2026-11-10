# feature: F02
"""Build and install real plugin distributions into an isolated import target."""
import os
import sys

from _helpers import make_environment, parse_metadata, read_zip, run_cli
from F01_helpers import BUILD_SYSTEM, project_cli, succeeded, write_project


def installed_plugin(root, env, source, *, group, target="Extension"):
    package = write_project(root / "plugin-source", '''[project]
name = "acceptance-extension"
version = "1.0.0"
requires-python = ">=3.9"
dependencies = ["velnora"]
[project.entry-points."''' + group + '''"]
acceptance = "acceptance_extension:''' + target + '''"
''' + BUILD_SYSTEM, module="acceptance_extension")
    (package / "acceptance_extension" / "__init__.py").write_text(source, encoding="utf-8")
    succeeded(project_cli(package, env, "--no-plugins", "build", "--format", "wheel"))
    wheels = list((package / "dist").glob("*.whl"))
    assert len(wheels) == 1, wheels
    destination = root / "installed-plugin"
    succeeded(run_cli((sys.executable, "-m", "pip"),
        ("install", "--no-index", "--no-deps", "--no-compile", "--target", str(destination), str(wheels[0])),
        cwd=root, env=env, timeout=120))
    return make_environment(env, updates={
        "PYTHONPATH": os.pathsep.join((str(destination), env["PYTHONPATH"]))})


PROJECT_EXTENSION = '''from pathlib import Path
import os
from velnora.plugins.plugin import Plugin
from poetry.core.constraints.version import Version
from poetry.core.packages.directory_dependency import DirectoryDependency

class Extension(Plugin):
    def activate(self, velnora, io):
        velnora.package.version = Version.parse("4.7.2")
        velnora.package.description = "Metadata supplied by an installed extension"
        velnora.package.add_dependency(DirectoryDependency(
            "local-addon", Path(os.environ["ACCEPTANCE_ADDON"])))
'''

APPLICATION_EXTENSION = '''from pathlib import Path
import json
import os
from cleo.commands.command import Command
from cleo.events.console_events import COMMAND
from velnora.plugins.application_plugin import ApplicationPlugin

class DigestCommand(Command):
    name = "extension-count"

    def handle(self):
        values = json.loads(Path(os.environ["ACCEPTANCE_INPUT"]).read_text())
        self.line(json.dumps({"total": sum(values), "count": len(values)}))
        return 0

class Extension(ApplicationPlugin):
    def activate(self, application):
        application.command_loader.register_factory("extension-count", DigestCommand)
        application.event_dispatcher.add_listener(COMMAND, self.prepare_readme)

    def prepare_readme(self, event, event_name, dispatcher):
        if event.command.name == "build":
            Path("README.md").write_text(Path(os.environ["ACCEPTANCE_INPUT"]).read_text())
'''

INVALID_EXTENSION = '''class Extension:
    def activate(self, *args):
        return None
'''


def extension_wheel_metadata(path, env, *flags):
    succeeded(project_cli(path, env, *flags, "build", "--format", "wheel"))
    wheels = list((path / "dist").glob("*.whl"))
    assert len(wheels) == 1, wheels
    records = [data for name, data in read_zip(wheels[0]).items()
               if name.endswith(".dist-info/METADATA")]
    assert len(records) == 1, len(records)
    return parse_metadata(records[0])
