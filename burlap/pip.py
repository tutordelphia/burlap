import os
import re

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

from fabric.tasks import Task

from burlap.common import run, put

env.pip_virtual_env_dir = '.env'
env.pip_virtual_env_exe = sudo
env.pip_requirements_fn = 'pip-requirements.txt'
env.pip_use_virt = True
env.pip_path = 'pip'
env.pip_update_command = '%(pip_path)s install --use-mirrors --timeout=120 --no-install %(no_deps)s --download %(pip_cache_dir)s --exists-action w %(pip_package)s'
env.pip_install_command = '. %(pip_virtual_env_dir)s/bin/activate; pip install --upgrade --timeout=60 "%(pip_package)s"; deactivate'
env.pip_remote_cache_dir = '/tmp/pip_cache'
env.pip_local_cache_dir = './.pip_cache/%(role)s'
env.pip_upgrade = ''
env.pip_install_command = ". %(pip_virtual_env_dir)s/bin/activate; %(pip_path)s install %(pip_upgrade)s --find-links file://%(pip_cache_dir)s --no-index %(pip_package)s; deactivate"

@task
def init(clean=0):
    """
    Creates the virtual environment.
    """
    require('role')
    
    # Delete any pre-existing environment.
    if int(clean):
        with settings(warn_only=True):
            print 'Deleting old virtual environment...'
            run('rm -Rf %(pip_virtual_env_dir)s' % env)
        assert not files.exists(env.pip_virtual_env_dir), \
            'Unable to delete pre-existing environment.'
            
    print 'Creating new virtual environment...'
    run('virtualenv %(pip_virtual_env_dir)s' % env)

def iter_pip_requirements():
    for line in open(env.pip_requirements_fn):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        yield line
        
def get_desired_package_versions():
    versions = {}
    for line in open(env.pip_requirements_fn).read().split('\n'):
        if not line.strip() or line.startswith('#'):
            continue
        #print line
        matches = re.findall('([a-zA-Z0-9\-_]+)[\=\<\>]{2}(.*)', line)
        if matches:
            #print line,matches[0]
            versions[matches[0][0]] = (matches[0][1], line)
        else:
            matches = re.findall('([a-zA-Z\-]+)\-([0-9\.]+)(?:$|\.)', line)
            if matches:
                versions[matches[0][0]] = (matches[0][1], line)
            else:
                versions[line] = ('current', line)
    return versions

@task
def check():
    """
    Lists the packages that are missing or obsolete on the target.
    """
    require('role')
    
    init()
    
    def get_version_nums(v):
        if re.findall('^[0-9\.]+$', v):
            return tuple(int(_) for _ in v.split('.') if _.strip().isdigit())
    
    use_virt = env.pip_use_virt
    if use_virt:
        cmd_template = ". %(pip_virtual_env_dir)s/bin/activate; %(pip_path)s freeze; deactivate"
    else:
        cmd_template = "%(pip_path)s freeze"
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
        if v != 'current' and v != installed_package_versions.get(k,v):
            obsolete[k] = (v, line)
    if obsolete:
        print '!'*80
        print 'Obsolete:'
        for k,(v0,line) in sorted(obsolete.iteritems(), key=lambda o:o[0]):
            v0nums = get_version_nums(v0)
            v1 = installed_package_versions[k]
            v1nums = get_version_nums(v1)
            installed_is_newer = v1nums > v0nums
            newer_str = ''
            if installed_is_newer:
                newer_str = ', this is newer!!! Update pip-requirements.txt???'
            print k,v0,'(Installed is %s%s)' % (v1, newer_str)
            pending.append((line,'update'))
    else:
        print '-'*80
        print 'None are obsolete.'
    return pending

@task
def update(package='', ignore_errors=0, no_deps=0, all=0):
    """
    Updates the local cache of pip packages.
    """
    require('role')
    ignore_errors = int(ignore_errors)
    env.pip_cache_dir = env.pip_local_cache_dir % env
    if not os.path.isdir(env.pip_cache_dir):
        os.makedirs(env.pip_cache_dir)
    env.package = (package or '').strip()
    env.no_deps = '--no-deps' if int(no_deps) else ''
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
                packages = list(iter_pip_requirements)
            else:
                packages = [k for k,v in check()]
            
            for package in packages:
                env.pip_package = package.strip()
                local(env.pip_update_command % env)

@task
def install(package='', clean=0, all=0, upgrade=0):
    """
    Installs the local cache of pip packages.
    """
    print 'Installing pip requirements...'
    require('role', 'is_local')

    if env.is_local:
        env.pip_cache_dir = os.path.abspath(env.pip_local_cache_dir % env)
    else:
        env.pip_cache_dir = env.pip_remote_cache_dir % env
        local('rsync -avz --progress --rsh "ssh -i %(key_filename)s" %(pip_local_cache_dir)s/* %(host_string)s:%(remote_pip_cache_dir)s' % env)
    
    if int(upgrade):
        env.pip_upgrade_str = ' -U '
        
    with cd(env.pip_virtual_env_dir):
        
        if int(all):
            packages = list(iter_pip_requirements)
        elif package:
            packages = [package]
        else:
            packages = [k for k,v in check()]
        
        for package in packages:
            env.pip_package = package
            run(env.pip_install_command % env)
