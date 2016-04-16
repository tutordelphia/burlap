from __future__ import print_function

from burlap.constants import *
from burlap import Satchel

class SoftwareRaidSatchel(Satchel):
    
    name = 'softwareraid'
    
    def set_defaults(self):
        self.env.hdd_replace_description = None
    
    def configure(self):
        pass
    
    configure.deploy_before = ['user', 'packager']

SoftwareRaidSatchel()
