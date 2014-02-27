 
from setuptools import setup, find_packages, Command

import os

setup(
    name = "burlap",
    version = '0.1.2',
    packages = find_packages(),
    scripts = ['bin/burlap'],
    package_data = {
        'burlap': [
            'templates/*.*',
        ],
    },
    author = "Chris Spencer",
    author_email = "chrisspen@gmail.com",
    description = "Fabric commands for simplifying Django deployment",
    license = "LGPL",
    url = "https://github.com/chrisspen/burlap",
    #https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: LGPL License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ],
    install_requires = ['fabric', 'pyyaml'],
)
