import re

from fabric.api import (
    env,
    local as _local,
    settings,
    hide,
)

import burlap

#from burlap import user, package, pip, service, file, tarball
from burlap.common import (
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    run_or_dryrun,
    get_verbose,
)
from burlap.decorators import task_or_dryrun

env.vagrant_box = '?'
env.vagrant_provider = '?'
env.vagrant_shell_command = 'vagrant ssh'

def ssh_config(name=''):
    """
    Get the SSH parameters for connecting to a vagrant VM.
    """
    with settings(hide('running')):
        output = _local('vagrant ssh-config %s' % name, capture=True)

    config = {}
    for line in output.splitlines()[1:]:
        key, value = line.strip().split(' ', 2)
        config[key] = value
    return config

def _get_settings(config):
    settings = {}

    user = config['User']
    hostname = config['HostName']
    port = config['Port']

    # Build host string
    host_string = "%s@%s:%s" % (user, hostname, port)

    settings['user'] = user
    settings['hosts'] = [host_string]
    settings['host_string'] = host_string

    # Strip leading and trailing double quotes introduced by vagrant 1.1
    settings['key_filename'] = config['IdentityFile'].strip('"')

    settings['forward_agent'] = (config.get('ForwardAgent', 'no') == 'yes')
    settings['disable_known_hosts'] = True

    return settings

@task_or_dryrun
def set(name=''):
    _settings = _get_settings(ssh_config(name=name))
    if get_verbose():
        print _settings
    env.update(_settings)
    
@task_or_dryrun
def init():
    local_or_dryrun('vagrant init %(vagrant_box)s' % env)
    
@task_or_dryrun
def up():
    local_or_dryrun('vagrant up --provider=%(vagrant_provider)s' % env)
    
@task_or_dryrun
def shell():
    set()
    local_or_dryrun(env.vagrant_shell_command)
    
@task_or_dryrun
def destroy():
    local_or_dryrun('vagrant destroy' % env)

@task_or_dryrun
def upload(src, dst=None):
    put_or_dryrun(local_path=src, remote_path=dst)

#http://serverfault.com/a/758017/41252
@task_or_dryrun
def ssh():
    set()
    hostname, port = env.host_string.split('@')[-1].split(':')
    local_or_dryrun('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s@%s -p %s' % (
        env.key_filename, env.user, hostname, port))
