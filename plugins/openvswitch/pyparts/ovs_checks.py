import os
import re

from core import (
    issues_utils,
    issue_types,
)
from core.cli_helpers import CLIHelper
from core.searchtools import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)
from core.utils import mktemp_dump
from core.plugins.openvswitch import (
    OpenvSwitchChecksBase,
    OpenvSwitchEventChecksBase,
)

YAML_PRIORITY = 1


class OpenvSwitchDaemonChecks(OpenvSwitchEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='daemon-checks')

    def _stats_sort(self, stats):
        stats_sorted = {}
        for k, v in sorted(stats.items(),
                           key=lambda x: x[0]):
            stats_sorted[k] = v

        return stats_sorted

    def get_results_stats(self, event, results, key_by_date=True):
        """
        Collect information about how often a resource occurs. A resource can
        be anything e.g. an interface or a loglevel string.

        @param event: string identifier for this set of results.
        @param results: a list of SearchResult objects containing two groups; a
                        date and a resource.
        @param key_by_date: by default the results are collected by datetime
                            i.e. for each timestamp show how many of each
                            resource occured.
        """
        stats = {}
        for r in results:
            if key_by_date:
                key = r.get(1)
                value = r.get(2)
            else:
                key = r.get(2)
                value = r.get(1)

            if key not in stats:
                stats[key] = {}

            if value not in stats[key]:
                stats[key][value] = 1
            else:
                stats[key][value] += 1

            # sort each keyset
            if not key_by_date:
                stats[key] = self._stats_sort(stats[key])

        if stats:
            # only if sorted per key
            if key_by_date:
                stats = self._stats_sort(stats)

            return {event: stats}

    def process_results(self, results):
        """ See defs/events.yaml for definitions. """
        checkresults = {}
        for section, events in self.event_definitions.items():
            for event in events:
                _results = results.find_by_tag(event)
                if not _results:
                    continue

                if section == 'errors-and-warnings':
                    ret = self.get_results_stats(event, _results,
                                                 key_by_date=False)
                    out_key = 'logs'
                elif section == 'vswitchd':
                    ret = self.get_results_stats(event, _results)
                    out_key = 'ovs-vswitchd'

                if ret:
                    if out_key not in checkresults:
                        checkresults[out_key] = ret
                    else:
                        checkresults[out_key].update(ret)

        if checkresults:
            self._output["daemon-checks"] = checkresults


class OpenvSwitchDPChecks(OpenvSwitchChecksBase):

    def __init__(self):
        super().__init__()
        cli = CLIHelper()
        out = cli.ovs_appctl_dpctl_show(datapath="system@ovs-system")
        self.f_dpctl = mktemp_dump(''.join(out))
        bridges = cli.ovs_vsctl_list_br()
        self.ovs_bridges = [br.strip() for br in bridges]
        self.searchobj = FileSearcher()
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
            self.searchobj.add_search_term(sd, self.f_dpctl)

    def process_results(self, results):
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
            for section in results.find_sequence_sections(sd).values():
                port = None
                _stats = {}
                for result in section:
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

    def __call__(self):
        self.register_search_terms()
        self.process_results(self.searchobj.search())
