"""Install verified Playwright archives in a shared, user-independent directory."""
import json
from pathlib import Path
import site
import stat
from urllib.parse import urlparse
import zipfile

root = Path('/opt/ms-playwright')
for artifact in json.loads(Path('/env-assets/browsers.json').read_text()):
    archive = Path('/opt/browser-archives') / Path(urlparse(artifact['url']).path).name
    destination = root / artifact['directory']
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
        for member in bundle.infolist():
            mode = member.external_attr >> 16
            if stat.S_ISREG(mode):
                (destination / member.filename).chmod(mode & 0o777)
    (destination / 'INSTALLATION_COMPLETE').touch()
# Python startup selects the same shared resources for every judge user, even
# without a login shell. An explicit caller override remains supported.
site_packages = Path(site.getsitepackages()[0])
(site_packages / 'codingbench_browser_path.pth').write_text(
    "import os; os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '/opt/ms-playwright')\n"
)
