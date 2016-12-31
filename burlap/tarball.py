from __future__ import print_function

import os
import hashlib

from burlap import Satchel
from burlap.constants import *
from burlap.decorators import task
from burlap.common import only_hostname

TARBALL = 'tarball'
RSYNC = 'rsync'

class TarballSatchel(Satchel):
    
    name = 'tarball'
    
    def set_defaults(self):
        
        self.env.clean = 1
        
        self.env.gzip = 1
        
        self.env.method = TARBALL
        
        self.env.rsync_source_dir = 'src'
        
        self.env.rsync_source_dirs = [] # This overrides rsync_source_dir
        
        self.env.rsync_target_dir = None
        
        self.env.rsync_target_host = '%(user)s@%(host_string)s:'
        
        self.env.rsync_auth = '--rsh "ssh -t -o StrictHostKeyChecking=no -i %(key_filename)s"'
         
        self.env.rsync_command_template = (
            'rsync '
            '--recursive --verbose --perms --times --links '
            '--compress --copy-links %(tarball_exclude_str)s '
            '--delete --delete-before --force '
            '%(tarball_rsync_auth)s '
            '%(tarball_rsync_source_dir)s '
            '%(tarball_rsync_target_host)s%(tarball_rsync_target_dir)s'
        )
            
        self.env.exclusions = [
            '*_local.py',
            '*.pyc',
            '*.svn',
            '*.tar.gz',
            '*.log',
            'twistd.pid',
            '*.sqlite',
        ]
        
        self.env.dir = '.burlap/tarball_cache'
        
        self.env.extra_dirs = []
        
        self.env.user = 'www-data'
        
        self.env.group = 'www-data'
        
        self.env.set_permissions = True
    
    def render_template_paths(self, d=None):
        
        d = d or self.genv
        genv = type(self.genv)(d)
        
        genv.remote_app_dir = \
            genv.remote_app_dir_template % genv
        genv.remote_app_src_dir = \
            genv.remote_app_src_dir_template % genv
        genv.remote_app_src_package_dir = \
            genv.remote_app_src_package_dir_template % genv
            
        return genv
    
    def record_manifest(self):
        """
        Called after a deployment to record any data necessary to detect changes
        for a future deployment.
        """
        from burlap.common import get_last_modified_timestamp
        self.get_tarball_path()
        fn = self.env.absolute_src_dir
        if self.verbose:
            print('tarball.fn:', fn)
        data = get_last_modified_timestamp(fn)
        if self.verbose:
            print(data)
        return data
        
    def get_tarball_path(self):
        self.env.gzip_flag = ''
        self.env.ext = 'tar'
        if self.env.gzip:
            self.env.gzip_flag = '--gzip'
            self.env.ext = 'tgz'
        if not os.path.isdir(self.env.dir):
            os.makedirs(self.env.dir)
        self.env.absolute_src_dir = os.path.abspath(self.genv.src_dir)
        self.env.path = os.path.abspath('%(tarball_dir)s/code-%(ROLE)s-%(SITE)s-%(host_string)s.%(tarball_ext)s' % self.genv)
        return self.env.path
    
    @task
    def create(self, gzip=1):
        """
        Generates a tarball of all deployable code.
        """
        assert self.genv.SITE, 'Site unspecified.'
        assert self.genv.ROLE, 'Role unspecified.'
        self.env.gzip = bool(int(gzip))
        self.get_tarball_path()
        print('Creating tarball...')
        self.env.exclusions_str = ' '.join(
            "--exclude='%s'" % _ for _ in self.env.exclusions)
        cmd = ("cd %(tarball_absolute_src_dir)s; " \
            "tar %(tarball_exclusions_str)s --exclude-vcs %(tarball_gzip_flag)s " \
            "--create --verbose --dereference --file %(tarball_path)s *") % self.genv
        self.local(cmd)
    
    @task
    def get_tarball_hash(self, fn=None, refresh=1, verbose=0):
        """
        Calculates the hash for the tarball.
        """
        self.get_tarball_path()
        fn = fn or self.env.path
        if int(refresh):
            self.create()
        # Note, gzip is almost deterministic, but it includes a timestamp in the
        # first few bytes so we strip that off before taking the hash.
        tarball_hash = hashlib.sha512(open(fn).read()[8:]).hexdigest()
        if int(verbose):
            print(fn)
            print(tarball_hash)
        return tarball_hash
    
    @task
    def set_permissions(self, d=None):
        
        genv = self.render_template_paths(d)
        
        # Mark executables.
        print('Marking source files as executable...')
        self.sudo_or_dryrun(
            'chmod +x %(remote_app_src_package_dir)s/*' % genv)
        self.sudo_or_dryrun(
            'chmod -R %(apache_chmod)s %(remote_app_src_package_dir)s' % genv)
        self.sudo_or_dryrun(
            'chown -R %(apache_user)s:%(apache_group)s %(remote_app_dir)s' % genv)
    
    def _run_rsync(self, src, dst, genv):
        print('rsync %s -> %s' % (src, dst))
        
        genv.hostname = only_hostname(genv.host_string)
        
        # Rsync to a temporary directory where we'll have full permissions.
        #tmp_dir = (self.run_or_dryrun('mktemp -d') or '').strip() or '/tmp/sometempdir'
        tmp_dir = '/tmp/tmp_%s_%s' % (
            self.env.rsync_target_dir.replace('/', '_'),
            src.replace('/', '_'))
        genv.tarball_rsync_target_dir = tmp_dir
        genv.tarball_rsync_source_dir = src
        tmp_rsync_command = (self.env.rsync_command_template % genv) % genv
        self.local(tmp_rsync_command)
        
        # Then rsync from the temp directory as sudo to complete the operation.
        genv.tarball_rsync_tmp_dir = tmp_dir
        genv.tarball_rsync_target_host = ''
        genv.tarball_rsync_auth = ''
        #genv.tarball_rsync_source_dir = '%(user)s@%(host_string)s:%(tarball_rsync_tmp_dir)s' % genv
        genv.tarball_rsync_source_dir = '%(tarball_rsync_tmp_dir)s/*' % genv
        genv.tarball_rsync_target_dir = self.env.rsync_target_dir
        final_rsync_command = self.env.rsync_command_template % genv
        self.sudo_or_dryrun(final_rsync_command)
        
    @task
    def deploy_rsync(self, *args, **kwargs):
        
        # Confirm source directories.
        src_dirs = list(self.env.rsync_source_dirs)
        if not src_dirs:
            src_dirs.append(self.env.rsync_source_dir)
            
        # Confirm target directories.
        assert self.env.rsync_target_dir
        
        genv = self.render_template_paths()
        genv.tarball_exclude_str = ' '.join('--exclude=%s' % _ for _ in self.env.exclusions)
        
        for src_dir in src_dirs:
            _genv = type(genv)(genv)
            self._run_rsync(src=src_dir, dst=self.env.rsync_target_dir, genv=_genv)
        
        if self.env.set_permissions:
            self.set_permissions(genv)
    
    @task
    def deploy_tarball(self, clean=None, refresh=1):
        """
        Copies the tarball to the target server.
        
        Note, clean=1 will delete any dynamically generated files not included
        in the tarball.
        """
    
        if clean is None:
            clean = self.env.clean
        clean = int(clean)
        
        # Generate fresh tarball.
        if int(refresh):
            self.create()
        
        tarball_path = self.get_tarball_path()
        assert os.path.isfile(tarball_path), \
            'No tarball found. Ensure you ran create() first.'
        self.put_or_dryrun(local_path=self.env.path)
        
        genv = self.render_template_paths()
        
        if int(clean):
            print('Deleting old remote source...')
            self.sudo_or_dryrun('rm -Rf  %(remote_app_src_dir)s' % genv)
            self.sudo_or_dryrun('mkdir -p %(remote_app_src_dir)s' % genv)
        
        print('Extracting tarball...')
        self.sudo_or_dryrun('mkdir -p %(remote_app_src_dir)s' % genv)
        self.sudo_or_dryrun('tar -xvzf %(put_remote_path)s -C %(remote_app_src_dir)s' % genv)
        
        for path in self.env.extra_dirs:
            self.env.extra_dir_path = path % genv
            if path.startswith('/'):
                self.sudo_or_dryrun(
                    'mkdir -p %(tarball_extra_dir_path)s' % genv)
            else:
                self.sudo_or_dryrun(
                    'mkdir -p %(remote_app_dir)s/%(tarball_extra_dir_path)s' % genv)
        
        if self.env.set_permissions:
            self.set_permissions(genv)
    
    @task
    def configure(self, *args, **kwargs):
        if self.env.method == TARBALL:
            self.deploy_tarball(*args, **kwargs)
        elif self.env.method == RSYNC:
            self.deploy_rsync(*args, **kwargs)
        
    
    configure.deploy_before = ['gitchecker', 'packager', 'apache2', 'pip', 'user']
            
tarball_satchel = TarballSatchel()

deploy = tarball_satchel.configure
