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

@task
def create(username):
    """
    Creates a user with the given username.
    """
    sudo('adduser %s' % username)

@task
def togroups(username, groups):
    """
    Adds the user to the given list of groups.
    """
    if isinstance(groups, basestring):
        groups = [_ for _ in groups.split(',') if _.strip()]
    for group in groups:
        env.user_username = username
        env.user_group = group
        sudo('adduser %(user_username)s %(user_group)s' % env)

@task
def passwordless(username, pubkey):
    """
    Configures the user to use an SSL key without a password.
    """
    env.user_username = username
    env.user_pubkey = pubkey
    assert os.path.isfile(pubkey)
    
    first = os.path.splitext(pubkey)[0]
    env.user_pemkey = first+'.pem'
    
    # Upload the SSH key.
    put(local_path=pubkey)
    sudo('mkdir -p /home/%(user_username)s/.ssh' % env)
    sudo('cat %(put_remote_path)s >> /home/%(user_username)s/.ssh/authorized_keys' % env)
    sudo('rm -f %(put_remote_path)s' % env)
    
    # Disable password.
    sudo('cp /etc/sudoers %(user_tmp_sudoers_fn)s' % env)
    sudo('echo "%(user_username)s ALL=(ALL) NOPASSWD: ALL" >> %(user_tmp_sudoers_fn)s' % env)
    sudo('sudo EDITOR="cp %(user_tmp_sudoers_fn)s" visudo' % env)
    
    sudo('service ssh reload')
    
    print 'You should now be able to login with:'
    print '\tssh -i %(user_pemkey)s %(user_username)s@%(host_string)s' % env
    