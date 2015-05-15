 
from setuptools import setup, find_packages, Command

import os

os.environ['BURLAP_NO_LOAD'] = '1'

import burlap

def get_reqs(test=0):
    # optparse is included with Python <= 2.7, but has been deprecated in favor
    # of argparse.  We try to import argparse and if we can't, then we'll add
    # it to the requirements
    reqs = [
        'Fabric>=1.8.2',
        'PyYAML>=3.11',
        'feedparser>=5.1.3',
        'pytz>=2014.4',
        'python-dateutil>=2.2',
        'lockfile>=0.9.1',
        'requirements-parser>=0.1.0',
    ]
    try:
        import argparse
    except ImportError:
        reqs.append('argparse>=1.1')
        
    if test:
        reqs.append('python-vagrant>=0.5.0')
        
    return reqs

class TestCommand(Command):
    description = "Runs unittests."
    user_options = [
        ('name=', None,
         'Name of the specific test to run.'),
        ('virtual-env-dir=', None,
         'The location of the virtual environment to use.'),
        ('pv=', None,
         'The version of Python to use. e.g. 2.7 or 3'),
    ]
    
    def initialize_options(self):
        self.name = None
        self.virtual_env_dir = './.env%s'
        self.pv = 0
        self.iso_dir = '~/downloads'
        self.iso = 'ubuntu-14.04.1-server-amd64.iso'
        self.iso_path = ''
        self.versions = [2.7]#, 3]
        
    def finalize_options(self):
        self.iso_dir = os.path.expanduser(self.iso_dir)
        
        self.iso_path = os.path.join(self.iso_dir, self.iso)
        if not os.path.isfile(self.iso_path):
            raise Exception, ('ISO %s not found. Download from '\
                'http://www.ubuntu.com/download/server?') % self.iso_path
        
        ret = os.system('which vagrant')
        if ret:
            raise Exception, 'Vagrant not installed. '\
                'Run `sudo apt-get install vagrant`?'
    
    def build_virtualenv(self, pv):
        #TODO:check for/install vagrant? `sudo apt-get install vagrant`?
        virtual_env_dir = self.virtual_env_dir % pv
        kwargs = dict(virtual_env_dir=virtual_env_dir, pv=pv)
        if not os.path.isdir(virtual_env_dir):
            cmd = ('virtualenv -p /usr/bin/python{pv} '\
                '{virtual_env_dir}').format(**kwargs)
            #print(cmd)
            os.system(cmd)
            
            cmd = ('. {virtual_env_dir}/bin/activate; easy_install '\
                '-U distribute; deactivate').format(**kwargs)
            os.system(cmd)
            
            for package in get_reqs(test=1):
                kwargs['package'] = package
                cmd = ('. {virtual_env_dir}/bin/activate; pip install '\
                    '-U {package}; deactivate').format(**kwargs)
                #print(cmd)
                os.system(cmd)
    
    def run(self):
        versions = self.versions
        if self.pv:
            versions = [self.pv]
        
        for pv in versions:
            
            self.build_virtualenv(pv)
            kwargs = dict(pv=pv, name=self.name)
                
            if self.name:
                cmd = ('. ./.env{pv}/bin/activate; '\
                    'python burlap/tests/tests.py Tests.{name}; '\
                    'deactivate').format(**kwargs)
            else:
                cmd = ('. ./.env{pv}/bin/activate; '\
                    'python burlap/tests/tests.py; '\
                    'deactivate').format(**kwargs)
                
            print(cmd)
            ret = os.system(cmd)
            if ret:
                return
                
setup(
    name = "burlap",
    version = burlap.__version__,
    packages = find_packages(),
    scripts = ['bin/burlap'],
    package_data = {
        'burlap': [
            'templates/*.*',
        ],
    },
    author = "Chris Spencer",
    author_email = "chrisspen@gmail.com",
    description = "Fabric commands for simplifying server deployments",
    license = "LGPL",
    url = "https://github.com/chrisspen/burlap",
    #https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Lesser General Public License v3 '\
            '(LGPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        #'Programming Language :: Python :: 3.0',#TODO
    ],
    zip_safe = False,
    install_requires = get_reqs(),
    cmdclass={
        'test': TestCommand,
    },
)
