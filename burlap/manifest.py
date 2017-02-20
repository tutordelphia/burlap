"""
Tracks changes between deployments.
"""
from __future__ import print_function

#TODO: remove? largely deprecated, use the deploy module instead

from fabric.api import (
    env,
    runs_once,
)

from burlap import common
from burlap.decorators import task_or_dryrun

@task_or_dryrun
@runs_once
def show(name):
    name = name.strip().lower()
    func = common.manifest_recorder[name]
    ret = func()
    print(ret)

@task_or_dryrun
@runs_once
def get_current(name):
    name = name.strip().lower()
    func = common.manifest_recorder[name]
    return func()
    
@task_or_dryrun
@runs_once
def get_last(name):
    from burlap.deploy import get_last_thumbprint
    name = common.assert_valid_satchel(name)
    last_thumbprint = get_last_thumbprint()
    if last_thumbprint:
        if name in last_thumbprint:
            return last_thumbprint.get(name, type(env)())
    return type(env)()
    
@task_or_dryrun
@runs_once
def changed(name):
    from burlap.deploy import get_last_thumbprint
    name = name.strip().lower()
    if name not in common.manifest_recorder:
        print('No manifest recorder has been registered for component "%s"' % name)
    else:
        last_thumbprint = get_last_thumbprint()
        if last_thumbprint:
            if name in last_thumbprint:
                last_manifest = last_thumbprint[name]
                current_manifest = common.manifest_recorder[name]()
                if last_manifest == current_manifest:
                    print('No')
                    return False
                else:
                    print('Yes')
                    return True
            else:
                print('Yes, first deployment for this component.')
                return True
        else:
            print('Yes, first deployment.')
            return True
