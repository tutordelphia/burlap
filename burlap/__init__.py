VERSION = (0, 1, 0)
__version__ = '.'.join(map(str, VERSION))

import copy
import os
import re
import sys
import yaml

from fabric.api import env
from fabric.tasks import WrappedCallableTask

ROLE_DIR = env.ROLES_DIR = 'roles'

env.is_local = None
env.base_config_dir = '.'
env.src_dir = 'src' # The path relative to fab where the code resides.
env.settings_module = '%(app_name)s.settings.%(role)s'
env.python_version = 2.7
env_default = copy.deepcopy(env)

def _get_environ_handler(name, d):
    def func():
        env.update(env_default)
        env.role = name
        print name, d
        env.update(d)
        print 'Loaded role %s.' % (name,)
    return func

# Dynamically create a Fabric task for each role.
_common = {}
_common_fn = os.path.join(ROLE_DIR, 'common.yaml')
if os.path.isfile(_common_fn):
    _common = yaml.safe_load(open(_common_fn))
for fn in os.listdir(ROLE_DIR):
    if not fn.endswith('.yaml') or fn.startswith('common'):
        continue
    _name = re.findall('(.*?)\.yaml', fn)[0]
    _config = yaml.safe_load(open(os.path.join(ROLE_DIR, fn)))
    _config.update(_common)
    _f = _get_environ_handler(_name, _config)
    _var_name = 'role_'+_name
    _f = WrappedCallableTask(_f, name=_name)
    exec "%s = _f" % (_var_name,)
