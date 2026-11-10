"""Install the public caller offline and validate its current runtime identity."""
import subprocess
import sys

subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
                '--no-build-isolation', '.'], check=True)
# A separate interpreter checks the installed import, without creating a binding
# file. The judge resolves again against its own import context at initialization.
subprocess.run([sys.executable, '-I', '-c',
                'import json; from xmlschema._public import binding; '
                'print("Schema caller initialization: " + json.dumps(binding, sort_keys=True))'],
               check=True)
