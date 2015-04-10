"""
Tracks changes between deployments.
"""
from datetime import datetime
import os
import re
import yaml

from fabric.api import (
    env,
    require,
    settings,
    cd,
)

from burlap import common
from burlap.decorators import task_or_dryrun

env.manifest_dir = '.manifests'

def get_manifest_path():
    #manifest_path = '%(manifest_dir)s/%(host_string)s' % env
    manifest_path = '%(manifest_dir)s/%(ROLE)s' % env
    if not os.path.isdir(manifest_path):
        os.makedirs(manifest_path)
    env.manifest_path = os.path.abspath(manifest_path)
    return env.manifest_path

def get_manifest_filename(timestamp=True, extension=True):
    parts = ['burlap', 'manifest', env.ROLE, env.host_string]
    if timestamp:
        parts.append(datetime.now().strftime('%Y%m%d-%H%M%S'))
    fn = '-'.join(parts)
    if extension:
        fn += '.yaml'
    return fn

def get_last_manifest_filename():
    dir = get_manifest_path()
    prefix = get_manifest_filename(timestamp=False, extension=False)
    for fn in sorted(os.listdir(dir), reverse=True):
        if fn.startswith(prefix):
            return os.path.join(dir, fn)

@task_or_dryrun
def record():
    """
    Creates a manifest file for the current host, listing all current settings
    so that a future deployment can use it as a reference to perform an
    idempotent deployment.
    """
    data = {} # {component:data}
    manifest_path = get_manifest_path()
    print 'manifest_path:',manifest_path
    manifest_filename = get_manifest_filename()
    manifest_fqfn = os.path.join(manifest_path, manifest_filename)
    
#    print 'host_string:',env.host_string
#    print 'hosts:',env.hosts
    manifest_data = {}
    for component_name, func in common.manifest_recorder.iteritems():
        component_name = component_name.upper()
        print 'component_name:',component_name
        manifest_data[component_name] = func()
    if not common.manifest_recorder:
        print 'No manifest recorders.'
    manifest_data['manifest_creation_timestamp'] = datetime.now()
    yaml.dump(manifest_data, open(manifest_fqfn, 'w'))
    print 'Wrote %s.' % (manifest_fqfn,)

@task_or_dryrun
def compare(component=None):
    """
    Determines what methods need to be run to make the target match
    the current settings.
    """
    last_manifest_fn = get_last_manifest_filename()
    print 'last_manifest_fn:',last_manifest_fn
    manifest_data = type(env)()
    if last_manifest_fn:
        #manifest_data = yaml.safe_load(open(last_manifest_fn)) or type(env)()
        manifest_data = yaml.load(open(last_manifest_fn)) or type(env)()
    pending_methods = []
    component = (component or '').strip().upper()
    report = []
    services = set(_.upper() for _ in env.services)
    
    valid_component_names = set(component_name.strip().upper() for component_name in common.manifest_comparer.iterkeys())
    if component and component not in valid_component_names:
        raise Exception, 'Invalid component "%s". Must be one of %s.' % (component, ', '.join(sorted(valid_component_names)))
    
    print 'Checking components for changes:'
    for component_name, func in common.manifest_comparer.iteritems():
        component_name = component_name.upper()
        #print 'component_name:',component_name
        if component and component != component_name:
            #print 'skipping 1'
            continue
        if component_name not in services:
            #print 'skipping 2'
            continue
        #print 'component_name:',component_name
        methods = func(manifest_data.get(component_name))
        if methods:
            msg = '%s %s' % (component_name.ljust(20), 'YES')
            pending_methods.extend(methods)
        else:
            msg = '%s %s' % (component_name.ljust(20), 'NO')
        print msg
        report.append(msg)
    if not common.manifest_comparer:
        print 'No manifest comparers.'
    
    print
    print 'Component change report:'
    print '\n'.join(sorted(report))
    
    if pending_methods:
        print '-'*80
        print 'Component methods pending execution:'
        for method in sorted(pending_methods):
            print method
            #print method.wrapped.func_name
    else:
        print '-'*80
        print 'No changes detected.'

@task_or_dryrun
def extract(component=None):
    """
    Attempts to read or deduce the settings of the host.
    """
    todo

@task_or_dryrun
def deploy():
    """
    Makes the target host match the current settings.
    Tries to be idempotent by comparing current settings to last manifest
    and only running the commands necessary to effect the difference.
    """
    