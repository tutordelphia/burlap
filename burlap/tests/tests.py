"""
Tests for verifying burlap functionality.

Uses Vagrant to simulate a remote host.
https://pypi.python.org/pypi/python-vagrant/0.5.0
"""
import os
import sys
import unittest

# Allow the local burlap source to be used as the package.
BURLAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..')
VAGRANT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BURLAP_DIR)

try:
    import vagrant
except ImportError as e:
    print>>sys.stderr, \
        'Warning: Optional vagrant not installed. Tests disabled.'

from fabric.api import env, execute, task, run

from burlap import (
    package, tarball, service, user, common,
    pip,
)

class Tests(unittest.TestCase):
    
    def setUp(self):
        print 'Creating VM...'
        os.chdir(VAGRANT_DIR)
        self.v = v = vagrant.Vagrant(quiet_stdout=False, quiet_stderr=False)
        #v.up()
        env[common.ROLE] = 'testing'
        env[common.SITE] = 'mysite_site'
        env.hosts = [v.user_hostname_port()]
        env.host_string = v.user_hostname_port()
#        print 'hosts:',env.hosts
#        print 'host_string:',env.host_string
        env.key_filename = v.keyfile()
#        print 'key_filename:',env.key_filename
        env.disable_known_hosts = True # useful for when the vagrant box ip changes.
    
    def tearDown(self):
        print 'Destroying VM...'
        #self.v.destroy()
    
    def test_abc(self):
        """
        """
        
        execute(package.install)
        
        execute(pip.bootstrap)
        execute(pip.update)
        execute(pip.install)
#        
#        tarball.create()
#        tarball.deploy(clean=1)
#        
#        service.configure()
#        service.deploy()
#        #service.restart()
#        service.post_deploy()

if __name__ == '__main__':
    unittest.main()
    