# feature: F12
"""Acceptance checks for persistent array and group user attributes."""
from F12_helpers import check_attribute_changes


def test_f12_t01(tmp_path):
    for version in (2, 3):
        for kind in ('array', 'group'):
            observed = check_attribute_changes('''
assert dict(node.attrs) == {}
values = {
    'title': '测量 café',
    'nested': {'samples': [3, None, False, {'offset': -2.5}], 'empty': {}},
    'active': True,
    'count': 17,
    'empty': [],
}
for key, value in values.items():
    node.attrs[key] = value
assert set(node.attrs) == set(values)
for key, value in values.items():
    assert key in node.attrs
    assert node.attrs[key] == value
assert 'missing' not in node.attrs
with pytest.raises(KeyError):
    node.attrs['missing']
with pytest.raises(KeyError):
    del node.attrs['missing']
assert dict(open_node(location, mode='r').attrs) == values
node.attrs['count'] = -23
del node.attrs['active']
expected = dict(values)
expected['count'] = -23
del expected['active']
assert dict(node.attrs) == expected
reopened = open_node(location, mode='r')
assert dict(reopened.attrs) == expected
with pytest.raises(KeyError):
    reopened.attrs['active']
''', tmp_path / f'basic-{version}-{kind}', version, kind)
            assert observed == {
                'title': '测量 café',
                'nested': {'samples': [3, None, False, {'offset': -2.5}], 'empty': {}},
                'count': -23, 'empty': [],
            }


def test_f12_t02(tmp_path):
    for version in (2, 3):
        for kind in ('array', 'group'):
            observed = check_attribute_changes('''
node.attrs.update({'keep': {'units': ['m', 's']}, 'change': 4})
node.attrs.update({'change': [8, None], 'added': False})
merged = {'keep': {'units': ['m', 's']}, 'change': [8, None], 'added': False}
assert dict(open_node(location, mode='r').attrs) == merged
node.attrs.update({})
assert dict(open_node(location, mode='r').attrs) == merged
node.attrs.put({'replacement': {'runs': [9, -6]}, 'change': 'new'})
replacement = {'replacement': {'runs': [9, -6]}, 'change': 'new'}
assert dict(open_node(location, mode='r').attrs) == replacement
# Failed operations are observed on freshly opened handles: persistence is
# promised, while rollback of an already-held in-memory view is not.
for operation in ('assign', 'update', 'put'):
    writable = open_node(location, mode='r+')
    with pytest.raises(TypeError):
        if operation == 'assign':
            writable.attrs['invalid'] = object()
        elif operation == 'update':
            writable.attrs.update({'invalid': object()})
        else:
            writable.attrs.put({'invalid': object()})
    assert dict(open_node(location, mode='r').attrs) == replacement
for operation in ('assign', 'delete', 'update', 'put'):
    readonly = open_node(location, mode='r')
    assert dict(readonly.attrs) == replacement
    with pytest.raises(ValueError):
        if operation == 'assign':
            readonly.attrs['change'] = 'refused'
        elif operation == 'delete':
            del readonly.attrs['change']
        elif operation == 'update':
            readonly.attrs.update({'change': 'refused'})
        else:
            readonly.attrs.put({'other': 'refused'})
    assert dict(open_node(location, mode='r').attrs) == replacement
# Empty replacement must clear rather than act like an empty merge.
node = open_node(location, mode='r+')
node.attrs.put({})
assert dict(open_node(location, mode='r').attrs) == {}
node.attrs.update({'final': [False, None, {'value': 12.5}]})
''', tmp_path / f'updates-{version}-{kind}', version, kind)
            assert observed == {'final': [False, None, {'value': 12.5}]}
