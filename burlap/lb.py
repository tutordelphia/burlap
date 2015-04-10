import os
import sys
import datetime
import socket
import pprint
import time
import yaml

from fabric.api import (
    env,
    require,
    settings,
    cd,
)
from fabric.contrib import files

from burlap import common
from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
)
from burlap.decorators import task_or_dryrun

def get_boto():
    # Importing this directly causing all the ssl.* commands
    # to show up under lb.boto.connection?!
    try:
        import boto
    except ImportError:
        boto = None
    return boto

EC2 = 'ec2'

env.lb_names = []
env.lb_name = ''
env.lb_type = '' # ec2

@task_or_dryrun
def add():
    """
    Adds a host to one or more load balancers.
    """
    todo

@task_or_dryrun
def remove():
    """
    Removes a host to one or more load balancers.
    """
    todo
