
from burlap import common
from burlap.common import (
    ServiceSatchel
)

class ElasticSearchSatchel(ServiceSatchel):
    
    name = 'elasticsearch'
    
    ## Service options.
    
    #ignore_errors = True
    
    # {action: {os_version_distro: command}}
#     commands = env.networkmanager_service_commands
    
    tasks = (
        'configure',
    )
    
    required_system_packages = {
        common.UBUNTU: ['elasticsearch'],
    }
    
    def set_defaults(self):
    
        self.env.conf_path = '/etc/elasticsearch/elasticsearch.yml'
        self.env.script_engine_groovy_inline_search = False
    
        self.env.service_commands = {
            common.START:{
                common.UBUNTU: 'service elasticsearch start',
            },
            common.STOP:{
                common.UBUNTU: 'service elasticsearch stop',
            },
            common.DISABLE:{
                common.UBUNTU: 'chkconfig elasticsearch off',
                (common.UBUNTU, '14.04'): 'update-rc.d -f elasticsearch remove',
            },
            common.ENABLE:{
                common.UBUNTU: 'chkconfig elasticsearch on',
                (common.UBUNTU, '14.04'): 'update-rc.d elasticsearch defaults',
            },
            common.RESTART:{
                common.UBUNTU: 'service elasticsearch restart',
            },
            common.STATUS:{
                common.UBUNTU: 'service elasticsearch status',
            },
        }
        
    def configure(self):
        
        if self.env.enabled:
            
            if self.env.script_engine_groovy_inline_search:
                self.sudo_or_dryrun(
                    "sed '/script.engine.groovy.inline.search: off/d' {conf_path}"\
                        .format(conf_path=self.env.conf_path))
                self.sudo_or_dryrun(
                    "echo 'script.engine.groovy.inline.search: on' >> {conf_path}"\
                        .format(conf_path=self.env.conf_path))
            else:
                self.sudo_or_dryrun(
                    "sed '/script.engine.groovy.inline.search: on/d' {conf_path}"\
                        .format(conf_path=self.env.conf_path))
            
            self.enable()
            self.restart()
        else:
            self.disable()
            self.stop()
        
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user', 'cron']

ElasticSearchSatchel()
