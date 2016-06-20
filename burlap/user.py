from __future__ import print_function

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

from burlap.constants import *
from burlap import Satchel

from burlap import common
from burlap.common import (
    QueuedCommand,
)

from pipes import quote
import posixpath
import random
import string

from fabric.api import hide, run, settings, sudo, local

from burlap.group import (
    exists as _group_exists,
    create as _group_create,
)
from burlap.files import uncommented_lines
from burlap.utils import run_as_root


def exists(name):
    """
    Check if a user exists.
    """
    with settings(hide('running', 'stdout', 'warnings'), warn_only=True):
        return run('getent passwd %(name)s' % locals()).succeeded


_SALT_CHARS = string.ascii_letters + string.digits + './'


def _crypt_password(password):
    from crypt import crypt
    random.seed()
    salt = ''
    for _ in range(2):
        salt += random.choice(_SALT_CHARS)
    crypted_password = crypt(password, salt)
    return crypted_password


def create(name, comment=None, home=None, create_home=None, skeleton_dir=None,
           group=None, create_group=True, extra_groups=None, password=None,
           system=False, shell=None, uid=None, ssh_public_keys=None,
           non_unique=False):
    """
    Create a new user and its home directory.

    If *create_home* is ``None`` (the default), a home directory will be
    created for normal users, but not for system users.
    You can override the default behaviour by setting *create_home* to
    ``True`` or ``False``.

    If *system* is ``True``, the user will be a system account. Its UID
    will be chosen in a specific range, and it will not have a home
    directory, unless you explicitely set *create_home* to ``True``.

    If *shell* is ``None``, the user's login shell will be the system's
    default login shell (usually ``/bin/sh``).

    *ssh_public_keys* can be a (local) filename or a list of (local)
    filenames of public keys that should be added to the user's SSH
    authorized keys (see :py:func:`burlap.user.add_ssh_public_keys`).

    Example::

        import burlap

        if not burlap.user.exists('alice'):
            burlap.user.create('alice')

        with cd('/home/alice'):
            # ...

    """

    # Note that we use useradd (and not adduser), as it is the most
    # portable command to create users across various distributions:
    # http://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/useradd.html

    args = []
    if comment:
        args.append('-c %s' % quote(comment))
    if home:
        args.append('-d %s' % quote(home))
    if group:
        args.append('-g %s' % quote(group))
        if create_group:
            if not _group_exists(group):
                _group_create(group)
    if extra_groups:
        groups = ','.join(quote(group) for group in extra_groups)
        args.append('-G %s' % groups)

    if create_home is None:
        create_home = not system
    if create_home is True:
        args.append('-m')
    elif create_home is False:
        args.append('-M')

    if skeleton_dir:
        args.append('-k %s' % quote(skeleton_dir))
    if password:
        crypted_password = _crypt_password(password)
        args.append('-p %s' % quote(crypted_password))
    if system:
        args.append('-r')
    if shell:
        args.append('-s %s' % quote(shell))
    if uid:
        args.append('-u %s' % uid)
        if non_unique:
            args.append('-o')
    args.append(name)
    args = ' '.join(args)
    run_as_root('useradd %s' % args)

    if ssh_public_keys:
        if isinstance(ssh_public_keys, basestring):
            ssh_public_keys = [ssh_public_keys]
        add_ssh_public_keys(name, ssh_public_keys)


def modify(name, comment=None, home=None, move_current_home=False, group=None,
           extra_groups=None, login_name=None, password=None, shell=None,
           uid=None, ssh_public_keys=None, non_unique=False):
    """
    Modify an existing user.

    *ssh_public_keys* can be a (local) filename or a list of (local)
    filenames of public keys that should be added to the user's SSH
    authorized keys (see :py:func:`burlap.user.add_ssh_public_keys`).

    Example::

        import burlap

        if burlap.user.exists('alice'):
            burlap.user.modify('alice', shell='/bin/sh')

    """

    args = []
    if comment:
        args.append('-c %s' % quote(comment))
    if home:
        args.append('-d %s' % quote(home))
        if move_current_home:
            args.append('-m')
    if group:
        args.append('-g %s' % quote(group))
    if extra_groups:
        groups = ','.join(quote(group) for group in extra_groups)
        args.append('-G %s' % groups)
    if login_name:
        args.append('-l %s' % quote(login_name))
    if password:
        crypted_password = _crypt_password(password)
        args.append('-p %s' % quote(crypted_password))
    if shell:
        args.append('-s %s' % quote(shell))
    if uid:
        args.append('-u %s' % quote(uid))
        if non_unique:
            args.append('-o')

    if args:
        args.append(name)
        args = ' '.join(args)
        run_as_root('usermod %s' % args)

    if ssh_public_keys:
        if isinstance(ssh_public_keys, basestring):
            ssh_public_keys = [ssh_public_keys]
        add_ssh_public_keys(name, ssh_public_keys)


def home_directory(name):
    """
    Get the absolute path to the user's home directory

    Example::

        import burlap

        home = burlap.user.home_directory('alice')

    """
    with settings(hide('running', 'stdout')):
        return run('echo ~' + name)


def local_home_directory(name=''):
    """
    Get the absolute path to the local user's home directory

    Example::

        import burlap

        local_home = burlap.user.local_home_directory()

    """
    with settings(hide('running', 'stdout')):
        return local('echo ~' + name, capture=True)


def authorized_keys(name):
    """
    Get the list of authorized SSH public keys for the user
    """

    ssh_dir = posixpath.join(home_directory(name), '.ssh')
    authorized_keys_filename = posixpath.join(ssh_dir, 'authorized_keys')

    return uncommented_lines(authorized_keys_filename, use_sudo=True)


def add_ssh_public_key(name, filename):
    """
    Add a public key to the user's authorized SSH keys.

    *filename* must be the local filename of a public key that should be
    added to the user's SSH authorized keys.

    Example::

        import burlap

        burlap.user.add_ssh_public_key('alice', '~/.ssh/id_rsa.pub')

    """

    add_ssh_public_keys(name, [filename])


def add_ssh_public_keys(name, filenames):
    """
    Add multiple public keys to the user's authorized SSH keys.

    *filenames* must be a list of local filenames of public keys that
    should be added to the user's SSH authorized keys.

    Example::

        import burlap

        burlap.user.add_ssh_public_keys('alice', [
            '~/.ssh/id1_rsa.pub',
            '~/.ssh/id2_rsa.pub',
        ])

    """

    from burlap.require.files import (
        directory as _require_directory,
        file as _require_file,
    )

    ssh_dir = posixpath.join(home_directory(name), '.ssh')
    _require_directory(ssh_dir, mode='700', owner=name, use_sudo=True)

    authorized_keys_filename = posixpath.join(ssh_dir, 'authorized_keys')
    _require_file(authorized_keys_filename, mode='600', owner=name,
                  use_sudo=True)

    for filename in filenames:

        with open(filename) as public_key_file:
            public_key = public_key_file.read().strip()

        # we don't use fabric.contrib.files.append() as it's buggy
        if public_key not in authorized_keys(name):
            sudo('echo %s >>%s' % (quote(public_key),
                                   quote(authorized_keys_filename)))


def add_host_keys(name, hostname):
    """
    Add all public keys of a host to the user's SSH known hosts file
    """

    from burlap.require.files import (
        directory as _require_directory,
        file as _require_file,
    )

    ssh_dir = posixpath.join(home_directory(name), '.ssh')
    _require_directory(ssh_dir, mode='700', owner=name, use_sudo=True)

    known_hosts_filename = posixpath.join(ssh_dir, 'known_hosts')
    _require_file(known_hosts_filename, mode='644', owner=name, use_sudo=True)

    known_hosts = uncommented_lines(known_hosts_filename, use_sudo=True)

    with hide('running', 'stdout'):
        res = run('ssh-keyscan -t rsa,dsa %s 2>/dev/null' % hostname)
    for host_key in res.splitlines():
        if host_key not in known_hosts:
            sudo('echo %s >>%s' % (quote(host_key),
                                   quote(known_hosts_filename)))


#DEPRECATED
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

class UserSatchel(Satchel):
    
    name = 'user'
    
    tasks = (
        'configure',
        'togroups',
        'configure_keyless',
        'passwordless',
        'create',
    )
    
    def set_defaults(self):
                
        self.env.tmp_sudoers_fn = '/tmp/sudoers'
        
        self.env.key_type = 'rsa' # e.g. rsa|dsa
        self.env.key_bits = 2048 # e.g. 1024, 2048, or 4096
        self.env.key_filename_template = 'roles/{ROLE}/{host}-{username}.pem'
        self.env.key_perms = '600'
        
        self.env.home_template = '/home/{username}'
        #self.env.passwordless = True
        self.env.groups = {} # {username:[groups]}
        self.env.passwordless = {} # {username:True/False}
        self.env.passwords = {} # {user: password}

    def configure_keyless(self):
        generate_keys()
        passwordless()

    def togroups(self, user, groups):
        """
        Adds the user to the given list of groups.
        """
        
        r = self.local_renderer
        
        if isinstance(groups, basestring):
            groups = [_.strip() for _ in groups.split(',') if _.strip()]
        for group in groups:
            r.env.username = user
            r.env.group = group
            r.sudo('groupadd --force {group}')
            r.sudo('adduser {username} {group}')

    def passwordless(self, username, pubkey):
        """
        Configures the user to use an SSL key without a password.
        Assumes you've run generate_keys() first.
        """
        
        r = self.local_renderer
        
        r.env.username = username
        r.env.pubkey = pubkey
        if not self.dryrun:
            assert os.path.isfile(r.env.pubkey), \
                'Public key file "%s" does not exist.' % (str(r.env.pubkey),)
        
        first = os.path.splitext(r.env.pubkey)[0]
        r.env.pubkey = first+'.pub'
        r.env.pemkey = first+'.pem'
        r.env.home = r.env.home_template.format(username=username)
        
        # Upload the SSH key.
        put_remote_paths = self.put(local_path=r.env.pubkey)
        print('put_remote_path:', put_remote_paths)
        r.env.put_remote_path = put_remote_paths[0]
        r.sudo('mkdir -p {home}/.ssh' % env)
        r.sudo('cat {put_remote_path} >> {home}/.ssh/authorized_keys')
        r.sudo('rm -f {put_remote_path}')
        
        # Disable password.
        r.sudo('cp /etc/sudoers {tmp_sudoers_fn}')
        r.sudo('echo "{username} ALL=(ALL) NOPASSWD: ALL" >> {tmp_sudoers_fn}')
        r.sudo('sudo EDITOR="cp {tmp_sudoers_fn}" visudo')
        
        r.sudo('service ssh reload')
        
        print('You should now be able to login with:')
        r.env.host_string = self.genv.hostname_hostname
        r.comment('\tssh -i {pemkey} {username}@{host_string}')

    def generate_keys(self, username, host):
        """
        Generates *.pem and *.pub key files suitable for setting up passwordless SSH.
        """
        
        r = self.local_renderer
        
        #r.env.key_filename = r.env.key_filename or env.key_filename
        #assert r.env.key_filename, 'r.env.key_filename or env.key_filename must be set. e.g. roles/role/app_name-role.pem'
        r.env.key_filename = self.env.key_filename_template.format(
            ROLE=self.genv.ROLE,
            host=host,
            username=username,
        )
#         print('r.env.key_filename:', r.env.key_filename)
        if not os.path.isfile(r.env.key_filename):
            r.local("ssh-keygen -t {key_type} -b {key_bits} -f {key_filename} -N ''")
            r.local('chmod {key_perms} {key_filename}')
            if r.env.key_filename.endswith('.pem'):
                src = r.env.key_filename+'.pub'
                dst = (r.env.key_filename+'.pub').replace('.pem', '')
#                 print('generate_keys:', src, dst)
                r.env.src = src
                r.env.dst = dst
                r.local('mv {src} {dst}')
        return r.env.key_filename
    
    def create(self, username):
        """
        Creates a user with the given username.
        """
        r = self.local_renderer
        r.env.username = username
        r.sudo('adduser {username}')
        
    def configure(self):
        r = self.local_renderer
        
        for username, groups in r.env.groups.items():
            self.togroups(username, groups)
            
        for username, is_passwordless in r.env.passwordless.items():
            if is_passwordless:
                pubkey = self.generate_keys(username=username, host=self.genv.hostname_hostname)
                self.passwordless(username=username, pubkey=pubkey)
                
        for username, password in r.env.passwords.items():
            r.env.username = username
            r.env.password = password
            r.sudo('echo "{username}:{password}"|chpasswd')
    
    configure.deploy_before = []

user = UserSatchel()
