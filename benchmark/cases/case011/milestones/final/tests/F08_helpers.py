# feature: F08
"""Observation helpers for evaluation options (FP-08).

New names only. Sealed F03–F07 helpers are imported, not copied.
A predecessor that is not sealed on this walk is not imported.
A helper that cannot classify its input raises; it never returns
``None``, ``False``, ``[]``, or ``0`` to mean "no options result".
"""

from __future__ import annotations

import collections
from collections.abc import Mapping
from typing import Any, Callable

from _harness import (
    CallResult,
    HarnessError,
    call,
    call_method,
    evaluation_options,
)
from F03_helpers import (
    _bracket_search_entry,
    assert_bracket_search_is_value_error,
    compile_bracket_expression,
    require_bracket_value,
    require_bracket_value_error,
)
from F07_helpers import fn_ident

# Attribute name of the search callable on a successful compile result.
_PARSED_SEARCH = "search"

# Built-in names a custom length / extra function must not reuse.
_BUILTIN_NAMES = frozenset(
    {
        "abs",
        "avg",
        "ceil",
        "contains",
        "ends_with",
        "floor",
        "join",
        "keys",
        "length",
        "map",
        "max",
        "max_by",
        "merge",
        "min",
        "min_by",
        "not_null",
        "reverse",
        "sort",
        "sort_by",
        "starts_with",
        "sum",
        "to_array",
        "to_number",
        "to_string",
        "type",
        "values",
    }
)
_FORBIDDEN_LENGTH_NAMES = _BUILTIN_NAMES | frozenset(
    {"length0", "custom_add", "my_subtract"}
)
_PUBLIC_FN_NAMES = frozenset({"custom_add", "my_subtract"})


def _provider_surface() -> tuple[type, Callable[..., Any]]:
    """Return the public function-provider attachment surface.

    Custom argument types have no route through the package-root
    search/compile entries alone. The provider that carries the FP-07
    built-in set and declared parameter types is imported from its
    submodule.
    """
    from pathsel.functions import Functions, signature

    if not callable(Functions):
        raise HarnessError("function provider type is not callable")
    if not callable(signature):
        raise HarnessError("function signature attachment is not callable")
    return Functions, signature


def _require_options(options: Any, *, label: str) -> Any:
    if options is None:
        raise HarnessError(
            f"{label} refuses options is None; that is the F01 no-options path"
        )
    return options


def _require_function_ident(
    name: str, *, label: str, forbid: frozenset[str] | None = None
) -> str:
    if not isinstance(name, str) or name == "":
        raise HarnessError(f"{label} requires a non-empty str name, got {name!r}")
    first = name[0]
    if not (first == "_" or (first.isascii() and first.isalpha())):
        raise HarnessError(
            f"{label} must start with a Latin letter or '_': {name!r}"
        )
    if any(not (ch == "_" or ch.isalnum()) for ch in name):
        raise HarnessError(f"{label} is not a legal unquoted identifier: {name!r}")
    blocked = _BUILTIN_NAMES if forbid is None else forbid
    if name in blocked:
        raise HarnessError(f"{label} reused a reserved function name: {name!r}")
    return name


def _extending_provider(
    entries: list[tuple[str, tuple[Any, ...], Callable[..., Any]]],
) -> Any:
    """Build a provider that extends the built-in set with *entries*.

    Each entry is ``(name, signature_args, impl)``. *impl* is
    ``(self, *args) -> value``. Class creation registers the names;
    failure to produce a provider raises.
    """
    if not entries:
        raise HarnessError("_extending_provider requires at least one function")
    Functions, signature = _provider_surface()
    attrs: dict[str, Any] = {}
    for name, sig_args, impl in entries:
        if not callable(impl):
            raise HarnessError(f"provider impl for {name!r} is not callable")
        bound = signature(*sig_args)(impl)
        attrs["_func_" + name] = bound
    try:
        cls = type("ExtendingFunctions", (Functions,), attrs)
    except Exception as exc:
        raise HarnessError(f"cannot construct extending provider: {exc}") from exc
    try:
        provider = cls()
    except Exception as exc:
        raise HarnessError(f"cannot instantiate extending provider: {exc}") from exc
    print(
        f"extending_provider names={[name for name, _, _ in entries]!r}",
        flush=True,
    )
    return provider


def oneshot_search_with_options(
    expression: str, document: Any, options: Any
) -> CallResult:
    """Search *expression* against *document* with a caller-owned options object.

    Options are a positional argument of the one-shot search entry.
    ``options is None`` raises — that is the F01 no-options path.
    """
    if not isinstance(expression, str):
        raise HarnessError(
            f"oneshot_search_with_options requires str expression, "
            f"got {type(expression)!r}"
        )
    opts = _require_options(options, label="oneshot_search_with_options")
    print(f"oneshot_with_options expression={expression!r}", flush=True)
    return call(_bracket_search_entry(), expression, document, opts)


def search_parsed_with_options(parsed: Any, document: Any, options: Any) -> CallResult:
    """Search a compiled expression against *document* with options.

    Options are a positional argument of the parsed-expression search.
    ``options is None`` raises. Does not compile.
    """
    if parsed is None:
        raise HarnessError("search_parsed_with_options has no parsed expression")
    opts = _require_options(options, label="search_parsed_with_options")
    print("search_parsed_with_options", flush=True)
    return call_method(parsed, _PARSED_SEARCH, document, opts)


def require_oneshot_with_options_equals(
    expression: str, document: Any, options: Any, expected: object
) -> object:
    """Search once with options and require the value to equal *expected*."""
    value = require_bracket_value(
        oneshot_search_with_options(expression, document, options)
    )
    print(
        f"oneshot_with_options_equals expression={expression!r} "
        f"value={value!r} expected={expected!r}",
        flush=True,
    )
    assert value == expected, (
        f"{expression!r} with options yielded {value!r}, expected {expected!r}"
    )
    return value


def compile_once_then_search_with_options(
    expression: str, document: Any, options: Any
) -> Any:
    """Compile once, then search the same parsed object twice with *options*.

    Compile does not receive options. The second search must not compile
    again. The two searches must agree. Returns that value.
    """
    opts = _require_options(options, label="compile_once_then_search_with_options")
    parsed = require_bracket_value(compile_bracket_expression(expression))
    first = require_bracket_value(search_parsed_with_options(parsed, document, opts))
    second = require_bracket_value(search_parsed_with_options(parsed, document, opts))
    print(
        f"compile_once_with_options expression={expression!r} "
        f"first={first!r} second={second!r}",
        flush=True,
    )
    assert first == second, (
        "second search of the same parsed expression disagreed with the first "
        f"({first!r} vs {second!r}); a new compile must not be required"
    )
    return first


def order_preserving_mapping_type() -> type:
    """The order-preserving mapping type ``collections.OrderedDict``.

    It is the order-preserving mapping type the PRD (FP-08) names as an
    object for every purpose of the language, including built-in function
    arguments. A type that cannot be contrasted with the host ordinary
    mapping raises.
    """
    mapping_type = collections.OrderedDict
    if mapping_type is type({}):
        raise HarnessError(
            "order-preserving mapping type is the host ordinary mapping"
        )
    sample = mapping_type()
    if type(sample) is type({}):
        raise HarnessError(
            "order-preserving mapping type instances are host ordinary mappings"
        )
    if type(sample) is not mapping_type:
        raise HarnessError(
            "order-preserving mapping type did not construct its own instances"
        )
    print(f"order_preserving_mapping_type={mapping_type!r}", flush=True)
    return mapping_type


def require_mapping_of_type(value: Any, mapping_type: type) -> Mapping:
    """Require ``type(value) is mapping_type``.

    A non-mapping, a type mismatch, or a failure to read the type raises
    — never ``False``. A supplied type that is ``type({})`` raises: that
    type cannot be contrasted with the host ordinary mapping.
    """
    if mapping_type is type({}):
        raise HarnessError(
            "supplied mapping type is the host ordinary mapping; "
            "cannot contrast constructed hashes with merge / no-options"
        )
    try:
        observed_type = type(value)
    except Exception as exc:
        raise HarnessError(f"cannot read type of constructed value: {exc}") from exc
    if value is None:
        raise HarnessError("expected a mapping of the supplied type; got successful null")
    if isinstance(value, (str, list)):
        raise HarnessError(
            f"expected a mapping of the supplied type; "
            f"got {type(value).__name__} {value!r}"
        )
    if not isinstance(value, Mapping):
        raise HarnessError(
            f"expected a mapping of the supplied type; "
            f"got {type(value).__name__} {value!r}"
        )
    print(
        f"mapping_of_type observed={observed_type!r} expected={mapping_type!r} "
        f"keys={list(value.keys())!r}",
        flush=True,
    )
    if observed_type is not mapping_type:
        raise HarnessError(
            "constructed mapping is not the supplied type: "
            f"got {observed_type!r}, expected {mapping_type!r}"
        )
    return value


def require_host_ordinary_mapping(value: Any) -> Mapping:
    """Require ``type(value) is type({})``.

    A value that is not a mapping, or whose type is not the host
    ordinary mapping, raises — never ``False``. This is the positive
    carrier for merge and for a no-options constructed hash.
    """
    try:
        observed_type = type(value)
    except Exception as exc:
        raise HarnessError(f"cannot read type of mapping value: {exc}") from exc
    if value is None:
        raise HarnessError("expected a host ordinary mapping; got successful null")
    if isinstance(value, (str, list)):
        raise HarnessError(
            f"expected a host ordinary mapping; got {type(value).__name__} {value!r}"
        )
    if not isinstance(value, Mapping):
        raise HarnessError(
            f"expected a host ordinary mapping; got {type(value).__name__} {value!r}"
        )
    print(
        f"host_ordinary_mapping type={observed_type!r} keys={list(value.keys())!r}",
        flush=True,
    )
    if observed_type is not type({}):
        raise HarnessError(
            "expected the host ordinary mapping type; "
            f"got {observed_type!r}"
        )
    return value


def empty_evaluation_options() -> Any:
    """Return a real empty options object: no mapping type, no provider.

    The two slots exist and are unset. An object with neither slot would
    be unclassifiable on the search entry (the entry reads both).
    """
    return evaluation_options(dict_cls=None, custom_functions=None)


def options_with_mapping_type(mapping_type: type) -> Any:
    """Options object that supplies only a mapping type."""
    if mapping_type is type({}):
        raise HarnessError(
            "options_with_mapping_type refuses the host ordinary mapping type"
        )
    return evaluation_options(dict_cls=mapping_type, custom_functions=None)


def options_with_provider(provider: Any) -> Any:
    """Options object that supplies only a custom function provider."""
    if provider is None:
        raise HarnessError("options_with_provider refuses provider is None")
    return evaluation_options(dict_cls=None, custom_functions=provider)


def options_with_mapping_and_provider(mapping_type: type, provider: Any) -> Any:
    """Options object that supplies both slots together."""
    if mapping_type is type({}):
        raise HarnessError(
            "options_with_mapping_and_provider refuses the host ordinary "
            "mapping type"
        )
    if provider is None:
        raise HarnessError(
            "options_with_mapping_and_provider refuses provider is None"
        )
    return evaluation_options(dict_cls=mapping_type, custom_functions=provider)


def extending_binary_number_provider(add_name: str, sub_name: str) -> Any:
    """Extend the built-in set with two two-number functions: sum and difference.

    *add_name* and *sub_name* must be non-empty identifiers. Public
    oracle names are allowed for the named arms.
    """
    add = _require_function_ident(add_name, label="extending_binary_number_provider add")
    sub = _require_function_ident(sub_name, label="extending_binary_number_provider sub")
    if add == sub:
        raise HarnessError(
            f"extending_binary_number_provider add and sub must differ: {add!r}"
        )
    number = ({"types": ["number"]}, {"types": ["number"]})

    def _add(self: Any, left: Any, right: Any) -> Any:
        return left + right

    def _sub(self: Any, left: Any, right: Any) -> Any:
        return left - right

    return _extending_provider(
        [
            (add, number, _add),
            (sub, number, _sub),
        ]
    )


def extending_two_number_function_provider(
    name: str, *, subtract: bool = False
) -> Any:
    """Extend the built-in set with one two-number function (sum or difference)."""
    ident = _require_function_ident(
        name, label="extending_two_number_function_provider"
    )
    number = ({"types": ["number"]}, {"types": ["number"]})
    if subtract:

        def _sub(self: Any, left: Any, right: Any) -> Any:
            return left - right

        impl = _sub
    else:

        def _add(self: Any, left: Any, right: Any) -> Any:
            return left + right

        impl = _add
    return _extending_provider([(ident, number, impl)])


def extending_null_tolerant_length_provider(name: str) -> Any:
    """Extend the built-in set with a string/array/object/null length.

    *name* must be a process-local identifier — not ``length``,
    ``length0``, a built-in, or a public custom-function oracle name.
    Null maps to 0; otherwise the host ``len``.
    """
    ident = _require_function_ident(
        name,
        label="extending_null_tolerant_length_provider",
        forbid=_FORBIDDEN_LENGTH_NAMES,
    )
    if ident in _PUBLIC_FN_NAMES:
        raise HarnessError(
            f"extending_null_tolerant_length_provider reused a public "
            f"custom-function name: {ident!r}"
        )

    def _length(self: Any, value: Any) -> int:
        if value is None:
            return 0
        return len(value)

    accepted = (
        {"types": ["string", "array", "object", "null"]},
    )
    return _extending_provider([(ident, accepted, _length)])


def process_local_function_name() -> str:
    """Process-local function name that is not a built-in or public oracle."""
    token = fn_ident()
    if token in _FORBIDDEN_LENGTH_NAMES or token in _PUBLIC_FN_NAMES:
        raise HarnessError(
            f"process_local_function_name collided with a reserved name: {token}"
        )
    print(f"process_local_function_name={token!r}", flush=True)
    return token


def published_function_call_kind_examples() -> tuple[
    BaseException, BaseException, BaseException
]:
    """Capture the three published F07 function-call kind examples.

    ``unknown_function(`1`, `2`)``, ``abs()``, and ``abs(str)``. The
    type example needs a current value named ``str``. Kind is the
    caller-visible marker F07 already names; this helper does not grade
    leftover wording.
    """
    document = {"str": "Str"}
    unknown = assert_bracket_search_is_value_error(
        "unknown_function(`1`, `2`)", document
    )
    arity = assert_bracket_search_is_value_error("abs()", document)
    typed = assert_bracket_search_is_value_error("abs(str)", document)
    print(
        "published_function_call_kind_examples "
        f"unknown={type(unknown).__name__} arity={type(arity).__name__} "
        f"typed={type(typed).__name__}",
        flush=True,
    )
    return unknown, arity, typed


def assert_search_with_options_is_value_error(
    expression: str, document: Any, options: Any
) -> ValueError:
    """One-shot search with options is a value error.

    The call must not return *document* and must not succeed as none.
    Unclassifiable outcomes raise.
    """
    opts = _require_options(options, label="assert_search_with_options_is_value_error")
    result = oneshot_search_with_options(expression, document, opts)
    if result.exception is None:
        raise HarnessError(
            f"search of {expression!r} with options succeeded "
            f"(value={result.value!r}); expected a value error, not a "
            "successful null, 0, [], 3, or the document"
        )
    if result.value is document:
        raise HarnessError(
            f"failed search of {expression!r} yielded the input document"
        )
    exc = require_bracket_value_error(result)
    print(f"search_with_options_value_error expression={expression!r}", flush=True)
    return exc


def assert_parsed_search_with_options_is_value_error(
    parsed: Any, document: Any, options: Any
) -> ValueError:
    """Parsed-expression search with options is a value error.

    The call must not return *document* and must not succeed as none.
    Unclassifiable outcomes raise.
    """
    if parsed is None:
        raise HarnessError(
            "assert_parsed_search_with_options_is_value_error has no parsed "
            "expression"
        )
    opts = _require_options(
        options, label="assert_parsed_search_with_options_is_value_error"
    )
    result = search_parsed_with_options(parsed, document, opts)
    if result.exception is None:
        raise HarnessError(
            f"parsed search with options succeeded (value={result.value!r}); "
            "expected a value error, not a successful null, 0, [], 3, "
            "or the document"
        )
    if result.value is document:
        raise HarnessError("failed parsed search yielded the input document")
    exc = require_bracket_value_error(result)
    print("parsed_search_with_options_value_error", flush=True)
    return exc


__all__ = (
    "assert_parsed_search_with_options_is_value_error",
    "assert_search_with_options_is_value_error",
    "compile_once_then_search_with_options",
    "empty_evaluation_options",
    "extending_binary_number_provider",
    "extending_null_tolerant_length_provider",
    "extending_two_number_function_provider",
    "oneshot_search_with_options",
    "options_with_mapping_and_provider",
    "options_with_mapping_type",
    "options_with_provider",
    "order_preserving_mapping_type",
    "process_local_function_name",
    "published_function_call_kind_examples",
    "require_host_ordinary_mapping",
    "require_mapping_of_type",
    "require_oneshot_with_options_equals",
    "search_parsed_with_options",
)
