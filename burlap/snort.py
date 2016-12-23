from __future__ import print_function

from burlap import ServiceSatchel
from burlap.constants import *

class SnortSatchel(ServiceSatchel):
    
    name = 'snort'
    
    def set_defaults(self):
    
        pass

    @property
    def packager_system_packages(self):
        return {
            DEBIAN: [
                'snort',
            ],
            UBUNTU: [
                'snort',
            ],
        }
        
    def configure(self):
        r = self.local_renderer
        self.install_packages()
    
    configure.deploy_before = ['packager', 'user', 'cron']

snort = SnortSatchel()
