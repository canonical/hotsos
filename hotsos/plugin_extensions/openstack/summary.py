from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.plugins.openstack.common import OpenstackChecksBase
from hotsos.core.plugins.openstack.neutron import NeutronHAInfo


class OpenstackSummary(OpenstackChecksBase):

    @idx(0)
    def __summary_release(self):
        return {'name': self.release_name,
                'days-to-eol': self.days_to_eol}

    @idx(1)
    def __summary_services(self):
        """Get string info for running services."""
        if self.systemd.services:
            return self.systemd.summary
        elif self.pebble.services:
            return self.pebble.summary

    @idx(2)
    def __summary_dpkg(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.apt.core:
            return self.apt.all_formatted

    @idx(3)
    def __summary_docker_images(self):
        # require at least one core image to be in-use to include
        # this in the report.
        if self.docker.core:
            return self.docker.all_formatted

    @idx(4)
    def __summary_neutron_l3ha(self):
        routers = {}
        ha_info = NeutronHAInfo()
        for router in ha_info.ha_routers:
            state = router.ha_state
            if state in routers:
                routers[state].append(router.uuid)
            else:
                routers[state] = [router.uuid]

        if routers:
            return routers
