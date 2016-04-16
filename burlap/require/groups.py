"""
System groups
=============
"""
from burlap.group import create, exists


def group(name, gid=None):
    """
    Require a group.

    ::

        from burlap import require

        require.group('mygroup')

    .. note:: This function can be accessed directly from the
              ``burlap.require`` module for convenience.

    """

    # Make sure the group exists
    if not exists(name):
        create(name, gid=gid)
