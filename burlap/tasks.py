
from fabric.tasks import WrappedCallableTask as _WrappedCallableTask

from burlap.common import get_dryrun, set_dryrun

class WrappedCallableTask(_WrappedCallableTask):
    """
    A modified version of Fabric's WrappedCallableTask that sets a global
    dryrun variable from a task call.
    
    The variable is then removed from the function call, allowing all wrapped
    function calls to implicitly use the keyword argument.
    """

    def __call__(self, *args, **kwargs):
        if 'dryrun' in kwargs:
            set_dryrun(kwargs['dryrun'])
            del kwargs['dryrun']
        return self.run(*args, **kwargs)

    def run(self, *args, **kwargs):
        if 'dryrun' in kwargs:
            set_dryrun(kwargs['dryrun'])
            del kwargs['dryrun']
        return self.wrapped(*args, **kwargs)
        