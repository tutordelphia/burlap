
from fabric.api import (
    env,
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
def vagrant():
    env.user = 'vagrant'
    env.hosts = ['127.0.0.1:2222']
    result = local('vagrant ssh-config | grep IdentityFile', capture=True)
    env.key_filename = result.split()[1]
    env.is_local = True
    env.shell_load_dj = False
    env.shell_interactive_shell_str = env.vagrant_shell_command
    
@task_or_dryrun
def init():
    local_or_dryrun('vagrant init %(vagrant_box)s' % env)
    
@task_or_dryrun
def up():
    local_or_dryrun('vagrant up --provider=%(vagrant_provider)s' % env)
    
@task_or_dryrun
def shell():
    local_or_dryrun(env.vagrant_shell_command)
    
@task_or_dryrun
def destroy():
    local_or_dryrun('vagrant destroy' % env)
