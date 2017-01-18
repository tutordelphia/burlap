"""
RabbitMQ
============

https://www.rabbitmq.com/

"""
from __future__ import print_function

import sys

from fabric.api import settings

from burlap import Satchel, ServiceSatchel
from burlap.constants import *
from burlap.decorators import task

RABBITMQ = 'rabbitmq'

class RabbitMQBleedingSatchel(Satchel):

    name = 'rabbitmqbleeding'
    
    @task
    def configure(self):
        """
        Enables the repository for a most current version on Debian systems.
        
            https://www.rabbitmq.com/install-debian.html
        """
        r = self.local_renderer
        
#         r.sudo("echo 'deb http://www.rabbitmq.com/debian/ testing main' >> /etc/apt/sources.list")
        r.append(
            text='deb http://www.rabbitmq.com/debian/ testing main',
            filename='/etc/apt/sources.list.d/rabbitmq.list',
            use_sudo=True)
        #r.sudo("echo 'deb http://www.rabbitmq.com/debian/ testing main' >> /etc/apt/sources.list.d/rabbitmq.list")
#         r.sudo('cd /tmp; '
#             'wget https://www.rabbitmq.com/rabbitmq-signing-key-public.asc; '
#             'apt-key add rabbitmq-signing-key-public.asc')
        r.sudo('cd /tmp; wget -O- https://www.rabbitmq.com/rabbitmq-release-signing-key.asc | sudo apt-key add -')
        r.sudo('apt-get update')
    
    configure.deploy_before = ['packager', 'rabbitmq']
    
class RabbitMQSatchel(ServiceSatchel):
    
    name = RABBITMQ
    
    ## Service options.
    
    ignore_errors = True
    
    @property
    def packager_system_packages(self):
        return {
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
        self.env.admin_username = 'admin'
            
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
    
    @task
    def list_vhosts(self):
        """
        Displays a list of configured RabbitMQ vhosts.
        """
        self.sudo('rabbitmqctl list_vhosts')
    
    @task
    def list_users(self):
        """
        Displays a list of configured RabbitMQ users.
        """
        self.sudo('rabbitmqctl list_users')
        
    @task
    def list_queues(self):
        self.sudo('rabbitmqctl list_queues')
        
    @task
    def create_user(self, username, password):
        self.genv._rabbitmq_user = username
        self.genv._rabbitmq_password = password
        self.sudo('rabbitmqctl add_user %(_rabbitmq_user)s %(_rabbitmq_password)s' % self.genv)

    @task
    def force_stop_and_purge(self):
        """
        Forcibly kills Rabbit and purges all its queues.
        
        For emergency use when the server becomes unresponsive, even to service stop calls.
        
        If this also fails to correct the performance issues, the server may have to be completely
        reinstalled.
        """
        r = self.local_renderer
        r.sudo('killall rabbitmq-server')
        r.sudo('killall beam.smp')
        #TODO:explicitly delete all subfolders, star-delete doesn't work
        r.sudo('rm -Rf /var/lib/rabbitmq/mnesia/*')

    @task
    def add_admin_user(self):
        r = self.local_renderer
        r.sudo('rabbitmqctl add_user {admin_username} {admin_password}')
        r.sudo('rabbitmqctl set_user_tags {admin_username} administrator')
        r.sudo('rabbitmqctl set_permissions -p / {admin_username} ".*" ".*" ".*"')

    @task
    def enable_management_interface(self):
        r = self.local_renderer
        r.sudo('rabbitmq-plugins enable rabbitmq_management')
        r.sudo('service rabbitmq-server restart')
        self.add_admin_user()
        print('You should now be able to access the RabbitMQ web console from:')
        print('\n    http://%s:15672/' % self.genv.host_string)
    
    @task
    def set_loopback_users(self):
        # This allows guest to login through the management interface.
        self.sudo('touch /etc/rabbitmq/rabbitmq.config')
        self.sudo("echo '[{rabbit, [{loopback_users, []}]}].' >> /etc/rabbitmq/rabbitmq.config")
        self.sudo('service rabbitmq-server restart')
    
    def _configure(self, site=None, full=0, only_data=0):
        """
        Installs and configures RabbitMQ.
        """
        from burlap.dj import get_settings
        from burlap import packager
        from burlap.common import get_current_hostname, iter_sites
        
        full = int(full)
        
    #    assert self.env.erlang_cookie
        if full and not only_data:
            packager.install_required(type=SYSTEM, service=RABBITMQ)
        
        #render_paths()
        
        hostname = get_current_hostname()
        
        target_sites = self.genv.available_sites_by_host.get(hostname, None)
        
        r = self.local_renderer
        
        params = set() # [(user,vhost)]
        for site, site_data in iter_sites(site=site, renderer=self.render_paths, no_secure=True):
            if self.verbose:
                print('!'*80, file=sys.stderr)
                print('site:', site, file=sys.stderr)
                
            # Only load site configurations that are allowed for this host.
            if target_sites is not None:
                assert isinstance(target_sites, (tuple, list))
                if site not in target_sites:
                    continue
                
            _settings = get_settings(site=site)
            #print '_settings:',_settings
            if not _settings:
                continue
            if hasattr(_settings, 'BROKER_USER') and hasattr(_settings, 'BROKER_VHOST'):
                if self.verbose:
                    print('RabbitMQ:', _settings.BROKER_USER, _settings.BROKER_VHOST)
                params.add((_settings.BROKER_USER, _settings.BROKER_PASSWORD, _settings.BROKER_VHOST))
        
        with settings(warn_only=True):
            self.add_admin_user()
        
        params = sorted(list(params))
        if not only_data:
            for user, password, vhost in params:
                r.env.broker_user = user
                r.env.broker_password = password
                r.env.broker_vhost = vhost
                with settings(warn_only=True):
                    r.sudo('rabbitmqctl add_user {broker_user} {broker_password}')
                    r.sudo('rabbitmqctl add_vhost {broker_vhost}')
                    r.sudo('rabbitmqctl set_permissions -p {broker_vhost} {broker_user} ".*" ".*" ".*"')
                    r.sudo('rabbitmqctl set_permissions -p {broker_vhost} {admin_username} ".*" ".*" ".*"')
                    
        return params
    
    @task
    def configure(self, last=None, current=None, site=None, **kwargs):
        
        RABBITMQ = self.name.upper()
        
        last = last or {}
        if RABBITMQ in last:
            last = last[RABBITMQ]
        
        current = current or {}
        if RABBITMQ in current:
            current = current[RABBITMQ]
        
        if last.get('rabbitmq_management_enabled') != current.get('rabbitmq_management_enabled'):
            self.enable_management_interface()
        
        if last.get('rabbitmq_loopback_users') != current.get('rabbitmq_loopback_users'):
            self.set_loopback_users()
        
        kwargs['site'] = site or ALL
        return self._configure(**kwargs)
    
    configure.deploy_before = ['packager', 'user']
    configure.takes_diff = True
    
RabbitMQSatchel()
RabbitMQBleedingSatchel()
