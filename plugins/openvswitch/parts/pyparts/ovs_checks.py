#!/usr/bin/python3
import os
import re

from common import (
    constants,
    cli_helpers,
    issues_utils,
    issue_types,
)
from common.searchtools import (
    FileSearcher,
    FilterDef,
    SearchDef,
    SequenceSearchDef,
)
from common.utils import mktemp_dump
from ovs_common import OVS_DAEMONS, OpenvSwitchChecksBase

YAML_PRIORITY = 1


class OpenvSwitchDaemonChecksBase(OpenvSwitchChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_obj = FileSearcher()
        self.results = []

    def register_search_terms(self):
        raise NotImplementedError

    def process_results(self):
        raise NotImplementedError

    def __call__(self):
        self.register_search_terms()
        self.results = self.search_obj.search()
        self.process_results()


class OpenvSwitchDaemonChecksCommon(OpenvSwitchDaemonChecksBase):

    def register_search_terms(self):
        for d in OVS_DAEMONS:
            path = os.path.join(constants.DATA_ROOT, OVS_DAEMONS[d]["logs"])
            if constants.USE_ALL_LOGS:
                path = f"{path}*"

            sd = SearchDef(r"([0-9-]+)T([0-9:\.]+)Z.+\|(ERR|ERROR|WARN)\|.+",
                           tag=d)
            self.search_obj.add_search_term(sd, path)

    def process_results(self):
        stats = {}
        for d in OVS_DAEMONS:
            tag = d
            for r in self.results.find_by_tag(tag):
                ts_date = r.get(1)
                loglevel = r.get(3)
                for key in ["warn", "error", "ERR", "WARN"]:
                    if loglevel != key:
                        continue

                    if d not in stats:
                        stats[d] = {key: {}}

                    if key not in stats[d]:
                        stats[d][key] = {}

                    if ts_date in stats[d][key]:
                        stats[d][key][ts_date] += 1
                    else:
                        stats[d][key][ts_date] = 1

            if stats.get(d):
                for key in stats[d]:
                    stats_sorted = {}
                    for k, v in sorted(stats[d][key].items(),
                                       key=lambda x: x[0]):
                        stats_sorted[k] = v

                    stats[d][key] = stats_sorted

        if stats:
            if "daemon-checks" not in self._output:
                self._output["daemon-checks"] = {}

            self._output["daemon-checks"]["logs"] = stats


class OpenvSwitchvSwitchdChecks(OpenvSwitchDaemonChecksBase):

    def __init__(self):
        super().__init__()
        self.daemon = "ovs-vswitchd"
        self.tags = []

    def register_search_terms(self):
        path = os.path.join(constants.DATA_ROOT,
                            OVS_DAEMONS[self.daemon]["logs"])
        if constants.USE_ALL_LOGS:
            path = f"{path}*"

        fd = FilterDef(r"ERROR|WARN")
        self.search_obj.add_filter_term(fd, path)

        tag = "netdev_linux-no-such-device"
        sd = SearchDef(r"([0-9-]+)T([0-9:\.]+)Z.+\|(\S+): .+: No such device",
                       tag=tag)
        self.tags.append(tag)
        self.search_obj.add_search_term(sd, path)

        tag = "bridge-no-such-device"
        sd = SearchDef(r"([0-9-]+)T([0-9:\.]+)Z.+\|could not open network "
                       r"device (\S+) \(No such device\)", tag=tag)
        self.tags.append(tag)
        self.search_obj.add_search_term(sd, path)

    def process_results(self):
        stats = {}
        for tag in self.tags:
            for r in self.results.find_by_tag(tag):
                if tag not in stats:
                    stats[tag] = {}

                ts_date = r.get(1)
                iface = r.get(3)
                if ts_date not in stats[tag]:
                    stats[tag][ts_date] = {}

                if iface not in stats[tag][ts_date]:
                    stats[tag][ts_date][iface] = 1
                else:
                    stats[tag][ts_date][iface] += 1

        if stats:
            for tag in stats:
                stats_sorted = {}
                for k, v in sorted(stats[tag].items(),
                                   key=lambda x: x[0]):
                    stats_sorted[k] = v

                stats[tag] = stats_sorted

            if "daemon-checks" not in self._output:
                self._output["daemon-checks"] = {}

            self._output["daemon-checks"]["ovs-vswitchd"] = stats


class OpenvSwitchDPChecks(OpenvSwitchDaemonChecksBase):

    def __init__(self):
        super().__init__()
        out = cli_helpers.get_ovs_appctl_dpctl_show("system@ovs-system")
        self.f_dpctl = mktemp_dump(''.join(out))
        bridges = cli_helpers.get_ovs_vsctl_list_br()
        self.ovs_bridges = [br.strip() for br in bridges]
        self.sequence_defs = []

    def __del__(self):
        if os.path.exists(self.f_dpctl):
            os.unlink(self.f_dpctl)

    def register_search_terms(self):
        self.sequence_defs.append(SequenceSearchDef(
            start=SearchDef(r"\s+port \d+: (\S+) .+"),
            body=SearchDef(r"\s+([RT]X) \S+:(\d+) \S+:(\d+) \S+:(\d+) "
                           r"\S+:(\d+) \S+:(\d+)"),
            tag="port-stats"))
        for sd in self.sequence_defs:
            self.search_obj.add_search_term(sd, self.f_dpctl)

    def process_results(self):
        """
        Report on interfaces that are showing packet drops or errors.

        Sometimes it is normal for an interface to have packet drops and if
        we think that is the case we ignore but otherwise we raise an issue
        to alert.

        Interfaces we currently ignore:

        OVS bridges.

        In Openstack for example when using Neutron HA routers, vrrp peers
        that are in BACKUP state may still receive packets on their external
        interface but these will be dropped since they have no where to go. In
        this case it is possible to have 100% packet drops on the interface
        if that VR has never been a vrrp MASTER. For this scenario we filter
        interfaces whose name matches e.g. qg-3ca935f4-07.
        """
        stats = {}
        all_dropped = []  # interfaces where all packets are dropped
        all_errors = []  # interfaces where all packets are errors
        for sd in self.sequence_defs:
            for results in self.results.find_sequence_sections(sd).values():
                port = None
                _stats = {}
                for result in results:
                    if result.tag == sd.start_tag:
                        port = result.get(1)
                    elif result.tag == sd.body_tag:
                        key = result.get(1)
                        packets = int(result.get(2))
                        errors = int(result.get(3))
                        dropped = int(result.get(4))

                        log_stats = False
                        if packets:
                            dropped_pcent = int((100/packets) * dropped)
                            errors_pcent = int((100/packets) * errors)
                            if dropped_pcent > 1 or errors_pcent > 1:
                                log_stats = True
                        elif errors or dropped:
                            log_stats = True

                        if log_stats:
                            _stats[key] = {"packets": packets}
                            if errors:
                                _stats[key]["errors"] = errors
                            if dropped:
                                _stats[key]["dropped"] = dropped

                if port and _stats:
                    # Ports to ignore - see docstring for info
                    if (port in self.ovs_bridges or
                            re.compile(r"^(q|s)g-\S{11}$").match(port)):
                        continue

                    for key in _stats:
                        s = _stats[key]
                        if s.get('dropped') and not s['packets']:
                            all_dropped.append(port)

                        if s.get('errors') and not s['packets']:
                            all_errors.append(port)

                    stats[port] = _stats

        if stats:
            if all_dropped:
                msg = ("found {} ovs interfaces with 100% dropped packets"
                       .format(len(all_dropped)))
                issues_utils.add_issue(issue_types.OpenvSwitchWarning(msg))

            if all_errors:
                msg = ("found {} ovs interfaces with 100% packet errors"
                       .format(len(all_errors)))
                issues_utils.add_issue(issue_types.OpenvSwitchWarning(msg))

            stats_sorted = {}
            for k in sorted(stats):
                stats_sorted[k] = stats[k]

            self._output["port-stats"] = stats_sorted
