#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# Ubuntu packages come from Canonical's official archive snapshot 20261107T052315Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
sed -i -e 's/^Components: .*/Components: main/' /etc/apt/sources.list.d/ubuntu.sources
apt-get --snapshot 20261107T052315Z -o Acquire::Retries=3 -o Acquire::Languages=none -o Acquire::https::Timeout=30 -o APT::Update::Error-Mode=any update
python3 /env-assets/install-system.py
curl -fL --retry 3 --connect-timeout 20 --speed-limit 1024 --speed-time 30 https://repo1.maven.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.tar.gz -o /tmp/maven.tar.gz
echo 'a555254d6b53d267965a3404ecb14e53c3827c09c3b94b5678835887ab404556bfaf78dcfe03ba76fa2508649dca8531c74bca4d5846513522404d48e8c4ac8b  /tmp/maven.tar.gz' | sha512sum -c -
tar -xzf /tmp/maven.tar.gz -C /opt
ln -sf /opt/apache-maven-3.9.9/bin/mvn /usr/local/bin/mvn
rm /tmp/maven.tar.gz
mkdir -p /opt/maven-repository
cp /env-assets/settings.xml /opt/apache-maven-3.9.9/conf/settings.xml
