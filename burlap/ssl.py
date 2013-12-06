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
    ALL,
    #run,
    put,
    SITE,
    ROLE,
)

env.ssl_country = '?'
env.ssl_state = '?'
env.ssl_city = '?'
env.ssl_organization = '?'
env.ssl_common_name = '?'
env.ssl_days = 365
env.ssl_length = 4096
env.ssl_domain = ''

@task
def generate_self_signed_certificate(domain='', r=None):
    """
    Generates a self-signed certificate for use in an internal development
    environment for testing SSL pages.
    """
    env.ssl_domain = domain or env.ssl_domain
    assert env.ssl_domain, 'No SSL domain defined.'
    role = r or env.ROLE or ALL
    ssl_dst = 'roles/%s/ssl' % (role,)
    if not os.path.isdir(ssl_dst):
        os.makedirs(ssl_dst)

    env.ssl_base_dst = '%s/%s' % (ssl_dst, env.ssl_domain)
#    http://almostalldigital.wordpress.com/2013/03/07/self-signed-ssl-certificate-for-ec2-load-balancer/

    #openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 -subj "/C=US/ST=Denial/L=Springfield/O=Dis/CN=www.example.com" -keyout www.example.com.key  -out www.example.com.cert
#    local('openssl genrsa -des3 -passout "pass:" -out %(ssl_base_dst)s.key 1024' % env)
#    #enter simple passphrase, we'll remove it later
#
#    local('openssl req -nodes -newkey rsa:2048 -keyout %(ssl_base_dst)s.key -out %(ssl_base_dst)s.csr' % env)
#
#    local('cp %(ssl_base_dst)s.key %(ssl_base_dst)s.key.org' % env)
#    local('openssl rsa -in %(ssl_base_dst)s.key.org -out %(ssl_base_dst)s.key' % env)
#    local('rm -f %(ssl_base_dst)s.key.org' % env)
#
#    local('openssl x509 -req -days 365 -in %(ssl_base_dst)s.csr -signkey %(ssl_base_dst)s.key -out %(ssl_base_dst)s.crt' % env)
#
#    local('openssl rsa -in %(ssl_base_dst)s.key -text' % env)
#    local('openssl x509 -inform PEM -in %(ssl_base_dst)s.crt' % env)
    cmd = 'openssl req -new -newkey rsa:%(ssl_length)s -days %(ssl_days)s -nodes -x509 -subj "/C=%(ssl_country)s/ST=%(ssl_state)s/L=%(ssl_city)s/O=%(ssl_organization)s/CN=%(ssl_domain)s" -keyout %(ssl_base_dst)s.key  -out %(ssl_base_dst)s.crt' % env
    print cmd
    local(cmd)

@task
def generate_csr(domain='', r=None):
    """
    Creates a certificate signing request to be submitted to a formal
    certificate authority to generate a certificate.
    """
    from apache import set_apache_specifics, set_apache_site_specifics
    env.ssl_domain = domain or env.ssl_domain
    role = r or env.ROLE or ALL
    ssl_dst = 'roles/%s/ssl' % (role,)
    print 'ssl_dst:',ssl_dst
    if not os.path.isdir(ssl_dst):
        os.makedirs(ssl_dst)

    #apache_specifics = set_apache_specifics()
    
    for site, site_data in common.iter_sites(setter=set_apache_site_specifics):
        print 'site:',site
        #continue
#        
        assert env.ssl_domain, 'No SSL domain defined.'
    
        #2048?
        env.ssl_base_dst = '%s/%s' % (ssl_dst, env.ssl_domain)
        cmd = 'openssl req -nodes -newkey rsa:%(ssl_length)s -subj "/C=%(ssl_country)s/ST=%(ssl_state)s/L=%(ssl_city)s/O=%(ssl_organization)s/CN=%(ssl_domain)s" -keyout %(ssl_base_dst)s.key -out %(ssl_base_dst)s.csr' % env
        print cmd
        local(cmd)
    