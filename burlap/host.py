from __future__ import print_function

import os

from fabric.api import (
    env,
    settings,
    cd,
    runs_once,
    execute,
)

from burlap import Satchel
from burlap.constants import *
from burlap.decorators import task, task_or_dryrun

def iter_hostnames():
    from burlap.common import get_hosts_retriever, get_verbose
    
    verbose = get_verbose()
    
    retriever = get_hosts_retriever()
    
    hosts = list(retriever(extended=1))
    for _hostname, _data in hosts:
        yield _hostname
#         if _data.ip == env.host_string:
#             yield _hostname
#         elif _data.public_dns_name == env.host_string:
#             yield _hostname

@task_or_dryrun
@runs_once
def list_hostnames():
    for hostname in iter_hostnames():
        print(hostname)

@task_or_dryrun
@runs_once
def list_public_ips(show_hostname=0):
    """
    Aggregates the public IPs for several hosts.
    """
    show_hostname = int(show_hostname)
    ret = execute(get_public_ip)
    print('-'*80)
    have_updates = 0
    for hn, output in ret.items():
        if show_hostname:
            print(hn, output)
        else:
            print(output)

class HostSatchel(Satchel):
    """
    Used for initializing the host.
    
    Should only be called once, manually on a fresh install to initialize
    the primary user login.
    
    e.g. fab prod host.initrole host.configure
    """
    
    name = 'host'
    
    def set_defaults(self):
        
        self.env.default_hostname = 'somehost'
        self.env.default_user = 'someuser'
        self.env.default_password = 'somepassword'
            
        self.env.os_type = None # Linux/Windows/etc
        self.env.os_distro = None # Ubuntu/Fedora/etc
        self.env.os_release = None # 12.04/14.04/etc
    
    @task
    def initrole(self):
        from burlap.common import env
        #env.host_string = self.env.default_hostname
        env.hosts = [self.env.default_hostname]
        env.user = self.env.default_user
        env.password = self.env.default_password
        env.key_filename = None
    
    @task
    def reboot():
        common.sudo_or_dryrun('reboot now; sleep 10;')
    
    @task
    def configure(self):
        from burlap.user import user
        
        # Create primary user.
        # Allow primary user to login with a key.
        user.configure()
        
        # Set hostname.
        hostname.configure()
        
        self.reboot()
        
class HostnameSatchel(Satchel):
    
    name = 'hostname'
    
    def record_manifest(self):
        """
        Returns a dictionary representing a serialized state of the service.
        """
        data = {}
        data['hostnames'] = sorted(list(set(iter_hostnames())))
        return data
    
    def set_defaults(self):
        self.env.hostname = None
        self.env.get_public_ip_command = 'wget -qO- http://ipecho.net/plain ; echo'

    @task
    def get_public_ip(self):
        """
        Gets the public IP for a host.
        """
        ret = self.run_or_dryrun(self.env.get_public_ip_command)
        return ret
    
    @task
    def configure(self):
        """
        Assigns a name to the server accessible from user space.
        
        Note, we add the name to /etc/hosts since not all programs use
        /etc/hostname to reliably identify the server hostname.
        """
        from burlap.common import get_hosts_retriever
        
        verbose = self.verbose
        
        retriever = get_hosts_retriever()
        
        hostname = self.env.hostname
        hosts = list(retriever(verbose=verbose, extended=1))
        for _hostname, _data in hosts:
            if _data.ip == env.host_string:
                hostname = _hostname
                break
            elif _data.public_dns_name == env.host_string:
                hostname = _hostname
                break
                
        assert hostname, 'Unable to lookup hostname.'
    
        #env.host_hostname = name or env.host_hostname or env.host_string or env.hosts[0]
        self.env.hostname = hostname
        
        kwargs = dict(hostname=hostname)
        self.sudo_or_dryrun('echo "%(hostname)s" > /etc/hostname' % kwargs)
        self.sudo_or_dryrun('echo "127.0.0.1 %(hostname)s" | cat - /etc/hosts > /tmp/out && mv /tmp/out /etc/hosts' % kwargs)
        self.sudo_or_dryrun('service hostname restart; sleep 3')
        
    
    configure.deploy_before = []

class SSHNiceSatchel(Satchel):

    name = 'sshnice'
    
    required_system_packages = {
        FEDORA: ['cron'],
        UBUNTU: ['cron'],
        DEBIAN: ['cron'],
    }
    
    def set_defaults(self):
        self.env.enabled = False
        self.env.cron_script_path = '/etc/cron.d/sshnice'
        self.env.cron_perms = '600'
    
    @task
    def configure(self):
        if self.env.enabled:
            self.install_packages()
            remote_path = self.env.cron_script_path
            self.put_or_dryrun(
                local_path=self.find_template('host/etc_crond_sshnice'),
                remote_path=remote_path, use_sudo=True)
            self.sudo_or_dryrun('chown root:root %s' % remote_path)
            # Must be 600, otherwise gives INSECURE MODE error.
            # http://unix.stackexchange.com/questions/91202/cron-does-not-print-to-syslog
            self.sudo_or_dryrun('chmod %s %s' % (self.env.cron_perms, remote_path))#env.put_remote_path)
            self.sudo_or_dryrun('service cron restart')
        else:
            self.sudo_or_dryrun('rm -f {cron_script_path}'.format(**self.lenv))
            self.sudo_or_dryrun('service cron restart')
    configure.deploy_before = ['packager']

class TimezoneSatchel(Satchel):
    """
    Manages setting the system-wide timezone.
    
    For a list of standard timezones see:
    
        https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
    """

    name = 'timezone'
    
    def set_defaults(self):
        self.env.timezone = 'America/New_York'
    
    @task
    def configure(self):
        self.sudo_or_dryrun("sudo sh -c 'echo \"{timezone}\" > /etc/timezone'".format(**self.lenv))    
        self.sudo_or_dryrun('dpkg-reconfigure -f noninteractive tzdata')
    configure.deploy_before = ['packager']

host = HostSatchel()
hostname = HostnameSatchel()
sshnice = SSHNiceSatchel()
timezone = TimezoneSatchel()
