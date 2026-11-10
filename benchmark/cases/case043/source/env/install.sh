#!/bin/bash
set -euo pipefail
# Versions follow the repository CI toolchain declarations.
# Neither Zig nor wasm-tools has an Alibaba Cloud source in the mirror catalog.
# Checksums come from the official Zig release index and GitHub release metadata.
test "$(uname -m)" = x86_64
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
curl -fL --retry 5 --retry-delay 2 --connect-timeout 30 --speed-limit 1024 --speed-time 30 https://ziglang.org/download/0.16.0/zig-x86_64-linux-0.16.0.tar.xz -o "$stage/zig.tar.xz"
printf '%s  %s\n' 70e49664a74374b48b51e6f3fdfbf437f6395d42509050588bd49abe52ba3d00 "$stage/zig.tar.xz" | sha256sum -c -
mkdir -p /opt/zig-0.16.0
tar -xJf "$stage/zig.tar.xz" --strip-components=1 -C /opt/zig-0.16.0
ln -s /opt/zig-0.16.0/zig /usr/local/bin/zig
curl -fL --retry 5 --retry-delay 2 --connect-timeout 30 --speed-limit 1024 --speed-time 30 https://github.com/bytecodealliance/wasm-tools/releases/download/v1.251.0/wasm-tools-1.251.0-x86_64-linux.tar.gz -o "$stage/wasm-tools.tar.gz"
printf '%s  %s\n' 08d523676ec71d9afbae05aa4255041ce91bf2d325d87b7e722d190d558be689 "$stage/wasm-tools.tar.gz" | sha256sum -c -
tar -xzf "$stage/wasm-tools.tar.gz" -C "$stage"
install -m 0755 "$stage/wasm-tools-1.251.0-x86_64-linux/wasm-tools" /usr/local/bin/wasm-tools
