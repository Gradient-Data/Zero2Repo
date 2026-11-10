# feature: F16
"""Real application extensions exercised through the configured source CLI."""
from textwrap import dedent
from _helpers import workspace, read_json
from F02_helpers import config_file, check_configured

APPLICATION = '''
from velnora.error_code import register_error_code
from velnora.signature import Signature, SigParameter
from velnora.value import KnownValue, TypedValue

CATEGORY_DESCRIPTION = "Application selector policy"
category = register_error_code("application_policy", CATEGORY_DESCRIPTION)

def loose(*args, **kwargs): pass
class Record:
    def __init__(self, *args, **kwargs): pass

def select(value): pass

def inspect_call(ctx):
    value = ctx.vars["value"]
    if isinstance(value, KnownValue):
        if value.val == "blocked":
            ctx.show_error("Selector blocked by application", category)
        return TypedValue(bytes if isinstance(value.val, str) else int)
    if isinstance(value, TypedValue) and value.typ is str:
        ctx.show_error("Selector requires a known string", category)
        return TypedValue(str)
    return TypedValue(int)

def signatures(cache):
    return {
        loose: Signature.make([SigParameter("count", annotation=TypedValue(int))],
                              TypedValue(str), callable=loose),
        select: Signature.make([SigParameter("value")], impl=inspect_call, callable=select),
    }

def constructors(cls):
    if cls is Record:
        return Signature.make([SigParameter("self"), SigParameter("name", annotation=TypedValue(str))], TypedValue(Record))
    return None

class Field: pass
class Entity:
    title = Field()
class Wrapped:
    pass

def unwrap(cls):
    return Record if cls is Wrapped else cls

def attribute(attr):
    if isinstance(attr, Field):
        return TypedValue(str), TypedValue(int)
    return None

def resolve(obj, name):
    if obj is Entity and name == "virtual":
        return KnownValue(b"resolved")
    return None

def evaluate(text, count=1):
    if count < 0:
        raise ValueError("Negative repetition requested")
    return text * count
'''


def check_application(source, *, settings='', flags=(), base_settings=None):
    source = dedent(source).lstrip('\n')
    expected = []
    for line, text in enumerate(source.splitlines(), 1):
        if '# E: ' in text:
            expected.extend(('sample.py', line, code)
                            for code in text.split('# E: ', 1)[1].split(', '))
    source = '\n'.join(line.split('# E: ', 1)[0].rstrip()
                       for line in source.splitlines()) + '\n'
    with workspace({'application.py': APPLICATION, 'sample.py': source}) as root:
        if base_settings is not None:
            config_file(root, base_settings, 'base.toml')
            settings = 'extend_config = "base.toml"\n' + settings
        config = config_file(root, '''unused_variable = false
known_signatures = ["application.signatures"]
constructor_hooks = ["application.constructors"]
class_attribute_transformers = ["application.attribute"]
known_attribute_hook = ["application.resolve"]
unwrap_class = ["application.unwrap"]
functions_safe_to_call = ["application.evaluate"]
''' + settings)
        result = check_configured(root, config, [root / 'sample.py'], flags, expected)
        # Successful file checks need not create a JSON report. The shared
        # runner has already checked status zero and an empty error channel.
        if not expected:
            return result, None
        return result, read_json(root / 'report.json', result=result)
