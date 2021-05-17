#!/usr/bin/python3
import re
import os

from common import (
    constants,
    cli_helpers,
    plugin_yaml,
)
from openstack_common import (
    OST_PROJECTS,
    OST_SERVICES_DEPS,
    OST_SERVICES_EXPRS,
    OpenstackServiceChecksBase,
)

# configs that dont use standard /etc/<project>/<project>.conf
OST_ETC_OVERRIDES = {"glance": "glance-api.conf",
                     "swift": "proxy.conf"}

APT_SOURCE_PATH = os.path.join(constants.DATA_ROOT, "etc/apt/sources.list.d")
OPENSTACK_INFO = {}


class OpenstackServiceChecks(OpenstackServiceChecksBase):
    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            OPENSTACK_INFO["services"] = self.get_service_info_str()

    def get_release_info(self):
        if not os.path.exists(APT_SOURCE_PATH):
            return

        release_info = {}
        for source in os.listdir(APT_SOURCE_PATH):
            apt_path = os.path.join(APT_SOURCE_PATH, source)
            for line in cli_helpers.safe_readlines(apt_path):
                rexpr = r"deb .+ubuntu-cloud.+ [a-z]+-([a-z]+)/([a-z]+) .+"
                ret = re.compile(rexpr).match(line)
                if ret:
                    if "uca" not in release_info:
                        release_info["uca"] = set()

                    if ret[1] != "updates":
                        release_info["uca"].add("{}-{}".format(ret[2], ret[1]))
                    else:
                        release_info["uca"].add(ret[2])

        if release_info:
            if release_info.get("uca"):
                OPENSTACK_INFO["release"] = sorted(release_info["uca"],
                                                   reverse=True)[0]
        else:
            OPENSTACK_INFO["release"] = "distro"

    def get_debug_log_info(self):
        debug_enabled = {}
        for proj in OST_PROJECTS:
            path = OST_ETC_OVERRIDES.get(proj)
            if path is None:
                path = os.path.join(constants.DATA_ROOT,
                                    "etc", proj, "{}.conf".format(proj))

            if os.path.exists(path):
                for line in cli_helpers.safe_readlines(path):
                    ret = re.compile(r"^debug\s*=\s*([A-Za-z]+).*").match(line)
                    if ret:
                        debug_enabled[proj] = cli_helpers.bool_str(ret[1])

        if debug_enabled:
            OPENSTACK_INFO["debug-logging-enabled"] = debug_enabled

    def __call__(self):
        super().__call__()
        self.get_release_info()
        self.get_running_services_info()
        self.get_debug_log_info()


def get_openstack_service_checker():
    # Do this way to make it easier to write unit tests.
    OPENSTACK_SERVICES_EXPRS = OST_SERVICES_EXPRS + OST_SERVICES_DEPS
    return OpenstackServiceChecks(OPENSTACK_SERVICES_EXPRS, hint_range=(0, 3))


if __name__ == "__main__":
    get_openstack_service_checker()()
    if OPENSTACK_INFO:
        plugin_yaml.save_part(OPENSTACK_INFO, priority=0)
