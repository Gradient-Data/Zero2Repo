"""Run a Python build command with the version locked from the original revision."""
import json
import os
from pathlib import Path
import sys

metadata = json.loads(Path(__file__).with_name('product-version.json').read_text())
# Supply the exact SCM-derived version even when the build source has no .git.
# Scope this input to the build subprocess, not third-party dependency installs.
environment = dict(os.environ, SETUPTOOLS_SCM_PRETEND_VERSION=metadata['version'])
os.execve(sys.executable, [sys.executable, *sys.argv[1:]], environment)
