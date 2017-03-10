from commands import getstatusoutput

from burlap.tests.base import TestCase as _TestCase

class TestCase(_TestCase):

    # These are set in conftest.py before the functional tests are run, and aren't set again,
    # so tell the parent TestCase to not clear them between individual tests.
    keep_env_keys = [
        'host_string',
        'hosts',
        'roles',
        'user',
        'key_filename',
        'disable_known_hosts',
        'abort_on_prompts',
        'always_use_pty',
    ]

    def bash(self, cmd):
        cmd = cmd.replace('"', r'\"')
        s = '/bin/bash -c "%s"' % cmd
        print('cmd:', s)
        return getstatusoutput(s)
