"""
Django-specific helper utilities.
"""
import os
import sys
import importlib
import traceback
import commands
from StringIO import StringIO

from fabric.api import (
    env,
    require,
    settings,
    cd,
)

from burlap import common
from burlap.common import (
    ROLE, QueuedCommand, ALL,
    sudo_or_dryrun,
    run_or_dryrun,
    local_or_dryrun,
)
from burlap.decorators import task_or_dryrun

env.setdefault('dj_settings_loaded', False)
if not env.dj_settings_loaded:
    env.dj_settings_loaded = True
    
    # The default django settings module import path.
    print>>sys.stderr, 'reset django settings module template!!!'
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

DJANGO = 'DJANGO'
DJANGO_MEDIA = 'DJANGO_MEDIA'
DJANGO_SYNCDB = 'DJANGO_SYNCDB'
DJANGO_MIGRATIONS = 'DJANGO_MIGRATIONS'

@task_or_dryrun
def check_remote_paths(verbose=1):
    if 'django_settings_module' in env:
        return
    render_remote_paths(verbose)

@task_or_dryrun
def render_remote_paths(verbose=0):
    verbose = int(verbose)
    env.django_settings_module = env.django_settings_module_template % env
    env.remote_app_dir = env.remote_app_dir_template % env
    env.remote_app_src_dir = env.remote_app_src_dir_template % env
    env.remote_app_src_package_dir = env.remote_app_src_package_dir_template % env
    if env.is_local:
        if env.remote_app_dir.startswith('./') or env.remote_app_dir == '.':
            env.remote_app_dir = os.path.abspath(env.remote_app_dir)
        if env.remote_app_src_dir.startswith('./') or env.remote_app_src_dir == '.':
            env.remote_app_src_dir = os.path.abspath(env.remote_app_src_dir)
        if env.remote_app_src_package_dir.startswith('./') or env.remote_app_src_package_dir == '.':
            env.remote_app_src_package_dir = os.path.abspath(env.remote_app_src_package_dir)
    env.remote_manage_dir = env.remote_manage_dir_template % env
    env.shell_default_dir = env.shell_default_dir_template % env
    if verbose:
        print 'render_remote_paths'
        print 'django_settings_module_template:',env.django_settings_module_template
        print 'django_settings_module:',env.django_settings_module
        print 'shell_default_dir:',env.shell_default_dir
        print 'src_dir:',env.src_dir
        print 'remote_app_dir:',env.remote_app_dir
        print 'remote_app_src_dir:',env.remote_app_src_dir
        print 'remote_app_src_package_dir_template:',env.remote_app_src_package_dir_template
        print 'remote_app_src_package_dir:',env.remote_app_src_package_dir
        print 'remote_manage_dir:',env.remote_manage_dir

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
def syncdb(site=None):
    """
    Runs the standard Django syncdb command for one or more sites.
    """
    
    render_remote_paths()
    for site, site_data in iter_unique_databases(site=site):
        cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s syncdb' % env
        run_or_dryrun(cmd)

@task_or_dryrun
def migrate(app='', migration='', site=None, fake=0):
    """
    Runs the standard South migrate command for one or more sites.
    """
    
    render_remote_paths()
    env.django_migrate_migration = migration
    env.django_migrate_fake_str = '--fake' if int(fake) else ''
    for site, site_data in iter_unique_databases(site=site):
        if app in env.django_settings.INSTALLED_APPS:
            env.django_migrate_app = app
        else:
            env.django_migrate_app = ''
        cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate %(django_migrate_app)s %(django_migrate_migration)s %(django_migrate_fake_str)s' % env
        cmd = cmd.strip()
        run_or_dryrun(cmd)

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
    return default_db

def has_database(name, site=None, role=None):
    settings = get_settings(site=site, role=role, verbose=0)
    return name in settings.DATABASES

@task_or_dryrun
def get_settings(site=None, role=None, verbose=1):
    """
    Retrieves the Django settings dictionary.
    """
    stdout = sys.stdout
    stderr = sys.stderr
    verbose = int(verbose)
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
def record_manifest_media(verbose=0):
    latest_timestamp = -1e9999999999999999
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
    for app_name, _dir in iter_app_directories():
        migration_dir = os.path.join(_dir, 'migrations')
        if not os.path.isdir(migration_dir):
            continue
        for migration_name in iter_migrations(migration_dir):
            data[app_name] = migration_name
    if int(verbose):
        print data
    return data
    
common.manifest_recorder[DJANGO_MEDIA] = record_manifest_media
common.manifest_recorder[DJANGO_MIGRATIONS] = record_manifest_migrations

# DJANGO_SYNCDB = 'DJANGO_SYNCDB'
# DJANGO_MIGRATIONS = 'DJANGO_MIGRATIONS'

common.add_deployer(DJANGO_MIGRATIONS, 'db.update_all_from_diff',
    before=['packager', 'apache', 'apache2', 'pip', 'tarball', 'django_media'],
    takes_diff=True)
