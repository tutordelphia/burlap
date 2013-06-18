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

from fabric.contrib import files

from burlap.common import run, put
from burlap import common

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
    common.UBUNTU: ['cron'],
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

@task
def enable():
    cmd = get_service_command(common.ENABLE)
    print cmd
    sudo(cmd)

@task
def disable():
    cmd = get_service_command(common.DISABLE)
    print cmd
    sudo(cmd)

@task
def start():
    cmd = get_service_command(common.START)
    print cmd
    sudo(cmd)

@task
def stop():
    cmd = get_service_command(common.STOP)
    print cmd
    sudo(cmd)

@task
def restart():
    cmd = get_service_command(common.RESTART)
    print cmd
    sudo(cmd)

@task
def status():
    cmd = get_service_command(common.STATUS)
    print cmd
    sudo(cmd)

@task
def deploy(site=None, dryrun=0):
    """
    Writes entire crontab to the host.
    """
    #assert crontab, 'No crontab specified.'
    
    site = site or env.SITE
    if site == 'all':
        sites = env.sites.iteritems()
    else:
        sites = [(site, env.sites[site])]
    
    cron_crontabs = []
    for site, site_data in common.iter_sites(sites, renderer=render_paths):
        print site
        for selected_crontab in env.cron_crontabs_selected:
            for line in env.cron_crontabs_available.get(selected_crontab, []):
                cron_crontabs.append(line % env)
    
    if not cron_crontabs:
        return
    
    cron_crontabs = env.cron_crontab_headers + cron_crontabs
    cron_crontabs.append('\n')
    env.cron_crontabs_rendered = '\n'.join(cron_crontabs)
    fn = common.write_to_file(content=env.cron_crontabs_rendered)
    if not int(dryrun):
        put(local_path=fn)
        sudo('crontab -u %(cron_user)s %(put_remote_path)s' % env)

@task
def deploy_all(**kwargs):
    kwargs['site'] = 'all'
    return deploy(**kwargs)

#common.service_configurators[CRON] = [configure]
common.service_deployers[CRON] = [deploy_all]
common.service_restarters[CRON] = [restart]
