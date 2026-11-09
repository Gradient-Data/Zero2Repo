# feature: F19
"""Build a real C host against the product's public C archive interface."""

from pathlib import Path

import pytest

from _helpers import (
    build_go, isolated_workspace, parse_json, read_bytes, run_process, write_files,
)


F19_C_HOST = r'''
#include <stdio.h>
#include <stdlib.h>
#include "libzelviro.h"

/* Transport only: preserve NULL, empty strings, and all returned text. */
static void json_string(FILE *out, const char *s) {
    if (s == NULL) {
        fputs("null", out);
        return;
    }
    fputc('"', out);
    for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
        if (*p == '"' || *p == '\\') {
            fputc('\\', out);
            fputc(*p, out);
        } else if (*p < 0x20) {
            fprintf(out, "\\u%04x", (unsigned int)*p);
        } else {
            fputc(*p, out);
        }
    }
    fputc('"', out);
}

int main(int argc, char **argv) {
    if (argc < 4 || (argc - 2) % 2 != 0) {
        fputs("Expected output path and label/source pairs\n", stderr);
        return 2;
    }
    FILE *out = fopen(argv[1], "wb");
    if (out == NULL) {
        perror("Cannot open observation file");
        return 3;
    }
    uintptr_t interpreter = ZelviroNew();
    fputs("{\"evaluations\":[", out);
    for (int n = 2; n < argc; n += 2) {
        char *result = NULL;
        char *error = NULL;
        int status = ZelviroEval(interpreter, argv[n], argv[n + 1], &result, &error);
        if (n != 2) fputc(',', out);
        fprintf(out, "{\"status\":%d,\"result\":", status);
        json_string(out, result);
        fputs(",\"error\":", out);
        json_string(out, error);
        fputc('}', out);
        if (result != NULL) ZelviroFreeString(result);
        if (error != NULL) ZelviroFreeString(error);
    }
    ZelviroFree(interpreter);
    fputs("],\"completed\":true}\n", out);
    int failed = ferror(out);
    if (fclose(out) != 0 || failed) {
        fputs("Cannot write observations\n", stderr);
        return 4;
    }
    return 0;
}
'''


@pytest.fixture(scope="module")
def f19_c_driver():
    """Each invocation uses one fresh C host and reuses its interpreter."""
    product = Path.cwd()
    assert (product / "go.mod").is_file(), "Run from the product module directory"
    with isolated_workspace(overrides={
        "GOPROXY": "off", "CGO_ENABLED": "1", "CC": "cc",
        "ZELVIRO_DEBUG": None, "ZELVIRO_TRACE": None,
    }) as workspace:
        archive = build_go(
            ["go"], "./examples/c/shim", cwd=product,
            output=workspace.cwd / "libzelviro.a", env=workspace.env,
            # Read-only judge checkouts need no Git build metadata.
            flags=["-buildvcs=false", "-buildmode=c-archive"], timeout=300,
        ).artifact
        source = write_files(workspace.cwd, {"host.c": F19_C_HOST})["host.c"]
        binary = workspace.cwd / "host"
        compiled = run_process(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", binary,
             source, archive, "-lpthread", "-ldl", "-lm"],
            cwd=workspace.cwd, env=workspace.env, timeout=60,
        )
        assert compiled.returncode == 0, compiled
        count = 0

        def observe(evaluations):
            nonlocal count
            count += 1
            response = workspace.cwd / f"observations-{count}.json"
            arguments = [binary, response]
            for label, source_text in evaluations:
                arguments.extend([label, source_text])
            process = run_process(arguments, cwd=workspace.cwd,
                                  env=workspace.env, timeout=45)
            assert process.returncode == 0, process
            data = parse_json(read_bytes(response))
            assert data["completed"] is True, data
            assert len(data["evaluations"]) == len(evaluations), data
            return data["evaluations"], process

        yield observe


def f19_c_result(observation, expected):
    """Read success and its separate output parameters without normalizing them."""
    assert observation["status"] == 0, observation
    assert observation["error"] is None, observation
    assert observation["result"] == expected, observation
