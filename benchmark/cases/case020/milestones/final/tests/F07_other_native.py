# feature: F07
"""Real Meson and SCons consumers using offline native-tool dependencies."""
import ctypes
from pathlib import Path

from _helpers import environment, write_file
from F01_helpers import cli_success
from F02_helpers import recipe_client, recipe_file
from F07_helpers import (CMAKE_SETTINGS, NATIVE_SOURCE, compiled_usage_package,
                         native_command, offline_native_tools, autotools_configure)


def test_meson_dependency_and_toolchain_usage(tmp_path):
    # F07.T02. Meson evaluates the generated native file and pkg-config inputs.
    client = offline_native_tools(recipe_client(tmp_path), tmp_path / 'tools')
    compiled_usage_package(client, tmp_path / 'package')
    root = tmp_path / 'consumer'
    recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = "nativeusage/1.0"
    generators = "MesonToolchain", "PkgConfigDeps"
''')
    write_file(root / 'main.c', NATIVE_SOURCE.replace(
        '(int)(uintptr_t)&usage_link_value',
        '(int)(uintptr_t)&usage_link_value+TOOLCHAIN_COMPILE+(int)(uintptr_t)&caller_link_value')
        .replace('extern char usage_link_value;',
                 'extern char usage_link_value, caller_link_value;'))
    # Both selections are read, since Meson has a build type of its own by default.
    for configuration in ('Release', 'Debug'):
        write_file(root / 'meson.build', '''project('consumer', 'c')
assert(get_option('buildtype') == '%s', 'Build configuration was not applied')
assert(host_machine.system() == 'linux' and host_machine.cpu_family() == 'x86_64', 'Target platform was not applied')
dep = dependency('nativeusage', method: 'pkg-config')
executable('app', 'main.c', dependencies: dep)
''' % configuration.lower())
        cli_success(client, 'install', root, '-nr', *CMAKE_SETTINGS, '-s', 'build_type='+configuration,
                    '-c', 'tools.build:cflags=["-DTOOLCHAIN_COMPILE=13"]',
                    '-c', 'tools.build:exelinkflags=["-Wl,--defsym,caller_link_value=17"]')
        build = 'build-' + configuration
        native_command(client, root, 'meson', 'setup', build,
                       '--native-file', str(root / 'velmora_meson_native.ini'))
        native_command(client, root, 'meson', 'compile', '-C', build)
        assert native_command(client, root, str(root / build / 'app')).text('stdout') == '111\n'


def test_scons_dependency_usage(tmp_path):
    # F07.T11. SCons loads the generated script itself; the test does not parse
    # or reimplement the dependency transform.
    client = offline_native_tools(recipe_client(tmp_path), tmp_path / 'tools')
    compiled_usage_package(client, tmp_path / 'package')
    root = tmp_path / 'consumer'
    recipe_file(root, '    requires = "nativeusage/1.0"\n    generators = "SConsDeps"\n')
    write_file(root / 'main.c', NATIVE_SOURCE)
    write_file(root / 'SConstruct', '''requirements = SConscript('SConscript_velmoradeps')
env = Environment()
env.MergeFlags(requirements['velmoradeps'])
env.Program('app', ['main.c'])
''')
    cli_success(client, 'install', root, '-nr')
    native_command(client, root, 'scons', '-Q')
    assert native_command(client, root, str(root / 'app')).text('stdout') == '81\n'


def test_premake_dependency_and_toolchain_usage(tmp_path):
    # F07.T09. Premake itself evaluates generated Lua, then Make builds the
    # consumer from that evaluated project.
    client = offline_native_tools(recipe_client(tmp_path), tmp_path / 'tools')
    compiled_usage_package(client, tmp_path / 'package')
    root = tmp_path / 'consumer'
    recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = "nativeusage/1.0"
    generators = "PremakeDeps", "PremakeToolchain"
''')
    write_file(root / 'main.c', NATIVE_SOURCE.replace(
        '(int)(uintptr_t)&usage_link_value',
        '(int)(uintptr_t)&usage_link_value+TOOLCHAIN_COMPILE+(int)(uintptr_t)&caller_link_value')
        .replace('extern char usage_link_value;',
                 'extern char usage_link_value, caller_link_value;'))
    write_file(root / 'premake5.lua', '''workspace "Consumer"
    configurations { "Release" }
    architecture "x86_64"
project "app"
    kind "ConsoleApp"
    language "C"
    files { "main.c" }
include "velmoratoolchain.premake5.lua"
project "app"
    local usage = velmoradeps["release_x86_64"]["nativeusage"]
    buildoptions(usage["cflags"])
    linkoptions(usage["exelinkflags"])
''')
    cli_success(client, 'install', root, '-nr', *CMAKE_SETTINGS,
                '-c', 'tools.build:cflags=["-DTOOLCHAIN_COMPILE=13"]',
                '-c', 'tools.build:exelinkflags=["-Wl,--defsym,caller_link_value=17"]')
    native_command(client, root, 'premake5', 'gmake2')
    native_command(client, root, 'make', 'config=release')
    assert native_command(client, root, str(root / 'bin/app')).text('stdout') == '111\n'


def test_premake_platform_standard_and_shared_choice(tmp_path):
    # F07.T18, Premake choices. Bazel selections are exercised in T08.
    # Both arms start from fresh homes and execute the same command sequence.
    for shared in (False, True):
        area = tmp_path / str(shared)
        client = offline_native_tools(recipe_client(area), area / 'tools')
        compiled_usage_package(client, area / 'package')
        root = area / 'consumer'
        recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = "nativeusage/1.0"
    options = {"shared": [True, False]}
    default_options = {"shared": False}
    generators = "PremakeDeps", "PremakeToolchain"
''')
        write_file(root / 'selected.cpp', '''#if !defined(__linux__) || !defined(__x86_64__)
#error Wrong target platform
#endif
template<class T> concept Addable = requires(T value) { value + 1; };
static_assert(Addable<int>);
extern "C" int selected(void) { return 23; }
''')
        write_file(root / 'main.cpp', '''#include <cstdio>
extern "C" int selected(void), probe(void);
extern "C" int __wrap_probe(void) { return 17; }
int main(void) { std::printf("%d\\n", selected()+probe()+TOOLCHAIN_COMPILE); }
''')
        write_file(root / 'premake5.lua', '''workspace "Choices"
    configurations { "Release" }
    architecture "x86_64"
project "selectedlibrary"
    language "C++"
    files { "selected.cpp" }
project "app"
    kind "ConsoleApp"
    language "C++"
    files { "main.cpp" }
    links { "selectedlibrary" }
include "velmoratoolchain.premake5.lua"
''')
        cli_success(client, 'install', root, '-nr', *CMAKE_SETTINGS,
                    '-s', 'compiler.cppstd=20', '-o', 'shared='+str(shared),
                    '-c', 'tools.build:cxxflags=["-DTOOLCHAIN_COMPILE=7"]',
                    '-c', 'tools.build:exelinkflags=["-Wl,--wrap,probe"]')
        native_command(client, root, 'premake5', 'gmake2')
        native_command(client, root, 'make', 'config=release')
        env = environment(client.env, updates={'LD_LIBRARY_PATH': str(root / 'bin')})
        assert native_command(client, root, str(root / 'bin/app'), env=env).text('stdout') == '47\n'
        if shared:
            library = ctypes.CDLL(str(root / 'bin/libselectedlibrary.so'))
            assert library.selected() == 23
        else:
            native_command(client, root, 'ar', 't', str(root / 'bin/libselectedlibrary.a'))


def test_autotools_dependency_and_toolchain_usage(tmp_path):
    # F07.T04. Use real configure/Make consumers for both build configurations.
    for configuration, expected in (('Debug', '112\n'), ('Release', '111\n')):
        area = tmp_path / configuration
        client = recipe_client(area)
        compiled_usage_package(client, area / 'package')
        root = area / 'consumer'
        recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = "nativeusage/1.0"
    generators = "AutotoolsDeps", "AutotoolsToolchain"
    def build(self):
        from velmora.tools.gnu import Autotools
        native = Autotools(self)
        native.configure()
        native.make()
''')
        configure = write_file(root / 'configure', autotools_configure())
        configure.chmod(0o755)
        source = NATIVE_SOURCE.replace(
            '(int)(uintptr_t)&usage_link_value',
            '(int)(uintptr_t)&usage_link_value+TOOLCHAIN_COMPILE+(int)(uintptr_t)&caller_link_value')
        source = source.replace('extern char usage_link_value;',
                                'extern char usage_link_value, caller_link_value;')
        source = source.replace('int main(void) {',
                                'int main(void) { int checked = 0; assert(++checked);')
        source = source.replace('usage()+', 'checked+usage()+')
        write_file(root / 'main.c', '''#include <assert.h>
#if !defined(__linux__) || !defined(__x86_64__)
#error Wrong target platform
#endif
''' + source)
        write_file(root / 'Makefile.in', '''CC = @CC@
CPPFLAGS = @CPPFLAGS@
CFLAGS = @CFLAGS@
LDFLAGS = @LDFLAGS@
LIBS = @LIBS@
app: main.c
\t$(CC) $(CPPFLAGS) $(CFLAGS) main.c -o app $(LDFLAGS) $(LIBS)
''')
        args = (*CMAKE_SETTINGS, '-s', 'build_type='+configuration,
                '-c', 'tools.build:cflags=["-DTOOLCHAIN_COMPILE=13"]',
                '-c', 'tools.build:exelinkflags=["-Wl,--defsym,caller_link_value=17"]')
        cli_success(client, 'install', root, '-nr', *args)
        cli_success(client, 'build', root, '-nr', *args)
        assert native_command(client, root, str(root / 'app')).text('stdout') == expected
