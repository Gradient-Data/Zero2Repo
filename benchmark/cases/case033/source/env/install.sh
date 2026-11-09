#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# Ubuntu packages come from Canonical's official archive snapshot 20261107T063054Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T063054Z
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=5 update
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=5 install -y --no-install-recommends graphviz=2.42.2-9ubuntu0.1
/usr/bin/python3 -m venv /opt/runtime
/usr/bin/python3 /env-assets/fetch.py
/opt/runtime/bin/python -m pip install --no-index --no-deps --no-build-isolation /opt/dependency-archives/setuptools-77.0.3-py3-none-any.whl /opt/dependency-archives/wheel-*.whl /opt/dependency-archives/packaging-*.whl
/opt/runtime/bin/python -m pip install --no-index --find-links=/opt/dependency-archives --no-build-isolation --require-hashes -r /env-assets/requirements.txt
printf '[global]\nno-index = true\nfind-links = /opt/dependency-archives\ndisable-pip-version-check = true\n' > /opt/runtime/pip.conf
chmod -R a+rX /opt/runtime /opt/dependency-archives

# The trusted judge launches python3 independently of the pytest command.
# Use exec wrappers: a symlink outside the venv loses its pyvenv.cfg.
for directory in /opt/conda/bin /usr/local/bin; do
    for command in python python3 pip pip3 pytest; do
        case "$command" in
            python|python3) module= ;;
            pip|pip3) module='-m pip' ;;
            pytest) module='-m pytest' ;;
        esac
        printf '#!/bin/sh\nexec /opt/runtime/bin/python %s "$@"\n' "$module" > "$directory/$command.runtime"
        chmod 755 "$directory/$command.runtime"
        mv -f "$directory/$command.runtime" "$directory/$command"
    done
done
python3 -I -c 'import sys, torch, numpy, scipy, pytest; assert sys.prefix == "/opt/runtime"; print(sys.executable, sys.version); print(*(module.__file__ for module in (torch, numpy, scipy, pytest)), sep="\n")'
