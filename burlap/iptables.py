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

from burlap.common import run, put, render_to_string

env.iptables_ssh_port = 22

def configure():
    todo

def unconfigure():
    todo