from __future__ import print_function

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
        r = self.local_renderer
        
        if self.env.enabled:
            
            if self.env.script_engine_groovy_inline_search:
                
                # Turn on online groovy search.
                r.sed(
                    filename=self.env.conf_path,
                    before='script.engine.groovy.inline.search: off',
                    after='script.engine.groovy.inline.search: on',
                    use_sudo=True,
                )
                # Remove off.
#                 r.sudo(
#                     "sed '/script.engine.groovy.inline.search: off/d' {conf_path}"\
#                         .format(conf_path=self.env.conf_path))
                # Add on.
#                 r.sudo(
#                     "echo 'script.engine.groovy.inline.search: on' >> {conf_path}"\
#                         .format(conf_path=self.env.conf_path))
#                 r.append(
#                     text='script.engine.groovy.inline.search: on',
#                     filename=self.env.conf_path,
#                     use_sudo=True)
            else:
#                 r.sudo(
#                     "sed '/script.engine.groovy.inline.search: on/d' {conf_path}"\
#                         .format(conf_path=self.env.conf_path))
                r.sed(
                    filename=self.env.conf_path,
                    before='script.engine.groovy.inline.search: on',
                    after='script.engine.groovy.inline.search: off',
                    use_sudo=True,
                )
            
            self.enable()
            self.restart()
        else:
            self.disable()
            self.stop()
        
    
    configure.deploy_before = ['packager', 'user', 'cron']

ElasticSearchSatchel()
