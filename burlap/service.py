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
from fabric.tasks import Task

from burlap import common
from burlap.common import (
    #run,
    put,
    get_settings,
    SITE,
    ROLE,
)

@task
def configure():
    """
    Applies one-time settings changes to the host, usually to initialize the service.
    """
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_configurators.get(service, [])
        if funcs:
            print 'Configuring service %s...' % (service,)
            for func in funcs:
                func()
    
@task
def deploy():
    """
    Applies routine, typically application-level changes to the service.
    """
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_deployers.get(service)
        if funcs:
            print 'Deploying service %s...' % (service,)
            for func in funcs:
                func()

@task
def restart():
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_restarters.get(service)
        if funcs:
            print 'Restarting service %s...' % (service,)
            for func in funcs:
                func()
                