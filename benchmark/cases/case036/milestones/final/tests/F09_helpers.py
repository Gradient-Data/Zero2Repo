# feature: F09
"""String workflow construction and finite-sample frequency observations."""
from collections import Counter
from math import log, sqrt
import string
from F07_helpers import utility_run
from _helpers import temporary_workspace, keyword_calls


def velun_expression(value):
    return repr(value).replace('\\', '\\\\').replace(' ', r'\ ')


class StringWorkflow:
    def __init__(self):
        self.lines = ['Working']
        self.failures = []
        self.rejected_targets = {}

    def operation(self, keyword, *args, expected=None, reject=False, **kwargs):
        if reject:
            name = 'Rejected ' + str(len(self.failures))
            self.failures.append(name)
            self.rejected_targets[name] = keyword
            self.lines.append(name)
        arguments = []
        for i, value in enumerate((*args, *kwargs.values())):
            variable = '${arg' + str(i) + '}'
            self.lines.append('    ' + variable + '=    Evaluate    ' + velun_expression(value))
            arguments.append(variable)
        cells = arguments[:len(args)] + [key + '=' + variable for key, variable in zip(kwargs, arguments[len(args):])]
        self.lines.append('    ${actual}=    String.' + keyword + '    ' + '    '.join(cells))
        if not reject:
            if not keyword.startswith('Should '):
                self.lines.append('    Check    ${actual}    ' + velun_expression(expected))
            if keyword.startswith(('Replace ', 'Remove ')):
                self.lines.append('    Check    ' + arguments[0] + '    ' + velun_expression(args[0]))

    def run_and_verify(self):
        with temporary_workspace() as directory:
            names = ['Working', *self.failures]
            root = utility_run(directory, '\n'.join(self.lines) + '\n',
                               {name: 'FAIL' if name in self.failures else 'PASS' for name in names},
                               settings='Library    String\n')
            for case in root.findall('.//test'):
                if case.attrib['name'] in self.rejected_targets:
                    calls = case.findall('kw')
                    assert calls[-1] in keyword_calls(case, self.rejected_targets[case.attrib['name']], owner='String')
                    assert calls[-1].find('status').attrib['status'] == 'FAIL'
                    assert all(call.find('status').attrib['status'] == 'PASS' for call in calls[:-1])
            return root


def frequency_cells(observations, probabilities):
    counts = Counter(observations)
    assert set(counts) <= set(probabilities), counts
    return [(counts[value], len(observations), probability)
            for value, probability in probabilities.items()]


def assert_frequency_budget(cells):
    # Bernstein's binomial bound, union-bounded over ALL cells in this test.
    # No independence between cells is required. Total false rejection <= 1e-9.
    tail = log(2 * len(cells) / 1e-9)
    for count, size, probability in cells:
        mean = size * probability
        margin = sqrt(2 * size * probability * (1 - probability) * tail) + 2 * tail / 3
        assert abs(count - mean) <= margin, (count, size, probability, margin)


CHARACTER_COLLECTIONS = {
    '[LOWER]': string.ascii_lowercase,
    '[UPPER]': string.ascii_uppercase,
    '[LETTERS]': string.ascii_letters,
    '[NUMBERS]': string.digits,
    '[ARABIC]': ''.join(chr(c) for c in range(0x600, 0x700)),
    '[POLISH]': string.ascii_letters + 'ąćęłńóśźżĄĆĘŁŃÓŚŹŻ',
    '[LOWER][NUMBERS]!?': string.ascii_lowercase + string.digits + '!?',
}
