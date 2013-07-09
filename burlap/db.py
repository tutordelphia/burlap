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
    get_settings,
    set_site,
    render_remote_paths,
    SITE,
    ROLE,
)

env.db_dump_fn = None

# This overrides the built-in load command.
env.db_dump_command = None

# This overrides the built-in dump command.
env.db_load_command = None

env.db_app_migration_order = []
env.db_dump_dest_dir = '/tmp'

# The login for performance administrative tasks (e.g. CREATE/DROP database).
env.db_root_password = 'root'
env.db_root_user = 'root'

# If set, allows remote users to connect to the database.
# This shouldn't be necessary if the webserver and database
# share the same server.
env.db_allow_remote_connections = False

env.db_postgresql_dump_command = 'time pg_dump -c -U %(db_user)s --blobs --format=c %(db_name)s %(db_schemas_str)s | gzip -c > %(db_dump_fn)s'
env.db_postgresql_createlangs = ['plpgsql'] # plpythonu
env.db_postgresql_postgres_user = 'postgres'

env.db_mysql_max_allowed_packet = 524288000 # 500M
env.db_mysql_net_buffer_length = 1000000
env.db_mysql_conf = '/etc/mysql/my.cnf'
env.db_mysql_dump_command = 'mysqldump --opt --compress --max_allowed_packet=%(db_mysql_max_allowed_packet)s --force --single-transaction --quick --user %(db_user)s --password=%(db_password)s -h %(db_host)s %(db_name)s | gzip > %(db_dump_fn)s'
env.db_mysql_preload_commands = []

env.db_fixture_sets = {} # {name:[list of fixtures]}

MYSQL = 'MYSQL'
MYSQLCLIENT = 'MYSQLCLIENT'
POSTGRESQL = 'POSTGRESQL'
POSTGRESQLCLIENT = 'POSTGRESQLCLIENT'

common.required_system_packages[MYSQL] = {
    common.FEDORA: ['mysql-server'],    common.UBUNTU: ['mysql-server', 'libmysqlclient-dev'],
}
common.required_system_packages[POSTGRESQL] = {
    common.FEDORA: ['postgresql-server'],
    common.UBUNTU: ['postgresql-9.1'],
}

common.required_system_packages[MYSQLCLIENT] = {
    common.FEDORA: ['mysql-client'],
    common.UBUNTU: ['mysql-client', 'libmysqlclient-dev'],
}
common.required_system_packages[POSTGRESQLCLIENT] = {
    common.FEDORA: ['postgresql-client'],
    common.UBUNTU: ['postgresql-client-9.1','python-psycopg2'],
}

def set_db(name=None, site=None, role=None):
    name = name or 'default'
    settings = get_settings(site=site, role=role)
    print 'settings:',settings
    default_db = settings.DATABASES[name]
    env.db_name = default_db['NAME']
    env.db_user = default_db['USER']
    env.db_host = default_db['HOST']
    env.db_password = default_db['PASSWORD']
    env.db_engine = default_db['ENGINE']

@task
def configure(name=None, site=None, _role=None, dryrun=0):
    """
    Configures a fresh install of the database
    """
    assert env[ROLE]
    require('app_name')
    set_db(name=name, site=site, role=_role)
    print 'site:',env[SITE]
    print 'role:',env[ROLE]
    env.dryrun = int(dryrun)
    if 'postgres' in env.db_engine:

        env.pg_ver = run('psql --version | grep -o -E "[0-9]+.[0-9]+"')
        print 'PostgreSQL version %(pg_ver)s detected.' % env
        
        print 'Backing up PostgreSQL configuration files...'
        sudo('cp /etc/postgresql/%(pg_ver)s/main/postgresql.conf /etc/postgresql/%(pg_ver)s/main/postgresql.conf.$(date +%%Y%%m%%d%%H%%M).bak' % env)
        sudo('cp /etc/postgresql/%(pg_ver)s/main/pg_hba.conf /etc/postgresql/%(pg_ver)s/main/pg_hba.conf.$(date +%%Y%%m%%d%%H%%M).bak' % env)
        
        print 'Allowing remote connections...'
        fn = common.render_to_file('pg_hba.template.conf')
        put(local_path=fn,
            remote_path='/etc/postgresql/%(pg_ver)s/main/pg_hba.conf' % env,
            use_sudo=True)
        
        # Don't do this. Keep it locked down and use an SSH tunnel instead.
        # See common.tunnel()
        #sudo('sed -i "s/#listen_addresses = \'localhost\'/listen_addresses = \'*\'/g" /etc/postgresql/%(pg_ver)s/main/postgresql.conf' % env)
        
        print 'Enabling auto-vacuuming...'
        sudo('sed -i "s/#autovacuum = on/autovacuum = on/g" /etc/postgresql/%(pg_ver)s/main/postgresql.conf' % env)
        sudo('sed -i "s/#track_counts = on/track_counts = on/g" /etc/postgresql/%(pg_ver)s/main/postgresql.conf' % env)
        
        # Set UTF-8 as the default database encoding.
        sudo('psql --user=postgres --no-password --command="'
            'UPDATE pg_database SET datistemplate = FALSE WHERE datname = \'template1\';'
            'DROP DATABASE template1;'
            'CREATE DATABASE template1 WITH TEMPLATE = template0 ENCODING = \'UNICODE\';'
            'UPDATE pg_database SET datistemplate = TRUE WHERE datname = \'template1\';'
            '\c template1'
            'VACUUM FREEZE;'
            'UPDATE pg_database SET datallowconn = FALSE WHERE datname = \'template1\';"')

    elif 'mysql' in env.db_engine:
        if env.db_allow_remote_connections:
            
            # Enable remote connections.
            sudo("sed -i 's/127.0.0.1/0.0.0.0/g' %(db_mysql_conf)s" % env)
            
            # Enable root logins from remote connections.
            sudo('mysql -u %(db_root_user)s -p"%(db_root_password)s" --execute="USE mysql; GRANT ALL ON *.* to %(db_root_user)s@\'%%\' IDENTIFIED BY \'%(db_root_password)s\'; FLUSH PRIVILEGES;"' % env)
            
            sudo('service mysql restart')

@task
def create(drop=0, name=None, dryrun=0, site=None, post_process=0):
    """
    Creates the target database
    """
    assert env[ROLE]
    dryrun = int(dryrun)
    render_remote_paths()
    require('app_name')
    env.db_drop_flag = '--drop' if int(drop) else ''
    set_db(name=name, site=site)
    print 'site:',env[SITE]
    print 'role:',env[ROLE]
    env.dryrun = int(dryrun)
    if 'postgres' in env.db_engine:
        env.src_dir = os.path.abspath(env.src_dir)
        # This assumes the django-extensions app is installed, which
        # provides the convenient sqlcreate command.
        if env.is_local:
            env.db_src_dir = env.src_dir
        else:
            env.db_src_dir = env.remote_app_src_dir
        cmd = 'cd %(db_src_dir)s; export SITE=%(SITE)s; export ROLE=%(ROLE)s; %(django_manage)s sqlcreate --router=default %(db_drop_flag)s | psql --user=%(db_postgresql_postgres_user)s --no-password' % env
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
        
        # Create user.
        cmd = "mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' --execute=\"GRANT USAGE ON *.* TO %(db_user)s@'%%'; DROP USER %(db_user)s@'%%';\"" % env
        print cmd
        if not int(dryrun):
            run(cmd)
        #cmd = "mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' --execute=\"CREATE USER %(db_user)s@%(db_host)s IDENTIFIED BY '%(db_password)s';\"" % env
        #cmd = "mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' --execute=\"GRANT ALL PRIVILEGES ON %(db_name)s.* TO %(db_user)s@%(db_host)s IDENTIFIED BY '%(db_password)s';\"" % env
        cmd = "mysql -v -h %(db_host)s -u %(db_root_user)s -p'%(db_root_password)s' --execute=\"GRANT ALL PRIVILEGES ON %(db_name)s.* TO %(db_user)s@'%%' IDENTIFIED BY '%(db_password)s';\"" % env
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
    assert env[ROLE]
    require('app_name')
    set_db(name=name, site=site)
    print 'site:',env[SITE]
    print 'role:',env[ROLE]
    env.dryrun = int(dryrun)
    
    syncdb(all=True, site=site)
    migrate(fake=True, site=site)
    install_sql(name=name, site=site)
    createsuperuser()

@task
def update(name=None, site=None):
    """
    Updates schema and custom SQL.
    """
    set_db(name=name, site=site)
    syncdb(site=site)
    migrate(site=site)
    install_sql(name=name, site=site)

@task
def dump(dryrun=0, dest_dir=None):
    """
    Exports the target database to a single transportable file on the localhost,
    appropriate for loading using load().
    """
    set_db()
    if dest_dir:
        env.db_dump_dest_dir = dest_dir
    env.db_date = datetime.date.today().strftime('%Y%m%d')
    env.db_dump_fn = '%(db_dump_dest_dir)s/%(db_name)s_%(db_date)s.sql.gz' % env
    if env.db_dump_command:
        run(env.db_dump_command % env)
    elif 'postgres' in env.db_engine:
        assert env.db_schemas, \
            'Please specify the list of schemas to dump in db_schemas.'
        env.db_schemas_str = ' '.join('-n %s' % _ for _ in env.db_schemas)
        cmd = env.db_postgresql_dump_command % env
        print cmd
        if not int(dryrun):
            local(cmd)
    elif 'mysql' in env.db_engine:
        cmd = env.db_mysql_dump_command % env
        print cmd
        if not int(dryrun):
            local(cmd)
    else:
        raise NotImplemented
    return env.db_dump_fn

@task
def load(db_dump_fn, dryrun=0):
    """
    Restores a database snapshot onto the target database server.
    """
    env.db_dump_fn = db_dump_fn
    set_db()
    
    dryrun = int(dryrun)
    
    # Copy snapshot file to target.
    missing_local_dump_error = (
        "Database dump file %(db_dump_fn)s does not exist."
    ) % env
    env.db_remote_dump_fn = '/tmp/'+os.path.split(env.db_dump_fn)[-1]
    if not dryrun and not files.exists(env.db_dump_fn):
        assert os.path.isfile(env.db_dump_fn), \
            missing_local_dump_error
        put(local_path=env.db_dump_fn, remote_path=env.db_remote_dump_fn)
    
    if env.db_load_command:
        run(env.db_load_command % env)
    elif 'postgres' in env.db_engine:
        
        cmd = 'dropdb --user=%(db_postgresql_postgres_user)s %(db_name)s' % env
        print cmd
        if not dryrun:
            run(cmd)
        cmd = 'psql --user=%(db_postgresql_postgres_user)s -c "CREATE DATABASE %(db_name)s;"' % env
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
        cmd = 'gunzip -c %(db_remote_dump_fn)s | pg_restore -U %(db_postgresql_postgres_user)s --create --dbname=%(db_name)s' % env
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
        
    else:
        raise NotImplemented

@task
def syncdb(site=None, all=0, dryrun=0):
    """
    Wrapper around Django's syncdb command.
    """
    set_site(site)
    
    render_remote_paths()
    
    env.db_syncdb_all_flag = '--all' if int(all) else ''
    cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s syncdb --noinput %(db_syncdb_all_flag)s -v 3 --traceback' % env
    print cmd
    if not int(dryrun):
        run(cmd)

@task
def migrate(app_name='', site=None, fake=0):
    """
    Wrapper around Django's migrate command.
    """
    set_site(site)
    
    render_remote_paths()
    
    env.db_migrate_fake = '--fake' if int(fake) else ''
    if app_name:
        env.db_app_name = app_name
        run('export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate %(db_app_name)s --noinput --delete-ghost-migrations %(db_migrate_fake)s -v 3 --traceback' % env)
    else:
        
        # First migrate apps in a specific order if given.
        for app_name in env.db_app_migration_order:
            env.db_app_name = app_name
            run('export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate --noinput --delete-ghost-migrations %(db_migrate_fake)s %(db_app_name)s -v 3 --traceback' % env)
            
        # Then migrate everything else remaining.
        cmd = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s migrate --noinput --delete-ghost-migrations %(db_migrate_fake)s -v 3 --traceback' % env
        #print cmd
        run(cmd)

@task
def drop_views(name=None, site=None):
    """
    Drops all views.
    """
    set_db(name=name, site=site)
    if 'postgres' in env.db_engine:
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
def install_sql(name=None, site=None):
    """
    Installs all custom SQL.
    """
    #_settings = get_settings(site=site, role=env.ROLE)
    set_db(name=name, site=site)
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
            content = open(path, 'r').read()
            matches = re.findall('[\s\t]+VIEW[\s\t]+([a-zA-Z0-9_]+)', content, flags=re.IGNORECASE)
            #assert matches, 'Unable to find view name: %s' % (p,)
            view_name = ''
            if matches:
                view_name = matches[0]
            data.append((path, view_name, content))
        for d in sorted(data, cmp=cmp_paths):
            yield d[0]
    
    if 'postgres' in env.db_engine:
        #print 'postgres'
        for path in get_paths('postgresql'):
            put(local_path=path)
            #cmd = ("mysql -v -h %(db_host)s -u %(db_user)s -p'%(db_password)s' %(db_name)s < %(put_remote_path)s") % env
            cmd = ("psql --host=%(db_host)s --user=%(db_user)s -d %(db_name)s -f %(put_remote_path)s") % env
            #print cmd
            sudo(cmd)
    elif 'mysql' in env.db_engine:
        for path in get_paths('mysql'):
            put(local_path=path)
            cmd = ("mysql -v -h %(db_host)s -u %(db_user)s -p'%(db_password)s' %(db_name)s < %(put_remote_path)s") % env
            #print cmd
            sudo(cmd)
    else:
        raise NotImplementedError

@task
def createsuperuser(username='admin', email=None, password=None, site=None):
    """
    Runs the Django createsuperuser management command.
    """
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
def restart(site=common.ALL):
    for site, site_data in common.iter_sites(site=site, renderer=lambda: set_db(name='default')):
        print site
        #set_db(name=name, site=site)
        if 'postgres' in env.db_engine:
            sudo('service postgresql restart; sleep 3')
#        elif 'mysql' in env.db_engine:
#            sudo('service mysql restart')

@task
def save_db_password(user, password):
    set_db(name='default')
    if 'postgres' in env.db_engine:
        env.db_save_user = user
        env.db_save_password = password
        # Note, this requires pg_hba.conf needs the line:
        # local   all         postgres                          ident
        #assert env.db_postgresql_postgres_password
#        sudo('sudo -u postgres psql -c "ALTER USER postgres PASSWORD \'%(db_postgresql_postgres_password)s\';"' % env)
#        sudo('echo "localhost:5432:*:postgres:%(db_postgresql_postgres_password)s" >> ~/.pgpass' % env)

        sudo('sudo -u postgres psql -c "ALTER USER %(db_save_user)s PASSWORD \'%(db_save_password)s\';"' % env)
        
        #'if [ "$(cat ~/.pgpass | grep issue_mapper)" ]; then echo "found"; else echo "none"; fi' % env
        #sudo('sed -i "s/#listen_addresses = \'localhost\'/listen_addresses = \'*\'/g" /etc/postgresql/%(pg_ver)s/main/postgresql.conf' % env)
        sudo("sed -i '/%(db_save_user)s/d' ~/.pgpass" % env)
        sudo('echo "localhost:5432:*:%(db_save_user)s:%(db_save_password)s" >> ~/.pgpass' % env)
        sudo('chmod 600 ~/.pgpass')
    else:
        raise NotImplementedError

common.service_configurators[MYSQL] = [configure]
common.service_configurators[POSTGRESQL] = [configure]
common.service_deployers[MYSQL] = [update]
common.service_restarters[POSTGRESQL] = [restart]
common.service_restarters[MYSQL] = [restart]
