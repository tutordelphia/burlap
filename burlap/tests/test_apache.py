from __future__ import print_function

import os
import shutil
import getpass

from fabric.contrib.files import append
from fabric.api import settings

import burlap
from burlap.common import env
from burlap.tests.base import TestCase
from burlap.project import project
from burlap.context import set_cwd
from burlap.deploy import STORAGE_LOCAL

class ApacheTests(TestCase):

    def test_diff(self):
        """
        Confirm on a multi-site multi-host environment, apache correctly reports change.
        """
        print('Setting paths...')
        #env.plan_storage = STORAGE_LOCAL
        env.disable_known_hosts = True
        burlap_dir = os.path.abspath(os.path.split(burlap.__file__)[0])

        print('Initializing tmp directory...')
        d = '/tmp/test_apache_change'
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)

        activate_cmd = '. {d}/.env/bin/activate;'.format(d=d)
        with set_cwd(d):
            print('Creating project skeleton...')
            project.create_skeleton(
                project_name='test_apache_change',
                roles='prod',
                components='apache',
            )

            assert not os.path.isfile('%s/plans/prod/000/thumbprints/test-dj-migrate-1' % d)
            assert not os.path.isfile('%s/plans/prod/000/thumbprints/test-dj-migrate-2' % d)

            # Simulate multiple remote hosts my creating aliases of localhost.
            # Note, for testing this on your localhost for a user without passwordless sudo,
            # you may have to run: `sudo chmod 777 /etc/hosts`
            # This won't work on Travis, where these will instead be set in .travis.yml.
            print('Modifying /etc/hosts...')
            env.host_string = 'localhost'
            env.hosts = [env.host_string]
            env.user = getpass.getuser()
            with settings(warn_only=True):
                for use_sudo in (False, True):
                    ret = append(filename='/etc/hosts', text='127.0.0.1 test-dj-migrate-1\n127.0.0.1 test-dj-migrate-2', use_sudo=use_sudo)
                    if ret is None:
                        break

            os.system('ln -s %s %s/' % (burlap_dir, d))

            project.update_settings({
                    'plan_storage': STORAGE_LOCAL,
                    'plan_data_dir': os.path.join(d, 'plans'),
                    'services': ['apache'],
                    'default_site': 'testsite1',
                    'default_role': 'prod',
                    # This is necessary to stop get_current_hostname() from attempting to lookup our actual hostname.
                    '_ip_to_hostname': {
                        'test-dj-migrate-1': 'test-dj-migrate-1',
                        'test-dj-migrate-2': 'test-dj-migrate-2',
                    },
                    'apache_application_name': 'testsite1',
                    'apache_server_admin_email': 'sysadmin@mydomain.com',
                    'apache_server_aliases_template': '{apache_locale}.mydomain.com',
                    'apache_wsgi_dir_template': '/usr/local/{apache_application_name}/wsgi',
                    'apache_wsgi_processes': 1,
                    'apache_wsgi_threads': 0,
                },
                role='all')

            project.update_settings({
                    'hosts': ['test-dj-migrate-1', 'test-dj-migrate-2'],
                    'available_sites_by_host':{
                        'test-dj-migrate-1': [
                            'testsite1',
                        ],
                        'test-dj-migrate-2': [
                            'testsite2',
                        ]
                    },
                    'sites': {
                        'testsite1': {
                            'apache_domain_template': 'testsite1.test-dj-migrate-1.com',
                        },
                        'testsite2': {
                            'apache_domain_template': 'testsite2.test-dj-migrate-2.com',
                        },
                    },
                },
                role='prod')

            # Run a deployment preview.
            kwargs = dict(
                activate_cmd=activate_cmd,
            )
            status, output = self.getstatusoutput('{activate_cmd} fab prod deploy.preview'.format(**kwargs))
            assert not status
            # The deployment preview should include both hosts.
            assert "[test-dj-migrate-1] Executing task 'deploy.preview'" in output
            assert "[test-dj-migrate-2] Executing task 'deploy.preview'" in output
            assert not os.path.isfile('%s/plans/prod/000/thumbprints/test-dj-migrate-1' % d)
            assert not os.path.isfile('%s/plans/prod/000/thumbprints/test-dj-migrate-2' % d)

            status, output = self.getstatusoutput(
                '{activate_cmd} '
                'fab prod debug.set_satchel_value:apache,site,xyz '
                'debug.show_satchel_items:apache'.format(**kwargs))
            assert not status
            assert ' = xyz' in output

            # Fake a deployment.
            #status, output = self.getstatusoutput((
                #'{activate_cmd} '
                #'fab prod debug.set_satchel_value:apache,site,abc '
                #'deploy.fake:set_satchels="apache-site-abc"').format(**kwargs))
            #assert not status
            #assert os.path.isfile('%s/plans/prod/000/thumbprints/test-dj-migrate-1' % d)
            #assert os.path.isfile('%s/plans/prod/000/thumbprints/test-dj-migrate-2' % d)

            ## Confirm apache now reports no changes needing deployment.
            #status, output = self.getstatusoutput('{activate_cmd} fab prod deploy.preview'.format(**kwargs))
            #assert not status
            #assert "[test-dj-migrate-1] Executing task 'deploy.preview'" in output
            #assert "[test-dj-migrate-2] Executing task 'deploy.preview'" in output
            #assert os.path.isfile('%s/plans/prod/000/thumbprints/test-dj-migrate-1' % d)
            #print(open('%s/plans/prod/000/thumbprints/test-dj-migrate-1' % d).read())
            #assert os.path.isfile('%s/plans/prod/000/thumbprints/test-dj-migrate-2' % d)
            #print(open('%s/plans/prod/000/thumbprints/test-dj-migrate-2' % d).read())
