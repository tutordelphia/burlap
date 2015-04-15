import os
import sys
import re

from fabric.api import (
    env,
    local,
    require,
    settings,
    sudo,
    cd,
    task,
)

from fabric.contrib import files

from burlap.common import (
    run_or_dryrun,
    sudo_or_dryrun,
    put_or_dryrun,
    local_or_dryrun,
)
from burlap.decorators import task_or_dryrun
from burlap import common
from burlap.common import QueuedCommand

env.cron_crontabs_available = type(env)() # {name:[cron lines]}

#env._cron_create_crontab_callbacks = []
#def register_callback(f):
#    env._cron_create_crontab_callbacks.append(f)

env.cron_command = 'cron'
env.cron_user = 'www-data'
env.cron_python = None
env.cron_crontab_headers = ['PATH=/usr/sbin:/usr/bin:/sbin:/bin\nSHELL=/bin/bash']
env.cron_django_manage_template = '%(remote_app_src_package_dir)s/manage.py'
env.cron_stdout_log_template = '/tmp/chroniker-%(SITE)s-stdout.$(date +\%%d).log'
env.cron_stderr_log_template = '/tmp/chroniker-%(SITE)s-stderr.$(date +\%%d).log'
env.cron_crontabs_selected = [] # [name]

env.cron_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start crond.service',
        common.UBUNTU: 'service cron start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop crond.service',
        common.UBUNTU: 'service cron stop',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable crond.service',
        common.UBUNTU: 'chkconfig cron off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable crond.service',
        common.UBUNTU: 'chkconfig cron on',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl restart crond.service',
        common.UBUNTU: 'service cron restart; sleep 3',
    },
    common.STATUS:{
        common.FEDORA: 'systemctl status crond.service',
        common.UBUNTU: 'service cron status',
    },
}

CRON = 'CRON'

common.required_system_packages[CRON] = {
    common.FEDORA: ['crontabs'],
    (common.UBUNTU, '12.04'): ['cron'],
}

common.required_python_packages[CRON] = {
    common.FEDORA: [],
    common.UBUNTU: [],
}

def render_paths():
    from pip import render_paths as pip_render_paths
    
    pip_render_paths()
    
    env.cron_python = os.path.join(env.pip_virtual_env_dir, 'bin', 'python')
    env.cron_django_manage = env.cron_django_manage_template % env
    env.cron_stdout_log = env.cron_stdout_log_template % env
    env.cron_stderr_log = env.cron_stderr_log_template % env

def get_service_command(action):
    os_version = common.get_os_version()
    return env.cron_service_commands[action][os_version.distro]

@task_or_dryrun
def enable():
    cmd = get_service_command(common.ENABLE)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def disable():
    cmd = get_service_command(common.DISABLE)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def start():
    with settings(warn_only=True):
        cmd = get_service_command(common.START)
        
        sudo_or_dryrun(cmd)

@task_or_dryrun
def stop():
    # If cron service already stopped, will throw the error
    # "Instance unknown:" on Ubuntu.
    with settings(warn_only=True):
        cmd = get_service_command(common.STOP)
        
        sudo_or_dryrun(cmd)

@task_or_dryrun
def restart():
    cmd = get_service_command(common.RESTART)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def status():
    cmd = get_service_command(common.STATUS)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def deploy(site=None, verbose=0):
    """
    Writes entire crontab to the host.
    """
    from burlap.common import get_current_hostname
    
    verbose = int(verbose)
    cron_crontabs = []
    hostname = get_current_hostname()
    target_sites = env.available_sites_by_host.get(hostname, None)
    if verbose:
        print>>sys.stderr, 'hostname: "%s"' % (hostname,) 
    for site, site_data in common.iter_sites(site=site, renderer=render_paths):
        if verbose:
            print>>sys.stderr, 'site:',site
        #print 'cron_crontabs_selected:',env.cron_crontabs_selected
        
        # Only load site configurations that are allowed for this host.
        if target_sites is None:
            pass
        else:
            assert isinstance(target_sites, (tuple, list))
            if site not in target_sites:
                print>>sys.stderr, 'Skipping:', site
                continue
        
        if verbose:
            print>>sys.stderr, 'env.cron_crontabs_selected:',env.cron_crontabs_selected
        for selected_crontab in env.cron_crontabs_selected:
            lines = env.cron_crontabs_available.get(selected_crontab, [])
            if verbose:
                print>>sys.stderr, 'lines:',lines
            for line in lines:
                cron_crontabs.append(line % env)
    
    if not cron_crontabs:
        return
    
    cron_crontabs = env.cron_crontab_headers + cron_crontabs
    cron_crontabs.append('\n')
    env.cron_crontabs_rendered = '\n'.join(cron_crontabs)
    fn = common.write_to_file(content=env.cron_crontabs_rendered)
    put_or_dryrun(local_path=fn)
    sudo_or_dryrun('crontab -u %(cron_user)s %(put_remote_path)s' % env)

@task_or_dryrun
def deploy_all(**kwargs):
    kwargs['site'] = common.ALL
    return deploy(**kwargs)

@task_or_dryrun
def record_manifest(verbose=0):
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = common.get_component_settings(CRON)
    if int(verbose):
        print data
    return data

def compare_manifest(old):
    """
    Compares the current settings to previous manifests and returns the methods
    to be executed to make the target match current settings.
    """
    old = old or {}
    methods = []
    pre = ['user','packages']
    new = common.get_component_settings(CRON)
    has_diffs = common.check_settings_for_differences(old, new, as_bool=True)
    if has_diffs:
        methods.append(QueuedCommand('cron.deploy_all', pre=pre))
    return methods

#common.service_configurators[CRON] = [configure]
common.service_deployers[CRON] = [deploy_all]
common.service_restarters[CRON] = [restart]
common.service_stoppers[CRON] = [stop]
common.service_pre_deployers[CRON] = [stop]
common.service_post_deployers[CRON] = [start]

common.manifest_recorder[CRON] = record_manifest
common.manifest_comparer[CRON] = compare_manifest
