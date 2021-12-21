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
    def setters(self):
        if not self._config:
            return {}

        return self._config['set']

    @property
    def unsetters(self):
        if not self._config:
            return {}

        return self._config['unset']

    def _read_conf(self):
        if not os.path.isfile(self.path):
            return

        setters = {}
        unsetters = {}
        with open(self.path) as fd:
            for line in fd.readlines():
                if line.startswith("#"):
                    continue

                split = line.partition("=")
                if split[1]:
                    key = split[0].strip()
                    value = split[2].strip()

                    # ignore wildcarded keys'
                    if '*' in key:
                        continue

                    setters[key] = value
                elif line.startswith('-'):
                    key = line.partition('-')[2].strip()
                    unsetters[key] = None
                    continue

        self._config['set'] = setters
        self._config['unset'] = unsetters


class SystemBase(plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sysctl_all = None

    @property
    def date(self):
        return CLIHelper().date(no_format=True)

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
        """ Return number of cpus or 0 if none found. """
        lscpu_output = CLIHelper().lscpu()
        if lscpu_output:
            for line in lscpu_output:
                ret = re.compile(r"^CPU\(s\):\s+([0-9]+)\s*.*").match(line)
                if ret:
                    return int(ret[1])

        return 0

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

    @property
    def sysctl_all(self):
        if self._sysctl_all is not None:
            return self._sysctl_all

        actuals = {}
        for kv in CLIHelper().sysctl_all():
            k = kv.partition("=")[0].strip()
            v = kv.partition("=")[2].strip()
            # normalise multi-whitespace into a single
            actuals[k] = ' '.join(v.split())

        self._sysctl_all = actuals
        return self._sysctl_all


class SystemChecksBase(SystemBase, plugintools.PluginPartBase):

    @property
    def plugin_runnable(self):
        # Always run
        return True
