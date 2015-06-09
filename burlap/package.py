import os
import sys
import tempfile
from collections import OrderedDict

from fabric.api import (
    env,
    require,
)

from burlap import common
from burlap.common import (
    get_packager, APT, YUM, ROLE, SITE,
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    find_template,
    QueuedCommand,
)
from burlap.decorators import task_or_dryrun

env.package_install_apt_extras = []
env.package_install_yum_extras = []

PACKAGER = 'PACKAGER'

@task_or_dryrun
def prepare():
    """
    Preparse the packaging system for installations.
    """
    packager = get_packager()
    if packager == APT:
        sudo_or_dryrun('apt-get update')
    elif package == YUM:
        sudo_or_dryrun('yum update')
    else:
        raise Exception, 'Unknown packager: %s' % (packager,)

@task_or_dryrun
def install(**kwargs):
    refresh()
    install_required(type=common.SYSTEM, **kwargs)
    install_custom(**kwargs)
    
@task_or_dryrun
def install_custom(*args, **kwargs):
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

@task_or_dryrun
def refresh(*args, **kwargs):
    """
    Updates/upgrades all system packages.
    """
    packager = get_packager()
    if packager == APT:
        return refresh_apt(*args, **kwargs)
    elif package == YUM:
        raise NotImplementedError
        #return upgrade_yum(*args, **kwargs)
    else:
        raise Exception, 'Unknown packager: %s' % (packager,)

def refresh_apt():
    sudo_or_dryrun('apt-get update -y --fix-missing')

@task_or_dryrun
def upgrade(*args, **kwargs):
    """
    Updates/upgrades all system packages.
    """
    packager = get_packager()
    if packager == APT:
        return upgrade_apt(*args, **kwargs)
    elif package == YUM:
        raise NotImplementedError
        #return upgrade_yum(*args, **kwargs)
    else:
        raise Exception, 'Unknown packager: %s' % (packager,)

def upgrade_apt():
    sudo_or_dryrun('apt-get update -y --fix-missing')
    sudo_or_dryrun('apt-get upgrade -y')

env.apt_fn = 'apt-requirements.txt'

def install_apt(fn=None, package_name=None, update=0, list_only=0):
    """
    Installs system packages listed in apt-requirements.txt.
    """
    #print 'Installing apt requirements...'
    assert env[ROLE]
    env.apt_fqfn = fn or find_template(env.apt_fn)
    if not env.apt_fqfn:
        return
    assert os.path.isfile(env.apt_fqfn)
    lines = [
        _.strip() for _ in open(env.apt_fqfn).readlines()
        if _.strip() and not _.strip().startswith('#')
        and (not package_name or _.strip() == package_name)
    ]
    if list_only:
        return lines
    fd, tmp_fn = tempfile.mkstemp()
    fout = open(tmp_fn, 'w')
    fout.write('\n'.join(lines))
    fout.close()
    env.apt_fqfn = tmp_fn
    if not env.is_local:
        put_or_dryrun(local_path=tmp_fn)
        env.apt_fqfn = env.put_remote_path
#    if int(update):
    sudo_or_dryrun('apt-get update -y --fix-missing')
    sudo_or_dryrun('apt-get install -y `cat "%(apt_fqfn)s" | tr "\\n" " "`' % env)

env.yum_fn = 'yum-requirements.txt'

def install_yum(fn=None, package_name=None, update=0, list_only=0):
    """
    Installs system packages listed in yum-requirements.txt.
    """
    #print 'Installing yum requirements...'
    assert env[ROLE]
    env.yum_fn = fn or find_template(env.yum_fn)
    assert os.path.isfile(env.yum_fn)
    update = int(update)
    if list_only:
        return [
            _.strip() for _ in open(env.yum_fn).readlines()
            if _.strip() and not _.strip.startswith('#')
            and (not package_name or _.strip() == package_name)
        ]
    if update:
        sudo_or_dryrun('yum update --assumeyes')
    if package_name:
        sudo_or_dryrun('yum install --assumeyes %s' % package_name)
    else:
        if env.is_local:
            put_or_dryrun(local_path=env.yum_fn)
            env.yum_fn = env.put_remote_fn
        sudo_or_dryrun('yum install --assumeyes $(cat %(yum_fn)s)' % env)

@task_or_dryrun
def list_required(type=None, service=None, verbose=True):
    """
    Displays all packages required by the current role
    based on the documented services provided.
    """
    service = (service or '').strip().upper()
    type = (type or '').lower().strip()
    assert not type or type in common.PACKAGE_TYPES, \
        'Unknown package type: %s' % (type,)
    packages_set = set()
    packages = []
    version = common.get_os_version()
    for _service in env.services:
        _service = _service.strip().upper()
        if service and service != _service:
            continue
        _new = []
        if not type or type == common.SYSTEM:
            _new.extend(common.required_system_packages.get(
                _service, {}).get((version.distro, version.release), []))
        if not type or type == common.PYTHON:
            _new.extend(common.required_python_packages.get(
                _service, {}).get((version.distro, version.release), []))
        if not type or type == common.RUBY:
            _new.extend(common.required_ruby_packages.get(
                _service, {}).get((version.distro, version.release), []))
#         if not _new and verbose:
#             print>>sys.stderr, \
#                 'Warning: no packages found for service "%s"' % (_service,)
        for _ in _new:
            if _ in packages_set:
                continue
            packages_set.add(_)
            packages.append(_)
    if verbose:
        for package in sorted(packages):
            print package
    return packages

@task_or_dryrun
def install_required(type=None, service=None, list_only=0, verbose=0, **kwargs):
    """
    Installs system packages listed as required by services this host uses.
    """
    verbose = int(verbose)
    list_only = int(list_only)
    type = (type or '').lower().strip()
    assert not type or type in common.PACKAGE_TYPES, \
        'Unknown package type: %s' % (type,)
    lst = []
    if type:
        types = [type]
    else:
        types = common.PACKAGE_TYPES
    for type in types:
        if type == common.SYSTEM:
            content = '\n'.join(list_required(type=type, service=service))
            if list_only:
                lst.extend(_ for _ in content.split('\n') if _.strip())
                if verbose:
                    print content
                break
            fd, fn = tempfile.mkstemp()
            fout = open(fn, 'w')
            fout.write(content)
            fout.close()
            install_custom(fn=fn)
        else:
            raise NotImplementedError
    return lst
            
@task_or_dryrun
def record_manifest(verbose=0):
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = []
    
    data.extend(install_required(type=common.SYSTEM, verbose=False, list_only=True))
    data.extend(install_custom(list_only=True))
    
    data.sort()
    if int(verbose):
        print data
    return data

common.manifest_recorder[PACKAGER] = record_manifest

common.add_deployer(PACKAGER, 'package.install', before=['user'])
