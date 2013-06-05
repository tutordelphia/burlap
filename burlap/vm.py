import os
import sys
import datetime
import socket
import pprint

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

try:
    import boto
except ImportError:
    boto = None

EC2 = 'ec2'

env.vm_type = None

def _ec2():
    assert 'AWS_CREDENTIAL_FILE' in os.environ, \
        'AWS environment variables not set.'
    return boto.connect_ec2()

def _ec2_fetch_instances():
    return sum(map(lambda r: r.instances, _ec2().get_all_instances()), [])

def _ec2_fetch_running_instances():
    instances = filter(lambda i: i.state == 'running', _ec2_fetch_instances())
    instances.reverse()
    return instances

@task
def list():
    require('vm_type')
    assert env.vm_type, 'No VM type specified.'
    env.vm_type = (env.vm_type or '').lower()
    data = type(env)()
    if env.vm_type == EC2:
        for instance in _ec2_fetch_running_instances():
            name = instance.tags.get('Name')
            data.setdefault(name, type(env)())
            data[name]['id'] = instance.id
            data[name]['dns_name'] = instance.dns_name
            data[name]['ip'] = socket.gethostbyname(instance.dns_name)
        pprint.pprint(data, indent=4)
        return data
    else:
        raise NotImplementedError
    