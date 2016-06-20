from __future__ import print_function

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
