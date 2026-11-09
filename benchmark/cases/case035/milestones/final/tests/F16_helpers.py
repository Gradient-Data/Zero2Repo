# feature: F16
"""Executable applications used to observe real command execution."""
from F01_helpers import BUILD_SYSTEM, write_project


EXECUTION_PROBE = '''import json, sys
import execution_dependency
print(json.dumps({"prefix": sys.prefix, "argv": sys.argv[2:],
                  "dependency": execution_dependency.value()}))
print("application stderr", file=sys.stderr)
sys.exit(int(sys.argv[1]))
'''


CONSOLE_APPLICATION = '''import json, sys

def report(operation, value):
    print(json.dumps({"operation": operation, "value": value,
                      "argv": sys.argv[2:], "prefix": sys.prefix}))
    print("console stderr", file=sys.stderr)
    return int(sys.argv[1])

def add():
    return report("sum", sum(int(v) for v in sys.argv[2:]))

def multiply():
    import math
    return report("product", math.prod(int(v) for v in sys.argv[2:]))
'''


def execution_project(path, *, scripts=""):
    document = '''[project]
name = "execution-subject"
version = "1.0"
requires-python = ">=3.9"
dependencies = []
''' + scripts + BUILD_SYSTEM
    return write_project(path, document, module="execution_subject")
