# Interface Contract

The Python import package is `velnora`, with source package file `src/velnora/__init__.py`. A source root mounted at `/app/src` contains `velnora/__init__.py` and must be importable as `velnora`.

Python API results are returned as objects. Calls leave `stdout` available to the calling application; diagnostic logging uses `stderr` and Python logging. CSV, JSON Lines, Markdown and vocabulary text exchanged here use UTF-8 (`utf-8`).

## Access representations

Access representation strings are `numpy`, `torch`, `tensorflow`, `jax`, `pandas`, `polars`, and `arrow`; ordinary Python access is named by `None`.

Batched ordinary access returns a dictionary of Python lists. Numerical and tensor representations return a dictionary of `numpy.ndarray`, `torch.Tensor`, `tensorflow.Tensor`, or `jax.Array`, respectively. Array shapes have the batch dimension followed by within-record dimensions. Row access returns the corresponding scalar or within-record array values. Table representations return `pandas.DataFrame`, `polars.DataFrame`, or `pyarrow.Table`, including one-row tables for a single-row request.

Numerical arrays and tensor values expose NumPy conversion and `shape`; PyTorch values expose `detach().cpu().numpy()` and `tolist()`, TensorFlow values expose `numpy()`, Pandas tables expose `columns` and column `tolist()`, Polars tables expose `to_dict(as_series=False)` and `to_dicts()`, and Arrow tables expose `to_pydict()`.

An unavailable representation is carried by `ValueError`; a successful independent table representation instead exposes the same `to_dict(as_series=False)` column mapping.

Feature declarations and `Features` mappings support equality comparison with `==` and copying with `copy.deepcopy`.

## `velnora`

The `velnora` package exposes `Dataset`, `DatasetDict`, `IterableDataset`, `IterableDatasetDict`, `DatasetInfo`, `ReadInstruction`, `concatenate_datasets`, `interleave_datasets`, `load_dataset`, `load_from_disk`, `get_dataset_config_names`, `get_dataset_default_config_name`, `get_dataset_infos`, `get_dataset_config_info`, `get_dataset_split_names`.

Its submodule `velnora.features` exposes the feature declarations `Features`, `Value`, `List`, `Array2D`, `Array3D`, `Array4D`, `Array5D`, `ClassLabel`, `Translation`, `TranslationVariableLanguages`, `Json`, `Image`, `Audio`, `Video`, `Pdf`, `Nifti`, `Mesh`, `BioSequence`, `BioStructure`; they are imported as `from velnora.features import <name>`.

## `velnora.arrow_dataset`

`velnora.arrow_dataset` exposes `DatasetTransformationNotAllowedError`.

## `velnora.download`

`velnora.download` exposes `DownloadConfig`, `DownloadManager`.

## `velnora.exceptions`

`velnora.exceptions` exposes `DataFilesNotFoundError`, `DatasetGenerationError`.

## `velnora.search`

`velnora.search` exposes `MissingIndex`.

## `velnora.distributed`

`velnora.distributed` exposes `split_dataset_by_node`.

## `velnora.config`

### Environment

Environment variable names are `HF_HOME` for the configuration and cache home, `HF_HUB_CACHE` for the download directory, and `HF_VELNORA_CACHE` for the dataset cache directory.

The environment variables `XDG_CACHE_HOME`, `TMPDIR`, `TMP`, and `TEMP` accept directory paths for cache home and process temporary storage, respectively.

## `velnora.Dataset`

`Dataset(arrow_table, info=...)` accepts a `pyarrow.Table` and optional `DatasetInfo`.

`num_rows` and `num_columns` are integers; `column_names` is a list of strings; `features` is a `Features` mapping; `info` is a `DatasetInfo`. `str(dataset.split)` is the split-name string. `len(dataset)` is the row count.

Ordinary `iter(dataset)` yields row dictionaries `{<column>: <value>}`. `dataset[<integer>]` returns a row dictionary; slice and position-list keys return `{<column>: [<value>, ...]}`. A column-name string key returns an iterable of column values. Decoded nested records are dictionaries; lists and arrays are nested Python lists. Scalar values have Python numeric, boolean, string, bytes, `decimal.Decimal`, `datetime.date`, `datetime.time`, `datetime.datetime`, `datetime.timedelta`, or `None` representations, according to their features.

Row-position rejection raises `IndexError`; column-selection rejection raises `ValueError`.

## `velnora.IterableDataset`

`IterableDataset` exposes `features`, a `Features` mapping when known. `iter(dataset)` yields row dictionaries `{<column>: <value>}`; a column-name string key returns an iterable of column values. A rejected positional access raises `TypeError`, `KeyError`, or `ValueError` at access or consumption. Instances can be passed to `torch.utils.data.DataLoader`.

## `velnora.DatasetDict`

`DatasetDict(mapping)` accepts a mapping from split-name strings to `Dataset` objects. It supports key iteration, `items()`, `values()` and subscription by split-name string. `num_rows` and `num_columns` map split names to integer counts; `column_names` maps split names to lists of column-name strings. Missing split access raises `KeyError`.

## `velnora.IterableDatasetDict`

`IterableDatasetDict(mapping)` accepts a mapping from split-name strings to `IterableDataset` objects. It supports key iteration, `items()` and subscription by split-name string.

## `velnora.DatasetInfo`

`DatasetInfo(features=..., description=..., citation=..., license=..., homepage=..., version=...)` takes optional `Features`, descriptive strings, and a version string. Read attributes are `description`, `citation`, `license`, `homepage`, and `version`; `str(info.version)` is dotted version text. Discovery results also expose `config_name: str` and `splits`, a mapping keyed by split-name strings.

## `velnora.Features`

`Features(mapping)` takes a dictionary of column names to feature declarations. Nested record declarations are dictionaries of field names to declarations. It supports column-name iteration, subscription, and equality comparison of declarations.

## `velnora.Value`

`Value(dtype)` takes a scalar type spelling string. `dtype` is the type spelling. Syntax includes `null`, `bool`, `int<width>`, `uint<width>`, `float<width>`, `decimal<width>(<precision>, <scale>)`, `string`, `binary`, `date32`, `date64`, `time<width>[<unit>]`, `timestamp[<unit>]`, `timestamp[<unit>, tz=<zone>]`, and `duration[<unit>]`.

## `velnora.List`

`List(feature, length=...)` takes an element feature and optional integer `length`. Its `feature` attribute is the element declaration. Decoded values are Python lists or `None`.

## `velnora.Array2D`

`Array2D(shape, dtype)` takes a dimension tuple and scalar type string. A variable dimension is written `None` in the dimension tuple. Decoded values are nested Python lists.

## `velnora.Array3D`

`Array3D(shape, dtype)` takes a dimension tuple and scalar type string. A variable dimension is written `None` in the dimension tuple. Decoded values are nested Python lists.

## `velnora.Array4D`

`Array4D(shape, dtype)` takes a dimension tuple and scalar type string. A variable dimension is written `None` in the dimension tuple. Decoded values are nested Python lists.

## `velnora.Array5D`

`Array5D(shape, dtype)` takes a dimension tuple and scalar type string. A variable dimension is written `None` in the dimension tuple. Decoded values are nested Python lists.

## `velnora.ClassLabel`

`ClassLabel(names=..., names_file=..., num_classes=...)` takes a list of vocabulary strings, a string vocabulary-file path, or an integer class count. Its `names` attribute is a list of strings. Decoded values are integers or `None`. Label-definition and label-value rejections raise `ValueError`.

## `velnora.ClassLabel.str2int`

`ClassLabel.str2int(values)` takes one string or an iterable of strings and returns one integer or a list of integers, respectively. Conversion rejection raises `ValueError`.

## `velnora.ClassLabel.int2str`

`ClassLabel.int2str(values)` takes one integer or an iterable of integers and returns one string or a list of strings, respectively. Conversion rejection raises `ValueError`.

## `velnora.Translation`

`Translation(languages=...)` takes a list of language-name strings. Input and decoded rows are dictionaries `{<language>: <text string>}`.

## `velnora.TranslationVariableLanguages`

`TranslationVariableLanguages(languages=...)` takes a list of language-name strings. Input maps each language to a string or list of strings. A decoded row is `{"language": [<language>, ...], "translation": [<text>, ...]}`; corresponding positions identify one language/text pair. A rejection raises `ValueError` at construction or consumption.

## `velnora.Json`

`Json()` is a feature declaration whose decoded values are JSON-shaped Python scalars, lists, dictionaries or `None`.

## `velnora.Dataset.from_dict`

Class method `Dataset.from_dict(mapping, features=..., info=..., split=..., on_mixed_types=...)` returns a `Dataset`. `mapping` is a dictionary of column-name strings to sequences. Optional keywords take `Features`, `DatasetInfo`, a split-name string and a mixed-type policy string or `None`, respectively. The JSON-treatment token is `use_json`. Incompatible data raises `ValueError` or `TypeError` at construction or consumption; inconsistent column lengths raise `ValueError`.

## `velnora.Dataset.from_list`

Class method `Dataset.from_list(mapping, features=..., info=..., split=..., on_mixed_types=...)` returns a `Dataset`. `mapping` is a list of row dictionaries. Optional keywords take `Features`, `DatasetInfo`, a split-name string and a mixed-type policy string or `None`, respectively. The JSON-treatment token is `use_json`. Rejected data raises `ValueError` or `TypeError` at construction or consumption.

## `velnora.Dataset.from_generator`

Class method `Dataset.from_generator(generator, features=..., cache_dir=...)` returns a `Dataset`. `generator` is a callable yielding row dictionaries; `features` is optional `Features` and `cache_dir` is an optional directory string.

## `velnora.Dataset.from_file`

Class method `Dataset.from_file(filename)` returns a `Dataset`. `filename` is a string path to an Arrow IPC stream file.

## `velnora.Dataset.from_pandas`

Class method `Dataset.from_pandas(df)` returns a `Dataset`. `df` is a `pandas.DataFrame`.

## `velnora.Dataset.from_polars`

Class method `Dataset.from_polars(df)` returns a `Dataset`. `df` is a `polars.DataFrame`.

## `velnora.Dataset.from_sql`

Class method `Dataset.from_sql(sql, con, cache_dir=...)` returns a `Dataset`. `sql` is a table-name or SQL-query string. `con` is a database URI string or SQLAlchemy connection. `cache_dir` is an optional directory string.

## `velnora.IterableDataset.from_generator`

`IterableDataset.from_generator(generator, features=..., gen_kwargs=...)` takes a callable yielding row dictionaries, optional `Features`, and an optional keyword-argument dictionary for the producer. It returns an `IterableDataset`. List-valued entries in `gen_kwargs` identify source shards; a tuple is a single producer argument.

## `velnora.Dataset.to_iterable_dataset`

`Dataset.to_iterable_dataset(num_shards=...)` takes an optional integer source-shard count and returns an `IterableDataset`.

## `velnora.Dataset.iter`

`Dataset.iter(batch_size=..., drop_last_batch=...)` takes integer `batch_size` and optional boolean `drop_last_batch`. It returns an iterator of batches, ordinarily `{<column>: [<value>, ...]}`. Formatted batches have the selected access representation.

## `velnora.Dataset.batch`

`Dataset.batch(batch_size=..., by_column=..., drop_last_batch=...)` takes optional integer `batch_size`, a column-name string or list of strings as `by_column`, and boolean `drop_last_batch`. It returns a `Dataset` with decoded grouped rows `{<column>: [<value>, ...]}`. Rejected grouping raises `ValueError`.

## `velnora.IterableDataset.iter`

`IterableDataset.iter(batch_size=..., drop_last_batch=...)` takes integer `batch_size` and optional boolean `drop_last_batch`. It returns an iterator of batches, ordinarily `{<column>: [<value>, ...]}`. Formatted batches have the selected access representation.

## `velnora.IterableDataset.batch`

`IterableDataset.batch(batch_size=..., by_column=..., drop_last_batch=...)` takes optional integer `batch_size`, a column-name string or list of strings as `by_column`, and boolean `drop_last_batch`. It returns a `IterableDataset` with decoded grouped rows `{<column>: [<value>, ...]}`. Rejected grouping raises `ValueError`.

## `velnora.IterableDataset.state_dict`

`IterableDataset.state_dict()` returns a checkpoint dictionary, passed as a whole to `load_state_dict` and copyable with `copy.deepcopy`.

## `velnora.IterableDataset.load_state_dict`

`IterableDataset.load_state_dict(state_dict)` takes a checkpoint dictionary and configures subsequent iteration on that object.

## `velnora.IterableDataset.set_epoch`

`IterableDataset.set_epoch(epoch)` takes an integer epoch on that object.

## `velnora.Dataset.take`

`Dataset.take(n)` takes `int` and returns a `Dataset`. Rejected prefix selection raises `IndexError`.

## `velnora.Dataset.skip`

`Dataset.skip(n)` takes `int` and returns a `Dataset`.

## `velnora.Dataset.repeat`

`Dataset.repeat(num_times)` takes `int | None` and returns a `Dataset`. Rejected repetition raises `ValueError`.

## `velnora.IterableDataset.take`

`IterableDataset.take(n)` takes `int` and returns a `IterableDataset`.

## `velnora.IterableDataset.skip`

`IterableDataset.skip(n)` takes `int` and returns a `IterableDataset`.

## `velnora.IterableDataset.repeat`

`IterableDataset.repeat(num_times)` takes `int | None` and returns a `IterableDataset`.

## `velnora.Dataset.select`

`Dataset.select(indices)` takes an iterable of integer positions and returns a `Dataset`. Selection rejection raises `IndexError`; attached-index rejection raises `DatasetTransformationNotAllowedError`.

## `velnora.Dataset.sort`

`Dataset.sort(column_names, reverse=..., null_placement=...)` takes a column-name string or sequence, optional boolean or boolean sequence as `reverse`, and optional string `null_placement`. The beginning-placement token is `at_start`. It returns a `Dataset`. Request rejection raises `ValueError`; attached-index rejection raises `DatasetTransformationNotAllowedError`.

## `velnora.Dataset.shuffle`

`Dataset.shuffle(seed=..., load_from_cache_file=...)` takes an optional integer seed and boolean reuse switch and returns a `Dataset`. Attached-index rejection raises `DatasetTransformationNotAllowedError`.

## `velnora.IterableDataset.shuffle`

`IterableDataset.shuffle(seed=..., buffer_size=...)` takes an integer seed and integer shuffle scope in records and returns an `IterableDataset`.

## `velnora.Dataset.train_test_split`

`Dataset.train_test_split(test_size=..., train_size=..., shuffle=..., stratify_by_column=..., seed=..., load_from_cache_file=...)` takes optional integer or float sizes, a boolean shuffle choice, a stratification column-name string, an integer seed and a boolean reuse switch. It returns a `DatasetDict` with `train` and `test` dataset entries. Partition rejection raises `ValueError`; attached-index rejection raises `DatasetTransformationNotAllowedError`.

## `velnora.Dataset.shard`

`Dataset.shard(num_shards, index, contiguous=...)` takes integer `num_shards` and `index` and optional boolean `contiguous` and returns a `Dataset`. Selection rejection raises `ValueError`; attached-index rejection raises `DatasetTransformationNotAllowedError`.

## `velnora.IterableDataset.shard`

`IterableDataset.shard(num_shards, index)` takes integer `num_shards` and `index` and returns a `IterableDataset`. Selection rejection raises `IndexError` or `ValueError`.

## `velnora.IterableDataset.reshard`

`IterableDataset.reshard()` returns an `IterableDataset` accepting subsequent `shard` selection.

## `velnora.Dataset.rename_column`

`Dataset.rename_column(original_column_name, new_column_name)` takes two column-name strings and returns a `Dataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.Dataset.rename_columns`

`Dataset.rename_columns(column_mapping)` takes a dictionary mapping source to destination column-name strings and returns a `Dataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.Dataset.remove_columns`

`Dataset.remove_columns(column_names)` takes a column-name string or list of strings and returns a `Dataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.Dataset.select_columns`

`Dataset.select_columns(column_names)` takes a list of column-name strings and returns a `Dataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.Dataset.cast_column`

`Dataset.cast_column(column, feature)` takes a column-name string and a feature declaration and returns a `Dataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.Dataset.cast`

`Dataset.cast(features)` takes a `Features` mapping and returns a `Dataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.IterableDataset.rename_column`

`IterableDataset.rename_column(original_column_name, new_column_name)` takes two column-name strings and returns a `IterableDataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.IterableDataset.rename_columns`

`IterableDataset.rename_columns(column_mapping)` takes a dictionary mapping source to destination column-name strings and returns a `IterableDataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.IterableDataset.remove_columns`

`IterableDataset.remove_columns(column_names)` takes a column-name string or list of strings and returns a `IterableDataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.IterableDataset.select_columns`

`IterableDataset.select_columns(column_names)` takes a list of column-name strings and returns a `IterableDataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.IterableDataset.cast_column`

`IterableDataset.cast_column(column, feature)` takes a column-name string and a feature declaration and returns a `IterableDataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.IterableDataset.cast`

`IterableDataset.cast(features)` takes a `Features` mapping and returns a `IterableDataset`. Rejected column operations raise `ValueError` at the call or during consumption.

## `velnora.DatasetDict.rename_column`

`DatasetDict.rename_column(original_column_name, new_column_name)` takes two column-name strings and returns a `DatasetDict`.

## `velnora.DatasetDict.rename_columns`

`DatasetDict.rename_columns(column_mapping)` takes a dictionary mapping source to destination column-name strings and returns a `DatasetDict`.

## `velnora.DatasetDict.remove_columns`

`DatasetDict.remove_columns(column_names)` takes a column-name string or list of strings and returns a `DatasetDict`.

## `velnora.DatasetDict.select_columns`

`DatasetDict.select_columns(column_names)` takes a list of column-name strings and returns a `DatasetDict`.

## `velnora.DatasetDict.cast_column`

`DatasetDict.cast_column(column, feature)` takes a column-name string and a feature declaration and returns a `DatasetDict`.

## `velnora.DatasetDict.cast`

`DatasetDict.cast(features)` takes a `Features` mapping and returns a `DatasetDict`.

## `velnora.IterableDatasetDict.rename_column`

`IterableDatasetDict.rename_column(original_column_name, new_column_name)` takes two column-name strings and returns a `IterableDatasetDict`.

## `velnora.IterableDatasetDict.rename_columns`

`IterableDatasetDict.rename_columns(column_mapping)` takes a dictionary mapping source to destination column-name strings and returns a `IterableDatasetDict`.

## `velnora.IterableDatasetDict.remove_columns`

`IterableDatasetDict.remove_columns(column_names)` takes a column-name string or list of strings and returns a `IterableDatasetDict`.

## `velnora.IterableDatasetDict.select_columns`

`IterableDatasetDict.select_columns(column_names)` takes a list of column-name strings and returns a `IterableDatasetDict`.

## `velnora.IterableDatasetDict.cast_column`

`IterableDatasetDict.cast_column(column, feature)` takes a column-name string and a feature declaration and returns a `IterableDatasetDict`.

## `velnora.IterableDatasetDict.cast`

`IterableDatasetDict.cast(features)` takes a `Features` mapping and returns a `IterableDatasetDict`.

## `velnora.Dataset.flatten`

`Dataset.flatten()` returns a `Dataset`. Flattened field names use `.` between nested field components.

## `velnora.Dataset.class_encode_column`

`Dataset.class_encode_column(column, include_nulls=...)` returns a `Dataset`. `column` is a column-name string and `include_nulls` an optional boolean. Rejected categorical operations raise `ValueError`.

## `velnora.Dataset.align_labels_with_mapping`

`Dataset.align_labels_with_mapping(label2id, label_column)` returns a `Dataset`. `label2id` maps class-name strings to integer labels; `label_column` is a column-name string. Rejected categorical operations raise `ValueError`.

## `velnora.DatasetDict.flatten`

`DatasetDict.flatten()` returns a `DatasetDict`. Flattened field names use `.` between nested field components.

## `velnora.DatasetDict.class_encode_column`

`DatasetDict.class_encode_column(column, include_nulls=...)` returns a `DatasetDict`. `column` is a column-name string and `include_nulls` an optional boolean.

## `velnora.DatasetDict.align_labels_with_mapping`

`DatasetDict.align_labels_with_mapping(label2id, label_column)` returns a `DatasetDict`. `label2id` maps class-name strings to integer labels; `label_column` is a column-name string.

## `velnora.Dataset.unique`

`Dataset.unique(column)` takes a column-name string and returns a list of scalar values. Null is represented by `None`. Rejected column selection raises `ValueError`.

## `velnora.DatasetDict.unique`

`DatasetDict.unique(column)` takes a column-name string and returns a dictionary from split names to lists of scalar values. Null is represented by `None`. Rejected column selection raises `ValueError`.

## `velnora.Dataset.add_column`

`Dataset.add_column(name, column)` takes a name string and list of values and returns a `Dataset`. Rejected addition raises `ValueError`.

## `velnora.Dataset.add_item`

`Dataset.add_item(item)` takes a row dictionary and returns a `Dataset`.

## `velnora.Dataset.map`

`Dataset.map(function, with_indices=..., input_columns=..., batched=..., batch_size=..., drop_last_batch=..., remove_columns=..., fn_kwargs=..., num_proc=..., load_from_cache_file=..., cache_file_name=..., on_mixed_types=...)` returns a `Dataset`. `function` is a synchronous or asynchronous callable. Optional `with_indices` and `batched` are booleans; `input_columns` is a list of column-name strings; `batch_size` is an integer. `drop_last_batch` is a boolean; `remove_columns` is a list of column-name strings. `fn_kwargs` is a keyword dictionary; `num_proc` is an integer; `load_from_cache_file` is a boolean; `cache_file_name` is a string path to the produced intermediate file; `on_mixed_types` accepts `None` as the ordinary-typing option. The callback receives a row dictionary or a batched column dictionary `{<column>: [<value>, ...]}`. With `input_columns`, selected values or value lists are positional arguments. With `with_indices`, an integer position or list of positions follows those arguments. The callback returns a column dictionary of scalar values or, in batched mode, value sequences. Callback keyword arguments come from `fn_kwargs`. Inconsistent output raises `pyarrow.ArrowInvalid` or `ValueError`. Incompatible mixed output raises `pyarrow.ArrowInvalid`, `pyarrow.ArrowTypeError`, `TypeError`, or `ValueError`. A failed caller operation is surfaced as an `Exception` at the public call or consumption.

A caller-selected intermediate path is a filesystem path; `cache-` and `.arrow` are the cache-file prefix and suffix used for removable intermediate files.

## `velnora.Dataset.filter`

`Dataset.filter(function, with_indices=..., input_columns=..., batched=..., batch_size=...)` returns a `Dataset`. `function` is a synchronous or asynchronous callable. Optional `with_indices` and `batched` are booleans; `input_columns` is a list of column-name strings; `batch_size` is an integer. The callback receives a row dictionary or a batched column dictionary `{<column>: [<value>, ...]}`. With `input_columns`, selected values or value lists are positional arguments. With `with_indices`, an integer position or list of positions follows those arguments. The callback returns a boolean or, in batched mode, a sequence of booleans. A failed caller operation is surfaced as an `Exception` at the public call or consumption. Attached-index rejection raises `DatasetTransformationNotAllowedError`.

## `velnora.IterableDataset.map`

`IterableDataset.map(function, with_indices=..., input_columns=..., batched=..., batch_size=..., drop_last_batch=..., remove_columns=...)` returns a `IterableDataset`. `function` is a synchronous or asynchronous callable. Optional `with_indices` and `batched` are booleans; `input_columns` is a list of column-name strings; `batch_size` is an integer. `drop_last_batch` is a boolean; `remove_columns` is a list of column-name strings. The callback receives a row dictionary or a batched column dictionary `{<column>: [<value>, ...]}`. With `input_columns`, selected values or value lists are positional arguments. With `with_indices`, an integer position or list of positions follows those arguments. The callback returns a column dictionary of scalar values or, in batched mode, value sequences. A failed caller operation is surfaced as an `Exception` at the public call or consumption.

## `velnora.IterableDataset.filter`

`IterableDataset.filter(function, with_indices=..., input_columns=..., batched=..., batch_size=...)` returns a `IterableDataset`. `function` is a synchronous or asynchronous callable. Optional `with_indices` and `batched` are booleans; `input_columns` is a list of column-name strings; `batch_size` is an integer. The callback receives a row dictionary or a batched column dictionary `{<column>: [<value>, ...]}`. With `input_columns`, selected values or value lists are positional arguments. With `with_indices`, an integer position or list of positions follows those arguments. The callback returns a boolean or, in batched mode, a sequence of booleans. A failed caller operation is surfaced as an `Exception` at the public call or consumption.

## `velnora.DatasetDict.map`

`DatasetDict.map(function, with_indices=...)` takes a callable and returns a `DatasetDict`. The callback receives a row dictionary. `with_indices` is an optional boolean; when selected, an integer row position follows the row argument. The callback returns a dictionary of column names to scalar values.

## `velnora.DatasetDict.filter`

`DatasetDict.filter(function)` takes a callable and returns a `DatasetDict`. The callback receives a row dictionary. The callback returns a boolean.

## `velnora.IterableDatasetDict.map`

`IterableDatasetDict.map(function, with_indices=...)` takes a callable and returns a `IterableDatasetDict`. The callback receives a row dictionary. `with_indices` is an optional boolean; when selected, an integer row position follows the row argument. The callback returns a dictionary of column names to scalar values.

## `velnora.IterableDatasetDict.filter`

`IterableDatasetDict.filter(function)` takes a callable and returns a `IterableDatasetDict`. The callback receives a row dictionary. The callback returns a boolean.

## `velnora.concatenate_datasets`

`concatenate_datasets(dsets, axis=...)` takes a list of source objects and optional integer `axis` (`0` names rows; `1` names columns). It returns a `Dataset` or `IterableDataset` matching the input access model. Rejected composition raises `ValueError`.

## `velnora.interleave_datasets`

`interleave_datasets` takes a list of source objects as its first positional argument, an optional `probabilities` list of source probabilities, an optional integer `seed` and an optional `stopping_strategy` string. Policy tokens are `first_exhausted`, `all_exhausted`, and `all_exhausted_without_replacement`. It returns a `Dataset` or `IterableDataset` matching the input access model. Rejected composition or policy raises `ValueError` at the call or consumption.

## `velnora.distributed.split_dataset_by_node`

`split_dataset_by_node(dataset, rank, world_size, strategy=...)` takes an `IterableDataset`, integer node position and node count, and optional policy string. Policy tokens are `auto`, `shards`, and `examples`. It returns an `IterableDataset`. Distribution rejection raises `ValueError` at the call or consumption.

## `velnora.load_dataset`

`load_dataset(path, name=..., data_dir=..., data_files=..., split=..., cache_dir=..., features=..., download_mode=..., streaming=..., storage_options=..., **config_kwargs)` accepts:

- `path: str`: local source directory or reader name.
- `name: str`: configuration name; `data_dir: str`: source directory.
- `data_files`: a file path/URL string, list of such strings, or mapping from split names to strings or lists. Wildcard file selections and archive references use string syntax. A ZIP member reference is `zip://<member>::<archive>`.
- `split`: a split-name/instruction string or `ReadInstruction`.
- `cache_dir: str`, `features: Features`, `streaming: bool`, and `storage_options: dict`.
- `download_mode`: a string policy token, `reuse_dataset_if_exists`, `reuse_cache_if_exists`, or `force_redownload`.

The return is a `Dataset` or `IterableDataset` for a selected split, or a `DatasetDict` or `IterableDatasetDict` mapping split-name strings to those objects. Automatic split-name keys are `train` for training, `validation` for validation, and `test` for testing. Source naming forms include `data/<split>-<five-digit shard>-of-<five-digit count>.<extension>`, `<split>/<relative file>`, and `<split>.<extension>`. Wildcard file selections use `*` for a filename fragment. Reader-specific keyword arguments are given below.

Source-availability or access rejection is carried by `FileNotFoundError`; configuration or split-selection rejection by `ValueError`. Reader data-generation failure is carried by `velnora.exceptions.DatasetGenerationError`.

HTTP storage options expose `headers`, a mapping of header-name strings to string values; `Authorization` is the authentication header name.

Automatic file identification uses `.csv` and `.tsv` for delimited tables, `.json` and `.jsonl` for JSON records, and `.lance` for Lance dataset directories.

### csv

Reader name `csv` in `load_dataset` accepts the following shell. `delimiter: str`, `header: int | None`, `names: list[str]`, `features: Features`. Returned rows map column names to decoded values.

### json

Reader name `json` in `load_dataset` accepts the following shell. `field: str`, `features: Features`. Source formats are JSON Lines, a JSON array of row objects, or a document containing a named array. Returned rows are dictionaries.

### text

Reader name `text` in `load_dataset` accepts the following shell. `keep_linebreaks: bool`, `sample_by: str`. Sample-unit tokens are `paragraph` and `document`. Returned rows have `text: str`.

### arrow

Reader name `arrow` in `load_dataset` accepts the following shell. Input is an Arrow IPC stream; rows are decoded column/value dictionaries.

### parquet

Reader name `parquet` in `load_dataset` accepts the following shell. `columns: list[str]`, `filters`: condition syntax below. Input and exported table files use Parquet; decoded rows are column/value dictionaries.

### hdf5

Reader name `hdf5` in `load_dataset` accepts the following shell. Input is an HDF5 file; decoded rows use dictionaries for named fields and nested groups and lists for within-row arrays.

### lance

Reader name `lance` in `load_dataset` accepts the following shell. `columns: list[str]`. A source location can name a Lance dataset directory. Returned rows are column/value dictionaries.

### vortex

Reader name `vortex` in `load_dataset` accepts the following shell. `columns: list[str]`, `filters`: condition syntax below. Returned rows are column/value dictionaries. Filter rejection raises `ValueError` or `DatasetGenerationError`.

### iceberg

Reader name `iceberg` in `load_dataset` accepts the following shell. `catalog`: catalog object; `table`: table-identifier string or mapping from split names to table identifiers; `snapshot_id: int`; `columns: list[str]`; `filters: str` containing a row condition. Returned rows are column/value dictionaries; named tables return a split mapping. Source-configuration rejection raises `ValueError`.

### conll

Reader name `conll` in `load_dataset` accepts the following shell. `column_names: list[str]`, `delimiter: str`, `comment_prefix: str`, `skip_docstart: bool`. Rows map requested column names to token/annotation lists. The ordinary token column is named `tokens`. Rejected data is carried by `DatasetGenerationError`.

### fasta

Reader name `fasta` in `load_dataset` accepts the following shell. `columns: list[str]`. Read row fields are `id: str`, `description: str`, `sequence: str`, and `record`, a decoded `BioSequence` value.

### fastq

Reader name `fastq` in `load_dataset` accepts the following shell. `columns: list[str]`. Read row fields are `id: str`, `description: str`, `sequence: str`, `quality: str`, and `record`, a decoded `BioSequence` value. Malformed-record rejection raises `ValueError` or `DatasetGenerationError`.

### genbank

Reader name `genbank` in `load_dataset` accepts the following shell. Read row fields are `locus_name: str`, `accession: str`, `version: str`, `sequence: str`, `organism: str`, `record` (decoded `BioSequence`), and `features` (a list of annotation dictionaries). Each read annotation has `type: str`, `qualifiers: dict[str, list[str]]`, and `location` with `start: int`, `end: int`, and `strand: int`; coordinate fields are integers.

### tsfile

Reader name `tsfile` in `load_dataset` accepts the following shell. `table_name: str`, `columns: list[str]`, `start_time`, `end_time`, `timestamp_unit: str`, and `on_bad_files: str`. Time bounds take integers, `datetime.date`, or `datetime.datetime`. Unit tokens are `s`, `ms`, `us`, and `ns`. Bad-file policy tokens used here are `warn` and `skip`.

Rows have source tag-name keys carrying scalar device identifiers, `time` carrying a list of `datetime.datetime` values, and source measurement-name keys carrying lists of measurement values or `None`. Invalid configuration raises `ValueError`. Unreadable-input failure raises `ValueError`, `OSError`, `RuntimeError`, or `DatasetGenerationError`; duplicate-data failure raises `ValueError` or `DatasetGenerationError`.

Warning diagnostics are Python logging records reaching the `velnora` logger at `WARNING` level. 

### harbor

Reader name `harbor` in `load_dataset` accepts the following shell. `include_files: bool` and `strip_canary: bool`. Read row fields are `name: str` (task name), `instruction: str` (instruction text), `config: dict` (task configuration), `metadata: dict` (task metadata), `location: str` (task directory relative to the source root), and `files: list[str] | None` (task-relative file paths or an omitted listing).

Configuration failure raises `DatasetGenerationError`; unavailable task-source failure raises `DataFilesNotFoundError`.

### webdataset

Reader name `webdataset` in `load_dataset` accepts the following shell. Input is a TAR archive or list of TAR archives. A component name has the form `<sample identity>.<component type>`. Component-type names are the row keys: `txt` carries a decoded string, `json` a JSON-shaped value, and a media component key carries its corresponding media feature value. Rejected sample data raises `ValueError` or `DatasetGenerationError`.

### filters

The `filters` argument for `parquet` and `vortex` uses tuples `(<column name>, <operator>, <operand>)`. A list of tuples is a conjunction; a list of lists of tuples is a disjunction of conjunctions. Operator spellings are `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, and `not in`. Membership operands are value lists; other operands are scalar values.

### imagefolder

Reader name `imagefolder` in `load_dataset` accepts `data_dir` or `data_files`, `split`, and `drop_labels: bool`. Its media column is `image`, declared as `Image`. A directory-label column is named `label` and declared as `ClassLabel`. Annotation columns use the metadata field names.

Media filename extensions are `.png`, `.bmp`.

### audiofolder

Reader name `audiofolder` in `load_dataset` accepts `data_dir` and `split`. Its media column is `audio`, declared as `Audio`.

Media filename extensions are `.wav`.

### videofolder

Reader name `videofolder` in `load_dataset` accepts `data_dir` and `split`. Its media column is `video`, declared as `Video`.

Media filename extensions are `.mkv`.

### pdffolder

Reader name `pdffolder` in `load_dataset` accepts `data_dir` and `split`. Its media column is `pdf`, declared as `Pdf`.

Media filename extensions are `.pdf`.

### niftifolder

Reader name `niftifolder` in `load_dataset` accepts `data_dir` and `split`. Its media column is `nifti`, declared as `Nifti`.

Media filename extensions are `.nii`, `.nii.gz`.

### meshfolder

Reader name `meshfolder` in `load_dataset` accepts `data_dir` and `split`. Its media column is `mesh`, declared as `Mesh`.

Media filename extensions are `.ply`, `.stl`.

### pdb

Reader name `pdb` in `load_dataset` accepts `data_dir` or `data_files`, `split`, and `drop_labels: bool`. Its media column is `structure`, declared as `BioStructure`. A directory-label column is named `label` and declared as `ClassLabel`. Annotation columns use the metadata field names.

Media filename extensions are `.pdb`.

### mmcif

Reader name `mmcif` in `load_dataset` accepts `data_dir` or `data_files`, `split`, and `drop_labels: bool`. Its media column is `structure`, declared as `BioStructure`. A directory-label column is named `label` and declared as `ClassLabel`. Annotation columns use the metadata field names.

Media filename extensions are `.cif`.

### Media metadata fields

Media metadata reference fields are `file_name` for the reader's media column, `<name>_file_name` for a named media column, `file_names` for the plural media column, and `<name>_file_names` for a named list-valued media column. Single references are strings; multiple references are lists of strings. For an image reader the unnamed columns are `image` and `images`. Named references expose their `<name>` prefix as the output key. Other annotation keys carry their typed values. Metadata rejection raises `ValueError`.

## `README.md`

A dataset repository's `README.md` is UTF-8 Markdown with YAML front matter delimited by `---` lines. Read fields are:

- `configs`: a list of mappings with `config_name: str`, `default: bool`, and `data_files`.
- `data_files`: a file-selection string or a list of mappings with `split: str` and `path: str | list[str]`.
- `dataset_info`: one information mapping or a list of information mappings, each carrying `config_name: str`, `features`, and `splits`. `features` is a list of mappings with `name: str` and `dtype: str`. `splits` is a list of mappings with `name: str`, `num_bytes: int`, and `num_examples: int`.

Configuration data-file paths are relative to the repository or are URL references.

## `metadata.csv`

Media-directory metadata is named `metadata.csv` and uses UTF-8 CSV with a header row. Its row fields include media references and caller-named annotation fields.

## `metadata.jsonl`

Media-directory metadata is named `metadata.jsonl` and uses UTF-8 JSON Lines with one object per line. Its row fields include media references and caller-named annotation fields.

## `metadata.parquet`

Media-directory metadata is named `metadata.parquet` and uses a Parquet table. Its row fields include media references and caller-named annotation fields.

## `velnora.get_dataset_config_names`

`get_dataset_config_names(path)` takes a source-path string and returns a list of configuration-name strings.

## `velnora.get_dataset_default_config_name`

`get_dataset_default_config_name(path)` takes a source-path string and returns a configuration-name string or `None`.

## `velnora.get_dataset_infos`

`get_dataset_infos(path)` takes a source-path string and returns a dictionary of configuration-name strings to `DatasetInfo`.

## `velnora.get_dataset_config_info`

`get_dataset_config_info(path, config_name=...)` takes a source-path string and optional configuration-name string and returns a `DatasetInfo`.

## `velnora.get_dataset_split_names`

`get_dataset_split_names(path, config_name=...)` takes a source-path string and optional configuration-name string and returns a list of split-name strings.

## `velnora.ReadInstruction`

`ReadInstruction(split_name, from_=..., to=..., unit=..., rounding=...)` takes a split-name string, optional integer interval endpoints, a unit string, and an optional rounding-policy string. The percentage unit token is `%`; the equal-percent rounding token is `pct1_dropremainder`. It is accepted as `load_dataset`'s `split` argument.

String instructions use `<split>[<start>:<end>]`; either endpoint can be omitted and a percentage endpoint is written `<number>%`. Concatenated selections use `+` between instructions. A rejected instruction raises `ValueError`.

## `velnora.Image`

`Image(mode=..., decode=...)` is a feature declaration. `mode` is a string and `decode` a boolean. Pixel-array input is a NumPy array. Decoded image access exposes `size` as `(width, height)`, `mode` as a string, NumPy array conversion, and `tobytes()` for pixel bytes. Null is returned as `None`.

File-backed inputs take a path string, encoded bytes, or a dictionary `{"path": <string or None>, "bytes": <bytes or None>}`. Encoded access returns that `path`/`bytes` dictionary; a path-only representation has `bytes: None`. A media-input failure raises an `Exception`, at construction, row access, or decoded consumption.

`ImportError` signals an unavailable external decoding prerequisite.

## `velnora.Audio`

`Audio(sampling_rate=..., num_channels=..., decode=...)` is a feature declaration. `sampling_rate` and `num_channels` are integers and `decode` a boolean. Sample-array input is `{"array": <numeric array>, "sampling_rate": <integer>}`. A decoded value exposes `get_all_samples()`, returning an object with `data` (NumPy-convertible array in channel-by-sample order) and `sample_rate: int`.

File-backed inputs take a path string, encoded bytes, or a dictionary `{"path": <string or None>, "bytes": <bytes or None>}`. Encoded access returns that `path`/`bytes` dictionary; a path-only representation has `bytes: None`. A media-input failure raises an `Exception`, at construction, row access, or decoded consumption.

`ImportError` signals an unavailable external decoding prerequisite.

## `velnora.Video`

`Video(stream_index=..., decode=...)` is a feature declaration. `stream_index` is an integer and `decode` a boolean. A decoded value exposes `get_frame_at(index)` for an integer frame position; its result has `data` (NumPy-convertible pixel array in channel, height, width order) and `pts_seconds` (numeric presentation timestamp in seconds).

File-backed inputs take a path string, encoded bytes, or a dictionary `{"path": <string or None>, "bytes": <bytes or None>}`. Encoded access returns that `path`/`bytes` dictionary; a path-only representation has `bytes: None`. A media-input failure raises an `Exception`, at construction, row access, or decoded consumption.

`ImportError` signals an unavailable external decoding prerequisite.

## `velnora.Pdf`

`Pdf(decode=...)` is a feature declaration. `decode` is a boolean. A decoded value exposes `pages`, an ordered page sequence; each page has `extract_text()` returning a string. The document exposes `close()`.

File-backed inputs take a path string, encoded bytes, or a dictionary `{"path": <string or None>, "bytes": <bytes or None>}`. Encoded access returns that `path`/`bytes` dictionary; a path-only representation has `bytes: None`. A media-input failure raises an `Exception`, at construction, row access, or decoded consumption.

`ImportError` signals an unavailable external decoding prerequisite.

## `velnora.Nifti`

`Nifti(decode=...)` is a feature declaration. `decode` is a boolean. A decoded value exposes `get_fdata()` (NumPy-convertible voxel array), `affine` (NumPy-convertible spatial matrix), and `header.get_zooms()` (voxel-spacing sequence).

File-backed inputs take a path string, encoded bytes, or a dictionary `{"path": <string or None>, "bytes": <bytes or None>}`. Encoded access returns that `path`/`bytes` dictionary; a path-only representation has `bytes: None`. A media-input failure raises an `Exception`, at construction, row access, or decoded consumption.

`ImportError` signals an unavailable external decoding prerequisite.

## `velnora.Mesh`

`Mesh(decode=...)` is a feature declaration. `decode` is a boolean. A decoded value is a mesh exposing `vertices` and `faces` as NumPy-convertible coordinate and vertex-index arrays, or a scene exposing `geometry`, a mapping of names to such meshes.

File-backed inputs take a path string, encoded bytes, or a dictionary `{"path": <string or None>, "bytes": <bytes or None>}`. Encoded access returns that `path`/`bytes` dictionary; a path-only representation has `bytes: None`. A media-input failure raises an `Exception`, at construction, row access, or decoded consumption.

`ImportError` signals an unavailable external decoding prerequisite.

## `velnora.BioSequence`

`BioSequence(format=..., decode=...)` is a feature declaration. `format` is a format-name string; `decode` is a boolean. A decoded record exposes `id: str`, `seq` convertible to sequence text, `letter_annotations` with `phred_quality: list[int]`, `annotations` with `organism: str`, and `features`, a sequence of feature objects with `qualifiers: dict[str, list[str]]`. Qualifier keys retain the source annotation names.

File-backed inputs take a path string, encoded bytes, or a dictionary `{"path": <string or None>, "bytes": <bytes or None>}`. Encoded access returns that `path`/`bytes` dictionary; a path-only representation has `bytes: None`.

## `velnora.BioStructure`

`BioStructure(format=..., decode=...)` is a feature declaration. `format` is a format-name string; `decode` is a boolean. A decoded structure exposes `get_models()` and `get_atoms()`. Models expose `get_chains()` and `get_residues()`; chains have `id: str`; residues have `resname: str`; atoms have `id: str` and NumPy-convertible `coord`.

File-backed inputs take a path string, encoded bytes, or a dictionary `{"path": <string or None>, "bytes": <bytes or None>}`. Encoded access returns that `path`/`bytes` dictionary; a path-only representation has `bytes: None`.

`ImportError` signals an unavailable external decoding prerequisite.

## `velnora.arrow_dataset.DatasetTransformationNotAllowedError`

`velnora.arrow_dataset.DatasetTransformationNotAllowedError` is a Python exception class. Its raised form is the failure carrier; no message text is prescribed.

## `velnora.search.MissingIndex`

`velnora.search.MissingIndex` is a Python exception class. Its raised form is the failure carrier; no message text is prescribed.

## `velnora.exceptions.DatasetGenerationError`

`velnora.exceptions.DatasetGenerationError` is a Python exception class. Its raised form is the failure carrier; no message text is prescribed.

## `velnora.exceptions.DataFilesNotFoundError`

`velnora.exceptions.DataFilesNotFoundError` is a Python exception class. Its raised form is the failure carrier; no message text is prescribed.

## `velnora.download.DownloadConfig`

`DownloadConfig(cache_dir=...)` takes a cache directory string and returns a download-configuration object.

## `velnora.download.DownloadManager`

`DownloadManager(download_config=...)` takes a `DownloadConfig` object and returns a download manager.

## `velnora.download.DownloadManager.extract`

`DownloadManager.extract(path_or_paths)` takes a string path. The returned string path names the extracted file or extracted directory. Archive-relative member paths are used beneath an extracted directory.

`ImportError` signals an unavailable external extraction prerequisite.

## `velnora.Dataset.add_faiss_index`

`Dataset.add_faiss_index(column, index_name=..., metric_type=...)` accepts a column-name string, optional index-name string and optional metric identifier. `faiss.METRIC_INNER_PRODUCT` is the inner-product metric token.

## `velnora.Dataset.add_faiss_index_from_external_arrays`

`Dataset.add_faiss_index_from_external_arrays(external_arrays, index_name=..., metric_type=...)` accepts a NumPy vector matrix, index-name string and optional metric identifier. `faiss.METRIC_INNER_PRODUCT` is the inner-product metric token.

## `velnora.Dataset.add_elasticsearch_index`

`Dataset.add_elasticsearch_index(column, index_name=..., host=..., port=..., es_client=..., es_index_name=...)` accepts a text-column name, optional index-name string, host string, integer port, external service client and service index-name string. Prerequisite failure raises `ImportError`; service-connection failure raises `elasticsearch.exceptions.ConnectionError`.

## `velnora.Dataset.load_elasticsearch_index`

`Dataset.load_elasticsearch_index(index_name, es_index_name=..., es_client=...)` accepts an index-name string, service index-name string and service client.

## `velnora.Dataset.list_indexes`

`Dataset.list_indexes()` accepts no arguments. It returns a list of index-name strings.

## `velnora.Dataset.drop_index`

`Dataset.drop_index(index_name)` accepts an index-name string.

## `velnora.Dataset.save_faiss_index`

`Dataset.save_faiss_index(index_name, file)` accepts an index-name string and a file-path string. The file path names a serialized vector index.

## `velnora.Dataset.load_faiss_index`

`Dataset.load_faiss_index(index_name, file)` accepts an index-name string and a file-path string. Index-compatibility rejection raises `ValueError`.

## `velnora.Dataset.search`

`Dataset.search(index_name, query, k=...)` accepts an index-name string, NumPy query vector and optional integer result count. Its result exposes `scores: sequence[number]` and `indices: sequence[int]` (dataset row positions). A missing-index failure raises `velnora.search.MissingIndex`. A vector-dimension rejection raises `ValueError` or `AssertionError`.

## `velnora.Dataset.search_batch`

`Dataset.search_batch(index_name, queries, k=...)` accepts an index-name string, NumPy query matrix and optional integer result count. Its result exposes `total_scores` and `total_indices`, each a sequence of per-query sequences in query order. Entries are numeric scores and integer row positions.

## `velnora.Dataset.get_nearest_examples`

`Dataset.get_nearest_examples(index_name, query, k=...)` accepts an index-name string, NumPy query vector or text query string, and optional integer count. Its result exposes `scores: sequence[number]` and `examples: dict[str, sequence]`, a column mapping of retrieved values aligned with the scores. A missing-index failure raises `velnora.search.MissingIndex`.

## `velnora.Dataset.get_nearest_examples_batch`

`Dataset.get_nearest_examples_batch(index_name, queries, k=...)` accepts an index-name string, NumPy query matrix and optional integer count. Its result exposes `total_scores`, a sequence of score sequences, and `total_examples`, a sequence of column mappings, with one entry per query in query order.

## `velnora.Dataset.with_format`

`Dataset.with_format(type, columns=..., output_all_columns=...)` takes an access-representation string or `None`. Optional `columns` is a list of column-name strings and `output_all_columns` is a boolean. Rejected column selection raises `ValueError`. It returns a `Dataset`.

## `velnora.Dataset.set_format`

`Dataset.set_format(type, columns=..., output_all_columns=...)` takes an access-representation string or `None`. Optional `columns` is a list of column-name strings and `output_all_columns` is a boolean. Rejected column selection raises `ValueError`.

## `velnora.IterableDataset.with_format`

`IterableDataset.with_format(type)` takes an access-representation string or `None`. It returns an `IterableDataset`.

## `velnora.Dataset.reset_format`

`Dataset.reset_format()` sets ordinary access on that dataset object.

## `velnora.Dataset.set_transform`

`Dataset.set_transform(transform)` takes a callable receiving a batch column dictionary and returning a dictionary of derived column sequences. Row access exposes a scalar-value dictionary; batch access exposes a sequence-valued dictionary.

## `velnora.Dataset.with_transform`

`Dataset.with_transform(transform)` takes a callable receiving a batch column dictionary and returning a dictionary of derived column sequences. Row access exposes a scalar-value dictionary; batch access exposes a sequence-valued dictionary. It returns a `Dataset`.

## `velnora.Dataset.to_tf_dataset`

`Dataset.to_tf_dataset(columns=..., label_cols=..., batch_size=..., shuffle=..., collate_fn=..., prefetch=...)` takes input and label selections as strings or lists of strings, an integer batch size, boolean shuffle and prefetch switches, and an optional collation callable. Collation receives a list of row dictionaries and returns a dictionary of array-valued columns.

The result is a `tensorflow.data.Dataset`. With scalar input and label column selections its elements are `(inputs, labels)` tensor pairs; `as_numpy_iterator()` exposes array pairs with a leading batch dimension. Selection rejection raises `ValueError`.

## `velnora.Dataset.save_to_disk`

`Dataset.save_to_disk(dataset_path, storage_options=..., num_shards=...)` takes a string or path-like destination directory and optional storage-option dictionary. `num_shards` is an optional integer storage-part count. Attached-index save rejection raises `ValueError`; active-source overwrite rejection raises `PermissionError`. Remote access rejection can raise `ftplib.error_perm`.

## `velnora.DatasetDict.save_to_disk`

`DatasetDict.save_to_disk(dataset_dict_path)` takes a string or path-like destination directory.

## `velnora.load_from_disk`

`load_from_disk(dataset_path, storage_options=...)` takes a string or path-like local directory or remote URI and optional storage-option dictionary. It returns a `Dataset` or `DatasetDict`. Invalid saved-source rejection raises `FileNotFoundError`; remote authentication rejection can raise `ftplib.error_perm`. FTP storage options have `host: str`, `port: int`, `username: str`, `password: str`, and `timeout` in seconds.

## `velnora.Dataset.to_csv`

`Dataset.to_csv(path_or_buf, batch_size=..., storage_options=...)` takes a string or path-like output path, optional integer batch size, and optional remote storage-option dictionary. It writes a UTF-8 CSV file with a column-name header and record rows. Remote authentication rejection can raise `ftplib.error_perm`.

## `velnora.Dataset.to_json`

`Dataset.to_json(path_or_buf, batch_size=..., storage_options=...)` takes a string or path-like output path, optional integer batch size, and optional remote storage-option dictionary. It writes a UTF-8 JSON Lines file with one row object per line. Remote authentication rejection can raise `ftplib.error_perm`.

## `velnora.Dataset.to_parquet`

`Dataset.to_parquet(path_or_buf, batch_size=..., storage_options=...)` takes a string or path-like output path, optional integer batch size, and optional remote storage-option dictionary. It writes a Parquet table file. Remote authentication rejection can raise `ftplib.error_perm`.

## `velnora.Dataset.to_sql`

`Dataset.to_sql(name, con, batch_size=..., if_exists=...)` takes a table-name string, SQLite connection, optional integer batch size and optional conflict-policy string. Tokens used here are `replace` and `append`. The output is a SQL table whose columns use dataset column names. A table-conflict rejection raises `ValueError`.

## `velnora.Dataset.to_list`

`Dataset.to_list()` returns a list of row dictionaries.

## `velnora.Dataset.to_dict`

`Dataset.to_dict()` returns a dictionary `{<column>: [<value>, ...]}`.

## `velnora.Dataset.to_pandas`

`Dataset.to_pandas()` returns a `pandas.DataFrame` exposing `to_dict(orient="records")`.

## `velnora.Dataset.to_polars`

`Dataset.to_polars()` returns a `polars.DataFrame` exposing `to_dicts()`.

## `velnora.IterableDataset.to_csv`

`IterableDataset.to_csv(path_or_buf, batch_size=..., storage_options=...)` takes a string or path-like output path, optional integer batch size, and optional remote storage-option dictionary. It writes a UTF-8 CSV file with a column-name header and record rows. Remote authentication rejection can raise `ftplib.error_perm`.

## `velnora.IterableDataset.to_json`

`IterableDataset.to_json(path_or_buf, batch_size=..., storage_options=...)` takes a string or path-like output path, optional integer batch size, and optional remote storage-option dictionary. It writes a UTF-8 JSON Lines file with one row object per line. Remote authentication rejection can raise `ftplib.error_perm`.

## `velnora.IterableDataset.to_parquet`

`IterableDataset.to_parquet(path_or_buf, batch_size=..., storage_options=...)` takes a string or path-like output path, optional integer batch size, and optional remote storage-option dictionary. It writes a Parquet table file. Remote authentication rejection can raise `ftplib.error_perm`.

## `velnora.IterableDataset.to_sql`

`IterableDataset.to_sql(name, con, batch_size=..., if_exists=...)` takes a table-name string, SQLite connection, optional integer batch size and optional conflict-policy string. Tokens used here are `replace` and `append`. The output is a SQL table whose columns use dataset column names. A table-conflict rejection raises `ValueError`.

## `velnora.IterableDataset.to_list`

`IterableDataset.to_list()` returns a list of row dictionaries.

## `velnora.IterableDataset.to_dict`

`IterableDataset.to_dict()` returns a dictionary `{<column>: [<value>, ...]}`.

## `velnora.IterableDataset.to_pandas`

`IterableDataset.to_pandas()` returns a `pandas.DataFrame` exposing `to_dict(orient="records")`.

## `velnora.IterableDataset.to_polars`

`IterableDataset.to_polars()` returns a `polars.DataFrame` exposing `to_dicts()`.

## `velnora.Dataset.cache_files`

`Dataset.cache_files` is a list of dictionaries with `filename: str`, naming the active dataset files.

## `velnora.Dataset.cleanup_cache_files`

`Dataset.cleanup_cache_files()` returns an integer removal count.

## `velnora.from_dict`

Stated under `velnora.Dataset.from_dict`.

## `velnora.from_file`

Class method `Dataset.from_file(filename)` returns a `Dataset`. `filename` is a string path to an Arrow IPC stream file.

## `velnora.from_generator`

Class method `Dataset.from_generator(generator, features=..., cache_dir=...)` returns a `Dataset`. `generator` is a callable yielding row dictionaries; `features` is optional `Features` and `cache_dir` is an optional directory string.

## `velnora.from_list`

Stated under `velnora.Dataset.from_list`.

## `velnora.from_pandas`

Class method `Dataset.from_pandas(df)` returns a `Dataset`. `df` is a `pandas.DataFrame`.

## `velnora.from_polars`

Class method `Dataset.from_polars(df)` returns a `Dataset`. `df` is a `polars.DataFrame`.

## `velnora.from_sql`

Class method `Dataset.from_sql(sql, con, cache_dir=...)` returns a `Dataset`. `sql` is a table-name or SQL-query string. `con` is a database URI string or SQLAlchemy connection. `cache_dir` is an optional directory string.

## `ClassLabel.names_file`

The path passed as `ClassLabel(names_file=...)` names a UTF-8 text file containing one vocabulary name per line.

## `task.toml`

`task.toml` is the TOML configuration document in a task directory. It is exchanged as the `config` row dictionary. Task-name input is `[task].name`; task metadata is the `[metadata]` table.

## `instruction.md`

`instruction.md` is the UTF-8 Markdown instruction document in a task directory. The corresponding returned row field is `instruction: str`.

## `ArrowInvalid`

Stated under `velnora.Dataset.map`.

## `ArrowTypeError`

Stated under `velnora.Dataset.map`.

## `Array`

The Python import package is `velnora`, with source package file `src/velnora/__init__.py`. A source root mounted at `/app/src` contains `velnora/__init__.py` and must be importable as `velnora`.

Python API results are returned as objects. Calls leave `stdout` available to the calling application; diagnostic logging uses `stderr` and Python logging. CSV, JSON Lines, Markdown and vocabulary text exchanged here use UTF-8 (`utf-8`).

### Access representations

Access representation strings are `numpy`, `torch`, `tensorflow`, `jax`, `pandas`, `polars`, and `arrow`; ordinary Python access is named by `None`.

Batched ordinary access returns a dictionary of Python lists. Numerical and tensor representations return a dictionary of `numpy.ndarray`, `torch.Tensor`, `tensorflow.Tensor`, or `jax.Array`, respectively. Array shapes have the batch dimension followed by within-record dimensions. Row access returns the corresponding scalar or within-record array values. Table representations return `pandas.DataFrame`, `polars.DataFrame`, or `pyarrow.Table`, including one-row tables for a single-row request.

Numerical arrays and tensor values expose NumPy conversion and `shape`; PyTorch values expose `detach().cpu().numpy()` and `tolist()`, TensorFlow values expose `numpy()`, Pandas tables expose `columns` and column `tolist()`, Polars tables expose `to_dict(as_series=False)` and `to_dicts()`, and Arrow tables expose `to_pydict()`.

An unavailable representation is carried by `ValueError`; a successful independent table representation instead exposes the same `to_dict(as_series=False)` column mapping.

Feature declarations and `Features` mappings support equality comparison with `==` and copying with `copy.deepcopy`.

## `DataFrame`

Stated under `Array`.

## `Tensor`

Stated under `Array`.

## `Table`

Stated under `Array`.

## `velnora.Dataset.from_spark`

Class method `Dataset.from_spark(df, cache_dir=...)` accepts a `pyspark.sql.DataFrame` and an optional string cache-directory path. It returns a `Dataset` whose iteration yields row dictionaries `{<column name>: <value>}`.

## `velnora.IterableDataset.from_spark`

Class method `IterableDataset.from_spark(df, cache_dir=...)` accepts a `pyspark.sql.DataFrame` and an optional string cache-directory path. It returns a `IterableDataset` whose iteration yields row dictionaries `{<column name>: <value>}`.

## `ConnectionError`

Stated under `velnora.Dataset.add_elasticsearch_index`.
