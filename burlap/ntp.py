from burlap import common

NTPCLIENT = 'NTPCLIENT'

common.required_system_packages[NTPCLIENT] = {
    common.FEDORA: ['ntpdate','ntp'],
    common.UBUNTU: ['ntpdate','ntp'],
}
