import assert from 'node:assert/strict';

assert.equal(process.version, `v${process.argv[2]}`);
assert.notEqual(process.getuid(), 0);
// Compile and instantiate the standard empty WebAssembly module. This checks
// runtime support only; the unchanged product tests check database behavior.
const module = await WebAssembly.compile(
    Uint8Array.from([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]),
);
const instance = await WebAssembly.instantiate(module);
assert.ok(instance instanceof WebAssembly.Instance);
console.log(JSON.stringify({
    node: process.version,
    executable: process.execPath,
    uid: process.getuid(),
    cwd: process.cwd(),
    esModules: true,
    topLevelAwait: true,
    webAssembly: true,
}));
