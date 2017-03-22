from __future__ import print_function

import os
import re
import shutil
import getpass
from commands import getstatusoutput

from fabric.contrib.files import append

import burlap
from burlap.common import env
from burlap.tests.base import TestCase
from burlap.dj import dj
from burlap.project import project
from burlap.context import set_cwd
from burlap.deploy import STORAGE_LOCAL

class DjTests(TestCase):
    
    def getstatusoutput(self, cmd):
        print(cmd)
        status, output = getstatusoutput(cmd)
        print('output:', output)
        return status, output
    
    def test_migrate(self):
        
        burlap_dir = os.path.abspath(os.path.split(burlap.__file__)[0])
        
        d = '/tmp/test_dj_migrate'
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
        
        activate_cmd = '. {d}/.env/bin/activate;'.format(d=d)
        with set_cwd(d):
            project.create_skeleton(
                project_name='test_dj_migrate',
                roles='prod',
                components='dj',
            )
            
            # Simulate multiple remote hosts my creating aliases of localhost.
            # Note, for testing this on your localhost for a user without passwordless sudo,
            # you may have to run: `sudo chmod 777 /etc/hosts`
            env.host_string = 'localhost'
            env.hosts = [env.host_string]
            env.user = getpass.getuser()
            for use_sudo in (False, True):
                append(filename='/etc/hosts', text='127.0.0.1 test-dj-migrate-1', use_sudo=use_sudo)
                append(filename='/etc/hosts', text='127.0.0.1 test-dj-migrate-2', use_sudo=use_sudo)
                break
            
            os.system('ln -s %s %s/' % (burlap_dir, d))
            
            project.update_settings(
                {
                    'plan_storage': STORAGE_LOCAL,
                    'plan_data_dir': os.path.join(d, 'plans'),
                    'services': ['dj'],
                    'dj_settings_module': 'test_dj_migrate.settings',
                    'default_site': 'test_dj_migrate',
                    'default_role': 'prod',
                    'dj_local_project_dir': 'src',
                    'dj_project_dir': 'src',
                    'dj_manage_media': False,
                    'dj_manage_migrations': True,
                },
                role='all')
                
            project.update_settings(
                {
                    'hosts': ['test-dj-migrate-1', 'test-dj-migrate-2'],
                },
                role='prod')
            
            # Create custom app.
            kwargs = dict(
                src_dir='/tmp/test_dj_migrate/src',
                activate_cmd=activate_cmd,
            )
            status, output = self.getstatusoutput('{activate_cmd} cd {src_dir}; python manage.py startapp myapp'.format(**kwargs))
            assert os.path.isdir('/tmp/test_dj_migrate/src/myapp')
            
            # Add myapp to installed apps list.
            settings_fn = '/tmp/test_dj_migrate/src/test_dj_migrate/settings.py'
            with open(settings_fn) as fin:
                settings_text = fin.read()
            p = re.compile(r'INSTALLED_APPS = \[([^\]]+)', flags=re.MULTILINE)
            settings_text = p.sub(r"INSTALLED_APPS = [\1    'myapp',\n", settings_text)
            with open(settings_fn, 'w') as fout:
                fout.write(settings_text)
            status, output = self.getstatusoutput('cd {src_dir}/test_dj_migrate; rm -f *.pyc'.format(**kwargs))
            assert not status
            
            # Populate model.
            open('/tmp/test_dj_migrate/src/myapp/models.py', 'w').write('''
from __future__ import unicode_literals

from django.db import models

class MyModel(models.Model):
    pass

''')
            kwargs = dict(
                src_dir='/tmp/test_dj_migrate/src',
                activate_cmd=activate_cmd,
            )
            status, output = self.getstatusoutput('{activate_cmd} cd {src_dir}; python manage.py makemigrations myapp'.format(**kwargs))
            assert os.path.isfile('/tmp/test_dj_migrate/src/myapp/migrations/0001_initial.py')

            # Apply migrations.
            kwargs = dict(
                activate_cmd=activate_cmd,
            )
            #cmd = '{activate_cmd} fab prod deploy.show_diff'.format(activate_cmd=activate_cmd)
            #cmd = '{activate_cmd} fab prod deploy.run'.format(activate_cmd=activate_cmd)
            status, output = self.getstatusoutput('{activate_cmd} fab prod dj.configure:dryrun=1,verbose=1'.format(**kwargs))
            assert not status
            # The migrations should have been run on both hosts.
            assert '@test-dj-migrate-1] run: ' in output
            assert '@test-dj-migrate-2] run: ' in output
