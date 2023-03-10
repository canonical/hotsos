import os

import glob
import re
import yaml

from hotsos.core.log import log
from hotsos.core import utils
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
            units.append(JujuUnit(id, app, self.juju_lib_path, path=path))

        return units


class JujuUnit(object):

    def __init__(self, id, application, juju_lib_path, path=None):
        self.id = id
        self.application = application
        self.name = '{}-{}'.format(application, id)
        self.juju_lib_path = juju_lib_path
        self.path = path

    @utils.cached_property
    def charm_name(self):
        """
        The deployer manifest file will give us the name of the charm used to
        deploy the unit whose name may not match the charm. It also tells us
        where the charm was deployed from i.e. cs:, ch: etc
        """
        manifest_path = ("agents/unit-{}/state/deployer/manifests/*".
                         format(self.name))
        for entry in glob.glob(os.path.join(self.juju_lib_path,
                                            manifest_path)):
            # we expect only one
            manifest_file = os.path.basename(entry)
            # e.g. ch_3a_amd64_2f_focal_2f_mysql-innodb-cluster-30
            return manifest_file.split('_')[-1].rpartition('-')[0]

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
        self.version = int(version)


class JujuBase(object):
    CHARM_MANIFEST_GLOB = "agents/unit-*/state/deployer/manifests"

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
        """
        Returns units running on this host.

        @return: dict of JujuUnit objects keyed by unit name.
        """
        _units = {}
        if not os.path.exists(self.juju_lib_path):
            return _units

        if self.machine and self.machine.version >= "2.9":
            _units = {u.name: u for u in self.machine.deployed_units}
        else:
            paths = glob.glob(os.path.join(self.juju_lib_path,
                                           "agents/unit-*"))
            for unit in paths:
                base = os.path.basename(unit)
                ret = re.compile(r"unit-(\S+)-(\d+)").match(base)
                if ret:
                    app = ret.group(1)
                    id = ret.group(2)
                    u = JujuUnit(id, app, self.juju_lib_path, path=unit)
                    _units[u.name] = u

        return _units

    @utils.cached_property
    def charms(self):
        """
        Returns charms used by units on this host.

        @return: dict of JujuCharm objects keyed by charm name.
        """
        _charms = {}
        if not os.path.exists(self.juju_lib_path):
            return _charms

        for entry in glob.glob(os.path.join(self.juju_lib_path,
                                            self.CHARM_MANIFEST_GLOB)):
            name = None
            versions = []
            for manifest in os.listdir(entry):
                base = os.path.basename(manifest)
                ret = re.compile(r".+_(\S+)-(\d+)$").match(base)
                if ret:
                    name = ret.group(1)
                    versions.append(int(ret.group(2)))

            if name and versions:
                _charms[name] = JujuCharm(name, max(versions))

        return _charms

    @utils.cached_property
    def charm_names(self):
        if not self.charms:
            return []

        return list(self.charms.keys())
