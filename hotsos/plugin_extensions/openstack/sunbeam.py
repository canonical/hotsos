from hotsos.core.plugins.openstack.common import OpenstackBase, OpenStackChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)
from hotsos.core.host_helpers import cli


class SunbeamStatus(OpenstackBase, OpenStackChecks):
    """ Get information from Sunbeam to display. """
    summary_part_index = 14

    @summary_entry('sunbeam', get_min_available_entry_index() + 10)
    @staticmethod
    def summary_sunbeam():
        status = {}
        _cli = cli.CLIHelper()
        _cli.kubectl_get(namespace='metallb-system', opt='l2advertisement')
        _cli.kubectl_get(namespace='openstack', opt='pods')
        _cli.kubectl_get(namespace='openstack', opt='statefulset')
        return status or None
