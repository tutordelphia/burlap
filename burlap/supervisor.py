import os
import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
    task,
)

from fabric.contrib import files

from burlap.common import (
    QueuedCommand,
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
)
from burlap import common
from burlap.decorators import task_or_dryrun

env.supervisor_config_template = 'supervisor_daemon.template2.config'
env.supervisor_config_path = '/etc/supervisor/supervisord.conf'
#/etc/supervisor/conf.d/celery_
env.supervisor_conf_dir = '/etc/supervisor/conf.d'
env.supervisor_daemon_bin_path_template = '%(pip_virtual_env_dir)s/bin/supervisord'
env.supervisor_daemon_path = '/etc/init.d/supervisord'
env.supervisor_bin_path_template = '%(pip_virtual_env_dir)s/bin'
env.supervisor_daemon_pid = '/var/run/supervisord.pid'
env.supervisor_log_path = "/var/log/supervisord.log"
env.supervisor_supervisorctl_path_template = '%(pip_virtual_env_dir)s/bin/supervisorctl'
env.supervisor_kill_pattern = ''

env.supervisor_services = []

# Functions that, when called, should return a supervisor service text
# ready to be appended to supervisord.conf.
# It will be called once for each site.
env._supervisor_create_service_callbacks = []

def register_callback(f):
    env._supervisor_create_service_callbacks.append(f)

env.supervisor_service_commands = {
    common.START:{
        common.FEDORA: 'systemctl start supervisord.service',
        common.UBUNTU: 'service supervisor start',
    },
    common.STOP:{
        common.FEDORA: 'systemctl stop supervisor.service',
        common.UBUNTU: 'service supervisor stop',
    },
    common.DISABLE:{
        common.FEDORA: 'systemctl disable httpd.service',
        common.UBUNTU: 'chkconfig supervisor off',
    },
    common.ENABLE:{
        common.FEDORA: 'systemctl enable httpd.service',
        common.UBUNTU: 'chkconfig supervisor on',
    },
    common.RESTART:{
        common.FEDORA: 'systemctl restart supervisord.service',
        common.UBUNTU: 'service supervisor restart; sleep 5',
    },
    common.STATUS:{
        common.FEDORA: 'systemctl status supervisord.service',
        common.UBUNTU: 'service supervisor status',
    },
}

SUPERVISOR = 'SUPERVISOR'

common.required_system_packages[SUPERVISOR] = {
#    common.FEDORA: ['rabbitmq-server'],
#    common.UBUNTU: ['rabbitmq-server'],
}

common.required_python_packages[SUPERVISOR] = {
    common.FEDORA: ['supervisor'],
    common.UBUNTU: ['supervisor'],
}

def get_service_command(action):
    os_version = common.get_os_version()
    return env.supervisor_service_commands[action][os_version.distro]

@task_or_dryrun
def enable():
    cmd = get_service_command(common.ENABLE)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def disable():
    cmd = get_service_command(common.DISABLE)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def start():
    cmd = get_service_command(common.START)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def stop():
    cmd = get_service_command(common.STOP)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def restart():
    cmd = get_service_command(common.RESTART)
    
    sudo_or_dryrun(cmd)

@task_or_dryrun
def status():
    cmd = get_service_command(common.STATUS)
    
    sudo_or_dryrun(cmd)

def render_paths():
    from pip import render_paths as pip_render_paths
    pip_render_paths()
    env.supervisor_daemon_bin_path = env.supervisor_daemon_bin_path_template % env
    env.supervisor_bin_path = env.supervisor_bin_path_template % env
    env.supervisor_supervisorctl_path = env.supervisor_supervisorctl_path_template % env

@task_or_dryrun
def configure():
    """
    Installs supervisor configuration and daemon.
    """
    render_paths()
    
    fn = common.render_to_file('supervisor_daemon.template.init')
    put(local_path=fn, remote_path=env.supervisor_daemon_path, use_sudo=True)
    
    sudo_or_dryrun('chmod +x %(supervisor_daemon_path)s' % env)
    sudo_or_dryrun('update-rc.d supervisord defaults' % env)

@task_or_dryrun
def unconfigure():
    render_paths()
    stop()
    sudo_or_dryrun('update-rc.d supervisord remove' % env)
    sudo_or_dryrun('rm -Rf %(supervisor_daemon_path)s' % env)

@task_or_dryrun
def deploy_services(site=None):
    """
    Collects the configurations for all registered services and writes
    the appropriate supervisord.conf file.
    """
    
    verbose = common.get_verbose()
    
    render_paths()
    
    supervisor_services = []
    process_groups = []
    
    for site, site_data in common.iter_sites(site=site, renderer=render_paths):
        if verbose:
            print site
        for cb in env._supervisor_create_service_callbacks:
            ret = cb()
            if isinstance(ret, basestring):
                supervisor_services.append(ret)
            elif isinstance(ret, tuple):
                assert len(ret) == 2
                conf_name, conf_content = ret
                if verbose:
                    print 'conf_name:', conf_name
                    print 'conf_content:', conf_content
                remote_fn = os.path.join(env.supervisor_conf_dir, conf_name)
                local_fn = common.write_to_file(conf_content)
                put_or_dryrun(local_path=local_fn, remote_path=remote_fn, use_sudo=True)
                
                process_groups.append(os.path.splitext(conf_name)[0])
                
                
    env.supervisor_services_rendered = '\n'.join(supervisor_services)

    fn = common.render_to_file(env.supervisor_config_template)
    put_or_dryrun(local_path=fn, remote_path=env.supervisor_config_path, use_sudo=True)
    
    for pg in process_groups:
        sudo_or_dryrun('supervisorctl add %s' % pg)
    
    #TODO:are all these really necessary?
    sudo_or_dryrun('supervisorctl restart all')
    sudo_or_dryrun('supervisorctl reread')
    sudo_or_dryrun('supervisorctl update')

@task_or_dryrun
def deploy_all_services(**kwargs):
    kwargs['site'] = common.ALL
    deploy_services(**kwargs)
    

@task_or_dryrun
def record_manifest():
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    verbose = common.get_verbose()
    
    data = common.get_component_settings(SUPERVISOR)
    
    # Celery deploys itself through supervisor, so monitor its changes too in Apache site configs.
    for site_name, site_data in env.sites.iteritems():
        if verbose:
            print site_name, site_data
        data['celery_has_worker_%s' % site_name] = site_data.get('celery_has_worker', False)
    
    return data

def compare_manifest(old):
    """
    Compares the current settings to previous manifests and returns the methods
    to be executed to make the target match current settings.
    """
    old = old or {}
    methods = []
    pre = ['user','packages','pip']
    new = common.get_component_settings(SUPERVISOR)
    has_diffs = common.check_settings_for_differences(old, new, as_bool=True)
    if has_diffs:
        methods.append(QueuedCommand('supervisor.configure', pre=pre))
        methods.append(QueuedCommand('supervisor.deploy_all_services', pre=pre))
    return methods

common.service_configurators[SUPERVISOR] = [configure]
common.service_deployers[SUPERVISOR] = [deploy_all_services]
common.service_restarters[SUPERVISOR] = [restart]
common.service_stoppers[SUPERVISOR] = [stop]
common.service_pre_deployers[SUPERVISOR] = [stop]
common.service_post_deployers[SUPERVISOR] = [start]

common.manifest_recorder[SUPERVISOR] = record_manifest
common.manifest_comparer[SUPERVISOR] = compare_manifest

# If the manifest changes, this method gets run.
common.add_deployer(
    SUPERVISOR,
    'supervisor.deploy_all_services',
    before=['packager', 'user', 'rabbitmq'])
