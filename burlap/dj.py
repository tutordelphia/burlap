"""
Django-specific helper utilities.
"""
import os
import sys
import importlib
import traceback
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

def iter_app_directories(ignore_import_error=False):
    #from django.utils.importlib import import_module
    from importlib import import_module
    settings = get_settings()
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

def iter_south_migrations(dir, *args, **kwargs):
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
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = {}
    
    settings = get_settings()
    
    # Record apps.
    data['installed_apps'] = settings.INSTALLED_APPS
    
    # Record database migrations.
    data['south'] = {}
    for south_app_name, dir in iter_south_directories(ignore_import_error=True):
        #print 'south:',dir
        data['south'][south_app_name] = []
        for fn in iter_south_migrations(dir):
            #print '\t',fn
            data['south'][south_app_name].append(fn)
    
    #TODO: Record hashes of all files in all app static directories.
    
    return data

@task_or_dryrun
def compare_manifest(data=None):
    """
    Called before a deployment, given the data returned by record_manifest(),
    for determining what, if any, tasks need to be run to make the target
    server reflect the current settings within the current context.
    """
    
    old = data or {}
    
    pre = ['tarball', 'pip', 'packager']
    
    methods = []
    
    old.setdefault('south', {})
    
    settings = get_settings()

    # Check installed apps and run syncdb for all that aren't managed by South.
    current_south_apps = set(
        _n for _n, _ in iter_south_directories(ignore_import_error=True)
    )
    old_apps = set(old.get('installed_apps', []))
    syncdb = False
    for app_name in settings.INSTALLED_APPS:
        if app_name in current_south_apps:
            pass
        else:
            if app_name not in old_apps and app_name not in old['south']:
                methods.append(QueuedCommand('dj.syncdb', kwargs=dict(site=ALL), pre=pre))
                syncdb = True
                break

    # Check South migrations.
    # We assume all inter-migration dependencies are appropriately documented
    # in the migrations. You know what those are, right?
    for south_app_name, dir in iter_south_directories(ignore_import_error=True):
        #print 'south:',south_app_name, dir
        #data['south'].setdefault(app_name, [])
        migrations = list(iter_south_migrations(dir))
        
        if south_app_name in old.get('installed_apps', []) and south_app_name not in old['south']:
            # A special case.
            # Somewhat rare, but very frustrating when it occurs.
            # The app was previously installed but not under South control,
            # but the author has since converted it to South.
            # This means the models exist in the database, but in order
            # to apply the new migrations, we must fake the initial migration
            # then apply the rest normally.
            methods.append(QueuedCommand('dj.migrate', kwargs=dict(site=ALL, app=south_app_name, migration='0001', fake=True), pre=pre))
            methods.append(QueuedCommand('dj.migrate', kwargs=dict(site=ALL, app=south_app_name), pre=pre))
        else:
            # Otherwise, find which migrations haven't been applied since the
            # last deployment and register a migrate command if any exist.
            old['south'].setdefault(south_app_name, [])
            new_migrations = set(migrations)
            old_migrations = set(old['south'][south_app_name])
            if new_migrations != old_migrations:
                methods.append(QueuedCommand('dj.migrate', kwargs=dict(site=ALL, app=south_app_name), pre=pre))
    
    #TODO: Compare hashes of all files in all app static directories.
    
    return methods
    
common.manifest_recorder[DJANGO] = record_manifest
common.manifest_comparer[DJANGO] = compare_manifest
