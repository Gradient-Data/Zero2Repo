# feature: F07
"""Acceptance through install and real native build entry points."""
from _helpers import write_file
from F01_helpers import cli_success, cli_rejection
from F02_helpers import recipe_client, recipe_file
from F07_helpers import (CMAKE_SETTINGS, cmake_usage_consumer, cmake_usage_project,
                         compiled_usage_package, make_usage_consumer, pkgconfig_usage_consumer)


def carrier_package(client, root):
    # A direct dependency that adds nothing itself: everything the consumer needs
    # is reached through the dependency it carries.
    path = recipe_file(root, '''    package_type = "static-library"
    def requirements(self):
        self.requires("nativeusage/1.0", transitive_headers=True, transitive_libs=True)
''', name='usagecarrier', version='1.0')
    cli_success(client, 'create', path.parent, '-nr')


def test_make_dependency_usage(tmp_path):
    # F07.T05
    client = recipe_client(tmp_path)
    compiled_usage_package(client, tmp_path / 'package')
    carrier_package(client, tmp_path / 'carrier')
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "usagecarrier/1.0"\n')
    generated = tmp_path / 'make-inputs'
    cli_success(client, 'install', consumer.parent, '-nr', '-g', 'MakeDeps', '-of', generated)
    assert make_usage_consumer(client, tmp_path / 'make-project', generated) == '81\n'


def test_pkgconfig_dependency_usage(tmp_path):
    # F07.T07: recipe-selected generator, as opposed to T05's CLI selection.
    client = recipe_client(tmp_path)
    compiled_usage_package(client, tmp_path / 'package')
    carrier_package(client, tmp_path / 'carrier')
    consumer = recipe_file(tmp_path / 'consumer',
        '    requires = "usagecarrier/1.0"\n    generators = "PkgConfigDeps"\n')
    generated = tmp_path / 'pkg-inputs'
    cli_success(client, 'install', consumer.parent, '-nr', '-of', generated)
    assert pkgconfig_usage_consumer(client, tmp_path / 'pkg-project', generated, 'usagecarrier') == '81\n'


def test_component_transitive_usage(tmp_path):
    # F07.T13. Both Linux component-aware integrations consume the declarations.
    client = recipe_client(tmp_path)
    compiled_usage_package(client, tmp_path / 'package', components=True)
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "nativeusage/1.0"\n')
    generated = tmp_path / 'components'
    cli_success(client, 'install', consumer.parent, '-nr', '-g', 'PkgConfigDeps', '-of', generated)
    assert pkgconfig_usage_consumer(client, tmp_path / 'component-project', generated,
                                    'nativeusage-api') == '81\n'
    cmake_root = tmp_path / 'cmake-component-project'
    cmake_usage_project(cmake_root, components=True)
    recipe_file(cmake_root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = "nativeusage/1.0"
    generators = "CMakeDeps", "CMakeToolchain"
    def layout(self):
        self.folders.build = "build"
        self.folders.generators = "build/generators"
''')
    cli_success(client, 'install', cmake_root, '-nr', *CMAKE_SETTINGS,
                '-s', 'build_type=Debug',
                '-c', 'tools.cmake.cmaketoolchain:generator=Unix Makefiles',
                '-c', 'tools.build:cflags=["-DTOOLCHAIN_COMPILE=13"]',
                '-c', 'tools.build:exelinkflags=["-Wl,--defsym,caller_link_value=17"]')
    assert cmake_usage_consumer(client, cmake_root) == '111\n'
    # A declared component requires an absent component: refusal must be visible.
    recipe_file(tmp_path / 'invalid', '''    package_type = "header-library"
    def package_info(self):
        self.cpp_info.components["api"].requires = ["absent"]
''', name='invalidusage', version='1.0')
    cli_success(client, 'export', tmp_path / 'invalid', '-nr')
    # Both component-aware integrations are given everything else they need, so a
    # refusal is about the declaration.
    invalid_consumer = recipe_file(tmp_path / 'invalid-consumer',
                                  '    settings = "os", "arch", "compiler", "build_type"\n'
                                  '    requires = "invalidusage/1.0"\n')
    for generator in ('PkgConfigDeps', 'CMakeDeps'):
        cli_rejection(client, 'install', invalid_consumer.parent, '-nr', '-g', generator,
                      '--build=*', *CMAKE_SETTINGS)


def test_layout_and_output_location(tmp_path):
    # F07.T16: native consumer uses only the declared generated-output folder.
    client = recipe_client(tmp_path)
    compiled_usage_package(client, tmp_path / 'package')
    consumer = recipe_file(tmp_path / 'consumer', '''    requires = "nativeusage/1.0"
    generators = "MakeDeps"
    def layout(self):
        self.folders.source = "sources"
        self.folders.build = "build-area"
        self.folders.generators = "build-area/native-inputs"
    def build(self):
        from velmora.tools.files import copy
        import os
        copy(self, "*", self.source_folder, self.build_folder)
        self.run("make", cwd=self.build_folder)
''')
    write_file(consumer.parent / 'sources/main.c', '#include <usage.h>\nint main(void) { return usage() == 26 ? 0 : 1; }\n')
    write_file(consumer.parent / 'sources/Makefile', '''VELMORA_INCLUDE_DIR_FLAG=-I
VELMORA_LIB_DIR_FLAG=-L
VELMORA_LIB_FLAG=-l
VELMORA_SYSTEM_LIB_FLAG=-l
include native-inputs/velmoradeps.mk
app: main.c
\tgcc $(VELMORA_INCLUDE_DIRS) main.c -o app $(VELMORA_LIB_DIRS) $(VELMORA_LIBS) $(VELMORA_SYSTEM_LIBS)
\t./app
''')
    output = tmp_path / 'selected-output'
    cli_success(client, 'install', consumer.parent, '-nr', '-of', output)
    cli_success(client, 'build', consumer.parent, '-nr', '-of', output)
    # The declared build and generated locations are resolved beneath the
    # caller-selected output area, not beside the recipe.
    assert (output / 'build-area/native-inputs/velmoradeps.mk').is_file()
    assert (output / 'build-area/app').is_file()
    assert not (consumer.parent / 'build-area').exists()


def test_generator_configuration_refusals(tmp_path):
    # F07.T17. The CLI publishes status and ERROR reporting, not diagnostic codes.
    client = recipe_client(tmp_path)
    valid_qbs = recipe_file(tmp_path / 'valid-qbs',
                           '    settings = "os", "arch", "compiler", "build_type"\n')
    cli_success(client, 'install', valid_qbs.parent, '-nr', '-g', 'QbsProfile',
                '-s', 'compiler=gcc', '-s', 'compiler.version=12',
                '-s', 'compiler.libcxx=libstdc++11')
    # The refused compiler selections name compiler executables that do exist, so
    # the refusal comes from the selection itself rather than an executable search.
    available = ('-c', 'tools.build:compiler_executables={"c":"gcc","cpp":"g++"}')
    cases = [
        ('unknown', '    settings = "os", "arch", "build_type"\n', 'UnknownNativeIntegration', ()),
        ('missing-compiler', '    settings = "os", "arch", "build_type"\n', 'QbsProfile', available),
        ('unsupported-compiler', '    settings = "os", "arch", "compiler", "build_type"\n', 'QbsProfile', ('-s', 'compiler=intel-cc', '-s', 'compiler.version=2021.3', '-s', 'compiler.mode=icx', *available)),
        ('unavailable-compiler', '    settings = "os", "arch", "compiler", "build_type"\n', 'QbsProfile',
         ('-s', 'compiler=gcc', '-s', 'compiler.version=12', '-s', 'compiler.libcxx=libstdc++11',
          '-c', 'tools.build:compiler_executables={"c":"unavailable-acceptance-cc","cpp":"unavailable-acceptance-cxx"}')),
    ]
    for name, body, generator, args in cases:
        consumer = recipe_file(tmp_path / name, body)
        cli_rejection(client, 'install', consumer.parent, '-nr', '-g', generator, *args)
