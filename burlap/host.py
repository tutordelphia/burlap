import os

from fabric.api import (
    env,
    settings,
    cd,
    runs_once,
    execute,
)

from burlap import common
from burlap.common import (
    Satchel,
)
from burlap.decorators import task_or_dryrun

if 'host_hostname' not in env:
    
    env.host_hostname = None
    env.host_os_type = None # Linux/Windows/etc
    env.host_os_distro = None # Ubuntu/Fedora/etc
    env.host_os_release = None # 12.04/14.04/etc

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
        print hostname

@task_or_dryrun
@runs_once
def list_public_ips(show_hostname=0):
    """
    Aggregates the public IPs for several hosts.
    """
    show_hostname = int(show_hostname)
    ret = execute(get_public_ip)
    print '-'*80
    have_updates = 0
    for hn, output in ret.items():
        if show_hostname:
            print hn, output
        else:
            print output

@task_or_dryrun
def reboot():
    common.sudo_or_dryrun('reboot now; sleep 10;')

class HostnameSatchel(Satchel):
    
    name = 'hostname'
    
    tasks = (
        'configure',
        'get_public_ip',
    )
    
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

    def get_public_ip(self):
        """
        Gets the public IP for a host.
        """
        ret = self.run_or_dryrun(self.env.get_public_ip_command)
        return ret
        
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
        
    configure.is_deployer = True
    configure.deploy_before = []

HostnameSatchel()
