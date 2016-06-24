from __future__ import print_function

from burlap import ServiceSatchel
from burlap.constants import *
from burlap.decorators import task

class NetworkManagerSatchel(ServiceSatchel):
    """
    Configures Network Manager for automatically controlling network interfaces.
    
    https://fedoraproject.org/wiki/Networking/CLI#Wifi
    """
    
    name = 'nm'
    
    @property
    def packager_system_packages(self):
        return {
            UBUNTU: ['network-manager', 'cron'],
            DEBIAN: ['network-manager', 'cron'],
        }
    
    templates = (
        'check_networkmanager.sh',
        'etc_crond_check_networkmanager',
    )
    
    def set_defaults(self):
        self.env.check_enabled = False
    
        self.env.service_commands = {
            START:{
                UBUNTU: 'service network-manager start',
                DEBIAN: 'service network-manager start',
            },
            STOP:{
                UBUNTU: 'service network-manager stop',
                DEBIAN: 'service network-manager stop',
            },
            DISABLE:{
                UBUNTU: 'chkconfig network-manager off',
                DEBIAN: 'update-rc.d network-manager disable',
                #(UBUNTU, '14.04'): 'update-rc.d -f network-manager remove',
                (UBUNTU, '14.04'): 'echo "manual" | sudo tee /etc/init/network-manager.override',
            },
            ENABLE:{
                DEBIAN: 'update-rc.d network-manager enable',
                UBUNTU: 'chkconfig network-manager on',
                (UBUNTU, '14.04'): 'rm /etc/init/network-manager.override || true',
            },
            RESTART:{
                UBUNTU: 'service network-manager restart',
                DEBIAN: 'service network-manager restart',
            },
            STATUS:{
                UBUNTU: 'service network-manager status',
                DEBIAN: 'service network-manager status',
            },
        }
        
        self.env.check_script_path = '/usr/local/bin/check_networkmanager.sh'
        self.env.cron_script_path = '/etc/cron.d/check_networkmanager'
        self.env.cron_perms = '600'
        
        self.env.connections = {} # {ssid: passphrase}
    
    @task
    def add_wifi_connection(self, ssid, passphrase=None):
        r = self.local_renderer
        r.env.ssid = ssid = ssid
        r.env.passphrase = passphrase
        r.sudo('nmcli device wifi connect "{ssid}" password "{passphrase}"')
    
    @task
    def remove_connection(self, ssid):
        r = self.local_renderer
        r.env.ssid = ssid = ssid
        #r.sudo("nmcli connection delete `nmcli --fields NAME,UUID con list | grep -i {ssid} | awk '{print $2}'`")
        r.sudo("nmcli connection delete id {ssid}")
        
    @task
    def dev_status(self):
        r = self.local_renderer
        r.sudo('nmcli device status')
        
    @task
    def dev_wifi_list(self):
        r = self.local_renderer
        r.sudo('nmcli device wifi list')
        
    @task
    def configure(self):
        
        if self.env.enabled:
            self.install_packages()
            
            # Clear the /etc/network/interfaces so NM will control all interfaces.
            if not self.files.exists('/etc/network/interfaces'):
                self.sudo('mv /etc/network/interfaces /etc/network/interfaces.bak')
            self.sudo('rm -f /etc/network/interfaces')
            self.sudo('touch /etc/network/interfaces')
            self.sudo('echo -e "auto lo\\niface lo inet loopback" > /etc/network/interfaces')
            
            self.enable()
            self.restart()
        else:
            self.disable()
            self.stop()
        
        if self.env.check_enabled:
            # Installs a crontab to check Network-Manager every ten minutes
            # and restart it if theres' no Internet connection.
            self.install_script(
                local_path='%s/check_networkmanager.sh' % self.name,
                remote_path=self.lenv.check_script_path)
            remote_path = self.put_or_dryrun(
                local_path=self.find_template('%s/etc_crond_check_networkmanager' % self.name),
                remote_path=self.env.cron_script_path, use_sudo=True)[0]
            self.sudo_or_dryrun('chown root:root %s' % remote_path)#env.put_remote_path)
            # Must be 600, otherwise gives INSECURE MODE error.
            # http://unix.stackexchange.com/questions/91202/cron-does-not-print-to-syslog
            self.sudo_or_dryrun('chmod %s %s' % (self.env.cron_perms, remote_path))#env.put_remote_path)
            self.sudo_or_dryrun('service cron restart')
        else:
            self.sudo_or_dryrun('rm -f {cron_script_path}'.format(**self.lenv))
            self.sudo_or_dryrun('service cron restart')
    
    configure.deploy_before = ['packager', 'user', 'cron']

nm = NetworkManagerSatchel()
