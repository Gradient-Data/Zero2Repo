set -eux
export DEBIAN_FRONTEND=noninteractive
# Ubuntu packages come from Canonical's official archive snapshot 20261107T060749Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T060749Z
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=3 -o APT::Update::Error-Mode=any update
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=3 install -y --no-install-recommends libclang-dev libssl-dev pkg-config openjdk-21-jre-headless strace
bash /env-assets/prepare-python.sh
/opt/product-env/bin/python /env-assets/install-native.py
/opt/product-env/bin/python /env-assets/install-data.py
chmod -R a+rX /opt/product-env /opt/rust /opt/cargo /opt/offline
