import re
import os

from uuid import uuid4

from common import (
    constants,
    issue_types,
    issues_utils,
)
from common.cli_helpers import CLIHelper
from common.plugins.openstack import (
    OpenstackConfig,
    OPENSTACK_SHOW_CPU_PINNING_RESULTS,
)
from common.plugins.kernel import (
    KernelConfig,
    SystemdConfig,
)

YAML_PRIORITY = 6


def list_to_str(slist, separator=None):
    """Convert list of any type to string separated by separator."""
    if not separator:
        separator = ','

    if not slist:
        return ""

    slist = OpenstackConfig.squash_int_range(slist)
    return separator.join([str(e) for e in slist])


class NUMAInfo(object):

    numactl = ""

    def __init__(self):
        try:
            self.numactl = CLIHelper().numactl() or ""
        except OSError:
            self.numactl = ""

        self._nodes = {}

    @property
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
        return self.nodes.get(node)


class Results(object):
    def __init__(self):
        self.config = {}
        self._results = {"INFO": {"label": "info", "main": {}, "extras": {}},
                         "WARNING": {"label": "warnings", "main": {},
                                     "extras": {}},
                         "ERROR": {"label": "errors", "main": {},
                                   "extras": {}}}

    def add_config(self, application, key, value):
        """Save service/application config. This servces as a record of what
        we have used as a data source to cross-reference settings.
        """
        if not value:
            return

        if application in self.config:
            self.config[application][key] = value
        else:
            self.config[application] = {key: value}

    def _add_msg(self, level, msg, extra=None):
        """Add message to be displayed"""
        key = str(uuid4())
        self._results[level]["main"][key] = msg
        if extra:
            self._results[level]["extras"][key] = extra

    def add_info(self, msg, extra=None):
        """Add message to be displayed as INFO"""
        self._add_msg("INFO", msg, extra)

    def add_warn(self, msg, extra=None):
        """Add message to be displayed as WARNING"""
        self._add_msg("WARNING", msg, extra)

    def add_error(self, msg, extra=None):
        """Add message to be displayed as ERROR"""
        self._add_msg("ERROR", msg, extra)

    @property
    def has_results(self):
        return any([e[1]["main"] for e in self._results.items()])

    def get(self):
        if not (self.config or self.has_results):
            return

        info = {}
        if self.config:
            info["input"] = {}
            for app in self.config:
                info["input"][app] = self.config[app]

        if self.has_results:
            info["results"] = {}
            for level in self._results:
                if not self._results[level]["main"]:
                    continue

                label = self._results[level]["label"]
                if label not in info["results"]:
                    info["results"][label] = []

                for key in self._results[level]["main"]:
                    msg = self._results[level]["main"][key]
                    info["results"][label].append(msg)
                    extras = self._results[level]["extras"].get(key)
                    if OPENSTACK_SHOW_CPU_PINNING_RESULTS and extras:
                        _extras = {"extra-info": extras.split('\n')}
                        info["results"][label].append(_extras)

        return info


class CPUPinningChecker(object):

    def __init__(self):
        self.numa = NUMAInfo()
        self.systemd = SystemdConfig()
        self.kernel = KernelConfig()
        self.nova_cfg = OpenstackConfig(os.path.join(constants.DATA_ROOT,
                                                     "etc/nova/nova.conf"))
        self.results = Results()
        self.cpu_dedicated_set = self.nova_cfg.get("cpu_dedicated_set",
                                                   expand_ranges=True) or []
        self.cpu_shared_set = self.nova_cfg.get("cpu_shared_set",
                                                expand_ranges=True) or []
        self.vcpu_pin_set = self.nova_cfg.get("vcpu_pin_set",
                                              expand_ranges=True) or []
        self.cpu_dedicated_set_name = ""

        # convert to sets
        self.cpu_dedicated_set = set(self.cpu_dedicated_set)
        self.cpu_shared_set = set(self.cpu_shared_set)
        self.vcpu_pin_set = set(self.vcpu_pin_set)

        # >= Train
        if self.cpu_dedicated_set:
            self.cpu_dedicated_set_name = "cpu_dedicated_set"
        elif self.vcpu_pin_set:
            self.cpu_dedicated_set = self.vcpu_pin_set
            self.cpu_dedicated_set_name = "vcpu_pin_set"

        self.isolcpus = self.kernel.get("isolcpus", expand_ranges=True) or []
        self.isolcpus = set(self.isolcpus)

        self.cpuaffinity = self.systemd.get("CPUAffinity",
                                            expand_ranges=True) or []
        self.cpuaffinity = set(self.cpuaffinity)

        if self.nova_cfg.get("cpu_dedicated_set"):
            self.results.add_config("nova", "cpu_dedicated_set",
                                    list_to_str(self.cpu_dedicated_set))

        self.results.add_config("nova", "vcpu_pin_set",
                                list_to_str(self.vcpu_pin_set))

        self.results.add_config("nova", "cpu_shared_set",
                                list_to_str(self.cpu_shared_set))

        self.results.add_config("kernel", "isolcpus",
                                list_to_str(self.isolcpus))
        self.results.add_config("systemd", "cpuaffinity",
                                list_to_str(self.cpuaffinity))

        for node in self.numa.nodes:
            self.results.add_config("numa", "node{}".format(node),
                                    list_to_str(self.numa.cores(node)))

    @property
    def output(self):
        _output = self.results.get()
        if _output:
            return {"cpu-pinning-checks": _output}

    def __call__(self):
        """Perform a set of checks on Nova cpu pinning configuration to ensure
        it is setup as expected.
        """

        if self.cpu_dedicated_set:
            intersect1 = self.cpu_dedicated_set.intersection(self.isolcpus)
            intersect2 = self.cpu_dedicated_set.intersection(self.cpuaffinity)
            if intersect1:
                if intersect2:
                    extra = ("intersection with isolcpus: {}\nintersection "
                             "with cpuaffinity: {}".format(intersect1,
                                                           intersect2))
                    msg = ("{} is a subset of both isolcpus AND "
                           "cpuaffinity".format(self.cpu_dedicated_set_name))
                    self.results.add_error(msg, extra)
                    issue = issue_types.OpenstackWarning(msg)
                    issues_utils.add_issue(issue)
            elif intersect2:
                if intersect1:
                    extra = ("intersection with isolcpus: {}\nintersection "
                             "with cpuaffinity: {}".format(intersect1,
                                                           intersect2))
                    msg = ("{} is a subset of both isolcpus AND "
                           "cpuaffinity".format(self.cpu_dedicated_set_name))
                    self.results.add_error(msg, extra)
                    issue = issue_types.OpenstackWarning(msg)
                    issues_utils.add_issue(issue)
            else:
                msg = ("{} is neither a subset of isolcpus nor cpuaffinity".
                       format(self.cpu_dedicated_set_name))
                self.results.add_info(msg)
                # this is not necessarily an error. If using
                # hw:cpu_policy=shared this allows moving non-kvm workloads
                # off a set of cores while still allowing vm cores to be
                # overcommitted.

        intersect = self.cpu_shared_set.intersection(self.isolcpus)
        if intersect:
            extra = "intersection: {}".format(list_to_str(intersect))
            msg = "cpu_shared_set contains cores from isolcpus"
            self.results.add_error(msg, extra)
            issue = issue_types.OpenstackWarning(msg)
            issues_utils.add_issue(issue)

        intersect = self.cpu_dedicated_set.intersection(self.cpu_shared_set)
        if intersect:
            extra = "intersection: {}".format(list_to_str(intersect))
            msg = ("cpu_shared_set and {} overlap".
                   format(self.cpu_dedicated_set_name))
            self.results.add_error(msg, extra)
            issue = issue_types.OpenstackWarning(msg)
            issues_utils.add_issue(issue)

        intersect = self.isolcpus.intersection(self.cpuaffinity)
        if intersect:
            extra = "intersection: {}".format(list_to_str(intersect))
            msg = "isolcpus and cpuaffinity overlap"
            self.results.add_error(msg, extra)
            issue = issue_types.OpenstackWarning(msg)
            issues_utils.add_issue(issue)

        node_count = 0
        for node in self.numa.nodes:
            if self.cpu_dedicated_set.intersection(set(self.numa.cores(node))):
                node_count += 1

        if node_count > 1:
            extra = ""
            for node in self.numa.nodes:
                if extra:
                    extra += "\n"

                extra += "node{}: {}".format(node,
                                             list_to_str(
                                                 self.numa.cores(node)))

            extra += "\n{}: {}".format(self.cpu_dedicated_set_name,
                                       list_to_str(self.cpu_dedicated_set))

            msg = ("{} has cores from > 1 numa node".
                   format(self.cpu_dedicated_set_name))
            self.results.add_warning(msg, extra)
            issue = issue_types.OpenstackWarning(msg)
            issues_utils.add_issue(issue)

        if self.isolcpus or self.cpuaffinity:
            total_isolated = self.isolcpus.union(self.cpuaffinity)
            nonisolated = set(total_isolated).intersection()

            pcent_unpinned = ((float(100) / len(total_isolated)) *
                              len(nonisolated))
            if pcent_unpinned < 10 or len(nonisolated) <= 4:
                msg = ("Host has only {} cores ({}%) unpinned. This might "
                       "cause unintended performance problems".
                       format(len(nonisolated), pcent_unpinned))
                self.results.add_warn(msg)
                issue = issue_types.OpenstackWarning(msg)
                issues_utils.add_issue(issue)
