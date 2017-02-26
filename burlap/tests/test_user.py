import unittest

from burlap.user import user

class CreateUserTestCase(unittest.TestCase):

    def test_uid_str(self):
        user.create('alice', uid='421')

    def test_uid_int(self):
        user.create('alice', uid=421)
