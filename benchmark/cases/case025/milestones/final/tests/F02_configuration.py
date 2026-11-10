# feature: F02
"""Acceptance checks for configuration and source suppression."""

from _helpers import workspace, write_files
from F01_helpers import check_source
from F02_helpers import config_file, check_configured, displayed_options, displayed_paths


def test_relative_locations_and_explicit_targets():
    with workspace({
        'settings/src/dep.pyi': 'def number() -> int: ...\n',
        'settings/src/dep.py': 'def number() -> int:\n    return 1\n',
        'onlystub.py': 'def text():\n    return \"text\"\n',
        'settings/stubs/onlystub/__init__.pyi': 'def text() -> str: ...\n',
        'settings/stdlib/VERSIONS': 'math: 3.8\n',
        'settings/stdlib/math.pyi': 'def sqrt(x: float) -> str: ...\n',
        'settings/default.py': 'from dep import number\nfrom onlystub import text\nimport math\ndef f() -> None:\n    a: str = number()\n    b: int = text()\n    c: float = math.sqrt(4.0)\n    print(a, b, c)\n',
        'chosen.py': "value: int = 'bad'\n",
    }) as root:
        config = config_file(root, 'paths = ["default.py"]\nimport_paths = ["src"]\nstub_path = ["stubs"]\ntypeshed_path = "stdlib"\n', 'settings/check.toml')
        check_configured(root, config, expected=[('settings/default.py', n, 'incompatible_assignment') for n in (5, 6, 7)])
        check_configured(root, config, [root/'chosen.py'], expected=[('chosen.py', 1, 'incompatible_assignment')])
        empty = config_file(root)
        check_configured(root, empty, [root/'settings/default.py'], flags=['--import-paths', 'settings/src', '--stub-path', 'settings/stubs', '--typeshed-path', 'settings/stdlib'], expected=[('settings/default.py', n, 'incompatible_assignment') for n in (5, 6, 7)])


def test_category_switch_precedence():
    source = "def f() -> None:\n    x: int = 'bad'\n    missing\n    print(x)\n"
    with workspace({'sample.py': source}) as root:
        config = config_file(root)
        both = [('sample.py', 2, 'incompatible_assignment'), ('sample.py', 3, 'undefined_name')]
        for flags, expected in [([], both), (['--disable-all'], []),
            (['--disable-all', '--enable', 'undefined_name'], both[1:]),
            (['--enable', 'undefined_name', '--disable', 'undefined_name'], both[:1]),
            (['--disable', 'undefined_name', '--enable', 'undefined_name'], both[:1])]:
            check_configured(root, config, [root/'sample.py'], flags, expected)
        # Line 2 carries an unused suppression, a finding that is off by default,
        # so only a working collective enable can produce it.
        write_files(root, {'sample.py': "value: int = 'bad'\nother: int = 1  # static analysis: ignore[incompatible_assignment]\n"})
        assign, unused = ('sample.py',1,'incompatible_assignment'), ('sample.py',2,'unused_ignore')
        check_configured(root, config, [root/'sample.py'], [], [assign])
        check_configured(root, config, [root/'sample.py'], ['--enable-all'], [assign, unused])
        check_configured(root, config, [root/'sample.py'], ['--enable-all','--disable','incompatible_assignment'], [unused])
        check_configured(root, config, [root/'sample.py'], ['--disable-all','--enable','unused_ignore'], [unused])
        check_configured(root, config, [root/'sample.py'], ['--enable-all','--disable','incompatible_assignment','--disable','unused_ignore'])


def test_configuration_priority_and_module_scope():
    bad = "value: int = 'bad'\n"
    with workspace({'pkg/__init__.py':'', 'pkg/broad.py':bad, 'pkg/deep/__init__.py':'',
                    'pkg/deep/leaf.py':bad, 'other.py':bad, 'discarded.py':bad,
                    'oldstubs/contract/__init__.pyi':'def get() -> str: ...\n',
                    'newstubs/contract/__init__.pyi':'def get() -> int: ...\n',
                    'contract.py':'def get():\n    return 1\n',
                    'use.py':'from contract import get\ndef f() -> None:\n    value: str = get()\n    print(value)\n'}) as root:
        config_file(root, 'paths = ["discarded.py"]\nimport_paths = ["oldroot"]\nstub_path = ["oldstubs"]\nincompatible_assignment = false\n[[tool.velnora.overrides]]\nmodule = "pkg.deep"\nincompatible_assignment = false\n[[tool.velnora.overrides]]\nmodule = "other"\nincompatible_assignment = false\n', 'base.toml')
        config = config_file(root, 'extend_config = "base.toml"\npaths = ["pkg", "other.py", "use.py"]\nimport_paths = ["."]\nstub_path = ["newstubs"]\nincompatible_assignment = true\n[[tool.velnora.overrides]]\nmodule = "pkg"\nincompatible_assignment = false\n[[tool.velnora.overrides]]\nmodule = "pkg.deep"\nincompatible_assignment = true\n')
        check_configured(root, config, expected=[(p, n, 'incompatible_assignment') for p,n in [('pkg/deep/leaf.py',1),('other.py',1),('use.py',3)]])
        check_configured(root, config, flags=['--disable', 'incompatible_assignment'])
        check_configured(root, config, [root/'pkg'], flags=['--enable', 'incompatible_assignment'], expected=[(p,1,'incompatible_assignment') for p in ['pkg/broad.py','pkg/deep/leaf.py']])
        check_configured(root, config, [root/'use.py'], flags=['--stub-path', 'oldstubs'])
        blocks = displayed_options(root, config)
        for name, paths in [('paths', ['pkg', 'other.py', 'use.py']), ('import_paths', ['.']), ('stub_path', ['newstubs'])]:
            assert displayed_paths(blocks[name][0], root) == [(root/path).resolve() for path in paths]
        blocks = displayed_options(root, config, ['--import-paths', 'chosenroot'])
        assert displayed_paths(blocks['import_paths'][0], root) == [(root/'chosenroot').resolve()]


def test_invalid_configuration_is_refused():
    with workspace({'good.py':'value: int = 1\n'}) as root:
        good = config_file(root)
        check_configured(root, good, [root/'good.py'])
        configs = [root/'missing.toml']
        for name, body in {
            'cycle.toml':'extend_config = "cycle.toml"\n',
            'unknown.toml':'unknown_setting = true\n',
            'type.toml':'incompatible_assignment = "yes"\n',
            'override.toml':'[[tool.velnora.overrides]]\nincompatible_assignment = false\n',
        }.items():
            configs.append(config_file(root, body, name))
        for config in configs:
            result = check_source(root, ['--config-file', str(config), str(root/'good.py')])
            assert result.returncode == 1, result
            assert result.stderr.strip(), result


def test_checker_suppression_scope():
    base = "def f() -> None:\n    a: int = 'bad'\n    missing\n    b: int = 'bad'\n    print(a, b)\n"
    scenarios = [
        (base, [(2,'incompatible_assignment'),(3,'undefined_name'),(4,'incompatible_assignment')]),
        (base.replace("a: int = 'bad'", "a: int = 'bad'  # static analysis: ignore"), [(3,'undefined_name'),(4,'incompatible_assignment')]),
        (base.replace("    a:", "    # static analysis: ignore[incompatible_assignment]\n    a:"), [(4,'undefined_name'),(5,'incompatible_assignment')]),
        (base.replace('missing', 'missing  # static analysis: ignore[incompatible_assignment]'), [(2,'incompatible_assignment'),(3,'undefined_name'),(4,'incompatible_assignment')]),
        ("def f() -> None:\n    a: int = 'bad'; missing  # static analysis: ignore[incompatible_assignment]\n    print(a)\n", [(2,'undefined_name')]),
        ("def f() -> None:\n    # static analysis: ignore\n    a: int = 'bad'; missing\n    b: int = 'bad'\n    print(a, b)\n", [(4,'incompatible_assignment')]),
        ('# static analysis: ignore\n'+base, []),
        ("def f() -> None:\n    a: int = 'bad'  # static analysis: ignore[incompatible_assignment]\n    print(a)\n", []),
    ]
    for source, expected in scenarios:
        with workspace({'sample.py': source}) as root:
            check_configured(root, config_file(root), [root/'sample.py'], expected=[('sample.py',n,c) for n,c in expected])


def test_standard_ignore_scope():
    base = "def f() -> None:\n    a: int = 'bad'\n    b: int = 'bad'\n    print(a, b)\n"
    for source, lines in [(base,[2,3]),
        (base.replace("a: int = 'bad'", "a: int = 'bad'  # type: ignore"),[3]),
        ('# type: ignore\n'+base,[]),
        ('sentinel = 1\n# type: ignore\n'+base,[4,5])]:
        with workspace({'sample.py':source}) as root:
            check_configured(root, config_file(root), [root/'sample.py'], expected=[('sample.py',n,'incompatible_assignment') for n in lines])


def test_suppression_hygiene_is_optional():
    source = "def f() -> None:\n    a: int = 'bad'  # static analysis: ignore[incompatible_assignment]\n    b: int = 1  # static analysis: ignore[incompatible_assignment]\n    c: int = 'bad'  # static analysis: ignore\n    print(a, b, c)\n"
    with workspace({'sample.py':source}) as root:
        config = config_file(root)
        check_configured(root, config, [root/'sample.py'])
        check_configured(root, config, [root/'sample.py'], ['--enable','unused_ignore','--enable','bare_ignore'], [('sample.py',3,'unused_ignore'),('sample.py',4,'bare_ignore')])
        write_files(root, {'sample.py':'# static analysis: ignore\n'+source})
        check_configured(root, config, [root/'sample.py'], ['--enable','bare_ignore'])


def test_display_options_without_checking_source():
    with workspace({'never.py':"from pathlib import Path\nPath('executed').write_text('yes')\nraise RuntimeError('must not execute')\n"}) as root:
        config_file(root, 'incompatible_assignment = false\n', 'base.toml')
        config = config_file(root, 'extend_config = "base.toml"\npaths = ["never.py"]\nincompatible_assignment = true\n[[tool.velnora.overrides]]\nmodule = "pkg.deep"\nincompatible_assignment = false\n')
        blocks = displayed_options(root, config, ['--disable','incompatible_assignment'])
        value, overrides = blocks['incompatible_assignment']
        assert value == 'False'
        assert set(overrides) == {'False (from command line)', 'False (module: pkg.deep, from config file)', 'True (from config file)', 'False (from config file)'}
        assert not (root/'executed').exists()


def test_accumulated_policies_and_providers():
    import ast
    import re

    providers = '''class A:
    pass
class B:
    pass
class C:
    pass

def integer(self, value: int) -> None:
    pass

def text(self, value: str) -> None:
    pass

def base(typ):
    if typ in (A, B, C):
        return integer
    return None

def included(typ):
    if typ is B:
        return text
    return None

def command(typ):
    if typ is C:
        return text
    return None

def base_second(typ):
    if typ is A:
        return text
    return None

def included_second(typ):
    if typ is B:
        return integer
    return None

def command_second(typ):
    if typ is C:
        return integer
    return None

def exempt_a(value: int) -> None:
    pass

def exempt_b(value: int) -> None:
    pass

def exempt_c(value: int) -> None:
    pass
'''
    source = '''import math
import json
import decimal
from providers import A, B, C, exempt_a, exempt_b, exempt_c

def check() -> None:
    A('bad')
    B(2)
    C(3)
    exempt_a('bad')
    exempt_b('bad')
    exempt_c('bad')
    A(1)
    B('good')
    C('good')
import fractions
import datetime
import cmath
'''
    with workspace({'providers.py':providers, 'sample.py':source}) as root:
        config_file(root, 'disallowed_imports = ["math", "fractions"]\nignored_callees = ["providers.exempt_a"]\nconstructor_hooks = ["providers.base", "providers.base_second"]\n', 'base.toml')
        config = config_file(root, 'extend_config = "base.toml"\ndisallowed_imports = ["json", "datetime"]\nignored_callees = ["providers.exempt_b"]\nconstructor_hooks = ["providers.included", "providers.included_second"]\n[[tool.velnora.overrides]]\nmodule = "sample"\ndisallowed_imports = ["cmath"]\n')
        flags = ['--disallowed-imports','decimal','--ignored-callees','providers.exempt_c','--constructor-hooks','providers.command','--constructor-hooks','providers.command_second']
        check_configured(root, config, [root/'sample.py'], flags, [('sample.py',n,c) for n,c in [(1,'disallowed_import'),(2,'disallowed_import'),(3,'disallowed_import'),(16,'disallowed_import'),(17,'disallowed_import'),(18,'disallowed_import'),(7,'incompatible_argument'),(8,'incompatible_argument'),(9,'incompatible_argument')]])
        empty = config_file(root, name='empty.toml')
        # Each exemption has a live baseline on the same source and environment.
        check_configured(root, empty, [root/'sample.py'], flags=['--constructor-hooks','providers.command','--constructor-hooks','providers.included','--constructor-hooks','providers.base'], expected=[('sample.py',n,'incompatible_argument') for n in (7,8,9,10,11,12)])
        blocks = displayed_options(root, config, flags)
        assert ast.literal_eval(blocks['disallowed_imports'][0]) == ['decimal','json','datetime','math','fractions']
        # Function addresses are presentation-only; read the published function
        # representation with an address placeholder rather than pinning it.
        function_form = r'<function (\w+) at 0x[0-9a-fA-F]+>'
        assert re.fullmatch(r'\[' + function_form + r'(?:, ' + function_form + r')*\]', blocks['constructor_hooks'][0])
        assert re.findall(function_form, blocks['constructor_hooks'][0]) == [
            'command','command_second','included','included_second','base','base_second']
        configured_names = {'exempt_a', 'exempt_b', 'exempt_c'}
        displayed = blocks['ignored_callees'][0]
        entries = (re.findall(function_form, displayed) if re.search(function_form, displayed)
                   else [name.rpartition('.')[2] for name in ast.literal_eval(displayed)])
        exemptions = [name for name in entries if name in configured_names]
        assert exemptions == ['exempt_c', 'exempt_b', 'exempt_a']
