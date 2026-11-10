# feature: F14
"""Formatting and regex acceptance through the source-checking CLI."""
from F03_helpers import check_types
from F04_helpers import check_extension_source
from F14_helpers import regex_syntax_error


def test_percent_conversion_families():
    # Every numeric spelling has both an accepted and a rejected operand.
    lines = [
        'class Indexed:',
        '    def __index__(self) -> int:',
        '        return 7',
        'def use(n: int, f: float, indexed: Indexed):',
    ]
    for conversion in 'diouxXeEfFgG':
        for prefix in ('', 'b'):
            for operand in ('n', 'f', 'indexed'):
                lines.append(f'    {prefix}"%{conversion}" % {operand}')
            lines.append(f'    {prefix}"%{conversion}" % "wrong"  # E: bad_format_string')
    lines.extend([
        '    "%s %r %a" % (object(), b"data", {"key": 1})',
        '    b"%s %b %r %a" % (b"data", b"more", "text", object())',
        '    "%% %d" % n',
        '    b"%% %d" % n',
    ])
    for prefix, character in (('', '"z"'), ('b', 'b"z"')):
        for operand in ('0', '255', character):
            lines.append(f'    {prefix}"%c" % {operand}')
        for operand in ('-1', '256', '3.5', '""' if not prefix else 'b""',
                        '"xy"' if not prefix else 'b"xy"'):
            lines.append(f'    {prefix}"%c" % {operand}  # E: bad_format_string')
    check_types('\n'.join(lines))


def test_replacement_fields_and_result_type():
    check_types('''
        from typing import assert_type
        def use(value: float, width: int):
            assert_type("{{item}} {}".format(value), str)
            assert_type("{name!r}".format(name=value), str)
            assert_type("{0:.{1}f}".format(value, width), str)
            assert_type("{value:>{width}}".format(value=value, width=width), str)
            assert_type("{0} {0}".format(value), str)
            "{".format()  # E: incompatible_call
            "}".format()  # E: incompatible_call
            "{0!q}".format(value)  # E: incompatible_call
            "{} {}".format(value)  # E: incompatible_call
            "{1}".format()  # E: incompatible_call
            "{absent}".format()  # E: incompatible_call
            "{0:.{1}f}".format(value)  # E: incompatible_call
            "{value:>{width}}".format(value=value)  # E: incompatible_call
            "{}".format(value, width)  # E: incompatible_call
            "{value}".format(value=value, width=width)  # E: incompatible_call
            assert_type("{}".format(value), int)  # E: inference_failure
    ''')


def test_missing_interpolation_prefix_opt_in():
    source = '''
        def consume(template: str, **kwargs: object) -> None:
            pass
        def use(name: str, count: int):
            "standalone {name}"
            explicit = "hello {name}".format(name=name)
            consume("hello {name} {count}", name=name, count=count)
            unknown = "hello {missing}"
            mixed = "hello {name} {missing}"
            malformed = "hello {name +}"
            valid = f"hello {name}"
            first = "hello {name}"
            second = "count {count + 1} for {name}"
            "another standalone {name}"
            "%d" % "invalid"  # E: bad_format_string
            return first, second
    '''
    check_extension_source(source)
    # Recreate the same project; only the diagnostic enablement differs.
    check_extension_source(source, options=('--enable', 'missing_f'),
                           extra_errors={11: 'missing_f', 12: 'missing_f'})


def test_regex_operations_and_annotations():
    patterns = [
        r'[a-z]+', r'(?i:alpha)$', r'(?x) a \s+ b', r'(?P<word>ab)(?P=word)',
        r'[', r'(abc', r'[z-a]', r'(?P<word>a)(?P<word>b)', r'(?P=missing)',
        r'(?<=a+)b', r'(?i)abc', r'abc(?i)',
        b'[a-z]+', b'(?i:abc)', b'(', b'[z-a]',
    ]
    lines = [
        'import re',
        'from typing import Annotated',
        'from velnora.extensions import ValidRegex',
        'def accept(pattern: Annotated[str | bytes, ValidRegex()]):',
        '    pass',
        'def use(unknown: str, unknown_bytes: bytes):',
        '    re.compile(unknown)',
        '    re.compile(unknown_bytes)',
        '    accept(unknown)',
        '    accept(unknown_bytes)',
    ]
    reasons = {}
    for pattern in patterns:
        reason = regex_syntax_error(pattern)
        reasons[pattern] = reason
        suffix = '  # E: incompatible_call' if reason is not None else ''
        subject = b'abc' if isinstance(pattern, bytes) else 'abc'
        lines.append(f'    re.compile({pattern!r}){suffix}')
        lines.append(f'    re.match({pattern!r}, {subject!r}){suffix}')
        lines.append(f'    re.sub({pattern!r}, {subject!r}, {subject!r}){suffix}')
        suffix = '  # E: invalid_regex' if reason is not None else ''
        lines.append(f'    accept({pattern!r}){suffix}')
    try:
        check_types('\n'.join(lines))
    except AssertionError as error:
        raise AssertionError(f'Standard regex parser results: {reasons!r}') from error


def test_percent_argument_binding():
    check_types('''
        def use(value: object):
            "%(name)s %(count)d" % {"name": "row", "count": 4}
            b"%(name)s %(count)d" % {b"name": b"row", b"count": 4}
            "%*.*f %s" % (8, 2, 1.25, "tail")
            b"%*.*f %s" % (8, 2, 1.25, b"tail")
            "%s %r %a" % (b"bytes", value, value)
            b"%r %a" % (value, "text")
            "%(missing)s" % {}  # E: bad_format_string
            "%(name)s" % 2  # E: bad_format_string
            "%(count)d" % {"count": "bad"}  # E: bad_format_string
            "%s %s" % ("one",)  # E: bad_format_string
            "%s" % ("one", "two")  # E: bad_format_string
            "%*s" % ("wide", "text")  # E: bad_format_string
            "%.*f" % (1.5, 2.0)  # E: bad_format_string
            "%*.*f" % (8, 2, "bad")  # E: bad_format_string
            "%*s" % ("text", 8)  # E: bad_format_string
            "%q" % 3  # E: bad_format_string
            "%b" % b"data"  # E: bad_format_string
            b"%s" % "text"  # E: bad_format_string
            b"%b" % 4  # E: bad_format_string
            "%c" % b"a"  # E: bad_format_string
            b"%c" % "a"  # E: bad_format_string
    ''')
