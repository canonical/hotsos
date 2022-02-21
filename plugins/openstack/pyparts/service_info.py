from core.plugins.openstack import (
    NeutronHAInfo,
    OpenstackChecksBase,
    OpenstackServiceChecksBase,
    OpenstackPackageChecksBase,
    OpenstackDockerImageChecksBase,
)

YAML_PRIORITY = 0


class OpenstackInfo(OpenstackServiceChecksBase):

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            self._output['services'] = {'systemd': self.service_info,
                                        'ps': self.process_info}

    def get_debug_log_info(self):
        """Return dictionary of OpenStack services and the value of the debug
        setting in their configuration.
        """
        debug_enabled = {}
        for name, info in self.ost_projects.all.items():
            cfg = info.config.get('main')
            if cfg and cfg.exists:
                debug_enabled[name] = cfg.get("debug", section="DEFAULT")

        if debug_enabled:
            self._output["debug-logging-enabled"] = debug_enabled

    def __call__(self):
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        self._output["release"] = self.release_name
        self.get_running_services_info()
        self.get_debug_log_info()


class OpenstackPackageChecks(OpenstackPackageChecksBase):

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.apt_check.core:
            self._output["dpkg"] = self.apt_check.all_formatted


class OpenstackDockerImageChecks(OpenstackDockerImageChecksBase):

    def __call__(self):
        # require at least one core image to be in-use to include
        # this in the report.
        if self.core:
            self._output["docker-images"] = self.all_formatted


class NeutronL3HAInfo(OpenstackChecksBase):

    def get_ha_router_states(self):
        routers = {}
        ha_info = NeutronHAInfo()
        for router in ha_info.ha_routers:
            state = router.ha_state
            if state in routers:
                routers[state].append(router.uuid)
            else:
                routers[state] = [router.uuid]

        if routers:
            self._output['neutron-l3ha'] = routers

    def __call__(self):
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        self.get_ha_router_states()
