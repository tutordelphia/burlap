from __future__ import absolute_import, print_function

from pprint import pprint

from burlap.common import Satchel
from burlap.constants import *
from burlap.decorators import task

EZ_SETUP = 'ez_setup'
PYTHON_PIP = 'python-pip'
GET_PIP = 'get-pip'
BOOTSTRAP_METHODS = (
    EZ_SETUP,
    PYTHON_PIP,
    GET_PIP,
)

class PIPSatchel(Satchel):
    
    name = 'pip'
    
    @property
    def packager_system_packages(self):
        return {
            UBUNTU: [
                'gcc', 'python-dev', 'build-essential', 'python-pip',
            ],
            (UBUNTU, '14.04'): [
                #'python-pip',#obsolete in 14.04?
                #'python-virtualenv',#obsolete in 14.04?
                'gcc', 'python-dev', 'build-essential', 'python-pip',
            ],
            (UBUNTU, '14.10'): [
                'gcc', 'python-dev', 'build-essential', 'python-pip',
            ],
            (UBUNTU, '16.04'): [
                'gcc', 'python-dev', 'build-essential', 'python-pip',
            ],
            (UBUNTU, '16.10'): [
                'gcc', 'python-dev', 'build-essential', 'python-pip',
            ],
        }
        
    def set_defaults(self):
        self.env.bootstrap_method = GET_PIP
        self.env.check_permissions = True
        self.env.user = 'www-data'
        self.env.group = 'www-data'
        self.env.perms = '775'
        self.env.virtualenv_dir = '.env'
        self.env.requirements = 'pip-requirements.txt'

    @task
    def has_pip(self):
        r = self.local_renderer
        with self.settings(warn_only=True):
            ret = (r.run('which pip') or '').strip()
            return bool(ret)
            
    @task
    def bootstrap(self, force=0):
        """
        Installs all the necessary packages necessary for managing virtual
        environments with pip.
        """
        force = int(force)
        if self.has_pip() and not force:
            return
        
        r = self.local_renderer
        
        if r.env.bootstrap_method == GET_PIP:
            r.sudo('curl --silent --show-error --retry 5 https://bootstrap.pypa.io/get-pip.py | python')
        elif r.env.bootstrap_method == EZ_SETUP:
            r.run('wget http://peak.telecommunity.com/dist/ez_setup.py -O /tmp/ez_setup.py')
            with self.settings(warn_only=True):
                r.sudo('python /tmp/ez_setup.py -U setuptools')
            r.sudo('easy_install -U pip')
        elif r.env.bootstrap_method == PYTHON_PIP:
            r.sudo('apt-get install -y python-pip')
        else:
            raise NotImplementedError('Unknown pip bootstrap method: %s' % r.env.bootstrap_method)
            
        r.sudo('pip install --upgrade pip')
        r.sudo('pip install --upgrade virtualenv')

    @task
    def clean_virtualenv(self, virtualenv_dir=None):
        r = self.local_renderer
        with self.settings(warn_only=True):
            print('Deleting old virtual environment...')
            r.sudo('rm -Rf {virtualenv_dir}')
        
    @task
    def has_virtualenv(self):
        """
        Returns true if the virtualenv tool is installed.
        """
        with self.settings(warn_only=True):
            ret = self.run('which virtualenv').strip()
            return bool(ret)
    
    @task
    def virtualenv_exists(self, virtualenv_dir=None):
        """
        Returns true if the virtual environment has been created.
        """
        r = self.local_renderer
        ret = True
        with self.settings(warn_only=True):
            ret = r.run('ls {virtualenv_dir}') or ''
            ret = 'cannot access' not in ret.strip().lower()
            
        if self.verbose:
            if ret:
                print('Yes')
            else:
                print('No')
            
        return ret
    
    @task
    def init(self):
        """
        Creates the virtual environment.
        """
        r = self.local_renderer
        
#         if self.virtualenv_exists():
#             print('virtualenv exists')
#             return
        
        print('Creating new virtual environment...')
        with self.settings(warn_only=True):
            cmd = '[ ! -d {virtualenv_dir} ] && virtualenv --no-site-packages {virtualenv_dir} || true'
            if self.is_local:
                r.run(cmd)
            else:
                r.sudo(cmd)
    
    @task
    def set_permissions(self):
        r = self.local_renderer
        if not self.is_local and r.env.check_permissions:
            r.sudo('chown -R {pip_user}:{pip_group} {virtualenv_dir}')
            r.sudo('chmod -R {pip_perms} {virtualenv_dir}')
    
    def get_combined_requirements(self, requirements=None):
        """
        Returns all requirements files combined into one string.
        """
        
        requirements = requirements or self.env.requirements
        
        def iter_lines(fn):
            with open(fn, 'r') as fin:
                for line in fin.readlines():
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    yield line
        
        content = []
        if isinstance(requirements, (tuple, list)):
            for f in requirements:
                f = self.find_template(f)
                content.extend(list(iter_lines(f)))
        else:
            assert isinstance(requirements, basestring)
            f = self.find_template(requirements)
            content.extend(list(iter_lines(f)))
        
        return '\n'.join(content)
    
    @task
    def update_install(self, **kwargs):
        r = self.local_renderer
        
        options = [
            'requirements',
            'virtualenv_dir',
            'user',
            'group',
            'perms',
        ]
        for option in options:
            setattr(r.env, option, kwargs.pop(option, None) or getattr(r.env, option))
        
        # Make sure pip is installed.
        self.bootstrap()
        
        # Make sure our virtualenv is installed.
        self.init()
        
        # Collect all requirements.
        tmp_fn = r.write_temp_file(self.get_combined_requirements(requirements=r.env.requirements))
        
        # Copy up our requirements.
        r.env.pip_remote_requirements_fn = '/tmp/pip-requirements.txt'
        r.put(
            local_path=tmp_fn,
            remote_path=r.env.pip_remote_requirements_fn,
        )
        
        # Ensure we're always using the latest pip.
        if self.is_local:
            r.run('{virtualenv_dir}/bin/pip install -U pip')
        else:
            r.sudo('{virtualenv_dir}/bin/pip install -U pip')
        
        cmd = "{virtualenv_dir}/bin/pip install -r {pip_remote_requirements_fn}"
        if self.is_local:
            r.run(cmd)
        else:
            r.sudo(cmd)
            
        if not self.is_local and r.env.check_permissions:
            self.set_permissions()

    @task
    def record_manifest(self):
        """
        Called after a deployment to record any data necessary to detect changes
        for a future deployment.
        """
        manifest = super(PIPSatchel, self).record_manifest()
        manifest['all-requirements'] = self.get_combined_requirements()
        if self.verbose:
            pprint(manifest, indent=4)
        return manifest
    
    @task(precursors=['packager', 'user'])
    def configure(self, *args, **kwargs):
        
        # Necessary to make warning message go away.
        # http://stackoverflow.com/q/27870003/247542
        self.genv['sudo_prefix'] += '-H '
        
        self.update_install(*args, **kwargs)
        
pip = PIPSatchel()
