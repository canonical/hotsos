#!/usr/bin/python3
import os

from ceph_common import (
    CephChecksBase,
    CEPH_SERVICES_EXPRS,
)
from common import (
    constants,
    searchtools,
    plugin_yaml,
)


CEPH_LOGS = "var/log/ceph/"
DAEMON_INFO = {}


class CephDaemonLogChecks(CephChecksBase):

    def process_osd_failure_reports(self):
        reported_failed = {}
        for result in sorted(self.results.find_by_tag("osd-reported-failed"),
                             key=lambda r: r.get(1)):
            date = result.get(1)
            failed_osd = result.get(2)
            if failed_osd not in reported_failed:
                reported_failed[failed_osd] = {date: 1}
            else:
                if date in reported_failed[failed_osd]:
                    reported_failed[failed_osd][date] += 1
                else:
                    reported_failed[failed_osd][date] = 1

        if reported_failed:
            DAEMON_INFO["osd-reported-failed"] = reported_failed

    def process_mon_elections(self):
        elections_called = {}
        for result in sorted(self.results.find_by_tag("mon-election-called"),
                             key=lambda r: r.get(1)):
            date = result.get(1)
            calling_mon = result.get(2)
            if calling_mon not in elections_called:
                elections_called[calling_mon] = {date: 1}
            else:
                if date in elections_called[calling_mon]:
                    elections_called[calling_mon][date] += 1
                else:
                    elections_called[calling_mon][date] = 1

        if elections_called:
            DAEMON_INFO["mon-elections-called"] = elections_called

    def process_slow_requests(self):
        slow_requests = {}
        for result in sorted(self.results.find_by_tag("slow-requests"),
                             key=lambda r: r.get(1)):
            date = result.get(1)
            count = result.get(2)
            if date not in slow_requests:
                slow_requests[date] = int(count)
            else:
                slow_requests[date] += int(count)

        if slow_requests:
            DAEMON_INFO["slow-requests"] = slow_requests

    def process_crc_bluestore(self):
        crc_error = {}
        for result in sorted(self.results.find_by_tag("crc-err-bluestore"),
                             key=lambda r: r.get(1)):
            date = result.get(1)
            if date not in crc_error:
                crc_error[date] = 1
            else:
                crc_error[date] += 1

        if crc_error:
            DAEMON_INFO["crc-err-bluestore"] = crc_error

    def process_crc_rocksdb(self):
        crc_error = {}
        for result in sorted(self.results.find_by_tag("crc-err-rocksdb"),
                             key=lambda r: r.get(1)):
            date = result.get(1)
            if date not in crc_error:
                crc_error[date] = 1
            else:
                crc_error[date] += 1

        if crc_error:
            DAEMON_INFO["crc-err-rocksdb"] = crc_error

    def process_long_heartbeat(self):
        long_heartbeats = {}
        for result in sorted(self.results.find_by_tag("long-heartbeat"),
                             key=lambda r: r.get(1)):
            date = result.get(1)
            if date not in long_heartbeats:
                long_heartbeats[date] = 1
            else:
                long_heartbeats[date] += 1

        if long_heartbeats:
            DAEMON_INFO["long-heartbeat-pings"] = long_heartbeats

    def process_heartbeat_no_reply(self):
        no_replies = {}
        for result in sorted(self.results.find_by_tag("heartbeat-no-reply"),
                             key=lambda r: r.get(1)):
            date = result.get(1)
            remote_osd = result.get(2)
            if date not in no_replies:
                no_replies[date] = {}
            if remote_osd not in no_replies[date]:
                no_replies[date][remote_osd] = 1
            else:
                no_replies[date][remote_osd] += 1

        if no_replies:
            DAEMON_INFO["heartbeat-no-reply"] = no_replies

    def __call__(self):
        super().__call__()
        data_source = os.path.join(constants.DATA_ROOT, CEPH_LOGS, 'ceph*.log')
        if constants.USE_ALL_LOGS:
            data_source = "{}*".format(data_source)

        s = searchtools.FileSearcher()

        term = (r"^([0-9-]+) \S+ .+ (osd.[0-9]+) reported failed "
                r"by osd.[0-9]+")
        s.add_search_term(term, data_source, tag="osd-reported-failed",
                          hint="reported failed")

        term = (r"^([0-9-]+) \S+ .+ (mon.\S+) calling monitor "
                r"election")
        s.add_search_term(term, data_source, tag="mon-election-called",
                          hint="calling monitor election")

        term = (r"^([0-9-]+) \S+ .+ ([0-9]+) slow requests are blocked "
                r".+ \(REQUEST_SLOW\)")
        s.add_search_term(term, data_source, tag="slow-requests",
                          hint="REQUEST_SLOW")

        s.add_search_term(r"^([0-9-]+) .+ _verify_csum bad .+",
                          data_source, tag="crc-err-bluestore",
                          hint="_verify_csum")

        s.add_search_term(r".+ ceph_abort_msg\(\"(block checksum mismatch).+",
                          data_source, tag="crc-err-rocksdb",
                          hint="block checksum mismatch")

        term = (r"^([0-9-]+) \S+ .+ Long heartbeat ping times on \S+ "
                "interface seen, longest is ([0-9.]+) msec.+")
        s.add_search_term(term, data_source, tag="long-heartbeat",
                          hint="Long heartbeat ping")

        term = (r"^([0-9-]+) \S+ \S+ \S+ osd.[0-9]+ .+ heartbeat_check: no "
                "reply from [0-9.:]+ (osd.[0-9]+)")
        s.add_search_term(term, data_source,
                          tag="heartbeat-no-reply", hint="heartbeat_check")

        self.results = s.search()
        self.process_osd_failure_reports()
        self.process_mon_elections()
        self.process_slow_requests()
        self.process_crc_bluestore()
        self.process_crc_rocksdb()
        self.process_long_heartbeat()
        self.process_heartbeat_no_reply()


def get_ceph_daemon_log_checker():
    # Do this way to make it easier to write unit tests.
    return CephDaemonLogChecks(CEPH_SERVICES_EXPRS)


if __name__ == "__main__":
    get_ceph_daemon_log_checker()()
    if DAEMON_INFO:
        DAEMON_INFO = {"daemon-events": DAEMON_INFO}
        plugin_yaml.dump(DAEMON_INFO)
