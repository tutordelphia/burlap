from __future__ import print_function

import os
import re
import sys
import datetime
import glob
import tempfile
import subprocess
import warnings
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
    LocalRenderer,
)
from burlap.decorators import task
#from burlap.plan import run, sudo

# if 'db_dump_fn' not in env:
#     
#     env.db_dump_fn = None
#     #env.db_dump_fn_template = '%(db_dump_dest_dir)s/db_%(SITE)s_%(ROLE)s_%(db_date)s.sql.gz'
#     env.db_dump_fn_template = '%(db_dump_dest_dir)s/db_%(db_type)s_%(SITE)s_%(ROLE)s_$(date +%%Y%%m%%d).sql.gz'
#     
#     # This overrides the built-in load command.
#     env.db_dump_command = None
#     
#     env.db_engine = None # postgres|mysql
#     env.db_engine_subtype = None # amazon_rds
#     
#     # This overrides the built-in dump command.
#     env.db_load_command = None
#     
#     env.db_app_migration_order = []
#     env.db_dump_dest_dir = '/tmp'
#     env.db_dump_archive_dir = 'snapshots'
#     
#     # The login for performance administrative tasks (e.g. CREATE/DROP database).
#     env.db_root_user = 'root'#DEPRECATED
#     env.db_root_password = 'root'#DEPRECATED
#     env.db_root_logins = {} # {(type,host):{user:?, password:?}}
#     
#     #DEPRECATED:2015.12.12
#     #env.db_postgresql_dump_command = 'time pg_dump -c -U %(db_user)s --blobs --format=c %(db_name)s %(db_schemas_str)s | gzip -c > %(db_dump_fn)s'
#     env.db_postgresql_dump_command = 'time pg_dump -c -U %(db_user)s --blobs --format=c %(db_name)s %(db_schemas_str)s > %(db_dump_fn)s'
#     env.db_postgresql_createlangs = ['plpgsql'] # plpythonu
#     env.db_postgresql_postgres_user = 'postgres'
#     env.db_postgresql_encoding = 'UTF8'
#     env.db_postgresql_custom_load_cmd = ''
#     env.db_postgresql_port = 5432
#     env.db_postgresql_pgass_path = '~/.pgpass'
#     env.db_postgresql_pgpass_chmod = 600
#     env.db_postgresql_version_command = '`psql --version | grep -o -E "[0-9]+.[0-9]+"`'
#     
#     #DEPRECATED:2015.12.12
#     env.db_mysql_max_allowed_packet = 524288000 # 500M
#     env.db_mysql_net_buffer_length = 1000000
#     env.db_mysql_conf = '/etc/mysql/my.cnf' # /etc/my.cnf on fedora
#     env.db_mysql_dump_command = 'mysqldump --opt --compress --max_allowed_packet=%(db_mysql_max_allowed_packet)s --force --single-transaction --quick --user %(db_user)s --password=%(db_password)s -h %(db_host)s %(db_name)s | gzip > %(db_dump_fn)s'
#     env.db_mysql_preload_commands = []
#     env.db_mysql_character_set = 'utf8'
#     env.db_mysql_collate = 'utf8_general_ci'
#     env.db_mysql_port = 3306
#     env.db_mysql_root_password = None
#     env.db_mysql_custom_mycnf = False
#     
#     # Should be set to False for Django >= 1.7.
#     env.db_check_ghost_migrations = True
#     
#     env.db_syncdb_command_template = 'export SITE=%(SITE)s; export ROLE=%(ROLE)s; cd %(remote_manage_dir)s; %(django_manage)s syncdb --noinput %(db_syncdb_database)s %(db_syncdb_all_flag)s --traceback'
#     
#     # If true, means we're responsible for installing and configuring
#     # the database server.
#     # If false, means we can assume the server is not our responsibility.
#     env.db_server_managed = True
#     
#     # If true, means we're responsible for creating the logical database on
#     # the database server.
#     # If false, means creation of the database is not our responsibility.
#     env.db_database_managed = True
#     
#     env.db_fixture_sets = {} # {name:[list of fixtures]}
#     
#     #DEPRECATED
#     env.db_sets = {} # {name:{configs}}

CONNECTION_HANDLER_DJANGO = 'django'

class DatabaseSatchel(ServiceSatchel):
    
    name = 'db'
    
    def set_defaults(self):
                
        # If set, allows remote users to connect to the database.
        # This shouldn't be necessary if the webserver and database
        # share the same server.
        self.env.allow_remote_connections = False
        
        # Directory where database snapshots will be temporarily stored.
        self.env.dump_dest_dir = '/tmp'
        
        self.env.dump_archive_dir = 'snapshots'
        
        # Default filename of database snapshots.
        self.env.dump_fn_template = '{dump_dest_dir}/db_{db_type}_{SITE}_{ROLE}_{db_name}_$(date +%Y%m%d).sql.gz'
        
        # This overrides the built-in dump command.
        self.env.dump_command = None
         
        # This overrides the built-in load command.
        self.env.load_command = None
        
        # {hostname: {username: ?, password: ?}}
        self.env.root_logins = {}
        
        # Settings for specific databases within the server.
        self.env.databases = {} # {name: {}}
        
        self.env.default_db_name = 'default'
        
        # Local cache for renderers.
        self._database_renderers = {} # {(name, site): renderer}

    def get_database_defaults(self):
        """
        Returns a dictionary of default settings for each database.
        """
        return dict(
            # {name: None=burlap settings, Django=Django Python settings}
            connection_handler=None,
        )

    @task
    def set_root_login(self, r):
        """
        Looks up the root login for the given database on the given host and sets
        it to environment variables.
        
        Populates these standard variables:
        
            db_root_password
            db_root_username
            
        """
        
        # Check the legacy password location.
        try:
            r.env.db_root_username = r.env.root_username
        except AttributeError:
            pass
        try:
            r.env.db_root_password = r.env.root_password
        except AttributeError:
            pass
        
        # Check the new password location.
        key = r.env.db_host
#         print('root login key:', key)
#         print('r.env.root_logins:', r.env.root_logins)
        if key in r.env.root_logins:
            data = r.env.root_logins[key]
#             print('data:', data)
            if 'username' in data:
                r.env.db_root_username = data['username']
                r.genv.db_root_username = data['username']
            if 'password' in data:
                r.env.db_root_password = data['password']
                r.genv.db_root_password = data['password']
        else:
            msg = 'Warning: No root login entry found for host %s in role %s.' \
                % (r.env.db_host, self.genv.ROLE)
            print(msg, file=sys.stderr)
            #warnings.warn(msg, UserWarning)

    def database_renderer(self, name=None, site=None, role=None):
        """
        Renders local settings for a specific database.
        """
        
        name = name or self.env.default_db_name
        
        site = site or self.genv.SITE
        
        role = role or self.genv.ROLE
        
        key = (name, site, role)
#         print('key:', key)
        if key not in self._database_renderers:
            
            d = type(self.genv)(self.lenv)
            d.update(self.get_database_defaults())
            d.update(self.env.databases[name])
            d['db_name'] = name
            
            if d.connection_handler == CONNECTION_HANDLER_DJANGO:
                from burlap.dj import set_db
                _d = type(self.genv)()
                print('Loading Django DB settings for site {} and role {}.'.format(site, role), file=sys.stderr)
                set_db(name=name, site=site, role=role, e=_d)
                print('Loaded:', _d, file=sys.stderr)
                d.update(_d)
            
            r = LocalRenderer(self, lenv=d)
            
            # Optionally set any root logins needed for administrative commands.
            self.set_root_login(r)
            
            self._database_renderers[key] = r
        
        return self._database_renderers[key]
        
    @task
    def configure(self, *args, **kwargs):
        raise NotImplementedError
    
    @task
    def get_free_space(self):
        """
        Return free space in bytes.
        """
        cmd = "df -k | grep -vE '^Filesystem|tmpfs|cdrom|none|udev|cgroup' | awk '{ print($1 \" \" $4 }'"
        lines = [_ for _ in run_or_dryrun(cmd).strip().split('\n') if _.startswith('/')]
        assert len(lines) == 1, 'Ambiguous devices: %s' % str(lines)
        device, kb = lines[0].split(' ')
        free_space = int(kb) * 1024
        if int(verbose):
            print('free_space (bytes):', free_space)
        return free_space
    
    @task
    def get_size(self):
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
                print('database size (bytes):', output)
            return output
        else:
            raise NotImplementedError

    @task
    def load_db_set(self, name, r=None):
        """
        Loads database parameters from a specific named set.
        """
        r = r or self
        db_set = r.genv.db_sets.get(name, {})
        r.genv.update(db_set)

    @task
    def loadable(self, src, dst):
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
            print('src_db_size:',common.pretty_bytes(src_size_bytes))
            print('dst_db_size:',common.pretty_bytes(dst_size_bytes))
            print('dst_free_space:',common.pretty_bytes(free_space_bytes))
            print
            if viable:
                print('Viable! There will be %.02f %s of disk space left.' % (balance_bytes_scaled, units))
            else:
                print('Not viable! We would be %.02f %s short.' % (balance_bytes_scaled, units))
        
        return viable
    
    @task
    def dumpload(self):
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

    def render_fn(self, fn):
        return subprocess.check_output('echo %s' % fn, shell=True)
        
    def get_default_db_fn(self, fn_template=None, dest_dir=None, name=None, site=None):
        
        r = self.database_renderer(name=name, site=site)
        r.dump_dest_dir = dest_dir
        
        fn = r.format(fn_template or r.env.dump_fn_template)
        fn = self.render_fn(fn)
        fn = fn.strip()
        return fn
        
    @task
    @runs_once
    def dump(self, dest_dir=None, to_local=1, from_local=0, archive=0, dump_fn=None, name=None, site=None, use_sudo=0, cleanup=1):
        """
        Exports the target database to a single transportable file on the localhost,
        appropriate for loading using load().
        """
        
        r = self.database_renderer(name=name, site=site)
        
        use_sudo = int(use_sudo)
        
        from_local = int(from_local)
        
        to_local = int(to_local)
        
        dump_fn = dump_fn or r.env.dump_fn_template
        
        # Render the snapshot filename.
        r.env.dump_fn = self.get_default_db_fn(
            fn_template=dump_fn,
            dest_dir=dest_dir,
            name=name,
            site=site,
        )
        
        # Dump the database to a snapshot file.
        #if not os.path.isfile(os.path.abspath(r.env.dump_fn))):
        r.pc('Dumping database snapshot.')
        if from_local:
            r.local(r.env.dump_command)
        elif use_sudo:
            r.sudo(r.env.dump_command)
        else:
            r.run(r.env.dump_command)
        
        # Download the database dump file on the remote host to localhost.
        if not from_local and to_local:
            r.pc('Downloading database snapshot to localhost.')
            r.local('rsync -rvz --progress --recursive --no-p --no-g --rsh "ssh -o StrictHostKeyChecking=no -i {key_filename}" {user}@{host_string}:{dump_fn} {dump_fn}')
            
            # Delete the snapshot file on the remote system.
            if int(cleanup):
                r.pc('Deleting database snapshot on remote host.')
                r.sudo('rm {dump_fn}')
        
        # Move the database snapshot to an archive directory.
        if to_local and int(archive):
            r.pc('Archiving database snapshot.')
            db_fn = r.render_fn(r.env.dump_fn)
            r.env.archive_fn = '%s/%s' % (env.db_dump_archive_dir, os.path.split(db_fn)[-1])
            r.local('mv %s %s' % (db_fn, env.archive_fn))
        
        return r.env.dump_fn

    @task
    @runs_once
    def load(self, db_dump_fn='', prep_only=0, force_upload=0, from_local=0):
        """
        Restores a database snapshot onto the target database server.
        
        If prep_only=1, commands for preparing the load will be generated,
        but not the command to finally load the snapshot.
        """
        raise NotImplementedError
        
    @task
    def shell(self, name='default', user=None, password=None, root=0, verbose=1, write_password=1, no_db=0, no_pw=0):
        """
        Opens a SQL shell to the given database, assuming the configured database
        and user supports this feature.
        """
        raise NotImplementedError
        from burlap.dj import set_db
        
        r = self.database_renderer
        
        verbose = self.verbose
        
        root = int(root)
        write_password = int(write_password)
        no_db = int(no_db)
        no_pw = int(no_pw)
        
        # Load database credentials.
        #set_db(name=name, verbose=verbose, e=r.genv)
        #load_db_set(name=name, verbose=verbose, r=r)
        #set_root_login()
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
            
        elif 'mysql' in env.db_engine:
            
            if not no_db:
                env.db_name_str = ' %(db_name)s' % env
            
            if env.db_password:
                cmds.append(('/bin/bash -i -c \"mysql -u %(db_user)s '\
                    '-p\'%(db_password)s\' -h %(db_shell_host)s%(db_name_str)s\"') % env)
            else:
                cmds.append(('/bin/bash -i -c "mysql -u {db_user} -h {db_shell_host}{db_name_str}"') % env)
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

    @task
    def create(self, **kwargs):
        """
        Creates the target database.
        """
        raise NotImplementedError
        
    @task
    def drop_views(self, name=None, site=None):
        """
        Drops all views.
        """
        raise NotImplementedError

    @task
    def exists(self, name='default', site=None):
        """
        Returns true if a database with the given name exists. False otherwise.
        """
        raise NotImplementedError

#db = DatabaseSatchel()
