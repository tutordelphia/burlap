# import unittest

# from mock import patch


class _Success(str):

    @property
    def failed(self):
        return False

#TODO:fix
# class TestVagrantVersion(unittest.TestCase):
# 
#     def test_vagrant_version_1_3_0(self):
#         with patch('burlap.vagrant.local') as mock_local:
#             mock_local.return_value = _Success("Vagrant version 1.3.0\n")
#             from burlap.vagrant import version
#             self.assertEqual(version(), (1, 3, 0))
# 
#     def test_vagrant_version_1_3_1(self):
#         with patch('burlap.vagrant.local') as mock_local:
#             mock_local.return_value = _Success("Vagrant v1.3.1\n")
#             from burlap.vagrant import version
#             self.assertEqual(version(), (1, 3, 1))
# 
#     def test_vagrant_version_1_4_3(self):
#         with patch('burlap.vagrant.local') as mock_local:
#             mock_local.return_value = _Success("Vagrant 1.4.3\n")
#             from burlap.vagrant import version
#             self.assertEqual(version(), (1, 4, 3))
#
#     def test_vagrant_version_1_5_0_dev(self):
#         with patch('burlap.vagrant.local') as mock_local:
#             mock_local.return_value = _Success("Vagrant 1.5.0.dev\n")
#             from burlap.vagrant import version
#             self.assertEqual(version(), (1, 5, 0, 'dev'))
