import os
 
from burlap.files import is_dir
from burlap.common import (
    sudo_or_dryrun,
)

def test_create_user():
    from burlap.user import create, exists
 
    try:
        create('user1', create_home=False)
 
        assert exists('user1')
        assert not is_dir('/home/user1')
 
    finally:
        sudo_or_dryrun('userdel -r user1')
