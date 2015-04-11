import os
import sys
import datetime

from fabric.api import (
    env,
    require,
    settings,
    cd,
    task,
)
from fabric.contrib import files

from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    render_to_string,
    QueuedCommand,
)
from burlap import common
from burlap.decorators import task_or_dryrun

env.iptables_enabled = True
env.iptables_ssh_port = 22
env.iptables_rules_template = 'iptables.template.rules'

env.iptables_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start iptables.service',
        common.UBUNTU: 'service iptables start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop iptables.service',
        common.UBUNTU: 'service iptables stop',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable iptables.service',
        common.UBUNTU: 'chkconfig iptables off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable iptables.service',
        common.UBUNTU: 'chkconfig iptables on',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl restart iptables.service',
        common.UBUNTU: 'service iptables restart',
    },
}

IPTABLES = 'IPTABLES'

common.required_system_packages[IPTABLES] = {
    common.FEDORA: ['iptables'],
    (common.UBUNTU, '12.04'): ['iptables'],
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.iptables_service_commands[action][os_version.distro]

@task_or_dryrun
def enable():
    cmd = get_service_command(common.ENABLE)
    print cmd
    run(cmd)

@task_or_dryrun
def disable():
    cmd = get_service_command(common.DISABLE)
    print cmd
    run(cmd)

@task_or_dryrun
def start():
    cmd = get_service_command(common.START)
    print cmd
    run(cmd)

@task_or_dryrun
def stop():
    cmd = get_service_command(common.STOP)
    print cmd
    run(cmd)

@task_or_dryrun
def restart():
    cmd = get_service_command(common.RESTART)
    print cmd
    run(cmd)

@task_or_dryrun
def configure():
    """
    Configures rules for IPTables.
    """
    if env.iptables_enabled:
        fn = common.render_to_file(env.iptables_rules_template)
        put(local_path=fn)
        
        cmd = 'iptables-restore < %(put_remote_path)s; iptables-save > /etc/iptables.up.rules' % env
        sudo_or_dryrun(cmd)
        
        enable()
        restart()
    else:
        disable()
        stop()

@task_or_dryrun
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = common.get_component_settings(IPTABLES)
    data['iptables_rules_template_content'] = common.render_to_string(env.iptables_rules_template, verbose=False)
    return data

def compare_manifest(old):
    """
    Compares the current settings to previous manifests and returns the methods
    to be executed to make the target match current settings.
    """
    old = old or {}
    methods = []
    pre = ['ip']
    new = record_manifest()
    has_diffs = common.check_settings_for_differences(old, new, as_bool=True)
    if has_diffs:
        methods.append(QueuedCommand('iptables.configure', pre=pre))
    return methods

common.manifest_recorder[IPTABLES] = record_manifest
common.manifest_comparer[IPTABLES] = compare_manifest
