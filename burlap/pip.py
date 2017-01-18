from __future__ import absolute_import, print_function

import os
import sys
import csv
import re
import tempfile
import traceback
from collections import defaultdict
import shutil

from fabric.api import (
    env,
    require,
    settings,
    cd,
    run as _run,
    runs_once,
    execute,
    hide,
)

from fabric.contrib import files
from fabric.tasks import Task

from burlap import common
from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    SITE,
    ROLE,
    find_template,
    QueuedCommand,
    Satchel,
    Deployer,
    get_verbose,
)
from burlap.decorators import task_or_dryrun
#from burlap import versioner
from burlap.constants import *
from burlap.decorators import task
from burlap import versioner

try:
    from requirements.requirement import Requirement
except ImportError:
    Requirement = None

env.pip_build_directory = '/tmp/pip-build-root/pip'
env.pip_check_permissions = True
env.pip_user = 'www-data'
env.pip_group = 'www-data'
env.pip_chmod = '775'
env.pip_python_version = 2.7
env.pip_virtual_env_dir_template = '%(remote_app_dir)s/.env'
env.pip_virtual_env_dir = '.env'
env.pip_virtual_env_exe = sudo_or_dryrun
env.pip_requirements_fn = 'pip-requirements.txt'
env.pip_use_virt = True
env.pip_bootstrap_method = 'ez_setup' # |python-pip
env.pip_bootstrap_packages = ['setuptools', 'distribute', 'virtualenv', 'pip']
env.pip_build_dir = '/tmp/pip-build'
env.pip_path = 'pip%(pip_python_version)s'
env.pip_update_command = ('%(pip_path_versioned)s install --use-mirrors --timeout=120 '
    '--no-install %(pip_no_deps)s --build %(pip_build_dir)s --download %(pip_cache_dir)s '
    '--exists-action w %(pip_package)s')
env.pip_remote_cache_dir = '/tmp/pip_cache'
env.pip_local_cache_dir_template = './.pip_cache/%(ROLE)s'
env.pip_upgrade = ''
env.pip_download_dir = '/tmp'
env.pip_install_command = (". %(pip_virtual_env_dir)s/bin/activate; %(pip_path_versioned)s install "
    "%(pip_no_deps)s %(pip_upgrade_flag)s --build %(pip_build_dir)s --find-links file://%(pip_cache_dir)s --no-index %(pip_package)s; deactivate")
env.pip_uninstall_command = ". %(pip_virtual_env_dir)s/bin/activate; %(pip_path_versioned)s uninstall %(pip_package)s; deactivate"
env.pip_depend_command = (". %(pip_virtual_env_dir)s/bin/activate; %(pip_path_versioned)s install "
    "--no-install --ignore-installed --download=%(pip_download_dir)s --use-mirrors %(pip_package)s; deactivate")

INSTALLED = 'installed'
PENDING = 'pending'

PIP = 'PIP'

def render_paths(e=None):
    from burlap.dj import render_remote_paths
    
    _global_env = e is None
    
    e = e or env
    e = type(e)(e)
    
    e.pip_path_versioned = e.pip_path % e
    e = render_remote_paths(e)
    if e.pip_virtual_env_dir_template:
        e.pip_virtual_env_dir = e.pip_virtual_env_dir_template % e
    if e.is_local:
        e.pip_virtual_env_dir = os.path.abspath(e.pip_virtual_env_dir)
    
    if _global_env:
        env.update(e)
    
    return e

def clean_virtualenv(virtualenv_dir=None):
    render_paths()
    env.pip_virtual_env_dir = virtualenv_dir or env.pip_virtual_env_dir
    with settings(warn_only=True):
        print('Deleting old virtual environment...')
        sudo_or_dryrun('rm -Rf %(pip_virtual_env_dir)s' % env)
    assert not files.exists(env.pip_virtual_env_dir), \
        'Unable to delete pre-existing environment.'

@task_or_dryrun
def has_pip():
    with settings(warn_only=True):
        ret = _run('which pip').strip()
        return bool(ret)
    
@task_or_dryrun
def has_virtualenv():
    with settings(warn_only=True):
        ret = _run('which virtualenv').strip()
        return bool(ret)

@task_or_dryrun
def bootstrap(force=0):
    """
    Installs all the necessary packages necessary for managing virtual
    environments with pip.
    """
    force = int(force)
    if has_pip() and has_virtualenv() and not force:
        return
        
    _env = type(env)(env)
        
    _env.pip_path_versioned = _env.pip_path % _env
    
    if _env.pip_bootstrap_method == 'ez_setup':
        #TODO:buggy and unreliable? replace with `sudo apt-get install python-pip`?
        run_or_dryrun('wget http://peak.telecommunity.com/dist/ez_setup.py -O /tmp/ez_setup.py')
        #sudo_or_dryrun('python{pip_python_version} /tmp/ez_setup.py -U setuptools'.format(**env))
        with settings(warn_only=True):
            sudo_or_dryrun('python{pip_python_version} /tmp/ez_setup.py -U setuptools'.format(**_env))
        sudo_or_dryrun('easy_install -U pip')
    elif _env.pip_bootstrap_method == 'python-pip':
        sudo_or_dryrun('apt-get install python-pip')
    else:
        raise NotImplementedError('Unknown pip bootstrap method: %s' % _env.pip_bootstrap_method)
        
    # Hacky fix for bug https://github.com/pypa/pip/issues/3045
    sudo_or_dryrun('pip uninstall distribute -y || true')
    sudo_or_dryrun('pip uninstall setuptools -y || true')
    if env.pip_bootstrap_packages:
        for package in _env.pip_bootstrap_packages:
            _env.package = package
            sudo_or_dryrun('pip install --upgrade {package}'.format(**_env))

@task_or_dryrun
def virtualenv_exists(virtualenv_dir=None):
    
    render_paths()
    
    #base_dir = os.path.split(env.pip_virtual_env_dir)[0]
    base_dir = virtualenv_dir or env.pip_virtual_env_dir
    
    ret = True
    with settings(warn_only=True):
        ret = _run('ls %s' % base_dir) or ''
        ret = 'cannot access' not in ret.strip().lower()
        
    if common.get_verbose():
        if ret:
            print('Yes')
        else:
            print('No')
        
    return ret

@task_or_dryrun
def init(clean=0, check_global=0, virtualenv_dir=None, check_permissions=None):
    """
    Creates the virtual environment.
    """
    assert env[ROLE]
    
    render_paths()
    
    # Delete any pre-existing environment.
    if int(clean):
        clean_virtualenv(virtualenv_dir=virtualenv_dir)
    
    if virtualenv_exists(virtualenv_dir=virtualenv_dir):
        print('virtualenv exists')
        return
    
    # Important. Default Ubuntu 12.04 package uses Pip 1.0, which
    # is horribly buggy. Should use 1.3 or later.
    if int(check_global):
        print('Ensuring the global pip install is up-to-date.')
        sudo_or_dryrun('pip install --upgrade pip')
    
    virtualenv_dir = virtualenv_dir or env.pip_virtual_env_dir
    
    #if not files.exists(env.pip_virtual_env_dir):
    print('Creating new virtual environment...')
    with settings(warn_only=True):
        cmd = 'virtualenv --no-site-packages %s' % virtualenv_dir
        if env.is_local:
            run_or_dryrun(cmd)
        else:
            sudo_or_dryrun(cmd)
    
    if check_permissions is None:
        check_permissions = env.pip_check_permissions
    
    if not env.is_local and check_permissions:
        sudo_or_dryrun('chown -R %(pip_user)s:%(pip_group)s %(remote_app_dir)s' % env)
        sudo_or_dryrun('chmod -R %(pip_chmod)s %(remote_app_dir)s' % env)

@task_or_dryrun
def set_virtualenv_permissions(user=None, group=None, perms=None, virtualenv_dir=None):
    from burlap.dj import render_remote_paths
    
    _env = type(env)(env)
    
    _env.pip_user = user or _env.pip_user
    _env.pip_group = group or _env.pip_group
    _env.pip_chmod = perms or _env.pip_chmod
    _env.pip_virtual_env_dir = virtualenv_dir or _env.pip_virtual_env_dir
    
    render_remote_paths()
    if virtualenv_dir:
        _env.pip_virtual_env_dir = virtualenv_dir
    elif _env.pip_virtual_env_dir_template:
        _env.pip_virtual_env_dir = _env.pip_virtual_env_dir_template % _env
    
    sudo_or_dryrun('chown -R %(pip_user)s:%(pip_group)s %(pip_virtual_env_dir)s' % _env)
    sudo_or_dryrun('chmod -R %(pip_chmod)s %(pip_virtual_env_dir)s' % _env)

def iter_pip_requirements():
    for line in open(find_template(env.pip_requirements_fn)):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        yield line.split('#')[0]

def get_desired_package_versions(preserve_order=False):
    versions_lst = []
    versions = {}
    for line in open(find_template(env.pip_requirements_fn)).read().split('\n'):
        line = line or ''
        if '#' in line:
            line = line.split('#')[0].strip()
        if not line.strip() or line.startswith('#'):
            continue
        #print line
        matches = re.findall(r'([a-zA-Z0-9\-_]+)[\=\<\>]{2}(.*)', line)
        if matches:
            if matches[0][0] not in versions_lst:
                versions_lst.append((matches[0][0], (matches[0][1], line)))
            versions[matches[0][0]] = (matches[0][1], line)
        else:
            matches = re.findall(r'([a-zA-Z0-9\-]+)\-([0-9\.]+)(?:$|\.)', line)
            if matches:
                if matches[0][0] not in versions_lst:
                    versions_lst.append((matches[0][0], (matches[0][1], line)))
                versions[matches[0][0]] = (matches[0][1], line)
            else:
                if line not in versions_lst:
                    versions_lst.append((line, ('current', line)))
                versions[line] = ('current', line)
    if preserve_order:
        return versions_lst
    return versions

PIP_REQ_NAME_PATTERN = re.compile(r'^[a-z_\-0-9]+', flags=re.I)
PIP_REQ_SPEC_PATTERN = re.compile(r',?([\!\>\<\=]+)([a-z0-9\.]+)', flags=re.I)

PIP_DEP_PATTERN = re.compile(
    r'^\s*(?:Collecting|Downloading/unpacking)\s+(?P<name>[^\(\n]+)\(from\s+(?P<from>[^,\)]+)',
    flags=re.I|re.DOTALL|re.M)
    
PIP_DEPENDS_HEADERS = [
    'package_name',
    'package_version',
    'dependency_name',
    'dependency_specs',
]

@task_or_dryrun
def get_dependencies_fn(output=''):
    #depends_fn = '.pip_cache/%s/.depends' % env.ROLE
    if output:
        depends_fn = output
    else:
        depends_fn = 'roles/all/pip-dependencies.txt'
    return depends_fn

@task_or_dryrun
def update_dependency_cache(name=None, output=None):
    """
    Reads all pip package dependencies and saves them to a file for later use with organizing
    pip-requirements.txt.
    
    Outputs CSV to stdout.
    """

    common.set_show(0)

    try:
        shutil.rmtree('./.env/build')
    except OSError:
        pass

    env.pip_path_versioned = env.pip_path % env
    
    #depends_fn = get_dependencies_fn(output)
    fout = open(output, 'w')
    #fout = sys.stdout
    writer = csv.DictWriter(fout, PIP_DEPENDS_HEADERS)
    writer.writerow(dict(zip(PIP_DEPENDS_HEADERS, PIP_DEPENDS_HEADERS)))
    
    package_to_fqv = {}
    for dep in pip_to_deps():
        #print dep
        assert dep.name not in package_to_fqv, 'Package %s specified multiple times!' % dep.name
        package_to_fqv[dep.name] = str(dep)
    
    #dep_tree = defaultdict(set) # {package:set([deps])}
    reqs = list(iter_pip_requirements())
    total = len(reqs)
    i = 0
    for line in reqs:
        i += 1
        
        if name and name not in line:
            continue
        
        print('line %s: %i %i %.02f%%' % (line, i, total, i/float(total)*100), file=sys.stderr)
        
        env.pip_package = line
        env.pip_download_dir = tempfile.mkdtemp()
        cmd = env.pip_depend_command % env
        #with hide('output', 'running', 'warnings'):
        ret = local_or_dryrun(cmd, capture=True)
        print('ret:', ret)
        matches = PIP_DEP_PATTERN.findall(ret) # [(child,parent)]
        print('matches:', matches)
        
        for child, parent in matches:
            try:
                child_line = child.strip()
                #print 'child_line:',child_line
                #child = Requirement(child_line)
                child_name = PIP_REQ_NAME_PATTERN.findall(child_line)[0]
                child_specs = PIP_REQ_SPEC_PATTERN.findall(child_line)
                #print 'child:',child_name,child_specs
                parent = Requirement.parse_line(parent.strip().split('->')[0])
                #print 'parent:',parent.__dict__
#                 print('parent.specs:',parent.specs,bool(parent.specs)
                assert not parent.specs \
                or (parent.specs and parent.specs[0][0] in ('==', '>=', '<=', '!=', '<', '>')), \
                    'Invalid parent: %s (%s)' % (parent, parent.specs)
                    
#                 if parent.specs and parent.specs[0][0] == '==':
#                     parent.specs[0] = list(parent.specs[0])
#                     parent.specs[0][0] = '>='
                parent_version = ''
                if parent.specs:
                    parent_version = parent.specs[0][1]
                    
                writer.writerow(dict(
                    package_name=parent.name,
                    package_version=parent_version,
                    dependency_name=child_name,
                    dependency_specs=';'.join([''.join(_) for _ in child_specs]),
                ))
                fout.flush()
            except Exception as e:
                print('Error: %s' % e, file=sys.stderr)
                print(e, file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                raise
            
    #fout.close()

@task_or_dryrun
def sort_requirements(fn=None):
    """
    Prints to stdout the current pip-requirements.txt sorted by dependency.
    """
    
    ignore_packages = set(['setuptools'])
    
    package_names_dep = set()
    package_names_req = set()
    package_name_to_version = {}
    package_name_to_original = {}
    
    fn = fn or 'roles/all/pip-requirements.txt'
    
    i = 0
    for line in open(fn).readlines():
        i += 1
        try:
            line = line.strip()
            parent = Requirement.parse_line(line)
            print(parent.specs, parent.__dict__)
            package_name, package_version = line.split('==')
            if package_name in ignore_packages:
                continue
            package_name_to_original[package_name.lower()] = package_name
            package_names_req.add(package_name.lower())
            package_name_to_version[package_name.lower()] = package_version
        except Exception as e:
            print('Error on line %i.' % i, file=sys.stderr)
            raise
    
    package_to_deps = defaultdict(set) # {package:set(dependencies)}
    
    depends_fn = get_dependencies_fn()
    reader = csv.DictReader(open(depends_fn))
    for line in reader:
        print(line, file=sys.stderr)
        package_name = line['package_name'].lower()
        if package_name in ignore_packages:
            continue
        dependency_name = line['dependency_name'].lower()
        if dependency_name in ignore_packages:
            continue
        package_names_dep.add(package_name)
        package_names_dep.add(dependency_name)
        package_to_deps[package_name].add(dependency_name)
        
    reqs_missing_deps = set(map(str.lower, package_names_req)).difference(set(map(str.lower, package_names_dep)))
    print('reqs_missing_deps:', reqs_missing_deps, file=sys.stderr)
    
    deps_missing_reqs = set(map(str.lower, package_names_dep)).difference(set(map(str.lower, package_names_req)))
    print('deps_missing_reqs:', deps_missing_reqs, file=sys.stderr)
    
#     def sort_by_dep(a_name, b_name):
#         if a_name in package_to_deps[b_name]:
#             # b depends on a, so a should come first
#             return -1
#         elif b_name in package_to_deps[a_name]:
#             # a depends on b, so a should come first
#             return +1
#         #else:
#         #    return cmp(a_name, b_name)
#         return 0
    
    for package_name in package_names_req:
        package_to_deps[package_name]
    
    all_names = common.topological_sort(package_to_deps)
    for name in all_names:
        print('%s==%s' % (package_name_to_original[name], package_name_to_version[name]))

@task_or_dryrun
@runs_once
def check_report():
    """
    Runs check() on all hosts and reports the results.
    """
    execute(check)

GITHUB_TO_PIP_NAME_PATTERN = re.compile(r'^.*github.com/[^/]+/(?P<name>[^/]+)/[^/]+/(?P<tag>[^/]+)/?')

def pip_line_to_package_name(line):
    return list(pip_to_deps(lines=[line]))[0].name

def pip_to_deps(lines=None):
    if not lines:
        lines = iter_pip_requirements()
#     total = len(lines)
#     i = 0
    for line in lines:
        
        # Extract the dependency data from the pip-requirements.txt line.
        # e.g.
        #type,name,uri,version,rss_field,rss_regex
        #pip,Django,Django,1.4,,
        parts = line.split('==')
        if len(parts) == 2:
            dep_type = versioner.PIP
            name = uri = parts[0].strip()
            version = parts[1].strip()
        elif '>=' in line and len(line.split('>=')) == 2:
            dep_type = versioner.PIP
            parts = line.split('>=')
            name = uri = parts[0].strip()
            version = parts[1].strip()
        elif 'github' in line.lower():
            dep_type = versioner.GITHUB_TAG
            matches = GITHUB_TO_PIP_NAME_PATTERN.findall(line)
            assert matches, 'No github tag matches for line: %s' % line
            name = matches[0][0]
            uri = line
            tag_name = matches[0][1].strip()
            version = tag_name.replace(name, '')[1:].strip()
            if version.endswith('.zip'):
                version = version.replace('.zip', '')
            if version.endswith('.tar.gz'):
                version = version.replace('.tar.gz', '')
        else:
            raise NotImplementedError('Unhandled line: %s' % line)
        
        # Create the dependency.
        dep = versioner.Dependency(
            type=dep_type,
            name=name,
            uri=uri,
            version=version,
            rss_field=None,
            rss_regex=None,
        )
        yield dep

@task_or_dryrun
def check_for_updates():
    """
    Determines which packages have a newer version available.
    """
    stale_lines = []
    lines = list(iter_pip_requirements())
    total = len(lines)
    i = 0
    for line in lines:
        i += 1
        print('\rChecking requirement %i of %i...' % (i, total))
        sys.stdout.flush()
        #if i > 5:break#TODO:remove
        
        # Extract the dependency data from the pip-requirements.txt line.
        # e.g.
        #type,name,uri,version,rss_field,rss_regex
        #pip,Django,Django,1.4,,
        parts = line.split('==')
        if len(parts) == 2:
            dep_type = versioner.PIP
            name = uri = parts[0].strip()
            version = parts[1].strip()
        elif 'github' in line.lower():
            dep_type = versioner.GITHUB_TAG
            matches = GITHUB_TO_PIP_NAME_PATTERN.findall(line)
            assert matches, 'No github tag matches for line: %s' % line
            name = matches[0][0]
            uri = line
            tag_name = matches[0][1].strip()
            version = tag_name.replace(name, '')[1:].strip()
            if version.endswith('.zip'):
                version = version.replace('.zip', '')
            if version.endswith('.tar.gz'):
                version = version.replace('.tar.gz', '')
        else:
            raise NotImplementedError('Unhandled line: %s' % line)
        
        # Create the dependency.
        dep = versioner.Dependency(
            type=dep_type,
            name=name,
            uri=uri,
            version=version,
            rss_field=None,
            rss_regex=None,
        )
        try:
            if dep.is_stale():
                stale_lines.append(dep)
        except Exception as e:
            print()
            print('Error checking line %s: %s' % (line, e))
            raise
            
    print()
    print('='*80)
    if stale_lines:
        print('The following packages have updated versions available:')
        spaced_lines = []
        max_lengths = defaultdict(int)
        for dep in sorted(stale_lines, key=lambda _: _.name):
            dep_name = dep.name
            dep_current_version = dep.get_current_version()
            dep_installed_version = dep.version
            max_lengths['package'] = max(max_lengths['package'], len(dep_name))
            max_lengths['most_recent_version'] = max(max_lengths['most_recent_version'], len(str(dep_current_version)))
            max_lengths['installed_version'] = max(max_lengths['installed_version'], len(str(dep_installed_version)))
            spaced_lines.append((dep_name, dep_installed_version, dep_current_version))
        
        delimiter = ', '
        columns = ['package', 'installed_version', 'most_recent_version']
        for column in columns:
            max_lengths[column] = max(max_lengths[column], len(column))
        print(''.join((_+('' if i+1 == len(columns) else delimiter)).ljust(max_lengths[_]+2) for i, _ in enumerate(columns)))
        for dep in sorted(spaced_lines):
            last = i+1 == len(columns)
            line_data = dict(zip(columns, dep))
            print(''.join((line_data[_]+('' if i+1 == len(columns) else delimiter)).ljust(max_lengths[_]+2) for i, _ in enumerate(columns)))
    print('-'*80)
    print('%i packages have updates' % (len(stale_lines),))


@task_or_dryrun
def check(return_type=PENDING):
    """
    Lists the packages that are missing or obsolete on the target.
    
    return_type := pending|installed
    """
    
    assert env[ROLE]
    
    ignored_packages = set(['pip', 'argparse'])
    
    env.pip_path_versioned = env.pip_path % env
    init()
    
    def get_version_nums(v):
        if re.findall(r'^[0-9\.]+$', v):
            return tuple(int(_) for _ in v.split('.') if _.strip().isdigit())
    
    use_virt = env.pip_use_virt
    if use_virt:
        cmd_template = ". %(pip_virtual_env_dir)s/bin/activate; %(pip_path_versioned)s freeze; deactivate"
    else:
        cmd_template = "%(pip_path_versioned)s freeze"
    cmd = cmd_template % env
    result = run_or_dryrun(cmd)
    installed_package_versions = {}
    for line in result.split('\n'):
        line = line.strip()
        if '#' in line:
            line = line.split('#')[0].strip()
        if not line:
            continue
        elif line.startswith('#'):
            continue
        elif ' ' in line:
            continue
        try:
            k, v = line.split('==')
        except ValueError as e:
#             print('Malformed line: %s' % line
#             sys.exit()
            continue
        if not k.strip() or not v.strip():
            continue
        print('Installed:', k, v)
        if k.strip().lower() in ignored_packages:
            continue
        installed_package_versions[k.strip()] = v.strip()
        
    desired_package_version = get_desired_package_versions()
    for k, v in desired_package_version.iteritems():
        print('Desired:', k, v)
    
    pending = [] # (package_line, type)]
    
    not_installed = {}
    for k, (v, line) in desired_package_version.iteritems():
        if k not in installed_package_versions:
            not_installed[k] = (v, line)
            
    if not_installed:
        print('!'*80)
        print('Not installed:')
        for k, (v, line) in sorted(not_installed.iteritems(), key=lambda o: o[0]):
            if k.lower() in ignored_packages:
                continue
            print(k, v)
            pending.append((line, 'install'))
    else:
        print('-'*80)
        print('All are installed.')
    
    obsolete = {}
    for k, (v, line) in desired_package_version.iteritems():
        #line
        if v != 'current' and v != installed_package_versions.get(k, v):
            obsolete[k] = (v, line)
    if obsolete:
        print('!'*80)
        print('Obsolete:')
        for k, (v0, line) in sorted(obsolete.iteritems(), key=lambda o: o[0]):
            v0nums = get_version_nums(v0) or v0
            v1 = installed_package_versions[k]
            v1nums = get_version_nums(v1) or v1
            #print 'v1nums > v0nums:',v1nums, v0nums
            installed_is_newer = v1nums > v0nums
            newer_str = ''
            if installed_is_newer:
                newer_str = ', this is newer!!! Update pip-requirements.txt???'
            print(k, v0, '(Installed is %s%s)' % (v1, newer_str))
            pending.append((line, 'update'))
    else:
        print('-'*80)
        print('None are obsolete.')
    
    if return_type == INSTALLED:
        return installed_package_versions
    return pending


@task_or_dryrun
@runs_once
def update(package='', ignore_errors=0, no_deps=0, all=0, mirrors=1): # pylint: disable=redefined-builtin
    """
    Updates the local cache of pip packages.
    
    If all=1, skips check of host and simply updates everything.
    """
    
    assert env[ROLE]
    ignore_errors = int(ignore_errors)
    env.pip_path_versioned = env.pip_path % env
    env.pip_local_cache_dir = env.pip_local_cache_dir_template % env
    env.pip_cache_dir = env.pip_local_cache_dir
    if not os.path.isdir(env.pip_cache_dir):
        os.makedirs(env.pip_cache_dir)
    env.pip_package = (package or '').strip()
    env.pip_no_deps = '--no-deps' if int(no_deps) else ''
    env.pip_build_dir = tempfile.mkdtemp()
    
    # Clear build directory in case it wasn't properly cleaned up previously.
    cmd = 'rm -Rf %(pip_build_directory)s' % env
    if env.is_local:
        run_or_dryrun(cmd)
    else:
        sudo_or_dryrun(cmd)
    
    with settings(warn_only=ignore_errors):
        if package:
            # Download a single specific package.
            cmd = env.pip_update_command % env
            if not int(mirrors):
                cmd = cmd.replace('--use-mirrors', '')
            local_or_dryrun(cmd)
        else:
            # Download each package in a requirements file.
            # Note, specifying the requirements file in the command isn't properly
            # supported by pip, thus we have to parse the file itself and send each
            # to pip separately.
            
            if int(all):
                packages = list(iter_pip_requirements())
            else:
                packages = [k for k, v in check()]
            
            for package in packages:
                env.pip_package = package.strip()
                
                cmd = env.pip_update_command % env
                if not int(mirrors):
                    cmd = cmd.replace('--use-mirrors', '')
                    
                local_or_dryrun(cmd)


@task_or_dryrun
def upgrade_pip():
    from burlap.dj import render_remote_paths
    render_remote_paths()
    if env.pip_virtual_env_dir_template:
        env.pip_virtual_env_dir = env.pip_virtual_env_dir_template % env
    sudo_or_dryrun("chown -R %(pip_user)s:%(pip_group)s %(pip_virtual_env_dir)s" % env)
    run_or_dryrun(". %(pip_virtual_env_dir)s/bin/activate; pip install --upgrade setuptools" % env)
    run_or_dryrun(". %(pip_virtual_env_dir)s/bin/activate; pip install --upgrade distribute" % env)
    with settings(warn_only=True):
        run_or_dryrun(". %(pip_virtual_env_dir)s/bin/activate; pip install --upgrade pip" % env)


@task_or_dryrun
def uninstall(package):
    from burlap.dj import render_remote_paths
    
    render_remote_paths()
    if env.pip_virtual_env_dir_template:
        env.pip_virtual_env_dir = env.pip_virtual_env_dir_template % env
    
    env.pip_local_cache_dir = env.pip_local_cache_dir_template % env
    
    env.pip_package = package
    if env.is_local:
        run_or_dryrun(env.pip_uninstall_command % env)
    else:
        sudo_or_dryrun(env.pip_uninstall_command % env)
    
@task_or_dryrun
def update_install(clean=0, pip_requirements_fn=None, virtualenv_dir=None, user=None, group=None, perms=None):
    try:
        from burlap.dj import render_remote_paths
    except ImportError:
        render_remote_paths = None
    
    _env = type(env)(env)
    
    pip_requirements_fn = pip_requirements_fn or env.pip_requirements_fn
    
    bootstrap(force=clean)
    
    init(clean=clean, virtualenv_dir=virtualenv_dir, check_permissions=False)
    
    req_fn = find_template(pip_requirements_fn)
    assert req_fn, 'Could not find file: %s' % pip_requirements_fn
    _env.pip_remote_requirements_fn = '/tmp/pip-requirements.txt'
    put_or_dryrun(
        local_path=req_fn,
        remote_path=_env.pip_remote_requirements_fn,
    )

    if render_remote_paths:
        render_remote_paths()
    
    if virtualenv_dir:
        _env.virtualenv_dir = virtualenv_dir
    elif _env.pip_virtual_env_dir_template:
        _env.virtualenv_dir = _env.pip_virtual_env_dir_template % _env
    
    # Ensure we're always using the latest pip.
    if _env.is_local:
        run_or_dryrun('%(virtualenv_dir)s/bin/pip install -U pip' % _env)
    else:
        sudo_or_dryrun('%(virtualenv_dir)s/bin/pip install -U pip' % _env)
    
    _env.pip_update_install_command = "%(virtualenv_dir)s/bin/pip install -r %(pip_remote_requirements_fn)s"
    if _env.is_local:
        run_or_dryrun(_env.pip_update_install_command % _env)
    else:
        sudo_or_dryrun(_env.pip_update_install_command % _env)
        
    if not _env.is_local and (_env.pip_check_permissions or user or group or perms):
        set_virtualenv_permissions(
            user=user,
            group=group,
            perms=perms,
            virtualenv_dir=virtualenv_dir,
        )
    
@task_or_dryrun
def install(package='', clean=0, no_deps=1, all=0, upgrade=1): # pylint: disable=redefined-builtin
    """
    Installs the local cache of pip packages.
    """
    from burlap.dj import render_remote_paths
    print('Installing pip requirements...')
    assert env[ROLE]
    
    require('is_local')
    
    # Delete any pre-existing environment.
    if int(clean):
        clean_virtualenv()
    
    render_remote_paths()
    if env.pip_virtual_env_dir_template:
        env.pip_virtual_env_dir = env.pip_virtual_env_dir_template % env
    
    env.pip_local_cache_dir = env.pip_local_cache_dir_template % env
    
    env.pip_path_versioned = env.pip_path % env
    if env.is_local:
        env.pip_cache_dir = os.path.abspath(env.pip_local_cache_dir % env)
    else:
        env.pip_cache_dir = env.pip_remote_cache_dir % env
        print('env.host_string:', env.host_string)
        print('env.key_filename:', env.key_filename)
        run_or_dryrun('mkdir -p %(pip_cache_dir)s' % env)
        
        if not env.pip_cache_dir.endswith('/'):
            env.pip_cache_dir = env.pip_cache_dir + '/'
        
        env.pip_key_filename = os.path.abspath(env.key_filename)
        local_or_dryrun((
            'rsync -avz --progress --rsh "ssh -o StrictHostKeyChecking=no '
            '-i %(pip_key_filename)s" %(pip_local_cache_dir)s/* %(user)s@%(host_string)s:%(pip_cache_dir)s') % env)
    
    env.pip_upgrade_flag = ''
    if int(upgrade):
        env.pip_upgrade_flag = ' -U '
    
    env.pip_no_deps = ''
    if int(no_deps):
        env.pip_no_deps = '--no-deps'
    
    if int(all):
        packages = list(iter_pip_requirements())
    elif package:
        packages = [package]
    else:
        packages = [k for k, v in check()]
    
    env.pip_build_dir = tempfile.mkdtemp()
    for package in packages:
        env.pip_package = package
        if env.is_local:
            run_or_dryrun(env.pip_install_command % env)
        else:
            sudo_or_dryrun(env.pip_install_command % env)

    if not env.is_local:
        sudo_or_dryrun('chown -R %(pip_user)s:%(pip_group)s %(remote_app_dir)s' % env)
        sudo_or_dryrun('chmod -R %(pip_chmod)s %(remote_app_dir)s' % env)

class PIPSatchel(Satchel):
    
    name = PIP
    
    @property
    def packager_system_packages(self):
        return {
            UBUNTU: [
                #'python-pip',#obsolete in 14.04?
                #'python-virtualenv',#obsolete in 14.04?
                'gcc', 'python-dev', 'build-essential', 'python-pip',
            ],
        }
        
    def set_defaults(self):
        pass

    def record_manifest(self):
        """
        Called after a deployment to record any data necessary to detect changes
        for a future deployment.
        """
        # Not really necessary, because pre-deployment, we'll just retrieve this
        # list again, but it's nice to have a separate record to detect
        # non-deployment changes to installed packages.
        #data = check(return_type=INSTALLED)
        
        desired = get_desired_package_versions(preserve_order=True)
        data = sorted(_raw for _n, (_v, _raw) in desired)
        if get_verbose():
            print(data)
        return data
    
    @task
    def configure(self, *args, **kwargs):
        
        # Necessary to make warning message go away.
        # http://stackoverflow.com/q/27870003/247542
        self.genv['sudo_prefix'] += '-H '
        
        update_install(*args, **kwargs)
    
    configure.deploy_before = ['packager', 'user']
        
pip = PIPSatchel()
