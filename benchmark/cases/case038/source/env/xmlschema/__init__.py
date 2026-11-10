"""Real XML Schema inputs with a contestant-independent implementation."""
from _schema_fixture import processor
from .bridge import Bridge, View
from . import xpath

__version__ = processor.__version__


class XMLSchemaBase(View):
    def __init__(self, *args, **kwargs):
        bridge = Bridge()
        value = self._factory(*args, **kwargs)
        super().__init__(bridge, value)
        bridge.objects[id(value)] = self


class XMLSchema10(XMLSchemaBase):
    _factory = processor.XMLSchema10


class XMLSchema11(XMLSchemaBase):
    _factory = processor.XMLSchema11


XMLSchema = XMLSchema10
