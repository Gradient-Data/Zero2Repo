# feature: F12
"""Script execution, artifact publication, isolation, and failure semantics."""
import shlex

from velnora import Dir, File, script
from velnora.scripting import ScriptError

from _helpers import memory_scheduler, run_workflow, working_environment
from F01_helpers import resolved
from F03_helpers import disk_contents


def test_f12_t01(tmp_path):
    with working_environment(cwd=tmp_path):
        assert resolved(script("printf '%s\\n' $((17 * 4 - 9))")) == b'59\n'
        assert resolved(script([
            'printf', '<%s>\n', 'two  spaces', '', 'literal $HOME; *', "a'b\"c"
        ])) == b'<two  spaces>\n<>\n<literal $HOME; *>\n<a\'b"c>\n'

        result = resolved(script(
            "mkdir -p bundle/nested\n"
            "printf 'alpha\\nbeta\\n' > report.txt\n"
            "printf 'child-data' > bundle/nested/item\n"
            "printf 'top-data' > bundle/top\n"
            "printf 'finished\\n'",
            outputs={'report': [File('report.txt')],
                     'collection': (Dir('bundle'), File('-'))},
        ))
        assert isinstance(result, dict)
        assert isinstance(result['report'], list)
        assert isinstance(result['collection'], tuple)
        assert isinstance(result['report'][0], File)
        assert result['report'][0].path == 'report.txt'
        assert (tmp_path / result['report'][0].path).read_bytes() == b'alpha\nbeta\n'
        directory, stdout = result['collection']
        assert isinstance(directory, Dir)
        assert directory.path == 'bundle'
        assert disk_contents(tmp_path / directory.path) == {
            'nested/item': b'child-data', 'top': b'top-data'}
        assert stdout == b'finished\n'


def test_f12_t02(tmp_path):
    source = tmp_path / 'source.txt'
    source.write_bytes(b'cedar\nmaple\n')
    source_dir = tmp_path / 'source-directory'
    (source_dir / 'nested').mkdir(parents=True)
    (source_dir / 'nested' / 'tail').write_bytes(b'willow\n')
    # Identical commands and inputs: only isolation differs between the arms.
    # The append operation makes a reused intermediate visible in published data.
    command = ("tr '[:lower:]' '[:upper:]' < incoming >> intermediate\n"
               "cat incoming-dir/nested/tail >> intermediate\n"
               "mkdir -p produced/nested\n"
               "cp intermediate produced/nested/result\n"
               "cp intermediate summary")
    one = b'CEDAR\nMAPLE\nwillow\n'
    for isolated in (False, True):
        work = tmp_path / ('isolated' if isolated else 'shared')
        work.mkdir()
        with working_environment(cwd=work):
            for invocation in range(2):
                destination = tmp_path / f'published-{isolated}-{invocation}'
                destination.mkdir()
                summary = destination / 'summary.txt'
                tree = destination / 'tree'
                result = resolved(script(
                    command, tempdir=isolated,
                    inputs=[File(str(source)).stage('incoming'),
                            Dir(str(source_dir)).stage('incoming-dir')],
                    outputs={'summary': File(str(summary)).stage('summary'),
                             'tree': Dir(str(tree)).stage('produced')},
                ))
                expected = one if isolated else one * (invocation + 1)
                assert isinstance(result['summary'], File)
                assert result['summary'].path == str(summary)
                assert summary.read_bytes() == expected
                assert isinstance(result['tree'], Dir)
                assert result['tree'].path == str(tree)
                assert disk_contents(tree) == {'nested/result': expected}
    assert source.read_bytes() == b'cedar\nmaple\n'
    assert disk_contents(source_dir) == {'nested/tail': b'willow\n'}

    # Invocations overlapping in time use the same relative name. Each waits (for
    # a bounded time) until the other has written, then reads back its own data.
    arrivals = tmp_path / 'arrivals'
    arrivals.mkdir()
    def overlapping(own, other):
        here, there = shlex.quote(str(arrivals / own)), shlex.quote(str(arrivals / other))
        return script(f"printf {own} > scratch\n"
                      f": > {here}\n"
                      f"for attempt in $(seq 100); do [ -e {there} ] && break; sleep .05; done\n"
                      "cat scratch", tempdir=True)
    with working_environment(cwd=tmp_path):
        assert resolved([overlapping('alder', 'birch'),
                         overlapping('birch', 'alder')]) == [b'alder', b'birch']


def test_f12_t03(tmp_path):
    # A false condition is a successful control-flow decision, unlike an
    # unhandled failure. Keep all other commands identical for each contrast.
    for name, failure, condition in (
        ('standalone', 'false', 'if false; then :; fi'),
        ('pipeline', 'false | cat', 'if false | cat; then :; fi'),
    ):
        marker = tmp_path / (name + '.after')
        quoted = shlex.quote(str(marker))
        prefix = "printf 'script-owned diagnostic\\n' >&2\n"
        suffix = f"\nprintf 'continued' > {quoted}\nprintf 'complete\\n'"
        with working_environment(cwd=tmp_path):
            baseline = run_workflow(memory_scheduler(), script(prefix + condition + suffix))
            assert baseline.exception is None, baseline.exception
            assert baseline.value == b'complete\n'
            assert marker.read_bytes() == b'continued'
            marker.unlink()
            failed = run_workflow(memory_scheduler(), script(prefix + failure + suffix))
        assert isinstance(failed.exception, ScriptError), failed.exception
        # This is text deliberately emitted by our script, not Bash wording.
        assert 'script-owned diagnostic' in failed.exception.message.splitlines()
        assert not marker.exists()
    # Other forms in which a command is only a condition.
    for condition in ('false && :', 'false || :', 'while false; do :; done'):
        with working_environment(cwd=tmp_path):
            assert resolved(script(condition + "\nprintf 'complete\\n'")) == b'complete\n'


def test_f12_t04(tmp_path):
    with working_environment(cwd=tmp_path):
        # Arrays and process substitution require Bash rather than plain sh.
        assert resolved(script(
            "values=(8 13 21)\ncat <(printf '%s\\n' \"${values[2]}:${#values[@]}\")"
        )) == b'21:3\n'
        assert resolved(script(
            '#!/usr/bin/env python3\n'
            'values = [3, 8, 5]\n'
            'print(sum(x * x for x in values))\n'
        )) == b'98\n'
        # The stop-on-failure rule belongs to the default mode: under an explicit
        # interpreter only that interpreter's own semantics apply.
        assert resolved(script(
            "#!/usr/bin/env bash\nfalse\nfalse | cat\nprintf 'continued\\n'"
        )) == b'continued\n'
        failed = run_workflow(memory_scheduler(), script(
            '#!/usr/bin/env python3\n'
            'import sys\n'
            "sys.stderr.write('interpreter-owned diagnostic\\n')\n"
            'sys.exit(3)\n'
        ))
        assert isinstance(failed.exception, ScriptError), failed.exception
        assert 'interpreter-owned diagnostic' in failed.exception.message.splitlines()
