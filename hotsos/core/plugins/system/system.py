import re
import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper, SYSCtlFactory
from hotsos.core.utils import cached_property


class NUMAInfo(object):
    numactl = ""

    def __init__(self):
        try:
            self.numactl = CLIHelper().numactl() or ""
        except OSError:
            self.numactl = ""

        self._nodes = {}

    @cached_property
    def nodes(self):
        """Returns dictionary of numa nodes and their associated list of cpu
           cores.
        """
        if self._nodes:
            return self._nodes

        node_ids = []
        for line in self.numactl:
            expr = r'^available:\s+[0-9]+\s+nodes\s+\(([0-9\-]+)\)'
            ret = re.compile(expr).match(line)
            if ret:
                p = ret[1].partition('-')
                if p[1] == '-':
                    node_ids = range(int(p[0]), int(p[2]) + 1)
                else:
                    node_ids = [int(p[0])]

                break

        for node in node_ids:
            for line in self.numactl:
                expr = r'^node\s+{}\s+cpus:\s([0-9\s]+)'.format(node)
                ret = re.compile(expr).match(line)
                if ret:
                    self._nodes[node] = [int(e) for e in ret[1].split()]
                    break

        return self._nodes

    def cores(self, node=None):
        """Returns list of cores for a given numa node.

        If no node id is provided, all cores from all numa nodes are returned.
        """
        if not self.nodes:
            return []

        if node is None:
            _cores = []
            for c in self.nodes.values():
                _cores += c

            return _cores

        return self.nodes.get(node)


class SystemBase(object):

    @cached_property
    def date(self):
        return CLIHelper().date(no_format=True)

    @cached_property
    def hostname(self):
        return CLIHelper().hostname()

    @cached_property
    def os_release_name(self):
        data_source = os.path.join(HotSOSConfig.data_root, "etc/lsb-release")
        if os.path.exists(data_source):
            for line in open(data_source).read().split():
                ret = re.compile(r"^DISTRIB_CODENAME=(.+)").match(line)
                if ret:
                    return "ubuntu {}".format(ret[1])

    @cached_property
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

    @cached_property
    def num_cpus(self):
        """ Return number of cpus or 0 if none found. """
        lscpu_output = CLIHelper().lscpu()
        if lscpu_output:
            for line in lscpu_output:
                ret = re.compile(r"^CPU\(s\):\s+([0-9]+)\s*.*").match(line)
                if ret:
                    return int(ret[1])

        return 0

    @cached_property
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

    @cached_property
    def sysctl_all(self):
        return SYSCtlFactory().sysctl_all
