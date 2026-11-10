# feature: F15
"""Guest resources retain identity, run destructors, and reject invalid uses.

The guest's exported state and journal values below were observed through the
public API on the original repository. They are fixture computations, not
resource handle numbering rules. No assertions inspect the product's tables.
"""
from F15_helpers import (
    F15_RESOURCE_WAT, F15_EQUAL_REP_WAT, f01_driver, f15_driver, f15_borrow, f15_drop,
    f15_invoke, f15_resource_call,
)
from F13_helpers import f13_component, f13_values


def test_resource_identity_and_borrowed_state(f15_driver):
    # F15.T01: interleave distinct resources, including equal initial states.
    c, b = f15_resource_call, f15_borrow
    observed = f15_driver.observe(F15_RESOURCE_WAT, [
        c('new-counter', {'u32': 13}),
        c('new-counter', {'u32': 204}),
        c('new-counter', {'u32': 13}),
        c('read-counter', b(0)),
        c('read-counter', b(1)),
        c('add-counter', b(0), {'u32': 7}),
        c('read-counter', b(2)),
        c('add-counter', b(1), {'u32': 31}),
        c('add-counter', b(0), {'u32': 9}),
        c('read-counter', b(1)),
        c('read-counter', b(0)),
        c('add-counter', b(2), {'u32': 5}),
        c('read-counter', b(0)),
        c('read-counter', b(2)),
        f15_drop(0), f15_drop(1), f15_drop(2),
        c('new-counter', {'u32':61}), c('read-counter',b(17)),
        c('add-counter',b(17),{'u32':4}), f15_drop(17),
    ])
    values = f13_values(observed)
    assert len(values) == 21, observed
    assert set(values[17]) == {'own'}, observed
    assert values[18:] == [{'u32':61},{'u32':65},None], observed
    assert all(set(v) == {'own'} for v in values[:3]), observed
    assert len({v['own'] for v in values[:3]}) == 3, observed
    assert values[3:17] == [
        {'u32': n} for n in (13, 204, 20, 13, 235, 29, 235, 29, 18, 29, 18)
    ] + [None, None, None], observed

    observed = f15_driver.observe(F15_EQUAL_REP_WAT, [
        f15_invoke('tickets#mint', {'u32':57}), f15_invoke('tickets#mint', {'u32':57}),
        f15_invoke('tickets#inspect',b(0)),f15_invoke('tickets#inspect',b(1)),
        f15_invoke('tickets#released'),f15_drop(0),f15_invoke('tickets#released'),
        f15_invoke('tickets#inspect',b(1)),f15_drop(1),f15_invoke('tickets#released')])
    values = f13_values(observed)
    assert values[0]['own'] != values[1]['own'], observed
    assert values[2:] == [{'u32':57},{'u32':57},{'u32':0},None,
                          {'u32':1},{'u32':57},None,{'u32':2}], observed


def test_release_runs_guest_destructor_once(f15_driver):
    # F15.T02: the guest records destroyed values in order in separate journals.
    # Releasing out of construction order also checks destructor routing.
    c, b = f15_resource_call, f15_borrow
    observed = f15_driver.observe(F15_RESOURCE_WAT, [
        c('new-counter', {'u32': 7}),
        c('new-counter', {'u32': 23}),
        c('new-token', {'u32': 41}),
        c('add-counter', b(0), {'u32': 4}),
        c('counter-journal'), c('token-journal'),
        f15_drop(1), c('counter-journal'),
        c('read-counter', b(0)), c('read-token', b(2)),
        f15_drop(0), c('counter-journal'), c('token-journal'),
        f15_drop(2), c('token-journal'), c('counter-journal'),
    ])
    values = f13_values(observed)
    assert len(values) == 16, observed
    assert values[3:] == [
        {'u32': 11}, {'u32': 0}, {'u32': 0}, None,
        {'u32': 23}, {'u32': 11}, {'u32': 41}, None,
        {'u32': 241}, {'u32': 0}, None, {'u32': 41}, {'u32': 241},
    ], observed


def test_invalid_resource_operations_preserve_live_state(f15_driver):
    # F15.T03: rejected mutations must leave other resources usable, and a
    # repeated release is tested before any further allocation can reuse a handle.
    c, b = f15_resource_call, f15_borrow
    observed = f15_driver.observe(F15_RESOURCE_WAT, [
        c('new-counter', {'u32': 17}),
        c('new-counter', {'u32': 29}),
        c('new-token', {'u32': 43}),
        c('add-counter', b(0), {'u32': 2}),
        c('add-counter', b(2), {'u32': 100}),
        c('read-token', b(0)),
        c('read-counter', {'borrow': {'unused': {}}}),
        {'drop': {'unused': {}}},
        c('read-counter', b(0)), c('read-counter', b(1)), c('read-token', b(2)),
        c('counter-journal'), c('token-journal'),
        f15_drop(0), c('counter-journal'), f15_drop(0),
        c('read-counter', b(0)), c('counter-journal'),
        c('add-counter', b(1), {'u32': 3}), c('read-token', b(2)),
        f15_drop(1), f15_drop(2), c('counter-journal'), c('token-journal'),
        {'drop': {'unused_high': {}}}, c('counter-journal'), c('token-journal'),
    ])
    assert observed['opened'] is True, observed
    calls = observed['calls']
    assert len(calls) == 27, observed
    errors = {4: 'ValueTypeMismatch', 5: 'ValueTypeMismatch', 6: 'ValueTypeMismatch',
              7: 'InvalidHandle', 15: 'InvalidHandle', 16: 'ValueTypeMismatch', 24: 'InvalidHandle'}
    for i, call in enumerate(calls):
        allowed = ('ValueTypeMismatch','Unreachable') if errors.get(i) == 'ValueTypeMismatch' else ('InvalidHandle','NoResourceTable') if errors.get(i) == 'InvalidHandle' else (errors.get(i),)
        assert call['err'] in allowed, (i, observed)
        if i in errors:
            assert call['value'] is None, (i, observed)
    expected = {
        3: 19, 8: 19, 9: 29, 10: 43, 11: 0, 12: 0, 14: 19,
        17: 19, 18: 32, 19: 43, 22: 222, 23: 43, 25: 222, 26: 43,
    }
    for i, n in expected.items():
        assert calls[i]['value'] == {'u32': n}, (i, observed)
    for i in (13, 20, 21):
        assert calls[i]['value'] is None, (i, observed)

    plain = f13_component([
        ('baseline', '(param "value" u32)', 'u32',
         '(param i32) (result i32) local.get 0 i32.const 9 i32.add'),
    ])
    no_resources = f15_driver.observe(plain, [
        f15_invoke('baseline', {'u32': 31}),
        {'drop': {'literal': 1}},
        f15_invoke('baseline', {'u32': 72}),
    ])
    assert no_resources['opened'] is True, no_resources
    assert no_resources['calls'][1]['err'] in ('InvalidHandle','NoResourceTable'), no_resources
    assert no_resources['calls'] == [
        {'value': {'u32': 40}, 'err': None},
        {'value': None, 'err': no_resources['calls'][1]['err']},
        {'value': {'u32': 81}, 'err': None},
    ], no_resources
