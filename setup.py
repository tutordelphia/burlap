 
from setuptools import setup, find_packages, Command

import os

os.environ['BURLAP_NO_LOAD'] = '1'

import burlap

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
        'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],
    install_requires = [
        'Fabric>=1.9.0',
        'PyYAML>=3.11',
        'feedparser>=5.1.3',
    ],
)
