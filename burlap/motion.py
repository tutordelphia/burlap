"""
Wrapper around the Motion service.

http://www.lavrsen.dk/foswiki/bin/view/Motion/WebHome
"""

from burlap import ServiceSatchel
from burlap.constants import *

class MotionSatchel(ServiceSatchel):
    
    name = 'motion'
    
    ## Service options.
    
    #ignore_errors = True
    
    required_system_packages = {
        FEDORA: ['motion'],
        UBUNTU: ['motion'],
    }

    tasks = (
        'configure',
    )
    
    def set_defaults(self):
        self.env.notify_enabled = False
        self.env.service_commands = {
            START:{
                FEDORA: 'systemctl start motion.service',
                UBUNTU: 'service motion start',
            },
            STOP:{
                FEDORA: 'systemctl stop motion.service',
                UBUNTU: 'service motion stop',
            },
            DISABLE:{
                FEDORA: 'systemctl disable motion.service',
                UBUNTU: 'chkconfig motion off',
            },
            ENABLE:{
                FEDORA: 'systemctl enable motion.service',
                UBUNTU: 'chkconfig motion on',
            },
            RESTART:{
                FEDORA: 'systemctl restart motion.service',
                UBUNTU: 'service motion restart; sleep 5',
            },
            STATUS:{
                FEDORA: 'systemctl status motion.service',
                UBUNTU: 'service motion status',
            },
        }    
    
    def configure(self):
        todo
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']
    
motion_satchel = MotionSatchel()
