from __future__ import print_function
from __future__ import absolute_import

import copy
import os
import re
import sys
import types
import importlib
import pkgutil
import inspect
import warnings

from pprint import pprint

VERSION = (0, 4, 2)
__version__ = '.'.join(map(str, VERSION))

burlap_populate_stack = int(os.environ.get('BURLAP_POPULATE_STACK', 1))
no_load = int(os.environ.get('BURLAP_NO_LOAD', 0))

env = None
#common = None
#debug = None
env_default = {}

try:
    from fabric.api import env
    from fabric.tasks import WrappedCallableTask
    from fabric.utils import _AliasDict

    import yaml
    
    # Variables cached per-role. Must be after deepcopy.
    env._rc = type(env)()

    def _represent_dictorder(self, data):
        return self.represent_mapping(u'tag:yaml.org,2002:map', data.items())
    
    def _represent_tuple(self, data):
        return self.represent_sequence(u'tag:yaml.org,2002:seq', data)
    
    def _construct_tuple(self, node):
        return tuple(self.construct_sequence(node))
    
    def _represent_function(self, data):
        return self.represent_scalar(u'tag:yaml.org,2002:null', u'null')
    
    yaml.add_representer(type(env), _represent_dictorder)
    yaml.add_representer(_AliasDict, _represent_dictorder)
    #yaml.add_representer(tuple, _represent_tuple) # we need tuples for hash keys
    yaml.add_constructor(u'tag:yaml.org,2002:python/tuple', _construct_tuple)
    yaml.add_representer(types.FunctionType, _represent_function)

    from . import common
    from . import debug
    
    env_default = common.save_env()

except ImportError as e:
    print(e, file=sys.stderr)
    pass

try:
    common
except NameError:
    common = None

try:
    debug
except NameError:
    debug = None
    
def _get_environ_handler(name, d):
    """
    Dynamically creates a Fabric task for each configuration role.
    """
    
    def func(site=None, **kwargs):
        site = site or d.get('default_site') or env.SITE
        
        hostname = kwargs.get('hostname')
        hostname = hostname or kwargs.get('name')
        hostname = hostname or kwargs.get('hn')
        hostname = hostname or kwargs.get('h')

        verbose = int(kwargs.get('verbose', '0'))
        
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
        
        # Dynamically retrieve hosts.
        if env.hosts_retriever:
#            print('retriever:',retriever)
#            print('hosts:',env.hosts)
            if verbose:
                print('Building host list...')
            env.hosts = list(retriever(verbose=verbose))

        # Filter hosts list by a specific host name.
        #env.hostname = hostname
        if hostname:
            _hostname = hostname
            hostname = translator(hostname=hostname)
            _hosts = env.hosts
            env.hosts = [_ for _ in env.hosts if _ == hostname]
            assert env.hosts, \
                'Hostname %s does not match any known hosts.' % (_hostname,)
                
        if env.is_local is None:
            if env.hosts:
                env.is_local = 'localhost' in env.hosts or '127.0.0.1' in env.hosts
            elif env.host_string:
                env.is_local = 'localhost' in env.host_string or '127.0.0.1' in env.host_string
        
        print('Loaded role %s.' % (name,), file=sys.stderr)
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

def find_yaml_settings_fn(name, local=False):
    if local:
        settings_fn = os.path.join(common.ROLE_DIR, name, 'settings_local.yaml')
    else:
        settings_fn = os.path.join(common.ROLE_DIR, name, 'settings.yaml')
    if os.path.isfile(settings_fn):
        return settings_fn

def load_yaml_settings(name, priors=None, verbose=0):
    verbose = int(verbose)
    config = type(env)()
    if priors is None:
        priors = set()
    if name in priors:
        return config
    priors.add(name)
    
    settings_fn = find_yaml_settings_fn(name)
    if not settings_fn:
        warnings.warn('Warning: Could not find Yaml settings for role %s.' % (name,))
        return config
    if verbose:
        print('Loading settings:', settings_fn)
    config.update(yaml.safe_load(open(settings_fn)) or type(env)())
    #if verbose: sys.stdout.write('sites0:'); pprint(config['sites'], indent=4)
    if 'inherits' in config:
        parent_name = config['inherits']
        del config['inherits']
        parent_config = load_yaml_settings(
            parent_name,
            priors=priors,
            verbose=verbose)
        parent_config.update(config)
        config = parent_config
    #if verbose: sys.stdout.write('sites1:'); pprint(config['sites'], indent=4)
    
    # Load local overrides.
    settings_local_fn = find_yaml_settings_fn(name, local=True)
    if settings_local_fn:
        if verbose:
            print('Loading local settings:', settings_local_fn)
        config.update(yaml.safe_load(open(settings_local_fn)) or type(env)())
    
    return config

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
        locals_['shell'] = debug.shell
        locals_['info'] = debug.info
        #locals_['djshell'] = common.djshell
        locals_['tunnel'] = debug.tunnel
    finally:
        del stack

# Dynamically create a Fabric task for each role.
role_commands = {}
if common and not no_load:
    #_common = type(env)()
    #_common_fn = os.path.join(common.ROLE_DIR, 'all', 'settings.yaml')
    #if os.path.isfile(_common_fn):
    #    _common = yaml.safe_load(open(_common_fn))
    if os.path.isdir(common.ROLE_DIR):
        for _name in os.listdir(common.ROLE_DIR):
            _settings_fn = os.path.join(common.ROLE_DIR, _name, 'settings.yaml')
            if _name.startswith('.') or not os.path.isfile(_settings_fn):
                continue
    #        if _name == 'all' or not :
    #            continue
    #        _config = copy.deepcopy(_common)
    #        _config.update(yaml.safe_load(open(_settings_fn)) or type(env)())
    #        _settings_local_fn = os.path.join(common.ROLE_DIR, _name, 'settings_local.yaml')
    #        if os.path.isfile(_settings_local_fn):
    #            _config.update(yaml.safe_load(open(_settings_local_fn)) or type(env)())
            _config = load_yaml_settings(_name)
            _f = _get_environ_handler(_name, _config)
            _var_name = 'role_'+_name
            _f = WrappedCallableTask(_f, name=_name)
            _cmd = "%s = _f" % (_var_name,)
            exec _cmd
            #print('Creating role %s.' % _var_name, file=sys.stderr)
            role_commands[_var_name] = _f

    # Auto-import all sub-modules.
    sub_modules = {}
    sub_modules['common'] = common
    __all__ = []
    for loader, module_name, is_pkg in  pkgutil.walk_packages(__path__):
        if module_name in locals():
            continue
        __all__.append(module_name)
        #print('Importing: %s' % module_name, file=sys.stderr)
        module = loader.find_module(module_name).load_module(module_name)
        sub_modules[module_name] = module

    if burlap_populate_stack:
        populate_fabfile()
    
    # Execute any callbacks registered by sub-modules.
    # These are useful for calling inter-sub-module functions
    # after the modules tasks are registered so task names don't get
    # mistakenly registered under the wrong module.
    for cb in env.post_callbacks:
        cb()
