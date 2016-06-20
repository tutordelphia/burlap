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
        
        self.env.default_hostname = None
        self.env.default_hosts = []
        self.env.default_user = None
        self.env.default_password = None
        self.env.default_key_filename = None
            
#         self.env.os_type = None # Linux/Windows/etc
#         self.env.os_distro = None # Ubuntu/Fedora/etc
#         self.env.os_release = None # 12.04/14.04/etc
    
    @task
    def is_present(self, host=None):
        """
        Returns true if the given host exists on the network.
        Returns false otherwise.
        """
        r = self.local_renderer
        r.env.host = host or self.genv.host_string
        ret = r._local("getent hosts {host} | awk '{{ print $1 }}'", capture=True) or ''
        if self.verbose:
            print('ret:', ret)
        ret = ret.strip()
        if self.verbose:
            print('Host %s %s present.' % (r.env.host, 'IS' if bool(ret) else 'IS NOT'))
        return bool(ret)
    
    @task
    def needs_initrole(self, stop_on_error=False):
        
        ret = False
            
        target_host_present = self.is_present()
        
        if not target_host_present:
            default_host_present = self.is_present(self.env.default_hostname)
            if default_host_present:
                if self.verbose:
                    print('Target host missing and default host present so host init required.')
                ret = True
            else:
                if self.verbose:
                    print('Target host missing but default host also missing, '
                        'so no host init required.')
                if stop_on_error:
                    raise Exception, (
                        'Both target and default hosts missing! '
                        'Is the machine turned on and plugged into the network?')
        else:
            if self.verbose:
                print('Target host is present so no host init required.')
                
        return ret
    
    @task
    def initrole(self, check=True):
        """
        Called to set default password login for systems that do not yet have passwordless
        login setup.
        """
        
        needs = True
        if check:
            needs = self.needs_initrole(stop_on_error=True)
        if not needs:
            return
        
        assert self.env.default_hostname, 'No default hostname set.'
        assert self.env.default_user, 'No default user set.'
        self.genv.host_string = self.env.default_hostname
        if self.env.default_hosts:
            self.genv.hosts = self.env.default_hosts
        else:
            self.genv.hosts = [self.env.default_hostname]
        self.genv.user = self.env.default_user
        self.genv.password = self.env.default_password
        self.genv.key_filename = self.env.default_key_filename
    
    def deploy_pre_run(self):
        
        # If the desired hostname is not present but the default hostname is present,
        # then we assume the host is new or has been reset and needs to be reconfigured.
        self.initrole()
        
    def configure(self):
        # Just a stub. All the magic happens in deploy_pre_run().
        pass
        
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
        
        # The bash command to run to get our public IP as we appear on the WAN.
        self.env.get_public_ip_command = 'wget -qO- http://ipecho.net/plain ; echo'

    @task
    def get_public_ip(self):
        """
        Gets the public IP for a host.
        """
        r = self.local_renderer
        ret = r.run(r.env.get_public_ip_command) or ''
        ret = ret.strip()
        return ret
    
    @task
    def configure(self):
        """
        Assigns a name to the server accessible from user space.
        
        Note, we add the name to /etc/hosts since not all programs use
        /etc/hostname to reliably identify the server hostname.
        """
        from burlap.common import get_hosts_retriever
        
        r = self.local_renderer
        
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
        
        r.env.hostname = hostname
        r.sudo('echo "{hostname}" > /etc/hostname')
        r.sudo('echo "127.0.0.1 {hostname}" | cat - /etc/hosts > /tmp/out && mv /tmp/out /etc/hosts')
        r.sudo('service hostname restart; sleep 3')
    
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
        r = self.local_renderer
        if self.env.enabled:
            self.install_packages()
            remote_path = r.env.remote_path = self.env.cron_script_path
            r.put(
                local_path=self.find_template('host/etc_crond_sshnice'),
                remote_path=remote_path, use_sudo=True)
            r.sudo('chown root:root %s' % remote_path)
            # Must be 600, otherwise gives INSECURE MODE error.
            # http://unix.stackexchange.com/questions/91202/cron-does-not-print-to-syslog
            r.sudo('chmod {cron_perms} {remote_path}')
            r.sudo('service cron restart')
        else:
            r.sudo('rm -f {cron_script_path}')
            r.sudo('service cron restart')
    configure.deploy_before = ['packager']

class TimezoneSatchel(Satchel):
    """
    Manages setting the system-wide timezone.
    
    For a list of standard timezones see:
    
        https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
    """

    name = 'timezone'
    
    def set_defaults(self):
        self.env.timezone = 'Etc/UTC'
    
    @task
    def configure(self):
        r = self.local_renderer
        r.sudo("sudo sh -c 'echo \"{timezone}\" > /etc/timezone'")
        r.sudo('dpkg-reconfigure -f noninteractive tzdata')
    configure.deploy_before = ['packager']

host = HostSatchel()
hostname = HostnameSatchel()
sshnice = SSHNiceSatchel()
timezone = TimezoneSatchel()
