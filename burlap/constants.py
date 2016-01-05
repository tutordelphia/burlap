PACKAGERS = APT, YUM = ('apt-get', 'yum')

OS_TYPES = LINUX, WINDOWS = ('linux', 'windows')
OS_DISTRO = FEDORA, UBUNTU, DEBIAN, CENTOS = ('fedora', 'ubuntu', 'debian', 'centos')

SYSTEM = 'system'
RUBY = 'ruby'
PYTHON = 'python'
PACKAGE_TYPES = (
    SYSTEM,
    PYTHON, # pip
    RUBY, # gem
)

ALL = 'all' # denotes the global role

START = 'start'
STOP = 'stop'
STATUS = 'status'
RELOAD = 'reload'
RESTART = 'restart'
ENABLE = 'enable'
DISABLE = 'disable'
STATUS = 'status'
SERVICE_COMMANDS = (
    START,
    STOP,
    STATUS,
    RESTART,
    ENABLE,
    DISABLE,
    STATUS,
)

DJANGO = 'DJANGO'

SITE = 'SITE'
ROLE = 'ROLE'

LOCALHOSTS = ('localhost', '127.0.0.1')

UTF8 = 'UTF8'
