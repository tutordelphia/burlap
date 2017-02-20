"""
Fabric command script for project buildbot.

For most deployments, you'll want to do:

    fab prod deploy.run
    
"""
import sys

sys.path.insert(0, '..')

# import burlap
# from burlap.common import (
#     env,
#     run_or_dryrun,
#     put_or_dryrun,
#     sudo_or_dryrun,
#     local_or_dryrun,
# )
from burlap.decorators import task_or_dryrun
 
@task_or_dryrun
def custom_task():
    #run_or_dryrun('echo "$(date)"')
    pass
