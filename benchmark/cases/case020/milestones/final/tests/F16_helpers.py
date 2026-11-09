# feature: F16
"""Real working-tree libraries and native consumers for editable acceptance."""
from pathlib import Path

from _helpers import write_file
from F01_helpers import cli_success, named_node
from F02_helpers import recipe_file
from F07_helpers import CMAKE_SETTINGS, cmake_command, native_command


def editable_mappings(client):
    return cli_success(client, 'editable', 'list', '--format=json').json('stdout')


def working_library(root, *, version='1.0', source='sources', build='artifacts'):
    root = Path(root)
    recipe_file(root, '''    package_type = "static-library"
    exports_sources = "*"
    def layout(self):
        self.folders.source = %r
        self.folders.build = %r
        self.cpp.source.components["api"].includedirs = ["public"]
        self.cpp.build.components["api"].includedirs = ["generated"]
        self.cpp.build.components["api"].libdirs = ["front"]
        self.cpp.build.components["base"].libdirs = ["foundation"]
        self.cpp.source.components["base"].includedirs = []
        self.cpp.build.components["base"].includedirs = []
    def build(self):
        import os, subprocess
        from velmora.tools.files import copy
        copy(self, "built.h", self.source_folder, os.path.join(self.build_folder, "generated"))
        for source, directory, library in (("base.c", "foundation", "foundation"),
                                           ("api.c", "front", "front")):
            destination = os.path.join(self.build_folder, directory)
            os.makedirs(destination, exist_ok=True)
            obj = os.path.join(destination, library + ".o")
            subprocess.check_call(["gcc", "-c", os.path.join(self.source_folder, source), "-o", obj])
            subprocess.check_call(["ar", "rcs", os.path.join(destination, "lib" + library + ".a"), obj])
    def package(self):
        import os
        from velmora.tools.files import copy
        copy(self, "*.h", os.path.join(self.source_folder, "public"), os.path.join(self.package_folder, "include"))
        copy(self, "built.h", os.path.join(self.build_folder, "generated"), os.path.join(self.package_folder, "include"))
        copy(self, "*.a", self.build_folder, os.path.join(self.package_folder, "lib"), keep_path=False)
    def package_info(self):
        self.cpp_info.components["base"].libs = ["foundation"]
        self.cpp_info.components["api"].libs = ["front"]
        self.cpp_info.components["api"].requires = ["base"]
''' % (source, build), name='worklib', version=version)
    update_working_library(root / source, header=7, generated=11, library=23)
    write_file(root / source / 'api.c', 'int base(void); int api(void) { return base() + 5; }\n')
    return root


def update_working_library(source, *, header, generated, library):
    source = Path(source)
    write_file(source / 'public/work.h', '#define SOURCE_VALUE %d\nint api(void);\n' % header)
    write_file(source / 'built.h', '#define BUILD_VALUE %d\n' % generated)
    write_file(source / 'base.c', 'int base(void) { return %d; }\n' % library)


def build_working_library(client, root, *, output=None):
    cli_success(client, 'build', root, '-nr', *(('-of', output) if output is not None else ()))


def native_editable_consumer(client, root, reference):
    root = Path(root)
    recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = %r
    generators = "CMakeDeps"
''' % reference)
    write_file(root / 'main.c', '''#include <stdio.h>
#include <work.h>
#include <built.h>
int main(void) { printf("%d %d %d\\n", SOURCE_VALUE, BUILD_VALUE, api()); return 0; }
''')
    write_file(root / 'CMakeLists.txt', '''cmake_minimum_required(VERSION 3.23)
project(EditableConsumer C)
find_package(worklib REQUIRED)
add_executable(app main.c)
target_link_libraries(app PRIVATE worklib::api)
''')
    report = cli_success(client, 'install', root, '-nr', '--format=json',
                         *CMAKE_SETTINGS).json('stdout')
    cmake_command(client, root, '-S', str(root), '-B', str(root / 'native'),
                  '-DCMAKE_PREFIX_PATH=' + str(root), '-DCMAKE_BUILD_TYPE=Release')
    cmake_command(client, root, '--build', str(root / 'native'))
    result = native_command(client, root, str(root / 'native/app')).text('stdout')
    return named_node(report, 'worklib'), result
