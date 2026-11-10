# feature: F16
"""DateTime calls through Velun with independent caller-side expectations."""
from _helpers import temporary_workspace, keyword_calls
from F07_helpers import utility_run
from F09_helpers import velun_expression


class CalendarWorkflow:
    def __init__(self):
        self.lines = ['Working']
        self.failures = {}

    def operation(self, keyword, *args, expected=None, reject=False, **kwargs):
        if reject:
            name = 'Rejected ' + str(len(self.failures))
            self.failures[name] = keyword
            self.lines.append(name)
        variables = []
        for i, value in enumerate((*args, *kwargs.values())):
            variable = '${arg' + str(i) + '}'
            self.lines.append('    ' + variable + '=    Evaluate    ' + velun_expression(value) + '    modules=datetime')
            variables.append(variable)
        cells = variables[:len(args)] + [key + '=' + value for key, value in zip(kwargs, variables[len(args):])]
        self.lines.append('    ${actual}=    DateTime.' + keyword + '    ' + '    '.join(cells))
        if not reject:
            if isinstance(expected, float):
                # Permit binary representation noise, not a loss of input precision.
                self.lines += [
                    '    ${matches}=    Evaluate    type($actual) is float and math.isclose($actual, '
                    + repr(expected) + ', rel_tol=1e-14, abs_tol=0.0)    modules=math',
                    '    Should Be True    ${matches}',
                ]
                return
            expression = velun_expression(expected)
            for name in ('datetime', 'date', 'timedelta'):
                expression = expression.replace('datetime.' + name + '(', name + '(')
            self.lines.append('    Check    ${actual}    ' + expression)

    def run_and_verify(self):
        with temporary_workspace() as directory:
            root = utility_run(directory, '\n'.join(self.lines) + '\n',
                               {'Working': 'PASS', **{name: 'FAIL' for name in self.failures}},
                               settings='Library    DateTime\n')
            for case in root.findall('.//test'):
                if case.attrib['name'] in self.failures:
                    calls = case.findall('kw')
                    assert all(call.find('status').attrib['status'] == 'PASS' for call in calls[:-1])
                    failed = calls[-1]
                    assert failed in keyword_calls(case, self.failures[case.attrib['name']], owner='DateTime')
                    assert failed.find('status').attrib['status'] == 'FAIL'
                    errors = failed.findall("msg[@level='FAIL']")
                    assert errors and all(message.text for message in errors)
            return root
