"""
GIT component.

Merely a stub to document which packages should be installed
if a system uses this component.

It should be otherwise maintenance-free.
"""

from fabric.api import (
    env,
    local as _local
)

from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    render_to_string,
    QueuedCommand,
)
from burlap import common
from burlap.decorators import task_or_dryrun

# Installs git on host.
GIT = 'GIT'

# Tracks git versions deployed remotely.
GITTRACKER = 'GITTRACKER'

common.required_system_packages[GIT] = {
    common.FEDORA: ['git'],
    (common.UBUNTU, '12.04'): ['git'],
    (common.UBUNTU, '14.04'): ['git'],
}

@task_or_dryrun
def get_current_commit():
    """
    Retrieves the git commit number of the current head branch.
    """
    verbose = common.get_verbose()
    s = str(_local('git rev-parse HEAD', capture=True))
    if verbose:
        print 'current commit:', s
    return s

@task_or_dryrun
def get_logs_between_commits(a, b):
    """
    Retrieves all commit messages for all commits between the given commit numbers
    on the current branch.
    """
    verbose = common.get_verbose()
    ret = _local('git log --pretty=oneline %s...%s' % (a, b), capture=True)
    if verbose:
        print ret
    return str(ret)

@task_or_dryrun
def record_manifest_git_tracker(verbose=0):
    """
    Called after a deployment to record any data necessary to detect changes
    for a future deployment.
    """
    data = {
        'current_commit': get_current_commit(),
    }
    return data

common.manifest_recorder[GITTRACKER] = record_manifest_git_tracker

common.add_deployer(GITTRACKER, 'jirahelp.update_tickets_from_git',
    before=['packager', 'pip', 'tarball', 'django_media', 'django_migrations'],
    takes_diff=True)
    