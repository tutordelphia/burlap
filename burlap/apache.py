import os
import sys
import datetime
from pprint import pprint

from fabric.api import (
    env,
    require,
    settings,
    cd,
)
from fabric.contrib import files

from burlap.common import (
    ALL,
    run_or_dryrun,
    put_or_dryrun,
    local_or_dryrun,
    sudo_or_dryrun,
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
)
from burlap.decorators import task_or_dryrun
from burlap import common

# An Apache-conf file and filename friendly string that uniquely identifies
# your web application.
env.apache_application_name = None

env.apache_error_log = '/var/log/apache2/error.log'
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
env.apache_ssl_secure_paths_enforce = True
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

env.apache_domain_redirect_templates = [] # [(wrong_domain,right_domain)]
env.apache_domain_redirects = [] # [(wrong_domain,right_domain)]

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

env._apache_settings = None

ignore_keys = [
    'apache_site_conf_fqfn',
    'apache_domain_without_sub',
    'apache_server_name',
    'apache_domain_with_sub',
    'apache_site_conf',
    'apache_mod_enabled',
    'apache_tmp_chmod',
    'apache_sync_local_path',
    'apache_sync_remote_path',
    'apache_site',
    'apache_auth_basic_authuserfile',
    'apache_domain',
    'apache_ssl_domain',
    'apache_domain_without_sub_template',
    'apache_django_wsgi',
    'apache_domain_template',
    'apache_server_aliases_template',
    'apache_enforce_subdomain',
    'apache_domain_with_sub_template',
    'apache_server_aliases',
]

def get_apache_settings():
    if not env._apache_settings:
        set_apache_specifics()
    return env._apache_settings

def set_apache_specifics():
    
    if not env._apache_settings:
        env._apache_settings = type(env)()
        for _k, _v in env.iteritems():
            if _k.startswith('apache_'):
                env._apache_settings[_k] = _v
    
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

APACHE = 'APACHE'
APACHE2 = 'APACHE2'
APACHE2_MODEVASIVE = 'APACHE2_MODEVASIVE'
APACHE2_MODSECURITY = 'APACHE2_MODSECURITY'
APACHE2_VISITORS = 'APACHE2_VISITORS'
APACHE2_MEDIA = 'APACHE2_MEDIA'

common.required_system_packages[APACHE2] = {
    common.FEDORA: ['httpd'],
    #common.UBUNTU: ['apache2', 'mod_ssl', 'mod_wsgi'],
    (common.UBUNTU, '12.04'): ['apache2', 'libapache2-mod-wsgi'],
    (common.UBUNTU, '14.04'): ['apache2', 'libapache2-mod-wsgi', 'apache2-utils'],
}
common.required_system_packages[APACHE2_MODEVASIVE] = {
    (common.UBUNTU, '12.04'): ['libapache2-mod-evasive'],
    (common.UBUNTU, '14.04'): ['libapache2-mod-evasive'],
}
common.required_system_packages[APACHE2_MODEVASIVE] = {
    (common.UBUNTU, '12.04'): ['libapache2-modsecurity'],
    (common.UBUNTU, '14.04'): ['libapache2-modsecurity'],
}
common.required_system_packages[APACHE2_VISITORS] = {
    (common.UBUNTU, '12.04'): ['visitors'],
    (common.UBUNTU, '14.04'): ['visitors'],
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.apache_service_commands[action][os_version.distro]

@task_or_dryrun
def enable():
    cmd = get_service_command(common.ENABLE)
    sudo_or_dryrun(cmd)

@task_or_dryrun
def disable():
    cmd = get_service_command(common.DISABLE)
    sudo_or_dryrun(cmd)

@task_or_dryrun
def start():
    cmd = get_service_command(common.START)
    sudo_or_dryrun(cmd)

@task_or_dryrun
def stop():
    cmd = get_service_command(common.STOP)
    sudo_or_dryrun(cmd)

@task_or_dryrun
def reload():
    cmd = get_service_command(common.RELOAD)
    sudo_or_dryrun(cmd)

@task_or_dryrun
def restart():
    cmd = get_service_command(common.RESTART)
    sudo_or_dryrun(cmd)

@task_or_dryrun
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
    from burlap.dj import get_settings
    
    site_data = env.sites[site]
    
#    print 'env.django_settings_module_template0:',env.django_settings_module_template
#    print 'env.django_settings_module0:',env.django_settings_module
    
    get_settings(site=site)
    
#    print 'env.django_settings_module_template1:',env.django_settings_module_template
#    print 'env.django_settings_module1:',env.django_settings_module
    
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
    env.apache_django_wsgi = env.apache_django_wsgi.replace('-', '_')
    env.apache_server_aliases = env.apache_server_aliases_template % env
    env.apache_ssl_domain = env.apache_ssl_domain_template % env
    env.apache_auth_basic_authuserfile = env.apache_auth_basic_authuserfile_template % env
    env.apache_domain_with_sub = env.apache_domain_with_sub_template % env
    env.apache_domain_without_sub = env.apache_domain_without_sub_template % env
    
    env.apache_domain_redirects = []
    for _wrong, _right in env.apache_domain_redirect_templates:
        env.apache_domain_redirects.append((_wrong % env, _right % env))
    
#    print 'site:',env.SITE
#    print 'env.apache_domain_with_sub_template:',env.apache_domain_with_sub_template
#    print 'env.apache_domain_with_sub:',env.apache_domain_with_sub
#    print 'env.apache_enforce_subdomain:',env.apache_enforce_subdomain
#    raw_input('<enter>')

@task_or_dryrun
def configure(full=1, site=None, delete_old=0, verbose=0):
    """
    Configures Apache to host one or more websites.
    """
    from burlap.common import get_current_hostname
    from burlap import service
    
    print>>sys.stderr, 'Configuring Apache...'
    
    verbose = int(verbose)
    
    site = site or env.SITE
    
    apache_specifics = set_apache_specifics()
    hostname = get_current_hostname()
    target_sites = env.available_sites_by_host.get(hostname, None)
    
    if int(delete_old):
        # Delete all existing enabled and available sites.
        cmd = 'rm -f %(apache_sites_available)s/*' % env
        sudo_or_dryrun(cmd)
        cmd = 'rm -f %(apache_sites_enabled)s/*' % env
        sudo_or_dryrun(cmd)
    
    for site, site_data in common.iter_sites(site=site, setter=set_apache_site_specifics):
        print>>sys.stderr, '-'*80
        print>>sys.stderr, 'Site:',site
        print>>sys.stderr, '-'*80
        
        # Only load site configurations that are allowed for this host.
        if target_sites is None:
            pass
        else:
            assert isinstance(target_sites, (tuple, list))
            if site not in target_sites:
                continue
                
        print>>sys.stderr, 'env.apache_ssl_domain:',env.apache_ssl_domain
        print>>sys.stderr, 'env.apache_ssl_domain_template:',env.apache_ssl_domain_template
        print>>sys.stderr, 'env.django_settings_module:',env.django_settings_module
#        raw_input('enter')
        fn = common.render_to_file('django.template.wsgi', verbose=verbose)
        remote_dir = os.path.split(env.apache_django_wsgi)[0]
        cmd = 'mkdir -p %s' % remote_dir
        sudo_or_dryrun(cmd)
        
        print>>sys.stderr, fn
        put_or_dryrun(local_path=fn, remote_path=env.apache_django_wsgi, use_sudo=True)
        
        if env.apache_ssl:
            env.apache_ssl_certificates = list(iter_certificates())
        
        fn = common.render_to_file('apache_site.template.conf', verbose=verbose)
        env.apache_site_conf = site+'.conf'
        env.apache_site_conf_fqfn = os.path.join(env.apache_sites_available, env.apache_site_conf)
        put_or_dryrun(local_path=fn, remote_path=env.apache_site_conf_fqfn, use_sudo=True)
        
        cmd = 'a2ensite %(apache_site_conf)s' % env
        sudo_or_dryrun(cmd)
    
    if service.is_selected(APACHE2_MODEVASIVE):
        configure_modevasive()
        
    if service.is_selected(APACHE2_MODSECURITY):
        configure_modsecurity()
    
    for mod_enabled in env.apache_mods_enabled:
        env.apache_mod_enabled = mod_enabled
        cmd = 'a2enmod %(apache_mod_enabled)s' % env
        sudo_or_dryrun(cmd)
        
    if int(full):
        # Write master Apache configuration file.
        fn = common.render_to_file('apache_httpd.template.conf', verbose=verbose)
        put_or_dryrun(local_path=fn, remote_path=env.apache_conf, use_sudo=True)
        
        # Write Apache listening ports configuration.
        fn = common.render_to_file('apache_ports.template.conf', verbose=verbose)
        put_or_dryrun(local_path=fn, remote_path=env.apache_ports, use_sudo=True)
        
    #sudo_or_dryrun('mkdir -p %(apache_app_log_dir)s' % env)
    #sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_app_log_dir)s' % env)
#    sudo_or_dryrun('mkdir -p %(apache_log_dir)s' % env)
#    sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_log_dir)s' % env)
    cmd = 'chown -R %(apache_user)s:%(apache_group)s %(apache_root)s' % env
    sudo_or_dryrun(cmd)
#    sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_docroot)s' % env)
#    sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_pid)s' % env)

    #restart()#break apache? run separately?

@task_or_dryrun
def configure_modsecurity():
    
    env.apache_mods_enabled.append('mod-security')
    env.apache_mods_enabled.append('headers')
    
    # Write modsecurity.conf.
    fn = common.render_to_file('apache_modsecurity.template.conf')
    put_or_dryrun(local_path=fn, remote_path='/etc/modsecurity/modsecurity.conf', use_sudo=True)
    
    # Write OWASP rules.
    env.apache_modsecurity_download_filename = '/tmp/owasp-modsecurity-crs.tar.gz'
    sudo_or_dryrun('cd /tmp; wget --output-document=%(apache_modsecurity_download_filename)s %(apache_modsecurity_download_url)s' % env)
    env.apache_modsecurity_download_top = sudo_or_dryrun("cd /tmp; tar tzf %(apache_modsecurity_download_filename)s | sed -e 's@/.*@@' | uniq" % env)
    sudo_or_dryrun('cd /tmp; tar -zxvf %(apache_modsecurity_download_filename)s' % env)
    sudo_or_dryrun('cd /tmp; cp -R %(apache_modsecurity_download_top)s/* /etc/modsecurity/' % env)
    sudo_or_dryrun('mv /etc/modsecurity/modsecurity_crs_10_setup.conf.example  /etc/modsecurity/modsecurity_crs_10_setup.conf' % env)
    
    sudo_or_dryrun('rm -f /etc/modsecurity/activated_rules/*')
    sudo_or_dryrun('cd /etc/modsecurity/base_rules; for f in * ; do ln -s /etc/modsecurity/base_rules/$f /etc/modsecurity/activated_rules/$f ; done')
    sudo_or_dryrun('cd /etc/modsecurity/optional_rules; for f in * ; do ln -s /etc/modsecurity/optional_rules/$f /etc/modsecurity/activated_rules/$f ; done')
    
    env.apache_httpd_conf_append.append('Include "/etc/modsecurity/activated_rules/*.conf"')

@task_or_dryrun
def configure_modevasive():
    
    env.apache_mods_enabled.append('mod-evasive')
    
    # Write modsecurity.conf.
    fn = common.render_to_file('apache_modevasive.template.conf')
    put(local_path=fn, remote_path='/etc/apache2/mods-available/mod-evasive.conf', use_sudo=True)
    
def iter_certificates():
    print>>sys.stderr, 'apache_ssl_domain:',env.apache_ssl_domain
    for cert_type, cert_file_template in env.apache_ssl_certificates_templates:
        print>>sys.stderr, 'cert_type, cert_file_template:',cert_type, cert_file_template
        _local_cert_file = os.path.join(env.apache_ssl_dir_local, cert_file_template % env)
        local_cert_file = find_template(_local_cert_file)
        assert local_cert_file, 'Unable to find local certificate file: %s' % (_local_cert_file,)
        remote_cert_file = os.path.join(env.apache_ssl_dir, cert_file_template % env)
        yield cert_type, local_cert_file, remote_cert_file

@task_or_dryrun
def install_ssl(site=ALL):
    apache_specifics = set_apache_specifics()
    
    for site, site_data in common.iter_sites(site=site, setter=set_apache_site_specifics):
#        print 'site:',site
#        continue
        
        site_secure = site+'_secure'
        if site_secure not in env.sites:
            continue
        set_apache_site_specifics(site_secure)
    
        sudo_or_dryrun('mkdir -p %(apache_ssl_dir)s' % env)
        
        if env.apache_ssl:
            for cert_type, local_cert_file, remote_cert_file in iter_certificates():
                print '='*80
                print 'Installing certificate %s...' % (remote_cert_file,)
                put_or_dryrun(
                    local_path=local_cert_file,
                    remote_path=remote_cert_file, use_sudo=True)
    
    sudo_or_dryrun('mkdir -p %(apache_ssl_dir)s' % env)
    sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_ssl_dir)s' % env)
    sudo_or_dryrun('chmod -R %(apache_ssl_chmod)s %(apache_ssl_dir)s' % env)
    
#@task_or_dryrun
#def unconfigure():
#    """
#    Removes all custom configurations for Apache hosted websites.
#    """
#    check_required()
#    print 'Un-configuring Apache...'
#    os_version = get_os_version()
#    env.apache_root = env.apache_roots[os_type][os_distro]
#    with settings(warn_only=True):
#        sudo_or_dryrun("[ -f %(apache_root)s/sites-enabled/%(apache_server_name)s ] && rm -f %(apache_root)s/sites-enabled/%(apache_server_name)s" % env)
#        sudo_or_dryrun("[ -f %(apache_root)s/sites-available/%(apache_server_name)s ] && rm -f %(apache_root)s/sites-available/%(apache_server_name)s" % env)

@task_or_dryrun
def install_auth_basic_user_file(site=None):
    """
    Installs users for basic httpd auth.
    """
    print>>sys.stderr, 'env.apache_auth_basic0:',env.apache_auth_basic
    apache_specifics = set_apache_specifics()
    print>>sys.stderr, 'env.apache_auth_basic1:',env.apache_auth_basic
    
    for site, site_data in common.iter_sites(site=site, setter=set_apache_site_specifics):
        print>>sys.stderr, '~'*80
        print>>sys.stderr, 'Site:',site
        #env.update(env_default)
        #env.update(env.sites[site])
        #set_apache_site_specifics(site)
        
        print>>sys.stderr, 'env.apache_auth_basic:',env.apache_auth_basic
        if not env.apache_auth_basic:
            continue
        
        #assert env.apache_auth_basic, 'This site is not configured for Apache basic authenticated.'
        assert env.apache_auth_basic_users, 'No apache auth users specified.'
        for username,password in env.apache_auth_basic_users:
            env.apache_auth_basic_username = username
            env.apache_auth_basic_password = password
            if files.exists(env.apache_auth_basic_authuserfile):
                sudo_or_dryrun('htpasswd -b %(apache_auth_basic_authuserfile)s %(apache_auth_basic_username)s %(apache_auth_basic_password)s' % env)
            else:
                sudo_or_dryrun('htpasswd -b -c %(apache_auth_basic_authuserfile)s %(apache_auth_basic_username)s %(apache_auth_basic_password)s' % env)

@task_or_dryrun
def install_auth_basic_user_file_all():
    install_auth_basic_user_file(site='all')
    
@task_or_dryrun
def sync_media(sync_set=None, clean=0, iter_local_paths=0):
    """
    Uploads select media to an Apache accessible directory.
    """
    from burlap.dj import render_remote_paths
    apache_specifics = set_apache_specifics()
    
    render_remote_paths()
    
    clean = int(clean)
    site_data = env.sites[env.SITE]
    env.update(site_data)
    
    sync_sets = env.apache_sync_sets
    if sync_set:
        sync_sets = [sync_set]
    
    ret_paths = []
    for sync_set in sync_sets:
        for paths in env.apache_sync_sets[sync_set]:
            #print 'paths:',paths
            env.apache_sync_local_path = os.path.abspath(paths['local_path'] % env)
            if paths['local_path'].endswith('/') and not env.apache_sync_local_path.endswith('/'):
                env.apache_sync_local_path += '/'
                
            if iter_local_paths:
                ret_paths.append(env.apache_sync_local_path)
                continue
                
            env.apache_sync_remote_path = paths['remote_path'] % env
            
            if clean:
                sudo_or_dryrun('rm -Rf %(apache_sync_remote_path)s' % env) 
            
            print 'Syncing %s to %s...' % (env.apache_sync_local_path, env.apache_sync_remote_path)
            
            env.apache_tmp_chmod = paths.get('chmod',  env.apache_chmod)
            #with settings(warn_only=True):
            sudo_or_dryrun('mkdir -p %(apache_sync_remote_path)s' % env, user=env.apache_user)
            sudo_or_dryrun('chmod -R %(apache_tmp_chmod)s %(apache_sync_remote_path)s' % env, user=env.apache_user)
            cmd = ('rsync -rvz --progress --recursive --no-p --no-g --rsh "ssh -o StrictHostKeyChecking=no -i %(key_filename)s" %(apache_sync_local_path)s %(user)s@%(host_string)s:%(apache_sync_remote_path)s') % env
#            print '!'*80
#            print cmd
            local_or_dryrun(cmd)
            sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_sync_remote_path)s' % env)
            
    if iter_local_paths:
        return ret_paths

@task_or_dryrun
def view_error_log():
    run_or_dryrun('tail -f %(apache_error_log)s' % env)
    
@task_or_dryrun
def configure_all():
    """
    Installs the Apache site configurations for both secure and non-secure
    sites.
    """
    return configure(full=1, site=ALL, delete_old=1)

@task_or_dryrun
def record_manifest(verbose=0):
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = get_apache_settings()
    if int(verbose):
        pprint(data, indent=4)
    return data

@task_or_dryrun
def record_manifest_sync_media(verbose=0):
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = 0
    for path in sync_media(iter_local_paths=1):
        data = min(data, common.get_last_modified_timestamp(path) or data)
    #TODO:hash media names and content
    if int(verbose):
        print data
    return data

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
common.manifest_recorder[APACHE2_MEDIA] = record_manifest_sync_media

common.add_deployer(APACHE2, 'apache.configure_all', before=['packager', 'user'])
common.add_deployer(APACHE2_MEDIA, 'apache.sync_media', before=['packager', APACHE, APACHE2, 'pip', 'tarball'])
