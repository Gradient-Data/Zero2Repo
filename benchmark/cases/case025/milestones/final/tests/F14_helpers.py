# feature: F14
"""Independent regular-expression syntax oracle for the running Python."""
import re


def regex_syntax_error(pattern):
    """Return the standard parser's rejection reason, or None for valid syntax."""
    try:
        re.compile(pattern)
    except re.error as error:
        return str(error)
    return None
