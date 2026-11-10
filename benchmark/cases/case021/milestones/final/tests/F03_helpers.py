# feature: F03
"""Independent C oracle and application-level rejection assertions."""
from _helpers import temporary_project, tool_path, build_native, run_command, parse_json


def c_observation(body):
    """Compile an independent ISO C consumer emitting one JSON document."""
    with temporary_project() as project:
        source = project.write('oracle.c', '#include <stdio.h>\n#include <stddef.h>\n'
                               '#include <stdint.h>\n#include <complex.h>\n'
                               'int main(void) {\n' + body + '\nreturn 0;\n}\n')
        binary = project.path('oracle')
        build_native(tool_path('cc'), [source], binary,
                     before=['-std=c17']).check_returncode()
        result = run_command([binary]).check_returncode()
        return parse_json(result.stdout)


# Included in the fresh driver process, so expected rejections cannot hide a
# failed build, import or an unrelated exception.
REJECTIONS = '''
def rejects(kind, call, *args):
    try:
        call(*args)
    except kind:
        return
    raise AssertionError("Expected " + kind.__name__)
'''

AGGREGATES = '''
cdef struct Record:
    int count
    double weight

def record(value):
    cdef Record item = value
    item.count += 7
    item.weight *= 2
    return item

def array(value):
    cdef int items[3]
    items = value
    items[1] += 7
    return items

def packed(value):
    cdef (int, double) pair = value
    pair = (pair[0] + 7, pair[1] * 2)
    return pair
'''
