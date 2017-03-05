 
from burlap.files import file # pylint: disable=redefined-builtin
from burlap.user import user

is_dir = file.is_dir

def test_create_user():
    try:
        user.create('user1', create_home=False, password=False)
        assert user.exists('user1')
        assert not is_dir('/home/user1')
    finally:
        user.sudo('userdel -r user1')
