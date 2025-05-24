""" OpenStack Sunbeam helper code. """
from collections import defaultdict
from functools import cached_property

from hotsos.core.host_helpers import CLIHelper, SnapPackageHelper


class SunbeamInfo():
    """ OpenStack Sunbeam helpers. """

    @cached_property
    def is_controller(self):
        return 'openstack' in SnapPackageHelper(core_snaps=['openstack']).core

    @cached_property
    def pods(self):
        """ Return dictionary of pods keyed by their status e.g. Running. """
        if not self.is_controller:
            return {}

        cli = CLIHelper()
        out = cli.kubectl_get(namespace='openstack', opt='pods')
        pods = defaultdict(list)
        for pod in out['items']:
            phase = pod['status']['phase']
            pods[phase].append(pod['metadata']['name'])

        # must be type dict for pyyaml
        return dict(pods)

    @cached_property
    def statefulsets(self):
        """ Return dictionary of statefulsets grouped under either 'complete'
        or 'incomplete' depending on whether all members are ready.
        """
        if not self.is_controller:
            return {}

        cli = CLIHelper()
        out = cli.kubectl_get(namespace='openstack', opt='statefulsets')
        ss = {'complete': [], 'incomplete': []}
        for i in out['items']:
            name = i['metadata']['name']
            if i['status']['replicas'] / i['status']['readyReplicas']:
                ss['complete'].append(name)
            else:
                ss['incomplete'].append(name)

        # must be type dict for pyyaml
        return dict(ss)
