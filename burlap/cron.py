import os
import sys

from burlap import common
from burlap.common import env, ServiceSatchel

class CronSatchel(ServiceSatchel):
    
    name = 'cron'
    
    ## Service options.
    
    #ignore_errors = True
    
    tasks = (
        'configure',
    )
    
    post_deploy_command = None
    
#     def __init__(self):
#         #Satchel, Service
#         super(CronSatchel, self).__init__()

    required_system_packages = {
        common.FEDORA: ['crontabs'],
        (common.UBUNTU, '12.04'): ['cron'],
    }

    def set_defaults(self):
        env.enabled = True
        env.crontabs_available = type(env)() # {name:[cron lines]}
        env.command = 'cron'
        env.user = 'www-data'
        env.python = None
        env.crontab_headers = ['PATH=/usr/sbin:/usr/bin:/sbin:/bin\nSHELL=/bin/bash']
        env.django_manage_template = '%(remote_app_src_package_dir)s/manage.py'
        env.stdout_log_template = '/tmp/chroniker-%(SITE)s-stdout.$(date +\%%d).log'
        env.stderr_log_template = '/tmp/chroniker-%(SITE)s-stderr.$(date +\%%d).log'
        env.crontabs_selected = [] # [name]
           
        env.service_commands = {
            common.START:{
                common.FEDORA: 'systemctl start crond.service',
                common.UBUNTU: 'service cron start',
            },
            common.STOP:{
                common.FEDORA: 'systemctl stop crond.service',
                common.UBUNTU: 'service cron stop',
            },
            common.DISABLE:{
                common.FEDORA: 'systemctl disable crond.service',
                common.UBUNTU: 'chkconfig cron off',
                (common.UBUNTU, '14.04'): 'update-rc.d -f cron remove',
            },
            common.ENABLE:{
                common.FEDORA: 'systemctl enable crond.service',
                common.UBUNTU: 'chkconfig cron on',
                (common.UBUNTU, '14.04'): 'update-rc.d cron defaults',
            },
            common.RESTART:{
                common.FEDORA: 'systemctl restart crond.service',
                common.UBUNTU: 'service cron restart; sleep 3',
            },
            common.STATUS:{
                common.FEDORA: 'systemctl status crond.service',
                common.UBUNTU: 'service cron status',
            },
        }
        
    def render_paths(self):
        from pip import render_paths as pip_render_paths
        
        pip_render_paths()
        
        self.env.python = os.path.join(env.pip_virtual_env_dir, 'bin', 'python')
        self.env.django_manage = env.cron_django_manage_template % env
        self.env.stdout_log = env.cron_stdout_log_template % env
        self.env.stderr_log = env.cron_stderr_log_template % env
    
    def deploy(self, site=None, verbose=0):
        """
        Writes entire crontab to the host.
        """ 
        
        verbose = int(verbose)
        cron_crontabs = []
        hostname = common.get_current_hostname()
        target_sites = env.available_sites_by_host.get(hostname, None)
        if verbose:
            print>>sys.stderr, 'hostname: "%s"' % (hostname,) 
        for site, site_data in common.iter_sites(site=site, renderer=render_paths):
            if verbose:
                print>>sys.stderr, 'site:',site
            #print 'cron_crontabs_selected:',env.cron_crontabs_selected
            
            # Only load site configurations that are allowed for this host.
            if target_sites is None:
                pass
            else:
                assert isinstance(target_sites, (tuple, list))
                if site not in target_sites:
                    print>>sys.stderr, 'Skipping:', site
                    continue
            
            if verbose:
                print>>sys.stderr, 'env.cron_crontabs_selected:',env.cron_crontabs_selected
            for selected_crontab in env.cron_crontabs_selected:
                lines = env.cron_crontabs_available.get(selected_crontab, [])
                if verbose:
                    print>>sys.stderr, 'lines:',lines
                for line in lines:
                    cron_crontabs.append(line % env)
        
        if not cron_crontabs:
            return
        
        cron_crontabs = env.cron_crontab_headers + cron_crontabs
        cron_crontabs.append('\n')
        env.cron_crontabs_rendered = '\n'.join(cron_crontabs)
        fn = self.write_to_file(content=env.cron_crontabs_rendered)
        if common.get_dryrun():
            print 'echo %s > %s' % (env.cron_crontabs_rendered, fn)
        self.put_or_dryrun(local_path=fn)
        self.sudo_or_dryrun('crontab -u %(cron_user)s %(put_remote_path)s' % env)
    
    def configure(self, **kwargs):
        if env.cron_enabled:
            kwargs['site'] = common.ALL
            self.deploy(**kwargs)
            self.enable()
            self.restart()
        else:
            self.disable()
            self.stop()
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user', 'tarball']
        
CronSatchel()
