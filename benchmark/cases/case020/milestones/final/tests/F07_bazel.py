# feature: F07
"""Build a native consumer with the generated Bazel dependencies and toolchain."""
from _helpers import write_file
from F01_helpers import cli_success
from F02_helpers import recipe_client, recipe_file
from F07_helpers import (CMAKE_SETTINGS, NATIVE_SOURCE, compiled_usage_package,
                         native_command, offline_bazel)


def test_bazel_dependency_and_toolchain_usage(tmp_path):
    # F07.T08. Bazel evaluates both the dependency declarations and rc file.
    client = recipe_client(tmp_path)
    bazel = offline_bazel(tmp_path / 'tools')
    compiled_usage_package(client, tmp_path / 'package')
    root = tmp_path / 'consumer'
    recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = "nativeusage/1.0"
    def layout(self):
        self.folders.generators = "velmora"
    def generate(self):
        from velmora.tools.google import BazelDeps, BazelToolchain
        BazelDeps(self).generate()
        toolchain = BazelToolchain(self)
        toolchain.compiler = "consumer-gcc"
        toolchain.cpu = "consumer-cpu"
        toolchain.crosstool_top = "//:selected_toolchain"
        toolchain.generate()
''')
    # Bazel copts belong to the target being built rather than its dependents;
    # dependency definitions and link requirements are transitive.
    source = NATIVE_SOURCE.replace('+USAGE_CFLAG', '').replace(
        '(int)(uintptr_t)&usage_link_value',
        '(int)(uintptr_t)&usage_link_value+TOOLCHAIN_COMPILE+(int)(uintptr_t)&caller_link_value+SELECTED_CONFIGURATION')
    source = source.replace('extern char usage_link_value;',
                            'extern char usage_link_value, caller_link_value;')
    write_file(root / 'main.c', source)
    write_file(root / 'WORKSPACE', '''load("//velmora:dependencies.bzl", "load_velmora_dependencies")
load_velmora_dependencies()
''')
    write_file(root / 'BUILD', '''cc_toolchain_suite(
    name="selected_toolchain",
    toolchains={"consumer-cpu|consumer-gcc": "@local_config_cc//:cc-compiler-k8"},
)
config_setting(name="debug", values={"compilation_mode": "dbg", "compiler": "consumer-gcc", "cpu": "consumer-cpu"})
cc_binary(
    name="app", srcs=["main.c"], deps=["@nativeusage//:nativeusage"],
    defines=select({":debug": ["SELECTED_CONFIGURATION=19"], "//conditions:default": ["SELECTED_CONFIGURATION=31"]}),
)
''')
    for configuration, expected in (('Debug', '123\n'), ('Release', '135\n')):
        cli_success(client, 'install', root, '-nr', *CMAKE_SETTINGS,
                    '-s', 'build_type='+configuration,
                    '-c', 'tools.build:cflags=["-DTOOLCHAIN_COMPILE=13"]',
                    '-c', 'tools.build:exelinkflags=["-Wl,--defsym,caller_link_value=17"]')
        native_command(client, root, str(bazel), '--batch',
                       '--output_user_root='+str(tmp_path / 'bazel-state'),
                       '--bazelrc='+str(root / 'velmora/velmora_bzl.rc'),
                       'build', '--distdir='+str(bazel.parent), '--config=velmora-config', '--jobs=2', '//:app')
        assert native_command(client, root, str(root / 'bazel-bin/app')).text('stdout') == expected
