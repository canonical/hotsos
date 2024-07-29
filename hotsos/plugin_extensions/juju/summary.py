import os
import re
from datetime import datetime, timedelta

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.log import log
from hotsos.core.plugins.juju.common import JujuChecks
from hotsos.core.search import (
    FileSearcher,
    SearchDef,
    SearchConstraintSearchSince,
)
from hotsos.core.utils import sorted_dict
from hotsos.core.search import CommonTimestampMatcher
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class UnitLogInfo():
    """
    Create a tally of log errors and warnings for each unit.
    """

    @staticmethod
    def error_and_warnings():
        log.debug("searching unit logs for errors and warnings")
        c = SearchConstraintSearchSince(ts_matcher_cls=CommonTimestampMatcher)
        searchobj = FileSearcher(constraint=c)
        path = os.path.join(HotSOSConfig.data_root, 'var/log/juju/unit-*.log')
        ts_expr = r"^([\d-]+)\s+([\d:]+)"
        for msg in ['ERROR', 'WARNING']:
            expr = rf'{ts_expr} {msg} (\S+) (\S+):\d+ '
            tag = msg
            hint = msg
            searchobj.add(SearchDef(expr, tag=tag, hint=hint), path)

        results = searchobj.run()
        log.debug("fetching unit log results")
        events = {}
        date_format = CommonTimestampMatcher.DEFAULT_DATETIME_FORMAT
        now = CLIHelper().date(format=f"+{date_format}")
        now = datetime.strptime(now, date_format)

        for tag in ['WARNING', 'ERROR']:
            for result in results.find_by_tag(tag):
                ts_date = result.get(1)
                if HotSOSConfig.event_tally_granularity == 'time':
                    ts_time = result.get(2)
                    # use hours and minutes only
                    ts_time = re.compile(r'(\d+:\d+).+').search(ts_time)[1]
                    key = f"{ts_date}_{ts_time}"
                else:
                    ts_time = '00:00:00'
                    key = ts_date

                # Since juju logs files don't typically get logrotated they
                # may contain a large history of logs so we have to do this to
                # ensure we don't get too much.
                then = datetime.strptime(f"{ts_date} {ts_time}", date_format)
                days = 1
                if HotSOSConfig.use_all_logs:
                    days = HotSOSConfig.max_logrotate_depth

                if then < now - timedelta(days=days):
                    continue

                path = searchobj.resolve_source_id(result.source_id)
                name = re.search(r".+/unit-(\S+).log.*", path).group(1)
                if name not in events:
                    events[name] = {}

                tag = tag.lower()
                if tag not in events[name]:
                    events[name][tag] = {}

                origin = result.get(3)
                origin_child = origin.rpartition('.')[2]
                if origin_child not in events[name][tag]:
                    events[name][tag][origin_child] = {}

                mod = result.get(4)
                if mod not in events[name][tag][origin_child]:
                    events[name][tag][origin_child][mod] = {}

                if key not in events[name][tag][origin_child][mod]:
                    events[name][tag][origin_child][mod][key] = 1
                else:
                    events[name][tag][origin_child][mod][key] += 1

        # ensure consistent ordering of results
        for tag, units in events.items():
            for unit, keys in units.items():
                units[unit] = sorted_dict(keys)

            events[tag] = sorted_dict(units)

        return sorted_dict(events)


class JujuSummary(JujuChecks):
    """ Implementation of Juju summary. """
    summary_part_index = 0

    @summary_entry('machine', get_min_available_entry_index())
    def summary_machine(self):
        if self.machine:
            return self.machine.id

        return "unknown"

    @summary_entry('units', get_min_available_entry_index() + 1)
    def summary_units(self):
        if not self.units:
            return None

        unit_info = {}
        loginfo = UnitLogInfo().error_and_warnings()
        for u in self.units.values():
            name, _, ver = u.name.rpartition('-')
            u_name = f"{name}/{ver}"
            unit_info[u_name] = {}
            if u.repo_info:
                c_name = u.charm_name
                if c_name:
                    unit_info[u_name]['charm'] = {'name': c_name}
                    sha1 = u.repo_info.get('commit')
                    unit_info[u_name]['charm']['repo-info'] = sha1
                    if c_name in self.charms:
                        unit_info[u_name]['charm']['version'] = \
                            self.charms[c_name].version

            if u.name in loginfo:
                unit_info[u_name]['logs'] = loginfo[u.name]

        return unit_info or None
