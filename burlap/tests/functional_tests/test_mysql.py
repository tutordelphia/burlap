
from burlap.mysql import MySQLSatchel, MYSQLD_SAFE

MYSQL_ROOT_PASSWORD = 's3cr3t'

def test_set_root_password_mysqld_safe():
    mysql = MySQLSatchel()
    try:
        mysql.verbose = True
        mysql.install_packages()
        mysql.env.root_username = 'root'
        mysql.env.root_password = mysql.env.db_root_password = MYSQL_ROOT_PASSWORD
        mysql.set_root_password(method=MYSQLD_SAFE)
        ret = mysql.execute('SHOW DATABASES;', use_sudo=True)
        print('ret:', ret)
    finally:
        mysql.purge_packages()
