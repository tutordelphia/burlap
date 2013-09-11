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
def visitors():
    run('visitors -o text /var/log/apache2/%(apache_application_name)s-access.log* | less' % env)
