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
    Satchel,
    Deployer,
    Service,
)
from burlap import common
from burlap.decorators import task_or_dryrun
    
RABBITMQ = 'RABBITMQ'
    
if 'rabbitmq_host' not in env:
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
    
    common.required_system_packages[RABBITMQ] = {
        common.FEDORA: ['rabbitmq-server'],
        (common.UBUNTU, '12.04'): ['rabbitmq-server'],
        (common.UBUNTU, '14.04'): ['rabbitmq-server'],
    }

def get_service_command(action):
    os_version = common.get_os_version()
    return env.rabbitmq_service_commands[action][os_version.distro]

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
def configure(site=None, full=0, only_data=0):
    """
    Installs and configures RabbitMQ.
    """
    from burlap.dj import get_settings
    from burlap import package
    
    full = int(full)
    
#    assert env.rabbitmq_erlang_cookie
    if full and not only_data:
        package.install_required(type=package.common.SYSTEM, service=RABBITMQ)
    
    #render_paths()
    
    params = set() # [(user,vhost)]
    for site, site_data in common.iter_sites(site=site, renderer=render_paths, no_secure=True):
        print '!'*80
        print 'site:', site
        _settings = get_settings(site=site)
        #print '_settings:',_settings
        if not _settings:
            continue
        if hasattr(_settings, 'BROKER_USER') and hasattr(_settings, 'BROKER_VHOST'):
            print 'RabbitMQ:',_settings.BROKER_USER, _settings.BROKER_VHOST
            params.add((_settings.BROKER_USER, _settings.BROKER_VHOST))
    
    params = sorted(list(params))
    if not only_data:
        for user, vhost in params:
            env.rabbitmq_broker_user = user
            env.rabbitmq_broker_vhost = vhost
            with settings(warn_only=True):
                cmd = 'rabbitmqctl add_vhost %(rabbitmq_broker_vhost)s' % env
                sudo_or_dryrun(cmd)
                cmd = 'rabbitmqctl set_permissions -p %(rabbitmq_broker_vhost)s %(rabbitmq_broker_user)s ".*" ".*" ".*"' % env
                sudo_or_dryrun(cmd)
                
    return params

@task_or_dryrun
def configure_all(**kwargs):
    kwargs['site'] = common.ALL
    return configure(**kwargs)

class RabbitMQSatchel(Satchel, Service):
    
    name = RABBITMQ
    
    ## Service options.
    
    ignore_errors = True
    
    # {action: {os_version_distro: command}}
    commands = env.rabbitmq_service_commands
    
    def record_manifest(self):
        """
        Returns a dictionary representing a serialized state of the service.
        """
        data = common.get_component_settings(RABBITMQ)
        vhosts = configure_all(only_data=1)
        data['rabbitmq_all_site_vhosts'] = vhosts
        return data
        
    def get_deployers(self):
        """
        Returns one or more Deployer instances, representing tasks to run during a deployment.
        """
        return [
            Deployer(
                func='rabbitmq.configure_all',
                # if they need to be run, these must be run before this deployer
                before=['packager', 'user'],
                # if they need to be run, these must be run after this deployer
                after=[],
                takes_diff=False)
        ]

RabbitMQSatchel()
