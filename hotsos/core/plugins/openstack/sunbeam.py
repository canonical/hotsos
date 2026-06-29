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

    @staticmethod
    def _kubectl_get(opt):
        """ Run kubectl get for the given resource and return its items.

        On a controller ~/.kube/config is expected to exist so if kubectl
        fails (e.g. missing/invalid config) the output will be empty. We catch
        that here and warn rather than silently returning nothing so that the
        reason is not hidden from the user.

        @param opt: resource to query e.g. 'pods' or 'statefulsets'.
        @return: list of items (possibly empty).
        """
        out = CLIHelper().kubectl_get(namespace='openstack', opt=opt,
                                      subopts='')
        if not out or 'items' not in out:
            log.warning("no sunbeam %s found - kubectl returned no data "
                        "(does ~/.kube/config exist?)", opt)
            return []

        return out['items']

    @cached_property
    def pods(self):
        """ Return dictionary of pods keyed by their status e.g. Running. """
        if not self.is_controller:
            return {}

        items = self._kubectl_get('pods')
        if not items:
            return {}

        pods = defaultdict(list)
        for pod in items:
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

        items = self._kubectl_get('statefulsets')
        if not items:
            return {}

        ss = {'complete': [], 'incomplete': []}
        metadata_fails = 0
        for i in items:
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
