import re

from hotsos.core.issues import IssuesManager, CephOSDError
from hotsos.core.ycheck.events import CallbackHelper
from hotsos.core.plugins.storage.ceph import (
    CEPH_LOGS_TS_EXPR,
    CephEventChecksBase,
)
from hotsos.core.search import (
    FileSearcher,
    SearchConstraintSearchSince,
)
EVENTCALLBACKS = CallbackHelper()
CEPH_ID_FROM_LOG_PATH_EXPR = r'.+ceph-osd\.(\d+)\.log'


class CephDaemonLogChecks(CephEventChecksBase):

    def __init__(self):
        c = SearchConstraintSearchSince(exprs=[CEPH_LOGS_TS_EXPR])
        super().__init__(EVENTCALLBACKS, yaml_defs_group='ceph',
                         searchobj=FileSearcher(constraint=c))

    @EVENTCALLBACKS.callback(event_group='ceph')
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

    @EVENTCALLBACKS.callback(event_group='ceph')
    def osd_reported_failed(self, event):
        return self.categorise_events(event, key_by_date=False)

    @EVENTCALLBACKS.callback(event_group='ceph')
    def mon_elections_called(self, event):
        return self.categorise_events(event, key_by_date=False)

    def _get_crc_errors(self, event, osd_type):
        if not event.results:
            return

        c_expr = re.compile(CEPH_ID_FROM_LOG_PATH_EXPR)
        results = []
        for r in event.results:
            ret = c_expr.match(self.searchobj.resolve_source_id(r.source_id))
            if ret:
                key = "osd.{}".format(ret.group(1))
            else:
                key = None

            results.append({'date': r.get(1), 'key': key})

        ret = self.categorise_events(event, results=results,
                                     squash_if_none_keys=True)

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

    @EVENTCALLBACKS.callback(event_group='ceph')
    def crc_err_bluestore(self, event):
        return self._get_crc_errors(event, 'bluestore')

    @EVENTCALLBACKS.callback(event_group='ceph')
    def crc_err_rocksdb(self, event):
        return self._get_crc_errors(event, 'rocksdb')

    @EVENTCALLBACKS.callback(event_group='ceph')
    def long_heartbeat_pings(self, event):
        c_expr = re.compile(CEPH_ID_FROM_LOG_PATH_EXPR)
        results = []
        for r in event.results:
            ret = c_expr.match(self.searchobj.resolve_source_id(r.source_id))
            if ret:
                key = "osd.{}".format(ret.group(1))
            else:
                key = None

            results.append({'date': r.get(1), 'key': key})

        return self.categorise_events(event, results=results,
                                      squash_if_none_keys=True)

    @EVENTCALLBACKS.callback(event_group='ceph')
    def heartbeat_no_reply(self, event):
        return self.categorise_events(event)

    @EVENTCALLBACKS.callback(event_group='ceph')
    def superblock_read_error(self, event):  # pylint: disable=W0613
        msg = ('Detected superblock read errors which indicates an OSD disk '
               'failure or its likely failure in the near future. This '
               'drive needs to be inspected further using sar/smartctl.')
        IssuesManager().add(CephOSDError(msg))
