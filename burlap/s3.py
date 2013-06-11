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

from burlap import common
from burlap.common import (
    #run,
    put,
    get_settings,
    SITE,
    ROLE,
)

env.AWS_ACCESS_KEY_ID = None
env.AWS_SECRET_ACCESS_KEY = None
env.s3_sync_sets = {} # {name:[dict(local_path='static/', remote_path='$AWS_BUCKET:/')]}
env.s3_media_postfix = ''

S3SYNC = 'S3SYNC'

common.required_system_packages[S3SYNC] = {
    common.FEDORA: ['ruby', 'rubygems'],
    common.UBUNTU: ['ruby', 'rubygems'],
}
common.required_ruby_packages[S3SYNC] = {
    common.FEDORA: ['s3sync'],
    common.UBUNTU: ['s3sync'],
}

@task
def sync(sync_set, dryrun=0):
    """
    Uploads media to an Amazon S3 bucket using s3sync.
    
    Requires the s3sync gem: sudo gem install s3sync
    """
    env.dryrun = int(dryrun)
    _settings = get_settings()
    for k in _settings.__dict__.iterkeys():
        if k.startswith('AWS_'):
            env[k] = _settings.__dict__[k]
    
    #local('which s3sync')
    #print 'AWS_STATIC_BUCKET_NAME:',_settings.AWS_STATIC_BUCKET_NAME
    
    common.render_remote_paths()
    
    site_data = env.sites[env.SITE]
    env.update(site_data)
    
    for paths in env.s3_sync_sets[sync_set]:
        is_local = paths.get('is_local', True)
        local_path = paths['local_path'] % env
        remote_path = paths['remote_path']
        local_path = local_path % env
        
        if is_local:
            local('which s3sync')
            env.s3_local_path = os.path.abspath(local_path)
        else:
            run('which s3sync')
            env.s3_local_path = local_path
            
        if local_path.endswith('/') and not env.s3_local_path.endswith('/'):
            env.s3_local_path = env.s3_local_path + '/'
            
        env.s3_remote_path = remote_path % env
        
        print 'Syncing %s to %s...' % (env.s3_local_path, env.s3_remote_path)
        
        cmd = ('export AWS_ACCESS_KEY_ID=%(AWS_ACCESS_KEY_ID)s; '\
            'export AWS_SECRET_ACCESS_KEY=%(AWS_SECRET_ACCESS_KEY)s; '\
            's3sync --recursive --verbose --progress --public-read '\
            '%(s3_local_path)s %(s3_remote_path)s') % env
        print cmd
        if not int(dryrun):
            if is_local:
                local(cmd)
            else:
                run(cmd)
    