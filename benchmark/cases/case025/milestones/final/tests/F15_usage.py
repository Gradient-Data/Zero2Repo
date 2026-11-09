# feature: F15
"""Acceptance of usage diagnostics and opt-in whole-source searches."""
from collections import Counter
from F04_helpers import check_extension_source
from F15_helpers import (usage_run, usage_diagnostics, unused_members,
                         unused_objects, call_pattern_subjects, call_pattern_results)


def test_unused_locals_and_overwritten_values():
    usage_diagnostics('''
        def work(items: list[tuple[int, int]]):
            abandoned = 4  # E: unused_variable
            replaced = 1  # E: unused_assignment
            replaced = 2
            _intentional = 3
            left, right = (1, 2)
            [head, tail] = [3, 4]
            captured = 5
            def nested():
                return captured
            values = [a for a, b in items]
            return replaced, left, head, nested, values
    ''')


def test_unused_objects_and_members():
    files = {'subject.py': '''
        from typing import Protocol
        from velnora.find_unused import used
        def abandoned():
            pass
        class Forgotten:
            pass
        @used
        def registered():
            pass
        def exempt():
            pass
        class Base:
            inherited = 3
            dead = 4
            exempt = 5
            def idle(self):
                pass
        class Child(Base):
            pass
        class Shape(Protocol):
            def size(self) -> int: ...
        class Concrete:
            def size(self) -> int:
                return 1
        def measure(value: Shape) -> int:
            return value.size()
        def local():
            return measure(Concrete())
        class Shared:
            live = 6
            dead = 7
    ''', 'consumer.py': '''
        import subject
        def consume():
            return subject.Child().inherited + subject.Shared.live + subject.local()
    ''', 'policy.py': '''
        def ignore(module, name, value):
            return name == 'exempt'
    '''}
    targets = ['subject.py', 'consumer.py']
    for flags, exemptions in (((), False), (('--find-unused',), False),
                               (('--find-unused',), True),
                               (('--find-unused-attributes',), False),
                               (('--find-unused-attributes',), True)):
        result, findings = usage_run(files, flags=flags, targets=targets,
            config=('ignore_unused = ["policy.ignore"]\n'
                    'ignored_unused_attribute_paths = ["subject.Base.exempt"]\n')
                    if exemptions else '')
        assert result.returncode == (1 if "--find-unused" in flags else 0), result
        assert result.stderr == "", result
        if "--find-unused" not in flags:
            assert findings == [], findings
        objects = unused_objects(result.stdout)
        members = unused_members(result.stdout)
        if '--find-unused' in flags:
            assert objects['subject.abandoned'] == 'unused', result
            assert objects['subject.Forgotten'] == 'unused', result
            assert ('subject.exempt' not in objects) == exemptions, result
            assert {f['description'] for f in findings} == {
                name + ': ' + status for name, status in objects.items()}, findings
            for name in ('registered', 'Child', 'Shared', 'local'):
                assert 'subject.' + name not in objects, result
        else:
            assert objects == {}, result
        if '--find-unused-attributes' in flags:
            expected_members = {('attribute', 'subject.Base', 'dead'),
                                ('method', 'subject.Base', 'idle'),
                                ('attribute', 'subject.Shared', 'dead')}
            if not exemptions:
                expected_members.add(('attribute', 'subject.Base', 'exempt'))
            assert members == expected_members, result
        else:
            assert members == set(), result


def test_unused_call_alternatives():
    files = {'subject.py': '''
        from typing import Any
        def union(value: int | str | bytes):
            return value
        def truth(flag: bool):
            return flag
        def omitted(count: int = 4):
            return count
        def defaults(flag: bool = False):
            return flag
        def uncalled(value: int | str, flag: bool = False):
            return value, flag
        def uncertain(value: int | str, flag: bool):
            return value, flag
        def across(value: int | str, flag: bool):
            return value, flag
        def exercise(unknown: Any):
            union(3)
            truth(True)
            omitted()
            defaults()
            defaults(True)
            uncertain(unknown, unknown)
            across(2, True)
    ''', 'consumer.py': '''
        import subject
        def exercise():
            return subject.across('other', False)
    '''}
    for flags in ((), ('--find-unused-call-patterns',)):
        result, findings = usage_run(files, flags=flags)
        expected = Counter({('subject.union', 'value'): 1,
                            ('subject.truth', 'flag'): 1,
                            ('subject.omitted', 'count'): 1}) if flags else Counter()
        assert result.returncode == (1 if expected else 0), result
        assert call_pattern_subjects(findings) == expected, (result, findings)
        assert bool(result.stderr.strip()) == bool(expected), result
        assert call_pattern_results(findings) == ({
            ('subject.union', 'value'): ('union', frozenset({'str', 'bytes'}), frozenset({'int'})),
            ('subject.truth', 'flag'): ('literal', True),
            ('subject.omitted', 'count'): ('omitted',),
        } if flags else {}), findings

    # Reverse the observed alternatives, then exercise every declared choice.
    reversed_files = dict(files)
    reversed_files['subject.py'] = files['subject.py'].replace(
        'union(3)', "union('text')\n            union(b'data')"
    ).replace('truth(True)', 'truth(False)').replace('omitted()', 'omitted(5)')
    result, findings = usage_run(reversed_files, flags=('--find-unused-call-patterns',))
    assert result.returncode == 1 and result.stderr.strip(), result
    assert call_pattern_results(findings) == {
        ('subject.union', 'value'): ('union', frozenset({'int'}), frozenset({'str', 'bytes'})),
        ('subject.truth', 'flag'): ('literal', False),
    }, findings

    complete_files = dict(reversed_files)
    complete_files['subject.py'] = reversed_files['subject.py'].replace(
        "union('text')", "union('text')\n            union(3)"
    ).replace('truth(False)', 'truth(False)\n            truth(True)')
    result, findings = usage_run(complete_files, flags=('--find-unused-call-patterns',))
    assert result.returncode == 0 and result.stderr == '', result
    assert call_pattern_results(findings) == {}, findings


def test_deprecated_apis_and_selected_overloads():
    findings = usage_diagnostics('''
        from typing import overload
        from typing_extensions import deprecated
        @deprecated('Function migration reason')
        def old_function() -> int:
            return 1
        @deprecated('Class migration reason')
        class OldClass:
            pass
        class Api:
            @deprecated('Member migration reason')
            def old_method(self) -> int:
                return 2
        @overload
        @deprecated('Integer overload migration reason')
        def choose(value: int) -> int: ...
        @overload
        def choose(value: str) -> str: ...
        def choose(value: int | str):
            return value
        def exercise():
            old_function()  # E: deprecated
            OldClass()  # E: deprecated
            Api().old_method()  # E: deprecated
            choose(4)  # E: deprecated
            choose('valid')
    ''')
    for finding, reason in zip(sorted(findings, key=lambda f: f['lineno']),
                              ('Function migration reason', 'Class migration reason',
                               'Member migration reason', 'Integer overload migration reason')):
        assert reason in finding['description'], finding


def test_import_policy_and_private_access():
    files = {'blocked/__init__.py': '', 'blocked/child.py': 'value = 1\n',
             'blocked_extra.py': 'value = 2\n',
             'provider.py': '_secret = 3\n__allowed = 4\npublic = 5\n'}
    source = '''
        import blocked
        import blocked.child
        import blocked_extra
        import provider
        from provider import _secret
        from provider import __allowed
        def exercise():
            return provider._secret, provider.__allowed, provider.public
    '''
    usage_diagnostics(source, files=files)
    usage_diagnostics(source.replace('import blocked\n', 'import blocked  # E: disallowed_import\n')
                      .replace('import blocked.child\n', 'import blocked.child  # E: disallowed_import\n'),
                      files=files, config='disallowed_imports = ["blocked"]\n')
    usage_diagnostics(source.replace('from provider import _secret',
                                    'from provider import _secret  # E: private_import')
                      .replace('return provider._secret, provider.__allowed, provider.public',
                               'return provider._secret, provider.__allowed, provider.public  # E: private_import'),
                      files=files, flags=('--enable', 'private_import'))


def test_truth_conditions_and_discarded_results():
    check_extension_source('''
        from typing import Generator, AsyncGenerator
        from asynq import asynq
        class Broken:
            def __bool__(self):
                raise ValueError('No truth value')
        broken = Broken()
        class Api:
            def method(self) -> bool:
                return True
        def predicate() -> bool:
            return True
        @asynq()
        def deferred() -> int:
            return 3
        def generate() -> Generator[int, None, None]:
            yield 2
        async def async_generate() -> AsyncGenerator[int, None]:
            yield 3
        def exercise(flag: bool, api: Api):
            if predicate:  # E: type_always_true
                pass
            if api.method:  # E: type_always_true
                pass
            if broken:  # E: type_does_not_support_bool
                pass
            if deferred.asynq():  # E: type_does_not_support_bool
                pass
            if flag:
                pass
            if predicate():
                pass
            if api.method():
                pass
            generate()  # E: must_use
            async_generate()  # E: must_use
            predicate()
            return list(generate()), async_generate()
    ''')
