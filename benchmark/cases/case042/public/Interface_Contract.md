# Interface Contract

Python imports use `velnora`, `velnora_metadata`, `velnora_indexing`, and `velnora_http_server`.

The installed Python distribution `velnora` declares a `console_scripts` entry named `velnora`.

The independently installable coordinate package is at `packages/velnora-indexing` relative to the project root. It accepts the build environment variable `SETUPTOOLS_SCM_PRETEND_VERSION`.

Store keys and node paths are strings. Hierarchical relative paths use `/`. Metadata documents are JSON; stored JSON is carried as bytes.

## `velnora`

The package exposes `Array`, `Group`, `config`, `create_array`, `create`, `zeros`, `ones`, `full`, `open`, `open_array`, `open_group`, `create_group`, `create_hierarchy`, `consolidate_metadata`, `from_array`, `save`, `save_array`, and `save_group`. `load` returns native array data. `dtype`, `codecs`, `storage`, and `buffer` are importable submodules.

## `velnora.create_array`

`create_array(store, *, name, shape, dtype, data, chunks, shards, filters, compressors, serializer, fill_value, order, zarr_format, attributes, chunk_key_encoding, dimension_names, overwrite, config)` returns an `Array`. Parameters shown after `*` are supplied by keyword; callers may omit optional parameters. `store` also accepts keyword passing and may be a store handle, a mutable mapping, or a filesystem path.

`name` is a relative node path; `shape` is a tuple of integer lengths; `dtype` is a native dtype, dtype spelling, or Velnora dtype object; `data` is native array data. `chunks` accepts a regular shape, per-axis size sequences, or `auto`; a per-axis `-1` spells the full-span choice. `shards` accepts a shape, per-axis size sequences, `None`, or a mapping with `shape` and `index_location`. `filters` and `compressors` accept codec objects, sequences, named-configuration mappings, `auto`, or `None`; `serializer` accepts a codec, named configuration, `auto`, or `None`. `attributes` is a string-keyed JSON mapping. `dimension_names` is a sequence of strings or `None` entries. `chunk_key_encoding` accepts a mapping with `name` and `separator`. `config` is a mapping with `order`, `write_empty_chunks`, and `read_missing_chunks`.

Definition rejection is signalled by `ValueError`; incompatible chunk-length types raise `TypeError` or `ValueError`; incompatible fill conversion raises `TypeError` or `ValueError`; incompatible encoding inputs may raise `TypeError` or `ValueError`. An existing-array conflict raises `ContainsArrayError`. Invalid per-array configuration raises `TypeError`.

## `velnora.create`

`create(shape, *, store, chunks, dtype, zarr_format)` returns an `Array`. `shape` may be supplied by keyword; `dtype`, `chunks`, and `zarr_format` may be omitted. `chunks` accepts a shape or `False`.

## `velnora.zeros`

`zeros(shape, **kwargs)` returns an `Array`. `store`, `dtype`, and `zarr_format` are accepted keyword arguments; `shape` is a tuple of integers.

## `velnora.ones`

`ones(shape, **kwargs)` returns an `Array`. `store`, `dtype`, and `zarr_format` are accepted keyword arguments; `shape` is a tuple of integers.

## `velnora.full`

`full(shape, fill_value, **kwargs)` returns an `Array`. `store`, `dtype`, and `zarr_format` are accepted keyword arguments; `shape` is a tuple of integers.

## `velnora.open`

`open(store, *, mode, zarr_format, shape, dtype)` returns an `Array` or `Group`. Optional keywords may be omitted. `mode` is an access-mode string and `zarr_format` is an integer or `None`.

Missing targets raise `FileNotFoundError`; exclusive-creation conflicts raise `FileExistsError`.

Access-mode spellings are `r`, `r+`, `a`, `w-`, and `w`. These spellings also apply to array and group opening.

## `velnora.open_array`

`open_array(store, *, mode, path, zarr_format, shape, dtype)` returns an `Array`. Optional keywords may be omitted. `path` is a relative node path.

Missing array lookup raises `ArrayNotFoundError`, a `FileNotFoundError` subtype. `ArrayNotFoundError` also carries format-2 wrong-kind lookup; `NodeTypeValidationError` carries format-3 wrong-kind lookup. Exclusive-creation refusal raises `FileExistsError`. Invalid stored JSON raises `json.JSONDecodeError`. Disabled rectilinear access raises `RectilinearChunksDisabledError`.

Malformed stored array definitions raise `ValueError`.

## `velnora.Array`

`Array` exposes `shape: tuple[int, ...]`, `ndim: int`, `dtype: numpy.dtype`, `chunks: tuple[int, ...]`, `shards: tuple[int, ...] | None`, `read_chunk_sizes: tuple[tuple[int, ...], ...]`, `order: str`, `fill_value`, `read_only: bool`, `path: str`, `store`, `store_path.path: str`, `attrs`, and `metadata`.

`metadata` exposes `zarr_format: int`, `fill_value`, `dimension_names: tuple[str | None, ...] | None`, `data_type`, `codecs`, and `compressor`. `data_type.to_json(zarr_format=...)` returns its type document. `codecs` is a tuple of codec objects; `compressor` is a format-2 codec or `None`.

`filters` and `compressors` are tuples of codecs; `serializer` is a codec or `None`. Format-3 codec descriptions come from `to_dict()` as `{'name': <str>, 'configuration': <mapping>}`. Format-2 descriptions come from `get_config()` with `id` and codec configuration fields.

`nbytes`, `nchunks`, and `nchunks_initialized` are integers reporting logical bytes, possible storage chunks, and initialized storage chunks. `nbytes_stored()` returns the stored byte count as an integer.

`array[selection]` and `numpy.asarray(array)` return native array values, including scalar selections. Assignment is `array[selection] = value`, also exposed as `__setitem__(selection, value)`. Native record results provide field-name indexing; temporal scalar results expose `dtype` with their unit and scale. `oindex`, `vindex`, and `blocks` expose bracket reads and writes.

`get_basic_selection(selection, *, out, prototype)`, `get_orthogonal_selection(selection, *, out)`, `get_coordinate_selection(selection, *, out)`, `get_mask_selection(mask, *, out)`, and `get_block_selection(selection, *, out)` return selected native values. Optional output arguments may be omitted. `out` is an `NDBuffer` wrapping the destination; `prototype` is a buffer prototype. Native results expose `shape`, `dtype`, and element indexing.

Native array results expose `flags.c_contiguous: bool` and `flags.f_contiguous: bool`, indicating contiguous row-major and column-major storage, respectively. Memory-order spellings for `order` are `C` and `F`.

`set_basic_selection(selection, value)`, `set_orthogonal_selection(selection, value)`, `set_coordinate_selection(selection, value)`, `set_mask_selection(mask, value)`, and `set_block_selection(selection, value)` are synchronous assignment entries. `IndexError` is the invalid-index or selector-structure carrier. `ValueError` is the zero-step or shape-incompatibility carrier, including incompatible coordinate broadcasting, assigned shapes, and output shapes. A missing-data refusal raises `ChunkNotFoundError`. A corrupt shard-index refusal raises `ValueError`.

`with_config(config)` returns an array view and accepts `order`, `write_empty_chunks`, and `read_missing_chunks`. Invalid configuration raises `TypeError`. `resize(new_shape)` accepts a tuple and completes synchronously. `append(data, axis=...)` returns the new shape tuple; `axis` may be omitted. Invalid resize or append raises `ValueError`. Read-only mutation raises `ValueError`; unsupported deletion raises `NotImplementedError`. Asking for a uniform shape on a variable grid raises `NotImplementedError`.

## `velnora.api`

`from velnora.api import asynchronous` exposes the asynchronous array API.

## `velnora.api.asynchronous`

`create_array(store, *, shape, dtype, data, chunks, fill_value, zarr_format, dimension_names)` and `open_array(*, store, mode, zarr_format)` are awaitable calls returning `AsyncArray`. Optional definition parameters may be omitted. Array creation accepts the same definition types as the synchronous array API.

The returned object exposes `shape`, `ndim`, `dtype`, `chunks`, `shards`, `metadata`, `filters`, `serializer`, `compressors`, and `store`. `getitem(selection)` is awaitable and returns native array values. `resize(new_shape, delete_outside_chunks=...)` is awaitable; the boolean keyword may be omitted. Definition and resize refusal raises `ValueError`.

## `velnora.Group`

`Group` exposes `metadata.zarr_format: int`, `attrs`, `store`, `store_path.path: str`, and `name: str`.

`group[path]`, also exposed as `__getitem__(path)`, returns an `Array` or `Group`; `get_array(path)` returns an `Array`; `get_group(path)` returns a `Group`. The generic missing-member failure is `KeyError`; typed lookup failures are `ArrayNotFoundError` and `GroupNotFoundError`. Wrong-kind typed lookups use `ContainsGroupError` and `ContainsArrayError`.

`path in group` returns a boolean. Iteration yields relative-name strings and `len(group)` returns an integer. `members(max_depth=...)` returns a finite iterable of `(relative_name, node)` pairs; `nmembers(max_depth=...)` returns an integer. The depth argument may be omitted or be an integer or `None`. `arrays()` yields `(name, Array)` pairs. Invalid depth raises `ValueError`.

`create_group(name, *, attributes)` returns a `Group`. `create_array(name, *, data, shape, dtype, chunks, shards, filters, serializer, compressors, fill_value, attributes, dimension_names, order, chunk_key_encoding)` returns an `Array`; optional keywords may be omitted. These definition arguments have the array-creation types.

`require_group(name)` returns a `Group`. `require_array(name, *, shape, dtype, exact, fill_value, attributes)` returns an `Array`; `exact`, `fill_value`, and `attributes` may be omitted. Incompatible-existing-content refusal raises `TypeError`.

`del group[path]` is synchronous. Read-only deletion raises `ValueError`; unsupported deletion raises `NotImplementedError`.

`tree(level=..., plain=True)` returns an object whose `repr()` is text. The first line is the group's `name`. Each subsequent node row has zero or more four-character ancestor cells (`│   ` or four spaces), a `├── ` or `└── ` connector, and the node's name. An array row appends a space, a Python tuple shape, another space, and a NumPy dtype spelling; a group row has no annotation. Invalid level raises `ValueError`.

## `velnora.create_group`

`create_group(store, *, zarr_format, attributes)` returns a `Group`. Optional keywords may be omitted. `store` is a store handle, mapping, or filesystem path; `attributes` is a string-keyed JSON mapping.

## `velnora.open_group`

`open_group(store, *, mode, path, zarr_format, use_consolidated)` returns a `Group`. Optional keywords may be omitted. `path` is a relative string; `mode` is an access-mode string; `use_consolidated` is a boolean. Required-consolidation and hierarchy-conflict refusals raise `ValueError`. Missing targets raise `FileNotFoundError`; exclusive-creation conflicts raise `FileExistsError`.

## `velnora.create_hierarchy`

`create_hierarchy(*, store, nodes, overwrite)` returns a finite iterable of `(relative_path, Group | Array)` pairs. `overwrite` may be omitted. `nodes` maps paths to array metadata or `GroupMetadata` objects. Existing-content refusal raises `ContainsArrayError` or `ContainsGroupError`; an invalid hierarchy raises `ValueError`.

## `velnora.core.group.GroupMetadata`

`GroupMetadata(zarr_format=..., attributes=...)` is a group description accepted in the `nodes` mapping of `create_hierarchy`. `attributes` may be omitted.

## `velnora.core.attributes.Attributes`

The `attrs` property of arrays and groups is a string-keyed mutable mapping of JSON-compatible values. It supports `attrs[key]`, assignment, deletion, key iteration, membership, and `dict(attrs)`. `asdict()` returns the attribute dictionary.

`update(mapping)` accepts several entries. `put(mapping)` accepts a replacement dictionary. Missing lookup or deletion raises `KeyError`; serialization refusal raises `TypeError`; read-only modification raises `ValueError`.

## `velnora.consolidate_metadata`

`consolidate_metadata(store, zarr_format=...)` returns a `Group`; `zarr_format` may be omitted. A store-capability refusal raises `TypeError`.

## `velnora.from_array`

`from_array(store, *, data, name, write_data, overwrite, chunks, shards, filters, serializer, compressors, fill_value, zarr_format, attributes, dimension_names)` returns an `Array`. `data` is native array-like data or an existing `Array`. Other keywords may be omitted; representation arguments use the array-creation types. Existing-array refusal raises `ContainsArrayError`; overlap refusal raises `ValueError`.

## `velnora.save`

`save(store, *args, path=..., zarr_format=..., **kwargs)` accepts positional native arrays and keyword-named native arrays. Optional location and format keywords may be omitted. Missing-input refusal raises `ValueError`. An existing-array refusal raises `ContainsArrayError`.

## `velnora.save_array`

`save_array(store, arr, *, zarr_format, overwrite)` accepts native array data; keywords may be omitted. Missing the array argument raises `TypeError`; an existing-array refusal raises `ContainsArrayError`.

## `velnora.save_group`

`save_group(store, *args, path=..., zarr_format=..., **kwargs)` accepts positional native arrays and keyword-named native arrays. Optional location and format keywords may be omitted. Missing-input refusal raises `ValueError`.

## `velnora.load`

`load(store, path=...)` returns a native ndarray for an array location. `path` may be omitted. The result exposes `shape`, `dtype`, and element indexing.

## `velnora.abc.store`

The module exports `Store`, `RangeByteRequest`, `OffsetByteRequest`, and `SuffixByteRequest`.

## `velnora.abc.store.Store`

`Store` is a subclassable storage protocol with `__init__(*, read_only=...)`. Capability attributes are `supports_writes`, `supports_deletes`, `supports_listing`, and `supports_consolidated_metadata`, each boolean. Subclasses supply equality and `close()`.

`get(key, prototype, byte_range=...)` is awaitable and returns a `Buffer` or `None` for absence. Concrete built-in stores also accept an omitted `prototype`. `key` is a string, `prototype` supplies the buffer class, and `byte_range` is a byte request or `None`. `get_partial_values(prototype, key_ranges)` is awaitable and returns a list whose entries are `Buffer` or `None`, with `None` carrying absence; `key_ranges` contains `(key, byte_request)` pairs.

`set(key, value)` and `delete(key)` are awaitable; `value` is a `Buffer`. `delete_dir(prefix)` is awaitable. `exists(key)` returns an awaitable boolean; `getsize(key)` returns an awaitable integer byte count.

`list()`, `list_prefix(prefix)`, and `list_dir(prefix)` return finite asynchronous iterables of string keys or immediate child names. `with_read_only(read_only)` returns a store view; the argument and the view's `read_only` attribute are booleans. `close()` is synchronous. Read-only refusal raises `ValueError`; unsupported deletion raises `NotImplementedError`.

Remote connection and authentication failures are reported by raising an exception; no specific backend exception subclass is prescribed.

## `velnora.abc.store.RangeByteRequest`

`RangeByteRequest(start, end)` is a byte-request object accepted by store reads. `start` and `end` are integer attributes.

## `velnora.abc.store.OffsetByteRequest`

`OffsetByteRequest(offset)` is a byte-request object accepted by store reads. `offset` is an integer attribute.

## `velnora.abc.store.SuffixByteRequest`

`SuffixByteRequest(suffix)` is a byte-request object accepted by store reads. `suffix` is an integer attribute.

## `velnora.storage`

The module exports `MemoryStore`, `LocalStore`, `ZipStore`, `FsspecStore`, and `ObjectStore`.

## `velnora.storage.MemoryStore`

`MemoryStore()` returns a store handle implementing `Store`, including `get`, `set`, `delete`, `exists`, `getsize`, `list`, `list_prefix`, `list_dir`, `with_read_only`, and `close`.

## `velnora.storage.LocalStore`

`LocalStore(root, *, read_only=...)` accepts a string or path-like directory and returns a `Store`. The keyword may be omitted. Public keys address files under that directory using `/` as the path separator.

## `velnora.storage.ZipStore`

`ZipStore(path, *, mode=...)` and awaitable `ZipStore.open(path, mode=...)` accept a filesystem path or an open binary file and return a store handle. `mode` is the archive access-mode string. The handle exposes `read_only: bool`; read-only mutation raises `ValueError`. The handle supports synchronous context management and `close()`.

A public store key is the Zip archive member name. `supports_deletes` is a boolean capability. Unsupported deletion raises `NotImplementedError`.

## `velnora.storage.FsspecStore`

`FsspecStore.from_url(url, storage_options=..., read_only=...)` returns a `Store` handle. `url` is a string and `storage_options` is a provider-options mapping; the HTTP provider accepts `skip_instance_cache: bool` and `headers: dict[str, str]`.

S3 locations use `s3://<bucket>/<prefix>`. S3 provider options include `endpoint_url`, `key`, and `secret` strings, `anon` and `skip_instance_cache` booleans, `client_kwargs` with a `region_name` string, and `config_kwargs` with numeric `connect_timeout` and `read_timeout` plus a `retries` mapping containing integer `max_attempts`.

## `velnora.storage.ObjectStore`

`ObjectStore(store, *, read_only=...)` accepts an object-store provider handle and returns a `Store`.

## `velnora.experimental.cache_store`

The module exposes `CacheStore`.

## `velnora.experimental.cache_store.CacheStore`

`CacheStore(store, *, cache_store, max_age_seconds, max_size, cache_set_data)` accepts source and reuse store handles. The three policy keywords may be omitted. `max_age_seconds` accepts an elapsed-second count; `max_size` accepts a byte count or `None`; `cache_set_data` is boolean. `max_size` is also an assignable public attribute.

It presents awaitable `get(key, prototype, byte_range=...)`, `set(key, buffer)`, `delete(key)`, and `clear_cache()`. Reads return `Buffer | None`; clearing completes without a result. `with_read_only(True)` returns a store view; `close()` is synchronous. Incompatible reuse storage and read-only mutation raise `ValueError`.

## `velnora.buffer`

The module exposes the provider module `cpu`.

## `velnora.buffer.cpu.Buffer`

`Buffer.from_bytes(data)` accepts bytes and returns a buffer. `to_bytes()` returns bytes. CPU buffer implementations are available as `velnora.buffer.cpu.Buffer`.

## `velnora.buffer.cpu.NDBuffer`

`cpu.NDBuffer.from_numpy_array(array_like)` returns a multidimensional buffer wrapping native array storage for use as `out`. The CPU implementation is `velnora.buffer.cpu.NDBuffer` and accepts native ndarray storage in its constructor.

A selected CPU subclass can implement `create(*, shape, dtype, order, fill_value)` and `empty(shape, dtype, order)`. `shape` is an integer tuple, `dtype` is NumPy-compatible, `order` is a memory-order string, and `fill_value` is a scalar or `None`. Each constructor returns an instance of that subclass.

## `velnora.core.buffer`

The module exports `default_buffer_prototype`.

## `velnora.core.buffer.default_buffer_prototype`

`default_buffer_prototype()` returns a prototype with `buffer` and `nd_buffer` provider classes. `buffer.from_bytes(data)` constructs a byte buffer.

## `velnora.buffer.cpu`

The CPU provider exports subclassable `Buffer`, subclassable `NDBuffer`, and `buffer_prototype`.

## `velnora.core.sync.sync`

`sync(coro)` accepts an awaitable and returns its completed value. Exceptions from the operation propagate.

## `velnora.config`

`velnora.config.get(key)` returns the Python value addressed by a string key. `set(mapping)` accepts dotted-key overrides and returns an object usable as a context manager; calls also support use without a `with` statement. `reset()` reloads configuration.

Global keys used by array access are `default_zarr_format`, `array.order`, `array.rectilinear_chunks`, `array.write_empty_chunks`, and `array.read_missing_chunks`. Provider-selection keys use the prefix `codecs.` followed by the encoding name, or `buffer` and `ndbuffer`; provider values are fully qualified class-name strings.

`VELNORA_CONFIG` names a YAML configuration file; `VELNORA_ROOT_CONFIG` names a configuration directory. `VELNORA_DEFAULT_ZARR_FORMAT` carries the format setting as text. YAML configuration is a mapping with `default_zarr_format` and a nested `array` mapping containing `order`.

## `velnora.registry`

The module exports `register_codec`, `register_buffer`, `register_ndbuffer`, and `fully_qualified_name`.

## `velnora.registry.register_codec`

`register_codec(key, codec_cls)` accepts an encoding-name string and codec class. A registered class can supply `from_dict(data)` and `to_dict()` with the named-configuration envelope `{'name': <str>, 'configuration': <mapping>}`.

## `velnora.registry.register_buffer`

`register_buffer(cls)` accepts a provider class.

## `velnora.registry.register_ndbuffer`

`register_ndbuffer(cls)` accepts a provider class.

## `velnora.registry.fully_qualified_name`

`fully_qualified_name(cls)` returns the fully qualified class-name string used in provider configuration.

## `velnora.core.config.BadConfigError`

`BadConfigError` is the exception carrier for unavailable configured providers.

## `velnora.errors`

The module exports `ArrayNotFoundError`, `GroupNotFoundError`, `ContainsArrayError`, `ContainsGroupError`, `NodeTypeValidationError`, `ChunkNotFoundError`, `UnknownCodecError`, and `VelnoraUserWarning`.

## `velnora.errors.ArrayNotFoundError`

`ArrayNotFoundError` is the public exception class for missing-array lookup. It is a `FileNotFoundError` subtype.

## `velnora.errors.GroupNotFoundError`

`GroupNotFoundError` is the public exception class for missing-group lookup.

## `velnora.errors.ContainsArrayError`

`ContainsArrayError` is the public exception class for an existing-array conflict.

## `velnora.errors.ContainsGroupError`

`ContainsGroupError` is the public exception class for an existing-group conflict.

## `velnora.errors.NodeTypeValidationError`

`NodeTypeValidationError` is the public exception class for node-kind mismatch.

## `velnora.errors.ChunkNotFoundError`

`ChunkNotFoundError` is the public exception class for missing stored data.

## `velnora.errors.UnknownCodecError`

`UnknownCodecError` is the public exception class for unresolved encoding. Its human-readable message carries the unresolved encoding name.

## `velnora.core.metadata.v3.RectilinearChunksDisabledError`

`RectilinearChunksDisabledError` is the exception class signalling disabled rectilinear access.

## `velnora_metadata`

The package exports the attribute-document annotation `VelnoraV2ZAttrsJSON`. Its public submodules include `model`, `typed_json`, `pydantic`, and `v3.definition`.

## `velnora_metadata.VelnoraV2ZAttrsJSON`

`VelnoraV2ZAttrsJSON` is an annotation for a string-keyed mapping of JSON attribute values. It can be used as a member type in a caller's `TypedDict` passed to `check`.

## `velnora_metadata.model`

The module exports `VelnoraV2ArrayMetadata`, `VelnoraV3ArrayMetadata`, `VelnoraV2GroupMetadata`, `VelnoraV3GroupMetadata`, `VelnoraV2ConsolidatedMetadata`, `VelnoraV3ConsolidatedMetadata`, `MetadataValidationError`, `UNSET`, `validate_array_metadata_v2`, `validate_array_metadata_v3`, `validate_group_metadata_v2`, and `validate_group_metadata_v3`.

## `velnora_metadata.model.VelnoraV2ArrayMetadata`

`VelnoraV2ArrayMetadata.from_json(data)` returns a metadata model. `data` is a JSON-compatible mapping. `from_key_value(mapping)` accepts a string-keyed mapping of metadata bytes and returns the model. Optional context may be omitted. `to_json()` returns a JSON-compatible document; `to_key_value()` returns a mapping of metadata keys to JSON bytes.

The document fields are `zarr_format`, `shape`, `chunks`, `dtype`, `fill_value`, `order`, `filters`, `compressor`, and `attributes`. The model's `shape` is a tuple of integers. `attributes` is a string-keyed JSON mapping or the `UNSET` sentinel when the attribute document is absent. `chunks` is a tuple of integers.

Parsing refusal raises `MetadataValidationError` with a `problems` tuple.

## `velnora_metadata.model.VelnoraV3ArrayMetadata`

`VelnoraV3ArrayMetadata.from_json(data, context=...)` returns a metadata model. `data` is a JSON-compatible mapping. `from_key_value(mapping, context=...)` accepts a string-keyed mapping of metadata bytes and returns the model. Optional context may be omitted. `to_json()` returns a JSON-compatible document; `to_key_value()` returns a mapping of metadata keys to JSON bytes.

The document fields are `zarr_format`, `node_type`, `shape`, `data_type`, `fill_value`, `chunk_grid`, `chunk_key_encoding`, `codecs`, `attributes`, `dimension_names`, and `storage_transformers`. The model's `shape` is a tuple of integers. `attributes` is a string-keyed JSON mapping. `data_type`, `chunk_grid`, `chunk_key_encoding`, and members of `codecs` and `storage_transformers` expose `name: str` and `configuration: mapping`. Named declarations in JSON are a name string or a mapping with `name`, `configuration`, and `must_understand`. `dimension_names` is a tuple of strings or `None` entries when supplied. Nested configuration fields include `chunk_shape`, `chunk_shapes`, `kind`, `separator`, `endian`, `order`, `codecs`, `index_codecs`, `level`, `cname`, `clevel`, `shuffle`, `blocksize`, `typesize`, `unit`, `scale_factor`, `fields`, `data_type`, `offset`, and `scale`. Record field entries have `name` and `data_type`.

`extra_fields` and `must_understand_fields` are mappings from extension member names to their JSON values. `update(attributes=..., extra_fields=...)` returns a metadata model; supplied keywords may be omitted. Conflicting extra members raise `ValueError`.

Parsing refusal raises `MetadataValidationError` with a `problems` tuple.

## `velnora_metadata.model.VelnoraV2GroupMetadata`

`VelnoraV2GroupMetadata.from_json(data)` returns a metadata model. `data` is a JSON-compatible mapping. `from_key_value(mapping)` accepts a string-keyed mapping of metadata bytes and returns the model. Optional context may be omitted. `to_json()` returns a JSON-compatible document; `to_key_value()` returns a mapping of metadata keys to JSON bytes.

The document fields are `zarr_format` and `attributes`. `attributes` is a string-keyed JSON mapping or the `UNSET` sentinel when the attribute document is absent.

Parsing refusal raises `MetadataValidationError` with a `problems` tuple.

## `velnora_metadata.model.VelnoraV3GroupMetadata`

`VelnoraV3GroupMetadata.from_json(data, context=...)` returns a metadata model. `data` is a JSON-compatible mapping. `from_key_value(mapping, context=...)` accepts a string-keyed mapping of metadata bytes and returns the model. Optional context may be omitted. `to_json()` returns a JSON-compatible document; `to_key_value()` returns a mapping of metadata keys to JSON bytes.

The document fields are `zarr_format`, `node_type`, `attributes`, and `consolidated_metadata`. `attributes` is a string-keyed JSON mapping. `consolidated_metadata` is a consolidated metadata model whose `metadata` mapping has relative paths as keys and node models as values.

`extra_fields` and `must_understand_fields` are mappings from extension member names to their JSON values. `update(attributes=..., extra_fields=...)` returns a metadata model; supplied keywords may be omitted. Conflicting extra members raise `ValueError`.

Parsing refusal raises `MetadataValidationError` with a `problems` tuple.

## `velnora_metadata.model.VelnoraV2ConsolidatedMetadata`

`VelnoraV2ConsolidatedMetadata.from_json(data)` returns a consolidated model; `to_json()` returns `{'zarr_consolidated_format': <int>, 'metadata': {<str>: <JSON document>}}`. `from_key_value(mapping)` and `to_key_value()` exchange JSON bytes under `.zmetadata`. Metadata mapping keys are relative metadata document paths. Parsing refusal raises `MetadataValidationError`.

## `velnora_metadata.model.VelnoraV3ConsolidatedMetadata`

`VelnoraV3ConsolidatedMetadata.from_json(data)` returns a consolidated model. `to_json()` returns `{'kind': <str>, 'must_understand': <bool>, 'metadata': {<relative node path>: <node document>}}`. The `metadata` attribute maps paths to node metadata models and `must_understand` is a boolean. Parsing refusal raises `MetadataValidationError`.

The inline document tag is `kind: "inline"`.

## `velnora_metadata.model.MetadataValidationError`

`MetadataValidationError.problems` is a tuple of validation problems. Each problem exposes `loc: tuple[str | int, ...]`, the path to the offending document position, and `kind: str`, a machine-readable category. Category labels are `missing_key`, `unknown_key`, `invalid_type`, `invalid_value`, and `invalid_json`.

## `velnora_metadata.model.UNSET`

`UNSET` is an identity-comparable sentinel available from `velnora_metadata.model` for an absent attribute collection.

## `velnora_metadata.model.validate_array_metadata_v2`

`validate_array_metadata_v2(data)` returns a tuple of validation problems. `data` is a JSON-compatible document. Problems expose `loc` and `kind`.

## `velnora_metadata.model.validate_array_metadata_v3`

`validate_array_metadata_v3(data, context=...)` returns a tuple of validation problems. `data` is a JSON-compatible document and the optional `context` is a definition collection. Problems expose `loc` and `kind`.

## `velnora_metadata.model.validate_group_metadata_v2`

`validate_group_metadata_v2(data)` returns a tuple of validation problems. `data` is a JSON-compatible document. Problems expose `loc` and `kind`.

## `velnora_metadata.model.validate_group_metadata_v3`

`validate_group_metadata_v3(data, context=...)` returns a tuple of validation problems. `data` is a JSON-compatible document and the optional `context` is a definition collection. Problems expose `loc` and `kind`.

## `velnora_metadata.typed_json`

The module exports `check`.

## `velnora_metadata.typed_json.check`

`check(value, annotation)` accepts JSON-compatible data and a caller-supplied `TypedDict` annotation. It returns `(checked_value, problems)`, where `checked_value` is the checked mapping or `None`, and `problems` is a tuple of objects exposing `loc` and `kind`.

## `velnora_metadata.pydantic`

The module exposes `VelnoraV3ArrayMetadata` as a field annotation for a caller's Pydantic model.

## `velnora_metadata.pydantic.VelnoraV3ArrayMetadata`

`VelnoraV3ArrayMetadata` is usable as a caller-model field annotation. `model_validate` accepts the field's JSON document and returns a field value exposing `shape`, `attributes`, and `to_json()`. Rejection raises `pydantic.ValidationError`. `model_dump_json()` places the metadata document in that field of the caller's JSON object. `model_json_schema()` returns a JSON Schema accepted by `jsonschema.Draft202012Validator`.

## `velnora_metadata.v3.definition`

The module exports `CORE`, `CORE_AND_EXTENSIONS`, `Context`, `DataTypeDefinition`, `ChunkGridDefinition`, `ChunkKeyEncodingDefinition`, `CodecDefinition`, `StorageTransformerDefinition`, `resolve`, and `canonicalize`.

Metadata declaration names are `bool`; `int8`, `int16`, `int32`, `int64`; `uint8`, `uint16`, `uint32`, `uint64`; `float16`, `float32`, `float64`; `complex64`, `complex128`; `r<N>` for a raw-bit width expressed in decimal bits; `string`; `bytes`; `numpy.datetime64`; `numpy.timedelta64`; and `struct`. Grid names are `regular` and `rectilinear`; addressing names are `default` and `v2`. Codec names are `blosc`, `bytes`, `crc32c`, `gzip`, `sharding_indexed`, `transpose`, `zstd`, `scale_offset`, and `cast_value`. Rectilinear configuration uses `kind: "inline"` and `chunk_shapes`; a repeated-size entry is `[size, count]`. Temporal configuration uses `unit` and `scale_factor`; records use `fields` with `name` and `data_type`. Definition descriptors reached here are `kind="bytes_bytes"` and `size="static"`.

## `velnora_metadata.v3.definition.DataTypeDefinition`

`DataTypeDefinition(name=..., configuration=...)` constructs a definition value. `name` is a string and `configuration` is a caller-supplied `TypedDict` type.

## `velnora_metadata.v3.definition.ChunkGridDefinition`

`ChunkGridDefinition(name=..., configuration=...)` constructs a definition value. `name` is a string and `configuration` is a caller-supplied `TypedDict` type.

## `velnora_metadata.v3.definition.ChunkKeyEncodingDefinition`

`ChunkKeyEncodingDefinition(name=..., configuration=...)` constructs a definition value. `name` is a string and `configuration` is a caller-supplied `TypedDict` type.

## `velnora_metadata.v3.definition.StorageTransformerDefinition`

`StorageTransformerDefinition(name=..., configuration=...)` constructs a definition value. `name` is a string and `configuration` is a caller-supplied `TypedDict` type.

## `velnora_metadata.v3.definition.CodecDefinition`

`CodecDefinition(name=..., configuration=..., kind=..., size=...)` constructs a definition value. `name` is a string and `configuration` is a caller-supplied `TypedDict` type. `kind` and `size` are string descriptors of the codec's transformation and encoded-size category. The value supports `dataclasses.replace` for replacing `configuration`.

## `velnora_metadata.v3.definition.Context`

`Context.of(*definitions)` returns a definition collection. `context.extended_with(*definitions)` returns another collection. `context.definitions()` returns an iterable of definition values.

## `velnora_metadata.v3.definition.CORE`

`CORE` is a definition collection accepted as a `context`, exposing `definitions()` and `extended_with(*definitions)`.

## `velnora_metadata.v3.definition.CORE_AND_EXTENSIONS`

`CORE_AND_EXTENSIONS` is a definition collection accepted as a `context`, exposing `definitions()` and `extended_with(*definitions)`.

## `velnora_metadata.v3.definition.resolve`

`resolve(field, kind, context)` returns `(resolved, problems)`. A declaration is a name string or `{'name': <str>, 'configuration': <mapping>, 'must_understand': <bool>}` with optional configuration and understanding members. `kind` is a definition category class. `resolved` exposes `resolution`, `definition`, and `configuration`; `problems` is a tuple of validation problems. Resolution labels are `read`, `invalid`, and `out_of_scope`. `definition` may be `None` and `configuration` is a checked mapping.

## `velnora_metadata.v3.definition.canonicalize`

`canonicalize(field, kind, context)` returns `(declaration, problems)`. `declaration` is a name string, a named-configuration mapping, or `None`; `problems` is a tuple of validation problems.

## `velnora.dtype`

The module exports `Bool`, `Int8`, `Int16`, `Int32`, `Int64`, `UInt8`, `UInt16`, `UInt32`, `UInt64`, `Float16`, `Float32`, `Float64`, `Complex64`, `Complex128`, `FixedLengthUTF32`, `VariableLengthUTF8`, `NullTerminatedBytes`, `RawBytes`, `VariableLengthBytes`, `DateTime64`, `TimeDelta64`, `Struct`, `parse_dtype`, and `data_type_registry`. Floating-point scalar carriers spell non-finite values `NaN`, `Infinity`, and `-Infinity`.

Temporal unit spellings, from years through attoseconds and unspecified units, are `Y`, `M`, `W`, `D`, `h`, `m`, `s`, `ms`, `us`, `ns`, `ps`, `fs`, `as`, and `generic`.

## `velnora.dtype.Bool`

`Bool()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are JSON booleans.

## `velnora.dtype.Int8`

`Int8()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` and `cast_scalar(data)` return native scalars. Scalar carriers are JSON integers.

## `velnora.dtype.Int16`

`Int16()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are JSON integers.

The class is subclassable; `_velnora_v3_name` is the class-level metadata-name string used by registered subclasses.

## `velnora.dtype.Int32`

`Int32()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are JSON integers.

## `velnora.dtype.Int64`

`Int64()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are JSON integers.

## `velnora.dtype.UInt8`

`UInt8()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are JSON integers.

## `velnora.dtype.UInt16`

`UInt16()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are JSON integers.

## `velnora.dtype.UInt32`

`UInt32()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are JSON integers.

## `velnora.dtype.UInt64`

`UInt64()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are JSON integers.

## `velnora.dtype.Float16`

`Float16()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Finite scalar carriers are JSON numbers.

## `velnora.dtype.Float32`

`Float32()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` and `cast_scalar(data)` return native scalars. Finite scalar carriers are JSON numbers.

## `velnora.dtype.Float64`

`Float64()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Finite scalar carriers are JSON numbers.

## `velnora.dtype.Complex64`

`Complex64()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Complex carriers are two-element lists or tuples of real and imaginary components.

## `velnora.dtype.Complex128`

`Complex128()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Complex carriers are two-element lists or tuples of real and imaginary components.

## `velnora.dtype.FixedLengthUTF32`

`FixedLengthUTF32(length=...)` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are text strings.

## `velnora.dtype.VariableLengthUTF8`

`VariableLengthUTF8()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Scalar carriers are text strings.

## `velnora.dtype.NullTerminatedBytes`

`NullTerminatedBytes(length=...)` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Byte scalar carriers are base64 strings.

## `velnora.dtype.RawBytes`

`RawBytes(length=...)` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Byte scalar carriers are base64 strings.

## `velnora.dtype.VariableLengthBytes`

`VariableLengthBytes()` returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Byte scalar carriers are base64 strings.

## `velnora.dtype.DateTime64`

`DateTime64(unit=..., scale_factor=...)` returns a Velnora dtype object. `scale_factor` may be omitted.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype. Temporal configurations have `unit: str` and `scale_factor: int`; `from_native_dtype(dtype)` is also supported.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` and `cast_scalar(data)` return native scalars. Temporal scalar carriers are integer tick counts or the missing-time marker `NaT`. Invalid type construction raises `ValueError`.

The format-3 metadata name is `numpy.datetime64`.

## `velnora.dtype.TimeDelta64`

`TimeDelta64(unit=..., scale_factor=...)` returns a Velnora dtype object. `scale_factor` may be omitted.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype. Temporal configurations have `unit: str` and `scale_factor: int`; `from_native_dtype(dtype)` is also supported.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Temporal scalar carriers are integer tick counts or the missing-time marker `NaT`. Invalid type construction raises `ValueError`.

The format-3 metadata name is `numpy.timedelta64`.

## `velnora.dtype.Struct`

`Struct.from_native_dtype(dtype)` accepts a native record dtype and returns a Velnora dtype object.

`to_json(zarr_format=...)` returns a type description. The format-2 carrier is `{'name': <dtype spelling or recursive field list>, 'object_codec_id': <str | None>}`. The format-3 carrier is a name string or `{'name': <str>, 'configuration': <mapping>}`. `to_native_dtype()` returns the corresponding NumPy-compatible dtype. Record configuration uses `fields`, a sequence of entries with `name` and `data_type`.

`to_json_scalar(data, *, zarr_format)` returns a JSON scalar carrier; `from_json_scalar(data, *, zarr_format)` returns a native scalar. `default_scalar()` returns a native scalar. Record scalar carriers are recursively named field mappings or base64 strings containing one record's bytes; format-2 bytes use the native record byte order and format-3 bytes use little-endian field storage. Invalid type construction raises `ValueError`.

## `velnora.dtype.parse_dtype`

`parse_dtype(dtype, *, zarr_format)` accepts a native dtype and returns a Velnora dtype object exposing `to_native_dtype()`. Rejection raises `ValueError`.

## `velnora.data_type_registry`

`data_type_registry`, also exported by `velnora.dtype`, exposes `register(key, cls)`, `unregister(key)`, `match_dtype(dtype)`, and `match_json(data, *, zarr_format)`. Keys are metadata-name strings and registered classes provide native-type and metadata conversion methods. Matching returns a dtype object exposing `to_native_dtype`, `to_json`, `to_json_scalar`, and `from_json_scalar`. Unresolved or ambiguous matching raises `ValueError`.

## `velnora.codecs`

The module exports `BloscCodec`, `BytesCodec`, `Crc32cCodec`, `GzipCodec`, `ZstdCodec`, `TransposeCodec`, `ScaleOffset`, `CastValue`, `VLenUTF8Codec`, and `VLenBytesCodec`. `numcodecs` is an importable submodule; `BZ2`, `Zlib`, `LZ4`, `LZMA`, `CRC32`, `Delta`, and `BitRound` are available both here and through that submodule.

## `velnora.codecs.BloscCodec`

`BloscCodec(*, typesize, cname, clevel, shuffle, blocksize)` constructs a codec; listed configuration keywords may be omitted. `typesize`, `clevel`, and `blocksize` are integers; `cname` and `shuffle` are string selectors.

`to_dict()` returns `{'name': <encoding name>, 'configuration': <configuration mapping>}`.

The serialized `name` is `blosc`. `shuffle` spellings are `noshuffle`, `shuffle`, and `bitshuffle`.

Algorithm spellings for `cname` are `lz4`, `lz4hc`, `blosclz`, `snappy`, `zlib`, and `zstd`.

## `velnora.codecs.BytesCodec`

`BytesCodec(*, endian)` constructs a codec; listed configuration keywords may be omitted. `endian` is a byte-order string.

`to_dict()` returns `{'name': <encoding name>, 'configuration': <configuration mapping>}`.

The serialized `name` is `bytes`. `endian` uses `little` or `big`. Its payload carries fixed-width elements in the declared byte order.

## `velnora.codecs.Crc32cCodec`

`Crc32cCodec()` constructs a codec.

The payload consists of the protected bytes followed by a four-byte little-endian CRC32C checksum. A checksum refusal raises `ValueError`.

## `velnora.codecs.GzipCodec`

`GzipCodec(*, level)` constructs a codec; listed configuration keywords may be omitted. `level` is an integer.

`to_dict()` returns `{'name': <encoding name>, 'configuration': <configuration mapping>}`. The class is subclassable. A registered subclass can implement `from_dict(data)`, `to_dict()`, `_encode_sync(chunk_bytes, chunk_spec)`, and `_decode_sync(chunk_bytes, chunk_spec)`. These hooks receive byte buffers and a chunk specification with `prototype.buffer.from_bytes(...)`, and return byte buffers. `level` is a public integer attribute.

The serialized `name` is `gzip`.

## `velnora.codecs.ZstdCodec`

`ZstdCodec(*, level, checksum)` constructs a codec; listed configuration keywords may be omitted. `level` is an integer. `checksum` is boolean.

`to_dict()` returns `{'name': <encoding name>, 'configuration': <configuration mapping>}`.

The serialized `name` is `zstd`.

## `velnora.codecs.TransposeCodec`

`TransposeCodec(*, order)` constructs a codec; `order` is a sequence of axis integers.

## `velnora.codecs.ScaleOffset`

`ScaleOffset(*, offset, scale)` constructs a codec; either keyword may be omitted. `offset` and `scale` are scalar configuration values.

## `velnora.codecs.CastValue`

`CastValue(*, data_type, rounding, out_of_range, scalar_map)` constructs a codec; `data_type` is required and other listed keywords may be omitted. `data_type` is a dtype name or object, `rounding` and `out_of_range` are string choices, and `scalar_map` is a mapping with optional `encode` and `decode` entries, each a sequence of `(source_scalar, target_scalar)` pairs.

`rounding` spellings are `nearest-even`, `nearest-away`, `towards-zero`, `towards-positive`, and `towards-negative`; `out_of_range` includes `clamp` and `wrap`.

Unavailable required conversion support raises `ImportError`. Incompatible conversion inputs raise `ValueError`.

## `velnora.codecs.VLenUTF8Codec`

`VLenUTF8Codec()` constructs a codec.

The byte payload starts with a little-endian unsigned 32-bit element count. Each element then has a little-endian unsigned 32-bit byte length followed by that many bytes. Element bytes are UTF-8 text.

## `velnora.codecs.VLenBytesCodec`

`VLenBytesCodec()` constructs a codec.

The byte payload starts with a little-endian unsigned 32-bit element count. Each element then has a little-endian unsigned 32-bit byte length followed by that many bytes.

## `velnora.codecs.numcodecs`

The module exposes `LZ4`, `Zlib`, `BZ2`, `LZMA`, `CRC32`, `Delta`, `BitRound`, `PackBits`, and `Quantize` as codec constructors. Instances expose `codec_name: str` and `to_dict()` returning `{'name': <str>, 'configuration': <mapping>}`.

## `velnora.codecs.numcodecs.LZ4`

`LZ4()` returns a codec instance. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora.codecs.numcodecs.Zlib`

`Zlib(*, level)` returns a codec instance. Listed configuration arguments may be omitted. Compression settings are integers. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora.codecs.numcodecs.BZ2`

`BZ2(*, level)` returns a codec instance. Listed configuration arguments may be omitted. Compression settings are integers. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora.codecs.numcodecs.LZMA`

`LZMA(*, format, check, preset)` returns a codec instance. Listed configuration arguments may be omitted. Compression settings are integers. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora.codecs.numcodecs.CRC32`

`CRC32()` returns a codec instance. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

The payload consists of a four-byte little-endian unsigned CRC32 checksum followed by the protected bytes. A checksum refusal raises `RuntimeError`.

## `velnora.codecs.numcodecs.Delta`

`Delta(*, dtype, astype)` returns a codec instance. `dtype` is required; `astype` may be omitted; `dtype` and `astype` are dtype spellings. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora_indexing`

The package exports `IndexDomain`, `IndexTransform`, `ConstantMap`, `DimensionMap`, `ArrayMap`, `BoundsCheckError`, `NdselError`, `parse_ndsel`, `normalize_ndsel`, `dimension_grids_from_chunks`, `plan_chunks`, `LazyArray`, and `basic_reader`.

## `velnora_indexing.IndexDomain`

`IndexDomain(inclusive_min, exclusive_max, labels)` accepts integer tuples for bounds and an optional tuple of string labels or `None`; the third argument may be omitted or passed by keyword. `IndexDomain.from_shape(shape)` returns a domain from a shape tuple.

Public fields are `inclusive_min`, `exclusive_max`, `origin`, and `shape`, each an integer tuple; `ndim` is an integer; `labels` is a string tuple or `None`. `contains(index)` and `contains_domain(other)` return booleans. `translate(offset)` returns an `IndexDomain`. Invalid construction or incompatible translation raises `ValueError`.

## `velnora_indexing.ConstantMap`

`ConstantMap(offset)` accepts an integer source coordinate and returns an output-coordinate map accepted by `IndexTransform`.

## `velnora_indexing.DimensionMap`

`DimensionMap(input_dimension, offset=..., stride=...)` accepts an integer input-axis number and optional integer offset and stride, and returns an output-coordinate map accepted by `IndexTransform`.

## `velnora_indexing.ArrayMap`

`ArrayMap(index_array, offset=..., stride=...)` accepts a native integer ndarray and optional integer offset and stride, and returns an output-coordinate map accepted by `IndexTransform`.

## `velnora_indexing.IndexTransform`

`IndexTransform(domain, output)` accepts an `IndexDomain` and a tuple of output-coordinate maps. `IndexTransform.from_shape(shape)` and `IndexTransform.identity(domain)` return transforms.

`domain` is an `IndexDomain`. `apply(point)` accepts an integer coordinate sequence and returns an integer tuple with one entry per source dimension. `compose(inner)` and `translate_domain_by(shift)` return transforms; incompatible ranks raise `ValueError`.

Bracket selection, `oindex[...]`, and `vindex[...]` return transforms. Selectors include integers, slices, ellipses, `None`, integer coordinate arrays, and Boolean masks. Out-of-domain refusal raises `BoundsCheckError`.

`intersect(output_domain)` returns `None` or `(restricted_transform, <bookkeeping>)`. Rank disagreement raises `ValueError`.

`from_json(data)` returns an executable transform from a transform-body mapping; `to_json()` returns such a mapping. The body has `input_rank: int`, `input_inclusive_min: list`, `input_exclusive_max: list`, `input_labels: list[str]`, and `output: list[dict]`. Incoming descriptions also accept `input_shape` and `input_inclusive_max`. Each output rule has `offset` and optional `stride`, `input_dimension`, `index_array`, and `index_array_bounds`. `index_array` is a nested integer list; `index_array_bounds` is a two-entry list of inclusive bounds. Bound carriers are integers, `-inf`, or `+inf`; a single-element list wraps an implicitly declared bound. Unnamed labels are empty strings. Invalid exchange data raises `NdselError`.

## `velnora_indexing.BoundsCheckError`

`BoundsCheckError` is the public exception carrier for a coordinate selection outside its source domain.

## `velnora_indexing.NdselError`

`NdselError` exposes a string `reason`. Its reason labels are `invalid_json`, `unknown_kind`, `unknown_field`, `rank_mismatch`, `multiple_upper_bounds`, `bounds_out_of_order`, `step_zero`, and `output_map_conflict`.

## `velnora_indexing.parse_ndsel`

`parse_ndsel(obj)` accepts a selection-message mapping and returns a validated message mapping accepted by `normalize_ndsel`. Rejection raises `NdselError`.

A selection message has `kind`. A `point` or `points` message carries `coords`. A `box` message carries `inclusive_min`, `exclusive_max`, `inclusive_max`, `shape`, and `labels` as applicable. A `slice` message carries `start`, `stop`, and optional `step` integer lists. A `transform` message carries a transform body: `input_rank`, `input_inclusive_min`, `input_exclusive_max`, `input_inclusive_max`, `input_shape`, `input_labels`, and `output`, as applicable.

## `velnora_indexing.normalize_ndsel`

`normalize_ndsel(obj)` accepts a selection-message mapping or a validated message and returns a transform-body mapping without `kind`: `{'input_rank': <int>, 'input_inclusive_min': <list>, 'input_exclusive_max': <list>, 'input_labels': <list[str]>, 'output': <list[coordinate-rule mapping]>}`. Coordinate rules use `offset`, `stride`, `input_dimension`, or `index_array`; bound carriers include integers, `-inf` and `+inf`, and singleton lists for implicit declarations. Rejection raises `NdselError`.

## `velnora_indexing.dimension_grids_from_chunks`

`dimension_grids_from_chunks(chunks, shape)` accepts a sequence of regular integer sizes or per-axis size sequences plus the source shape. It returns dimension-grid objects accepted by `plan_chunks`.

## `velnora_indexing.plan_chunks`

`plan_chunks(transform, dimension_grids)` returns a finite iterable of chunk projections. Each exposes `chunk_coords: tuple[int, ...]`, `chunk_domain: IndexDomain`, `chunk_transform: IndexTransform`, `cell_transform: IndexTransform`, and `coverage: str`. `chunk_transform` maps contribution positions to chunk-local source coordinates; `cell_transform` maps them to requested-result positions. Coverage labels are `full`, `partial`, and `unknown`.

`IndexError` carries out-of-grid refusal; `ValueError` carries unsupported shared-axis affine planning; `NotImplementedError` carries unsupported shared-axis mixed affine/explicit planning.

## `velnora_indexing.LazyArray`

`LazyArray(array)` accepts an array-like source exposing `shape`, NumPy-compatible `dtype`, and integer/slice bracket reads. Views expose `shape: tuple[int, ...]` and `transform: IndexTransform`.

Bracket selection, `oindex[...]`, and `vindex[...]` return views. A refused ordinary selector raises `IndexError`. A refused `IndexDomain` key raises `BoundsCheckError`, or `ValueError` for a rank disagreement. Ordinary selectors, `IndexDomain`, and `IndexTransform` are accepted bracket keys. `result()` returns a writable host NumPy ndarray exposing its shape, dtype, and selected element values. `numpy.asarray(view, dtype=...)` uses the NumPy conversion protocol; dtype may be omitted.

`with_reader(reader)` returns a derived view. The reader supplies `read_into(source, context, out, /)`, receiving the source, a context with `transform` and `projection`, and a writable ndarray destination. `projection` is a chunk projection or `None`.

`with_parts(parts)` accepts a sequence of regular partition lengths; `with_parts_per_axis(sizes)` accepts per-axis length sequences. Each returns a view. `parts()` returns a finite iterable whose entries expose `projection`, `view`, and `out_selection`. `projection` exposes the same fields as a chunk projection. `view` is a lazy view and `out_selection` is a tuple of native destination index selectors.

`write(values)`, bracket assignment, `oindex[...] = values`, and `vindex[...] = values` are synchronous write entries. Incompatible assignment shapes raise `ValueError`; assignment to a source lacking assignment support raises `TypeError`.

## `velnora_indexing.basic_reader`

`basic_reader.read_into(source, context, out)` is synchronous and fills the supplied native ndarray destination. `context` exposes `transform` and `projection`.

## `velnora_http_server`

The package exports `store_app`, `node_app`, `CorsOptions`, `serve`, and `serve_background`.

## `velnora_http_server.store_app`

`store_app(store, *, methods, cors_options, max_body_size)` returns an ASGI application. Keywords may be omitted. `methods` is a set of HTTP method strings; `cors_options` is a `CorsOptions` object; `max_body_size` is a request-body byte count or `None`. Configuration rejection raises `ValueError`.

## `velnora_http_server.node_app`

`node_app(node, *, methods)` accepts an `Array` or `Group` and returns an ASGI application. `methods` may be omitted and is a set of HTTP method strings.

Configuration rejection raises `ValueError`.

## `velnora_http_server.CorsOptions`

`CorsOptions(allow_origins=..., allow_methods=..., allow_headers=..., allow_credentials=..., expose_headers=...)` accepts string lists and a boolean credentials choice; keywords may be omitted. `allow_methods` also accepts `*` as a member.

## `velnora_http_server.serve`

`serve(app, *, port)` accepts an ASGI application and an integer port. It is a blocking call completing without a result on managed shutdown.

The managed process-stop signal is `SIGTERM`. Successful managed termination returns control to the caller and exits with status `0` when the caller finishes.

## `velnora_http_server.serve_background`

`serve_background(app, *, port, shutdown_timeout, uvicorn_options)` returns a background server handle. Keywords may be omitted; `port` is an integer or `auto`; `shutdown_timeout` is a duration in seconds. `uvicorn_options` is a mapping accepting `ssl_certfile` and `ssl_keyfile` PEM file paths, or a `uds` socket path.

The handle has `url`, a string shaped as `<scheme>://<host>:<port>` or `None` for a non-network binding. Scheme spellings are `http` and `https`. `shutdown()` is synchronous and returns `None`; unsuccessful startup or shutdown raises `RuntimeError`. The handle supports synchronous context management.

## `HTTP`

Applications address stored objects at `/<key>` with the raw object bytes as the response body. Methods reached through this interface are `GET`, `HEAD`, `PUT`, `POST`, `DELETE`, `PATCH`, and `OPTIONS`. A replacement request carries raw bytes in its body, with either `Content-Length` or chunked HTTP transfer framing.

Response statuses are `200` for a complete read, `206` for a partial representation, `204` for an accepted replacement, `404` for not found, `405` for method refusal, `416` for an unsatisfiable range, and `413` for a body-size refusal. `HEAD` has an empty response body. `Content-Length` is a decimal byte count.

`Range` uses the single-byte-range request grammar `bytes=<first>-<last>`, `bytes=<first>-`, or `bytes=-<suffix>`. A partial response carries `Content-Range: bytes <first>-<last>/<total>`; the total carrier may be a decimal length or `*`.

Cross-origin requests use `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`. Cross-origin response headers are `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Methods`, and `Access-Control-Expose-Headers`. Credentials are advertised as `true`; method and header collections are comma-separated text. Header names are case-insensitive. Preflight status is `200` for acceptance or `400` for refusal. Lowercase lookup spellings are `content-length`, `content-range`, `access-control-allow-origin`, `access-control-allow-credentials`, `access-control-allow-headers`, `access-control-allow-methods`, and `access-control-expose-headers`.

## `velnora.metadata.migrate_v3`

The module exports synchronous `migrate_v2_to_v3` and asynchronous `remove_metadata`.

## `velnora.metadata.migrate_v3.migrate_v2_to_v3`

`migrate_v2_to_v3(*, input_store, output_store, dry_run)` completes synchronously without a result. `input_store` and optional `output_store` are store handles; `dry_run` is an optional boolean. `TypeError` carries an unsupported source format or codec role; `NotImplementedError` carries unsupported consolidated-source migration; `ValueError` carries an unknown codec conversion. Refusing existing format 3 metadata raises `TypeError` or `ValueError`.

Operation reports use Python logging messages. A reported local target is carried by a literal `file://` followed by its absolute filesystem path through the end of the message line.

## `velnora.metadata.migrate_v3.remove_metadata`

`remove_metadata(store, zarr_format, force=..., dry_run=...)` is awaitable and completes without a result. `zarr_format` is an integer; optional policy arguments are booleans. Refusal raises `ValueError`.

Operation reports use Python logging messages. A reported local target is carried by a literal `file://` followed by its absolute filesystem path through the end of the message line.

## `velnora migrate v3`

Command syntax is `velnora migrate v3 INPUT [OUTPUT] [--remove-v2-metadata] [--overwrite] [--force] [--dry-run]`. Locations are command arguments naming stores. Options are switches without values. Successful completion exits `0`; refused operations exit `1` and carry a nonempty human-readable diagnostic on `stderr`.

Operation reports are text lines on `stderr`. A reported local target is carried by a literal `file://` followed by its absolute filesystem path through the end of the line.

## `velnora remove-metadata`

Command syntax is `velnora remove-metadata v2|v3 STORE [--force] [--dry-run]`. The version token is a literal command argument and options are switches. Successful completion exits `0`; refused operations exit `1` with a nonempty human-readable diagnostic on `stderr`.

Operation reports are text lines on `stderr`. A reported local target is carried by a literal `file://` followed by its absolute filesystem path through the end of the line.

## `.zarray`

An array's format-2 document is at `<node path>/.zarray`, or `.zarray` at the root. It contains JSON with `zarr_format`, `shape`, `chunks`, `dtype`, `fill_value`, `order`, `filters`, and `compressor`; chunk-addressing configuration may use `dimension_separator`. Shape and chunks are integer lists. `dtype` is a native dtype spelling or recursive named-field description; codecs are configuration mappings with `id`.

## `.zgroup`

A group's format-2 document is at `<node path>/.zgroup`, or `.zgroup` at the root. It contains a JSON object with `zarr_format`.

## `.zattrs`

Format-2 attributes are stored at `<node path>/.zattrs`, or `.zattrs` at the root. The file contains the string-keyed JSON attribute object.

## `.zmetadata`

Format-2 consolidated metadata uses `.zmetadata` at the consolidated root. Its JSON object has `zarr_consolidated_format` and `metadata`; `metadata` maps relative metadata-document keys to JSON documents.

The consolidated-format tag is `zarr_consolidated_format: 1`.

## `zarr.json`

A format-3 node document is at `<node path>/zarr.json`, or `zarr.json` at the root. Its JSON object carries `zarr_format` and `node_type`; `node_type` is the string `array` or `group` identifying the node kind. Array documents carry `shape`, `data_type`, `fill_value`, `chunk_grid`, `chunk_key_encoding`, and `codecs`, with `attributes` and `dimension_names` when represented. Codecs use named declarations: a name string or an object with `name`, `configuration`, and `must_understand`.

A group's `consolidated_metadata` field has `kind`, `must_understand`, and `metadata`. That mapping uses relative node paths as keys and node JSON objects as values.

An array's `chunk_grid` is a named declaration with the outer chunk's integer length list at `configuration.chunk_shape`. A sharding codec declaration has `name: 'sharding_indexed'` and a `configuration` mapping whose `chunk_shape` is the inner chunk's integer length list.

## `chunk keys`

Default format-3 data keys use `c/<coordinate>/<coordinate>/...`; format-2 data keys use decimal chunk coordinates separated by `.`. Keys are relative to the array path. The separator can also be `/` for format-2-compatible chunk addressing. A sharded data key addresses a shard.

With `index_location` set to `end`, the shard index is at the end of the shard object and its last four bytes are its CRC32C checksum.

## `velnora.core.group`

The module exposes `GroupMetadata` for hierarchy descriptions.

## `velnora.core.metadata.v3`

The module exposes `RectilinearChunksDisabledError`.

## `velnora.core.sync`

The module exposes `sync` for completing awaitable store calls.

## `velnora.config.set`

Stated under `velnora.config`.

## `velnora.data_type_registry.match_dtype`

Stated under `velnora.data_type_registry`.

## `velnora.data_type_registry.match_json`

Stated under `velnora.data_type_registry`.

## `velnora.data_type_registry.register`

Stated under `velnora.data_type_registry`.

## `velnora.data_type_registry.unregister`

Stated under `velnora.data_type_registry`.

## `velnora.dtype.Struct.from_native_dtype`

Stated under `velnora.dtype.Struct`.

## `velnora.api.asynchronous.create_array`

Stated under `velnora.api.asynchronous`.

## `velnora.api.asynchronous.open_array`

Stated under `velnora.api.asynchronous`.

## `velnora.buffer.cpu.NDBuffer.from_numpy_array`

Stated under `velnora.buffer.cpu.NDBuffer`.

## `velnora.buffer.cpu.buffer_prototype`

The CPU provider exports subclassable `Buffer`, subclassable `NDBuffer`, and `buffer_prototype`.

## `velnora_metadata.v3.definition.Context.of`

`Context.of(*definitions)` returns a definition collection. `context.extended_with(*definitions)` returns another collection. `context.definitions()` returns an iterable of definition values.

## `velnora_metadata.v3.definition.Context.extended_with`

`Context.of(*definitions)` returns a definition collection. `context.extended_with(*definitions)` returns another collection. `context.definitions()` returns an iterable of definition values.

## `velnora_metadata.v3.definition.Context.definitions`

`Context.of(*definitions)` returns a definition collection. `context.extended_with(*definitions)` returns another collection. `context.definitions()` returns an iterable of definition values.

## `from_json`

Stated under `velnora_indexing.IndexTransform`.

## `from_key_value`

Stated under `velnora_metadata.model.VelnoraV2ArrayMetadata`.

## `from_shape`

Stated under `velnora_indexing.IndexDomain`.

## `identity`

Stated under `velnora_indexing.IndexTransform`.

## `read_into`

Stated under `velnora_indexing.LazyArray`.

## `from_url`

Stated under `velnora.storage.FsspecStore`.

## `BitRound`

`BitRound(*, keepbits)` accepts an integer `keepbits` and returns a codec object. Its configuration mapping has `name` and `configuration`, with `keepbits` in the latter.

Invalid precision raises `ValueError`; incompatible data types raise `TypeError` or `ValueError`. Rejection may occur during construction, array binding, writing, or reading.

## `BaseModel`

These entries belong to installed third-party packages, rather than the product package.

`numpy` exposes the floating-point constants `inf` and `nan`. It supplies `array(object, dtype=...)`, `asarray(object, dtype=...)`, `arange(stop, dtype=...)`, `empty(shape, dtype=..., order=...)`, `full_like(array, value)`, and `concatenate(arrays, axis=...)`, returning `ndarray` objects. `ndarray` exposes `shape` and supports indexing and arithmetic. `shape(array)` returns an integer tuple. `frombuffer(bytes, dtype=...)` returns an `ndarray`. Numeric scalar types include `int16`, `int32`, `float32`, `float64`, and `datetime64`. `datetime_data(dtype)` returns `(unit, count)`; `isnat(values)` returns Boolean values. `frexp(values)` returns fraction and binary-exponent arrays; `ldexp(values, exponents)` and `rint(values)` return numeric arrays. `array_equal(left, right)` returns a Boolean. `count_nonzero(values)` returns an integer. `flatnonzero(values)` returns integer indices; `ix_(*indices)` returns broadcast index arrays; `ndindex(shape)` yields coordinate tuples; `unravel_index(indices, shape)` returns coordinate arrays. `add.at(array, indices, values)` mutates the supplied array. The `dtypes` module supplies `StringDType()`. The `testing` module supplies `assert_array_equal(actual, desired)`, which raises `AssertionError` on mismatch.

`numcodecs` supplies codec constructors `Blosc(cname=..., clevel=..., shuffle=...)`, `Zstd(level=..., checksum=...)`, `GZip(level=...)`, `FixedScaleOffset(offset=..., scale=..., dtype=...)`, and `Categorize(labels=..., dtype=...)`. Instances supply `get_config()` mappings with `id` and codec-specific configuration members. `decode(bytes)` returns the decoded bytes-like value.

`obstore.store.HTTPStore(url, client_options=...)` is a remote store handle; `client_options` accepts `allow_http: bool` and `default_headers: dict[str, str]`. `obstore.get(store, key).bytes()` returns stored bytes. `httpx.Client(timeout=..., transport=...)` is a managed HTTP client; `HTTPTransport(uds=...)` accepts a local socket path. `client.get(url)` returns a response exposing integer `status_code` and byte-string `content`.

`pydantic.BaseModel` is the caller-model base. Instances provide `model_dump_json()` returning JSON text; `model_json_schema()` returns a schema mapping. `model_validate(value)` constructs a model and failures raise `pydantic.ValidationError`. `jsonschema.Draft202012Validator(schema).is_valid(document)` returns a Boolean. `typing_extensions.TypedDict` declares caller-owned typed mappings.

`yaml.safe_dump(mapping)` returns YAML text.

`obstore.store.S3Store(bucket, *, prefix, endpoint, access_key_id, secret_access_key, region, skip_signature, client_options, retry_config)` returns an object-store provider handle. `bucket`, `prefix`, `endpoint`, credential fields, and `region` are strings; `skip_signature` is boolean. `client_options` accepts `allow_http: bool` and `connect_timeout` and `timeout` duration strings; `retry_config` accepts integer `max_retries`.

`botocore.session.get_session().create_client('s3', endpoint_url=..., aws_access_key_id=..., aws_secret_access_key=..., region_name=..., config=...)` returns a client with `list_buckets()`, `create_bucket(Bucket=...)`, `put_object(Bucket=..., Key=..., Body=...)`, `get_object(Bucket=..., Key=...)`, and `close()`. `get_object` returns a mapping whose `Body` is a closable byte stream with `read()`. `botocore.config.Config` accepts numeric `connect_timeout` and `read_timeout`, and a `retries` mapping. `botocore.exceptions.ClientError.response` is a mapping with `Error.Code` identifying the service error.

## `Blosc`

Stated under `BaseModel`.

## `Categorize`

Stated under `BaseModel`.

## `Client`

Stated under `BaseModel`.

## `Draft202012Validator`

Stated under `BaseModel`.

## `FixedScaleOffset`

Stated under `BaseModel`.

## `GZip`

Stated under `BaseModel`.

## `HTTPStore`

Stated under `BaseModel`.

## `HTTPTransport`

Stated under `BaseModel`.

## `StringDType`

Stated under `BaseModel`.

## `TypedDict`

Stated under `BaseModel`.

## `ValidationError`

Stated under `BaseModel`.

## `Zstd`

Stated under `BaseModel`.

## `add`

Stated under `BaseModel`.

## `arange`

Stated under `BaseModel`.

## `array`

Stated under `BaseModel`.

## `array_equal`

Stated under `BaseModel`.

## `asarray`

Stated under `BaseModel`.

## `assert_array_equal`

Stated under `BaseModel`.

## `at`

Stated under `BaseModel`.

## `concatenate`

Stated under `BaseModel`.

## `count_nonzero`

Stated under `BaseModel`.

## `datetime64`

Stated under `BaseModel`.

## `datetime_data`

Stated under `BaseModel`.

## `dtypes`

Stated under `BaseModel`.

## `empty`

Stated under `BaseModel`.

## `flatnonzero`

Stated under `BaseModel`.

## `float32`

Stated under `BaseModel`.

## `float64`

Stated under `BaseModel`.

## `frombuffer`

Stated under `BaseModel`.

## `full_like`

Stated under `BaseModel`.

## `get`

Stated under `BaseModel`.

## `int16`

Stated under `BaseModel`.

## `int32`

Stated under `BaseModel`.

## `isnat`

Stated under `BaseModel`.

## `ix_`

Stated under `BaseModel`.

## `ndarray`

Stated under `BaseModel`.

## `ndindex`

Stated under `BaseModel`.

## `safe_dump`

Stated under `BaseModel`.

## `safe_load`

Stated under `BaseModel`.

## `shape`

Stated under `BaseModel`.

## `testing`

Stated under `BaseModel`.

## `unravel_index`

Stated under `BaseModel`.

## `value`

Stated under `BaseModel`.

## `_dependencies`

Stated under `BaseModel`.

## `velnora.codecs.numcodecs.BitRound`

Stated under `BitRound`.

## `frexp`

Stated under `BaseModel`.

## `ldexp`

Stated under `BaseModel`.

## `rint`

Stated under `BaseModel`.

## `decode`

Stated under `BaseModel`.

## `velnora.errors.VelnoraUserWarning`

`VelnoraUserWarning` is a `UserWarning` subclass carrying array-metadata compatibility warnings.

## `ASGI lifespan`

An application passed to `serve_background` is an async callable `application(scope, receive, send)`. The lifespan scope has `type: "lifespan"`. `receive()` is awaitable and supplies messages with `type: "lifespan.startup"` and `type: "lifespan.shutdown"`. The application acknowledges these through awaitable `send(message)` calls with `type: "lifespan.startup.complete"` and `type: "lifespan.shutdown.complete"`, respectively. Other scopes are passed to the supplied HTTP application.

## `velnora.codecs.BZ2`

`BZ2(*, level)` returns a codec instance. Listed configuration arguments may be omitted. Compression settings are integers. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora.codecs.BitRound`

Stated under `BitRound`.

## `velnora.codecs.CRC32`

`CRC32()` returns a codec instance. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

The payload consists of a four-byte little-endian unsigned CRC32 checksum followed by the protected bytes. A checksum refusal raises `RuntimeError`.

## `velnora.codecs.Delta`

`Delta(*, dtype, astype)` returns a codec instance. `dtype` is required; `astype` may be omitted; `dtype` and `astype` are dtype spellings. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora.codecs.LZ4`

`LZ4()` returns a codec instance. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora.codecs.LZMA`

`LZMA(*, format, check, preset)` returns a codec instance. Listed configuration arguments may be omitted. Compression settings are integers. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora.codecs.Zlib`

`Zlib(*, level)` returns a codec instance. Listed configuration arguments may be omitted. Compression settings are integers. Instances expose `codec_name` and `to_dict()` with `name` and `configuration`.

## `velnora.dtype.data_type_registry`

Stated under `velnora.data_type_registry`.

## `inf`

Stated under `BaseModel`.

## `nan`

Stated under `BaseModel`.

## `velnora.codecs.numcodecs.PackBits`

`PackBits()` returns a codec object accepted in `create_array(filters=...)`. Incompatible data types raise `ValueError` during construction, array binding, writing, or reading.

## `velnora.codecs.numcodecs.Quantize`

`Quantize(*, digits)` accepts an integer `digits` and returns a codec object accepted in `create_array(filters=...)`.
