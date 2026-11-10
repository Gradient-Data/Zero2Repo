# feature: F07
"""File-based option contrasts, reusing the existing CLI/configuration transport."""
from textwrap import dedent
from _helpers import workspace, read_json
from F02_helpers import config_file, check_configured


def check_object_options(source, *, flags=(), expected=()):
    """Return diagnostics for a failing check, or None for a verified clean run."""
    with workspace({'objects.py': dedent(source).lstrip('\n')}) as root:
        config = config_file(root, 'unused_variable = false\n')
        result = check_configured(root, config, [root / 'objects.py'], flags,
                                  [('objects.py', line, code) for line, code in expected])
        if expected:
            return read_json(root / 'report.json', result=result)
        # check_configured has verified status zero and an empty error channel.
        return None
