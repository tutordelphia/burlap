import os
import re
import sys
import datetime
import glob
import tempfile
from collections import defaultdict

from fabric.api import (
    env,
    require,
    execute,
    settings,
    cd,
    runs_once,
    execute,
)
from fabric.contrib import files

from burlap.constants import *
from burlap import Satchel, ServiceSatchel
from burlap import common
from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    set_site,
    SITE,
    ROLE,
    ALL,
    QueuedCommand,
    get_dryrun,
)
from burlap.decorators import task_or_dryrun
#from burlap.plan import run, sudo

env.db_dump_fn = None
#env.db_dump_fn_template = '%(db_dump_dest_dir)s/db_%(SITE)s_%(ROLE)s_%(db_date)s.sql.gz'
env.db_dump_fn_template = '%(db_dump_dest_dir)s/db_%(db_type)s_%(SITE)s_%(ROLE)s_$(date +%%Y%%m%%d).sql.gz'

# This overrides the built-in load command.
env.db_dump_command = None

env.db_engine = None # postgres|mysql
env.db_engine_subtype = None # amazon_rds

# This overrides the built-in dump command.
env.db_load_command = None

env.db_app_migration_order = []
env.db_dump_dest_dir = '/tmp'
env.db_dump_archive_dir = 'snapshots'

# The login for performance administrative tasks (e.g. CREATE/DROP database).
env.db_root_user = 'root'#DEPRECATED
env.db_root_password = 'root'#DEPRECATED
env.db_root_logins = {} # {(type,host):{user:?, password:?}}

#DEPRECATED:2015.12.12
#env.db_postgresql_dump_command = 'time pg_dump -c -U %(db_user)s --blobs --format=c %(db_name)s %(db_schemas_str)s | gzip -c > %(db_dump_fn)s'
env.db_postgresql_dump_command = 'time pg_dump -c -U %(db_user)s --blobs --format=c %(db_name)s %(db_schemas_str)s > %(db_dump_fn)s'
env.db_postgresql_createlangs = ['plpgsql'] # plpythonu
env.db_postgresql_postgres_user = 'postgres'
env.db_postgresql_encoding = 'UTF8'
env.db_postgresql_custom_load_cmd = ''
env.db_postgresql_port = 5432
env.db_postgresql_pgass_path = '~/.pgpass'
env.db_postgresql_pgpass_chmod = 600
env.db_postgresql_version_command = '`psql --version | grep -o -E "[0-9]+.[0-9]+"`'

#DEPRECATED:2015.12.12
env.db_mysql_max_allowed_packet = 524288000 # 500M
env.db_mysql_net_buffer_length = 1000000
env.db_mysql_conf = '/etc/mysql/my.cnf' # /etc/my.cnf on fedora
env.db_mysql_dump_command = 'mysqldump --opt --compress --max_allowed_packet=%(db_mysql_max_allowed_packet)s --force --single-transaction --quick --user %(db_user)s --password=%(db_password)s -h %(db_host)s %(db_name)s | gzip > %(db_dump_fn)s'
env.db_mysql_preload_commands = []
env.db_mysql_character_set = 'utf8'
env.db_mysql_collate = 'utf8_general_ci'
env.db_mysql_port = 3306
env.db_mysql_root_password = None
env.db_mysql_custom_mycnf = False

# Should be set to False for Django >= 1.7.
env.db_check_ghost_migrations = True

env.db_syncdb_command_template = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s syncdb --noinput %(db_syncdb_database)s %(db_syncdb_all_flag)s --traceback'

# If true, means we're responsible for installing and configuring
# the database server.
# If false, means we can assume the server is not our responsibility.
env.db_server_managed = True

# If true, means we're responsible for creating the logical database on
# the database server.
# If false, means creation of the database is not our responsibility.
env.db_database_managed = True

env.db_fixture_sets = {} # {name:[list of fixtures]}

env.db_sets = {} # {name:{configs}}

# Service names.
DB = 'DB'
MYSQL = 'MYSQL'
MYSQLGIS = 'MYSQLGIS'
MYSQLCLIENT = 'MYSQLCLIENT'
POSTGRESQL = 'POSTGRESQL'
POSTGRESQLCLIENT = 'POSTGRESQLCLIENT'
POSTGIS = 'POSTGIS'

@task_or_dryrun
def load_db_set(name):
    """
    Loads database parameters from a specific named set.
    """
    verbose = common.get_verbose()
    db_set = env.db_sets.get(name, {})
    env.update(db_set)

@task_or_dryrun
def exists(name='default', site=None):
    """
    Returns true if the database exists. False otherwise.
    """
    from burlap.dj import set_db, render_remote_paths
    
    verbose = common.get_verbose()
    if verbose:
        print '!'*80
        print 'db.exists:', name
    
    if name:
        set_db(name=name, site=site, verbose=verbose)
        load_db_set(name=name)
        
    set_root_login()
    
    ret = None
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        
        kwargs = dict(
            db_user=env.db_root_user,
            db_password=env.db_root_password,
            db_host=env.db_host,
            db_name=env.db_name,
        )
        env.update(kwargs)
        
        # Set pgpass file.
        if env.db_password:
            write_postgres_pgpass(verbose=verbose, name=name)
        
#        cmd = ('psql --username={db_user} --no-password -l '\
#            '--host={db_host} --dbname={db_name}'\
#            '| grep {db_name} | wc -l').format(**env)
        cmd = ('psql --username={db_user} --host={db_host} -l '\
            '| grep {db_name} | wc -l').format(**env)
        if verbose:
            print cmd
        with settings(warn_only=True):
            ret = run_or_dryrun(cmd)
            #print 'ret:', ret
            if ret is not None:
                if 'password authentication failed' in ret:
                    ret = False
                else:
                    ret = int(ret) >= 1
            
    elif 'mysql' in env.db_engine:
        
        kwargs = dict(
            db_user=env.db_root_user,
            db_password=env.db_root_password,
            db_host=env.db_host,
            db_name=env.db_name,
        )
        env.update(kwargs)
            
        cmd = ('mysql -h {db_host} -u {db_user} '\
            '-p"{db_password}" -N -B -e "SELECT IF(\'{db_name}\''\
            ' IN(SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA), '\
            '\'exists\', \'notexists\') AS found;"').format(**env)
        if verbose:
            print cmd
        ret = run_or_dryrun(cmd)
        if ret is not None:
            ret = 'notexists' not in (ret or 'notexists')

    else:
        raise NotImplementedError
    
    if ret is not None:
        print('%s database on site %s %s exist' % (name, env.SITE, 'DOES' if ret else 'DOES NOT'))
        return ret

def set_root_login(db_type=None, db_host=None, e=None):
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
        if 'mysql' in _env.db_engine:
            db_type = 'mysql'
            _env.db_root_password = _env.mysql_root_password
        elif 'postgres' in _env.db_engine or 'postgis' in _env.db_engine:
            db_type = 'postgresql'
        else:
            raise NotImplementedError
    
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

@task_or_dryrun
def create(drop=0, name='default', site=None, post_process=0, db_engine=None, db_user=None, db_host=None, db_password=None, db_name=None):
    """
    Creates the target database.
    """
    from burlap.dj import set_db, render_remote_paths
    assert env[ROLE]
    
    require('app_name')
    drop = int(drop)
    
    # Do nothing if we're not dropping and the database already exists.
    print 'Checking to see if database already exists...'
    if exists(name=name, site=site) and not drop:
        print('Database already exists. Aborting creation. '\
            'Use drop=1 to override.')
        return
    
    env.db_drop_flag = '--drop' if drop else ''
    if name:
        set_db(name=name, site=site)
        load_db_set(name=name)
    if db_engine:
        env.db_engine = db_engine
    if db_user:
        env.db_user = db_user
    if db_host:
        env.db_host = db_host
    if db_password:
        env.db_password = db_password
    if db_name:
        env.db_name = db_name
#    print 'site:',env[SITE]
#    print 'role:',env[ROLE]
    
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        
        print 'Setting root login...'
        set_root_login()
        
        # Create role/user.
        with settings(warn_only=True):
            print 'Creating user...'
            cmd = 'psql --user={db_postgresql_postgres_user} --no-password --command="CREATE USER {db_user} WITH PASSWORD \'{db_password}\';"'.format(**env)
            run_or_dryrun(cmd)
        
        print 'Creating database...'
        cmd = 'psql --user=%(db_postgresql_postgres_user)s --no-password --command="CREATE DATABASE %(db_name)s WITH OWNER=%(db_user)s ENCODING=\'%(db_postgresql_encoding)s\'"' % env
        run_or_dryrun(cmd)
        
        #run_or_dryrun('psql --user=postgres -d %(db_name)s -c "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %(db_user)s_ro CASCADE; DROP ROLE IF EXISTS %(db_user)s_ro; DROP USER IF EXISTS %(db_user)s_ro; CREATE USER %(db_user)s_ro WITH PASSWORD \'readonly\'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO %(db_user)s_ro;"')
        with settings(warn_only=True):
            print 'Enabling plpgsql on database...'
            cmd = 'createlang -U postgres plpgsql %(db_name)s' % env
            run_or_dryrun(cmd)
            
    elif 'mysql' in env.db_engine:
        
        set_root_login()
        
        if int(drop):
            cmd = "mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' --execute='DROP DATABASE IF EXISTS %(db_name)s'" % env
            sudo_or_dryrun(cmd)
            
        cmd = "mysqladmin -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' create %(db_name)s" % env
        sudo_or_dryrun(cmd)
            
#        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
#            "--execute='ALTER DATABASE %(db_name)s CHARACTER SET %(db_mysql_character_set)s COLLATE %(db_mysql_collate)s;'") % env
#        print cmd
        set_collation_mysql()
            
        # Create user.
        cmd = "mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' --execute=\"GRANT USAGE ON *.* TO %(db_user)s@'%%'; DROP USER %(db_user)s@'%%';\"" % env
        run_or_dryrun(cmd)
        
        # Grant user access to the database.
        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s "\
            "-p'%(db_root_password)s' --execute=\"GRANT ALL PRIVILEGES "\
            "ON %(db_name)s.* TO %(db_user)s@'%%' IDENTIFIED BY "\
            "'%(db_password)s'; FLUSH PRIVILEGES;\"") % env
        run_or_dryrun(cmd)
        
        #TODO:why is this necessary? why doesn't the user@% pattern above give
        #localhost access?!
        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s "\
            "-p'%(db_root_password)s' --execute=\"GRANT ALL PRIVILEGES "\
            "ON %(db_name)s.* TO %(db_user)s@%(db_host)s IDENTIFIED BY "\
            "'%(db_password)s'; FLUSH PRIVILEGES;\"") % env
        run_or_dryrun(cmd)
            
        # Let the primary login do so from everywhere.
#        cmd = 'mysql -h %(db_host)s -u %()s -p'%(db_root_password)s' --execute="USE mysql; GRANT ALL ON %(db_name)s.* to %(db_user)s@\'%\' IDENTIFIED BY \'%(db_password)s\'; FLUSH PRIVILEGES;"'
#        sudo_or_dryrun(cmd)
    
    else:
        raise NotImplemented
    
#     if not get_dryrun() and int(post_process):
#         post_create(name=name, site=site)
# 
# @task_or_dryrun
# def post_create(name=None, site=None):
#     from burlap.dj import set_db
#     assert env[ROLE]
#     require('app_name')
#     site = site or env.SITE
#     #print 'site:',site
#     set_db(name=name, site=site, verbose=1)
#     load_db_set(name=name)
# #    print 'site:',env[SITE]
# #    print 'role:',env[ROLE]
#     
#     syncdb(all=True, site=site)
#     #migrate(fake=True, site=site)
#     install_sql(name=name, site=site)
#     #createsuperuser()

#DEPRECATED:use dj.update
@task_or_dryrun
#@runs_once
def update(name=None, site=None, skip_databases=None, do_install_sql=0, migrate_apps=''):
    """
    Updates schema and custom SQL.
    """
    from burlap.dj import set_db
    
    set_db(name=name, site=site)
    syncdb(site=site) # Note, this loads initial_data fixtures.
    migrate(
        site=site,
        skip_databases=skip_databases,
        migrate_apps=migrate_apps)
    if int(do_install_sql):
        install_sql(name=name, site=site)
    #TODO:run syncdb --all to force population of new content types?

#DEPRECATED:use dj.update_all
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

# @task_or_dryrun
# def update_all_from_diff(last=None, current=None):
#     migrate_apps = []
#     if last and current:
#         last = last['DJANGO_MIGRATIONS']
#         current = current['DJANGO_MIGRATIONS']
#         for app_name in current:
#             if current[app_name] != last.get(app_name):
#                 migrate_apps.append(app_name)
#     return update_all(migrate_apps=','.join(migrate_apps))

@task_or_dryrun
@runs_once
def dump(dest_dir=None, to_local=None, from_local=0, archive=0, dump_fn=None):
    """
    Exports the target database to a single transportable file on the localhost,
    appropriate for loading using load().
    """
    from burlap.dj import set_db
    
    from_local = int(from_local)
    set_db()
    if dest_dir:
        env.db_dump_dest_dir = dest_dir
    env.db_date = datetime.date.today().strftime('%Y%m%d')
    #env.db_dump_fn = dump_fn or (env.db_dump_fn_template % env)
    env.db_dump_fn = get_default_db_fn(dump_fn or env.db_dump_fn_template)
    
    if to_local is None and not env.is_local:
        to_local = 1
        
    if env.db_dump_command:
        run_or_dryrun(env.db_dump_command % env)
    elif 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        assert env.db_schemas, \
            'Please specify the list of schemas to dump in db_schemas.'
        env.db_schemas_str = ' '.join('-n %s' % _ for _ in env.db_schemas)
        cmd = env.db_postgresql_dump_command % env
        #print 'db_host:',env.db_host
        if env.is_local or from_local:
            local_or_dryrun(cmd)
        else:
            sudo_or_dryrun(cmd)
    elif 'mysql' in env.db_engine:
        cmd = env.db_mysql_dump_command % env
        if env.is_local:
            local_or_dryrun(cmd)
        else:
            sudo_or_dryrun(cmd)
    else:
        raise NotImplemented
    
    # Download the database dump file on the remote host to localhost.
    if not from_local and (0 if to_local is None else int(to_local)) and not env.is_local:
        cmd = ('rsync -rvz --progress --recursive --no-p --no-g --rsh "ssh -o StrictHostKeyChecking=no -i %(key_filename)s" %(user)s@%(host_string)s:%(db_dump_fn)s %(db_dump_fn)s') % env
        local_or_dryrun(cmd)
    
    if to_local and int(archive):
        db_fn = render_fn(env.db_dump_fn)
        env.db_archive_fn = '%s/%s' % (env.db_dump_archive_dir, os.path.split(db_fn)[-1])
        local_or_dryrun('mv %s %s' % (db_fn, env.db_archive_fn))
    
    return env.db_dump_fn

@task_or_dryrun
def get_free_space():
    """
    Return free space in bytes.
    """
    cmd = "df -k | grep -vE '^Filesystem|tmpfs|cdrom|none|udev|cgroup' | awk '{ print $1 \" \" $4 }'"
    lines = [_ for _ in run_or_dryrun(cmd).strip().split('\n') if _.startswith('/')]
    assert len(lines) == 1, 'Ambiguous devices: %s' % str(lines)
    device, kb = lines[0].split(' ')
    free_space = int(kb) * 1024
    if int(verbose):
        print 'free_space (bytes):',free_space
    return free_space

@task_or_dryrun
def get_size():
    """
    Retrieves the size of the database in bytes.
    """
    from burlap.dj import set_db
    set_db(site=env.SITE, role=env.ROLE)
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        #cmd = 'psql --user=%(db_postgresql_postgres_user)s --tuples-only -c "SELECT pg_size_pretty(pg_database_size(\'%(db_name)s\'));"' % env
        cmd = 'psql --user=%(db_postgresql_postgres_user)s --tuples-only -c "SELECT pg_database_size(\'%(db_name)s\');"' % env
        #print cmd
        output = run_or_dryrun(cmd)
        output = int(output.strip().split('\n')[-1].strip())
        if int(verbose):
            print 'database size (bytes):',output
        return output
    else:
        raise NotImplementedError

@task_or_dryrun
def loadable(src, dst):
    """
    Determines if there's enough space to load the target database.
    """
    from fabric import state
    from fabric.task_utils import crawl
    
    src_task = crawl(src, state.commands)
    assert src_task, 'Unknown source role: %s' % src
    
    dst_task = crawl(dst, state.commands)
    assert dst_task, 'Unknown destination role: %s' % src
    
    # Get source database size.
    src_task()
    env.host_string = env.hosts[0]
    src_size_bytes = get_size()
    
    # Get target database size, if any.
    dst_task()
    env.host_string = env.hosts[0]
    try:
        dst_size_bytes = get_size()
    except:
        dst_size_bytes = 0
    
    # Get target host disk size.
    free_space_bytes = get_free_space()
    
    # Deduct existing database size, because we'll be deleting it.
    balance_bytes = free_space_bytes + dst_size_bytes - src_size_bytes
    balance_bytes_scaled, units = common.pretty_bytes(balance_bytes)
    
    viable = balance_bytes >= 0
    if int(verbose):
        print 'src_db_size:',common.pretty_bytes(src_size_bytes)
        print 'dst_db_size:',common.pretty_bytes(dst_size_bytes)
        print 'dst_free_space:',common.pretty_bytes(free_space_bytes)
        print
        if viable:
            print 'Viable! There will be %.02f %s of disk space left.' % (balance_bytes_scaled, units)
        else:
            print 'Not viable! We would be %.02f %s short.' % (balance_bytes_scaled, units)
    
    return viable

@task_or_dryrun
def dumpload():
    """
    Dumps and loads a database snapshot simultaneously.
    Requires that the destination server has direct database access
    to the source server.
    
    This is better than a serial dump+load when:
    1. The network connection is reliable.
    2. You don't need to save the dump file.
    
    The benefits of this over a dump+load are:
    1. Usually runs faster, since the load and dump happen in parallel.
    2. Usually takes up less disk space since no separate dump file is
        downloaded.
    """
    set_db(site=env.SITE, role=env.ROLE)
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        cmd = ('pg_dump -c --host=%(host_string)s --username=%(db_user)s '\
            '--blobs --format=c %(db_name)s -n public | '\
            'pg_restore -U %(db_postgresql_postgres_user)s --create '\
            '--dbname=%(db_name)s') % env
        run_or_dryrun(cmd)
    else:
        raise NotImplementedError

def render_fn(fn):
    import commands
    return commands.getoutput('echo %s' % fn)

@task_or_dryrun
def get_default_db_fn(fn_template=None):
    fn_template = fn_template or env.db_dump_fn_template
    fn = fn_template % env
    fn = render_fn(fn)
    return fn

@task_or_dryrun
@runs_once
def load(db_dump_fn='', prep_only=0, force_upload=0, from_local=0):
    """
    Restores a database snapshot onto the target database server.
    
    If prep_only=1, commands for preparing the load will be generated,
    but not the command to finally load the snapshot.
    """
    verbose = common.get_verbose()
    from burlap.dj import set_db
    from burlap.common import get_dryrun
#    print '!'*80
#    print 'db.load.site:',env.SITE
#    print 'db.load.role:',env.ROLE
    
    if not db_dump_fn:
        db_dump_fn = get_default_db_fn()
    
    env.db_dump_fn = render_fn(db_dump_fn)
    
    set_db(site=env.SITE, role=env.ROLE)
    
    from_local = int(from_local)
    prep_only = int(prep_only)
    
    # Copy snapshot file to target.
    missing_local_dump_error = (
        "Database dump file %(db_dump_fn)s does not exist."
    ) % env
    if env.is_local:
        env.db_remote_dump_fn = db_dump_fn
    else:
        env.db_remote_dump_fn = '/tmp/'+os.path.split(env.db_dump_fn)[-1]
        #env.db_remote_dump_fn = 'snapshots/'+os.path.split(env.db_dump_fn)[-1]
#    print '~'*80
#    print 'env.db_remote_dump_fn:',env.db_remote_dump_fn
#    print 'env.hosts2:',env.hosts,env.host_string
    
    if not prep_only:
        if int(force_upload) or (not get_dryrun() and not env.is_local and not files.exists(env.db_remote_dump_fn)):
            assert os.path.isfile(env.db_dump_fn), \
                missing_local_dump_error
            if verbose:
                print 'Uploading database snapshot...'
            put_or_dryrun(local_path=env.db_dump_fn, remote_path=env.db_remote_dump_fn)
    
    if env.is_local and not get_dryrun() and not prep_only:
        assert os.path.isfile(env.db_dump_fn), \
            missing_local_dump_error
    
    if env.db_load_command:
        cmd = env.db_load_command % env
        run_or_dryrun(cmd)
        
    elif 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        
        set_root_login()
        
        with settings(warn_only=True):
            cmd = 'dropdb --user=%(db_postgresql_postgres_user)s %(db_name)s' % env
            run_or_dryrun(cmd)
                
        cmd = 'psql --user=%(db_postgresql_postgres_user)s -c "CREATE DATABASE %(db_name)s;"' % env
        run_or_dryrun(cmd)
        
        with settings(warn_only=True):
            
            if 'postgis' in env.db_engine:
                cmd = 'psql --user=%(db_postgresql_postgres_user)s --no-password --dbname=%(db_name)s --command="CREATE EXTENSION postgis;"' % env
                run_or_dryrun(cmd)
                cmd = 'psql --user=%(db_postgresql_postgres_user)s --no-password --dbname=%(db_name)s --command="CREATE EXTENSION postgis_topology;"' % env
                run_or_dryrun(cmd)
            
            cmd = 'psql --user=%(db_postgresql_postgres_user)s -c "DROP OWNED BY %(db_user)s CASCADE;"' % env
            run_or_dryrun(cmd)
            
        cmd = ('psql --user=%(db_postgresql_postgres_user)s -c "DROP USER IF EXISTS %(db_user)s; '
            'CREATE USER %(db_user)s WITH PASSWORD \'%(db_password)s\'; '
            'GRANT ALL PRIVILEGES ON DATABASE %(db_name)s to %(db_user)s;"') % env
        run_or_dryrun(cmd)
        for createlang in env.db_postgresql_createlangs:
            env.db_createlang = createlang
            cmd = 'createlang -U %(db_postgresql_postgres_user)s %(db_createlang)s %(db_name)s || true' % env
            run_or_dryrun(cmd)
        
        if not prep_only:
            #cmd = 'gunzip -c %(db_remote_dump_fn)s | pg_restore --jobs=8 -U %(db_postgresql_postgres_user)s --create --dbname=%(db_name)s' % env #TODO:deprecated
            #cmd = 'gunzip -c %(db_remote_dump_fn)s | pg_restore -U %(db_postgresql_postgres_user)s --create --dbname=%(db_name)s' % env #TODO:deprecated
            if env.db_postgresql_custom_load_cmd:
                cmd = env.db_postgresql_custom_load_cmd % env
            else:
                cmd = 'pg_restore --jobs=8 -U %(db_postgresql_postgres_user)s --create --dbname=%(db_name)s %(db_remote_dump_fn)s' % env
            run_or_dryrun(cmd)
        
    elif 'mysql' in env.db_engine:
        
        set_root_login()
        
        # Drop the database if it's there.
        #cmd = ("mysql -v -h %(db_host)s -u %(db_user)s -p'%(db_password)s' "
        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
            "--execute='DROP DATABASE IF EXISTS %(db_name)s'") % env
        run_or_dryrun(cmd)
        
        # Now, create the database.
        #cmd = ("mysqladmin -h %(db_host)s -u %(db_user)s -p'%(db_password)s' "
        cmd = ("mysqladmin -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
            "create %(db_name)s") % env
        run_or_dryrun(cmd)
        
        # Create user
        with settings(warn_only=True):
            cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
                "--execute=\"CREATE USER '%(db_user)s'@'%%' IDENTIFIED BY '%(db_password)s'; GRANT ALL PRIVILEGES ON *.* TO '%(db_user)s'@'%%' WITH GRANT OPTION; FLUSH PRIVILEGES;\"") % env
            run_or_dryrun(cmd)
#        DROP USER '<username>'@'%';
#        CREATE USER '<username>'@'%' IDENTIFIED BY '<password>';
#        GRANT ALL PRIVILEGES ON *.* TO '<username>'@'%' WITH GRANT OPTION;
#        FLUSH PRIVILEGES;
        
        # Set collation.
#        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
#            "--execute='ALTER DATABASE %(db_name)s CHARACTER SET %(db_mysql_character_set)s COLLATE %(db_mysql_collate)s;'") % env
#        print cmd
        set_collation_mysql()
        
        # Raise max packet limitation.
#         run_or_dryrun(
#             ('mysql -v -h %(db_host)s -D %(db_name)s -u %(db_root_user)s '
#             '-p"%(db_root_password)s" --execute="SET global '
#             'net_buffer_length=%(db_mysql_net_buffer_length)s; SET global '
#             'max_allowed_packet=%(db_mysql_max_allowed_packet)s;"') % env)
        set_max_mysql_packet_size(do_set=0)
        
        # Run any server-specific commands (e.g. to setup permissions) before
        # we load the data.
        for command in env.db_mysql_preload_commands:
            run_or_dryrun(command % env)
        
        # Restore the database content from the dump file.
        env.db_dump_fn = db_dump_fn
        cmd = ('gunzip < %(db_remote_dump_fn)s | mysql -u %(db_root_user)s '
            '--password=%(db_root_password)s --host=%(db_host)s '
            '-D %(db_name)s') % env
        run_or_dryrun(cmd)
        
        set_collation_mysql()
        
    else:
        raise NotImplemented


# @task_or_dryrun
# def syncdb(site=None, all=0, database=None):
#     """
#     Wrapper around Django's syncdb command.
#     """
# #    
#     #print 'remote_app_src_package_dir_template:',env.remote_app_src_package_dir_template
#     from burlap.dj import render_remote_paths
#     
#     
# #    print 'remote_app_src_package_dir_template:',env.remote_app_src_package_dir_template
# #    print 'remote_app_src_package_dir:',env.remote_app_src_package_dir
# #    print 'remote_manage_dir:',env.remote_manage_dir
# #    return
#     set_site(site)
#     
#     render_remote_paths()
#     
#     env.db_syncdb_all_flag = '--all' if int(all) else ''
#     env.db_syncdb_database = ''
#     if database:
#         env.db_syncdb_database = ' --database=%s' % database
#     cmd = env.db_syncdb_command_template % env
#     run_or_dryrun(cmd)

# @task_or_dryrun
# def migrate(app_name='', site=None, fake=0, skip_databases=None, do_fake=1, do_real=0, migrate_apps=''):
#     """
#     Wrapper around Django's migrate command.
#     """
#     from burlap.dj import render_remote_paths, has_database
#     
#     # If fake migrations are enabled, then run the real migrations on the real database.
#     do_real = int(do_real)
#     do_fake = int(do_fake)
#     
#     set_site(site or env.SITE)
#     
#     render_remote_paths()
#     
#     migrate_apps = [
#         _.strip()
#         for _ in migrate_apps.strip().split(',')
#         if _.strip()
#     ]
#     
#     skip_databases = (skip_databases or '')
#     if isinstance(skip_databases, basestring):
#         skip_databases = [_.strip() for _ in skip_databases.split(',') if _.strip()]
#     
#     if env.db_check_ghost_migrations:
#         env.db_check_ghost_migrations_flag = '--delete-ghost-migrations'
#     else:
#         env.db_check_ghost_migrations_flag = ''
#     
#     # Since South doesn't properly support multi-database applications, we have
#     # to fake app migrations on every database except the one where they exist.
#     #TODO:remove this when South fixes this or gets merged into Django core.
#     if env.django_migrate_fakeouts:
#         for fakeout in env.django_migrate_fakeouts:
#             env.db_app_name = fakeout['app']
#             if migrate_apps and env.db_app_name not in migrate_apps:
#                 continue
#             env.db_database_name = fakeout['database']
#             if env.db_database_name in skip_databases:
#                 continue
#             if do_fake:
#                 cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate %(db_app_name)s --noinput %(db_check_ghost_migrations_flag)s --fake --traceback' % env
#                 run_or_dryrun(cmd)
#             if do_real and has_database(name=env.db_database_name, site=site):
# #                cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s syncdb --database=%(db_database_name)s --traceback' % env
# #                run_or_dryrun(cmd)
#                 cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate %(db_app_name)s --database=%(db_database_name)s --noinput %(db_check_ghost_migrations_flag)s --traceback' % env
#                 run_or_dryrun(cmd)
#     
#     env.db_migrate_fake = '--fake' if int(fake) else ''
#     if migrate_apps:
#         for app_name in migrate_apps:
#             env.db_app_name = app_name
#             cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate %(db_app_name)s --noinput %(db_check_ghost_migrations_flag)s %(db_migrate_fake)s --traceback' % env
#             run_or_dryrun(cmd)
#     elif app_name:
#         env.db_app_name = app_name
#         cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate %(db_app_name)s --noinput %(db_check_ghost_migrations_flag)s %(db_migrate_fake)s --traceback' % env
#         run_or_dryrun(cmd)
#     else:
#         
#         # First migrate apps in a specific order if given.
#         for app_name in env.db_app_migration_order:
#             env.db_app_name = app_name
#             cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate --noinput %(db_check_ghost_migrations_flag)s %(db_migrate_fake)s %(db_app_name)s --traceback' % env
#             run_or_dryrun(cmd)
#             
#         # Then migrate everything else remaining.
#         cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate --noinput %(db_check_ghost_migrations_flag)s %(db_migrate_fake)s --traceback' % env
#         run_or_dryrun(cmd)


#TODO:deprecated? use write_postgres_pgass instead?
@task_or_dryrun
def save_db_password(user, password):
    """
    Writes the database user's password to a file, allowing automatic login
    from a secure location.
    
    Currently, only PostgreSQL is supported.
    """
    from burlap.dj import set_db
    set_db(name='default')
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        env.db_save_user = user
        env.db_save_password = password

        sudo_or_dryrun('sudo -u postgres psql -c "ALTER USER %(db_save_user)s PASSWORD \'%(db_save_password)s\';"' % env)
        
        sudo_or_dryrun("sed -i '/%(db_save_user)s/d' ~/.pgpass" % env)
        sudo_or_dryrun('echo "localhost:5432:*:%(db_save_user)s:%(db_save_password)s" >> ~/.pgpass' % env)
        sudo_or_dryrun('chmod 600 ~/.pgpass')
    else:
        raise NotImplementedError

def set_collation_mysql(name=None, site=None):
    from burlap.dj import set_db
    
    set_db(name=name, site=site)
    set_root_login()
    cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
        "--execute='ALTER DATABASE %(db_name)s CHARACTER SET %(db_mysql_character_set)s COLLATE %(db_mysql_collate)s;'") % env
    run_or_dryrun(cmd)

def set_collation_mysql_all(name=None, site=None):
    for site in env.available_sites:
        set_collation_mysql(name=name, site=site)
    
@task_or_dryrun
def set_max_mysql_packet_size(do_set=1):
    verbose = common.get_verbose()
    from burlap.dj import set_db

    do_set = int(do_set)

    if do_set:
        set_db(site=env.SITE, role=env.ROLE)
    
    # Raise max packet limitation.
    run_or_dryrun(
        ('mysql -v -h %(db_host)s -D %(db_name)s -u %(db_root_user)s '
        '-p"%(db_root_password)s" --execute="SET global '
        'net_buffer_length=%(db_mysql_net_buffer_length)s; SET global '
        'max_allowed_packet=%(db_mysql_max_allowed_packet)s;"') % env)

@task_or_dryrun
def prep_root_password():
    args = dict(
        db_root_password=env.db_mysql_root_password or env.db_root_password,
    )
    sudo_or_dryrun("dpkg --configure -a")
    sudo_or_dryrun("debconf-set-selections <<< 'mysql-server mysql-server/root_password password %(db_root_password)s'" % args)
    sudo_or_dryrun("debconf-set-selections <<< 'mysql-server mysql-server/root_password_again password %(db_root_password)s'" % args)

# common.service_configurators[MYSQL] = [configure]
# common.service_configurators[POSTGRESQL] = [configure]
# common.service_deployers[MYSQL] = [update]
# common.service_restarters[POSTGRESQL] = [restart]
# common.service_restarters[MYSQL] = [restart]

# @task_or_dryrun
# def record_manifest():
#     """
#     Called after a deployment to record any data necessary to detect changes
#     for a future deployment.
#     """
#     from burlap.dj import get_settings
#         
#     data = common.get_component_settings(DB)
#     
#     data['databases'] = []#{} # {site:django DATABASES}
#     data['database_users'] = {} # {user:(host,password)}
#     for site, site_data in common.iter_sites(site=ALL, no_secure=True):
#         settings = get_settings(site=site)
#         for _, db_data in settings.DATABASES.iteritems():
#             #data['databases'][site] = settings.DATABASES
#             data['databases'].append(dict(
#                 engine=db_data['ENGINE'],
#                 name=db_data['NAME'],
#                 host=db_data['HOST'],
#                 port=db_data.get('PORT')))
#             data['database_users'].setdefault(db_data['USER'], [])
#             data['database_users'][db_data['USER']].append(dict(
#                 password=db_data['PASSWORD'],
#                 engine=db_data['ENGINE'],
#                 name=db_data['NAME'],
#                 host=db_data['HOST'],
#                 port=db_data.get('PORT')))
#     
#     return data
# 
# def compare_manifest(old):
#     """
#     Compares the current settings to previous manifests and returns the methods
#     to be executed to make the target match current settings.
#     """
#     old = old or {}
#     methods = []
#     pre = ['user', 'ip', 'package']
#     new = record_manifest()
#     
#     old_databases = old.get('databases', {})
#     del old['databases']
#     new_databases = new.get('databases', {})
#     del new['databases']
#     
#     old_databases = [tuple(sorted(_.items())) for _ in old_databases]
#     old_databases = dict(zip(old_databases, old_databases))
#     new_databases = [tuple(sorted(_.items())) for _ in new_databases]
#     new_databases = dict(zip(new_databases, new_databases))
#     added, updated, deleted = common.check_settings_for_differences(old_databases, new_databases, as_tri=True)
#     for added_db in added:
#         methods.append(QueuedCommand('db.create', pre=pre))
# 
#     old_database_users = old.get('database_users', {})
#     del old['database_users']
#     new_database_users = new.get('database_users', {})
#     del new['database_users']
# 
# #    created_dbs = []
# #    deleted_dbs = []
# #    updated_dbs = []
# #    for site_name in set(old_databases.keys()).union(new_databases.keys()):
# #        print site_name
#     
#     has_diffs = common.check_settings_for_differences(old, new, as_bool=True)
#     if has_diffs:
#         methods.append(QueuedCommand('db.configure', pre=pre))
#     return methods

class DatabaseSatchel(ServiceSatchel):
    
    tasks = (
        'shell',
        'drop_views',
    )
    
    def set_defaults(self):
                
        # If set, allows remote users to connect to the database.
        # This shouldn't be necessary if the webserver and database
        # share the same server.
        self.env.allow_remote_connections = False
        
    def shell(self, name='default', user=None, password=None, root=0, verbose=1, write_password=1, no_db=0, no_pw=0):
        """
        Opens a SQL shell to the given database, assuming the configured database
        and user supports this feature.
        """
        from burlap.dj import set_db
        
        verbose = self.verbose
        
        root = int(root)
        write_password = int(write_password)
        no_db = int(no_db)
        no_pw = int(no_pw)
        
        # Load database credentials.
        set_db(name=name, verbose=verbose)
        load_db_set(name=name, verbose=verbose)
        set_root_login()
        if root:
            env.db_user = env.db_root_user
            env.db_password = env.db_root_password
        else:
            if user is not None:
                env.db_user = user
            if password is not None:
                env.db_password = password
        
        # Switch relative to absolute host name.
        env.db_shell_host = env.db_host
    #    if env.db_shell_host in ('localhost', '127.0.0.1'):
    #        env.db_shell_host = env.host_string
        
        if no_pw:
            env.db_password = ''
        
        cmds = []
        env.db_name_str = ''
        if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
            # Note, psql does not support specifying password at the command line.
            # If you don't want to manually type it at the command line, you must
            # add the password to your local ~/.pgpass file.
            # Each line in that file should be formatted as:
            # host:port:username:password
            
            # Set pgpass file.
            if write_password and env.db_password:
                cmds.extend(write_postgres_pgpass(verbose=0, commands_only=1, name=name))
            
            if not no_db:
                env.db_name_str = ' --dbname=%(db_name)s' % env
            
            cmds.append(('/bin/bash -i -c \"psql --username=%(db_user)s '\
                '--host=%(db_shell_host)s%(db_name_str)s\"') % env)
        elif 'mysql' in env.db_engine:
            
            if not no_db:
                env.db_name_str = ' %(db_name)s' % env
            
            if env.db_password:
                cmds.append(('/bin/bash -i -c \"mysql -u %(db_user)s '\
                    '-p\'%(db_password)s\' -h %(db_shell_host)s%(db_name_str)s\"') % env)
            else:
                cmds.append(('/bin/bash -i -c \"mysql -u %(db_user)s '\
                    '-h %(db_shell_host)s%(db_name_str)s\"') % env)
        else:
            raise NotImplementedError
            
        if cmds:
            for cmd in cmds:
                if verbose:
                    print(cmd)
                if env.is_local:
                    local_or_dryrun(cmd)
                else:
                    run_or_dryrun(cmd)

    def drop_views(self, name=None, site=None):
        """
        Drops all views.
        """
        from burlap.dj import set_db
        set_db(name=name, site=site)
        if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
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
            todo
        elif 'mysql' in env.db_engine:
            
            set_root_login()
            
            cmd = ("mysql --batch -v -h %(db_host)s " \
                #"-u %(db_root_user)s -p'%(db_root_password)s' " \
                "-u %(db_user)s -p'%(db_password)s' " \
                "--execute=\"SELECT GROUP_CONCAT(CONCAT(TABLE_SCHEMA,'.',table_name) SEPARATOR ', ') AS views FROM INFORMATION_SCHEMA.views WHERE TABLE_SCHEMA = '%(db_name)s' ORDER BY table_name DESC;\"") % env
            result = sudo_or_dryrun(cmd)
            result = re.findall(
                '^views[\s\t\r\n]+(.*)',
                result,
                flags=re.IGNORECASE|re.DOTALL|re.MULTILINE)
            if not result:
                return
            env.db_view_list = result[0]
            #cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' " \
            cmd = ("mysql -v -h %(db_host)s -u %(db_user)s -p'%(db_password)s' " \
                "--execute=\"DROP VIEW %(db_view_list)s CASCADE;\"") % env
            sudo_or_dryrun(cmd)
        else:
            raise NotImplementedError

class MySQLSatchel(DatabaseSatchel):
    
    name = 'mysql'
    
    tasks = (
        'configure',
        'set_max_packet_size',
        'prep_root_password',
        'set_root_password',
    )
    
    required_system_packages = {
        FEDORA: ['mysql-server'],
        (UBUNTU, '12.04'): ['mysql-server', 'libmysqlclient-dev'],
        (UBUNTU, '14.04'): ['mysql-server', 'libmysqlclient-dev'],
    }
    
    def set_defaults(self):
    
        super(MySQLSatchel, self).set_defaults()
        
        # You want this to be large, and set in both the client and server.
        # Otherwise, MySQL may silently truncate database dumps, leading to much
        # frustration.
        self.env.max_allowed_packet = 524288000 # 500M
        
        self.env.net_buffer_length = 1000000
        self.env.conf = '/etc/mysql/my.cnf' # /etc/my.cnf on fedora
        self.env.dump_command = 'mysqldump --opt --compress --max_allowed_packet=%(mysql_max_allowed_packet)s --force --single-transaction --quick --user %(db_user)s --password=%(db_password)s -h %(db_host)s %(db_name)s | gzip > %(db_dump_fn)s'
        self.env.preload_commands = []
        self.env.character_set = 'utf8'
        self.env.collate = 'utf8_general_ci'
        self.env.port = 3306
        self.env.root_password = None
        self.env.custom_mycnf = False

        self.env.service_commands = {
            START:{
                UBUNTU: 'service mysql start',
            },
            STOP:{
                UBUNTU: 'service mysql stop',
            },
            ENABLE:{
                UBUNTU: 'update-rc.d mysql defaults',
            },
            DISABLE:{
                UBUNTU: 'update-rc.d -f mysql remove',
            },
            RESTART:{
                UBUNTU: 'service mysql restart',
            },
            STATUS:{
                UBUNTU: 'service mysql status',
            },
        }
            
    def set_collation_mysql(self, name=None, site=None):
        from burlap.dj import set_db
        
        set_db(name=name, site=site)
        set_root_login()
        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
            "--execute='ALTER DATABASE %(db_name)s CHARACTER SET %(db_mysql_character_set)s COLLATE %(db_mysql_collate)s;'") % env
        run_or_dryrun(cmd)
    
    def set_collation_mysql_all(self, name=None, site=None):
        for site in env.available_sites:
            set_collation_mysql(name=name, site=site)
        
    def set_max_packet_size(self, do_set=1):
        verbose = common.get_verbose()
        from burlap.dj import set_db
    
        do_set = int(do_set)
    
        if do_set:
            set_db(site=env.SITE, role=env.ROLE)
        
        # Raise max packet limitation.
        self.run_or_dryrun(
            ('mysql -v -h %(db_host)s -D %(db_name)s -u %(db_root_user)s '
            '-p"%(db_root_password)s" --execute="SET global '
            'net_buffer_length=%(db_mysql_net_buffer_length)s; SET global '
            'max_allowed_packet=%(db_mysql_max_allowed_packet)s;"') % env)
    
    def packager_pre_configure(self):
        """
        Called before packager.configure is run.
        """
        prep_root_password()
        
    def prep_root_password(self):
        args = dict(
            db_root_password=\
                self.genv.mysql_root_password or \
                self.genv.db_mysql_root_password or \
                self.genv.db_root_password,
        )
        self.sudo_or_dryrun("dpkg --configure -a")
        self.sudo_or_dryrun("debconf-set-selections <<< 'mysql-server mysql-server/root_password password %(db_root_password)s'" % args)
        self.sudo_or_dryrun("debconf-set-selections <<< 'mysql-server mysql-server/root_password_again password %(db_root_password)s'" % args)
        
    def set_root_password(self):
        self.prep_root_password()
        #self.sudo_or_dryrun('dpkg-reconfigure mysql-server-5.5')
        self.sudo_or_dryrun("dpkg-reconfigure -fnoninteractive `dpkg --list | egrep -o 'mysql-server-([0-9.]+)'`")
        
    def configure(self, do_packages=0):

        _env = type(self.genv)(self.genv)
        
        _env = set_root_login(db_type='mysql', db_host=self.genv.db_host, e=_env)
        
        if int(do_packages):
            self.prep_root_password()
            self.install_packages()
            
        self.set_root_password()
        
        if _env.mysql_custom_mycnf:
            fn = self.render_to_file('my.template.cnf', extra=_env)
            self.put_or_dryrun(
                local_path=fn,
                remote_path=_env.mysql_conf,
                use_sudo=True,
            )
        
        if _env.mysql_allow_remote_connections:
            
            # Enable remote connections.
            self.sudo_or_dryrun("sed -i 's/127.0.0.1/0.0.0.0/g' %(mysql_conf)s" % _env)
            
            # Enable root logins from remote connections.
            cmd = 'mysql -u %(db_root_user)s -p"%(mysql_root_password)s" --execute="USE mysql; GRANT ALL ON *.* to %(db_root_user)s@\'%%\' IDENTIFIED BY \'%(db_root_password)s\'; FLUSH PRIVILEGES;"' % _env
            sudo_or_dryrun(cmd)
            
            self.restart()
        
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']

class MySQLClientSatchel(Satchel):

    name = 'mysqlclient'

    tasks = (
        #'configure_mysql_client',
    )
    
    required_system_packages = {
        FEDORA: ['mysql-server'],
        (UBUNTU, '12.04'): ['mysql-server', 'libmysqlclient-dev'],
        (UBUNTU, '14.04'): ['mysql-server', 'libmysqlclient-dev'],
    }
    
class PostgreSQLSatchel(DatabaseSatchel):
    
    name = 'postgres'
    
    tasks = (
        'configure',
        'write_pgpass',
    )
    
    required_system_packages = {
        (UBUNTU, '12.04'): ['postgresql-9.3'],
        (UBUNTU, '14.04'): ['postgresql-9.3'],
    }
    
    def set_defaults(self):
    
        super(PostgreSQLSatchel, self).set_defaults()
    
        env.dump_command = 'time pg_dump -c -U %(db_user)s --blobs --format=c %(db_name)s %(db_schemas_str)s > %(db_dump_fn)s'
        env.createlangs = ['plpgsql'] # plpythonu
        env.postgres_user = 'postgres'
        env.encoding = 'UTF8'
        env.custom_load_cmd = ''
        env.port = 5432
        env.pgass_path = '~/.pgpass'
        env.pgpass_chmod = 600
        env.version_command = '`psql --version | grep -o -E "[0-9]+.[0-9]+"`'

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

    def write_pgpass(name=None, use_sudo=0, verbose=1, commands_only=0):
        """
        Write the file used to store login credentials for PostgreSQL.
        """
        from burlap.dj import set_db
        from burlap.file import appendline
        
        use_sudo = int(use_sudo)
        verbose = common.get_verbose()
        commands_only = int(commands_only)
        
        if name:
            set_db(name=name)
        
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
                if verbose:
                    print(cmd)
                if use_sudo:
                    sudo_or_dryrun(cmd)
                else:
                    run_or_dryrun(cmd)
                    
        return cmds

    def configure(self):
        #TODO:set postgres user password?
        #https://help.ubuntu.com/community/PostgreSQL
        #set postgres ident in pg_hba.conf
        #sudo -u postgres psql postgres
        #sudo service postgresql restart
        #sudo -u postgres psql
        #\password postgres

        pc('Backing up PostgreSQL configuration files...')
        cmd = 'cp /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf.$(date +%%Y%%m%%d%%H%%M).bak' % env
        sudo_or_dryrun(cmd)
        cmd = 'cp /etc/postgresql/%(db_postgresql_version_command)s/main/pg_hba.conf /etc/postgresql/%(db_postgresql_version_command)s/main/pg_hba.conf.$(date +%%Y%%m%%d%%H%%M).bak' % env
        sudo_or_dryrun(cmd)
        
        pc('Allowing remote connections...')
        fn = common.render_to_file('pg_hba.template.conf')
        put_or_dryrun(local_path=fn,
            remote_path='/etc/postgresql/%(db_postgresql_version_command)s/main/pg_hba.conf' % env,
            use_sudo=True,
            )
        
        # Don't do this. Keep it locked down and use an SSH tunnel instead.
        # See common.tunnel()
        #sudo_or_dryrun('sed -i "s/#listen_addresses = \'localhost\'/listen_addresses = \'*\'/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf' % env)
        
        pc('Enabling auto-vacuuming...')
        cmd = 'sed -i "s/#autovacuum = on/autovacuum = on/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf' % env
        sudo_or_dryrun(cmd)
        cmd = 'sed -i "s/#track_counts = on/track_counts = on/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf' % env
        sudo_or_dryrun(cmd)
        
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

        cmd = 'service postgresql restart'
        sudo_or_dryrun(cmd)

    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']
    
class PostgreSQLClientSatchel(Satchel):

    name = 'postgresqlclient'

    tasks = (
        #'configure_postgresql_client',
    )
    
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
    
mysql = MySQLSatchel()
MySQLClientSatchel()

postgresql = PostgreSQLSatchel()
PostgreSQLClientSatchel()