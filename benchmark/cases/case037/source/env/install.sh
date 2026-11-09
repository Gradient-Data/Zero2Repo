#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# Ubuntu packages come from Canonical's official archive snapshot 20261107T063834Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T063834Z
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=5 -o Acquire::https::Timeout=30 update
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=5 -o Acquire::https::Timeout=30 install -y --no-install-recommends \
    libkrb5-dev=1.20.1-6ubuntu2.10 libssl-dev=3.0.13-0ubuntu3.16 \
    libnettle8t64=3.9.1-2.2build1.1 openssh-client=1:9.6p1-3ubuntu13.20 \
    openssh-server=1:9.6p1-3ubuntu13.20 cmake=3.28.3-1build7 ninja-build=1.11.1-2
install -o root -g root -m 0644 /env-assets/ssh-keysign.conf \
    /etc/ssh/ssh_config.d/00-codingbench-keysign.conf
ssh-keygen -A
python3 /env-assets/download.py
python3 -m pip install --no-index --find-links=/opt/offline-packages --require-hashes --no-deps -r /env-assets/bootstrap.txt
python3 -m pip install --no-index --find-links=/opt/offline-packages --require-hashes --no-build-isolation -r /env-assets/requirements.txt
mkdir -p /tmp/native-build
for attempt in 1 2 3; do
    if git -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=30 clone \
        --depth=1 --branch 0.10.1 https://github.com/open-quantum-safe/liboqs.git \
        /tmp/native-build/source; then
        break
    else
        status=$?
        if [ "$attempt" -eq 3 ]; then exit "$status"; fi
        rm -rf /tmp/native-build/source
    fi
done
actual=$(git -C /tmp/native-build/source rev-parse HEAD)
if [ "$actual" != 5dd87dcaafa6f90e983ef464f9f6a75f9485fb26 ]; then
    echo "Unexpected native dependency commit: $actual" >&2
    exit 1
fi
cmake -G Ninja -S /tmp/native-build/source -B /tmp/native-build/build \
    -DCMAKE_INSTALL_PREFIX=/usr/local -DBUILD_SHARED_LIBS=ON \
    -DOQS_BUILD_ONLY_LIB=ON -DOQS_DIST_BUILD=ON -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/native-build/build --parallel 2
cmake --install /tmp/native-build/build
ldconfig
rm -rf /tmp/native-build
mkdir -p /etc/pip
printf '[global]\nno-index = true\nfind-links = /opt/offline-packages\ndisable-pip-version-check = true\n' > /etc/pip.conf
chmod -R a+rX /opt/offline-packages
