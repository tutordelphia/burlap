"""
This is a py.test plugin configuration that initializes a Vagrant VM.

https://pytest.org/latest/writing_plugins.html

Environment variables:

    BURLAP_TEST_BOX
    BURLAP_TEST_PROVIDER
    BURLAP_TEST_REUSE_VM

"""
from __future__ import print_function

from pipes import quote
import logging
import os
import sys

from mock import patch
import pytest

from fabric.api import env, hide, lcd, local, settings
from fabric.state import connections

from burlap.vagrant import version as _vagrant_version

HERE = os.path.dirname(__file__)
VAGRANT_VERSION = _vagrant_version()
MIN_VAGRANT_VERSION = (1, 3)


@pytest.yield_fixture(scope='session', autouse=True)
def setup_package():
    
    # Setup.
    vagrant_box = (os.environ.get('BURLAP_TEST_BOX') or '').strip()
    print('vagrant_box:', vagrant_box)
    if not vagrant_box:
        pytest.skip("Set BURLAP_TEST_BOX to choose a Vagrant base box for functional tests")
    elif vagrant_box == 'localhost':
        # Use no VM. This is intended for use on Travis-CI, where we're already running inside a VM.
        # Be careful with using this option on your development environment, because the tests
        # may disrupt your configuration.
        _configure_logging()
        _target_local_machine()
        yield
    else:
        # Spin up a VM for each test.
        # This is used when running on your development platform.
        # Unfortunately, this isn't supported in Travis-CI, which is already a VM and doesn't support
        # running additional VMs inside of it.
        _check_vagrant_version()
        vagrant_provider = os.environ.get('BURLAP_TEST_PROVIDER')
        reuse_vm = os.environ.get('BURLAP_TEST_REUSE_VM')
        _configure_logging()
        _allow_fabric_to_access_the_real_stdin()
        if not reuse_vm:
            _stop_vagrant_machine()
        _fix_home_directory()
        _init_vagrant_machine(vagrant_box)
        _start_vagrant_machine(vagrant_provider)
        _target_vagrant_machine()
        _set_optional_http_proxy()
        _update_package_index()
        yield
        
        # Teardown.
        if not reuse_vm:
            _stop_vagrant_machine()


def _check_vagrant_version():
    if VAGRANT_VERSION is None:
        pytest.skip("Vagrant is required for functional tests")
    elif VAGRANT_VERSION < MIN_VAGRANT_VERSION:
        pytest.skip("Vagrant >= %s is required for functional tests" % ".".join(map(str, MIN_VAGRANT_VERSION)))


def _configure_logging():
    logger = logging.getLogger('paramiko')
    logger.setLevel(logging.WARN)


def _allow_fabric_to_access_the_real_stdin():
    patcher = patch('fabric.io.sys')
    mock_sys = patcher.start()
    mock_sys.stdin = sys.__stdin__


def _fix_home_directory():
    local('sudo chown -R `whoami`:`whoami` ~/.vagrant.d')


def _init_vagrant_machine(base_box):
    path = os.path.join(HERE, 'Vagrantfile')
    contents = """\
Vagrant.configure(2) do |config|

  config.vm.box = "%s"

  # Speed up downloads using a shared cache across boxes
  if Vagrant.has_plugin?("vagrant-cachier")
    config.cache.scope = :box
  end
  
  config.vm.boot_timeout = 3000

  config.vm.provider "virtualbox" do |vb|
    vb.memory = "2048"
  end

end
""" % base_box
    with open(path, 'w') as vagrantfile:
        vagrantfile.write(contents)


def _start_vagrant_machine(provider):
    if provider:
        options = ' --provider %s' % quote(provider)
    else:
        options = ''
    with lcd(HERE):
#         with settings(hide('stdout')):
#             local('vagrant up' + options)
        local('vagrant up' + options)
        #local('export VAGRANT_LOG=DEBUG; vagrant up' + options)


def _stop_vagrant_machine():
    with lcd(HERE):
        with settings(hide('stdout', 'stderr', 'warnings'), warn_only=True):
            local('vagrant halt')
            local('vagrant destroy -f')


def _target_vagrant_machine():
    config = _vagrant_ssh_config()
    _set_fabric_env(
        host=config['HostName'],
        port=config['Port'],
        user=config['User'],
        key_filename=config['IdentityFile'].strip('"'),
    )
    _clear_fabric_connection_cache()


def _target_local_machine():
    import getpass
    #http://stackoverflow.com/a/16651742/247542
    _set_fabric_env(
        host='127.0.0.1',
        port='',
        user=getpass.getuser(),
        key_filename=None,
    )
    _clear_fabric_connection_cache()


def _vagrant_ssh_config():
    with lcd(HERE):
        with settings(hide('running')):
            output = local('vagrant ssh-config', capture=True)
    config = {}
    for line in output.splitlines()[1:]:
        key, value = line.strip().split(' ', 2)
        config[key] = value
    return config


def _set_fabric_env(host, port, user, key_filename):
    if port:
        env.host_string = env.host = "%s:%s" % (host, port)
    else:
        env.host_string = env.host = host
    env.user = user
    env.key_filename = key_filename
    env.disable_known_hosts = True
    env.abort_on_prompts = True


def _set_optional_http_proxy():
    http_proxy = os.environ.get('BURLAP_HTTP_PROXY')
    if http_proxy is not None:
        env.shell_env['http_proxy'] = http_proxy


def _clear_fabric_connection_cache():
    if env.host_string in connections:
        del connections[env.host_string]


def _update_package_index():
    from burlap.system import distrib_family
    family = distrib_family()
    if family == 'debian':
        from burlap.require.deb import uptodate_index
        uptodate_index()


@pytest.fixture(scope='session', autouse=True)
def allow_sudo_user(setup_package):
    """
    Fix sudo config if needed

    Some Vagrant boxes come with a too restrictive sudoers config
    and only allow the vagrant user to run commands as root.
    """
    from burlap.require import file as require_file
    require_file(
        '/etc/sudoers.d/burlap',
        contents="vagrant ALL=(ALL) NOPASSWD:ALL\n",
        owner='root',
        mode='440',
        use_sudo=True,
    )
