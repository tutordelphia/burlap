from __future__ import print_function
 
from setuptools import setup, find_packages, Command
from setuptools.command.test import test as TestCommand

import os

os.environ['BURLAP_NO_LOAD'] = '1'

import burlap

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))

def get_reqs(fn):
    return [
        _.strip()
        for _ in open(os.path.join(CURRENT_DIR, fn)).readlines()
        if _.strip()
    ]

# class BaseCommand(Command):
#     user_options = [
#         ('virtual-env-dir=', None,
#          'The location of the virtual environment to use.'),
#         ('pv=', None,
#          'The version of Python to use. e.g. 2.7 or 3'),
#     ]
#     
#     def finalize_options(self):
#         pass
#         
#     def initialize_options(self):
#         self.name = None
#         self.virtual_env_dir = './.env%s'
#         self.pv = 0
#         self.iso_dir = '~/downloads'
#         self.iso = 'ubuntu-14.04.1-server-amd64.iso'
#         self.iso_path = ''
#         self.versions = [2.7]#, 3]
#         
#     def build_virtualenv(self, pv):
#         #TODO:check for/install vagrant? `sudo apt-get install vagrant`?
#         print('build_virtualenv:', pv)
#         virtual_env_dir = self.virtual_env_dir % pv
#         kwargs = dict(virtual_env_dir=virtual_env_dir, pv=pv)
#         if os.path.isdir(virtual_env_dir):
#             print('%s exists' % virtual_env_dir)
#         else:
#             cmd = ('virtualenv -p /usr/bin/python{pv} '\
#                 '{virtual_env_dir}').format(**kwargs)
#             print(cmd)
#             os.system(cmd)
#             
#             cmd = ('. {virtual_env_dir}/bin/activate; easy_install '\
#                 '-U distribute; deactivate').format(**kwargs)
#             print(cmd)
#             os.system(cmd)
#             
#             for package in get_reqs(test=1):
#                 kwargs['package'] = package
#                 cmd = ('. {virtual_env_dir}/bin/activate; pip install '\
#                     '-U {package}; deactivate').format(**kwargs)
#                 #print(cmd)
#                 os.system(cmd)
#                 
# class SetupDevCommand(BaseCommand):
#     description = "Sets up the local dev environment."
#     
#     def run(self):
#         print('run')
#         versions = self.versions
#         if self.pv:
#             versions = [self.pv]
#         for pv in versions:
#             self.build_virtualenv(pv)
# 
# class CustomTestCommand(BaseCommand):
#     description = "Runs unittests."
#     user_options = [
#         ('name=', None,
#          'Name of the specific test to run.'),
#         ('virtual-env-dir=', None,
#          'The location of the virtual environment to use.'),
#         ('pv=', None,
#          'The version of Python to use. e.g. 2.7 or 3'),
#     ]
#     
#     def finalize_options(self):
#         self.init_iso()
#         
#     def init_iso(self):
#         self.iso_dir = os.path.expanduser(self.iso_dir)
#         
#         self.iso_path = os.path.join(self.iso_dir, self.iso)
#         if not os.path.isfile(self.iso_path):
#             raise Exception, ('ISO %s not found. Download from '\
#                 'http://www.ubuntu.com/download/server?') % self.iso_path
#         
#         ret = os.system('which vagrant')
#         if ret:
#             raise Exception, 'Vagrant not installed. '\
#                 'Run `sudo apt-get install vagrant`?'
#     
#     def run(self):
#         versions = self.versions
#         if self.pv:
#             versions = [self.pv]
#         
#         for pv in versions:
#             
#             self.build_virtualenv(pv)
#             kwargs = dict(pv=pv, name=self.name)
#                 
#             if self.name:
#                 cmd = ('. ./.env{pv}/bin/activate; '\
#                     'python burlap/tests/tests.py Tests.{name}; '\
#                     'deactivate').format(**kwargs)
#             else:
#                 cmd = ('. ./.env{pv}/bin/activate; '\
#                     'python burlap/tests/tests.py; '\
#                     'deactivate').format(**kwargs)
#                 
#             print(cmd)
#             ret = os.system(cmd)
#             if ret:
#                 return

class Tox(TestCommand):

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import tox
        errno = tox.cmdline(self.test_args)
        sys.exit(errno)
        
setup(
    name="burlap",
    version=burlap.__version__,
    packages=find_packages(exclude=['ez_setup', 'tests']),
    scripts=['bin/burlap'],
    package_data={
        'burlap': [
            'templates/*.*',
        ],
    },
    author="Chris Spencer",
    author_email="chrisspen@gmail.com",
    description="Fabric commands for simplifying server deployments",
    license="MIT",
    url="https://github.com/chrisspen/burlap",
    #https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        #'Development Status :: 3 - Alpha',
        'Development Status :: 4 - Beta',
        #'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        #'Programming Language :: Python :: 3.0',#TODO
    ],
    zip_safe=False,
    include_package_data=True,
    install_requires=get_reqs('pip-requirements.txt'),
    setup_requires=[],
    tests_require=get_reqs('pip-requirements-test.txt'),
    cmdclass={
#         'test': CustomTestCommand,
#         'dev': SetupDevCommand,
        'test': Tox,
    },
)
