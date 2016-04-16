"""
Groups
======
"""
from __future__ import print_function

from fabric.api import hide, run, settings

from burlap.utils import run_as_root


def exists(name):
    """
    Check if a group exists.
    """
    with settings(hide('running', 'stdout', 'warnings'), warn_only=True):
        return run('getent group %(name)s' % locals()).succeeded


def create(name, gid=None):
    """
    Create a new group.

    Example::

        import burlap

        if not burlap.group.exists('admin'):
            burlap.group.create('admin')

    """

    args = []
    if gid:
        args.append('-g %s' % gid)
    args.append(name)
    args = ' '.join(args)
    run_as_root('groupadd %s' % args)
