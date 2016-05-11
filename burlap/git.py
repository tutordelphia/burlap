"""
GIT component.

Merely a stub to document which packages should be installed
if a system uses this component.

It should be otherwise maintenance-free.
"""
from __future__ import print_function

import time

from burlap import Satchel
from burlap.constants import *
from burlap.exceptions import AbortDeployment

class GitCheckerSatchel(Satchel):
    """
    Ensures the appropriate Git branch is being deployed.
    """
    
    name = 'gitchecker'
    
    tasks = (
        'configure',
        'check',
    )
    
    required_system_packages = {
        (UBUNTU, '12.04'): ['git'],
        (UBUNTU, '14.04'): ['git'],
    }
    
    def set_defaults(self):
        self.env.branch = 'master'
    
    def check(self):
        print('Checking GIT branch...')
        branch_name = self._local('git rev-parse --abbrev-ref HEAD', capture=True).strip()
        if not self.env.branch == branch_name:
            raise AbortDeployment(
                'Expected branch "%s" but see branch "%s".' % (self.env.branch, branch_name))
    
    def record_manifest(self):
        self.check()
        return super(GitCheckerSatchel, self).record_manifest()
        
    def configure(self):
        pass
    

class GitTrackerSatchel(Satchel):
    """
    Tracks changes between Git commits.
    """
    
    name = 'gittracker'
    
    tasks = (
        'configure',
    )
    
    required_system_packages = {
        (UBUNTU, '12.04'): ['git'],
        (UBUNTU, '14.04'): ['git'],
    }
    
    def set_defaults(self):
        pass
        
    def get_logs_between_commits(self, a, b):
        """
        Retrieves all commit messages for all commits between the given commit numbers
        on the current branch.
        """
        ret = self.local('git log --pretty=oneline %s...%s' % (a, b), capture=True)
        if self.verbose:
            print(ret)
        return str(ret)

    def get_current_commit(self):
        """
        Retrieves the git commit number of the current head branch.
        """
        s = str(self.local('git rev-parse HEAD', capture=True))
        if self.verbose:
            print('current commit:', s)
        return s
    
    def record_manifest(self):
        """
        Called after a deployment to record any data necessary to detect changes
        for a future deployment.
        """
        data = {
            'current_commit': self.get_current_commit(),
        }
        return data
    
    def configure(self):
        from burlap.jirahelp import update_tickets_from_git
        update_tickets_from_git()
    
    configure.deploy_before = ['packager', 'pip', 'tarball', 'djangomedia', 'djangomigrations']

gitchecker = GitCheckerSatchel()
gittracker = GitTrackerSatchel()
