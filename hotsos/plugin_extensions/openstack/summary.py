from hotsos.core.plugins.openstack.common import OpenstackBase, OpenStackChecks
from hotsos.core.plugins.openstack.neutron import NeutronHAInfo
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class OpenStackSummary(OpenstackBase, OpenStackChecks):
    """ Implementation of OpenStack summary. """
    summary_part_index = 0

    # REMINDER: Common entries are implemented in
    #           plugintools.ApplicationSummaryBase. Only customisations are
    #           implemented here. See
    #           plugintools.get_min_available_entry_index() for an explanation
    #           on how entry indices are managed.

    @staticmethod
    @summary_entry('neutron-l3ha', get_min_available_entry_index())
    def summary_neutron_l3ha():
        routers = {}
        ha_info = NeutronHAInfo()
        for router in ha_info.ha_routers:
            state = router.ha_state
            if state in routers:
                routers[state] += 1
            else:
                routers[state] = 1

        return routers or None
