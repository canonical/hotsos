import re

from hotsos.core.issues import IssuesManager, CephOSDError
from hotsos.core.ycheck import CallbackHelper
from hotsos.core.plugins.storage.ceph import CephEventChecksBase
from hotsos.core.searchtools import FileSearcher

EVENTCALLBACKS = CallbackHelper()


class CephDaemonLogChecks(CephEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='ceph',
                         searchobj=FileSearcher(),
                         callback_helper=EVENTCALLBACKS)

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
        if not results:
            return

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

    @EVENTCALLBACKS.callback()
    def slow_requests(self, event):
        slow_requests = {}
        for result in sorted(event.results, key=lambda r: r.get(1)):
            date = result.get(1)
            count = result.get(2)
            if date not in slow_requests:
                slow_requests[date] = int(count)
            else:
                slow_requests[date] += int(count)

        return slow_requests

    @EVENTCALLBACKS.callback()
    def osd_reported_failed(self, event):
        return self.get_timings(event.results,
                                group_by_resource=True)

    @EVENTCALLBACKS.callback()
    def mon_elections_called(self, event):
        return self.get_timings(event.results,
                                group_by_resource=True)

    def _get_crc_errors(self, results, osd_type):
        if results:
            ret = self.get_timings(results, resource_osd_from_source=True)

            # If on any particular day there were > 3 crc errors for a
            # particular osd we raise an issue since that indicates they are
            # likely to reflect a real problem.
            osds_in_err = set()
            osd_err_max = 0
            # ret is keyed by day
            for osds in ret.values():
                # If we were unable to glean the osd id from the search results
                # this will not be a dict so skip.
                if type(osds) != dict:
                    continue

                for osd, num_errs in osds.items():
                    if num_errs > 3:
                        if num_errs > osd_err_max:
                            osd_err_max = num_errs

                        osds_in_err.add(osd)

            if osds_in_err:
                msg = ("{} osds ({}) found with > 3 {} crc errors (max={}) "
                       "each within a 24hr period - please investigate".
                       format(len(osds_in_err), ','.join(osds_in_err),
                              osd_type, osd_err_max))
                IssuesManager().add(CephOSDError(msg))

            return ret

    @EVENTCALLBACKS.callback()
    def crc_err_bluestore(self, event):
        return self._get_crc_errors(event.results, 'bluestore')

    @EVENTCALLBACKS.callback()
    def crc_err_rocksdb(self, event):
        return self._get_crc_errors(event.results, 'rocksdb')

    @EVENTCALLBACKS.callback()
    def long_heartbeat_pings(self, event):
        return self.get_timings(event.results,
                                resource_osd_from_source=True)

    @EVENTCALLBACKS.callback()
    def heartbeat_no_reply(self, event):
        return self.get_timings(event.results)

    @EVENTCALLBACKS.callback()
    def superblock_read_error(self, event):  # pylint: disable=W0613
        msg = ('Detected superblock read errors which indicates an OSD disk '
               'failure or its likely failure in the near future. This '
               'drive needs to be inspected further using sar/smartctl.')
        IssuesManager().add(CephOSDError(msg))
