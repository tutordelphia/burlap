import os
import re
import sys
import datetime
import glob
import tempfile

from fabric.api import (
    env,
    local,
    put as _put,
    require,
    run,
    execute,
    settings,
    sudo,
    cd,
    task,
)
from fabric.contrib import files

from burlap import common
from burlap.common import (
    run,
    put,
    set_site,
    SITE,
    ROLE,
    ALL,
    QueuedCommand,
    Migratable,
)

env.db_dump_fn = None

# This overrides the built-in load command.
env.db_dump_command = None

env.db_engine = None # postgres|mysql
env.db_engine_subtype = None # amazon_rds

# This overrides the built-in dump command.
env.db_load_command = None

env.db_app_migration_order = []
env.db_dump_dest_dir = '/tmp'

# The login for performance administrative tasks (e.g. CREATE/DROP database).
env.db_root_user = 'root'
env.db_root_password = 'root'

# If set, allows remote users to connect to the database.
# This shouldn't be necessary if the webserver and database
# share the same server.
env.db_allow_remote_connections = False

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

# You want this to be large, and set in both the client and server.
# Otherwise, MySQL may silently truncate database dumps, leading to much
# frustration.
env.db_mysql_max_allowed_packet = 524288000 # 500M
env.db_mysql_net_buffer_length = 1000000
env.db_mysql_conf = '/etc/mysql/my.cnf' # /etc/my.cnf on fedora
env.db_mysql_dump_command = 'mysqldump --opt --compress --max_allowed_packet=%(db_mysql_max_allowed_packet)s --force --single-transaction --quick --user %(db_user)s --password=%(db_password)s -h %(db_host)s %(db_name)s | gzip > %(db_dump_fn)s'
env.db_mysql_preload_commands = []
env.db_mysql_character_set = 'utf8'
env.db_mysql_collate = 'utf8_general_ci'
env.db_mysql_port = 3306

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
POSTGIS = 'POSTGIS'
POSTGRESQLCLIENT = 'POSTGRESQLCLIENT'

common.required_system_packages[MYSQL] = {
    common.FEDORA: ['mysql-server'],
    (common.UBUNTU, '12.04'): ['mysql-server', 'libmysqlclient-dev'],
    (common.UBUNTU, '14.04'): ['mysql-server', 'libmysqlclient-dev'],
}
common.required_system_packages[POSTGRESQL] = {
    common.FEDORA: ['postgresql-server'],
    (common.UBUNTU, '12.04'): ['postgresql-9.1'],
    (common.UBUNTU, '14.04'): ['postgresql-9.3'],
}

common.required_system_packages[MYSQLCLIENT] = {
    common.FEDORA: ['mysql-client'],
    (common.UBUNTU, '12.04'): ['mysql-client', 'libmysqlclient-dev'],
    (common.UBUNTU, '14.04'): ['mysql-client', 'libmysqlclient-dev'],
}
common.required_system_packages[POSTGRESQLCLIENT] = {
    common.FEDORA: ['postgresql-client'],
    (common.UBUNTU, '12.04'): [
        'postgresql-client-9.1',
        #'python-psycopg2',#install from pip instead
        #'postgresql-server-dev-9.1',
    ],
    (common.UBUNTU, '14.04'): [
        'postgresql-client-9.3',
        #'python-psycopg2',#install from pip instead
        #'postgresql-server-dev-9.3',
    ],
}

UTF8 = 'UTF8'

class Database(Migratable):
    
    # True means we're responsible for created and deleting it.
    # False means it exists outside of our realm and we're just tenants.
    managed = True
    
    users = []
    
    owner = None
    
    encoding = UTF8
    
    # postgresql/mysql
    engine = None
    
    class Meta:
        abstract = True
    
    def __init__(self, *args, **kwargs):
        pass

    def create(self):
        args = dict(
            name=self.name,
            owner=self.owner,
            encoding=self.encoding,
        )
        if self.engine in (POSTGRESQL, POSTGIS):
            cmd = "CREATE DATABASE {name} WITH {owner} ENCODING {encoding};".format(**args)
        elif self.engine in (MYSQL,):
            raise NotImplementedError
        else:
            raise NotImplementedError
            
class User(Migratable):
    
    username = None
    
    password = None
    
    class Meta:
        abstract = True
        
    def __init__(self, *args, **kwargs):
        pass
    
    def create(self, db):
        args = dict(
            username=self.username,
            password=self.password,
        )
        if db.engine in (POSTGRESQL,):
            cmd = "CREATE USER {username} PASSWORD '{password}';".format(**args)
        elif db.engine in (MYSQL,):
            raise NotImplementedError
        else:
            raise NotImplementedError

def set_collation_mysql(name=None, site=None, dryrun=0):
    from burlap.dj import set_db
    set_db(name=name, site=site)
    cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
        "--execute='ALTER DATABASE %(db_name)s CHARACTER SET %(db_mysql_character_set)s COLLATE %(db_mysql_collate)s;'") % env
    print cmd
    if not int(dryrun):
        run(cmd)

def set_collation_mysql_all(name=None, site=None, dryrun=0):
    for site in env.available_sites:
        set_collation_mysql(name=name, site=site, dryrun=dryrun)

@task
def configure(name='default', site=None, _role=None, dryrun=0):
    """
    Configures a fresh install of the database
    """
    from burlap.dj import set_db
    from burlap.common import pc
    assert env[ROLE]
#    print 'role:',env[ROLE]
#    print 'site:',env[SITE]
    require('app_name')
    #set_db(name=name, site=site, role=_role)
    if name:
        set_db(name=name, site=site or env[SITE], role=_role or env[ROLE], verbose=1)
    load_db_set(name=name)
#    print 'site:',env[SITE]
#    print 'role:',env[ROLE]
    dryrun = int(dryrun)
    
    if not env.db_server_managed:
        print 'Aborting database server configuration because it is marked as unmanaged.'
        return
        
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        #TODO:set postgres user password?
        #https://help.ubuntu.com/community/PostgreSQL
        #set postgres ident in pg_hba.conf
        #sudo -u postgres psql postgres
        #sudo service postgresql restart
        #sudo -u postgres psql
        #\password postgres

        pc('Backing up PostgreSQL configuration files...')
        cmd = 'cp /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf.$(date +%%Y%%m%%d%%H%%M).bak' % env
        print(cmd)
        if not dryrun:
            sudo(cmd)
        cmd = 'cp /etc/postgresql/%(db_postgresql_version_command)s/main/pg_hba.conf /etc/postgresql/%(db_postgresql_version_command)s/main/pg_hba.conf.$(date +%%Y%%m%%d%%H%%M).bak' % env
        print(cmd)
        if not dryrun:
            sudo(cmd)
        
        pc('Allowing remote connections...')
        if not dryrun:
            #TODO:reimplement put() to support command generation and dryrun?
            fn = common.render_to_file('pg_hba.template.conf')
            put(local_path=fn,
                remote_path='/etc/postgresql/%(db_postgresql_version_command)s/main/pg_hba.conf' % env,
                use_sudo=True)
        
        # Don't do this. Keep it locked down and use an SSH tunnel instead.
        # See common.tunnel()
        #sudo('sed -i "s/#listen_addresses = \'localhost\'/listen_addresses = \'*\'/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf' % env)
        
        pc('Enabling auto-vacuuming...')
        cmd = 'sed -i "s/#autovacuum = on/autovacuum = on/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf' % env
        print(cmd)
        if not dryrun:
            sudo(cmd)
        cmd = 'sed -i "s/#track_counts = on/track_counts = on/g" /etc/postgresql/%(db_postgresql_version_command)s/main/postgresql.conf' % env
        print(cmd)
        if not dryrun:
            sudo(cmd)
        
        # Set UTF-8 as the default database encoding.
        #TODO:fix? throws error code?
#        sudo('psql --user=postgres --no-password --command="'
#            'UPDATE pg_database SET datistemplate = FALSE WHERE datname = \'template1\';'
#            'DROP DATABASE template1;'
#            'CREATE DATABASE template1 WITH TEMPLATE = template0 ENCODING = \'UNICODE\';'
#            'UPDATE pg_database SET datistemplate = TRUE WHERE datname = \'template1\';'
#            '\c template1\n'
#            'VACUUM FREEZE;'
#            'UPDATE pg_database SET datallowconn = FALSE WHERE datname = \'template1\';"')

        cmd = 'service postgresql restart'
        print(cmd)
        if not dryrun:
            sudo(cmd)

    elif 'mysql' in env.db_engine:
        if env.db_allow_remote_connections:
            
            # Enable remote connections.
            cmd = "sed -i 's/127.0.0.1/0.0.0.0/g' %(db_mysql_conf)s" % env
            print(cmd)
            if not dryrun:
                sudo(cmd)
            
            # Enable root logins from remote connections.
            cmd = 'mysql -u %(db_root_user)s -p"%(db_root_password)s" --execute="USE mysql; GRANT ALL ON *.* to %(db_root_user)s@\'%%\' IDENTIFIED BY \'%(db_root_password)s\'; FLUSH PRIVILEGES;"' % env
            print(cmd)
            if not dryrun:
                sudo(cmd)
            
            cmd = 'service mysql restart'
            print(cmd)
            if not dryrun:
                sudo(cmd)
            
    else:
        print 'No database parameters found.'

@task
def load_db_set(name, verbose=0):
    """
    Loads database parameters from a specific named set.
    """
    verbose = int(verbose)
    db_set = env.db_sets.get(name, {})
    env.update(db_set)

@task
def exists(name='default', site=None, dryrun=0, verbose=1):
    """
    Returns true if the database exists. False otherwise.
    """
    from burlap.dj import set_db, render_remote_paths
    
    dryrun = int(dryrun)
    verbose = int(verbose)
    
    if name:
        set_db(name=name, site=site, verbose=verbose)
        load_db_set(name=name)
    
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
            write_postgres_pgpass(dryrun=dryrun, verbose=verbose)
        
#        cmd = ('psql --username={db_user} --no-password -l '\
#            '--host={db_host} --dbname={db_name}'\
#            '| grep {db_name} | wc -l').format(**env)
        cmd = ('psql --username={db_user} --host={db_host} -l '\
            '| grep {db_name} | wc -l').format(**env)
        if verbose:
            print cmd
        if not dryrun:
            ret = run(cmd)
            #print('ret:',ret)
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
        if not dryrun:
            ret = run(cmd)
            ret = 'notexists' not in ret

    else:
        raise NotImplementedError
    
    if ret is not None:
        print('%s database on site %s %s exist' % (name, env.SITE, 'DOES' if ret else 'DOES NOT'))
        return ret

@task
def prep_mysql_root_password():
    sudo("dpkg --configure -a")
    sudo("debconf-set-selections <<< 'mysql-server mysql-server/root_password password %(db_root_password)s'" % env)
    sudo("debconf-set-selections <<< 'mysql-server mysql-server/root_password_again password %(db_root_password)s'" % env)

@task
def create(drop=0, name='default', dryrun=0, site=None, post_process=0, db_engine=None, db_user=None, db_host=None, db_password=None, db_name=None):
    """
    Creates the target database.
    """
    from burlap.dj import set_db, render_remote_paths
    assert env[ROLE]
    dryrun = int(dryrun)
    require('app_name')
    drop = int(drop)
    
    # Do nothing if we're not dropping and the database already exists.
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
    env.dryrun = int(dryrun)
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
            
        # Create role/user.
        with settings(warn_only=True):
            cmd = 'psql --user={db_postgresql_postgres_user} --no-password --command="CREATE USER {db_user} WITH PASSWORD \'{db_password}\';"'.format(**env)
            print cmd
            if not dryrun:
                sudo(cmd)
            
        cmd = 'psql --user=%(db_postgresql_postgres_user)s --no-password --command="CREATE DATABASE %(db_name)s WITH OWNER=%(db_user)s ENCODING=\'%(db_postgresql_encoding)s\'"' % env
        print cmd
        if not dryrun:
            sudo(cmd)
        #run('psql --user=postgres -d %(db_name)s -c "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %(db_user)s_ro CASCADE; DROP ROLE IF EXISTS %(db_user)s_ro; DROP USER IF EXISTS %(db_user)s_ro; CREATE USER %(db_user)s_ro WITH PASSWORD \'readonly\'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO %(db_user)s_ro;"')
        with settings(warn_only=True):
            cmd = 'createlang -U postgres plpgsql %(db_name)s' % env
            print cmd
            if not dryrun:
                sudo(cmd)
    elif 'mysql' in env.db_engine:
        
        if int(drop):
            cmd = "mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' --execute='DROP DATABASE IF EXISTS %(db_name)s'" % env
            print cmd
            if not int(dryrun):
                sudo(cmd)
            
        cmd = "mysqladmin -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' create %(db_name)s" % env
        print cmd
        if not int(dryrun):
            sudo(cmd)
            
#        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
#            "--execute='ALTER DATABASE %(db_name)s CHARACTER SET %(db_mysql_character_set)s COLLATE %(db_mysql_collate)s;'") % env
#        print cmd
#        if not int(dryrun):
#            sudo(cmd)
        set_collation_mysql(dryrun=dryrun)
            
        # Create user.
        cmd = "mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' --execute=\"GRANT USAGE ON *.* TO %(db_user)s@'%%'; DROP USER %(db_user)s@'%%';\"" % env
        print cmd
        if not int(dryrun):
            run(cmd)
        
        # Grant user access to the database.
        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s "\
            "-p'%(db_root_password)s' --execute=\"GRANT ALL PRIVILEGES "\
            "ON %(db_name)s.* TO %(db_user)s@'%%' IDENTIFIED BY "\
            "'%(db_password)s'; FLUSH PRIVILEGES;\"") % env
        print cmd
        if not int(dryrun):
            run(cmd)
        
        #TODO:why is this necessary? why doesn't the user@% pattern above give
        #localhost access?!
        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s "\
            "-p'%(db_root_password)s' --execute=\"GRANT ALL PRIVILEGES "\
            "ON %(db_name)s.* TO %(db_user)s@%(db_host)s IDENTIFIED BY "\
            "'%(db_password)s'; FLUSH PRIVILEGES;\"") % env
        print cmd
        if not int(dryrun):
            run(cmd)
            
        # Let the primary login do so from everywhere.
#        cmd = 'mysql -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' --execute="USE mysql; GRANT ALL ON %(db_name)s.* to %(db_user)s@\'%\' IDENTIFIED BY \'%(db_password)s\'; FLUSH PRIVILEGES;"'
#        sudo(cmd)
    
    else:
        raise NotImplemented
    
    if not env.dryrun and int(post_process):
        post_create(name=name, dryrun=dryrun, site=site)

@task
def post_create(name=None, dryrun=0, site=None):
    from burlap.dj import set_db
    assert env[ROLE]
    require('app_name')
    site = site or env.SITE
    #print 'site:',site
    set_db(name=name, site=site, verbose=1)
    load_db_set(name=name)
#    print 'site:',env[SITE]
#    print 'role:',env[ROLE]
    env.dryrun = dryrun = int(dryrun)
    
    syncdb(all=True, site=site, dryrun=dryrun)
    migrate(fake=True, site=site, dryrun=dryrun)
    install_sql(name=name, site=site, dryrun=dryrun)
    #createsuperuser(dryrun=dryrun)

@task
def update(name=None, site=None, skip_databases=None):
    """
    Updates schema and custom SQL.
    """
    from burlap.dj import set_db
    set_db(name=name, site=site)
    syncdb(site=site) # Note, this loads initial_data fixtures.
    migrate(site=site, skip_databases=skip_databases)
    install_sql(name=name, site=site)
    #TODO:run syncdb --all to force population of new content types?

@task
def update_all(skip_databases=None):
    """
    Runs the Django migrate command for all unique databases
    for all available sites.
    """
    for site in env.available_sites:
        update(site=site, skip_databases=skip_databases)

@task
def dump(dryrun=0, dest_dir=None, to_local=None, from_local=0):
    """
    Exports the target database to a single transportable file on the localhost,
    appropriate for loading using load().
    """
    from burlap.dj import set_db
    dryrun = int(dryrun)
    from_local = int(from_local)
    set_db()
    if dest_dir:
        env.db_dump_dest_dir = dest_dir
    env.db_date = datetime.date.today().strftime('%Y%m%d')
    env.db_dump_fn = '%(db_dump_dest_dir)s/%(db_name)s_%(db_date)s.sql.gz' % env
    if to_local is None and not env.is_local:
        to_local = 1
        
    if env.db_dump_command:
        run(env.db_dump_command % env)
    elif 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        assert env.db_schemas, \
            'Please specify the list of schemas to dump in db_schemas.'
        env.db_schemas_str = ' '.join('-n %s' % _ for _ in env.db_schemas)
        cmd = env.db_postgresql_dump_command % env
        print cmd
        print 'db_host:',env.db_host
        if not dryrun:
            if env.is_local or from_local:
                local(cmd)
            else:
                sudo(cmd)
    elif 'mysql' in env.db_engine:
        cmd = env.db_mysql_dump_command % env
        print cmd
        if not dryrun:
            if env.is_local:
                local(cmd)
            else:
                sudo(cmd)
    else:
        raise NotImplemented
    
    # Download the database dump file on the remote host to localhost.
    if not from_local and (0 if to_local is None else int(to_local)) and not env.is_local:
        cmd = ('rsync -rvz --progress --recursive --no-p --no-g --rsh "ssh -o StrictHostKeyChecking=no -i %(key_filename)s" %(user)s@%(host_string)s:%(db_dump_fn)s %(db_dump_fn)s') % env
        print cmd
        if not dryrun:
            local(cmd)
    
    return env.db_dump_fn

@task
def get_free_space(verbose=0):
    """
    Return free space in bytes.
    """
    cmd = "df -k | grep -vE '^Filesystem|tmpfs|cdrom|none|udev|cgroup' | awk '{ print $1 \" \" $4 }'"
    lines = [_ for _ in run(cmd).strip().split('\n') if _.startswith('/')]
    assert len(lines) == 1, 'Ambiguous devices: %s' % str(lines)
    device, kb = lines[0].split(' ')
    free_space = int(kb) * 1024
    if int(verbose):
        print 'free_space (bytes):',free_space
    return free_space

@task
def get_size(verbose=0):
    """
    Retrieves the size of the database in bytes.
    """
    from burlap.dj import set_db
    set_db(site=env.SITE, role=env.ROLE)
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        #cmd = 'psql --user=%(db_postgresql_postgres_user)s --tuples-only -c "SELECT pg_size_pretty(pg_database_size(\'%(db_name)s\'));"' % env
        cmd = 'psql --user=%(db_postgresql_postgres_user)s --tuples-only -c "SELECT pg_database_size(\'%(db_name)s\');"' % env
        #print cmd
        output = run(cmd)
        output = int(output.strip().split('\n')[-1].strip())
        if int(verbose):
            print 'database size (bytes):',output
        return output
    else:
        raise NotImplementedError

@task
def loadable(src, dst, verbose=0):
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

@task
def dumpload(dryrun=0):
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
    dryrun = int(dryrun)
    set_db(site=env.SITE, role=env.ROLE)
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        cmd = ('pg_dump -c --host=%(host_string)s --username=%(db_user)s '\
            '--blobs --format=c %(db_name)s -n public | '\
            'pg_restore -U %(db_postgresql_postgres_user)s --create '\
            '--dbname=%(db_name)s') % env
        print cmd
        if not dryrun:
            run(cmd)
    else:
        raise NotImplementedError

@task
def load(db_dump_fn='', dryrun=0, prep_only=0, force_upload=0):
    """
    Restores a database snapshot onto the target database server.
    
    If dryrun=1, commands will be printed but not executed.
    
    If prep_only=1, commands for preparing the load will be generated,
    but not the command to finally load the snapshot.
    """
    from burlap.dj import set_db
    print '!'*80
    print 'db.load.site:',env.SITE
    print 'db.load.role:',env.ROLE
    env.db_dump_fn = db_dump_fn
    set_db(site=env.SITE, role=env.ROLE)
    
    prep_only = int(prep_only)
    dryrun = int(dryrun)
    
    # Copy snapshot file to target.
    missing_local_dump_error = (
        "Database dump file %(db_dump_fn)s does not exist."
    ) % env
    if env.is_local:
        env.db_remote_dump_fn = db_dump_fn
    else:
        env.db_remote_dump_fn = '/tmp/'+os.path.split(env.db_dump_fn)[-1]
    
    if not prep_only:
        if int(force_upload) or (not dryrun and not env.is_local and not files.exists(env.db_dump_fn)):
            assert os.path.isfile(env.db_dump_fn), \
                missing_local_dump_error
            print 'Uploading database snapshot...'
            put(local_path=env.db_dump_fn, remote_path=env.db_remote_dump_fn)
    
    if env.is_local and not dryrun and not prep_only:
        assert os.path.isfile(env.db_dump_fn), \
            missing_local_dump_error
    
    if env.db_load_command:
        cmd = env.db_load_command % env
        print cmd
        if not dryrun:
            run(cmd)
    elif 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        
        with settings(warn_only=True):
            cmd = 'dropdb --user=%(db_postgresql_postgres_user)s %(db_name)s' % env
            print cmd
            if not dryrun:
                run(cmd)
                
        cmd = 'psql --user=%(db_postgresql_postgres_user)s -c "CREATE DATABASE %(db_name)s;"' % env
        print cmd
        if not dryrun:
            run(cmd)
        
        with settings(warn_only=True):
            
            if 'postgis' in env.db_engine:
                cmd = 'psql --user=%(db_postgresql_postgres_user)s --no-password --dbname=%(db_name)s --command="CREATE EXTENSION postgis;"' % env
                print cmd
                if not dryrun:
                    run(cmd)
                cmd = 'psql --user=%(db_postgresql_postgres_user)s --no-password --dbname=%(db_name)s --command="CREATE EXTENSION postgis_topology;"' % env
                print cmd
                if not dryrun:
                    run(cmd)
            
            cmd = 'psql --user=%(db_postgresql_postgres_user)s -c "DROP OWNED BY %(db_user)s CASCADE;"' % env
            print cmd
            if not dryrun:
                run(cmd)
            
        cmd = ('psql --user=%(db_postgresql_postgres_user)s -c "DROP USER IF EXISTS %(db_user)s; '
            'CREATE USER %(db_user)s WITH PASSWORD \'%(db_password)s\'; '
            'GRANT ALL PRIVILEGES ON DATABASE %(db_name)s to %(db_user)s;"') % env
        print cmd
        if not dryrun:
            run(cmd)
        for createlang in env.db_postgresql_createlangs:
            env.db_createlang = createlang
            cmd = 'createlang -U %(db_postgresql_postgres_user)s %(db_createlang)s %(db_name)s || true' % env
            print cmd
            if not dryrun:
                run(cmd)
        
        if not prep_only:
            #cmd = 'gunzip -c %(db_remote_dump_fn)s | pg_restore --jobs=8 -U %(db_postgresql_postgres_user)s --create --dbname=%(db_name)s' % env #TODO:deprecated
            #cmd = 'gunzip -c %(db_remote_dump_fn)s | pg_restore -U %(db_postgresql_postgres_user)s --create --dbname=%(db_name)s' % env #TODO:deprecated
            if env.db_postgresql_custom_load_cmd:
                cmd = env.db_postgresql_custom_load_cmd % env
            else:
                cmd = 'pg_restore --jobs=8 -U %(db_postgresql_postgres_user)s --create --dbname=%(db_name)s %(db_remote_dump_fn)s' % env
            print cmd
            if not dryrun:
                run(cmd)
        
    elif 'mysql' in env.db_engine:
        
        # Drop the database if it's there.
        #cmd = ("mysql -v -h %(db_host)s -u %(db_user)s -p'%(db_password)s' "
        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
            "--execute='DROP DATABASE IF EXISTS %(db_name)s'") % env
        run(cmd)
        
        # Now, create the database.
        #cmd = ("mysqladmin -h %(db_host)s -u %(db_user)s -p'%(db_password)s' "
        cmd = ("mysqladmin -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
            "create %(db_name)s") % env
        run(cmd)
        
        #TODO:create user
#        DROP USER '<username>'@'%';
#        CREATE USER '<username>'@'%' IDENTIFIED BY '<password>';
#        GRANT ALL PRIVILEGES ON *.* TO '<username>'@'%' WITH GRANT OPTION;
#        FLUSH PRIVILEGES;
        
        # Set collation.
#        cmd = ("mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' "
#            "--execute='ALTER DATABASE %(db_name)s CHARACTER SET %(db_mysql_character_set)s COLLATE %(db_mysql_collate)s;'") % env
#        print cmd
#        if not int(dryrun):
#            sudo(cmd)
        set_collation_mysql(dryrun=dryrun)
        
        # Raise max packet limitation.
        run(
            ('mysql -v -h %(db_host)s -D %(db_name)s -u %(db_root_user)s '
            '-p"%(db_root_password)s" --execute="SET global '
            'net_buffer_length=%(db_mysql_net_buffer_length)s; SET global '
            'max_allowed_packet=%(db_mysql_max_allowed_packet)s;"') % env)
        
        # Run any server-specific commands (e.g. to setup permissions) before
        # we load the data.
        for command in env.db_mysql_preload_commands:
            run(command % env)
        
        # Restore the database content from the dump file.
        env.db_dump_fn = db_dump_fn
        cmd = ('gunzip < %(db_dump_fn)s | mysql -u %(db_root_user)s '
            '--password=%(db_root_password)s --host=%(db_host)s '
            '-D %(db_name)s') % env
        run(cmd)
        
        set_collation_mysql(dryrun=dryrun)
        
    else:
        raise NotImplemented

@task
def syncdb(site=None, all=0, dryrun=0):
    """
    Wrapper around Django's syncdb command.
    """
#    
    #print 'remote_app_src_package_dir_template:',env.remote_app_src_package_dir_template
    from burlap.dj import render_remote_paths
    
    dryrun = int(dryrun)
#    print 'remote_app_src_package_dir_template:',env.remote_app_src_package_dir_template
#    print 'remote_app_src_package_dir:',env.remote_app_src_package_dir
#    print 'remote_manage_dir:',env.remote_manage_dir
#    return
    set_site(site)
    
    render_remote_paths()
    
    env.db_syncdb_all_flag = '--all' if int(all) else ''
    cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s syncdb --noinput %(db_syncdb_all_flag)s -v 3 --traceback' % env
    print 'cmd:',cmd
    if not dryrun:
        run(cmd)

@task
def migrate(app_name='', site=None, fake=0, skip_databases=None, dryrun=0):
    """
    Wrapper around Django's migrate command.
    """
    from burlap.dj import render_remote_paths, has_database
    
    dryrun = int(dryrun)
    
    print 'Migrating...'
    set_site(site or env.SITE)
    
    render_remote_paths()
    
    skip_databases = (skip_databases or '')
    if isinstance(skip_databases, basestring):
        skip_databases = [_.strip() for _ in skip_databases.split(',') if _.strip()]
    
    # Since South doesn't properly support multi-database applications, we have
    # to fake app migrations on every database except the one where they exist.
    #TODO:remove this when South fixes this or gets merged into Django core.
    if env.django_migrate_fakeouts:
        for fakeout in env.django_migrate_fakeouts:
            env.db_app_name = fakeout['app']
            env.db_database_name = fakeout['database']
            if env.db_database_name in skip_databases:
                continue
            cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate %(db_app_name)s --noinput --delete-ghost-migrations --fake -v 3 --traceback' % env
            print(cmd)
            if not dryrun:
                run(cmd)
            if has_database(name=env.db_database_name, site=site):
                cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s syncdb --database=%(db_database_name)s --traceback' % env
                print(cmd)
                if not dryrun: run(cmd)
                cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate %(db_app_name)s --database=%(db_database_name)s --noinput --delete-ghost-migrations -v 3 --traceback' % env
                print(cmd)
                if not dryrun: run(cmd)
    
    env.db_migrate_fake = '--fake' if int(fake) else ''
    if app_name:
        env.db_app_name = app_name
        cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate %(db_app_name)s --noinput --delete-ghost-migrations %(db_migrate_fake)s -v 3 --traceback' % env
        print(cmd)
        if not dryrun:
            run(cmd)
    else:
        
        # First migrate apps in a specific order if given.
        for app_name in env.db_app_migration_order:
            env.db_app_name = app_name
            cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate --noinput --delete-ghost-migrations %(db_migrate_fake)s %(db_app_name)s -v 3 --traceback' % env
            print(cmd)
            if not dryrun:
                run(cmd)
            
        # Then migrate everything else remaining.
        cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate --noinput --delete-ghost-migrations %(db_migrate_fake)s -v 3 --traceback' % env
        print(cmd)
        if not dryrun:
            run(cmd)

@task
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
        local(cmd)
    else:
        run(cmd)

@task
def drop_views(name=None, site=None):
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
        cmd = ("mysql --batch -v -h %(db_host)s " \
            #"-u %(db_root_user)s -p'%(db_root_password)s' " \
            "-u %(db_user)s -p'%(db_password)s' " \
            "--execute=\"SELECT GROUP_CONCAT(CONCAT(TABLE_SCHEMA,'.',table_name) SEPARATOR ', ') AS views FROM INFORMATION_SCHEMA.views WHERE TABLE_SCHEMA = '%(db_name)s' ORDER BY table_name DESC;\"") % env
        result = sudo(cmd)
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
        sudo(cmd)
    else:
        raise NotImplementedError

env.db_install_sql_path_template = '%(src_dir)s/%(app_name)s/*/sql/*'

@task
def install_sql(name='default', site=None, dryrun=0):
    """
    Installs all custom SQL.
    """
    from burlap.dj import set_db
    dryrun = int(dryrun)
    set_db(name=name, site=site)
    load_db_set(name=name)
    paths = glob.glob(env.db_install_sql_path_template % env)
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
    
    if 'postgres' in env.db_engine or 'postgis' in env.db_engine:
        #print 'postgres'
        for path in get_paths('postgresql'):
            if not dryrun:
                print 'Installing PostgreSQL script %s.' % path
                put(local_path=path)
            else:
                env.put_remote_path = path
            #cmd = ("mysql -v -h %(db_host)s -u %(db_user)s -p'%(db_password)s' %(db_name)s < %(put_remote_path)s") % env
            cmd = ("psql --host=%(db_host)s --user=%(db_user)s -d %(db_name)s -f %(put_remote_path)s") % env
            print(cmd)
            if not dryrun:
                run(cmd)
    elif 'mysql' in env.db_engine:
        for path in get_paths('mysql'):
            print 'Installing MySQL script %s.' % path
            put(local_path=path)
            cmd = ("mysql -v -h %(db_host)s -u %(db_user)s -p'%(db_password)s' %(db_name)s < %(put_remote_path)s") % env
            print(cmd)
            if not dryrun:
                run(cmd)
    else:
        raise NotImplementedError

@task
def createsuperuser(username='admin', email=None, password=None, site=None):
    """
    Runs the Django createsuperuser management command.
    """
    from burlap.dj import render_remote_paths
    
    set_site(site)
    
    render_remote_paths()
    
    env.db_createsuperuser_username = username
    env.db_createsuperuser_email = email or username
    run('export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s createsuperuser --username=%(db_createsuperuser_username)s --email=%(db_createsuperuser_email)s' % env)

@task
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
            put(local_path=env.db_fq_fixture_path, remote_path='/tmp/data.json', use_sudo=True)
            env.db_fq_fixture_path = env.put_remote_path
        cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s loaddata %(db_fq_fixture_path)s' % env
        print cmd
        run(cmd)

@task
def restart(site=common.ALL, dryrun=0):
    """
    Restarts the database engine.
    """
    dryrun = int(dryrun)
    for service_name in env.services:
        if service_name.upper() == MYSQL:
            cmd = 'service mysqld restart'
            print(cmd)
            if not dryrun:
                sudo(cmd)
        elif service_name.upper() == POSTGRESQL:
            cmd = 'service postgresql restart; sleep 3'
            print(cmd)
            if not dryrun:
                sudo(cmd)

#TODO:deprecated? use write_postgres_pgass instead?
@task
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

        sudo('sudo -u postgres psql -c "ALTER USER %(db_save_user)s PASSWORD \'%(db_save_password)s\';"' % env)
        
        sudo("sed -i '/%(db_save_user)s/d' ~/.pgpass" % env)
        sudo('echo "localhost:5432:*:%(db_save_user)s:%(db_save_password)s" >> ~/.pgpass' % env)
        sudo('chmod 600 ~/.pgpass')
    else:
        raise NotImplementedError

@task
def write_postgres_pgpass(name=None, use_sudo=0, dryrun=0, verbose=1):
    """
    Write the file used to store login credentials for PostgreSQL.
    """
    from burlap.dj import set_db
    from burlap.file import appendline
    
    dryrun = int(dryrun)
    use_sudo = int(use_sudo)
    verbose = int(verbose)
    
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
        dryrun=1,
        verbose=0))
        
    for cmd in cmds:
        if verbose:
            print(cmd)
        if not dryrun:
            if use_sudo:
                sudo(cmd)
            else:
                run(cmd)
                
    return cmds

@task
def shell(name='default', user=None, password=None, dryrun=0, root=0, verbose=1, write_password=1, no_db=0, no_pw=0):
    """
    Opens a SQL shell to the given database, assuming the configured database
    and user supports this feature.
    """
    from burlap.dj import set_db
    
    verbose = int(verbose)
    dryrun = int(dryrun)
    root = int(root)
    write_password = int(write_password)
    no_db = int(no_db)
    no_pw = int(no_pw)
    
    # Load database credentials.
    set_db(name=name, verbose=verbose)
    load_db_set(name=name, verbose=verbose)
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
            cmds.extend(write_postgres_pgpass(dryrun=1, verbose=0))
        
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
            if not dryrun:
                if env.is_local:
                    local(cmd)
                else:
                    run(cmd)

common.service_configurators[MYSQL] = [configure]
common.service_configurators[POSTGRESQL] = [configure]
common.service_deployers[MYSQL] = [update]
common.service_restarters[POSTGRESQL] = [restart]
common.service_restarters[MYSQL] = [restart]

@task
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    from burlap.dj import get_settings
        
    data = common.get_component_settings(DB)
    
    #data['databases'] = {} # {site:django DATABASES}
    data['databases'] = []#{} # {site:django DATABASES}
    data['database_users'] = {} # {user:(host,password)}
    for site, site_data in common.iter_sites(site=ALL, no_secure=True):
        settings = get_settings(site=site)
        for _, db_data in settings.DATABASES.iteritems():
            #data['databases'][site] = settings.DATABASES
            data['databases'].append(dict(engine=db_data['ENGINE'], name=db_data['NAME'], host=db_data['HOST'], port=db_data.get('PORT')))
            data['database_users'].setdefault(db_data['USER'], [])
            data['database_users'][db_data['USER']].append(dict(password=db_data['PASSWORD'], engine=db_data['ENGINE'], name=db_data['NAME'], host=db_data['HOST'], port=db_data.get('PORT')))
    
    return data

def compare_manifest(old):
    """
    Compares the current settings to previous manifests and returns the methods
    to be executed to make the target match current settings.
    """
    old = old or {}
    methods = []
    pre = ['user', 'ip', 'package']
    new = record_manifest()
    
    old_databases = old.get('databases', {})
    del old['databases']
    new_databases = new.get('databases', {})
    del new['databases']
    
    old_databases = [tuple(sorted(_.items())) for _ in old_databases]
    old_databases = dict(zip(old_databases, old_databases))
    new_databases = [tuple(sorted(_.items())) for _ in new_databases]
    new_databases = dict(zip(new_databases, new_databases))
    added, updated, deleted = common.check_settings_for_differences(old_databases, new_databases, as_tri=True)
    for added_db in added:
        methods.append(QueuedCommand('db.create', pre=pre))

    old_database_users = old.get('database_users', {})
    del old['database_users']
    new_database_users = new.get('database_users', {})
    del new['database_users']

#    created_dbs = []
#    deleted_dbs = []
#    updated_dbs = []
#    for site_name in set(old_databases.keys()).union(new_databases.keys()):
#        print site_name
    
    has_diffs = common.check_settings_for_differences(old, new, as_bool=True)
    if has_diffs:
        methods.append(QueuedCommand('db.configure', pre=pre))
    return methods

common.manifest_recorder[MYSQL] = record_manifest
common.manifest_recorder[POSTGRESQL] = record_manifest
common.manifest_recorder[DB] = record_manifest

common.manifest_comparer[MYSQL] = compare_manifest
common.manifest_comparer[POSTGRESQL] = compare_manifest
common.manifest_comparer[DB] = compare_manifest
