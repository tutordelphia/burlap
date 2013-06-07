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


env.celery_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start celeryd.service',
        common.UBUNTU: 'service celeryd start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop celery.service',
        common.UBUNTU: 'service celeryd stop',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable httpd.service',
        common.UBUNTU: 'chkconfig celeryd off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable httpd.service',
        common.UBUNTU: 'chkconfig celeryd on',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl restart celeryd.service',
        common.UBUNTU: 'service celeryd restart; sleep 5',
    },
    common.STATUS:{
        common.FEDORA: 'systemctl status celeryd.service',
        common.UBUNTU: 'service celeryd status',
    },
}

CELERY = 'CELERY'

common.required_system_packages[CELERY] = {
#    common.FEDORA: ['rabbitmq-server'],
#    common.UBUNTU: ['rabbitmq-server'],
}

common.required_python_packages[CELERY] = {
    common.FEDORA: ['celery', 'django-celery'],
    common.UBUNTU: ['celery', 'django-celery'],
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.celery_service_commands[action][os_version.distro]

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
def configure():
    todo
