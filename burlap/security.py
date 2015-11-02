"""
General tweaks and services to enhance system security.
"""

from burlap import common
from burlap.common import Satchel, env

class UnattendedUpgradesSatchel(Satchel):
    """
    Enables various degrees of automatic package download and installation.
    """
    
    name = 'security_unattended_upgrades'
    
    required_system_packages = {
        common.UBUNTU: ['unattended-upgrades'],
        (common.UBUNTU, '12.04'): ['unattended-upgrades'],
        (common.UBUNTU, '14.04'): ['unattended-upgrades'],
    }
    
    def set_defaults(self):

        self.env.unattended_upgrades_enabled = False
        
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
        assert not env.host_os_distro or env.host_os_distro == common.UBUNTU, \
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
