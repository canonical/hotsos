from hotsos.core.plugins.openstack.common import OpenstackBase, OpenStackChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)
from hotsos.core.host_helpers import CLIHelper


class SunbeamStatus(OpenstackBase, OpenStackChecks):
    """ Get information from Sunbeam to display. """
    summary_part_index = 14

    @staticmethod
    @summary_entry('sunbeam', get_min_available_entry_index() + 10)
    def summary_sunbeam():
        status = {}
        cli = CLIHelper()
        # status = cli.kubectl_get(namespace='metallb-system',
        #                          opt='l2advertisement')
        out = cli.kubectl_get(namespace='openstack', opt='pods')
        status['pods'] = {i['metadata']['name']: i['status']['phase']
                          for i in out['items']}
        out = cli.kubectl_get(namespace='openstack', opt='statefulsets')
        status['statefulsets'] = {i['metadata']['name']:
                                  i['status']['readyReplicas']
                                  for i in out['items']}
        return status or None
