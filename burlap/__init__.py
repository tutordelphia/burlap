VERSION = (0, 1, 1)
__version__ = '.'.join(map(str, VERSION))

import copy
import os
import re
import sys
import types
import yaml

from fabric.api import env
from fabric.tasks import WrappedCallableTask

env.is_local = None
env.base_config_dir = '.'
env.src_dir = 'src' # The path relative to fab where the code resides.

from common import ROLE_DIR, SITE, ROLE

env.django_settings_module_template = '%(app_name)s.settings.settings'
env[SITE] = None
env[ROLE] = None
env_default = copy.deepcopy(dict((k, v) for k, v in env.iteritems() if type(v) not in (types.GeneratorType,)))

# Variables cached per-role. Must be after deepcopy.
env._rc = type(env)()

def _get_environ_handler(name, d):
    def func(site=None):
        env.update(env_default)
        env[ROLE] = os.environ[ROLE] = name
        if site:
            env[SITE] = os.environ[SITE] = site
        #print name, d
        env.update(d)
        print 'Loaded role %s.' % (name,)
    func.__doc__ = 'Sets enivronment variables for the "%s" role.' % (name,)
    return func

def update_merge(d, u):
    """
    Recursively merges two dictionaries.
    
    Uses fabric's AttributeDict so you can reference values via dot-notation.
    e.g. env.value1.value2.value3...
    
    http://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth
    """
    import collections
    for k, v in u.iteritems():
        if isinstance(v, collections.Mapping):
            r = update_merge(d.get(k, dict()), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d

# Dynamically create a Fabric task for each role.
_common = type(env)()
_common_fn = os.path.join(ROLE_DIR, 'all', 'settings.yaml')
if os.path.isfile(_common_fn):
    _common = yaml.safe_load(open(_common_fn))
for _name in os.listdir(ROLE_DIR):
    #print 'checking',_name
    _settings_fn = os.path.join(ROLE_DIR, _name, 'settings.yaml')
    if _name == 'all' or not os.path.isfile(_settings_fn):
        continue
    _config = copy.deepcopy(_common)
    _config.update(yaml.safe_load(open(_settings_fn)) or type(env)())
    _settings_local_fn = os.path.join(ROLE_DIR, _name, 'settings_local.yaml')
    if os.path.isfile(_settings_local_fn):
        _config.update(yaml.safe_load(open(_settings_local_fn)) or type(env)())
    _f = _get_environ_handler(_name, _config)
    _var_name = 'role_'+_name
    _f = WrappedCallableTask(_f, name=_name)
    exec "%s = _f" % (_var_name,)
