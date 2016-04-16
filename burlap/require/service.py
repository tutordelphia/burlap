"""
System services
===============

This module provides high-level tools for managing system services.
The underlying operations use the ``service`` command, allowing to
support both `upstart`_ services and traditional SysV-style
``/etc/init.d/`` scripts.

.. _upstart: http://upstart.ubuntu.com/

"""

from burlap.service import is_running, restart, start, stop
from burlap.system import using_systemd
import burlap.systemd as systemd


def started(service):
    """
    Require a service to be started.

    ::

        from burlap import require

        require.service.started('foo')
    """
    if not is_running(service):
        if using_systemd():
            systemd.start(service)
        else:
            start(service)


def stopped(service):
    """
    Require a service to be stopped.

    ::

        from burlap import require

        require.service.stopped('foo')
    """
    if is_running(service):
        if using_systemd():
            systemd.stop(service)
        else:
            stop(service)


def restarted(service):
    """
    Require a service to be restarted.

    ::

        from burlap import require

        require.service.restarted('foo')
    """
    if is_running(service):
        if using_systemd():
            systemd.restart(service)
        else:
            restart(service)
    else:
        if using_systemd():
            systemd.start(service)
        else:
            start(service)


__all__ = ['started', 'stopped', 'restarted']
