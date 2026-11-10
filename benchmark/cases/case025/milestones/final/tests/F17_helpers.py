# feature: F17
"""File-backed declarative typing observations using existing CLI helpers."""
from textwrap import dedent
from _helpers import workspace, read_json
from F02_helpers import config_file, check_configured


def check_evaluated_source(source):
    """Return diagnostics after checking status, channel, locations and codes.

    Successful file checks produce no JSON artifact; their public outcome is
    status zero with an empty error channel, and this helper returns None.
    """
    source = dedent(source).lstrip('\n')
    expected = []
    for line, text in enumerate(source.splitlines(), 1):
        if '# E: ' in text:
            expected.extend(('subject.py', line, code)
                            for code in text.split('# E: ', 1)[1].split(', '))
    source = '\n'.join(text.split('# E: ', 1)[0].rstrip()
                       for text in source.splitlines()) + '\n'
    with workspace({'subject.py': source}) as root:
        config = config_file(root, 'unused_variable = false\n')
        result = check_configured(root, config, [root / 'subject.py'], expected=expected)
        if expected:
            return read_json(root / 'report.json', result=result)
        return None
