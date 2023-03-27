import re
import os

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper, SYSCtlFactory
from hotsos.core.utils import cached_property, mktemp_dump
from hotsos.core.search import (
    FileSearcher, SearchDef,
    SequenceSearchDef
)


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
    def ubuntu_pro_status(self):
        """Parse and retrieve Ubuntu Pro status

        Returns:
            Dictionary: Ubuntu pro status as a dictionary, e.g.::
            {
                "status": "<attached|not-attached|error>"
                "services": {
                    "esm-apps": {
                        "entitled": "yes",
                        "status": "enabled"
                    }, /* ... */
                },
                "account": "ACME Corporation",
                "subscription": "Ubuntu Pro (Apps-only) - Virtual",
                "technical_support_level": "essential",
                "valid_until": "Sat Jan  1 01:01:01 9999 +03"
            }

        """

        # TODO(mkg): Unfortunately, sos does not capture `pro status
        # --format json` output at the moment. We have to parse the
        # human-readable output for now. This function should ideally
        # rely on the json output when the upstream sos starts to
        # include it.
        s = FileSearcher()
        service_status_seqdef = SequenceSearchDef(
            start=SearchDef(r"^SERVICE +ENTITLED +STATUS +DESCRIPTION"),
            body=SearchDef(r"^(\S+) +(\S+) +(\S+) +(.+)\n"),
            end=SearchDef(r"\n"),
            tag="service-status")
        account_status_seqdef = SequenceSearchDef(
            start=SearchDef(r" *?(Account): (.*)\n"),
            body=SearchDef(r" *?([\S ]+): (.*)\n"),
            end=SearchDef(r" *?(Technical support level): (.*)\n"),
            tag="account-status")
        not_attached_def = SearchDef(
            r".*not attached to.*(Ubuntu (Pro|Advantage)|UA).*",
            tag="not-attached")

        f = mktemp_dump("".join(CLIHelper().pro_status()))
        s.add(not_attached_def, f)
        s.add(service_status_seqdef, f)
        s.add(account_status_seqdef, f)
        results = s.run()

        if results.find_by_tag("not-attached"):
            return {"status": "not-attached"}

        ssects = results.find_sequence_sections(service_status_seqdef)
        asects = results.find_sequence_sections(account_status_seqdef)
        if not all([ssects, asects]):
            log.debug("badness: `pro status` does not match "
                      "the expected format")
            return {"status": "error"}

        result = {}
        result["status"] = "attached"
        result["services"] = {}

        for id in ssects:
            result["services"] = {**result["services"], **{
                v.get(1): {
                    "entitled": v.get(2),
                    "status": v.get(3)
                }
                for v in ssects[id] if v.tag == service_status_seqdef.body_tag
            }}

        for id in asects:
            result = {**result, **{
                re.sub(r'\W+', '_', v.get(1).strip()).lower(): v.get(2).strip()
                for v in asects[id]
            }}

        return result

    @cached_property
    def sysctl_all(self):
        return SYSCtlFactory().sysctl_all
