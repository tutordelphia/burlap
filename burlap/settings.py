"""
Inspects and manipulates settings files.
"""

import os
import re
from pprint import pprint
import types

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
from fabric.tasks import Task

from burlap import common
from burlap.common import DJANGO, ALL

#class MyTask(Task):
#    name = "testtask"
#    def run(self, environment, domain="whatever.com"):
##        run("git clone foo")
##        sudo("service apache2 restart")
#        pass
#
#class Component(object):
#    
#    def __init__(self):
#        import inspect
#        
#        self.tasks = []
#        self.tasks.append(MyTask())
#        
#        stack = inspect.stack()
#        fab_frame = None
#        for frame_obj, script_fn, line, _, _, _ in stack:
#            print 'settings.fab_frame.script:',script_fn,__file__,__file__ in script_fn
#            if script_fn in __file__:
#                fab_frame = frame_obj
#                break
#        print 'settings.fab_frame:',fab_frame
#        if not fab_frame:
#            return
#        locals_ = fab_frame.f_locals
#        for task in self.tasks:
#            locals_[task.name] = task
#    
#    @task
#    def anothertask(self):
#        todo
#
#Component()

@task
def list(keyword=''):
    """
    Displays a list of all environment key/value pairs for the current role.
    """
    keyword = keyword.strip().lower()
    max_len = max(len(k) for k in env.iterkeys())
    keyword_found = False
    for k in sorted(env.iterkeys()):
        if keyword and keyword not in k.lower():
            continue
        keyword_found = True
        #print '%s: %s' % (k, env[k])
        print '%s: ' % (k.ljust(max_len),),
        pprint(env[k], indent=4)
    if keyword:
        if not keyword_found:
            print 'Keyword "%s" not found.' % keyword

@task
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = {}
    # Record settings.
    data['settings'] = dict(
        (k, v)
        for k,v in env.iteritems()
        if not isinstance(v, types.GeneratorType) and k.strip() and not k.startswith('_') and not callable(v)
    )
    # Record tarball hash.
    # Record database migrations.
    # Record media hash.
    return data

def compare_manifest(data=None):
    """
    Called before a deployment, given the data returned by record_manifest(),
    for determining what, if any, tasks need to be run to make the target
    server reflect the current settings within the current context.
    """

#TODO:unnecessary?
#common.manifest_recorder[ALL.upper()] = record_manifest
#common.manifest_comparer[ALL.upper()] = compare_manifest
