import re
import os

from core import constants
from core.cli_helpers import CLIHelper
from core import plugintools


class SYSCtlHelper(object):

    def __init__(self, path):
        self.path = path
        self._config = {}
        self._read_conf()

    def get(self, key):
        return self._config.get(key)

    @property
    def all(self):
        return self._config

    def _read_conf(self):
        if not os.path.isfile(self.path):
            return

        with open(self.path) as fd:
            for line in fd.readlines():
                if line.startswith("#"):
                    continue

                split = line.partition("=")
                if not split[1]:
                    continue

                key = split[0].strip()
                value = split[2].strip()

                # ignore wildcarded keys'
                if '*' in key:
                    continue

                # ignore unsetters
                if key.startswith('-'):
                    continue

                self._config[key] = value


class SystemBase(plugintools.PluginPartBase):

    @property
    def hostname(self):
        return CLIHelper().hostname()

    @property
    def os_release_name(self):
        data_source = os.path.join(constants.DATA_ROOT, "etc/lsb-release")
        if os.path.exists(data_source):
            for line in open(data_source).read().split():
                ret = re.compile(r"^DISTRIB_CODENAME=(.+)").match(line)
                if ret:
                    return "ubuntu {}".format(ret[1])

    @property
    def virtualisation_type(self):
        """
        @return: virt type e.g. kvm or lxc if host is virtualised otherwise
                 None.
        """
        info = CLIHelper().hostnamectl()
        for line in info:
            split_line = line.partition(': ')
            if 'Virtualization' in split_line[0]:
                return split_line[2].strip()

        return

    @property
    def num_cpus(self):
        lscpu_output = CLIHelper().lscpu()
        if lscpu_output:
            for line in lscpu_output:
                ret = re.compile(r"^CPU\(s\):\s+([0-9]+)\s*.*").match(line)
                if ret:
                    return int(ret[1])

    @property
    def loadavg(self):
        uptime = CLIHelper().uptime()
        if uptime:
            ret = re.compile(r".+load average:\s+(.+)").match(uptime)
            if ret:
                return ret[1]

    @property
    def unattended_upgrades_enabled(self):
        apt_config_dump = CLIHelper().apt_config_dump()
        if not apt_config_dump:
            return

        for line in apt_config_dump:
            ret = re.compile(r"^APT::Periodic::Unattended-Upgrade\s+"
                             "\"([0-9]+)\";").match(line)
            if ret:
                if int(ret[1]) == 0:
                    return False
                else:
                    return True

        return False


class SystemChecksBase(SystemBase, plugintools.PluginPartBase):
    pass
