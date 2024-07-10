from hotsos.core.plugins.openstack.common import OpenStackChecks
from hotsos.core.plugins.openstack.neutron import NeutronHAInfo


class OpenStackSummary(OpenStackChecks):
    """ Implementation of OpenStack summary. """
    summary_part_index = 0

    def __0_summary_release(self):
        return {'name': self.release_name,
                'days-to-eol': self.days_to_eol}

    def __1_summary_services(self):
        """Get string info for running services."""
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

        return None

    def __2_summary_dpkg(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.apt.core:
            return self.apt.all_formatted

        return None

    def __3_summary_docker_images(self):
        # require at least one core image to be in-use to include
        # this in the report.
        if self.docker.core:
            return self.docker.all_formatted

        return None

    @staticmethod
    def __4_summary_neutron_l3ha():
        routers = {}
        ha_info = NeutronHAInfo()
        for router in ha_info.ha_routers:
            state = router.ha_state
            if state in routers:
                routers[state] += 1
            else:
                routers[state] = 1

        return routers or None
