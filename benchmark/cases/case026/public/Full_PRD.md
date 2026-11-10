# VelqoraMap Full PRD

VelqoraMap is an embedded Java record store with concurrent map access, optional persistence, SQL-like querying, HTTP services, and shared-nothing clustering.

### FP-01: Concurrent map storage

- A caller can create an empty in-memory map or initialize it from existing entries. Inserting a key makes its value readable, replacing an existing value returns its previous value, and reading an absent key returns absence or the caller-supplied alternative. Size, emptiness, key membership, and value membership reflect the stored entries.

- Conditional insertion changes only an absent key. Replacement changes only an existing key; comparison-based replacement and removal change an entry only when its current value equals the supplied expected value. Callers can distinguish a successful conditional change from an unmet condition, which leaves the entry unchanged.

- Caller-supplied computations can create, update, or remove entries, with variants restricted to absent or present keys. Combining a supplied value with an existing value uses the supplied combination rule; absence stores the supplied value directly. For these single-entry computations and combinations, a null result removes an existing entry or leaves an absent entry absent. Concurrent conditional updates and combinations preserve completed updates without losing them to competing updates.

- Bulk insertion stores all supplied entries. A caller can replace every existing value using a computation of its key and current value; each computed replacement must be non-null. Bulk removal removes the requested keys and reports whether any entry was removed, and clearing removes all entries. Removing one key returns its previous value or absence.

- The key, value, and entry views reflect subsequent map changes. Attempts to remove, clear, or replace stored values through these views are refused as unsupported modifications.

- Null keys and stored null values are refused as invalid inputs.

- An in-memory map accepts durability, compaction, and close requests without requiring a persistence directory.

- Applications can register observers that receive the affected key for successful insertion, replacement, and removal requests; every registered observer has received the key by the time the mutating call returns. Bulk changes notify for each affected key. Removing an absent key or attempting a conditional change whose condition is unmet produces no notification.

### FP-02: Durability and restart recovery

- A persistent map accepts a storage directory and application-supplied reversible encodings for keys and values. Opening a missing directory creates it; reopening an existing directory with compatible encodings restores its latest durable entries and deletions. The built-in UTF-8 string option preserves Unicode keys and values across reopening.

- Successful explicit durability checkpoints and orderly close make previously completed map mutations recoverable, including conditional, computed, combined, bulk, and clear operations. Repeated close requests succeed without repeating a required application action.

- Ordinary map reads and mutations remain available while an application-supplied encoder is waiting for an external resource; an explicit durability request does not report success while required encoding remains unfinished.

- When the final stored record is incomplete, reopening retains the preceding complete records and allows new writes that survive another reopening. A stored key or value data field declaring a negative length or a length greater than 256 MiB is refused as corrupt storage; a recognized deletion record is not a value data field. An invalid declared field length takes precedence over incomplete contents of that field. One MiB is 1,048,576 bytes.

- Opening a location that cannot serve as a persistence directory reports a storage failure. After saving fails because encoding or storage I/O fails, durability requests and the first close request report that failure, and subsequent attempts to record mutations report failure rather than durable success.

- Convenience-opened persistent maps save their pending mutations during ordinary application shutdown when their encoders and storage remain operational and shutdown is allowed to finish.

### FP-03: Reclaiming persistence history

- Manual compaction preserves the current entries and deletions for reopening. For unchanged encodings and identical live entries, the resulting log byte size does not grow with the number of earlier overwritten or deleted versions; compacting an empty map leaves an empty data log.

- If encoding the compacted state fails, compaction reports failure and the previously durable log remains recoverable.

### FP-04: Destructive entry eviction

- Maps retain their entries by default. A caller can enable destructive eviction with a positive entry-count limit, and a later positive limit replaces the earlier one. Non-positive limits are refused as invalid configuration.

- Once a map exceeds its configured limit and writes and explicit removals have stopped, eviction reduces the population to no more than that limit. A previously nonempty overflowing map retains a nonempty subset when the limit is at least two; a limit of one can empty the map. The limit counts entries, and concurrent or bulk writes may temporarily exceed it.

- Eviction deletes selected entries from the map. A successful durability checkpoint settles pending eviction; for a persistent map it also preserves those deletions across reopening.

### FP-05: Table selection and predicates

- Applications can register maps as named query tables and supply readers for their visible columns. Each table also exposes its map key, and subsequent queries reflect completed changes to its registered map. A query can select named columns, give selected values output aliases, or select all visible columns and the key. A plain selection returns a row for each qualifying entry and no rows for an empty table.

- Table aliases qualify column references. Unqualified references resolve when only one participating table contains the column. Local materialized results and their row mappings refuse structural changes by the caller.

- Predicates support equality, inequality, greater than, greater than or equal, less than, and less than or equal comparisons. Operands can be columns, string literals, signed 64-bit integer or finite decimal literals, boolean literals, null, or named parameter values. Reusing query text with different bindings applies the new bindings.

- Conjunction requires both conditions and disjunction requires either condition. Conjunction binds more tightly than disjunction unless parentheses specify a different grouping.

- Equality treats two nulls as equal and one null as unequal to a non-null value; ordered comparisons involving null do not match. A finite numeric value compares equal to itself. For finite numbers exactly representable at double precision other than negative floating zero, comparisons use numeric value across primitive numeric representations. Non-numeric equality compares values without converting their types or changing text case. Non-numeric ordered comparisons follow the natural order of mutually comparable values of the same type; incomparable operands are refused.

- Malformed statements, unterminated string literals, and unexpected trailing text are refused. Selecting from an unregistered table is refused. For a selection with no limit or a positive limit and at least one qualifying row, an unknown selected column or qualifier is refused. For a nonempty table and no limit or a positive limit, a predicate consisting of a comparison against an omitted named parameter is refused.

### FP-06: Result ordering and limits

- Queries can order by one or more selected columns or output aliases. Each successive ordering term breaks ties left by the earlier terms. Ascending order is the default, and each term can instead request descending order.

- Ascending ordering places null values after non-null values; descending ordering places them before non-null values. Finite numeric values exactly representable at double precision other than negative floating zero follow numeric value order; mutually comparable non-numeric values of the same type follow their natural order. Incomparable ordering values are refused.

- A result limit accepts whole numbers from zero through 2,147,483,647. Across query forms, the result contains the requested number of rows when enough qualifying result rows exist, and otherwise contains all qualifying result rows; zero returns no rows. Without ordering, the selected rows form a subset of the qualifying result rows with their original multiplicities. Without a limit, all qualifying result rows are returned. Limits outside the accepted range are refused.

- For queries requesting ordering and a limit, the returned rows are the requested prefix of the complete ordered result.

### FP-07: Inner equality joins

- A query can join one or more named tables by equality between a column from the newly joined table and a column from an existing table. All matching row combinations are returned, preserving multiple matches; rows with no match are omitted. Either equality operand may name the newly joined table.

- Local joins support non-null map-key and ordinary-column relationships with matching text, booleans, or numeric values represented by the same numeric type. Text and boolean join values match by exact value without conversion to another type. Selected fields and wildcard selection can include every joined table, and predicates can restrict joined rows. Later queries reflect completed changes to the participating maps and use the current supplied bindings.

- A join condition that references the newly joined table on neither side or on both sides is refused. Selecting an unqualified column present in more than one participating table is refused when qualifying joined rows exist.

### FP-08: Grouping and aggregate summaries

- Queries can group qualifying rows by one or more columns and return one result per distinct grouping-value combination. Grouping without an aggregate still returns one row per distinct combination. Numeric grouping covers finite values exactly representable at double precision other than negative floating zero: equal values across primitive numeric representations belong to the same group. Null grouping values can form groups.

- The supported summaries are total row count, count of non-null values, sum, arithmetic mean, minimum, and maximum. Except for total row count, these summaries ignore null inputs. Without grouping columns an aggregate query returns one summary row, even for empty input: both counts are zero and the remaining summaries are null. An empty input with explicit grouping columns produces no groups.

- Sum and mean accept signed 8-bit, 16-bit, 32-bit, and 64-bit integer values and 32-bit and 64-bit floating values. An all-integral sum returns an integral total; a sum containing floating values and every nonempty mean return floating results. Minimum and maximum return the least or greatest non-null input value under the numeric and non-numeric comparison rules; incomparable inputs are refused. Non-numeric inputs to sum or mean are refused.

- Integral sums are exact when the sum of absolute input magnitudes fits a signed 64-bit integer. For up to one million finite inputs within that same magnitude bound, floating sums have absolute error no greater than the larger of one trillionth and one billionth of the sum of absolute input magnitudes. Means have absolute error no greater than the larger of one trillionth and one billionth of the sum of absolute input magnitudes divided by the non-null input count. All-zero non-null inputs produce zero.

- Each selected non-aggregate column in an aggregate or grouped query must be a grouping column. Selecting all columns in such a query, selecting an ungrouped non-aggregate column, or requesting a wildcard argument for a summary other than total row count is refused.

### FP-09: Efficient local query access

- Applications can configure accelerated equality queries on visible non-key columns of tables backed by the embedded store. This access configuration is refused for an unknown column, the map-key column, or a table backed by an ordinary map rather than the embedded store.

- For repeated single-table equality queries selecting a fixed number of rows by a non-numeric map key or a non-key column configured for accelerated equality access, tenfold table growth increases median query completion time by less than fourfold. This relation applies with fixed-width records, fixed match count, unchanged query and access configuration, enough memory for both table sizes, and the same processors; it excludes table loading and access configuration.

- A caller can consume single-table selection and filtering results incrementally with an optional result limit. Joins, grouping, aggregates, and ordering are refused by this incremental-query form.

- For a single-table projection without predicates, joins, grouping, aggregation, or ordering, obtaining a fixed positive number of rows through a limit or through incremental consumption takes less than four times the median time after tenfold table growth. Record width, requested row count, query configuration, processors, and available memory remain fixed, with enough memory to hold both table sizes.

### FP-10: HTTP map service and access policy

- An application can expose one map or multiple named maps over HTTP, with independently supplied key and value encodings for each map. Single-entry insertion, reading, and deletion affect only the selected map. Reading or deleting an absent entry, or addressing an unknown map or route, reports not found.

- Batch insertion and batch deletion apply the supplied entries or keys to the selected map. Empty batches succeed without changing entries, and absent keys in a deletion batch do not prevent removal of present keys. Application encodings preserve key and value contents across binary batch round trips.

- For supported batch requests to a known map, truncated batch fields, missing values in entry batches, negative data-field lengths, and data-field lengths greater than 256 MiB are refused as invalid requests. Keys or values rejected by their supplied decoders are also refused as invalid requests. Malformed and oversized bodies share the same invalid-request failure form. For entry or batch mutation requests, a malformed body does not apply a partial mutation.

- For entry insertion, batch insertion or deletion, ordinary queries, node selection streams, and node key lookups, request bodies greater than 64 MiB are refused when the resource is enabled, the method is supported, and an entry key is decodable when required. The size bound measures the complete request body in bytes. Using an unsupported HTTP method for an existing enabled resource is refused as a method error when an entry key is decodable if required; an undecodable entry key is refused as malformed input even with an unsupported method.

- Health requests expose the current entry count for a single map; a service with named maps exposes the total entry count across served maps and the number of served maps.

- Remote durability and compaction requests apply to the addressed map and report completion only when that operation succeeds. Closing the HTTP service stops access through that service while the maps remain available for embedded use and separate close.

- Without a supplied authorization policy, requests are allowed. A supplied policy can permit or refuse each request on every route, including health and query routes. Refused requests report authorization failure without changing the addressed map or its durable data, returning requested data, or invoking application column readers for the refused query. A refused durability request returns without waiting for a pending application encoder. Authorization refusal takes precedence over not-found, method, and malformed-input responses. A policy that raises an I/O error yields a service failure without changing the addressed map or its durable data.

- Application-supplied HTTP filters can inspect requests and modify responses; response changes made by a filter are visible to the client.

- A service requires at least one map. Named maps must have distinct, nonempty names consisting of ASCII letters, digits, periods, underscores, or hyphens; duplicate or invalid names are refused as configuration errors.

### FP-11: HTTP query execution

- When ordinary HTTP querying is enabled, callers can submit SQL-like query text and named bindings and receive the resulting local query rows, including joined and aggregated results. Well-formed Unicode strings, finite numbers, booleans, null values, and embedded string control characters retain their meanings in the returned data.

- Text bindings representing null, booleans, decimal integers, or decimal fractions are interpreted as those scalar values; other binding text remains a string. Decimal integers consist of digits with an optional leading minus sign and fit the signed 64-bit range. Integer-shaped text outside that range is refused. Decimal fractions have digits on both sides of the decimal point and may have a leading minus sign; finite representable fractions are supported.

- Submitting an ordinary query with the supported HTTP method but without configuring ordinary querying is refused, regardless of the query text. When ordinary querying is enabled, a malformed query is also refused. These refusals share the same invalid-request failure form.

- HTTP map names and query table names are independently configured. Registering a map for record requests does not by itself make it a query table, and a map can have different record-service and query-table names.

### FP-12: Shared-nothing key ownership and routing

- A caller can configure a positive logical-partition count and a nonempty set of named nodes, then either provide every partition owner or request an even ownership distribution. Even distribution gives node partition counts differing by at most one. Empty node sets, non-positive partition counts, duplicate node names, and assignments to unknown nodes are refused. Node names must be nonempty and consist of ASCII letters, digits, periods, underscores, or hyphens; other names are refused as invalid configuration.

- The partition for a key is determined by its encoded key bytes and the fixed partition count, independently of process-local object identity. The same bytes and partition count yield the same partition across clients and restarts. Independently uniformly sampled encoded keys of at least eight bytes are distributed uniformly over the logical partitions. Ownership follows the supplied assignment, and callers can inspect both the partition and owner of a key.

- Clustered reads, writes, deletion, and batch mutations operate on each key at its sole owner over the configured transport, including HTTP transport to independently running processes. Reads distinguish an absent entry from a stored value, and single deletion reports whether an entry existed. A supplied transport can carry application request headers to the owner.

- Adding node membership preserves existing ownership. Explicit reassignment changes only the selected partitions; explicit rebalancing evenly redistributes the fixed partitions over the supplied node list. Installing a topology with a different logical-partition count, selecting a nonexistent partition, or removing a node that remains an assigned owner is refused as invalid topology.

- Installing reassigned ownership changes subsequent routing without moving old records. Old records remain at their previous owner, and a newly assigned owner returns absence for a key it does not already hold.

- An unavailable sole owner causes affected operations to report an owner-access failure identifying that owner, without succeeding through a different node. Operations on other available owners remain usable.

### FP-13: Typed query rows across node boundaries

- Individual scalar interchange preserves scalar types and values across encoding and decoding. Binary row interchange additionally preserves row sequence and field associations, including an empty sequence. The supported scalar family is null, strings containing well-formed Unicode text, booleans, signed 8-bit, 16-bit, 32-bit, and 64-bit integers, 32-bit and 64-bit floating values, non-surrogate characters in the Unicode Basic Multilingual Plane, and byte arrays. Other application objects are refused as unsupported interchange data.

- A truncated row or a stream missing its clean ending is reported as incomplete input rather than successful exhaustion. Invalid row markers, unknown scalar types, negative declared data lengths, and declared scalar lengths exceeding 256 MiB are refused as malformed input. Decoding an individual scalar also refuses extra data after that scalar.

- Decoding a row refuses a negative field count or more than 100,000 fields. A field name whose declared encoded length is negative or greater than 16 MiB is refused as malformed input.

- Embedded table access and a configured node query service expose registered table rows with a caller-supplied table qualifier and support lookup by a scalar map key. The node service also supports local selection, filtering, projection, and limits. Missing keys produce no rows. Joins, grouping, aggregates, and ordering are refused by the node selection-stream facility.

- Node query access and ordinary HTTP querying are independently enabled. Enabling only one leaves the other unavailable.

### FP-14: Distributed query results and resource control

- A caller can query a nonempty collection of local catalogs, remote node catalogs, or both, with each referenced table declared in every participating catalog. A declared table may be empty on individual nodes. Selection and filtering operate over the combined rows. For a nonempty input and no limit or a positive limit, a predicate consisting of a comparison against an omitted named parameter fails. For remote selections without joins, grouping, aggregates, or ordering, binding values are interpreted from their text as ordinary HTTP bindings. Application-supplied request headers accompany remote query requests.

- Distributed inner equality joins return all matches across node boundaries, including when related rows reside on different nodes and when equal finite nonzero numeric join values exactly representable at double precision have different primitive numeric representations. Grouping and the supported summaries combine all qualifying rows across nodes. Global ordering and limits apply to the combined result.

- Results expose their total row count and permit incremental consumption without requiring the caller to collect all rows. Returned row mappings reject caller modification.

- For unordered remote projections of one fixed-width ASCII text column, increasing the input and result row counts tenfold increases the median peak coordinator used heap across repeated executions by less than twofold, including workloads whose total returned text exceeds the coordinator heap limit. This relation applies when both workloads exceed the configured row allowance, the text in that allowance of rows totals at most one eighth of the heap limit in bytes, counting one byte per ASCII character, and node count, query settings, heap limit, and row widths remain fixed, with sufficient temporary disk space, and incremental result consumption that does not retain earlier rows; source storage resides outside the coordinator process.

- A caller can set a positive in-memory row allowance and a temporary-storage location. Temporary query files are confined to that location; releasing query files preserves pre-existing application files there. Results larger than that allowance remain complete and consumable, including joins with many duplicate matching keys. Closing the result releases temporary result files, and closing its consumption stream also releases those files.

- Configuring no query nodes, duplicate query-node names ignoring letter case, or non-positive row allowances is refused as a configuration error. Query-node names must be nonempty and consist of ASCII letters, digits, periods, underscores, or hyphens; other names are refused as invalid configuration. With no result limit or a positive limit, invalid grouped selections are refused and release temporary query data. If a required remote node becomes unavailable during a complete table scan or globally ordered query, execution fails rather than returning a successful partial result, and temporary data from that failed scan is removed.
