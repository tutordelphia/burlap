import os
import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
)
 
from burlap import common
from burlap.common import (
    ServiceSatchel,
)

STATIC = 'static'
DYNAMIC = 'dynamic'

if 'ip_type' not in env:
    env.ip_type = DYNAMIC#STATIC
    env.ip_interface = 'eth0'
    env.ip_address = None
    env.ip_network = '192.168.0.0'
    env.ip_netmask = '255.255.255.0'
    env.ip_broadcast = '10.157.10.255'
    env.ip_gateway = '10.157.10.1'
    env.ip_dns_nameservers = None
    env.ip_interfaces_fn = '/etc/network/interfaces'
    #env.ip_network_restart_command = '/etc/init.d/networking restart'
    env.ip_daemon_name = 'networking'
    env.ip_service_commands = {
        common.START:{
            common.UBUNTU: 'service %s start' % env.ip_daemon_name,
        },
        common.STOP:{
            common.UBUNTU: 'service %s stop' % env.ip_daemon_name,
        },
        common.DISABLE:{
            common.UBUNTU: 'chkconfig %s off' % env.ip_daemon_name,
        },
        common.ENABLE:{
            common.UBUNTU: 'chkconfig %s on' % env.ip_daemon_name,
        },
        common.RESTART:{
            common.UBUNTU: 'service %s restart' % env.ip_daemon_name,
        },
        common.STATUS:{
            common.UBUNTU: 'service %s status' % env.ip_daemon_name,
        },
    }

class IPSatchel(ServiceSatchel):
    
    name = 'ip'
    
    commands = env.ip_service_commands
    
    tasks = (
        'configure',
        'static',
        'dynamic',
    )
    
    post_deploy_command = None

    def static(self):
        """
        Configures the server to use a static IP.
        """
        fn = self.render_to_file('ip/ip_interfaces_static.template')
        self.put_or_dryrun(local_path=fn, remote_path=env.ip_interfaces_fn, use_sudo=True)
    
    def dynamic(self):
        """
        Configures the server to use a static IP.
        """
        fn = self.render_to_file('ip/ip_interfaces_dynamic.template')
        self.put_or_dryrun(local_path=fn, remote_path=env.ip_interfaces_fn, use_sudo=True)
    
    def configure(self):
        if env.ip_type == STATIC:
            self.static()
        elif env.ip_type == DYNAMIC:
            self.dynamic()
        else:
            raise NotImplementedError, 'Unknown type: %s' % env.ip_type
        self.restart()
        
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']
    
IPSatchel()
