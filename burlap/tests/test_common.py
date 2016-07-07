from __future__ import print_function

import os
import unittest

try:
    import pytest
except ImportError:
    pass

def test_shellquote():
    from burlap.common import shellquote
    
    s = """# /etc/cron.d/anacron: crontab entries for the anacron package

SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# minute hour day month weekday (0-6, 0 = Sunday) user command

*/5 * * * *   root    {command}
"""

    s = shellquote(s)
    
def test_regex():
    from burlap.common import CMD_VAR_REGEX, CMD_ESCAPED_VAR_REGEX, Satchel
    
    class TestSatchel(Satchel):
        
        name = 'test'
        
    test = TestSatchel()
    
    assert CMD_VAR_REGEX.findall('{cmd} {host}') == ['cmd', 'host']
    
    assert CMD_VAR_REGEX.findall("{cmd} {host} | {awk_cmd} '{{ print $1 }}'") == ['cmd', 'host', 'awk_cmd']

    assert CMD_ESCAPED_VAR_REGEX.findall("{cmd}} {{ print hello }}") == ['{{ print hello }}']

    r = test.local_renderer
    r.env.host = 'myhost'
    r.local("getent {host} | awk '{{ print $1 }}'", dryrun=1)

def test_settings_include():
    from burlap import load_yaml_settings
    
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
    