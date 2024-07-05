import os
from datetime import timedelta
from functools import cached_property

from searchkit import (   # noqa: F403,F401, pylint: disable=W0611
    FileSearcher as _FileSearcher,
    ResultFieldInfo,
    SearchDef,
    SequenceSearchDef,
)
from searchkit.constraints import (
    TimestampMatcherBase,
    SearchConstraintSearchSince as _SearchConstraintSearchSince
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper, UptimeHelper
from hotsos.core.log import log


class FileSearcher(_FileSearcher):
    """
    Custom representation of searchkit FilesSearcher that sets some parameters
    based on HotSOSConfig that we want to apply to all use cases.
    """
    def __init__(self, *args, **kwargs):
        if HotSOSConfig.use_all_logs:
            max_logrotate_depth = HotSOSConfig.max_logrotate_depth
        else:
            max_logrotate_depth = 1

        super().__init__(*args,
                         max_parallel_tasks=HotSOSConfig.max_parallel_tasks,
                         max_logrotate_depth=max_logrotate_depth,
                         **kwargs)


class SearchConstraintSearchSince(_SearchConstraintSearchSince):
    """
    Custom representation of searchkit SearchConstraintSearchSince that
    automatically applies global log history limiting.
    """
    def __init__(self, *args, **kwargs):
        if 'days' not in kwargs and 'hours' not in kwargs:
            days = 1
            if HotSOSConfig.use_all_logs:
                days = HotSOSConfig.max_logrotate_depth

            kwargs['days'] = days

        current_date = CLIHelper().date(format='+%Y-%m-%d %H:%M:%S')
        if not current_date or not isinstance(current_date, str):
            log.error("current date '%s' being provided to search "
                      "constraints is not valid.", current_date)
            return

        super().__init__(*args, current_date=current_date, **kwargs)

    def apply_to_line(self, *args, **kwargs):
        if not os.path.isdir(os.path.join(HotSOSConfig.data_root,
                                          'sos_commands')):
            log.info("skipping line constraint since data_root is not a "
                     "sosreport therefore files may be changing")
            return True

        return super().apply_to_line(*args, **kwargs)

    def apply_to_file(self, *args, **kwargs):
        if not os.path.isdir(os.path.join(HotSOSConfig.data_root,
                                          'sos_commands')):
            log.info("skipping file constraint since data_root is not a "
                     "sosreport therefore files may be changing")
            return 0

        return super().apply_to_file(*args, **kwargs)


class CommonTimestampMatcher(TimestampMatcherBase):
    """
    This class must support regex patterns to match any kind of timestamp that
    we would expect to find. When a plugin results in the search of file
    (typically log files) that contain timestamps it is necessary to ensure
    the patterns in this class support matching those timestamps in order for
    search constraints to work.

    TODO: timestamps typically use an RFC format so we should brand them
          as such here.
    """
    MONTH_MAP = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5,
                 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10,
                 'nov': 11, 'dec': 12}

    @cached_property
    def _current_year(self):
        return CLIHelper().date(format='+%Y')

    @property
    def year(self):
        """ Needed for kernlog which has no year group. """
        try:
            return self.result.group('year')
        except IndexError:
            pass

        return self._current_year

    @property
    def month(self):
        """ Needed for kernlog which has a string month. """
        try:
            return int(self.result.group('month'))
        except ValueError:
            pass

        _month = self.result.group('month').lower()
        try:
            return self.MONTH_MAP[_month[:3]]
        except KeyError:
            log.exception("could not establish month integer from '%s'",
                          _month)

        return None

    @property
    def patterns(self):
        """
        This needs to contain timestamp patterns for any/all types of file
        we want to analyse where SearchConstraintsSince is to be applied.
        """
        # should match plugins.openstack.openstack.OpenstackDateTimeMatcher
        openstack = (r'^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})+\s+'
                     r'(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d+)')
        # since they are identical we wont add but leaving in case we want to.
        # edit later.
        # juju = openstack
        # should match plugins.storage.ceph.CephDateTimeMatcher
        ceph = (r'^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[\sT]'
                r'(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d+)')
        # since they are identical we wont add but leaving in case we want to
        # edit later.
        # openvswitch = ceph
        kernlog = (r'^(?P<month>\w{3,5})\s+(?P<day>\d{1,2})\s+'
                   r'(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})')
        return [openstack, ceph, kernlog]


class ExtraSearchConstraints():
    """
    Provides a way to apply constraints to search results that are not yet
    natively supported by searchkit.
    """

    @classmethod
    def _get_datetime_from_result(cls, result):
        """
        This attempts to create a datetime object from a timestamp (usually
        from a log file) extracted from a search result. If it is not able
        to do so it will return None. The normal expectation is that two search
        result groups be available at index 1 and 2 but if only 1 is valid it
        will be used a fallback.
        """
        ts = result.get(1)
        ts = f"{ts} {result.get(2) or '00:00:00'}"

        ts_matcher = CommonTimestampMatcher(ts)
        if not ts_matcher.matched:
            log.warning("failed to parse timestamp string '%s' (num_group=%s) "
                        "- returning None", ts, len(result))
            return None

        return ts_matcher.strptime

    @classmethod
    def filter_by_period(cls, results, period_hours):
        """ Return the most recent period_hours worth of results. """
        if not period_hours:
            log.debug("period filter not specified - skipping")
            return results

        log.debug("applying search filter (period_hours=%s)", period_hours)

        _results = []
        for r in results:
            ts = cls._get_datetime_from_result(r)
            if ts:
                _results.append((ts, r))

        results = []
        last = None

        for r in sorted(_results, key=lambda i: i[0], reverse=True):
            if last is None:
                last = r[0]
            elif r[0] < last - timedelta(hours=period_hours):
                break

            results.append(r)

        log.debug("%s results remain after applying filter", len(results))
        return [r[1] for r in results]

    def apply(self, results, search_period_hours=None, min_results=None):
        if results:
            results = self.filter_by_period(results, search_period_hours)

        if min_results is None:
            return results

        count = len(results)
        if count < min_results:
            log.debug("search does not have enough matches (%s) to "
                      "satisfy min of %s", count, min_results)
            return []

        log.debug("applying extra search constraints reduced results from %s "
                  "to %s", count, len(results))
        return results


def create_constraint(search_result_age_hours=None,
                      min_hours_since_last_boot=None):
    """
    Create a SearchConstraintSearchSince object if necessary (if one of
    search_result_age_hours or min_hours_since_last_boot is not None).
    """
    if not any([search_result_age_hours, min_hours_since_last_boot]):
        return None

    uptime_etime_hours = UptimeHelper().in_hours
    hours = search_result_age_hours
    if not hours:
        hours = max(uptime_etime_hours - min_hours_since_last_boot, 0)
    elif min_hours_since_last_boot > 0:
        hours = min(hours,
                    max(uptime_etime_hours - min_hours_since_last_boot, 0))

    return SearchConstraintSearchSince(
                                     ts_matcher_cls=CommonTimestampMatcher,
                                     hours=hours)
