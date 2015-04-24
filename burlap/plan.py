from __future__ import print_function
import os
import gc
import re
import sys
import types
import datetime
import glob
import tempfile
import json

from fabric.api import (
    env,
)
import fabric.contrib.files
import fabric.api

from burlap import common
from burlap.decorators import task_or_dryrun

# Prevent globals from being reset by duplicate imports.
if not 'plan_init' in env:
    env.plan_init = True
    env.plan_root = None
    env.plan_originals = {}
_originals = env.plan_originals

env.plan = None
env.plan_data_dir = '%(burlap_data_dir)s/plans'

RUN = 'run'
SUDO = 'sudo'
LOCAL = 'local'
PUT = 'put'
PLAN_METHODS = [RUN, SUDO, LOCAL, PUT]

def init_plan_data_dir():
    common.init_burlap_data_dir()
    d = env.plan_data_dir % env
    if not os.path.isdir(d):
        os.mkdir(d)
    return d
        
class Step(object):
    """
    A single piece of a plan.
    """
    
    def __init__(self, command, host, method, user=None, key=None, args=[], kwargs={}):
        self.command = command
        self.host = host
        self.user = user
        self.method = method
        
        assert method in PLAN_METHODS
        
        self.key = key
        # The value entity attributes are set to as a result
        # of executing this step.
        self.args = args
        self.kwargs = kwargs
    
    @classmethod
    def from_line(cls, line):
        matches = re.findall(
            r'\[(?P<user>[^@]+)@(?P<host>[^\]]+)(?P<extra>{[^}]+})?]\s+(?P<method>[^\:]+):\s+(?P<command>.*?)$',
            line, flags=re.I|re.DOTALL)
        assert matches
        #print(matches)
        kwargs = dict(zip(['user', 'host', 'extra', 'method', 'command'], matches[0]))
        
        extra = {}
        if kwargs['extra']:
            extra = json.loads(kwargs['extra'])
        del kwargs['extra']
        
        if 'key' in extra:
            key = extra['key']
            del extra['key']
            kwargs['key'] = key
           
        step = Step(**kwargs)
        return step
    
    def execute(self):
        print('execute:',self)
        method = getattr(common, '%s_or_dryrun' % self.method)
        env.user = self.user
        env.host_string = self.host
        if self.key:
            env.key_filename = self.key
        else:
            env.key_filename = None
        method(self.command)
    
    def __str__(self):
        user_str = '%s@' % (self.user) if self.user else ''
        return '[%s%s] %s %s' % (
            user_str,
            self.host,
            self.method+':',
            self.command,
        )
    
    def __repr__(self):
        return str(self.__dict__)

HISTORY_HEADERS = ['step', 'start', 'end']

class Plan(object):
    """
    A sequence of steps for accomplishing a state change.
    """
    
    def __init__(self, name, role=None, verbose=1):
        
        self.verbose = verbose
        
        self.plan_dir = os.path.join(init_plan_data_dir(), role or env.ROLE, name)
        try:
            os.makedirs(self.plan_dir)
        except OSError:
            pass
        assert os.path.isdir(self.plan_dir)
        
        self.plan_dir_history = os.path.join(self.plan_dir, 'history')
        if not os.path.isfile(self.plan_dir_history):
            open(self.plan_dir_history, 'w').write(','.join(HISTORY_HEADERS))
        self.load_history()
        
        self.plan_dir_index = os.path.join(self.plan_dir, 'index')
        if not os.path.isfile(self.plan_dir_index):
            open(self.plan_dir_index, 'w').write(str(0))
        self.load_index()
        
        self.plan_dir_steps = os.path.join(self.plan_dir, 'steps')
        if not os.path.isfile(self.plan_dir_steps):
            open(self.plan_dir_steps, 'w').write('')
        self.load_steps()
        
        self.name = name
    
    def is_complete(self):
        return self.index == len(self._steps)
    
    def load_history(self):
        pass
    
    @property
    def remaining_step_count(self):
        return len(self._steps) - self.index
    
    def add_history(self, index, start, end):
        fout = open(self.plan_dir_history, 'a')
        fout.write('%s,%s,%s\n' % (index, start, end))
        fout.flush()
        fout.close()
    
    def load_index(self):
        self._index = int(open(self.plan_dir_index).read().strip())
    
    @property
    def index(self):
        return self._index
    
    @property
    def percent_complete(self):
        return self.index/float(len(self._steps))*100
    
    @index.setter
    def index(self, v):
        self._index = int(v)
        fout = open(self.plan_dir_index, 'w')
        fout.write(str(self._index))
        fout.flush()
        fout.close()
    
    def load_steps(self):
        self._steps = []
        lines = open(self.plan_dir_steps).readlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            elif '] executing task ' in line.lower():
                continue
            elif line.lower().startswith('done'):
                continue
            s = Step.from_line(line)
            self.add_step(s)
    
    @classmethod
    def load(cls, name, verbose=1):
        plan = cls(name, verbose=verbose)
        return plan
    
    def add_step(self, s):
        assert isinstance(s, Step)
        self._steps.append(s)
    
    @property
    def steps(self):
        return list(self._steps)
    
    def clear(self):
        self.index = 0
        self._steps = []
    
    def execute(self, i=None, j=None):
        i = i or self.index
        steps_ran = []
        for step_i, step in enumerate(self.steps):
            if step_i < i:
                continue
                
            # Run command.
            t0 = datetime.datetime.utcnow().isoformat()
            step.execute()
            t1 = datetime.datetime.utcnow().isoformat()
            steps_ran.append(step)
            
            # Record success.
            if not common.get_dryrun():
                self.index = step_i + 1
                self.add_history(self.index, t0, t1)
            
            if j is not None and step_i >= j:
                break
                
        return steps_ran

@task_or_dryrun
def record(name):
    common.set_dryrun(1)
    env.plan = Plan(name=name)
    
@task_or_dryrun
def execute(name, verbose=1):
    plan = Plan.load(name, verbose=int(verbose))
    if verbose:
        if plan.is_complete():
            print('Execution of plan %s is complete.' % (plan.name,), file=sys.stderr)
        else:
            print('Execution of plan %s is %.02f%% complete.' % (plan.name, plan.percent_complete), file=sys.stderr)
    steps = []
    if not plan.is_complete():
        steps = plan.execute()
        if verbose:
            if plan.is_complete():
                print('Execution of plan %s is complete.' % (plan.name,), file=sys.stderr)
            else:
                print('Execution of plan %s is %.02f%% complete.' % (plan.name, plan.percent_complete), file=sys.stderr)
    if verbose:
        print('Executed %i steps.' % (len(steps),), file=sys.stderr)

