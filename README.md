Burlap - configuration management designed for simplicity and speed
===================================================================

[![](https://img.shields.io/pypi/v/burlap.svg)](https://pypi.python.org/pypi/burlap) [![Build Status](https://img.shields.io/travis/chrisspen/burlap.svg?branch=master)](https://travis-ci.org/chrisspen/burlap) [![](https://pyup.io/repos/github/chrisspen/burlap/shield.svg)](https://pyup.io/repos/github/chrisspen/burlap)

Overview
--------

Burlap is a [configuration management](https://en.wikipedia.org/wiki/Comparison_of_open-source_configuration_management_software)
tool and framework for deploying software to servers.

It's written in Python and is built ontop of [Fabric](http://www.fabfile.org/) to run commands remotely over SSH.

Unlike [Chef](https://www.chef.io/) or [Ansible](http://www.ansible.com/) that target large "web-scale" platforms at the expense of great complexity, Burlap targets small to medium-scale platforms and keeps its configuration simple.

Much of the code is also heavily influenced by [Fabtools](https://github.com/fabtools/fabtools), another Fabric-based toolkit.

Installation
------------

Install the package via pip with:

    pip install burlap

Usage
-----

1. CD to a directory on your computer where you want to start your project and then run:

    burlap skel --name=<project name>

This will create a structure like:

    <project root>
    ├── roles
    |   ├── all
    |   |   ├── templates
    |   |   ├── settings.yaml
    |   |   ├── pip-requirements.txt
    |   |   └── <apt|yum>-requirements.txt
    |   |
    |   ├── dev
    |   |   ├── templates
    |   |   └── settings.yaml
    |   |
    |   └── prod
    |       ├── templates
    |       └── settings.yaml
    |
    ├── src
    |   ├── <project name>
    |   └── manage.py
    |
    └── fabfile.py

2. Now add the roles appropriate for your application. Common roles are development and production, e.g.

    burlap add role prod dev

2. Create your application code and test with Django's dev server.

3. Prepare remote host for deployment.

Allocate your production environment by setting up the physical server
or creating a VPS.

Populate your settings.yaml. At minimum it would have hosts, key_filename,
and user.

    hosts: [myserver.mydomain.com]
    user: sys-user
    key_filename: roles/prod/mydomain.pem

If you need to generate pub/pem files for passwordless SSH access, run:

    fab prod user.generate_keys
    
Ensure the filename of the *.pem file matches the key_filename in your
settings.yaml.

If you just created a fresh server and have password SSH access and need
to configure passwordless access, run:

    fab prod user.passwordless:username=<username>,pubkey=<path/to/yourdomain.pub>

Confirm you have passwordless access by running:

    fab prod shell

If you have an active shell prompt on the remote host and weren't prompted for
a password, you're ready to deploy.

4. Deploy your code.

    fab prod tarball.create tarball.deploy
    
5. Prepare your PIP cache.

List all your Python packages in pip-requirements.txt and then run:

    fab prod pip.update
    
This will download, but not install, all your packages into a local cache.
We do this to prevent network latency or timeouts from interferring with our
deployment. Few things are more frustrating then waiting for 50 packages to
install, only for the 50th to fail and torpedo our entire deployment.

Note, if you have multiple roles you're deploying to, you can update them all
in parallel by running this command for each role in separate terminals.
This can save quite a bit of time if you have many packages.

6. Install packages.

    fab prod pip.install
    
This will rsync all your cached packages up to the host, create a virtual
environment and install the packages.

7. Check for package updates.

Detecting updated packages is easy:

    fab prod pip.check_for_updates

example output:

    Checking requirement 83 of 83... 
    ===========================================================================
    The following packages have updated versions available:
    package,       installed_version, most_recent_version  
    Django,        1.5.5,             1.6.2                
    FeinCMS,       1.7.4,             1.9.3                
    billiard,      3.3.0.13,          3.3.0.16             
    celery,        3.1.1,             3.1.9                
    django-celery, 3.1.1,             3.1.9                
    kombu,         3.0.8,             3.0.12               
    reportlab,     2.2,               3.0                  
    ---------------------------------------------------------------------------
    7 packages have updates

Using this, you can review each package, determine which should be
updated in your pip-requirements.txt and installed via pip.install.

Development
-----------

To run tests:

    [tox](http://tox.readthedocs.org/en/latest/)
    
    tox -e py27 -- -s burlap/tests/test_project.py::test_project
