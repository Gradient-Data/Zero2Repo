#!/bin/sh
set -eu
case "$(uname -m)" in
    x86_64)
        arch=amd64
        checksum=1153d3d50e0ac764b447adfe05c2bcf08e889d42a02e0fe0259bd47f6733ad7f
        ;;
    aarch64)
        arch=arm64
        checksum=ef758ae7c6cf9267c9c0ef080b8965f453d89ab2d25d9eb22de4405925238768
        ;;
    *) echo "Unsupported machine architecture: $(uname -m)" >&2; exit 1 ;;
esac
archive=$(mktemp /tmp/go-toolchain.XXXXXX)
trap 'rm -f "$archive"' EXIT HUP INT TERM
curl --fail --location --retry 5 --retry-all-errors --connect-timeout 20 \
    --speed-limit 10240 --speed-time 60 --max-time 600 \
    "https://dl.google.com/go/go1.26.4.linux-${arch}.tar.gz" \
    --output "$archive"
printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --strict
mkdir -p /opt/go1.26.4 /usr/local/bin
tar -xzf "$archive" -C /opt/go1.26.4 --strip-components=1
ln -sfn /opt/go1.26.4/bin/go /usr/local/bin/go
ln -sfn /opt/go1.26.4/bin/gofmt /usr/local/bin/gofmt
