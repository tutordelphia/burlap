import os
import sys
import datetime

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

from burlap.common import run, put

env.tarball_exclusions = [
    'settings_local.py',
    '*.pyc',
    'manage',
    '*.svn',
    '*.tar.gz',
]

@task
def create():
    """
    Generates a tarball of all deployable code.
    """
    print 'Creating tarball...'
    env.src_dir = os.path.abspath(env.src_dir)
    env.tarball_name = 'code-%(role)s.tar' % env
    env.tarball_exclusions_str = ' '.join("--exclude='%s'" % _ for _ in env.tarball_exclusions)
    local("tar %(tarball_exclusions_str)s --exclude-vcs --create --verbose --file %(tarball_name)s %(src_dir)" % env)

@task
def deploy():
    """
    Copies the tarball to the target server.
    """
    todo
