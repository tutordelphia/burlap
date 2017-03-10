from __future__ import print_function
import os
import sys
# import tempfile
import shutil

from burlap import common
from burlap.tests.base import TestCase

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))

class ProjectTests(TestCase):
    
    def setUp(self):
        super(ProjectTests, self).setUp()
        
        common.set_verbose(True)
        # Ensure we're in burlap's root directory.
        os.chdir(os.path.abspath(os.path.join(CURRENT_DIR, '../..')))
    
    def test_project(self):
        try:
            project_dir = '/tmp/burlap_test'#tempfile.mkdtemp()
            if not os.path.isdir(project_dir):
                os.makedirs(project_dir)
            bin_dir = os.path.split(sys.executable)[0]
            
            cmd = (
                '. {bin_dir}/activate; '
                'cd {project_dir}; '
                'burlap skel --name=myproject'
            ).format(**locals())
            print(cmd)
            os.system(cmd)
            
            cmd = (
                '. {bin_dir}/activate; '
                'cd {project_dir}; '
                'burlap-admin.py add-role prod dev'
            ).format(**locals())
            print(cmd)
            os.system(cmd)
            
        finally:
            shutil.rmtree(project_dir)
    
    
    def test_find_template(self):
        fn = 'burlap/gitignore.template'
        ret = common.find_template(fn)
        print('ret:', ret)
        assert ret and ret.endswith(fn) 
    
    
    def test_render_to_string(self):
        ret = common.render_to_string(
            'postfix/etc_postfix_sasl_sasl_passwd',
            dict(
                postfix_host='smtp.test.com',
                postfix_port=1234,
                postfix_username='myusername',
                postfix_password='mypassword',
            ))
        print('ret:', ret)
        assert ret == "[smtp.test.com]:1234 myusername:mypassword"
