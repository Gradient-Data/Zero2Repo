"""Expose installed wheel commands on the default system search path."""
import importlib.metadata
import pathlib
import sysconfig

scripts = pathlib.Path(sysconfig.get_path('scripts'))
destination = pathlib.Path('/usr/local/bin')
for distribution in importlib.metadata.distributions():
    for entry in distribution.files:
        command = pathlib.Path(distribution.locate_file(entry)).absolute()
        if command.parent.resolve() != scripts.resolve():
            continue
        if not command.is_file():
            raise FileNotFoundError(command)
        link = destination / command.name
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(command.resolve())
