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
        common.FEDORA: 'systemctl disable httpd.service',
        common.UBUNTU: 'chkconfig rabbitmq-server off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable httpd.service',
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
    common.UBUNTU: ['rabbitmq-server'],
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.rabbitmq_service_commands[action][os_version.distro]

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
def configure(full=0):
    """
    Installs and configures RabbitMQ.
    """
    full = int(full)
    from burlap import package
    if env.rabbitmq_erlang_cookie_template:
        env.rabbitmq_erlang_cookie = env.rabbitmq_erlang_cookie_template % env
    assert env.rabbitmq_erlang_cookie
    if full:
        package.install_required(type=package.common.SYSTEM, service=RABBITMQ)
    
