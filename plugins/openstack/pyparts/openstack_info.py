import os

from core import constants
from core.plugins.openstack import (
    OST_PROJECTS,
    OST_SERVICES_DEPS,
    OST_SERVICES_EXPRS,
    OpenstackConfig,
    OpenstackServiceChecksBase,
)

# configs that dont use standard /etc/<project>/<project>.conf
OST_ETC_OVERRIDES = {"glance": "glance-api.conf",
                     "swift": "proxy.conf"}

YAML_PRIORITY = 0


class OpenstackInfo(OpenstackServiceChecksBase):

    def __init__(self):
        service_exprs = OST_SERVICES_EXPRS + OST_SERVICES_DEPS
        super().__init__(service_exprs=service_exprs, hint_range=(0, 3))

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            self._output["services"] = self.get_service_info_str()

    def get_debug_log_info(self):
        debug_enabled = {}
        for proj in OST_PROJECTS:
            conf = OST_ETC_OVERRIDES.get(proj)
            if conf is None:
                conf = "{}.conf".format(proj)

            path = os.path.join(constants.DATA_ROOT, "etc", proj, conf)
            cfg = OpenstackConfig(path)
            if cfg.exists:
                debug_enabled[proj] = cfg.get("debug", section="DEFAULT")

        if debug_enabled:
            self._output["debug-logging-enabled"] = debug_enabled

    def __call__(self):
        self._output["release"] = self.release_name
        self.get_running_services_info()
        self.get_debug_log_info()
