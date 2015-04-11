"""
Celery component.

Note, we manage Celery through Supervisor, since it's extremely difficult to
run several instances of Celery for multiple Apache sites.

"""
import os
import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
)

from fabric.contrib import files

from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
)
from burlap.decorators import task_or_dryrun
from burlap import common

env.celery_config_path = '/etc/sysconfig/celeryd'
#env.celery_daemon_opts = '--concurrency=1 --beat' # don't use --beat because it results in N workers all trying to run celerybeat, just run celerybeat via cron
env.celery_daemon_opts = '--concurrency=1 --loglevel=DEBUG'
env.celery_daemon_path = '/etc/init.d/celeryd'
env.celery_log_path_template = '/var/log/celeryd-%(SITE)s.log'
env.celery_celerybeat_log_path_template = '/var/log/celerybeat-%(SITE)s.log'
#env.celery_celeryd_command = 'celery worker' # doesn't support --beat or --concurrency?
env.celery_celeryd_command = 'celeryd'
env.celery_has_worker = False
env.celery_daemon_user = 'www-data'
env.celery_force_stop_command = 'pkill -9 -f celery'
env.celery_celeryd_command_template = '%(celery_supervisor_python)s %(celery_supervisor_django_manage)s %(celery_celeryd_command)s %(celery_daemon_opts)s'
env.celery_supervisor_django_manage_template = '%(remote_app_src_package_dir)s/manage.py'

env.celery_has_celerybeat = False
env.celery_celerybeat_command = 'celerybeat'
env.celery_paths_owned = ['/tmp/celerybeat-schedule*', '/var/log/celery*']
env.celery_celerybeat_opts_template = '--schedule=/tmp/celerybeat-schedule-%(SITE)s --pidfile=/tmp/celerybeat-%(SITE)s.pid --logfile=%(celery_celerybeat_log_path)s --loglevel=DEBUG'
env.celery_celerybeat_command_template = '%(celery_supervisor_python)s %(celery_supervisor_django_manage)s %(celery_celerybeat_command)s %(celery_celerybeat_opts)s'

env.celery_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start celeryd.service',
        common.UBUNTU: 'service celeryd start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop celery.service',
        common.UBUNTU: 'service celeryd stop',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable httpd.service',
        common.UBUNTU: 'chkconfig celeryd off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable httpd.service',
        common.UBUNTU: 'chkconfig celeryd on',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl stop celeryd.service; pkill -9 -f celery; systemctl start celeryd.service',
        common.UBUNTU: 'service celeryd stop; pkill -9 -f celery; service celeryd start',
    },
    common.STATUS:{
        common.FEDORA: 'systemctl status celeryd.service',
        common.UBUNTU: 'service celeryd status',
    },
}

CELERY = 'CELERY'

common.required_system_packages[CELERY] = {
#    common.FEDORA: ['rabbitmq-server'],
#    (common.UBUNTU, '12.04'): ['rabbitmq-server'],
}

common.required_python_packages[CELERY] = {
    common.FEDORA: ['celery', 'django-celery'],
    common.UBUNTU: ['celery', 'django-celery'],
}

def render_paths():
    from pip import render_paths as pip_render_paths
    
    pip_render_paths()
    
    env.celery_supervisor_remote_app_src_package_dir = env.remote_app_src_package_dir
    env.celery_supervisor_django_manage = env.celery_supervisor_django_manage_template % env
    env.celery_supervisor_python = os.path.join(env.pip_virtual_env_dir, 'bin', 'python')
    
#    if env.is_local:
#        env.celery_supervisor_django_manage = \
#            os.path.abspath(env.celery_supervisor_django_manage)
#        env.celery_supervisor_remote_app_src_package_dir = \
#            os.path.abspath(env.celery_supervisor_remote_app_src_package_dir)
    
    env.celery_log_path = env.celery_log_path_template % env
    env.celery_celerybeat_log_path = env.celery_celerybeat_log_path_template % env
    env.celery_celerybeat_opts = env.celery_celerybeat_opts_template % env
    
    env.celery_celeryd_command = env.celery_celeryd_command_template % env
    env.celery_celerybeat_command = env.celery_celerybeat_command_template % env

def create_supervisor_services():
    #print 'create_supervisor_services:',env.celery_has_worker
    if not env.celery_has_worker:
        return
    
    render_paths()
    
    ret = common.render_to_string('celery_supervisor.template.conf')
    #print ret
    return ret

def register_callbacks():
    from burlap.supervisor import register_callback
    register_callback(create_supervisor_services)

env.post_callbacks.append(register_callbacks)

def get_service_command(action):
    os_version = common.get_os_version()
    return env.celery_service_commands[action][os_version.distro]

@task_or_dryrun
def enable():
    cmd = get_service_command(common.ENABLE)
    print cmd
    sudo_or_dryrun(cmd)

@task_or_dryrun
def disable():
    cmd = get_service_command(common.DISABLE)
    print cmd
    sudo_or_dryrun(cmd)

@task_or_dryrun
def start():
    cmd = get_service_command(common.START)
    print cmd
    sudo_or_dryrun(cmd)

@task_or_dryrun
def stop():
    cmd = get_service_command(common.STOP)
    print cmd
    sudo_or_dryrun(cmd)

@task_or_dryrun
def restart():
    cmd = get_service_command(common.RESTART)
    print cmd
    sudo_or_dryrun(cmd)

@task_or_dryrun
def status():
    cmd = get_service_command(common.STATUS)
    print cmd
    sudo_or_dryrun(cmd)

@task_or_dryrun
def purge():
    """
    Clears all pending tasks in the Celery queue.
    """
    render_paths()
    sudo_or_dryrun('export SITE=%(SITE)s; export ROLE=%(ROLE)s; %(celery_supervisor_django_manage)s celeryctl purge' % env)

@task_or_dryrun
def force_stop():
    """
    Forcibly terminates all Celery processes.
    """
    with settings(warn_only=True):
        #sudo_or_dryrun(env.celery_force_stop_command % env)#fails?
        run('sudo pkill -9 -f celery')
    sudo_or_dryrun('rm -f /tmp/celery*.pid')
    #sudo_or_dryrun('rm -f /var/log/celery*.log')

@task_or_dryrun
def set_permissions():
    """
    Sets ownership and permissions for Celery-related files.
    """
    for path in env.celery_paths_owned:
        env.celery_path_owned = path
        sudo_or_dryrun('chown %(celery_daemon_user)s:%(celery_daemon_user)s %(celery_path_owned)s' % env)

#@task_or_dryrun
#def configure():
#    """
#    Installs Celery configuration and daemon.
#    """
#    todo
#    with settings(**{MODE_SUDO: True}):
#            
#        content = env.server.render_template(open(env.server.get_template_fn('celeryd.template.config')).read())
#        fn = '%(celery_config)s' % env
#        file_write(fn, content, mode='0600', owner=env.user, group=env.group, sudo=True)
#        
#        # This is included in the django-celery package, place in <virtualenv>/bin?
#        content = env.server.render_template(open(env.server.get_template_fn('celeryd.template.init')).read())
#        fn = '%(celery_daemon)s' % env
#        file_write(fn, content, mode='0755', owner=env.user, group=env.group, sudo=True)
#        