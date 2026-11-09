"""Provision the judge account's noninteractive same-identity authorization."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys

# This is the runner's account, not a product account or a fixed numeric UID.
name = 'cbagent'
try:
    account = pwd.getpwnam(name)
except KeyError:
    subprocess.run(['useradd', '--create-home', '--user-group', '--shell', '/bin/bash', name], check=True)
    account = pwd.getpwnam(name)
if account.pw_uid == 0 or account.pw_gid == 0:
    raise RuntimeError('The judge account must have non-root UID and GID')

# Included files are ordered lexically. Override the runner's broader grant,
# including its run-as group grant, before allowing only the original identity.
policy = Path('/etc/sudoers.d/zz-judge-self')
policy.write_text(f'{name} ALL=(ALL:ALL) !ALL\n{name} ALL=({name}) NOPASSWD: ALL\n')
os.chown(policy, 0, 0)
policy.chmod(0o440)
subprocess.run(['visudo', '-c'], check=True)

prefix = ['runuser', '-u', name, '--', 'sudo', '-n']
probe = 'import json,os; print(json.dumps([os.geteuid(),os.getegid()]))'
result = subprocess.run(prefix + ['-u', name, sys.executable, '-c', probe],
                        check=True, capture_output=True, text=True)
if json.loads(result.stdout) != [account.pw_uid, account.pw_gid]:
    raise RuntimeError(f'Same-user execution changed identity: {result.stdout}')
print(f'Validated same-user UID/GID: {result.stdout.strip()}', flush=True)

other = pwd.getpwnam('nobody')
for selection in (['-u', 'root'], ['-u', '#0'], ['-u', other.pw_name],
                  ['-u', f'#{other.pw_uid}'], ['-u', name, '-g', 'root']):
    # Query authorization independently of authentication, then try execution.
    query = subprocess.run(['sudo', '-n', '-l', '-U', name] + selection + ['/usr/bin/id'],
                           capture_output=True, text=True)
    attempt = subprocess.run(prefix + selection + ['/usr/bin/id'], capture_output=True, text=True)
    if query.returncode == 0 or attempt.returncode == 0:
        raise RuntimeError(f'Unexpected authorization for {selection}: {query.stdout}{attempt.stdout}')
    print(f'Validated denied identity {selection}: {query.stderr}{attempt.stderr}', flush=True)
