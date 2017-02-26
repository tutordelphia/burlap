 
from burlap.files import is_dir
from burlap.user import user

def test_create_user():
    try:
        user.create('user1', create_home=False)
        assert user.exists('user1')
        assert not is_dir('/home/user1')
    finally:
        user.sudo('userdel -r user1')
