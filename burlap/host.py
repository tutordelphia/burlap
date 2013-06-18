import os
import re

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    run as _run,
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

@task
def set_hostname(name):
    """
    Assigns a name to the server accessible from user space.
    
    Note, we add the name to /etc/hosts since not all programs use
    /etc/hostname to reliably identify the server hostname.
    """
    assert not env.hosts or len(env.hosts) == 1, 'Too many hosts.'
    env.host_hostname = name
    sudo('echo "%(host_hostname)s" > /etc/hostname' % env)
    sudo('echo "127.0.0.1 %(host_hostname)s" | cat - /etc/hosts > /tmp/out && mv /tmp/out /etc/hosts' % env)
    sudo('service hostname restart; sleep 3')
