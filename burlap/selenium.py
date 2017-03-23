"""
Wrapper around the Motion service.

http://www.lavrsen.dk/foswiki/bin/view/Motion/WebHome
"""
from __future__ import print_function
import re

import feedparser

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
        # Set version to None will default to most recent version.
        self.env.geckodriver_version = None#'0.13.0'
        
        self.env.geckodriver_arch = 'linux64'
        self.env.geckodriver_url_template = \
            'https://github.com/mozilla/geckodriver/releases/download/' \
            'v{geckodriver_version}/geckodriver-v{geckodriver_version}-{geckodriver_arch}.tar.gz'
        self.env.geckodriver_install_bin_path = '/usr/local/bin'
        self.env.geckodriver_bin_name = 'geckodriver'
        self.env.geckodriver_fingerprint_path = '/usr/local/lib/geckodriver/fingerprint.txt'

    @property
    def geckodriver_path(self):
        r = self.local_renderer
        return r.format('{geckodriver_install_bin_path}/{geckodriver_bin_name}')

    @task
    def install_geckodriver(self):
        r = self.local_renderer
        self.vprint('Checking geckdriver %s...' % r.env.geckodriver_version)
        if not r.env.geckodriver_version:
            r.env.geckodriver_version = self.get_most_recent_version()
        self.vprint('Installing geckdriver %s...' % r.env.geckodriver_version)
        r.run(
            'cd /tmp; '
            'wget -O geckodriver.tar.gz {geckodriver_url_template}; '
            'tar -xvzf geckodriver.tar.gz')
        r.sudo('mv /tmp/{geckodriver_bin_name} {geckodriver_install_bin_path}')

    @task
    def uninstall_geckodriver(self):
        r = self.local_renderer
        r.sudo('rm -f {geckodriver_install_bin_path}/{geckodriver_bin_name}')

    @task
    def check_for_change(self):
        """
        Determines if a new release has been made.
        """
        r = self.local_renderer
        lm = self.last_manifest
        print('lm:', lm)
        last_fingerprint = lm.fingerprint
        current_fingerprint = self.get_fingerprint()
        print('last_fingerprint:', last_fingerprint)
        print('current_fingerprint:', current_fingerprint)
        if last_fingerprint != current_fingerprint:
            print('A new release is available.')
        else:
            print('No updates found.')
    
    @task
    def get_most_recent_version(self):
        link = feedparser.parse('https://github.com/mozilla/geckodriver/tags.atom')['entries'][0]['link']
        self.vprint('link:', link)
        matches = re.findall(r'v([0-9]+.[0-9]+.[0-9]+)', link)
        if matches:
            version = matches[0]
            self.vprint('version:', version)
            return version
    
    @task
    def get_fingerprint(self):
        fingerprint = feedparser.parse('https://github.com/mozilla/geckodriver/tags.atom')['entries'][0]['link']
        self.vprint('fingerprint:', fingerprint)
        return fingerprint

    def record_manifest(self):
        """
        Called after a deployment to record any data necessary to detect changes
        for a future deployment.
        """
        manifest = super(SeleniumSatchel, self).record_manifest()
        manifest['fingerprint'] = self.get_fingerprint()
        return manifest

    @task(precursors=['packager'])
    def configure(self):
        if self.env.enabled:
            self.install_geckodriver()
        else:
            self.uninstall_geckodriver()

selenium = SeleniumSatchel()
