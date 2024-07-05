import re

from hotsos.core.issues import IssuesManager, CephOSDError
from hotsos.core.plugins.storage.ceph import (
    CephChecksBase,
    CephEventCallbackBase,
)
from hotsos.core.ycheck.events import EventHandlerBase

CEPH_ID_FROM_LOG_PATH_EXPR = r'.+ceph-osd\.(\d+)\.log'


class EventCallbackMisc(CephEventCallbackBase):
    event_group = 'ceph'
    event_names = ['heartbeat-no-reply', 'osd-reported-failed',
                   'mon-elections-called', 'superblock-read-error']

    def __call__(self, event):
        if event.name == 'superblock-read-error':
            msg = ('Detected superblock read errors which indicates an OSD '
                   'disk failure or its likely failure in the near future. '
                   'This drive needs to be inspected further using '
                   'sar/smartctl.')
            IssuesManager().add(CephOSDError(msg))
            return None

        key_by_date = event.name == 'heartbeat-no-reply'
        return self.categorise_events(event, key_by_date=key_by_date)


class EventCallbackSlowRequests(CephEventCallbackBase):
    event_group = 'ceph'
    event_names = ['slow-requests']

    def __call__(self, event):
        slow_requests = {}
        for result in sorted(event.results, key=lambda r: r.get(1)):
            date = result.get(1)
            count = result.get(2)
            if date not in slow_requests:
                slow_requests[date] = int(count)
            else:
                slow_requests[date] += int(count)

        return slow_requests


class EventCallbackCRCErrors(CephEventCallbackBase):
    event_group = 'ceph'
    event_names = ['crc-err-bluestore', 'crc-err-rocksdb']

    def __call__(self, event):
        osd_type = event.name.rpartition('_')[2]
        c_expr = re.compile(CEPH_ID_FROM_LOG_PATH_EXPR)
        results = []
        for r in event.results:
            ret = c_expr.match(event.searcher.resolve_source_id(r.source_id))
            if ret:
                key = f"osd.{ret.group(1)}"
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
            if not isinstance(osds, dict):
                continue

            for osd, num_errs in osds.items():
                if num_errs > 3:
                    osd_err_max = max(osd_err_max, num_errs)

                    osds_in_err.add(osd)

        if osds_in_err:
            msg = (f"{len(osds_in_err)} osds ({','.join(osds_in_err)}) "
                   f"found with > 3 {osd_type} crc errors (max={osd_err_max}) "
                   "each within a 24hr period - please investigate")
            IssuesManager().add(CephOSDError(msg))

        return ret


class EventCallbackHeartbeatPings(CephEventCallbackBase):
    event_group = 'ceph'
    event_names = ['long-heartbeat-pings']

    def __call__(self, event):
        c_expr = re.compile(CEPH_ID_FROM_LOG_PATH_EXPR)
        results = []
        for r in event.results:
            ret = c_expr.match(event.searcher.resolve_source_id(r.source_id))
            if ret:
                key = f"osd.{ret.group(1)}"
            else:
                key = None

            results.append({'date': r.get(1), 'key': key})

        return self.categorise_events(event, results=results,
                                      squash_if_none_keys=True)


class CephEventHandler(CephChecksBase, EventHandlerBase):
    event_group = 'ceph'
    summary_part_index = 1

    @property
    def summary(self):
        # mainline all results into summary root
        return self.run()
