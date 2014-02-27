from fabric.api import env, sudo, task

from burlap import common

MEMCACHED = 'MEMCACHED'

common.required_system_packages[MEMCACHED] = {
    common.UBUNTU: ['memcached'],
}

env.memcached_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start memcached',
        common.UBUNTU: 'service memcached start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop memcached',
        common.UBUNTU: 'service memcached stop',
    },
    common.STATUS:{
        common.FEDORA: 'systemctl stop status',
        common.UBUNTU: 'service memcached status',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable memcached',
        common.UBUNTU: 'chkconfig memcached off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable memcached',
        common.UBUNTU: 'chkconfig memcached on',
    },
    common.RELOAD:{
        common.FEDORA: 'systemctl reload memcached',
        common.UBUNTU: 'service memcached reload',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl restart memcached',
        #common.UBUNTU: 'service memcached restart',
        # Note, the sleep 5 is necessary because the stop/start appears to
        # happen in the background but gets aborted if Fabric exits before
        # it completes.
        common.UBUNTU: 'service memcached restart; sleep 3',
    },
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.memcached_service_commands[action][os_version.distro]

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
def reload():
    cmd = get_service_command(common.RELOAD)
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
    