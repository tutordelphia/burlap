import os
import sys
import datetime
import socket
import pprint
import time
import yaml

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

from burlap import common
from burlap.common import run, put

try:
    import boto
except ImportError:
    boto = None

EC2 = 'ec2'

env.lb_names = []
env.lb_name = ''
env.lb_type = '' # ec2

@task
def add():
    """
    Adds a host to one or more load balancers.
    """
    todo

@task
def remove():
    """
    Removes a host to one or more load balancers.
    """
    todo
