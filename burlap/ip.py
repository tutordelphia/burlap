import os
import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
)

from fabric.contrib import files
from fabric.tasks import Task
 
from burlap import common
from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    SITE,
    ROLE,
    render_to_file,
    find_template,
    QueuedCommand,
)
from burlap.decorators import task_or_dryrun

env.ip_type = 'static' # |dynamic
env.ip_interface = 'eth0'
env.ip_address = None
env.ip_network = '192.168.0.0'
env.ip_netmask = '255.255.255.0'
env.ip_broadcast = '10.157.10.255'
env.ip_gateway = '10.157.10.1'
env.ip_dns_nameservers = None
env.ip_interfaces_fn = '/etc/network/interfaces'
env.ip_network_restart_command = '/etc/init.d/networking restart'

IP = 'IP'

@task_or_dryrun
def static():
    """
    Configures the server to use a static IP.
    """
    fn = render_to_file('ip_interfaces_static.template')
    put(local_path=fn, remote_path=env.ip_interfaces_fn, use_sudo=True)
    
    #sudo_or_dryrun('ifdown %(ip_interface)s' % env)
    #sudo_or_dryrun('ifup %(ip_interface)s' % env)
    sudo_or_dryrun(env.ip_network_restart_command % env)

@task_or_dryrun
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = common.get_component_settings(IP)
    return data

def compare_manifest(old):
    """
    Compares the current settings to previous manifests and returns the methods
    to be executed to make the target match current settings.
    """
    old = old or {}
    methods = []
    pre = ['user']
    new = common.get_component_settings(IP)
    has_diffs = common.check_settings_for_differences(old, new, as_bool=True)
    if has_diffs:
        methods.append(QueuedCommand('ip.static', pre=pre))
    return methods

common.manifest_recorder[IP] = record_manifest
common.manifest_comparer[IP] = compare_manifest
