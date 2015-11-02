
from burlap import common
from burlap.common import (
    ServiceSatchel
)

class NetworkManagerSatchel(ServiceSatchel):
    
    name = 'networkmanager'
    
    ## Service options.
    
    #ignore_errors = True
    
    # {action: {os_version_distro: command}}
#     commands = env.networkmanager_service_commands
    
    tasks = (
        'configure',
    )
    
    required_system_packages = {
        common.UBUNTU: ['network-manager'],
    }
    
    def set_defaults(self):
        self.env.check_enabled = False
    
        self.env.service_commands = {
            common.START:{
                common.UBUNTU: 'service network-manager start',
            },
            common.STOP:{
                common.UBUNTU: 'service network-manager stop',
            },
            common.DISABLE:{
                common.UBUNTU: 'chkconfig network-manager off',
            },
            common.ENABLE:{
                common.UBUNTU: 'chkconfig network-manager on',
            },
            common.RESTART:{
                common.UBUNTU: 'service network-manager restart',
            },
            common.STATUS:{
                common.UBUNTU: 'service network-manager status',
            },
        }
        
    def configure(self):
        
        if self.env.enabled:
            self.enable()
            self.restart()
        else:
            self.disable()
            self.stop()
        
        if self.env.check_enabled:
            # Installs a crontab to check Network-Manager every ten minutes
            # and restart it if theres' no Internet connection.
            self.install_script(
                local_path='check_networkmanager.sh',
                remote_path='/usr/local/bin/check_networkmanager.sh')
            remote_path = self.put_or_dryrun(
                local_path='etc_crond_check_networkmanager',
                remote_path='/etc/cron.d/check_networkmanager', use_sudo=True)
            self.sudo_or_dryrun('chown root:root %s' % remote_path)#env.put_remote_path)
            # Must be 600, otherwise gives INSECURE MODE error.
            # http://unix.stackexchange.com/questions/91202/cron-does-not-print-to-syslog
            self.sudo_or_dryrun('chmod 600 %s' % remote_path)#env.put_remote_path)
            self.sudo_or_dryrun('service cron restart')
        else:
            self.sudo_or_dryrun('rm -f /etc/cron.d/check_networkmanager')
            self.sudo_or_dryrun('service cron restart')
            
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user', 'cron']

NetworkManagerSatchel()
