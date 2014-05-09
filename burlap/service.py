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
    SITE,
    ROLE,
)

@task
def configure():
    """
    Applies one-time settings changes to the host, usually to initialize the service.
    """
    print 'env.services:',env.services
    for service in list(env.services):
        service = service.strip().upper()
        funcs = common.service_configurators.get(service, [])
        if funcs:
            print '!'*80
            print 'Configuring service %s...' % (service,)
            for func in funcs:
                print 'Function:',func
                func()

@task
def pre_deploy():
    """
    Runs methods services have requested be run before each deployment.
    """
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_pre_deployers.get(service)
        if funcs:
            print 'Running pre-deployments for service %s...' % (service,)
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
def post_deploy():
    """
    Runs methods services have requested be run before after deployment.
    """
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_post_deployers.get(service)
        if funcs:
            print 'Running post-deployments for service %s...' % (service,)
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

@task
def stop():
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_stoppers.get(service)
        if funcs:
            print 'Restarting service %s...' % (service,)
            for func in funcs:
                func()
                
def is_selected(name):
    name = name.strip().upper()
    for service in env.services:
        if service.strip().upper() == name:
            return True
    return False

@task
def pre_db_dump():
    """
    Runs methods services that have requested to be run before each
    database dump.
    """
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_pre_db_dumpers.get(service)
        if funcs:
            print 'Running pre-database dump for service %s...' % (service,)
            for func in funcs:
                func()

@task
def post_db_dump():
    """
    Runs methods services that have requested to be run before each
    database dump.
    """
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_post_db_dumpers.get(service)
        if funcs:
            print 'Running post-database dump for service %s...' % (service,)
            for func in funcs:
                func()
