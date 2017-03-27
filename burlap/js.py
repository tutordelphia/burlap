from __future__ import print_function

from burlap import ServiceSatchel
from burlap.constants import *
from burlap.decorators import task

class JSHintSatchel(ServiceSatchel):
    
    name = 'jshint'

    def set_defaults(self):
        pass

    @property
    def packager_system_packages(self):
        return {
            DEBIAN: ['npm'],
            UBUNTU: ['npm'],
        }
        
    @task(precursors=['packager', 'user'])
    def configure(self):
        r = self.local_renderer
        if r.env.enabled:
            r.sudo('npm install -g jshint')
            # The Ubuntu 14 package is malformed and refers to "node" instead of "nodejs".
            r.sudo('ln -s /usr/bin/nodejs /usr/bin/node')
        else:
            r.sudo('npm uninstall -g jshint')
    
jshint = JSHintSatchel()
