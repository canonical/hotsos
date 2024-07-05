import re
from functools import cached_property

from hotsos.core.host_helpers import CLIHelper
from hotsos.core.log import log


class UptimeHelper():
    """ Helper to enable querying system uptime. """
    def __init__(self):
        """
        uptime is either expressed in different combinations of days, hours
        and minutes so we determine which format is used to then extract
        the time to present it in a common way.
        """
        # unfortunately sosreports don't have proc/uptime otherwise we would
        # use that.
        self.uptime = CLIHelper().uptime() or ""
        # this needs to take into account the different formats supported by
        # https://gitlab.com/procps-ng/procps/-/blob/newlib/library/uptime.c
        etime_expr = r"(?:([\d:]+)|(\d+\s+\S+,\s+[\d:]+)|(\d+\s+\S+)),"
        expr = rf"\s*[\d:]+\s+up\s+{etime_expr}.+\s+load average:\s+(.+)"
        ret = re.compile(expr).match(self.uptime)
        self.subgroups = {}
        if ret:
            self.subgroups['hour'] = {'value': ret.group(1),
                                      'expr': r'(\d+):(\d+)'}
            self.subgroups['day'] = {'value': ret.group(2),
                                     'expr': r"(\d+)\s+\S+,\s+(\d+):(\d+)"}
            self.subgroups['min'] = {'value': ret.group(3),
                                     'expr': r"(\d+)\s+(\S+)"}
            self.subgroups['loadavg'] = {'value': ret.group(4)}

    @cached_property
    def in_minutes(self):
        """ Total uptime in minutes. """
        if not self.subgroups:
            log.info("uptime not available")
            return None

        if self.subgroups['hour']['value']:
            expr = self.subgroups['hour']['expr']
            ret = re.match(expr, self.subgroups['hour']['value'])
            if ret:
                return (int(ret.group(1)) * 60) + int(ret.group(2))
        elif self.subgroups['day']['value']:
            expr = self.subgroups['day']['expr']
            ret = re.match(expr, self.subgroups['day']['value'])
            if ret:
                count = int(ret.group(1))
                hours = int(ret.group(2))
                mins = int(ret.group(3))
                day_mins = 24 * 60
                total = count * day_mins
                total += hours * 60
                total += mins
                return total
        elif self.subgroups['min']['value']:
            expr = self.subgroups['min']['expr']
            ret = re.match(expr, self.subgroups['min']['value'])
            if ret:
                return int(ret.group(1))

        log.warning("unknown uptime format in %s", self.uptime)
        return 0

    @property
    def in_seconds(self):
        """ Total uptime in seconds. """
        if self.in_minutes:
            return self.in_minutes * 60

        return 0

    @property
    def in_hours(self):
        """ Total uptime in hours. """
        if self.in_minutes:
            return int(self.in_minutes / 60)

        return 0

    def __repr__(self):
        days = int(self.in_hours / 24)
        hours = self.in_hours - days * 24
        minutes = self.in_minutes - (self.in_hours * 60)
        return f"{days}d:{hours}h:{minutes}m"

    @property
    def loadavg(self):
        if self.subgroups:
            return self.subgroups['loadavg']['value']

        return None
