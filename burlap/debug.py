
from fabric.api import (
    env,
    local,
    put as _put,
    require,
    #run as _run,
    run,
    settings,
    sudo,
    cd,
    task,
)

@task
def list_env():
    for k,v in env.iteritems():
        print k,v
        