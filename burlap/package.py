import os
import sys
import tempfile

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    sudo,
    task,
)

from burlap import common
from burlap.common import (
    get_packager, APT, YUM, ROLE, SITE, put,
    find_template,
)

env.package_install_apt_extras = []
env.package_install_yum_extras = []

@task
def prepare():
    """
    Preparse the packaging system for installations.
    """
    packager = get_packager()
    if packager == APT:
        sudo('apt-get update')
    elif package == YUM:
        sudo('yum update')
    else:
        raise Exception, 'Unknown packager: %s' % (packager,)

@task
def install(*args, **kwargs):
    """
    Installs all system packages listed in the appropriate
    <packager>-requirements.txt.
    """
    packager = get_packager()
    if packager == APT:
        return install_apt(*args, **kwargs)
    elif package == YUM:
        return install_yum(*args, **kwargs)
    else:
        raise Exception, 'Unknown packager: %s' % (packager,)

env.apt_fn = 'apt-requirements.txt'

def install_apt(fn=None, update=0):
    """
    Installs system packages listed in apt-requirements.txt.
    """
    print 'Installing apt requirements...'
    assert env[ROLE]
    env.apt_fqfn = fn or find_template(env.apt_fn)
    assert os.path.isfile(env.apt_fqfn)
    fd, tmp_fn = tempfile.mkstemp()
    lines = [
        _ for _ in open(env.apt_fqfn).readlines()
        if _.strip() and not _.strip().startswith('#')
    ]
    fout = open(tmp_fn, 'w')
    fout.write('\n'.join(lines))
    fout.close()
    if not env.is_local:
        put(local_path=tmp_fn)
        env.apt_fqfn = env.put_remote_path
    if int(update):
        sudo('apt-get update -y')
    sudo('apt-get install -y `cat "%(put_remote_path)s" | tr "\\n" " "`' % env)

env.yum_fn = 'yum-requirements.txt'

def install_yum(fn=None, update=0):
    """
    Installs system packages listed in yum-requirements.txt.
    """
    print 'Installing yum requirements...'
    assert env[ROLE]
    env.yum_fn = fn or find_template(env.yum_fn)
    assert os.path.isfile(env.yum_fn)
    update = int(update)
    env.yum_remote_fn = env.yum_fn
    if env.is_local:
        put(local_path=env.yum_fn)
        env.yum_remote_fn = env.put_remote_fn
    if update:
        sudo('yum update --assumeyes')
    sudo('yum install --assumeyes $(cat %(yum_remote_fn)s)' % env)

@task
def list_required(type=None, service=None):
    """
    Displays all packages required by the current role
    based on the documented services provided.
    """
    service = (service or '').strip().upper()
    type = (type or '').lower().strip()
    assert not type or type in common.PACKAGE_TYPES, \
        'Unknown package type: %s' % (type,)
    packages = set()
    version = common.get_os_version()
    for _service in env.services:
        _service = _service.strip().upper()
        if service and service != _service:
            continue
        _new = []
        if not type or type == common.SYSTEM:
            _new.extend(common.required_system_packages.get(
                _service, {}).get(version.distro, []))
        if not type or type == common.PYTHON:
            _new.extend(common.required_python_packages.get(
                _service, {}).get(version.distro, []))
        if not type or type == common.RUBY:
            _new.extend(common.required_ruby_packages.get(
                _service, {}).get(version.distro, []))
        if not _new:
            print>>sys.stderr, \
                'Warning: no packages found for service "%s"' % (_service,)
        packages.update(_new)
    for package in sorted(packages):
        print package
    return packages

@task
def install_required(type=None, service=None):
    type = (type or '').lower().strip()
    assert not type or type in common.PACKAGE_TYPES, \
        'Unknown package type: %s' % (type,)
    if type:
        types = [type]
    else:
        types = common.PACKAGE_TYPES
    for type in types:
        if type == common.SYSTEM:
            content = '\n'.join(list_required(type=type, service=service))
            fd, fn = tempfile.mkstemp()
            fout = open(fn, 'w')
            fout.write(content)
            fout.close()
            install(fn=fn)
        else:
            raise NotImplementedError
        