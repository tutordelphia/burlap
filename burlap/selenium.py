"""
Wrapper around the Motion service.

http://www.lavrsen.dk/foswiki/bin/view/Motion/WebHome
"""
from __future__ import print_function

from burlap import Satchel
from burlap.constants import *
from burlap.decorators import task

class SeleniumSatchel(Satchel):
    """
    Management commands for the Selenium browser automation and testing tool.
    
    http://www.seleniumhq.org/
    """

    name = 'selenium'

    def set_defaults(self):        
        # See https://github.com/mozilla/geckodriver/releases for other versions and architectures.
        self.env.geckodriver_version = '0.13.0'
        self.env.geckodriver_arch = 'linux64'
        self.env.geckodriver_url_template = \
            'https://github.com/mozilla/geckodriver/releases/download/' \
            'v{geckodriver_version}/geckodriver-v{geckodriver_version}-{geckodriver_arch}.tar.gz'
        self.env.geckodriver_install_bin_path = '/usr/local/bin'
        self.env.geckodriver_bin_name = 'geckodriver'

    @property
    def geckodriver_path(self):
        r = self.local_renderer
        return r.format('{geckodriver_install_bin_path}/{geckodriver_bin_name}')

    @task
    def install_geckodriver(self):
        r = self.local_renderer
        r.run(
            'cd /tmp; '
            'wget -O geckodriver.tar.gz {geckodriver_url_template}; '
            'tar -xvzf geckodriver.tar.gz')
        r.sudo('mv /tmp/{geckodriver_bin_name} {geckodriver_install_bin_path}')

    @task
    def uninstall_geckodriver(self):
        r = self.local_renderer
        r.sudo('rm -f {geckodriver_install_bin_path}/{geckodriver_bin_name}')

    @task(precursors=['packager'])
    def configure(self):
        if self.env.enabled:
            self.install_geckodriver()
        else:
            self.uninstall_geckodriver()

selenium = SeleniumSatchel()
