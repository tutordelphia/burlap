"""
GVM
===========

This module provides tools for installing `GVM`_ : the Groovy enVironment Manager

.. _GVM: http://gvmtool.net/

"""
from __future__ import print_function

from fabric.api import run
from fabric.contrib.files import sed

from burlap.system import UnsupportedFamily, distrib_family

from burlap.require.deb import packages as require_deb_packages
from burlap.require.oracle_jdk import installed as java
from burlap.require.pkg import packages as require_pkg_packages
from burlap.require.rpm import packages as require_rpm_packages


def install(java_version=None):
    """
    Install dependencies (curl and unzip) and Install GVM

    ::

        import burlap

        # Install GVM
        burlap.gvm.install()

    """
    res = run('gvm help', quiet=True)
    if res.failed:
        family = distrib_family()
        packages = ['curl', 'unzip']
        if family == 'debian':
            require_deb_packages(packages)
        elif family == 'redhat':
            require_rpm_packages(packages)
        elif family == 'sun':
            require_pkg_packages(packages)
        else:
            raise UnsupportedFamily(supported=['debian', 'redhat', 'sun'])

        if java_version is None:
            java()
        else:
            java(version=java_version)

        run('curl -s get.gvmtool.net | bash')
        user = run('whoami')
        run('source "/home/%s/.gvm/bin/gvm-init.sh"' % user)
        configFile = "/home/%s/.gvm/etc/config" % user
        sed(configFile, 'gvm_auto_answer=false', 'gvm_auto_answer=true')


def install_candidate(candidate, version=None, java_version=None):
    """
    Install a candidate

    ::

        import burlap

        # Install a GVM candidate (For example Groovy)
        burlap.gvm.install_candidate('groovy')

    """
    install(java_version)

    if version is None:
        cmd = 'gvm install %s' % candidate
    else:
        cmd = 'gvm install %s %s' % (candidate, version)

    run(cmd)
