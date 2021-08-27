import re

from common import checks
from common.plugins.storage import (
    CephChecksBase,
    CEPH_SERVICES_EXPRS,
)

YAML_PRIORITY = 2


class CephDaemonLogChecks(CephChecksBase, checks.EventChecksBase):

    def __init__(self):
        super().__init__(CEPH_SERVICES_EXPRS,
                         yaml_defs_group='ceph')

    def process_slow_requests(self, results):
        slow_requests = {}
        for result in sorted(results, key=lambda r: r.get(1)):
            date = result.get(1)
            count = result.get(2)
            if date not in slow_requests:
                slow_requests[date] = int(count)
            else:
                slow_requests[date] += int(count)

        return slow_requests

    def get_timings(self, results, group_by_resource=False,
                    resource_osd_from_source=False):
        """
        @param results: list of search results. Each result must contain a
        timestamp as the first group and optional a resource name as a
        second group. If timestamp only we return a list with a count of number
        of times an event occurred per timestamp. If resource is available we
        provide per-resource counts for each timestamp.
        @param group_by_resource: if resource is available group results by
        resource instead of by timestamp.
        @param resource_osd_from_source: extract osd id from search path and
                                         use that as resource.
        """
        info = {}
        c_expr = re.compile(r'.+ceph-osd\.(\d+)\.log')
        for result in sorted(results, key=lambda r: r.get(1)):
            date = result.get(1)
            resource = result.get(2)
            if resource_osd_from_source:
                ret = re.compile(c_expr).match(result.source)
                if ret:
                    resource = "osd.{}".format(ret.group(1))

            if resource:
                if group_by_resource:
                    if resource not in info:
                        info[resource] = {date: 1}
                    else:
                        if date in info[resource]:
                            info[resource][date] += 1
                        else:
                            info[resource][date] = 1
                else:
                    if date not in info:
                        info[date] = {resource: 1}
                    else:
                        if resource in info[date]:
                            info[date][resource] += 1
                        else:
                            info[date][resource] = 1
            else:
                if date not in info:
                    info[date] = 1
                else:
                    info[date] += 1

        return info

    def process_results(self, results):
        """ See defs/events.yaml for definitions. """
        info = {}
        for events in self.event_definitions.values():
            for event in events:
                _results = results.find_by_tag(event)
                ret = None
                if event == "osd-reported-failed":
                    ret = self.get_timings(_results, group_by_resource=True)
                elif event == "mon-elections-called":
                    ret = self.get_timings(_results, group_by_resource=True)
                elif event == "slow-requests":
                    # This one is special since we extract the count from the
                    # search result itself.
                    ret = self.process_slow_requests(_results)
                elif event == "crc-err-bluestore":
                    ret = self.get_timings(_results,
                                           resource_osd_from_source=True)
                elif event == "crc-err-rocksdb":
                    ret = self.get_timings(_results,
                                           resource_osd_from_source=True)
                elif event == "long-heartbeat-pings":
                    ret = self.get_timings(_results,
                                           resource_osd_from_source=True)
                elif event == "heartbeat-no-reply":
                    ret = self.get_timings(_results)

                if ret:
                    if event in info:
                        info[event].update(ret)
                    else:
                        info[event] = ret

        return info

    def __call__(self):
        self.register_search_terms()
        check_results = self.process_results(self.searchobj.search())
        if check_results:
            self._output.update(check_results)
