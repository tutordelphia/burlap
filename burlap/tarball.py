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

from burlap.common import (
    run,
    put,
    render_remote_paths,
)

env.tarball_gzip = True
env.tarball_exclusions = [
    '*_local.py',
    '*.pyc',
    '*.svn',
    '*.tar.gz',
    'static',
]
env.tarball_dir = '.tarball_cache'

def get_tarball_path():
    env.tarball_gzip_flag = ''
    env.tarball_ext = 'tar'
    if env.tarball_gzip:
        env.tarball_gzip_flag = '--gzip'
        env.tarball_ext = 'tgz'
    if not os.path.isdir(env.tarball_dir):
        os.makedirs(env.tarball_dir)
    env.absolute_src_dir = os.path.abspath(env.src_dir)
    env.tarball_path = os.path.abspath('%(tarball_dir)s/code-%(ROLE)s-%(SITE)s.%(tarball_ext)s' % env)
    return env.tarball_path

@task
def create(gzip=1):
    """
    Generates a tarball of all deployable code.
    """
    assert env.SITE, 'Site unspecified.'
    assert env.ROLE, 'Role unspecified.'
    env.tarball_gzip = bool(int(gzip))
    get_tarball_path()
    print 'Creating tarball...'
    env.tarball_exclusions_str = ' '.join(
        "--exclude='%s'" % _ for _ in env.tarball_exclusions)
    cmd = ("cd %(absolute_src_dir)s; " \
        "tar %(tarball_exclusions_str)s --exclude-vcs %(tarball_gzip_flag)s " \
        "--create --verbose --file %(tarball_path)s *") % env
    print cmd
    local(cmd)

@task
def deploy(clean=0):
    """
    Copies the tarball to the target server.
    
    Note, clean=1 will delete any dynamically generated files not included
    in the tarball.
    """
    
    tarball_path = get_tarball_path()
    assert os.path.isfile(tarball_path), \
        'No tarball found. Ensure you ran create() first.'
    put(local_path=env.tarball_path)
    
    env.remote_app_dir = env.remote_app_dir_template % env
    env.remote_app_src_dir = env.remote_app_src_dir_template % env
    env.remote_app_src_package_dir = env.remote_app_src_package_dir_template % env
    
    if int(clean):
        print 'Deleting old remote source...'
        #sudo('[ -d %(remote_app_src_dir)s ] && rm -Rf  %(remote_app_src_dir)s' % env)
        sudo('rm -Rf  %(remote_app_src_dir)s' % env)
        sudo('mkdir -p %(remote_app_src_dir)s' % env)
    
    print 'Extracting tarball...'
    sudo('mkdir -p %(remote_app_src_dir)s' % env)
    sudo('tar -xvzf %(put_remote_path)s -C %(remote_app_src_dir)s' % env)
    
    # Mark executables.
    print 'Marking source files as executable...'
    sudo('chmod +x %(remote_app_src_package_dir)s/*' % env)
    sudo('chmod -R %(apache_chmod)s %(remote_app_src_package_dir)s' % env)
    sudo('chown -R %(apache_user)s:%(apache_group)s %(remote_app_dir)s' % env)
    