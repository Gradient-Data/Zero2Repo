# feature: F12
"""Acceptance of supplied native routines, objects, and translated clients."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import write_text
from F04_helpers import require_native_failure
from F12_helpers import prepare_native, prepare_c_native, wrapped_values, translated_values


@pytest.fixture
def native_library(tmp_path):
    return prepare_native(tmp_path / 'native_interop')


def test_wrap_routines_and_missing_dependency(native_library):
    session, oracle = native_library
    values = wrapped_values(session, '''
import json
import numpy as np
from native_api import score, pair, update
a = np.array([[1.,2.,3.],[4.,5.,6.]], order='F')
update(a)
print(json.dumps([score(4,-3), score(-7,5), *pair(9,-4), *a.flatten().tolist()]))
''')
    assert values == oracle[:4] + oracle[12:18]
    # Same valid declaration and module search path; only the link dependency changes.
    stub = (session.root / 'native_api.pyi').read_text()
    try:
        missing = write_text(session.root, 'native_api.pyi',
                             stub.replace('libraries="native_api"', 'libraries="absent_native_dependency"'))
        require_native_failure(session.command('wrap', missing, '--language', 'fortran'))
    finally:
        write_text(session.root, 'native_api.pyi', stub)


def test_native_names_overloads_and_objects(native_library):
    session, oracle = native_library
    values = wrapped_values(session, '''
import json
from native_api import select, Meter
m = Meter(8)
values = [select(-3), select(1.25), m.tally_value, m.value]
m.move(-2)
values += [m.tally_value, m.value]
m *= 4
values += [m.tally_value, m.value]
try:
    m.value = 100
except AttributeError:
    pass
else:
    raise AssertionError('Read-only property accepted assignment')
try:
    select('incompatible')
except TypeError:
    pass
else:
    raise AssertionError('Unmatched overload was accepted')
values += [m.tally_value, m.value]
print(json.dumps(values))
''')
    assert values == oracle[4:12] + oracle[10:12]


def test_translate_native_library_client(native_library):
    session, oracle = native_library
    values = translated_values(session, 'scalar_client', '''from native_api import score, pair, Meter
import numpy as np
from native_api import update
if __name__ == '__main__':
    print(score(4, -3))
    print(score(-7, 5))
    p, q = pair(9, -4)
    print(p)
    print(q)
    m = Meter(8)
    m.move(-2)
    m *= 4
    print(m.tally_value)
    print(m.value)
    a = np.ones((2,3), order='F')
    update(a)
    print(a[0,0])
    print(a[1,2])
''')
    assert values == oracle[:4] + oracle[10:12] + oracle[24:26]


def test_translate_fortran_array_mutations(native_library):
    session, oracle = native_library
    values = translated_values(session, 'array_client', '''from native_api import update
import numpy as np
if __name__ == '__main__':
    a = np.zeros((2,3), dtype=float, order='F')
    for i in range(2):
        for j in range(3):
            a[i,j] = float(3*i+j+1)
    update(a)
    for i in range(2):
        for j in range(3):
            print(a[i,j])
    update(a)
    for i in range(2):
        for j in range(3):
            print(a[i,j])
''')
    assert values == oracle[12:24]


def test_wrap_c_routines_and_missing_dependency(tmp_path):
    session, oracle = prepare_c_native(tmp_path / 'c_library')
    values = wrapped_values(session, '''
import json
from c_api import score, select
print(json.dumps([score(4,-3), score(-7,5), select(-3), select(1.25)]))
''')
    assert values == oracle[:4]
    stub = (session.root / 'c_api.pyi').read_text()
    try:
        missing = write_text(session.root, 'c_api.pyi', stub.replace(
            'libraries="c_api"', 'libraries="absent_native_dependency"'))
        require_native_failure(session.command('wrap', missing, '--language', 'c'))
    finally:
        write_text(session.root, 'c_api.pyi', stub)


def test_c_native_names_overloads_and_objects(tmp_path):
    session, oracle = prepare_c_native(tmp_path / 'c_objects')
    values = wrapped_values(session, '''
import json
from c_api import Meter, select
values = [select(-3), select(1.25)]
for start, step, factor in ((8,-2,4), (-5,3,-2)):
    meter = Meter(start)
    values += [meter.tally_value, meter.value]
    meter.move(step)
    values += [meter.tally_value, meter.value]
    meter *= factor
    values += [meter.tally_value, meter.value]
    before = (meter.tally_value, meter.value)
    try:
        meter.value = 100
    except AttributeError:
        pass
    else:
        raise AssertionError('Read-only property accepted assignment')
    assert (meter.tally_value, meter.value) == before
try:
    select('incompatible')
except TypeError:
    pass
else:
    raise AssertionError('Unmatched overload was accepted')
print(json.dumps(values))
''')
    assert values == oracle[2:]


def test_translate_c_native_library_client(tmp_path):
    session, oracle = prepare_c_native(tmp_path / 'c_client')
    source = '''from c_api import score, select, Meter
if __name__ == '__main__':
    print(score(4,-3))
    print(score(-7,5))
    print(select(-3))
    print(select(1.25))
'''
    for index, (start, step, factor) in enumerate(((8,-2,4), (-5,3,-2))):
        source += f'''    m{index} = Meter({start})
    print(m{index}.tally_value)
    print(m{index}.value)
    m{index}.move({step})
    print(m{index}.tally_value)
    print(m{index}.value)
    m{index} *= {factor}
    print(m{index}.tally_value)
    print(m{index}.value)
'''
    assert translated_values(session, 'client', source, language='c') == oracle
