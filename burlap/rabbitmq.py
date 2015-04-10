import os
import re

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    #run as _run,
    #run,
    settings,
    #sudo,
    cd,
    task,
)

from fabric.contrib import files

from burlap.common import (
    run_or_dryrun,
    sudo_or_dryrun,
    put_or_dryrun,
    QueuedCommand,
)
from burlap import common
from burlap.decorators import task_or_dryrun

env.rabbitmq_host = "localhost"
env.rabbitmq_vhost = "/"
env.rabbitmq_erlang_cookie = ''
env.rabbitmq_nodename = "rabbit"
env.rabbitmq_user = "guest"
env.rabbitmq_password = "guest"
env.rabbitmq_node_ip_address = ''
env.rabbitmq_port = 5672
env.rabbitmq_erl_args = ""
env.rabbitmq_cluster = "no"
env.rabbitmq_cluster_config = "/etc/rabbitmq/rabbitmq_cluster.config"
env.rabbitmq_logdir = "/var/log/rabbitmq"
env.rabbitmq_mnesiadir = "/var/lib/rabbitmq/mnesia"
env.rabbitmq_start_args = ""
env.rabbitmq_erlang_cookie_template = ''
env.rabbitmq_ignore_service_errors = 0

env.rabbitmq_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start rabbitmq-server.service',
        common.UBUNTU: 'service rabbitmq-server start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop rabbitmq-server.service',
        common.UBUNTU: 'service rabbitmq-server stop',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable rabbitmq-server.service',
        common.UBUNTU: 'chkconfig rabbitmq-server off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable rabbitmq-server.service',
        common.UBUNTU: 'chkconfig rabbitmq-server on',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl restart rabbitmq-server.service',
        common.UBUNTU: 'service rabbitmq-server restart; sleep 5',
    },
    common.STATUS:{
        common.FEDORA: 'systemctl status rabbitmq-server.service',
        common.UBUNTU: 'service rabbitmq-server status',
    },
}

RABBITMQ = 'RABBITMQ'

common.required_system_packages[RABBITMQ] = {
    common.FEDORA: ['rabbitmq-server'],
    (common.UBUNTU, '12.04'): ['rabbitmq-server'],
    (common.UBUNTU, '14.04'): ['rabbitmq-server'],
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.rabbitmq_service_commands[action][os_version.distro]

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
    s = {'warn_only':True} if env.rabbitmq_ignore_service_errors else {} 
    with settings(**s):
        cmd = get_service_command(common.START)
        sudo_or_dryrun(cmd)

@task_or_dryrun
def stop():
    s = {'warn_only':True} if env.rabbitmq_ignore_service_errors else {} 
    with settings(**s):
        cmd = get_service_command(common.STOP)
        sudo_or_dryrun(cmd)

@task_or_dryrun
def restart():
    s = {'warn_only':True} if env.rabbitmq_ignore_service_errors else {} 
    with settings(**s):
        cmd = get_service_command(common.RESTART)
        sudo_or_dryrun(cmd)

@task_or_dryrun
def status():
    cmd = get_service_command(common.STATUS)
    sudo_or_dryrun(cmd)

def render_paths():
    from burlap.dj import render_remote_paths
    render_remote_paths()
    if env.rabbitmq_erlang_cookie_template:
        env.rabbitmq_erlang_cookie = env.rabbitmq_erlang_cookie_template % env

@task_or_dryrun
def list_vhosts():
    """
    Displays a list of configured RabbitMQ vhosts.
    """
    sudo_or_dryrun('rabbitmqctl list_vhosts')

@task_or_dryrun
def list_users():
    """
    Displays a list of configured RabbitMQ users.
    """
    sudo_or_dryrun('rabbitmqctl list_users')
    
@task_or_dryrun
def configure(site=None, full=0):
    """
    Installs and configures RabbitMQ.
    """
    from burlap.dj import get_settings
    from burlap import package
    
    full = int(full)
    
    
#    assert env.rabbitmq_erlang_cookie
    if full:
        package.install_required(type=package.common.SYSTEM, service=RABBITMQ)
    
    #render_paths()
    
    params = set() # [(user,vhost)]
    for site, site_data in common.iter_sites(site=site, renderer=render_paths, no_secure=True):
        print '!'*80
        print 'site:',site
        _settings = get_settings(site=site)
        #print '_settings:',_settings
        if not _settings:
            continue
        print 'RabbitMQ:',_settings.BROKER_USER, _settings.BROKER_VHOST
        params.add((_settings.BROKER_USER, _settings.BROKER_VHOST))
    
    for user, vhost in params:
        env.rabbitmq_broker_user = user
        env.rabbitmq_broker_vhost = vhost
        with settings(warn_only=True):
            cmd = 'rabbitmqctl add_vhost %(rabbitmq_broker_vhost)s' % env
            sudo_or_dryrun(cmd)
            cmd = 'rabbitmqctl set_permissions -p %(rabbitmq_broker_vhost)s %(rabbitmq_broker_user)s ".*" ".*" ".*"' % env
            sudo_or_dryrun(cmd)

@task_or_dryrun
def configure_all(**kwargs):
    kwargs['site'] = common.ALL
    return configure(**kwargs)

@task_or_dryrun
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = common.get_component_settings(RABBITMQ)
    return data

def compare_manifest(old):
    """
    Compares the current settings to previous manifests and returns the methods
    to be executed to make the target match current settings.
    """
    old = old or {}
    methods = []
    pre = ['user','packages']
    new = common.get_component_settings(RABBITMQ)
    has_diffs = common.check_settings_for_differences(old, new, as_bool=True)
    if has_diffs:
        methods.append(QueuedCommand('rabbitmq.configure_all', pre=pre))
    return methods

common.service_configurators[RABBITMQ] = [configure_all]
#common.service_deployers[RABBITMQ] = [deploy]
common.service_restarters[RABBITMQ] = [restart]
common.service_stoppers[RABBITMQ] = [stop]
common.service_pre_deployers[RABBITMQ] = [stop]
common.service_post_deployers[RABBITMQ] = [start]

common.manifest_recorder[RABBITMQ] = record_manifest
common.manifest_comparer[RABBITMQ] = compare_manifest
