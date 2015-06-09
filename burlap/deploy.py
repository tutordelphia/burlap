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
import yaml
import shutil

from fabric.api import (
    env, runs_once,
)
import fabric.contrib.files
import fabric.api

from burlap import common
from burlap.common import (
    local_or_dryrun,
)
from burlap.decorators import task_or_dryrun

# Prevent globals from being reset by duplicate imports.
if not 'plan_init' in env:
    env.plan_init = True
    env.plan_root = None
    env.plan_originals = {}
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

def init_plan_data_dir():
    common.init_burlap_data_dir()
    d = env.plan_data_dir % env
    if not os.path.isdir(d):
        os.makedirs(d)
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
    assert os.path.isdir(d)
    for name in os.listdir(d):
        fqfn = os.path.join(d, name)
        if not os.path.isdir(fqfn):
            continue
        yield name

def get_thumbprint_path(role, name):
    d = get_plan_dir(role=role, name=name)
    d = os.path.join(d, 'thumbprints')
#     print('d:',d)
    if not os.path.isdir(d):
        os.makedirs(d)
    return d

def get_thumbprint_filename():
    return 'thumbprint'
        
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

def get_plan_dir(role, name=None):
    if name:
        d = os.path.join(init_plan_data_dir(), role or env.ROLE, name)
    else:
        d = os.path.join(init_plan_data_dir(), role or env.ROLE)
    if not os.path.isdir(d):
        os.makedirs(d)
    return d

class Plan(object):
    """
    A sequence of steps for accomplishing a state change.
    """
    
    def __init__(self, name, role=None, verbose=1):
        
        self.verbose = verbose
        
        self.name = name
        
        self.role = role or env.ROLE
        
        self.plan_dir = get_plan_dir(role, name)
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
        
        self.plan_dir_hosts = os.path.join(self.plan_dir, 'hosts')
        if self.role == env.ROLE and not os.path.isfile(self.plan_dir_hosts):
            open(self.plan_dir_hosts, 'w').write('\n'.join(sorted(env.hosts)))
        self.load_hosts()
        
        #self.plan_thumbprint_fn = os.path.join(self.plan_dir, 'thumbprint')
    
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
        return int(re.findall('^[0-9]+', self.name)[0])
    
    def failed(self):
        return False #TODO
    
    def load_hosts(self):
        self.hosts = [
            _.strip()
            for _ in open(self.plan_dir_hosts, 'r').readlines()
            if _.strip()]
    
    @property
    def all_hosts_thumbprinted(self):
        for host in self.hosts:
            fn = self.get_thumbprint_filename(host)
            if not os.path.isfile(fn):
                return False
        return True
    
    def load_history(self):
        pass
    
    def get_thumbprint_filename(self, host_string):
        d = os.path.join(self.plan_dir, 'thumbprints')
        if not os.path.isdir(d):
            os.makedirs(d)
        fn = os.path.join(d, env.host_string)
        return fn
    
    @property
    def thumbprint(self):
        fn = self.get_thumbprint_filename(env.host_string)
        return yaml.load(open(fn))
    
    @thumbprint.setter
    def thumbprint(self, data):
        assert isinstance(data, dict)
        if not common.get_dryrun():
            fout = open(self.get_thumbprint_filename(env.host_string), 'w')
            yaml.dump(data, fout, default_flow_style=False, indent=4)
    
    def record_thumbprint(self):
        """
        Creates a thumbprint file for the current host in the current role and name.
        """
        data = get_current_thumbprint(role=self.role, name=self.name)
        print('Recording thumbprint for host %s with deployment %s on %s.' \
            % (env.host_string, self.name, self.role))
        self.thumbprint = data
    
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
    def load(cls, name, role=None, verbose=1):
        plan = cls(name, role=role, verbose=verbose)
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

def get_last_completed_plan():
    """
    Returns the last plan completed.
    """
    for _name in reversed(sorted(list(iter_plan_names()))):
        plan = Plan.load(_name)
#         print('plan:',plan.name,'completed:',plan.is_complete())
        if plan.is_complete():
            return plan
            
def get_last_plan(role=None):
    """
    Returns the last plan created.
    """
    for _name in reversed(sorted(list(iter_plan_names(role=role)))):
        plan = Plan.load(_name, role=role)
        return plan

def has_outstanding_plans():
    """
    Returns true if there are plans for this role that have not been executed.
    """
    last_completed = get_last_completed_plan()
#     print('last_completed plan:',last_completed)
    last = get_last_plan()
#     print('last plan:',last)
#     print('eq:',last == last_completed)
    return last != last_completed

@task_or_dryrun
@runs_once
def status(name=None, verbose=0):
    """
    Reports the status of any pending plans for the current role.
    """
    print('plan,complete,percent')
    for _name in iter_plan_names():
        #print(_name)
        plan = Plan.load(_name, verbose=int(verbose))
        output = '%s,%s,%s' % (_name, int(plan.is_complete()), plan.percent_complete)
        if plan.is_complete():
            output = success(output)
        elif plan.failed:
            output = fail(output)
        else:
            output = ongoing(output)
        print(output)

def get_current_thumbprint(role=None, name=None):
    """
    Retrieves a snapshot of the current code state.
    """
    if name == INITIAL:
        name = '0'*env.plan_digits
        
    data = {} # {component:data}
    manifest_data = {}
    for component_name, func in common.manifest_recorder.iteritems():
        component_name = component_name.upper()
        #print('component_name:',component_name)
        manifest_data[component_name] = func()
        
    return manifest_data

@task_or_dryrun
def get_last_thumbprint():
    """
    Returns thumbprint from the last complete deployment.
    """
    plan = get_last_completed_plan()
#     print('last completed plan:',plan.name)
    last_thumbprint = (plan and plan.thumbprint) or {}
    return last_thumbprint

def iter_thumbprint_differences():
    last = get_last_thumbprint()
    current = get_current_thumbprint()
    for k in current:
        if current[k] != last.get(k):
#             print('k:',k,current[k],last.get(k))
            yield k, last, current

@task_or_dryrun
def show_diff(only=None):
    """
    Inspects differences between the last deployment and the current code state.
    """
    for k, last, current in iter_thumbprint_differences():
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
@runs_once
def truncate():
    """
    Compacts all deployment records into a single initial deployment.
    """
    d = os.path.join(init_plan_data_dir(), env.ROLE)
    local_or_dryrun('rm -Rf "%s"' % d)
    local_or_dryrun('mkdir -p "%s"' % d)
    if not common.get_dryrun():
        fabric.api.execute(thumbprint, hosts=env.hosts)

@task_or_dryrun
def thumbprint(name=None):
    """
    Creates a manifest file for the current host, listing all current settings
    so that a future deployment can use it as a reference to perform an
    idempotent deployment.
    """
    if name:
        plan = Plan.load(name=name)
    else:
        plan = get_last_plan()
        if not plan:
            plan = Plan.get_or_create_next()
    plan.record_thumbprint()
    
@task_or_dryrun
@runs_once
def preview():
    """
    Lists the likely pending deployment steps.
    """
    auto(preview=1)
    
@task_or_dryrun
def auto(fake=0, preview=0, check_outstanding=1):
    """
    Generates a plan based on the components that have changed since the last deployment.
    
    The overall steps ran for each host:
    
        1. create plan
        2. run plan
        3. create thumbprint
    
    fake := If true, generates the plan and records the run as successful, but does not apply any
        changes to the hosts.
    
    """
    
    fake = int(fake)
    preview = int(preview)
    check_outstanding = int(check_outstanding)
    
    last_plan = get_last_completed_plan()
    if check_outstanding and has_outstanding_plans():
        print(fail((
            'There are outstanding plans pending execution! '
            'Run `fab %s plan.status` for details.') % env.ROLE))
        sys.exit(1)
        
    diffs = list(iter_thumbprint_differences())
    if not diffs:
        print('No differences detected.')
        return

    # Create plan.
    components = set()
    component_thumbprints = {}
    for component, last, current in diffs:
        component_thumbprints[component] = last, current
        components.add(component)
    component_dependences = {}
#     dict(
#         (_c, set(common.manifest_deployers_befores.get(_c, [])).intersection(components))
#         for _c in components)
#     print('component_dependences:',component_dependences)
    print('manifest_deployers_befores:',common.manifest_deployers_befores.keys())
    print('all components:',components)
    for _c in components:
        print('checking:',_c)
        deps = set(common.manifest_deployers_befores.get(_c, []))
        print('deps0:',deps)
        deps = deps.intersection(components)
        print('deps1:',deps)
        component_dependences[_c] = deps
    print('dependencies:')
    for _c in component_dependences:
        print(_c, component_dependences[_c])
    components = list(common.topological_sort(component_dependences.items()))
    #print('components:',components)
    if components:
        if preview:
            print('These components have changed:\n')
            for component in sorted(components):
                print((' '*4)+component)
            print('\nDeployment plan:\n')
    else:
        print('Nothing to do!')
        return
    
    # Execute plan.
    for component in components:
        funcs = common.manifest_deployers.get(component, [])
        for func_name in funcs:
            takes_diff = common.manifest_deployers_takes_diff.get(func_name, False)
            #print(func_name, takes_diff)
            if preview:
                print(success((' '*4)+func_name))
                continue
            func = common.resolve_deployer(func_name)
            last, current = component_thumbprints[component]
            if not fake:
                if takes_diff:
                    func(last=last, current=current)
                else:
                    func()
    if preview:
        print('\nTo execute this plan on all hosts run:\n\n    fab %s deploy.run' % env.ROLE)
        return
    
    # Create thumbprint.
    plan = Plan.get_or_create_next(last_plan=last_plan)
    plan.record_thumbprint()

@task_or_dryrun
def run(*args, **kwargs):
    """
    Performs a full deployment.
    """
    from burlap import service, notifier
    service.pre_deploy()
    auto(check_outstanding=0, *args, **kwargs)
    service.post_deploy()
    notifier.notify_post_deployment()
    