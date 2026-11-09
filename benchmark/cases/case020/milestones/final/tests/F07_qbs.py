# feature: F07
"""Real Qbs consumption of generated dependency and profile inputs."""
from _helpers import write_file
from F01_helpers import cli_success
from F02_helpers import recipe_client, recipe_file
from F07_helpers import (NATIVE_SOURCE, compiled_usage_package,
                         native_command, offline_qbs)


def test_qbs_dependency_and_toolchain_usage(tmp_path):
    # F07.T10: both supported compiler families build the same native consumer.
    # Qbs defaults to a debug variant, so one arm selects Release.
    for compiler, version, configuration in (('gcc', '12', 'Release'), ('clang', '18', 'Debug')):
        area = tmp_path / compiler
        client = offline_qbs(recipe_client(area), area / 'tools')
        compiled_usage_package(client, area / 'package', linker_driver=False)
        root = area / 'consumer'
        recipe_file(root, '''    settings = "os", "arch", "compiler", "build_type"
    requires = "nativeusage/1.0"
    generators = "QbsDeps", "QbsProfile"
''')
        family_check = ('#ifndef __clang__\n#error Clang selection was not applied\n#endif\n'
                        if compiler == 'clang' else
                        '#ifdef __clang__\n#error GCC selection was not applied\n#endif\n')
        write_file(root / 'main.c', family_check + NATIVE_SOURCE.replace(
            '(int)(uintptr_t)&usage_link_value',
            '(int)(uintptr_t)&usage_link_value+TOOLCHAIN_COMPILE+(int)(uintptr_t)&caller_link_value')
            .replace('extern char usage_link_value;',
                     'extern char usage_link_value, caller_link_value;'))
        write_file(root / 'app.qbs', '''import qbs
CppApplication {
    name: "app"
    files: ["main.c"]
    consoleApplication: true
    destinationDirectory: project.buildDirectory + "/output"
    Depends { name: "nativeusage" }
    qbsModuleProviders: ["conan"]
    type: {
        if (qbs.buildVariant !== "%s" || qbs.architecture !== "x86_64" || !qbs.targetOS.contains("linux"))
            throw "Selected configuration or target platform was not applied";
        return ["application"];
    }
}
''' % configuration.lower())
        cli_success(client, 'install', root, '-nr', '-s', 'compiler='+compiler, '-s', 'compiler.version='+version,
                    '-s', 'compiler.libcxx=libstdc++11', '-s', 'build_type='+configuration,
                    '-c', 'tools.build:cflags=["-DTOOLCHAIN_COMPILE=13"]',
                    '-c', 'tools.build:exelinkflags=["-Wl,--defsym,caller_link_value=17"]')
        settings = str(root / 'qbs-settings')
        native_command(client, root, 'qbs', 'config', '--settings-dir', settings,
                       '--import', str(root / 'qbs_settings.txt'))
        native_command(client, root, 'qbs', 'build', '--settings-dir', settings,
                       '--build-directory', str(root / 'build'), '--file', str(root / 'app.qbs'),
                       'moduleProviders.conan.installDirectory:'+str(root))
        assert native_command(client, root, str(root / 'build/default/output/app')).text('stdout') == '111\n'
    # The build machine's own architecture is also Qbs's default, so a different
    # target is selected. Resolving evaluates the project without a target libc.
    target = tmp_path / 'target'
    recipe_file(target, '    settings = "os", "arch", "compiler", "build_type"\n    generators = "QbsProfile"\n')
    write_file(target / 'app.qbs', '''import qbs
Product {
    type: {
        if (qbs.architecture !== "x86")
            throw "Selected target platform was not applied";
        return ["application"];
    }
    Depends { name: "cpp" }
}
''')
    cli_success(client, 'install', target, '-nr', '-s', 'compiler=gcc', '-s', 'compiler.version=12',
                '-s', 'compiler.libcxx=libstdc++11', '-s', 'arch=x86')
    settings = str(target / 'qbs-settings')
    native_command(client, target, 'qbs', 'config', '--settings-dir', settings,
                   '--import', str(target / 'qbs_settings.txt'))
    native_command(client, target, 'qbs', 'resolve', '--settings-dir', settings,
                   '--build-directory', str(target / 'build'), '--file', str(target / 'app.qbs'))
