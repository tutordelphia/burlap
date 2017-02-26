from __future__ import print_function

import os
import re
import sys
import datetime
import tempfile
import json
import functools
import traceback
from collections import defaultdict
from pprint import pprint

import yaml

from fabric.api import (
    env, runs_once, sudo as _sudo, get as _get,
)
import fabric.contrib.files
import fabric.api

from burlap import common
from burlap.common import (
    local_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
)
from burlap.decorators import task_or_dryrun
from burlap import exceptions

STORAGE_LOCAL = 'local'
STORAGE_REMOTE = 'remote'
STORAGES = (
    STORAGE_LOCAL,
    STORAGE_REMOTE,
)

default_remote_path = '/var/local/burlap'

# Prevent globals from being reset by duplicate imports.
if not 'plan_init' in env:
    env.plan_init = True
    env.plan_root = None
    env.plan_originals = {}
    env.plan_storage = STORAGE_REMOTE
    env.plan_lockfile_path = '/var/lock/burlap_deploy.lock'
_originals = env.plan_originals

env.plan = None
env.plan_data_dir = '%(burlap_data_dir)s/plans'
env.plan_digits = 3

RUN = 'run'
SUDO = 'sudo'
LOCAL = 'local'
PUT = 'put'
PLAN_METHODS = [RUN, SUDO, LOCAL, PUT]

INITIAL = 'initial'

_fs_cache = defaultdict(dict) # {func_name:{path:ret}}

def make_dir(d):
    if d not in _fs_cache['make_dir']:
        if env.plan_storage == STORAGE_REMOTE:
            sudo_or_dryrun('mkdir -p "%s"' % d)
        else:
            if not os.path.isdir(d):
                os.makedirs(d)
        _fs_cache['make_dir'][d] = True
    return _fs_cache['make_dir'][d]

@task_or_dryrun
def list_dir(d):
    if d not in _fs_cache['list_dir']:
        verbose = common.get_verbose()
        if env.plan_storage == STORAGE_REMOTE:
            #output = sudo_or_dryrun('ls "%s"' % d)
            output = _sudo('ls "%s"' % d)
            output = output.split()
            if verbose:
                print('output:', output)
            ret = output
        else:
            ret = os.listdir(d)
        _fs_cache['list_dir'][d] = ret
    return _fs_cache['list_dir'][d]

@task_or_dryrun
def is_dir(d):
    if d not in _fs_cache['is_dir']:
        verbose = common.get_verbose()
        if env.plan_storage == STORAGE_REMOTE:
            cmd = 'if [ -d "%s" ]; then echo 1; else echo 0; fi' % d
            output = _sudo(cmd)
            if verbose:
                print('output:', output)
            #ret = int(output)
            ret = int(re.findall(r'^[0-9]+$', output, flags=re.DOTALL|re.I|re.M)[0])
        else:
            ret = os.path.isdir(d)
        _fs_cache['is_dir'][d] = ret
    return _fs_cache['is_dir'][d]

@task_or_dryrun
def is_file(fqfn):
    if fqfn not in _fs_cache['is_file']:
        verbose = common.get_verbose()
        if env.plan_storage == STORAGE_REMOTE:
            cmd = 'if [ -f "%s" ]; then echo 1; else echo 0; fi' % fqfn
            output = _sudo(cmd)
            if verbose:
                print('output:', output)
            ret = int(re.findall(r'^[0-9]+$', output, flags=re.DOTALL|re.I|re.M)[0])
        else:
            ret = os.path.isfile(fqfn)
        _fs_cache['is_file'][fqfn] = ret
    return _fs_cache['is_file'][fqfn]

# class Singleton(type):
#     def __init__(cls, name, bases, dict):
#         print('singleton.init')
#         super(Singleton, cls).__init__(name, bases, dict)
#         cls.instance = None
#  
#     def __call__(cls, *args, **kw):
#         print('singleton.call')
#         return super(Singleton, cls).__call__(*args, **kw)
#         if cls.instance is None:
#             cls.instance = super(Singleton, cls).__call__(*args, **kw)
#         return cls.instance

class RemoteFile(object):
    """
    A helper class for allowing a remote file to be read and written locally
    while still ultimately being saved remotely.
    """
    
#     __metaclass__ = Singleton
    
    _file_cache = {} # {fqfn, obj}
    
    #TODO:use meta-class instead?
    #http://stackoverflow.com/questions/31875/is-there-a-simple-elegant-way-to-define-singletons-in-python/33201#33201
    
    def __new__(cls, fqfn, *args, **kwargs):
        # Remember and cache every class instance per unique file name.
        if fqfn not in cls._file_cache:
#             print('creating new instance:', fqfn)
            cls._file_cache[fqfn] = super(RemoteFile, cls).__new__(cls, fqfn, *args, **kwargs)
#         else:
#             print('using cache:', fqfn)
        return cls._file_cache[fqfn]
    
    def __init__(self, fqfn, mode='r'):
        super(RemoteFile, self).__init__() # causes instantiation error?
        
        assert mode in ('r', 'w', 'a'), 'Invalid mode: %s' % mode
        
        self.mode = mode
            
        # Due to the singleton-nature of __new__, this may be called multiple times,
        # so we check for and avoid duplicate calls.
        if not hasattr(self, 'fqfn'):
            
            self.fqfn = fqfn
            self.content = ''
            self.fresh = True
            
            if mode in 'ra':
    
                _, tmp_fn = tempfile.mkstemp()
                os.remove(tmp_fn)
                ret = _get(remote_path=fqfn, local_path=tmp_fn, use_sudo=True)
                #ret = get_or_dryrun(remote_path=fqfn, local_path=tmp_fn, use_sudo=True)
#                 print('ret:', ret)
                _fn = ret[0]
#                 print('reading:', _fn)
                fin = open(_fn, 'rb')
#                 print('reading2:', _fn)
                self.content = fin.read()
#                 print('closing')
                fin.close()
                #print('removing:', tmp_fn)
                os.remove(tmp_fn)#TODO:memory leak?
#                 print('done init load')
                
            if mode in 'wa':
                
                # Update file system cache.
                _fs_cache['is_file'][fqfn] = True
                
#         print('done init all')

    def write(self, s):
        assert self.mode in 'wa', 'File must be in write-mode.'
        self.content += s
        self.fresh = False
        # Note, flush() must to be called to actually write this.

    def read(self, *args, **kwargs):
        return self.content
    
    def readlines(self):
        return self.content.split('\n')
    
    def flush(self):
        if self.fresh:
            return
        
        print('Flushing contents to remote file.')
        _, tmp_fn = tempfile.mkstemp()
        os.remove(tmp_fn)
        fout = open(tmp_fn, 'w')
        fout.write(self.content)
        fout.close()
        put_or_dryrun(
            local_path=tmp_fn,
            remote_path=self.fqfn,
            use_sudo=True)
        os.remove(tmp_fn)#TODO:memory leak?
        self.fresh = True
        
        # Update file system cache.
        _fs_cache['is_file'][self.fqfn] = True
        
    def close(self):
        print('Closing remote file.')
        self.flush()

def open_file(fqfn, mode='r'):
    verbose = common.get_verbose()
    if env.plan_storage == STORAGE_REMOTE:
        return RemoteFile(fqfn, mode)
    else:
        return open(fqfn, mode)

def init_plan_data_dir():
    common.init_burlap_data_dir()
    d = env.plan_data_dir % env
    make_dir(d)
    return d

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def fail(s):
    return Colors.FAIL + str(s) + Colors.ENDC

def success(s):
    return Colors.OKGREEN + str(s) + Colors.ENDC

def ongoing(s):
    return Colors.WARNING + str(s) + Colors.ENDC

def iter_plan_names(role=None):
    d = get_plan_dir(role=role)
    try:
        assert is_dir(d), 'Plan directory %s does not exist.' % d
    except AssertionError:
        if common.get_dryrun():
            # During dryrun, and the directory is missing, assume the host has been reset
            # and there are no prior plan files.
            return
        else:
            raise
    for name in sorted(list_dir(d)):
        fqfn = os.path.join(d, name)
        if not is_dir(fqfn):
            continue
        yield name

def get_thumbprint_path(role, name):
    d = get_plan_dir(role=role, name=name)
    d = os.path.join(d, 'thumbprints')
    make_dir(d)
    return d

def get_thumbprint_filename():
    return 'thumbprint'
        
class Step(object):
    """
    A single piece of a plan.
    """
    
    def __init__(self, command, host, method, user=None, key=None, args=None, kwargs=None):
        
        args = args or []
        kargs = kwargs or {}
        
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

def get_plan_dir(role, name=None):
    if name:
        d = os.path.join(init_plan_data_dir(), role or env.ROLE, name)
    else:
        d = os.path.join(init_plan_data_dir(), role or env.ROLE)
    make_dir(d)
    return d

class Plan(object):
    """
    A sequence of steps for accomplishing a state change.
    """
    
    def __init__(self, name, role=None):
        
        self.verbose = verbose = common.get_verbose()
        
        self.name = name
        
        self.role = role or env.ROLE
        
        self.vprint('init plan dir')
        self.plan_dir = get_plan_dir(role, name)
        make_dir(self.plan_dir)
        assert is_dir(self.plan_dir)
        
        self.vprint('init plan history dir')
        self.plan_dir_history = os.path.join(self.plan_dir, 'history')
        if not is_file(self.plan_dir_history):
            fout = open_file(self.plan_dir_history, 'w')
            fout.write(','.join(HISTORY_HEADERS))
            fout.close()
        self.vprint('loading plan history')
        
        self.load_history()
        
        self.vprint('init plan index')
        self.plan_dir_index = os.path.join(self.plan_dir, 'index')
        if not is_file(self.plan_dir_index):
            fout = open_file(self.plan_dir_index, 'w')
            fout.write(str(0))
            fout.close()
        self.vprint('loading plan index')
        self.load_index()
        
        self.vprint('init plan steps')
        self.plan_dir_steps = os.path.join(self.plan_dir, 'steps')
        if not is_file(self.plan_dir_steps):
            fout = open_file(self.plan_dir_steps, 'w')
            fout.write('')
            fout.close()
        self.vprint('loading plan steps')
        self.load_steps()
        
        self.vprint('init plan hosts')
        self.plan_dir_hosts = os.path.join(self.plan_dir, 'hosts')
        if self.role == env.ROLE and not is_file(self.plan_dir_hosts):
            fout = open_file(self.plan_dir_hosts, 'w')
            fout.write('\n'.join(sorted(env.hosts)))
            fout.close()
        self.vprint('loading plan hosts')
        self.load_hosts()
        
        #self.plan_thumbprint_fn = os.path.join(self.plan_dir, 'thumbprint')
        
        self.vprint('plan init done')

    def vprint(self, *args, **kwargs):
        """
        When verbose is set, acts like the normal print() function.
        Otherwise, does nothing.
        """
        if common.get_verbose():
            print(*args, **kwargs)

    def __cmp__(self, other):
        if not isinstance(other, Plan):
            return NotImplemented
        return cmp((self.name, self.role), (other.name, other.role))
    
    def __unicode__(self):
        return unicode(self.name)
    
    def __repr__(self):
        return u'<%s: %s>' % (type(self).__name__, unicode(self))
    
    def is_complete(self):
        #return self.percent_complete == 100
        return self.all_hosts_thumbprinted and self.index == len(self._steps)
    
    @property
    def number(self):
        try:
            return int(re.findall('^[0-9]+', self.name)[0])
        except IndexError:
            #print('No number in "%s"' % self.name
            return 0
    
    def failed(self):
        return False #TODO
    
    def load_hosts(self):
        self.hosts = []
        if self.verbose: print('loading hosts, opening')
        fin = open_file(self.plan_dir_hosts, 'r')
        if self.verbose: print('loading hosts, readlines')
        lines = fin.readlines()
        if self.verbose: print('loading hosts, lines:', lines)
        for line in lines:
            if not line.strip():
                continue
            self.hosts.append(line.strip())
        if self.verbose: print('loading hosts, done')
    
    @property
    def all_hosts_thumbprinted(self):
        for host in self.hosts:
            fn = self.get_thumbprint_filename(host)
            if not is_file(fn):
                return False
        return True
    
    def load_history(self):
        pass
    
    def get_thumbprint_filename(self, host_string):
        d = os.path.join(self.plan_dir, 'thumbprints')
        make_dir(d)
        fn = os.path.join(d, env.host_string)
        return fn
    
    @property
    def thumbprint(self):
        verbose = common.get_verbose()
        self.vprint('plan.thumbprint')
        fn = self.get_thumbprint_filename(env.host_string)
        self.vprint('plan.thumbprint.fn:', fn)
        content = open_file(fn).read()
        self.vprint('plan.thumbprint.yaml.raw:', content)
        data = yaml.load(content)
        self.vprint('plan.thumbprint.yaml.data:', data)
        return data
    
    @thumbprint.setter
    def thumbprint(self, data):
        assert isinstance(data, dict)
        if not common.get_dryrun():
            fout = open_file(self.get_thumbprint_filename(env.host_string), 'w')
            yaml.dump(data, fout, default_flow_style=False, indent=4)
            fout.flush()
    
    def record_thumbprint(self, only_components=None):
        """
        Creates a thumbprint file for the current host in the current role and name.
        """
        only_components = only_components or []
        data = get_current_thumbprint(role=self.role, name=self.name, only_components=only_components)
        print('Recording thumbprint for host %s with deployment %s on %s.' \
            % (env.host_string, self.name, self.role))
        self.thumbprint = data
    
    @property
    def remaining_step_count(self):
        return len(self._steps) - self.index
    
    def add_history(self, index, start, end):
        fout = open_file(self.plan_dir_history, 'a')
        fout.write('%s,%s,%s\n' % (index, start, end))
        fout.flush()
        fout.close()
    
    def load_index(self):
        self._index = int(open_file(self.plan_dir_index).read().strip())
    
    @property
    def index(self):
        return self._index
    
    def is_initial(self):
        return set(self.name) == set(['0'])
    
    @property
    def percent_complete(self):
        if self.is_initial():
            return 100
        if not self._steps:
            return 100
        return self.index/float(len(self._steps))*100
    
    @index.setter
    def index(self, v):
        self._index = int(v)
        fout = open_file(self.plan_dir_index, 'w')
        fout.write(str(self._index))
        fout.flush()
        fout.close()
    
    def load_steps(self):
        self._steps = []
        lines = open_file(self.plan_dir_steps).readlines()
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
    def get_or_create_next(cls, role=None, last_plan=None):
        role = role or env.ROLE
        last_plan = last_plan or get_last_plan(role=role)
        if last_plan:
            number = last_plan.number + 1
        else:
            number = 0
        assert len(str(number)) <= env.plan_digits, \
            'Too many deployments. Truncate existing or increase `plan_digits`.'
        plan = Plan(role=role, name=('%0'+str(env.plan_digits)+'i') % number)
        return plan

    @classmethod
    def load(cls, name, role=None):
        verbose = common.get_verbose()
        if verbose:
            print('loading plan:', name)
        plan = cls(name, role=role)
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

#DEPRECATED
@task_or_dryrun
def record(name):
    common.set_dryrun(1)
    env.plan = Plan(name=name)

#DEPRECATED
@task_or_dryrun
def execute(name):
    verbose = common.get_verbose()
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

def get_last_completed_plan():
    """
    Returns the last plan completed.
    """
    verbose = common.get_verbose()
    if verbose:
        print('get_last_completed_plan')
    for _name in reversed(sorted(list(iter_plan_names()))):
        plan = Plan.load(_name)
        if verbose:
            print('plan:', plan.name)
            print('plan.completed:', plan.is_complete())
        if plan.is_complete():
            return plan
            
def get_last_plan(role=None):
    """
    Returns the last plan created.
    """
    for _name in reversed(sorted(list(iter_plan_names(role=role)))):
        plan = Plan.load(_name, role=role)
        return plan

@task_or_dryrun
def has_outstanding_plans():
    """
    Returns true if there are plans for this role that have not been executed.
    """
    verbose = common.get_verbose()
    last_completed = get_last_completed_plan()
    if verbose:
        print('last_completed plan:', last_completed)
    last = get_last_plan()
    if verbose:
        print('last plan:', last)
        print('eq:', last == last_completed)
    return last != last_completed

@task_or_dryrun
@runs_once
def status(name=None):
    """
    Reports the status of any pending plans for the current role.
    """
    print('plan,complete,percent')
    for _name in iter_plan_names():
        #print(_name)
        plan = Plan.load(_name)
        output = '%s,%s,%s' % (_name, int(plan.is_complete()), plan.percent_complete)
        if plan.is_complete():
            output = success(output)
        elif plan.failed:
            output = fail(output)
        else:
            output = ongoing(output)
        print(output)

def get_current_thumbprint(role=None, name=None, reraise=0, only_components=None):
    """
    Retrieves a snapshot of the current code state.
    """
    if name == INITIAL:
        name = '0'*env.plan_digits
    
    last = get_last_thumbprint()
    only_components = only_components or []
    only_components = [_.upper() for _ in only_components]
    data = {} # {component:data}
    manifest_data = (last and last.copy()) or {}
#     print('manifest_data:', manifest_data.keys())
#     print('only_components:', only_components)
#     raw_input('enter')
    for component_name, func in sorted(common.manifest_recorder.iteritems()):
        component_name = component_name.upper()
        #print('component_name:', component_name)
        
        if only_components and component_name not in only_components:
            if common.get_verbose():
                print('Skipping ignored component:', component_name)
            continue
            
        if component_name.lower() not in env.services:
            if common.get_verbose():
                print('Skipping unused component:', component_name)
            continue
            
        try:
            manifest_data[component_name] = func()
#             print('manifest:', component_name, manifest_data[component_name])
        except exceptions.AbortDeployment as e:
            raise
        except Exception as e:
            if int(reraise):
                raise
            print(traceback.format_exc(), file=sys.stderr)
        
    return manifest_data

@task_or_dryrun
def get_last_thumbprint():
    """
    Returns thumbprint from the last complete deployment.
    """
    verbose = common.get_verbose()
    plan = get_last_completed_plan()
    if verbose and plan: print('get_last_thumbprint.last completed plan:', plan.name)
    last_thumbprint = (plan and plan.thumbprint) or {}
    if verbose: print('get_last_thumbprint.last_thumbprint:', last_thumbprint)
    return last_thumbprint

def iter_thumbprint_differences(only_components=None, local_verbose=0):
    only_components = only_components or []
    local_verbose = int(local_verbose)
    verbose = common.get_verbose() or local_verbose
    #if verbose: print('getting last thumbprint')
    last = get_last_thumbprint()
    #if verbose: print('getting current thumbprint')
    current = get_current_thumbprint()
    #if verbose: print('comparing thumbprints')
    for k in current:
        if only_components and k not in only_components:
#             print('iter_thumbprint_differences.skipping:', k)
            continue
#         print('iter:',k); raw_input('enter')
#         if verbose: print('iter_thumbprint_differences.NOT skipping:', k)
        if current[k] != last.get(k):
            if verbose:
                print('DIFFERENCE! k:', k, current[k], last.get(k))
                print('Current:')
                pprint(current[k], indent=4)
                print('Last:')
                pprint(last.get(k), indent=4)
            yield k, (last, current)
#     if verbose: print('iter_thumbprint_differences done')

@task_or_dryrun
def explain(name, **kwargs):
    #common.set_verbose(1)
    kwargs = kwargs or {}
    name = common.assert_valid_satchel(name)
    kwargs['only_components'] = [name]
    kwargs['local_verbose'] = 1
    diffs = dict(iter_thumbprint_differences(**kwargs))
    last, current = diffs.get(name, (None, None))
    if last is None and current is None:
        print('There are no differences.')
#     else:
#         last = last or {}
#         last.setdefault(name, {})
#         print('last:')
#         pprint(last[name], indent=4)
#         print('current:')
#         pprint(current[name], indent=4)

@task_or_dryrun
def show_diff(only=None):
    """
    Inspects differences between the last deployment and the current code state.
    """
    for k, (last, current) in iter_thumbprint_differences():
        if only and k.lower() != only.lower():
            continue
        print('Component %s has changed.' % k)
        last = last.get(k)
        current = current.get(k)
        if isinstance(last, dict) and isinstance(current, dict):
            for _k in set(last).union(current):
                _a = last.get(_k)
                _b = current.get(_k)
                if _a != _b:
                    print('DIFF: %s =' % _k, _a, _b)
        else:
            print('DIFF:', last, current)

@task_or_dryrun
def info():
    d = os.path.join(init_plan_data_dir(), env.ROLE)
    print('storage:', env.plan_storage)
    print('dir:', d)

@task_or_dryrun
def reset():
    """
    Deletes all recorded plan executions.
    This will cause the planner to think everything needs to be re-deployed.
    """
    d = os.path.join(init_plan_data_dir(), env.ROLE)
    if env.plan_storage == STORAGE_REMOTE:
        sudo_or_dryrun('rm -Rf "%s"' % d)
        sudo_or_dryrun('mkdir -p "%s"' % d)
    elif env.plan_storage == STORAGE_LOCAL:
        local_or_dryrun('rm -Rf "%s"' % d)
        local_or_dryrun('mkdir -p "%s"' % d)
    else:
        raise NotImplementedError
    
@task_or_dryrun
@runs_once
def truncate():
    """
    Compacts all deployment records into a single initial deployment.
    """
    reset()
    if not common.get_dryrun():
        fabric.api.execute(thumbprint, hosts=env.hosts)

@task_or_dryrun
def thumbprint(name=None, components=None):
    """
    Creates a manifest file for the current host, listing all current settings
    so that a future deployment can use it as a reference to perform an
    idempotent deployment.
    """
    
    only_components = components or []
    if isinstance(only_components, basestring):
        only_components = [_.strip() for _ in only_components.split(',') if _.strip()]
    
    if name:
        plan = Plan.load(name=name)
    else:
        plan = get_last_plan()
        print('last plan:', plan)
        if not plan:
            plan = Plan.get_or_create_next()
    plan.record_thumbprint(only_components=only_components)
    
@task_or_dryrun
@runs_once
def preview(**kwargs):
    """
    Lists the likely pending deployment steps.
    """
    return auto(preview=1, **kwargs)

def get_last_current_diffs(target_component):
    """
    Retrieves differing manifests between the current and last snapshot.
    """
    target_component = target_component.strip().upper()
    
    all_services = set(_.strip().upper() for _ in env.services)
    diffs = list(iter_thumbprint_differences())
    components = set()
    component_thumbprints = {}
    for component, (last, current) in diffs:
        if component not in all_services:
            continue
        component_thumbprints[component] = last, current
    
    print('component_thumbprints:', component_thumbprints.keys())
    last, current = component_thumbprints[target_component]
    return last, current

@task_or_dryrun
def auto(fake=0, preview=0, check_outstanding=1, components=None, explain=0):
    """
    Generates a plan based on the components that have changed since the last deployment.
    
    The overall steps ran for each host:
    
        1. create plan
        2. run plan
        3. create thumbprint
    
    fake := If true, generates the plan and records the run as successful, but does not apply any
        changes to the hosts.
    
    components := list of names of components found in the services list
    
    """
    
    explain = int(explain)
    only_components = components or []
    if isinstance(only_components, basestring):
        only_components = [_.strip().upper() for _ in only_components.split(',') if _.strip()]
    if only_components:
        print('Limiting deployment to components: %s' % only_components)
    
    def get_deploy_funcs(components):
        for component in components:
            
            if only_components and component not in only_components:
                continue
            
            funcs = common.manifest_deployers.get(component, [])
            for func_name in funcs:
                
                #TODO:remove this after burlap.* naming prefix bug fixed
                if func_name.startswith('burlap.'):
                    print('skipping %s' % func_name)
                    continue
                    
                takes_diff = common.manifest_deployers_takes_diff.get(func_name, False)
#                 print(func_name, takes_diff)
                
                if preview:
                    #print(success((' '*4)+func_name))
                    #continue
                    yield func_name, None
                else:
                    func = common.resolve_deployer(func_name)
                    last, current = component_thumbprints[component]
                    if not fake:
                        if takes_diff:
                            yield func_name, functools.partial(func, last=last, current=current)
                        else:
                            yield func_name, functools.partial(func)
    
    verbose = common.get_verbose()
    fake = int(fake)
    preview = int(preview)
    check_outstanding = int(check_outstanding)
    
    all_services = set(_.strip().upper() for _ in env.services)
    if verbose:
        print('&'*80)
        print('services:', env.services)
    
    last_plan = get_last_completed_plan()
    outstanding = has_outstanding_plans()
    if verbose:
        print('outstanding plans:', outstanding)
    if check_outstanding and outstanding:
        print(fail((
            'There are outstanding plans pending execution! '
            'Run `fab %s deploy.status` for details.\n'
            'To ignore these, re-run with :check_outstanding=0.'
        ) % env.ROLE))
        sys.exit(1)
    
    if verbose:
        print('iter_thumbprint_differences')
    diffs = list(iter_thumbprint_differences(only_components=only_components))
    if diffs:
        if verbose:
            print('Differences detected!')

    # Create plan.
    components = set()
    component_thumbprints = {}
    for component, (last, current) in diffs:
        if component not in all_services:
            print('ignoring component:', component)
            continue
#         if only_components and component not in only_components:
#             continue
        component_thumbprints[component] = last, current
        components.add(component)
    component_dependences = {}
    
    if verbose:
        print('all_services:', all_services)
        print('manifest_deployers_befores:', common.manifest_deployers_befores.keys())
        print('*'*80)
        print('all components:', components)
    
    all_components = set(common.all_satchels)
    if only_components and not all_components.issuperset(only_components):
        unknown_components = set(only_components).difference(all_components)
        raise Exception('Unknown components: %s' \
            % ', '.join(sorted(unknown_components)))
    
    for _c in components:
        if verbose:
            print('checking:', _c)
        deps = set(common.manifest_deployers_befores.get(_c, []))
        if verbose:
            print('deps0:', deps)
        deps = deps.intersection(components)
        if verbose:
            print('deps1:', deps)
        component_dependences[_c] = deps
        
    if verbose:
        print('dependencies:')
        for _c in component_dependences:
            print(_c, component_dependences[_c])
        
    components = list(common.topological_sort(component_dependences.items()))
#     print('components:',components)
#     raw_input('enter')
    plan_funcs = list(get_deploy_funcs(components))
    if components and plan_funcs:
        print('These components have changed:\n')
        for component in sorted(components):
            print((' '*4)+component)
        print('\nDeployment plan:\n')
        for func_name, _ in plan_funcs:
            print(success((' '*4)+func_name))
    else:
        print('Nothing to do!')
        return False
    
    # Execute plan. 
    if preview:
        print('\nTo execute this plan on all hosts run:\n\n    fab %s deploy.run' % env.ROLE)
        return components, plan_funcs
    else:
        with open('/tmp/burlap.progress', 'w') as fout:
            print('%s Beginning plan execution!' % (datetime.datetime.now(),), file=fout)
            fout.flush()
            for func_name, plan_func in plan_funcs:
                print('%s Executing step %s...' % (datetime.datetime.now(), func_name))
                print('%s Executing step %s...' % (datetime.datetime.now(), func_name), file=fout)
                fout.flush()
                if callable(plan_func):
                    plan_func()
                    
                    # Record this step complete.
                    if not only_components:
                        try:
                            thumbprint(components=func_name.split('.')[0])
                        except AssertionError:
                            # On new installs where the host is not yet present, this may fail.
                            pass
                        
                print('%s Done!' % (datetime.datetime.now(),), file=fout)
                fout.flush()
            print('%s Plan execution complete!' % (datetime.datetime.now(),), file=fout)
            fout.flush()
    
    # Create thumbprint.
    if not common.get_dryrun():
        plan = Plan.get_or_create_next(last_plan=last_plan)
        plan.record_thumbprint(only_components=only_components)

@task_or_dryrun
def run(*args, **kwargs):
    """
    Performs a full deployment.
    
    Parameters:
    
        components := name of satchel to limit deployment to
    """
    from burlap import notifier
    from burlap.common import all_satchels, get_satchel
    
    service = get_satchel('service')
    
    assume_yes = int(kwargs.pop('assume_yes', 0)) or int(kwargs.pop('yes', 0))
    fake = int(kwargs.get('fake', 0))
    
    # Allow satchels to configure connection parameters before we try contacting the hosts.
    #TODO:support ordering?
    for name, satchel in all_satchels.iteritems():
        if hasattr(satchel, 'deploy_pre_run'):
            satchel.deploy_pre_run()
    
    if env.host_string == env.hosts[0]:
        pending = preview(*args, **kwargs)
        if pending:
            # There are changes that need to be deployed, but confirm first with user.
            if not assume_yes \
            and not raw_input('\nBegin deployment? [yn] ').strip().lower().startswith('y'):
                sys.exit(1)
        else:
            # There are no changes pending, so abort all further tasks.
            sys.exit(1)
    
    if not fake:
        service.pre_deploy()
        
    kwargs['check_outstanding'] = 0
    auto(*args, **kwargs)
    
    if not fake:
        service.post_deploy()
        notifier.notify_post_deployment()

@task_or_dryrun
def test_remotefile():
    f = RemoteFile('/var/log/auth.log')
    f.read()
    print(id(f))
    print('-'*80)
    f = RemoteFile('/var/log/auth.log')
    print(id(f))
    