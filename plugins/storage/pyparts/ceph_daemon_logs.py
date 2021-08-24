from common import checks
from common.plugins.storage import (
    CephChecksBase,
    CEPH_SERVICES_EXPRS,
)

YAML_PRIORITY = 2


class CephDaemonLogChecks(CephChecksBase, checks.EventChecksBase):

    def __init__(self):
        super().__init__(CEPH_SERVICES_EXPRS,
                         yaml_defs_label='ceph')

    def process_slow_requests(self, results):
        slow_requests = {}
        for result in sorted(results, key=lambda r: r.get(1)):
            date = result.get(1)
            count = result.get(2)
            if date not in slow_requests:
                slow_requests[date] = int(count)
            else:
                slow_requests[date] += int(count)

        if slow_requests:
            return {"slow-requests": slow_requests}

    def get_results_timings(self, results, output_key,
                            group_by_resource=False):
        """
        @param results: list of search results. Each result must contain a
        timestamp as the first group and optional a resource name as a
        second group. If timestamp only we return a list with a count of number
        of times an event occurred per timestamp. If resource is available we
        provide per-resource counts for each timestamp.
        @param group_by_resource: if resource is available group results by
        resource instead of by timestamp.
        """
        info = {}
        for result in sorted(results, key=lambda r: r.get(1)):
            date = result.get(1)
            resource = result.get(2)
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

        if info:
            return {output_key: info}

    def process_results(self, results):
        """ See defs/events.yaml for definitions. """
        info = {}
        for defs in self.event_definitions.values():
            for label in defs:
                _results = results.find_by_tag(label)
                if label == "report-failed":
                    ret = self.get_results_timings(_results,
                                                   'osd-reported-failed',
                                                   group_by_resource=True)
                elif label == "mon-elections":
                    ret = self.get_results_timings(_results,
                                                   'mon-elections-called',
                                                   group_by_resource=True)
                elif label == "slow-requests":
                    # This one is special since we extract the count from the
                    # search result itself.
                    ret = self.process_slow_requests(_results)
                elif label == "crc-err-bluestore":
                    ret = self.get_results_timings(_results,
                                                   'crc-err-bluestore')
                elif label == "crc-err-rocksdb":
                    ret = self.get_results_timings(_results,
                                                   'crc-err-rocksdb')
                elif label == "long-heartbeat":
                    ret = self.get_results_timings(_results,
                                                   'long-heartbeat-pings')
                elif label == "heartbeat-no-reply":
                    ret = self.get_results_timings(_results,
                                                   'heartbeat-no-reply')
                if ret:
                    info.update(ret)

        return info

    def __call__(self):
        self.register_search_terms()
        check_results = self.process_results(self.searchobj.search())
        if check_results:
            self._output.update(check_results)
