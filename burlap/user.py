import os
import re

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    #run as _run,
    run,
    settings,
    sudo,
    cd,
    task,
)

from fabric.contrib import files
from fabric.tasks import Task

from burlap.common import (
    run,
    put,
    SITE,
    ROLE,
    render_remote_paths,
    render_to_file,
    find_template,
)

env.user_tmp_sudoers_fn = '/tmp/sudoers'
env.user_groups = []
env.user_key_type = 'rsa' # e.g. rsa|dsa
env.user_key_bits = 2048 # e.g. 1024, 2048, or 4096
env.user_key_filename = None
env.user_home_template = '/home/%(user_username)s'

@task
def create(username):
    """
    Creates a user with the given username.
    """
    sudo('adduser %s' % username)

@task
def togroups(user=None, groups=None):
    """
    Adds the user to the given list of groups.
    """
    user = user or env.user
    groups = groups or env.user_groups
    if isinstance(groups, basestring):
        groups = [_ for _ in groups.split(',') if _.strip()]
    for group in groups:
        env.user_username = user
        env.user_group = group
        sudo('adduser %(user_username)s %(user_group)s' % env)

@task
def generate_keys():
    """
    Generates *.pem and *.pub key files suitable for setting up passwordless SSH.
    """
    env.user_key_filename = env.user_key_filename or env.key_filename
    local('ssh-keygen -t %(user_key_type)s -b %(user_key_bits)s -f %(user_key_filename)s' % env)
    if env.user_key_filename.endswith('.pem'):
        src = env.user_key_filename+'.pub'
        dst = (env.user_key_filename+'.pub').replace('.pem', '')
        print src, dst
        os.rename(src, dst)

@task
def passwordless(username=None, pubkey=None):
    """
    Configures the user to use an SSL key without a password.
    Assumes you've run generate_keys() first.
    """
    env.user_username = username or env.user
    env.user_pubkey = pubkey or env.key_filename
    assert os.path.isfile(env.user_pubkey), \
        'Public key file "%s" does not exist.' % (env.user_pubkey,)
    
    first = os.path.splitext(env.user_pubkey)[0]
    env.user_pubkey = first+'.pub'
    env.user_pemkey = first+'.pem'
    env.user_home = env.user_home_template % env
    
    # Upload the SSH key.
    put(local_path=env.user_pubkey)
    sudo('mkdir -p %(user_home)s/.ssh' % env)
    sudo('cat %(put_remote_path)s >> %(user_home)s/.ssh/authorized_keys' % env)
    sudo('rm -f %(put_remote_path)s' % env)
    
    # Disable password.
    sudo('cp /etc/sudoers %(user_tmp_sudoers_fn)s' % env)
    sudo('echo "%(user_username)s ALL=(ALL) NOPASSWD: ALL" >> %(user_tmp_sudoers_fn)s' % env)
    sudo('sudo EDITOR="cp %(user_tmp_sudoers_fn)s" visudo' % env)
    
    sudo('service ssh reload')
    
    print 'You should now be able to login with:'
    print '\tssh -i %(user_pemkey)s %(user_username)s@%(host_string)s' % env
    