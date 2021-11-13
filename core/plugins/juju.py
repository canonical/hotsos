import os

import glob
import re
import yaml

from core import (
    constants,
    plugintools,
    utils,
)
from core.cli_helpers import CLIHelper

JUJU_LOG_PATH = os.path.join(constants.DATA_ROOT, "var/log/juju")
JUJU_LIB_PATH = os.path.join(constants.DATA_ROOT, "var/lib/juju")
CHARM_MANIFEST_GLOB = "agents/unit-*/state/deployer/manifests"


class JujuMachine(object):

    def __init__(self):
        self.cfg = {}

    @property
    def id(self):
        name = self.agent_service_name
        if name:
            return name.partition("jujud-machine-")[2]

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
            app = unit.partition('/')[0]
            id = unit.partition('/')[2]
            units.append(JujuUnit(id, app))

        return units


class JujuUnit(object):

    def __init__(self, id, application):
        self.id = id
        self.application = application
        self.name = '{}-{}'.format(application, id)


class JujuCharm(object):

    def __init__(self, name, version):
        self.name = name
        self.version = version


class JujuBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._units = []
        self._charms = []

    @property
    def machine(self):
        machine = JujuMachine()
        if not machine.config:
            return

        return machine

    @property
    def units(self):
        if not os.path.exists(JUJU_LIB_PATH):
            return

        if self._units:
            return self._units

        if self.machine.version >= "2.9":
            self._units = self.machine.deployed_units
        else:
            paths = glob.glob(os.path.join(JUJU_LIB_PATH, "agents/unit-*"))
            for unit in paths:
                unit = os.path.basename(unit)
                ret = re.compile(r"unit-(\S+)-(\d+)").match(unit)
                if ret:
                    self._units.append(JujuUnit(ret.group(2), ret.group(1)))

        return self._units

    @property
    def charms(self):
        if self._charms:
            return self._charms

        if not os.path.exists(JUJU_LIB_PATH):
            return

        for entry in glob.glob(os.path.join(JUJU_LIB_PATH,
                                            CHARM_MANIFEST_GLOB)):
            for manifest in os.listdir(entry):
                base = os.path.basename(manifest)
                ret = re.compile(r".+_(\S+)-(\d+)$").match(base)
                if ret:
                    self._charms.append(JujuCharm(ret.group(1), ret.group(2)))

        return self._charms

    @property
    def ps_units(self):
        """ Units identified from running processes. """
        units = set()
        for line in CLIHelper().ps():
            if "unit-" in line:
                ret = re.compile(r".+jujud-unit-(\S+)-(\d+).*").match(line)
                if ret:
                    units.add(JujuUnit(ret[2], ret[1]))

        return units


class JujuChecksBase(JujuBase, plugintools.PluginPartBase):

    @property
    def plugin_runnable(self):
        # TODO: define whether this plugin should run or not.
        return True
