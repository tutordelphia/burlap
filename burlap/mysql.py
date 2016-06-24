"""
MySQL users and databases
=========================

This module provides tools for creating MySQL users and databases.

"""
from __future__ import print_function

import os
from pipes import quote

from fabric.api import env, hide, puts, run, settings, runs_once

from burlap import Satchel
from burlap.constants import *
from burlap.db import DatabaseSatchel
from burlap.decorators import task
from burlap.utils import run_as_root


class MySQLSatchel(DatabaseSatchel):
    
    name = 'mysql'
    
    @property
    def packager_system_packages(self):
        return {
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
        self.env.dump_command = 'mysqldump --opt --compress --max_allowed_packet={max_allowed_packet} --force --single-transaction --quick --user {db_user} --password={db_password} -h {db_host} {db_name} | gzip > {dump_fn}'
        self.env.preload_commands = []
        self.env.character_set = 'utf8'
        self.env.collate = 'utf8_general_ci'
        self.env.port = 3306
        self.env.root_username = 'root'
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
    
    def set_root_login(self, r):
        """
        Looks up the root login for the given database on the given host and sets
        it to environment variables.
        
        Populates these standard variables:
        
            db_root_password
            db_root_username
            
        """
        
        # Check the legacy password location.
        r.env.db_root_username = r.env.root_username
        r.env.db_root_password = r.env.root_password
        
        # Check the new password location.
        key = r.env.db_host
        if key in r.env.root_logins:
            data = r.env.root_logins[key]
            if 'username' in data:
                r.env.db_root_username = data['username']
            if 'password' in data:
                r.env.db_root_password = data['password']
        
    @task
    def set_collation(self, name=None, site=None):
        r = self.database_renderer(name=name, site=site)
        r.run("mysql -v -h {db_host} -u {db_root_username} -p'{db_root_password}' "
            "--execute='ALTER DATABASE {db_name} CHARACTER SET {character_set} COLLATE {collate};'")
    
    @task
    def set_collation_all(self, name=None, site=None):
        for site in self.genv.available_sites:
            self.set_collation(name=name, site=site)
    
    @task
    def set_max_packet_size(self, name=None, site=None):
        r = self.database_renderer(name=name, site=site)
        r.run(
            ('mysql -v -h {db_host} -D {db_name} -u {db_root_username} '
            '-p"{db_root_password}" --execute="SET global '
            'net_buffer_length={net_buffer_length}; SET global '
            'max_allowed_packet={max_allowed_packet};"') % env)
    
    def packager_pre_configure(self):
        """
        Called before packager.configure is run.
        """
        self.prep_root_password()
        
    @task
    def prep_root_password(self):
        """
        Enters the root password prompt entries into the debconf cache
        so we can set them without user interaction.
        
        We keep this process separate from set_root_password() because we also need to do
        this before installing the base MySQL package, because that will also prompt the user
        for a root login.
        """
        r = self.database_renderer()
        r.sudo("dpkg --configure -a")
        r.sudo("debconf-set-selections <<< 'mysql-server mysql-server/root_password password {db_root_password}'")
        r.sudo("debconf-set-selections <<< 'mysql-server mysql-server/root_password_again password {db_root_password}'")
    
    @task
    def set_root_password(self):
        self.prep_root_password()
        r = self.database_renderer()
        r.sudo("dpkg-reconfigure -fnoninteractive `dpkg --list | egrep -o 'mysql-server-([0-9.]+)'`")

    @task
    @runs_once
    def load(self, dump_fn='', prep_only=0, force_upload=0, from_local=0, name=None, site=None, dest_dir=None):
        """
        Restores a database snapshot onto the target database server.
        
        If prep_only=1, commands for preparing the load will be generated,
        but not the command to finally load the snapshot.
        """
        
        r = self.database_renderer(name=name, site=site)
        r.pc('Loading database snapshot.')
        
        # Render the snapshot filename.
        r.env.dump_fn = self.get_default_db_fn(fn_template=dump_fn, dest_dir=dest_dir).strip()
        
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
            if int(force_upload) or (not r.genv.is_local and not r.files_exists(r.env.remote_dump_fn)):
                if not self.dryrun:
                    assert os.path.isfile(r.env.dump_fn), \
                        missing_local_dump_error
                if self.verbose:
                    print('Uploading database snapshot...')
                r.put(
                    local_path=r.env.dump_fn,
                    remote_path=r.env.remote_dump_fn)
        
        if env.is_local and not prep_only and not self.dryrun:
            assert os.path.isfile(r.env.dump_fn), \
                missing_local_dump_error
        
        if r.env.load_command:
            r.run(r.env.load_command)
        
        # Drop the database if it's there.
        r.run("mysql -v -h {db_host} -u {db_root_username} -p'{db_root_password}' "
            "--execute='DROP DATABASE IF EXISTS {db_name}'")
        
        # Now, create the database.
        r.run("mysqladmin -h {db_host} -u {db_root_username} -p'{db_root_password}' create {db_name}")
        
        # Create user
        with settings(warn_only=True):
            r.run("mysql -v -h {db_host} -u {db_root_username} -p'{db_root_password}' "
                "--execute=\"CREATE USER '{db_user}'@'%%' IDENTIFIED BY '{db_password}'; "
                "GRANT ALL PRIVILEGES ON *.* TO '{db_user}'@'%%' WITH GRANT OPTION; "
                "FLUSH PRIVILEGES;\"")
        self.set_collation(name=name, site=site)
        
        self.set_max_packet_size(name=name, site=site)
        
        # Run any server-specific commands (e.g. to setup permissions) before
        # we load the data.
        for command in r.env.preload_commands:
            r.run(command)
        
        # Restore the database content from the dump file.
        r.run('gunzip < {remote_dump_fn} | mysql -u {db_root_username} '
            '--password={db_root_password} --host={db_host} '
            '-D {db_name}')
        
        self.set_collation(name=name, site=site)

    @task
    def configure(self, do_packages=0):

        r = self.database_renderer()
        
        if int(do_packages):
            self.prep_root_password()
            self.install_packages()
            
        self.set_root_password()
        
        if r.env.custom_mycnf:
            fn = r.render_to_file('my.template.cnf', extra=_env)
            r.put(
                local_path=fn,
                remote_path=r.env.conf,
                use_sudo=True,
            )
        
        if r.env.allow_remote_connections:
            
            # Enable remote connections.
            r.sudo("sed -i 's/127.0.0.1/0.0.0.0/g' {conf}")
            
            # Enable root logins from remote connections.
            r.sudo('mysql -u {db_root_username} -p"{db_root_password}" '
                '--execute="USE mysql; '
                'GRANT ALL ON *.* to {db_root_username}@\'%%\' IDENTIFIED BY \'{db_root_password}\'; '
                'FLUSH PRIVILEGES;"')
            
            self.restart()
    
    configure.deploy_before = ['packager', 'user']

class MySQLClientSatchel(Satchel):

    name = 'mysqlclient'
    
    @property
    def packager_system_packages(self):
        return {
            FEDORA: ['mysql-server'],
            (UBUNTU, '12.04'): ['mysql-server', 'libmysqlclient-dev'],
            (UBUNTU, '14.04'): ['mysql-server', 'libmysqlclient-dev'],
        }


mysql = MySQLSatchel()
mysqlclient = MySQLClientSatchel()


def query(query, use_sudo=True, **kwargs):
    """
    Run a MySQL query.
    """
    func = use_sudo and run_as_root or run

    user = kwargs.get('mysql_user') or env.get('mysql_user')
    password = kwargs.get('mysql_password') or env.get('mysql_password')

    options = [
        '--batch',
        '--raw',
        '--skip-column-names',
    ]
    if user:
        options.append('--user=%s' % quote(user))
    if password:
        options.append('--password=%s' % quote(password))
    options = ' '.join(options)

    return func('mysql %(options)s --execute=%(query)s' % {
        'options': options,
        'query': quote(query),
    })


def user_exists(name, host='localhost', **kwargs):
    """
    Check if a MySQL user exists.
    """
    with settings(hide('running', 'stdout', 'stderr', 'warnings'), warn_only=True):
        res = query("""
            use mysql;
            SELECT COUNT(*) FROM user
                WHERE User = '%(name)s' AND Host = '%(host)s';
            """ % {
                'name': name,
                'host': host,
            }, **kwargs)
    return res.succeeded and (int(res) == 1)


def create_user(name, password, host='localhost', **kwargs):
    """
    Create a MySQL user.

    Example::

        import burlap

        # Create DB user if it does not exist
        if not burlap.mysql.user_exists('dbuser'):
            burlap.mysql.create_user('dbuser', password='somerandomstring')

    """
    with settings(hide('running')):
        query("CREATE USER '%(name)s'@'%(host)s' IDENTIFIED BY '%(password)s';" % {
            'name': name,
            'password': password,
            'host': host
        }, **kwargs)
    puts("Created MySQL user '%s'." % name)


def database_exists(name, **kwargs):
    """
    Check if a MySQL database exists.
    """
    with settings(hide('running', 'stdout', 'stderr', 'warnings'), warn_only=True):
        res = query("SHOW DATABASES LIKE '%(name)s';" % {
            'name': name
        }, **kwargs)

    return res.succeeded and (res == name)


def create_database(name, owner=None, owner_host='localhost', charset='utf8',
                    collate='utf8_general_ci', **kwargs):
    """
    Create a MySQL database.

    Example::

        import burlap

        # Create DB if it does not exist
        if not burlap.mysql.database_exists('myapp'):
            burlap.mysql.create_database('myapp', owner='dbuser')

    """
    with settings(hide('running')):

        query("CREATE DATABASE %(name)s CHARACTER SET %(charset)s COLLATE %(collate)s;" % {
            'name': name,
            'charset': charset,
            'collate': collate
        }, **kwargs)

        if owner:
            query("GRANT ALL PRIVILEGES ON %(name)s.* TO '%(owner)s'@'%(owner_host)s' WITH GRANT OPTION;" % {
                'name': name,
                'owner': owner,
                'owner_host': owner_host
            }, **kwargs)

    puts("Created MySQL database '%s'." % name)
