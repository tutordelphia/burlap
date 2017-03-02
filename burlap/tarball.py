from __future__ import print_function

import os
import hashlib

from burlap import Satchel
from burlap.constants import *
from burlap.decorators import task
from burlap.common import only_hostname

TARBALL = 'tarball'
RSYNC = 'rsync'

#DEPRECATED: TODO: remove tarball functionality, and rename to CodeSatchel
class TarballSatchel(Satchel):
    
    name = 'tarball'
    
    def set_defaults(self):
        
        self.env.clean = 1
        
        self.env.gzip = 1
        
        self.env.method = TARBALL
        
        self.env.rsync_source_dir = 'src'
        
        self.env.rsync_source_dirs = [] # This overrides rsync_source_dir
        
        self.env.rsync_target_dir = None
        
        self.env.rsync_target_host = '{user}@{host_string}:'
        
        self.env.rsync_auth = '--rsh "ssh -t -o StrictHostKeyChecking=no -i {key_filename}"'
         
        self.env.rsync_command_template = (
            'rsync '
            '--recursive --verbose --perms --times --links '
            '--compress --copy-links {exclude_str} '
            '--delete --delete-before --force '
            '{rsync_auth} '
            '{rsync_source_dir} '
            '{rsync_target_host}{rsync_target_dir}'
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
        
        self.env.perm_user = 'www-data'
        
        self.env.perm_group = 'www-data'
        
        self.env.perm_chmod = None
        
        self.env.set_permissions = True
    
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
    def set_permissions(self):
        r = self.local_renderer
        if r.env.rsync_target_dir:
            if r.env.perm_chmod:
                r.sudo('chmod -R {perm_chmod} {rsync_target_dir}')
            r.sudo('chown -R {perm_user}:{perm_group} {rsync_target_dir}')
    
    def _run_rsync(self, src, dst):
        print('rsync %s -> %s' % (src, dst))
        r = self.local_renderer
        r.env.hostname = only_hostname(r.genv.host_string)
        real_rsync_target_dir = r.env.rsync_target_dir
        try:
            # Rsync to a temporary directory where we'll have full permissions.
            tmp_dir = '/tmp/tmp_%s_%s' % (self.env.rsync_target_dir.replace('/', '_'), src.replace('/', '_'))
            r.env.rsync_target_dir = tmp_dir
            r.env.rsync_source_dir = src
            r.local(self.env.rsync_command_template)
            
            # Then rsync from the temp directory as sudo to complete the operation.
            r.env.rsync_source_dir = tmp_dir
            r.env.rsync_target_dir = real_rsync_target_dir
            r.env.rsync_target_host = ''
            r.env.rsync_auth = ''
            r.sudo(self.env.rsync_command_template)
        finally:
            r.env.rsync_target_dir = real_rsync_target_dir
        
    @task
    def deploy_rsync(self, *args, **kwargs):
        r = self.local_renderer
        
        # Confirm source directories.
        src_dirs = list(self.env.rsync_source_dirs)
        if not src_dirs:
            src_dirs.append(self.env.rsync_source_dir)
            
        # Confirm target directories.
        assert self.env.rsync_target_dir
        
        r.env.exclude_str = ' '.join('--exclude=%s' % _ for _ in self.env.exclusions)
        
        for src_dir in src_dirs:
            self._run_rsync(src=src_dir, dst=self.env.rsync_target_dir)
        
        if self.env.set_permissions:
            self.set_permissions()
    
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
    
    @task(precursors=['gitchecker', 'packager', 'apache2', 'pip', 'user'])
    def configure(self, *args, **kwargs):
        if self.env.method == TARBALL:
            self.deploy_tarball(*args, **kwargs)
        elif self.env.method == RSYNC:
            self.deploy_rsync(*args, **kwargs)
            
tarball_satchel = TarballSatchel()

deploy = tarball_satchel.configure
