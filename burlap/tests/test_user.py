import unittest

import mock


class CreateUserTestCase(unittest.TestCase):

    @mock.patch('burlap.user.run_as_root')
    def test_uid_str(self, mock_run_as_root):
        from burlap.user import create
        create('alice', uid='421')

    @mock.patch('burlap.user.run_as_root')
    def test_uid_int(self, mock_run_as_root):
        from burlap.user import create
        create('alice', uid=421)
