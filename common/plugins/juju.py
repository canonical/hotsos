import os

import glob
import re
import yaml

from common import (
    constants,
    plugintools,
    utils,
)
from common.cli_helpers import CLIHelper

JUJU_LOG_PATH = os.path.join(constants.DATA_ROOT, "var/log/juju")
JUJU_LIB_PATH = os.path.join(constants.DATA_ROOT, "var/lib/juju")
CHARM_MANIFEST_GLOB = "agents/unit-*/state/deployer/manifests"


class JujuMachine(object):

    def __init__(self):
        self.cfg = {}

    @property
    def config(self):
        if not self.cfg:
            path = glob.glob(os.path.join(JUJU_LIB_PATH,
                                          "agents/machine-*/agent.conf"))
            if not path:
                return self.cfg

            # NOTE: we only expect one of these to exist
            path = path[0]
            # filter out 'sanitised' lines since they will not be valid yaml
            if os.path.exists(path):
                ftmp = utils.mktemp_dump("")
                with open(ftmp, 'w') as fdtmp:
                    expr = re.compile(r"\*\*\*\*\*\*\*\*\*")
                    with open(path) as fd:
                        for line in fd.readlines():
                            if not expr.search(line):
                                fdtmp.write(line)

                self.cfg = yaml.safe_load(open(ftmp))
                os.remove(ftmp)

        return self.cfg

    @property
    def agent_service_name(self):
        return self.config.get("values", {}).get("AGENT_SERVICE_NAME")

    @property
    def version(self):
        return self.config.get("upgradedToVersion", "unknown")

    @property
    def deployed_units(self):
        units = []
        # requires >= 2.9.x
        _units = self.config.get("values", {}).get("deployed-units", "")
        for unit in _units.split(','):
            units.append(unit.replace('/', '-'))

        return units


class JujuBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.machine = JujuMachine()

    def _get_app_from_unit_name(self, unit):
        ret = re.compile(r"([0-9a-z\-]+)-[0-9]+.*").match(unit)
        if ret:
            return ret[1]

    def _get_unit_version(self, unit):
        ret = re.compile(r"[0-9a-z\-]+-([0-9]+).*").match(unit)
        if ret:
            return int(ret[1])

    @property
    def ps_units(self):
        """ Units identified from running processes. """
        units = set()
        for line in CLIHelper().ps():
            if "unit-" in line:
                ret = re.compile(r".+unit-([0-9a-z\-]+-[0-9]+).*").match(line)
                if ret:
                    units.add(ret[1])

        return units

    @property
    def log_units(self):
        """ Units identified from extant logfiles. """
        units = set()
        for logfile in os.listdir(JUJU_LOG_PATH):
            ret = re.compile(r"unit-(.+)\.log$").match(logfile)
            if ret:
                units.add(ret[1])

        return units

    def _get_local_running_units(self):
        units = self.get_ps_units()
        return units.intersection(self.get_log_units())


class JujuChecksBase(JujuBase, plugintools.PluginPartBase):
    pass
