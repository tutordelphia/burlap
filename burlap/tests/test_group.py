import unittest

import mock


class CreateGroupTestCase(unittest.TestCase):

    @mock.patch('burlap.group.run_as_root')
    def test_gid_str(self, mock_run_as_root):
        from burlap.group import create
        create('some_group', gid='421')

    @mock.patch('burlap.group.run_as_root')
    def test_gid_int(self, mock_run_as_root):
        from burlap.group import create
        create('some_group', gid=421)
