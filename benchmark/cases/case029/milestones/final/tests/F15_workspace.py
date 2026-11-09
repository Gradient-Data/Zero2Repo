# feature: F15
"""Workspace content, authority boundaries, permissions and environments."""
import io
import json
import os
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

import pytest

from _helpers import bounded, environment, run_process
from F15_helpers import local_workspace, workspace_bytes, workspace_command
from velmora.sandbox import Manifest, Permissions, SandboxError, SandboxPathGrant
from velmora.sandbox.entries import Dir, File, GitRepo, LocalDir, LocalFile
from velmora.sandbox.manifest import Environment
from velmora.sandbox.sandboxes.unix_local import UnixLocalSandboxClient


@pytest.mark.asyncio
async def test_f15_t01(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'document').write_bytes(b'copied bytes\x00\xff')
    (source / 'nested').mkdir()
    (source / 'nested' / 'record').write_bytes(b'directory content')
    # A second level and a sibling file distinguish a recursive copy from a shallow one.
    (source / 'nested' / 'deeper' / 'deepest').mkdir(parents=True)
    (source / 'nested' / 'deeper' / 'second').write_bytes(b'second level')
    (source / 'nested' / 'deeper' / 'deepest' / 'third').write_bytes(b'third level')
    repo = tmp_path / 'history.git'
    repo.mkdir()
    def git(*args):
        result = run_process(['git', '-C', str(repo), *args])
        assert result.returncode == 0, result.stderr
        return result.stdout.decode().strip()
    git('init')
    git('config', 'user.email', 'workspace@example.invalid')
    git('config', 'user.name', 'Workspace author')
    (repo / 'version').write_text('chosen revision')
    git('add', '.')
    git('commit', '-m', 'First revision')
    git('tag', 'selected')
    (repo / 'version').write_text('later revision')
    git('commit', '-am', 'Later revision')
    monkeypatch.chdir(tmp_path)
    # Git's standard URL rewriting uses a real offline repository, not a fake client.
    with environment({'GIT_CONFIG_COUNT': '1',
                      'GIT_CONFIG_KEY_0': f'url.{tmp_path.as_uri()}/.insteadOf',
                      'GIT_CONFIG_VALUE_0': 'https://offline.invalid/'}):
        manifest = Manifest(entries={
            'created': Dir(children={'data': File(content=b'declared content')}),
            'copy': LocalFile(src=Path('source/document')),
            'tree': LocalDir(src=Path('source/nested')),
            'checkout': GitRepo(host='offline.invalid', repo='history', ref='selected'),
        }, environment=Environment(value={'WORKSPACE_DECLARED': 'manifest value'}))
        async with local_workspace(manifest) as session:
            for path, expected in [('created/data', b'declared content'),
                                   ('copy', b'copied bytes\x00\xff'),
                                   ('tree/record', b'directory content'),
                                   ('tree/deeper/second', b'second level'),
                                   ('tree/deeper/deepest/third', b'third level'),
                                   ('checkout/version', b'chosen revision')]:
                assert await workspace_bytes(session, path) == expected
            result = await workspace_command(session, 'cat created/data; printf "|%s" "$WORKSPACE_DECLARED"')
            assert result.exit_code == 0
            assert result.stdout == b'declared content|manifest value'


@pytest.mark.asyncio
async def test_f15_t02(tmp_path):
    outside = tmp_path / 'protected'
    outside.write_bytes(b'unchanged')
    async with local_workspace(Manifest(entries={'safe': File(content=b'inside')})) as session:
        assert await workspace_bytes(session, 'safe') == b'inside'
        for escaping in (outside, '../protected', 'safe/../../protected'):
            with pytest.raises(SandboxError):
                await workspace_bytes(session, escaping)
        for escaping in (outside, Path('../protected'), Path('safe/../../protected')):
            with pytest.raises(SandboxError):
                await bounded(session.write(escaping, io.BytesIO(b'forbidden')))
        assert outside.read_bytes() == b'unchanged'
    for destination in (str(outside), '../protected', 'inner/../../protected'):
        with pytest.raises(SandboxError):
            manifest = Manifest(root=str(tmp_path / 'workspace'),
                                entries={destination: File(content=b'forbidden')})
            async with local_workspace(manifest):
                pytest.fail('Invalid manifest destination was accepted')
        assert outside.read_bytes() == b'unchanged'


@pytest.mark.asyncio
async def test_f15_t03(tmp_path, monkeypatch):
    cwd = tmp_path / 'project'
    cwd.mkdir()
    (cwd / 'local').write_bytes(b'working directory input')
    external = tmp_path / 'external'
    external.mkdir()
    (external / 'source').write_bytes(b'granted input')
    # A sibling whose name merely extends the granted directory name is not inside the grant.
    sibling = tmp_path / 'external-sibling'
    sibling.mkdir()
    (sibling / 'source').write_bytes(b'sibling input')
    monkeypatch.chdir(cwd)
    async with local_workspace(Manifest(entries={'copy': LocalFile(src=Path('local'))})) as session:
        assert await workspace_bytes(session, 'copy') == b'working directory input'
    with pytest.raises(SandboxError):
        async with local_workspace(Manifest(entries={'copy': LocalFile(src=external / 'source')})):
            pytest.fail('Unauthorized source was copied')
    for read_only in (True, False):
        manifest = Manifest(entries={'copy': LocalFile(src=external / 'source')},
                            extra_path_grants=(SandboxPathGrant(path=str(external), read_only=read_only),))
        async with local_workspace(manifest) as session:
            assert await workspace_bytes(session, 'copy') == b'granted input'
            assert await workspace_bytes(session, external / 'source') == b'granted input'
            with pytest.raises(SandboxError):
                await workspace_bytes(session, sibling / 'source')
            with pytest.raises(SandboxError):
                await bounded(session.write(sibling / 'source', io.BytesIO(b'updated sibling')))
            assert (sibling / 'source').read_bytes() == b'sibling input'
            if read_only:
                with pytest.raises(SandboxError):
                    await bounded(session.write(external / 'source', io.BytesIO(b'updated input')))
                assert (external / 'source').read_bytes() == b'granted input'
            else:
                await bounded(session.write(external / 'source', io.BytesIO(b'updated input')))
                assert (external / 'source').read_bytes() == b'updated input'
                (external / 'source').write_bytes(b'granted input')
    with pytest.raises(SandboxError):
        async with local_workspace(Manifest(entries={'copy': LocalFile(src=sibling / 'source')},
                extra_path_grants=(SandboxPathGrant(path=str(external), read_only=True),))):
            pytest.fail('A source outside the granted directory was copied')
    with pytest.raises(ValueError):
        await bounded(UnixLocalSandboxClient().create(manifest=Manifest(extra_path_grants=(
            SandboxPathGrant(path='/mapped-source', host_path=str(external)),))))


@pytest.mark.asyncio
async def test_f15_t08():
    token = os.urandom(16).hex()
    allowed = token.encode()
    script = f'#!/bin/sh\nprintf %s {token}'.encode()
    # Select the owner observed inside a real session, then qualify that explicit
    # selection before any restrictive manifest or expected-denial capture exists.
    with TemporaryDirectory(prefix='permission-workspace-') as root:
        async with local_workspace(Manifest(root=root, entries={
                'probe': File(content=allowed)})) as session:
            result = await workspace_command(session, sys.executable, '-c',
                'import json,os,pwd; print(json.dumps({"name":pwd.getpwuid(os.geteuid()).pw_name,"uid":os.geteuid(),"gid":os.getegid()}))',
                shell=False)
            assert result.exit_code == 0, (result.stdout, result.stderr)
            owner = json.loads(result.stdout)
            assert owner['uid'] == os.geteuid() != 0, owner
            assert owner['gid'] == os.getegid(), owner
            identity = owner['name']
            probe = ('import json,os; from pathlib import Path; '
                     'p=Path("probe"); print(json.dumps({'
                     '"uid":os.geteuid(),"gid":os.getegid(),"cwd":os.getcwd(),'
                     '"root_owner":Path(".").stat().st_uid,"file_owner":p.stat().st_uid,'
                     '"content":p.read_bytes().hex()}))')
            result = await workspace_command(session, sys.executable, '-c', probe,
                                             shell=False, user=identity)
            assert result.exit_code == 0, (result.stdout, result.stderr)
            observed = json.loads(result.stdout)
            assert observed == {
                'uid': owner['uid'], 'gid': owner['gid'],
                'cwd': str(Path(root).resolve()), 'root_owner': owner['uid'],
                'file_owner': owner['uid'], 'content': allowed.hex(),
            }, observed
            assert await workspace_bytes(session, 'probe', user=identity) == allowed
            print('Permission setup:', json.dumps({'identity': identity, **observed}))

        manifest = Manifest(root=root, entries={
            'probe': File(content=allowed),
            'default-script': File(content=script),
            'readable': File(content=allowed, permissions=Permissions(owner=4, group=0, other=0)),
            'private': File(content=token[::-1].encode(), permissions=Permissions(owner=0, group=0, other=0)),
        })
        async with local_workspace(manifest) as session:
            # Recheck execution context after provisioning the restrictive manifest.
            result = await workspace_command(session, sys.executable, '-c', probe,
                                             shell=False, user=identity)
            assert result.exit_code == 0, (result.stdout, result.stderr)
            assert json.loads(result.stdout) == observed
            assert await workspace_bytes(session, 'readable', user=identity) == allowed
            result = await workspace_command(session, 'cat readable', user=identity)
            assert result.exit_code == 0 and result.stdout == allowed, (result.stdout, result.stderr)
            assert await workspace_bytes(session, 'default-script', user=identity) == script
            result = await workspace_command(session, './default-script', user=identity)
            assert result.exit_code == 0 and result.stdout == allowed, (result.stdout, result.stderr)
            result = await workspace_command(session,
                f'printf %s {token} >> default-script && cat default-script', user=identity)
            assert result.exit_code == 0 and result.stdout == script + allowed, (result.stdout, result.stderr)
            await bounded(session.write(Path('default-script'), io.BytesIO(script), user=identity))
            assert await workspace_bytes(session, 'default-script', user=identity) == script
            result = await workspace_command(session, 'cat default-script', user=identity)
            assert result.exit_code == 0 and result.stdout == script, (result.stdout, result.stderr)
            for command in ('cat private', 'printf forbidden > readable'):
                result = await workspace_command(session, command, user=identity)
                assert result.exit_code != 0, (command, result.stdout, result.stderr)
                assert result.stderr
            assert await workspace_bytes(session, 'readable', user=identity) == allowed
            result = await workspace_command(session, 'cat readable', user=identity)
            assert result.exit_code == 0 and result.stdout == allowed, (result.stdout, result.stderr)
            # The SDK's own file operations honour the same qualified identity.
            with pytest.raises(SandboxError):
                await workspace_bytes(session, 'private', user=identity)
            with pytest.raises(SandboxError):
                await bounded(session.write(Path('readable'), io.BytesIO(b'forbidden'), user=identity))
            assert await workspace_bytes(session, 'readable', user=identity) == allowed
            result = await workspace_command(session, 'cat readable', user=identity)
            assert result.exit_code == 0 and result.stdout == allowed, (result.stdout, result.stderr)
            # Native metadata verifies all three access classes and file ownership.
            result = await workspace_command(session, sys.executable, '-c',
                'import json,os,stat; print(json.dumps({p:[stat.S_IMODE(os.stat(p).st_mode),os.stat(p).st_uid] for p in ["default-script","readable","private"]}))',
                shell=False, user=identity)
            assert result.exit_code == 0, (result.stdout, result.stderr)
            assert json.loads(result.stdout) == {
                'default-script': [0o755, owner['uid']],
                'readable': [0o400, owner['uid']], 'private': [0, owner['uid']],
            }
    for accounts in ({'users': [{'name': 'declared-user'}]},
                     {'groups': [{'name': 'declared-group', 'users': []}]}):
        with pytest.raises(ValueError):
            async with local_workspace(Manifest(**accounts)):
                pytest.fail('Unix-local account declarations were accepted.')


@pytest.mark.asyncio
async def test_f15_t09():
    command = 'import json,os; print(json.dumps({k:os.environ.get(k) for k in ["WORKSPACE_KEEP","WORKSPACE_DROP","WORKSPACE_OVERRIDE"]}))'
    with environment({'WORKSPACE_KEEP': 'host keep', 'WORKSPACE_DROP': 'host drop',
                      'WORKSPACE_OVERRIDE': 'host original'}):
        for filtered in (False, True):
            client = (UnixLocalSandboxClient(inherit_host_environment=False,
                        host_environment_allowlist={'WORKSPACE_KEEP', 'WORKSPACE_OVERRIDE'})
                      if filtered else UnixLocalSandboxClient())
            manifest = Manifest(environment=Environment(value={'WORKSPACE_OVERRIDE': 'manifest wins'}))
            async with local_workspace(manifest, client=client) as session:
                result = await workspace_command(session, sys.executable, '-c', command, shell=False)
                assert result.exit_code == 0
                assert json.loads(result.stdout) == {
                    'WORKSPACE_KEEP': 'host keep',
                    'WORKSPACE_DROP': None if filtered else 'host drop',
                    'WORKSPACE_OVERRIDE': 'manifest wins',
                }
