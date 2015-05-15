import re

from fabric.api import (
    env,
    local as _local
)

import burlap

#from burlap import user, package, pip, service, file, tarball
from burlap.common import (
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    run_or_dryrun,
)
from burlap.decorators import task_or_dryrun

env.vagrant_box = '?'
env.vagrant_provider = '?'
env.vagrant_shell_command = 'vagrant ssh'

@task_or_dryrun
def set():
    result = _local('vagrant ssh-config', capture=True)
    
    hostname = re.findall(r'HostName\s+([^\n]+)', result)[0]
    port = re.findall(r'Port\s+([^\n]+)', result)[0]
    env.hosts = ['%s:%s' % (hostname, port)]
    
    env.user = re.findall(r'User\s+([^\n]+)', result)[0]
    env.key_filename = re.findall(r'IdentityFile\s+([^\n]+)', result)[0]
    
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
