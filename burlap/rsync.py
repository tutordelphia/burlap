import os
import hashlib

from burlap import Satchel
from burlap.constants import *

class RsyncSatchel(Satchel):
    
    name = 'rsync'
    
    tasks = (
        'deploy_code',
    )
    
    def set_defaults(self):
        self.env.clean = 1
        self.env.gzip = 1
        self.env.exclusions = [
            '*_local.py',
            '*.pyc',
            '*.pyo',
            '*.pyd',
            '*.svn',
            '*.tar.gz',
            #'static',
        ]
        self.src_dir = '.'
        #self.env.dir = '.burlap/rsync_cache'
        self.env.extra_dirs = []
        self.env.chown_user = 'www-data'
        self.env.chown_group = 'www-data'
        self.env.command = 'rsync --verbose --compress --recursive --delete --rsh "ssh -i {key_filename}" {exclusions_str} {rsync_src_dir} {user}@{host_string}:{rsync_dst_dir}'
    
#     def record_manifest(self):
#         """
#         Called after a deployment to record any data necessary to detect changes
#         for a future deployment.
#         """
#         from burlap.common import get_last_modified_timestamp
#         self.get_rsync_path()
#         fn = self.env.absolute_src_dir
#         if self.verbose:
#             print 'rsync.fn:', fn
#         data = get_last_modified_timestamp(fn)
#         if self.verbose:
#             print data
#         return data
    
    def deploy_code(self):
        """
        Generates a rsync of all deployable code.
        """
        
        assert self.genv.SITE, 'Site unspecified.'
        assert self.genv.ROLE, 'Role unspecified.'
        
        _env = type(self.genv)(self.genv)
        
        if self.env.exclusions:
            _env.exclusions_str = ' '.join(
                "--exclude='%s'" % _ for _ in self.env.exclusions)
            
        cmd = _env.rsync_command.format(**_env)
        self.local_or_dryrun(cmd)
        
        self.sudo_or_dryrun('chown -R {rsync_chown_user}:{rsync_chown_group} {rsync_dst_dir}'.format(**_env))
    
#     def get_rsync_hash(fn=None, refresh=1, verbose=0):
#         """
#         Calculates the hash for the rsync.
#         """
#         self.get_rsync_path()
#         fn = fn or self.env.path
#         if int(refresh):
#             self.create()
#         # Note, gzip is almost deterministic, but it includes a timestamp in the
#         # first few bytes so we strip that off before taking the hash.
#         rsync_hash = hashlib.sha512(open(fn).read()[8:]).hexdigest()
#         if int(verbose):
#             print fn
#             print rsync_hash
#         return rsync_hash
        
#     def configure(self, clean=None, refresh=1):
#         """
#         Copies the rsync to the target server.
#         
#         Note, clean=1 will delete any dynamically generated files not included
#         in the rsync.
#         """
#         
#         if clean is None:
#             clean = self.env.clean
#         clean = int(clean)
#         
#         # Generate fresh rsync.
#         if int(refresh):
#             self.create()
#         
#         rsync_path = self.get_rsync_path()
#         assert os.path.isfile(rsync_path), \
#             'No rsync found. Ensure you ran create() first.'
#         self.put_or_dryrun(local_path=self.env.path)
#         
#         self.genv.remote_app_dir = \
#             self.genv.remote_app_dir_template % self.genv
#         self.genv.remote_app_src_dir = \
#             self.genv.remote_app_src_dir_template % self.genv
#         self.genv.remote_app_src_package_dir = \
#             self.genv.remote_app_src_package_dir_template % self.genv
#         
#         if int(clean):
#             print 'Deleting old remote source...'
#             self.sudo_or_dryrun('rm -Rf  %(remote_app_src_dir)s' % self.genv)
#             self.sudo_or_dryrun('mkdir -p %(remote_app_src_dir)s' % self.genv)
#         
#         print 'Extracting rsync...'
#         self.sudo_or_dryrun('mkdir -p %(remote_app_src_dir)s' % self.genv)
#         self.sudo_or_dryrun('tar -xvzf %(put_remote_path)s -C %(remote_app_src_dir)s' % self.genv)
#         
#         for path in self.env.extra_dirs:
#             self.env.extra_dir_path = path % self.genv
#             if path.startswith('/'):
#                 self.sudo_or_dryrun(
#                     'mkdir -p %(rsync_extra_dir_path)s' % self.genv)
#             else:
#                 self.sudo_or_dryrun(
#                     'mkdir -p %(remote_app_dir)s/%(rsync_extra_dir_path)s' % self.genv)
#         
#         # Mark executables.
#         print 'Marking source files as executable...'
#         self.sudo_or_dryrun(
#             'chmod +x %(remote_app_src_package_dir)s/*' % self.genv)
#         self.sudo_or_dryrun(
#             'chmod -R %(apache_chmod)s %(remote_app_src_package_dir)s' % self.genv)
#         self.sudo_or_dryrun(
#             'chown -R %(apache_user)s:%(apache_group)s %(remote_app_dir)s' % self.genv)
#     configure.is_deployer = True
#     configure.deploy_before = ['packager', 'apache2', 'pip', 'user']
            
rsync_satchel = RsyncSatchel()

