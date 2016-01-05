"""
NTP component.

Merely a stub to document which packages should be installed
if a system uses this component.

It should be otherwise maintenance-free and have required settings to configure.
"""

from burlap import ServiceSatchel
from burlap.common import FEDORA, UBUNTU, START, STOP, ENABLE, DISABLE, RESTART, STATUS

class NTPClientSatchel(ServiceSatchel):

    name = 'ntpclient'
    
    required_system_packages = {
        FEDORA: ['ntpdate','ntp'],
        (UBUNTU, '12.04'): ['ntpdate','ntp'],
        (UBUNTU, '14.04'): ['ntpdate','ntp'],
    }
    
    tasks = (
        'configure',
    )
    
    def set_defaults(self):
        self.env.enabled = True
        self.env.service_commands = {
            START:{
                UBUNTU: 'service ntp start',
            },
            STOP:{
                UBUNTU: 'service ntp stop',
            },
            DISABLE:{
                UBUNTU: 'chkconfig ntp off',
                (UBUNTU, '14.04'): 'update-rc.d -f ntp remove',
            },
            ENABLE:{
                UBUNTU: 'chkconfig ntp on',
                (UBUNTU, '14.04'): 'update-rc.d ntp defaults',
            },
            RESTART:{
                UBUNTU: 'service ntp restart',
            },
            STATUS:{
                UBUNTU: 'service ntp status',
            },
        }

    def configure(self):
        if self.env.enabled:
            self.install_packages()
            self.enable()
            self.start()
        else:
            self.disable()
            self.stop()
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']
    
NTPClientSatchel()
