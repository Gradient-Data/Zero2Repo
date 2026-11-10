# feature: F01
"""Native public-API clients. Set VELNORA_ROOT to the product checkout (default /app).

F01_CARGO_CONFIG optionally selects an offline Cargo source configuration.
CARGO_TARGET_DIR, CARGO_HOME, CC and NODE retain their usual explicit meanings.
No build or execution failure is converted into a successful observation.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from _helpers import build_artifact, run_command, locate_artifact


def product_root():
    return Path(os.environ.get("VELNORA_ROOT", "/app")).resolve(strict=True)


def build_rust_client(source, directory, *, features=("ffi", "heap-profile"), environment=None):
    root = product_root()
    directory = Path(directory)
    (directory / "src").mkdir()
    (directory / "src/main.rs").write_text(source, encoding="utf-8")
    if tuple(features) == ("ffi", "heap-profile"):
        # Link the real library from the required product build. Recompiling it
        # under each external client's unrelated Cargo profile is unnecessary.
        target = Path(os.environ.get("CARGO_TARGET_DIR", str(root / "target")))
        library = locate_artifact(target / "release/libvelnora.rlib", root=root)
        binary, _ = build_artifact(
            ["rustc", "--edition=2021", "-C", "opt-level=3", "-C", "panic=abort",
             "-L", "dependency=" + str(target / "release/deps"),
             "--extern", "velnora=" + str(library), str(directory / "src/main.rs"),
             "-o", str(directory / "f01-client")], cwd=directory,
            artifact=directory / "f01-client", timeout=120, executable=True)
        return binary
    (directory / "Cargo.toml").write_text(
        '[package]\nname = "f01-client"\nversion = "0.1.0"\nedition = "2021"\n'
        '[dependencies]\nvelnora = { path = ' + json.dumps(str(root)) +
        ', features = ' + json.dumps(list(features)) + ' }\n', encoding="utf-8")
    command = ["cargo"]
    if "F01_CARGO_CONFIG" in os.environ:
        command += ["--config", os.environ["F01_CARGO_CONFIG"]]
    command += ["build", "--offline", "--release", "--manifest-path", str(directory / "Cargo.toml")]
    target = Path(os.environ.get("CARGO_TARGET_DIR", str(directory.parent / "cargo-target")))
    environment = dict(os.environ, **({} if environment is None else environment), CARGO_TARGET_DIR=str(target))
    try:
        binary, _ = build_artifact(command, cwd=directory,
                                   artifact=target / "release/f01-client", timeout=900,
                                   env=environment, executable=True)
    except subprocess.CalledProcessError as error:
        sys.stderr.buffer.write(error.stderr)
        raise
    # Cargo validates dependency fingerprints; each caller retains its own client.
    retained = directory / "f01-client"
    shutil.copy2(binary, retained)
    return retained


def run_native_client(binary, case):
    result = run_command([binary, case], cwd=binary.parent, timeout=120)
    assert result.returncode == 0, (result.stdout, result.stderr)
    return result


def run_c_client(source, directory):
    root = product_root()
    directory = Path(directory)
    source_path = directory / "client.c"
    source_path.write_text(source, encoding="utf-8")
    # The case's documented ffi build supplies this library; absence is an error.
    library = locate_artifact("target/release/libvelnora.so", root=root)
    binary, _ = build_artifact(
        [os.environ.get("CC", "cc"), str(source_path), "-I", str(root / "include"),
         str(library), "-Wl,-rpath," + str(library.parent), "-o", str(directory / "client")],
        cwd=directory, artifact=directory / "client", timeout=60, executable=True)
    return run_native_client(binary, "c")


def run_wasm_client(source, directory):
    """Run the public module in its portable JavaScript host.

    Node supplies the ECMAScript engine, not the product's operating-system
    services. This is a compatibility observer, not a security sandbox. Local
    relative ES modules are resolved normally, including cyclic dependencies.
    """
    root = product_root()
    driver = Path(directory) / "host.mjs"
    driver.write_text(r'''
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import vm from 'node:vm';

const context = vm.createContext({
    WebAssembly, TextEncoder, TextDecoder, URL, URLSearchParams,
    crypto, performance, console, setTimeout, clearTimeout, setInterval,
    clearInterval, queueMicrotask, atob, btoa,
});
const modules = new Map();
function resolve(specifier, parent) {
    if (!(specifier.startsWith('./') || specifier.startsWith('../') ||
          specifier.startsWith('/') || specifier.startsWith('file:'))) {
        throw new Error(`Module is unavailable in the portable host: ${specifier}`);
    }
    return new URL(specifier, parent).href;
}
function load(url) {
    if (modules.has(url)) return modules.get(url);
    const module = new vm.SourceTextModule(readFileSync(new URL(url), 'utf8'), {
        context, identifier: url,
        initializeImportMeta(meta) { meta.url = url; },
        async importModuleDynamically(specifier, parent) {
            const dependency = load(resolve(specifier, parent.identifier));
            if (dependency.status === 'unlinked') await dependency.link(link);
            if (dependency.status === 'linked') await dependency.evaluate();
            if (dependency.status === 'errored') throw dependency.error;
            return dependency;
        },
    });
    modules.set(url, module);
    return module;
}
function link(specifier, parent) {
    return load(resolve(specifier, parent.identifier));
}
const product = load(pathToFileURL(process.argv[3]).href);
await product.link(link);
await product.evaluate();
context.api = product.namespace;
context.byteValues = Array.from(readFileSync(process.argv[4]));
vm.runInContext('globalThis.wasmBytes = Uint8Array.from(byteValues); delete globalThis.byteValues;', context);
const client = load(pathToFileURL(process.argv[2]).href);
await client.link(link);
await client.evaluate();
''', encoding="utf-8")
    script = Path(directory) / "client.mjs"
    script.write_text(source, encoding="utf-8")
    result = run_command([os.environ.get("NODE", "node"), "--experimental-vm-modules",
                          str(driver), str(script),
                          str(root / "docs/assets/wasm/velnora.js"),
                          str(root / "docs/assets/wasm/velnora_bg.wasm")],
                         cwd=directory, timeout=120)
    assert result.returncode == 0, (result.stdout, result.stderr)
    return result.stdout
