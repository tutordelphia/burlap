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

try:
    import boto
except ImportError:
    boto = None
    
from fabric.contrib import files
from fabric.tasks import Task

from burlap import common
from burlap.common import (
    #run,
    put,
    SITE,
    ROLE,
)

env.file_sync_sets = []
env.file_default_user = 'www-data'
env.file_default_group = 'www-data'

@task
def sync(dryrun=0):
    """
    Uploads sets of files to the host.
    """
    dryrun = int(dryrun)
    for data in env.file_sync_sets:
        env.file_src = src = data['src']
        assert os.path.isfile(src), 'File %s does not exist.' % (src,)
        env.file_dst = dst = data['dst']
        
        env.file_dst_dir, env.file_dst_file = os.path.split(dst)
        cmd = 'mkdir -p %(file_dst_dir)s' % env
        if dryrun:
            print env.host_string+':', cmd
        else:
            sudo(cmd)
        
        if dryrun:
            #print 'put(%s, %s)' % (src, dst)
            print 'localhost: scp -i %s %s %s@%s:%s' % (env.key_filename, src, env.user, env.host_string, dst)
        else:
            put(local_path=src, remote_path=dst, use_sudo=True)
        
        env.file_user = data.get('user', env.file_default_user)
        env.file_group = data.get('group', env.file_default_group)
        cmd = 'chown %(file_user)s:%(file_group)s %(file_dst)s' % env
        if dryrun:
            print env.host_string+':', cmd
        else:
            sudo(cmd)
        