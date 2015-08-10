"""
General tweaks and services to enhance system security.
"""
import os
import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
    runs_once,
    execute,
)

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
)
from burlap.decorators import task_or_dryrun

# Environment variables.
if 'security_unattended_upgrades_enabled' not in env:

    env.security_unattended_upgrades_enabled = False
    
    env.security_unattended_upgrades_mail_to = 'root@localhost'
    env.security_unattended_upgrades_reboot = 'true'
    env.security_unattended_upgrades_reboot_time = '02:00'
    env.security_unattended_upgrades_mailonlyonerror = "true"
    
    env.security_unattended_upgrades_update_package_lists = 1;
    env.security_unattended_upgrades_download_upgradeable_packages = 1;
    env.security_unattended_upgrades_autoclean_interval = 7;
    env.security_unattended_upgrades_unattended_upgrade = 1;

# Names.
UNATTENDED_UPGRADES = 'security_unattended_upgrades'

# Package declarations.
common.required_system_packages[UNATTENDED_UPGRADES] = {
    common.UBUNTU: ['unattended-upgrades'],
    (common.UBUNTU, '12.04'): ['unattended-upgrades'],
    (common.UBUNTU, '14.04'): ['unattended-upgrades'],
}

### Task functions.

@task_or_dryrun
def configure_unattended_upgrades():
    
    #TODO:generalize for other distros?
    assert not env.host_os_distro or env.host_os_distro == common.UBUNTU, \
        'Only Ubuntu is supported.'
    
    #sudo apt-get install unattended-upgrades
    
    if env.security_unattended_upgrades_enabled:
        
        # Enable automatic package updates for Ubuntu.
        # Taken from the guide at https://help.ubuntu.com/lts/serverguide/automatic-updates.html.
        fn = common.render_to_file('unattended_upgrades/etc_apt_aptconfd_50unattended_upgrades')
        put_or_dryrun(local_path=fn, remote_path='/etc/apt/apt.conf.d/50unattended-upgrades', use_sudo=True)
        fn = common.render_to_file('unattended_upgrades/etc_apt_aptconfd_10periodic')
        put_or_dryrun(local_path=fn, remote_path='/etc/apt/apt.conf.d/10periodic', use_sudo=True)

### Manifest functions. 

@task_or_dryrun
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    verbose = common.get_verbose()
    data = common.get_component_settings(UNATTENDED_UPGRADES)
    if verbose:
        print data
    return data

common.manifest_recorder[UNATTENDED_UPGRADES] = record_manifest

common.add_deployer(
    UNATTENDED_UPGRADES,
    'security.configure_unattended_upgrades',
    before=['packager', 'user'])
