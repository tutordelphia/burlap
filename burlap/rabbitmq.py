
from fabric.api import settings

from burlap import Satchel, ServiceSatchel
from burlap.constants import *

class RabbitMQBleedingSatchel(Satchel):

    name = 'rabbitmqbleeding'
    
    tasks = (
        'configure',
    )
    
    def configure(self):
        """
        Enables the repository for a most current version on Debian systems.
        
            https://www.rabbitmq.com/install-debian.html
        """
        
        self.sudo_or_dryrun("echo 'deb http://www.rabbitmq.com/debian/ testing main' >> /etc/apt/sources.list")
        self.sudo_or_dryrun('cd /tmp; '
            'wget https://www.rabbitmq.com/rabbitmq-signing-key-public.asc; '
            'apt-key add rabbitmq-signing-key-public.asc')
        self.sudo_or_dryrun('apt-get update')
        
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'rabbitmq']
    
class RabbitMQSatchel(ServiceSatchel):
    
    name = 'rabbitmq'
    
    ## Service options.
    
    ignore_errors = True
    
    tasks = (
        'configure',
        'create_user',
        'enable_management_interface',
        'set_loopback_users',
    )
    
    required_system_packages = {
        FEDORA: ['rabbitmq-server'],
        (UBUNTU, '12.04'): ['rabbitmq-server'],
        (UBUNTU, '14.04'): ['rabbitmq-server'],
    }
    
    def set_defaults(self):
        self.env.rabbitmq_host = "localhost"
        self.env.vhost = "/"
        self.env.erlang_cookie = ''
        self.env.nodename = "rabbit"
        self.env.user = "guest" # DEPRECATED
        self.env.password = "guest" # DEPRECATED
        self.env.node_ip_address = ''
        self.env.port = 5672
        self.env.erl_args = ""
        self.env.cluster = "no"
        self.env.cluster_config = "/etc/rabbitmq/rabbitmq_cluster.config"
        self.env.logdir = "/var/log/rabbitmq"
        self.env.mnesiadir = "/var/lib/rabbitmq/mnesia"
        self.env.start_args = ""
        self.env.erlang_cookie_template = ''
        self.env.ignore_service_errors = 0
        self.env.management_enabled = False
        self.env.loopback_users = False
            
        self.env.service_commands = {
            START:{
                FEDORA: 'systemctl start rabbitmq-server.service',
                UBUNTU: 'service rabbitmq-server start',
            },
            STOP:{
                FEDORA: 'systemctl stop rabbitmq-server.service',
                UBUNTU: 'service rabbitmq-server stop',
            },
            DISABLE:{
                FEDORA: 'systemctl disable rabbitmq-server.service',
                UBUNTU: 'chkconfig rabbitmq-server off',
            },
            ENABLE:{
                FEDORA: 'systemctl enable rabbitmq-server.service',
                UBUNTU: 'chkconfig rabbitmq-server on',
            },
            RESTART:{
                FEDORA: 'systemctl restart rabbitmq-server.service',
                UBUNTU: 'service rabbitmq-server restart; sleep 5',
            },
            STATUS:{
                FEDORA: 'systemctl status rabbitmq-server.service',
                UBUNTU: 'service rabbitmq-server status',
            },
        }
    
    def render_paths(self):
        from burlap.dj import render_remote_paths
        render_remote_paths()
        if self.env.erlang_cookie_template:
            self.env.erlang_cookie = self.env.erlang_cookie_template % self.genv    
    
    def record_manifest(self):
        """
        Returns a dictionary representing a serialized state of the service.
        """
        data = super(RabbitMQSatchel, self).record_manifest()
        vhosts = self.configure(only_data=1)
        data['rabbitmq_all_site_vhosts'] = vhosts
        return data
    
    def list_vhosts(self):
        """
        Displays a list of configured RabbitMQ vhosts.
        """
        self.sudo_or_dryrun('rabbitmqctl list_vhosts')
    
    def list_users(self):
        """
        Displays a list of configured RabbitMQ users.
        """
        self.sudo_or_dryrun('rabbitmqctl list_users')
        
    def create_user(self, username, password):
        self.genv._rabbitmq_user = username
        self.genv._rabbitmq_password = password
        self.sudo_or_dryrun('rabbitmqctl add_user %(_rabbitmq_user)s %(_rabbitmq_password)s' % self.genv)
        #sudo_or_dryrun('rabbitmqctl set_user_tags %(rabbitmq_user)s administrator')
        #sudo_or_dryrun('rabbitmqctl set_permissions -p / %(rabbitmq_user)s ".*" ".*" ".*"')
        #sudo_or_dryrun('rabbitmqctl set_permissions -p alphabuyer %(rabbitmq_user)s ".*" ".*" ".*"')

    def enable_management_interface(self):
        self.sudo_or_dryrun('rabbitmq-plugins enable rabbitmq_management')
        self.sudo_or_dryrun('service rabbitmq-server restart')
        print 'You should not be able to access the RabbitMQ web console from:'
        print '\n    http://54.83.61.46:15672/'
        print '\nNote, the default login is guest/guest.'
    
    def set_loopback_users(self):
        # This allows guest to login through the management interface.
        self.sudo_or_dryrun('touch /etc/rabbitmq/rabbitmq.config')
        self.sudo_or_dryrun("echo '[{rabbit, [{loopback_users, []}]}].' >> /etc/rabbitmq/rabbitmq.config")
        self.sudo_or_dryrun('service rabbitmq-server restart')
    
    def _configure(self, site=None, full=0, only_data=0):
        """
        Installs and configures RabbitMQ.
        """
        from burlap.dj import get_settings
        from burlap import packager
        from burlap.common import iter_sites
        
        full = int(full)
        
    #    assert self.env.erlang_cookie
        if full and not only_data:
            packager.install_required(type=SYSTEM, service=RABBITMQ)
        
        #render_paths()
        
        params = set() # [(user,vhost)]
        for site, site_data in iter_sites(site=site, renderer=self.render_paths, no_secure=True):
            if self.verbose:
                print '!'*80
                print 'site:', site
            _settings = get_settings(site=site)
            #print '_settings:',_settings
            if not _settings:
                continue
            if hasattr(_settings, 'BROKER_USER') and hasattr(_settings, 'BROKER_VHOST'):
                if self.verbose:
                    print 'RabbitMQ:',_settings.BROKER_USER, _settings.BROKER_VHOST
                params.add((_settings.BROKER_USER, _settings.BROKER_PASSWORD, _settings.BROKER_VHOST))
        
        params = sorted(list(params))
        if not only_data:
            for user, password, vhost in params:
                self.env.broker_user = user
                self.env.broker_password = password
                self.env.broker_vhost = vhost
                with settings(warn_only=True):
                    self.sudo_or_dryrun('rabbitmqctl add_user %(rabbitmq_broker_user)s %(rabbitmq_broker_password)s' % self.genv)
                    cmd = 'rabbitmqctl add_vhost %(rabbitmq_broker_vhost)s' % self.genv
                    self.sudo_or_dryrun(cmd)
                    cmd = 'rabbitmqctl set_permissions -p %(rabbitmq_broker_vhost)s %(rabbitmq_broker_user)s ".*" ".*" ".*"' % self.genv
                    self.sudo_or_dryrun(cmd)
                    
        return params
    
    def configure(self, last=None, current=None, site=None, **kwargs):
        
        RABBITMQ = self.name.upper()
        
        last = last or {}
        if RABBITMQ in last:
            last = last[RABBITMQ]
        
        current = current or {}
        if RABBITMQ in current:
            current = current[RABBITMQ]
        
        if last.get('rabbitmq_management_enabled') != current.get('rabbitmq_management_enabled'):
            enable_management_interface()
        
        if last.get('rabbitmq_loopback_users') != current.get('rabbitmq_loopback_users'):
            set_loopback_users()
        
        kwargs['site'] = site or ALL
        return self._configure(**kwargs)
    configure.is_deployer = True
    configure.deploy_before = ['packager', 'user']
    configure.takes_diff = True
    
RabbitMQSatchel()
RabbitMQBleedingSatchel()
