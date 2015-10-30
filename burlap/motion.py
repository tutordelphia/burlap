"""
Wrapper around the Motion service.

http://www.lavrsen.dk/foswiki/bin/view/Motion/WebHome
"""
from fabric.api import env

from burlap import common
from burlap.common import (
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    run_or_dryrun,
    Satchel,
    Service,
)

MOTION = 'motion'

if 'motion_enabled' not in env:
    
    env.motion_enabled = False
    env.motion_notify_enabled = False

    env.motion_service_commands = {
        common.START:{
            common.FEDORA: 'systemctl start motion.service',
            common.UBUNTU: 'service motion start',
        },
        common.STOP:{
            common.FEDORA: 'systemctl stop motion.service',
            common.UBUNTU: 'service motion stop',
        },
        common.DISABLE:{
            common.FEDORA: 'systemctl disable motion.service',
            common.UBUNTU: 'chkconfig motion off',
        },
        common.ENABLE:{
            common.FEDORA: 'systemctl enable motion.service',
            common.UBUNTU: 'chkconfig motion on',
        },
        common.RESTART:{
            common.FEDORA: 'systemctl restart motion.service',
            common.UBUNTU: 'service motion restart; sleep 5',
        },
        common.STATUS:{
            common.FEDORA: 'systemctl status motion.service',
            common.UBUNTU: 'service motion status',
        },
    }
    
common.required_system_packages[MOTION] = {
    common.FEDORA: ['motion'],
    common.UBUNTU: ['motion'],
}

class MotionSatchel(Satchel, Service):
    
    name = MOTION
    
    ## Service options.
    
    #ignore_errors = True
    
    # {action: {os_version_distro: command}}
    commands = env.motion_service_commands

    tasks = (
        'configure',
    )
    
    def configure(self):
        todo
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']
    
motion_satchel = MotionSatchel()
