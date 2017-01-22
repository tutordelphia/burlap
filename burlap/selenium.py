"""
Wrapper around the Motion service.

http://www.lavrsen.dk/foswiki/bin/view/Motion/WebHome
"""
from __future__ import print_function

from burlap import Satchel
from burlap.constants import *
from burlap.decorators import task

class SeleniumSatchel(Satchel):
    
    name = 'selenium'
    
    def set_defaults(self):
        
        # See https://github.com/mozilla/geckodriver/releases for other versions and architectures.
        self.env.geckodriver_version = '0.13.0'
        self.env.geckodriver_arch = 'linux64'
    
    @task
    def install_geckodriver(self):
        r = self.local_renderer
        r.run(
            'cd /tmp; '
            'wget --show-progress https://github.com/mozilla/geckodriver/releases/download/v{geckodriver_version}/'
                'geckodriver-v{geckodriver_version}-{geckodriver_arch}.tar.gz; '
            'tar -xvzf geckodriver-v{geckodriver_version}-{geckodriver_arch}.tar.gz')
        r.sudo('mv /tmp/geckodriver /usr/local/bin') 
    
    @task
    def configure(self):
        pass
    configure.deploy_before = ['packager', 'user']
    
selenium = SeleniumSatchel()
