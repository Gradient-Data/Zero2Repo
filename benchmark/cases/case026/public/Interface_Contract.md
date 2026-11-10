# Interface Contract

VelqoraMap is a Java 17 library. The project root is `/app`; compiled public classes are available on the classpath at `/app/target/classes` (`target/classes` relative to the project root).

Java imports use `dev.velqoramap`, `dev.velqoramap.codec`, `dev.velqoramap.query`, `dev.velqoramap.http`, and `dev.velqoramap.cluster`. Embedded calls deliver results through return values, exceptions, and caller-supplied callbacks; they leave `stdout` to the calling application.

HTTP services are reached at `http://<host>:<port>` using the configured listening address and the port returned by the server. In route templates, `{prefix}` is empty for the map supplied to the single-map builder, or `/maps/{map}` for a map registered by name.

HTTP error bodies are UTF-8 JSON objects of the form `{"error":"<diagnostic>"}`. `error` is a nonempty human-readable diagnostic string. The status carriers are: `400` for a refused request or unavailable ordinary-query configuration; `401` for authorization refusal; `404` for a missing entry, map, route, or unavailable node-query resource; `405` for a method refusal; and `500` for a service or persistence failure.

An authorization-refusal response includes `WWW-Authenticate: VelqoraMap`. A method-refusal response includes `Allow`, containing comma-separated method tokens for the addressed resource: entry resources use `GET`, `PUT`, `DELETE`; batch resources use `PUT`, `DELETE`; health and scan resources use `GET`; flush, compact, ordinary query, selection stream, and lookup resources use `POST`.

## `dev.velqoramap.VelqoraMap`

`VelqoraMap<K,V>` is usable as a `java.util.Map<K,V>` and `java.util.concurrent.ConcurrentMap<K,V>`, and as an `AutoCloseable` resource.

```java
new VelqoraMap<K,V>()
new VelqoraMap<K,V>(Map<? extends K, ? extends V> initialEntries)
VelqoraMap.<K,V>memory()                 // VelqoraMap<K,V>
new VelqoraMap<K,V>(Path directory, Codec<K> keys, Codec<V> values) // throws IOException
VelqoraMap.open(Path directory, Codec<K> keys, Codec<V> values)    // VelqoraMap<K,V>
VelqoraMap.open(String directory, Codec<K> keys, Codec<V> values)  // VelqoraMap<K,V>
VelqoraMap.strings(Path directory)       // VelqoraMap<String,String>
VelqoraMap.strings(String directory)     // VelqoraMap<String,String>
```

`directory` identifies the persistence directory; `keys` and `values` are application codecs. The checked persistence constructor reports storage-opening failure as `java.io.IOException`; the convenience opening methods report it as `java.io.UncheckedIOException`.

### Reading and views

| Signature | Return form |
|---|---|
| `V get(Object key)` | Stored value; `null` denotes absence. |
| `V getOrDefault(Object key, V defaultValue)` | Stored value or the supplied alternative. |
| `int size()` | Entry count. |
| `boolean isEmpty()` | Emptiness indicator. |
| `boolean containsKey(Object key)` | Key-membership indicator. |
| `boolean containsValue(Object value)` | Value-membership indicator. |
| `Set<K> keySet()` | Key view. |
| `Collection<V> values()` | Value view. |
| `Set<Map.Entry<K,V>> entrySet()` | Entry view, with `getKey()` and `getValue()`. |

The views expose the standard Java collection operations `iterator()`, `stream()`, `spliterator()`, `forEach(Consumer)`, and `toArray()`. Iterators expose `hasNext()`, `next()`, and `remove()`; spliterators expose `tryAdvance(Consumer)`. Refused view modifications through `remove`, `clear`, `removeAll`, `retainAll`, `removeIf`, `Iterator.remove`, or `Map.Entry.setValue` raise `java.lang.UnsupportedOperationException`.

### Mutation calls

| Signature | Return form |
|---|---|
| `V put(K key, V value)` | Previous value or `null`. |
| `V putIfAbsent(K key, V value)` | Previous value or `null`. |
| `V replace(K key, V value)` | Previous value or `null`. |
| `boolean replace(K key, V oldValue, V newValue)` | Whether the conditional replacement occurred. |
| `V remove(Object key)` | Removed value or `null`. |
| `boolean remove(Object key, Object value)` | Whether the conditional removal occurred. |
| `void putAll(Map<? extends K, ? extends V> additions)` | Normal completion. |
| `boolean removeAll(Collection<?> keys)` | Whether any entry was removed. |
| `void clear()` | Normal completion. |

In the previous-value and removed-value forms, `null` denotes absence. A rejected null input or null bulk replacement result is carried by `java.lang.NullPointerException`.

### Application computations and observers

```java
V compute(K key, BiFunction<? super K, ? super V, ? extends V> remappingFunction)
V computeIfAbsent(K key, Function<? super K, ? extends V> mappingFunction)
V computeIfPresent(K key, BiFunction<? super K, ? super V, ? extends V> remappingFunction)
V merge(K key, V value, BiFunction<? super V, ? super V, ? extends V> remappingFunction)
void replaceAll(BiFunction<? super K, ? super V, ? extends V> function)
void onMutation(Consumer<K> listener)
```

Computation calls return the resulting value or `null` for absence. Key-based callbacks receive the key and, for two-argument callbacks, its current value; the absent current value is `null`. A merge callback receives the existing value and supplied value. A mutation listener receives an affected key of type `K`.

### Maintenance and eviction configuration

```java
void flush() throws IOException
void compact() throws IOException
void close() throws IOException
VelqoraMap<K,V> evictAt(int maximumEntries)
```

`maximumEntries` is an entry-count configuration argument. Rejected eviction configuration raises `java.lang.IllegalArgumentException`. Maintenance persistence failures are reported as `java.io.IOException`. A mutation-recording failure is reported as `java.io.UncheckedIOException`; the mutation that first encounters a saving failure can either return normally with deferred failure reporting or throw `UncheckedIOException` immediately.

## `dev.velqoramap.codec.Codec`

Application codecs implement `dev.velqoramap.codec.Codec<T>`:

```java
byte[] encode(T value) throws IOException;
T decode(byte[] bytes) throws IOException;
```

The byte array is the encoded representation of the application key or value. Codec I/O failures use `java.io.IOException`.

## `dev.velqoramap.codec.Utf8StringCodec`

`dev.velqoramap.codec.Utf8StringCodec.INSTANCE` is a `Codec<String>`. Its callable methods are `byte[] encode(String value)` and `String decode(byte[] bytes)`; the exchanged string bytes are UTF-8.

## `velqoramap.log`

The persistence directory contains the binary file `velqoramap.log`.

A value record has this consecutive byte layout:

```text
<key-byte-count:int32><encoded-key:bytes><value-byte-count:int32><encoded-value:bytes>
```

Each `int32` is a signed four-byte big-endian integer. Byte counts describe the immediately following encoded field. Records are concatenated without an enclosing header or record count. Key and value bytes are exchanged through their supplied codecs.

A deletion record has the same key field followed by the signed value-length marker `-1`, with no value bytes.

## `dev.velqoramap.query.Schema`

`dev.velqoramap.query.Schema<T>` exposes `static <T> Schema.Builder<T> builder()`. The resulting schema is passed with an application map to a catalog.

## `dev.velqoramap.query.Schema.Builder`

The schema builder exposes:

```java
Schema.Builder<T> column(String name, Function<T, ?> reader)
Schema<T> build()
```

`name` is a column name; `reader` accepts an application value and returns that column's value as an object, including `null`. `column` supports chained calls.

## `dev.velqoramap.query.Catalog`

`dev.velqoramap.query.Catalog` has a public no-argument constructor and these chained registration methods:

```java
<K,V> Catalog add(String name, Map<K,V> data, Schema<V> schema)
Catalog index(String table, String column)
```

`name` identifies the table; `data` is its application map; `schema` supplies its column readers. `table` and `column` identify an index target. Rejected index configuration raises `java.lang.IllegalArgumentException`.

## `dev.velqoramap.query.QueryEngine`

`dev.velqoramap.query.QueryEngine` is constructed as `new QueryEngine(Catalog catalog)` and exposes:

```java
QueryResult query(String sql)
QueryResult query(String sql, Map<String,?> parameters)
Iterable<Map<String,Object>> stream(String sql, Map<String,?> parameters)
```

`sql` is the query text. Parameter-map keys are binding names without the leading `:`; values are Java application objects, including `null`. A refused query is carried by `java.lang.IllegalArgumentException`, including subclasses. The carrier can be observed at the call or while obtaining and consuming its result.

```java
Iterable<Map<String,Object>> scan(String table, String alias)
Map<String,Object> lookup(String table, String alias, Object key)
```

`table` is a catalog table name and `alias` is the caller's qualifier. Scan rows and a present lookup row have keys `<alias>._key` and `<alias>.<column>`, carrying the map key and schema column values. Lookup absence is returned as `null`.

## `dev.velqoramap.query.QueryResult`

`dev.velqoramap.query.QueryResult.rows()` returns `List<Map<String,Object>>`. List elements are result rows; each map associates a result field name with its value, including `null`. List position carries result sequence. Refused list or row-map modifications raise `java.lang.UnsupportedOperationException`.

The list exposes the standard Java `List` entries `get(int)`, `size()`, `iterator()`, `add(Map<String,Object>)`, `addAll(Collection<? extends Map<String,Object>>)`, `set(int, Map<String,Object>)`, `remove(int)`, `removeIf(Predicate<? super Map<String,Object>>)`, and `clear()`.

Row mappings expose the standard Java `Map` entries `get(Object)`, `keySet()`, `values()`, `entrySet()`, `forEach(BiConsumer<? super String,? super Object>)`, `put(String,Object)`, `putAll(Map<? extends String,?>)`, `replace(String,Object)`, `remove(Object)`, and `clear()`. Key and value views expose `remove(Object)`. Row-map entries expose `setValue(Object)`. Iterators expose `hasNext()`, `next()`, and `remove()`.

## `SELECT`

### Query text syntax

The query-text form is:

```text
SELECT <selection> FROM <table> [<table-alias>]
  [JOIN <table> <table-alias> ON <column-reference> = <column-reference>] ...
  [WHERE <predicate>]
  [GROUP BY <column-reference> [, <column-reference>] ...]
  [ORDER BY <ordering-term> [, <ordering-term>] ...]
  [LIMIT <integer>]
```

Square brackets and angle brackets above are notation, not literal characters. A selection is `*` or comma-separated column references and aggregate expressions; selected expressions can be followed by `AS <output-alias>`. A column reference is `<column>` or `<table-or-alias>.<column>`. The map-key column is `_key`.

A predicate uses comparisons with `=`, `!=`, `>`, `>=`, `<`, or `<=`, and can contain `AND`, `OR`, and parenthesized predicates. Operand syntax includes column references, single-quoted string literals, integer and decimal literals with an optional leading minus sign, `true`, `false`, `NULL`, and `:<binding-name>`.

An ordering term is a column reference or output alias, optionally followed by `ASC` or `DESC`. Aggregate expression spellings are `COUNT(*)`, `COUNT(<column-reference>)`, `SUM(<column-reference>)`, `AVG(<column-reference>)`, `MIN(<column-reference>)`, and `MAX(<column-reference>)`.

### Result field names

An explicitly aliased selection has its `<output-alias>` as the result field name. An explicitly selected column without an output alias has its unqualified column name. Wildcard selection over aliased tables has `<alias>._key` and `<alias>.<column>` field names.

A field holds the selected value or aggregate result; local numeric result objects implement `java.lang.Number`. Integral result carriers include `Byte`, `Short`, `Integer`, `Long`, and `java.math.BigInteger`; floating result carriers include `Float`, `Double`, and `java.math.BigDecimal`.

## `dev.velqoramap.http.VelqoraMapHttpServer`

`dev.velqoramap.http.VelqoraMapHttpServer<K,V>` implements `AutoCloseable` and exposes:

```java
static <K,V> VelqoraMapHttpServer.Builder<K,V> builder(
    VelqoraMap<K,V> map, Codec<K> keys, Codec<V> values)
static VelqoraMapHttpServer.Builder<Object,Object> builder()
VelqoraMapHttpServer<K,V> start()
int port()
void close()
```

The first builder accepts the root map and its key and value codecs. `start()` returns the server; `port()` returns its bound listening port.

`VelqoraMapHttpServer<K,V> addFilter(com.sun.net.httpserver.Filter filter)` returns the server. The supplied filter receives a `com.sun.net.httpserver.HttpExchange` and `Filter.Chain` through `doFilter(HttpExchange, Chain) throws IOException`. Request inspection uses `getRequestMethod()`, `getRequestURI().getPath()`, and `getRequestHeaders().getFirst(String)`; response headers are exposed through `getResponseHeaders().set(String, String)`. The filter can continue the exchange with `Chain.doFilter(exchange)`.

Following service closure, requests have a terminal connection failure or an HTTP status in `400`–`599`. For a Java HTTP client, the connection-failure form is an `IOException` containing a `ConnectException`, `java.net.SocketException`, or `EOFException` in its cause chain.

## `dev.velqoramap.http.VelqoraMapHttpServer.Builder`

The HTTP builder methods are:

```java
<MK,MV> VelqoraMapHttpServer.Builder<K,V> map(
    String name, VelqoraMap<MK,MV> map, Codec<MK> keys, Codec<MV> values)
VelqoraMapHttpServer.Builder<K,V> port(int port)
VelqoraMapHttpServer.Builder<K,V> address(InetSocketAddress address)
VelqoraMapHttpServer.Builder<K,V> queries(QueryEngine queries)
VelqoraMapHttpServer.Builder<K,V> clusterQueries(QueryEngine queries)
VelqoraMapHttpServer.Builder<K,V> authorize(RequestAuthorizer authorizer)
VelqoraMapHttpServer<K,V> build() throws IOException
```

Configuration methods support chaining. `map` binds a route name to a map and its codecs. `port` and `address` supply the listening endpoint; port `0` requests an allocated port. `queries` accepts the ordinary-query engine, `clusterQueries` the node-query engine, and `authorize` the request policy.

Missing map registration is signaled by `java.lang.IllegalStateException`. Rejected map-name registration is signaled by `java.lang.IllegalArgumentException`. `build()` exposes service construction I/O failure as `java.io.IOException`.

## `dev.velqoramap.http.RequestAuthorizer`

`dev.velqoramap.http.RequestAuthorizer` is a functional interface:

```java
boolean authorize(com.sun.net.httpserver.HttpExchange exchange) throws IOException;
```

The callback receives the request exchange, including application headers through `getRequestHeaders().getFirst(String)`. Its return is the policy decision (`true` for permission, `false` for refusal); `java.io.IOException` is the policy I/O failure carrier.

## `dev.velqoramap.http.BinaryBatchCodec`

`dev.velqoramap.http.BinaryBatchCodec<K,V>` exposes:

```java
new BinaryBatchCodec<K,V>(Codec<K> keys, Codec<V> values)
byte[] encodeEntries(Map<? extends K, ? extends V> entries) throws IOException
Map<K,V> decodeEntries(byte[] bytes) throws IOException
byte[] encodeKeys(Iterable<? extends K> keys) throws IOException
List<K> decodeKeys(byte[] bytes) throws IOException
```

Entry byte arrays use the batch-entry body format; key byte arrays use the batch-key body format. Decoded objects are the application entries or keys.

## `{prefix}/entries/{key}`

The entry resource is `{prefix}/entries/{key}`. The `{key}` path segment is unpadded URL-safe Base64 of the key codec's encoded bytes.

| Method | Request body | Success response |
|---|---|---|
| `GET` | None | `200`, body containing the encoded value bytes. |
| `PUT` | Encoded value bytes | `204`. |
| `DELETE` | None | `204`. |

## `{prefix}/entries`

The batch resource is `{prefix}/entries`.

| Method | Request body | Success response |
|---|---|---|
| `PUT` | Concatenated entry records | `204`. |
| `DELETE` | Concatenated key records | `204`. |

Each entry record is `<key-byte-count:int32><encoded-key:bytes><value-byte-count:int32><encoded-value:bytes>`. Each key record is `<key-byte-count:int32><encoded-key:bytes>`. Counts are signed four-byte big-endian integers measuring the immediately following field in bytes. The body has no enclosing header or record count; an empty batch has an empty body. Payload fields contain the configured application codec bytes.

## `{prefix}/flush`

`POST {prefix}/flush` has no request body. Successful completion returns HTTP `204`.

## `{prefix}/compact`

`POST {prefix}/compact` has no request body. Successful completion returns HTTP `204`.

## `/health`

`GET /health` returns HTTP `200` with a UTF-8 JSON object. The numeric field `size` is the current entry count across the served maps. The named-map form additionally exposes the numeric field `maps`, the number of served maps.

```text
{"size":<entry-count>}
{"size":<entry-count>,"maps":<map-count>}
```

## `/query`

`POST /query` accepts UTF-8 query text in its body. Named bindings are supplied as URL query parameters, with UTF-8 URL-encoded names and text values:

```text
/query?<binding-name>=<encoded-binding-text>&<binding-name>=<encoded-binding-text>
```

A successful response has HTTP status `200` and a UTF-8 JSON body of this form:

```text
{"rows":[{"<result-field-name>":<JSON-value>}, ...]}
```

`rows` is the result-row array. Each row is an object keyed by result field names. Values use JSON strings, numbers, booleans, and `null`.

## `/cluster/scan`

`GET /cluster/scan?table=<encoded-table-name>&alias=<encoded-qualifier>` has no request body. The `table` and `alias` query parameters are UTF-8 URL-encoded text. HTTP `200` carries a complete binary row stream in the `BinaryRowStream` form. Each row has `<qualifier>._key` and `<qualifier>.<column>` fields.

## `/cluster/lookup`

`POST /cluster/lookup?table=<encoded-table-name>&alias=<encoded-qualifier>` takes one key encoded in the `BinaryScalar` form as its request body. The `table` and `alias` query parameters are UTF-8 URL-encoded text. HTTP `200` carries a complete `BinaryRowStream`, containing the lookup result. A returned row has `<qualifier>._key` and `<qualifier>.<column>` fields; absence uses an empty row stream.

## `/cluster/stream`

`POST /cluster/stream` accepts UTF-8 query text as its request body, with named bindings supplied as UTF-8 URL-encoded query-parameter names and text values. HTTP `200` carries a complete `BinaryRowStream` whose row keys are query result field names.

## `dev.velqoramap.cluster.ClusterNode`

`dev.velqoramap.cluster.ClusterNode` is constructed with `new ClusterNode(String name, URI address)`. Its accessors are `String name()` for the node's identity and `URI address()` for its HTTP base address. Node values support equality by their name and address. Rejected node-name configuration raises `java.lang.IllegalArgumentException`.

## `dev.velqoramap.cluster.ClusterTopology`

`dev.velqoramap.cluster.ClusterTopology` exposes:

```java
static ClusterTopology evenly(int partitions, List<ClusterNode> nodes)
static ClusterTopology assigned(List<ClusterNode> nodes, List<String> owners)
int partitions()
List<ClusterNode> nodes()
List<String> owners()
ClusterNode owner(int partition)
ClusterTopology withNodes(List<ClusterNode> nodes)
ClusterTopology reassign(Map<Integer,String> assignments)
ClusterTopology rebalance(List<ClusterNode> nodes)
```

`partitions()` is the partition count; `nodes()` is membership. `owners()` is a list of node names indexed by partition number, and `owner(int)` returns the node for that partition. `assignments` maps partition numbers to owner names. Topology-editing methods return a topology value. Configuration and topology refusals use `java.lang.IllegalArgumentException`.

## `dev.velqoramap.cluster.KeyPartitioner`

`dev.velqoramap.cluster.KeyPartitioner<K>` exposes `new KeyPartitioner<K>(Codec<K> keys, int partitions)` and `int partition(K key)`. The constructor accepts the application key codec and logical-partition count. The result is a zero-based logical-partition index.

## `dev.velqoramap.cluster.ClusterMap`

`dev.velqoramap.cluster.ClusterMap<K,V>` is constructed as:

```java
new ClusterMap<K,V>(String name, Codec<K> keys,
                    ClusterTopology topology, ClusterTransport<K,V> transport)
```

`name` is the served map name, `keys` is the application key codec, and the remaining arguments supply ownership and transport.

| Signature | Return form |
|---|---|
| `V get(K key)` | Value or `null` for absence. |
| `void put(K key, V value)` | Normal completion. |
| `boolean remove(K key)` | Whether an entry was removed. |
| `void putAll(Map<K,V> entries)` | Normal completion. |
| `void removeAll(Collection<K> keys)` | Normal completion. |
| `int partition(K key)` | Logical-partition index. |
| `ClusterNode owner(K key)` | Owning node. |
| `void topology(ClusterTopology topology)` | Configuration completion. |

Rejected topology installation raises `java.lang.IllegalArgumentException`. Owner-access failure raises `java.io.UncheckedIOException`; its `getMessage()` diagnostic includes the affected owner's name.

## `dev.velqoramap.cluster.ClusterTransport`

Application transports implement `dev.velqoramap.cluster.ClusterTransport<K,V>`:

```java
V get(ClusterNode node, String map, K key) throws IOException;
void put(ClusterNode node, String map, K key, V value) throws IOException;
boolean remove(ClusterNode node, String map, K key) throws IOException;
void putAll(ClusterNode node, String map, Map<K,V> entries) throws IOException;
void removeAll(ClusterNode node, String map, Collection<K> keys) throws IOException;
```

The arguments identify the owner, served map, and application keys or values. `get` returns a value or `null` for absence; `remove` returns whether an entry was removed. I/O failures are carried by `java.io.IOException`.

## `dev.velqoramap.cluster.HttpClusterTransport`

`dev.velqoramap.cluster.HttpClusterTransport<K,V>` implements `ClusterTransport<K,V>` and has the constructors:

```java
new HttpClusterTransport<K,V>(Codec<K> keys, Codec<V> values)
new HttpClusterTransport<K,V>(HttpClient client, Codec<K> keys,
                             Codec<V> values, Map<String,String> headers)
```

`client` is a `java.net.http.HttpClient`; codecs describe the exchanged keys and values, and `headers` supplies application HTTP header names and values.

## `dev.velqoramap.query.BinaryScalar`

`dev.velqoramap.query.BinaryScalar` exposes:

```java
static byte[] encode(Object value)
static Object decode(byte[] bytes) throws IOException
```

The decoded object has the Java scalar type designated by the wire tag. Encoding refusal uses `java.lang.IllegalArgumentException`. Decoding failure uses `java.io.IOException`; incomplete input uses its subclass `java.io.EOFException`, while malformed input uses an `IOException` other than `EOFException`.

### Scalar byte form

A scalar consists of one unsigned tag byte followed by the payload below. Multibyte integers use signed big-endian encoding. Text uses UTF-8. A length-prefixed payload starts with its signed four-byte byte count, followed by exactly that many bytes.

| Tag | Java type | Payload |
|---|---|---|
| `0` | `null` | No payload. |
| `1` | `String` | Length-prefixed text bytes. |
| `2` | `Boolean` | One byte: `0` for `false`, `1` for `true`. |
| `3` | `Byte` | Signed 8-bit integer. |
| `4` | `Short` | Signed 16-bit integer. |
| `5` | `Integer` | Signed 32-bit integer. |
| `6` | `Long` | Signed 64-bit integer. |
| `7` | `Float` | Big-endian IEEE 754 binary32. |
| `8` | `Double` | Big-endian IEEE 754 binary64. |
| `9` | `byte[]` | Length-prefixed raw bytes. |
| `10` | `Character` | Length-prefixed text bytes representing the character. |

## `dev.velqoramap.query.BinaryRowStream`

`dev.velqoramap.query.BinaryRowStream` has a public no-argument constructor and exposes:

```java
void write(OutputStream output, Iterable<Map<String,Object>> values) throws IOException
Iterable<Map<String,Object>> read(InputStream input)
```

Each map is a row associating field names with scalar values. `write` sends bytes to the caller's output stream. `read` exposes rows through `Iterator.hasNext()` and `Iterator.next()`.

Writing refusal uses `java.io.IOException`. Reading failure uses `java.io.UncheckedIOException`: its direct cause is `java.io.EOFException` for incomplete input, and another `java.io.IOException` for malformed input. This failure may arise during `read`, iterator creation, or iteration.

### Row-stream byte form

The stream consists of consecutive row frames followed by the single byte `0` as its ending. A row frame starts with byte `1`, then a signed four-byte big-endian field count. Each field consists of a signed four-byte big-endian utf-8 field-name byte count, those name bytes, and one scalar in the `BinaryScalar` form.

```text
<1:byte><field-count:int32>
    <name-byte-count:int32><name:utf-8-bytes><tagged-scalar> ...
...
<0:byte>
```

A row's field names are its mapping keys; frame positions carry row sequence.

## `dev.velqoramap.query.DistributedQueryEngine`

`dev.velqoramap.query.DistributedQueryEngine` exposes:

```java
static DistributedQueryEngine.Builder builder()
DistributedQueryResult query(String sql)
DistributedQueryResult query(String sql, Map<String, ?> parameters)
```

`sql` is query text. Parameter keys are binding names without the leading `:`, and parameter values are Java objects. Local query refusal is carried by `java.lang.IllegalArgumentException`; remote request or transport failure is carried by `java.io.UncheckedIOException`. Failure may be observed at query creation, iterator creation, consumption, or result closure.

## `dev.velqoramap.query.DistributedQueryEngine.Builder`

The distributed-query builder exposes:

```java
DistributedQueryEngine.Builder node(String name, Catalog catalog)
DistributedQueryEngine.Builder node(String name, URI address)
DistributedQueryEngine.Builder header(String name, String value)
DistributedQueryEngine.Builder maxRowsInMemory(int rows)
DistributedQueryEngine.Builder spillDirectory(Path directory)
DistributedQueryEngine build()
```

Configuration methods support chaining. `node` registers a query-node name with an embedded catalog or an HTTP base URI. `header` supplies an application HTTP request header. `maxRowsInMemory` takes a row-count allowance. `spillDirectory` supplies the temporary-storage path.

Rejected empty or duplicate query-node configuration is carried by `java.lang.IllegalStateException`. Rejected query-node names or row-allowance configuration are carried by `java.lang.IllegalArgumentException`. A configuration failure can be raised by the configuration call or `build()`.

## `dev.velqoramap.query.DistributedQueryResult`

`dev.velqoramap.query.DistributedQueryResult` implements `Iterable<Map<String,Object>>` and `AutoCloseable`, with these methods:

```java
long size()
Iterator<Map<String,Object>> iterator()
java.util.stream.Stream<Map<String,Object>> stream()
void close()
```

`size()` is the total result row count. Iteration and the stream expose row mappings from result field names to values, including `null`; iteration position carries result sequence. Refused modifications to a returned mapping through `put`, `remove`, or `Map.Entry.setValue` raise `java.lang.UnsupportedOperationException`. Both the result and its stream expose `close()` for resource release.
