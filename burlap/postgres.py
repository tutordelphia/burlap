"""
PostgreSQL users and databases
==============================

This module provides tools for creating PostgreSQL users and databases.

"""
from __future__ import print_function

import os

from fabric.api import cd, hide, sudo, settings, runs_once

from burlap import Satchel
from burlap.constants import *
from burlap.db import DatabaseSatchel
from burlap.decorators import task

POSTGIS = 'postgis'
POSTGRESQL = 'postgresql'

def _run_as_pg(command):
    """
    Run command as 'postgres' user
    """
    with cd('~postgres'):
        return sudo(command, user='postgres')


def user_exists(name):
    """
    Check if a PostgreSQL user exists.
    """
    with settings(hide('running', 'stdout', 'stderr', 'warnings'),
                  warn_only=True):
        res = _run_as_pg('''psql -t -A -c "SELECT COUNT(*) FROM pg_user WHERE usename = '%(name)s';"''' % locals())
    return (res == "1")


def create_user(name, password, superuser=False, createdb=False,
                createrole=False, inherit=True, login=True,
                connection_limit=None, encrypted_password=False):
    """
    Create a PostgreSQL user.

    Example::

        import burlap

        # Create DB user if it does not exist
        if not burlap.postgres.user_exists('dbuser'):
            burlap.postgres.create_user('dbuser', password='somerandomstring')

        # Create DB user with custom options
        burlap.postgres.create_user('dbuser2', password='s3cr3t',
            createdb=True, createrole=True, connection_limit=20)

    """
    options = [
        'SUPERUSER' if superuser else 'NOSUPERUSER',
        'CREATEDB' if createdb else 'NOCREATEDB',
        'CREATEROLE' if createrole else 'NOCREATEROLE',
        'INHERIT' if inherit else 'NOINHERIT',
        'LOGIN' if login else 'NOLOGIN',
    ]
    if connection_limit is not None:
        options.append('CONNECTION LIMIT %d' % connection_limit)
    password_type = 'ENCRYPTED' if encrypted_password else 'UNENCRYPTED'
    options.append("%s PASSWORD '%s'" % (password_type, password))
    options = ' '.join(options)
    _run_as_pg('''psql -c "CREATE USER %(name)s %(options)s;"''' % locals())


def drop_user(name):
    """
    Drop a PostgreSQL user.

    Example::

        import burlap

        # Remove DB user if it exists
        if burlap.postgres.user_exists('dbuser'):
            burlap.postgres.drop_user('dbuser')

    """
    _run_as_pg('''psql -c "DROP USER %(name)s;"''' % locals())


def database_exists(name):
    """
    Check if a PostgreSQL database exists.
    """
    with settings(hide('running', 'stdout', 'stderr', 'warnings'),
                  warn_only=True):
        return _run_as_pg('''psql -d %(name)s -c ""''' % locals()).succeeded


def create_database(name, owner, template='template0', encoding='UTF8',
                    locale='en_US.UTF-8'):
    """
    Create a PostgreSQL database.

    Example::

        import burlap

        # Create DB if it does not exist
        if not burlap.postgres.database_exists('myapp'):
            burlap.postgres.create_database('myapp', owner='dbuser')

    """
    _run_as_pg('''createdb --owner %(owner)s --template %(template)s \
                  --encoding=%(encoding)s --lc-ctype=%(locale)s \
                  --lc-collate=%(locale)s %(name)s''' % locals())


def drop_database(name):
    """
    Delete a PostgreSQL database.

    Example::

        import burlap

        # Remove DB if it exists
        if burlap.postgres.database_exists('myapp'):
            burlap.postgres.drop_database('myapp')

    """
    _run_as_pg('''dropdb %(name)s''' % locals())


def create_schema(name, database, owner=None):
    """
    Create a schema within a database.
    """
    if owner:
        _run_as_pg('''psql %(database)s -c "CREATE SCHEMA %(name)s AUTHORIZATION %(owner)s"''' % locals())
    else:
        _run_as_pg('''psql %(database)s -c "CREATE SCHEMA %(name)s"''' % locals())

class PostgreSQLSatchel(DatabaseSatchel):
    """
    Represents a PostgreSQL server.
    """
    
    name = 'postgresql'
    
    @property
    def packager_system_packages(self):
        return {
            (UBUNTU, '12.04'): ['postgresql-9.1'],
            (UBUNTU, '14.04'): ['postgresql-9.3'],
        }
    
    def set_defaults(self):
        super(PostgreSQLSatchel, self).set_defaults()
        
        self.env.dump_command = 'time pg_dump -c -U {db_user} --blobs --format=c --schema=public --host={db_host} {db_name} > {dump_fn}'
        self.env.createlangs = ['plpgsql'] # plpythonu
        self.env.postgres_user = 'postgres'
        self.env.encoding = 'UTF8'
        self.env.custom_load_cmd = ''
        self.env.port = 5432
        self.env.pgass_path = '~/.pgpass'
        self.env.pgpass_chmod = 600
        self.env.default_version = '9.3'
        self.env.version_command = '`psql --version | grep -o -E "[0-9]+.[0-9]+"`'
        self.env.engine = 'postgresql' # 'postgresql' | 'postgis'

        self.env.service_commands = {
            START:{
                UBUNTU: 'service postgresql start',
            },
            STOP:{
                UBUNTU: 'service postgresql stop',
            },
            ENABLE:{
                UBUNTU: 'update-rc.d postgresql defaults',
            },
            DISABLE:{
                UBUNTU: 'update-rc.d -f postgresql remove',
            },
            RESTART:{
                UBUNTU: 'service postgresql restart',
            },
            STATUS:{
                UBUNTU: 'service postgresql status',
            },
        }

    @task
    def write_pgpass(self, name=None, use_sudo=0):
        """
        Write the file used to store login credentials for PostgreSQL.
        """
        
        r = self.database_renderer(name)
        
        use_sudo = int(use_sudo)
        
        r.run('touch {pgass_path}')
        r.sudo('chmod {pgpass_chmod} {pgass_path}')
        
        r.append(
            '{db_host}:{port}:*:{db_user}:{db_password}',
            r.env.pgpass_path,
            use_sudo=use_sudo)
                    
        return cmds

    @task
    def drop_views(self, name=None, site=None):
        """
        Drops all views.
        """
        raise NotImplementedError
    #        SELECT 'DROP VIEW ' || table_name || ';'
    #        FROM information_schema.views
    #        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    #        AND table_name !~ '^pg_';
            # http://stackoverflow.com/questions/13643831/drop-all-views-postgresql
    #        DO$$
    #        BEGIN
    #        
    #        EXECUTE (
    #           SELECT string_agg('DROP VIEW ' || t.oid::regclass || ';', ' ')  -- CASCADE?
    #           FROM   pg_class t
    #           JOIN   pg_namespace n ON n.oid = t.relnamespace
    #           WHERE  t.relkind = 'v'
    #           AND    n.nspname = 'my_messed_up_schema'
    #           );
    #        
    #        END
    #        $$

    @task
    def exists(self, name='default', site=None):
        """
        Returns true if a database with the given name exists. False otherwise.
        """
            
        r = self.database_renderer(name=name, site=site)
            
#         kwargs = dict(
#             db_user=env.db_root_user,
#             db_password=env.db_root_password,
#             db_host=env.db_host,
#             db_name=env.db_name,
#         )
#         env.update(kwargs)
        
        # Set pgpass file.
#         if env.db_password:
#             self.write_pgpass(verbose=verbose, name=name)
        
#        cmd = ('psql --username={db_user} --no-password -l '\
#            '--host={db_host} --dbname={db_name}'\
#            '| grep {db_name} | wc -l').format(**env)

        ret = None
        with settings(warn_only=True):
            ret = r.run('psql --username={db_user} --host={db_host} -l '\
            '| grep {db_name} | wc -l')
            if ret is not None:
                if 'password authentication failed' in ret:
                    ret = False
                else:
                    ret = int(ret) >= 1
              
        if ret is not None:
            print('%s database on site %s %s exist' % (name, env.SITE, 'DOES' if ret else 'DOES NOT'))
            return ret

    @task
    def create(self, name='default', site=None, **kargs):
        
        r = self.database_renderer(name=name, site=site)
        
        # Create role/user.
        with settings(warn_only=True):
            r.pc('Creating user...')
            r.run('psql --user={postgres_user} --no-password --command="CREATE USER {db_user} WITH PASSWORD \'{db_password}\';"')
        
        r.pc('Creating database...')
        r.run('psql --user={postgres_user} --no-password --command="CREATE DATABASE {db_name} WITH OWNER={db_user} ENCODING=\'{encoding}\'"')
        
        with settings(warn_only=True):
            r.pc('Enabling plpgsql on database...')
            r.run('createlang -U postgres plpgsql {db_name}')

    @task
    @runs_once
    def load(self, dump_fn='', prep_only=0, force_upload=0, from_local=0, name=None, site=None, dest_dir=None):
        """
        Restores a database snapshot onto the target database server.
        
        If prep_only=1, commands for preparing the load will be generated,
        but not the command to finally load the snapshot.
        """
        
        r = self.database_renderer(name=name, site=site)
        
        # Render the snapshot filename.
        r.env.dump_fn = self.get_default_db_fn(fn_template=dump_fn, dest_dir=dest_dir)
        
        from_local = int(from_local)
        
        prep_only = int(prep_only)
        
        missing_local_dump_error = r.format(
            "Database dump file {dump_fn} does not exist."
        )
        
        # Copy snapshot file to target.
        if r.genv.is_local:
            r.env.remote_dump_fn = dump_fn
        else:
            r.env.remote_dump_fn = '/tmp/' + os.path.split(r.env.dump_fn)[-1]
        
        if not prep_only:
            if int(force_upload) or (not r.genv.is_local and not r.file_exists(r.env.remote_dump_fn)):
                if not self.dryrun:
                    assert os.path.isfile(r.env.dump_fn), \
                        missing_local_dump_error
                if self.verbose:
                    print('Uploading database snapshot...')
                r.put(
                    local_path=r.env.dump_fn,
                    remote_path=r.env.remote_dump_fn)
        
        if r.genv.is_local and not prep_only and not self.dryrun:
            assert os.path.isfile(r.env.dump_fn), \
                missing_local_dump_error
        
        with settings(warn_only=True):
            r.run('dropdb --user={db_root_username} {db_name}')
                
        r.run('psql --user={db_root_username} -c "CREATE DATABASE {db_name};"')
        
        with settings(warn_only=True):
            
            if r.env.engine == POSTGIS:
                r.run('psql --user={db_root_username} --no-password --dbname={db_name} --command="CREATE EXTENSION postgis;"')
                r.run('psql --user={db_root_username} --no-password --dbname={db_name} --command="CREATE EXTENSION postgis_topology;"')
            
            r.run('psql --user={db_root_username} -c "DROP OWNED BY {db_user} CASCADE;"')
            
        r.run('psql --user={db_root_username} -c "DROP USER IF EXISTS {db_user}; '
            'CREATE USER {db_user} WITH PASSWORD \'{db_password}\'; '
            'GRANT ALL PRIVILEGES ON DATABASE {db_name} to {db_user};"')
        for createlang in r.env.createlangs:
            r.env.createlang = createlang
            r.run('createlang -U {db_root_username} {createlang} {db_name} || true')
        
        if not prep_only:
            if r.env.load_command:
                r.run(r.env.load_command)
            else:
                r.run('pg_restore --jobs=8 -U {db_root_username} --create --dbname={db_name} {remote_dump_fn}')

    @task
    def configure(self, *args, **kwargs):
        #TODO:set postgres user password?
        #https://help.ubuntu.com/community/PostgreSQL
        #set postgres ident in pg_hba.conf
        #sudo -u postgres psql postgres
        #sudo service postgresql restart
        #sudo -u postgres psql
        #\password postgres
        r = self.local_renderer

        self.install_packages()

        r.env.pg_version = r.run('echo {version_command}') or r.env.default_version
        
#         r.pc('Backing up PostgreSQL configuration files...')
        r.sudo('cp /etc/postgresql/{pg_version}/main/postgresql.conf /etc/postgresql/{pg_version}/main/postgresql.conf.$(date +%Y%m%d%H%M).bak')
        r.sudo('cp /etc/postgresql/{pg_version}/main/pg_hba.conf /etc/postgresql/{pg_version}/main/pg_hba.conf.$(date +%Y%m%d%H%M).bak')
        
        r.pc('Allowing remote connections...')
        fn = self.render_to_file('postgresql/pg_hba.template.conf')
        r.put(
            local_path=fn,
            remote_path='/etc/postgresql/{pg_version}/main/pg_hba.conf',
            use_sudo=True,
        )
        
        # Don't do this. Keep it locked down and use an SSH tunnel instead.
        # See common.tunnel()
        #sudo_or_dryrun('sed -i "s/#listen_addresses = \'localhost\'/listen_addresses = \'*\'/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf' % env)
        
        r.pc('Enabling auto-vacuuming...')
        #r.sudo('sed -i "s/#autovacuum = on/autovacuum = on/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf')
        r.sed(  
            filename='/etc/postgresql/{version_command}/main/postgresql.conf'.format(**self.lenv),
            before='#autovacuum = on',
            after='/autovacuum = on',
            backup='',
            use_sudo=True,
        )
        #r.sudo('sed -i "s/#track_counts = on/track_counts = on/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf')
        r.sed(
            filename='/etc/postgresql/{version_command}/main/postgresql.conf'.format(**self.lenv),
            before='#track_counts = on',
            after='track_counts = on',
            backup='',
            use_sudo=True,
        )
        
        # Set UTF-8 as the default database encoding.
        #TODO:fix? throws error code?
#        sudo_or_dryrun('psql --user=postgres --no-password --command="'
#            'UPDATE pg_database SET datistemplate = FALSE WHERE datname = \'template1\';'
#            'DROP DATABASE template1;'
#            'CREATE DATABASE template1 WITH TEMPLATE = template0 ENCODING = \'UNICODE\';'
#            'UPDATE pg_database SET datistemplate = TRUE WHERE datname = \'template1\';'
#            '\c template1\n'
#            'VACUUM FREEZE;'
#            'UPDATE pg_database SET datallowconn = FALSE WHERE datname = \'template1\';"')

        r.sudo('service postgresql restart')

    configure.deploy_before = ['packager', 'user']
    
class PostgreSQLClientSatchel(Satchel):

    name = 'postgresqlclient'

    @property
    def packager_system_packages(self):
        return {
            FEDORA: ['postgresql-client'],
            (UBUNTU, '12.04'): [
                'postgresql-client-9.1',
                #'python-psycopg2',#install from pip instead
                #'postgresql-server-dev-9.1',
            ],
            (UBUNTU, '14.04'): [
                'postgresql-client-9.3',
                #'python-psycopg2',#install from pip instead
                #'postgresql-server-dev-9.3',
            ],
        }

postgresql = PostgreSQLSatchel()
PostgreSQLClientSatchel()

write_postgres_pgpass = postgresql.write_pgpass
