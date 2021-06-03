#!/usr/bin/python3
import os

import yaml

from common import (
    checks,
    constants,
    plugin_yaml,
    utils,
)
from common.searchtools import (
    SearchDef,
    FileSearcher,
)
from openstack_common import (
    SERVICE_RESOURCES,
)

LB_CHECKS = {}


class OctaviaLBChecks(checks.APTPackageChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.searcher = FileSearcher()
        self.logs_path = os.path.join(constants.DATA_ROOT,
                                      SERVICE_RESOURCES["octavia"]["logs"])

        self.data_sources = {}
        fname = 'octavia-health-manager.log'
        self.data_sources["health-manager"] = os.path.join(self.logs_path,
                                                           fname)
        self.data_sources["worker"] = os.path.join(self.logs_path,
                                                   'octavia-worker.log')
        if constants.USE_ALL_LOGS:
            self.data_sources["health-manager"] = (
                "{}*".format(self.data_sources["health-manager"]))
            self.data_sources["worker"] = (
                "{}*".format(self.data_sources["worker"]))

    def get_hm_amphora_missed_heartbeats(self):
        missed_heartbeats = {}
        expr = (r"^(\S+) \S+ .+ Amphora (\S+) health message was processed "
                r"too slowly:.+")
        d = SearchDef(expr, tag="amp-missed-hb", hint="health message")
        self.searcher.add_search_term(d, self.data_sources["health-manager"])

        results = self.searcher.search()
        for r in results.find_by_tag("amp-missed-hb"):
            ts_date = r.get(1)
            amp_id = r.get(2)

            if ts_date not in missed_heartbeats:
                missed_heartbeats[ts_date] = {}

            if amp_id in missed_heartbeats[ts_date]:
                missed_heartbeats[ts_date][amp_id] += 1
            else:
                missed_heartbeats[ts_date][amp_id] = 1

        # sort each amp by occurences
        for ts_date in missed_heartbeats:
            d = utils.sorted_dict(missed_heartbeats[ts_date],
                                  key=lambda e: e[1], reverse=True)
            missed_heartbeats[ts_date] = d

        if missed_heartbeats:
            # not sort by date
            LB_CHECKS["amp-missed-heartbeats"] = \
                utils.sorted_dict(missed_heartbeats)

    def get_lb_failovers(self):
        """Get loadbalancer failover counts."""
        failovers = {}
        expr = (r"^(\S+) \S+ .+ Performing failover for amphora:\s+(.+)")
        d = SearchDef(expr, tag="lb-failover-auto", hint="failover")
        self.searcher.add_search_term(d, self.data_sources["health-manager"])

        expr = (r"^(\S+) \S+ .+ Performing failover for amphora:\s+(.+)")
        d = SearchDef(expr, tag="lb-failover-manual", hint="failover")
        self.searcher.add_search_term(d, self.data_sources["worker"])

        for fo_type in ["auto", "manual"]:
            results = self.searcher.search()
            for r in results.find_by_tag("lb-failover-{}".format(fo_type)):
                ts_date = r.get(1)
                payload = r.get(2)
                payload = yaml.safe_load(payload)
                lb_id = payload.get("load_balancer_id")
                if lb_id is None:
                    continue

                if fo_type not in failovers:
                    failovers[fo_type] = {}

                if ts_date not in failovers[fo_type]:
                    failovers[fo_type][ts_date] = {}

                if lb_id in failovers[fo_type][ts_date]:
                    failovers[fo_type][ts_date][lb_id] += 1
                else:
                    failovers[fo_type][ts_date][lb_id] = 1

        for fo_type in failovers:
            # sort each failover by occurences
            for ts_date in failovers[fo_type]:
                d = utils.sorted_dict(failovers[fo_type][ts_date],
                                      key=lambda e: e[1], reverse=True)
                failovers[fo_type][ts_date] = d

            # now sort the dates
            d = utils.sorted_dict(failovers[fo_type])

        if failovers:
            LB_CHECKS["lb-failovers"] = failovers

    def __call__(self):
        if self.core:
            self.get_lb_failovers()
            self.get_hm_amphora_missed_heartbeats()


def run_checks():
    # gate on whether octavia is installed
    return OctaviaLBChecks(["octavia-common"])


if __name__ == "__main__":
    run_checks()()
    if LB_CHECKS:
        plugin_yaml.save_part({"octavia": LB_CHECKS}, priority=9)
