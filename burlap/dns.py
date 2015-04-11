"""
Management functions for DNS servers (currently only Bind).

http://docs.fedoraproject.org/en-US/Fedora/13/html/Deployment_Guide/ch-The_BIND_DNS_Server.html
http://www.server-world.info/en/note?os=Fedora_16&p=dns
https://help.ubuntu.com/community/BIND9ServerHowto
"""
from burlap import common

from fabric.api import (
    env,
    require,
    settings,
    cd,
)

from burlap.common import run_or_dryrun, sudo_or_dryrun
from burlap.decorators import task_or_dryrun

BIND = 'BIND'

common.required_system_packages[BIND] = {
    common.FEDORA: ['bind','bind-utils '],
    (common.UBUNTU, '12.04'): ['bind9'],
}

env.dns_service_commands = {
    common.START:{
        (common.FEDORA, '13'): 'service named start',
        common.FEDORA: 'systemctl start named.service',
        common.UBUNTU: 'service named start',
    },
    common.STOP:{
        (common.FEDORA, '13'): 'service named stop',
        common.FEDORA: 'systemctl stop supervisor.service',
        common.UBUNTU: 'service namedstop',
    },
    common.DISABLE:{
        (common.FEDORA, '13'): 'chkconfig named off',
        common.FEDORA: 'systemctl disable httpd.service',
        common.UBUNTU: 'chkconfig supervisord off',
    },
    common.ENABLE:{
        (common.FEDORA, '13'): 'chkconfig named on',
        common.FEDORA: 'systemctl enable httpd.service',
        common.UBUNTU: 'chkconfig supervisord on',
    },
    common.RESTART:{
        (common.FEDORA, '13'): 'service named restart',
        common.FEDORA: 'systemctl restart supervisord.service',
        common.UBUNTU: 'service namedrestart; sleep 5',
    },
    common.STATUS:{
        (common.FEDORA, '13'): 'service named status',
        common.FEDORA: 'systemctl status supervisord.service',
        common.UBUNTU: 'service named status',
    },
}

def get_service_command(action):
    os_version = common.get_os_version()
    cmd = env.dns_service_commands[action].get((os_version.distro, os_version.release))
    if cmd:
        return cmd
    return env.dns_service_commands[action][os_version.distro]

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
    cmd = get_service_command(common.START)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def stop():
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
def configure():
    """
    Installs DNS configuration.
    """
    todo

@task_or_dryrun
def deploy():
    """
    Installs DNS configuration.
    """
    todo

#common.service_configurators[BIND] = [configure]
#common.service_deployers[BIND] = [deploy]
common.service_restarters[BIND] = [restart]
