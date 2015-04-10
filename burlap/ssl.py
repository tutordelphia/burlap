import os
import re
from datetime import datetime

from fabric.api import (
    env,
    require,
    settings,
    cd,
    task,
    hide,
)

try:
    import boto
except ImportError:
    boto = None

import pytz

from fabric.contrib import files
from fabric.tasks import Task

import dateutil.parser

from burlap import common
from burlap.common import (
    ALL,
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    SITE,
    ROLE,
)
from burlap.decorators import task_or_dryrun

env.ssl_country = '?'
env.ssl_state = '?'
env.ssl_city = '?'
env.ssl_organization = '?'
env.ssl_common_name = '?'
env.ssl_days = 365
env.ssl_length = 4096
env.ssl_domain = ''

@task_or_dryrun
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
#    local_or_dryrun('openssl genrsa -des3 -passout "pass:" -out %(ssl_base_dst)s.key 1024' % env)
#    #enter simple passphrase, we'll remove it later
#
#    local_or_dryrun('openssl req -nodes -newkey rsa:2048 -keyout %(ssl_base_dst)s.key -out %(ssl_base_dst)s.csr' % env)
#
#    local_or_dryrun('cp %(ssl_base_dst)s.key %(ssl_base_dst)s.key.org' % env)
#    local_or_dryrun('openssl rsa -in %(ssl_base_dst)s.key.org -out %(ssl_base_dst)s.key' % env)
#    local_or_dryrun('rm -f %(ssl_base_dst)s.key.org' % env)
#
#    local_or_dryrun('openssl x509 -req -days 365 -in %(ssl_base_dst)s.csr -signkey %(ssl_base_dst)s.key -out %(ssl_base_dst)s.crt' % env)
#
#    local_or_dryrun('openssl rsa -in %(ssl_base_dst)s.key -text' % env)
#    local_or_dryrun('openssl x509 -inform PEM -in %(ssl_base_dst)s.crt' % env)
    cmd = 'openssl req -new -newkey rsa:%(ssl_length)s -days %(ssl_days)s -nodes -x509 -subj "/C=%(ssl_country)s/ST=%(ssl_state)s/L=%(ssl_city)s/O=%(ssl_organization)s/CN=%(ssl_domain)s" -keyout %(ssl_base_dst)s.key  -out %(ssl_base_dst)s.crt' % env
    print cmd
    local_or_dryrun(cmd)

@task_or_dryrun
def generate_csr(domain='', r=None):
    """
    Creates a certificate signing request to be submitted to a formal
    certificate authority to generate a certificate.
    
    Note, the provider may say the CSR must be created on the target server,
    but this is not necessary.
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
#        
        assert env.ssl_domain, 'No SSL domain defined.'
    
        #2048?
        env.ssl_base_dst = '%s/%s' % (ssl_dst, env.ssl_domain.replace('*.', ''))
        cmd = 'openssl req -nodes -newkey rsa:%(ssl_length)s -subj "/C=%(ssl_country)s/ST=%(ssl_state)s/L=%(ssl_city)s/O=%(ssl_organization)s/CN=%(ssl_domain)s" -keyout %(ssl_base_dst)s.key -out %(ssl_base_dst)s.csr' % env
        local_or_dryrun(cmd)

def get_expiration_date(fn):
    """
    Reads the expiration date of a local crt file.
    """
    env.ssl_crt_fn = fn
    with hide('running'):
        ret = local_or_dryrun('openssl x509 -noout -in %(ssl_crt_fn)s -dates' % env, capture=True)
    matches = re.findall('notAfter=(.*?)$', ret, flags=re.IGNORECASE)
    if matches:
        return dateutil.parser.parse(matches[0])

@task_or_dryrun
def list_expiration_dates(base='roles/all/ssl'):
    """
    Scans through all local .crt files and displays the expiration dates.
    """
    max_fn_len = 0
    max_date_len = 0
    data = []
    for fn in os.listdir(base):
        fqfn = os.path.join(base, fn)
        if not os.path.isfile(fqfn):
            continue
        if not fn.endswith('.crt'):
            continue
        expiration_date = get_expiration_date(fqfn)
        max_fn_len = max(max_fn_len, len(fn))
        max_date_len = max(max_date_len, len(str(expiration_date)))
        data.append((fn, expiration_date))
    print '%s %s %s' % ('Filename'.ljust(max_fn_len), 'Expiration Date'.ljust(max_date_len), 'Expired')
    now = datetime.now().replace(tzinfo=pytz.UTC)
    for fn, dt in sorted(data):
        
        if dt is None:
            expired = '?'
        elif dt < now:
            expired = 'YES'
        else:
            expired = 'NO'
        print '%s %s %s' % (fn.ljust(max_fn_len), str(dt).ljust(max_date_len), expired)
        