from __future__ import print_function
import os
import sys
import re
import traceback

from fabric.api import (
    env,
    require,
    settings,
    cd,
    task,
)

from fabric.contrib import files
from fabric.tasks import Task

from burlap import common
from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    get_dryrun,
    SITE,
    ROLE,
)
from burlap.decorators import task_or_dryrun

@task_or_dryrun
def configure():
    """
    Applies one-time settings changes to the host, usually to initialize the service.
    """
    
    print('env.services:', env.services)
    for service in list(env.services):
        service = service.strip().upper()
        funcs = common.service_configurators.get(service, [])
        if funcs:
            print('!'*80)
            print('Configuring service %s...' % (service,))
            for func in funcs:
                print('Function:', func)
                if not get_dryrun():
                    func()

@task_or_dryrun
def pre_deploy():
    """
    Runs methods services have requested be run before each deployment.
    """
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_pre_deployers.get(service)
        if funcs:
            print('Running pre-deployments for service %s...' % (service,))
            for func in funcs:
                func()
                
@task_or_dryrun
def deploy():
    """
    Applies routine, typically application-level changes to the service.
    """
    
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_deployers.get(service)
        if funcs:
            print('Deploying service %s...' % (service,))
            for func in funcs:
                if not get_dryrun():
                    func()

@task_or_dryrun
def post_deploy():
    """
    Runs methods services have requested be run before after deployment.
    """
    verbose = common.get_verbose()
    for service in env.services:
        service = service.strip().upper()
        if verbose:
            print('post_deploy:', service)
        funcs = common.service_post_deployers.get(service)
        if funcs:
            if verbose:
                print('Running post-deployments for service %s...' % (service,))
            for func in funcs:
                try:
                    func()
                except Exception as e:
                    print(traceback.format_exc(), file=sys.stderr)

@task_or_dryrun
def restart(name=''):
    name = name.strip().lower()
    _ran = False
    #print common.service_restarters
    for service in env.services:
        service = service.strip().upper()
#         print 'checking', service
        if name and service.lower() != name:
            continue
        srv = common.services.get(service)
        if srv:
            srv.restart()
            _ran = True
            continue
        funcs = common.service_restarters.get(service)
        if funcs:
            print('Restarting service %s...' % (service,))
            for func in funcs:
                if not get_dryrun():
                    func()
                    _ran = True
    if not get_dryrun() and not _ran and name:
        raise Exception, 'No restart command found for service "%s".' % name

@task_or_dryrun
def stop(name=''):
    name = name.strip().lower()
    for service in env.services:
        service = service.strip().upper()
        if name and service.lower() != name:
            continue
        funcs = common.service_stoppers.get(service)
        if funcs:
            print('Restarting service %s...' % (service,))
            for func in funcs:
                func()

@task_or_dryrun
def is_running(name):
    name = name.strip().lower()
    _ran = False
    #print common.service_restarters
    for service in env.services:
        service = service.strip().upper()
#         print 'checking', service
        if name and service.lower() != name:
            continue
        srv = common.services.get(service)
        if srv:
            _ran = True
            print('%s.is_running: %s' % (name, srv.is_running()))
    if not get_dryrun() and not _ran and name:
        raise Exception, 'No restart command found for service "%s".' % name

def is_selected(name):
    name = name.strip().upper()
    for service in env.services:
        if service.strip().upper() == name:
            return True
    return False

@task_or_dryrun
def pre_db_dump():
    """
    Runs methods services that have requested to be run before each
    database dump.
    """
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_pre_db_dumpers.get(service)
        if funcs:
            print('Running pre-database dump for service %s...' % (service,))
            for func in funcs:
                func()

@task_or_dryrun
def post_db_dump():
    """
    Runs methods services that have requested to be run before each
    database dump.
    """
    for service in env.services:
        service = service.strip().upper()
        funcs = common.service_post_db_dumpers.get(service)
        if funcs:
            print('Running post-database dump for service %s...' % (service,))
            for func in funcs:
                func()
