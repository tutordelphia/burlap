from fabric.contrib.files import exists
 
from burlap.common import set_verbose
from burlap.js import jshint
from burlap.tests.functional_tests.base import TestCase
from burlap.deploy import thumbprint, clear_fs_cache, delete_plan_data_dir

class JSTests(TestCase):
    
    def test_jshint(self):
        
        set_verbose(True)
        jshint.genv.ROLE = 'local'
        jshint.genv.services = ['jshint']
        jshint.clear_caches()

        print('Installing jshint...')
        jshint.env.enabled = True
        jshint.env.geckodriver_version = '0.13.0'
        jshint.clear_local_renderer()
        jshint.install_packages()
        jshint.configure()
        clear_fs_cache()
        delete_plan_data_dir()
        print('-'*80)
        print('Thumbprinting...')
        thumbprint(components=jshint.name)
        clear_fs_cache()
        print('-'*80)
        
        # Confirm jshint was installed.
        assert exists('/usr/local/bin/jshint')
        output = jshint.run('jshint --version')
        print('output:', output)
        assert 'jshint v' in output
        
        print('Disabling jshint...')
        jshint.env.enabled = False
        jshint.clear_local_renderer()
        jshint.configure()

        # Confirm jshint was uninstalled.
        assert not exists('/usr/local/bin/jshint')
