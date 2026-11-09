# feature: F10
"""Harbor task documents and isolated public-source observations."""
import functools
import json
from pathlib import Path

from _helpers import deadline, run_python


def harbor_source_test(function):
    """Keep product imports bound to the product built by the acceptance harness."""
    @functools.wraps(function)
    def execute(tmp_path):
        source = '''
import sys
from pathlib import Path
source = Path('/app/src')
if not (source / 'velnora/__init__.py').is_file():
    raise RuntimeError('Mounted product source is missing')
sys.path.insert(0, str(source))
sys.path.insert(0, sys.argv[1])
from F10_harbor import FUNCTION
FUNCTION.__wrapped__(Path(sys.argv[2]))
'''.replace('FUNCTION', function.__name__)
        result = run_python(source, timeout=150,
                            args=(str(Path(__file__).parent), str(tmp_path)))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def harbor_task(root, relative, *, name, instruction, marker):
    """Write a real task and return independent expected configuration and file names."""
    directory = root / relative
    directory.mkdir(parents=True)
    config = {
        'schema_version': '1.0',
        'task': {'name': name, 'description': 'Inspect ' + name,
                 'keywords': ['inspection', name]},
        'metadata': {'owner': name, 'tags': ['offline', 'small'], 'weight': 2.5},
        'environment': {'cpus': 2, 'memory_mb': 1024},
        'verifier': {'timeout_sec': 45.0},
        'steps': [{'name': 'inspect', 'type': 'user'}],
    }
    text = ('schema_version = "1.0"\n'
            '[task]\nname = ' + json.dumps(name) + '\n'
            'description = ' + json.dumps('Inspect ' + name) + '\n'
            'keywords = ["inspection", ' + json.dumps(name) + ']\n'
            '[metadata]\nowner = ' + json.dumps(name) + '\n'
            'tags = ["offline", "small"]\nweight = 2.5\n'
            '[environment]\ncpus = 2\nmemory_mb = 1024\n'
            '[verifier]\ntimeout_sec = 45.0\n'
            '[[steps]]\nname = "inspect"\ntype = "user"\n')
    script = '#!/bin/sh\nprintf executed > ' + "'" + str(marker) + "'\n"
    files = {'task.toml': text, 'instruction.md': instruction,
             'steps/inspect/instruction.md': 'This is a separate step, not the top-level instruction.\n',
             'environment/Dockerfile': 'FROM scratch\nRUN ' + script.split('\n')[1] + '\n',
             'tests/test.sh': script, 'solution/solve.sh': script,
             'agent.py': 'from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("executed")\n',
             'assets/details.txt': 'Static task attachment.\n'}
    for relative_file, content in files.items():
        path = directory / relative_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        if relative_file.endswith('.sh'):
            path.chmod(0o755)
    return config, set(files)


def harbor_rows(root, **kwargs):
    from velnora import load_dataset
    with deadline(60):
        result = load_dataset(str(root), **kwargs)
        return {name: list(split) for name, split in result.items()}
