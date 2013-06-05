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

env.rabbitmq_erlang_cookie = None

env.rabbitmq_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start rabbitmq-server.service',
        common.UBUNTU: 'service rabbitmq-server start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop httpd.service',
        common.UBUNTU: 'service apache2 stop',
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
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.apache_service_commands[action][os_version.distro]

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
def configure():
    assert env.rabbitmq_erlang_cookie
    todo
    