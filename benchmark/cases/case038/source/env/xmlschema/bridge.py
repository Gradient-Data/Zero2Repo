"""Identity-preserving declarations and bidirectional public atomic values.

The processor owns schema construction, validation and lexical conversion.
The contestant owns all public XPath selection and proxy binding.
"""
from collections.abc import Iterator, Mapping
from decimal import Decimal
from _schema_fixture.schema_engine import datatypes as engine_types


def atomic(value, source, target, namespaces=None, xsd_version=None):
    """Reconstruct a datatype in the receiving implementation's type universe."""
    if source is engine_types:
        name = type(value).__name__
        kind = type(value)
    else:
        if type(value) in (str, int, float, bool, bytes, Decimal, type(None)):
            return value
        # Public classes can be aliases of classes with different internal names.
        # Match only concrete exported datatypes, never unpublished base classes.
        candidates = []
        for name in engine_types.__all__:
            kind = getattr(engine_types, name)
            public = getattr(source, name, None)
            if isinstance(kind, type) and isinstance(public, type) and \
                    kind.__module__.startswith(engine_types.__name__ + '.') and \
                    not name.startswith('Abstract') and not name.endswith('Proxy') and \
                    name not in ('AnyType', 'AnySimpleType', 'AnyAtomicType',
                                 'OrderedDateTime', 'ListType') and isinstance(value, public):
                candidates.append((len(kind.__mro__), name, kind))
        if not candidates:
            return value
        _, name, kind = max(candidates)
    if issubclass(kind, engine_types.AbstractDateTime):
        from ._public import api
        XPath2Parser = api.XPath2Parser
        XPathContext = api.XPathContext
        if source is engine_types:
            # Version-specific calendar classes are not part of the public shell.
            # Ask the public builtin constructor for its native representation.
            lexical = str(value).replace('"', '""')
            parser = XPath2Parser(xsd_version=kind._xsd_version)
            return parser.parse(f'xs:{kind.name}("{lexical}")').get_results(None)
        lexical = XPath2Parser().parse('string($value)').get_results(
            XPathContext(item=1, variables={'value': value}))
        if xsd_version == '1.0' and name in ('Date', 'DateTime', 'GregorianYear',
                                           'GregorianYearMonth'):
            name += '10'
        return getattr(engine_types, name).fromstring(lexical)
    factory = getattr(target, name)
    if issubclass(kind, (engine_types.AnyURI, engine_types.UntypedAtomic)):
        return factory(str(value))
    if issubclass(kind, engine_types.AbstractQName):
        if source is engine_types:
            lexical = value.qname
        elif not value.namespace:
            lexical = value.local_name
        else:
            lexical = value.local_name
            for prefix, uri in (namespaces or {}).items():
                if uri == value.namespace:
                    lexical = f'{prefix}:{value.local_name}' if prefix else value.local_name
                    break
        return factory(value.namespace, lexical)
    if issubclass(kind, engine_types.Duration):
        if source is engine_types:
            return factory.fromstring(str(value))
        if issubclass(kind, engine_types.YearMonthDuration):
            return factory(value.months)
        if issubclass(kind, engine_types.DayTimeDuration):
            return factory(value.seconds)
        return factory(value.months, value.seconds)
    if issubclass(kind, engine_types.AbstractBinary):
        return factory(kind.encoder(value.decode()))
    if issubclass(kind, engine_types.ListType):
        return factory([atomic(v, source, target, namespaces, xsd_version) for v in value])
    if kind.__module__.startswith(engine_types.__name__ + '.'):
        return factory(value)
    return value


class Bridge:
    def __init__(self):
        self.objects = {}

    def unwrap(self, value, namespaces=None, xsd_version=None):
        if isinstance(value, View):
            return value._value
        if isinstance(value, dict):
            return {self.unwrap(k, namespaces, xsd_version): self.unwrap(v, namespaces, xsd_version)
                    for k, v in value.items()}
        if isinstance(value, (tuple, list, set)):
            return type(value)(self.unwrap(v, namespaces, xsd_version) for v in value)
        from ._public import api
        datatypes = api.datatypes
        return atomic(value, datatypes, engine_types, namespaces, xsd_version)

    def wrap(self, value):
        if isinstance(value, type) and value.__module__.startswith(engine_types.__name__ + '.'):
            from ._public import api
            datatypes = api.datatypes
            return getattr(datatypes, value.__name__)
        if type(value).__module__.startswith(engine_types.__name__ + '.'):
            from ._public import api
            datatypes = api.datatypes
            return atomic(value, engine_types, datatypes)
        module = value.__module__ if isinstance(value, type) else type(value).__module__
        if module.startswith('_schema_fixture.schema_engine.'):
            raise TypeError('Processor-internal evaluator objects cannot cross the schema bridge')
        if isinstance(value, (tuple, list, set)):
            return type(value)(self.wrap(v) for v in value)
        if isinstance(value, Iterator):
            return (self.wrap(v) for v in value)
        if isinstance(value, Mapping) or type(value).__module__.startswith(
                '_schema_fixture.processor.'):
            key = id(value)
            if key not in self.objects:
                cls = MappingView if isinstance(value, Mapping) else View
                self.objects[key] = cls(self, value)
            return self.objects[key]
        return value


class View:
    def __init__(self, bridge, value):
        self._bridge = bridge
        self._value = value

    def __getattr__(self, name):
        # Private engine nodes/tokens must never cross into the public evaluator.
        if name in ('xpath_node', '_xpath_node', 'xpath_constructors', 'xpath_tokens'):
            raise AttributeError(name)
        value = getattr(self._value, name)
        if isinstance(value, type):
            return self._bridge.wrap(value)
        if callable(value):
            def call(*args, **kwargs):
                namespaces = kwargs.get('namespaces', getattr(self._value, 'namespaces', None))
                version = getattr(self._value, 'xsd_version', None)
                return self._bridge.wrap(value(
                    *self._bridge.unwrap(args, namespaces, version),
                    **self._bridge.unwrap(kwargs, namespaces, version)))
            return call
        return self._bridge.wrap(value)

    def __iter__(self):
        return (self._bridge.wrap(v) for v in self._value)

    def __len__(self):
        return len(self._value)

    def __getitem__(self, key):
        return self._bridge.wrap(self._value[self._bridge.unwrap(key)])

    def __repr__(self):
        return repr(self._value)

    @property
    def xpath_proxy(self):
        from .xpath import XMLSchemaProxy
        if hasattr(self._value, 'schema'):
            return XMLSchemaProxy(self.schema, self)
        return XMLSchemaProxy(self)

    def iterfind(self, path, namespaces=None):
        from ._public import api
        XPath2Parser = api.XPath2Parser
        XPathSchemaContext = api.XPathSchemaContext
        parser = XPath2Parser(namespaces=self.namespaces if namespaces is None else namespaces,
                              strict=False)
        return parser.parse(path).select_results(XPathSchemaContext(self))

    def find(self, path, namespaces=None):
        return next(self.iterfind(path, namespaces), None)

    def findall(self, path, namespaces=None):
        return list(self.iterfind(path, namespaces))


class MappingView(View, Mapping):
    """Keep map identity while exposing the same declaration views everywhere."""
