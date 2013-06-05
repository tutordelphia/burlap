import os
import re

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    #run as _run,
    run,
    settings,
    sudo,
    cd,
    task,
)

from fabric.contrib import files
from fabric.tasks import Task

from burlap.common import (
    run,
    put,
    SITE,
    ROLE,
    render_remote_paths,
    render_to_file,
    find_template,
)

env.ip_type = 'static' # |dynamic
env.ip_interface = 'eth0'
env.ip_netmask = '255.255.255.0'
env.ip_broadcast = '10.157.10.255'
env.ip_gateway = '10.157.10.1'
env.ip_dns_nameservers = None
env.ip_interfaces_fn = '/etc/network/interfaces'
env.ip_network_restart_command = '/etc/init.d/networking restart'

@task
def static():
    """
    Configures the server to use a static IP.
    """
    fn = render_to_file('ip_interfaces_static.template')
    put(local_path=fn, remote_path=env.ip_interfaces_fn, use_sudo=True)
    
    #sudo('ifdown %(ip_interface)s' % env)
    #sudo('ifup %(ip_interface)s' % env)
    sudo(env.ip_network_restart_command % env)
