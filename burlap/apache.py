import os
import sys
import datetime

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

from burlap.common import (
    run,
    put,
    render_to_string,
    get_packager,
    get_os_version,
    YUM,
    APT,
    FEDORA,
)

# An Apache-conf file and filename friendly string that uniquely identifies
# your web application.
env.apache_application_name = None

# If true, activates a rewrite rule that causes domain.com to redirect
# to www.domain.com.
env.apache_enforce_subdomain = True

# The value of the Apache's ServerName field. Usually should be set
# to the domain.
env.apache_server_name = None

env.apache_server_aliases = ''

env.apache_docroot = '/usr/local/%(apache_application_name)s',

env.apache_wsgi_dir = '/usr/local/%(apache_application_name)s/src/%(app_name)s',

env.apache_wsgi_processes = 5

env.apache_wsgi_threads = 15

env.apache_log_dir = '/var/log/%(apache_application_name)s'

env.apache_extra_rewrite_rules = ''

def check_required():
    for name in ['apache_application_name', 'apache_server_name']:
        assert env[name], 'Missing %s.' % (name,)

@task
def configure():
    """
    Configures Apache to host one or more websites.
    """
    print 'Configuring Apache...'
    check_required()
    fn = render_to_file('apache.template.conf')
    env.apache_tmp_conf_fn = fn+'1'
    put(local_path=fn, remote_path=env.apache_tmp_conf_fn)
    sudo("cp %(env.apache_tmp_conf_fn)s /etc/apache2/sites-available/%(apache_server_name)s" % env)
    sudo("a2ensite %(apache_server_name)s" % env)

@task
def unconfigure():
    """
    Removes all custom configurations for Apache hosted websites.
    """
    check_required()
    print 'Un-configuring Apache...'
    with settings(warn_only=True):
        sudo("[ -f /etc/apache2/sites-enabled/%(apache_server_name)s ] && rm -f /etc/apache2/sites-enabled/%(apache_server_name)s" % env)
        sudo("[ -f /etc/apache2/sites-available/%(apache_server_name)s ] && rm -f /etc/apache2/sites-available/%(apache_server_name)s" % env)

@task
def stop():
    """
    Stops Apache.
    """
    packager = get_packager()
    os_version = get_os_version()
    if packager == YUM:
        os_release = float(os_version.release)
        if os_version.distro == FEDORA and os_release >= 16:
            sudo('systemctl stop httpd.service')
        else:
            sudo('service httpd stop')
    elif packager == APT:
        sudo('service apache2 stop')

@task
def start():
    """
    Starts Apache.
    """
    packager = get_packager()
    os_version = get_os_version()
    if packager == YUM:
        os_release = float(os_version.release)
        if os_version.distro == FEDORA and os_release >= 16:
            sudo('systemctl start httpd.service')
        else:
            sudo('service httpd start')
    elif package == APT:
        sudo('service apache2 start')

@task
def restart():
    """
    Restarts Apache.
    """
    packager = get_packager()
    os_version = get_os_version()
    if packager == YUM:
        os_release = float(os_version.release)
        if os_version.distro == FEDORA and os_release >= 16:
            sudo('systemctl restart httpd.service')
        else:
            sudo('service httpd restart')
    elif package == APT:
        sudo('service apache2 restart')
