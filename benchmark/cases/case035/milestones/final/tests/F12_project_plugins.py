# feature: F12
"""Provisioning checked through installation and later independent invocations."""
import shutil

from _helpers import make_environment, run_cli
import sys
import tarfile

from F01_helpers import project_cli, refused, succeeded
from F04_helpers import DistributionFactory
from F08_helpers import ASSETS, standalone_releases
from F09_helpers import direct_observation
from F11_helpers import installation_python
from F12_helpers import (global_extension, plugin_contribution, provisioning_project,
    provisioning_wheel, runtime_inventory, provisioning_environment, provisioning_repository)


def test_required_plugins_reuse_provision_and_disable(tmp_path, current_product_wheel):
    env = provisioning_environment(tmp_path, current_product_wheel)
    wheel = provisioning_wheel(tmp_path / 'release', env, '2.0.0')
    global_env = global_extension(tmp_path / 'global', env)
    # The installed compatible release has no obtainable distribution or cache.
    shutil.rmtree(tmp_path / 'global' / 'plugin-source')
    cache = tmp_path / 'cache'
    if cache.exists():
        shutil.rmtree(cache)
    with provisioning_repository(tmp_path, env, [wheel]) as url:
        reused = provisioning_project(tmp_path / 'reuse', url, 'acceptance-extension="^1.0"')
        succeeded(project_cli(reused, global_env, 'install'))
        plugin_contribution(reused, global_env, '1.0.0')
        for label, active in (('missing', env), ('different', global_env)):
            project = provisioning_project(tmp_path / label, url, 'acceptance-extension="^2.0"')
            succeeded(project_cli(project, active, 'install'))
            plugin_contribution(project, active, '2.0.0')
        disabled = provisioning_project(tmp_path / 'disabled', url, 'acceptance-extension="^2.0"')
        succeeded(project_cli(disabled, global_env, '--no-plugins', 'install'))
        # Re-enabling loading alone must still see the original global release.
        plugin_contribution(disabled, global_env, '1.0.0')


def test_plugin_constraints_and_runtime_markers(tmp_path, current_product_wheel):
    env = provisioning_environment(tmp_path, current_product_wheel)
    wheels = [provisioning_wheel(tmp_path / ('release-' + str(v)), env, str(v) + '.0.0')
              for v in (1, 2, 3)]
    wheels.append(provisioning_wheel(tmp_path / 'inapplicable', env, '1.0.0',
        name='inapplicable-extension', command='dormant-count'))
    # Use a real different Python in the project so evaluating its marker would
    # select the wrong requirement. The archive is the earlier feature's asset.
    release = next(r for r in standalone_releases() if r['implementation'] == 'cpython'
                   and not r['free_threaded']
                   and tuple(map(int, r['version'].split('.')[:2])) != sys.version_info[:2])
    extracted = tmp_path / 'interpreter'
    extracted.mkdir()
    with tarfile.open(ASSETS / release['asset']) as archive:
        archive.extractall(extracted, filter='data')
    interpreter, = extracted.glob('*/bin/python3')
    minor = '.'.join(map(str, sys.version_info[:2]))
    requirements = f"""acceptance-extension=[
        {{version=">=2,<3", markers="python_version == '{minor}'"}},
        {{version="^3", markers="python_version != '{minor}'"}}]
        inapplicable-extension={{version="*", markers="python_version == '0.1'"}}
    """
    with provisioning_repository(tmp_path, env, wheels) as url:
        project = provisioning_project(tmp_path / 'project', url, requirements)
        succeeded(project_cli(project, env, 'env', 'use', str(interpreter)))
        observed = direct_observation(installation_python(project, env), project, env)
        assert tuple(map(int, observed['version'].split('.')[:2])) != sys.version_info[:2]
        before = runtime_inventory(project, env)
        succeeded(project_cli(project, env, 'install'))
        plugin_contribution(project, env, '2.0.0')
        assert runtime_inventory(project, env) == before
        dormant_input = tmp_path / 'dormant-values.json'
        dormant_input.write_text('[12, 4]')
        dormant_env = make_environment(env, updates={'ACCEPTANCE_INPUT': str(dormant_input)})
        refused(project_cli(project, dormant_env, 'dormant-count'), 'dormant-count')


def test_project_plugin_isolation_and_runtime_conflict(tmp_path, current_product_wheel):
    env = provisioning_environment(tmp_path, current_product_wheel)
    global_env = global_extension(tmp_path / 'global', env)
    factory = DistributionFactory(tmp_path / 'runtime-package')
    _, retained = factory.create('runtime-anchor', '1.0')
    _, replacement = factory.create('runtime-anchor', '2.0')
    succeeded(run_cli((sys.executable, '-m', 'pip', '--python', env['F12_RUNTIME_PYTHON']),
        ('install', '--no-index', '--no-deps', str(retained)), cwd=tmp_path, env=env))
    wheels = [provisioning_wheel(tmp_path / 'release2', env, '2.0.0'),
              provisioning_wheel(tmp_path / 'release3', env, '3.0.0'),
              provisioning_wheel(tmp_path / 'conflict-release', env, '4.0.0',
                                 dependencies=('runtime-anchor>=2',)), retained, replacement]
    with provisioning_repository(tmp_path, env, wheels) as url:
        baseline = provisioning_project(tmp_path / 'baseline', url, '')
        before = runtime_inventory(baseline, global_env)
        projects = [provisioning_project(tmp_path / ('project-' + str(v)), url,
                    'acceptance-extension="^' + str(v) + '.0"') for v in (2, 3)]
        for project in projects:
            succeeded(project_cli(project, global_env, 'install'))
        for project, version in zip(projects, ('2.0.0', '3.0.0')):
            plugin_contribution(project, global_env, version)
        plugin_contribution(baseline, global_env, '1.0.0')
        assert runtime_inventory(baseline, global_env) == before
        conflict = provisioning_project(tmp_path / 'conflict', url,
                                        'acceptance-extension="^4.0"')
        refused(project_cli(conflict, env, 'install'), 'runtime-anchor', 'acceptance-extension')
        # The refused provisioning leaves no partial plugin contribution for that project.
        refused(project_cli(conflict, env, 'extension-count'), 'extension-count')
        assert runtime_inventory(baseline, global_env) == before
        plugin_contribution(baseline, global_env, '1.0.0')
