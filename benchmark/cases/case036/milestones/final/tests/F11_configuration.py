# feature: F11
"""Acceptance tests for execution selection and configuration."""
from collections import Counter
from itertools import permutations
from math import comb, exp, log, sqrt
import os
from random import SystemRandom
import signal
import subprocess
import sys

from _helpers import write_file, wait_until
from F01_helpers import native_case
from F03_helpers import library_outcomes
from F11_helpers import (configured_run, configured_result, selected_cases,
                         configuration_error, selection_tree)


def test_name_hierarchy_and_tag_selection(tmp_path):
    source = selection_tree(tmp_path / 'catalog')
    scenarios = [
        (['--test','aLPHA_oNE'], {'Alpha One'}),
        (['--test','*north_WING.beta_two'], {'Beta Two'}),
        (['--suite','NORTH_wing'], {'Alpha One','Beta Two','Gamma Three'}),
        (['--test','[AB]*?o*'], {'Alpha One','Beta Two','Alpha One Extra'}),
        (['--test','Alpha'], set()),
        (['--include','RED_AND_READY'], {'Alpha One'}),
        (['--include','redORblueANDready'], {'Alpha One','Beta Two','Gamma Three'}),
        (['--include','redORblueNOTblocked'], {'Alpha One','Beta Two','Alpha One Extra'}),
        (['--include','NOTred'], {'Beta Two','Delta Four','Alpha One Extra'}),
        # AND binds tighter than NOT: ready NOT (blocked AND red).
        (['--include','readyNOTblockedANDred'], {'Alpha One','Beta Two'}),
        # Every right-hand condition of a NOT chain is excluded.
        (['--include','NOTredNOTgreen'], {'Beta Two','Alpha One Extra'}),
        # Tag patterns match whole tags: 'read' is not a prefix match of 'ready'.
        (['--include','read','--include','green'], {'Delta Four'}),
        # Suites are also selectable by hierarchical (full) name.
        (['--suite','catalog.SOUTH_wing'], {'Delta Four','Alpha One Extra'}),
        (['--include','r?d','--include','gr[ae]en'], {'Alpha One','Gamma Three','Delta Four'}),
        (['--exclude','BL*'], {'Alpha One','Delta Four'}),
        (['--test','Alpha*','--test','Beta*','--suite','North*',
          '--include','ready','--exclude','blue'], {'Alpha One'}),
    ]
    for index, (options, expected) in enumerate(scenarios):
        directory = tmp_path / str(index)
        process = configured_run(directory, [source], options)
        if expected:
            selected_cases(process, directory, expected)
        else:
            configuration_error(process)
            allowed = tmp_path / 'empty'
            process = configured_run(allowed, [source], [*options,'--runemptysuite'])
            selected_cases(process, allowed, set())


def test_discovery_path_patterns_and_extensions(tmp_path):
    source = tmp_path / 'sources'
    for relative, name in [('one/CHOSEN.velun','Near'), ('one/deep/chosen.velun','Deep'),
                           ('one/deep/nested/chosen.velun','Nested'),
                           ('two/other.velun','Other'), ('one/custom.TxT','Custom')]:
        write_file(source / relative, native_case(name))
    write_file(source / 'notes.txt', 'This is not a test source.\n')
    scenarios = [(['--parseinclude','CHOSEN.VELUN'], {'Near','Deep','Nested'}),
        (['--parseinclude',str(source / 'one' / '*.velun')], {'Near'}),
        (['--parseinclude',str(source / 'one' / '**chosen.velun')], {'Near','Deep','Nested'}),
        (['--parseinclude',str(source / 'two' / 'other.velun')], {'Other'}),
        (['--extension','velun:TXT'], {'Near','Deep','Nested','Other','Custom'})]
    for index, (options, expected) in enumerate(scenarios):
        directory = tmp_path / str(index)
        selected_cases(configured_run(directory,[source],options),directory,expected)


def test_reruns_use_current_definitions_and_empty_policy(tmp_path):
    source = tmp_path / 'reruns'
    failed = write_file(source / 'first.velun', '*** Test Cases ***\nBroken\n    Fail    old failure\nSibling\n    No Operation\n')
    write_file(source / 'second.velun', native_case('Unrelated'))
    old = tmp_path / 'old'
    process = configured_run(old,[source])
    library_outcomes(process, configured_result(old), {'Broken':'FAIL','Sibling':'PASS','Unrelated':'PASS'})
    write_file(failed, '*** Test Cases ***\nBroken\n    Log    current-definition\nSibling\n    No Operation\n')
    for option, expected in [('--rerunfailed',{'Broken'}),('--rerunfailedsuites',{'Broken','Sibling'})]:
        directory = tmp_path / option[2:]
        root = selected_cases(configured_run(directory,[source],[option,old/'output.xml']),directory,expected)
        assert root.find(".//test[@name='Broken']/kw/msg").text == 'current-definition'
    clean = tmp_path / 'clean'
    selected_cases(configured_run(clean,[source]),clean,{'Broken','Sibling','Unrelated'})
    for allow in (False,True):
        directory = tmp_path / ('allow' if allow else 'refuse')
        options = ['--rerunfailed',clean/'output.xml'] + (['--runemptysuite'] if allow else [])
        process = configured_run(directory,[source],options)
        if allow:
            selected_cases(process,directory,set())
        else:
            configuration_error(process)
    bad = write_file(tmp_path/'broken.xml','<velun><suite>')
    for prior in (bad,tmp_path/'missing.xml'):
        configuration_error(configured_run(tmp_path/'bad',[source],['--rerunfailed',prior]))


def test_configuration_precedence_and_argument_files(tmp_path):
    source = write_file(tmp_path/'suite.velun','*** Settings ***\nDocumentation    source doc\nMetadata    Origin    source\n*** Test Cases ***\nWitness\n    [Tags]    original\n    No Operation\n')
    arguments = write_file(tmp_path/'options.args','--name File Name\n--doc File documentation\n--metadata Owner:file\n--settag from-file\n')
    defaults = '--name Environment --doc Environment --metadata Owner:environment --settag from-env'
    options = ['--argumentfile',arguments,'--name','Discarded','--name','Final Name',
               '--doc','Final documentation','--metadata','Owner:direct','--metadata','Build:current',
               '--settag','from-direct']
    directory = tmp_path/'configured'
    root = selected_cases(configured_run(directory,[source],options,defaults),directory,{'Witness'})
    suite = root.find('suite')
    assert suite.attrib['name'] == 'Final Name'
    assert suite.find('doc').text == 'Final documentation'
    assert {m.attrib['name']:m.text for m in suite.findall('meta')} == {'Origin':'source','Owner':'direct','Build':'current'}
    assert {t.text for t in suite.findall('test/tag')} == {'original','from-env','from-file','from-direct'}
    envdir = tmp_path/'environment'
    envroot = selected_cases(configured_run(envdir,[source],defaults=defaults),envdir,{'Witness'})
    assert envroot.find('suite').attrib['name'] == 'Environment'
    # Argument-file options are explicit invocation and override environment defaults.
    filedir = tmp_path/'argumentfile'
    fileroot = selected_cases(configured_run(filedir,[source],['--argumentfile',arguments],defaults),filedir,{'Witness'})
    filesuite = fileroot.find('suite')
    assert filesuite.attrib['name'] == 'File Name'
    assert filesuite.find('doc').text == 'File documentation'
    assert {m.attrib['name']:m.text for m in filesuite.findall('meta')} == {'Origin':'source','Owner':'file'}
    assert {t.text for t in filesuite.findall('test/tag')} == {'original','from-env','from-file'}
    for options in (['--argumentfile',tmp_path/'missing.args'],['--randomize','invalid'],['--unknown-option']):
        configuration_error(configured_run(tmp_path/'invalid',[source],options))


def test_seeded_order_modes_preserve_membership(tmp_path):
    source = tmp_path/'ordering'
    recorder = write_file(tmp_path / 'ExecutionWitness.py', '''from pathlib import Path
def record_execution(path, name):
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(name + '\\n')
''')
    expected = {}
    # Suite D is large enough for an order statistic to expose biased shuffles
    # whose bias is invisible in five-element permutation frequencies.
    for letter, size in zip('abcd', (5, 5, 5, 32)):
        names = [letter + str(i) for i in range(size)]
        expected[letter.upper()] = names
        write_file(source/(letter+'.velun'),
                   f'*** Settings ***\nName    {letter.upper()}\nLibrary    {recorder}\n*** Test Cases ***\n'
                   + ''.join(f'{n}\n    Record Execution    ${{EXECUTION_TRACE}}    {n}\n'
                             for n in names))
    parent_by_name = {name: parent for parent, names in expected.items() for name in names}
    def order(directory, mode):
        trace = directory / 'execution.txt'
        root = selected_cases(configured_run(directory, [source],
                              ['--randomize', mode, '--variable', 'EXECUTION_TRACE:' + str(trace)]),
                              directory, set(parent_by_name))
        suites = root.findall('./suite/suite')
        assert len(suites) == len(expected)
        assert {suite.attrib['name']: {test.attrib['name'] for test in suite.findall('test')}
                for suite in suites} == {parent: set(names) for parent, names in expected.items()}
        execution = trace.read_text(encoding='utf-8').splitlines()
        assert Counter(execution) == Counter(parent_by_name.keys())
        parents = list(dict.fromkeys(parent_by_name[name] for name in execution))
        return [(parent, [name for name in execution if parent_by_name[name] == parent])
                for parent in parents]
    baseline = order(tmp_path/'default','none')
    assert dict(baseline) == expected
    baseline_suites = [parent for parent, _ in baseline]
    for mode in ('none','suites','tests','all'):
        first = order(tmp_path/(mode+'1'),mode+':7541')
        assert first == order(tmp_path/(mode+'2'),mode+':7541')
        assert {name:set(tests) for name,tests in first} == {name:set(tests) for name,tests in expected.items()}
        if mode in ('none','tests'):
            assert [name for name,_ in first] == baseline_suites
        if mode in ('none','suites'):
            assert dict(first) == expected

    # Uniform-permutation observations use independent caller-chosen seeds.
    # Thirty-two executions per mode are enough to reject a materially
    # restricted generator: for 24 possible suite permutations, seeing at
    # most 9 distinct permutations has probability below 2.5e-8 under the
    # uniform model (the occupancy probability is computed below). The same
    # bound is much smaller for the 120 test permutations. This keeps the
    # distribution check independent of any seed-to-permutation mapping while
    # avoiding hundreds of process launches.
    cells = []
    diversities = []
    deficiencies = []
    seeds = SystemRandom()
    for mode in ('suites', 'tests', 'all'):
        observations = [order(tmp_path / (mode + '-sample-' + str(i)),
                              mode + ':' + str(seeds.getrandbits(63)))
                        for i in range(32)]
        # Every sampled seed, not only a fixed one, leaves unselected dimensions alone.
        for run in observations:
            if mode == 'suites':
                assert dict(run) == expected, run
            if mode == 'tests':
                assert [name for name, _ in run] == baseline_suites, run
        dimensions = []
        if mode in ('suites', 'all'):
            dimensions.append(([tuple(name for name, _ in run) for run in observations],
                               list(permutations(expected))))
        if mode in ('tests', 'all'):
            for name, names in expected.items():
                if len(names) > 5:
                    # Count tests run before their declared position.
                    deficiencies.extend(sum(position < names.index(test) for position, test
                                            in enumerate(dict(run)[name]))
                                        for run in observations)
                    continue
                dimensions.append(([tuple(dict(run)[name]) for run in observations],
                                   list(permutations(names))))
        for samples, outcomes in dimensions:
            counts = Counter(samples)
            assert set(counts) <= set(outcomes)
            diversities.append((len(counts), len(outcomes), len(samples)))
            cells.extend((counts[outcome], len(samples), 1 / len(outcomes))
                         for outcome in outcomes)
    tail = log(2 * len(cells) / 5e-10)
    for count, size, probability in cells:
        mean = size * probability
        margin = sqrt(2 * size * probability * (1 - probability) * tail) + 2 * tail / 3
        assert abs(count - mean) <= margin, (count, size, probability, margin)
    for distinct, population, size in diversities:
        # At most d distinct results means that all samples belong to one of
        # C(k,d) subsets, each having probability (d/k)**n under uniformity.
        rejected = [d for d in range(1, population)
                    if log(comb(population, d)) + size * log(d / population)
                    <= log(5e-10 / len(diversities))]
        assert rejected
        assert distinct > max(rejected), (distinct, population, size, max(rejected))
    # For a uniform permutation of k items, the number of items placed before
    # their original position follows the Eulerian distribution A(k, j) / k!.
    # An exact Chernoff bound on the sum of the independent samples gives a
    # two-sided false-rejection budget of 1e-10.
    size = len(expected['D'])
    eulerian = [1]
    for k in range(2, size + 1):
        eulerian = [(j + 1) * (eulerian[j] if j < len(eulerian) else 0)
                    + (k - j) * (eulerian[j - 1] if 0 < j <= len(eulerian) else 0)
                    for j in range(k)]
    total = sum(eulerian)
    def log_tail(observed, sign):
        bound = 0.0
        for step in range(1, 400):
            theta = sign * step / 100
            moment = log(sum(count / total * exp(theta * j) for j, count in enumerate(eulerian)))
            bound = min(bound, len(deficiencies) * moment - theta * observed)
        return bound
    observed = sum(deficiencies)
    assert len(deficiencies) == 64
    assert log_tail(observed, 1) > log(5e-11) and log_tail(observed, -1) > log(5e-11), (
        observed, len(deficiencies) * (size - 1) / 2)


def test_dryrun_validates_without_library_effects(tmp_path):
    library = write_file(tmp_path/'Effects.py','from pathlib import Path\ndef touch(path):\n    Path(path).write_text("executed")\n')
    for dry in (False,True):
        directory = tmp_path/str(dry)
        marker = directory/'effect'
        source = write_file(directory/'suite.velun', f'*** Settings ***\nLibrary    {library}\n*** Test Cases ***\nValid\n    Touch    {marker}\nMissing\n    Unavailable Operation\nArguments\n    Touch\nStructure\n    IF    True\n        No Operation\n')
        options = ['--dryrun'] if dry else []
        process = configured_run(directory,[source],options)
        root = configured_result(directory)
        library_outcomes(process,root,{'Valid':'PASS','Missing':'FAIL','Arguments':'FAIL','Structure':'FAIL'})
        for name in ('Missing','Arguments','Structure'):
            assert root.find(f".//test[@name='{name}']/status").text
        # Validation outcomes identify the invalid call, in dry run as in real runs.
        reasons = {name: ' '.join(root.find(f".//test[@name='{name}']/status").text.lower().replace('_', ' ').split())
                   for name in ('Missing','Arguments')}
        assert 'unavailable operation' in reasons['Missing'], reasons
        assert 'touch' in reasons['Arguments'], reasons
        if dry:
            assert not marker.exists()
        else:
            assert marker.read_text() == 'executed'


def test_completion_failure_input_and_status_suppression(tmp_path):
    source = write_file(tmp_path/'suite.velun','*** Test Cases ***\nGood\n    No Operation\nBad\n    Fail    recorded rejection\nAnother Bad\n    Fail    second rejection\n')
    for suppressed in (False,True):
        directory = tmp_path/str(suppressed)
        options = ['--nostatusrc'] if suppressed else []
        process = configured_run(directory,[source],options)
        root = configured_result(directory)
        assert {t.attrib['name']:t.find('status').attrib['status'] for t in root.findall('.//test')} == {'Good':'PASS','Bad':'FAIL','Another Bad':'FAIL'}
        assert root.find(".//test[@name='Bad']/status").text == 'recorded rejection'
        assert root.find(".//test[@name='Another Bad']/status").text == 'second rejection'
        # The Contract states the status: the failed-test count (two here), capped at 250.
        assert process.returncode == (0 if suppressed else 2), (process.returncode, process.stderr)
        configuration_error(configured_run(tmp_path/('invalid'+str(suppressed)),[source],[*options,'--not-an-option']))
    directory = tmp_path/'success'
    selected_cases(configured_run(directory,[source],['--test','Good']),directory,{'Good'})

    # A real external interrupt during a public parser's source preparation
    # precedes test execution. First prove the same parser completes normally.
    parser = write_file(tmp_path / 'PreparingParser.py', '''import time
from velun.api import TestSuite
class PreparingParser:
    extension = 'preparing'
    def parse(self, source, defaults):
        source.with_suffix('.ready').write_text('preparing')
        time.sleep(float(source.read_text()))
        suite = TestSuite(name='Prepared')
        suite.tests.create(name='Ready').body.create_keyword('No Operation')
        return suite
''')
    prepared = write_file(tmp_path / 'source.preparing', '0')
    options = ['--pythonpath', str(tmp_path), '--parser', 'PreparingParser.PreparingParser']
    selected_cases(configured_run(tmp_path / 'prepared', [prepared], options),
                   tmp_path / 'prepared', {'Ready'})
    ready = prepared.with_suffix('.ready')
    ready.unlink()
    prepared.write_text('30')
    interrupt_dir = tmp_path / 'interrupted'
    interrupt_dir.mkdir()
    process = subprocess.Popen(
        [sys.executable, '-m', 'velun', '--outputdir', str(interrupt_dir),
         '--log', 'NONE', '--report', 'NONE', *options, str(prepared)],
        env={key: value for key, value in os.environ.items() if key != 'VELUN_OPTIONS'},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        def preparing():
            assert process.poll() is None, 'Product exited before preparation synchronization.'
            return ready.exists()
        wait_until(preparing, timeout=15)
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 253, (stdout, stderr)
        assert b'[ ERROR ]' in stderr, stderr
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)


def test_execution_error_policy_controls_remaining_effects(tmp_path):
    library = write_file(tmp_path/'Progress.py','from pathlib import Path\ndef append(path, text):\n    with Path(path).open("a") as stream: stream.write(text + "\\n")\n')
    for fatal in (False,True):
        directory = tmp_path/str(fatal)
        marker = directory/'progress'
        source = write_file(directory/'suite.velun', f'*** Settings ***\nLibrary    {library}\nLibrary    {tmp_path / "UnavailableLibrary.py"}\n*** Test Cases ***\nFirst\n    Append    {marker}    first\nSecond\n    Append    {marker}    second\n')
        process = configured_run(directory,[source],['--exitonerror'] if fatal else [])
        root = configured_result(directory)
        errors = root.findall('./errors/msg')
        assert any(m.attrib['level'] == 'ERROR' and 'UnavailableLibrary.py' in (m.text or '') for m in errors)
        assert b'[ ERROR ]' in process.stderr
        if fatal:
            library_outcomes(process,root,{'First':'FAIL','Second':'FAIL'})
            assert not marker.exists()
        else:
            library_outcomes(process,root,{'First':'PASS','Second':'PASS'})
            assert marker.read_text().splitlines() == ['first','second']
