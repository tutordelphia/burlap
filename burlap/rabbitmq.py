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
RABBITMQ_BLEEDING = 'RABBITMQ_BLEEDING'
    
if 'rabbitmq_host' not in env:
    env.rabbitmq_host = "localhost"
    env.rabbitmq_vhost = "/"
    env.rabbitmq_erlang_cookie = ''
    env.rabbitmq_nodename = "rabbit"
    env.rabbitmq_user = "guest" # DEPRECATED
    env.rabbitmq_password = "guest" # DEPRECATED
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
    env.rabbitmq_management_enabled = False
    env.rabbitmq_loopback_users = False
    env.rabbitmq_bleeding_edge = False
    
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
def enable_management_interface():
    sudo_or_dryrun('rabbitmq-plugins enable rabbitmq_management')
    sudo_or_dryrun('service rabbitmq-server restart')
    print 'You should not be able to access the RabbitMQ web console from:'
    print '\n    http://54.83.61.46:15672/'
    print '\nNote, the default login is guest/guest.'

@task_or_dryrun
def set_loopback_users():
    # This allows guest to login through the management interface.
    sudo_or_dryrun('touch /etc/rabbitmq/rabbitmq.config')
    sudo_or_dryrun("echo '[{rabbit, [{loopback_users, []}]}].' >> /etc/rabbitmq/rabbitmq.config")
    sudo_or_dryrun('service rabbitmq-server restart')

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
            params.add((_settings.BROKER_USER, _settings.BROKER_PASSWORD, _settings.BROKER_VHOST))
    
    params = sorted(list(params))
    if not only_data:
        for user, password, vhost in params:
            env.rabbitmq_broker_user = user
            env.rabbitmq_broker_password = password
            env.rabbitmq_broker_vhost = vhost
            with settings(warn_only=True):
                sudo_or_dryrun('rabbitmqctl add_user %(rabbitmq_broker_user)s %(rabbitmq_broker_password)s' % env)
                cmd = 'rabbitmqctl add_vhost %(rabbitmq_broker_vhost)s' % env
                sudo_or_dryrun(cmd)
                cmd = 'rabbitmqctl set_permissions -p %(rabbitmq_broker_vhost)s %(rabbitmq_broker_user)s ".*" ".*" ".*"' % env
                sudo_or_dryrun(cmd)
                
    return params

@task_or_dryrun
def enable_bleeding_edge_repo():
    """
    Enables the repository for a most current version on Debian systems.
    
        https://www.rabbitmq.com/install-debian.html
    """
    
    sudo_or_dryrun("echo 'deb http://www.rabbitmq.com/debian/ testing main' >> /etc/apt/sources.list")
    sudo_or_dryrun('cd /tmp; '
        'wget https://www.rabbitmq.com/rabbitmq-signing-key-public.asc; '
        'apt-key add rabbitmq-signing-key-public.asc')
    sudo_or_dryrun('apt-get update')

@task_or_dryrun
def create_user(username, password):
    env._rabbitmq_user = username
    env._rabbitmq_password = password
    sudo_or_dryrun('rabbitmqctl add_user %(_rabbitmq_user)s %(_rabbitmq_password)s' % env)
    #sudo_or_dryrun('rabbitmqctl set_user_tags %(rabbitmq_user)s administrator')
    #sudo_or_dryrun('rabbitmqctl set_permissions -p / %(rabbitmq_user)s ".*" ".*" ".*"')
    #sudo_or_dryrun('rabbitmqctl set_permissions -p alphabuyer %(rabbitmq_user)s ".*" ".*" ".*"')

@task_or_dryrun
def configure_all(last=None, current=None, **kwargs):
    
    last = last or {}
    if RABBITMQ in last:
        last = last[RABBITMQ]
    
    current = current or {}
    if RABBITMQ in current:
        current = current[RABBITMQ]
    
    if last.get('rabbitmq_management_enabled') != current.get('rabbitmq_management_enabled'):
        enable_management_interface()
    
    if last.get('rabbitmq_loopback_users') != current.get('rabbitmq_loopback_users'):
        set_loopback_users()
        
    kwargs['site'] = common.ALL
    return configure(**kwargs)

class RabbitMQBleedingSatchel(Satchel):

    name = RABBITMQ_BLEEDING
    
    def record_manifest(self):
        data = dict(
            bleeding=env.rabbitmq_bleeding_edge,
        )
        return data
        
    def get_deployers(self):
        """
        Returns one or more Deployer instances, representing tasks to run during a deployment.
        """
        return [
            Deployer(
                func='rabbitmq.enable_bleeding_edge_repo',
                # if they need to be run, these must be run before this deployer
                before=['user'],
                # if they need to be run, these must be run after this deployer
                after=['packager', 'rabbitmq'],
                takes_diff=False)
        ]
    
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
                takes_diff=True)
        ]

RabbitMQSatchel()
RabbitMQBleedingSatchel()
