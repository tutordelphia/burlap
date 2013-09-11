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
    render_remote_paths,
    render_to_file,
    find_template,
)

env.media_mount_dirs = []

@task
def set_hostname(name):
    """
    Assigns a name to the server accessible from user space.
    
    Note, we add the name to /etc/hosts since not all programs use
    /etc/hostname to reliably identify the server hostname.
    """
    assert not env.hosts or len(env.hosts) == 1, 'Too many hosts.'
    env.host_hostname = name
    sudo('echo "%(host_hostname)s" > /etc/hostname' % env)
    sudo('echo "127.0.0.1 %(host_hostname)s" | cat - /etc/hosts > /tmp/out && mv /tmp/out /etc/hosts' % env)
    sudo('service hostname restart; sleep 3')

@task
def mount(dryrun=0):
    """
    Mounts /i and /medialibrary from NFS on alphafs to prodadmin.
    
    TODO:Remove? This should be no longer be an issue now that
    prodadmin:/etc/fstab has the proper mount settings.
    
    alphafs:/data/media/production  /data/media             nfs     _netdev,soft,intr,rw,bg        0 0
    """
    #TODO:these are temporary commands, change to auto-mount in /etc/fstab?
    dryrun = int(dryrun)
#    env.user = 'root'
#    env.host_string = 'devweb01'
#    env.key_filename = "%s.pem" % config.local_key
#    run("mount -t nfs alphafs:/data/media/development/i /data/media/i")
#    run("mount -t nfs alphafs:/data/media/development/medialibrary /data/media/medialibrary")
    for from_path, to_path, owner, group, perms in env.media_mount_dirs:
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
