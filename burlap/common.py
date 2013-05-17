import os
import sys
from collections import namedtuple
from fabric.api import (
    env,
    local,
    put as _put,
    require,
    run as _run,
    settings,
    sudo,
    cd,
    task,
)

PACKAGERS = APT, YUM = ('apt-get', 'yum')

OS_TYPES = LINUX, WINDOWS = ('linux', 'windows')
OS_DISTRO = FEDORA, UBUNTU = ('fedora', 'ubuntu')

OS = namedtuple('OS', ['type', 'distro', 'release'])

# Variables cached per-role.
env._rc = type(env)()
#env._rc.common_packager = None
#env._rc.common_os_version = None

def _get_template_dirs():
    yield os.path.join(env.ROLES_DIR, env.role)
    yield os.path.join(env.ROLES_DIR, '..', 'templates', env.role)
    yield os.path.join(env.ROLES_DIR, '..', 'templates')
    yield os.path.join(os.path.dirname(__file__), 'templates')

env.template_dirs = _get_template_dirs()

from django.conf import settings
settings.configure(TEMPLATE_DIRS=env.template_dirs)

def run(*args, **kwargs):
    if env.is_local:
        kwargs['capture'] = True
        result = local(*args, **kwargs)
        print result
        return result
    return _run(*args, **kwargs)

def put(**kwargs):
    local_path = kwargs['local_path']
    kwargs['remote_path'] = kwargs.get('remote_path', '/tmp/%s' % os.path.split(local_path)[-1])
    env.put_remote_path = kwargs['remote_path']
    return _put(**kwargs)

def get_rc(k):
    return env._rc.get(env.role, type(env)()).get(k)

def set_rc(k, v):
    env._rc.setdefault(env.role, type(env))()
    env._rc[env.role][k] = v

def get_packager(self):
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

def get_os_version(self):
    common_os_version = get_rc('common_os_version')
    if common_os_version:
        return common_os_version
    with settings(warn_only=True):
        with hide('running', 'stdout', 'stderr', 'warnings'):
            ret = self.run('cat /etc/fedora-release')
            if ret.succeeded:
                common_os_version = OS(
                    type = LINUX,
                    distro = FEDORA,
                    release = re.findall('release ([0-9]+)', ret)[0])
            else:
                ret = self.run('cat /etc/lsb-release')
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

def render_to_string(template):
    """
    Renders the given template to a string.
    """
    from django.template import Context, Template
    from django.template.loader import render_to_string
    
    final_fqfn = None
    for path in _get_template_dirs():
        fqfn = os.path.join(path, template)
        if os.path.isfile(fqfn):
            print>>sys.stderr, 'Using template: %s' % (fqfn,)
            final_fqfn = fqfn
            break
    assert final_fqfn, 'Template not found in any of:\n%s' % ('\n'.join(paths),)
    
    #content = render_to_string('template.txt', dict(env=env))
    template_content = open(final_fqfn, 'r').read()
    t = Template(template_content)
    c = Context(dict(env=env))
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
    fout.write(rendered_content)
    fout.close()
    return fn
