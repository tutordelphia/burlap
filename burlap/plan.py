from __future__ import print_function
import os
import gc
import re
import sys
import types
import datetime
import glob
import tempfile

from fabric.api import (
    env,
)
import fabric.contrib.files
import fabric.api

from burlap import common
from burlap.decorators import task_or_dryrun

# Prevent globals from being reset by duplicate imports.
if not 'plan_init' in env:
    #print('creating _originals')
    env.plan_init = True
    env.plan_root = None
    env.plan_originals = {}
_originals = env.plan_originals

class Step(object):
    """
    A single piece of a plan.
    """
    
    def __init__(self, command, host, user=None, key=None, args=[], kwargs={}):
        self.command = command
        self.host = host
        self.user = user
        self.key = key
        # The value entity attributes are set to as a result
        # of executing this step.
        self.args = args
        self.kwargs = kwargs
    
    @property
    def remote_command(self):
        return ("%s %s" % (
            ' '.join(map(str, self.args)),
            ' '.join('%s=%s' % (_k, repr(_v)) for _k, _v in self.kwargs.iteritems())
        )).strip()
    
    def __str__(self):
        user_str = '%s@' % (self.user) if self.user else ''
        return '[%s%s] %s %s' % (
            user_str,
            self.host,
            self.command+':',
            self.remote_command,
        )
    
    def __repr__(self):
        return str(self.__dict__)

class Plan(object):
    """
    A sequence of steps for accomplishing a state change.
    """
    
    def __init__(self, last={}, current={}, verbose=False):
        
        self._steps = []
        
        self.verbose = verbose
        
    @property
    def steps(self):
        return list(self._steps)
    
    def clear(self):
        self._steps = []
    
    def local(self, *args, **kwargs):
        self._steps.append(Step(
            command='local',
            host='localhost',
            user=env.user,
            args=args,
            kwargs=kwargs))
        
    def run(self, *args, **kwargs):
        self._steps.append(Step(
            command='run',
            host=env.host_string,
            user=env.user,
            key=env.key_filename,
            args=args,
            kwargs=kwargs))
        
    def sudo(self, *args, **kwargs):
        self._steps.append(Step(
            command='sudo',
            host=env.host_string,
            user=env.user,
            key=env.key_filename,
            args=args,
            kwargs=kwargs))
        
    def put(self, *args, **kwargs):
        raise NotImplementedError
        self._steps.append(Step(
            command='put',
            host=env.host_string,
            user=env.user,
            key=env.key_filename,
            args=args,
            kwargs=kwargs))
        
    def exists(self, *args, **kwargs):
        #TODO:remove? can't support due to implicit uncertainty of dependencies?
        self._steps.append(Step(
            command='exists',
            host=env.host_string,
            user=env.user,
            key=env.key_filename,
            args=args,
            kwargs=kwargs))
    
    def pprint(self, as_csv=False):
        if as_csv:
            print('step,user,host_string,key_filename,type,command')
        i = 0
        for step in self.steps:
            i += 1
            if as_csv:
                print('%i,"%s","%s","%s","%s","%s"' % (
                    i,
                    step.user,
                    step.host,
                    step.key,
                    step.command,
                    step.remote_command))
            else:
                print(step)

def replace(function, mock):
    """
    Replaces all references to the given function with the given mock object.
    """
    if function.func_name in _originals:
        return
    _originals[function.func_name] = function
    for obj in gc.get_referrers(function):
        if obj is _originals:
            # Don't replace the original.
            continue
        elif isinstance(obj, dict):
            for _k, _v in obj.items():
                if _v is function:
                    obj[_k] = mock
        elif isinstance(obj, types.FrameType):
            for _k, _v in obj.f_locals.items():
                if _v is function:
                    obj.f_locals[_k] = mock
        elif isinstance(obj, list):
            for i, _v in list(enumerate(obj)):
                if _v is function:
                    obj[i] = mock
        else:
            raise NotImplementedError, type(obj)

def get_original(name):
    """
    Returns a reference to the original function.
    """
    print('_originals:',_originals.keys())
    if name in _originals:
        print('using originals')
        return _originals[name]
    if hasattr(fabric.api, name):
        return getattr(fabric.api, name)
    if hasattr(fabric.contrib.files, name):
        return getattr(fabric.contrib.files, name)

@task_or_dryrun
def create():
    """
    Instantiates a new plan and replaces the standard `run` and `sudo`
    commands with mocks to log their command instead of executing.
    """
    env.plan_root = plan = Plan()
    replace(fabric.api.local, plan.local)
    replace(fabric.api.run, plan.run)
    replace(fabric.api.sudo, plan.sudo)
    replace(fabric.api.put, plan.put)
    replace(fabric.contrib.files.exists, plan.exists)
    
@task_or_dryrun
def show(csv=0):
    """
    Prints all pending commands.
    """
    assert env.plan_root, 'You must first run plan.create.'
    csv = int(csv)
    plan = env.plan_root
    plan.pprint(as_csv=csv)

@task_or_dryrun
def execute():
    """
    Runs the commands in the currently cached plan.
    """
    assert env.plan_root, 'You must first run plan.create.'
    todo
    
@task_or_dryrun
def clear():
    """
    Deletes all commands in the current plan.
    """
    assert env.plan_root, 'You must first run plan.create.'
    env.plan_root.clear()
    