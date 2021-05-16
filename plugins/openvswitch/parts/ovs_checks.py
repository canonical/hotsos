#!/usr/bin/python3
import os

from common import (
    constants,
    plugin_yaml,
)
from common.searchtools import (
    FileSearcher,
    SearchDef,
)
from ovs_common import (
    OVS_DAEMONS,
)

OVS_INFO = {}


class OpenvSwitchDaemonChecks(object):

    def __init__(self):
        self.search_obj = FileSearcher()
        self.results = []

    def register_search_terms(self):
        for d in OVS_DAEMONS:
            path = os.path.join(constants.DATA_ROOT, OVS_DAEMONS[d]["logs"])
            if constants.USE_ALL_LOGS:
                path = f"{path}*"

            sd = SearchDef(r".+\|WARN\|.+", tag="{}-warn".format(d))
            self.search_obj.add_search_term(sd, path)
            sd = SearchDef(r".+\|ERROR\|.+", tag="{}-error".format(d))
            self.search_obj.add_search_term(sd, path)

    def process_results(self):
        stats = {}
        for d in OVS_DAEMONS:
            for key in ["warn", "error"]:
                tag = "{}-{}".format(d, key)
                num = len(self.results.find_by_tag(tag))
                if not num:
                    continue

                if d not in stats:
                    stats[d] = {}

                stats[d][key] = num

        if stats:
            OVS_INFO.update(stats)

    def __call__(self):
        self.register_search_terms()
        self.results = self.search_obj.search()
        self.process_results()


def get_checks():
    return OpenvSwitchDaemonChecks()


if __name__ == "__main__":
    get_checks()()
    if OVS_INFO:
        plugin_yaml.save_part(OVS_INFO, priority=1)
