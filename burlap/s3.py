import os
import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
    task,
    runs_once,
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
    get_dryrun,
    SITE,
    ROLE,
)
from burlap.decorators import task_or_dryrun

env.AWS_ACCESS_KEY_ID = None
env.AWS_SECRET_ACCESS_KEY = None
env.s3_sync_enabled = False
# {name:[dict(local_path='static/', remote_path='$AWS_BUCKET:/')]}
env.s3_sync_sets = {}
env.s3_media_postfix = ''

S3SYNC = 'S3SYNC'

common.required_system_packages[S3SYNC] = {
#     common.FEDORA: ['ruby', 'rubygems'],
    (common.UBUNTU, '12.04'): [
        #'ruby', 'rubygems', 'libxml2-dev', 'libxslt-dev'
    ],
    (common.UBUNTU, '14.04'): [
        #'ruby', 'rubygems', 'libxml2-dev', 'libxslt-dev'
    ],
}
common.required_ruby_packages[S3SYNC] = {
#     common.FEDORA: ['s3sync==1.2.5'],
#     common.UBUNTU: ['s3sync==1.2.5'],
}

@task_or_dryrun
def get_or_create_bucket(name):
    if not get_dryrun():
        conn = boto.connect_s3()
        bucket = conn.create_bucket(name)
        return bucket
    else:
        print 'boto.connect_s3().create_bucket(%s)' % repr(name)

#S3SYNC_PATH_PATTERN = r'(?:Create|Update)\s+node\s+([^\n]+)'
S3SYNC_PATH_PATTERN = r'(?:->)\s+([^\n]+)'

@task_or_dryrun
@runs_once
def sync(sync_set, force=0):
    """
    Uploads media to an Amazon S3 bucket using s3sync.
    
    Requires the s3sync gem: sudo gem install s3sync
    """
    from burlap.dj import get_settings, render_remote_paths
    force = int(force)
    env.s3_sync_force_flag = ' --force ' if force else ''
    
#    print'env.SITE:',env.SITE
    _settings = get_settings(verbose=1)
    assert _settings, 'Unable to import settings.'
    for k in _settings.__dict__.iterkeys():
        if k.startswith('AWS_'):
            env[k] = _settings.__dict__[k]
    
    #local_or_dryrun('which s3sync')
    #print 'AWS_STATIC_BUCKET_NAME:',_settings.AWS_STATIC_BUCKET_NAME
    
    render_remote_paths()
    
    site_data = env.sites[env.SITE]
    env.update(site_data)
    
    rets = []
    for paths in env.s3_sync_sets[sync_set]:
        is_local = paths.get('is_local', True)
        local_path = paths['local_path'] % env
        remote_path = paths['remote_path']
        remote_path = remote_path.replace(':/', '/')
        if not remote_path.startswith('s3://'):
            remote_path = 's3://' + remote_path
        local_path = local_path % env
        
        if is_local:
            #local_or_dryrun('which s3sync')#, capture=True)
            env.s3_local_path = os.path.abspath(local_path)
        else:
            #run('which s3sync')
            env.s3_local_path = local_path
            
        if local_path.endswith('/') and not env.s3_local_path.endswith('/'):
            env.s3_local_path = env.s3_local_path + '/'
            
        env.s3_remote_path = remote_path % env
        
        print 'Syncing %s to %s...' % (env.s3_local_path, env.s3_remote_path)
        
        # Old buggy Ruby version.
#         cmd = ('export AWS_ACCESS_KEY_ID=%(AWS_ACCESS_KEY_ID)s; '\
#             'export AWS_SECRET_ACCESS_KEY=%(AWS_SECRET_ACCESS_KEY)s; '\
#             's3sync --recursive --verbose --progress --public-read '\
#             '%(s3_local_path)s %(s3_remote_path)s') % env
        # Superior Python version.
        if force:
            env.s3_sync_cmd = 'put'
        else:
            env.s3_sync_cmd = 'sync'
        cmd = (
            'export AWS_ACCESS_KEY_ID=%(AWS_ACCESS_KEY_ID)s; '\
            'export AWS_SECRET_ACCESS_KEY=%(AWS_SECRET_ACCESS_KEY)s; '\
            's3cmd %(s3_sync_cmd)s --progress --acl-public --guess-mime-type --no-mime-magic '\
            '--delete-removed --cf-invalidate --recursive %(s3_sync_force_flag)s '\
            '%(s3_local_path)s %(s3_remote_path)s') % env
        if is_local:
            local_or_dryrun(cmd)
        else:
            run_or_dryrun(cmd)
    
#     if auto_invalidate:
#         for ret in rets:
#             print 's3sync:', ret
#             paths = re.findall(
#                 S3SYNC_PATH_PATTERN,
#                 ret,
#                 flags=re.DOTALL|re.MULTILINE|re.IGNORECASE)
#             print 'paths:', paths
#             #TODO:handle more than 1000 paths?
#             invalidate(*paths)

@task_or_dryrun
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
            raise Exception, ('Target distribution %s could not be found '
                'in the AWS account.') \
                    % (settings.AWS_STATIC_BUCKET_NAME,)
        print 'Using distribution %s associated with origin %s.' \
            % (target_dist.id, _settings.AWS_STATIC_BUCKET_NAME)
        inval_req = c.create_invalidation_request(target_dist.id, paths)
        print 'Issue invalidation request %s.' % (inval_req,)
        
        i += 1000
        