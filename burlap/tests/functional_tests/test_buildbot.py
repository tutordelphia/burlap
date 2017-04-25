from __future__ import print_function

from fabric.contrib.files import exists

from burlap.buildbot import buildbot
from burlap.tests.functional_tests.base import TestCase

class BuildbotTests(TestCase):

    def test_cron_check(self):
        try:
            buildbot.genv.ROLE = 'local'
            buildbot.genv.services = ['buildbot']
            buildbot.clear_caches()

            buildbot.env.cron_check_enabled = True
            buildbot.env.cron_check_worker_pid_path = '/usr/local/myproject/src/buildbot/worker/twistd.pid'
            buildbot.update_cron_check()

            assert exists(buildbot.env.cron_check_command_path)
            assert exists(buildbot.env.cron_check_crontab_path)

            self.thumbprint(components=buildbot.name)

            buildbot.env.cron_check_enabled = False
            buildbot.update_cron_check()

            assert not exists(buildbot.env.cron_check_command_path)
            assert not exists(buildbot.env.cron_check_crontab_path)
        finally:
            buildbot.uninstall_cron_check()

    def test_configure(self):
        try:
            buildbot.genv.ROLE = 'local'
            buildbot.genv.services = ['buildbot']
            buildbot.clear_caches()

            buildbot.env.cron_check_enabled = True
            buildbot.env.cron_check_worker_pid_path = '/usr/local/myproject/src/buildbot/worker/twistd.pid'
            buildbot.configure()

            assert exists(buildbot.env.cron_check_command_path)
            assert exists(buildbot.env.cron_check_crontab_path)

            self.thumbprint(components=buildbot.name)

            buildbot.env.cron_check_enabled = False
            buildbot.configure()

            assert not exists(buildbot.env.cron_check_command_path)
            assert not exists(buildbot.env.cron_check_crontab_path)
        finally:
            buildbot.uninstall()
