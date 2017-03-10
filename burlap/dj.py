"""
Django-specific helper utilities.
"""
from __future__ import print_function

import os
import re
import sys
import traceback
import glob
from importlib import import_module
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
        self.env.settings_module = '{app_name}.settings'
        
        # The folder containing manage.py.
        self.env.project_dir = None
        
        # The folder containing manage.py on the local filesystem.
        self.env.local_project_dir = None

        self.env.shell_template = 'cd {project_dir}; /bin/bash -i -c \"{manage_cmd} shell;\"'
        
        # These apps will be migrated on a specific database, while faked
        # on all others.
        # This is necessary since South does not have proper support for
        # multi-database applications.
        #./manage migrate <app> --fake
        #./manage migrate --database=<database> <app>
        self.env.migrate_fakeouts = [] # [{database:<database>, app:<app>}]
        
        self.env.install_sql_path_template = '{src_dir}/{app_name}/*/sql/*'
        
        # The target version of Django to assume.
        self.env.version = (1, 6, 0)
        
        self.env.media_dirs = ['static']
        
        # The path relative to fab where the code resides.
        self.env.src_dir = 'src'
        
        self.env.manage_dir = 'src'
        
        self.env.ignore_errors = 0
        
        # Modules whose name start with one of these values will be deleted before settings are imported.
        self.env.delete_module_with_prefixes = []

    def has_database(self, name, site=None, role=None):
        settings = self.get_settings(site=site, role=role)
        return name in settings.DATABASES

    @task
    def get_settings(self, site=None, role=None):
        """
        Retrieves the Django settings dictionary.
        """
        r = self.local_renderer
        _stdout = sys.stdout
        _stderr = sys.stderr
        if not self.verbose:
            sys.stdout = StringIO()
            sys.stderr = StringIO()
        try:
            sys.path.insert(0, r.env.src_dir)
            
            # Temporarily override SITE.
            tmp_site = self.genv.SITE
            if site and site.endswith('_secure'):
                site = site[:-7]
            site = site or self.genv.SITE or self.genv.default_site
            self.set_site(site)
            
            # Temporarily override ROLE.
            tmp_role = self.genv.ROLE
            if role:
                self.set_role(role)

            try:
                # We need to explicitly delete sub-modules from sys.modules. Otherwise, reload() skips
                # them and they'll continue to contain obsolete settings.
                if r.env.delete_module_with_prefixes:
                    for name in sorted(sys.modules):
                        for prefix in r.env.delete_module_with_prefixes:
                            if name.startswith(prefix):
                                if self.verbose:
                                    print('Deleting module %s prior to re-import.' % name)
                                del sys.modules[name]
                                break
                        
                if r.env.settings_module in sys.modules:
                    del sys.modules[r.env.settings_module]
                module = import_module(r.format(r.env.settings_module))
        
                # Works as long as settings.py doesn't also reload anything.
                import imp
                imp.reload(module)
                
            except ImportError as e:
                print('Warning: Could not import settings for site "%s": %s' % (site, e), file=_stdout)
                traceback.print_exc(file=_stdout)
                #raise # breaks *_secure pseudo sites
                return
            finally:
                if tmp_site:
                    self.set_site(tmp_site)
                if tmp_role:
                    self.set_role(tmp_role)
        finally:
            sys.stdout = _stdout
            sys.stderr = _stderr
            sys.path.remove(r.env.src_dir)
        return module

    def set_db(self, name=None, site=None, role=None):
        r = self.local_renderer
        name = name or 'default'
        site = site or r.env.get('SITE') or r.genv.SITE or r.genv.default_site
        role = role or r.env.get('ROLE') or r.genv.ROLE
        settings = self.get_settings(site=site, role=role)
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
        
        for k, v in r.genv.iteritems():
            if not k.startswith(self.name.lower()+'_db_'):
                continue
            print('db.kv:', k, v)
        
        return default_db

    @task
    def install_sql(self, site=None, database='default', apps=None, stop_on_error=0):
        """
        Installs all custom SQL.
        """
        #from burlap.db import load_db_set
        
        stop_on_error = int(stop_on_error)
        
        name = database
        self.set_db(name=name, site=site)

        r = self.local_renderer
        paths = glob.glob(r.format(r.env.install_sql_path_template))
        
        apps = [_ for _ in (apps or '').split(',') if _.strip()]
        if self.verbose:
            print('install_sql.apps:', apps)
        
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
            paths = list(sorted(paths))
            error_counts = defaultdict(int) # {path:count}
            terminal = set()
            if self.verbose:
                print('Checking %i paths.' % len(paths))
            while paths:
                path = paths.pop(0)
                if self.verbose:
                    print('path:', path)
                app_name = re.findall(r'/([^/]+)/sql/', path)[0]
                if apps and app_name not in apps:
                    self.vprint('skipping because app_name %s not in apps' % app_name)
                    continue
                with self.settings(warn_only=True):
                    if self.is_local:
                        r.env.sql_path = path
                    else:
                        r.env.sql_path = '/tmp/%s' % os.path.split(path)[-1]
                        r.put(local_path=path, remote_path=r.env.sql_path)
                    ret = r.run_or_local(cmd_template)
                    if ret and ret.return_code:
                        
                        if stop_on_error:
                            raise Exception('Unable to execute file %s' % path)
                            
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
        
        if self.verbose:
            print('install_sql.db_engine:', r.env.db_engine)
        
        if 'postgres' in r.env.db_engine or 'postgis' in r.env.db_engine:
            run_paths(
                paths=get_paths('postgresql'),
                cmd_template="psql --host={db_host} --user={db_user} -d {db_name} -f {sql_path}")
                        
        elif 'mysql' in r.env.db_engine:
            run_paths(
                paths=get_paths('mysql'),
                cmd_template="mysql -v -h {db_host} -u {db_user} -p'{db_password}' {db_name} < {sql_path}")
                
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
        r.run_or_local('export SITE={SITE}; export ROLE={ROLE};{environs} cd {project_dir}; {manage_cmd} {cmd} {args} {kwargs}')

    @task
    def manage_all(self, *args, **kwargs):
        """
        Runs manage() across all unique site default databases.
        """
        for site, site_data in self.iter_unique_databases(site='all'):
            if self.verbose:
                print('-'*80, file=sys.stderr)
                print('site:', site, file=sys.stderr)
            if self.env.available_sites_by_host:
                hostname = self.current_hostname
                sites_on_host = self.env.available_sites_by_host.get(hostname, [])
                if sites_on_host and site not in sites_on_host:
                    self.vprint('skipping site:', site, sites_on_host, file=sys.stderr)
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
        r = self.local_renderer
        if '@' in self.genv.host_string:
            r.env.shell_host_string = self.genv.host_string
        else:
            r.env.shell_host_string = '{user}@{host_string}'
        r.env.shell_default_dir = self.genv.shell_default_dir_template
        r.env.shell_interactive_djshell_str = self.genv.interactive_shell_template
        r.run_or_local('ssh -t -i {key_filename} {shell_host_string} "{shell_interactive_djshell_str}"')
        
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
                r.run_or_local(
                    'export SITE={SITE}; export ROLE={ROLE}; cd {project_dir}; '
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
                    r.run_or_local(
                        'export SITE={SITE}; export ROLE={ROLE}; cd {project_dir}; '
                        '{manage_cmd} migrate --noinput {migrate_merge} --traceback '
                        '{migrate_database} {delete_ghosts} {migrate_app} {migrate_migration} '
                        '{migrate_fake_str}')

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
        r.run('export SITE={SITE}; export ROLE={ROLE}; cd {app_dir}; {manage_cmd} schemamigration {app} --initial')
        r.run('export SITE={SITE}; export ROLE={ROLE}; cd {app_dir}; {manage_cmd} migrate {app} --fake')

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
            r.env.end_email_command = ''
            if end_message:
                end_message = end_message + ' for ' + site
                end_message = end_message.replace(' ', '_')
                r.env.end_message = end_message
                r.env.end_email_command = r.format('{manage_cmd} send_mail --subject={end_message} --recipients={recipients}')
            r.env.name = name.format(**r.genv)
            r.run(
                'screen -dmS {name} bash -c "export SITE={SITE}; '\
                'export ROLE={ROLE}; cd {project_dir}; '\
                '{manage_cmd} {command} --traceback; {end_email_command}"; sleep 3;')

    def get_media_timestamp(self):
        latest_timestamp = -1e9999999999999999
        for path in self.iter_static_paths():
            if self.verbose:
                print('checking timestamp of path:', path)
            latest_timestamp = max(
                latest_timestamp,
                get_last_modified_timestamp(path) or latest_timestamp)
        if self.verbose:
            print('latest_timestamp:', latest_timestamp)
        return latest_timestamp
        
    @property
    def media_changed(self):
        lm = self.last_manifest
        last_timestamp = lm.latest_timestamp
        current_timestamp = self.get_media_timestamp()
        self.vprint('last_timestamp:', last_timestamp)
        self.vprint('current_timestamp:', current_timestamp)
        return last_timestamp != current_timestamp

    def get_migration_fingerprint(self):
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
        return data

    def record_manifest(self):
        manifest = super(DjangoSatchel, self).record_manifest()
        manifest['latest_timestamp'] = self.get_media_timestamp()
        manifest['migrations'] = self.get_migration_fingerprint()
        return manifest
    
    @task(precursors=['packager', 'pip'])
    def configure_media(self, *args, **kwargs):
        if self.media_changed:
            r = self.local_renderer
            assert r.env.local_project_dir
            r.local('cd {local_project_dir}; {manage_cmd} collectstatic --noinput')
        
    @task(precursors=['packager', 'apache', 'pip', 'tarball', 'postgresql', 'mysql'])
    def configure_migrations(self):
        last = self.last_manifest.migrations or {}
        current = self.current_manifest.get('migrations') or {}
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
                self.migrate(app=app, ignore_errors=self.env.ignore_errors)

    @task(precursors=['packager'])
    def configure(self, *args, **kwargs):
        self.configure_media()
        self.configure_migrations()

dj = DjangoSatchel()
