VERSION = (0, 1, 1)
__version__ = '.'.join(map(str, VERSION))

import copy
import os
import re
import sys
import types
import yaml
import importlib
import pkgutil
import inspect

from fabric.api import env
from fabric.tasks import WrappedCallableTask

burlap_populate_stack = int(os.environ.get('BURLAP_POPULATE_STACK', 1))

import common

env_default = common.save_env()

# Variables cached per-role. Must be after deepcopy.
env._rc = type(env)()

def _get_environ_handler(name, d):
    """
    Dynamically creates a Fabric task for each configuration role.
    """
    def func(site=None, **kwargs):
        site = site or env.SITE
        hostname = kwargs.get('hostname', kwargs.get('hn', kwargs.get('h')))
        
        # Load environment for current role.
        env.update(env_default)
        env[common.ROLE] = os.environ[common.ROLE] = name
        if site:
            env[common.SITE] = os.environ[common.SITE] = site
        env.update(d)
        
        # Load host retriever.
        retriever = None
        if env.hosts_retriever:
            # Dynamically retrieve hosts.
            module_name = '.'.join(env.hosts_retriever.split('.')[:-1])
            func_name = env.hosts_retriever.split('.')[-1]
            retriever = getattr(importlib.import_module(module_name), func_name)
        
        # Load host translator.
        translator = None
        if hostname:
            # Filter hosts list by a specific host name.
            module_name = '.'.join(env.hostname_translator.split('.')[:-1])
            func_name = env.hostname_translator.split('.')[-1]
            translator = getattr(importlib.import_module(module_name), func_name)
        
        # Re-load environment for current role, incase loading
        # the retriever/translator reset some environment values.
        env.update(env_default)
        env[common.ROLE] = os.environ[common.ROLE] = name
        if site:
            env[common.SITE] = os.environ[common.SITE] = site
        env.update(d)
#        print 'd:'
#        for k in sorted(d.keys()):
#            print k,d[k]
        #print 'env.vm_type0:',env.vm_type
        
        # Dynamically retrieve hosts.
        if env.hosts_retriever:
            env.hosts = list(retriever())
            
        #print 'env.vm_type1:',env.vm_type
        # Filter hosts list by a specific host name.
        if hostname:
            hostname = translator(hostname=hostname)
            _hosts = env.hosts
            env.hosts = [_ for _ in env.hosts if _ == hostname]
            assert env.hosts, \
                'Hostname %s does not match any known hosts.' % (hostname,)
        
        #print 'env.vm_type2:',env.vm_type
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
role_commands = {}
_common = type(env)()
_common_fn = os.path.join(common.ROLE_DIR, 'all', 'settings.yaml')
if os.path.isfile(_common_fn):
    _common = yaml.safe_load(open(_common_fn))
if os.path.isdir(common.ROLE_DIR):
    for _name in os.listdir(common.ROLE_DIR):
        #print 'checking',_name
        _settings_fn = os.path.join(common.ROLE_DIR, _name, 'settings.yaml')
        if _name == 'all' or not os.path.isfile(_settings_fn):
            continue
        _config = copy.deepcopy(_common)
        _config.update(yaml.safe_load(open(_settings_fn)) or type(env)())
        _settings_local_fn = os.path.join(common.ROLE_DIR, _name, 'settings_local.yaml')
        if os.path.isfile(_settings_local_fn):
            _config.update(yaml.safe_load(open(_settings_local_fn)) or type(env)())
        _f = _get_environ_handler(_name, _config)
        _var_name = 'role_'+_name
        _f = WrappedCallableTask(_f, name=_name)
        exec "%s = _f" % (_var_name,)
        role_commands[_var_name] = _f

# Auto-import all sub-modules.
sub_modules = {}
sub_modules['common'] = common
__all__ = []
for loader, module_name, is_pkg in  pkgutil.walk_packages(__path__):
    if module_name in locals():
        continue
    __all__.append(module_name)
    module = loader.find_module(module_name).load_module(module_name)
    sub_modules[module_name] = module
    #print module

def populate_fabfile():
    """
    Automatically includes all submodules and role selectors
    in the top-level fabfile using spooky-scary black magic.
    
    This allows us to avoid manually declaring imports for every module, e.g.
    
        import burlap.pip
        import burlap.vm
        import burlap...
    
    which has the added benefit of allowing us to manually call the commands
    without typing "burlap".
    
    This is soley for convenience. If not needed, it can be disabled
    by specifying the environment variable:
    
        export BURLAP_POPULATE_STACK=0
    """
    stack = inspect.stack()
    fab_frame = None
    for frame_obj, script_fn, line, _, _, _ in stack:
        if 'fabfile.py' in script_fn:
            fab_frame = frame_obj
            break
    if not fab_frame:
        return
    try:
        locals_ = fab_frame.f_locals
        for module_name, module in sub_modules.iteritems():
            locals_[module_name] = module
        for role_name, role_func in role_commands.iteritems():
            assert role_name not in sub_modules, \
                ('The role %s conflicts with a built-in submodule. '
                 'Please choose a different name.') % (role_name)
            locals_[role_name] = role_func
        locals_['common'] = common
        locals_['shell'] = common.shell
        locals_['djshell'] = common.djshell
    finally:
        del stack

if burlap_populate_stack:
    populate_fabfile()

# Execute any callbacks registered by sub-modules.
# These are useful for calling inter-sub-module functions
# after the modules tasks are registered so task names don't get
# mistakenly registered under the wrong module.
for cb in env.post_callbacks:
    cb()
