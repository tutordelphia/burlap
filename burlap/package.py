import os

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    sudo,
    task,
)

from burlap.common import (
    get_packager, APT, YUM, ROLE, SITE, put,
    find_template,
)

@task
def install(*args, **kwargs):
    """
    Installs all system packages listed in the appropriate <packager>-requirements.txt.
    """
    packager = get_packager()
    if packager == APT:
        return install_apt(*args, **kwargs)
    elif package == YUM:
        return install_yum(*args, **kwargs)
    else:
        raise Exception, 'Unknown packager: %s' % (packager,)

env.apt_fn = 'apt-requirements.txt'

def install_apt(update=0):
    """
    Installs system packages listed in apt-requirements.txt.
    """
    print 'Installing apt requirements...'
    assert env[ROLE]
    env.apt_fqfn = find_template(env.apt_fn)
    assert os.path.isfile(env.apt_fqfn)
    if not env.is_local:
        put(local_path=env.apt_fqfn)
        env.apt_fqfn = env.put_remote_path
    if int(update):
        sudo('apt-get update -y')
    sudo('apt-get install -y `cat "%(apt_fqfn)s" | tr "\\n" " "`' % env)

env.yum_fn = 'yum-requirements.txt'

def install_yum(update=0):
    """
    Installs system packages listed in yum-requirements.txt.
    """
    print 'Installing yum requirements...'
    assert env[ROLE]
    assert os.path.isfile(env.yum_fn)
    update = int(update)
    env.yum_remote_fn = env.yum_fn
    if env.is_local:
        put(local_path=env.yum_fn)
        env.yum_remote_fn = env.put_remote_fn
    if update:
        sudo('yum update --assumeyes')
    sudo('yum install --assumeyes $(cat %(yum_remote_fn)s)' % env)
