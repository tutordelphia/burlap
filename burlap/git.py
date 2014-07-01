"""
GIT component.

Merely a stub to document which packages should be installed
if a system uses this component.

It should be otherwise maintenance-free.
"""
from burlap import common

GIT = 'GIT'

common.required_system_packages[GIT] = {
    common.FEDORA: ['git'],
    (common.UBUNTU, '12.04'): ['git'],
    (common.UBUNTU, '14.04'): ['git'],
}
