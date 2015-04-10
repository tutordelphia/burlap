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

from fabric.contrib import files
from fabric.tasks import Task

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

env.host_hostname = None
env.media_mount_dirs = []

@task_or_dryrun
def set_hostname(name=None):
    """
    Assigns a name to the server accessible from user space.
    
    Note, we add the name to /etc/hosts since not all programs use
    /etc/hostname to reliably identify the server hostname.
    """
    assert not env.hosts or len(env.hosts) == 1, 'Too many hosts.'
    env.host_hostname = name or env.host_hostname or env.host_string or env.hosts[0]
    sudo_or_dryrun('echo "%(host_hostname)s" > /etc/hostname' % env)
    sudo_or_dryrun('echo "127.0.0.1 %(host_hostname)s" | cat - /etc/hosts > /tmp/out && mv /tmp/out /etc/hosts' % env)
    sudo_or_dryrun('service hostname restart; sleep 3')

#TODO:deprecated?
@task_or_dryrun
def mount():
    """
    Mounts file systems.
    
    TODO:Remove? This should be no longer be an issue now that
    /etc/fstab has the proper mount settings.
    
    remote_host:remote_path  /data/media             nfs     _netdev,soft,intr,rw,bg        0 0
    """
    #TODO:these are temporary commands, change to auto-mount in /etc/fstab?
    for data in env.media_mount_dirs:
        if isinstance(data, (list, tuple)):
            from_path, to_path, owner, group, perms = data
        else:
            assert isinstance(data, dict)
            from_path = data['src']
            to_path = data['dst']
            owner = data['owner']
            group = data['group']
            perms = data['perms']
            
        with settings(warn_only=1):
            
            cmd = 'umount %s' % to_path
            sudo_or_dryrun(cmd)
                
            cmd = 'rm -Rf %s' % to_path
            sudo_or_dryrun(cmd)
                
            cmd = 'mkdir -p %s' % to_path
            sudo_or_dryrun(cmd)
                
        cmd = 'mount -t nfs %s %s' % (from_path, to_path)
        sudo_or_dryrun(cmd)
        
        if owner and group:
            env.mount_owner = owner
            env.mount_group = group
            cmd = 'chown -R %(mount_owner)s:%(mount_group)s /data/ops' % env
            sudo_or_dryrun(cmd)
        
        if perms:
            env.mount_perms = perms
            cmd = 'chmod -R %(mount_perms)s /data/ops' % env
            sudo_or_dryrun(cmd)

@task_or_dryrun
def get_public_ip():
    """
    Gets the public IP for a host.
    """
    ret = run_or_dryrun('wget -qO- http://ipecho.net/plain ; echo')
    return ret

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
        