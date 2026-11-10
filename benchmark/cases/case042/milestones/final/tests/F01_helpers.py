# feature: F01
"""Caller-owned documents and observations through public metadata entries."""
import json
import pytest
from typing_extensions import TypedDict
from velnora_metadata import VelnoraV2ZAttrsJSON


class AttributeEnvelope(TypedDict):
    attributes: VelnoraV2ZAttrsJSON

from _helpers import invoke
from velnora_metadata.model import (
    MetadataValidationError, VelnoraV2ArrayMetadata, VelnoraV3ArrayMetadata,
    validate_array_metadata_v2, validate_array_metadata_v3,
)


def metadata_json(value):
    """Compare JSON meaning without pinning tuple/list or member order."""
    return json.loads(json.dumps(value))


def assert_metadata_document(actual, expected):
    """Check represented input properties through either declaration envelope.

    A named declaration may be a string or an object. Expanded declarations may
    include omitted configuration defaults; all explicitly supplied information
    must still survive. Attribute values are compared as data, never declarations.
    """
    actual, expected = metadata_json(actual), metadata_json(expected)

    def declaration(got, wanted):
        got = {'name': got} if isinstance(got, str) else got
        wanted = {'name': wanted} if isinstance(wanted, str) else wanted
        assert got['name'] == wanted['name']
        if 'must_understand' in wanted:
            assert got.get('must_understand', True) == wanted['must_understand']
        for key, value in wanted.get('configuration', {}).items():
            assert got['configuration'][key] == value

    for key, value in expected.items():
        assert key in actual
        if expected.get('zarr_format') == 3 and key in (
                'data_type', 'chunk_grid', 'chunk_key_encoding'):
            declaration(actual[key], value)
        elif expected.get('zarr_format') == 3 and key in ('codecs', 'storage_transformers'):
            assert len(actual[key]) == len(value)
            for got, wanted in zip(actual[key], value, strict=True):
                declaration(got, wanted)
        elif key == 'metadata':
            assert set(actual[key]) == set(value)
            for path, document in value.items():
                assert_metadata_document(actual[key][path], document)
        elif key == 'consolidated_metadata':
            assert_metadata_document(actual[key], value)
        else:
            assert actual[key] == value


def named(name, **configuration):
    return {"name": name, "configuration": configuration}


def array_document(version=3, shape=(12, 8), chunks=(4, 2), **changes):
    if version == 3:
        doc = dict(zarr_format=3, node_type="array", shape=list(shape),
                   data_type="uint8", fill_value=7,
                   chunk_grid=named("regular", chunk_shape=list(chunks)),
                   chunk_key_encoding="default", codecs=["bytes"])
    else:
        doc = dict(zarr_format=2, shape=list(shape), chunks=list(chunks),
                   dtype="|u1", fill_value=7, order="C", filters=None, compressor=None)
    return doc | changes


def problem_pairs(problems):
    return {(tuple(p.loc), p.kind) for p in problems}


def has_problem(found, expected, document):
    """Accept an offending item or its enclosing sequence, preserving fields.

    Expected paths identify the actual bad item. A validator may aggregate a
    sequence error at its container; it must still identify the same named
    field and category, and cannot point at a different item or nested field.
    For a whole-sequence violation, an existing member is also a valid location.
    A problem with an encoding entry's configuration may be reported at that entry.
    The expected category may be a set when the documents leave the label open.
    """
    loc, kind = expected
    loc = tuple(loc)
    kinds = {kind} if isinstance(kind, str) else set(kind)
    for actual, actual_kind in found:
        if actual_kind not in kinds:
            continue
        if actual == loc:
            return True
        if (len(loc) >= 2 and loc[-1] == "configuration" and type(loc[-2]) is int
                and actual == loc[:-1]):
            return True
        if (actual_kind in {"invalid_type", "invalid_value"} and actual
                and loc[:len(actual)] == actual
                and all(type(part) is int for part in loc[len(actual):])):
            return True
        if (actual_kind in {"invalid_type", "invalid_value"}
                and actual[:len(loc)] == loc):
            value = document
            for part in loc:
                value = value[part]
            for part in actual[len(loc):]:
                if (type(part) is not int or not isinstance(value, (list, tuple))
                        or not 0 <= part < len(value)):
                    break
                value = value[part]
            else:
                return True
    return False


def refused(entry, value, expected, **kwargs):
    with pytest.raises(MetadataValidationError) as raised:
        invoke(entry, value, call_kwargs=kwargs)
    found = problem_pairs(raised.value.problems)
    assert all(has_problem(found, problem, value) for problem in expected), (expected, found)
    return found


def array_accepts(doc, *, context=None):
    version = 3 if "node_type" in doc else 2
    model, validator = ((VelnoraV3ArrayMetadata, validate_array_metadata_v3) if version == 3
                        else (VelnoraV2ArrayMetadata, validate_array_metadata_v2))
    kwargs = {} if context is None else {"context": context}
    assert invoke(validator, doc, call_kwargs=kwargs).value == ()
    return invoke(model.from_json, doc, call_kwargs=kwargs).value


def array_refuses(doc, loc, kind="invalid_value", *, context=None):
    version = 3 if "node_type" in doc else 2
    model, validator = ((VelnoraV3ArrayMetadata, validate_array_metadata_v3) if version == 3
                        else (VelnoraV2ArrayMetadata, validate_array_metadata_v2))
    kwargs = {} if context is None else {"context": context}
    expected = (tuple(loc), kind)
    found = problem_pairs(invoke(validator, doc, call_kwargs=kwargs).value)
    assert has_problem(found, expected, doc), (expected, found)
    refused(model.from_json, doc, [expected], **kwargs)


def fill_document(data_type, fill_value):
    # Unknown encoding leaves fill validation independent of serialization support.
    return array_document(data_type=data_type, fill_value=fill_value, codecs=["vendor.serialize"])


def shard_document(inner=(2, 2), codecs=None, index_codecs=None):
    return array_document(codecs=[named("sharding_indexed", chunk_shape=list(inner),
        codecs=["bytes"] if codecs is None else codecs,
        index_codecs=[named("bytes", endian="little"), "crc32c"]
        if index_codecs is None else index_codecs)])
