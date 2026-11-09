# feature: F17
"""XML keyword workflows with caller-side content checks and explicit failures."""
from _helpers import keyword_calls
from F07_helpers import utility_run
from F09_helpers import velun_expression


class XMLReference:
    def __init__(self, name):
        self.name = name


class XMLWorkflow:
    def __init__(self, directory, *, full_xpath=False):
        self.directory = directory
        self.lines = ['Working']
        self.failures = {}
        self.counter = 0
        self.settings = 'Library    XML' + ('    use_lxml=True' if full_xpath else '') + '\n'

    def call(self, keyword, *args, **kwargs):
        cells = []
        for key, value in [(None, value) for value in args] + list(kwargs.items()):
            if isinstance(value, XMLReference):
                cell = '${' + value.name + '}'
            else:
                self.counter += 1
                cell = '${input' + str(self.counter) + '}'
                self.lines.append('    ' + cell + '=    Evaluate    ' + velun_expression(value))
            cells.append((key + '=' if key else '') + cell)
        self.counter += 1
        result = XMLReference('result' + str(self.counter))
        self.lines.append('    ${' + result.name + '}=    XML.' + keyword + '    ' + '    '.join(cells))
        return result

    def check(self, reference, expected):
        self.lines.append('    Check    ${' + reference.name + '}    ' + velun_expression(expected))

    def inspect(self, expression, expected, *, modules=None):
        self.counter += 1
        result = XMLReference('view' + str(self.counter))
        self.lines.append('    ${' + result.name + '}=    Evaluate    ' + expression
                          + ('    modules=' + modules if modules else ''))
        self.check(result, expected)

    def reject(self, keyword, *args, identifies=(), **kwargs):
        name = 'Rejected ' + str(len(self.failures))
        self.lines.append(name)
        self.failures[name] = (keyword, identifies)
        self.call(keyword, *args, **kwargs)

    def run_and_verify(self):
        root = utility_run(self.directory, '\n'.join(self.lines) + '\n',
                           {'Working': 'PASS', **{name: 'FAIL' for name in self.failures}},
                           settings=self.settings)
        for case in root.findall('.//test'):
            if case.attrib['name'] in self.failures:
                keyword, identifies = self.failures[case.attrib['name']]
                calls = case.findall('kw')
                assert all(call.find('status').attrib['status'] == 'PASS' for call in calls[:-1])
                failed = calls[-1]
                assert failed in keyword_calls(case, keyword, owner='XML'), (keyword, [(c.attrib, c.find('status').text) for c in calls])
                assert failed.attrib['owner'] == 'XML'
                assert failed.find('status').attrib['status'] == 'FAIL'
                messages = failed.findall("msg[@level='FAIL']")
                assert messages and all(message.text for message in messages)
                for value in identifies:
                    assert any(value in message.text for message in messages), (keyword, value, [message.text for message in messages])
        return root
