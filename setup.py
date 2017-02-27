from __future__ import print_function

import os
import sys
 
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand

os.environ['BURLAP_NO_LOAD'] = '1'

import burlap # pylint: disable=wrong-import-position

try:
    from pypandoc import convert
    read_md = lambda f: convert(f, 'rst')
except ImportError:
    print('warning: pypandoc module not found, could not convert Markdown to RST')
    read_md = lambda f: open(f, 'r').read()

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))

def read(filename):
    path = os.path.join(os.path.dirname(__file__), filename)
    with open(path, 'rb') as fin:
        text = fin.read().decode('utf-8')
    #data.decode("utf8", "ignore")
    return text
    
def get_reqs(fn):
    return [
        _.strip()
        for _ in open(os.path.join(CURRENT_DIR, fn)).readlines()
        if _.strip()
    ]

class Tox(TestCommand):

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import tox
        tox.cmdline(self.test_args)
        sys.exit(0)
        
setup(
    name="burlap",
    version=burlap.__version__,
    packages=find_packages(exclude=['ez_setup', 'tests']),
    scripts=['bin/burlap-admin.py'],
    package_data={
        'burlap': [
            'templates/*.*',
        ],
    },
    author="Chris Spencer",
    author_email="chrisspen@gmail.com",
    description="Fabric commands for simplifying server deployments",
    long_description=read_md('README.md'),
    license="MIT",
    url="https://github.com/chrisspen/burlap",
    #https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        #'Development Status :: 3 - Alpha',
        'Development Status :: 4 - Beta',
        #'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: Unix',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.0',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Software Development',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Software Distribution',
        'Topic :: System :: Systems Administration',
    ],
    zip_safe=False,
    include_package_data=True,
    install_requires=get_reqs('requirements.txt'),
    setup_requires=[],
    tests_require=get_reqs('requirements-test.txt'),
    cmdclass={
        'test': Tox,
    },
)
