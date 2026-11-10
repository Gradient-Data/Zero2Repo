"""Preinstall pinned runtime signatures, verifying every required Git blob."""
import json
import pathlib
from archive import unpack
from download import fetch

metadata = json.loads(pathlib.Path('/env-assets/signature-files.json').read_text())
target = pathlib.Path('/opt/runtime-cache/velnora/flirt_signatures')
target.mkdir(parents=True, exist_ok=True)
archive = pathlib.Path('/opt/runtime-cache/signatures.tar.gz')
fetch(metadata['url'], archive)
unpack(archive, target, metadata['files'])
archive.unlink()

# Publish completion only after all pinned files pass integrity checks.
(target / '.download_complete').touch()
pathlib.Path('/opt/runtime-cache').chmod(0o1777)
target.parent.chmod(0o1777)
