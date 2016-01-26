"""
General tweaks and services to enhance system security.
"""

from burlap import Satchel
from burlap.constants import *

class UnattendedUpgradesSatchel(Satchel):
    """
    Enables various degrees of automatic package download and installation.
    """
    
    name = 'unattendedupgrades'
    
    required_system_packages = {
        UBUNTU: ['unattended-upgrades'],
        (UBUNTU, '12.04'): ['unattended-upgrades'],
        (UBUNTU, '14.04'): ['unattended-upgrades'],
    }
    
    tasks = (
        'configure',
    )
    
    def set_defaults(self):
        
        self.env.mail_to = 'root@localhost'
        self.env.reboot = 'true'
        self.env.reboot_time = '02:00'
        self.env.mailonlyonerror = "true"
        
        self.env.update_package_lists = 1
        self.env.download_upgradeable_packages = 1
        self.env.autoclean_interval = 7
        self.env.unattended_upgrade = 1

    def configure(self):
        
        #TODO:generalize for other distros?
        assert not self.genv.host_os_distro or self.genv.host_os_distro == UBUNTU, \
            'Only Ubuntu is supported.'
        
        if self.env.enabled:
            
            # Enable automatic package updates for Ubuntu.
            # Taken from the guide at https://help.ubuntu.com/lts/serverguide/automatic-updates.html.
            self.sudo_or_dryrun('apt-get install --yes unattended-upgrades')
            fn = self.render_to_file('unattended_upgrades/etc_apt_aptconfd_50unattended_upgrades')
            self.put_or_dryrun(local_path=fn, remote_path='/etc/apt/apt.conf.d/50unattended-upgrades', use_sudo=True)
            fn = self.render_to_file('unattended_upgrades/etc_apt_aptconfd_10periodic')
            self.put_or_dryrun(local_path=fn, remote_path='/etc/apt/apt.conf.d/10periodic', use_sudo=True)
            
        else:
            #TODO:disable
            pass
    
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']
        
UnattendedUpgradesSatchel()
