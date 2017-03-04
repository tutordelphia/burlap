"""
Tests for the common module.
"""
from __future__ import print_function

import os
import tempfile
import unittest

# try:
#     import pytest
# except ImportError:
#     pass

from burlap import load_yaml_settings
from burlap.common import CMD_VAR_REGEX, CMD_ESCAPED_VAR_REGEX
from burlap.common import shellquote
from burlap.common import Satchel, env
#from burlap.common import LocalRenderer
    
class _TestSatchel(Satchel):
    
    name = 'test'
    
    def configure(self):
        pass

class CommonTests(unittest.TestCase):
    
    def setUp(self):
        self.test = _TestSatchel()
        self.test.genv.hosts = ['localhost']
        self.test.genv.host_string = self.test.genv.hosts[0]
    
    def test_shellquote(self):
        
        s = """# /etc/cron.d/anacron: crontab entries for the anacron package
    
    SHELL=/bin/bash
    PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
    
    # minute hour day month weekday (0-6, 0 = Sunday) user command
    
    */5 * * * *   root    {command}
    """
    
        s = shellquote(s)
        
    def test_format_regex(self):
        
        assert CMD_VAR_REGEX.findall('{cmd} {host}') == ['cmd', 'host']
        
        assert CMD_VAR_REGEX.findall("{cmd} {host} | {awk_cmd} '{{ print $1 }}'") == ['cmd', 'host', 'awk_cmd']
    
        assert CMD_ESCAPED_VAR_REGEX.findall("{cmd}} {{ print hello }}") == ['{{ print hello }}']
    
        r = self.test.local_renderer
        r.env.host = 'myhost'
        r.local("getent {host} | awk '{{ print $1 }}'", dryrun=1)
        
        s = "rsync --recursive --verbose --perms --times --links --compress --copy-links {exclude_str}  ' \
            '--delete --delete-before --force {rsync_auth} {rsync_source_dir} {rsync_target_host}{rsync_target_dir}"
        assert CMD_VAR_REGEX.findall(s) == ['exclude_str', 'rsync_auth', 'rsync_source_dir', 'rsync_target_host', 'rsync_target_dir']
    
    def test_settings_include(self):
        try:
            os.makedirs('/tmp/burlap_test/roles/all')
        except OSError:
            pass
            
        try:
            os.makedirs('/tmp/burlap_test/roles/prod')
        except OSError:
            pass
            
        open('/tmp/burlap_test/roles/all/settings.yaml', 'w').write("""
only_all_param: "just in all"
overridden_by_prod: 123
overridden_by_local: slkdjflsk
    """)
        open('/tmp/burlap_test/roles/prod/settings.yaml', 'w').write("""inherits: all
overridden_by_prod: 'prod'
only_prod_param: 7891
overriden_by_include: 7892
overridden_by_local: oiuweoiruwo
#includes: [settings_include1.yaml]
includes: [settings_include2.yaml]
    """)
        open('/tmp/burlap_test/roles/prod/settings_include2.yaml', 'w').write("""
overriden_by_include: xyz
overridden_by_local: ovmxlkfsweirwio
    """)
        open('/tmp/burlap_test/roles/prod/settings_local.yaml', 'w').write("""
overridden_by_local: 'hello world'
includes: [settings_include3.yaml]
    """)
        open('/tmp/burlap_test/roles/prod/settings_include3.yaml', 'w').write("""
set_by_include3: 'some special setting'
    """)
        os.chdir('/tmp/burlap_test')
        config = load_yaml_settings(name='prod')
        
        assert config['includes'] == ['settings_include2.yaml', 'settings_include3.yaml']
        assert config['only_all_param'] == 'just in all'
        assert config['overridden_by_prod'] == 'prod'
        assert config['only_prod_param'] == 7891
        assert config['overriden_by_include'] == 'xyz'
        assert config['overridden_by_local'] == 'hello world'
        assert config['set_by_include3'] == 'some special setting'
    
    def test_renderer(self):
        
        _env = env.copy()
        try:
            
            # Confirm renderer is cached.
            r1 = self.test.local_renderer
            r2 = self.test.local_renderer
            assert r1 is r2
            
            # Confirm clear method.
            self.test.clear_local_renderer()
            r3 = self.test.local_renderer
            assert r1 is not r3
            
            r = r3
            env.clear()
            assert r.genv is env
            
            # Confirm local env var gets renderered.
            r.env.var1 = 'a'
            assert r.format('{var1}') == 'a'
            
            # Confirm global env var in local namespace gets rendered.
            env.test_var2 = 'b'
            assert r.format('{var2}') == 'b'
            
            # Confirm global env var in global namespace gets rendered.
            env.test_var2 = 'b2'
            assert r.format('{test_var2}') == 'b2'
            
            # Confirm global env var overridden in local namespace get rendered.
            env.apache_var3 = '0'
            r.env.apache_var3 = 'c'
            assert r.format('{apache_var3}') == 'c'
            
            # Confirm recursive template variables get rendered.
            r.env.some_template = '{target_value}'
            r.env.target_value = 'd'
            assert r.format('{some_template}') == 'd'
            
            class ApacheSatchel(Satchel):
                
                name = 'apache'
                
                def configure(self):
                    pass
                
            apache = ApacheSatchel()
            r = apache.local_renderer
            r.env.application_name = 'someappname'
            r.env.site = 'sitename'
            r.env.wsgi_path = '/usr/local/{apache_application_name}/src/wsgi/{apache_site}.wsgi'
            assert r.format(r.env.wsgi_path) == '/usr/local/someappname/src/wsgi/sitename.wsgi'
        finally:
            env.update(_env)
    
    def test_iter_sites(self):
        
        env.sites = {
            'site1': {'apache_ssl': False},
            'site2': {'apache_ssl': True},
        }
        
        lst = list(self.test.iter_sites())
        print('lst:', lst)
        assert len(lst) == 2
        
        lst = list(self.test.iter_sites(site='site2'))
        print('lst:', lst)
        assert len(lst) == 1
    
    def test_append(self):
        
        self.test.genv.host_string = 'localhost'
        
        _, fn = tempfile.mkstemp()
        
        text = '[{rabbit, [{loopback_users, []}]}].'
        
        self.test.append(filename=fn, text=text)
        content = open(fn).read()
        print('content0:', content)
        assert content.count(text) == 1
        
        # Confirm duplicate lines are appended.
        self.test.append(filename=fn, text=text)
        content = open(fn).read()
        print('content1:', content)
        assert content.count(text) == 1
