"""
Various tools for manipulating files.
"""
import os
import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
)

try:
    import boto
except ImportError:
    boto = None
    
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
)
from burlap.decorators import task_or_dryrun

env.file_sync_sets = []
env.file_default_user = 'www-data'
env.file_default_group = 'www-data'

@task_or_dryrun
def sync():
    """
    Uploads sets of files to the host.
    """
    
    for data in env.file_sync_sets:
        env.file_src = src = data['src']
        assert os.path.isfile(src), 'File %s does not exist.' % (src,)
        env.file_dst = dst = data['dst']
        
        env.file_dst_dir, env.file_dst_file = os.path.split(dst)
        cmd = 'mkdir -p %(file_dst_dir)s' % env
        sudo_or_dryrun(cmd)
        
        put_or_dryrun(local_path=src, remote_path=dst, use_sudo=True)
        
        env.file_user = data.get('user', env.file_default_user)
        env.file_group = data.get('group', env.file_default_group)
        cmd = 'chown %(file_user)s:%(file_group)s %(file_dst)s' % env
        sudo_or_dryrun(cmd)

@task_or_dryrun
def appendline(fqfn, line, use_sudo=0, verbose=1, commands_only=0):
    """
    Appends the given line to the given file only if the line does not already
    exist in the file.
    """
    verbose = int(verbose)
    commands_only = int(commands_only)
    
    use_sudo = int(use_sudo)
    kwargs = dict(fqfn=fqfn, line=line)
    cmd = 'grep -qF "{line}" {fqfn} || echo "{line}" >> {fqfn}'.format(**kwargs)
    if verbose:
        print(cmd)
    if not commands_only:
        if use_sudo:
            sudo_or_dryrun(cmd)
        else:
            run_or_dryrun(cmd)
    return [cmd]
    