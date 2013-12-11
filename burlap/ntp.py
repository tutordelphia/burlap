"""
NTP component.

Merely a stub to document which packages should be installed
if a system uses this component.

It should be otherwise maintenance-free.
"""
from burlap import common

NTPCLIENT = 'NTPCLIENT'

common.required_system_packages[NTPCLIENT] = {
    common.FEDORA: ['ntpdate','ntp'],
    common.UBUNTU: ['ntpdate','ntp'],
}
