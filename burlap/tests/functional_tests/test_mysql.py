import pytest

from fabric.api import run, settings

from burlap.require import file as require_file
from burlap.service import is_running


pytestmark = pytest.mark.network


MYSQL_ROOT_PASSWORD = 's3cr3t'


def test_require_mysql_server():
    from burlap.require.mysql import server
    server(password=MYSQL_ROOT_PASSWORD)
    assert is_running('mysql')


@pytest.fixture
def mysql_server():
    from burlap.require.mysql import server
    server(password=MYSQL_ROOT_PASSWORD)


def test_create_user(mysql_server):

    from burlap.mysql import create_user, query, user_exists

    with settings(mysql_user='root', mysql_password=MYSQL_ROOT_PASSWORD):
        try:
            create_user('bob', 'password', host='host1')
            create_user('bob', 'password', host='host2')
            assert user_exists('bob', host='host1')
            assert user_exists('bob', host='host2')
            assert not user_exists('bob', host='localhost')
        finally:
            query('DROP USER bob@host1;')
            query('DROP USER bob@host2;')


def test_require_user(mysql_server):

    from burlap.mysql import query, user_exists
    from burlap.require.mysql import user

    with settings(mysql_user='root', mysql_password=MYSQL_ROOT_PASSWORD):
        try:
            user('myuser', 'foo')
            assert user_exists('myuser')
        finally:
            query('DROP USER myuser@localhost;')


@pytest.yield_fixture
def mysql_user():

    from burlap.mysql import query
    from burlap.require.mysql import user

    username = 'myuser'
    password = 'foo'

    with settings(mysql_user='root', mysql_password=MYSQL_ROOT_PASSWORD):
        user(username, password)

    yield username, password

    with settings(mysql_user='root', mysql_password=MYSQL_ROOT_PASSWORD):
        query('DROP USER {0}@localhost;'.format(username))


def test_require_database(mysql_server, mysql_user):

    from burlap.mysql import database_exists, query
    from burlap.require.mysql import database

    with settings(mysql_user='root', mysql_password=MYSQL_ROOT_PASSWORD):
        try:
            database('mydb', owner='myuser')
            assert database_exists('mydb')
        finally:
            query('DROP DATABASE mydb;')


def test_run_query_as_a_specific_user(mysql_server, mysql_user):

    from burlap.mysql import query

    with settings(mysql_user='myuser', mysql_password='foo'):
        query('select 1;')


def test_run_query_without_supplying_the_password(mysql_server, mysql_user):

    from burlap.mysql import query

    username, password = mysql_user

    try:
        require_file('.my.cnf', contents="[mysql]\npassword={0}".format(password))
        with settings(mysql_user=username):
            query('select 2;', use_sudo=False)
    finally:
        run('rm -f .my.cnf')
