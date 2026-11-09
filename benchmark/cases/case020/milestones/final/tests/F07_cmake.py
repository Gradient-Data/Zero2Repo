# feature: F07
"""Native CMake dependency, configuration and cross-compilation acceptance."""
import json

from _helpers import run, write_file
from F01_helpers import cli_success
from F02_helpers import recipe_client, recipe_file
from F07_helpers import (CMAKE_SETTINGS, cmake_command, cmake_usage_consumer,
                         cmake_usage_project, compiled_usage_package, native_command,
                         offline_native_tools, autotools_configure)


def test_cmake_dependency_and_toolchain_usage(tmp_path):
    # F07.T01. CMake's generated preset, rather than command-line overrides,
    # binds the build configuration and the caller's compile/link options.
    client = recipe_client(tmp_path)
    compiled_usage_package(client, tmp_path / 'package')
    root = tmp_path / 'consumer'
    cmake_usage_project(root)
    # C++ compile flags are caller input of their own, read by a C++ translation unit.
    project = (root / 'CMakeLists.txt').read_text().replace('project(Consumer C)', 'project(Consumer C CXX)')
    write_file(root / 'CMakeLists.txt', project + 'add_library(cxxprobe OBJECT probe.cpp)\n')
    write_file(root / 'probe.cpp', '#if TOOLCHAIN_CXX != 5\n#error C++ flags were not applied\n#endif\n')
    recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = "nativeusage/1.0"
    generators = "CMakeDeps", "CMakeToolchain"
    def layout(self):
        self.folders.build = "build"
        self.folders.generators = "build/generators"
''')
    cli_success(client, 'install', root, '-nr', *CMAKE_SETTINGS, '-s', 'build_type=Debug',
                '-c', 'tools.cmake.cmaketoolchain:generator=Unix Makefiles',
                '-c', 'tools.build:cflags=["-DTOOLCHAIN_COMPILE=13"]',
                '-c', 'tools.build:cxxflags=["-DTOOLCHAIN_CXX=5"]',
                '-c', 'tools.build:exelinkflags=["-Wl,--defsym,caller_link_value=17"]')
    assert cmake_usage_consumer(client, root) == '111\n'


def test_cmake_configurations_coexist(tmp_path):
    # F07.T14. Each configuration has a genuinely different archive. Neither
    # expected result is read back from product-generated metadata.
    client = recipe_client(tmp_path)
    package = recipe_file(tmp_path / 'package', '''    settings = "build_type"
    package_type = "static-library"
    def package(self):
        import os, subprocess
        from velmora.tools.files import save
        debug = str(self.settings.build_type) == "Debug"
        name, value = ("selected_debug", 17) if debug else ("selected_release", 53)
        save(self, "selected.c", "int selected(void) { return %d; }" % value)
        subprocess.check_call(["gcc", "-c", "selected.c", "-o", "selected.o"])
        os.makedirs(os.path.join(self.package_folder, "lib"))
        subprocess.check_call(["ar", "rcs", os.path.join(self.package_folder, "lib", "lib"+name+".a"), "selected.o"])
    def package_info(self):
        self.cpp_info.includedirs = []
        self.cpp_info.libs = ["selected_debug" if str(self.settings.build_type) == "Debug" else "selected_release"]
''', name='selected', version='1.0')
    for configuration in ('Debug', 'Release'):
        cli_success(client, 'create', package.parent, '-nr', '-s', 'build_type='+configuration)
    root = tmp_path / 'consumer'
    recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = "selected/1.0"
    generators = "CMakeDeps", "CMakeToolchain"
''')
    generated = tmp_path / 'combined'
    for configuration in ('Debug', 'Release'):
        cli_success(client, 'install', root, '-nr', '-of', generated, *CMAKE_SETTINGS,
                    '-s', 'build_type='+configuration,
                    '-c', 'tools.cmake.cmaketoolchain:generator=Unix Makefiles')
    write_file(root / 'main.c', '#include <stdio.h>\nint selected(void);\nint main(void) { printf("%d\\n", selected()); }\n')
    write_file(root / 'CMakeLists.txt', '''cmake_minimum_required(VERSION 3.23)
project(Configurations C)
find_package(selected REQUIRED)
add_executable(app main.c)
target_link_libraries(app PRIVATE selected::selected)
''')
    for configuration, expected in (('Debug', '17\n'), ('Release', '53\n')):
        build = tmp_path / configuration
        cmake_command(client, root, '-S', str(root), '-B', str(build),
                      '-DCMAKE_TOOLCHAIN_FILE='+str(generated / 'velmora_toolchain.cmake'),
                      '-DCMAKE_BUILD_TYPE='+configuration)
        cmake_command(client, root, '--build', str(build))
        assert native_command(client, root, str(build / 'app')).text('stdout') == expected


def test_cmake_cross_target_and_build_tool(tmp_path):
    # F07.T15. GCC and Clang produce freestanding i386 executables without a 32-bit
    # libc installation; Linux executes its exit syscall directly. The build
    # tool is separately compiled as x86_64 and runs during host generation.
    for family, version in (('gcc', '12'), ('clang', '18')):
        area = tmp_path / family
        client = offline_native_tools(recipe_client(area), area / 'tools')
        tool = recipe_file(area / 'tool', '''    package_type = "application"
    settings = "os", "arch"
    def package(self):
        import os, subprocess
        from velmora.tools.files import save
        save(self, "tool.c", '#ifndef __x86_64__\\n#error Wrong build-tool architecture\\n#endif\\n#include <stdio.h>\\nint main(void) { puts("13"); }')
        os.makedirs(os.path.join(self.package_folder, "bin"))
        subprocess.check_call(["gcc", "tool.c", "-o", os.path.join(self.package_folder, "bin", "native-build-tool")])
''', name='native-build-tool', version='1.0')
        cli_success(client, 'create', tool.parent, '-nr')
        root = area / 'consumer'
        recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    tool_requires = "native-build-tool/1.0"
    def generate(self):
        import os, subprocess
        from velmora.tools.cmake import CMakeToolchain
        from velmora.tools.meson import MesonToolchain
        from velmora.tools.gnu import AutotoolsToolchain
        from velmora.tools.env import VirtualBuildEnv
        from velmora.tools.files import save
        with VirtualBuildEnv(self).vars().apply():
            value = subprocess.check_output(["native-build-tool"], text=True).strip()
        save(self, os.path.join(self.source_folder, "build_value.h"), "#define BUILD_VALUE " + value + "\\n")
        CMakeToolchain(self).generate()
        MesonToolchain(self).generate()
        AutotoolsToolchain(self).generate()
    def build(self):
        from velmora.tools.gnu import Autotools
        native = Autotools(self)
        native.configure()
        native.make()
    def layout(self):
        self.folders.build = "build"
        self.folders.generators = "build/generators"
''')
        sysroot = area / 'sdk'
        write_file(sysroot / 'usr/include/target_value.h', '#define SYSROOT_VALUE 19\n')
        compiler = write_file(area / ('selected-'+family), '#!/bin/sh\nexec /usr/bin/'+family+' -DSELECTED_COMPILER=29 "$@"\n')
        compiler.chmod(0o755)
        write_file(root / 'main.c', '''#if !defined(__i386__)
#error Wrong host target architecture
#endif
#include <target_value.h>
#include "build_value.h"
extern char cross_link_value;
void _start(void) {
  int result = SYSROOT_VALUE + TARGET_FLAG + SELECTED_COMPILER + BUILD_VALUE + (int)&cross_link_value;
  __asm__ volatile("int $0x80" : : "a"(1), "b"(result));
  __builtin_unreachable();
}
''')
        write_file(root / 'CMakeLists.txt', '''cmake_minimum_required(VERSION 3.23)
project(CrossConsumer C)
add_executable(app main.c)
''')
        settings = ('-s', 'compiler='+family, '-s', 'compiler.version='+version,
                    '-s', 'compiler.libcxx=libstdc++11', '-s', 'arch=x86',
                    '-c', 'tools.cmake.cmaketoolchain:generator=Unix Makefiles',
                    '-c', 'tools.build:compiler_executables='+json.dumps({'c': str(compiler)}),
                    '-c', 'tools.build:sysroot='+str(sysroot),
                    '-c', 'tools.build:cflags=["-ffreestanding", "-fno-pie", "-fno-stack-protector", "-DTARGET_FLAG=7"]',
                    '-c', 'tools.build:exelinkflags=["-nostdlib", "-static", "-Wl,-e,_start", "-Wl,--defsym,cross_link_value=5"]',
                    '-c', 'tools.cmake.cmaketoolchain:extra_variables={"CMAKE_TRY_COMPILE_TARGET_TYPE":"STATIC_LIBRARY"}')
        cli_success(client, 'install', root, '-nr', *settings)
        cmake_command(client, root, '--preset', 'velmora-release')
        cmake_command(client, root, '--build', '--preset', 'velmora-release')
        result = run((str(root / 'build/app'),), cwd=root, env=client.env)
        assert result.returncode == 73, result
        # The same caller inputs must also reach Meson and Autotools. Each native
        # tool builds its own executable; no generated flags are parsed by Python.
        write_file(root / 'meson.build', '''project('CrossConsumer', 'c')
assert(host_machine.system() == 'linux' and host_machine.cpu_family() == 'x86', 'Wrong target')
executable('app', 'main.c')
''')
        native_command(client, root, 'meson', 'setup', 'meson-build', '--cross-file',
                       str(root / 'build/generators/velmora_meson_cross.ini'))
        native_command(client, root, 'meson', 'compile', '-C', 'meson-build')
        result = run((str(root / 'meson-build/app'),), cwd=root, env=client.env)
        assert result.returncode == 73, result
        configure = write_file(root / 'configure', autotools_configure())
        configure.chmod(0o755)
        write_file(root / 'Makefile.in', '''CC = @CC@
CPPFLAGS = @CPPFLAGS@
CFLAGS = @CFLAGS@
LDFLAGS = @LDFLAGS@
LIBS = @LIBS@
autotools-app: ../main.c
\t$(CC) $(CPPFLAGS) $(CFLAGS) ../main.c -o autotools-app $(LDFLAGS) $(LIBS)
''')
        cli_success(client, 'build', root, '-nr', *settings)
        result = run((str(root / 'build/autotools-app'),), cwd=root, env=client.env)
        assert result.returncode == 73, result
