
from burlap.constants import *
from burlap import ServiceSatchel

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
        UBUNTU: ['network-manager'],
    }
    
    def set_defaults(self):
        self.env.check_enabled = False
    
        self.env.service_commands = {
            START:{
                UBUNTU: 'service network-manager start',
            },
            STOP:{
                UBUNTU: 'service network-manager stop',
            },
            DISABLE:{
                UBUNTU: 'chkconfig network-manager off',
            },
            ENABLE:{
                UBUNTU: 'chkconfig network-manager on',
            },
            RESTART:{
                UBUNTU: 'service network-manager restart',
            },
            STATUS:{
                UBUNTU: 'service network-manager status',
            },
        }
        
        self.env.check_script_path = '/usr/local/bin/check_networkmanager.sh'
        self.env.cron_script_path = '/etc/cron.d/check_networkmanager'
        self.env.cron_perms = '600'
        
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
                remote_path=self.lenv.check_script_path)
            remote_path = self.put_or_dryrun(
                local_path='etc_crond_check_networkmanager',
                remote_path=self.env.cron_script_path, use_sudo=True)
            self.sudo_or_dryrun('chown root:root %s' % remote_path)#env.put_remote_path)
            # Must be 600, otherwise gives INSECURE MODE error.
            # http://unix.stackexchange.com/questions/91202/cron-does-not-print-to-syslog
            self.sudo_or_dryrun('chmod %s %s' % (self.env.cron_perms, remote_path))#env.put_remote_path)
            self.sudo_or_dryrun('service cron restart')
        else:
            self.sudo_or_dryrun('rm -f {cron_script_path}'.format(**self.lenv))
            self.sudo_or_dryrun('service cron restart')
            
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user', 'cron']

NetworkManagerSatchel()
