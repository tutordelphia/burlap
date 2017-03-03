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

from burlap import Satchel
from burlap.constants import *
from burlap.decorators import task
from burlap.common import get_last_modified_timestamp

class DjangoSatchel(Satchel):

    # We don't use "django" as the name so as to not conflict with the official django package.    
    name = 'dj'
    
    def set_defaults(self):
        
        # This is the name of the executable to call to access Django's management features.
        self.env.manage_cmd = 'manage.py'
        
        # This is the name of your Django application.
        self.env.app_name = None
        
        # This is the import path to your Django settings file.
        self.env.settings_module_template = '{app_name}.settings'
        
        self.env.shell_template = 'cd {project_dir}; /bin/bash -i -c \"{manage_cmd} shell;\"'
        
        # These apps will be migrated on a specific database, while faked
        # on all others.
        # This is necessary since South does not have proper support for
        # multi-database applications.
        #./manage migrate <app> --fake
        #./manage migrate --database=<database> <app>
        self.env.migrate_fakeouts = [] # [{database:<database>, app:<app>}]
        
        self.env.install_sql_path_template = '%(src_dir)s/%(app_name)s/*/sql/*'
        
        # The target version of Django to assume.
        self.env.version = (1, 6, 0)
        
        self.env.media_dirs = ['static']
        
        self.env.manage_dir = 'src'
        
        self.env.ignore_errors = 0

    def has_database(self, name, site=None, role=None):
        settings = self.get_settings(site=site, role=role, verbose=0)
        return name in settings.DATABASES

    @task
    def get_settings(self, site=None, role=None):
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
            sys.path.insert(0, self.env.src_dir)
            if site and site.endswith('_secure'):
                site = site[:-7]
            site = site or self.env.SITE or self.env.default_site
    #         if verbose:
    #             print('get_settings.site:',env.SITE)
    #             print('get_settings.role:',env.ROLE)
            self.set_site(site)
            tmp_role = self.env.ROLE
            if role:
                self.env.ROLE = os.environ[ROLE] = role

            self.env.settings_module = self.env.settings_module_template
            try:
                os.environ['SITE'] = self.env.SITE
                os.environ['ROLE'] = self.env.ROLE
                
                # We need to explicitly delete sub-modules from sys.modules. Otherwise, reload() skips
                # them and they'll continue to contain obsolete settings.
                for name in sorted(sys.modules):
                    if name.startswith('alphabuyer.settings.role_') \
                    or name.startswith('alphabuyer.settings.site_'):
                        del sys.modules[name]
                if self.env.settings_module in sys.modules:
                    del sys.modules[self.env.settings_module]
                module = importlib.import_module(self.env.settings_module)
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
                self.env.ROLE = os.environ[ROLE] = tmp_role
        finally:
            sys.stdout = stdout
            sys.stderr = stderr
        return module

    def set_db(self, name=None, site=None, role=None, verbose=0):
        r = self.local_renderer
        name = name or 'default'
        site = site or r.env.SITE
        role = role or r.env.ROLE
        settings = self.get_settings(site=site, role=role, verbose=verbose)
        assert settings, 'Unable to load Django settings for site %s.' % (site,)
        r.env.django_settings = settings
        default_db = settings.DATABASES[name]
        r.env.db_name = default_db['NAME']
        r.env.db_user = default_db['USER']
        r.env.db_host = default_db['HOST']
        r.env.db_password = default_db['PASSWORD']
        r.env.db_engine = default_db['ENGINE']
        
        if 'mysql' in r.env.db_engine.lower():
            r.env.db_type = 'mysql'
        elif 'postgres' in r.env.db_engine.lower() or 'postgis' in r.env.db_engine.lower():
            r.env.db_type = 'postgresql'
        elif 'sqlite' in r.env.db_engine.lower():
            r.env.db_type = 'sqlite'
        else:
            r.env.db_type = r.env.db_engine
        
        return default_db

    @task
    def install_sql(self, site=None, database='default', apps=None):
        """
        Installs all custom SQL.
        """
        #from burlap.db import load_db_set
        
        name = database
        self.set_db(name=name, site=site)
        #load_db_set(name=name)
        paths = glob.glob(self.env.install_sql_path_template)
        #paths = glob.glob('%(src_dir)s/%(app_name)s/*/sql/*')
        
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
            r = self.local_renderer
            paths = list(paths)
            error_counts = defaultdict(int) # {path:count}
            terminal = set()
            while paths:
                path = paths.pop(0)
                app_name = re.findall(r'/([^/]+)/sql/', path)[0]
                if apps and app_name not in apps:
                    continue
                with self.settings(warn_only=True):
                    r.put(local_path=path)
                    error_code = r.run(cmd_template)
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
        
        if 'postgres' in self.env.db_engine or 'postgis' in self.env.db_engine:
            run_paths(
                paths=get_paths('postgresql'),
                cmd_template="psql --host=%(db_host)s --user=%(db_user)s -d %(db_name)s -f %(put_remote_path)s")
                        
        elif 'mysql' in self.env.db_engine:
            run_paths(
                paths=get_paths('mysql'),
                cmd_template="mysql -v -h %(db_host)s -u %(db_user)s -p'%(db_password)s' %(db_name)s < %(put_remote_path)s")
                
        else:
            raise NotImplementedError

    @task
    def createsuperuser(self, username='admin', email=None, password=None, site=None):
        """
        Runs the Django createsuperuser management command.
        """
        r = self.local_renderer
        self.set_site_specifics(site)
        r.env.db_createsuperuser_username = username
        r.env.db_createsuperuser_email = email or username
        r.run('export SITE={SITE}; export ROLE={ROLE}; '
            'cd {project_dir}; {manage_cmd} createsuperuser '
            '--username={db_createsuperuser_username} --email={db_createsuperuser_email}')

    @task
    def loaddata(self, path, site=None):
        """
        Runs the Dango loaddata management command.
        
        By default, runs on only the current site.
        
        Pass site=all to run on all sites.
        """
        site = site or self.env.SITE
        r = self.local_renderer
        r.env._loaddata_path = path
        for site, site_data in self.iter_sites(site=site, no_secure=True):
            try:
                self.set_db(site=site)
                r.env.SITE = site
                r.sudo('export SITE={SITE}; export ROLE={ROLE}; '
                    'cd {project_dir}; '
                    '{manage_cmd} loaddata {_loaddata_path}')
            except KeyError:
                pass

    @task
    def manage(self, cmd, *args, **kwargs):
        """
        A generic wrapper around Django's manage command.
        """
        r = self.local_renderer
        environs = kwargs.pop('environs', '').strip()
        if environs:
            environs = ' '.join('export %s=%s;' % tuple(_.split('=')) for _ in environs.split(','))
            environs = ' ' + environs + ' '
        r.env.cmd = cmd
        r.env.SITE = r.genv.SITE or r.genv.default_site
        r.env.args = ' '.join(map(str, args))
        r.env.kwargs = ' '.join(
            ('--%s' % _k if _v in (True, 'True') else '--%s=%s' % (_k, _v))
            for _k, _v in kwargs.iteritems())
        r.env.environs = environs
        cmd = 'export SITE={SITE}; export ROLE={ROLE};{environs} cd {project_dir}; {manage_cmd} {cmd} {args} {kwargs}'
        if r.genv.is_local:
            r.local(cmd)
        else:
            r.run(cmd)

    @task
    def manage_all(self, *args, **kwargs):
        """
        Runs manage() across all unique site default databases.
        """
        
        for site, site_data in self.iter_unique_databases(site='all'):
            print('-'*80, file=sys.stderr)
            print('site:', site, file=sys.stderr)
            
            if self.env.available_sites_by_host:
                hostname = self.current_hostname
                sites_on_host = self.env.available_sites_by_host.get(hostname, [])
                if sites_on_host and site not in sites_on_host:
                    print('skipping site:', site, sites_on_host, file=sys.stderr)
                    continue
                
            self.manage(*args, **kwargs)

    def load_django_settings(self):
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
        settings = self.get_settings()
        try:
            from django.contrib import staticfiles
            from django.conf import settings as _settings
            for k, v in settings.__dict__.iteritems():
                setattr(_settings, k, v)
        except (ImportError, RuntimeError):
            traceback.print_exc()
            
        return settings
    
    def iter_static_paths(self, ignore_import_error=False):
    
        self.load_django_settings()
    
        from django.contrib.staticfiles import finders, storage
        for finder in finders.get_finders():
            for _n, _s in finder.storages.iteritems():
                yield _s.location
    
    def iter_app_directories(self, ignore_import_error=False):
        from importlib import import_module
        
        settings = self.load_django_settings()
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
    
    def iter_south_directories(self, *args, **kwargs):
        for app_name, base_app_dir in self.iter_app_directories(*args, **kwargs):
            migrations_dir = os.path.join(base_app_dir, 'migrations')
            if not os.path.isdir(migrations_dir):
                continue
            yield app_name, migrations_dir
    
    def iter_migrations(self, d, *args, **kwargs):
        for fn in sorted(os.listdir(d)):
            if fn.startswith('_') or not fn.endswith('.py'):
                continue
            fqfn = os.path.join(d, fn)
            if not os.path.isfile(fqfn):
                continue
            yield fn
    
    def iter_unique_databases(self, site=None):
        r = self.local_renderer
        prior_database_names = set()
        for site, site_data in self.iter_sites(site=site, no_secure=True):
            self.set_db(site=site)
            key = (r.env.db_name, r.env.db_user, r.env.db_host, r.env.db_engine)
            if key in prior_database_names:
                continue
            prior_database_names.add(key)
            r.env.SITE = site
            yield site, site_data
    
    @task
    def shell(self):
        """
        Opens a Django focussed Python shell.
        Essentially the equivalent of running `manage.py shell`.
        """
        if '@' in self.env.host_string:
            self.env.shell_host_string = self.env.host_string
        else:
            self.env.shell_host_string = '%(user)s@%(host_string)s'
        self.env.shell_default_dir = self.env.shell_default_dir_template
        self.env.shell_interactive_djshell_str = self.env.interactive_shell_template
        if self.env.is_local:
            cmd = '%(shell_interactive_djshell_str)s'
        else:
            cmd = 'ssh -t -i %(key_filename)s %(shell_host_string)s "%(shell_interactive_djshell_str)s"'
        #print cmd
        os.system(cmd)
        
    @task
    def syncdb(self, site=None, all=0, database=None, ignore_errors=1): # pylint: disable=redefined-builtin
        """
        Runs the standard Django syncdb command for one or more sites.
        """
        r = self.local_renderer
        
        ignore_errors = int(ignore_errors)
        
        r.env.db_syncdb_all_flag = '--all' if int(all) else ''
        
        r.env.db_syncdb_database = ''
        if database:
            r.env.db_syncdb_database = ' --database=%s' % database

        for site, site_data in r.iter_unique_databases(site=site):
            r.env.SITE = site
            with self.settings(warn_only=ignore_errors):
                r.run(
                    'export SITE={SITE}; export ROLE={ROLE}; cd {remote_manage_dir}; '
                    '{manage_cmd} syncdb --noinput {db_syncdb_all_flag} {db_syncdb_database}')

    @task
    def migrate(self, app='', migration='', site=None, fake=0, ignore_errors=0, skip_databases=None, database=None, migrate_apps='', delete_ghosts=1):
        """
        Runs the standard South migrate command for one or more sites.
        """
    #     Note, to pass a comma-delimted list in a fab command, escape the comma with a back slash.
    #         
    #         e.g.
    #         
    #             fab staging dj.migrate:migrate_apps=oneapp\,twoapp\,threeapp
        
        r = self.local_renderer
        
        ignore_errors = int(ignore_errors)
        
        delete_ghosts = int(delete_ghosts)
        
        post_south = tuple(r.env.version) >= (1, 7, 0)
        
        if tuple(r.env.version) >= (1, 9, 0):
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
    
        #print('ignore_errors:', ignore_errors)
        
        r.env.migrate_migration = migration or ''
    #     print('r.env.migrate_migration:', r.env.migrate_migration)
        r.env.migrate_fake_str = '--fake' if int(fake) else ''
        r.env.migrate_database = '--database=%s' % database if database else ''
        r.env.migrate_merge = '--merge' if not post_south else ''
        r.env.delete_ghosts = '--delete-ghost-migrations' if delete_ghosts and not post_south else ''
        for site, site_data in self.iter_unique_databases(site=site):
    #         print('-'*80, file=sys.stderr)
    #         print('site:', site, file=sys.stderr)
            
            if self.env.available_sites_by_host:
                hostname = self.current_hostname
                sites_on_host = self.env.available_sites_by_host.get(hostname, [])
                if sites_on_host and site not in sites_on_host:
    #                 print('skipping site:', site, sites_on_host, file=sys.stderr)
                    continue
            
    #         print('migrate_apps:', migrate_apps, file=sys.stderr)
            if not migrate_apps:
                migrate_apps.append(' ')
                
            for app in migrate_apps:
    #             print('app:', app)
                r.env.migrate_app = app
    #             print('r.env.migrate_app:', r.env.migrate_app)
                r.env.SITE = site
                with self.settings(warn_only=ignore_errors):
                    r.run(
                    'export SITE={SITE}; export ROLE={ROLE}; cd {project_dir}; '
                    '{manage_cmd} migrate --noinput {migrate_merge} --traceback '
                    '{migrate_database} {delete_ghosts} {django_migrate_app} {django_migrate_migration} '
                    '{django_migrate_fake_str}')

    @task
    def migrate_all(self, *args, **kwargs):
        kwargs['site'] = 'all'
        return self.migrate(*args, **kwargs)

    @task
    def truncate(self, app):
        assert self.genv.SITE, 'This should only be run for a specific site.'
        r = self.local_renderer
        r.env.app = app
        r.run('rm -f {app_dir}/{app}/migrations/*.py')
        r.run('rm -f {app_dir}/{app}/migrations/*.pyc')
        r.run('touch {app_dir}/{app}/migrations/__init__.py')
        r.run('export SITE={SITE}; export ROLE={ROLE}; cd {app_dir}; ./manage schemamigration {app} --initial')
        r.run('export SITE={SITE}; export ROLE={ROLE}; cd {app_dir}; ./manage migrate {app} --fake')

    @task
    def manage_async(self, command='', name='process', site=ALL, exclude_sites='', end_message='', recipients=''):
        """
        Starts a Django management command in a screen.
        
        Parameters:
            
            command :- all arguments passed to `./manage` as a single string
            
            site :- the site to run the command for (default is all)
            
        Designed to be ran like:
        
            fab <role> dj.manage_async:"some_management_command --force"

        """
        exclude_sites = exclude_sites.split(':')
        r = self.local_renderer
        for site, site_data in self.iter_sites(site=site, no_secure=True):
            if site in exclude_sites:
                continue
            r.env.SITE = site
            r.env.command = command
            r.env.end_email_command = ''
            r.env.recipients = recipients or ''
            if end_message:
                end_message = end_message + ' for ' + site
                end_message = end_message.replace(' ', '_')
                r.env.end_email_command = (
                    '{django_manage_cmd} send_mail '\
                    '--subject=%s '\
                    '--recipients={recipients}; '
                ) % end_message
            r.env.name = name.format(**r.genv)
            r.run(
                'screen -dmS {name} bash -c "export SITE={SITE}; '\
                'export ROLE={ROLE}; cd /usr/local/alphabuyer/src/alphabuyer; '\
                './manage {command} --traceback; {end_email_command}"; sleep 3;')

    def record_manifest(self):
        manifest = super(DjangoSatchel, self).record_manifest()
        
        latest_timestamp = -1e9999999999999999
        for path in self.iter_static_paths():
            if self.verbose:
                print('checking timestamp of path:', path)
            latest_timestamp = max(
                latest_timestamp,
                get_last_modified_timestamp(path) or latest_timestamp)
        if self.verbose:
            print('latest_timestamp:', latest_timestamp)
        manifest['latest_timestamp'] = latest_timestamp

        data = {} # {app: latest_migration_name}
        for app_name, _dir in self.iter_app_directories():
            migration_dir = os.path.join(_dir, 'migrations')
            if not os.path.isdir(migration_dir):
                continue
            for migration_name in self.iter_migrations(migration_dir):
                data[app_name] = migration_name
        if self.verbose:
            print('%s.migrations:' % self.name)
            pprint(data, indent=4)
        manifest['migrations'] = data

        return latest_timestamp
    
    @task(precursors=['packager''pip'])
    def configure_media(self, *args, **kwargs):
        self.local('cd %(manage_dir)s; ./manage collectstatic --noinput' % self.lenv)
        
    @task(precursors=['packager', 'apache', 'pip', 'tarball', 'postgresql', 'mysql'])
    def configure_migrations(self):
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
                self.update_all(apps=app, ignore_errors=self.env.ignore_errors)

    @task(precursors=['packager'])
    def configure(self, *args, **kwargs):
        self.configure_media()
        self.configure_migrations()

dj = DjangoSatchel()
