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
    get_settings,
    SITE,
    ROLE,
)

env.ssl_domain = ''

@task
def generate_certificate():
    """
    Generates a self-signed certificate.
    """
    assert env.ssl_domain, 'No SSL domain defined.'
    role = env.ROLE
    ssl_dst = 'roles/%s/ssl' % (role,)
    if not os.path.isdir(ssl_dst):
        os.makedirs(ssl_dst)

    env.ssl_base_dst = '%s/%s' % (ssl_dst, env.ssl_domain)
#    http://almostalldigital.wordpress.com/2013/03/07/self-signed-ssl-certificate-for-ec2-load-balancer/

    local('openssl genrsa -des3 -out %(ssl_base_dst)s.key 1024' % env)
    #enter simple passphrase, we'll remove it later

    local('openssl req -nodes -newkey rsa:2048 -keyout %(ssl_base_dst)s.key -out %(ssl_base_dst)s.csr' % env)

    local('cp %(ssl_base_dst)s.key %(ssl_base_dst)s.key.org' % env)
    local('openssl rsa -in %(ssl_base_dst)s.key.org -out %(ssl_base_dst)s.key' % env)
    local('rm -f %(ssl_base_dst)s.key.org' % env)

    local('openssl x509 -req -days 365 -in %(ssl_base_dst)s.csr -signkey %(ssl_base_dst)s.key -out %(ssl_base_dst)s.crt' % env)

    local('openssl rsa -in %(ssl_base_dst)s.key -text' % env)
    local('openssl x509 -inform PEM -in %(ssl_base_dst)s.crt' % env)
    