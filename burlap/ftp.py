#NOTE, experimental, incomplete
import os
import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
)

from fabric.contrib import files

from burlap.common import (
    QueuedCommand,
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
)
from burlap import common
from burlap.decorators import task_or_dryrun

#env.proftpd

env.proftpd_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start proftpd.service',
        common.UBUNTU: 'service proftpd start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop proftpd.service',
        common.UBUNTU: 'service proftpd stop',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable proftpd.service',
        common.UBUNTU: 'chkconfig proftpd off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable proftpd.service',
        common.UBUNTU: 'chkconfig proftpd on',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl restart proftpd.service',
        common.UBUNTU: 'service proftpd restart; sleep 5',
    },
    common.STATUS:{
        common.FEDORA: 'systemctl status proftpd.service',
        common.UBUNTU: 'service proftpd status',
    },
}

PROFTPD = 'PROFTPD'

common.required_system_packages[PROFTPD] = {
    common.FEDORA: ['proftpd'],
    (common.UBUNTU, '12.04'): ['proftpd'],
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.proftpd_service_commands[action][os_version.distro]

@task_or_dryrun
def enable():
    cmd = get_service_command(common.ENABLE)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def disable():
    cmd = get_service_command(common.DISABLE)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def start():
    cmd = get_service_command(common.START)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def stop():
    cmd = get_service_command(common.STOP)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def restart():
    cmd = get_service_command(common.RESTART)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def status():
    cmd = get_service_command(common.STATUS)
    
    sudo_or_dryrun(cmd)

def render_paths():
    from burlap.dj import render_remote_paths
    render_remote_paths()

@task_or_dryrun
def configure(site=None, full=0):
    """
    Installs and configures proftpd.
    """
    full = int(full)

def configure_all(**kwargs):
    kwargs['site'] = common.ALL
    return configure(**kwargs)

@task_or_dryrun
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = common.get_component_settings(PROFTPD)
    #data['iptables_rules_template_content'] = common.render_to_string(env.iptables_rules_template, verbose=False)
    return data

def compare_manifest(old):
    """
    Compares the current settings to previous manifests and returns the methods
    to be executed to make the target match current settings.
    """
    old = old or {}
    methods = []
    pre = ['package']
    new = record_manifest()
    has_diffs = common.check_settings_for_differences(old, new, as_bool=True)
    if has_diffs:
        methods.append(QueuedCommand('ftp.configure_all', pre=pre))
    return methods

common.manifest_recorder[PROFTPD] = record_manifest
common.manifest_comparer[PROFTPD] = compare_manifest

common.service_configurators[PROFTPD] = [configure_all]
common.service_restarters[PROFTPD] = [restart]
