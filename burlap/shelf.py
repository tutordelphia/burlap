
from collections import OrderedDict

import yaml

from fabric.api import env

class Shelf(object):
    """
    A helper class for serializing Python dictionaries to and from YAML,
    keeping the dictionary keys sorted to help readability.
    """
    
    def __init__(self, ascii_str=True, filename='roles/{role}/shelf.yaml'):
        
        # If true, automatically ensure all string values are plain ASCII.
        # This helps keep the YAML clean, otherwise verbose syntax would be
        # added for non-ASCII encodings, even if the string only contains
        # ASCII characters.
        self.ascii_str = ascii_str
        
        self._filename = filename
        
    @property
    def filename(self):
        return self._filename.format(role=env.ROLE.lower())

    @property
    def _dict(self):
        try:
            return OrderedDict(yaml.load(open(self.filename, 'rb')) or {})
        except IOError:
            return OrderedDict()

    def __getitem__(self, name):
        return self.get(name=name)

    def __setitem__(self, name, value):
        return self.set(name=name, value=value)

    def get(self, name, default=None):
        d = self._dict
        return d.get(name, default)
    
    def setdefault(self, name, default):
        d = self._dict
        d.setdefault(name, default)
        yaml.dump(d, open(self.filename, 'wb'))
    
    def set(self, name, value):
        d = self._dict
        if self.ascii_str and isinstance(value, basestring):
            value = str(value)
        d[name] = value
        yaml.dump(d, open(self.filename, 'wb'))
