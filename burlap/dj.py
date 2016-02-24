"""
Django-specific helper utilities.
"""
import os
import sys
import importlib
import traceback
import commands
import glob
from collections import defaultdict
from StringIO import StringIO

from fabric.api import (
    env,
    require,
    settings,
    cd,
)

from burlap import Satchel
from burlap import common
from burlap.common import (
    ROLE, QueuedCommand, ALL,
    sudo_or_dryrun,
    run_or_dryrun,
    local_or_dryrun,
    put_or_dryrun,
    set_site,
)
from burlap.decorators import task_or_dryrun

if 'dj_settings_loaded' not in env:
    env.dj_settings_loaded = True
    
    # The default django settings module import path.
    #print>>sys.stderr, 'reset django settings module template!!!'
    if 'django_settings_module_template' in env:
        print>>sys.stderr,  '!'*80
        print>>sys.stderr,  'env.django_settings_module_template:',env.django_settings_module_template
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

DJANGO = 'DJANGO'
DJANGO_MEDIA = 'DJANGO_MEDIA'
DJANGO_SYNCDB = 'DJANGO_SYNCDB'
DJANGO_MIGRATIONS = 'DJANGO_MIGRATIONS'

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
    if verbose:
        print 'render_remote_paths'
        print 'django_settings_module_template:',e.django_settings_module_template
        print 'django_settings_module:',e.django_settings_module
        print 'shell_default_dir:',e.shell_default_dir
        print 'src_dir:',e.src_dir
        print 'remote_app_dir:',e.remote_app_dir
        print 'remote_app_src_dir:',e.remote_app_src_dir
        print 'remote_app_src_package_dir_template:',e.remote_app_src_package_dir_template
        print 'remote_app_src_package_dir:',e.remote_app_src_package_dir
        print 'remote_manage_dir:',e.remote_manage_dir
    
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
    except ImportError:
        pass

    # Load Django settings.
    settings = get_settings()
    from django.contrib import staticfiles
    from django.conf import settings as _settings
    for k,v in settings.__dict__.iteritems():
        setattr(_settings, k, v)
        
    return settings

def iter_static_paths(ignore_import_error=False):

    load_django_settings()

    from django.contrib.staticfiles import finders, storage
    for finder in finders.get_finders():
        for _n,_s in finder.storages.iteritems():
            yield _s.location

def iter_app_directories(ignore_import_error=False):
    from importlib import import_module
    
    settings = load_django_settings()
    
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

def iter_migrations(dir, *args, **kwargs):
    for fn in sorted(os.listdir(dir)):
        if fn.startswith('_') or not fn.endswith('.py'):
            continue
        fqfn = os.path.join(dir, fn)
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
def syncdb(site=None, all=0, database=None):
    """
    Runs the standard Django syncdb command for one or more sites.
    """
    
    _env = type(env)(env)
    
    _env.db_syncdb_all_flag = '--all' if int(all) else ''
    
    _env.db_syncdb_database = ''
    if database:
        _env.db_syncdb_database = ' --database=%s' % database

    _env = render_remote_paths(e=_env)
    for site, site_data in iter_unique_databases(site=site):
        cmd = (
            'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; '
            '%(django_manage)s syncdb %(db_syncdb_all_flag)s %(db_syncdb_database)s') % _env
        run_or_dryrun(cmd)

@task_or_dryrun
def manage(cmd, *args, **kwargs):
    """
    A generic wrapper around Django's manage command.
    """
    
    render_remote_paths()

    env.dj_cmd = cmd
    env.dj_args = ' '.join(map(str, args))
    env.dj_kwargs = ' '.join(
        ('--%s' % _k if _v is True else '--%s=%s' % (_k, _v))
        for _k, _v in kwargs.iteritems())

    cmd = (
        'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; '
        '%(django_manage)s %(dj_cmd)s %(dj_args)s %(dj_kwargs)s') % env
    run_or_dryrun(cmd)
    
@task_or_dryrun
def migrate(app='', migration='', site=None, fake=0, ignore_errors=0, skip_databases=None, database=None, migrate_apps='', delete_ghosts=1):
    """
    Runs the standard South migrate command for one or more sites.
    """
    
    ignore_errors = int(ignore_errors)
    
    delete_ghosts = int(delete_ghosts)
    
    skip_databases = (skip_databases or '')
    if isinstance(skip_databases, basestring):
        skip_databases = [_.strip() for _ in skip_databases.split(',') if _.strip()]
        
    migrate_apps = [
        _.strip().split('.')[-1]
        for _ in migrate_apps.strip().split(',')
        if _.strip()
    ]
    if app:
        migrate_apps.append(app)

    render_remote_paths()
    
    _env = type(env)(env)
    _env.django_migrate_migration = migration or ''
    _env.django_migrate_fake_str = '--fake' if int(fake) else ''
    _env.django_migrate_database = '--database=%s' % database if database else ''
    _env.delete_ghosts = '--delete-ghost-migrations' if delete_ghosts else ''
    for site, site_data in iter_unique_databases(site=site):
        
        print 'migrate_apps:',migrate_apps
        if migrate_apps:
            _env.django_migrate_app = ' '.join(migrate_apps)
        else:
            _env.django_migrate_app = ''
        
        _env.SITE = site
        cmd = (
            'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; '
            '%(django_manage)s migrate --noinput %(django_migrate_database)s %(delete_ghosts)s %(django_migrate_app)s %(django_migrate_migration)s '
            '%(django_migrate_fake_str)s'
        ) % _env
        cmd = cmd.strip()
        with settings(warn_only=ignore_errors):
            run_or_dryrun(cmd)

@task_or_dryrun
def migrate_all(*args, **kwargs):
    kwargs['site'] = 'all'
    return migrate(*args, **kwargs)
    
@task_or_dryrun
def create_db(name=None):
    from burlap.db import create
    set_db(name=name)
    create(
        name=name,
        db_engine=env.db_engine,
        db_user=env.db_user,
        db_host=env.db_host,
        db_password=env.db_password,
        db_name=env.db_name,
    )

def set_db(name=None, site=None, role=None, verbose=0):
    name = name or 'default'
#    print '!'*80
    site = site or env.SITE
    role = role or env.ROLE
    verbose = int(verbose)
    if verbose:
        print 'set_db.site:',site
        print 'set_db.role:',role
    settings = get_settings(site=site, role=role, verbose=verbose)
    assert settings, 'Unable to load Django settings for site %s.' % (site,)
    env.django_settings = settings
    if verbose:
        print 'settings:',settings
        print 'databases:',settings.DATABASES
    default_db = settings.DATABASES[name]
    if verbose:
        print 'default_db:',default_db
    env.db_name = default_db['NAME']
    env.db_user = default_db['USER']
    env.db_host = default_db['HOST']
    env.db_password = default_db['PASSWORD']
    env.db_engine = default_db['ENGINE']
    
    if 'mysql' in env.db_engine.lower():
        env.db_type = 'mysql'
    elif 'postgres' in env.db_engine.lower() or 'postgis' in env.db_engine.lower():
        env.db_type = 'postgresql'
    elif 'sqlite' in env.db_engine.lower():
        env.db_type = 'sqlite'
    else:
        env.db_type = env.db_engine    
    
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
        site = site or env.SITE
        if verbose:
            print 'get_settings.site:',env.SITE
            print 'get_settings.role:',env.ROLE
        common.set_site(site)
        tmp_role = env.ROLE
        if role:
            env.ROLE = os.environ[ROLE] = role
        check_remote_paths(verbose=verbose)
        if verbose:
            print 'get_settings.django_settings_module_template:',env.django_settings_module_template
            print 'get_settings.django_settings_module:',env.django_settings_module
        env.django_settings_module = env.django_settings_module_template % env
        try:
    #        module = __import__(
    #            env.django_settings_module,
    #            fromlist='.'.join(env.django_settings_module.split('.')[:-1]))
            #print 'env.src_dir:',env.src_dir
            #settings_dir = os.path.split(os.path.join(env.src_dir, env.django_settings_module.replace('.', '/')))[0]
            #print 'settings_dir:',settings_dir
            os.environ['SITE'] = env.SITE
            os.environ['ROLE'] = env.ROLE
#            if verbose:
#                print 'SITE:',env.SITE
#                print 'ROLE:',env.ROLE
#                print 'env.django_settings_module:',env.django_settings_module
            module = importlib.import_module(env.django_settings_module)
#            print 'module.__name__:',module.__name__
#            settings_dir = os.path.split(module.__file__)[0]
#            print 'settings_dir:',settings_dir
    #        sys.modules[module.__name__] = module # This isn't done automatically by import?!
    
            # Note, we have to reload the settings module whenever we change the
            # SITE or ROLE environment variables.
            
            #does not work
    #        import reimport
    #        reimport.reimport(module)
    
            #does not work
    #        print 'Reloading...'
    #        cmd = 'rm -f %s/*.pyc' % (settings_dir,)
    #        print cmd
    #        os.system(cmd)
    #        print os.listdir(settings_dir)
    #        for fn in os.listdir(settings_dir):
    #            path = os.path.join(settings_dir, fn)
    #            os.utime(path, None)
    #        #module = reload(module)
    #        module = reload(sys.modules[module.__name__])
    #        use_reimport = True
    #        try:
    #            import reimport
    #        except ImportError:
    #            use_reimport = False
    #        if use_reimport:
    #            reimport(module)
    #        print 'Reloaded.'
    
            # Works as long as settings.py doesn't also reload anything.
            import imp
            imp.reload(module)
            
        except ImportError, e:
            print 'Warning: Could not import settings for site "%s": %s' % (site, e)
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
def execute_sql(fn, name='default', site=None):
    """
    Executes an arbitrary SQL file.
    """
    from burlap.dj import set_db
    from burlap.db import load_db_set
    
    assert os.path.isfile(fn), 'Missing file: %s' % fn
    
    site_summary = {} # {site: ret}
    
    for site, site_data in common.iter_sites(site=site, no_secure=True):
        try:
                    
            set_db(name=name, site=site)
            load_db_set(name=name)
            env.SITE = site
                    
            put_or_dryrun(local_path=fn)
            
            with settings(warn_only=True):
                ret = None
                if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
                    ret = run_or_dryrun("psql --host=%(db_host)s --user=%(db_user)s -d %(db_name)s -f %(put_remote_path)s" % env)
                                
                elif 'mysql' in env.db_engine:
                    ret = run_or_dryrun("mysql -h %(db_host)s -u %(db_user)s -p'%(db_password)s' %(db_name)s < %(put_remote_path)s" % env)
                    
                else:
                    raise NotImplementedError, 'Unknown database type: %s' % env.db_engine
                
            print 'ret:', ret
            site_summary[site] = ret
                    
        except KeyError as e:
            site_summary[site] = 'Error: %s' % str(e) 
            pass
            
    print '-'*80
    print 'Site Summary:'
    for site, ret in sorted(site_summary.items(), key=lambda o: o[0]):
        print site, ret
    
@task_or_dryrun
def install_sql(name='default', site=None):
    """
    Installs all custom SQL.
    """
    from burlap.dj import set_db
    from burlap.db import load_db_set
    
    set_db(name=name, site=site)
    load_db_set(name=name)
    paths = glob.glob(env.django_install_sql_path_template % env)
    #paths = glob.glob('%(src_dir)s/%(app_name)s/*/sql/*' % env)
    
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
            matches = re.findall('[\s\t]+VIEW[\s\t]+([a-zA-Z0-9_]+)', content, flags=re.IGNORECASE)
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
            print>>sys.stderr, '%i files could not be loaded.' % len(terminal)
            for path in sorted(list(terminal)):
                print>>sys.stderr, path
            print>>sys.stderr
    
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
    from burlap.dj import render_remote_paths
    
    set_site(site)
    
    render_remote_paths()
    
    env.db_createsuperuser_username = username
    env.db_createsuperuser_email = email or username
    run_or_dryrun('export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s createsuperuser --username=%(db_createsuperuser_username)s --email=%(db_createsuperuser_email)s' % env)

@task_or_dryrun
def install_fixtures(name, site=None):
    """
    Installs a set of Django fixtures.
    """
    from burlap.dj import render_remote_paths
    set_site(site)
    
    render_remote_paths()
    
    fixtures_paths = env.db_fixture_sets.get(name, [])
    for fixture_path in fixtures_paths:
        env.db_fq_fixture_path = os.path.join(env.remote_app_src_package_dir, fixture_path)
        print 'Loading %s...' % (env.db_fq_fixture_path,)
        if not env.is_local and not files.exists(env.db_fq_fixture_path):
            put_or_dryrun(
                local_path=env.db_fq_fixture_path,
                remote_path='/tmp/data.json',
                use_sudo=True,
                )
            env.db_fq_fixture_path = env.put_remote_path
        cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s loaddata %(db_fq_fixture_path)s' % env
        print cmd
        run_or_dryrun(cmd)

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

@task_or_dryrun
def post_db_create(name=None, site=None):
    assert env[ROLE]
    require('app_name')
    site = site or env.SITE
    #print 'site:',site
    set_db(name=name, site=site, verbose=1)
    load_db_set(name=name)
#    print 'site:',env[SITE]
#    print 'role:',env[ROLE]
    
    syncdb(all=True, site=site)
    migrate(fake=True, site=site)
    install_sql(name=name, site=site)
    #createsuperuser()

@task_or_dryrun
def database_files_dump(site=None):
    """
    Runs the Django management command to export files stored in the database to the filesystem.
    Assumes the app django_database_files is installed.
    """
    from burlap.dj import render_remote_paths
    set_site(site or env.SITE)
    
    render_remote_paths()
    
    cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s database_files_dump' % env
    if env.is_local:
        local_or_dryrun(cmd)
    else:
        run_or_dryrun(cmd)

@task_or_dryrun
def record_manifest_media(verbose=0):
    latest_timestamp = -1e9999999999999999
    if 'dj' in env.services:
        for path in iter_static_paths():
            latest_timestamp = max(
                latest_timestamp,
                common.get_last_modified_timestamp(path) or latest_timestamp)
    if int(verbose):
        print latest_timestamp
    return latest_timestamp

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
            print data
    return data

@task_or_dryrun
#@runs_once
def update(name=None, site=None, skip_databases=None, do_install_sql=0, migrate_apps=''):
    """
    Updates schema and custom SQL.
    """
    #from burlap.dj import set_db
    
    set_db(name=name, site=site)
    syncdb(site=site) # Note, this loads initial_data fixtures.
    migrate(
        site=site,
        skip_databases=skip_databases,
        migrate_apps=migrate_apps)
    if int(do_install_sql):
        install_sql(name=name, site=site)
    #TODO:run syncdb --all to force population of new content types?

@task_or_dryrun
#@runs_once
def update_all(skip_databases=None, do_install_sql=0, migrate_apps=''):
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
    
    for site in sites:
        update(
            site=site,
            skip_databases=skip_databases,
            do_install_sql=do_install_sql,
            migrate_apps=migrate_apps)

@task_or_dryrun
def update_all_from_diff(last=None, current=None):
    migrate_apps = []
    if last and current:
        last = last['DJANGO_MIGRATIONS']
        current = current['DJANGO_MIGRATIONS']
        for app_name in current:
            if current[app_name] != last.get(app_name):
                migrate_apps.append(app_name)
    return update_all(migrate_apps=','.join(migrate_apps))

class DjangoMediaSatchel(Satchel):
    
    name = 'djangomedia'
    
    tasks = (
        'configure',
    )
    
    def set_defaults(self):
        super(DjangoMediaSatchel, self).set_defaults()
        
        self.env.media_dirs = ['static']
        self.env.manage_dir = 'src'
    
    def record_manifest(self):
        from burlap.common import get_last_modified_timestamp
        data = 0
        for path in self.env.media_dirs:
            data = min(data, get_last_modified_timestamp(path) or data)
        #TODO:hash media names and content
        if self.verbose:
            print data
        return data
    
    def configure(self, *args, **kwargs):
        self.local_or_dryrun('cd %(manage_dir)s; ./manage collectstatic --noinput' % self.lenv)
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'apache2', 'pip', 'user']

common.manifest_recorder[DJANGO_MEDIA] = record_manifest_media
common.manifest_recorder[DJANGO_MIGRATIONS] = record_manifest_migrations

# DJANGO_SYNCDB = 'DJANGO_SYNCDB'
# DJANGO_MIGRATIONS = 'DJANGO_MIGRATIONS'

common.add_deployer(DJANGO_MIGRATIONS, 'dj.update_all_from_diff',
    before=['packager', 'apache', 'apache2', 'pip', 'tarball', 'django_media'],
    takes_diff=True)

DjangoMediaSatchel()
