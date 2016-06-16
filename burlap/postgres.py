"""
PostgreSQL users and databases
==============================

This module provides tools for creating PostgreSQL users and databases.

"""
from __future__ import print_function

from fabric.api import cd, hide, sudo, settings, runs_once

from burlap import Satchel
from burlap.constants import *
from burlap.db import DatabaseSatchel
from burlap.decorators import task

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
    
    required_system_packages = {
        (UBUNTU, '12.04'): ['postgresql-9.3'],
        (UBUNTU, '14.04'): ['postgresql-9.3'],
    }
    
    def set_defaults(self):
        super(PostgreSQLSatchel, self).set_defaults()
        
        self.env.dump_command = 'time pg_dump -c -U %(db_user)s --blobs --format=c %(db_name)s %(db_schemas_str)s > %(db_dump_fn)s'
        self.env.createlangs = ['plpgsql'] # plpythonu
        self.env.postgres_user = 'postgres'
        self.env.encoding = 'UTF8'
        self.env.custom_load_cmd = ''
        self.env.port = 5432
        self.env.pgass_path = '~/.pgpass'
        self.env.pgpass_chmod = 600
        self.env.version_command = '`psql --version | grep -o -E "[0-9]+.[0-9]+"`'

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
    def set_root_login(self, db_type=None, db_host=None, e=None):
        """
        Looks up the root login for the given database on the given host and sets
        it to environment variables. 
        """
        
        if e:
            _env = e
            _env = type(_env)(_env)
        else:
            _env = env
        
        # Check the legacy password location.
        if db_type is None:
            db_type = 'postgresql'
        
        # Check the new password location.
        db_host = db_host or _env.db_host
        key = '%s-%s' % (db_type, db_host)
        if key in _env.db_root_logins:
            data = _env.db_root_logins[key]
            if 'username' in data:
                _env.db_root_user = data['username']
            if 'password' in data:
                _env.db_root_password = data['password']
            
        return _env

    @task
    def write_pgpass(self, name=None, use_sudo=0, verbose=1, commands_only=0):
        """
        Write the file used to store login credentials for PostgreSQL.
        """
        #from burlap.dj import set_db
        from burlap.file import appendline
        
        use_sudo = int(use_sudo)
        commands_only = int(commands_only)
        
#         if name:
#             set_db(name=name)
        
        cmds = []
        cmds.append(
            'touch {db_postgresql_pgass_path}'.format(
                db_postgresql_pgass_path=env.db_postgresql_pgass_path))
        cmds.append(
            'chmod {db_postgresql_pgpass_chmod} {db_postgresql_pgass_path}'.format(
                db_postgresql_pgass_path=env.db_postgresql_pgass_path,
                db_postgresql_pgpass_chmod=env.db_postgresql_pgpass_chmod))
        
        pgpass_kwargs = dict(
            db_host=env.db_host,
            db_port=env.db_postgresql_port,
            db_user=env.db_user,
            db_password=env.db_password,
        )
        pgpass_line = '{db_host}:{db_port}:*:{db_user}:{db_password}'\
            .format(**pgpass_kwargs)
        cmds.extend(appendline(
            fqfn=env.db_postgresql_pgass_path,
            line=pgpass_line,
            use_sudo=use_sudo,
            commands_only=1,
            verbose=0))
            
        if not commands_only:
            for cmd in cmds:
                if self.verbose:
                    print(cmd)
                if use_sudo:
                    sudo_or_dryrun(cmd)
                else:
                    run_or_dryrun(cmd)
                    
        return cmds

    @task
    def create(self, name, **kargs):
        
        r = self.database_renderer(name)
        
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
    def load(self, dump_fn='', prep_only=0, force_upload=0, from_local=0):
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
        if env.is_local:
            env.db_remote_dump_fn = db_dump_fn
        else:
            env.db_remote_dump_fn = '/tmp/'+os.path.split(env.db_dump_fn)[-1]
        
        if not prep_only:
            if int(force_upload) or (not self.dryrun and not env.is_local and not files.exists(env.db_remote_dump_fn)):
                assert os.path.isfile(env.db_dump_fn), \
                    missing_local_dump_error
                if self.verbose:
                    print('Uploading database snapshot...')
                put_or_dryrun(local_path=env.db_dump_fn, remote_path=env.db_remote_dump_fn)
        
        if env.is_local and not prep_only and not self.dryrun:
            assert os.path.isfile(r.env.dump_fn), \
                missing_local_dump_error
            
        self.set_root_login()
        
        with settings(warn_only=True):
            r.run('dropdb --user={db_postgresql_postgres_user} {db_name}')
                
        r.run('psql --user={db_postgresql_postgres_user} -c "CREATE DATABASE {db_name};"')
        
        with settings(warn_only=True):
            
            if 'postgis' in env.db_engine:
                r.run('psql --user={postgres_user} --no-password --dbname={db_name} --command="CREATE EXTENSION postgis;"')
                r.run('psql --user={postgres_user} --no-password --dbname={db_name} --command="CREATE EXTENSION postgis_topology;"')
            
            r.run('psql --user={postgres_user} -c "DROP OWNED BY {db_user} CASCADE;"')
            
        r.run('psql --user=%(db_postgresql_postgres_user)s -c "DROP USER IF EXISTS %(db_user)s; '
            'CREATE USER %(db_user)s WITH PASSWORD \'%(db_password)s\'; '
            'GRANT ALL PRIVILEGES ON DATABASE %(db_name)s to %(db_user)s;"')
        for createlang in env.db_postgresql_createlangs:
            r.env.createlang = createlang
            r.run('createlang -U {postgres_user} {createlang} {db_name} || true')
        
        if not prep_only:
            if r.env.load_command:
                r.run(r.env.load_command)
            else:
                r.run('pg_restore --jobs=8 -U {postgres_user} --create --dbname={db_name} {db_remote_dump_fn}')

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

#         r.pc('Backing up PostgreSQL configuration files...')
        r.sudo('cp /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf.$(date +%%Y%%m%%d%%H%%M).bak')
        r.sudo('cp /etc/postgresql/%(db_postgresql_version_command)s/main/pg_hba.conf /etc/postgresql/%(db_postgresql_version_command)s/main/pg_hba.conf.$(date +%%Y%%m%%d%%H%%M).bak')
        
        r.pc('Allowing remote connections...')
        fn = self.render_to_file('postgresql/pg_hba.template.conf')
        r.put(
            local_path=fn,
            remote_path='/etc/postgresql/%(db_postgresql_version_command)s/main/pg_hba.conf' % env,
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
        )
        #r.sudo('sed -i "s/#track_counts = on/track_counts = on/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf')
        r.sed(
            filename='/etc/postgresql/{version_command}/main/postgresql.conf'.format(**self.lenv),
            before='#track_counts = on',
            after='track_counts = on',
            backup='',
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
    
    required_system_packages = {
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
