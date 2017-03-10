from burlap.constants import *
from burlap.mysql import MySQLSatchel, MYSQLD_SAFE
from burlap.tests.functional_tests.base import TestCase

MYSQL_ROOT_PASSWORD = 's3cr3t'

class MySQLTests(TestCase):
        
    def test_set_root_password_mysqld_safe(self):
        mysql = MySQLSatchel()
        try:
            mysql.verbose = True
            
            # https://docs.travis-ci.com/user/ci-environment/
            # Travis-CI uses Ubuntu 14.04, which has some odd default MySQL packages that we need to remove
            # before we can install the correct ones.
            # http://askubuntu.com/a/489817/13217
    #         os_ver = mysql.os_version
    #         if os_ver.distro == UBUNTU and os_ver.release == '14.04':
    #             mysql.sudo('DEBIAN_FRONTEND=noninteractive apt-get -yq purge mysql*')
    #             mysql.sudo('DEBIAN_FRONTEND=noninteractive apt-get -yq autoremove')
    #             mysql.sudo('DEBIAN_FRONTEND=noninteractive apt-get -yq autoclean')
    #             mysql.sudo('DEBIAN_FRONTEND=noninteractive apt-get -yq update')
    #             mysql.sudo('DEBIAN_FRONTEND=noninteractive apt-get -yq install mysql-client-core-5.5')
                
            mysql.install_packages()
            mysql.env.root_username = 'root'
            mysql.env.root_password = mysql.env.db_root_password = MYSQL_ROOT_PASSWORD
            mysql.set_root_password(method=MYSQLD_SAFE)
            ret = mysql.execute('SHOW DATABASES;', use_sudo=True)
            print('ret:', ret)
        finally:
            mysql.purge_packages()
