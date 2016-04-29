
from burlap.constants import *
from burlap import ServiceSatchel

class GPSDSatchel(ServiceSatchel):

    name = 'gpsd'
    
    tasks = (
        'configure',
        'launch',
    )
    
    required_system_packages = {
        UBUNTU: ['gpsd', 'gpsd-clients', 'python-gps', 'ntp'],
        DEBIAN: ['gpsd', 'gpsd-clients', 'python-gps', 'ntp'],
    }
    
    def set_defaults(self):
        self.env.service_commands = {
            START:{
                UBUNTU: 'service gpsd start',
                DEBIAN: 'service gpsd start',
            },
            STOP:{
                UBUNTU: 'service gpsd stop',
                DEBIAN: 'service gpsd stop',
            },
            DISABLE:{
                UBUNTU: 'chkconfig gpsd off',
                (UBUNTU, '14.04'): 'update-rc.d -f gpsd remove',
                DEBIAN: 'update-rc.d gpsd disable',
            },
            ENABLE:{
                UBUNTU: 'chkconfig gpsd on',
                (UBUNTU, '14.04'): 'update-rc.d gpsd defaults',
                DEBIAN: 'update-rc.d gpsd enable',
            },
            RELOAD:{
                UBUNTU: 'service gpsd reload',
                DEBIAN: 'service gpsd reload',
            },
            RESTART:{
                UBUNTU: 'service gpsd restart; sleep 3',
                DEBIAN: 'service gpsd restart; sleep 3',
            },
        }
        
    def launch(self):
        self.run('gpsd /dev/ttyUSB0 -F /var/run/gpsd.sock')
        
    def configure(self):
        self.install_packages()
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']

gpsd = GPSDSatchel()
