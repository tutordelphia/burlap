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
    ALL,
    run,
    put,
    render_to_string,
    get_packager,
    get_os_version,
    find_template,
    ROLE,
    SITE,
    YUM,
    APT,
    LINUX,
    WINDOWS,
    FEDORA,
    UBUNTU,
    QueuedCommand,
    Migratable,
)
from burlap import common

# An Apache-conf file and filename friendly string that uniquely identifies
# your web application.
env.apache_application_name = None

env.apache_log_level = 'warn'

env.apache_auth_basic = False
env.apache_auth_basic_authuserfile_template = '%(apache_docroot)s/.htpasswd_%(apache_site)s'
env.apache_auth_basic_users = [] # [(user,password)]

# If true, activates a rewrite rule that causes domain.com to redirect
# to www.domain.com.
env.apache_enforce_subdomain = True

env.apache_ssl = False
env.apache_ssl_port = 443
env.apache_ssl_chmod = 440
env.apache_listen_ports = [80, 443]

# A list of path patterns that should have HTTPS enforced.
env.apache_ssl_secure_paths = ['/admin/(.*)']

# Defines the expected name of the SSL certificates.
env.apache_ssl_domain_template = '%(apache_domain)s'

env.apache_user = 'www-data'
env.apache_group = 'www-data'
env.apache_wsgi_user = 'www-data'
env.apache_wsgi_group = 'www-data'
env.apache_chmod = 775

env.apache_mods_enabled = ['rewrite', 'wsgi', 'ssl']

# The value of the Apache's ServerName field. Usually should be set
# to the domain.
env.apache_server_name = None

env.apache_server_aliases_template = ''

env.apache_docroot_template = '/usr/local/%(apache_application_name)s'
env.apache_wsgi_dir_template = '/usr/local/%(apache_application_name)s/src/wsgi'
#env.apache_app_log_dir_template = '/var/log/%(apache_application_name)s'
env.apache_django_wsgi_template = '%(apache_wsgi_dir)s/%(apache_site)s.wsgi'
env.apache_ports_template = '%(apache_root)s/ports.conf'
env.apache_ssl_dir_template = '%(apache_root)s/ssl'

env.apache_domain_with_sub_template = ''
env.apache_domain_without_sub_template = ''
env.apache_domain_with_sub = None
env.apache_domain_without_sub = None

env.apache_wsgi_processes = 5

env.apache_wsgi_threads = 15

env.apache_extra_rewrite_rules = ''

env.apache_modevasive_DOSEmailNotify = 'admin@localhost'
env.apache_modevasive_DOSPageInterval = 1 # seconds
env.apache_modevasive_DOSPageCount = 2
env.apache_modevasive_DOSSiteCount = 50
env.apache_modevasive_DOSSiteInterval = 1 # seconds
env.apache_modevasive_DOSBlockingPeriod = 10 # seconds

env.apache_modsecurity_download_url = 'https://github.com/SpiderLabs/owasp-modsecurity-crs/tarball/master'

env.apache_wsgi_python_path_template = '%(apache_docroot)s/.env/lib/python%(pip_python_version)s/site-packages'

# OS specific default settings.
env.apache_specifics = type(env)()
env.apache_specifics[LINUX] = type(env)()
env.apache_specifics[LINUX][FEDORA] = type(env)()
env.apache_specifics[LINUX][FEDORA].root = '/etc/httpd'
env.apache_specifics[LINUX][FEDORA].conf = '/etc/httpd/conf/httpd.conf'
env.apache_specifics[LINUX][FEDORA].sites_available = '/etc/httpd/sites-available'
env.apache_specifics[LINUX][FEDORA].sites_enabled = '/etc/httpd/sites-enabled'
env.apache_specifics[LINUX][FEDORA].log_dir = '/var/log/httpd'
env.apache_specifics[LINUX][FEDORA].pid = '/var/run/httpd/httpd.pid'
env.apache_specifics[LINUX][UBUNTU] = type(env)()
env.apache_specifics[LINUX][UBUNTU].root = '/etc/apache2'
env.apache_specifics[LINUX][UBUNTU].conf = '/etc/apache2/httpd.conf'
env.apache_specifics[LINUX][UBUNTU].sites_available = '/etc/apache2/sites-available'
env.apache_specifics[LINUX][UBUNTU].sites_enabled = '/etc/apache2/sites-enabled'
env.apache_specifics[LINUX][UBUNTU].log_dir = '/var/log/apache2'
env.apache_specifics[LINUX][UBUNTU].pid = '/var/run/apache2/apache2.pid'

env.apache_ssl_certificates = None
env.apache_ssl_certificates_templates = []

# The local and remote relative directory where the SSL certificates are stored.
env.apache_ssl_dir_local = 'ssl'

# An optional segment to insert into the domain, customizable by role.
# Useful for easily keying domain-local.com/domain-dev.com/domain-staging.com.
env.apache_locale = ''

env.apache_sync_sets = {} # {name:[dict(local_path='static/', remote_path='$AWS_BUCKET:/')]}

# This will be appended to the custom Apache configuration file.
env.apache_httpd_conf_append = []

class Apache2(Migratable):
    
    class Meta:
        abstract = True

def set_apache_specifics():
    os_version = common.get_os_version()
    apache_specifics = env.apache_specifics[os_version.type][os_version.distro]
    
#    from pprint import pprint
#    pprint(apache_specifics, indent=4)
    
    env.apache_root = apache_specifics.root
    env.apache_conf = apache_specifics.conf
    env.apache_sites_available = apache_specifics.sites_available
    env.apache_sites_enabled = apache_specifics.sites_enabled
    env.apache_log_dir = apache_specifics.log_dir
    env.apache_pid = apache_specifics.pid
    env.apache_ports = env.apache_ports_template % env
    env.apache_ssl_dir = env.apache_ssl_dir_template % env
    
    return apache_specifics

env.apache_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start httpd.service',
        common.UBUNTU: 'service apache2 start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop httpd.service',
        common.UBUNTU: 'service apache2 stop',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable httpd.service',
        common.UBUNTU: 'chkconfig apache2 off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable httpd.service',
        common.UBUNTU: 'chkconfig apache2 on',
    },
    common.RELOAD:{
        common.FEDORA: 'systemctl reload httpd.service',
        common.UBUNTU: 'service apache2 reload',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl restart httpd.service',
        #common.UBUNTU: 'service apache2 restart',
        # Note, the sleep 5 is necessary because the stop/start appears to
        # happen in the background but gets aborted if Fabric exits before
        # it completes.
        common.UBUNTU: 'service apache2 restart; sleep 3',
    },
}

APACHE2 = 'APACHE2'
APACHE2_MODEVASIVE = 'APACHE2_MODEVASIVE'
APACHE2_MODSECURITY = 'APACHE2_MODSECURITY'
APACHE2_VISITORS = 'APACHE2_VISITORS'

common.required_system_packages[APACHE2] = {
    common.FEDORA: ['httpd'],
    #common.UBUNTU: ['apache2', 'mod_ssl', 'mod_wsgi'],
    (common.UBUNTU, '12.04'): ['apache2', 'libapache2-mod-wsgi'],
}
common.required_system_packages[APACHE2_MODEVASIVE] = {
    (common.UBUNTU, '12.04'): ['libapache2-mod-evasive'],
}
common.required_system_packages[APACHE2_MODEVASIVE] = {
    (common.UBUNTU, '12.04'): ['libapache2-modsecurity'],
}
common.required_system_packages[APACHE2_VISITORS] = {
    (common.UBUNTU, '12.04'): ['visitors'],
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.apache_service_commands[action][os_version.distro]

@task
def enable():
    cmd = get_service_command(common.ENABLE)
    print cmd
    sudo(cmd)

@task
def disable():
    cmd = get_service_command(common.DISABLE)
    print cmd
    sudo(cmd)

@task
def start():
    cmd = get_service_command(common.START)
    print cmd
    sudo(cmd)

@task
def stop():
    cmd = get_service_command(common.STOP)
    print cmd
    sudo(cmd)

@task
def reload():
    cmd = get_service_command(common.RELOAD)
    print cmd
    sudo(cmd)

@task
def restart():
    cmd = get_service_command(common.RESTART)
    print cmd
    sudo(cmd)

@task
def visitors(force=0):
    """
    Generates an Apache access report using the Visitors command line tool.
    Requires the APACHE2_VISITORS service to be enabled for the current host.
    """
    if not int(force):
        assert APACHE2_VISITORS.upper() in env.services or APACHE2_VISITORS.lower() in env.services, \
            'Visitors has not been configured for this host.'
    run('visitors -o text /var/log/apache2/%(apache_application_name)s-access.log* | less' % env)

def check_required():
    for name in ['apache_application_name', 'apache_server_name']:
        assert env[name], 'Missing %s.' % (name,)

def set_apache_site_specifics(site):
    from burlap.dj2 import get_settings
    
    site_data = env.sites[site]
    
    get_settings(site=site)
    
    # Set site specific values.
    env.apache_site = site
    env.update(site_data)
    env.apache_docroot = env.apache_docroot_template % env
    env.apache_wsgi_dir = env.apache_wsgi_dir_template % env
    #env.apache_app_log_dir = env.apache_app_log_dir_template % env
    env.apache_domain = env.apache_domain_template % env
    env.apache_server_name = env.apache_domain
    env.apache_wsgi_python_path = env.apache_wsgi_python_path_template % env
    env.apache_django_wsgi = env.apache_django_wsgi_template % env
    env.apache_server_aliases = env.apache_server_aliases_template % env
    env.apache_ssl_domain = env.apache_ssl_domain_template % env
    env.apache_auth_basic_authuserfile = env.apache_auth_basic_authuserfile_template % env
    env.apache_domain_with_sub = env.apache_domain_with_sub_template % env
    env.apache_domain_without_sub = env.apache_domain_without_sub_template % env
#    print 'site:',env.SITE
#    print 'env.apache_domain_with_sub_template:',env.apache_domain_with_sub_template
#    print 'env.apache_domain_with_sub:',env.apache_domain_with_sub
#    print 'env.apache_enforce_subdomain:',env.apache_enforce_subdomain
#    raw_input('<enter>')

@task
def configure(full=1, site=ALL, delete_old=0):
    """
    Configures Apache to host one or more websites.
    """
    from burlap import service
    
    print 'Configuring Apache...'
    apache_specifics = set_apache_specifics()
    
    if int(delete_old):
        # Delete all existing enabled and available sites.
        sudo('rm -f %(apache_sites_available)s/*' % env)
        sudo('rm -f %(apache_sites_enabled)s/*' % env)
    
    for site, site_data in common.iter_sites(site=site, setter=set_apache_site_specifics):
        print '-'*80
        print 'Site:',site
        
        print 'env.apache_ssl_domain:',env.apache_ssl_domain
        print 'env.apache_ssl_domain_template:',env.apache_ssl_domain_template
        
        fn = common.render_to_file('django.template.wsgi')
        remote_dir = os.path.split(env.apache_django_wsgi)[0]
        sudo('mkdir -p %s' % remote_dir)
        put(local_path=fn, remote_path=env.apache_django_wsgi, use_sudo=True)
        
        if env.apache_ssl:
            env.apache_ssl_certificates = list(iter_certificates())
        
        fn = common.render_to_file('apache_site.template.conf')
        env.apache_site_conf = site+'.conf'
        env.apache_site_conf_fqfn = os.path.join(env.apache_sites_available, env.apache_site_conf)
        put(local_path=fn, remote_path=env.apache_site_conf_fqfn, use_sudo=True)
        
        sudo('a2ensite %(apache_site_conf)s' % env)
    
    if service.is_selected(APACHE2_MODEVASIVE):
        configure_modevasive()
        
    if service.is_selected(APACHE2_MODSECURITY):
        configure_modsecurity()
    
    for mod_enabled in env.apache_mods_enabled:
        env.apache_mod_enabled = mod_enabled
        sudo('a2enmod %(apache_mod_enabled)s' % env)
        
    if int(full):
        # Write master Apache configuration file.
        fn = common.render_to_file('apache_httpd.template.conf')
        put(local_path=fn, remote_path=env.apache_conf, use_sudo=True)
        
        # Write Apache listening ports configuration.
        fn = common.render_to_file('apache_ports.template.conf')
        put(local_path=fn, remote_path=env.apache_ports, use_sudo=True)
        
    #sudo('mkdir -p %(apache_app_log_dir)s' % env)
    #sudo('chown -R %(apache_user)s:%(apache_group)s %(apache_app_log_dir)s' % env)
#    sudo('mkdir -p %(apache_log_dir)s' % env)
#    sudo('chown -R %(apache_user)s:%(apache_group)s %(apache_log_dir)s' % env)
    sudo('chown -R %(apache_user)s:%(apache_group)s %(apache_root)s' % env)
#    sudo('chown -R %(apache_user)s:%(apache_group)s %(apache_docroot)s' % env)
#    sudo('chown -R %(apache_user)s:%(apache_group)s %(apache_pid)s' % env)

    #restart()#break apache? run separately?

@task
def configure_modsecurity():
    
    env.apache_mods_enabled.append('mod-security')
    env.apache_mods_enabled.append('headers')
    
    # Write modsecurity.conf.
    fn = common.render_to_file('apache_modsecurity.template.conf')
    put(local_path=fn, remote_path='/etc/modsecurity/modsecurity.conf', use_sudo=True)
    
    # Write OWASP rules.
    env.apache_modsecurity_download_filename = '/tmp/owasp-modsecurity-crs.tar.gz'
    sudo('cd /tmp; wget --output-document=%(apache_modsecurity_download_filename)s %(apache_modsecurity_download_url)s' % env)
    env.apache_modsecurity_download_top = sudo("cd /tmp; tar tzf %(apache_modsecurity_download_filename)s | sed -e 's@/.*@@' | uniq" % env)
    sudo('cd /tmp; tar -zxvf %(apache_modsecurity_download_filename)s' % env)
    sudo('cd /tmp; cp -R %(apache_modsecurity_download_top)s/* /etc/modsecurity/' % env)
    sudo('mv /etc/modsecurity/modsecurity_crs_10_setup.conf.example  /etc/modsecurity/modsecurity_crs_10_setup.conf' % env)
    
    sudo('rm -f /etc/modsecurity/activated_rules/*')
    sudo('cd /etc/modsecurity/base_rules; for f in * ; do ln -s /etc/modsecurity/base_rules/$f /etc/modsecurity/activated_rules/$f ; done')
    sudo('cd /etc/modsecurity/optional_rules; for f in * ; do ln -s /etc/modsecurity/optional_rules/$f /etc/modsecurity/activated_rules/$f ; done')
    
    env.apache_httpd_conf_append.append('Include "/etc/modsecurity/activated_rules/*.conf"')

@task
def configure_modevasive():
    
    env.apache_mods_enabled.append('mod-evasive')
    
    # Write modsecurity.conf.
    fn = common.render_to_file('apache_modevasive.template.conf')
    put(local_path=fn, remote_path='/etc/apache2/mods-available/mod-evasive.conf', use_sudo=True)
    
def iter_certificates():
    print 'apache_ssl_domain:',env.apache_ssl_domain
    for cert_type, cert_file_template in env.apache_ssl_certificates_templates:
        print 'cert_type, cert_file_template:',cert_type, cert_file_template
        _local_cert_file = os.path.join(env.apache_ssl_dir_local, cert_file_template % env)
        local_cert_file = find_template(_local_cert_file)
        assert local_cert_file, 'Unable to find local certificate file: %s' % (_local_cert_file,)
        remote_cert_file = os.path.join(env.apache_ssl_dir, cert_file_template % env)
        yield cert_type, local_cert_file, remote_cert_file

@task
def install_ssl(site=ALL, dryrun=0):
    apache_specifics = set_apache_specifics()
    
    for site, site_data in common.iter_sites(site=site, setter=set_apache_site_specifics):
#        print 'site:',site
#        continue
        
        site_secure = site+'_secure'
        if site_secure not in env.sites:
            continue
        set_apache_site_specifics(site_secure)
    
        sudo('mkdir -p %(apache_ssl_dir)s' % env)
        
        if env.apache_ssl:
            for cert_type, local_cert_file, remote_cert_file in iter_certificates():
                print '='*80
                print 'Installing certificate %s...' % (remote_cert_file,)
                if not int(dryrun):
                    put(
                        local_path=local_cert_file,
                        remote_path=remote_cert_file, use_sudo=True)
    
    sudo('mkdir -p %(apache_ssl_dir)s' % env)
    sudo('chown -R %(apache_user)s:%(apache_group)s %(apache_ssl_dir)s' % env)
    sudo('chmod -R %(apache_ssl_chmod)s %(apache_ssl_dir)s' % env)
    
#@task
#def unconfigure():
#    """
#    Removes all custom configurations for Apache hosted websites.
#    """
#    check_required()
#    print 'Un-configuring Apache...'
#    os_version = get_os_version()
#    env.apache_root = env.apache_roots[os_type][os_distro]
#    with settings(warn_only=True):
#        sudo("[ -f %(apache_root)s/sites-enabled/%(apache_server_name)s ] && rm -f %(apache_root)s/sites-enabled/%(apache_server_name)s" % env)
#        sudo("[ -f %(apache_root)s/sites-available/%(apache_server_name)s ] && rm -f %(apache_root)s/sites-available/%(apache_server_name)s" % env)

@task
def install_auth_basic_user_file(site=None):
    """
    Installs users for basic httpd auth.
    """
    apache_specifics = set_apache_specifics()
    
    for site, site_data in common.iter_sites(site=site, setter=set_apache_site_specifics):
        print '~'*80
        print 'Site:',site
        #env.update(env_default)
        #env.update(env.sites[site])
        #set_apache_site_specifics(site)
        
        print 'env.apache_auth_basic:',env.apache_auth_basic
        if not env.apache_auth_basic:
            continue
        
        #assert env.apache_auth_basic, 'This site is not configured for Apache basic authenticated.'
        assert env.apache_auth_basic_users, 'No apache auth users specified.'
        for username,password in env.apache_auth_basic_users:
            env.apache_auth_basic_username = username
            env.apache_auth_basic_password = password
            if files.exists(env.apache_auth_basic_authuserfile):
                sudo('htpasswd -b %(apache_auth_basic_authuserfile)s %(apache_auth_basic_username)s %(apache_auth_basic_password)s' % env)
            else:
                sudo('htpasswd -b -c %(apache_auth_basic_authuserfile)s %(apache_auth_basic_username)s %(apache_auth_basic_password)s' % env)

@task
def sync_media(sync_set=None, dryrun=0):
    """
    Uploads select media to an Apache accessible directory.
    """
    from burlap.dj import render_remote_paths
    apache_specifics = set_apache_specifics()
    
    render_remote_paths()
    
    site_data = env.sites[env.SITE]
    env.update(site_data)
    
    sync_sets = env.apache_sync_sets
    if sync_set:
        sync_sets = [sync_set]
    
    for sync_set in sync_sets:
        for paths in env.apache_sync_sets[sync_set]:
            print 'paths:',paths
            env.apache_sync_local_path = os.path.abspath(paths['local_path'] % env)
            if paths['local_path'].endswith('/') and not env.apache_sync_local_path.endswith('/'):
                env.apache_sync_local_path += '/'
            env.apache_sync_remote_path = paths['remote_path'] % env
            
            print 'Syncing %s to %s...' % (env.apache_sync_local_path, env.apache_sync_remote_path)
            
            env.apache_tmp_chmod = paths.get('chmod',  env.apache_chmod)
            #with settings(warn_only=True):
            sudo('mkdir -p %(apache_sync_remote_path)s' % env, user=env.apache_user)
            sudo('chmod -R %(apache_tmp_chmod)s %(apache_sync_remote_path)s' % env, user=env.apache_user)
            cmd = ('rsync -rvz --progress --recursive --no-p --no-g --rsh "ssh -i %(key_filename)s" %(apache_sync_local_path)s %(user)s@%(host_string)s:%(apache_sync_remote_path)s') % env
#            print '!'*80
#            print cmd
            if not int(dryrun):
                local(cmd)
            sudo('chown -R %(apache_user)s:%(apache_group)s %(apache_sync_remote_path)s' % env)

@task
def configure_all():
    return configure(full=1, site=ALL, delete_old=1)

@task
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = common.get_component_settings(APACHE2)
    #TODO:hash media names and content
    return data

def compare_manifest(old):
    """
    Compares the current settings to previous manifests and returns the methods
    to be executed to make the target match current settings.
    """
    old = old or {}
    methods = []
    pre = ['user','packages']
    #TODO:sites and server conf
    #TODO:basic auth
    #TODO:ssl certs
    #TODO:sync_media
#    new = common.get_component_settings(CRON)
#    has_diffs = common.check_settings_for_differences(old, new, as_bool=True)
#    if has_diffs:
#        methods.append(QueuedCommand('cron.deploy_all'))
    return methods

# These tasks are run when the service.configure task is run.
common.service_configurators[APACHE2] = [
    configure_all,
    lambda: install_auth_basic_user_file(site=ALL),
    lambda: install_ssl(site=ALL),
    sync_media,
]

# These tasks are run when the service.deploy task is run.
#common.service_deployers[APACHE2] = [configure]

# These tasks are run when the service.restart task is run.
common.service_restarters[APACHE2] = [reload]
common.service_stoppers[APACHE2] = [stop]

# Apache doesn't strictly need to be stopped, as reload can cleanly reload all
# configs without much noticable downtime.
# A more legitmate concern is how allowing users to browse the site during
# a deployment will effect other components, and how we want to avoid any
# negative effects system-wide.
# e.g. If Django ORM models have been changed but the migrations have not yet
# run, we don't want any part of site accessible, since the user might
# encounter errors due to a mismatch between the code and database schema or
# submit bad data to the database. However, that case is a system-wide concern
# so we'd want to ideally switch all Apache instances to maintenance mode,
# showing a clean static "site is down for maintenance" message.
common.service_pre_deployers[APACHE2] = []

common.service_post_deployers[APACHE2] = [reload]

common.manifest_recorder[APACHE2] = record_manifest
common.manifest_comparer[APACHE2] = compare_manifest
