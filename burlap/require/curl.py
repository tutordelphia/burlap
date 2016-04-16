"""
Curl
====

This module provides high-level tools for using curl.

"""
from burlap.system import UnsupportedFamily, distrib_family


def command():
    """
    Require the curl command-line tool.

    Example::

        from fabric.api import run
        from burlap import require

        require.curl.command()
        run('curl --help')

    """

    from burlap.require.deb import package as require_deb_package
    from burlap.require.rpm import package as require_rpm_package

    family = distrib_family()

    if family == 'debian':
        require_deb_package('curl')
    elif family == 'redhat':
        require_rpm_package('curl')
    else:
        raise UnsupportedFamily(supported=['debian', 'redhat'])
