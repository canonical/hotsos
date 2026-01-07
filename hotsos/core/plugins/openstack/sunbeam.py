""" OpenStack Sunbeam helper code. """
from collections import defaultdict
from functools import cached_property

from hotsos.core.host_helpers import CLIHelper, SnapPackageHelper
from hotsos.core.log import log


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
        out = cli.kubectl_get(namespace='openstack', opt='pods', subopts='')
        if 'items' not in out:
            log.info('no sunbeam pods found')
            return {}

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
        out = cli.kubectl_get(namespace='openstack', opt='statefulsets',
                              subopts='')

        ss = {'complete': [], 'incomplete': []}
        if 'items' not in out:
            log.info('no sunbeam statefulsets found')
            return {}

        metadata_fails = 0
        for i in out['items']:
            try:
                name = i['metadata']['name']
            except KeyError:
                metadata_fails += 1
                continue

            try:
                ready = i['status'].get('readyReplicas', 0)
                if ready and i['status']['replicas'] / ready:
                    ss['complete'].append(name)
                else:
                    ss['incomplete'].append(name)
            except KeyError:
                log.warning("failed to get replicaset '%s' status", name)

        if metadata_fails:
            log.warning("failed to get replicaset metadata for %s items",
                        metadata_fails)

        # must be type dict for pyyaml
        return dict(ss)
