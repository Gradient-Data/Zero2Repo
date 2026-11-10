# feature: F01
"""Acceptance checks for standalone metadata; no array contents are accessed."""
import json
import math
from dataclasses import replace

import pytest
from typing_extensions import TypedDict
from velnora_metadata import VelnoraV2ZAttrsJSON
from velnora_metadata.typed_json import check
from velnora_metadata.model import (
    MetadataValidationError, UNSET, VelnoraV2ArrayMetadata, VelnoraV3ArrayMetadata,
    VelnoraV2GroupMetadata, VelnoraV3GroupMetadata,
    VelnoraV2ConsolidatedMetadata, VelnoraV3ConsolidatedMetadata,
    validate_group_metadata_v2, validate_group_metadata_v3,
)
from velnora_metadata.v3.definition import (
    CORE, CORE_AND_EXTENSIONS, Context, DataTypeDefinition, ChunkGridDefinition,
    ChunkKeyEncodingDefinition, CodecDefinition, StorageTransformerDefinition,
    canonicalize, resolve,
)
from F01_helpers import (
    AttributeEnvelope, metadata_json, named, array_document, problem_pairs, refused,
    array_accepts, array_refuses, fill_document, shard_document, assert_metadata_document,
)


def test_document_exchange():
    # F01.T01: caller input is also an independent oracle for output content.
    attrs = {"experiment": {"labels": ["north", "south"], "count": 19}}
    for cls, doc in (
        (VelnoraV2ArrayMetadata, array_document(2, attributes=attrs)),
        (VelnoraV3ArrayMetadata, array_document(attributes=attrs, dimension_names=["y", None])),
        (VelnoraV2GroupMetadata, {"zarr_format": 2, "attributes": attrs}),
        (VelnoraV3GroupMetadata, {"zarr_format": 3, "node_type": "group", "attributes": attrs}),
    ):
        model = cls.from_json(doc)
        out = metadata_json(model.to_json())
        assert_metadata_document(out, doc)
        assert_metadata_document(cls.from_key_value(model.to_key_value()).to_json(), doc)
    checked, problems = check({"attributes": attrs}, AttributeEnvelope)
    assert problems == ()
    assert metadata_json(checked["attributes"]) == attrs
    bad, problems = check({"attributes": ["not an attribute object"]}, AttributeEnvelope)
    assert bad is None
    assert (("attributes",), "invalid_type") in problem_pairs(problems)

    merged2 = {"zarr_consolidated_format": 1, "metadata": {
        ".zgroup": {"zarr_format": 2}, ".zattrs": attrs,
        "branch/.zgroup": {"zarr_format": 2}, "branch/a/.zarray": array_document(2),
    }}
    m2 = VelnoraV2ConsolidatedMetadata.from_json(merged2)
    assert_metadata_document(m2.to_json(), merged2)
    assert_metadata_document(json.loads(m2.to_key_value()[".zmetadata"]), merged2)
    assert_metadata_document(VelnoraV2ConsolidatedMetadata.from_key_value(m2.to_key_value()).to_json(), merged2)
    merged3 = {"kind": "inline", "must_understand": False, "metadata": {
        "branch": {"zarr_format": 3, "node_type": "group", "attributes": attrs},
        "branch/a": array_document(attributes=attrs),
    }}
    m3 = VelnoraV3ConsolidatedMetadata.from_json(merged3)
    assert_metadata_document(m3.to_json(), merged3)
    group = VelnoraV3GroupMetadata.from_json({"zarr_format": 3, "node_type": "group",
                                          "consolidated_metadata": merged3})
    stored = group.to_key_value()
    assert_metadata_document(json.loads(stored["zarr.json"])["consolidated_metadata"], merged3)
    reread = VelnoraV3GroupMetadata.from_key_value(stored)
    assert_metadata_document(reread.consolidated_metadata.to_json(), merged3)
    assert reread.consolidated_metadata.metadata["branch/a"].shape == (12, 8)


def test_strict_document_problems():
    # F01.T02: every required member is checked individually, without a cross-product.
    for version, required in ((2, ("zarr_format", "shape", "chunks", "dtype", "fill_value", "order", "filters", "compressor")),
                              (3, ("zarr_format", "node_type", "shape", "data_type", "fill_value", "chunk_grid", "chunk_key_encoding", "codecs"))):
        doc = array_document(version)
        array_accepts(doc)
        for key in required:
            broken = dict(doc)
            del broken[key]
            # Preserve dispatch even when the declared format itself is missing.
            cls = VelnoraV2ArrayMetadata if version == 2 else VelnoraV3ArrayMetadata
            refused(cls.from_json, broken, [((key,), "missing_key")])
        array_refuses(doc | {"zarr_format": 9}, ("zarr_format",))
        array_refuses(doc | {"shape": "large"}, ("shape",), "invalid_type")
        array_refuses(doc | {"shape": [-1, 8]}, ("shape", 0))
    array_refuses(array_document(node_type="group"), ("node_type",))
    array_refuses(array_document(data_type=42), ("data_type",), "invalid_type")
    array_refuses(array_document(attributes=[]), ("attributes",), "invalid_type")
    array_refuses(array_document(dimension_names=["x"]), ("dimension_names",))
    array_refuses(array_document(dimension_names=["x", 4]), ("dimension_names", 1), "invalid_type")
    array_refuses(array_document(codecs=[named("bytes", unexpected=1)]),
                  ("codecs", 0, "configuration", "unexpected"), "unknown_key")
    for cls, validator, doc in (
        (VelnoraV2GroupMetadata, validate_group_metadata_v2, {"zarr_format": 2}),
        (VelnoraV3GroupMetadata, validate_group_metadata_v3, {"zarr_format": 3, "node_type": "group"}),
    ):
        assert validator(doc) == ()
        assert metadata_json(cls.from_json(doc).to_json()).get("attributes", {}) == {}
        for key in doc:
            bad = dict(doc)
            del bad[key]
            refused(cls.from_json, bad, [((key,), "missing_key")])
        refused(cls.from_json, doc | {"zarr_format": 0}, [(("zarr_format",), "invalid_value")])
    refused(VelnoraV3ArrayMetadata.from_key_value, {"zarr.json": b'{'},
            [(("zarr.json",), "invalid_json")])
    for doc, loc, kind in (({"metadata": {}}, ("zarr_consolidated_format",), "missing_key"),
                           ({"zarr_consolidated_format": 2, "metadata": {}}, ("zarr_consolidated_format",), "invalid_value"),
                           ({"zarr_consolidated_format": 1}, ("metadata",), "missing_key"),
                           ({"zarr_consolidated_format": 1, "metadata": 3}, ("metadata",), "invalid_type")):
        refused(VelnoraV2ConsolidatedMetadata.from_json, doc, [(loc, kind)])
    inline = {"kind": "inline", "must_understand": False, "metadata": {}}
    assert VelnoraV3ConsolidatedMetadata.from_json(inline).metadata == {}
    for doc, loc, kind in (({"must_understand": False, "metadata": {}}, ("kind",), "missing_key"),
                           (inline | {"kind": "other"}, ("kind",), "invalid_value"),
                           ({"kind": "inline", "must_understand": False}, ("metadata",), "missing_key"),
                           (inline | {"metadata": 3}, ("metadata",), "invalid_type"),
                           (inline | {"metadata": {"a": {"zarr_format": 3, "node_type": "other"}}},
                            ("metadata", "a", "node_type"), "invalid_value")):
        refused(VelnoraV3ConsolidatedMetadata.from_json, doc, [(loc, kind)])
    for field, value in (("filters", [3]), ("compressor", 3), ("dtype", 42), ("chunks", "x")):
        array_refuses(array_document(2) | {field: value}, (field,), "invalid_type")
    array_refuses(array_document(2) | {"order": "Z"}, ("order",))


def test_shapes_chunks_and_dimension_names():
    # F01.T03
    for version in (2, 3):
        for shape, chunks in (((), ()), ((0, 5), (3, 2)), ((3, 2), (8, 9))):
            doc = array_document(version, shape=shape, chunks=chunks)
            if version == 3:
                doc["dimension_names"] = [None] * len(shape)
            model = array_accepts(doc)
            assert model.shape == shape
            if version == 3:
                assert model.dimension_names == (None,) * len(shape)
                assert tuple(model.chunk_grid.configuration["chunk_shape"]) == chunks
            else:
                assert model.chunks == chunks
        array_refuses(array_document(version, chunks=(2,)),
                      ("chunks",) if version == 2 else ("chunk_grid", "configuration", "chunk_shape"))
        for shape in ([True, 8], [2.0, 8]):
            array_refuses(array_document(version, shape=shape), ("shape", 0), "invalid_type")
    array_accepts(array_document(shape=(0, 5), chunks=(0, 2)))
    array_refuses(array_document(chunks=(0, 2)), ("chunk_grid", "configuration", "chunk_shape", 0))
    array_refuses(array_document(chunks=(-1, 2)), ("chunk_grid", "configuration", "chunk_shape", 0))


def test_definition_scopes_and_normalization():
    # F01.T04: enumerate the promised catalogue, not private registry tables.
    examples = [(DataTypeDefinition, n, False) for n in (
        "bool", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
        "float16", "float32", "float64", "complex64", "complex128", "r24")]
    examples += [(DataTypeDefinition, "string", True), (DataTypeDefinition, "bytes", True)]
    examples += [(DataTypeDefinition, named(n, unit="ms", scale_factor=1), True)
                 for n in ("numpy.datetime64", "numpy.timedelta64")]
    examples += [(DataTypeDefinition, named("struct", fields=[{"name": "a", "data_type": "int8"}]), True),
        (ChunkGridDefinition, named("regular", chunk_shape=[3]), False),
        (ChunkGridDefinition, named("rectilinear", kind="inline", chunk_shapes=[3]), True),
        (ChunkKeyEncodingDefinition, "default", False), (ChunkKeyEncodingDefinition, "v2", False),
        (CodecDefinition, named("blosc", cname="lz4", clevel=1, shuffle="noshuffle", blocksize=0), False),
        (CodecDefinition, "bytes", False), (CodecDefinition, "crc32c", False),
        (CodecDefinition, named("gzip", level=2), False),
        (CodecDefinition, shard_document()["codecs"][0], False),
        (CodecDefinition, named("transpose", order=[1, 0]), False),
        (CodecDefinition, named("zstd", level=3), True),
        (CodecDefinition, named("scale_offset", scale=2), True),
        (CodecDefinition, named("cast_value", data_type="int16"), True)]
    for kind, field, extension in examples:
        resolved, problems = resolve(field, kind, CORE_AND_EXTENSIONS)
        assert problems == (), (field, problems)
        assert resolved.resolution == "read"
        simple, problems = canonicalize(field, kind, CORE_AND_EXTENSIONS)
        assert problems == () and simple is not None
        assert canonicalize(simple, kind, CORE_AND_EXTENSIONS) == (simple, ())
        reread, problems = resolve(simple, kind, CORE_AND_EXTENSIONS)
        assert problems == ()
        assert metadata_json(reread.configuration) == metadata_json(resolved.configuration)
        core_read, problems = resolve(field, kind, CORE)
        assert problems == ()
        assert core_read.resolution == ("out_of_scope" if extension else "read")
    for kind in (DataTypeDefinition, ChunkGridDefinition, ChunkKeyEncodingDefinition,
                 CodecDefinition, StorageTransformerDefinition):
        field = named("vendor.unclaimed", nested={"values": [1, 2]})
        resolved, problems = resolve(field, kind, CORE_AND_EXTENSIONS)
        assert (resolved.resolution, resolved.definition, problems) == ("out_of_scope", None, ())
        simple, problems = canonicalize(field, kind, CORE_AND_EXTENSIONS)
        assert problems == ()
        assert metadata_json(simple) == field
    assert not any(isinstance(d, StorageTransformerDefinition) for d in CORE_AND_EXTENSIONS.definitions())

    def spelled_out(entries):
        sizes = []
        for entry in entries:
            sizes += [entry] if isinstance(entry, int) else [entry[0]] * entry[1]
        return sizes
    for spec in ([1, [1, 2]], [[1, 3]], [4, 4, [2, 3], 2], [[2, 3], [2, 1], 3], [[4, 1], [4, 2]], [5, 3, 5]):
        field = named("rectilinear", kind="inline", chunk_shapes=[spec])
        simple, problems = canonicalize(field, ChunkGridDefinition, CORE_AND_EXTENSIONS)
        assert problems == ()
        assert spelled_out(metadata_json(simple)["configuration"]["chunk_shapes"][0]) == spelled_out(spec)
        assert canonicalize(simple, ChunkGridDefinition, CORE_AND_EXTENSIONS) == (simple, ())

    class First(TypedDict, closed=True):
        first: int

    class Last(TypedDict, closed=True):
        last: str

    for kind in (DataTypeDefinition, ChunkGridDefinition, ChunkKeyEncodingDefinition, StorageTransformerDefinition):
        first = kind(name="vendor.custom", configuration=First)
        last = kind(name="vendor.custom", configuration=Last)
        scope = Context.of(first).extended_with(last)
        got, problems = resolve(named("vendor.custom", last="ok"), kind, scope)
        assert problems == () and got.configuration == {"last": "ok"}
        _, problems = resolve(named("vendor.custom", first=1), kind, scope)
        assert (("configuration", "last"), "missing_key") in problem_pairs(problems)
    first = CodecDefinition(name="vendor.codec", configuration=First, kind="bytes_bytes", size="static")
    last = replace(first, configuration=Last)
    scope = CORE_AND_EXTENSIONS.extended_with(first, last)
    doc = array_document(codecs=["bytes", named("vendor.codec", last="ok")])
    assert array_accepts(doc, context=scope).codecs[1].configuration == {"last": "ok"}
    bad = array_document(codecs=["bytes", named("vendor.codec", first=1)])
    array_refuses(bad, ("codecs", 1, "configuration", "last"), "missing_key", context=scope)
    for field, loc, kind in ((named("gzip", level=12), ("configuration", "level"), "invalid_value"),
                              (named("bytes", unexpected=1), ("configuration", "unexpected"), "unknown_key")):
        simple, problems = canonicalize(field, CodecDefinition, CORE_AND_EXTENSIONS)
        assert simple is None
        assert (loc, kind) in problem_pairs(problems)


def test_contextual_codec_pipeline():
    # F01.T05
    transpose = named("transpose", order=[1, 0])
    little = named("bytes", endian="little")
    for codecs in (["bytes"], [transpose, "bytes", "crc32c"],
                   ["bytes", named("gzip", level=1)], ["vendor.codec"],
                   ["vendor.codec", named("transpose", order=[0, 1, 2]), "bytes"]):
        assert len(array_accepts(array_document(codecs=codecs)).codecs) == len(codecs)
    for codecs, loc in (([], ("codecs",)), ([transpose], ("codecs",)),
                        (["bytes", "bytes"], ("codecs", 1)),
                        (["bytes", transpose], ("codecs", 1)),
                        ([named("gzip", level=1)], ("codecs",)),
                        ([named("transpose", order=[0]), "bytes"], ("codecs", 0, "configuration", "order")),
                        ([named("transpose", order=[0, 0]), "bytes"], ("codecs", 0, "configuration", "order"))):
        array_refuses(array_document(codecs=codecs), loc)
    array_accepts(array_document(data_type="float32", fill_value=2.5, codecs=[little]))
    for dt, fill in (("bool", False), ("int8", 0), ("uint8", 0), ("r8", [0]),
                     (named("struct", fields=[{"name": "a", "data_type": "int8"}]), {"a": 0})):
        array_accepts(array_document(data_type=dt, fill_value=fill, codecs=["bytes"]))
    for dt, fill in (("uint16", 0), ("int32", 0), ("float64", 0.0), ("complex64", [0.0, 0.0]),
                     (named("numpy.datetime64", unit="s", scale_factor=1), 0),
                     (named("struct", fields=[{"name": "a", "data_type": "int16"}]), {"a": 0})):
        array_refuses(array_document(data_type=dt, fill_value=fill, codecs=["bytes"]),
                      ("codecs", 0, "configuration", "endian"), "missing_key")
    # A numeric conversion decides what the following serialization receives.
    array_accepts(array_document(data_type="int16", codecs=[named("cast_value", data_type="uint8"), "bytes"]))
    array_refuses(array_document(codecs=[named("cast_value", data_type="int16"), "bytes"]),
                  ("codecs", 1, "configuration", "endian"), "missing_key")
    array_refuses(array_document(data_type="int16", codecs=["bytes"]),
                  ("codecs", 0, "configuration", "endian"), "missing_key")
    for dt, fill in (("string", "text"), ("bytes", [1, 2])):
        array_refuses(array_document(data_type=dt, fill_value=fill, codecs=[little]),
                      ("codecs", 0, "configuration"))
        array_accepts(array_document(data_type=dt, fill_value=fill, codecs=["vendor.codec", little]))
    array_refuses(array_document(data_type="int8", fill_value=128), ("fill_value",))
    array_refuses(array_document(chunk_grid=named("regular", chunk_shape=[1])),
                  ("chunk_grid", "configuration", "chunk_shape"))


def test_indexed_sharding_constraints():
    # F01.T06
    for inner, codecs, index in (((2, 1), ["bytes"], [named("bytes", endian="little")]),
                                 ((4, 2), ["bytes", named("gzip", level=1)],
                                  [named("bytes", endian="big"), "crc32c"])):
        got = array_accepts(shard_document(inner, codecs, index))
        assert tuple(got.codecs[0].configuration["chunk_shape"]) == inner
    prefix = ("codecs", 0, "configuration")
    for inner, loc in (((2,), ("chunk_shape",)), ((0, 1), ("chunk_shape", 0)),
                       ((-1, 1), ("chunk_shape", 0)), ((3, 1), ("chunk_shape", 0))):
        array_refuses(shard_document(inner), prefix + loc)
    array_refuses(shard_document(codecs=["bytes", "bytes"]), prefix + ("codecs", 1))
    array_refuses(shard_document(codecs=[]), prefix + ("codecs",))
    array_refuses(shard_document(index_codecs=[named("bytes", endian="little"), named("gzip", level=1)]),
                  prefix + ("index_codecs", 1))
    array_refuses(shard_document(codecs=[named("gzip", level=12)]),
                  prefix + ("codecs", 0, "configuration", "level"))


def test_store_documents_and_export_independence():
    # F01.T07
    attrs = {"nested": {"label": "original", "values": [11, 22]}}
    for cls, key, doc in ((VelnoraV2ArrayMetadata, ".zarray", array_document(2)),
                          (VelnoraV2GroupMetadata, ".zgroup", {"zarr_format": 2}),
                          (VelnoraV3ArrayMetadata, "zarr.json", array_document()),
                          (VelnoraV3GroupMetadata, "zarr.json", {"zarr_format": 3, "node_type": "group"})):
        v2 = key != "zarr.json"
        stored = {key: json.dumps(doc if v2 else doc | {"attributes": attrs}).encode()}
        if v2:
            stored[".zattrs"] = json.dumps(attrs).encode()
        model = cls.from_key_value(stored)
        assert metadata_json(model.attributes) == attrs
        written = model.to_key_value()
        assert json.loads(written[".zattrs"] if v2 else written[key])["nested" if v2 else "attributes"] == (attrs["nested"] if v2 else attrs)
        exported = model.to_json()
        exported["attributes"]["nested"]["label"] = "edited"
        assert metadata_json(model.to_json())["attributes"] == attrs
        assert metadata_json(cls.from_key_value(written).attributes) == attrs
        refused(cls.from_key_value, {}, [((key,), "missing_key")])
        with pytest.raises(MetadataValidationError) as raised:
            cls.from_key_value({key: b'[1]'})
        assert "invalid_type" in {problem.kind for problem in raised.value.problems}
        for raw in (b'{', b'\xff'):
            refused(cls.from_key_value, {key: raw}, [((key,), "invalid_json")])
        if v2:
            absent = cls.from_key_value({key: stored[key]})
            empty = cls.from_key_value({key: stored[key], ".zattrs": b'{}'})
            assert absent.attributes is UNSET
            assert ".zattrs" not in absent.to_key_value()
            assert empty.attributes == {}
            assert json.loads(empty.to_key_value()[".zattrs"]) == {}
            refused(cls.from_key_value, {key: stored[key], ".zattrs": b'{'},
                    [((".zattrs",), "invalid_json")])
    merged = VelnoraV3ConsolidatedMetadata.from_json({"kind": "inline", "must_understand": False,
        "metadata": {"a": array_document(attributes=attrs)}})
    out = merged.to_json()
    out["metadata"]["a"]["attributes"]["nested"]["label"] = "edited"
    assert metadata_json(merged.to_json())["metadata"]["a"]["attributes"] == attrs


# Category labels the documents do not assign: any value or exchange category, never acceptance.
NONFINITE_KINDS = frozenset({"invalid_value", "invalid_type", "invalid_json"})
WRONG_LENGTH_KINDS = frozenset({"invalid_value", "invalid_type"})


def test_nonfinite_values_in_store_metadata():
    # F01.T08
    attrs = {"nan": math.nan, "range": [-math.inf, math.inf]}
    for cls, key, doc in ((VelnoraV2ArrayMetadata, ".zarray", array_document(2)),
                          (VelnoraV2GroupMetadata, ".zgroup", {"zarr_format": 2}),
                          (VelnoraV3ArrayMetadata, "zarr.json", array_document()),
                          (VelnoraV3GroupMetadata, "zarr.json", {"zarr_format": 3, "node_type": "group"})):
        stored = {key: json.dumps(doc).encode(), ".zattrs": json.dumps(attrs).encode()} if key != "zarr.json" else {key: json.dumps(doc | {"attributes": attrs}).encode()}
        model = cls.from_key_value(stored)
        for held in (model.attributes, cls.from_key_value(model.to_key_value()).attributes):
            assert math.isnan(held["nan"])
            assert tuple(held["range"]) == (-math.inf, math.inf)
    for value in (math.nan, math.inf, -math.inf):
        for version, cls, key in ((2, VelnoraV2ArrayMetadata, ".zarray"), (3, VelnoraV3ArrayMetadata, "zarr.json")):
            doc = array_document(version, fill_value=value)
            refused(cls.from_key_value, {key: json.dumps(doc).encode()}, [(("fill_value",), NONFINITE_KINDS)])
    for value in ("NaN", "Infinity", "-Infinity"):
        doc = array_document(data_type="float32", fill_value=value, codecs=[named("bytes", endian="little")])
        model = VelnoraV3ArrayMetadata.from_key_value({"zarr.json": json.dumps(doc).encode()})
        assert json.loads(model.to_key_value()["zarr.json"])["fill_value"] == value
    doc = array_document(codecs=[named("bytes", endian="little", scale=math.inf)])
    refused(VelnoraV3ArrayMetadata.from_key_value, {"zarr.json": json.dumps(doc).encode()},
            [(("codecs", 0, "configuration", "scale"), NONFINITE_KINDS | {"unknown_key"})])
    # An optional unknown member is otherwise accepted, so only its non-finite content refuses it.
    for value in (math.nan, math.inf, -math.inf):
        doc = array_document(vendor_extra={"must_understand": False, "payload": [value]})
        refused(VelnoraV3ArrayMetadata.from_key_value, {"zarr.json": json.dumps(doc).encode()}, [])


def test_caller_validation_model_integration():
    # F01.T09: schema is judged by behavior, not its internal $defs layout.
    from pydantic import BaseModel, ValidationError
    from jsonschema import Draft202012Validator
    import velnora_metadata.pydantic as velnora_mp

    class Manifest(BaseModel):
        metadata: velnora_mp.VelnoraV3ArrayMetadata

    doc = array_document(attributes={"run": 41})
    manifest = Manifest.model_validate({"metadata": doc})
    assert manifest.metadata.shape == (12, 8)
    assert manifest.metadata.attributes == {"run": 41}
    assert json.loads(manifest.model_dump_json())["metadata"]["shape"] == [12, 8]
    validator = Draft202012Validator(Manifest.model_json_schema())
    assert validator.is_valid({"metadata": doc})
    invalid = [doc | {"shape": [-1, 8]}, doc | {"shape": [True, 8]},
               doc | {"node_type": "group"}, doc | {"attributes": []}]
    missing = dict(doc)
    del missing["fill_value"]
    invalid.append(missing)
    for bad in invalid:
        with pytest.raises(ValidationError):
            Manifest.model_validate({"metadata": bad})
        assert not validator.is_valid({"metadata": bad})
    with pytest.raises(ValidationError):
        Manifest.model_validate({"metadata": doc | {"dimension_names": ["x"]}})
    exported = json.loads(manifest.model_dump_json())
    assert metadata_json(Manifest.model_validate(exported).metadata.to_json())["attributes"] == {"run": 41}


def test_compression_configuration_rules():
    # F01.T10: enumerate algorithms and shuffles independently.
    for name, lower, upper in (("gzip", 0, 9), ("zstd", -131072, 22)):
        for level in (lower, 1, upper):
            field = named(name, level=level)
            resolved, problems = resolve(field, CodecDefinition, CORE_AND_EXTENSIONS)
            assert problems == () and resolved.configuration["level"] == level
            array_accepts(array_document(codecs=["bytes", field]))
        for level, kind in ((lower - 1, "invalid_value"), (upper + 1, "invalid_value"),
                            (True, "invalid_type"), (1.5, "invalid_type")):
            array_refuses(array_document(codecs=["bytes", named(name, level=level)]),
                          ("codecs", 1, "configuration", "level"), kind)
        array_refuses(array_document(codecs=["bytes", named(name)]),
                      ("codecs", 1, "configuration", "level"), "missing_key")
    blosc = dict(cname="lz4", clevel=3, shuffle="noshuffle", blocksize=0)
    for cname in ("lz4", "lz4hc", "blosclz", "snappy", "zlib", "zstd"):
        array_accepts(array_document(codecs=["bytes", named("blosc", **(blosc | {"cname": cname}))]))
    for shuffle in ("noshuffle", "shuffle", "bitshuffle"):
        conf = blosc | {"shuffle": shuffle, "typesize": 2}
        array_accepts(array_document(codecs=["bytes", named("blosc", **conf)]))
    for field, value, kind in (("clevel", -1, "invalid_value"), ("clevel", 10, "invalid_value"),
        ("clevel", True, "invalid_type"), ("blocksize", -1, "invalid_value"),
        ("cname", "unsupported", "invalid_value"), ("shuffle", "unsupported", "invalid_value"),
        ("extra", 1, "unknown_key")):
        array_refuses(array_document(codecs=["bytes", named("blosc", **(blosc | {field: value}))]),
                      ("codecs", 1, "configuration", field), kind)
    for level in (0, 9):
        array_accepts(array_document(codecs=["bytes", named("blosc", **(blosc | {"clevel": level}))]))
    for field in blosc:
        conf = {k: v for k, v in blosc.items() if k != field}
        array_refuses(array_document(codecs=["bytes", named("blosc", **conf)]),
                      ("codecs", 1, "configuration", field), "missing_key")
    for shuffle in ("shuffle", "bitshuffle"):
        conf = blosc | {"shuffle": shuffle}
        array_refuses(array_document(codecs=["bytes", named("blosc", **conf)]),
                      ("codecs", 1, "configuration", "typesize"), "missing_key")
        array_refuses(array_document(codecs=["bytes", named("blosc", **(conf | {"typesize": 0}))]),
                      ("codecs", 1, "configuration", "typesize"))
    array_accepts(array_document(codecs=["bytes", named("blosc", **(blosc | {"typesize": 0}))]))


def test_data_type_fill_and_configuration_rules():
    # F01.T11
    for signed in (True, False):
        for bits in (8, 16, 32, 64):
            dt = ("int" if signed else "uint") + str(bits)
            lower, upper = (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1) if signed else (0, 2 ** bits - 1)
            for value in (lower, upper):
                assert array_accepts(fill_document(dt, value)).fill_value == value
            for value in (lower - 1, upper + 1):
                array_refuses(fill_document(dt, value), ("fill_value",))
    for dt, value in (("bool", True), ("string", "hello"), ("bytes", [0, 255]),
                      ("r24", [2, 3, 255]), ("complex64", [1e20, "NaN"]),
                      ("complex128", ["Infinity", -3.5])):
        assert metadata_json(array_accepts(fill_document(dt, value)).fill_value) == value
    for dt, value, kind, loc in (("bool", 1, "invalid_type", ()), ("string", 1, "invalid_type", ()),
        ("bytes", [256], "invalid_value", (0,)), ("bytes", [-1], "invalid_value", (0,)),
        ("r24", [1], WRONG_LENGTH_KINDS, ()), ("r0", [], "invalid_value", None),
        ("r12", [1], "invalid_value", None), ("complex64", [1], WRONG_LENGTH_KINDS, ()),
        ("complex64", [1, "wrong"], "invalid_value", (1,))):
        array_refuses(fill_document(dt, value), ("data_type",) if loc is None else ("fill_value",) + loc, kind)
    for dt in ("float16", "float32", "float64"):
        assert array_accepts(fill_document(dt, 1e200)).fill_value == 1e200
    units = ("Y", "M", "W", "D", "h", "m", "s", "ms", "us", "ns", "ps", "fs", "as", "generic")
    for name in ("numpy.datetime64", "numpy.timedelta64"):
        for unit in units:
            array_accepts(fill_document(named(name, unit=unit, scale_factor=1), "NaT"))
        for scale in (1, 2147483647):
            for value in (-(2**63), 2**63 - 1):
                array_accepts(fill_document(named(name, unit="ns", scale_factor=scale), value))
        for scale in (0, 2147483648):
            array_refuses(fill_document(named(name, unit="s", scale_factor=scale), 0),
                          ("data_type", "configuration", "scale_factor"))
        for value in (-(2**63) - 1, 2**63):
            array_refuses(fill_document(named(name, unit="s", scale_factor=1), value), ("fill_value",))
    fields = [{"name": "left", "data_type": "int8"}, {"name": "right", "data_type": "float32"}]
    dt = named("struct", fields=fields)
    array_accepts(fill_document(dt, {"left": -8, "right": 1.5}))
    for fill, loc, kind in (({"left": 1}, ("right",), "missing_key"),
        ({"left": 1, "right": 2, "other": 0}, ("other",), "unknown_key"),
        ({"left": 128, "right": 2}, ("left",), "invalid_value")):
        array_refuses(fill_document(dt, fill), ("fill_value",) + loc, kind)
    for fields, loc in (([], ("fields",)), ([{"name": "", "data_type": "int8"}], ("fields", 0, "name")),
        ([{"name": "a", "data_type": "int8"}, {"name": "a", "data_type": "uint8"}], ("fields", 1, "name")),
        ([{"name": "a", "data_type": "string"}], ("fields", 0, "data_type")),
        ([{"name": "a", "data_type": named("struct", fields=[{"name": "b", "data_type": "bytes"}])}],
         ("fields", 0, "data_type", "configuration", "fields", 0, "data_type"))):
        array_refuses(fill_document(named("struct", fields=fields), {}), ("data_type", "configuration") + loc)


def test_rectilinear_grid_coverage():
    # F01.T12
    for shape, specs in (((10,), [4]), ((10,), [[4, 4, 2]]), ((10,), [[[4, 2], 2]]),
                          ((10,), [[4, 4, 9]]), ((0,), [[]]), ((7, 6), [2, [3, 3]])):
        doc = array_document(shape=shape, chunk_grid=named("rectilinear", kind="inline", chunk_shapes=specs))
        got = array_accepts(doc)
        assert metadata_json(got.chunk_grid.configuration)["chunk_shapes"] == specs
    for shape, specs, loc in (((10,), [[4, 4]], (0,)), ((10,), [[]], (0,)),
        ((3, 2), [2], ()), ((10,), [0], (0,)), ((10,), [[4, 0]], (0, 1)),
        ((10,), [[[4, 0]]], (0, 0, 1)), ((10,), [[[-1, 4]]], (0, 0, 0))):
        array_refuses(array_document(shape=shape, chunk_grid=named("rectilinear", kind="inline", chunk_shapes=specs)),
                      ("chunk_grid", "configuration", "chunk_shapes") + loc)


def test_unknown_fields_and_understanding_obligations():
    # F01.T13
    unknown = {"optional": {"must_understand": False, "payload": [1, 2]},
               "implicit": {"payload": "required"}, "explicit": {"must_understand": True},
               "scalar": 42}
    m2 = VelnoraV2ArrayMetadata.from_json(array_document(2) | unknown)
    assert not (set(unknown) & set(m2.to_json()))
    refused(VelnoraV2GroupMetadata.from_json, {"zarr_format": 2, "vendor": 1},
            [(("vendor",), "invalid_value")])
    for cls, doc in ((VelnoraV3ArrayMetadata, array_document()),
                     (VelnoraV3GroupMetadata, {"zarr_format": 3, "node_type": "group"})):
        model = cls.from_json(doc | unknown)
        assert metadata_json(model.extra_fields) == unknown
        required = {k: v for k, v in unknown.items() if k != "optional"}
        assert metadata_json(model.must_understand_fields) == required
        for out in (model.to_json(), cls.from_key_value(model.to_key_value()).to_json()):
            assert {k: metadata_json(out[k]) for k in unknown} == unknown
        updated = model.update(attributes={"new": 3})
        assert metadata_json(updated.extra_fields) == unknown
        assert updated.attributes == {"new": 3}
        with pytest.raises(ValueError):
            model.update(extra_fields={"zarr_format": 5})


def test_extension_understanding_declarations():
    # F01.T14: each interpretation category, including unclaimed names.
    for field in ("data_type", "chunk_grid", "chunk_key_encoding", "codecs", "storage_transformers"):
        declaration = {"name": "vendor.interpretation", "must_understand": True}
        doc = array_document()
        doc[field] = [declaration] if field in ("codecs", "storage_transformers") else declaration
        array_accepts(doc)
        optional = declaration | {"must_understand": False}
        doc[field] = [optional] if isinstance(doc[field], list) else optional
        loc = (field, 0, "must_understand") if isinstance(doc[field], list) else (field, "must_understand")
        array_refuses(doc, loc)
    merged = {"kind": "inline", "must_understand": False, "metadata": {}}
    assert VelnoraV3ConsolidatedMetadata.from_json(merged).must_understand is False
    refused(VelnoraV3ConsolidatedMetadata.from_json, merged | {"must_understand": True},
            [(("must_understand",), "invalid_value")])
