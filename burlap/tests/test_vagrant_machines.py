import unittest

try:
    import pytest
    from mock import patch
except ImportError:
    pass

class TestVagrantMachines(unittest.TestCase):

    def test_machines_one(self):
#         with patch('fabtools.vagrant._status') as mock_status:
#             mock_status.return_value = [('default', 'running')]
#             from fabtools.vagrant import machines
#             self.assertEqual(machines(), ['default'])
        pass
        