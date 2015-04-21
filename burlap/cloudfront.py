from fabric.api import (
    env,
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

@task_or_dryrun
def get_or_create_distribution(s3_bucket):
    if not get_dryrun():
        conn = boto.connect_cloudfront()
        origin_dns = '%s.s3.amazonaws.com' % s3_bucket.name
        origin = boto.cloudfront.origin\
            .S3Origin(origin_dns)
#        origin = boto.cloudfront.origin\
#            .S3Origin(s3_bucket.get_website_endpoint())
        
        distro = None
        dists = conn.get_all_distributions()
        for d in dists:
            if origin_dns == d.get_distribution().config.origin.dns_name:
                distro = d
                break
        
        if not distro:
            distro = conn.create_distribution(origin=origin, enabled=True)
            
        return distro
    else:
        print 'boto.connect_cloudfront().create_distribution(%s)' % repr(name)
