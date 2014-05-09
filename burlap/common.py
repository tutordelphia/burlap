import os
import re
import sys
import types
import copy
import tempfile
import importlib
import warnings
import glob
from collections import namedtuple
from StringIO import StringIO
from pprint import pprint
from fabric.api import (
    env,
    local,
    put as _put,
    require,
    run as _run,
    settings,
    sudo,
    cd,
    hide,
    task,
)

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

env.confirm_deployment = False
env.is_local = None
env.base_config_dir = '.'
env.src_dir = 'src' # The path relative to fab where the code resides.

env[SITE] = None
env[ROLE] = None

env.sites = {} # {site:site_settings}

# If true, prevents run() from executing its command.
env.dryrun = 0

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

# The command run to determine the percent of disk usage.
env.disk_usage_command = "df -H | grep -vE '^Filesystem|tmpfs|cdrom|none' | awk '{ print $5 " " $1 }'"

env.post_callbacks = []

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

def get_component_settings(name):
    """
    Returns a subset of the env dictionary containing
    only those keys with the name prefix.
    """
    name = name.lower().strip()
    assert len(name), 'No name specified.'
    data = {}
    for k in env:
        if k.startswith('%s_' % name):
            data[k] = env[k]
    return data

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

class Role(object):
    
    def __init__(self):
        pass

    @classmethod
    def to_dict(cls):
        return (cls.__name__,) #TODO:add vars

class Meta(object):
    
    def __init__(self, **kwargs):
        self.abstract = False
        self.__dict__.update(kwargs)

class MigratableMetaclass(type):
    
    def __new__(cls, clsname, bases, dct):
#        print '-'*80
#        print 'MigratableMetaclass:',cls, clsname, bases, dct
        local_meta = dct.get('Meta')
#        print 'local meta:',local_meta and local_meta.abstract
        if local_meta:
            dct['_meta'] = Meta(**local_meta.__dict__)
        else:
            dct['_meta'] = Meta(abstract=False)
#        print '_meta:',dct['_meta'].abstract
        return type.__new__(cls, clsname, bases, dct)

class Migratable(object):
    
    __metaclass__ = MigratableMetaclass
    
    class Meta:
        abstract = False
    
    def __init__(self):
        pass
    
    @classmethod
    def to_dict(cls):
        return {}
    
class BaseMigration(object):
    
    components = {}
    
    def __init__(self):
        pass
    
    def forwards(self):
        pass
    
    def backwards(self):
        pass

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

class AppHandler(object):
    
    def __init__(self, name):
        self.name = name
        self.package = get_app_package(name)

    @property
    def base_dir(self):
        return os.path.split(self.package.__file__)[0]

    @property
    def migrations_dir(self):
        return os.path.join(self.base_dir, 'migrations')

    def init_migrations(self):
        migrations_dir = self.migrations_dir
        if not os.path.isdir(migrations_dir):
            os.makedirs(migrations_dir)
        f = os.path.join(migrations_dir, '__init__.py')
        if not os.path.isfile(f):
            open(f, 'w').write('')

    def get_migrations(self):
        migrations = importlib.import_module('arch.%s.migrations' % (self.name,))
        return get_submodules(migrations)

    def to_dict(self, migratable):
        d = {}
        d['Meta'] = {} #TODO:load ._meta
        for _name in dir(migratable):
            if _name.startswith('__') or _name == 'Meta' or _name == '_meta':
                continue
            value = getattr(migratable, _name)
            if callable(value):
                continue
            d[_name] = to_dict(value)
        return d

    def create_initial_migration(self):
        template = [
            '# -*- coding: utf-8 -*-',
            'from burlap.common import BaseMigration',
            '',
            'class Migration(BaseMigration):',
            '',
            '    def forwards(self):',
            '        pass',
            '',
            '    def backwards(self):',
            '        pass',
            '',
        ]
    
#        print 'initial'
#        print dir(self.package)
        components = importlib.import_module('arch.%s.components' % self.name)
        components_dict = {}
        for _name in dir(components):
            cls = getattr(components, _name)
            try:
                if issubclass(cls, Migratable):
                    if cls._meta.abstract:
                        continue
#                    print cls
#                    print dir(cls)
#                    print 'dict:',self.to_dict(cls)
                    components_dict[cls.__name__] = self.to_dict(cls)
            except TypeError:
                pass
            
        fout = StringIO()
        pprint(components_dict, stream=fout, indent=4)
            
        template.extend([
            '    components = {',
            '\n'.join((' '*8)+_ for _ in fout.getvalue().split('\n')),
            '    }',
        ])
        template_str = '\n'.join(template)
        print template_str

    def create_migration(self, initial=False):
        self.init_migrations()
        migrations = self.get_migrations()
        if initial:
            if migrations:
                raise Exception, 'Unable to create initial migration because migrations already exist.'
            self.create_initial_migration()
        elif migrations:
            # Compare last migration state to current state.
            todo
        else:
            raise Exception, 'No existing migrations. Run with --initial to create first migration.'
        
    def migrate(self):
        todo

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

def run(*args, **kwargs):
#    if env.is_local:
#        kwargs['capture'] = True
#        if env.dryrun:
#            print args, kwargs
#        else:
#            print args, kwargs
#            cmd = ' '.join(args)
#            #cmd = ' '.join(args + ('2>&1',))
#            try:
#                output = StringIO()
#                error = StringIO()
#                sys.stdout = output
#                sys.stderr = error
#                result = local(cmd, **kwargs)
#            except:
#                raise
#            finally:
#                sys.stdout = sys.__stdout__
#                sys.stderr = sys.__stderr__
#                print 'stdout:',output.getvalue()
#                print 'stderr:',error.getvalue()
##            print 'result:',result
##            print 'stdout:',result.stdout
##            print 'stderr:',result.stderr
#            print 
#            return result
    if env.dryrun:
        print ' '.join(map(str, args)), kwargs
    else:
        return _run(*args, **kwargs)

def put(**kwargs):
    local_path = kwargs['local_path']
    fd, fn = tempfile.mkstemp()
    if not env.is_local:
        os.remove(fn)
    #kwargs['remote_path'] = kwargs.get('remote_path', '/tmp/%s' % os.path.split(local_path)[-1])
    kwargs['remote_path'] = kwargs.get('remote_path', fn)
    env.put_remote_path = kwargs['remote_path']
    return _put(**kwargs)

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
            ret = run('cat /etc/fedora-release')
            if ret.succeeded:
                common_packager = YUM
            else:
                ret = run('cat /etc/lsb-release')
                if ret.succeeded:
                    common_packager = APT
                else:
                    for pn in PACKAGERS:
                        ret = run('which %s' % pn)
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
            ret = run('cat /etc/fedora-release')
            if ret.succeeded:
                common_os_version = OS(
                    type = LINUX,
                    distro = FEDORA,
                    release = re.findall('release ([0-9]+)', ret)[0])
            else:
                ret = run('cat /etc/lsb-release')
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
    from django.template import Context, Template
    from django.template.loader import render_to_string
    
    final_fqfn = find_template(template, verbose=verbose)
#    for path in get_template_dirs():
#        fqfn = os.path.abspath(os.path.join(path, template))
#        if os.path.isfile(fqfn):
#            print>>sys.stderr, 'Using template: %s' % (fqfn,)
#            final_fqfn = fqfn
#            break
#        else:
#            print>>sys.stderr, 'Template not found: %s' % (fqfn,)
    assert final_fqfn, 'Template not found in any of:\n%s' % ('\n'.join(paths),)
    
    #content = render_to_string('template.txt', dict(env=env))
    template_content = open(final_fqfn, 'r').read()
    t = Template(template_content)
    c = Context(env)
    rendered_content = t.render(c)
    rendered_content = rendered_content.replace('&quot;', '"')
    return rendered_content

def render_to_file(template, fn=None, verbose=True):
    """
    Returns a template to a file.
    If no filename given, a temporary filename will be generated and returned.
    """
    import tempfile
    content = render_to_string(template, verbose=verbose)
    if fn:
        fout = open(fn, 'w')
    else:
        fd,fn = tempfile.mkstemp()
        fout = os.fdopen(fd, 'wt')
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

@task
def info():
    print 'ROLE:',env.ROLE
    print 'SITE:',env.SITE
    print 'default_site:',env.default_site

@task
def shell(gui=0, dryrun=0):
    """
    Opens a UNIX shell.
    """
    from dj import render_remote_paths
    render_remote_paths()
    print 'env.remote_app_dir:',env.remote_app_dir
    env.SITE = env.SITE or env.default_site
    env.shell_x_opt = '-X' if int(gui) else ''
    if '@' in env.host_string:
        env.shell_host_string = env.host_string
    else:
        env.shell_host_string = '%(user)s@%(host_string)s' % env
    env.shell_default_dir = env.shell_default_dir_template % env
    env.shell_interactive_shell_str = env.shell_interactive_shell % env
    if env.is_local:
        cmd = '%(shell_interactive_shell_str)s' % env
    else:
        cmd = 'ssh -t %(shell_x_opt)s -i %(key_filename)s %(shell_host_string)s "%(shell_interactive_shell_str)s"' % env
    print cmd
    if int(dryrun):
        return
    os.system(cmd)

def iter_sites(sites=None, site=None, renderer=None, setter=None, no_secure=False):
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
        if no_secure and site.endswith('_secure'):
            continue
        env.update(env_default)
        env.update(env.sites[site])
        env.SITE = site
        renderer()
        if setter:
            setter(site)
        yield site, site_data
    env.update(env_default)

@task
def disk():
    """
    Display percent of disk usage.
    """
    run(env.disk_usage_command % env)

@task
def tunnel(local_port, remote_port):
    """
    Creates an SSH tunnel.
    """
    env.tunnel_local_port = local_port
    env.tunnel_remote_port = remote_port
    local(' ssh -i %(key_filename)s -L %(tunnel_local_port)s:localhost:%(tunnel_remote_port)s %(user)s@%(host_string)s -N' % env)
