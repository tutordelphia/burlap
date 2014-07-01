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

env.AWS_ACCESS_KEY_ID = None
env.AWS_SECRET_ACCESS_KEY = None
env.s3_sync_enabled = False
env.s3_sync_sets = {} # {name:[dict(local_path='static/', remote_path='$AWS_BUCKET:/')]}
env.s3_media_postfix = ''

S3SYNC = 'S3SYNC'

common.required_system_packages[S3SYNC] = {
    common.FEDORA: ['ruby', 'rubygems'],
    (common.UBUNTU, '12.04'): ['ruby', 'rubygems', 'libxml2-dev', 'libxslt-dev'],
}
common.required_ruby_packages[S3SYNC] = {
    common.FEDORA: ['s3sync==1.2.5'],
    common.UBUNTU: ['s3sync==1.2.5'],
}

@task
def sync(sync_set, dryrun=0, auto_invalidate=1):
    """
    Uploads media to an Amazon S3 bucket using s3sync.
    
    Requires the s3sync gem: sudo gem install s3sync
    """
    from burlap.dj import get_settings, render_remote_paths
    auto_invalidate = int(auto_invalidate)
    env.dryrun = int(dryrun)
#    print'env.SITE:',env.SITE
    _settings = get_settings(verbose=1)
    assert _settings, 'Unable to import settings.'
    for k in _settings.__dict__.iterkeys():
        if k.startswith('AWS_'):
            env[k] = _settings.__dict__[k]
    
    #local('which s3sync')
    #print 'AWS_STATIC_BUCKET_NAME:',_settings.AWS_STATIC_BUCKET_NAME
    
    render_remote_paths()
    
    site_data = env.sites[env.SITE]
    env.update(site_data)
    
    rets = []
    for paths in env.s3_sync_sets[sync_set]:
        is_local = paths.get('is_local', True)
        local_path = paths['local_path'] % env
        remote_path = paths['remote_path']
        local_path = local_path % env
        
        if is_local:
            local('which s3sync')#, capture=True)
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
                rets.append(local(cmd, capture=True)) # can't see progress
                #rets.append(run(cmd))
            else:
                rets.append(run(cmd))
    
    if auto_invalidate:
        for ret in rets:
            print 's3sync:', ret
            paths = re.findall(
                '(?:Create|Update)\s+node\s+([^\n]+)',
                ret,
                flags=re.DOTALL|re.MULTILINE|re.IGNORECASE)
            print 'paths:', paths
            #TODO:handle more than 1000 paths?
            invalidate(*paths)

@task
def invalidate(*paths):
    """
    Issues invalidation requests to a Cloudfront distribution
    for the current static media bucket, triggering it to reload the specified
    paths from the origin.
    
    Note, only 1000 paths can be issued in a request at any one time.
    """
    from burlap.dj import get_settings
    if not paths:
        return
    # http://boto.readthedocs.org/en/latest/cloudfront_tut.html
    _settings = get_settings()
    if not _settings.AWS_STATIC_BUCKET_NAME:
        print 'No static media bucket set.'
        return
    if isinstance(paths, basestring):
        paths = paths.split(',')
    all_paths = map(str.strip, paths)
#    assert len(paths) <= 1000, \
#        'Cloudfront invalidation request limited to 1000 paths or less.'
    i = 0
    while 1:
        paths = all_paths[i:i+1000]
        if not paths:
            break
        
        #print 'paths:',paths
        c = boto.connect_cloudfront()
        rs = c.get_all_distributions()
        target_dist = None
        for dist in rs:
            print dist.domain_name, dir(dist), dist.__dict__
            bucket_name = dist.origin.dns_name.replace('.s3.amazonaws.com', '')
            if bucket_name == _settings.AWS_STATIC_BUCKET_NAME:
                target_dist = dist
                break
        if not target_dist:
            raise Exception, \
                'Target distribution %s could not be found in the AWS account.' \
                    % (settings.AWS_STATIC_BUCKET_NAME,)
        print 'Using distribution %s associated with origin %s.' \
            % (target_dist.id, _settings.AWS_STATIC_BUCKET_NAME)
        inval_req = c.create_invalidation_request(target_dist.id, paths)
        print 'Issue invalidation request %s.' % (inval_req,)
        
        i += 1000
        