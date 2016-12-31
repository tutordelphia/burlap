from __future__ import print_function

import re

from fabric.api import (
    env,
    local,
    settings,
    hide,
    task,
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
        output = local('vagrant ssh-config %s' % name, capture=True)

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


def _to_int(val):
    try:
        return int(val)
    except ValueError:
        return val
        

@task_or_dryrun
def version():
    """
    Get the Vagrant version.
    """
    with settings(hide('running', 'warnings'), warn_only=True):
        res = local_or_dryrun('vagrant --version', capture=True)
    if res.failed:
        return None
    line = res.splitlines()[-1]
    version = re.match(r'Vagrant (?:v(?:ersion )?)?(.*)', line).group(1)
    return tuple(_to_int(part) for part in version.split('.'))


@task_or_dryrun
def setup(name=''):
    _settings = _get_settings(ssh_config(name=name))
    if get_verbose():
        print(_settings)
    env.update(_settings)

    
@task_or_dryrun
def init():
    local_or_dryrun('vagrant init %(vagrant_box)s' % env)

    
@task_or_dryrun
def up():
    local_or_dryrun('vagrant up --provider=%(vagrant_provider)s' % env)

    
@task_or_dryrun
def shell():
    setup()
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
    setup()
    hostname, port = env.host_string.split('@')[-1].split(':')
    local_or_dryrun((
        'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no '
        '-i %s %s@%s -p %s') % (
        env.key_filename, env.user, hostname, port))


def _settings_dict(config):
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


@task
def vagrant(name=''):
    """
    Run the following tasks on a vagrant box.

    First, you need to import this task in your ``fabfile.py``::

        from fabric.api import *
        from burlap.vagrant import vagrant

        @task
        def some_task():
            run('echo hello')

    Then you can easily run tasks on your current Vagrant box::

        $ fab vagrant some_task

    """
    config = ssh_config(name)

    extra_args = _settings_dict(config)
    env.update(extra_args)


def vagrant_settings(name='', *args, **kwargs):
    """
    Context manager that sets a vagrant VM
    as the remote host.

    Use this context manager inside a task to run commands
    on your current Vagrant box::

        from burlap.vagrant import vagrant_settings

        with vagrant_settings():
            run('hostname')
    """
    config = ssh_config(name)

    extra_args = _settings_dict(config)
    kwargs.update(extra_args)

    return settings(*args, **kwargs)


def status(name='default'):
    """
    Get the status of a vagrant machine
    """
    machine_states = dict(_status())
    return machine_states[name]


def _status():
    if version() >= (1, 4):
        return _status_machine_readable()
    else:
        return _status_human_readable()


def _status_machine_readable():
    with settings(hide('running')):
        output = local('vagrant status --machine-readable', capture=True)
    tuples = [tuple(line.split(',')) for line in output.splitlines() if line.strip() != '']
    return [(target, data) for timestamp, target, type_, data in tuples if type_ == 'state-human-short']


def _status_human_readable():
    with settings(hide('running')):
        output = local('vagrant status', capture=True)
    lines = output.splitlines()[2:]
    states = []
    for line in lines:
        if line == '':
            break
        target = line[:25].strip()
        state = re.match(r'(.{25}) ([^\(]+)( \(.+\))?$', line).group(2)
        states.append((target, state))
    return states


def machines():
    """
    Get the list of vagrant machines
    """
    return [name for name, state in _status()]


def base_boxes():
    """
    Get the list of vagrant base boxes
    """
    return sorted(list(set([name for name, provider in _box_list()])))


def _box_list():
    if version() >= (1, 4):
        return _box_list_machine_readable()
    else:
        return _box_list_human_readable()


def _box_list_machine_readable():
    with settings(hide('running')):
        output = local('vagrant box list --machine-readable', capture=True)
    tuples = [tuple(line.split(',')) for line in output.splitlines() if line.strip() != '']
    res = []
    for timestamp, target, type_, data in tuples:
        if type_ == 'box-name':
            box_name = data
        elif type_ == 'box-provider':
            box_provider = data
            res.append((box_name, box_provider))
        else:
            raise ValueError('Unknown item type')
    return res


def _box_list_human_readable():
    with settings(hide('running')):
        output = local('vagrant box list', capture=True)
    lines = output.splitlines()
    res = []
    for line in lines:
        box_name = line[:25].strip()
        mo = re.match(r'.{25} \((.+)\)$', line)
        box_provider = mo.group(1) if mo is not None else 'virtualbox'
        res.append((box_name, box_provider))
    return res
