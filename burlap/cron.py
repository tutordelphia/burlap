from __future__ import print_function

import os
import sys

from burlap import ServiceSatchel
from burlap.constants import * 

class CronSatchel(ServiceSatchel):
    
    name = 'cron'
    
    ## Service options.
    
    #ignore_errors = True
        
    post_deploy_command = None
    
    @property
    def packager_system_packages(self):
        return {
            FEDORA: ['crontabs'],
            (UBUNTU, '12.04'): ['cron'],
        }

    def set_defaults(self):
        self.env.enabled = True
        self.env.crontabs_available = type(self.genv)() # {name:[cron lines]}
        self.env.command = 'cron'
        self.env.user = 'www-data'
        self.env.python = None
        self.env.crontab_headers = ['PATH=/usr/sbin:/usr/bin:/sbin:/bin\nSHELL=/bin/bash']
        self.env.django_manage_template = '%(remote_app_src_package_dir)s/manage.py'
        self.env.stdout_log_template = r'/tmp/chroniker-%(SITE)s-stdout.$(date +\%%d).log'
        self.env.stderr_log_template = r'/tmp/chroniker-%(SITE)s-stderr.$(date +\%%d).log'
        self.env.crontabs_selected = [] # [name]
           
        self.env.service_commands = {
            START:{
                FEDORA: 'systemctl start crond.service',
                UBUNTU: 'service cron start',
            },
            STOP:{
                FEDORA: 'systemctl stop crond.service',
                UBUNTU: 'service cron stop',
            },
            DISABLE:{
                FEDORA: 'systemctl disable crond.service',
                UBUNTU: 'chkconfig cron off',
                (UBUNTU, '14.04'): 'update-rc.d -f cron remove',
            },
            ENABLE:{
                FEDORA: 'systemctl enable crond.service',
                UBUNTU: 'chkconfig cron on',
                (UBUNTU, '14.04'): 'update-rc.d cron defaults',
            },
            RESTART:{
                FEDORA: 'systemctl restart crond.service',
                UBUNTU: 'service cron restart; sleep 3',
            },
            STATUS:{
                FEDORA: 'systemctl status crond.service',
                UBUNTU: 'service cron status',
            },
        }
        
    def render_paths(self, env=None):
        from burlap.pip import render_paths as pip_render_paths
        from burlap.dj import render_remote_paths as dj_render_paths
        
        env = env or self.genv
        env = pip_render_paths(env)
        env = dj_render_paths(env)
        
        print('remote_app_src_package_dir:', env.remote_app_src_package_dir)
        
        env.cron_python = os.path.join(env.pip_virtual_env_dir, 'bin', 'python')
        env.cron_django_manage = self.env.django_manage_template % env
        env.cron_stdout_log = self.env.stdout_log_template % env
        env.cron_stderr_log = self.env.stderr_log_template % env
        
        return env
    
    def deploy(self, site=None):
        """
        Writes entire crontab to the host.
        """
        from burlap.common import get_current_hostname, iter_sites
        
        cron_crontabs = []
        hostname = get_current_hostname()
        target_sites = self.genv.available_sites_by_host.get(hostname, None)
        if self.verbose:
            print('hostname: "%s"' % (hostname,), file=sys.stderr) 
        for site, site_data in iter_sites(site=site):
            if self.verbose:
                print('site:', site, file=sys.stderr)
            
            env = self.render_paths(type(self.genv)(self.genv))
            
            # Only load site configurations that are allowed for this host.
            if target_sites is None:
                pass
            else:
                assert isinstance(target_sites, (tuple, list))
                if site not in target_sites:
                    print('Skipping:', site, file=sys.stderr)
                    continue
            
            if self.verbose:
                print('env.crontabs_selected:', self.env.crontabs_selected, file=sys.stderr)
                
            for selected_crontab in self.env.crontabs_selected:
                lines = self.env.crontabs_available.get(selected_crontab, [])
                if self.verbose:
                    print('lines:', lines, file=sys.stderr)
                for line in lines:
                    cron_crontabs.append(line % env)
        
        if not cron_crontabs:
            return
        
        cron_crontabs = self.env.crontab_headers + cron_crontabs
        cron_crontabs.append('\n')
        env.crontabs_rendered = '\n'.join(cron_crontabs)
        fn = self.write_to_file(content=env.crontabs_rendered)
        if self.dryrun:
            print('echo %s > %s' % (env.crontabs_rendered, fn))
        self.put_or_dryrun(local_path=fn)
        env.put_remote_path = self.genv.put_remote_path
        self.sudo_or_dryrun('crontab -u %(cron_user)s %(put_remote_path)s' % env)
    
    def configure(self, **kwargs):
        if self.env.enabled:
            kwargs['site'] = ALL
            self.deploy(**kwargs)
            self.enable()
            self.restart()
        else:
            self.disable()
            self.stop()
    
    configure.deploy_before = ['packager', 'user', 'tarball']
        
CronSatchel()
