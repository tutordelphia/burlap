import os
import re
import tempfile

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    #run as _run,
    run,
    settings,
    sudo,
    cd,
    task,
)

from fabric.contrib import files
from fabric.tasks import Task

from burlap import common
from burlap.common import (
    run,
    put,
    SITE,
    ROLE,
    render_remote_paths,
    find_template,
    QueuedCommand,
)

env.pip_build_directory = '/tmp/pip-build-root/pip'
env.pip_user = 'www-data'
env.pip_group = 'www-data'
env.pip_chmod = '775'
env.pip_python_version = 2.7
env.pip_virtual_env_dir_template = '%(remote_app_dir)s/.env'
env.pip_virtual_env_dir = '.env'
env.pip_virtual_env_exe = sudo
env.pip_requirements_fn = 'pip-requirements.txt'
env.pip_use_virt = True
env.pip_build_dir = '/tmp/pip-build'
env.pip_path = 'pip-%(pip_python_version)s'
env.pip_update_command = '%(pip_path_versioned)s install --use-mirrors --timeout=120 --no-install %(pip_no_deps)s --build %(pip_build_dir)s --download %(pip_cache_dir)s --exists-action w %(pip_package)s'
#env.pip_install_command = 'cd %(pip_virtual_env_dir)s; . %(pip_virtual_env_dir)s/bin/activate; pip install --upgrade --timeout=60 "%(pip_package)s"; deactivate'
env.pip_remote_cache_dir = '/tmp/pip_cache'
env.pip_local_cache_dir_template = './.pip_cache/%(ROLE)s'
env.pip_upgrade = ''
env.pip_install_command = ". %(pip_virtual_env_dir)s/bin/activate; %(pip_path_versioned)s install %(pip_no_deps)s %(pip_upgrade_flag)s --build %(pip_build_dir)s --find-links file://%(pip_cache_dir)s --no-index %(pip_package)s; deactivate"
env.pip_uninstall_command = ". %(pip_virtual_env_dir)s/bin/activate; %(pip_path_versioned)s uninstall %(pip_package)s; deactivate"

INSTALLED = 'installed'
PENDING = 'pending'

PIP = 'PIP'

common.required_system_packages[PIP] = {
    common.FEDORA: ['python-pip'],
    common.UBUNTU: ['python-pip', 'python-virtualenv', 'gcc', 'python-dev'],
}

def render_paths():
    env.pip_path_versioned = env.pip_path % env
    render_remote_paths()
    if env.pip_virtual_env_dir_template:
        env.pip_virtual_env_dir = env.pip_virtual_env_dir_template % env
    if env.is_local:
        env.pip_virtual_env_dir = os.path.abspath(env.pip_virtual_env_dir)

def clean_virtualenv():
    render_paths()
    with settings(warn_only=True):
        print 'Deleting old virtual environment...'
        sudo('rm -Rf %(pip_virtual_env_dir)s' % env)
    assert not files.exists(env.pip_virtual_env_dir), \
        'Unable to delete pre-existing environment.'

@task
def init(clean=0, check_global=0):
    """
    Creates the virtual environment.
    """
    assert env[ROLE]
    
    render_paths()
    
    # Delete any pre-existing environment.
    if int(clean):
        clean_virtualenv()
    
    # Important. Default Ubuntu 12.04 package uses Pip 1.0, which
    # is horribly buggy. Should use 1.3 or later.
    if int(check_global):
        print 'Ensuring the global pip install is up-to-date.'
        sudo('pip install --upgrade pip')
    
    print env.pip_virtual_env_dir
    if not files.exists(env.pip_virtual_env_dir):
        print 'Creating new virtual environment...'
        cmd = 'virtualenv --no-site-packages %(pip_virtual_env_dir)s' % env
        if env.is_local:
            run(cmd)
        else:
            sudo(cmd)
        
    if not env.is_local:
        sudo('chown -R %(pip_user)s:%(pip_group)s %(remote_app_dir)s' % env)
        sudo('chmod -R %(pip_chmod)s %(remote_app_dir)s' % env)

def iter_pip_requirements():
    for line in open(find_template(env.pip_requirements_fn)):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        yield line
        
def get_desired_package_versions(preserve_order=False):
    versions_lst = []
    versions = {}
    for line in open(find_template(env.pip_requirements_fn)).read().split('\n'):
        if not line.strip() or line.startswith('#'):
            continue
        #print line
        matches = re.findall('([a-zA-Z0-9\-_]+)[\=\<\>]{2}(.*)', line)
        if matches:
            if matches[0][0] not in versions_lst:
                versions_lst.append((matches[0][0], (matches[0][1], line)))
            versions[matches[0][0]] = (matches[0][1], line)
        else:
            matches = re.findall('([a-zA-Z\-]+)\-([0-9\.]+)(?:$|\.)', line)
            if matches:
                if matches[0][0] not in versions_lst:
                    versions_lst.append((matches[0][0], (matches[0][1], line)))
                versions[matches[0][0]] = (matches[0][1], line)
            else:
                if line not in versions_lst:
                    versions_lst.append((line, ('current', line)))
                versions[line] = ('current', line)
    if preserve_order:
        return versions_lst
    return versions

@task
def check(return_type=PENDING):
    """
    Lists the packages that are missing or obsolete on the target.
    
    return_type := pending|installed
    """
    assert env[ROLE]
    
    env.pip_path_versioned = env.pip_path % env
    init()
    
    def get_version_nums(v):
        if re.findall('^[0-9\.]+$', v):
            return tuple(int(_) for _ in v.split('.') if _.strip().isdigit())
    
    use_virt = env.pip_use_virt
    if use_virt:
        cmd_template = ". %(pip_virtual_env_dir)s/bin/activate; %(pip_path_versioned)s freeze; deactivate"
    else:
        cmd_template = "%(pip_path_versioned)s freeze"
    cmd = cmd_template % env
    result = run(cmd)
    installed_package_versions = {}
    for line in result.split('\n'):
        line = line.strip()
        if not line:
            continue
        if ' ' in line:
            continue
        k, v = line.split('==')
        if not k.strip() or not v.strip():
            continue
        print 'Installed:',k,v
        installed_package_versions[k.strip()] = v.strip()
        
    desired_package_version = get_desired_package_versions()
    for k,v in desired_package_version.iteritems():
        print 'Desired:',k,v
    
    pending = [] # (package_line, type)]
    
    not_installed = {}
    for k, (v, line) in desired_package_version.iteritems():
        if k not in installed_package_versions:
            not_installed[k] = (v, line)
            
    if not_installed:
        print '!'*80
        print 'Not installed:'
        for k,(v,line) in sorted(not_installed.iteritems(), key=lambda o:o[0]):
            print k,v
            pending.append((line,'install'))
    else:
        print '-'*80
        print 'All are installed.'
    
    obsolete = {}
    for k,(v,line) in desired_package_version.iteritems():
        #line
        if v != 'current' and v != installed_package_versions.get(k,v):
            obsolete[k] = (v, line)
    if obsolete:
        print '!'*80
        print 'Obsolete:'
        for k,(v0,line) in sorted(obsolete.iteritems(), key=lambda o:o[0]):
            v0nums = get_version_nums(v0) or v0
            v1 = installed_package_versions[k]
            v1nums = get_version_nums(v1) or v1
            #print 'v1nums > v0nums:',v1nums, v0nums
            installed_is_newer = v1nums > v0nums
            newer_str = ''
            if installed_is_newer:
                newer_str = ', this is newer!!! Update pip-requirements.txt???'
            print k,v0,'(Installed is %s%s)' % (v1, newer_str)
            pending.append((line,'update'))
    else:
        print '-'*80
        print 'None are obsolete.'
    
    if return_type == INSTALLED:
        return installed_package_versions
    return pending

@task
def update(package='', ignore_errors=0, no_deps=0, all=0):
    """
    Updates the local cache of pip packages.
    
    If all=1, skips check of host and simply updates everything.
    """
    assert env[ROLE]
    ignore_errors = int(ignore_errors)
    env.pip_path_versioned = env.pip_path % env
    env.pip_local_cache_dir = env.pip_local_cache_dir_template % env
    env.pip_cache_dir = env.pip_local_cache_dir
    if not os.path.isdir(env.pip_cache_dir):
        os.makedirs(env.pip_cache_dir)
    env.pip_package = (package or '').strip()
    env.pip_no_deps = '--no-deps' if int(no_deps) else ''
    env.pip_build_dir = tempfile.mkdtemp()
    
    # Clear build directory in case it wasn't properly cleaned up previously.
    sudo('rm -Rf %(pip_build_directory)s' % env)
    
    with settings(warn_only=ignore_errors):
        if package:
            # Download a single specific package.
            local(env.pip_update_command % env)
        else:
            # Download each package in a requirements file.
            # Note, specifying the requirements file in the command isn't properly
            # supported by pip, thus we have to parse the file itself and send each
            # to pip separately.
            
            if int(all):
                packages = list(iter_pip_requirements())
            else:
                packages = [k for k,v in check()]
            
            for package in packages:
                env.pip_package = package.strip()
                local(env.pip_update_command % env)

@task
def upgrade_pip():
    render_remote_paths()
    if env.pip_virtual_env_dir_template:
        env.pip_virtual_env_dir = env.pip_virtual_env_dir_template % env
    run(". %(pip_virtual_env_dir)s/bin/activate; pip install --upgrade setuptools" % env)
    run(". %(pip_virtual_env_dir)s/bin/activate; pip install --upgrade distribute" % env)

@task
def uninstall(package):
    
    render_remote_paths()
    if env.pip_virtual_env_dir_template:
        env.pip_virtual_env_dir = env.pip_virtual_env_dir_template % env
    
    env.pip_local_cache_dir = env.pip_local_cache_dir_template % env
    
    env.pip_package = package
    if env.is_local:
        run(env.pip_uninstall_command % env)
    else:
        sudo(env.pip_uninstall_command % env)
    
@task
def install(package='', clean=0, no_deps=1, all=0, upgrade=1):
    """
    Installs the local cache of pip packages.
    """
    print 'Installing pip requirements...'
    assert env[ROLE]
    require('is_local')
    
    # Delete any pre-existing environment.
    if int(clean):
        clean_virtualenv()
    
    render_remote_paths()
    if env.pip_virtual_env_dir_template:
        env.pip_virtual_env_dir = env.pip_virtual_env_dir_template % env
    
    env.pip_local_cache_dir = env.pip_local_cache_dir_template % env
    
    env.pip_path_versioned = env.pip_path % env
    if env.is_local:
        env.pip_cache_dir = os.path.abspath(env.pip_local_cache_dir % env)
    else:
        env.pip_cache_dir = env.pip_remote_cache_dir % env
        env.pip_key_filename = os.path.abspath(env.key_filename)
        local('rsync -avz --progress --rsh "ssh -i %(pip_key_filename)s" %(pip_local_cache_dir)s/* %(user)s@%(host_string)s:%(pip_remote_cache_dir)s' % env)
    
    env.pip_upgrade_flag = ''
    if int(upgrade):
        env.pip_upgrade_flag = ' -U '
    
    env.pip_no_deps = ''
    if int(no_deps):
        env.pip_no_deps = '--no-deps'
    
    if int(all):
        packages = list(iter_pip_requirements())
    elif package:
        packages = [package]
    else:
        packages = [k for k,v in check()]
    
    env.pip_build_dir = tempfile.mkdtemp()
    for package in packages:
        env.pip_package = package
        if env.is_local:
            run(env.pip_install_command % env)
        else:
            sudo(env.pip_install_command % env)

    if not env.is_local:
        sudo('chown -R %(pip_user)s:%(pip_group)s %(remote_app_dir)s' % env)
        sudo('chmod -R %(pip_chmod)s %(remote_app_dir)s' % env)

@task
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    # Not really necessary, because pre-deployment, we'll just retrieve this
    # list again, but it's nice to have a separate record to detect
    # non-deployment changes to installed packages.
    #data = check(return_type=INSTALLED)
    
    desired = get_desired_package_versions(preserve_order=True)
    data = [[_n, _v, _raw] for _n, (_v, _raw) in desired]
    
    return data

def compare_manifest(data=None):
    """
    Called before a deployment, given the data returned by record_manifest(),
    for determining what, if any, tasks need to be run to make the target
    server reflect the current settings within the current context.
    """
#    pending = check(return_type=PENDING)
#    if pending:
#        return [update, install]

    pre = ['package']
    update_methods = []
    install_methods = []
    uninstall_methods = []
    old = data or []
    
    old_packages = set(tuple(_) for _ in old)
    old_package_names = set(tuple(_[0]) for _ in old)
    
    new_packages_ordered = get_desired_package_versions(preserve_order=True)
    new_packages = set((_n, _v, _raw) for _n, (_v, _raw) in new_packages_ordered)
    new_package_names = set(_n for _n, (_v, _raw) in new_packages_ordered)
    
    #print 'new_package_names:',new_package_names
    
    added = [_ for _ in new_packages if _ not in old_packages]
    #print 'added:',added
    for _name, _version, _line in added:
        update_methods.append(QueuedCommand('pip.update', kwargs=dict(package=_line), pre=pre))
        install_methods.append(QueuedCommand('pip.install', kwargs=dict(package=_line), pre=pre))
    
    removed = [(_name, _version, _line) for _name, _version, _line in old_packages if _name not in new_package_names]
    #print 'removed:',removed
    for _name, _version, _line in removed:
        uninstall_methods.append(QueuedCommand('pip.uninstall', kwargs=dict(package=_line), pre=pre))
    
    return update_methods + uninstall_methods + install_methods

common.manifest_recorder[PIP] = record_manifest
common.manifest_comparer[PIP] = compare_manifest
