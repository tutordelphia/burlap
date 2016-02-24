import os
import sys
import datetime
import warnings
from pprint import pprint

from fabric.api import settings

from burlap.constants import *
from burlap import Satchel, ServiceSatchel

#TODO:deprecated, removed
ignore_keys = [
    # These are templated environment variables, so we should ignore them when
    # saving a snapshot of the apache settings, since they'll be host-specific.
    'apache_docroot',
    'apache_wsgi_dir',
    'apache_domain',
    'apache_wsgi_python_path',
    'apache_django_wsgi',
    'apache_server_aliases',
    'apache_ssl_domain',
    'apache_auth_basic_authuserfile',
    'apache_domain_with_sub',
    'apache_domain_without_sub',
    'apache_ports',
    'apache_ssl_dir',
    
    #TODO:remove? these are possibly distro-specific?
#     'apache_root',
#     'apache_conf',
#     'apache_sites_available',
#     'apache_sites_enabled',
#     'apache_log_dir',
#     'apache_pid',
]

#DEPRECATED
def set_apache_site_specifics(site):
    from burlap.common import env
    from burlap.dj import get_settings
    
    warnings.warn("Use ApacheSatchel instead.", DeprecationWarning)
    
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

class ApacheSatchel(ServiceSatchel):
    
    name = 'apache'
    
    ## Service options.
    
    #ignore_errors = True
    
    post_deploy_command = 'reload'
    
    required_system_packages = {
        FEDORA: ['httpd'],
        UBUNTU: ['apache2'],
        (UBUNTU, '12.04'): ['apache2', 'libapache2-mod-wsgi'],
        (UBUNTU, '14.04'): ['apache2', 'libapache2-mod-wsgi', 'apache2-utils'],
    }
    
    tasks = (
        'configure',
        'configure_site',
        'install_auth_basic_user_file',
        'install_auth_basic_user_file_all',
        'view_error_log',
        'install_ssl',
        'visitors',
        'optimize_wsgi_processes',
        'enable_site',
        'disable_site',
    )
    
    def set_defaults(self):
        
        self.env.service_commands = {
#             START:{
#                 UBUNTU: 'service network-manager start',
#             },
#             STOP:{
#                 UBUNTU: 'service network-manager stop',
#             },
#             DISABLE:{
#                 UBUNTU: 'chkconfig network-manager off',
#             },
#             ENABLE:{
#                 UBUNTU: 'chkconfig network-manager on',
#             },
#             RESTART:{
#                 UBUNTU: 'service network-manager restart',
#             },
#             STATUS:{
#                 UBUNTU: 'service network-manager status',
#             },
            START:{
                FEDORA: 'systemctl start httpd.service',
                UBUNTU: 'service apache2 start',
            },
            STOP:{
                FEDORA: 'systemctl stop httpd.service',
                UBUNTU: 'service apache2 stop',
            },
            DISABLE:{
                FEDORA: 'systemctl disable httpd.service',
                UBUNTU: 'chkconfig apache2 off',
                (UBUNTU, '14.04'): 'update-rc.d -f apache2 remove',
            },
            ENABLE:{
                FEDORA: 'systemctl enable httpd.service',
                UBUNTU: 'chkconfig apache2 on',
                (UBUNTU, '14.04'): 'update-rc.d apache2 defaults',
            },
            RELOAD:{
                FEDORA: 'systemctl reload httpd.service',
                UBUNTU: 'service apache2 reload',
            },
            RESTART:{
                FEDORA: 'systemctl restart httpd.service',
                #UBUNTU: 'service apache2 restart',
                # Note, the sleep 5 is necessary because the stop/start appears to
                # happen in the background but gets aborted if Fabric exits before
                # it completes.
                UBUNTU: 'service apache2 restart; sleep 3',
            },
        }
        
        # An Apache-conf file and filename friendly string that uniquely identifies
        # your web application.
        self.env.application_name = None
        
        # The Jinja-formatted template file used to render site configurations.
        self.env.site_template = 'apache/apache_site.template.conf'
        
        self.env.error_log = '/var/log/apache2/error.log'
        self.env.log_level = 'warn'
        
        self.env.auth_basic = False
        self.env.auth_basic_authuserfile_template = '%(apache_docroot)s/.htpasswd_%(apache_site)s'
        self.env.auth_basic_users = [] # [(user,password)]
        
        # If true, activates a rewrite rule that causes domain.com to redirect
        # to www.domain.com.
        self.env.enforce_subdomain = True
        
        self.env.ssl = False
        self.env.ssl_port = 443
        self.env.ssl_chmod = 440
        self.env.listen_ports = [80, 443]
        
        # A list of path patterns that should have HTTPS enforced.
        self.env.ssl_secure_paths_enforce = True
        self.env.ssl_secure_paths = ['/admin/(.*)']
        
        # Defines the expected name of the SSL certificates.
        self.env.domain_template = 'mydomain'
        self.env.ssl_domain_template = '%(apache_domain)s'
        
        self.env.user = 'www-data'
        self.env.group = 'www-data'
        self.env.wsgi_user = 'www-data'
        self.env.wsgi_group = 'www-data'
        self.env.chmod = 775
        
        self.env.mods_enabled = ['rewrite', 'wsgi', 'ssl']
        
        # The value of the Apache's ServerName field. Usually should be set
        # to the domain.
        self.env.server_name = None
        
        self.env.server_aliases_template = ''
        
        self.env.docroot_template = '/usr/local/%(apache_application_name)s'
        self.env.wsgi_dir_template = '/usr/local/%(apache_application_name)s/src/wsgi'
        self.env.django_wsgi_template = '%(apache_wsgi_dir)s/%(apache_site)s.wsgi'
        self.env.ports_template = '%(apache_root)s/ports.conf'
        self.env.ssl_dir_template = '%(apache_root)s/ssl'
        
        self.env.domain_with_sub_template = ''
        self.env.domain_without_sub_template = ''
        self.env.domain_with_sub = None
        self.env.domain_without_sub = None
        
        self.env.wsgi_server_memory_gb = 8
        self.env.wsgi_processes = 5
        self.env.wsgi_threads = 15
        
        self.env.domain_redirect_templates = [] # [(wrong_domain,right_domain)]
        self.env.domain_redirects = [] # [(wrong_domain,right_domain)]
        
        self.env.extra_rewrite_rules = ''
        
        self.env.modevasive_DOSEmailNotify = 'admin@localhost'
        self.env.modevasive_DOSPageInterval = 1 # seconds
        self.env.modevasive_DOSPageCount = 2
        self.env.modevasive_DOSSiteCount = 50
        self.env.modevasive_DOSSiteInterval = 1 # seconds
        self.env.modevasive_DOSBlockingPeriod = 10 # seconds
        
        self.env.modsecurity_download_url = 'https://github.com/SpiderLabs/owasp-modsecurity-crs/tarball/master'
        
        self.env.wsgi_python_path_template = '%(apache_docroot)s/.env/lib/python%(pip_python_version)s/site-packages'
        
        # OS specific default settings.
        self.env.specifics = type(self.genv)()
        self.env.specifics[LINUX] = type(self.genv)()
        
        self.env.specifics[LINUX][FEDORA] = type(self.genv)()
        self.env.specifics[LINUX][FEDORA].root = '/etc/httpd'
        self.env.specifics[LINUX][FEDORA].conf = '/etc/httpd/conf/httpd.conf'
        self.env.specifics[LINUX][FEDORA].sites_available = '/etc/httpd/sites-available'
        self.env.specifics[LINUX][FEDORA].sites_enabled = '/etc/httpd/sites-enabled'
        self.env.specifics[LINUX][FEDORA].log_dir = '/var/log/httpd'
        self.env.specifics[LINUX][FEDORA].pid = '/var/run/httpd/httpd.pid'
        
        self.env.specifics[LINUX][UBUNTU] = type(self.genv)()
        self.env.specifics[LINUX][UBUNTU].root = '/etc/apache2'
        self.env.specifics[LINUX][UBUNTU].conf = '/etc/apache2/httpd.conf'
        self.env.specifics[LINUX][UBUNTU].sites_available = '/etc/apache2/sites-available'
        self.env.specifics[LINUX][UBUNTU].sites_enabled = '/etc/apache2/sites-enabled'
        self.env.specifics[LINUX][UBUNTU].log_dir = '/var/log/apache2'
        self.env.specifics[LINUX][UBUNTU].pid = '/var/run/apache2/apache2.pid'
        
        self.env.ssl_certificates = None
        self.env.ssl_certificates_templates = []
        
        # The local and remote relative directory where the SSL certificates are stored.
        self.env.ssl_dir_local = 'ssl'
        
        # An optional segment to insert into the domain, customizable by role.
        # Useful for easily keying domain-local.com/domain-dev.com/domain-staging.com.
        self.env.locale = ''
        
        self.env.sync_sets = {} # {name:[dict(local_path='static/', remote_path='$AWS_BUCKET:/')]}
        
        # This will be appended to the custom Apache configuration file.
        self.env.httpd_conf_append = []

    def get_apache_settings(self):
        if not self.genv.get('_apache_settings'):
            self.set_apache_specifics()
        return self.genv._apache_settings
    
    def enable_site(self, name):
        self.sudo_or_dryrun('a2ensite %s' % name)
        
    def disable_site(self, name):
        self.sudo_or_dryrun('a2dissite %s' % name)
    
    def set_apache_specifics(self):
        from burlap import common
        
        if not self.genv.get('_apache_settings'):
            self.genv._apache_settings = type(self.genv)()
            for _k, _v in self.genv.iteritems():
                if _k.startswith('apache_') and _k not in ignore_keys:
                    self.genv._apache_settings[_k] = _v
                    
        os_version = self.os_version
        apache_specifics = self.genv.apache_specifics[os_version.type][os_version.distro]
        
        self.genv.apache_root = apache_specifics.root
        self.genv.apache_conf = apache_specifics.conf
        self.genv.apache_sites_available = apache_specifics.sites_available
        self.genv.apache_sites_enabled = apache_specifics.sites_enabled
        self.genv.apache_log_dir = apache_specifics.log_dir
        self.genv.apache_pid = apache_specifics.pid
    
        self.genv.apache_ports = self.genv.apache_ports_template % self.genv
        self.genv.apache_ssl_dir = self.genv.apache_ssl_dir_template % self.genv
    
        return apache_specifics
    
    def optimize_wsgi_processes(self):
        """
        Based on the number of sites per server and the number of resources on the server,
        calculates the optimal number of processes that should be allocated for each WSGI site.
        """
        from burlap.common import iter_sites
        #self.env.wsgi_processes = 5
        self.env.wsgi_server_memory_gb = 8
        
        verbose = self.verbose
        self.get_apache_settings()
        apache_specifics = self.set_apache_specifics()
        
        all_sites = list(iter_sites(site=ALL, setter=self.set_apache_site_specifics))
        
        #(current_mem/current_sites)/current_process = ()
        #(16/x)/(8/16) = y
        #(16/x)*(16/8) = y
        #(16*16)/(num_sites*8) = y
        
    def visitors(self, force=0):
        """
        Generates an Apache access report using the Visitors command line tool.
        Requires the APACHE2_VISITORS service to be enabled for the current host.
        """
        if not int(force):
            assert APACHE2_VISITORS.upper() in self.genv.services or APACHE2_VISITORS.lower() in self.genv.services, \
                'Visitors has not been configured for this host.'
        self.run_or_dryrun('visitors -o text /var/log/apache2/%(apache_application_name)s-access.log* | less' % self.genv)
    
    def check_required(self):
        for name in ['apache_application_name', 'apache_server_name']:
            assert self.genv[name], 'Missing %s.' % (name,)
    
    def set_apache_site_specifics(self, site):
        from burlap.dj import get_settings
        
        site_data = self.genv.sites[site]
        
        get_settings(site=site)
        
        # Set site specific values.
        self.genv.apache_site = site
        self.genv.update(site_data)
        self.genv.apache_docroot = self.genv.apache_docroot_template % self.genv
        self.genv.apache_wsgi_dir = self.genv.apache_wsgi_dir_template % self.genv
        #self.genv.apache_app_log_dir = self.genv.apache_app_log_dir_template % self.genv
        self.genv.apache_domain = self.genv.apache_domain_template % self.genv
        self.genv.apache_server_name = self.genv.apache_domain
        self.genv.apache_wsgi_python_path = self.genv.apache_wsgi_python_path_template % self.genv
        self.genv.apache_django_wsgi = self.genv.apache_django_wsgi_template % self.genv
        self.genv.apache_django_wsgi = self.genv.apache_django_wsgi.replace('-', '_')
        self.genv.apache_server_aliases = self.genv.apache_server_aliases_template % self.genv
        self.genv.apache_ssl_domain = self.genv.apache_ssl_domain_template % self.genv
        self.genv.apache_auth_basic_authuserfile = self.genv.apache_auth_basic_authuserfile_template % self.genv
        self.genv.apache_domain_with_sub = self.genv.apache_domain_with_sub_template % self.genv
        self.genv.apache_domain_without_sub = self.genv.apache_domain_without_sub_template % self.genv
        
        self.genv.apache_domain_redirects = []
        for _wrong, _right in self.genv.apache_domain_redirect_templates:
            self.genv.apache_domain_redirects.append((_wrong % self.genv, _right % self.genv))
        
    def iter_certificates(self):
        verbose = self.verbose
        self.get_apache_settings()
        
        if verbose:
            print>>sys.stderr, 'apache_ssl_domain:', self.genv.apache_ssl_domain
        for cert_type, cert_file_template in self.genv.apache_ssl_certificates_templates:
            if verbose:
                print>>sys.stderr, 'cert_type, cert_file_template:',cert_type, cert_file_template
            _local_cert_file = os.path.join(self.genv.apache_ssl_dir_local, cert_file_template % self.genv)
            local_cert_file = self.find_template(_local_cert_file)
            assert local_cert_file, 'Unable to find local certificate file: %s' % (_local_cert_file,)
            remote_cert_file = os.path.join(self.genv.apache_ssl_dir, cert_file_template % self.genv)
            yield cert_type, local_cert_file, remote_cert_file
    
    def install_ssl(self, site=ALL):
        from burlap.common import iter_sites
        verbose = self.verbose
        self.get_apache_settings()
        apache_specifics = self.set_apache_specifics()
        
        for site, site_data in iter_sites(site=site, setter=self.set_apache_site_specifics):
    #        print 'site:',site
    #        continue
            
            site_secure = site+'_secure'
            if site_secure not in self.genv.sites:
                continue
            self.set_apache_site_specifics(site_secure)
        
            self.sudo_or_dryrun('mkdir -p %(apache_ssl_dir)s' % self.genv)
            
            if self.genv.apache_ssl:
                for cert_type, local_cert_file, remote_cert_file in self.iter_certificates():
                    if verbose:
                        print '='*80
                        print 'Installing certificate %s...' % (remote_cert_file,)
                    self.put_or_dryrun(
                        local_path=local_cert_file,
                        remote_path=remote_cert_file,
                        use_sudo=True)
        
        self.sudo_or_dryrun('mkdir -p %(apache_ssl_dir)s' % self.genv)
        self.sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_ssl_dir)s' % self.genv)
        self.sudo_or_dryrun('chmod -R %(apache_ssl_chmod)s %(apache_ssl_dir)s' % self.genv)
    
    def install_auth_basic_user_file(self, site=None):
        """
        Installs users for basic httpd auth.
        """
        from burlap.common import iter_sites
        
        self.get_apache_settings()
        
        apache_specifics = self.set_apache_specifics()
        
        for site, site_data in iter_sites(site=site, setter=self.set_apache_site_specifics):
            if self.verbose:
                print>>sys.stderr, '~'*80
                print>>sys.stderr, 'Site:',site
                print>>sys.stderr, 'env.apache_auth_basic:', self.genv.apache_auth_basic
                
            if not self.genv.apache_auth_basic:
                continue
            
            #assert self.genv.apache_auth_basic, 'This site is not configured for Apache basic authenticated.'
            assert self.genv.apache_auth_basic_users, 'No apache auth users specified.'
            for username,password in self.genv.apache_auth_basic_users:
                self.genv.apache_auth_basic_username = username
                self.genv.apache_auth_basic_password = password
                if self.files.exists(self.genv.apache_auth_basic_authuserfile):
                    self.sudo_or_dryrun('htpasswd -b %(apache_auth_basic_authuserfile)s %(apache_auth_basic_username)s %(apache_auth_basic_password)s' % self.genv)
                else:
                    self.sudo_or_dryrun('htpasswd -b -c %(apache_auth_basic_authuserfile)s %(apache_auth_basic_username)s %(apache_auth_basic_password)s' % self.genv)
    
    def install_auth_basic_user_file_all(self):
        self.get_apache_settings()
        self.install_auth_basic_user_file(site='all')
    
    def view_error_log(self):
        self.run_or_dryrun('tail -f %(apache_error_log)s' % self.genv)
    
    def record_manifest(self):
        """
        Called after a deployment to record any data necessary to detect changes
        for a future deployment.
        """
        data = self.get_apache_settings()
        data['site_template_contents'] = self.get_template_contents(self.env.site_template)
        if self.verbose:
            pprint(data, indent=4)
        return data

    def configure_site(self, full=1, site=None, delete_old=0):
        """
        Configures Apache to host one or more websites.
        """
        from burlap.common import get_current_hostname, iter_sites
        from burlap import service
        
        print>>sys.stderr, 'Configuring Apache...'
        
        verbose = self.verbose
        
        site = site or self.genv.SITE
        
        apache_specifics = self.set_apache_specifics()
        hostname = get_current_hostname()
        target_sites = self.genv.available_sites_by_host.get(hostname, None)
        
        if int(delete_old):
            # Delete all existing enabled and available sites.
            cmd = 'rm -f %(apache_sites_available)s/*' % self.genv
            self.sudo_or_dryrun(cmd)
            cmd = 'rm -f %(apache_sites_enabled)s/*' % self.genv
            self.sudo_or_dryrun(cmd)
        
        for site, site_data in iter_sites(site=site, setter=self.set_apache_site_specifics):
            if self.verbose:
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
            
            if self.verbose:
                print>>sys.stderr, 'env.apache_ssl_domain:', self.genv.apache_ssl_domain
                print>>sys.stderr, 'env.apache_ssl_domain_template:', self.genv.apache_ssl_domain_template
                print>>sys.stderr, 'env.django_settings_module:', self.genv.django_settings_module
            
    #        raw_input('enter')
            fn = self.render_to_file('django/django.template.wsgi', verbose=verbose)
            remote_dir = os.path.split(self.genv.apache_django_wsgi)[0]
            cmd = 'mkdir -p %s' % remote_dir
            self.sudo_or_dryrun(cmd)
            
            if self.verbose:
                print>>sys.stderr, fn
            self.put_or_dryrun(local_path=fn, remote_path=self.genv.apache_django_wsgi, use_sudo=True)
            
            if self.genv.apache_ssl:
                self.genv.apache_ssl_certificates = list(self.iter_certificates())
            
            fn = self.render_to_file(self.env.site_template, verbose=verbose)
            self.genv.apache_site_conf = site+'.conf'
            self.genv.apache_site_conf_fqfn = os.path.join(self.genv.apache_sites_available, self.genv.apache_site_conf)
            self.put_or_dryrun(local_path=fn, remote_path=self.genv.apache_site_conf_fqfn, use_sudo=True)
            
            cmd = 'a2ensite %(apache_site_conf)s' % self.genv
            self.sudo_or_dryrun(cmd)
        
#         if service.is_selected(APACHE2_MODEVASIVE):
#             configure_modevasive()
#             
#         if service.is_selected(APACHE2_MODSECURITY):
#             configure_modsecurity()
        
        for mod_enabled in self.genv.apache_mods_enabled:
            self.genv.apache_mod_enabled = mod_enabled
            cmd = 'a2enmod %(apache_mod_enabled)s' % self.genv
            with settings(warn_only=True):
                self.sudo_or_dryrun(cmd)
            
        if int(full):
            # Write master Apache configuration file.
            fn = self.render_to_file('apache/apache_httpd.template.conf', verbose=verbose)
            self.put_or_dryrun(local_path=fn, remote_path=self.genv.apache_conf, use_sudo=True)
            
            # Write Apache listening ports configuration.
            fn = self.render_to_file('apache/apache_ports.template.conf', verbose=verbose)
            self.put_or_dryrun(local_path=fn, remote_path=self.genv.apache_ports, use_sudo=True)
            
        #sudo_or_dryrun('mkdir -p %(apache_app_log_dir)s' % self.genv)
        #sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_app_log_dir)s' % self.genv)
    #    self.sudo_or_dryrun('mkdir -p %(apache_log_dir)s' % self.genv)
    #    self.sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_log_dir)s' % self.genv)
        cmd = 'chown -R %(apache_user)s:%(apache_group)s %(apache_root)s' % self.genv
        self.sudo_or_dryrun(cmd)
    #    self.sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_docroot)s' % self.genv)
    #    self.sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_pid)s' % self.genv)
    
        #restart()#break apache? run separately?

    def configure(self):
            
        self.get_apache_settings()
        self.configure_site(full=1, site=ALL, delete_old=1)
        
        self.install_auth_basic_user_file(site=ALL)
        self.install_ssl(site=ALL)
        
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']

class ApacheModEvasiveSatchel(Satchel):
    
    name = 'apachemodevasive'
    
    tasks = (
        'configure',
    )
    
    required_system_packages = {
        (UBUNTU, '12.04'): ['libapache2-mod-evasive'],
        (UBUNTU, '14.04'): ['libapache2-mod-evasive'],
    }
    
        
    def configure():
        self.get_apache_settings()
        
        self.genv.apache_mods_enabled.append('mod-evasive')#Ubuntu 12.04
        self.genv.apache_mods_enabled.append('evasive')#Ubuntu 14.04
        
        # Write conf.
        fn = self.render_to_file('apache_modevasive.template.conf')
        self.put_or_dryrun(local_path=fn, remote_path='/etc/apache2/mods-available/mod-evasive.conf', use_sudo=True)#Ubuntu 12.04
        self.put_or_dryrun(local_path=fn, remote_path='/etc/apache2/mods-available/evasive.conf', use_sudo=True)#Ubuntu 14.04
        
    configure.is_deployer = True
    configure.deploy_before = ['apache']
    
class ApacheModRPAFSatchel(Satchel):
    
    name = 'apachemodrpaf'
    
    tasks = (
        'configure',
    )
    
    required_system_packages = {
        (UBUNTU, '12.04'): ['libapache2-mod-rpaf'],
        (UBUNTU, '14.04'): ['libapache2-mod-rpaf'],
    }
    
    def configure():
        self.get_apache_settings()
        self.genv.apache_mods_enabled.append('rpaf')
        
    configure.is_deployer = True
    configure.deploy_before = ['apache']
    
class ApacheModSecurity(Satchel):
    
    name = 'apachemodsecurity'
    
    tasks = (
        'configure',
    )
    
    required_system_packages = {
        (UBUNTU, '12.04'): ['libapache2-modsecurity'],
        (UBUNTU, '14.04'): ['libapache2-modsecurity'],
    }
    
    def configure():
        self.get_apache_settings()
        
        self.genv.apache_mods_enabled.append('mod-security')
        self.genv.apache_mods_enabled.append('headers')
        
        # Write modsecurity.conf.
        fn = self.render_to_file('apache_modsecurity.template.conf')
        self.put_or_dryrun(local_path=fn, remote_path='/etc/modsecurity/modsecurity.conf', use_sudo=True)
        
        # Write OWASP rules.
        self.genv.apache_modsecurity_download_filename = '/tmp/owasp-modsecurity-crs.tar.gz'
        self.sudo_or_dryrun('cd /tmp; wget --output-document=%(apache_modsecurity_download_filename)s %(apache_modsecurity_download_url)s' % self.genv)
        self.genv.apache_modsecurity_download_top = self.sudo_or_dryrun("cd /tmp; tar tzf %(apache_modsecurity_download_filename)s | sed -e 's@/.*@@' | uniq" % self.genv)
        self.sudo_or_dryrun('cd /tmp; tar -zxvf %(apache_modsecurity_download_filename)s' % self.genv)
        self.sudo_or_dryrun('cd /tmp; cp -R %(apache_modsecurity_download_top)s/* /etc/modsecurity/' % self.genv)
        self.sudo_or_dryrun('mv /etc/modsecurity/modsecurity_crs_10_setup.conf.example  /etc/modsecurity/modsecurity_crs_10_setup.conf' % self.genv)
        
        self.sudo_or_dryrun('rm -f /etc/modsecurity/activated_rules/*')
        self.sudo_or_dryrun('cd /etc/modsecurity/base_rules; for f in * ; do ln -s /etc/modsecurity/base_rules/$f /etc/modsecurity/activated_rules/$f ; done')
        self.sudo_or_dryrun('cd /etc/modsecurity/optional_rules; for f in * ; do ln -s /etc/modsecurity/optional_rules/$f /etc/modsecurity/activated_rules/$f ; done')
        
        self.genv.apache_httpd_conf_append.append('Include "/etc/modsecurity/activated_rules/*.conf"')
        
    configure.is_deployer = True
    configure.deploy_before = ['apache']
    
class ApacheVisitors(Satchel):
    
    name = 'apachevisitors'

    tasks = (
        'configure',
    )
    
    required_system_packages = {
        (UBUNTU, '12.04'): ['visitors'],
        (UBUNTU, '14.04'): ['visitors'],
    }
    
class ApacheMediaSatchel(Satchel):
    
    name = 'apachemedia'
    
    tasks = (
        'configure',
    )
    
    def sync_media(self, sync_set=None, clean=0, iter_local_paths=0):
        """
        Uploads select media to an Apache accessible directory.
        """
        apache.get_apache_settings()
        
        from burlap.dj import render_remote_paths
        
        apache_specifics = apache.set_apache_specifics()
        
        render_remote_paths()
        
        clean = int(clean)
        print 'Getting site data for %s...' % self.genv.SITE
#         print 'sites:', self.genv.sites
        site_data = self.genv.sites[self.genv.SITE]
        self.genv.update(site_data)
        
        sync_sets = self.genv.apache_sync_sets
        if sync_set:
            sync_sets = [sync_set]
        
        ret_paths = []
        for sync_set in sync_sets:
            for paths in self.genv.apache_sync_sets[sync_set]:
                #print 'paths:',paths
                self.genv.apache_sync_local_path = os.path.abspath(paths['local_path'] % self.genv)
                if paths['local_path'].endswith('/') and not self.genv.apache_sync_local_path.endswith('/'):
                    self.genv.apache_sync_local_path += '/'
                    
                if iter_local_paths:
                    ret_paths.append(self.genv.apache_sync_local_path)
                    continue
                    
                self.genv.apache_sync_remote_path = paths['remote_path'] % self.genv
                
                if clean:
                    self.sudo_or_dryrun('rm -Rf %(apache_sync_remote_path)s' % self.genv) 
                
                print 'Syncing %s to %s...' % (self.genv.apache_sync_local_path, self.genv.apache_sync_remote_path)
                
                self.genv.apache_tmp_chmod = paths.get('chmod',  self.genv.apache_chmod)
                #with settings(warn_only=True):
                self.sudo_or_dryrun('mkdir -p %(apache_sync_remote_path)s' % self.genv, user=self.genv.apache_user)
                self.sudo_or_dryrun('chmod -R %(apache_tmp_chmod)s %(apache_sync_remote_path)s' % self.genv, user=self.genv.apache_user)
                cmd = ('rsync -rvz --progress --recursive --no-p --no-g --rsh "ssh -o StrictHostKeyChecking=no -i %(key_filename)s" %(apache_sync_local_path)s %(user)s@%(host_string)s:%(apache_sync_remote_path)s') % self.genv
    #            print '!'*80
    #            print cmd
                self.local_or_dryrun(cmd)
                self.sudo_or_dryrun('chown -R %(apache_user)s:%(apache_group)s %(apache_sync_remote_path)s' % self.genv)
                
        if iter_local_paths:
            return ret_paths

    def record_manifest(self):
        """
        Called after a deployment to record any data necessary to detect changes
        for a future deployment.
        """
        from burlap.common import get_last_modified_timestamp
        data = 0
        for path in self.sync_media(iter_local_paths=1):
            data = min(data, get_last_modified_timestamp(path) or data)
        #TODO:hash media names and content
        if self.verbose:
            print data
        return data
        
    def configure(self):
        self.sync_media()
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'apache', 'apache2', 'pip', 'tarball']
            
apache = ApacheSatchel()

# apache_modevasive = ApacheModEvasiveSatchel()
# apache_modevasive.requires_satchel(apache)
# 
# apache_modrpaf = ApacheModRPAFSatchel()
# apache_modrpaf.requires_satchel(apache)
# 
# apache_modsecurity = ApacheModSecurity()
# apache_modsecurity.requires_satchel(apache)
# 
# apache_visitors = ApacheVisitors()
# apache_visitors.requires_satchel(apache)
# 
apachemedia = ApacheMediaSatchel()
apachemedia.requires_satchel(apache)
