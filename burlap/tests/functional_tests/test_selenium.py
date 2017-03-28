
from fabric.contrib.files import exists

from burlap.common import set_verbose
from burlap.selenium import selenium
from burlap.tests.functional_tests.base import TestCase
from burlap.deploy import thumbprint, clear_fs_cache, delete_plan_data_dir

class SeleniumTests(TestCase):

    def test_selenium(self):
        try:
            set_verbose(True)
            print('selenium.geckodriver_path:', selenium.geckodriver_path)
            selenium.genv.ROLE = 'local'
            selenium.genv.services = ['selenium']
            selenium.clear_caches()
    
            print('Enabling selenium/gecko to install and track old version.')
            selenium.env.enabled = True
            selenium.env.geckodriver_version = '0.13.0'
            selenium.clear_local_renderer()
            assert selenium.get_target_geckodriver_version_number() == '0.13.0'
            selenium.configure()
            clear_fs_cache()
            thumbprint(components=selenium.name)
            clear_fs_cache()
    
            # Confirm install succeeded.
            assert exists(selenium.geckodriver_path)
            assert not selenium.check_for_change()
            output = selenium.run('geckodriver --version')
            expected_version = selenium.env.geckodriver_version
            assert expected_version in output
            
            # Update configuration to track the most recent version.
            selenium.env.geckodriver_version = None
            selenium.clear_local_renderer()
            assert selenium.get_target_geckodriver_version_number() != '0.13.0'
            assert selenium.last_manifest.fingerprint == '0.13.0'
            
            print('Confirm we now see a pending change...')
            assert selenium.check_for_change()
            
            print('-'*80)
            print('Applying change...')
            selenium.configure()
            clear_fs_cache()
            delete_plan_data_dir()
            print('-'*80)
            print('Thumbprinting...')
            thumbprint(components=selenium.name)
            clear_fs_cache()
            print('-'*80)
            
            # Confirm the most recent version was installed.
            selenium.clear_caches()
            assert selenium.last_manifest.fingerprint == '0.15.0'
            output = selenium.run('geckodriver --version')
            expected_version = selenium.get_latest_geckodriver_version_number()
            assert expected_version in output
            assert not selenium.check_for_change()
    
            print('Update configuration to not manage gecko and apply...')
            selenium.env.enabled = False
            selenium.clear_local_renderer()
            selenium.configure()
    
            # Confirm gecko was uninstalled.
            assert not exists(selenium.geckodriver_path)

        finally:
            selenium.uninstall_geckodriver()
