# feature: F04
"""Custom annotation provider and CLI checks needing extra source modules."""
from collections import Counter
from textwrap import dedent
from _helpers import workspace, read_json
from F01_helpers import check_source


def check_extension_source(source, *, options=(), extra_errors=None, provider=None):
    source = dedent(source).lstrip('\n')
    expected = Counter((line, text.split('# E: ', 1)[1])
                       for line, text in enumerate(source.splitlines(), 1)
                       if '# E: ' in text)
    expected.update((line, code) for line, code in (extra_errors or {}).items())
    clean = '\n'.join(line.split('# E: ', 1)[0].rstrip() for line in source.splitlines()) + '\n'
    files = {'subject.py': clean}
    if provider is not None:
        files['restrictions.py'] = provider
    with workspace(files) as root:
        report = root / 'report.json'
        result = check_source(root, ['--disable', 'unused_variable', *options,
                                    '--json-output', str(report), str(root / 'subject.py')])
        assert result.returncode == (1 if expected else 0), result
        findings = read_json(report, result=result)
        assert Counter((f['lineno'], f['code']) for f in findings) == expected, findings
        assert bool(result.stderr.strip()) == bool(expected), result
        return findings


CUSTOM_CHECKS = """
from dataclasses import dataclass
from typing import TypeVar
from velnora.extensions import CustomCheck
from velnora.value import AnyValue, KnownValue, CanAssignError, TypeVarValue, TypeVarParam

class Incoming(CustomCheck):
    def can_assign(self, value, ctx):
        if isinstance(value, KnownValue) and value.val == 0:
            return CanAssignError('incoming-zero-forbidden')
        return {}

class Outgoing(CustomCheck):
    def can_be_assigned(self, value, ctx):
        if isinstance(value, AnyValue):
            return CanAssignError('outgoing-unknown-forbidden')
        return {}

@dataclass(frozen=True)
class Matches(CustomCheck):
    expected: object
    def can_assign(self, value, ctx):
        if isinstance(self.expected, TypeVar):
            return {}
        if isinstance(value, KnownValue) and value.val == self.expected:
            return {}
        return CanAssignError('specialized-value-required')
    def walk_values(self):
        if isinstance(self.expected, TypeVar):
            yield TypeVarValue(TypeVarParam(self.expected, owner=None))
    def substitute_typevars(self, typevars):
        if isinstance(self.expected, TypeVar):
            resolved = typevars.get_typevar(TypeVarParam(self.expected, owner=None))
            if isinstance(resolved, KnownValue):
                return Matches(resolved.val)
        return self
"""
