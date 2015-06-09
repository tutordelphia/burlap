import os
import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
    task,
)

from fabric.contrib import files
from fabric.tasks import Task

from burlap import common
from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    SITE,
    ROLE,
    render_to_file,
    find_template,
    QueuedCommand,
)
from burlap.decorators import task_or_dryrun

env.user_tmp_sudoers_fn = '/tmp/sudoers'
env.user_groups = []
env.user_key_type = 'rsa' # e.g. rsa|dsa
env.user_key_bits = 2048 # e.g. 1024, 2048, or 4096
env.user_key_filename = None
env.user_home_template = '/home/%(user_username)s'
env.user_passwordless = True

USER = 'USER'

@task_or_dryrun
def create(username):
    """
    Creates a user with the given username.
    """
    sudo_or_dryrun('adduser %s' % username)

@task_or_dryrun
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
        sudo_or_dryrun('adduser %(user_username)s %(user_group)s' % env)

@task_or_dryrun
def generate_keys():
    """
    Generates *.pem and *.pub key files suitable for setting up passwordless SSH.
    """
    env.user_key_filename = env.user_key_filename or env.key_filename
    assert env.user_key_filename, 'env.user_key_filename or env.key_filename must be set. e.g. roles/role/app_name-role.pem'
    local_or_dryrun("ssh-keygen -t %(user_key_type)s -b %(user_key_bits)s -f %(user_key_filename)s -N ''" % env)
    if env.user_key_filename.endswith('.pem'):
        src = env.user_key_filename+'.pub'
        dst = (env.user_key_filename+'.pub').replace('.pem', '')
        print src, dst
        os.rename(src, dst)

@task_or_dryrun
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
    put_or_dryrun(local_path=env.user_pubkey)
    sudo_or_dryrun('mkdir -p %(user_home)s/.ssh' % env)
    sudo_or_dryrun('cat %(put_remote_path)s >> %(user_home)s/.ssh/authorized_keys' % env)
    sudo_or_dryrun('rm -f %(put_remote_path)s' % env)
    
    # Disable password.
    sudo_or_dryrun('cp /etc/sudoers %(user_tmp_sudoers_fn)s' % env)
    sudo_or_dryrun('echo "%(user_username)s ALL=(ALL) NOPASSWD: ALL" >> %(user_tmp_sudoers_fn)s' % env)
    sudo_or_dryrun('sudo EDITOR="cp %(user_tmp_sudoers_fn)s" visudo' % env)
    
    sudo_or_dryrun('service ssh reload')
    
    print 'You should now be able to login with:'
    print '\tssh -i %(user_pemkey)s %(user_username)s@%(host_string)s' % env

@task_or_dryrun
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = common.get_component_settings(USER)
    data['user'] = env.user
    return data

def compare_manifest(old):
    old = old or {}
    methods = []
    pre = []
    
    # Handle SSH key specification change.
    old_key = (old.get('user_key_type'), old.get('user_key_bits'), old.get('user_key_filename'))
    new_key = (env.get('user_key_type'), env.get('user_key_bits'), env.get('user_key_filename'))
    if old_key != new_key:
        methods.append(QueuedCommand('user.generate_keys', pre=pre))
    
    # Handle username change.
    force_togroups = False
    force_passwordless = env.user_passwordless and old.get('user_passwordless') != env.user_passwordless
    if old.get('user') != env.user:
        force_togroups = True
        force_passwordless = env.user_passwordless
        methods.append(QueuedCommand('user.create', kwargs=dict(username=env.user), pre=pre))
    
    # Handle user group change.
    if force_togroups or old.get('user_groups') != env.user_groups:
        methods.append(QueuedCommand('user.togroups', kwargs=dict(user=env.user, groups=env.user_groups), pre=pre))
    
    # Handle switch to passwordless access.
    #TODO:support different username used for creating passworless user?
    if force_passwordless:
        methods.append(QueuedCommand('user.passwordless', kwargs=dict(username=env.user, pubkey=env.key_filename), pre=pre))
        
    #TODO: Handle switch from passwordless access? Remove old SSH key from remote and local caches?
    
    return methods
    
common.manifest_recorder[USER] = record_manifest
common.manifest_comparer[USER] = compare_manifest

common.add_deployer(USER, 'user.togroups', before=[])
