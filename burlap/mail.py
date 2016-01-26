
from burlap import common
from burlap.common import (
    ServiceSatchel,
)

class PostfixSatchel(ServiceSatchel):
    
    name = 'postfix'
    
    ## Service options.
    
    #ignore_errors = True
    
    # {action: {os_version_distro: command}}
#     commands = env.postfix_service_commands
    
    tasks = (
        'configure',
    )
    
    required_system_packages = {
        common.UBUNTU: [
            'postfix',
            'mailutils',
            'libsasl2-2',
            'ca-certificates',
            'libsasl2-modules',
            'nano',
        ],
    }
    
    install_required_system_packages = False 
    
    def set_defaults(self):
        self.env.service_commands = {
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
    
    def configure():
        
        if self.env.postfix_enabled:
            
            # Ensure any previous mail setups are wiped clean.
            # Note, this configuration is not compatible with mailx or sendmail.
            self.sudo_or_dryrun('if [ -e "{fn}" ]; then rm "{fn}"; fi'.format(fn='~/.mailrc'))
            self.sudo_or_dryrun('apt-get purge --yes postfix mailutils mailx sendmail')
            
            self.sudo_or_dryrun('debconf-set-selections <<< "postfix postfix/mailname string %(postfix_domain)s"' % env)
            self.sudo_or_dryrun('debconf-set-selections <<< "postfix postfix/main_mailer_type string \'Internet Site\'"')
            self.sudo_or_dryrun('apt-get install --yes postfix mailutils libsasl2-2 ca-certificates libsasl2-modules nano')
            
            remote_path = self.put_or_dryrun(
                local_path='etc_postfix_main.cf',
                remote_path='/etc/postfix/main.cf', use_sudo=True)
                
            self.sudo_or_dryrun('cat /etc/ssl/certs/Thawte_Premium_Server_CA.pem | tee -a /etc/postfix/cacert.pem')
            
            # Note, ensure Gmail account is using 2-step verification: https://accounts.google.com/SmsAuthConfig
            # Note, ensure Gmail account is using an app password: https://security.google.com/settings/security/apppasswords?pli=1
            remote_path = self.put_or_dryrun(
                local_path='etc_postfix_sasl_sasl_passwd',
                remote_path='/etc/postfix/sasl/sasl_passwd', use_sudo=True)
                
            self.sudo_or_dryrun('chmod 400 /etc/postfix/sasl/sasl_passwd')
            self.sudo_or_dryrun('chown -R root:root /etc/postfix/sasl')
            self.sudo_or_dryrun('postmap /etc/postfix/sasl/sasl_passwd')
            self.sudo_or_dryrun('update-rc.d postfix defaults')
            self.sudo_or_dryrun('service postfix start')
            self.sudo_or_dryrun('/usr/sbin/postfix reload')
            
            # Test with:
            #echo "Test mail from postfix" | mail -s "Test Postfix" user@domain
            
        else:
            self.disable()
            self.stop()
    
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']
    configure.deploy_after = []
    
PostfixSatchel()
