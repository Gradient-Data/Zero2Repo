# Velnora Product Requirements

Velnora provides compressed, chunked, multidimensional arrays and hierarchical groups. Its accompanying tools support metadata documents, composable selections, and access to stored data over HTTP.

### FP-01: Metadata document validation and exchange

- Callers can read and produce standalone array, group, and consolidated metadata documents for format 2 and format 3, and standalone attribute documents for format 2. Format 3 attributes are embedded in the node document. A document round trip preserves the represented node properties, attributes, and descendant metadata without requiring access to array contents.

- Strict document validation refuses missing required information, incorrect value types, incorrect format or node-kind declarations, negative dimension lengths, and disagreement between the number of dimensions and the number of dimension names. Validation identifies the offending location and distinguishes missing information, unknown information, invalid types, invalid values, and invalid JSON.

- Metadata validation accepts zero-length dimensions and scalar arrays. For format 2 arrays, the number of chunk dimensions must equal the number of array dimensions; for regular format 3 grids, chunk lengths must be nonnegative, a zero chunk length is accepted only along an empty array dimension, and the ranks must agree.

- Callers can validate format 3 data types, chunk grids, chunk key encodings, codecs, and storage transformers against a chosen collection of definitions, including caller-supplied definitions. When definitions of the same kind claim the same name, the last supplied definition takes precedence. Claimed names are checked against their definitions; unclaimed names remain distinguishable as outside that collection rather than being declared valid implementations or rejected solely for being unknown.

- For recognized format 3 definitions, validation checks fill values against the declared data type and grids against the array shape. It refuses encoding configurations that apply an array transformation after conversion to bytes, omit conversion to bytes, or convert from arrays to bytes more than once. Byte serialization of multibyte values requires an explicit byte order and refuses variable-length values. Axis transposition must permute all current chunk axes. Shard inner shapes must have the shard rank, have positive lengths, and divide every corresponding shard length; inner data encodings obey the same compatibility rules, and index encodings must have a determinable encoded size. Violations are reported at the relevant nested location. A later encoding is not refused for a type or rank conflict that depends on the unknown output of an earlier unrecognized encoding.

- Metadata can be exchanged as documents or as collections of stored metadata bytes. Malformed JSON and missing required metadata documents are refused. Returned editable documents do not share nested mutable values with the metadata representation from which they were exported.

- Non-finite numeric attribute values survive stored-metadata round trips. Non-finite JSON numbers outside node attribute values, including within unknown extra members and descendant metadata, are refused; this restriction does not prohibit the defined representations of non-finite floating-point fill values.

- Metadata embedded in a caller's validation model receives the same strict document checks as standalone metadata, returns the same represented metadata on success, and can be exported again. Generated document schemas describe individual field constraints; cross-field rank agreement remains enforced by document validation.

- The default definition collection recognizes Boolean values; signed and unsigned integers of 8, 16, 32, and 64 bits; floating-point values of 16, 32, and 64 bits; complex values of 64 and 128 bits; fixed-width raw bits; variable-length text and bytes; date-time and time-delta values; and records. It recognizes regular and rectilinear grids, format-3 and format-2-compatible chunk addressing, and Blosc, byte serialization, CRC32C, Gzip, indexed sharding, axis transposition, Zstandard, scale-and-offset, and numeric-value-conversion encodings. No storage transformer is predefined. A caller can instead select the collection without the variable-length, temporal, record, rectilinear, Zstandard, scale-and-offset, and numeric-value-conversion extensions.

- For recognized compression definitions, Gzip and Blosc require declared compression levels, which must be integers from 0 through 9, and Zstandard requires a declared integer compression level from -131072 through 22. Blosc requires an algorithm, shuffle choice, and block size. It accepts LZ4, high-compression LZ4, BloscLZ, Snappy, Zlib, and Zstandard, with no shuffle, byte shuffle, or bit shuffle. Its block size must be nonnegative; either shuffle requires a positive element byte size, while no shuffle ignores that size. Configuration members not declared by a recognized definition are refused as unknown information.

- Recognized integer fill values must fit the declared signedness and width. Raw-bit widths must be positive multiples of eight and their fill values must have that width. Temporal scales must be integers from 1 through 2147483647; temporal fill values must be signed 64-bit counts or missing-time values. A record must contain at least one field with nonempty, distinct names and fixed-size field types; its fill value must supply exactly those fields with values accepted by their respective types. Rectilinear grids require one size description per array dimension. A uniform size repeats until the dimension is covered; an explicit sequence supplies successive sizes and may repeat a size a specified number of times. Sizes and repetition counts must be positive, and explicit sequences must cover their dimension, allowing excess extent. An empty sequence is accepted for an empty dimension.

- Unknown top-level format 2 array metadata members with valid JSON values are accepted and ignored; format 2 group metadata refuses unknown members as invalid values. Unknown top-level format 3 metadata members survive exchange. For format 3, callers can distinguish unknown members explicitly declared optional from those requiring understanding; all unknown members without an explicit optional declaration require understanding. Supplying extra members that replace a standard metadata member is refused as conflicting input. This distinction does not by itself reject an otherwise structurally valid document.

- An array document requires its format, shape, data type, fill value, and chunk organization. Format 2 additionally requires its storage order, filter sequence, and compressor choice, including explicit choices of none. Format 3 additionally requires its array node kind, chunk addressing choice, and encoding sequence. Group documents require the format and, for format 3, the group node kind. Attributes, dimension names, and storage transformers are optional. Absent attributes contain no user entries. Format 2 metadata exchange preserves the distinction between an absent attribute document and an explicitly empty one. Integer dimensions must be integers rather than Boolean or floating-point values; dimension names must be text or unnamed positions.

- Format 3 data-type, chunk-grid, chunk-addressing, encoding, and storage-transformer declarations cannot be declared ignorable, because each determines interpretation of the stored data. Such declarations are refused as invalid values even if their names are outside the selected definition collection. Consolidated format 3 metadata instead must be declared optional.

- Callers can normalize recognized format 3 extension declarations while preserving their represented meaning. Repeating normalization leaves the result unchanged. Declarations outside the selected definition collection retain their original information; invalid recognized declarations instead return the relevant validation problems without a successful normalized declaration.

- Metadata-only validation of floating-point fills accepts finite numeric values without requiring that they fit the declared floating-point width. Complex fills supply real and imaginary components, each accepted by the corresponding real floating-point type. Boolean fills require Boolean values; text fills require text; byte fills contain byte values from zero through 255. Temporal definitions accept years, months, weeks, days, hours, minutes, seconds, milliseconds, microseconds, nanoseconds, picoseconds, femtoseconds, attoseconds, and unspecified units.

### FP-02: Data types and scalar values

- Arrays support Boolean values; signed and unsigned integers of 8, 16, 32, and 64 bits; floating-point values of 16, 32, and 64 bits; complex values of 64 and 128 bits; fixed-length UTF-32 text; variable-length UTF-8 text; fixed-length null-terminated bytes; fixed-length raw bytes; variable-length bytes; 64-bit date-time and time-delta values; and structured records with named fields, including nested records.

- Callers can translate a supported native data type to its array-format metadata description and back, and translate representable scalar values to metadata and back for either format. Type width, signedness, text or byte length, temporal unit and scale, and record field names and order remain meaningful after conversion. Format 2 preserves applicable byte order; format 3 obtains stored byte order from the encoding configuration.

- A plain object data type with no unambiguous text or byte interpretation is refused as ambiguous. Arbitrary object references cannot be persisted as array elements; callers can explicitly select text interpretation to persist supplied objects as text. Native types with no registered interpretation or more than one registered interpretation are refused; these refusals need not have distinct failure categories.

- Structured records preserve field values when stored from aligned or padded native records. Field titles and subarray fields, including those nested in records, are refused as unsupported.

- The default scalar is false for Boolean data, zero for numeric data, a missing-time value for temporal data, empty text or bytes for variable-length data, and zero-filled storage for fixed-length text and bytes. Structured defaults are zero-valued numeric and Boolean fields and zero-filled fixed-size text and byte fields, recursively within nested records; temporal fields in records have zero tick counts. A requested fill value that cannot be represented by its data type is refused as incompatible.

- Callers can register additional data types and use their native-type interpretation and metadata and scalar conversions. Registered types are usable in arrays when their required encodings are available; unresolved metadata type names are refused as unsupported.

- Temporal values support years, months, weeks, days, hours, minutes, seconds, milliseconds, microseconds, nanoseconds, picoseconds, femtoseconds, attoseconds, and unspecified units, with an integer count from 1 through 2147483647 units per tick. Counts outside that range are refused as invalid temporal scales. Conversion preserves missing-time values as missing rather than converting them to ordinary counts.

### FP-03: Storage access and persistence

- Callers can keep array data in memory, local filesystem directories, Zip archives, remote filesystems, and object stores. Local and Zip data remain available after the original storage handle is closed and a new handle is opened. Remote filesystem and object-store access supports compatible services runnable locally on the offline Linux host, including HTTP resources and S3-compatible endpoints. Access uses the caller-configured endpoint, storage location and applicable local-service connection options.

- A store exposes complete values and requested byte intervals, existence, value sizes, and listing of keys, prefixes, and immediate directory contents. A single read of an absent key reports absence; an empty stored value remains distinguishable from absence. A forward byte interval starts at a nonnegative offset and excludes its stop offset; an open-ended interval continues to the end. A positive suffix length requests the final bytes up to that length. Reads of existing values clip requested intervals to the available bytes. A batch of reads returns one result per request in the supplied request order. This batch guarantee applies to local directory storage when all requested keys exist; memory and Zip storage also return absence for individual missing keys within a batch.

- Memory and local-directory storage access is writable by default. Writable stores support inserting and replacing complete values. Stores advertising deletion support also support removing keys and directory subtrees. Mutations through a read-only view are refused as read-only violations; creating such a view does not change the access mode of another view of the same storage.

- Zip archives support creation, reopening, and reading through an open binary file. Deletion and operations requiring deletion are refused as unsupported on Zip storage. The caller must keep a supplied binary file open for the duration of archive access.

- Callers can use a custom store with the same observable read, write, range, and listing capabilities. Operations requiring a capability the store does not provide are refused as unsupported, and storage failures remain visible to the caller.

### FP-04: Reusable stored reads

- A caller can supply a source store and separate storage for reusing previously read values. Reuse storage must support deletion; storage without deletion support is refused as incompatible. Reading a previously unseen key returns the source value. A successful read of stored bytes whose result fits any configured byte budget makes that result reusable until expiry, invalidation, clearing, or space is needed for subsequent reads or writes; repeating a read while its value remains retained and unexpired returns that value without another source read. A finite age is measured in elapsed seconds since that value was stored for reuse; after expiry, a read observes the current source value. The default permits reuse without expiration.

- Callers can set a byte budget for values available for reuse. For sequential reads of unchanged source data into initially empty reuse storage, with complete values individually fitting within the budget, the sum of payload byte lengths available for reuse across complete-value and byte-range reads stays within that budget. A requested byte-range value larger than the budget is still readable but is not retained. The default has no byte budget; removing an explicitly supplied limit restores unlimited retention. Clearing retained data preserves source data and makes later reads obtain source values again.

- Writes through this storage access update the source and, by default, the reusable value. Callers can disable retaining written values. Replacing or deleting a key invalidates previously retained byte ranges for that key, so subsequent reads do not return the old ranges. Deletion removes the source value as well.

- Reading a bounded interval or suffix returns the same bytes as the corresponding source read. Reuse of one interval does not substitute it for a different interval or for the complete value. Read-only access refuses mutations of the source.

- Under the sequential-read workload with expiration disabled, when retaining another fitting value requires space, retained results with the oldest last access lose reuse eligibility first. Accessing a retained result makes it more recent. Complete-value results and individual byte-range results compete for the same budget.

### FP-05: Encoding, compression, and integrity

- Callers can select uncompressed storage or lossless compression using Blosc, Zstandard, or Gzip. Writing and reopening an array preserves its values and selected encoding. Default compression is Zstandard for both formats. With the default settings of Blosc, Zstandard, and Gzip, fixed-width numeric chunks containing one repeated non-fill value and at least 65536 uncompressed bytes occupy fewer stored payload bytes than their uncompressed equivalents.

- Format 3 permits an ordered sequence of array transformations, one conversion from arrays to bytes, and subsequent byte transformations. Invalid ordering, absence of an array-to-byte conversion, multiple such conversions, and incompatible data-type or dimensional requirements are refused as incompatible encodings. Format 2 accepts an ordered filter sequence and at most one compressor.

- Numeric byte serialization accepts little-endian and big-endian storage. Text and byte serialization preserve variable-length elements. Stored element order follows the caller's axis permutation, while reading preserves the logical dimensions and values; an axis order that is not a permutation of the chunk axes is refused.

- A caller can enable checksum integrity protection for stored encoded data. CRC32C uses the checksum calculation in RFC 3720, Appendix B.4, on the protected encoded bytes in their stored order. Unchanged protected data is readable; a payload whose checksum does not match its contents is refused as corrupt data.

- For floating-point transformations and integer transformations whose mathematical intermediate and final values are representable in the declared type, elementwise scale-and-offset encoding and decoding follow the published scale_offset codec specification at revision 4da7b37a84f76e660902f6d3de3eaef0e0febae6, operating on the caller's array values and fill value with the caller's offset and scale in the declared numeric data type. Format 2 scale-and-offset filters follow the legacy codec section of that revision using the caller's array values, offset, scale, and numeric data type. Only signed integers, unsigned integers, and real floating-point array types are accepted. Zero scale, scale or offset values not representable by the declared type, and nonintegral integer decoding results are refused as incompatible numeric transformations. For integer types up to 32 bits, a final result outside the declared type is refused. For unsigned 64-bit arrays, final results outside the declared type are refused.

- Elementwise numeric conversion during encoding and decoding follows the Procedure, rounding, out-of-range, and scalar-mapping rules of the published cast_value codec specification at revision 4da7b37a84f76e660902f6d3de3eaef0e0febae6 for the caller's source values, source and target numeric types, rounding choice, out-of-range choice, and separate encoding and decoding scalar mappings whose input values are distinct within each mapping. Source and target types are limited to signed integers, unsigned integers, and real floating-point types. Missing conversion support is reported as an unavailable dependency.

- Callers can supply registered additional encodings for compression, checksums, numeric transformation, and precision reduction. With the corresponding encoding support installed, additional checksum protection includes CRC32 calculated according to RFC 1952, section 2.3.1, on the protected encoded bytes in their stored order. Additional lossless compression choices include LZ4, Zlib, BZ2, and LZMA; writing and reopening preserves the input values. Reopening uses the stored encoding configuration. An encoding with no available implementation is refused as unknown and identifies the unresolved encoding; registering an implementation makes data using that encoding accessible.

- For nonempty format 3 integer or real floating-point chunks whose first value and adjacent differences are exactly representable in both encoded and decoded types, and whose reconstructed values are exactly representable in the decoded type, difference encoding retains the first element and replaces each later element by its difference from the preceding input element, in row-major coordinate order within each chunk. Callers can choose another encoded numeric type subject to those representability conditions; decoding restores the original values and array shape.

- Binary precision reduction accepts floating-point data of 16, 32, and 64 bits. The retained fraction-bit count is an integer from zero through 10, 23, or 52 respectively; negative counts and counts exceeding the corresponding width are refused as invalid precision. For zero or normal inputs whose rounded outputs remain zero or normal and finite, results round to the nearest value with that retained precision, with ties to an even retained significand. Other data types are refused as incompatible.

- Boolean packing preserves every element and the array shape after reopening, and refuses non-Boolean data as incompatible. For a chunk containing at least eight Boolean elements, its packed payload occupies fewer bytes than byte-per-element serialization of the same chunk, measured before any subsequent compression.

- Decimal-guided precision reduction accepts floating-point data and a caller-selected integer number of decimal places. It rounds each element to the nearest multiple of the greatest power-of-two increment no greater than one unit at that decimal precision, with ties to even. Negative decimal-place counts select coarser increments. This guarantee applies when the increment, its reciprocal, scaled values, and rounded values are finite and representable in the declared floating-point type and the encoded and decoded types are the same. Reopening preserves the rounded values and logical shape.

### FP-06: Runtime configuration

- Callers can set and retrieve global configuration, temporarily override it within a scope, and reload defaults together with external configuration. Leaving a temporary scope restores the prior values, including when the scope exits with an error. Configuration can also be supplied through environment variables and configuration documents.

- The default format for new data is format 3; callers can select format 2 instead.

- Callers can select registered alternative codecs and array-buffer providers. Selection of an unavailable provider fails visibly.

- Environment-supplied values override configuration-document values, which override built-in defaults. Explicit global settings override the values already loaded. Reloading removes those explicit settings and rereads external configuration.

### FP-07: Array creation and opening

- Callers can create arrays with a specified shape, data type, regular chunk shape, fill value, and storage location in format 2 or format 3. Scalar arrays and arrays with zero-length dimensions are supported. Negative dimensions and mismatched chunk rank are refused as invalid array definitions.

- Creating from supplied array data derives the shape and data type from that data and stores its values. Supplying both initial data and a separate shape or data type is refused as conflicting input. In this data-or-definition creation form, omitting initial data requires an explicit data type. Shape-only convenience creation instead defaults to 64-bit floating-point data; explicitly zero-filled, one-filled, and caller-filled creation makes every logical element read as the selected value.

- Arrays can be reopened from existing storage without restating their creation properties. Automatic format detection recognizes formats 2 and 3 and prefers format 3 when both are present at the same location; an explicit format request selects that format. A generic node-opening request returns the stored node kind, while opening a group as an array is refused.

- Read-only opening and read-write opening of existing nodes require the target to exist. Open-or-create reuses an existing node or creates a missing one. Exclusive creation refuses an existing node; replacement creation replaces an existing node and its descendants when storage permits deletion. With no explicit access mode, generic node opening uses read-only access for a read-only store and open-or-create for a writable store; given no array properties, it creates a group. Array-specific opening with omitted mode supports existing targets; creating missing arrays requires an explicit creation mode.

- Creating a node below an existing array is refused as a hierarchy conflict. A missing node is distinguished from a malformed metadata document. Format 3 array opening also distinguishes a node of the wrong kind; format 2 array opening may report a group as a missing array. Read-only array access refuses data and metadata mutations.

- Format 3 arrays can retain caller-supplied dimension names, with one name or unnamed position per dimension. A count that differs from the array rank is refused as incompatible metadata.

- Array inspection exposes shape, rank, data type, fill value, format, encoding choices, and chunk organization. Complete storage inspection distinguishes the logical byte size of fixed-size data from the total bytes of stored array objects, including metadata. For unsharded arrays it distinguishes the number of stored data objects from the number of possible chunks.

- When chunk dimensions are not supplied, creation chooses a regular chunk shape and exposes the choice through array inspection; reopening retains it. Callers can also request a single chunk covering the whole nonempty array. An omitted fill uses the data type default in either format. An explicitly unspecified fill also uses that default in format 3, but records no defined fill value in format 2.

- In the data-or-definition creation form, explicitly supplied regular chunk lengths must be positive integers, apart from the separate choice of a full-span chunk. Zero, negative lengths other than that choice, and nonintegral lengths are refused as invalid chunk definitions.

- Reopening otherwise valid stored array metadata with regular chunk lengths of zero uses a positive replacement extent along those dimensions: one for unsharded arrays, or the corresponding positive inner chunk length for sharded arrays. This compatibility rule applies in either format, including empty dimensions, and does not permit creating new arrays with zero chunk lengths. A replacement along a nonempty dimension produces a compatibility warning. Negative stored lengths and wrong chunk rank remain malformed; a zero outer length with an invalid inner shard shape is not repaired.

### FP-08: Array selection and modification

- Basic selection reads and writes integers, positive-step slices, omitted trailing dimensions, and an ellipsis over an array. Negative integer positions count from the end; slice bounds are clipped to the dimension extent. Integer-selected dimensions disappear from the result. Out-of-bounds integers, excess indices, zero or negative slice steps, and multiple ellipses are refused as invalid selections.

- Orthogonal selection chooses the Cartesian product of independent per-axis selections. Each axis accepts an integer, a positive-step slice, a one-dimensional integer collection, or a one-dimensional Boolean mask. Supplied integer ordering and repeated positions are retained in reads; an axis mask must match its dimension length. Unsupported selector shapes and out-of-bounds positions are refused.

- Coordinate selection chooses paired coordinates, one coordinate collection per dimension, with singleton dimensions broadcast to the common selection shape. The result retains that shape, coordinate order, and repeated points. Non-broadcastable coordinate collections and out-of-bounds coordinates are refused.

- Full-array Boolean masks select true positions into a one-dimensional result in row-major coordinate order. Mask shape must equal array shape, otherwise selection is refused as incompatible. Block selection reads and writes whole chunk regions using integer chunk positions or contiguous chunk slices, clipped to the array boundary.

- Assignment accepts a scalar or values matching the selection shape, converts them to the array's data type, and changes only selected positions. For non-coordinate selections contained in one chunk, equal-rank values may also have singleton dimensions broadcast to the corresponding selection dimensions. Coordinate assignment accepts a scalar or a complete collection of selected values. Incompatible assignment shapes are refused.

- For unsharded arrays with a defined fill value, missing chunk data reads as that fill value under the default policy. A caller can instead require stored chunks, in which case selecting absent chunk data fails as missing data. Under the default fill-only write policy, writing a complete chunk to its fill value removes or omits its stored payload; an explicit retain-empty choice stores that payload.

- Callers can read a selection into a supplied writable output of matching shape and compatible data type. Selected values populate that output; a mismatched output shape is refused. Whole-array loading returns the array's values in memory.

- Multiple readers of unchanged storage obtain consistent array values. Concurrent writers to disjoint storage chunks of unsharded arrays preserve each writer's updates when the underlying store supports concurrent writes.

- On creation, per-array configuration overrides global defaults, while unspecified choices inherit global values. Reopening existing arrays inherits global choices. A new view inherits unspecified choices from the original array and can use different read-result memory order, fill-only write policy, and missing-chunk read policy while accessing the same stored array. Unknown configuration choices supplied at creation or when making a new view are refused as invalid configuration. Read results default to row-major memory order; requesting column-major order preserves the logical values.

- For the first nonempty element write following opening with replacement chunk extents, with stored metadata still present and metadata and element operations performed sequentially, the stored metadata describes positive extents that locate the written values after reopening without another replacement warning. If another caller has changed the stored chunk or shard organization to conflict with that handle, this write is refused as changed storage and does not alter stored content. Compatible metadata changes completed by another caller before this write are preserved.

### FP-09: Shards and variable chunk boundaries

- Format 3 arrays can group multiple logical chunks into a shard with independently configured inner chunk and outer shard shapes. Each shard dimension must be divisible by the corresponding inner chunk dimension. Reads and partial writes preserve values across inner chunk and shard boundaries, and partial writes preserve unselected values in the same shard.

- Sharding reduces the number of stored data objects to the number of occupied shards rather than occupied inner chunks. Absent inner chunks within an existing shard read as fill values even when missing stored data is otherwise forbidden. That strict policy refuses a read only when an addressed shard is absent. Malformed or checksum-damaged shard indexes are refused as corrupt data.

- Explicitly enabled rectilinear chunking permits a separate positive size for every chunk along each dimension of a format 3 array. At creation, an explicit size sequence on a nonempty dimension must sum to its length. Shrinking retains declared boundaries, so the final boundary may then extend beyond the current data extent. Empty size collections on nonempty dimensions, nonpositive sizes, rank mismatches, and unequal initial total extent are refused. Creating or opening a rectilinear array without enabling this capability is refused as disabled functionality.

- Chunk-size inspection reports the actual data extents, including clipped boundary chunks. Asking for a single uniform shape for an unsharded variable grid is refused as unsupported.

- Rectilinear outer shard boundaries can be combined with regular inner chunks when every outer size is divisible by the corresponding inner size. Rectilinear inner chunks are refused for sharding. A zero-length rectilinear dimension accepts positive future chunk sizes and retains them for subsequent growth.

- For sharded arrays, concurrent writes preserve each writer's updates when they affect disjoint shards and the store supports concurrent writes.

### FP-10: Resizing and appending

- Callers can increase or decrease dimension lengths without changing array rank. Values in the retained region remain at the same coordinates. Changing rank or supplying negative lengths is refused as an incompatible shape.

- Shrinking normally removes stored data objects whose entire region lies outside the new shape and retains the full data in objects that intersect it. The region is one chunk for unsharded arrays and one whole shard for sharded arrays. Growing later exposes retained values and fill values where no stored data remains. The explicit preserve-outside choice retains wholly outside objects as well.

- Appending extends a selected axis, places supplied values after its existing extent, preserves prior values, and reports the new shape. The default axis is the first axis. The appended data must have the same rank and equal lengths along every other axis; violations are refused as incompatible append data.

- For rectilinear arrays, growth beyond the sum of declared chunk sizes adds a new extent covering the extra length; growth within retained boundaries reuses those boundaries. Appending follows the same rule.

- A shrink that requires deletion on storage without deletion support is refused as unsupported, and reopening still exposes the original shape and values. Growth and shrinkage that retain every stored data object do not require deletion support.

### FP-11: Hierarchical groups

- Callers can create and reopen groups containing arrays and other groups in either format. Nested creation supplies missing intermediate groups, and addressing a descendant returns its actual node kind. Missing members and requests for the wrong node kind are distinguished.

- Group membership queries, iteration, member counts, and hierarchy displays expose arrays and groups under their relative names. Enumeration defaults to immediate children. Depth zero includes immediate children, and each additional depth includes one further descendant level; callers can also enumerate throughout the hierarchy. Negative traversal depths are refused.

- Deleting a member removes its metadata and stored data, including descendants of a deleted group, without deleting siblings. Deleting through read-only access or a store without deletion support is refused.

- A caller can require a group or array, reusing a compatible existing node or creating a missing one. Existing arrays must have the requested shape and, by default, a data type safely convertible to the requested type; exact matching can instead be required. A node-kind, shape, or data-type conflict is refused as incompatible existing content.

- Batch hierarchy creation accepts descriptions of multiple groups and arrays and creates the intermediate groups needed to connect them to the root. Conflicting descriptions that place descendants below arrays or mix incompatible hierarchy formats are refused. Existing content is protected unless replacement is explicitly requested.

### FP-12: User attributes

- Arrays and groups retain caller-supplied attributes with text keys and JSON-compatible values. Callers can retrieve attributes, enumerate their keys, test membership, assign values, and delete entries. Completed changes are visible after reopening the node; reading or deleting an absent key fails as missing attribute data.

- Updating several attributes merges the supplied entries with existing attributes, replacing matching keys and preserving unrelated keys. Replacing the complete attribute collection removes entries not present in the replacement. Values that cannot be serialized as attribute data are refused, and read-only access refuses changes.

### FP-13: Consolidated hierarchy metadata

- Callers can consolidate metadata for a group and all descendants in formats 2 and 3. The resulting hierarchy view preserves node kinds, array properties, and attributes as they existed at consolidation, while array values continue to come from their stored data.

- Opening a group uses consolidated metadata by default when available. Requiring consolidated metadata fails if it is absent; explicitly disabling it reads the individual node metadata. A child added or changed after consolidation is reflected in the individual-metadata view and only appears in a consolidated view after consolidation is refreshed.

- After opening a consolidated group, descendant metadata lookup and enumeration do not require separate reads of those descendants' metadata documents. A store that disallows consolidation refuses consolidation and requests that require it; ordinary group opening on such a store uses individual metadata.

### FP-14: Creating copies and saving arrays

- Callers can create a new array from a native array, array-like values, or an existing stored array. The new array preserves logical shape and values. For a stored-array source, unspecified storage choices retain its format, chunking, sharding, encoding, fill value, dimension names, and attributes; callers can override these choices to create a different storage representation of the same values.

- A caller can create from an existing array without copying element data. The result retains the chosen metadata and reads as its fill value until data is written. By default, copied nested attributes are independent of the source; an explicitly supplied attribute collection replaces inherited attributes.

- Saving a single native array persists its shape, data type, and values for later whole-array loading. Saving multiple arrays, or any array given a name, creates individually addressable arrays in a group, preserving caller-supplied names and assigning distinct names to unnamed arrays. Saving without any arrays is refused as missing input.

- Default single-array saving refuses an existing array at the target. Explicit replacement through single-array saving replaces it when the store supports deletion. Copy creation also protects existing targets unless replacement is requested.

- When copying element data with replacement in the same storage, a destination equal to, containing, or contained by the source location is refused as an overlap conflict and the source remains intact. This protection applies even when the source is accessed through a read-only view. Metadata-only replacement does not require preserving source element data and permits overlap where the destination satisfies hierarchy rules; a destination below an array remains invalid.

### FP-15: Metadata migration and removal

- Callers can migrate format 2 metadata for an array or a hierarchy to format 3, either at the original location or a separate destination. Shape, chunk organization, fill value, attributes, byte order, and logical values described by compatible numeric encodings are preserved. In-place migration leaves existing chunk data unchanged and readable with the new metadata; migration to a separate destination transfers metadata only.

- Migration supports uncompressed numeric arrays, Blosc, Zstandard, Gzip, and additional registered filter or compressor conversions whose transformation kind matches their role. Non-format-2 input, consolidated source metadata, unknown codecs, and filter or compressor conversions of the wrong kind are refused as unsupported migration inputs.

- Migration retains source format 2 metadata by default. Callers can request its removal after migration, or separately remove format 2 or format 3 metadata throughout a hierarchy while retaining array payloads. Removal normally requires alternative-version metadata at each affected node; explicit forced removal permits its absence. Stores without deletion support refuse metadata removal.

- Standalone dry-run migration to a destination without existing format 3 metadata, and standalone dry-run removal, identify which metadata would be created or removed without changing stored data. Unsupported migration inputs remain failures during a dry run.

- Migration refuses to replace existing format 3 metadata by default. Explicit replacement permits regenerating it; removal of existing destination metadata requires alternative format 2 metadata unless forced removal is selected.

### FP-16: Coordinate domains and composable selections

- Callers can describe finite rectangular coordinate domains with inclusive lower and exclusive upper bounds, optional dimension labels, scalar rank, and empty extents. Bounds are literal coordinates, including negative origins. Unequal ranks, inverted bounds, or a label count that differs from rank are refused as invalid domains. Containment requires equal rank and all coordinate positions or subdomain bounds to lie within the enclosing bounds. An empty subdomain outside those bounds is not contained. Labels do not alter coordinate meaning.

- A selection maps each request coordinate to source coordinates using constant coordinates, offset-and-stride relationships, or explicit coordinate collections. An affine relationship scales the chosen request coordinate by its stride and shifts it by its offset; an explicit-coordinate relationship applies that same scaling and shift to the selected coordinate value. Omitted offsets are zero and omitted strides are one. Callers can compose selections, translate domains, permute axes, and restrict domains; the result maps to the same source coordinates as applying the supplied selections in sequence. Composing a selection with an inner selection maps each request coordinate through the selection and then through the inner selection. Incompatible ranks and nonempty selections outside the declared source domain are refused. Translation moves both bounds by the supplied displacement in each dimension; axis reordering can be expressed through the coordinate relationships. For selections whose explicit-coordinate and affine mappings do not share a varying request axis, restriction by a source domain retains only request positions whose mapped source coordinates fall within that domain; an empty intersection reports no selection. Coordinate collections are captured by value: changing a supplied collection afterward does not change an existing selection.

- Selection construction supports basic slicing with either stride direction, integer dimension removal, added singleton dimensions, orthogonal selections, broadcast paired-coordinate selections, and Boolean masks. Orthogonal choices form Cartesian products, while paired-coordinate choices retain their correlations. Result order and repeated source coordinates are preserved.

- Selection messages support five semantic forms: a point, a rectangular box, a strided region, an ordered list of points, and a complete coordinate transform. Point messages require a coordinate list, and ordered-point messages require a list of equal-rank coordinate lists. A point selects one source coordinate; a box includes its lower boundary and excludes its upper boundary; an ordered list retains its point ordering and repetitions. Validation distinguishes unknown forms, unknown members, rank disagreement, conflicting upper-bound descriptions, reversed bounds, zero steps, conflicting coordinate rules, and invalid numeric values. Validated integer fields use signed 64-bit values; Boolean values are not integers at this boundary. A complete transform with an explicitly declared input rank outside zero through 32 is refused as an invalid description.

- Normalizing a selection message preserves its coordinate meaning and produces a stable full description. Submitting that description as a complete-transform message and normalizing again leaves the description unchanged. Finite complete descriptions can be converted to executable selections and back while preserving their coordinate mapping. Unbounded domains are accepted in descriptive messages but refused as executable finite domains.

- Executable explicit-coordinate collections must be rectangular integer collections with a shape broadcastable to the request domain; malformed collections and references to nonexistent request axes are refused as invalid descriptions. When loading executable explicit-coordinate selections with supplied coordinate bounds, every supplied coordinate must satisfy those inclusive bounds before offset and stride are applied. Any violation refuses the whole selection, even when subsequent selection would avoid that coordinate. Empty coordinate collections satisfy ordered bounds.

- Direct coordinate slicing and strided selection messages determine their result domains and coordinate mappings according to ndsel version 1.0-draft.2, section 5.3, using each dimension's traversal start, excluded stop, and signed step. The result domain's lower bound is the traversal start divided by the step, rounded toward zero. Direct slicing treats explicit bounds as literal coordinates without wrapping or clipping. An omitted direct-slice start is the domain's lower bound for forward traversal and its final coordinate for backward traversal; an omitted stop is the upper bound for forward traversal and one below the lower bound for backward traversal. A nonempty traversal interval must lie within the source domain.

- In box and complete-transform messages, omitted lower bounds are zero and omitted upper bounds are unbounded; omitted labels leave dimensions unnamed. Rank is inferred from supplied bounds or labels when not declared and is zero when none are supplied. An inclusive upper bound denotes the same domain as one greater exclusive bound; a supplied shape gives lengths from the lower bounds. These alternative upper-bound descriptions are mutually exclusive. Omitted output-coordinate rules describe identity mapping. Normalization preserves whether each bound was explicitly or implicitly declared. An explicit-coordinate rule may use zero stride to select the same source coordinate throughout; a zero traversal step remains invalid.

### FP-17: Chunk projection and partitioning

- Given a coordinate selection and per-dimension grids, callers can obtain the touched chunk coordinates, each chunk's bounds, the selected positions within it, and the destination positions in the requested result. Uniform and variable-sized bounded grids are supported. Chunk-local positions resolve to the same global source coordinates as the original selection, and destination positions preserve its ordering and duplicates.

- Nonempty selections are refused as unsupported planning if multiple affine source dimensions depend on the same request axis, or if an affine source dimension and an explicit-coordinate source dimension vary along the same request axis. Without these shared-axis relationships, an empty request domain yields no chunk contributions. Chunk contributions stay within the valid data extent of boundary chunks, and out-of-grid source coordinates are refused as out of bounds.

- Callers can inspect each contribution's data coverage. Basic selections covering every valid element exactly once are identified as complete even for a clipped boundary chunk; partial and repeated coverage are not reported as complete. Explicit-coordinate coverage may conservatively remain partial.

### FP-18: Lazy array views and write-through selections

- Callers can wrap an array-like source, chain basic, orthogonal, and paired-coordinate selections, and inspect view shape and coordinate meaning without retrieving source element values. Materializing a view returns the selected source values in host memory with the requested shape, data type, and repeated positions.

- Ordinary array selectors are relative to the current view, with negative positions wrapping from its end and slice bounds clipped to its extent. Positions outside the view, excess indices, and multiple ellipses are refused. Domain and transform selectors instead use absolute coordinates; a domain selector of another rank or extending outside the view is refused. Derived views retain their absolute domains, so relative and absolute selections can be composed without changing the selected source values.

- Callers can partition views against chosen chunk boundaries and materialize individual parts. Each part supplies its source contribution and result placement, permitting recovery of the full requested result without loss of order or repeated values. Parts use the source reader selected by the caller, and errors from that reader propagate to the caller.

- Assignment through a view writes to the selected coordinates of the original writable source, preserving unselected source values. Scalars and values broadcastable to the view shape are accepted; incompatible assignment shapes and sources without assignment support are refused. Reads remain available for sources that cannot be written.

- Materialized results are independent of source storage: modifying a returned result does not modify the source. Requesting another materialization observes the source values at that request, rather than a previous materialized result.

### FP-19: HTTP access to stores and nodes

- Callers can serve a complete store or restrict serving to one array or group. Complete-store serving exposes existing keys; node-scoped serving exposes only valid metadata and chunk keys belonging to that node and its descendants. Keys outside the node, invalid chunk coordinates, and attempts to escape its scope are answered as not found, even if the underlying store contains corresponding data.

- HTTP clients can retrieve stored bytes or request their size without a response body. These read operations are enabled by default. Enabling retrieval also enables bodyless size requests. Replacing a value is available only when explicitly enabled on writable storage; unsupported operations are refused as method-not-allowed. Configuring writes on read-only storage is refused as contradictory configuration.

- Partial reads implement single byte ranges from RFC 9110, sections 14.1.2 and 14.2, using the client's range and the requested object's bytes and length. Bounded, open-ended, and suffix ranges are supported. Well-formed ranges with no readable bytes are refused as unsatisfiable. Unrecognized units, malformed ranges, and multiple ranges return the complete representation instead of a multipart response.

- An enabled replacement stores the request body at the addressed key. The default accepted body limit is 256 MiB, measured as 268435456 request-body bytes; larger bodies are refused as too large. Callers can set a different limit or remove it. Rejected oversized requests do not replace the existing value.

- Callers can enable browser cross-origin access for specified origins, request methods, headers, and credentials. Without that configuration, responses grant no browser cross-origin permission. The default range-related allowances permit requesting a byte range and reading the returned range description. Explicit header choices replace those defaults. Explicitly advertising a method the service does not allow is refused; an all-methods choice expands only to enabled methods.

- A server can run until stopped or start while returning control to the caller. Successful background startup provides the actual reachable address; shutdown stops serving and releases its listening endpoint. An explicitly selected occupied port fails rather than selecting another port. Automatic selection prefers port 8000 and chooses an available port if that port is occupied; requesting any free port has no preference.

- Server configuration can enable encrypted HTTP. The reported address reflects whether encryption is active; a non-network-socket binding does not report a network address. Leaving a server's managed lifetime stops it, and failure to stop is reported visibly.

- Configured operations can include only retrieval, bodyless size requests, and complete-value replacement, with at least one operation enabled. Configuring an empty collection or any other operation is refused as invalid configuration.
