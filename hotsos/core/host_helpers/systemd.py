from datetime import datetime
import os
import glob

import re

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.host_helpers.common import ServiceManagerBase
from hotsos.core.utils import cached_property, sorted_dict


class SystemdService(object):

    def __init__(self, name, state, has_instances=False):
        self.name = name
        self.state = state
        self.has_instances = has_instances

    @cached_property
    def start_time(self):
        """ Get most recent start time of this service unit.

        @returns: datetime.datetime object or None if time not found.
        """
        log.debug("fetching start time for svc %s", self.name)
        # must be in short-iso format
        cexpr = re.compile(r"^(([0-9-]+)T[\d:]+\+[\d]+)\s+.+: "
                           "(Started|Starting) .+")
        journal = CLIHelper().journalctl(unit=self.name)
        last = None
        for line in journal:
            ret = cexpr.search(line)
            if ret:
                last = ret.group(1)

        if last:
            return datetime.strptime(last, "%Y-%m-%dT%H:%M:%S%z")
        else:
            log.debug("no start time identified for svc %s", self.name)

    @cached_property
    def start_time_secs(self):
        """ Get most recent start time of this service unit in seconds.

        @returns: posix timestamp
        """
        t = self.start_time
        if t is None:
            return 0

        return t.timestamp()

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
    def services(self):  # pylint: disable=W0236
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
    def processes(self):  # pylint: disable=W0236
        """
        Identify running processes from ps that are associated with resolved
        systemd services. The search pattern used to identify a service is also
        used to match the process binary name.

        Returns a dictionary of process names along with the number of each.
        """
        _proc_info = {}
        for line in self._service_filtered_ps:
            for expr in self._service_exprs:
                """
                look for running process with this name.
                We need to account for different types of process binary e.g.

                /snap/<name>/1830/<svc>
                /usr/bin/<svc>

                and filter e.g.

                /var/lib/<svc> and /var/log/<svc>
                """
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
