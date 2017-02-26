# 
# import pytest
# 
# 
# pytestmark = pytest.mark.network
# 
# 
# @pytest.fixture(scope='module')
# def postgres_server():
#     from burlap.require.postgresql import server
#     server()
# 
# 
# @pytest.yield_fixture(scope='module')
# def postgres_user():
#     from burlap.postgresql import drop_user
#     from burlap.require.postgresql import user
#     name = 'pguser'
#     user(name, password='s3cr3t')
#     yield name
#     drop_user(name)
# 
# 
# def test_create_and_drop_user(postgres_server):
#     from burlap.postgresql import create_user, drop_user, user_exists
# 
#     create_user('alice', password='1234')
#     assert user_exists('alice')
# 
#     drop_user('alice')
#     assert not user_exists('alice')
# 
# 
# def test_require_user(postgres_server):
#     from burlap.postgresql import user_exists, drop_user
#     from burlap.require.postgresql import user
# 
#     user('bob', password='foo')
# 
#     assert user_exists('bob')
# 
#     drop_user('bob')
# 
# 
# def test_require_database(postgres_server, postgres_user):
#     from burlap.postgresql import database_exists, drop_database
#     from burlap.require.postgresql import database
# 
#     database('pgdb', postgres_user)
# 
#     assert database_exists('pgdb')
# 
#     drop_database('pgdb')
