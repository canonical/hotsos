import os

import glob
import re
import yaml

from hotsos.core.log import log
from hotsos.core import (
    host_helpers,
    utils,
)
from hotsos.core.config import HotSOSConfig


class JujuMachine(object):

    def __init__(self, juju_lib_path):
        self.juju_lib_path = juju_lib_path
        self.cfg = {}

    @property
    def id(self):
        name = self.agent_service_name
        if name:
            return name.partition("jujud-machine-")[2]

    @utils.cached_property
    def config(self):
        if not self.cfg:
            path = glob.glob(os.path.join(self.juju_lib_path,
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

    @utils.cached_property
    def agent_service_name(self):
        return self.config.get("values", {}).get("AGENT_SERVICE_NAME")

    @utils.cached_property
    def version(self):
        return self.config.get("upgradedToVersion", "unknown")

    @utils.cached_property
    def deployed_units(self):
        units = []
        # requires >= 2.9.x
        _units = self.config.get("values", {}).get("deployed-units", "")
        if not _units:
            return units

        for unit in _units.split(','):
            app = unit.partition('/')[0]
            id = unit.partition('/')[2]
            path = os.path.join(self.juju_lib_path,
                                "agents/unit-{}-{}".format(app, id))
            units.append(JujuUnit(id, app, path))

        return units


class JujuUnit(object):

    def __init__(self, id, application, path=None):
        self.id = id
        self.application = application
        self.name = '{}-{}'.format(application, id)
        self.path = path

    @utils.cached_property
    def repo_info(self):
        """
        Some charms, e.g. the Openstack charms, provide a repo-info file that
        contains information from the charm's repository e.g. commit id.
        """
        info = {}
        path = os.path.join(self.path, 'charm/repo-info')
        if not os.path.exists(path):
            return info

        with open(path) as fd:
            for line in fd:
                if line.startswith('commit-short:'):
                    sha1_short = line.partition(' ')[2]
                    if sha1_short:
                        info['commit'] = sha1_short.strip()

        return info


class JujuCharm(object):

    def __init__(self, name, version):
        self.name = name
        self.version = version


class JujuBase(object):
    CHARM_MANIFEST_GLOB = "agents/unit-*/state/deployer/manifests"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._units = []
        self._charms = []

    @property
    def juju_lib_path(self):
        return os.path.join(HotSOSConfig.data_root, "var/lib/juju")

    @utils.cached_property
    def machine(self):
        machine = JujuMachine(self.juju_lib_path)
        if not machine.config:
            log.debug("no juju machine identified")
            return

        return machine

    @utils.cached_property
    def units(self):
        if not os.path.exists(self.juju_lib_path):
            return

        if self._units:
            return self._units

        if self.machine and self.machine.version >= "2.9":
            self._units = self.machine.deployed_units
        else:
            paths = glob.glob(os.path.join(self.juju_lib_path,
                                           "agents/unit-*"))
            for unit in paths:
                base = os.path.basename(unit)
                ret = re.compile(r"unit-(\S+)-(\d+)").match(base)
                if ret:
                    app = ret.group(1)
                    id = ret.group(2)
                    self._units.append(JujuUnit(id, app, unit))

        return self._units

    @utils.cached_property
    def nonlocal_units(self):
        """ These are units that may be running on the local host i.e.
        their associated jujud process is visible but inside containers.
        """
        units_nonlocal = []
        if self.units:
            local_units = [u.name for u in self.units]
        else:
            local_units = []

        for unit in self.ps_units:
            if unit.name in local_units:
                continue

            units_nonlocal.append(unit)

        if units_nonlocal:
            return units_nonlocal

    @utils.cached_property
    def charms(self):
        if self._charms:
            return self._charms

        if not os.path.exists(self.juju_lib_path):
            return

        for entry in glob.glob(os.path.join(self.juju_lib_path,
                                            self.CHARM_MANIFEST_GLOB)):
            for manifest in os.listdir(entry):
                base = os.path.basename(manifest)
                ret = re.compile(r".+_(\S+)-(\d+)$").match(base)
                if ret:
                    name = ret.group(1)
                    version = ret.group(2)
                    self._charms.append(JujuCharm(name, version))

        return self._charms

    @utils.cached_property
    def charm_names(self):
        if not self.charms:
            return []

        return [c.name for c in self.charms]

    @utils.cached_property
    def ps_units(self):
        """ Units identified from running processes. """
        units = set()
        for line in host_helpers.CLIHelper().ps():
            if "unit-" in line:
                ret = re.compile(r".+jujud-unit-(\S+)-(\d+).*").match(line)
                if ret:
                    units.add(JujuUnit(ret[2], ret[1]))

        return units
