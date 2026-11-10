# Interface Contract

The Python package is imported as `velunara` from the project root. Calls exchange Python objects in the current process. Results are return values or yielded items; failures are Python exceptions.

XML tree inputs use `xml.etree.ElementTree` or `lxml.etree` element/document objects (for example as built by `xml.etree.ElementTree.fromstring` or `lxml.etree.fromstring`), or XPath node objects. Schema inputs interoperate with `xmlschema.XMLSchema10`, `xmlschema.XMLSchema11`, and `xmlschema.xpath.XMLSchemaProxy`; these are caller-supplied schema processor objects.

Expression signatures use XPath sequence-type notation. Expression results use the Python carriers returned by expression evaluation or selection.

Remote text resources are addressed by `http://` and `ftp://` URLs.

All parser versions provide the expression prefix `xml` (`http://www.w3.org/XML/1998/namespace`) without caller bindings. XPath 2.0 and later also provide `xs` (`http://www.w3.org/2001/XMLSchema`) and `fn` (`http://www.w3.org/2005/xpath-functions`); XPath 3.0 and later provide `math` (`http://www.w3.org/2005/xpath-functions/math`), and XPath 3.1 provides `map` (`http://www.w3.org/2005/xpath-functions/map`) and `array` (`http://www.w3.org/2005/xpath-functions/array`).

## `velunara`

Import from `velunara`. Exposed names:

`get_node_tree`, `select`, `iter_select`, `Selector`, `XPath1Parser`, `XPath2Parser`, `XPathContext`, `XPathSchemaContext`, `AbstractSchemaProxy`, `datatypes`, `VelunaraError`, `VelunaraTypeError`, `VelunaraValueError`, `VelunaraNameError`, `VelunaraSyntaxError`, `VelunaraZeroDivisionError`, `VelunaraLocaleError`, `MissingContextError`.

The public integration uses `RegexError`, `translate_pattern`, `install_unicode_data`, and `unicode_version` from this package.

## `datatypes`

Import from `velunara.datatypes`. Exposed names:

`StringProxy`, `BooleanProxy`, `DecimalProxy`, `Float`, `Float10`, `DoubleProxy10`, `Integer`, `NonPositiveInteger`, `NegativeInteger`, `NonNegativeInteger`, `PositiveInteger`, `Byte`, `Short`, `Int`, `Long`, `UnsignedByte`, `UnsignedShort`, `UnsignedInt`, `UnsignedLong`, `NormalizedString`, `XsdToken`, `Language`, `Name`, `NCName`, `NMToken`, `Id`, `Idref`, `Entity`, `NMTokens`, `Idrefs`, `Entities`, `QName`, `Notation`, `Base64Binary`, `HexBinary`, `AnyURI`, `Date`, `Time`, `DateTime`, `DateTimeStamp`, `GregorianYear`, `GregorianYearMonth`, `GregorianMonth`, `GregorianMonthDay`, `GregorianDay`, `Timezone`, `Duration`, `YearMonthDuration`, `DayTimeDuration`, `UntypedAtomic`.

## `velunara.exceptions`

Import from `velunara.exceptions`. Exposed names:

`VelunaraValueError`, `XMLResourceForbidden`.

`XMLResourceForbidden` is the exception carrier for forbidden XML entity declarations.

## `velunara.xpath3`

Import from `velunara.xpath3`. Exposed names:

`XPath30Parser`, `XPath31Parser`.

## `velunara.xpath30`

Import from `velunara.xpath30`. Exposed names:

`XPath30Parser`.

## `velunara.xpath31`

Import from `velunara.xpath31`. Exposed names:

`XPath31Parser`.

## `select`

`velunara.select(root, path, parser=..., fragment=..., item=..., position=..., size=..., variables=..., variable_types=..., namespaces=..., schema=...)` accepts an XML tree or XPath node as `root` (or `None`), an expression `str` as `path`, a parser class, `bool | None` fragment treatment, a context item, integer context position and sequence size, namespace bindings, a schema proxy, variable-value bindings, and variable sequence-type declarations. The options after `path` are supplied by keyword.

The complete result is an atomic Python value or a `list` of selected items; an empty result is `[]`. Node results use XML element, comment, processing-instruction or document objects. Attributes and text are `str`. A singleton atomic selection can be a scalar or a one-item list. Failures use public `VelunaraError` subclasses.

Node selections use a `list`, including a single selected node.

## `iter_select`

`velunara.iter_select(root, path)` returns an iterator of selected items. Element results are XML element objects; text and attributes are `str`; atomic results are Python atomic values. Failures can be raised on invocation or iteration as public `VelunaraError` subclasses.

## `Selector`

`velunara.Selector(path)` accepts an expression `str`. Its `select(root, variables=...)` returns an atomic value or a `list` of selected items. Its `iter_select(root, variables=...)` returns an iterator of selected items. `root` is an XML element; `variables` is a mapping of variable names to values. A singleton atomic result can be scalar or a one-item list; an empty selection is `[]` or an iterator yielding no items. Failures use public `VelunaraError` subclasses and can be raised on invocation or iteration.

Node selections use a `list`, including a single selected node.

## `get_node_tree`

`velunara.get_node_tree(root, namespaces=..., uri=..., fragment=...)` returns an XPath node. `root` is an XML element, XML document or existing XPath node; `namespaces` maps namespace prefixes to URI strings; `uri` is a URI `str`; `fragment` is `bool | None`. Results expose the node attributes described below. Invalid tree input uses `VelunaraTypeError`.

## `XPathNode`

XPath node results expose these attributes:

| Attribute | Form and meaning |
| --- | --- |
| `node_kind` | `str` kind tag: `document`, `element`, `attribute`, `namespace`, `text`, `comment` or `processing-instruction`. |
| `name` | Expanded element/attribute name, namespace prefix, processing-instruction target, or `None` for an unnamed node. Namespaced expanded names use `{<namespace URI>}<local name>`. The default namespace prefix is `None`. |
| `value` | XML object for an element, document, comment or processing instruction; `str` for attribute, namespace and text values. |
| `string_value` | The node's string value as `str`. |
| `parent` | Parent node or `None`. |
| `children` | Indexable `list` of child nodes on element and document nodes. |
| `attributes` | Iterable of attribute nodes on an element node. |
| `namespace_nodes` | Iterable of namespace nodes on an element node. |
| `base_uri` | Base URI `str | None`. |
| `document_uri` | Document URI `str | None`. |
| `elem` | XML element carried by an element-node result. |
| `type_name` | Expanded schema type-name `str` on a typed element-node result. |

XML element objects expose `tag: str`, `attrib: dict[str, str]`, `text: str | None`, `tail: str | None`, length, indexing and child iteration. XML document results expose `getroot()` returning their root element.

## `XPathContext`

`velunara.XPathContext(root=..., namespaces=..., uri=..., item=..., position=..., size=..., schema=..., variables=..., current_dt=..., timezone=..., documents=..., collections=..., default_collection=..., text_resources=..., resource_collections=..., default_resource_collection=..., default_language=...)` constructs a context for expression methods. `root` can also be positional; it is an XML tree, XPath tree or `None`.

| Keyword | Input form |
| --- | --- |
| `namespaces` | Mapping of prefixes to namespace URI strings. |
| `uri` | Document URI string. |
| `item` | XML node or atomic context item. |
| `position`, `size` | Integer context position and sequence size. |
| `schema` | Schema proxy object. |
| `variables` | Mapping of variable-name strings to XPath items or lists of items. Items include atomic values, nodes, and opaque map, array or function items. |
| `current_dt` | Python `datetime.datetime`. |
| `timezone` | Lexical timezone offset string. |
| `documents` | Mapping of URI strings to XML document/tree objects. |
| `collections` | Mapping of URI strings to node lists. |
| `default_collection` | Node list. |
| `text_resources` | Mapping of URI strings to text strings. |
| `resource_collections` | Mapping of URI strings to lists of URI strings. |
| `default_resource_collection` | URI string. |
| `default_language` | Language string. |

The return value is a context object. Invalid context construction uses `VelunaraTypeError`.

## `XPathSchemaContext`

`velunara.XPathSchemaContext(root)` accepts a schema component tree and returns a context accepted by expression methods. Selected schema declarations are the corresponding schema processor component objects.

## `XPath1Parser`

`velunara.XPath1Parser(namespaces=..., strict=...)` constructs a parser. `namespaces` maps prefixes to URI strings; `strict` is `bool`. `parse(source)` accepts an XPath expression `str` and returns an expression object with `evaluate(context)` and `select_results(context)`.

The `source` string uses XPath expression syntax. Axis names are `self`, `child`, `parent`, `ancestor`, `ancestor-or-self`, `descendant`, `descendant-or-self`, `following`, `preceding`, `following-sibling`, `preceding-sibling`, `attribute` and `namespace`, followed by `::` and a node test. Node-test spellings are `node()`, `text()`, `comment()` and `processing-instruction(...)`. Names can be unprefixed, prefix-qualified, or wildcards. Path, focus, predicate and attribute notation uses `/`, `//`, `.`, `..`, `[...]` and `@`. Variable references use `$<name>`; function calls use `<name>(<arguments>)` with comma-separated arguments. Literals are quoted strings or numeric text. Operator spellings include `|`, `+`, `-`, `*`, `div`, `mod`, `and`, `or`, `=`, `!=`, `<`, `<=`, `>` and `>=`. Expanded names in the non-strict input form use `{<URI>}<local name>`.

## `XPath2Parser`

`velunara.XPath2Parser(namespaces=..., strict=..., compatibility_mode=..., default_collation=..., default_namespace=..., xsd_version=..., schema=..., base_uri=..., variable_types=..., document_types=..., collection_types=..., default_collection_type=...)` constructs a parser. `namespaces` maps prefixes to URI strings; `strict` and `compatibility_mode` are booleans; `default_collation`, `default_namespace`, `xsd_version` and `base_uri` are strings; `schema` is a schema proxy. `variable_types`, `document_types` and `collection_types` map names or URIs to sequence-type strings; `default_collection_type` is a sequence-type string. `parse(source)` accepts an expression `str` and returns an expression object with `evaluate(context)` and `select_results(context)`.

`external_function(callback, name=..., prefix=..., sequence_types=...)` accepts a Python callable, optional function-name and namespace-prefix strings, and a tuple of sequence-type strings: the final entry describes the return type; preceding entries describe arguments. `ValueError` identifies a name or duplicate-registration failure; `KeyError` identifies an unresolved registration prefix.

`schema_constructor(atomic_type_name)` accepts an expanded type-name string `{<namespace URI>}<local name>` for a constructor used in expressions. Invalid configuration uses `VelunaraValueError`; an invalid schema argument uses `TypeError`.

Expression strings additionally use parenthesized comma-separated sequences, `()`, `(: ... :)` comments, `to`, `for $<name> in <expression> return <expression>`, `some`/`every` with `satisfies`, `if (...) then ... else ...`, `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `is`, `<<`, `>>`, `intersect`, `except`, `idiv`, `instance of`, `treat as`, `cast as` and `castable as`. Sequence types use datatype names, `item()`, `node()`, `element(...)`, `attribute(...)`, `document-node(...)`, `empty-sequence()`, and occurrence suffixes `?`, `*` or `+`. Schema node tests are `schema-element(...)` and `schema-attribute(...)`. Datatype constructor calls are written `xs:<datatype name>(<value>)`.

## `XPath30Parser`

`XPath30Parser` is importable from `velunara.xpath30` and `velunara.xpath3`. Construction accepts the keyword inputs of `XPath2Parser`, plus `decimal_formats`, `defuse_xml`, `allow_environment` and `allow_external_resources`.

`decimal_formats` maps format-name strings to mappings of symbol-name strings to strings. Symbol keys at this interface are `decimal-separator`, `grouping-separator`, `minus-sign`, `percent`, `infinity` and `NaN`. `defuse_xml` is a boolean XML-protection choice. `allow_environment` and `allow_external_resources` accept `bool | list[str]`; entries are environment-name permissions or resource URI prefixes, respectively. An environment name-prefix permission uses `<prefix>*`. Invalid policy input types use `VelunaraTypeError`.

`parse(source)`, `external_function(callback, name=..., prefix=..., sequence_types=...)` and `schema_constructor(atomic_type_name)` have the calling forms described for `XPath2Parser`. Expression objects provide `evaluate(context)` and `select_results(context)`.

Expression strings additionally use `let $<name> := <expression> return <expression>`, `!`, `||`, URI-qualified names `Q{<URI>}<local name>`, `namespace-node()`, `function(*)` and typed function tests, `<function name>#<arity>`, `function(<parameters>) as <type> {<body>}`, dynamic function calls, and `?` argument placeholders. Mathematical function names use the `math:` prefix.

## `XPath31Parser`

`XPath31Parser` is importable from `velunara.xpath31` and `velunara.xpath3`. Construction accepts the keyword inputs of `XPath2Parser` and `XPath30Parser`. `parse(source)`, `external_function(callback, name=..., prefix=..., sequence_types=...)` and `schema_constructor(atomic_type_name)` have those same calling forms. Expression objects provide `evaluate(context)` and `select_results(context)`.

Expression strings additionally use `map{<key>:<value>, ...}`, `[<members>]`, `array{<expression>}`, `map(*)` and `array(*)` type tests, `?<key>`, `?(<expression>)` and `?*` lookup, and `=>` arrow calls. Maps and arrays are consumed through these expression forms and their named functions.

## `XPathToken`

Expression objects returned by `parse(source)` expose:

- `evaluate(context)` returns an atomic value or a `list` of XPath items. XPath nodes in this form are node objects; atomic items use Python `str`, `bool`, `int`, `float`, `decimal.Decimal` or public datatype objects. A present scalar-valued atomic result is returned directly; sequence-valued expressions return lists, including for a singleton sequence. Serialized text is a `str` result.
- `select_results(context)` returns an iterator of result items. With an XML context, element, comment, processing-instruction and representable document results are XML objects, while attributes and text are strings. A namespace result in XPath 1.0 is a `(prefix, URI)` tuple. Atomic values are yielded directly. Map, array and other function items are yielded as opaque Python objects accepted as context variable values. An empty selection yields no items.

`context` is an evaluation context or `None`. Public failures can be raised by `parse`, `evaluate`, `select_results` invocation or iterator consumption.

## `VelunaraError`

`velunara.VelunaraError` is the base exception for XPath failures. `code` carries a qualified error identity `str`, in the form `err:<local error name>` for standard XPath errors. Caller-supplied error identities use `<prefix>:<local name>`. `message` carries the description `str` supplied by an explicit error expression.

| Local error name | Failure identity | Exception carrier |
| --- | --- | --- |
| `XPST0003` | Expression syntax failure | `VelunaraSyntaxError` |
| `XPST0017` | Function name or argument-count failure | `VelunaraTypeError` |
| `XPST0008` | Unbound variable | `VelunaraNameError` |
| `XPST0081` | Unbound namespace prefix | `VelunaraNameError` |
| `XPDY0002` | Missing dynamic context | `MissingContextError` |
| `XPDY0050` | Declared sequence-type mismatch | `VelunaraTypeError` |
| `XPTY0004` | Operand, argument or result type mismatch | `VelunaraTypeError` |
| `FORG0001` | Lexical conversion failure | `VelunaraValueError` |
| `FOAR0001` | Division by zero | `VelunaraZeroDivisionError` |
| `FORG0003` | Zero-or-one cardinality failure | `VelunaraValueError` |
| `FORG0004` | One-or-more cardinality failure | `VelunaraValueError` |
| `FORG0005` | Exactly-one cardinality failure | `VelunaraValueError` |
| `FORX0001` | Regular-expression flag failure | `VelunaraValueError` |
| `FORX0002` | Regular-expression pattern failure | `VelunaraValueError` |
| `FORX0003` | Forbidden zero-length regular-expression match | `VelunaraValueError` |
| `FORX0004` | Regular-expression replacement failure | `VelunaraValueError` |
| `FOCH0002` | Unsupported collation | `VelunaraLocaleError` |
| `FOER0000` | Explicit error identity | `VelunaraError` |
| `FODF1310` | Invalid formatting picture | `VelunaraValueError` |
| `FODF1280` | Unknown decimal format | `VelunaraValueError` |
| `FOFD1340` | Invalid calendar picture | `VelunaraValueError` |
| `FOFD1350` | Unavailable calendar component | `VelunaraValueError` |
| `FODC0002` | Unavailable document or collection | `VelunaraValueError` |
| `FODC0004` | Collection URI failure | `VelunaraValueError` |
| `FODC0006` | XML parsing failure | `VelunaraValueError` |
| `FOUT1170` | Text or JSON resource-access failure | `VelunaraValueError` |
| `FOUT1190` | Text decoding or character failure | `VelunaraValueError` |
| `XQDY0137` | Duplicate map-constructor key | `VelunaraError` |
| `FOAY0001` | Array index failure | `VelunaraError` |
| `FOAY0002` | Negative array length failure | `VelunaraError` |
| `FOAP0001` | Function application arity failure | `VelunaraError` |
| `FORG0006` | Invalid argument type | `VelunaraError` |
| `FORG0010` | Invalid Internet date string | `VelunaraError` |
| `FOCH0001` | Code point not valid | `VelunaraError` |
| `FOCH0003` | Unsupported normalization form | `VelunaraError` |
| `FOJS0001` | JSON syntax failure | `VelunaraError` |
| `FOJS0003` | Duplicate JSON or map-entry failure | `VelunaraError` |
| `FOJS0005` | JSON option failure | `VelunaraError` |
| `SENR0001` | XML item-serialization failure | `VelunaraTypeError` |
| `SEPM0019` | Duplicate serialization parameter | `VelunaraValueError` |
| `SEPM0017` | Invalid XML serialization parameter | `VelunaraValueError` |
| `SEPM0016` | Invalid character-map key | `VelunaraValueError` |
| `SERE0023` | JSON serialization cardinality failure | `VelunaraTypeError` |
| `SERE0020` | JSON serialization numeric failure | `VelunaraTypeError` |
| `SERE0021` | JSON function-item serialization failure | `VelunaraTypeError` |

## `VelunaraTypeError`

`velunara.VelunaraTypeError` is a public `VelunaraError` subclass identifying a type or input-kind failure. It exposes the `code` error-identity attribute.

## `VelunaraValueError`

`velunara.VelunaraValueError` is a public `VelunaraError` subclass identifying a value or configuration failure. It exposes the `code` error-identity attribute.

## `VelunaraSyntaxError`

`velunara.VelunaraSyntaxError` is a public `VelunaraError` subclass identifying a expression syntax failure. It exposes the `code` error-identity attribute.

## `VelunaraNameError`

`velunara.VelunaraNameError` is a public `VelunaraError` subclass identifying a name-resolution failure. It exposes the `code` error-identity attribute.

## `VelunaraZeroDivisionError`

`velunara.VelunaraZeroDivisionError` is a public `VelunaraError` subclass identifying a division-by-zero failure. It exposes the `code` error-identity attribute.

## `VelunaraLocaleError`

`velunara.VelunaraLocaleError` is a public `VelunaraError` subclass identifying a collation failure. It exposes the `code` error-identity attribute.

## `MissingContextError`

`velunara.MissingContextError` is a public `VelunaraError` subclass identifying a missing-context failure. It exposes the `code` error-identity attribute.

## `XMLResourceForbidden`

`velunara.exceptions.XMLResourceForbidden` identifies XML resource protection refusal.

## `StringProxy`

`velunara.datatypes.StringProxy(value)` accepts a lexical `str` and returns a Python `str`-compatible value. String equality is available. `StringProxy.validate(value)` accepts lexical input or a constructed value; success returns normally.

## `BooleanProxy`

`velunara.datatypes.BooleanProxy(value)` accepts a lexical `str` and returns a Python `bool` value. Numeric equality and ordering are available. `BooleanProxy.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `DecimalProxy`

`velunara.datatypes.DecimalProxy(value)` accepts a lexical `str` and returns a Python `decimal.Decimal`-compatible value. Numeric equality and ordering are available. `DecimalProxy.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `Float`

`velunara.datatypes.Float(value)` accepts a lexical `str` and returns a Python `float`-compatible value. Numeric equality and ordering are available. `Float.validate(value)` accepts a constructed floating-point value and returns normally on success; lexical refusal uses `ValueError`. Refused lexical construction or validation uses `ValueError`.

## `Float10`

`velunara.datatypes.Float10(value)` accepts a lexical `str` and returns a Python `float`-compatible value. Numeric equality and ordering are available.

## `DoubleProxy10`

`velunara.datatypes.DoubleProxy10(value)` accepts a lexical `str` and returns a Python `float`-compatible value. Numeric equality and ordering are available. `DoubleProxy10.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `Integer`

`velunara.datatypes.Integer(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `Integer.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `NonPositiveInteger`

`velunara.datatypes.NonPositiveInteger(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `NonPositiveInteger.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `NegativeInteger`

`velunara.datatypes.NegativeInteger(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `NegativeInteger.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `NonNegativeInteger`

`velunara.datatypes.NonNegativeInteger(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `NonNegativeInteger.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `PositiveInteger`

`velunara.datatypes.PositiveInteger(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `PositiveInteger.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `Byte`

`velunara.datatypes.Byte(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `Byte.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `Short`

`velunara.datatypes.Short(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `Short.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `Int`

`velunara.datatypes.Int(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `Int.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `Long`

`velunara.datatypes.Long(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `Long.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `UnsignedByte`

`velunara.datatypes.UnsignedByte(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `UnsignedByte.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `UnsignedShort`

`velunara.datatypes.UnsignedShort(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `UnsignedShort.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `UnsignedInt`

`velunara.datatypes.UnsignedInt(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `UnsignedInt.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `UnsignedLong`

`velunara.datatypes.UnsignedLong(value)` accepts a lexical `str` and returns a Python `int`-compatible value. Numeric equality and ordering are available. `UnsignedLong.validate(value)` accepts lexical input or a constructed value; success returns normally. Refused lexical construction or validation uses `ValueError`.

## `NormalizedString`

`velunara.datatypes.NormalizedString(value)` accepts lexical `str` and returns a `str`-compatible value readable by `str(instance)` and equality. `NormalizedString.validate(value)` accepts lexical input and returns normally on success. Refused lexical input uses `ValueError`.

## `XsdToken`

`velunara.datatypes.XsdToken(value)` accepts lexical `str` and returns a `str`-compatible value readable by `str(instance)` and equality. `XsdToken.validate(value)` accepts lexical input and returns normally on success. Refused lexical input uses `ValueError`.

## `Language`

`velunara.datatypes.Language(value)` accepts lexical `str` and returns a `str`-compatible value readable by `str(instance)` and equality. `Language.validate(value)` accepts lexical input and returns normally on success. Refused lexical input uses `ValueError`.

## `Name`

`velunara.datatypes.Name(value)` accepts lexical `str` and returns a `str`-compatible value readable by `str(instance)` and equality. `Name.validate(value)` accepts lexical input and returns normally on success. Refused lexical input uses `ValueError`.

## `NCName`

`velunara.datatypes.NCName(value)` accepts lexical `str` and returns a `str`-compatible value readable by `str(instance)` and equality. `NCName.validate(value)` accepts lexical input and returns normally on success. Refused lexical input uses `ValueError`.

## `NMToken`

`velunara.datatypes.NMToken(value)` accepts lexical `str` and returns a `str`-compatible value readable by `str(instance)` and equality. `NMToken.validate(value)` accepts lexical input and returns normally on success. Refused lexical input uses `ValueError`.

## `Id`

`velunara.datatypes.Id(value)` accepts lexical `str` and returns a `str`-compatible value readable by `str(instance)` and equality. `Id.validate(value)` accepts lexical input and returns normally on success. Refused lexical input uses `ValueError`.

## `Idref`

`velunara.datatypes.Idref(value)` accepts lexical `str` and returns a `str`-compatible value readable by `str(instance)` and equality. `Idref.validate(value)` accepts lexical input and returns normally on success. Refused lexical input uses `ValueError`.

## `Entity`

`velunara.datatypes.Entity(value)` accepts lexical `str` and returns a `str`-compatible value readable by `str(instance)` and equality. `Entity.validate(value)` accepts lexical input and returns normally on success. Refused lexical input uses `ValueError`.

## `NMTokens`

`velunara.datatypes.NMTokens.decode(value)` accepts lexical `str` and returns a list of typed string items. `NMTokens(value)` accepts that list and returns an iterable list value. `NMTokens.validate(value)` accepts an item list and returns normally on success. `item_type` is the item class, callable with a lexical string. Items support `str(item)`. Refusal uses `ValueError`.

## `Idrefs`

`velunara.datatypes.Idrefs.decode(value)` accepts lexical `str` and returns a list of typed string items. `Idrefs(value)` accepts that list and returns an iterable list value. `Idrefs.validate(value)` accepts an item list and returns normally on success. `item_type` is the item class, callable with a lexical string. Items support `str(item)`. Refusal uses `ValueError`.

## `Entities`

`velunara.datatypes.Entities.decode(value)` accepts lexical `str` and returns a list of typed string items. `Entities(value)` accepts that list and returns an iterable list value. `Entities.validate(value)` accepts an item list and returns normally on success. `item_type` is the item class, callable with a lexical string. Items support `str(item)`. Refusal uses `ValueError`.

## `QName`

Expression call: `QName(xs:string?, xs:string) -> xs:QName`.

## `Notation`

`velunara.datatypes.Notation.validate(value)` accepts a lexical qualified-name `str`. Successful validation returns normally; lexical refusal uses `ValueError`.

## `Base64Binary`

`velunara.datatypes.Base64Binary(value)` accepts lexical `str` or `bytes`, or a binary datatype instance. `decode()` returns decoded `bytes`. `Base64Binary.encoder(value)` accepts raw `bytes` and returns lexical `bytes`. `Base64Binary.validate(value)` accepts lexical input; success returns normally. Lexical refusal uses `ValueError`.

## `HexBinary`

`velunara.datatypes.HexBinary(value)` accepts lexical `str` or `bytes`, or a binary datatype instance. `decode()` returns decoded `bytes`. `HexBinary.encoder(value)` accepts raw `bytes` and returns lexical `bytes`. `HexBinary.validate(value)` accepts lexical input; success returns normally. Lexical refusal uses `ValueError`.

## `AnyURI`

`velunara.datatypes.AnyURI(value)` accepts lexical `str`; `str(instance)` exposes its URI string. `AnyURI.validate(value)` accepts lexical strings and returns normally on success. Lexical refusal uses `ValueError`.

## `Date`

`velunara.datatypes.Date.fromstring(datetime_string)` accepts lexical `str` and returns a calendar value. Integer component attributes are `year`, `month`, `day`. `tzinfo` is a timezone object or `None`; a timezone exposes `utcoffset(None)` returning a Python `datetime.timedelta`. Refused lexical input or fields use `ValueError`. `Date(year, month, day)` accepts three integers; year overflow uses `OverflowError`. Addition with `YearMonthDuration` returns a date value exposing `day: int`.

Python form: `date + duration` returns a date value.

## `Time`

`velunara.datatypes.Time.fromstring(datetime_string)` accepts lexical `str` and returns a calendar value. Integer component attributes are `hour`, `minute`, `second`, `microsecond`. `tzinfo` is a timezone object or `None`; a timezone exposes `utcoffset(None)` returning a Python `datetime.timedelta`. Refused lexical input or fields use `ValueError`.

## `DateTime`

`velunara.datatypes.DateTime.fromstring(datetime_string)` accepts lexical `str` and returns a calendar value. Integer component attributes are `year`, `month`, `day`, `hour`, `minute`, `second`, `microsecond`. `tzinfo` is a timezone object or `None`; a timezone exposes `utcoffset(None)` returning a Python `datetime.timedelta`. Refused lexical input or fields use `ValueError`. Addition with `DayTimeDuration` returns a calendar value with integer components. Equality returns `bool`.

Python form: `date_time + duration` returns a calendar value.

## `DateTimeStamp`

`velunara.datatypes.DateTimeStamp.fromstring(datetime_string)` accepts lexical `str` and returns a calendar value. Integer component attributes are `year`, `month`, `day`, `hour`, `minute`, `second`. `tzinfo` is a timezone object or `None`; a timezone exposes `utcoffset(None)` returning a Python `datetime.timedelta`. Refused lexical input or fields use `ValueError`.

## `GregorianYear`

`velunara.datatypes.GregorianYear.fromstring(datetime_string)` accepts lexical `str` and returns a calendar value. Integer component attributes are `year`. `tzinfo` is a timezone object or `None`; a timezone exposes `utcoffset(None)` returning a Python `datetime.timedelta`.

## `GregorianYearMonth`

`velunara.datatypes.GregorianYearMonth.fromstring(datetime_string)` accepts lexical `str` and returns a calendar value. Integer component attributes are `year`, `month`. `tzinfo` is a timezone object or `None`; a timezone exposes `utcoffset(None)` returning a Python `datetime.timedelta`.

## `GregorianMonth`

`velunara.datatypes.GregorianMonth.fromstring(datetime_string)` accepts lexical `str` and returns a calendar value. Integer component attributes are `month`. `tzinfo` is a timezone object or `None`; a timezone exposes `utcoffset(None)` returning a Python `datetime.timedelta`.

## `GregorianMonthDay`

`velunara.datatypes.GregorianMonthDay.fromstring(datetime_string)` accepts lexical `str` and returns a calendar value. Integer component attributes are `month`, `day`. `tzinfo` is a timezone object or `None`; a timezone exposes `utcoffset(None)` returning a Python `datetime.timedelta`.

## `GregorianDay`

`velunara.datatypes.GregorianDay.fromstring(datetime_string)` accepts lexical `str` and returns a calendar value. Integer component attributes are `day`. `tzinfo` is a timezone object or `None`; a timezone exposes `utcoffset(None)` returning a Python `datetime.timedelta`.

## `Timezone`

`velunara.datatypes.Timezone(offset)` accepts a Python `datetime.timedelta`. `utcoffset(None)` returns its offset as `datetime.timedelta`. Invalid offsets use `ValueError`.

## `Duration`

`velunara.datatypes.Duration(months, seconds)` constructs a duration. `months` is an integer month count; `seconds` is `int | decimal.Decimal`. `Duration.fromstring(text)` accepts lexical `str` and returns a duration. Result fields are `months`, `seconds`, represented as `int` for months and `decimal.Decimal` for seconds. Equality and ordering return `bool`. Invalid components use `ValueError`; component overflow uses `OverflowError`.

Python forms: `left == right` and `left < right` return `bool`.

## `YearMonthDuration`

`velunara.datatypes.YearMonthDuration(months)` constructs a duration. The input is an integer month count. `YearMonthDuration.fromstring(text)` accepts lexical `str` and returns a duration. The result field `months` is an `int`. Addition with a year-month duration and multiplication by a number return duration values exposing `months`.

Refused lexical input uses `ValueError`.

Python forms: `left + right` and `duration * number` return year-month durations.

## `DayTimeDuration`

`velunara.datatypes.DayTimeDuration(seconds)` constructs a duration. The input is `int | decimal.Decimal` seconds. `DayTimeDuration.fromstring(text)` accepts lexical `str` and returns a duration. The result field `seconds` is a `decimal.Decimal`. Multiplication by a number returns a duration exposing `seconds`; division by a day-time duration returns `decimal.Decimal`.

Refused lexical input uses `ValueError`.

Python forms: `duration * number` returns a day-time duration; `left / right` returns the numeric duration ratio.

## `UntypedAtomic`

`velunara.datatypes.UntypedAtomic(value)` accepts lexical `str`. `value` and `str(instance)` expose lexical strings. Python `int` and `float` conversions return numbers. Equality and ordering return `bool`; addition, reverse subtraction and multiplication with numbers return numeric values. Failed numeric lexical conversion uses `ValueError`. Instances can be supplied in context variable bindings.

Python forms include `instance + number`, `number - instance`, `instance < value`, `instance > value` and `instance == value`. The corresponding results use numeric or boolean Python values.

## `translate_pattern`

`velunara.translate_pattern(pattern, flags=..., xsd_version=..., back_references=..., lazy_quantifiers=..., anchors=...)` accepts a pattern `str`, integer Python regular-expression flags, a schema-version string and boolean extension controls. It returns a `str` accepted by `re.compile`, with captures accessible through compiled match objects. Translation refusal uses `velunara.RegexError`.

## `RegexError`

`velunara.RegexError` identifies regular-expression translation refusal.

## `install_unicode_data`

`velunara.install_unicode_data(version=..., name_or_url=...)` accepts an optional version string and optional data-location string; both can be positional. A location can be a local file URI carrying Unicode Character Database `UnicodeData.txt` records with semicolon-separated fields. Invocation without arguments is also supported. Success returns normally. `ValueError` identifies an invalid version; `TypeError` identifies incomplete data-source configuration.

## `unicode_version`

`velunara.unicode_version()` returns the active Unicode database version as a dotted `str`: `<major>.<minor>.<patch>`.

## `AbstractSchemaProxy`

`velunara.AbstractSchemaProxy.bind_parser(self, parser)` accepts an XPath parser on a concrete schema proxy. It is also accessible as an unbound method for a concrete subclass.

| Call | Result form |
| --- | --- |
| `get_type(qname)` | Schema type declaration or `None`. |
| `get_element(qname)` | Schema element declaration or `None`. |
| `get_attribute(qname)` | Schema attribute declaration or `None`. |
| `is_instance(obj, type_qname)` | `bool` type-membership result. |
| `cast_as(obj, type_qname)` | Converted atomic value. |

Type and declaration names are expanded-name strings `{<namespace URI>}<local name>`. Declaration results are the schema processor's declaration objects. Unknown conversion types use `KeyError`; invalid conversion values use `ValueError` or `TypeError`. Concrete proxies are accepted through the `schema` keyword of parser and context constructors.

## `last`

Expression call: `last() -> xs:integer`.

## `position`

Expression call: `position() -> xs:integer`.

## `count`

Expression call: `count(item()*) -> xs:integer`.

## `id`

Expression call: `id(xs:string*) -> element()*`.

## `name`

Expression call: `name() -> xs:string`; `name(node()?) -> xs:string`.

## `local-name`

Expression call: `local-name(node()?) -> xs:string`.

## `namespace-uri`

Expression call: `namespace-uri(node()?) -> xs:anyURI`.

## `string`

Expression call: `string() -> xs:string`; `string(item()?) -> xs:string`.

## `contains`

Expression call: `contains(xs:string?, xs:string?) -> xs:boolean`.

## `concat`

Expression call: `concat(xs:anyAtomicType?, xs:anyAtomicType?, ...) -> xs:string`. Arguments after the first two repeat the same positional input form.

## `string-length`

Expression call: `string-length(xs:string?) -> xs:integer`.

## `normalize-space`

Expression call: `normalize-space(xs:string?) -> xs:string`.

## `starts-with`

Expression call: `starts-with(xs:string?, xs:string?) -> xs:boolean`.

## `translate`

Expression call: `translate(xs:string?, xs:string, xs:string) -> xs:string`.

## `substring`

Expression call: `substring(xs:string?, xs:double) -> xs:string`; `substring(xs:string?, xs:double, xs:double) -> xs:string`.

## `substring-before`

Expression call: `substring-before(xs:string?, xs:string?) -> xs:string`.

## `substring-after`

Expression call: `substring-after(xs:string?, xs:string?) -> xs:string`.

## `boolean`

Expression call: `boolean(item()*) -> xs:boolean`.

## `not`

Expression call: `not(item()*) -> xs:boolean`.

## `true`

Expression call: `true() -> xs:boolean`.

## `false`

Expression call: `false() -> xs:boolean`.

## `lang`

Expression call: `lang(xs:string?) -> xs:boolean`.

## `number`

Expression call: `number() -> xs:double`; `number(xs:anyAtomicType?) -> xs:double`.

## `sum`

Expression call: `sum(xs:anyAtomicType*) -> xs:anyAtomicType?`.

## `ceiling`

Expression call: `ceiling(xs:numeric?) -> xs:numeric?`.

## `floor`

Expression call: `floor(xs:numeric?) -> xs:numeric?`.

## `round`

Expression call: XPath 1.0: `round(xs:numeric?) -> xs:numeric?`; XPath 3.0: `round(xs:numeric?) -> xs:numeric?`; XPath 3.0: `round(xs:numeric?, xs:integer) -> xs:numeric?`.

## `prefix-from-QName`

Expression call: `prefix-from-QName(xs:QName?) -> xs:NCName?`.

## `local-name-from-QName`

Expression call: `local-name-from-QName(xs:QName?) -> xs:NCName?`.

## `namespace-uri-from-QName`

Expression call: `namespace-uri-from-QName(xs:QName?) -> xs:anyURI?`.

## `namespace-uri-for-prefix`

Expression call: `namespace-uri-for-prefix(xs:string?, element()) -> xs:anyURI?`.

## `in-scope-prefixes`

Expression call: `in-scope-prefixes(element()) -> xs:string*`.

## `resolve-QName`

Expression call: `resolve-QName(xs:string?, element()) -> xs:QName?`.

## `node-name`

Expression call: `node-name(node()?) -> xs:QName?`.

## `nilled`

Expression call: `nilled(node()?) -> xs:boolean?`.

## `data`

Expression call: `data(item()*) -> xs:anyAtomicType*`.

## `base-uri`

Expression call: `base-uri(node()?) -> xs:anyURI?`.

## `document-uri`

Expression call: `document-uri(node()?) -> xs:anyURI?`.

## `round-half-to-even`

Expression call: `round-half-to-even(xs:numeric?) -> xs:numeric?`.

## `abs`

Expression call: `abs(xs:numeric?) -> xs:numeric?`.

## `avg`

Expression call: `avg(xs:anyAtomicType*) -> xs:anyAtomicType?`.

## `max`

Expression call: `max(xs:anyAtomicType*) -> xs:anyAtomicType?`.

## `min`

Expression call: `min(xs:anyAtomicType*) -> xs:anyAtomicType?`.

## `empty`

Expression call: `empty(item()*) -> xs:boolean`.

## `exists`

Expression call: `exists(item()*) -> xs:boolean`.

## `distinct-values`

Expression call: `distinct-values(xs:anyAtomicType*) -> xs:anyAtomicType*`.

## `insert-before`

Expression call: `insert-before(item()*, xs:integer, item()*) -> item()*`.

## `index-of`

Expression call: `index-of(xs:anyAtomicType*, xs:anyAtomicType) -> xs:integer*`.

## `remove`

Expression call: `remove(item()*, xs:integer) -> item()*`.

## `reverse`

Expression call: `reverse(item()*) -> item()*`.

## `subsequence`

Expression call: `subsequence(item()*, xs:double, xs:double) -> item()*`.

## `unordered`

Expression call: `unordered(item()*) -> item()*`.

## `zero-or-one`

Expression call: `zero-or-one(item()*) -> item()?`.

## `one-or-more`

Expression call: `one-or-more(item()*) -> item()+`.

## `exactly-one`

Expression call: `exactly-one(item()*) -> item()`.

## `deep-equal`

Expression call: `deep-equal(item()*, item()*) -> xs:boolean`.

## `matches`

Expression call: `matches(xs:string?, xs:string) -> xs:boolean`; `matches(xs:string?, xs:string, xs:string) -> xs:boolean`.

The selected value is a Python `bool`. The `flags` argument is a string of flag characters: `i`, `m`, `s`, `x` and, for XPath 3.0, `q`.

Positional arguments are the input text, regular-expression pattern and optional flag string.

## `replace`

Expression call: `replace(xs:string?, xs:string, xs:string) -> xs:string`; `replace(xs:string?, xs:string, xs:string, xs:string) -> xs:string`.

The evaluated value is a Python `str` carrying replacement text. Replacement capture references are written `$<group number>`. The optional flags use the same lexical form as `matches`.

Positional arguments are the input text, regular-expression pattern, replacement text and optional flag string.

## `tokenize`

Expression call: `tokenize(xs:string?, xs:string) -> xs:string*`; `tokenize(xs:string?, xs:string, xs:string) -> xs:string*`.

Selected items are Python `str` tokens, carried by the expression result sequence or its iterator. The optional flags use the same lexical form as `matches`.

Positional arguments are the input text, separator pattern and optional flag string.

## `resolve-uri`

Expression call: `resolve-uri(xs:string?) -> xs:anyURI?`; `resolve-uri(xs:string?, xs:string) -> xs:anyURI?`.

## `codepoints-to-string`

Expression call: `codepoints-to-string(xs:integer*) -> xs:string`.

## `string-to-codepoints`

Expression call: `string-to-codepoints(xs:string?) -> xs:integer*`.

## `compare`

Expression call: `compare(xs:string?, xs:string?) -> xs:integer?`; `compare(xs:string?, xs:string?, xs:string) -> xs:integer?`.

## `codepoint-equal`

Expression call: `codepoint-equal(xs:string?, xs:string?) -> xs:boolean?`.

## `string-join`

Expression call: XPath 2.0: `string-join(xs:string*, xs:string) -> xs:string`; XPath 3.0: `string-join(xs:string*) -> xs:string`; XPath 3.0: `string-join(xs:string*, xs:string) -> xs:string`; XPath 3.1: `string-join(xs:anyAtomicType*) -> xs:string`; XPath 3.1: `string-join(xs:anyAtomicType*, xs:string) -> xs:string`.

## `normalize-unicode`

Expression call: `normalize-unicode(xs:string?, xs:string) -> xs:string`.

## `upper-case`

Expression call: `upper-case(xs:string?) -> xs:string`.

## `lower-case`

Expression call: `lower-case(xs:string?) -> xs:string`.

## `encode-for-uri`

Expression call: `encode-for-uri(xs:string?) -> xs:string`.

## `iri-to-uri`

Expression call: `iri-to-uri(xs:string?) -> xs:string`.

## `escape-html-uri`

Expression call: `escape-html-uri(xs:string?) -> xs:string`.

## `ends-with`

Expression call: `ends-with(xs:string?, xs:string?) -> xs:boolean`.

## `years-from-duration`

Expression call: `years-from-duration(xs:duration?) -> xs:integer?`.

## `months-from-duration`

Expression call: `months-from-duration(xs:duration?) -> xs:integer?`.

## `days-from-duration`

Expression call: `days-from-duration(xs:duration?) -> xs:integer?`.

## `hours-from-duration`

Expression call: `hours-from-duration(xs:duration?) -> xs:integer?`.

## `minutes-from-duration`

Expression call: `minutes-from-duration(xs:duration?) -> xs:integer?`.

## `seconds-from-duration`

Expression call: `seconds-from-duration(xs:duration?) -> xs:decimal?`.

## `year-from-dateTime`

Expression call: `year-from-dateTime(xs:dateTime?) -> xs:integer?`.

## `month-from-dateTime`

Expression call: `month-from-dateTime(xs:dateTime?) -> xs:integer?`.

## `day-from-dateTime`

Expression call: `day-from-dateTime(xs:dateTime?) -> xs:integer?`.

## `hours-from-dateTime`

Expression call: `hours-from-dateTime(xs:dateTime?) -> xs:integer?`.

## `minutes-from-dateTime`

Expression call: `minutes-from-dateTime(xs:dateTime?) -> xs:integer?`.

## `seconds-from-dateTime`

Expression call: `seconds-from-dateTime(xs:dateTime?) -> xs:decimal?`.

## `timezone-from-dateTime`

Expression call: `timezone-from-dateTime(xs:dateTime?) -> xs:dayTimeDuration?`.

## `year-from-date`

Expression call: `year-from-date(xs:date?) -> xs:integer?`.

## `month-from-date`

Expression call: `month-from-date(xs:date?) -> xs:integer?`.

## `day-from-date`

Expression call: `day-from-date(xs:date?) -> xs:integer?`.

## `timezone-from-date`

Expression call: `timezone-from-date(xs:date?) -> xs:dayTimeDuration?`.

## `hours-from-time`

Expression call: `hours-from-time(xs:time?) -> xs:integer?`.

## `minutes-from-time`

Expression call: `minutes-from-time(xs:time?) -> xs:integer?`.

## `seconds-from-time`

Expression call: `seconds-from-time(xs:time?) -> xs:decimal?`.

## `timezone-from-time`

Expression call: `timezone-from-time(xs:time?) -> xs:dayTimeDuration?`.

## `adjust-dateTime-to-timezone`

Expression call: `adjust-dateTime-to-timezone(xs:dateTime?) -> xs:dateTime?`; `adjust-dateTime-to-timezone(xs:dateTime?, xs:dayTimeDuration?) -> xs:dateTime?`.

## `adjust-date-to-timezone`

Expression call: `adjust-date-to-timezone(xs:date?, xs:dayTimeDuration?) -> xs:date?`.

## `adjust-time-to-timezone`

Expression call: `adjust-time-to-timezone(xs:time?) -> xs:time?`; `adjust-time-to-timezone(xs:time?, xs:dayTimeDuration?) -> xs:time?`.

## `default-collation`

Expression call: `default-collation() -> xs:string`.

## `current-dateTime`

Expression call: `current-dateTime() -> xs:dateTime`.

## `current-date`

Expression call: `current-date() -> xs:date`.

## `current-time`

Expression call: `current-time() -> xs:time`.

## `implicit-timezone`

Expression call: `implicit-timezone() -> xs:dayTimeDuration`.

## `root`

Expression call: `root(node()?) -> node()?`.

## `idref`

Expression call: `idref(xs:string*) -> node()*`.

## `doc`

Expression call: `doc(xs:string?) -> document-node()?`.

The argument is a document URI string.

## `doc-available`

Expression call: `doc-available(xs:string?) -> xs:boolean`.

The argument is a document URI string.

## `collection`

Expression call: `collection() -> node()*`; `collection(xs:string?) -> node()*`.

The optional argument is the collection URI string.

## `trace`

Expression call: `trace(item()*, xs:string) -> item()*`.

## `error`

Expression call: `error() -> none`; `error(xs:QName?, xs:string) -> none`.

The two-argument form accepts the error qualified name and description string.

## `format-integer`

Expression call: `format-integer(xs:integer?, xs:string) -> xs:string`; `format-integer(xs:integer?, xs:string, xs:string?) -> xs:string`.

Positional arguments are the integer value, picture string and optional language string.

## `format-number`

Expression call: `format-number(xs:numeric?, xs:string) -> xs:string`; `format-number(xs:numeric?, xs:string, xs:string?) -> xs:string`.

Positional arguments are the numeric value, picture string and optional decimal-format name.

## `format-dateTime`

Expression call: `format-dateTime(xs:dateTime?, xs:string) -> xs:string?`; `format-dateTime(xs:dateTime?, xs:string, xs:string?, xs:string?, xs:string?) -> xs:string?`.

Positional arguments are the date-time value and picture string, or the date-time value, picture string, language, calendar and place.

## `format-date`

Expression call: `format-date(xs:date?, xs:string) -> xs:string?`; `format-date(xs:date?, xs:string, xs:string?, xs:string?, xs:string?) -> xs:string?`.

Positional arguments are the date value and picture string, or the date value, picture string, language, calendar and place.

## `format-time`

Expression call: `format-time(xs:time?, xs:string) -> xs:string?`.

Positional arguments are the time value and picture string.

## `analyze-string`

Expression call: `analyze-string(xs:string?, xs:string) -> element(fn:analyze-string-result)`; `analyze-string(xs:string?, xs:string, xs:string) -> element(fn:analyze-string-result)`.

The `evaluate(context)` result is an element-node object with `elem` carrying an XML element. Expanded names use `http://www.w3.org/2005/xpath-functions`. The root local name is `analyze-string-result`; its content uses `match`, `non-match` and nested `group` elements. A `group` carries `nr` as a decimal-integer string. Character content is available through `text` and `tail`; child elements are iterable.

Positional arguments are the input text, regular-expression pattern and optional flag string. Flags use the lexical form described for `matches`.

## `path`

Expression call: `path(node()?) -> xs:string?`.

## `has-children`

Expression call: `has-children(node()?) -> xs:boolean`.

## `innermost`

Expression call: `innermost(node()*) -> node()*`.

## `outermost`

Expression call: `outermost(node()*) -> node()*`.

## `head`

Expression call: `head(item()*) -> item()?`.

## `tail`

Expression call: `tail(item()*) -> item()*`.

## `generate-id`

Expression call: `generate-id(node()?) -> xs:string`.

## `uri-collection`

Expression call: `uri-collection() -> xs:anyURI*`; `uri-collection(xs:string?) -> xs:anyURI*`.

The optional argument is the collection URI string.

## `unparsed-text`

Expression call: `unparsed-text(xs:string?) -> xs:string?`; `unparsed-text(xs:string?, xs:string) -> xs:string?`.

Positional arguments are the resource URI string and optional encoding-name string.

## `unparsed-text-lines`

Expression call: `unparsed-text-lines(xs:string?) -> xs:string*`; `unparsed-text-lines(xs:string?, xs:string) -> xs:string*`.

Positional arguments are the resource URI string and optional encoding-name string.

## `unparsed-text-available`

Expression call: `unparsed-text-available(xs:string?) -> xs:boolean`; `unparsed-text-available(xs:string?, xs:string) -> xs:boolean`.

Positional arguments are the resource URI string and optional encoding-name string.

## `environment-variable`

Expression call: `environment-variable(xs:string) -> xs:string?`.

The argument is the environment-variable name string.

## `available-environment-variables`

Expression call: `available-environment-variables() -> xs:string*`.

## `parse-xml`

Expression call: `parse-xml(xs:string?) -> document-node(element(*))?`.

The argument is the XML document text.

## `parse-xml-fragment`

Expression call: `parse-xml-fragment(xs:string?) -> document-node()?`.

The argument is the XML fragment text.

## `serialize`

Expression call: `serialize(item()*) -> xs:string`; `serialize(item()*, element(output:serialization-parameters)? | map(*)) -> xs:string`.

The evaluated result is a Python `str` containing serialized output. XML output carries serialized XML text; JSON output carries a JSON document. When an XML declaration is present its leading marker is `<?xml `.

The second argument is an XML element in XPath 3.0 or an XPath parameter map in XPath 3.1.

| Map field | Type |
| --- | --- |
| `method` | `xs:string`, with spellings `xml` and `json`. |
| `omit-xml-declaration` | `xs:boolean`. |
| `item-separator` | `xs:string`. |
| `use-character-maps` | Map of strings to replacement strings. |

The XML parameter element has expanded name `{http://www.w3.org/2010/xslt-xquery-serialization}serialization-parameters`. Child parameter elements use that namespace. `omit-xml-declaration` carries a `value` attribute spelled `yes` or `no`; `item-separator` carries a string `value` attribute. `use-character-maps` contains `character-map` children with `character` and `map-string` attributes carrying a source character and replacement string.

Positional arguments are the item sequence and optional serialization parameters.

## `function-lookup`

Expression call: `function-lookup(xs:QName, xs:integer) -> function(*)?`.

## `function-name`

Expression call: `function-name(function(*)) -> xs:QName?`.

## `function-arity`

Expression call: `function-arity(function(*)) -> xs:integer`.

## `for-each`

Expression call: `for-each(item()*, function(item()) as item()*) -> item()*`.

## `filter`

Expression call: `filter(item()*, function(item()) as xs:boolean) -> item()*`.

## `fold-left`

Expression call: `fold-left(item()*, item()*, function(item()*, item()) as item()*) -> item()*`.

## `fold-right`

Expression call: `fold-right(item()*, item()*, function(item(), item()*) as item()*) -> item()*`.

## `for-each-pair`

Expression call: `for-each-pair(item()*, item()*, function(item(), item()) as item()*) -> item()*`.

## `math:pi`

Expression call: `math:pi() -> xs:double`.

## `math:exp`

Expression call: `math:exp(xs:double?) -> xs:double?`.

## `math:exp10`

Expression call: `math:exp10(xs:double?) -> xs:double?`.

## `math:log`

Expression call: `math:log(xs:double?) -> xs:double?`.

## `math:log10`

Expression call: `math:log10(xs:double?) -> xs:double?`.

## `math:pow`

Expression call: `math:pow(xs:double?, xs:numeric) -> xs:double?`.

## `math:sqrt`

Expression call: `math:sqrt(xs:double?) -> xs:double?`.

## `math:sin`

Expression call: `math:sin(xs:double?) -> xs:double?`.

## `math:cos`

Expression call: `math:cos(xs:double?) -> xs:double?`.

## `math:tan`

Expression call: `math:tan(xs:double?) -> xs:double?`.

## `math:asin`

Expression call: `math:asin(xs:double?) -> xs:double?`.

## `math:acos`

Expression call: `math:acos(xs:double?) -> xs:double?`.

## `math:atan`

Expression call: `math:atan(xs:double?) -> xs:double?`.

## `math:atan2`

Expression call: `math:atan2(xs:double, xs:double) -> xs:double`.

## `map:size`

Expression call: `map:size(map(*)) -> xs:integer`.

## `map:keys`

Expression call: `map:keys(map(*)) -> xs:anyAtomicType*`.

## `map:contains`

Expression call: `map:contains(map(*), xs:anyAtomicType) -> xs:boolean`.

## `map:get`

Expression call: `map:get(map(*), xs:anyAtomicType) -> item()*`.

## `map:put`

Expression call: `map:put(map(*), xs:anyAtomicType, item()*) -> map(*)`.

## `map:remove`

Expression call: `map:remove(map(*), xs:anyAtomicType*) -> map(*)`.

## `map:entry`

Expression call: `map:entry(xs:anyAtomicType, item()*) -> map(*)`.

## `map:merge`

Expression call: `map:merge(map(*)*) -> map(*)`; `map:merge(map(*)*, map(*)) -> map(*)`.

The optional parameter map has a `duplicates` string field. Its policy spellings are `use-first`, `use-last`, `use-any`, `reject` and `combine`. The result is an XPath map accessible through lookup and map functions.

## `map:find`

Expression call: `map:find(map(*), xs:anyAtomicType) -> array(*)`.

## `map:for-each`

Expression call: `map:for-each(map(*), function(xs:anyAtomicType, item()*) as item()*) -> item()*`.

## `array:size`

Expression call: `array:size(array(*)) -> xs:integer`.

## `array:get`

Expression call: `array:get(array(*), xs:integer) -> item()*`.

## `array:put`

Expression call: `array:put(array(*), xs:integer, item()*) -> array(*)`.

## `array:insert-before`

Expression call: `array:insert-before(array(*), xs:integer, item()*) -> array(*)`.

## `array:append`

Expression call: `array:append(array(*), item()*) -> array(*)`.

## `array:remove`

Expression call: `array:remove(array(*), xs:integer*) -> array(*)`.

## `array:subarray`

Expression call: `array:subarray(array(*), xs:integer) -> array(*)`; `array:subarray(array(*), xs:integer, xs:integer) -> array(*)`.

## `array:head`

Expression call: `array:head(array(*)) -> item()*`.

## `array:tail`

Expression call: `array:tail(array(*)) -> array(*)`.

## `array:reverse`

Expression call: `array:reverse(array(*)) -> array(*)`.

## `array:join`

Expression call: `array:join(array(*)*) -> array(*)`.

## `array:flatten`

Expression call: `array:flatten(item()*) -> item()*`.

## `array:for-each`

Expression call: `array:for-each(array(*), function(item()*) as item()*) -> array(*)`.

## `array:for-each-pair`

Expression call: `array:for-each-pair(array(*), array(*), function(item()*, item()*) as item()*) -> array(*)`.

## `array:filter`

Expression call: `array:filter(array(*), function(item()*) as xs:boolean) -> array(*)`.

## `array:fold-left`

Expression call: `array:fold-left(array(*), item()*, function(item()*, item()*) as item()*) -> item()*`.

## `array:fold-right`

Expression call: `array:fold-right(array(*), item()*, function(item()*, item()*) as item()*) -> item()*`.

## `array:sort`

Expression call: `array:sort(array(*)) -> array(*)`; `array:sort(array(*), xs:string?, function(item()*) as xs:anyAtomicType*) -> array(*)`; `array:sort(array(*), xs:string?) -> array(*)`.

## `sort`

Expression call: `sort(item()*) -> item()*`; `sort(item()*, xs:string?, function(item()) as xs:anyAtomicType*) -> item()*`; `sort(item()*, xs:string?) -> item()*`.

The function can also be called as `fn:sort` with the same positional arguments.

## `json-doc`

Expression call: `json-doc(xs:string?, map(*)) -> item()?`; `json-doc(xs:string?) -> item()?`.

The `options` argument is an XPath map. Fields are `duplicates: xs:string`, `liberal: xs:boolean`, `escape: xs:boolean` and `fallback: function(xs:string) as xs:string`. Duplicate-policy spellings are `use-first`, `use-last` and `reject`. The returned XPath value is read through map/array lookup or as a Python atomic value; a returned empty sequence has no selected items.

Positional arguments are the resource URI string and optional parameter map.

## `parse-json`

Expression call: `parse-json(xs:string?) -> item()?`; `parse-json(xs:string?, map(*)) -> item()?`.

The `options` argument is an XPath map. Fields are `duplicates: xs:string`, `liberal: xs:boolean`, `escape: xs:boolean` and `fallback: function(xs:string) as xs:string`. Duplicate-policy spellings are `use-first`, `use-last` and `reject`. The returned XPath value is read through map/array lookup or as a Python atomic value; a returned empty sequence has no selected items.

Positional arguments are the JSON text and optional parameter map.

## `random-number-generator`

Expression call: `random-number-generator() -> map(xs:string, item())`; `random-number-generator(xs:anyAtomicType?) -> map(xs:string, item())`.

The returned XPath map has `number`, `next` and `permute` fields. `number` carries a numeric value. `next` is a callable function item invoked without arguments and returning a generator map. `permute` is a callable function item accepting an item sequence and returning an item sequence. These fields are reached through XPath map lookup.

The optional argument is the seed atomic value.

## `apply`

Expression call: `apply(function(*), array(*)) -> item()*`.

## `parse-ietf-date`

Expression call: `parse-ietf-date(xs:string?) -> xs:dateTime?`.

## `contains-token`

Expression call: `contains-token(xs:string*, xs:string) -> xs:boolean`; `contains-token(xs:string*, xs:string, xs:string) -> xs:boolean`.

## `collation-key`

Expression call: `collation-key(xs:string) -> xs:base64Binary`; `collation-key(xs:string, xs:string) -> xs:base64Binary`.

Positional arguments are the input string and optional collation URI string.

## `default-language`

Expression call: `default-language() -> xs:language`.

## `xml-to-json`

Expression call: `xml-to-json(node()?) -> xs:string?`.

The supplied XML node uses the JSON XML representation with namespace `http://www.w3.org/2005/xpath-functions`, element local names `map`, `array`, `string`, `number`, `boolean` and `null`, and `key` attributes on object entries. The selected output is a JSON document in a Python `str`.

The argument is the XML node carrying the JSON XML representation.

## `json-to-xml`

Expression call: `json-to-xml(xs:string?, map(*)) -> document-node()?`; `json-to-xml(xs:string?) -> document-node()?`.

The optional XPath parameter map has `duplicates: xs:string`, `validate: xs:boolean`, `escape: xs:boolean` and `fallback: function(xs:string) as xs:string` fields. Duplicate-policy spellings are `retain`, `reject` and `use-first`.

A selected document is an XML document object with `getroot()`. The XML representation uses the namespace `http://www.w3.org/2005/xpath-functions` and element local names `map`, `array`, `string`, `number`, `boolean` and `null`. Object entries carry `key` string attributes; escaped content can carry an `escaped` attribute and an escaped entry name an `escaped-key` attribute, each in XML Schema boolean lexical form. Atomic character content is in `text`. Numeric text is a numeric lexical string. Boolean text is `true` or `1` for true and `false` or `0` for false. Child elements are indexable and iterable.

Positional arguments are the JSON text and optional parameter map.

## `velunara.datatypes.QName`

`velunara.datatypes.QName(uri, qname)` accepts a namespace URI `str | None` and a lexical qualified-name `str`. Results expose `namespace: str` and `local_name: str`, with equality and inequality returning `bool`. Invalid construction uses `ValueError`.

## `xs:string`

Expression constructor: `xs:string(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a Python `str` value, accessible through expression evaluation and selection.

## `xs:boolean`

Expression constructor: `xs:boolean(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a Python `bool` value, accessible through expression evaluation and selection.

## `xs:decimal`

Expression constructor: `xs:decimal(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a Python `decimal.Decimal` value, accessible through expression evaluation and selection.

## `xs:double`

Expression constructor: `xs:double(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a Python `float` value, accessible through expression evaluation and selection.

## `xs:float`

Expression constructor: `xs:float(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a Python `float` value, accessible through expression evaluation and selection.

## `xs:integer`

Expression constructor: `xs:integer(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a Python `int` value, accessible through expression evaluation and selection.

## `xs:date`

Expression constructor: `xs:date(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a calendar date object, accessible through expression evaluation and selection.

## `xs:dateTime`

Expression constructor: `xs:dateTime(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a calendar date-time object, accessible through expression evaluation and selection.

## `xs:dayTimeDuration`

Expression constructor: `xs:dayTimeDuration(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a day-time duration object, accessible through expression evaluation and selection.

## `xs:yearMonthDuration`

Expression constructor: `xs:yearMonthDuration(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a year-month duration object, accessible through expression evaluation and selection.

## `xs:QName`

Expression constructor: `xs:QName(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a qualified-name object, accessible through expression evaluation and selection.

The argument is the lexical qualified-name string.

## `xs:numeric`

Expression constructor: `xs:numeric(<value>)`. Its argument is an atomic XPath value. The evaluated singleton result is a Python numeric value, accessible through expression evaluation and selection.

The argument is a numeric atomic value or lexical numeric string.

## `bind_parser`

Stated under `AbstractSchemaProxy`.

## `xs:time`

Expression constructor: `xs:time(<value>)`. The datatype local name is `time`. The argument is an atomic XPath value; the evaluated singleton result is a calendar time object.

## `xs:duration`

Expression constructor: `xs:duration(<value>)`. The datatype local name is `duration`. The argument is an atomic XPath value; the evaluated singleton result is a duration object.

## `xs:nonPositiveInteger`

Expression constructor: `xs:nonPositiveInteger(<value>)`. The datatype local name is `nonPositiveInteger`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:negativeInteger`

Expression constructor: `xs:negativeInteger(<value>)`. The datatype local name is `negativeInteger`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:nonNegativeInteger`

Expression constructor: `xs:nonNegativeInteger(<value>)`. The datatype local name is `nonNegativeInteger`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:positiveInteger`

Expression constructor: `xs:positiveInteger(<value>)`. The datatype local name is `positiveInteger`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:byte`

Expression constructor: `xs:byte(<value>)`. The datatype local name is `byte`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:short`

Expression constructor: `xs:short(<value>)`. The datatype local name is `short`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:int`

Expression constructor: `xs:int(<value>)`. The datatype local name is `int`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:long`

Expression constructor: `xs:long(<value>)`. The datatype local name is `long`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:unsignedByte`

Expression constructor: `xs:unsignedByte(<value>)`. The datatype local name is `unsignedByte`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:unsignedShort`

Expression constructor: `xs:unsignedShort(<value>)`. The datatype local name is `unsignedShort`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:unsignedInt`

Expression constructor: `xs:unsignedInt(<value>)`. The datatype local name is `unsignedInt`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xs:unsignedLong`

Expression constructor: `xs:unsignedLong(<value>)`. The datatype local name is `unsignedLong`. The argument is an atomic XPath value; the evaluated singleton result is a Python `int` value.

## `xml.etree.ElementTree`

The Python package is imported as `velunara` from the project root. Calls exchange Python objects in the current process. Results are return values or yielded items; failures are Python exceptions.

XML tree inputs use `xml.etree.ElementTree` or `lxml.etree` element/document objects (for example as built by `xml.etree.ElementTree.fromstring` or `lxml.etree.fromstring`), or XPath node objects. Schema inputs interoperate with `xmlschema.XMLSchema10`, `xmlschema.XMLSchema11`, and `xmlschema.xpath.XMLSchemaProxy`; these are caller-supplied schema processor objects.

Expression signatures use XPath sequence-type notation. Expression results use the Python carriers returned by expression evaluation or selection.

Remote text resources are addressed by `http://` and `ftp://` URLs.

All parser versions provide the expression prefix `xml` (`http://www.w3.org/XML/1998/namespace`) without caller bindings. XPath 2.0 and later also provide `xs` (`http://www.w3.org/2001/XMLSchema`) and `fn` (`http://www.w3.org/2005/xpath-functions`); XPath 3.0 and later provide `math` (`http://www.w3.org/2005/xpath-functions/math`), and XPath 3.1 provides `map` (`http://www.w3.org/2005/xpath-functions/map`) and `array` (`http://www.w3.org/2005/xpath-functions/array`).

## `xml.etree.ElementTree.fromstring`

Stated under `xml.etree.ElementTree`.

## `lxml.etree`

Stated under `xml.etree.ElementTree`.

## `xmlschema.XMLSchema10`

Stated under `xml.etree.ElementTree`.

## `xmlschema.XMLSchema11`

Stated under `xml.etree.ElementTree`.

## `xmlschema.xpath`

Stated under `xml.etree.ElementTree`.

## `xmlschema.xpath.XMLSchemaProxy`

Stated under `xml.etree.ElementTree`.

## `AbstractSchemaProxy.get_type`

Stated under `AbstractSchemaProxy`.

## `AbstractSchemaProxy.get_element`

Stated under `AbstractSchemaProxy`.

## `AbstractSchemaProxy.get_attribute`

Stated under `AbstractSchemaProxy`.

## `velunara.datatypes.Integer.validate`

Stated under `Integer`.
