"""
Django-specific helper utilities.
"""
from __future__ import print_function

import os
import re
import sys
import importlib
import traceback
import glob
from collections import defaultdict
from pprint import pprint

from six import StringIO

from fabric.api import (
    env,
    settings,
    runs_once,
)

from burlap import Satchel
from burlap import common
from burlap.common import (
    ROLE,
    sudo_or_dryrun,
    run_or_dryrun,
    local_or_dryrun,
    put_or_dryrun,
    set_site,
)
from burlap.decorators import task_or_dryrun
from burlap.decorators import task

if 'dj_settings_loaded' not in env:
    env.dj_settings_loaded = True
    
    # The default django settings module import path.
    #print('reset django settings module template!!!'
    if 'django_settings_module_template' in env:
        print('!'*80, file=sys.stderr)
        print('env.django_settings_module_template:', env.django_settings_module_template, file=sys.stderr)
    env.django_settings_module_template = '%(app_name)s.settings.settings'
    #
    # This is the name of the executable to call to access Django's management
    # features.
    env.django_manage = './manage'
    
    env.django_interactive_shell_template = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(shell_default_dir)s; /bin/bash -i -c \"./manage shell;\"'
    
    # This is where your application's custom code will reside on the remote
    # server.
    env.remote_app_dir_template = '/usr/local/%(app_name)s'
    env.remote_app_src_dir_template = '%(remote_app_dir)s/%(src_dir)s'
    env.remote_app_src_package_dir_template = '%(remote_app_src_dir)s/%(app_name)s'
    env.remote_manage_dir_template = '%(remote_app_src_package_dir)s'
    
    # These apps will be migrated on a specific database, while faked
    # on all others.
    # This is necessary since South does not have proper support for
    # multi-database applications.
    #./manage migrate <app> --fake
    #./manage migrate --database=<database> <app>
    env.django_migrate_fakeouts = [] # [{database:<database>, app:<app>}]
    
    env.django_install_sql_path_template = '%(src_dir)s/%(app_name)s/*/sql/*'
    
    env.django_version = (1, 6, 0)

DJANGO = 'DJANGO'
DJANGOMEDIA = 'DJANGOMEDIA'
DJANGOSYNCDB = 'DJANGOSYNCDB'
DJANGOMIGRATIONS = 'DJANGOMIGRATIONS'

@task_or_dryrun
def check_remote_paths(verbose=1):
    if 'django_settings_module' in env:
        return
    render_remote_paths()

@task_or_dryrun
def render_remote_paths(e=None):
    verbose = common.get_verbose()
    
    _global_env = e is None
    
    e = e or env
    e = type(e)(e)
    
    try:
        e.django_settings_module = e.django_settings_module_template % e
    except KeyError:
        pass
    e.remote_app_dir = e.remote_app_dir_template % e
    e.remote_app_src_dir = e.remote_app_src_dir_template % e
    e.remote_app_src_package_dir = e.remote_app_src_package_dir_template % e
    if e.is_local:
        if e.remote_app_dir.startswith('./') or e.remote_app_dir == '.':
            e.remote_app_dir = os.path.abspath(e.remote_app_dir)
        if e.remote_app_src_dir.startswith('./') or e.remote_app_src_dir == '.':
            e.remote_app_src_dir = os.path.abspath(e.remote_app_src_dir)
        if e.remote_app_src_package_dir.startswith('./') or e.remote_app_src_package_dir == '.':
            e.remote_app_src_package_dir = os.path.abspath(e.remote_app_src_package_dir)
    e.remote_manage_dir = e.remote_manage_dir_template % e
    e.shell_default_dir = e.shell_default_dir_template % e
#     if verbose:
#         print('render_remote_paths')
#         print('django_settings_module_template:',e.django_settings_module_template)
#         print('django_settings_module:',e.django_settings_module)
#         print('shell_default_dir:',e.shell_default_dir)
#         print('src_dir:',e.src_dir)
#         print('remote_app_dir:',e.remote_app_dir)
#         print('remote_app_src_dir:',e.remote_app_src_dir)
#         print('remote_app_src_package_dir_template:',e.remote_app_src_package_dir_template)
#         print('remote_app_src_package_dir:',e.remote_app_src_package_dir)
#         print('remote_manage_dir:',e.remote_manage_dir)
    
    if _global_env:
        env.update(e)
    
    return e

def load_django_settings():
    """
    Loads Django settings for the current site and sets them so Django internals can be run.
    """

    #TODO:remove this once bug in django-celery has been fixed
    os.environ['ALLOW_CELERY'] = '0'

    #os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dryden_site.settings")

    # In Django >= 1.7, fixes the error AppRegistryNotReady: Apps aren't loaded yet
    try:
        from django.core.wsgi import get_wsgi_application
        application = get_wsgi_application()
    except (ImportError, RuntimeError):
        traceback.print_exc()

    # Load Django settings.
    settings = get_settings()
    try:
        from django.contrib import staticfiles
        from django.conf import settings as _settings
        for k, v in settings.__dict__.iteritems():
            setattr(_settings, k, v)
    except (ImportError, RuntimeError):
        traceback.print_exc()
        
    return settings

def iter_static_paths(ignore_import_error=False):

    load_django_settings()

    from django.contrib.staticfiles import finders, storage
    for finder in finders.get_finders():
        for _n, _s in finder.storages.iteritems():
            yield _s.location

def iter_app_directories(ignore_import_error=False):
    from importlib import import_module
    
    settings = load_django_settings()
    if not settings:
        return
    
    for app in settings.INSTALLED_APPS:
        try:
            mod = import_module(app)
        except ImportError:
            if ignore_import_error:
                continue
            else:
                raise
        yield app, os.path.dirname(mod.__file__)

def iter_south_directories(*args, **kwargs):
    for app_name, base_app_dir in iter_app_directories(*args, **kwargs):
        migrations_dir = os.path.join(base_app_dir, 'migrations')
        if not os.path.isdir(migrations_dir):
            continue
        yield app_name, migrations_dir

def iter_migrations(d, *args, **kwargs):
    for fn in sorted(os.listdir(d)):
        if fn.startswith('_') or not fn.endswith('.py'):
            continue
        fqfn = os.path.join(d, fn)
        if not os.path.isfile(fqfn):
            continue
        yield fn

def iter_unique_databases(site=None):
    prior_database_names = set()
    for site, site_data in common.iter_sites(site=site, no_secure=True):
        set_db(site=site)
        key = (env.db_name, env.db_user, env.db_host, env.db_engine)
        if key in prior_database_names:
            continue
        prior_database_names.add(key)
        env.SITE = site
        yield site, site_data

@task_or_dryrun
def shell():
    """
    Opens a Django focussed Python shell.
    Essentially the equivalent of running `manage.py shell`.
    """
    if '@' in env.host_string:
        env.shell_host_string = env.host_string
    else:
        env.shell_host_string = '%(user)s@%(host_string)s' % env
    env.shell_default_dir = env.shell_default_dir_template % env
    env.shell_interactive_djshell_str = env.django_interactive_shell_template % env
    if env.is_local:
        cmd = '%(shell_interactive_djshell_str)s' % env
    else:
        cmd = 'ssh -t -i %(key_filename)s %(shell_host_string)s "%(shell_interactive_djshell_str)s"' % env
    #print cmd
    os.system(cmd)
    
@task_or_dryrun
def syncdb(site=None, all=0, database=None, ignore_errors=1): # pylint: disable=redefined-builtin
    """
    Runs the standard Django syncdb command for one or more sites.
    """
    #print 'Running syncdb...'
    
    ignore_errors = int(ignore_errors)
    
    _env = type(env)(env)
    
    _env.db_syncdb_all_flag = '--all' if int(all) else ''
    
    _env.db_syncdb_database = ''
    if database:
        _env.db_syncdb_database = ' --database=%s' % database

    _env = render_remote_paths(e=_env)
    for site, site_data in iter_unique_databases(site=site):
        _env.SITE = site
        with settings(warn_only=ignore_errors):
            run_or_dryrun((
                'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; '
                '%(django_manage)s syncdb --noinput %(db_syncdb_all_flag)s %(db_syncdb_database)s'
            ) % _env)

@task_or_dryrun
def manage(cmd, *args, **kwargs):
    """
    A generic wrapper around Django's manage command.
    """
    
    render_remote_paths()

    environs = kwargs.pop('environs', '').strip()
    if environs:
        environs = ' '.join('export %s=%s;' % tuple(_.split('=')) for _ in environs.split(','))
        environs = ' ' + environs + ' '

    env.dj_cmd = cmd
    env.dj_args = ' '.join(map(str, args))
    env.dj_kwargs = ' '.join(
        ('--%s' % _k if _v in (True, 'True') else '--%s=%s' % (_k, _v))
        for _k, _v in kwargs.iteritems())
    env.dj_environs = environs

    cmd = (
        'export SITE=%(SITE)s; export ROLE=%(ROLE)s;%(dj_environs)scd %(remote_manage_dir)s; '
        '%(django_manage)s %(dj_cmd)s %(dj_args)s %(dj_kwargs)s') % env
    run_or_dryrun(cmd)


@task_or_dryrun
def manage_all(*args, **kwargs):
    """
    Runs manage() across all unique site default databases.
    """
    
    for site, site_data in iter_unique_databases(site='all'):
        print('-'*80, file=sys.stderr)
        print('site:', site, file=sys.stderr)
        
        if env.available_sites_by_host:
            hostname = common.get_current_hostname()
            sites_on_host = env.available_sites_by_host.get(hostname, [])
            if sites_on_host and site not in sites_on_host:
                print('skipping site:', site, sites_on_host, file=sys.stderr)
                continue
            
        manage(*args, **kwargs)


@task_or_dryrun
def migrate(app='', migration='', site=None, fake=0, ignore_errors=0, skip_databases=None, database=None, migrate_apps='', delete_ghosts=1):
    """
    Runs the standard South migrate command for one or more sites.
    """
#     Note, to pass a comma-delimted list in a fab command, escape the comma with a back slash.
#         
#         e.g.
#         
#             fab staging dj.migrate:migrate_apps=oneapp\,twoapp\,threeapp
    
    ignore_errors = int(ignore_errors)
    
    delete_ghosts = int(delete_ghosts)
    
    post_south = tuple(env.django_version) >= (1, 7, 0)
    
    if tuple(env.django_version) >= (1, 9, 0):
        delete_ghosts = 0
    
    skip_databases = (skip_databases or '')
    if isinstance(skip_databases, basestring):
        skip_databases = [_.strip() for _ in skip_databases.split(',') if _.strip()]
    
    migrate_apps = migrate_apps or ''    
    migrate_apps = [
        _.strip().split('.')[-1]
        for _ in migrate_apps.strip().split(',')
        if _.strip()
    ]
    if app:
        migrate_apps.append(app)

    render_remote_paths()
    
    #print('ignore_errors:', ignore_errors)
    
    _env = type(env)(env)
    _env.django_migrate_migration = migration or ''
#     print('_env.django_migrate_migration:', _env.django_migrate_migration)
    _env.django_migrate_fake_str = '--fake' if int(fake) else ''
    _env.django_migrate_database = '--database=%s' % database if database else ''
    _env.django_migrate_merge = '--merge' if not post_south else ''
    _env.delete_ghosts = '--delete-ghost-migrations' if delete_ghosts and not post_south else ''
    for site, site_data in iter_unique_databases(site=site):
#         print('-'*80, file=sys.stderr)
#         print('site:', site, file=sys.stderr)
        
        if env.available_sites_by_host:
            hostname = common.get_current_hostname()
            sites_on_host = env.available_sites_by_host.get(hostname, [])
            if sites_on_host and site not in sites_on_host:
#                 print('skipping site:', site, sites_on_host, file=sys.stderr)
                continue
        
#         print('migrate_apps:', migrate_apps, file=sys.stderr)
        if not migrate_apps:
            migrate_apps.append(' ')
            
        for app in migrate_apps:
#             print('app:', app)
            _env.django_migrate_app = app
#             print('_env.django_migrate_app:', _env.django_migrate_app)
            _env.SITE = site
            cmd = (
                'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; '
                '%(django_manage)s migrate --noinput %(django_migrate_merge)s --traceback '
                '%(django_migrate_database)s %(delete_ghosts)s %(django_migrate_app)s %(django_migrate_migration)s '
                '%(django_migrate_fake_str)s'
            ) % _env
#             print('cmd:', cmd)
            cmd = cmd.strip()
            with settings(warn_only=ignore_errors):
                run_or_dryrun(cmd)


@task_or_dryrun
def migrate_all(*args, **kwargs):
    kwargs['site'] = 'all'
    return migrate(*args, **kwargs)


def set_db(name=None, site=None, role=None, verbose=0, e=None):
    if e is None:
        e = env
    name = name or 'default'
    site = site or env.SITE
    role = role or env.ROLE
    verbose = 1#int(verbose)
#     if verbose:
#         print('set_db.site:',site)
#         print('set_db.role:',role)
    settings = get_settings(site=site, role=role, verbose=verbose)
    assert settings, 'Unable to load Django settings for site %s.' % (site,)
    e.django_settings = settings
#     if verbose:
#         print('settings:',settings)
#         print('databases:',settings.DATABASES)
    default_db = settings.DATABASES[name]
#     if verbose:
#         print('default_db:',default_db)
    e.db_name = default_db['NAME']
    e.db_user = default_db['USER']
    e.db_host = default_db['HOST']
    e.db_password = default_db['PASSWORD']
    e.db_engine = default_db['ENGINE']
    
    if 'mysql' in e.db_engine.lower():
        e.db_type = 'mysql'
    elif 'postgres' in e.db_engine.lower() or 'postgis' in e.db_engine.lower():
        e.db_type = 'postgresql'
    elif 'sqlite' in e.db_engine.lower():
        e.db_type = 'sqlite'
    else:
        e.db_type = e.db_engine
    
    return default_db


def has_database(name, site=None, role=None):
    settings = get_settings(site=site, role=role, verbose=0)
    return name in settings.DATABASES


@task_or_dryrun
def get_settings(site=None, role=None):
    """
    Retrieves the Django settings dictionary.
    """
    from burlap.common import get_verbose
    stdout = sys.stdout
    stderr = sys.stderr
    verbose = get_verbose()
    if not verbose:
        sys.stdout = StringIO()
        sys.stderr = StringIO()
    try:
        sys.path.insert(0, env.src_dir)
        if site and site.endswith('_secure'):
            site = site[:-7]
        site = site or env.SITE or env.default_site
#         if verbose:
#             print('get_settings.site:',env.SITE)
#             print('get_settings.role:',env.ROLE)
        common.set_site(site)
        tmp_role = env.ROLE
        if role:
            env.ROLE = os.environ[ROLE] = role
        check_remote_paths(verbose=verbose)
        env.django_settings_module = env.django_settings_module_template % env
        try:
            os.environ['SITE'] = env.SITE
            os.environ['ROLE'] = env.ROLE
            
            # We need to explicitly delete sub-modules from sys.modules. Otherwise, reload() skips
            # them and they'll continue to contain obsolete settings.
            for name in sorted(sys.modules):
                if name.startswith('alphabuyer.settings.role_') \
                or name.startswith('alphabuyer.settings.site_'):
                    del sys.modules[name]
            if env.django_settings_module in sys.modules:
                del sys.modules[env.django_settings_module]
            module = importlib.import_module(env.django_settings_module)
#             print('module:', module)
    
            # Works as long as settings.py doesn't also reload anything.
            import imp
            imp.reload(module)
            
        except ImportError as e:
            print('Warning: Could not import settings for site "%s": %s' % (site, e))
            traceback.print_exc(file=sys.stdout)
            #raise # breaks *_secure pseudo sites
            return
        finally:
            env.ROLE = os.environ[ROLE] = tmp_role
    finally:
        sys.stdout = stdout
        sys.stderr = stderr
    return module


@task_or_dryrun
def install_sql(site=None, database='default', apps=None):
    """
    Installs all custom SQL.
    """
    #from burlap.db import load_db_set
    
    name = database
    set_db(name=name, site=site)
    #load_db_set(name=name)
    paths = glob.glob(env.django_install_sql_path_template % env)
    #paths = glob.glob('%(src_dir)s/%(app_name)s/*/sql/*' % env)
    
    apps = (apps or '').split(',')
    
    def cmp_paths(d0, d1):
        if d0[1] and d0[1] in d1[2]:
            return -1
        if d1[1] and d1[1] in d0[2]:
            return +1
        return cmp(d0[0], d1[0])
    
    def get_paths(t):
        """
        Returns SQL file paths in an execution order that respect dependencies.
        """
        data = [] # [(path, view_name, content)]
        for path in paths:
            #print path
            parts = path.split('.')
            if len(parts) == 3 and parts[1] != t:
                continue
            if not path.lower().endswith('.sql'):
                continue
            content = open(path, 'r').read()
            matches = re.findall(r'[\s\t]+VIEW[\s\t]+([a-zA-Z0-9_]+)', content, flags=re.IGNORECASE)
            #assert matches, 'Unable to find view name: %s' % (p,)
            view_name = ''
            if matches:
                view_name = matches[0]
            data.append((path, view_name, content))
        for d in sorted(data, cmp=cmp_paths):
            yield d[0]
    
    def run_paths(paths, cmd_template, max_retries=3):
        paths = list(paths)
        error_counts = defaultdict(int) # {path:count}
        terminal = set()
        while paths:
            path = paths.pop(0)
            app_name = re.findall(r'/([^/]+)/sql/', path)[0]
            if apps and app_name not in apps:
                continue
            with settings(warn_only=True):
                put_or_dryrun(local_path=path)
                cmd = cmd_template % env
                error_code = run_or_dryrun(cmd)
                if error_code:
                    error_counts[path] += 1
                    if error_counts[path] < max_retries:
                        paths.append(path)
                    else:
                        terminal.add(path)
        if terminal:
            print('%i files could not be loaded.' % len(terminal), file=sys.stderr)
            for path in sorted(list(terminal)):
                print(path, file=sys.stderr)
            print(file=sys.stderr)
    
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        run_paths(
            paths=get_paths('postgresql'),
            cmd_template="psql --host=%(db_host)s --user=%(db_user)s -d %(db_name)s -f %(put_remote_path)s")
                    
    elif 'mysql' in env.db_engine:
        run_paths(
            paths=get_paths('mysql'),
            cmd_template="mysql -v -h %(db_host)s -u %(db_user)s -p'%(db_password)s' %(db_name)s < %(put_remote_path)s")
            
    else:
        raise NotImplementedError

@task_or_dryrun
def createsuperuser(username='admin', email=None, password=None, site=None):
    """
    Runs the Django createsuperuser management command.
    """
    
    set_site(site)
    
    render_remote_paths()
    
    env.db_createsuperuser_username = username
    env.db_createsuperuser_email = email or username
    run_or_dryrun((
        'export SITE=%(SITE)s; export ROLE=%(ROLE)s; '
        'cd %(remote_manage_dir)s; %(django_manage)s createsuperuser '
        '--username=%(db_createsuperuser_username)s --email=%(db_createsuperuser_email)s') % env)

# @task_or_dryrun
# def install_fixtures(name, site=None):
#     """
#     Installs a set of Django fixtures.
#     """
#     
#     set_site(site)
#     
#     render_remote_paths()
#     
#     fixtures_paths = env.db_fixture_sets.get(name, [])
#     for fixture_path in fixtures_paths:
#         env.db_fq_fixture_path = os.path.join(env.remote_app_src_package_dir, fixture_path)
#         print('Loading %s...' % (env.db_fq_fixture_path,))
#         if not env.is_local and not files.exists(env.db_fq_fixture_path):
#             put_or_dryrun(
#                 local_path=env.db_fq_fixture_path,
#                 remote_path='/tmp/data.json',
#                 use_sudo=True,
#                 )
#             env.db_fq_fixture_path = env.put_remote_path
#         cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s loaddata %(db_fq_fixture_path)s' % env
#         print(cmd)
#         run_or_dryrun(cmd)

@task_or_dryrun
def loaddata(path, site=None):
    """
    Runs the Dango loaddata management command.
    
    By default, runs on only the current site.
    
    Pass site=all to run on all sites.
    """
    render_remote_paths()
    site = site or env.SITE
    env._loaddata_path = path
    for site, site_data in common.iter_sites(site=site, no_secure=True):
        try:
            set_db(site=site)
            env.SITE = site
            cmd = ('export SITE=%(SITE)s; export ROLE=%(ROLE)s; '
                'cd %(shell_default_dir)s; '
                './manage loaddata %(_loaddata_path)s') % env
            sudo_or_dryrun(cmd)
        except KeyError:
            pass

# @task_or_dryrun
# def post_db_create(name=None, site=None, apps=None):
#     from burlap.db import load_db_set
#     print('post_db_create')
#     assert env[ROLE]
#     require('app_name')
#     site = site or env.SITE
#     set_db(name=name, site=site, verbose=1)
#     load_db_set(name=name)
#     
#     syncdb(all=True, site=site, database=name)
#     migrate(fake=True, site=site, database=name, migrate_apps=apps)
#     install_sql(site=site, database=name, apps=apps)
#     #createsuperuser()

@task_or_dryrun
def database_files_dump(site=None):
    """
    Runs the Django management command to export files stored in the database to the filesystem.
    Assumes the app django_database_files is installed.
    """
    
    set_site(site or env.SITE)
    
    render_remote_paths()
    
    cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s database_files_dump' % env
    if env.is_local:
        local_or_dryrun(cmd)
    else:
        run_or_dryrun(cmd)

#DEPRECATED
@task_or_dryrun
def record_manifest_media(verbose=0):
    latest_timestamp = -1e9999999999999999
    if 'dj' in env.services:
        for path in iter_static_paths():
            latest_timestamp = max(
                latest_timestamp,
                common.get_last_modified_timestamp(path) or latest_timestamp)
    if int(verbose):
        print(latest_timestamp)
    return latest_timestamp

#DEPRECATED
@task_or_dryrun
def record_manifest_migrations(verbose=0):
    data = {} # {app: latest_migration_name}
    if 'dj' in env.services:
        for app_name, _dir in iter_app_directories():
            migration_dir = os.path.join(_dir, 'migrations')
            if not os.path.isdir(migration_dir):
                continue
            for migration_name in iter_migrations(migration_dir):
                data[app_name] = migration_name
        if int(verbose):
            print(data)
    return data

@task_or_dryrun
#@runs_once
def update(name=None, site=None, skip_databases=None, do_install_sql=0, apps='', ignore_errors=0):
    """
    Updates schema and custom SQL.
    """
    #from burlap.dj import set_db
#    print('update()'
#     raise Exception
    set_db(name=name, site=site)
    syncdb(site=site) # Note, this loads initial_data fixtures.
    migrate(
        site=site,
        skip_databases=skip_databases,
        migrate_apps=apps,
        ignore_errors=ignore_errors)
    if int(do_install_sql):
        install_sql(name=name, site=site, apps=apps)
    #TODO:run syncdb --all to force population of new content types?

@task_or_dryrun
@runs_once
def update_all(skip_databases=None, do_install_sql=0, apps='', ignore_errors=0):
    """
    Runs the Django migrate command for all unique databases
    for all available sites.
    """
    from burlap.common import get_current_hostname
    hostname = get_current_hostname()
    
    if env.available_sites_by_host:
        sites = env.available_sites_by_host.get(hostname, [])
    else:
        sites = env.available_sites
    
    i = 0
    total = len(sites)
    for site in sorted(sites):
        i += 1
        print('!'*80)
        print('Updating site %s (%i of %i)...' % (site, i, total))
        print('!'*80)
        
        with settings(warn_only=int(ignore_errors)):
            update(
                site=site,
                skip_databases=skip_databases,
                do_install_sql=do_install_sql,
                apps=apps,
                ignore_errors=ignore_errors)

#DEPRECATED
@task_or_dryrun
def update_all_from_diff(last=None, current=None):
    migrate_apps = []
    if last and current:
        last = last.get(DJANGOMIGRATIONS)
        current = current.get(DJANGOMIGRATIONS)
        if last is not None and current is not None:
            for app_name in current:
                if current[app_name] != last.get(app_name):
                    migrate_apps.append(app_name)
    return update_all(apps=','.join(migrate_apps))

class DjangoMigrations(Satchel):
    
    name = 'djangomigrations'

    def set_defaults(self):
        
        self.env.app_dir = None
        self.env.ignore_errors = 0

    def record_manifest(self):
        data = {} # {app: latest_migration_name}
        for app_name, _dir in iter_app_directories():
            migration_dir = os.path.join(_dir, 'migrations')
            if not os.path.isdir(migration_dir):
                continue
            for migration_name in iter_migrations(migration_dir):
                data[app_name] = migration_name
        if self.verbose:
            print('%s.migrations:' % self.name)
            pprint(data, indent=4)
        return data
    
    @task
    def truncate(self, app):
        assert self.genv.SITE, 'This should only be run for a specific site.'
        r = self.local_renderer
        r.env.app = app
        r.run('rm -f {app_dir}/{app}/migrations/*.py')
        r.run('rm -f {app_dir}/{app}/migrations/*.pyc')
        r.run('touch {app_dir}/{app}/migrations/__init__.py')
        r.run('export SITE={SITE}; export ROLE={ROLE}; cd {app_dir}; ./manage schemamigration {app} --initial')
#         execute_sql(
#             sql="DELETE FROM south_migrationhistory WHERE app_name='{app}';".format(**r.env),
#             site=self.genv.SITE,
#             as_text=True,
#         )
        r.run('export SITE={SITE}; export ROLE={ROLE}; cd {app_dir}; ./manage migrate {app} --fake')
    
    @task    
    def configure(self):
        last = self.last_manifest or {}
        current = self.current_manifest or {}
        migrate_apps = []
        if last and current:
            if self.verbose:
                print('djangomigrations.last:', last)
                print('djangomigrations.current:', current)
            for app_name in current:
                if current[app_name] != last.get(app_name):
                    migrate_apps.append(app_name)
        if migrate_apps:
            # Note, Django's migrate command doesn't support multiple app name arguments
            # with all options, so we run it separately for each app.
            for app in migrate_apps:
                update_all(apps=app, ignore_errors=self.env.ignore_errors)
    
    configure.deploy_before = [
        'packager',
        'apache',
        'apache2',
        'pip',
        'tarball',
        'djangomedia',
        'postgresql',
        'mysql',
    ]
    #configure.takes_diff = True


class DjangoMediaSatchel(Satchel):
    
    name = 'djangomedia'
    
    def set_defaults(self):
        self.env.media_dirs = ['static']
        self.env.manage_dir = 'src'
    
    def record_manifest(self):
        latest_timestamp = -1e9999999999999999
        for path in iter_static_paths():
            if self.verbose:
                print('checking timestamp of path:', path)
            latest_timestamp = max(
                latest_timestamp,
                common.get_last_modified_timestamp(path) or latest_timestamp)
        if self.verbose:
            print('latest_timestamp:', latest_timestamp)
        return latest_timestamp
    
    @task
    def configure(self, *args, **kwargs):
        self.local_or_dryrun('cd %(manage_dir)s; ./manage collectstatic --noinput' % self.lenv)
    
    configure.deploy_before = ['packager', 'apache2', 'pip', 'user']

DjangoMigrations()
DjangoMediaSatchel()
