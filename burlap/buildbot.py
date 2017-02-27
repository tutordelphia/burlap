import os

from fabric.api import settings

from burlap.constants import *
from burlap import ServiceSatchel
from burlap.decorators import task

class BuildBotSatchel(ServiceSatchel):
    
    name = 'buildbot'
    
    #post_deploy_command = 'reload'
    
    required_system_packages = {
        UBUNTU: ['git'],
        (UBUNTU, '14.04'): ['git'],
        (UBUNTU, '16.04'): ['git'],
    }
    
    def set_defaults(self):
        
        self.env.project_dir = '/usr/local/myproject'
        self.env.virtualenv_dir = '/usr/local/myproject/.env'
        
        # Must match the main user, or otherwise we get rsync errors.
        self.env.user = 'ubuntu'
        self.env.group = 'ubuntu'
        
        self.env.bb_user = 'buildbot'
        self.env.bb_group = 'buildbot'
        
        self.env.manhole_user = 'admin'
        self.env.manhole_port = 1234
        
        self.env.perms = '777'
        
        self.env.cron_path = '/etc/cron.d/buildbot_boot'
        self.env.cron_user = 'root'
        self.env.cron_group = 'root'
        self.env.cron_perms = '600'
        
        self.env.extra_deploy_paths = ['buildbot/slave/info/', 'buildbot/slave/buildbot.tac']
        
        self.env.check_ok = True
        self.env.check_ok_paths = {} # {branch: (url, text)}
        
        self.env.rsync_paths = [] # [[from_path, to_path, user, group]]
        
        self.env.enable_apache_site = True
        
        self.env.requirements = 'pip-requirements.txt'
        
        self.env.service_commands = {
#             START:{
#                 UBUNTU: 'service apache2 start',
#             },
#             STOP:{
#                 UBUNTU: 'service apache2 stop',
#             },
#             DISABLE:{
#                 (UBUNTU, '14.04'): 'update-rc.d -f apache2 remove',
#             },
#             ENABLE:{
#                 (UBUNTU, '14.04'): 'update-rc.d apache2 defaults',
#             },
#             RELOAD:{
#                 UBUNTU: 'service apache2 reload',
#             },
#             RESTART:{
#                 # Note, the sleep 5 is necessary because the stop/start appears to
#                 # happen in the background but gets aborted if Fabric exits before
#                 # it completes.
#                 UBUNTU: 'service apache2 restart; sleep 3',
#             },
        }
    
    @task
    def restart(self):
        self.set_permissions()
        self.restart_master(ignore_errors=True)
        self.restart_slave(ignore_errors=True)
    
    @task
    def restart_master(self, ignore_errors=None):
        ignore_errors = self.ignore_errors if ignore_errors is None else ignore_errors
        r = self.local_renderer
        s = {'warn_only':True} if ignore_errors else {}
        with settings(**s):
            r.run(
                'sudo -u {bb_user} bash -c "cd {project_dir}/src/buildbot; '
                '{virtualenv_dir}/bin/buildbot restart master"')
        
    @task
    def restart_slave(self, ignore_errors=None):
        ignore_errors = self.ignore_errors if ignore_errors is None else ignore_errors
        r = self.local_renderer
        s = {'warn_only':True} if ignore_errors else {}
        with settings(**s):
            r.run(
                'sudo -u {bb_user} bash -c "cd {project_dir}/src/buildbot; '
                '{virtualenv_dir}/bin/buildslave restart slave"')
    
    @task
    def start(self):
        r = self.local_renderer
        s = {'warn_only':True} if self.ignore_errors else {}
        with settings(**s):
            r.run(
                'sudo -u {bb_user} bash -c "cd {project_dir}/src/buildbot; '
                '{virtualenv_dir}/bin/buildbot start master"')
    
    @task
    def stop(self):
        r = self.local_renderer
        s = {'warn_only':True} if self.ignore_errors else {}
        with settings(**s):
            r.run(
                'sudo -u {bb_user} bash -c "cd {project_dir}/src/buildbot; '
                '{virtualenv_dir}/bin/buildbot stop master"')
            r.run(
                'sudo -u {bb_user} bash -c "cd {project_dir}/src/buildbot; '
                '{virtualenv_dir}/bin/buildbot stop slave"')
    
    @task
    def reload(self):
        r = self.local_renderer
        s = {'warn_only':True} if self.ignore_errors else {}
        with settings(**s):
            r.run(
                'sudo -u {bb_user} bash -c "'
                'cd {project_dir}/src/buildbot; '
                '{virtualenv_dir}/bin/buildbot reconfig master"')
    
    @task
    def set_permissions(self):
        r = self.local_renderer
        r.sudo('chown -R {bb_user}:{bb_group} {project_dir}')
        #r.sudo('chown -R {bb_user}:{bb_group} {project_dir}/src/buildbot/master')
        #r.sudo('chown -R {bb_user}:{bb_group} {project_dir}/src/buildbot/slave')
        r.sudo('chmod -R {perms} {project_dir}')
    
    @task
    def rsync_paths(self):
        r = self.local_renderer
        for from_path, to_path, to_user, to_group, to_perms in r.env.rsync_paths:
            assert os.path.isfile(from_path)
            r.env.from_path = from_path
            r.env.to_path = to_path
            r.env.to_user = to_user
            r.env.to_group = to_group
            r.env.to_path_fq = os.path.join(to_path, os.path.split(from_path)[-1])
            r.env.to_perms = to_perms
#             r.local('rsync '
#                 '--verbose --compress '
#                 '--rsh "ssh -t -o StrictHostKeyChecking=no -i {key_filename}" '
#                 '{from_path} {user}@{host_string}:{to_path}')
            r.put(local_path=r.env.from_path, remote_path=r.env.to_path, use_sudo=True)
            r.sudo('chown {to_user}:{to_group} {to_path_fq}')
            r.sudo('chmod {to_perms} {to_path_fq}')
    
    @task
    def setup_dir(self, clean=0):
        pip = self.get_satchel('pip')
        clean = int(clean)
        r = self.local_renderer
        if clean:
            r.sudo('rm -Rf {virtualenv_dir} || true')
        r.sudo('mkdir -p {project_dir}')
        pip.update_install(
            requirements=self.env.requirements,
            virtualenv_dir=self.env.virtualenv_dir,
            user=self.env.user,
            group=self.env.group,
            perms=self.env.perms,
        )
        #r.sudo('{virtualenv_dir}/bin/pip install -U pip')
        r.sudo('chown -R {user}:{group} {project_dir}')
        r.sudo('chmod -R {perms} {project_dir}')
    
    @task
    def install_cron(self):
        r = self.local_renderer
        r.sudo(
            'printf \'SHELL=/bin/bash\\nPATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin\\n@reboot '
            'buildbot bash -c "cd {project_dir}/src/buildbot; '
            '{project_dir}/.env/bin/buildbot start master; '
            '{project_dir}/.env/bin/buildslave start slave"\\n\' > {cron_path}')
        r.sudo('chown {cron_user}:{cron_group} {cron_path}')
        # Must be 600, otherwise gives INSECURE MODE error.
        # http://unix.stackexchange.com/questions/91202/cron-does-not-print-to-syslog
        r.sudo('chmod {cron_perms} {cron_path}')
        r.sudo('service cron restart')
    
    @task
    def deploy_code(self):
        r = self.local_renderer
        
        r.sudo('chown -R {user}:{group} {project_dir}')
        r.sudo('chmod -R {perms} {project_dir}')
        
        r.local('rsync '
            '--recursive --verbose --perms --times --links '
            '--compress --copy-links '
            '--exclude=*.pyc --exclude=gitpoller-workdir --exclude=*.log --exclude=twistd.pid '
            '--exclude=*.sqlite '
            '--exclude=build '
            '--exclude=slave '
            '--exclude=*_runtests '
            '--delete --delete-before '
            '--rsh "ssh -t -o StrictHostKeyChecking=no -i {key_filename}" '
            'src {user}@{host_string}:{project_dir}')
        
        for path in self.env.extra_deploy_paths:
            if path.endswith('/'):
                # Directory.
                r.env.tmp_path = path[:-1]
                r.env.tmp_remote_path = os.path.split(path[:-1])[0]
                r.sudo('mkdir -p {project_dir}/src/{tmp_remote_path}')
            else:
                # File.
                r.env.tmp_path = path
                r.env.tmp_remote_path = os.path.split(path)[0]

            r.pc('Fixing permissions...')
            r.sudo('chown -R {bb_user}:{bb_group} {project_dir}')
            r.sudo('chmod -R {perms} {project_dir}')
            r.local('rsync '
                '--recursive --verbose --times --omit-dir-times --links '
                '--compress --copy-links '
                '--delete --delete-before '
                '--rsh "ssh -t -o StrictHostKeyChecking=no -i {key_filename}" '
                'src/{tmp_path} {user}@{host_string}:{project_dir}/src/{tmp_remote_path}')
        
        self.rsync_paths()
        
        self.set_permissions()
    
    @task
    def view_log(self, name='master', section='twistd'):
        r = self.local_renderer
        r.env.name = name
        assert section in ('twistd', 'http')
        r.env.section = section
        r.run('tail -f --lines=100 {project_dir}/src/buildbot/{name}/{section}.log')
    
    @task
    def manhole(self):
        r = self.local_renderer
        r.env.host_string = '127.0.0.1'#self.genv.host_string
        r.run('ssh -p{manhole_port} {manhole_user}@{host_string}')
    
    @task
    def check_ok(self):
        """
        Ensures all tests have passed for this branch.
        
        This should be called before deployment, to prevent accidental deployment of code
        that hasn't passed automated testing.
        """
        import requests
        
        if not self.env.check_ok:
            return
        
        # Find current git branch.
        branch_name = self._local('git rev-parse --abbrev-ref HEAD', capture=True).strip()
        
        check_ok_paths = self.env.check_ok_paths or {}
        
        if branch_name in check_ok_paths:
            check = check_ok_paths[branch_name]
            if 'username' in check:
                auth = (check['username'], check['password'])
            else:
                auth = None
            ret = requests.get(check['url'], auth=auth)
            passed = check['text'] in ret.content
            assert passed, 'Check failed: %s' % check['url']
    
    @task
    def setup_user(self):
        user = self.get_satchel('user')
        group = self.get_satchel('group')
        user.create(self.env.user, self.env.bb_group)
        group.create(self.env.bb_group)
        user.create(self.env.bb_user, self.env.bb_group)
    
    def deploy_pre_run(self):
        self.check_ok()
        
    @task(precursors=['packager', 'user', 'apache'])
    def configure(self):
        packager = self.get_satchel('packager')
#         umv = self.get_satchel('ubuntumultiverse')
        
        packager.configure()
        
        if self.env.enable_apache_site:
            apache = self.get_satchel('apache')
            apache.enable_mod('proxy_http')
        
        self.setup_user()
        
        #umv.configure()
        
        # Initialize base project directory and        
        # Setup Python virtual environment.
        self.setup_dir()
        
        # Copy up our code.
        self.deploy_code()
        
        self.install_cron()
        
buildbot = BuildBotSatchel()
