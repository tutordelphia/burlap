
from fabric.api import env

from burlap import common
from burlap.common import (
    ServiceSatchel,
)

AVAHI = 'avahi'

if 'avahi_enabled' not in env:
    
    env.avahi_enabled = True
    env.avahi_daemon_name = 'avahi-daemon'

    env.avahi_service_commands = {
        common.START:{
            common.UBUNTU: 'service %s start' % env.avahi_daemon_name,
        },
        common.STOP:{
            common.UBUNTU: 'service %s stop' % env.avahi_daemon_name,
        },
        common.DISABLE:{
            common.UBUNTU: 'chkconfig %s off' % env.avahi_daemon_name,
        },
        common.ENABLE:{
            common.UBUNTU: 'chkconfig %s on' % env.avahi_daemon_name,
        },
        common.RESTART:{
            common.UBUNTU: 'service %s restart' % env.avahi_daemon_name,
        },
        common.STATUS:{
            common.UBUNTU: 'service %s status' % env.avahi_daemon_name,
        },
    }
    
common.required_system_packages[AVAHI] = {
    common.UBUNTU: ['avahi-daemon'],
}

class AvahiSatchel(ServiceSatchel):
    
    name = AVAHI
    
    ## Service options.
    
    #ignore_errors = True
    
    # {action: {os_version_distro: command}}
    commands = env.avahi_service_commands
    
    tasks = (
        'configure',
    )
    
    def configure(self):
        if env.avahi_enabled:
            self.enable()
            self.restart()
        else:
            self.disable()
            self.stop()
        #sudo_or_dryrun('apt-get install avahi-daemon')
        
        #TODO:
        #sudo_or_dryrun('nano /etc/avahi/avahi-daemon.conf')
        
        #sudo_or_dryrun('service avahi-daemon restart')
        #sudo_or_dryrun('update-rc.d avahi-daemon defaults')
        
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']
    
AvahiSatchel()
