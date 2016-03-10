from burlap.constants import *
from burlap import Satchel

class SoftwareRaidSatchel(Satchel):
    
    name = 'softwareraid'
    
    tasks = (
        'configure',
    )
    
    def set_defaults(self):
        super(SoftwareRaidSatchel, self).set_defaults()
        
        self.env.hdd_replace_description = None
    
    def configure(self):
        pass
    configure.is_deployer = True
    configure.deploy_before = ['user', 'packager']
