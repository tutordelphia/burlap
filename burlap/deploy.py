from __future__ import print_function

import sys
from pprint import pprint
from functools import partial
from StringIO import StringIO

import yaml

from fabric.api import execute, get

from burlap import ContainerSatchel
from burlap.constants import *
from burlap.decorators import task
from burlap.common import manifest_recorder, success_str, manifest_deployers_befores, topological_sort, resolve_deployer, \
    manifest_deployers_takes_diff, manifest_deployers
from burlap import exceptions

def iter_dict_differences(a, b):
    """
    Returns a generator yielding all the keys that have values that differ between each dictionary.
    """
    common_keys = set(a).union(b)
    for k in common_keys:
        a_value = a.get(k)
        b_value = b.get(k)
        if a_value != b_value:
            yield k, (a_value, b_value)

def str_to_list(s):
    """
    Converts a string of comma delimited values and returns a list.
    """
    return [_.strip().lower() for _ in (s or '').split(',') if _.strip()]

def get_component_order(component_names):
    """
    Given a list of components, re-orders them according to inter-component dependencies so the most depended upon are first.
    """
    assert isinstance(component_names, (tuple, list))
    component_dependences = {}
    for _name in component_names:
        deps = set(manifest_deployers_befores.get(_name, []))
        deps = deps.intersection(component_names)
        component_dependences[_name] = deps
    component_order = list(topological_sort(component_dependences.items()))
    return component_order

def get_deploy_funcs(components, current_thumbprint, previous_thumbprint, preview=False):
    """
    Returns a generator yielding the named functions needed for a deployment.
    """
    for component in components:
        funcs = manifest_deployers.get(component, [])
        for func_name in funcs:

            #TODO:remove this after burlap.* naming prefix bug fixed
            if func_name.startswith('burlap.'):
                print('skipping %s' % func_name)
                continue

            takes_diff = manifest_deployers_takes_diff.get(func_name, False)

            #if preview:
                #yield func_name, None
            #else:
            func = resolve_deployer(func_name)
            #last, current = component_thumbprints[component]
            current = current_thumbprint.get(component)
            last = previous_thumbprint.get(component)
            if takes_diff:
                yield func_name, partial(func, last=last, current=current)
            else:
                yield func_name, partial(func)

class DeploySatchel(ContainerSatchel):

    name = 'deploy'

    def set_defaults(self):
        self.env.lockfile_path = '/var/lock/burlap_deploy.lock'
        self.env.data_dir = '/var/local/burlap/deploy'
        self._plan_funcs = None

    @task
    def init(self):
        """
        Initializes the configuration files on the remote server.
        """
        r = self.local_renderer
        r.sudo('mkdir -p {data_dir}; chown {user}:{user} {data_dir}')

    @task
    def purge(self):
        """
        The opposite of init(). Completely removes any manifest records from the remote host.
        """
        r = self.local_renderer
        r.sudo('[ -d {data_dir} ] && rm -Rf {data_dir} || true')

    @property
    def manifest_filename(self):
        """
        Returns the path to the manifest file.
        """
        r = self.local_renderer
        tp_fn = r.format(r.env.data_dir + '/manifest.yaml')
        return tp_fn

    def get_current_thumbprint(self, components=None):
        """
        Returns a dictionary representing the current configuration state.

        Thumbprint is of the form:

            {
                component_name1: {key: value},
                component_name2: {key: value},
                ...
            }

        """
        components = str_to_list(components)
        manifest_data = {} # {component:data}
        for component_name, func in sorted(manifest_recorder.iteritems()):
            component_name = component_name.upper()
            component_name_lower = component_name.lower()
            if component_name_lower not in self.genv.services:
                self.vprint('Skipping unused component:', component_name)
                continue
            elif components and component_name_lower not in components:
                continue
            try:
                self.vprint('Retrieving manifest for %s...' % component_name)
                manifest_data[component_name] = func()
            except exceptions.AbortDeployment as e:
                raise
            #except Exception as e:
                #print('Error getting current thumbnail:', file=sys.stderr)
                #traceback.print_exc()
        return manifest_data

    def get_previous_thumbprint(self, components=None):
        """
        Returns a dictionary representing the previous configuration state.

        Thumbprint is of the form:

            {
                component_name1: {key: value},
                component_name2: {key: value},
                ...
            }

        """
        components = str_to_list(components)
        tp_fn = self.manifest_filename
        tp_text = None
        if self.file_exists(tp_fn):
            fd = StringIO()
            get(tp_fn, fd)
            tp_text = fd.getvalue()
            manifest_data = {}
            raw_data = yaml.load(tp_text)
            for k, v in raw_data.items():
                if components and k not in components:
                    continue
                manifest_data[k] = v
            return manifest_data

    @task
    def lock(self):
        """
        Marks the remote server as currently being deployed to.
        """
        r = self.local_renderer
        if self.file_exists(r.env.lockfile_path):
            raise exceptions.AbortDeployment('Lock file %s exists. Perhaps another deployment is currently underway?' % r.env.lockfile_path)
        else:
            r.sudo('touch {lockfile_path}')

    @task
    def unlock(self):
        """
        Unmarks the remote server as currently being deployed to.
        """
        r = self.local_renderer
        if self.file_exists(r.env.lockfile_path):
            r.sudo('rm -f {lockfile_path}')

    @task
    def fake(self):
        """
        Update the thumbprint on the remote server but execute no satchel configurators.
        """
        self.init()
        tp = self.get_current_thumbprint()
        tp_text = yaml.dump(tp)
        r = self.local_renderer
        r.upload_content(content=tp_text, fn=self.manifest_filename)
        r.sudo('chown {user}:{user} "%s"' % self.manifest_filename)

    def get_component_funcs(self, components=None):
        """
        Calculates the components functions that need to be executed for a deployment.
        """

        current_tp = self.get_current_thumbprint(components=components) or {}
        previous_tp = self.get_previous_thumbprint(components=components) or {}

        if self.verbose:
            print('Current thumbprint:')
            pprint(current_tp, indent=4)
            print('Previous thumbprint:')
            pprint(previous_tp, indent=4)

        differences = list(iter_dict_differences(current_tp, previous_tp))
        component_order = get_component_order([k for k, (_, _) in differences])
        plan_funcs = list(get_deploy_funcs(component_order, current_tp, previous_tp))

        return component_order, plan_funcs

    @task
    def preview(self, components=None, ask=0):
        """
        Inspects differences between the last deployment and the current code state.
        """

        ask = int(ask)

        self.init()

        component_order, plan_funcs = self.get_component_funcs(components=components)

        print('\n%i changes found for host %s.\n' % (len(component_order), self.genv.host_string))
        if component_order and plan_funcs:
            if self.verbose:
                print('These components have changed:\n')
                for component in sorted(component_order):
                    print((' '*4)+component)
            print('Deployment plan for host %s:\n' % self.genv.host_string)
            for func_name, _ in plan_funcs:
                print(success_str((' '*4)+func_name))
        if component_order:
            print()

        if component_order and ask and self.genv.host_string == self.genv.hosts[-1] \
        and not raw_input('Begin deployment? [yn] ').strip().lower().startswith('y'):
            sys.exit(1)

    @task
    def run(self, components=None, yes=0):
        """
        Executes all satchel configurators to apply pending changes to the server.
        """
        from burlap import notifier
        service = self.get_satchel('service')
        self.lock()
        try:

            yes = int(yes)

            if not yes:
                execute(partial(self.preview, components=components, ask=1))

            component_order, plan_funcs = self.get_component_funcs(components=components)

            service.pre_deploy()
            for func_name, plan_func in plan_funcs:
                print('Executing %s...' % func_name)
                plan_func()
            self.fake()
            service.post_deploy()
            notifier.notify_post_deployment()

        finally:
            self.unlock()

deploy = DeploySatchel()
