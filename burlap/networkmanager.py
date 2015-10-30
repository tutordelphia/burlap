
from fabric.api import env

#from burlap import user, package, pip, service, file, tarball
from burlap import common
from burlap.common import (
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    run_or_dryrun,
    Satchel,
    Deployer,
    Service,
)

NETWORKMANAGER = 'networkmanager'

if 'networkmanager_enabled' not in env:
    
    env.networkmanager_enabled = False
    env.networkmanager_check_enabled = False

    env.networkmanager_service_commands = {
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
    
common.required_system_packages[NETWORKMANAGER] = {
    common.UBUNTU: ['network-manager'],
}

class NetworkManagerSatchel(Satchel, Service):
    
    name = NETWORKMANAGER
    
    ## Service options.
    
    #ignore_errors = True
    
    # {action: {os_version_distro: command}}
    commands = env.networkmanager_service_commands
    
    tasks = (
        'configure',
    )
        
    def configure(self):
        
        if env.networkmanager_enabled:
            self.enable()
            self.restart()
        else:
            self.disable()
            self.stop()
        
        if env.networkmanager_check_enabled:
            # Installs a crontab to check Network-Manager every ten minutes
            # and restart it if theres' no Internet connection.
            install_script(
                local_path='check_networkmanager.sh',
                remote_path='/usr/local/bin/check_networkmanager.sh')
            remote_path = put_or_dryrun(
                local_path='etc_crond_check_networkmanager',
                remote_path='/etc/cron.d/check_networkmanager', use_sudo=True)
            sudo_or_dryrun('chown root:root %s' % env.put_remote_path)
            # Must be 600, otherwise gives INSECURE MODE error.
            # http://unix.stackexchange.com/questions/91202/cron-does-not-print-to-syslog
            sudo_or_dryrun('chmod 600 %s' % env.put_remote_path)
            sudo_or_dryrun('service cron restart')
        else:
            sudo_or_dryrun('rm -f /etc/cron.d/check_networkmanager')
            sudo_or_dryrun('service cron restart')
            
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user', 'cron']

networkmanager_satchel = NetworkManagerSatchel()
