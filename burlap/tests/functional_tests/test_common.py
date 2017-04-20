from __future__ import print_function

from burlap.common import set_dryrun, run_or_dryrun, sudo_or_dryrun
from burlap.files import file # pylint: disable=redefined-builtin
from burlap.tests.functional_tests.base import TestCase

is_file = file.is_file

class CommonTests(TestCase):

    def test_dryrun(self):

        set_dryrun(True)
        run_or_dryrun('touch ~/abc.txt')
        assert not is_file('~/abc.txt')

        set_dryrun(1)
        run_or_dryrun('touch ~/def.txt')
        assert not is_file('~/def.txt')

        set_dryrun(False)
        run_or_dryrun('touch ~/mno.txt')
        assert not is_file('~/mno.txt')
        run_or_dryrun('rm -f ~/mno.txt')

        set_dryrun(0)
        run_or_dryrun('touch ~/xyz.txt')
        assert not is_file('~/xyz.txt')
        run_or_dryrun('rm -f ~/xyz.txt')

    def test_sudo(self):

        ret = run_or_dryrun('cut -d: -f1 /etc/passwd')
        print('all users:', ret)

        ret = sudo_or_dryrun('whoami')
        print('ret0:', ret)
        self.assertEqual(ret, 'root')

        ret = sudo_or_dryrun('whoami', user='daemon')
        print('ret1:', ret)
        self.assertEqual(ret, 'daemon')
