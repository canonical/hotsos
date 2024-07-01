import glob
import os
import re
from datetime import datetime, timezone
from functools import cached_property

import dateutil
import pytz
from dateutil import parser as dateutil_parser
# NOTE: we import direct from searchkit rather than hotsos.core.search to
#       avoid circular dependency issues.
from searchkit import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers import CLIHelper, CLIHelperFile
from hotsos.core.host_helpers.common import ServiceManagerBase
from hotsos.core.log import log
from hotsos.core.utils import sorted_dict


class SystemdService():

    def __init__(self, name, state, has_instances=False):
        self.name = name
        self.state = state
        self.has_instances = has_instances

    @cached_property
    def _tzinfos(self):
        """ Generates timezone name to zone mappings for common timezones.

        See https://dateutil.readthedocs.io/en/stable/parser.html#functions for
        how it is consumed. dateutil needs timezone abbreviated to timezone
        full name mappings in order to be able to parse timestamps with tz
        abbreviations.

        @return: dictionary of name: timezone mappings.
        """
        def fetch():
            for zone in pytz.common_timezones:
                try:
                    tzdate = pytz.timezone(zone).localize(datetime.utcnow(),
                                                          is_dst=None)
                except pytz.NonExistentTimeError:
                    pass
                else:
                    tzinfo = dateutil.tz.gettz(zone)
                    if tzinfo:
                        yield tzdate.tzname(), tzinfo

        return dict(fetch())

    @cached_property
    def start_time(self):
        """ Get most recent start time of this service unit.

        We first look in systemd journal since that should be the fastest and
        if not found (perhaps because service not restarted for a long time)
        we look in service status.

        @returns: datetime.datetime object or None if time not found.
        """
        log.debug("fetching start time for svc %s", self.name)
        cli = CLIHelper()
        # must be in short-iso format e.g. 2023-07-04T00:05:23+0100
        cexpr = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+\d{4})"
                           r"\s+.+: (Started|Starting)")
        journal = cli.journalctl(unit=self.name)
        last = None
        for line in journal:
            ret = cexpr.search(line)
            if ret:
                last = ret.group(1)

        if last:
            return datetime.strptime(last, "%Y-%m-%dT%H:%M:%S%z")

        log.debug("start time not found in journal, trying service status")
        # NOTE: should consider getting service status directly rather than
        #       searching in all but currently do this to have parity with
        #       sosreport.
        fs = FileSearcher(decode_errors='backslashreplace')
        # The following expressions need to take account of control characters
        # that might exist in the output e.g. line can start with '*' or U+25CF
        # Active: active (running) since Wed 2022-02-09 22:38:17 UTC; 17h ago
        seqdef = SequenceSearchDef(
                    start=SearchDef(r'\S+ ({}.service) -'.format(self.name)),
                    body=SearchDef(r"\s+Active: active \(?\S*\)?\s*since "
                                   r"\S{3} (\d{4}-\d{2}-\d{2} "
                                   r"\d{2}:\d{2}:\d{2} [\w\+:-]+);"),
                    end=SearchDef(r'(\S+) \S+.service'),
                    tag='systemd')
        with CLIHelperFile() as cli:
            fs.add(seqdef, path=cli.systemctl_status_all())
            sections = list(fs.run().find_sequence_sections(seqdef).values())
            if len(sections) == 0:
                log.warning("no active status found for %s.service (state=%s)",
                            self.name, self.state)
                return

            if len(sections) > 1:
                log.warning("more than one status found for %s.service",
                            self.name)

            for result in sections[0]:
                if result.tag == seqdef.body_tag:
                    return dateutil_parser.parse(result.get(1),
                                                 tzinfos=self._tzinfos)
        log.debug("no start time identified for svc %s (state=%s)", self.name,
                  self.state)

    @cached_property
    def start_time_secs(self):
        """ Get most recent start time of this service unit in seconds.

        @returns: posix timestamp
        """
        t = self.start_time
        if t is None:
            return 0

        if t.utcoffset() is None:
            t = t.replace(tzinfo=timezone.utc)
        else:
            t = t.astimezone(tz=timezone.utc)

        return t.timestamp()

    @property
    def memory_current_kb(self):
        """ Returns service current memory usage in kbytes.

        See https://www.kernel.org/doc/Documentation/cgroup-v1/memory.txt
        See https://www.kernel.org/doc/Documentation/cgroup-v2.txt
        """
        cgroupv1 = os.path.join(HotSOSConfig.data_root, 'sys/fs/cgroup',
                                "memory/system.slice/{}.service".
                                format(self.name), 'memory.stat')
        cgroupv2 = os.path.join(HotSOSConfig.data_root, 'sys/fs/cgroup',
                                'system.slice', "{}.service".
                                format(self.name), 'memory.current')
        if os.path.exists(cgroupv1):
            total_usage = {}
            fs = FileSearcher()
            fs.add(SearchDef(r'(cache|rss|swap) (\d+)'), path=cgroupv1)
            for result in fs.run().get(cgroupv1, {}):
                total_usage[result.get(1)] = int(result.get(2))

            if len(total_usage) == 0:
                log.warning("failed to identify mem usage info for %s in %s",
                            "{}.service".format(self.name), cgroupv1)

            total = sum(total_usage.values())
            if total == 0:
                return total

            return int(total / 1024)

        # NOTE: memory.current (v2) is assumed not to be an approximation like
        #       memory.usage_in_bytes in v1
        if not os.path.exists(cgroupv2):
            log.warning("service memory info not found at %s", cgroupv2)
            return 0

        with open(cgroupv2) as fd:
            total = int(fd.read())
            if total == 0:
                return total

            return int(total / 1024)

    def __repr__(self):
        return ("name={}, state={}, start_time={}, has_instances={}".
                format(self.name, self.state, self.start_time,
                       self.has_instances))


class SystemdHelper(ServiceManagerBase):
    """ Helper class used to query systemd services. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_unit_files_exprs = {}

    @cached_property
    def _systemctl_list_units(self):
        return CLIHelper().systemctl_list_units()

    @cached_property
    def _ps(self):
        return CLIHelper().ps()

    def _has_unit_instances(self, expr, ignore_exited=True):
        """
        Determine if unit has instances that match the given expression.

        @param expr: expression used to match one or more units in
                     systemctl list-units.
        @param ignore_exited: filter units that are "exited"
        """
        for line in self._systemctl_list_units:
            ret = re.compile(expr).match(line)
            if ret:
                if ignore_exited and ret.group(4) == 'exited':
                    continue

                return True

        return False

    def _unit_files_expr(self, svc_name_expr):
        """
        Returns search expression used to match unit files based in service
        name expression.

        @param svc_name_expr: expression to match service name.
        """
        if svc_name_expr in self._cached_unit_files_exprs:
            return self._cached_unit_files_exprs[svc_name_expr]

        # Add snap prefix/suffixes
        base_expr = r"(?:snap\.)?{}(?:\.daemon)?".format(svc_name_expr)
        # NOTE: we include indirect services (ending with @) so that
        #       we can search for related units later.
        unit_expr = r'^\s*({}@?)\.service\s+(\S+)'.format(base_expr)
        # match entries in systemctl list-unit-files
        self._cached_unit_files_exprs[svc_name_expr] = re.compile(unit_expr)
        return self._cached_unit_files_exprs[svc_name_expr]

    @cached_property
    def services(self):
        """
        Return a dict of identified systemd services and their state.

        Service units are either direct or indirect. We unify these types,
        taking the state of whichever is actually in use i.e. has in-memory
        instances. Enabled units are aggregated but masked units are not so
        that they can be identified and reported.
        """
        _services = {}
        for line in CLIHelper().systemctl_list_unit_files():
            for svc_name_expr in self._service_exprs:
                # check each matched unit file for instances
                ret = self._unit_files_expr(svc_name_expr).match(line)
                if not ret:
                    continue

                unit = ret.group(1)
                state = ret.group(2)
                has_instances = False
                units_expr = r"\*?\s+({})\.service\s+(\S+)\s+(\S+)\s+(\S+)"
                if unit.endswith('@'):
                    # indirect or "template" units can have "instantiated"
                    # units where only the latter represents whether the
                    # unit is in use. If an indirect unit has instantiated
                    # units we use them to represent the state of the
                    # service.
                    units_expr = units_expr.format(unit + r'\S+')
                    unit = unit.partition('@')[0]
                else:
                    units_expr = units_expr.format(unit)

                if state != 'disabled':
                    if self._has_unit_instances(units_expr):
                        has_instances = True
                elif unit in _services:
                    # don't override enabled with disabled
                    continue

                if state == 'indirect' and not has_instances:
                    continue

                if unit in _services:
                    if (_services[unit].state == 'indirect' and
                            _services[unit].has_instances):
                        continue

                _services[unit] = SystemdService(unit, state, has_instances)

        # NOTE: assumes that indirect instances always supersede direct ones
        #       i.e. you can't have both.
        for info in _services.values():
            if info.state == 'indirect':
                info.state = 'enabled'

        return _services

    @property
    def masked_services(self):
        """ Returns a list of masked services. """
        if not self.services:
            return []

        return sorted(self._service_info.get('masked', []))

    def get_services_expanded(self, name):
        _expanded = []
        for line in self._systemctl_list_units:
            expr = r'^\s*({}(@\S*)?)\.service'.format(name)
            ret = re.compile(expr).match(line)
            if ret:
                _expanded.append(ret.group(1))

        if not _expanded:
            _expanded = [name]

        return _expanded

    @cached_property
    def _service_filtered_ps(self):
        """
        For each service get list of processes started by that service and
        get their corresponding binary name from ps.

        Returns list of lines from ps that match the service pids.
        """
        ps_filtered = []
        path = os.path.join(HotSOSConfig.data_root,
                            'sys/fs/cgroup/unified/system.slice')
        if not os.path.exists(path):
            # Seems that this path changed between Ubuntu Focal and Jammy
            # releases.
            path = os.path.join(HotSOSConfig.data_root,
                                'sys/fs/cgroup/system.slice')

        for svc in self.services:
            for svc in self.get_services_expanded(svc):
                _path = os.path.join(path, "{}.service".format(svc),
                                     'cgroup.procs')
                if not os.path.exists(_path):
                    _path = glob.glob(os.path.join(path, 'system-*.slice',
                                                   "{}.service".format(svc),
                                                   'cgroup.procs'))
                    if not _path or not os.path.exists(_path[0]):
                        continue

                    _path = _path[0]

                with open(_path) as fd:
                    for pid in fd:
                        for line in self._ps:
                            if re.match(r'^\S+\s+{}\s+'.format(int(pid)),
                                        line):
                                ps_filtered.append(line)
                                break

        return ps_filtered

    @cached_property
    def processes(self):
        """
        Identify running processes from ps that are associated with resolved
        systemd services. The search pattern used to identify a service is also
        used to match the process binaryc/cmd name.

        Accounts for different types of process cmd path e.g.

        /snap/<name>/1830/<svc>
        /usr/bin/<svc>

        and filter e.g.

        /var/lib/<svc> and /var/log/<svc>

        Returns a dictionary of process names along with the number of each.
        """
        _proc_info = {}
        for line in self._service_filtered_ps:
            for expr in self._service_exprs:
                cmd = self.get_cmd_from_ps_line(line, expr)
                if not cmd:
                    continue

                if cmd in _proc_info:
                    _proc_info[cmd] += 1
                else:
                    _proc_info[cmd] = 1

        return _proc_info

    @property
    def _service_info(self):
        """Return a dictionary of systemd services grouped by state. """
        info = {}
        for svc, obj in sorted_dict(self.services).items():
            state = obj.state
            if state not in info:
                info[state] = []

            info[state].append(svc)

        return info

    @property
    def _process_info(self):
        """Return a list of processes associated with services. """
        return ["{} ({})".format(name, count)
                for name, count in sorted_dict(self.processes).items()]

    @property
    def summary(self):
        """
        Output a dict summary of this class i.e. services, their state and any
        processes run by them.
        """
        return {'systemd': self._service_info,
                'ps': self._process_info}


class ServiceFactory(FactoryBase):
    """
    Factory to dynamically create SystemdService objects for given services.

    Service objects are returned when a getattr() is done on this object using
    the name of the service as the attr name.
    """

    def __getattr__(self, svc):
        log.debug("creating service object for %s", svc)
        return SystemdHelper([svc]).services.get(svc)
