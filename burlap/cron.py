from __future__ import print_function

import sys

from burlap import ServiceSatchel
from burlap.constants import *
from burlap.decorators import task 

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
        
    def render_paths(self):
        r = self.local_renderer
        r.env.cron_stdout_log = r.format(r.env.stdout_log_template)
        r.env.cron_stderr_log = r.format(r.env.stderr_log_template)
    
    def deploy(self, site=None):
        """
        Writes entire crontab to the host.
        """
        r = self.local_renderer
        
        cron_crontabs = []
#         if self.verbose:
#             print('hostname: "%s"' % (hostname,), file=sys.stderr) 
        for site, site_data in self.iter_sites(site=site):
            if self.verbose:
                print('site:', site, file=sys.stderr)
                print('env.crontabs_selected:', self.env.crontabs_selected, file=sys.stderr)
                
            for selected_crontab in self.env.crontabs_selected:
                lines = self.env.crontabs_available.get(selected_crontab, [])
                if self.verbose:
                    print('lines:', lines, file=sys.stderr)
                for line in lines:
                    cron_crontabs.append(r.format(line))
        
        if not cron_crontabs:
            return
        
        cron_crontabs = self.env.crontab_headers + cron_crontabs
        cron_crontabs.append('\n')
        r.env.crontabs_rendered = '\n'.join(cron_crontabs)
        fn = self.write_to_file(content=r.env.crontabs_rendered)
        r.env.put_remote_path = r.put(local_path=fn)
        r.sudo('crontab -u {cron_user} {put_remote_path}')
    
    @task(precursors=['packager', 'user', 'tarball'])
    def configure(self, **kwargs):
        if self.env.enabled:
            kwargs['site'] = ALL
            self.deploy(**kwargs)
            self.enable()
            self.restart()
        else:
            self.disable()
            self.stop()
        
cron = CronSatchel()
