import os
import re

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    run as _run,
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
    render_to_file,
    find_template,
)

env.host_hostname = None
env.media_mount_dirs = []

@task
def set_hostname(name=None):
    """
    Assigns a name to the server accessible from user space.
    
    Note, we add the name to /etc/hosts since not all programs use
    /etc/hostname to reliably identify the server hostname.
    """
    assert not env.hosts or len(env.hosts) == 1, 'Too many hosts.'
    env.host_hostname = name or env.host_hostname or env.host_string or env.hosts[0]
    sudo('echo "%(host_hostname)s" > /etc/hostname' % env)
    sudo('echo "127.0.0.1 %(host_hostname)s" | cat - /etc/hosts > /tmp/out && mv /tmp/out /etc/hosts' % env)
    sudo('service hostname restart; sleep 3')

#TODO:deprecated?
@task
def mount(dryrun=0):
    """
    Mounts file systems.
    
    TODO:Remove? This should be no longer be an issue now that
    /etc/fstab has the proper mount settings.
    
    remote_host:remote_path  /data/media             nfs     _netdev,soft,intr,rw,bg        0 0
    """
    #TODO:these are temporary commands, change to auto-mount in /etc/fstab?
    dryrun = int(dryrun)
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
            print cmd
            if not dryrun:
                sudo(cmd)
                
            cmd = 'rm -Rf %s' % to_path
            print cmd
            if not dryrun:
                sudo(cmd)
                
            cmd = 'mkdir -p %s' % to_path
            print cmd
            if not dryrun:
                sudo(cmd)
                
        cmd = 'mount -t nfs %s %s' % (from_path, to_path)
        print cmd
        if not dryrun:
            sudo(cmd)
        
        if owner and group:
            env.mount_owner = owner
            env.mount_group = group
            cmd = 'chown -R %(mount_owner)s:%(mount_group)s /data/ops' % env
            print cmd
            if not dryrun:
                sudo(cmd)
        
        if perms:
            env.mount_perms = perms
            cmd = 'chmod -R %(mount_perms)s /data/ops' % env
            print cmd
            if not dryrun:
                sudo(cmd)
