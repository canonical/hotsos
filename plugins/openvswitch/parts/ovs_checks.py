#!/usr/bin/python3
import os

from common import (
    constants,
    plugin_yaml,
)
from common.searchtools import (
    FileSearcher,
    FilterDef,
    SearchDef,
)
from ovs_common import (
    OVS_DAEMONS,
)

OVS_INFO = {"daemon-checks": {}}


class OpenvSwitchDaemonChecksBase(object):

    def __init__(self):
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

            sd = SearchDef(r"([0-9-]+)T([0-9:\.]+)Z.+\|(?:ERROR|WARN)\|.+",
                           tag="{}-warn".format(d))
            self.search_obj.add_search_term(sd, path)

    def process_results(self):
        stats = {}
        for d in OVS_DAEMONS:
            for key in ["warn", "error"]:
                tag = "{}-{}".format(d, key)
                for r in self.results.find_by_tag(tag):
                    if d not in stats:
                        stats[d] = {key: {}}

                    ts_date = r.get(1)
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
            OVS_INFO["daemon-checks"]["logs"] = stats


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

            OVS_INFO["daemon-checks"]["ovs-vswitchd"] = stats


def get_checks():
    return [OpenvSwitchvSwitchdChecks(), OpenvSwitchDaemonChecksCommon()]


if __name__ == "__main__":
    [c() for c in get_checks()]
    if OVS_INFO:
        plugin_yaml.save_part(OVS_INFO, priority=1)
