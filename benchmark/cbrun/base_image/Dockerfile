# Shared pipeline base used by recipe.lock as codingbench-base/ubuntu:24.04.
# Replays the golden image's layer recipe FROM official Ubuntu, then the
# toolchain hidden tests and per-case install_command assume.
#
# ARG defaults are the official URLs the golden image was actually built
# with (the Dockerfile ARG stubs still listed China mirrors; build-args
# overrode them). Node and Miniconda installers are checksum-pinned to the
# versions in the golden image.
#
# In a full-suite run cbrun builds this through its supply proxy (Docker's
# predefined proxy build args plus --network host). Steps that download over
# HTTPS then fetch the proxy's CA bundle from the proxy and delete it when the
# step ends, so the certificate never lands in a layer. Without a proxy those
# lines do nothing.

ARG FROM_IMAGE=ubuntu:24.04
FROM ${FROM_IMAGE}

ARG UBUNTU_VERSION=24.04
ARG APT_MIRROR=archive.ubuntu.com
ARG PIP_INDEX=https://pypi.org/simple/
ARG PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org"
ARG NPM_REGISTRY=https://registry.npmjs.org
ARG NODE_MIRROR=https://nodejs.org/dist
ARG NODE_VERSION=20.18.1
ARG NODE_TARBALL_SHA256=c6fa75c841cbffac851678a472f2a5bd612fff8308ef39236190e1f8dbb0e567
ARG VITEST_VERSION=3.2.6
ARG TYPESCRIPT_VERSION=5.9.3
ARG TYPES_NODE_VERSION=20
ARG PYTEST_VERSION=9.0.3
ARG SYS_PYTEST_VERSION=9.1.0
ARG MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-py313_26.3.2-2-Linux-x86_64.sh
ARG MINICONDA_SHA256=2284bafb7863a23411b19874d216e237964d4b32dd9beb6807fa8b2d84570961
ARG CONDA_PKGS_MAIN=https://repo.anaconda.com/pkgs/main
ARG CONDA_PKGS_R=https://repo.anaconda.com/pkgs/r
ARG CONDA_PKGS_MSYS2=https://repo.anaconda.com/pkgs/msys2
ARG CONDA_CLOUD=https://conda.anaconda.org

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_NO_CACHE_DIR=1 \
    NPM_CONFIG_REGISTRY=${NPM_REGISTRY}

RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then \
      sed -i \
        "s|http://archive.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g; \
         s|http://security.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g" \
        /etc/apt/sources.list.d/ubuntu.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
      sed -i \
        "s|http://archive.ubuntu.com|http://${APT_MIRROR}|g; \
         s|http://security.ubuntu.com|http://${APT_MIRROR}|g" \
        /etc/apt/sources.list; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        git \
        curl \
        wget \
        ca-certificates \
        unzip \
        xz-utils \
        python3 \
        python3-pip \
        python3-venv; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    printf '%s\n' \
      '[global]' \
      "index-url = ${PIP_INDEX}" \
      "trusted-host = ${PIP_TRUSTED_HOST}" \
      > /etc/pip.conf
# PIP_TRUSTED_HOST must stay a quoted ARG: unquoted spaces truncate to "pypi.org".

RUN set -eux; \
    if [ -n "${https_proxy:-}" ]; then \
      trap 'rm -f /tmp/cbrun-ca-bundle.pem' EXIT; \
      curl -fsS --max-time 30 http://cbrun-proxy.invalid/ca-bundle.pem -o /tmp/cbrun-ca-bundle.pem; \
      export SSL_CERT_FILE=/tmp/cbrun-ca-bundle.pem REQUESTS_CA_BUNDLE=/tmp/cbrun-ca-bundle.pem \
        CURL_CA_BUNDLE=/tmp/cbrun-ca-bundle.pem PIP_CERT=/tmp/cbrun-ca-bundle.pem \
        NODE_EXTRA_CA_CERTS=/tmp/cbrun-ca-bundle.pem CONDA_SSL_VERIFY=/tmp/cbrun-ca-bundle.pem; \
    fi; \
    if [ "${UBUNTU_VERSION}" = "24.04" ]; then \
      python3 -m pip install --no-cache-dir --break-system-packages \
        -i "${PIP_INDEX}" "pytest==${SYS_PYTEST_VERSION}"; \
    else \
      python3 -m pip install --no-cache-dir \
        -i "${PIP_INDEX}" "pytest==${SYS_PYTEST_VERSION}"; \
    fi

RUN set -eux; \
    if [ -n "${https_proxy:-}" ]; then \
      trap 'rm -f /tmp/cbrun-ca-bundle.pem' EXIT; \
      curl -fsS --max-time 30 http://cbrun-proxy.invalid/ca-bundle.pem -o /tmp/cbrun-ca-bundle.pem; \
      export SSL_CERT_FILE=/tmp/cbrun-ca-bundle.pem REQUESTS_CA_BUNDLE=/tmp/cbrun-ca-bundle.pem \
        CURL_CA_BUNDLE=/tmp/cbrun-ca-bundle.pem PIP_CERT=/tmp/cbrun-ca-bundle.pem \
        NODE_EXTRA_CA_CERTS=/tmp/cbrun-ca-bundle.pem CONDA_SSL_VERIFY=/tmp/cbrun-ca-bundle.pem; \
    fi; \
    curl -fsSL \
        "${NODE_MIRROR}/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
        -o /tmp/node.tar.xz; \
    echo "${NODE_TARBALL_SHA256}  /tmp/node.tar.xz" | sha256sum -c -; \
    tar -xJ -C /usr/local --strip-components=1 -f /tmp/node.tar.xz; \
    rm -f /tmp/node.tar.xz; \
    npm install -g \
        "vitest@${VITEST_VERSION}" \
        "typescript@${TYPESCRIPT_VERSION}" \
        "@types/node@${TYPES_NODE_VERSION}"

RUN set -eux; \
    if [ -n "${https_proxy:-}" ]; then \
      trap 'rm -f /tmp/cbrun-ca-bundle.pem' EXIT; \
      curl -fsS --max-time 30 http://cbrun-proxy.invalid/ca-bundle.pem -o /tmp/cbrun-ca-bundle.pem; \
      export SSL_CERT_FILE=/tmp/cbrun-ca-bundle.pem REQUESTS_CA_BUNDLE=/tmp/cbrun-ca-bundle.pem \
        CURL_CA_BUNDLE=/tmp/cbrun-ca-bundle.pem PIP_CERT=/tmp/cbrun-ca-bundle.pem \
        NODE_EXTRA_CA_CERTS=/tmp/cbrun-ca-bundle.pem CONDA_SSL_VERIFY=/tmp/cbrun-ca-bundle.pem; \
    fi; \
    curl -fsSL "${MINICONDA_URL}" -o /tmp/miniconda.sh; \
    echo "${MINICONDA_SHA256}  /tmp/miniconda.sh" | sha256sum -c -; \
    bash /tmp/miniconda.sh -b -p /opt/conda; \
    rm -f /tmp/miniconda.sh; \
    printf '%s\n' \
      'channels:' \
      '  - defaults' \
      'show_channel_urls: true' \
      'default_channels:' \
      "  - ${CONDA_PKGS_MAIN}" \
      "  - ${CONDA_PKGS_R}" \
      "  - ${CONDA_PKGS_MSYS2}" \
      'custom_channels:' \
      "  conda-forge: ${CONDA_CLOUD}" \
      "  bioconda: ${CONDA_CLOUD}" \
      | tee /opt/conda/.condarc /root/.condarc > /dev/null; \
    for ch in "${CONDA_PKGS_MAIN}" "${CONDA_PKGS_R}" "${CONDA_PKGS_MSYS2}"; do \
      /opt/conda/bin/conda tos accept --override-channels --channel "$ch"; \
    done; \
    /opt/conda/bin/conda install -y "pytest=${PYTEST_VERSION}"; \
    /opt/conda/bin/conda clean -afy; \
    ln -sf /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh

ENV PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN python3 --version \
    && pytest --version \
    && conda --version \
    && node --version \
    && npm --version \
    && vitest --version \
    && tsc --version

# Present on the golden image (added after the toolchain layers).
RUN apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo \
    && command -v sudo \
    && rm -rf /var/lib/apt/lists/*
