# feature: F07
"""Real native consumers of generated dependency usage information."""
import shlex
import shutil
import sys
import tarfile
from pathlib import Path

from _helpers import Client, HelperError, environment, run, write_file
from F01_helpers import cli_success
from F02_helpers import recipe_file


def native_command(client, cwd, *args, env=None):
    result = run(args, cwd=cwd, env=client.env if env is None else env)
    assert result.returncode == 0, result
    return result


def compiled_usage_package(client, root, *, components=False, linker_driver=True):
    # All source and archives are real fixture artifacts, compiled by GCC.
    body = '''    package_type = "static-library"
    def package(self):
        import os, subprocess
        from velmora.tools.files import save
        inc = os.path.join(self.package_folder, "include")
        lib = os.path.join(self.package_folder, "lib")
        os.makedirs(lib, exist_ok=True)
        save(self, os.path.join(inc, "usage.h"), "int usage(void);\\n")
        save(self, "base.c", "#include <math.h>\\nint base(void) { volatile double x=3.9; return 23+(int)floor(x); }\\n")
        save(self, "front.c", "int base(void); int usage(void) { return base(); }\\n")
        for name in ("base", "front"):
            subprocess.check_call(["gcc", "-c", name+".c", "-o", name+".o"])
            subprocess.check_call(["ar", "rcs", os.path.join(lib, "lib"+name+".a"), name+".o"])
    def package_info(self):
'''
    if components:
        body += '''        self.cpp_info.components["foundation"].libs = ["base"]
        self.cpp_info.components["foundation"].system_libs = ["m"]
        self.cpp_info.components["api"].libs = ["front"]
        self.cpp_info.components["api"].requires = ["foundation"]
        info = self.cpp_info.components["api"]
'''
    else:
        body += '''        self.cpp_info.libs = ["front", "base"]
        self.cpp_info.system_libs = ["m"]
        info = self.cpp_info
'''
    body += '''        info.defines = ["USAGE_DEFINITION=11"]
        info.cflags = ["-DUSAGE_CFLAG=7"]
        info.exelinkflags = ["-no-pie", "-Wl,--defsym,usage_link_value=37"]
'''
    if not linker_driver:
        body = body.replace('-Wl,--defsym,usage_link_value=37', '--defsym=usage_link_value=37')
    path = recipe_file(root, body, name='nativeusage', version='1.0')
    cli_success(client, 'create', path.parent, '-nr')


NATIVE_SOURCE = '''#include <usage.h>
#include <stdint.h>
#include <stdio.h>
extern char usage_link_value;
int main(void) {
    printf("%d\\n", usage()+USAGE_DEFINITION+USAGE_CFLAG+(int)(uintptr_t)&usage_link_value);
    return 0;
}
'''


def make_usage_consumer(client, root, generated):
    root = Path(root)
    write_file(root / 'main.c', NATIVE_SOURCE)
    write_file(root / 'Makefile', f'''VELMORA_INCLUDE_DIR_FLAG = -I
VELMORA_LIB_DIR_FLAG = -L
VELMORA_LIB_FLAG = -l
VELMORA_SYSTEM_LIB_FLAG = -l
VELMORA_DEFINE_FLAG = -D
include {Path(generated) / 'velmoradeps.mk'}
app: main.c
\tgcc $(VELMORA_INCLUDE_DIRS) $(VELMORA_DEFINES) $(VELMORA_CFLAGS) main.c -o app $(VELMORA_LIB_DIRS) $(VELMORA_LIBS) $(VELMORA_SYSTEM_LIBS) $(VELMORA_EXELINKFLAGS)
''')
    native_command(client, root, 'make')
    return native_command(client, root, str(root / 'app')).text('stdout')


def pkgconfig_usage_consumer(client, root, generated, module):
    root = Path(root)
    write_file(root / 'main.c', NATIVE_SOURCE)
    env = environment(client.env, updates={'PKG_CONFIG_PATH': str(generated),
                                           'PKG_CONFIG_LIBDIR': str(generated)})
    flags = native_command(client, root, 'pkg-config', '--cflags', '--libs', module,
                           env=env).text('stdout')
    # pkg-config publishes shell-escaped compiler arguments; shlex reads that
    # format without guessing field order or matching generated text.
    native_command(client, root, 'gcc', 'main.c', '-o', 'app', *shlex.split(flags), env=env)
    return native_command(client, root, str(root / 'app')).text('stdout')


def cmake_command(client, cwd, *args):
    # Use the same lookup environment as recipe-internal native commands.
    executable = shutil.which('cmake', path=client.env['PATH'])
    if executable is None:
        raise HelperError(f"CMake prerequisite not executable on PATH={client.env['PATH']!r}")
    return native_command(client, cwd, executable, *args)


CMAKE_SETTINGS = ('-s', 'compiler=gcc', '-s', 'compiler.version=12',
                  '-s', 'compiler.libcxx=libstdc++11')


def cmake_usage_project(root, *, components=False):
    root = Path(root)
    target = 'nativeusage::api' if components else 'nativeusage::nativeusage'
    write_file(root / 'main.c', NATIVE_SOURCE.replace(
        '(int)(uintptr_t)&usage_link_value',
        '(int)(uintptr_t)&usage_link_value+TOOLCHAIN_COMPILE+(int)(uintptr_t)&caller_link_value')
        .replace('extern char usage_link_value;',
                 'extern char usage_link_value, caller_link_value;'))
    write_file(root / 'CMakeLists.txt', f'''cmake_minimum_required(VERSION 3.23)
project(Consumer C)
if(NOT CMAKE_BUILD_TYPE STREQUAL "Debug")
  message(FATAL_ERROR "Selected build configuration was not applied")
endif()
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "Selected target platform was not applied")
endif()
find_package(nativeusage REQUIRED)
add_executable(app main.c)
target_link_libraries(app PRIVATE {target})
''')


def cmake_usage_consumer(client, root):
    root = Path(root)
    cmake_command(client, root, '--preset', 'velmora-debug')
    cmake_command(client, root, '--build', '--preset', 'velmora-debug')
    return native_command(client, root, str(root / 'build/app')).text('stdout')


def offline_native_tools(client, root):
    """Install the unmodified PyPI native-tool wheels and Premake release offline."""
    root = Path(root)
    site = root / 'site'
    native_command(client, client.cwd, sys.executable, '-m', 'pip', 'install',
                   '--no-index', '--no-deps', '--target', str(site),
                   *(str(p) for p in sorted(TOOL_ASSETS.glob('*.whl'))))
    premake = site / 'bin/premake5'
    with tarfile.open(TOOL_ASSETS / 'premake-5.0.0-beta2-linux.tar.gz') as archive:
        premake.write_bytes(archive.extractfile('./premake5').read())
    premake.chmod(0o755)
    env = environment(client.env, updates={
        'PATH': str(site / 'bin') + ':' + client.env['PATH'],
        'PYTHONPATH': str(site) + ':' + client.env['PYTHONPATH']})
    return Client(client.command, client.cwd, env)


def offline_bazel(root):
    """Copy the unmodified Bazel release executable and rules_cc into a distdir."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TOOL_ASSETS / 'rules_cc-0.0.2.tar.gz', root / 'rules_cc-0.0.2.tar.gz')
    executable = root / 'bazel'
    shutil.copyfile(TOOL_ASSETS / 'bazel-6.5.0-linux-x86_64', executable)
    executable.chmod(0o755)
    return executable


def offline_qbs(client, root):
    """Unpack the Qbs release and Ubuntu's GLib runtime without changing the image."""
    root = Path(root)
    with tarfile.open(TOOL_ASSETS / 'qbs-linux-x86_64-2.5.0.tar.gz') as archive:
        archive.extractall(root, filter='data')
    qbs = root / 'qbs-linux-x86_64-2.5.0'
    # The Qbs release links against GLib, which the image does not provide.
    glib = root / 'glib'
    native_command(client, client.cwd, 'dpkg-deb', '-x',
                   str(TOOL_ASSETS / 'libglib2.0-0t64_2.80.0-6ubuntu3.10_amd64.deb'), str(glib))
    env = environment(client.env, updates={
        'PATH': str(qbs / 'bin') + ':' + client.env['PATH'],
        'LD_LIBRARY_PATH': str(qbs / 'lib') + ':' + str(glib / 'usr/lib/x86_64-linux-gnu')})
    return Client(client.command, client.cwd, env)


def autotools_configure():
    """Bytes of the Autoconf 2.71 configure script generated from F07_autotools/configure.ac."""
    return (Path(__file__).with_name('F07_autotools') / 'configure').read_bytes()


# Official upstream release files, fetched with the hidden tests (test_assets.json).
TOOL_ASSETS = Path(__file__).with_name('F07_assets')
