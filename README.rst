=============================================================================
Burlap - Fabric commands for simplifying Django deployment
=============================================================================

Overview
--------

Implements several modules containing `Fabric
<http://www.fabfile.org>`_ commands for performing common
system administration tasks for Django web applications, such as:

- application code compression, upload, and installation
- Apache configuration
- database (PostgreSQL and MySQL) creation, schema migration, and custom SQL execution
- Python package caching, upload, and installation
- user creation
- configuration of multiple deployment roles (e.g. development, staging and production)

My general philosophy behind this project is if I have to manually SSH into a
server to modify configuration files, I'm probably doing something wrong.

To increase maintainability and reliability of production systems, all
configuration should be represented in a version-controlled system and be
deployed via automated methods.

To that end, I've created this project to organize the dozens of Fabric
commands I've written over the years to help deploy Django sites.

It's not comprehensive, and only covers the platforms I've personally used,
which is primarily an Apache web server with a PostgreSQL or Amazon RDS hosted
MySQL database backend.

Although many modules in this package can be used for non-Django applications,
it largely assumes a basic Django setup, and expects to find a Django settings
module containing database credentials and static media lists.

Installation
------------

::

    pip install burlap

Usage
-----

1. CD to a directory on your computer where you want to start your project and then run:

::

    burlap skel --name=<project name>

This will create a structure like...

2. Create your application code and test with Django's dev server.

3. Prepare remote host for deployment.

Allocate your production environment by setting up the physical server or creating a VPS.

Populate your settings.yaml. At minimum it would have hosts, key_filename, and user.

::

    hosts: [myserver.mydomain.com]
    user: sys-user
    key_filename: roles/prod/mydomain.pem

If you need to generate pub/pem files for passwordless SSH access, run:

::

    fab prod user.generate_keys
    
Ensure the filename of the *.pem file matches the key_filename in your settings.yaml.

If you just created a fresh server and have password SSH access and need to configure passwordless access, run:

::

    fab prod user.passwordless:username=<username>,pubkey=<path/to/yourdomain.pub>

Confirm you have passwordless access by running:

::

    fab prod shell

If you have an active shell prompt on the remote host and weren't prompted for a password, you're ready to deploy.

4. Deploy your code.

::

    fab prod tarball.create tarball.deploy
    
5. Prepare your PIP cache.

List all your Python packages in pip-requirements.txt and then run:

::

    fab prod pip.update
    
This will download, but not install, all your packages into a local cache. We do this to prevent network latency or timeouts from interferring with our deployment.
Note, if you have multiple roles you're deploying to, you can update them all in parallel by running this command for each role in separate terminals.
This can save quite a bit of time if you have many packages.

6. Install packages.

::

    fab prod pip.install
    
This will rsync all your cached packages up to the host, create a virtual environment and install the packages.
