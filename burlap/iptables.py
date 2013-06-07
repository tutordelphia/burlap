import os
import sys
import datetime

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

from burlap.common import run, put, render_to_string
from burlap import common

env.iptables_enabled = True
env.iptables_ssh_port = 22

env.iptables_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start iptables.service',
        common.UBUNTU: 'service iptables start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop iptables.service',
        common.UBUNTU: 'service iptables stop',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable iptables.service',
        common.UBUNTU: 'chkconfig iptables off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable iptables.service',
        common.UBUNTU: 'chkconfig iptables on',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl restart iptables.service',
        common.UBUNTU: 'service iptables restart',
    },
}

IPTABLES = 'IPTABLES'

common.required_system_packages[IPTABLES] = {
    common.FEDORA: ['iptables'],
    common.UBUNTU: ['iptables'],
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.iptables_service_commands[action][os_version.distro]

@task
def enable():
    cmd = get_service_command(common.ENABLE)
    print cmd
    run(cmd)

@task
def disable():
    cmd = get_service_command(common.DISABLE)
    print cmd
    run(cmd)

@task
def start():
    cmd = get_service_command(common.START)
    print cmd
    run(cmd)

@task
def stop():
    cmd = get_service_command(common.STOP)
    print cmd
    run(cmd)

@task
def restart():
    cmd = get_service_command(common.RESTART)
    print cmd
    run(cmd)

@task
def configure():
    """
    Configures rules for IPTables.
    """
    if env.iptables_enabled:
        fn = common.render_to_file('iptables.template.rules')
        put(local_path=fn)
        
        cmd = 'iptables-restore < %(put_remote_path)s; iptables-save > /etc/iptables.up.rules' % env
        sudo(cmd)
        
        enable()
        restart()
    else:
        disable()
        stop()
