from hotsos.core.plugins.openstack.common import OpenStackChecks
from hotsos.core.plugins.openstack.neutron import NeutronHAInfo
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class OpenStackSummary(OpenStackChecks):
    """ Implementation of OpenStack summary. """
    summary_part_index = 0

    # REMINDER: common entries are implemented in the SummaryBase base class
    #           and only application plugin specific customisations are
    #           implemented here. We use the get_min_available_entry_index() to
    #           ensure that additional entries don't clobber existing ones but
    #           conversely can also replace them by re-using their indices.

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
