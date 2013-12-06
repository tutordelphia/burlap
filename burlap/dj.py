"""
Django-specific helper utilities.
"""
import os
import sys
import importlib

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    run as _run,
    settings,
    sudo,
    cd,
    task,
)

from burlap import common
from burlap.common import ROLE, QueuedCommand

# The default django settings module import path.
env.django_settings_module_template = '%(app_name)s.settings.settings'

# This is the name of the executable to call to access Django's management
# features.
env.django_manage = './manage'

DJANGO = 'DJANGO'

def iter_app_directories(ignore_import_error=False):
    from django.utils.importlib import import_module
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

def get_settings(site=None, role=None):
    """
    Retrieves the Django settings dictionary.
    """
    sys.path.insert(0, env.src_dir)
    if site and site.endswith('_secure'):
        site = site[:-7]
    common.set_site(site)
    tmp_role = env.ROLE
    if role:
        env.ROLE = os.environ[ROLE] = role
    env.django_settings_module = env.django_settings_module_template % env
    print 'Django settings module:',env.django_settings_module
    try:
#        module = __import__(
#            env.django_settings_module,
#            fromlist='.'.join(env.django_settings_module.split('.')[:-1]))
        #print 'env.src_dir:',env.src_dir
        #settings_dir = os.path.split(os.path.join(env.src_dir, env.django_settings_module.replace('.', '/')))[0]
        #print 'settings_dir:',settings_dir
        os.environ['SITE'] = env.SITE
        os.environ['ROLE'] = env.ROLE
        print 'SITE:',env.SITE
        print 'ROLE:',env.ROLE
        module = importlib.import_module(env.django_settings_module)
#        print 'module.__name__:',module.__name__
#        settings_dir = os.path.split(module.__file__)[0]
#        print 'settings_dir:',settings_dir
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
        print 'Warning: Could not import settings for site "%s"' % (site,)
        #raise # breaks *_secure pseudo sites
        return
    finally:
        env.ROLE = os.environ[ROLE] = tmp_role
    return module

@task
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

@task
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
    old_apps = set(old['installed_apps'])
    syncdb = False
    for app_name in settings.INSTALLED_APPS:
        if app_name in current_south_apps:
            pass
        else:
            if app_name not in old_apps and app_name not in old['south']:
                methods.append(QueuedCommand('dj.syncdb', pre=pre))
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
            methods.append(QueuedCommand('dj.migrate', args=(south_app_name, '0001'), kwargs=dict(fake=True), pre=pre))
            methods.append(QueuedCommand('dj.migrate', args=(south_app_name,), pre=pre))
        else:
            # Otherwise, find which migrations haven't been applied since the
            # last deployment and register a migrate command if any exist.
            old['south'].setdefault(south_app_name, [])
            new_migrations = set(migrations)
            old_migrations = set(old['south'][south_app_name])
            if new_migrations != old_migrations:
                methods.append(QueuedCommand('dj.migrate', args=(south_app_name,), pre=pre))
    
    #TODO: Compare hashes of all files in all app static directories.
    
    return methods
    
common.manifest_recorder[DJANGO] = record_manifest
common.manifest_comparer[DJANGO] = compare_manifest
