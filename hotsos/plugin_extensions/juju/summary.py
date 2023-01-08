import os
import re

from datetime import datetime, timedelta

from hotsos.core.log import log
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.juju.common import (
    JujuChecksBase,
    JUJU_UNIT_LOGS_TS_EXPR,
)
from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.search import FileSearcher, SearchDef
from hotsos.core.search.constraints import SearchConstraintSearchSince
from hotsos.core.utils import sorted_dict


class UnitLogInfo(object):
    """
    Create a tally of log errors and warnings for each unit.
    """

    def error_and_warnings(self):
        log.debug("searching unit logs for errors and warnings")
        c = SearchConstraintSearchSince(exprs=[JUJU_UNIT_LOGS_TS_EXPR])
        searchobj = FileSearcher(constraint=c)
        path = os.path.join(HotSOSConfig.data_root, 'var/log/juju/unit-*.log')
        for msg in ['ERROR', 'WARNING']:
            expr = (r'{} {} .+\.juju-log (\S+):\d+ '.
                    format(JUJU_UNIT_LOGS_TS_EXPR, msg))
            tag = msg
            hint = msg
            searchobj.add_search_term(SearchDef(expr, tag=tag, hint=hint),
                                      path)

        results = searchobj.search()
        log.debug("fetching unit log results")
        events = {}
        date_format = '%Y-%m-%d %H:%M:%S'
        now = CLIHelper().date(format="+{}".format(date_format))
        now = datetime.strptime(now, date_format)

        for tag in ['WARNING', 'ERROR']:
            for result in results.find_by_tag(tag):
                ts_date = result.get(1)
                if HotSOSConfig.event_tally_granularity == 'time':
                    ts_time = result.get(2)
                    # use hours and minutes only
                    ts_time = re.compile(r'(\d+:\d+).+').search(ts_time)[1]
                    key = "{}_{}".format(ts_date, ts_time)
                else:
                    ts_time = '00:00:00'
                    key = ts_date

                # Since juju logs files don't typically get logrotated they
                # may contain a large history of logs so we have to do this to
                # ensure we don't get too much.
                if not HotSOSConfig.allow_constraints_for_unverifiable_logs:
                    then = datetime.strptime("{} {}".format(ts_date, ts_time),
                                             date_format)
                    days = 1
                    if HotSOSConfig.use_all_logs:
                        days = HotSOSConfig.max_logrotate_depth

                    if then < now - timedelta(days=days):
                        continue

                name = re.search(r".+/unit-(\S+).log.*",
                                 result.source).group(1)
                if name not in events:
                    events[name] = {}

                tag = tag.lower()
                if tag not in events[name]:
                    events[name][tag] = {}

                mod = result.get(3)
                if mod not in events[name][tag]:
                    events[name][tag][mod] = {}

                if key not in events[name][tag][mod]:
                    events[name][tag][mod][key] = 1
                else:
                    events[name][tag][mod][key] += 1

        # ensure consistent ordering of results
        for tag, units in events.items():
            for unit, keys in units.items():
                units[unit] = sorted_dict(keys)

            events[tag] = sorted_dict(units)

        return sorted_dict(events)


class JujuSummary(JujuChecksBase):

    @idx(0)
    def __summary_services(self):
        if self.systemd.services:
            return self.systemd.summary

    @idx(1)
    def __summary_version(self):
        if self.machine:
            return self.machine.version
        else:
            return "unknown"

    @idx(2)
    def __summary_machine(self):
        if self.machine:
            return self.machine.id
        else:
            return "unknown"

    @idx(3)
    def __summary_charms(self):
        if self.charms:
            charms = ["{}-{}".format(c.name, c.version) for c in self.charms]
            return sorted(charms)

    @idx(4)
    def __summary_units(self):
        unit_info = {}
        if self.units:
            loginfo = UnitLogInfo().error_and_warnings()
            unit_info['local'] = []
            for u in self.units:
                unit_info['local'].append(u.name)
                if u.repo_info:
                    if 'repo-info' not in unit_info:
                        unit_info['repo-info'] = {}

                    sha1 = u.repo_info.get('commit')
                    unit_info['repo-info'][u.name] = sha1

                if u.name in loginfo:
                    if 'logs' not in unit_info:
                        unit_info['logs'] = {}

                    unit_info['logs'][u.name] = loginfo[u.name]

        # NOTE: consider removing this as it no longer has much purpose.
        if self.nonlocal_units:
            unit_info['lxd'] = sorted([u.name for u in self.nonlocal_units])

        if unit_info:
            return unit_info
