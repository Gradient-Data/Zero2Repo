# Velnora — Full Product Requirements

Velnora makes data collections available for inspection, preparation, model training, evaluation, and sharing through local and remote file storage.

### FP-01: Typed data and semantic features

- Callers can describe columns containing nulls, booleans, signed and unsigned integers of 8, 16, 32, or 64 bits, floating point values of 16, 32, or 64 bits, decimals of 128 or 256 bits with a chosen precision and scale, text, binary values, dates, times, timestamps with optional time zones, and durations. For columns supplied as ordinary Python integers, unsigned 64-bit value preservation is guaranteed from zero through 2 to the power of 63 minus one. Within the supported input ranges, values representable in the declared type retain their meaning; values that cannot be converted are refused as incompatible data.

- Nested records, variable length lists, fixed length lists, and arrays with two through five dimensions preserve their nesting and element values. Arrays may have a variable first dimension while their remaining dimensions are fixed. Declared fixed list lengths must match the supplied lists.

- A categorical vocabulary assigns consecutive integer labels starting at zero in the supplied name order and supports conversion between names and labels. Callers can supply the vocabulary directly, read it from a text file, or supply only a class count, in which case the names are the decimal representations of the consecutive labels. Duplicate names, disagreement between the declared class count and vocabulary length, unknown nonnumeric names, and out-of-range label-to-name conversion are refused as invalid label definitions or values. An unknown label can be stored as negative one, but has no vocabulary name.

- Translation data associates text with a fixed language set, or associates one or more translations with each language present in a row. For variable-language translations, callers supply an explicit allowed language set and at least one translation per row. All supplied translations remain associated with their languages; a language outside that set is refused.

- A column explicitly declared to contain arbitrary JSON values preserves mixed scalar, list, and record values, including differing record keys, without adding absent keys. Ordinary typed records instead represent missing declared fields as null.

### FP-02: Dataset construction and inspection

- Callers can create a finite dataset from equal-length named columns, a sequence of records with a common set of keys, an existing table, or a finite record producer. The result preserves row order, column values, and supplied semantic features. Unequal column lengths are refused as inconsistent tabular data.

- Without an explicit schema, homogeneous scalar and nested inputs receive inferred column types. Whole numbers infer integer types that preserve their values, fractional numbers infer floating-point types, and booleans, text and binary content retain their respective kinds; all-null columns infer the null type. An explicit schema determines the requested types for empty or all-null columns. When constructing from named columns or a sequence of records, incompatible mixed types are refused unless the caller explicitly requests automatic JSON treatment.

- A finite dataset exposes its row count, column count, column names, and semantic features. Callers can retrieve an individual row, a column, a slice, or an ordered collection of row positions; repeated positions repeat the corresponding rows. Negative row positions count from the end. A row position outside the dataset or a nonexistent column is refused as an invalid selection.

- Row iteration preserves dataset order. Batch iteration returns consecutive groups of the requested positive size and, by default, includes a smaller final group; callers can choose to omit that final incomplete group.

- Named split collections retain each split as a separately accessible dataset. Inspection distinguishes the sizes and schemas of individual splits, and selecting a missing split fails as an unknown split.

- Dataset metadata retains a supplied description, citation, license, homepage, version, and split identity so callers can retrieve that information alongside the data.

- Callers can retrieve the distinct values of a scalar column in a finite dataset or separately for each split. Each distinct value occurs once, including null when present; selecting a missing column is refused.

### FP-03: Similarity and text search

- Callers can associate dataset rows with numeric vectors from a dataset column or an external aligned vector collection. Exact vector search returns the requested nearest rows with their scores. The default score is squared Euclidean distance, with smaller scores first; callers can instead choose inner-product similarity, with larger scores first. The requested count defaults to ten; nearest-row retrieval returns at most the number of indexed rows. Single queries and batches of queries preserve each query's result association.

- Callers can associate a text column with Elasticsearch and retrieve matching dataset rows with relevance scores for a text query. Returned row content corresponds to the matched indexed text, and the requested result count limits the number of returned matches. Existing Elasticsearch indexes can be reattached for querying.

- Named search indexes can be listed and removed. Vector indexes can be saved and reloaded against the corresponding dataset, preserving search results. A missing index, a vector query with the wrong dimensionality, or a loaded index whose number of entries differs from the dataset row count fails as an invalid search request or incompatible index.

- Attached search indexes restrict the ordinary finite-dataset operations: selecting rows, filtering, sorting, shuffling, partitioning, and saving are refused while an index remains attached. Removing the index allows those operations.

- Missing search support or an unavailable search service causes an explicit prerequisite or service failure.

### FP-04: Incremental dataset consumption

- Callers can consume records from a restartable producer or convert a finite dataset into an iterable dataset. Iteration preserves source order, and column iteration returns the corresponding values. A finite prefix remains obtainable from an unbounded producer without exhausting it; iterable data collections do not provide positional random access to rows.

- Taking a nonnegative number of records returns at most that many leading records. Skipping a nonnegative number omits that prefix and returns the remainder. Taking beyond the end returns all available records; skipping beyond the end returns none.

- Grouping records into batches produces consecutive groups of the requested positive size. The incomplete final group is retained by default and can be omitted explicitly. Repeating a finite iterable source yields successive complete passes; callers can request a finite repetition count or indefinite repetition.

- For an unchanged, unshuffled iterable source, callers can capture an iteration checkpoint and restore it on an equivalent dataset to continue with the next unread record. For a source converted from a finite collection, restoration uses the same row-consumption mode, or the same batch-consumption mode and batch size, as when the checkpoint was captured. Restartable producer sources also support changing between row and batch consumption on restoration.

- Seeded iterable shuffling preserves every record in a complete uninterrupted pass and reproduces its order for the same seed, epoch, source, and shuffle choices. Changing the epoch permits a new order. For a finite iterable source, callers can request full-source randomization in which each record has equal probability of occupying each output position.

- Finite and iterable data collections can produce a new dataset whose rows are groups of source records, with each column holding the corresponding ordered values. Fixed-size grouping retains the final incomplete group by default. Callers can omit it for iterable collections, and for finite collections when at least one complete group exists. Alternatively, grouping by one or more scalar columns combines each maximal consecutive run having equal values in all selected columns; equal values separated by a different run remain separate groups. Grouping requires a size or grouping columns. When grouping columns are supplied, their value changes determine group boundaries even if a size is also supplied.

### FP-05: Dataset discovery and source selection

- Callers can load a dataset from a local directory, explicit local files, or remote file locations. A source containing one supported data format can select its reader automatically; callers can also select the reader explicitly. File selection supports explicit collections and wildcard matching; only selected data files contribute records. Missing paths and selections containing no supported data files fail as unavailable data.

- Loading a local dataset directory honors a requested configuration. An unknown configuration is refused. Omitting a configuration selects the sole configuration, or the unique configuration designated as default by its declaration or the reserved identity “default”. Conflicting default designations are refused as ambiguous configuration. When several configurations exist without a default, the caller must choose one; the failure makes the available choices discoverable.

- Explicit mappings of files to split names determine split membership and override repository split metadata. Without an explicit mapping, declared repository mappings take precedence over automatic split recognition. Automatic recognition gives shard-numbered files carrying a split identity priority over split names in directories, and directory names priority over filenames. Each recognized convention selects only its matching files. Training recognizes train and training; validation recognizes validation, valid, val, and dev; testing recognizes test, testing, eval, and evaluation. If none of these conventions matches ordinary data files, all such files form a training split. Requesting one split returns that split, while omitting the selection returns the split collection.

- Callers can discover configuration names, the declared default configuration, split names, and available dataset information without requesting all records. The reported choices correspond to the selected local directory. When a local directory declares configurations, split mappings and schema for remote newline-delimited record files, discovery obtains that information without retrieving the complete contents of any record file; metadata and partial-content requests may occur.

- Remote file locations accept the caller's storage access options, including credentials for access-controlled HTTP sources. Valid credentials allow loading their records; absent or invalid credentials cause loading to fail as inaccessible data.

- Incremental loading of record-oriented local or remote files delivers records without requiring the complete dataset to be downloaded or converted first. Compressed JSONL and text sources can be consumed this way, including sources larger than the available local disk space. For remote newline-delimited JSON and gzip-compressed JSON or text sources of at least 256 MiB before compression, containing records of approximately 1.4 KiB, the first three records remain accessible when the caller-selected working filesystem has at most 128 MiB total capacity and at least 16 MiB initially free, and each encoded source exceeds its total capacity. Across all HTTP responses used to obtain that prefix, transferred response-body bytes must total at most one quarter of the encoded source size. Source preparation and server storage are outside the constrained filesystem.

### FP-06: Tabular and text data ingestion

- CSV and TSV loading recovers records and columns using the caller's delimiter, header, and column type choices. Defaults use commas for CSV and tabs for TSV, with the first row supplying column names. JSON loading accepts newline-delimited records, arrays of records, and records selected from a named field within a containing document. Malformed input or values incompatible with a requested schema cause a data-reading failure.

- Text loading produces one row per line by default and omits line terminators by default. Callers can instead retain line terminators or choose one row per nonempty paragraph separated by blank lines, or one row containing the entire document.

- Arrow, Parquet, HDF5, Lance, Vortex, and Apache Iceberg inputs can supply dataset records. HDF5 inputs use equally sized first dimensions as rows, preserve groups as nested records, and preserve the remaining array dimensions within each row; differing row counts in selected HDF5 columns are refused. Arrow stream inputs can be opened directly as data collections. Loading preserves the represented scalar, nested, and array values rather than returning the source files as opaque content.

- Parquet, Lance, Vortex, and Apache Iceberg loading can restrict the returned columns. Parquet, Vortex, and Apache Iceberg also accept row conditions. Parquet and Vortex conditions support equality, inequality, less-than and greater-than comparisons with or without equality, membership, and negative membership, including conditions on columns omitted from the result. Conjunctions require every condition and disjunctions require at least one condition. For Vortex, null column values satisfy none of these conditions; empty membership sets, empty condition groups and unsupported comparison operators are refused as invalid conditions. For Parquet, a null column value satisfies negative membership in a non-null set, but does not satisfy the other comparisons against non-null values.

- Apache Iceberg loading accepts a catalog and table selection, optionally associates different tables with named splits, and can select an earlier snapshot. Omitting the catalog or table is refused as missing source configuration. A snapshot selection returns that snapshot's records rather than the latest table contents.

- SQL loading returns rows from a specified table or the result of the supplied query through the selected database connection. In-memory row-indexed tables, expression-oriented tables, and distributed analytical tables can be converted into data collections while preserving their column values; distributed analytical tables can also be consumed as iterable data collections.

- CoNLL loading groups token lines into sentences separated by blank lines and produces aligned lists for the requested number of leading token and annotation columns. By default only the first column is retained and spaces or tabs separate fields. A final sentence does not require a trailing blank line. Missing trailing fields become empty text and surplus fields are omitted; an empty column selection is refused. Callers can choose the field separator and comment prefix; matching comment lines are omitted, and document boundary records are omitted by default and can be retained explicitly.

- Loading supported text and tabular files from ZIP archives or gzip, bzip2, and xz compressed files recovers their records. File selection and split assignment apply to the chosen archived or compressed data, rather than treating compressed bytes as records. Callers can also recover data files from TAR and 7z archives and LZ4 and Zstandard compressed files for use with a selected reader. Recovered file contents match the original uncompressed contents; unavailable decompression support causes an explicit prerequisite failure.

### FP-07: Multimodal values and decoding

- Image columns accept image file references, encoded image content, and image pixel arrays. Decoded access exposes the image pixels and dimensions and retains the source color mode by default; a requested color mode determines the returned image mode. Null image values remain null.

- Audio columns accept audio file references, encoded audio content, and sample arrays accompanied by their sampling rate. Decoded access exposes samples and their sampling rate. By default the source sampling rate and channel count are retained; callers can request another sampling rate and either mono or stereo output. Lossless normalized PCM samples, including audio recovered after saving, differ from the encoded source by at most 0.0001 per sample. Rate conversion preserves duration to within one output sample. For channels containing distinct sinusoidal frequencies no higher than one quarter of the lower sampling rate and source peak amplitudes at most 0.5, after excluding 5 milliseconds at each end, each retained channel component has greater than 0.28 and less than 1.3 times its source amplitude, and residual root-mean-square error outside the source frequency components is below 0.02 in normalized sample units. Stereo preserves the separate source channels; mono combines both source channels.

- Video columns accept video file references and encoded content and expose decoded frames with their timing. Exact frame seeking is the default: requesting a frame by position returns that frame. Callers can select a video stream within a file containing multiple streams. For losslessly encoded constant-rate video, decoded pixels match the requested source frame and presentation timestamps differ from source timestamps by less than one microsecond.

- PDF columns expose document pages and extractable text from PDF file references or encoded content. NIfTI columns expose voxel data and spatial metadata from uncompressed or compressed NIfTI files. Voxel values are retained exactly when represented without loss; spatial matrix elements and voxel spacings have relative error at most 0.0000001, with zero values retained exactly.

- Mesh columns accept GLB, PLY, and STL files and expose their geometry as a mesh or scene. Embedded mesh content accompanied by its format-bearing file reference is decoded with that format, preserving the represented vertices and faces. Triangle geometry retains face multiplicity and connectivity independently of vertex numbering and face winding, with absolute coordinate error at most 0.00001 in source coordinate units.

- For image, audio, video, PDF, NIfTI, and mesh columns, decoding is enabled by default. When callers explicitly disable decoding, access returns the stored file reference or encoded content instead of decoded media. Missing decoding support, unreadable media, or a media value containing neither content nor a file reference fails as an unavailable prerequisite or invalid media input.

### FP-08: Media collections and archive samples

- Directory collections of images, audio, video, PDF documents, NIfTI volumes, and meshes produce media data collections with one sample per discovered media file when no row metadata is supplied. Without metadata, media stored in classification subdirectories at a common depth receives categorical labels from the immediate parent directory names, ordered lexicographically. Labels are not inferred automatically when every file is in one directory or directory depths differ; callers can explicitly retain or omit directory labels. When row metadata is present, it determines the rows and annotations, and directory labels are not added even when explicitly requested.

- CSV, JSONL, or Parquet metadata can associate annotations with media files through references relative to the metadata file. Metadata rows can reference one media item, multiple named media items, or lists of media items; these references become media values while other annotations retain their values. Metadata without any media-reference column containing text references or lists of text references is refused as unusable media metadata. Metadata files with different formats or different declared column types across splits are refused as incompatible metadata.

- ZIP collections containing media and their metadata preserve the associations between each metadata row and its media. Explicit split selection and collection split conventions determine the resulting named splits.

- WebDataset TAR archives with the same component types across samples yield one sample for each consecutive group of entries sharing a sample identity. Different entry types belonging to that sample become associated values; text and JSON annotations retain their content, and image, audio, video, and mesh entries become media values. Repeating a component type within one sample is refused as duplicate sample data. Multiple archives contribute samples to the selected split in both finite and incremental loading.

### FP-09: Biological and time-series data collections

- FASTA and FASTQ loading produces one row per biological sequence record, preserving its identifier, description, and complete sequence across wrapped lines. FASTQ additionally preserves the quality text aligned with that sequence; unequal sequence and quality lengths are refused as malformed records. Callers can restrict the returned columns.

- GenBank loading preserves each record's sequence, identity, organism information, and feature annotations as dataset data. Feature annotations retain source order, feature kind, qualifiers, and interval endpoints in the source's one-based inclusive coordinate notation; forward and complementary strands are distinguishable. FASTA, FASTQ, and GenBank records can also be accessed as decoded biological records or retained as encoded record content when decoding is disabled. Decoded FASTQ records expose quality scores for the supplied quality characters in sequence order using the Sanger FASTQ encoding documented by Cock et al., The Sanger FASTQ file format for sequences with quality scores, Nucleic Acids Research 38(6), 2010, Table 1.

- PDB and mmCIF collections produce one row per structure file with optional directory labels and row metadata. Decoded structure access exposes the source models, chains, residues, atoms, and coordinates. Callers can retain encoded content without decoding; missing biological decoding support fails as an unavailable prerequisite when decoding is requested.

- TsFile table loading produces one row per device identified by its tag values. Each row contains aligned time and measurement sequences in ascending timestamp order. Records for the same device across files in a split are combined; duplicate timestamps for that device are refused as ambiguous time-series data.

- TsFile loading can select a table, measurement columns, and inclusive start and end times. By default it selects the first table in the first readable file and all its measurements, with no time restriction. Device identifiers and timestamps remain available when measurement columns are restricted. Integer time bounds count seconds, milliseconds, microseconds, or nanoseconds since the Unix epoch; the default unit is milliseconds. Dates and date-times are accepted, dates denote midnight, and timezone-free date-times are interpreted as UTC. An empty measurement selection or an unsupported timestamp unit is refused as invalid configuration.

- When TsFile measurement columns differ across files, the result contains their union and represents missing measurements as nulls at the corresponding timestamps. Requested measurement columns absent from all files contain nulls. By default an unreadable input causes failure; callers can explicitly choose omission with a warning or omission without a warning.

### FP-10: Agent evaluation task ingestion

- A Harbor repository containing paired task configuration and instruction documents yields one dataset row per task directory, including nested task directories. Each row preserves the top-level instruction, complete configuration, task metadata, and task location. Automatic discovery assigns these tasks to the testing split and prefers complete task document pairs over ordinary data files in the same source. Loading tasks does not execute agents, environment definitions, solutions, or verifiers.

- Harbor task rows include the files belonging to that task by default; callers can disable the file listing. Invalid task configuration fails as malformed configuration, and a source containing no complete task document pairs fails as unavailable task data.

- For Harbor instructions beginning at a nonblank line, default cleaning removes a leading consecutive sequence of single-line HTML comments or hash-prefixed comment lines containing the contamination marker text “canary”, together with immediately following blank lines. Subsequent instruction content remains intact. Instructions beginning with ordinary text or comments without that marker text retain their content from the first nonblank line onward. Callers can request the original instruction content instead, including leading blank lines.

### FP-11: Column and schema transformation

- Callers can rename, remove, or retain selected columns in finite and iterable data collections while preserving retained values and semantic features. For finite data collections, renaming to an empty name, assigning the same new name to multiple renamed columns, or requesting a nonexistent source column is refused as an invalid column operation. For iterable data collections, renaming a missing source column or renaming to an existing column name is refused.

- A finite dataset can acquire a new column with one value per row or append a new record. Existing rows retain their order and values. Appending a record may introduce new columns: earlier rows receive nulls in those columns, and columns absent from the appended record receive nulls in that row. A previously all-null column can acquire the appended value's inferred type. A new column with a conflicting name or a length different from the dataset is refused.

- Casting a column or complete schema changes the declared types and converts the corresponding values. Lossless numeric widening and conversion of numeric text to numeric values succeed; nonnumeric text requested as numeric data fails as incompatible data. For finite data collections, casting a complete schema with different column names is refused.

- Flattening nested records in a finite dataset exposes their leaf fields as independently addressable columns while preserving row associations, leaf values, and lists. By default it removes at most 15 nested record levels; deeper records remain nested. The result retains the origin of each leaf through its qualified column name.

- Callers can encode a scalar column as categorical labels with a recoverable vocabulary of its distinct values. Labels start at zero in lexicographic order of the values' text representations. Nulls remain null by default and can explicitly be included as a category. A caller-supplied mapping of every class name to distinct consecutive labels starting at zero can realign scalar categorical labels while retaining their class meanings and nulls; class names match without regard to letter case. Missing source columns and nonscalar category encoding are refused.

- Column and schema transformations return a new dataset, leaving the original dataset's values and schema unchanged. Applying a supported column transformation to a named split collection applies it separately to every split and retains the split names.

### FP-12: Record transformation and filtering

- Callers can transform finite data collections without attached search indexes or iterable data collections with a supplied operation over individual records by default, or consecutive batches when requested. Returned columns add to or replace columns of the source, while retained source columns keep their values. A transformation produces a separate dataset and does not replace the source dataset's contents.

- Callers can supply selected input columns and request each record's current position as additional transformation input. A column requested for removal is still available to the supplied operation; if the operation returns a column with that name, the returned column is retained.

- Batch transformation can change the number of records. All returned and retained columns in each output batch must have the same length; conflicting lengths fail as inconsistent tabular output. The default input batch contains at most 1,000 records, measured before transformation, and callers can choose a different positive batch size. The final incomplete input batch is processed by default and may explicitly be omitted.

- Filtering a finite dataset without attached search indexes, or an iterable dataset, retains precisely the records for which a caller-supplied predicate is true, in source order. Predicates can receive individual records, batches, selected columns, and record positions. A predicate accepting no records produces an empty result and retains the source schema when it is known.

- Asynchronous caller-supplied transformations and predicates are supported and produce results associated with the correct input records in source order. A raised error from a supplied operation causes the requested transformation to fail rather than return a successful truncated result.

- Supported transformations and predicates apply independently to each split of a split collection. Each resulting split keeps its identity and contains only the results derived from its own source records.

- Incremental transformation and filtering can deliver a finite prefix from an unbounded source without exhausting it. For deterministic operations on unchanged unshuffled sources, restoring a checkpoint continues after the last delivered transformed record, including when batches change the number of records.

- Finite record transformations enable automatic JSON treatment of mixed output types by default. Callers can disable this treatment; mixed values that cannot be represented by an ordinary inferred type then fail as incompatible output data.

- For 256 independent short records each requiring a 100,000-iteration SHA-256 password-based key derivation with a 32-byte output, the median elapsed time over three fresh runs with four externally available cores is at most 75 percent of that with one. Both runs disable reuse of earlier results and use identical data, operation and processing choices permitting four-way processing; timing includes materializing all transformed records, excludes imports and source construction, and alternates resource-limit order. Output values and row order remain unchanged. At least four otherwise idle cores and a CPU quota permitting four cores are required.

### FP-13: Row selection, ordering, and partitioning

- Callers can create a finite dataset from an ordered selection of nonnegative row positions in a dataset without attached search indexes, including repeated positions and an empty selection. For a nonempty dataset they can take a nonnegative prefix no longer than the dataset, or skip a nonnegative prefix shorter than the dataset. These operations preserve the selected records and their features. On nonempty input, explicit positions at or beyond the row count and a requested leading prefix longer than the dataset fail as an invalid selection.

- Sorting a finite dataset without attached search indexes by one or more scalar columns orders rows by those columns in the supplied priority order, with ascending or descending direction chosen for each. The default is ascending order with null values last; callers can instead place null values first. A missing sort column or a direction list of the wrong length is refused as an invalid sort request.

- Shuffling a finite dataset without attached search indexes returns a random permutation of all rows without changing the rows themselves. Every row has equal probability of occupying any output position. The same source and seed reproduce the same permutation.

- Training and test partitions of a finite dataset without attached search indexes can be requested by row counts or fractions. A fractional test size rounds up to a whole row; a fractional training size rounds down. An omitted size uses the remaining rows, and omitting both sizes allocates one quarter of the rows to testing. When both sizes are supplied and their total is smaller than the source, the remaining rows are omitted. The two partitions do not overlap. Shuffling is enabled by default and is reproducible with a seed; without shuffling, training rows precede test rows in source order.

- For nonempty input, explicit partition counts must be positive and smaller than the source size, and fractions must be strictly between zero and one. Combined requested counts exceeding the source, two fractions summing to more than one, or sizes leaving no training rows are refused. Empty input produces empty training and test partitions.

- Stratified partitioning accepts a categorical label column. For each class, its training count differs by less than one row from its source proportion multiplied by the training partition size, and its testing count differs by less than two rows from its source proportion multiplied by the testing partition size. When those proportional counts are integral for both partitions, they are preserved exactly. Stratification without shuffling, with a noncategorical column, with fewer than two records in any class, or with a partition smaller than the number of classes is refused.

- Sharding a nonempty finite dataset without attached search indexes produces a selected partition from a caller-chosen positive number of partitions no greater than the source row count. By default partitions are contiguous, differ in size by at most one row, and assign the extra rows to earlier partitions. Interleaved partitioning instead assigns successive rows cyclically across the partitions. An index outside the partition range is refused.

- Repeating a finite dataset a nonnegative whole number of times yields that many consecutive copies in source order. Indefinite repetition is refused for finite data collections.

- Loading a finite split can select absolute intervals with endpoints within the split, or percentage intervals, including boundaries counted from the end, and concatenate selected split intervals in the requested order. Intervals include the starting row and exclude the ending row; an omitted endpoint denotes the corresponding end of the split. Percentage boundaries round to the nearest whole row by default, with ties to the nearest even integer. An alternative equal-percent mode uses whole one-percent portions and drops the remainder; it is refused for splits containing fewer than 100 records. Unknown splits and percentage boundaries outside negative 100 through positive 100 percent are refused.

### FP-14: Dataset composition

- Vertical concatenation appends rows in input dataset order and retains each input's row order. Columns absent from an input are filled with nulls. Shared fields require the same semantic types and categorical vocabularies, ignoring record-field order; a null-typed field can adopt the corresponding non-null type from another input. This rule also applies inside nested records and lists of null values. The inputs must be either all finite data collections or all iterable data collections. An empty collection, mixed access models, or incompatible shared features is refused.

- Horizontal concatenation combines columns by row position. Finite inputs must have equal row counts. Iterable inputs continue until every input is exhausted and fill missing values from exhausted inputs with nulls. Duplicate column names are refused.

- Interleaving combines nonempty sources by taking records in turn from each source by default, preserving order within each source. With one positive source probability per source summing to one, each source choice follows the supplied categorical distribution, and a fixed seed reproduces the choices for unchanged inputs. The source data collections must share an access model and compatible features. An empty source collection or mixed access models is refused.

- Interleaving supports three stopping behaviors: stop at the first source exhaustion, restart exhausted sources until every source has been exhausted at least once, or exhaust all sources without repeating records. The first behavior is the default. For finite inputs without probabilities, the first behavior emits as many complete rounds as the shortest source has rows, and the repeating behavior emits as many complete rounds as the longest source has rows. For iterable inputs and for probability-weighted finite inputs, these two behaviors end immediately after the record that meets the selected exhaustion condition. In the no-repetition behavior, exhausted sources cease contributing and the probabilities of the remaining sources retain their relative proportions. An unrecognized stopping behavior is refused.

- For weighted finite interleaving in the first-exhaustion mode, a source with zero probability contributes no records and does not affect termination, including when that source is empty. In the repeating all-exhausted mode, any zero-probability source is refused as an unreachable exhaustion condition. In either of these modes, an empty source with positive probability is refused as an invalid interleaving source.

### FP-15: Framework-ready access

- Dataset access returns ordinary language values by default. Callers can request numerical arrays, dynamic-graph training tensors, graph-based training tensors, differentiable accelerator arrays, row-indexed tables, expression-oriented tables, or columnar interchange tables for compatible data. Returned numeric values, row associations, and fixed multidimensional shapes correspond to the stored data. Selecting an unavailable representation fails as a missing prerequisite.

- Formatting can apply only to selected columns, with other columns either omitted or retained in their ordinary form as requested. Callers can apply formatting to an existing dataset or obtain a separately formatted dataset. Resetting formatting restores ordinary access without changing stored values; nonexistent selected columns are refused.

- A custom access transformation replaces the ordinary formatting operation and derives returned values from requested records. Repeated access invokes the custom transformation again, allowing changing augmentations while stored records remain unchanged. Removing the transformation restores ordinary values.

- A finite dataset can supply a graph-based framework training input with selected input and label columns, a requested batch size, optional shuffling, and caller-supplied collation. The collation result determines the contents of each delivered batch. Missing input or label columns and duplicate selected columns are refused.

- Finite and iterable data collections can be consumed by dynamic-graph framework data loaders, delivering the same records in the order selected by the dataset and loader. Iterable access can return the supported array, tensor, and table representations without first consuming the complete source.

### FP-16: Distributed iterable consumption

- Iterable data collections support assigning whole source shards across nodes or assigning successive examples cyclically across nodes. Nodes have consecutive positions starting at zero; whole-shard assignment distributes successive source shards cyclically in node order. Automatic assignment is the default and uses whole shards when the shard count is divisible by the node count and examples otherwise. Explicit whole-shard assignment requires at least one shard per node; insufficient shards fail as an invalid distribution request. An unknown assignment policy is refused.

- Iterable data collections can expose a selected subset of their source shards. By default the selections divide the ordered source shards into consecutive portions, so concatenating the selections in partition-index order recovers the source order. Partitioning into as many portions as source shards lets each index select its corresponding source shard. Repartitioning a Parquet iterable dataset can expose row groups as independently assignable portions without changing its complete record sequence. Nonnegative partition indices at or above the requested partition count are refused.

- With a common source order and seed across nodes, complete uninterrupted distributed iteration assigns each source record to one node. Within a dynamic-graph framework data loader, multiple workers receive distinct whole source shards rather than each returning the entire source. Interleaved inputs assign corresponding source-shard portions to the same worker. For interleaved inputs, each node or worker applies its stopping condition to its own assigned portions.

### FP-17: Persistence and export

- Callers can save a finite dataset or named split collection without attached search indexes and reload it in a fresh session. Reloading preserves current logical row order, values, semantic features, split names, and descriptive metadata. A missing location or a location that does not contain a saved dataset fails as an invalid saved-dataset source.

- Saved image and audio data collections remain decodable after the original local media files are removed. Saving over a dataset's own active source location is refused to prevent destroying the data being saved.

- Finite and iterable data collections can export their records as CSV, JSON, Parquet, or SQL table contents, and as ordinary records, named columns, row-indexed tables, or expression-oriented tables. Export preserves values representable by the chosen target; sequential record and file outputs retain the logical row sequence. SQL export refuses an existing table by default; callers can instead choose to replace it or append to it.

- Saving and loading individual finite data collections can use remote storage locations with caller-supplied access options. Successfully saved data can be reloaded from the selected location; storage access failures are surfaced as failures rather than a successful local-only result.

- On-disk finite data collections support reading selected rows within a bounded resident-memory budget. For a single storage shard containing a 64-bit integer and an 8192-byte binary value per row, opening the dataset and reading four rows each from the beginning, middle and end must remain within a 512 MiB externally sampled resident-memory budget at both 32,000 and 256,000 rows. Preparation is excluded. In three independent fresh reader sessions at each size, the median peak resident-memory increase over the post-import baseline at the larger size is at most three times that at the smaller size plus 24 MiB. With the same single-shard and slice conditions, a 64-bit integer and eight-byte binary value per row at 1,000,000 and 8,000,000 rows has median anonymous resident-memory increase after opening and reading at most three times the smaller-size increase plus 16 MiB. These measurements use Linux process resident-memory reports, with total resident memory sampled approximately every two milliseconds and at operation completion, and anonymous resident memory read immediately before and after the operations.

### FP-18: Reuse and intermediate-file cleanup

- Loading a previously obtained remote source again does not repeat a complete source-content retrieval by default. Existence and metadata requests may still occur, including requests closed before the complete response body is consumed. Callers can also select previously obtained source content explicitly or request fresh source retrieval. When a remote source changes at the same location without a change in its advertised length or modification information, default loading and explicit selection of previously obtained source content return the previously obtained records without another complete retrieval. When remote source contents change at the same location, explicit fresh retrieval returns the changed records rather than the previously obtained records. For an already-local newline-delimited source with 400,000 records, each containing a 64-bit integer and 256 characters of ASCII text, loading the unchanged source a second time in a fresh session takes at most half the time of the first load. Measure three first/second pairs with a separate initially empty result location per pair, identical source and options within each pair, and compare the medians. Measure from load invocation until its finite result is available; source creation and row inspection are outside the interval.

- For a saved finite dataset and a deterministic transformation with unchanged inputs and options, repeating the transformation reuses the previous result without invoking the caller's operation again by default. Changing the transformation or its meaningful inputs produces the corresponding new result. Explicitly disabling result reuse causes the operation to run again.

- Callers can remove unused intermediate dataset files from the chosen dataset directory while retaining files used by the current dataset. Cleanup reports how many files were removed, distinguishing no removed files from a nonzero removal, and the current dataset remains readable.

### FP-19: Remote file publication

- File exports can target remote storage locations with caller-supplied access options. Successful publication places the exported file at the selected remote location, where an independent storage client can retrieve it. Storage access failures are surfaced as failures rather than a successful local-only result.
