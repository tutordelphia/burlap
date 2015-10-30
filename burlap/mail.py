import re

from fabric.api import (
    env,
    local as _local
)

import burlap

#from burlap import user, package, pip, service, file, tarball
from burlap import common
from burlap.common import (
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    run_or_dryrun,
    Satchel,
    Deployer,
    Service,
)
from burlap.decorators import task_or_dryrun

POSTFIX = 'postfix'

if 'postfix_enabled' not in env:
    
    env.postfix_enabled = False
# 
    env.postfix_service_commands = {
        common.START:{
            common.UBUNTU: 'service postfix start',
        },
        common.STOP:{
            common.UBUNTU: 'service postfix stop',
        },
        common.DISABLE:{
            common.UBUNTU: 'chkconfig postfix off',
        },
        common.ENABLE:{
            common.UBUNTU: 'chkconfig postfix on',
        },
        common.RESTART:{
            common.UBUNTU: 'service postfix restart; sleep 5',
        },
        common.STATUS:{
            common.UBUNTU: 'service postfix status',
        },
    }
    
common.required_system_packages[POSTFIX] = {
    # We will handle package installation ourselves to ensure a clean installation.
#     common.UBUNTU: [
#         'postfix',
#         'mailutils',
#         'libsasl2-2',
#         'ca-certificates',
#         'libsasl2-modules',
#         'nano',
#     ],
}

class PostfixSatchel(Satchel, Service):
    
    name = POSTFIX
    
    ## Service options.
    
    #ignore_errors = True
    
    # {action: {os_version_distro: command}}
    commands = env.postfix_service_commands
    
    tasks = (
        'configure_postfix',
    )
    
    def configure_postfix():
        
        if env.postfix_enabled:
            
            # Ensure any previous mail setups are wiped clean.
            # Note, this configuration is not compatible with mailx or sendmail.
            sudo_or_dryrun('if [ -e "{fn}" ]; then rm "{fn}"; fi'.format(fn='~/.mailrc'))
            sudo_or_dryrun('apt-get purge --yes postfix mailutils mailx sendmail')
            
            sudo_or_dryrun('debconf-set-selections <<< "postfix postfix/mailname string %(postfix_domain)s"' % env)
            sudo_or_dryrun('debconf-set-selections <<< "postfix postfix/main_mailer_type string \'Internet Site\'"')
            sudo_or_dryrun('apt-get install --yes postfix mailutils libsasl2-2 ca-certificates libsasl2-modules nano')
            
            remote_path = put_or_dryrun(
                local_path='etc_postfix_main.cf',
                remote_path='/etc/postfix/main.cf', use_sudo=True)
                
            sudo_or_dryrun('cat /etc/ssl/certs/Thawte_Premium_Server_CA.pem | tee -a /etc/postfix/cacert.pem')
            
            # Note, ensure Gmail account is using 2-step verification: https://accounts.google.com/SmsAuthConfig
            # Note, ensure Gmail account is using an app password: https://security.google.com/settings/security/apppasswords?pli=1
            remote_path = put_or_dryrun(
                local_path='etc_postfix_sasl_sasl_passwd',
                remote_path='/etc/postfix/sasl/sasl_passwd', use_sudo=True)
                
            sudo_or_dryrun('chmod 400 /etc/postfix/sasl/sasl_passwd')
            sudo_or_dryrun('chown -R root:root /etc/postfix/sasl')
            sudo_or_dryrun('postmap /etc/postfix/sasl/sasl_passwd')
            sudo_or_dryrun('update-rc.d postfix defaults')
            sudo_or_dryrun('service postfix start')
            sudo_or_dryrun('/usr/sbin/postfix reload')
            
            # Test with:
            #echo "Test mail from postfix" | mail -s "Test Postfix" user@domain
            
        else:
            self.disable()
            self.stop()
    
    configure_postfix.is_deployer = True
    configure_postfix.deploy_before = ['packager', 'user']
    configure_postfix.deploy_after = []
    
postfix_satchel = PostfixSatchel()
