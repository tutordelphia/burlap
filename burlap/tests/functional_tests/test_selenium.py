
from fabric.contrib.files import exists

from burlap.selenium import selenium
from burlap.tests.functional_tests.base import TestCase

class SeleniumTests(TestCase):

    def test_selenium(self):

        print('selenium.geckodriver_path:', selenium.geckodriver_path)

        selenium.env.enabled = True
        selenium.configure()

        assert exists(selenium.geckodriver_path)

        selenium.env.enabled = False
        selenium.configure()

        assert not exists(selenium.geckodriver_path)
