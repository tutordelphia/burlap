import unittest

from burlap.group import group

class CreateGroupTestCase(unittest.TestCase):

    def test_gid_str(self):
        group.create('some_group', gid='421')

    def test_gid_int(self):
        group.create('some_group', gid=421)
