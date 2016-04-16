from __future__ import print_function

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
            
rsync_satchel = RsyncSatchel()
