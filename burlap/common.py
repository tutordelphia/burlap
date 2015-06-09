import os
import re
import sys
import types
import copy
import tempfile
import importlib
import warnings
import glob
import yaml
import pipes
import json
import getpass
from collections import namedtuple, OrderedDict
from StringIO import StringIO
from pprint import pprint
from fabric.api import (
    env,
    local,
    put as __put,
    get as __get,
    require,
    run as _run,
    settings,
    sudo as _sudo,
    cd,
    hide,
    runs_once,
)
from fabric import state

import fabric.api

if hasattr(fabric.api, '_run'):
    _run = fabric.api._run
    
if hasattr(fabric.api, '_sudo'):
    _sudo = fabric.api._sudo

PACKAGERS = APT, YUM = ('apt-get', 'yum')

OS_TYPES = LINUX, WINDOWS = ('linux', 'windows')
OS_DISTRO = FEDORA, UBUNTU = ('fedora', 'ubuntu')
FEDORA_13 = 'fedora-13'
FEDORA_16 = 'fedora-16'

SYSTEM = 'system'
RUBY = 'ruby'
PYTHON = 'python'
PACKAGE_TYPES = (
    SYSTEM,
    PYTHON, # pip
    RUBY, # gem
)

ALL = 'all' # denotes the global role

START = 'start'
STOP = 'stop'
STATUS = 'status'
RELOAD = 'reload'
RESTART = 'restart'
ENABLE = 'enable'
DISABLE = 'disable'
STATUS = 'status'
SERVICE_COMMANDS = (
    START,
    STOP,
    STATUS,
    RESTART,
    ENABLE,
    DISABLE,
    STATUS,
)

OS = namedtuple('OS', ['type', 'distro', 'release'])

ROLE_DIR = env.ROLES_DIR = 'roles'

DJANGO = 'DJANGO'

SITE = 'SITE'
ROLE = 'ROLE'

LOCALHOSTS = ('localhost', '127.0.0.1')

env.confirm_deployment = False
env.is_local = None
env.base_config_dir = '.'
env.src_dir = 'src' # The path relative to fab where the code resides.

env[SITE] = None
env[ROLE] = None

env.sites = {} # {site:site_settings}

# If true, prevents run() from executing its command.
_dryrun = False

_show_command_output = True

env.services = []
required_system_packages = type(env)() # {service:{os:[packages]}
required_python_packages = type(env)() # {service:{os:[packages]}
required_ruby_packages = type(env)() # {service:{os:[packages]}

service_configurators = type(env)() # {service:[func]}
service_pre_deployers = type(env)() # {service:[func]}
service_pre_db_dumpers = type(env)() # {service:[func]}
service_deployers = type(env)() # {service:[func]}
service_post_deployers = type(env)() # {service:[func]}
service_post_db_loaders = type(env)() # {service:[func]}
service_restarters = type(env)() # {service:[func]}
service_stoppers = type(env)() # {service:[func]}

manifest_recorder = type(env)() #{component:[func]}
manifest_comparer = type(env)() #{component:[func]}
manifest_deployers = type(env)() #{component:[func]}
manifest_deployers_befores = type(env)() #{component:[pending components that must be run first]}
#manifest_deployers_afters = type(env)() #{component:[pending components that must be run last]}
manifest_deployers_takes_diff = type(env)()

def add_deployer(event, func, before=[], after=[], takes_diff=False):
    event = event.strip().upper()
    
    manifest_deployers.setdefault(event, [])
    if func not in manifest_deployers[event]:
        manifest_deployers[event].append(func)
    
    manifest_deployers_befores.setdefault(event, [])
    manifest_deployers_befores[event].extend(map(str.upper, before))
    
    for _c in after:
        _c = _c.strip().upper()
        manifest_deployers_befores.setdefault(_c, [])
        manifest_deployers_befores[_c].append(event)
    
    manifest_deployers_takes_diff[func] = takes_diff

def resolve_deployer(func_name):
#     print('func:',func_name)
    if '.' in func_name:
        mod_name, func_name = func_name.split('.')
    else:
        mod_name = 'fabfile'
    ret = getattr(importlib.import_module(mod_name), func_name)
#     print('ret:',ret)
    return ret

env.hosts_retriever = None
env.hosts_retrievers = type(env)() #'default':lambda hostname: hostname,

env.hostname_translator = 'default'
env.hostname_translators = type(env)()
env.hostname_translators.default = lambda hostname: hostname

env.default_site = None

#env.shell_default_dir_template = '/usr/local/%(app_name)s'
env.shell_default_dir_template = '%(remote_app_src_package_dir)s'
env.shell_interactive_shell = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(shell_default_dir)s; /bin/bash -i'

# A list of all site names that should be available on the current host.
env.available_sites = []

# A list of all site names per host.
# {hostname: [sites]}
# If no entry found, will use available_sites.
env.available_sites_by_host = {}

# The command run to determine the percent of disk usage.
env.disk_usage_command = "df -H | grep -vE '^Filesystem|tmpfs|cdrom|none' | awk '{ print $5 " " $1 }'"

env.post_callbacks = []

env.burlap_data_dir = '.burlap'



def shellquote(s, singleline=True):
    if singleline:
        s = pipes.quote(s)
        s = repr(s)
        if s.startswith("u'") or s.startswith('u"'):
            s = s[4:-4]
        else:
            s = s[3:-3]
        s = '"%s"' % s
    else:
        s = '{}'.format(pipes.quote(s))
    return s

def init_burlap_data_dir():
    d = env.burlap_data_dir
    if not os.path.isdir(env.burlap_data_dir):
        os.mkdir(d)

def set_dryrun(dryrun):
    global _dryrun
    _dryrun = bool(int(dryrun or 0))
    if _dryrun:
        state.output.running = False
    else:
        state.output.running = True

def get_dryrun(dryrun=None):
    if dryrun is None or dryrun == '':
        return bool(int(_dryrun or 0))
    return bool(int(dryrun or 0))

def set_show(v):
    _show_command_output = bool(int(v))

def get_show():
    return _show_command_output
    
def render_command_prefix():
    extra = {}
    if env.key_filename:
        extra['key'] = env.key_filename
    extra_s = ''
    if extra:
        extra_s = json.dumps(extra)
    s = '[%s@%s%s]' % (env.user, env.host_string, extra_s)
    return s

def local_or_dryrun(*args, **kwargs):
    dryrun = get_dryrun(kwargs.get('dryrun'))
    if 'dryrun' in kwargs:
        del kwargs['dryrun']
    if dryrun:
        cmd = args[0]
        print '[%s@localhost] local: %s' % (getpass.getuser(), cmd)
    else:
        return local(*args, **kwargs)
        
def run_or_dryrun(*args, **kwargs):
    dryrun = get_dryrun(kwargs.get('dryrun'))
    if 'dryrun' in kwargs:
        del kwargs['dryrun']
    if dryrun:
        cmd = args[0]
        print '%s run: %s' % (render_command_prefix(), cmd)
    else:
        return _run(*args, **kwargs)

def sudo_or_dryrun(*args, **kwargs):
    dryrun = get_dryrun(kwargs.get('dryrun'))
    if 'dryrun' in kwargs:
        del kwargs['dryrun']
    if dryrun:
        cmd = args[0]
        print '%s sudo: %s' % (render_command_prefix(), cmd)
    else:
        return _sudo(*args, **kwargs)

def put_or_dryrun(**kwargs):
    dryrun = get_dryrun(kwargs.get('dryrun'))
    use_sudo = kwargs.get('use_sudo', False)
    if 'dryrun' in kwargs:
        del kwargs['dryrun']
    if dryrun:
        local_path = kwargs['local_path']
        remote_path = kwargs.get('remote_path', None)
        if not remote_path:
            remote_path = tempfile.mktemp()
        if not remote_path.startswith('/'):
            remote_path = '/tmp/' + remote_path
        if env.host_string in LOCALHOSTS:
            cmd = ('sudo ' if use_sudo else '')+'rsync --progress --verbose %s %s' % (local_path, remote_path)
            #print ('sudo ' if use_sudo else '')+'echo "%s" > %s' % (shellquote(open(local_path).read()), remote_path)
            print '%s put: %s' % (render_command_prefix(), cmd)
            env.put_remote_path = local_path
        else:
            cmd = ('sudo ' if use_sudo else '')+'rsync --progress --verbose %s %s' % (local_path, remote_path)
            env.put_remote_path = remote_path
            print '%s put: %s' % (render_command_prefix(), cmd)
            
    else:
        return _put(**kwargs)

def get_or_dryrun(**kwargs):
    dryrun = get_dryrun(kwargs.get('dryrun'))
    use_sudo = kwargs.get('use_sudo', False)
    if 'dryrun' in kwargs:
        del kwargs['dryrun']
    if dryrun:
        local_path = kwargs['local_path']
        remote_path = kwargs.get('remote_path', None)
        if not local_path:
            local_path = tempfile.mktemp()
        if not local_path.startswith('/'):
            local_path = '/tmp/' + local_path
        cmd = ('sudo ' if use_sudo else '')+'rsync --progress --verbose %s@%s:%s %s' % (env.user, env.host_string, remote_path, local_path)
        #print ('sudo ' if use_sudo else '')+'echo "%s" > %s' % (shellquote(open(local_path).read()), remote_path)
        print '[localhost] get: %s' % (cmd,)
        env.get_local_path = local_path
        
    else:
        return _get(**kwargs)

def _get(*args, **kwargs):
    ret = __get(*args, **kwargs)
    env.get_local_path = ret
    return ret

def pretty_bytes(bytes):
    """
    Scales a byte count to the largest scale with a small whole number
    that's easier to read.
    Returns a tuple of the format (scaled_float, unit_string).
    """
    if not bytes:
        return bytes, 'bytes'
    sign = bytes/float(bytes)
    bytes = abs(bytes)
    for x in ['bytes','KB','MB','GB','TB']:
        if bytes < 1024.0:
            #return "%3.1f %s" % (bytes, x)
            return sign*bytes, x
        bytes /= 1024.0

def get_component_settings(prefixes=[]):
    """
    Returns a subset of the env dictionary containing
    only those keys with the name prefix.
    """
    data = {}
    for name in prefixes:
        name = name.lower().strip()
        for k in env:
            if k.startswith('%s_' % name):
                data[k] = env[k]
    return data

def get_last_modified_timestamp(path):
    """
    Recursively finds the most recent timestamp in the given directory.
    """
    import commands
    cmd = 'find '+path+' -type f -printf "%T@ %p\n" | sort -n | tail -1 | cut -f 1 -d " "'
    ret = commands.getoutput(cmd)
    # Note, we round now to avoid rounding errors later on where some formatters
    # use different decimal contexts.
    try: 
        ret = round(float(ret), 2)
    except ValueError:
        return
    return ret

def check_settings_for_differences(old, new, as_bool=False, as_tri=False):
    """
    Returns a subset of the env dictionary keys that differ,
    either being added, deleted or changed between old and new.
    """
    
    assert not as_bool or not as_tri
    
    old = old or {}
    new = new or {}
    
    changes = set(k for k in set(new.iterkeys()).intersection(old.iterkeys()) if new[k] != old[k])
    if changes and as_bool:
        return True
    
    added_keys = set(new.iterkeys()).difference(old.iterkeys())
    if added_keys and as_bool:
        return True
    if not as_tri:
        changes.update(added_keys)
    
    deled_keys = set(old.iterkeys()).difference(new.iterkeys())
    if deled_keys and as_bool:
        return True
    if as_bool:
        return False
    if not as_tri:
        changes.update(deled_keys)
    
    if as_tri:
        return added_keys, changes, deled_keys
    
    return changes

def get_subpackages(module):
    dir = os.path.dirname(module.__file__)
    def is_package(d):
        d = os.path.join(dir, d)
        return os.path.isdir(d) and glob.glob(os.path.join(d, '__init__.py*'))
    return filter(is_package, os.listdir(dir))

def get_submodules(module):
    dir = os.path.dirname(module.__file__)
    def is_module(d):
        d = os.path.join(dir, d)
        return os.path.isfile(d) and glob.glob(os.path.join(d, '*.py*'))
    #print os.listdir(dir)
    return filter(is_module, os.listdir(dir))

def iter_apps():
    sys.path.insert(0, os.getcwd())
    arch = importlib.import_module('arch')
    settings = importlib.import_module('arch.settings')
    INSTALLED_APPS = set(settings.INSTALLED_APPS)
    for sub_name in get_subpackages(arch):
        if sub_name in INSTALLED_APPS:
            yield sub_name

def get_app_package(name):
    sys.path.insert(0, os.getcwd())
    arch = importlib.import_module('arch')
    settings = importlib.import_module('arch.settings')
    INSTALLED_APPS = set(settings.INSTALLED_APPS)
    assert name in INSTALLED_APPS, 'Unknown or uninstalled app: %s' % (name,)
    return importlib.import_module('arch.%s' % name)

def to_dict(obj):
    if isinstance(obj, (tuple, list)):
        return [to_dict(_) for _ in obj]
    elif isinstance(obj, dict):
        return dict((to_dict(k), to_dict(v)) for k,v in obj.iteritems())
    elif isinstance(obj, (int, bool, float, basestring)):
        return obj
    elif hasattr(obj, 'to_dict'):
        return obj.to_dict()
    else:
        raise Exception, 'Unknown type: %s %s' % (obj, type(obj))

class QueuedCommand(object):
    """
    Represents a fabric command that is pending execution.
    """
    
    def __init__(self, name, args=None, kwargs=None, pre=[], post=[]):
        self.name = name
        self.args = args or []
        self.kwargs = kwargs or {}
        
        # Used for ordering commands.
        self.pre = pre # commands that should come before this command
        assert isinstance(self.pre, (tuple, list)), 'Pre must be a list type.'
        self.post = post # commands that should come after this command
        assert isinstance(self.post, (tuple, list)), 'Post must be a list type.'
    
    @property
    def cn(self):
        """
        Returns the component name, if given in the name
        as "<component_name>.method".
        """
        parts = self.name.split('.')
        if len(parts) >= 2:
            return parts[0]
    
    def __repr__(self):
        kwargs = list(map(str, self.args))
        for k,v in self.kwargs.iteritems():
            if isinstance(v, bool):
                kwargs.append('%s=%i' % (k,int(v)))
            elif isinstance(v, basestring) and '=' in v:
                # Escape equals sign character in parameter values.
                kwargs.append('%s="%s"' % (k, v.replace('=', '\=')))
            else:
                kwargs.append('%s=%s' % (k, v))
        params = (self.name, ','.join(kwargs))
        if params[1]:
            return ('%s:%s' % params).strip()
        else:
            return (params[0]).strip()
    
    def __cmp__(self, other):
        """
        Return negative if x<y, zero if x==y, positive if x>y.
        """
        if not isinstance(self, type(other)):
            return NotImplemented
        
        x_cn = self.cn
        x_name = self.name
        x_pre = self.pre
        x_post = self.post
        
        y_cn = other.cn
        y_name = other.name
        y_pre = other.pre
        y_post = other.post
        
        if y_cn in x_pre or y_name in x_pre:
            # Other should come first.
            return +1
        elif y_cn in x_post or y_name in x_post:
            # Other should come last.
            return -1
        elif x_cn in y_pre or x_name in y_pre:
            # We should come first.
            return -1
        elif x_cn in y_post or x_name in y_post:
            # We should come last.
            return -1
        return 0
        #return cmp(hash(self), hash(other))
    
    def __hash__(self):
        return hash((self.name, tuple(self.args), tuple(self.kwargs.items())))
    
    def __call__(self):
        raise NotImplementedError

def get_template_dirs():
    yield os.path.join(env.ROLES_DIR, env[ROLE], 'templates')
    yield os.path.join(env.ROLES_DIR, env[ROLE])
    yield os.path.join(env.ROLES_DIR, '..', 'templates', env[ROLE])
    yield os.path.join(env.ROLES_DIR, ALL, 'templates')
    yield os.path.join(env.ROLES_DIR, ALL)
    yield os.path.join(env.ROLES_DIR, '..', 'templates', ALL)
    yield os.path.join(env.ROLES_DIR, '..', 'templates')
    yield os.path.join(os.path.dirname(__file__), 'templates')
    env.template_dirs = get_template_dirs()

env.template_dirs = get_template_dirs()

def save_env():
    env_default = {}
    for k, v in env.iteritems():
        if k.startswith('_'):
            continue
        elif isinstance(v, (types.GeneratorType, types.ModuleType)):
            continue
        #print type(k),type(v)
        env_default[k] = copy.deepcopy(v)
    return env_default

try:
    from django.conf import settings as _settings
    _settings.configure(TEMPLATE_DIRS=env.template_dirs)
except ImportError:
    warnings.warn('Unable to import Django settings.', ImportWarning)

def _put(**kwargs):
    local_path = kwargs['local_path']
    fd, fn = tempfile.mkstemp()
    if not env.is_local:
        os.remove(fn)
    #kwargs['remote_path'] = kwargs.get('remote_path', '/tmp/%s' % os.path.split(local_path)[-1])
    kwargs['remote_path'] = kwargs.get('remote_path', fn)
    env.put_remote_path = kwargs['remote_path']
    return __put(**kwargs)

def get_rc(k):
    return env._rc.get(env[ROLE], type(env)()).get(k)

def set_rc(k, v):
    env._rc.setdefault(env[ROLE], type(env)())
    env._rc[env[ROLE]][k] = v

def get_packager():
    common_packager = get_rc('common_packager')
    if common_packager:
        return common_packager
    #TODO:cache result by current env.host_string so we can handle multiple hosts with different OSes
    with settings(warn_only=True):
        with hide('running', 'stdout', 'stderr', 'warnings'):
            ret = _run('cat /etc/fedora-release')
            if ret.succeeded:
                common_packager = YUM
            else:
                ret = _run('cat /etc/lsb-release')
                if ret.succeeded:
                    common_packager = APT
                else:
                    for pn in PACKAGERS:
                        ret = run_or_dryrun('which %s' % pn)
                        if ret.succeeded:
                            common_packager = pn
                            break
    if not common_packager:
        raise Exception, 'Unable to determine packager.'
    set_rc('common_packager', common_packager)
    return common_packager

def get_os_version():
    common_os_version = get_rc('common_os_version')
    if common_os_version:
        return common_os_version
    with settings(warn_only=True):
        with hide('running', 'stdout', 'stderr', 'warnings'):
            ret = _run('cat /etc/fedora-release')
            if ret.succeeded:
                common_os_version = OS(
                    type = LINUX,
                    distro = FEDORA,
                    release = re.findall('release ([0-9]+)', ret)[0])
            else:
                ret = _run('cat /etc/lsb-release')
                if ret.succeeded:
                    common_os_version = OS(
                        type = LINUX,
                        distro = UBUNTU,
                        release = re.findall('DISTRIB_RELEASE=([0-9\.]+)', ret)[0])
                else:
                    raise Exception, 'Unable to determine OS version.'
    if not common_os_version:
        raise Exception, 'Unable to determine OS version.'
    set_rc('common_os_version', common_os_version)
    return common_os_version

def find_template(template, verbose=False):
    final_fqfn = None
    for path in get_template_dirs():
        fqfn = os.path.abspath(os.path.join(path, template))
        if os.path.isfile(fqfn):
            if verbose:
                print>>sys.stderr, 'Using template: %s' % (fqfn,)
            final_fqfn = fqfn
            break
        else:
            if verbose:
                print>>sys.stderr, 'Template not found: %s' % (fqfn,)
    return final_fqfn

def render_to_string(template, verbose=True):
    """
    Renders the given template to a string.
    """
    import django
    from django.template import Context, Template
    from django.template.loader import render_to_string
    
    final_fqfn = find_template(template, verbose=verbose)
    assert final_fqfn, 'Template not found: %s' % template
    from django.conf import settings
    try:
        settings.configure()
    except RuntimeError:
        pass
    
    #content = render_to_string('template.txt', dict(env=env))
    template_content = open(final_fqfn, 'r').read()
    t = Template(template_content)
    c = Context(env)
    rendered_content = t.render(c)
    rendered_content = rendered_content.replace('&quot;', '"')
    return rendered_content

def render_to_file(template, fn=None, verbose=True, **kwargs):
    """
    Returns a template to a file.
    If no filename given, a temporary filename will be generated and returned.
    """
    import tempfile
    dryrun = get_dryrun(kwargs.get('dryrun'))
    content = render_to_string(template, verbose=verbose)
    if fn:
        fout = open(fn, 'w')
    else:
        fd, fn = tempfile.mkstemp()
        fout = os.fdopen(fd, 'wt')
    print 'echo -e %s > %s' % (shellquote(content), fn)
    fout.write(content)
    fout.close()
    return fn

def write_to_file(content, fn=None):
    import tempfile
    if fn:
        fout = open(fn, 'w')
    else:
        fd,fn = tempfile.mkstemp()
        fout = os.fdopen(fd, 'wt')
    fout.write(content)
    fout.close()
    return fn

def set_site(site):
    if site is None:
        return
    env[SITE] = os.environ[SITE] = site


def iter_sites(sites=None, site=None, renderer=None, setter=None, no_secure=False, verbose=False):
    """
    Iterates over sites, safely setting environment variables for each site.
    """
    from dj import render_remote_paths
#    print 'site:',env.default_site
#    print 'site:',env.SITE
    #assert sites or site, 'Either site or sites must be specified.'
    if sites is None:
        site = site or env.SITE
        if site == ALL:
            sites = env.sites.iteritems()
        else:
            sites = [(site, env.sites[site])]
        
    renderer = renderer or render_remote_paths
    env_default = save_env()
    for site, site_data in sites:
#        print '-'*80
#        print 'site:',site
#        print 'env.django_settings_module_template00:',env.django_settings_module_template
        if no_secure and site.endswith('_secure'):
            continue
        env.update(env_default)
        env.update(env.sites[site])
        env.SITE = site
        renderer()
#        print 'env.django_settings_module_template01:',env.django_settings_module_template
        if setter:
            setter(site)
#        print 'env.django_settings_module_template02:',env.django_settings_module_template
        yield site, site_data
    env.update(env_default)

def pc(*args):
    """
    Print comment.
    """
    print('echo "%s"' % ' '.join(map(str, args)))

def get_current_hostname():
#    import importlib
#    
#    retriever = None
#    if env.hosts_retriever:
#        # Dynamically retrieve hosts.
#        module_name = '.'.join(env.hosts_retriever.split('.')[:-1])
#        func_name = env.hosts_retriever.split('.')[-1]
#        retriever = getattr(importlib.import_module(module_name), func_name)
#    
#    # Load host translator.
#    translator = None
#    if hostname:
#        # Filter hosts list by a specific host name.
#        module_name = '.'.join(env.hostname_translator.split('.')[:-1])
#        func_name = env.hostname_translator.split('.')[-1]
#        translator = getattr(importlib.import_module(module_name), func_name)
    ret = run_or_dryrun('hostname')#)
    return str(ret)

#http://stackoverflow.com/questions/11557241/python-sorting-a-dependency-list
def topological_sort(source):
    """perform topo sort on elements.

    :arg source: list of ``(name, [list of dependancies])`` pairs
    :returns: list of names, with dependancies listed first
    """
    if isinstance(source, dict):
        source = source.items()
    pending = sorted([(name, set(deps)) for name, deps in source]) # copy deps so we can modify set in-place       
    emitted = []        
    while pending:
        next_pending = []
        next_emitted = []
        for entry in pending:
            name, deps = entry
            deps.difference_update(emitted) # remove deps we emitted last pass
            if deps: # still has deps? recheck during next pass
                next_pending.append(entry) 
            else: # no more deps? time to emit
                yield name 
                emitted.append(name) # <-- not required, but helps preserve original ordering
                next_emitted.append(name) # remember what we emitted for difference_update() in next pass
        if not next_emitted: # all entries have unmet deps, one of two things is wrong...
            raise ValueError("cyclic or missing dependancy detected: %r" % (next_pending,))
        pending = next_pending
        emitted = next_emitted

def represent_ordereddict(dumper, data):
    value = []

    for item_key, item_value in data.items():
        node_key = dumper.represent_data(item_key)
        node_value = dumper.represent_data(item_value)

        value.append((node_key, node_value))

    return yaml.nodes.MappingNode(u'tag:yaml.org,2002:map', value)

yaml.add_representer(OrderedDict, represent_ordereddict)

#TODO:make thread/process safe with lockfile?
class Shelf(object):
    
    def __init__(self, ascii_str=True):
        
        # If true, automatically ensure all string values are plain ASCII.
        # This helps keep the YAML clean, otherwise verbose syntax would be
        # added for non-ASCII encodings, even if the string only contains
        # ASCII characters.
        self.ascii_str = ascii_str
        
    @property
    def filename(self):
        return 'roles/%s/shelf.yaml' % (env.ROLE.lower(),)

    @property
    def _dict(self):
        try:
            return OrderedDict(yaml.load(open(self.filename, 'rb')) or {})
        except IOError:
            return OrderedDict()

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

shelf = Shelf()
