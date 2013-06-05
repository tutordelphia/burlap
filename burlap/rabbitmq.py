import os
import re

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

env.rabbitmq_erlang_cookie = None

@task
def configure():
    assert env.rabbitmq_erlang_cookie
    todo