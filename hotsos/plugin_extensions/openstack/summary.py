from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.plugins.openstack.openstack import OpenstackServiceChecksBase
from hotsos.core.plugins.openstack.neutron import NeutronHAInfo


class OpenstackSummary(OpenstackServiceChecksBase):

    @idx(0)
    def __summary_release(self):
        return self.release_name

    @idx(1)
    def __summary_services(self):
        """Get string info for running services."""
        if self.services:
            return {'systemd': self.service_info,
                    'ps': self.process_info}

    @idx(2)
    def __summary_dpkg(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.apt_check.core:
            return self.apt_check.all_formatted

    @idx(3)
    def __summary_docker_images(self):
        # require at least one core image to be in-use to include
        # this in the report.
        if self.docker_check.core:
            return self.docker_check.all_formatted

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
