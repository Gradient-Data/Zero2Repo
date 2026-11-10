#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# Ubuntu packages come from Canonical's official archive snapshot 20261107T013132Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T013132Z
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=3 update
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=3 install -y --no-install-recommends gfortran=4:13.2.0-7ubuntu1 libblas-dev=3.12.0-3build1.1 liblapack-dev=3.12.0-3build1.1 libopenmpi-dev=4.1.6-7ubuntu2 openmpi-bin=4.1.6-7ubuntu2 libomp-dev=1:18.0-59~exp2 m4=1.4.19-4build1 cmake=3.28.3-1build7
/opt/conda/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 13), sys.version'
ln -s /opt/conda /opt/runtime
mkdir -p /opt/offline/wheels /opt/offline/modules
/usr/bin/python3 /env-assets/fetch.py
/opt/conda/bin/python -m pip install --no-index --find-links=/opt/offline/wheels --require-hashes -r /env-assets/requirements.txt
/opt/conda/bin/python /env-assets/publish_commands.py
/opt/conda/bin/python /env-assets/link_product.py
cp /env-assets/build.py /opt/offline/build.py
chmod -R a+rX /opt/offline
/opt/conda/bin/python - <<'PYTHON'
import pathlib
import sysconfig
site = pathlib.Path(sysconfig.get_path('purelib'))
(site / 'supplied-product.pth').write_text('/app/.product\n', encoding='utf-8')
PYTHON
