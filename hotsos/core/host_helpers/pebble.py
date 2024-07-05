import re
from functools import cached_property

from hotsos.core.log import log
from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.host_helpers.common import ServiceManagerBase
from hotsos.core.utils import sorted_dict


class PebbleService():

    def __init__(self, name, state):
        self.name = name
        self.state = state

    def __repr__(self):
        return f"name={self.name}, state={self.state}"


class PebbleHelper(ServiceManagerBase):
    """ Helper class used to query pebble services. """

    @cached_property
    def services(self):
        """ Return a dict of identified pebble services and their state. """
        _services = {}
        for line in CLIHelper().pebble_services():
            for svc_name_expr in self._service_exprs:
                _expr = rf"({svc_name_expr})\s+\S+\s+(\S+)\s+.*"
                ret = re.compile(_expr).match(line)
                if not ret:
                    continue

                name = ret.group(1)
                _services[name] = PebbleService(name=name, state=ret.group(2))

        return _services

    @cached_property
    def processes(self):
        """
        Identify running processes from ps that are associated with resolved
        pebble services.  The search pattern used to identify a service is also
        used to match the process binary/cmd name.

        Accounts for different types of process cmd path e.g.

        /snap/<name>/1830/<svc>
        /usr/bin/<svc>

        and filter e.g.

        /var/lib/<svc> and /var/log/<svc>

        Returns a dictionary of process names along with the number of each.
        """
        _proc_info = {}
        for line in CLIHelper().ps():
            for expr in self._service_exprs:
                cmd = self.get_cmd_from_ps_line(line, expr)
                if cmd:
                    if cmd in _proc_info:
                        _proc_info[cmd] += 1
                    else:
                        _proc_info[cmd] = 1

        return _proc_info

    @property
    def _service_info(self):
        """Return a dictionary of pebble services grouped by state. """
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
        return [f"{name} ({count})"
                for name, count in sorted_dict(self.processes).items()]

    @property
    def summary(self):
        """
        Output a dict summary of this class i.e. services, their state and any
        processes run by them.
        """
        return {'pebble': self._service_info,
                'ps': self._process_info}


class ServiceFactory(FactoryBase):
    """
    Factory to dynamically create PebbleService objects for given services.

    Service objects are returned when a getattr() is done on this object using
    the name of the service as the attr name.
    """

    def __getattr__(self, svc):
        log.debug("creating service object for %s", svc)
        return PebbleHelper([svc]).services.get(svc)
