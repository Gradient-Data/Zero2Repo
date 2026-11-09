"""Schema proxy using only the contestant's published schema binding shell."""
from ._public import api
AbstractSchemaProxy = api.AbstractSchemaProxy
XPathSchemaContext = api.XPathSchemaContext


class XMLSchemaProxy(AbstractSchemaProxy):
    def __init__(self, schema=None, base_element=None):
        if schema is None:
            from _schema_fixture.processor import XMLSchema10
            from .bridge import Bridge
            schema = Bridge().wrap(XMLSchema10.meta_schema)
        if base_element is not None and base_element.schema is not schema:
            raise ValueError('The base element does not belong to this schema')
        self._schema = schema
        self._base_element = base_element

    @property
    def schema(self):
        return self._schema

    @property
    def base_element(self):
        return self._base_element

    @property
    def xsd_version(self):
        return self.schema.xsd_version

    @property
    def validity(self):
        return self.schema.validity

    @property
    def validation_attempted(self):
        return self.schema.validation_attempted

    def is_fully_valid(self):
        return self.validity == 'valid' and self.validation_attempted == 'full'

    def get_context(self):
        return XPathSchemaContext(root=self.schema, item=self.base_element, schema=self)

    def get_type(self, qname):
        return self.schema.maps.types.get(qname)

    def get_element(self, qname):
        return self.schema.maps.elements.get(qname)

    def get_attribute(self, qname):
        return self.schema.maps.attributes.get(qname)

    def get_substitution_group(self, qname):
        return self.schema.maps.substitution_groups.get(qname)

    def find(self, path, namespaces=None):
        root = self.schema if self.base_element is None else self.base_element
        return root.find(path, namespaces)

    def cached_find(self, path):
        return self.find(path)

    def is_assertion_based(self):
        return self.base_element is not None and \
            self.base_element.parent is self.base_element.type

    def is_instance(self, obj, type_qname):
        xsd_type = self.schema.maps.types[type_qname]
        try:
            xsd_type.encode(obj)
        except ValueError:
            return False
        return True

    def cast_as(self, obj, type_qname):
        return self.schema.maps.types[type_qname].decode(obj)

    def iter_atomic_types(self):
        for xsd_type in self.schema.maps.types.values():
            if xsd_type.target_namespace != 'http://www.w3.org/2001/XMLSchema' and \
                    hasattr(xsd_type, 'primitive_type'):
                yield xsd_type
