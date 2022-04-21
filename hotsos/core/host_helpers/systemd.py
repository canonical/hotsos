import os
import glob

import re

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.utils import sorted_dict

SVC_EXPR_TEMPLATES = {
    "absolute": r".+\S+bin/({})(?:\s+.+|$)",
    "snap": r".+\S+\d+/({})(?:\s+.+|$)",
    "relative": r".+\s({})(?:\s+.+|$)",
    }


class ServiceChecksBase(object):
    """This class should be used by any plugin that wants to identify
    and check the status of running services."""

    def __init__(self, service_exprs, *args, ps_allow_relative=True,
                 **kwargs):
        """
        @param service_exprs: list of python.re expressions used to match a
        service name.
        @param ps_allow_relative: whether to allow commands to be identified
                                  from ps as not run using an absolute binary
                                  path e.g. mycmd as opposed to /bin/mycmd.
        """
        super().__init__(*args, **kwargs)
        self.ps_allow_relative = ps_allow_relative
        self._processes = {}
        self._service_info = {}
        self.service_exprs = set(service_exprs)

    def _get_systemd_units(self, expr):
        """
        Search systemd unit instances.

        @param expr: expression used to match one or more units in --list-units
        """
        units = []
        for line in CLIHelper().systemctl_list_units():
            ret = re.compile(expr).match(line)
            if ret:
                units.append(ret.group(1))

        return units

    @property
    def services(self):
        """
        Return a dict of identified systemd services and their state.

        Services are represented as either direct or indirect units and
        typically use one or the other. We homongenise these to present state
        based on the one we think is being used. Enabled units are aggregated
        but masked units are not so that they can be identified and reported.
        """
        if self._service_info:
            return self._service_info

        svc_info = {}
        indirect_svc_info = {}
        for line in CLIHelper().systemctl_list_unit_files():
            for expr in self.service_exprs:
                # Add snap prefix/suffixes
                base_expr = r"(?:snap\.)?{}(?:\.daemon)?".format(expr)
                # NOTE: we include indirect services (ending with @) so that
                #       we can search for related units later.
                unit_expr = r'^\s*({}(?:@\S*)?)\.service'.format(base_expr)
                # match entries in systemctl list-unit-files
                unit_files_expr = r'{}\s+(\S+)'.format(unit_expr)

                ret = re.compile(unit_files_expr).match(line)
                if ret:
                    unit = ret.group(1)
                    state = ret.group(2)
                    if unit.endswith('@'):
                        # indirect or "template" units can have "instantiated"
                        # units where only the latter represents whether the
                        # unit is in use. If an indirect unit has instanciated
                        # units we use them to represent the state of the
                        # service.
                        unit_svc_expr = r"\s+({}\d*)".format(unit)
                        unit = unit.partition('@')[0]
                        if self._get_systemd_units(unit_svc_expr):
                            state = 'enabled'

                        indirect_svc_info[unit] = state
                    else:
                        svc_info[unit] = state

        if indirect_svc_info:
            # Allow indirect unit info to override given certain conditions
            for unit, state in indirect_svc_info.items():
                if unit in svc_info:
                    if state == 'disabled' or svc_info[unit] == 'enabled':
                        continue

                svc_info[unit] = state

        self._service_info = svc_info
        return self._service_info

    @property
    def masked_services(self):
        """ Returns a list of masked services. """
        if not self.services:
            return []

        return self.service_info.get('masked', [])

    def get_process_cmd_from_line(self, line, expr):
        for expr_type, expr_tmplt in SVC_EXPR_TEMPLATES.items():
            if expr_type == 'relative' and not self.ps_allow_relative:
                continue

            ret = re.compile(expr_tmplt.format(expr)).match(line)
            if ret:
                svc = ret.group(1)
                log.debug("matched process %s with %s expr", svc,
                          expr_type)
                return svc

    def get_services_expanded(self, name):
        _expanded = []
        for line in CLIHelper().systemctl_list_units():
            expr = r'^\s*({}(@\S*)?)\.service'.format(name)
            ret = re.compile(expr).match(line)
            if ret:
                _expanded.append(ret.group(1))

        if not _expanded:
            _expanded = [name]

        return _expanded

    @property
    def service_filtered_ps(self):
        ps_filtered = []
        path = os.path.join(HotSOSConfig.DATA_ROOT,
                            'sys/fs/cgroup/unified/system.slice')
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

                pids = []
                with open(_path) as fd:
                    for line in fd:
                        pids.append(int(line))

                for line in CLIHelper().ps():
                    for pid in pids:
                        if " {} ".format(pid) in line:
                            ps_filtered.append(line)

        return ps_filtered

    @property
    def processes(self):
        """
        Identify running processes from ps that are associated with identified
        systemd services. The same search pattern used for identifying systemd
        services is used here.

        Returns a dictionary of process names along with the number of each.
        """
        if self._processes:
            return self._processes

        for line in self.service_filtered_ps:
            for expr in self.service_exprs:
                """
                look for running process with this name.
                We need to account for different types of process binary e.g.

                /snap/<name>/1830/<svc>
                /usr/bin/<svc>

                and filter e.g.

                /var/lib/<svc> and /var/log/<svc>
                """
                cmd = self.get_process_cmd_from_line(line, expr)
                if cmd:
                    if cmd not in self._processes:
                        self._processes[cmd] = 0

                    self._processes[cmd] += 1

        return self._processes

    @property
    def service_info(self):
        """Return a dictionary of systemd services grouped by state. """
        info = {}
        for svc, state in sorted_dict(self.services).items():
            if state not in info:
                info[state] = []

            info[state].append(svc)

        return info

    @property
    def process_info(self):
        """Return a list of processes associated with services. """
        return ["{} ({})".format(name, count)
                for name, count in sorted_dict(self.processes).items()]
