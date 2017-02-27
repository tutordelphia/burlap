
from burlap import Satchel
from burlap.constants import *
from burlap.decorators import task

class EC2MonitorSatchel(Satchel):
    """
    Manages a script to monitor
    
    http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/mon-scripts.html
    """
    
    name = 'ec2monitor'
    
    def set_defaults(self):
        self.env.installed = True
        self.env.cron_path = ''
        self.env.install_path = '/home/{user}/aws-scripts-mon'
        self.env.awscreds = 'roles/{role}/aws-{role}.creds'
        self.env.awscreds_install_path = '{install_path}/aws-{role}.creds'
        self.env.options = [
            '--mem-util',
            '--disk-path=/',
            '--disk-space-util',
            '--swap-util',
            # --verify --verbose
        ]
        self.env.access_key_id = None
        self.env.secret_access_key = None
        
        #r = self._get_renderer(verify=False)
        #cmd = #.format(**r.env)
        self.define_cron_job(
            template='etc_crond_ec2monitor',
            script_path='/etc/cron.d/ec2monitor',
            name='default',
        )
        
    def _get_renderer(self, verify=False):
        r = self.local_renderer
        
        r.env.install_path = r.env.install_path.format(**{'user': self.genv.user})
        
        kwargs = dict(
            role=self.genv.ROLE,
            install_path=r.env.install_path,
        )
        r.env.awscreds = r.env.awscreds.format(**kwargs)
        r.env.awscreds_install_path = r.env.awscreds_install_path.format(**kwargs)
        
        options = self.env.options
        if verify:
            options.extend(['--verify --verbose'])
        
        r.env.command_options = ' '.join(options)
        return r
    
    def _get_check_command(self):
        return 'cd {install_path}; export AWS_CREDENTIAL_FILE={awscreds_install_path}; ./mon-put-instance-data.pl {command_options}'
    
    @task
    def verify(self):
        r = self._get_renderer(verify=True)
        r.run(self._get_check_command())
    
    @task
    def check(self):
        r = self._get_renderer(verify=False)
        r.run(self._get_check_command())
    
    @task
    def install(self):
        r = self._get_renderer()
        r.sudo('apt-get install --yes unzip libwww-perl libdatetime-perl')
        r.run('cd ~; curl http://aws-cloudwatch.s3.amazonaws.com/downloads/CloudWatchMonitoringScripts-1.2.1.zip -O')
        r.run('cd ~; unzip -o CloudWatchMonitoringScripts-1.2.1.zip')
        r.run('cd ~; rm CloudWatchMonitoringScripts-1.2.1.zip')
        r.put(
            local_path=self.env.awscreds.format(role=self.genv.ROLE),
            remote_path=r.env.awscreds_install_path,
        )
        self.install_cron_job(
            name='default',
            extra=dict(
                command=self._get_check_command().format(**r.env)
            ))
    
    @task
    def uninstall(self):
        #todo
        pass
    
    @task(precursors=['packager', 'user'])
    def configure(self):
        """
        Executed when your settings have changed since the last deployment.
        Run commands to apply changes here.
        """
        self.install() 
                
ec2monitor = EC2MonitorSatchel()
