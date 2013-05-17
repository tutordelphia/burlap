import os
import sys
import datetime

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    #run as _run,
    run,
    settings,
    sudo,
    cd,
    task,
)
from fabric.contrib import files

from common import run, put

# This overrides the built-in load command.
env.db_dump_command = None

# This overrides the built-in dump command.
env.db_load_command = None

env.db_app_migration_order = []
env.db_dump_dest_dir = '/tmp'
env.db_root_password = 'root'
env.db_root_user = 'root'

env.db_postgresql_dump_command = 'time pg_dump -c -U %(db_user)s --blobs --format=c %(db_name)s %(db_schemas_str)s | gzip -c > %(db_dump_fn)s'
env.db_postgresql_createlangs = ['plpgsql'] # plpythonu
env.db_postgresql_postgres_user = 'postgres'

env.db_mysql_max_allowed_packet = '500M'
env.db_mysql_net_buffer_length = 1000000
env.db_mysql_dump_command = 'mysqldump --opt --compress --max_allowed_packet=%(db_mysql_max_allowed_packet)s --force --single-transaction --quick --user %(db_user)s --password=%(db_password)s -h %(db_host)s %(db_name)s | gzip > %(db_dump_fn)s'
env.db_mysql_preload_commands = []

def get_settings():
    module_path = env.settings_module % env
    module = __import__(module_path, fromlist='.'.join(module_path.split('.')[:-1]))
    return module

def set_db(name='default'):
    settings = get_settings()
    default_db = settings.DATABASES[name]
    env.db_name = default_db['NAME']
    env.db_user = default_db['USER']
    env.db_host = default_db['HOST']
    env.db_password = default_db['PASSWORD']
    env.db_engine = default_db['ENGINE']

@task
def create(drop=0):
    """
    Creates the target database
    """
    require('role', 'app_name')
    sys.path.insert(0, env.src_dir)
    env.db_drop_flag = '--drop' if int(drop) else ''
    set_db()
    if 'postgres' in env.db_engine:
        env.src_dir = os.path.abspath(env.src_dir)
        # This assumes the django-extensions app is installed, which
        # provides the convenient sqlcreate command.
        run('cd %(src_dir)s; ./manage sqlcreate --router=default %(db_drop_flag)s | psql --user=postgres --no-password' % env)
        #run('psql --user=postgres -d %(db_name)s -c "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %(db_user)s_ro CASCADE; DROP ROLE IF EXISTS %(db_user)s_ro; DROP USER IF EXISTS %(db_user)s_ro; CREATE USER %(db_user)s_ro WITH PASSWORD \'readonly\'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO %(db_user)s_ro;"')
        with settings(warn_only=True):
            run('createlang -U postgres plpgsql %(db_name)s' % env)
        #run('cd %(src_dir)s; ./manage syncdb --noinput --verbosity=2' % env)
        # First migrate apps in a specific order if given.
#        for app_name in env.db_app_migration_order:
#            env.db_app_name = app_name
#            run('cd %(src_dir)s; ./manage migrate --noinput --delete-ghost-migrations %(db_app_name)s' % env)
#        # Then migrate everything else remaining.
#        run('cd %(src_dir)s; ./manage migrate --noinput --delete-ghost-migrations' % env)
        syncdb()
        migrate()
    elif 'mysql' in default_db['ENGINE']:
        raise NotImplemented
    else:
        raise NotImplemented

@task
def dump():
    """
    Exports the target database to a single transportable file appropriate for
    loading using load().
    """
    set_db()
    env.db_date = datetime.date.today().strftime('%Y%m%d')
    env.db_dump_fn = '%(env.db_dump_dest_dir)s/%(db_name)s_%(db_date)s.sql.gz' % env
    if env.db_dump_command:
        run(env.db_dump_command % env)
    elif 'postgres' in env.db_engine:
        env.db_schemas_str = ' '.join('-n %s' % _ for _ in env.db_schemas)
        run(env.db_postgresql_dump_command % env)
    elif 'mysql' in env.db_engine:
        run(env.db_mysql_dump_command % env)
    else:
        raise NotImplemented
    return env.db_dump_fn

@task
def load(db_dump_fn):
    """
    Restores a database snapshot onto the target database server.
    """
    env.db_dump_fn = db_dump_fn
    set_db()
    
    # Copy snapshot file to target.
    missing_local_dump_error = (
        "Database dump file %(db_dump_fn)s does not exist."
    ) % env
    if not files.exists(env.db_dump_fn):
        assert os.path.isfile(env.db_dump_fn), \
            missing_local_dump_error
        put(env.db_dump_fn, env.db_dump_fn)
    
    if env.db_load_command:
        run(env.db_load_command % env)
    elif 'postgres' in env.db_engine:
        
        run('dropdb --user=%(db_postgresql_postgres_user)s %(db_name)s' % env)
        run('psql --user=%(db_postgresql_postgres_user)s -c "CREATE DATABASE %(db_name)s;"' % env)
        run('psql --user=%(db_postgresql_postgres_user)s -c "DROP OWNED BY %(db_user)s CASCADE;"' % env)
        run('psql --user=%(db_postgresql_postgres_user)s -c "DROP USER IF EXISTS %(db_user)s; '
            'CREATE USER %(db_user)s WITH PASSWORD \'%(db_password)s\'; '
            'GRANT ALL PRIVILEGES ON DATABASE %(db_name)s to %(db_user)s;"' % env)
        for createlang in env.db_postgresql_createlangs:
            env.db_createlang = createlang
            run('createlang -U %(db_postgresql_postgres_user)s %(db_createlang)s %(db_name)s || true' % env)
        run('gunzip -c %(db_dump_fn)s | pg_restore -U %(db_postgresql_postgres_user)s --create --dbname=%(db_name)s' % env)
        
    elif 'mysql' in env.db_engine:
        
        # Drop the database if it's there.
        cmd = "mysql -v -h %(db_host)s -u %(db_user)s -p%(db_password)s --execute='DROP DATABASE IF EXISTS %(db_name)s'" % env
        run(cmd)
        
        # Now, create the database.
        cmd = "mysqladmin -h %(db_host)s -u %(db_user)s -p%(db_password)s create %(db_name)s" % env
        run(cmd)
        
        # Raise max packet limitation.
        run(
            ('mysql -v -h %(db_host)s -D %(db_name)s -u %(db_root_user)s '
            '-p%(db_root_password)s --execute="SET global '
            'net_buffer_length=%(db_mysql_net_buffer_length)s; SET global '
            'max_allowed_packet=%(db_mysql_max_allowed_packet)s;"') % env)
        
        # Run any server-specific commands (e.g. to setup permissions) before we load the data.
        for command in env.db_mysql_preload_commands:
            run(command % env)
        
        # Restore the database content from the dump file.
        env.db_dump_fn = db_dump_fn
        cmd = ("gunzip < %(db_dump_fn)s | mysql -u %(db_root_user)s --password=%(db_root_password)s --host=%(db_host)s -D %(db_name)s") % env
        run(cmd)
        
    else:
        raise NotImplemented

@task
def syncdb():
    """
    Wrapper around Django's syncdb command.
    """
    env.src_dir = os.path.abspath(env.src_dir)
    run('cd %(src_dir)s; ./manage syncdb --noinput --verbosity=2' % env)

@task
def migrate(app_name=''):
    """
    Wrapper around Django's migrate command.
    """
    env.src_dir = os.path.abspath(env.src_dir)
    if app_name:
        env.db_app_name = app_name
        run('cd %(src_dir)s; ./manage migrate %(db_app_name)s --noinput --delete-ghost-migrations' % env)
    else:
        
        # First migrate apps in a specific order if given.
        for app_name in env.db_app_migration_order:
            env.db_app_name = app_name
            run('cd %(src_dir)s; ./manage migrate --noinput --delete-ghost-migrations %(db_app_name)s' % env)
            
        # Then migrate everything else remaining.
        run('cd %(src_dir)s; ./manage migrate --noinput --delete-ghost-migrations' % env)
        