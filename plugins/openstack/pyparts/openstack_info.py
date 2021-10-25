import os

from core import constants
from core.plugins.openstack import (
    OST_PROJECTS,
    OST_SERVICES_DEPS,
    OST_SERVICES_EXPRS,
    OpenstackConfig,
    OpenstackServiceChecksBase,
)
from core.issues import (
    issue_types,
    issue_utils,
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
            self._output["services"] = self.service_info_str

    def get_masked_services(self):
        """Get a list of masked services."""
        if self.service_info_str['systemd']:
            masked = self.service_info_str['systemd'].get('masked', {})
            if 'keystone' in masked:
                del masked['keystone']
            if masked:
                msg = (f'Found masked services: {", ".join(masked)}. Please '
                       + "ensure that this is intended.")
                issue_utils.add_issue(issue_types.OpenstackWarning(msg))

    def get_debug_log_info(self):
        """Return dictionary of OpenStack services and the value of the debug
        setting in their configuration.
        """
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
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        self._output["release"] = self.release_name
        self.get_running_services_info()
        self.get_debug_log_info()
        self.get_masked_services()
