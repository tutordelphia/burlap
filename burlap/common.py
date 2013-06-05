import os
import re
import sys
import tempfile
from collections import namedtuple
from StringIO import StringIO
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

ALL = 'all' # denotes the global role

START = 'start'
STOP = 'stop'
STATUS = 'status'
RESTART = 'restart'
ENABLE = 'enable'
DISABLE = 'disable'
SERVICE_COMMANDS = (
    START,
    STOP,
    STATUS,
    RESTART,
    ENABLE,
    DISABLE,
)

OS = namedtuple('OS', ['type', 'distro', 'release'])

ROLE_DIR = env.ROLES_DIR = 'roles'

SITE = 'SITE'
ROLE = 'ROLE'

# If true, prevents run() from executing its command.
env.dryrun = 0

env.hosts_retriever = None
env.hosts_retrievers = {
    #'default':lambda hostname: hostname,
}

env.hostname_translator = 'default'
env.hostname_translators = {
    'default':lambda hostname: hostname,
}

env.default_site = None

# This is where your application's custom code will reside on the remote
# server.
env.remote_app_dir_template = '/usr/local/%(app_name)s'
env.remote_app_src_dir_template = '/usr/local/%(app_name)s/%(src_dir)s'
env.remote_app_src_package_dir_template = '/usr/local/%(app_name)s/%(src_dir)s/%(app_name)s'

def render_remote_paths():
    env.remote_app_dir = env.remote_app_dir_template % env
    env.remote_app_src_dir = env.remote_app_src_dir_template % env
    env.remote_app_src_package_dir = env.remote_app_src_package_dir_template % env

# This is the name of the executable to call to access Django's management
# features.
env.django_manage = './manage'

def get_template_dirs():
    yield os.path.join(env.ROLES_DIR, env[ROLE])
    yield os.path.join(env.ROLES_DIR, '..', 'templates', env[ROLE])
    yield os.path.join(env.ROLES_DIR, ALL)
    yield os.path.join(env.ROLES_DIR, '..', 'templates', ALL)
    yield os.path.join(env.ROLES_DIR, '..', 'templates')
    yield os.path.join(os.path.dirname(__file__), 'templates')
    env.template_dirs = get_template_dirs()

env.template_dirs = get_template_dirs()

from django.conf import settings as _settings
_settings.configure(TEMPLATE_DIRS=env.template_dirs)

def run(*args, **kwargs):
    if env.is_local:
        kwargs['capture'] = True
        if env.dryrun:
            print args, kwargs
        else:
            print args, kwargs
            cmd = ' '.join(args)
            #cmd = ' '.join(args + ('2>&1',))
            try:
                output = StringIO()
                error = StringIO()
                sys.stdout = output
                sys.stderr = error
                result = local(cmd, **kwargs)
            except:
                raise
            finally:
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                print 'stdout:',output.getvalue()
                print 'stderr:',error.getvalue()
#            print 'result:',result
#            print 'stdout:',result.stdout
#            print 'stderr:',result.stderr
            print 
            return result
    if env.dryrun:
        print args, kwargs
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

def find_template(template):
    final_fqfn = None
    for path in get_template_dirs():
        fqfn = os.path.abspath(os.path.join(path, template))
        if os.path.isfile(fqfn):
            print>>sys.stderr, 'Using template: %s' % (fqfn,)
            final_fqfn = fqfn
            break
        else:
            print>>sys.stderr, 'Template not found: %s' % (fqfn,)
    return final_fqfn

def render_to_string(template):
    """
    Renders the given template to a string.
    """
    from django.template import Context, Template
    from django.template.loader import render_to_string
    
    final_fqfn = find_template(template)
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
    return rendered_content

def render_to_file(template, fn=None):
    """
    Returns a template to a file.
    If no filename given, a temporary filename will be generated and returned.
    """
    import tempfile
    content = render_to_string(template)
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
    
def get_settings(site=None, role=None):
    """
    Retrieves the Django settings dictionary.
    """
    sys.path.insert(0, env.src_dir)
    set_site(site)
    tmp_role = env.ROLE
    if role:
        env.ROLE = os.environ[ROLE] = role
    print 'environ.SITE:',os.environ.get(SITE)
    print 'environ.ROLE:',os.environ.get(ROLE)
    env.django_settings_module = env.django_settings_module_template % env
    print 'django_settings_module:',env.django_settings_module
    module = __import__(
        env.django_settings_module,
        fromlist='.'.join(env.django_settings_module.split('.')[:-1]))
    print 'module:',module
    env.ROLE = os.environ[ROLE] = tmp_role
    return module

env.shell_default_dir_template = '/usr/local/%(app_name)s'
env.shell_interactive_shell = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(shell_default_dir)s; /bin/bash -i'
env.shell_interactive_djshell = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(shell_default_dir)s; /bin/bash -i -c \"./manage shell;\"'

@task
def shell(gui=0, dryrun=0):
    """
    Opens a UNIX shell.
    """
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

@task
def djshell():
    """
    Opens a Django shell.
    """
    if '@' in env.host_string:
        env.shell_host_string = env.host_string
    else:
        env.shell_host_string = '%(user)s@%(host_string)s' % env
    env.shell_default_dir = env.shell_default_dir_template % env
    env.shell_interactive_djshell_str = env.shell_interactive_djshell % env
    if env.is_local:
        cmd = '%(shell_interactive_djshell_str)s' % env
    else:
        cmd = 'ssh -t -i %(key_filename)s %(shell_host_string)s "%(shell_interactive_djshell_str)s"' % env
    #print cmd
    os.system(cmd)
