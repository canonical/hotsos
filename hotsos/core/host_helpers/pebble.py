import re
from functools import cached_property

from hotsos.core.log import log
from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.host_helpers.common import ServiceManagerBase


class PebbleService():
    """ Representation of a pebble service. """
    def __init__(self, name, state):
        self.name = name
        self.state = state

    def __repr__(self):
        return f"name={self.name}, state={self.state}"


class PebbleHelper(ServiceManagerBase):
    """ Helper class used to query pebble services. """

    @property
    def _service_manager_type(self):
        return 'pebble'

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
    def _service_filtered_ps(self):
        return CLIHelper().ps()


class ServiceFactory(FactoryBase):
    """
    Factory to dynamically create PebbleService objects for given services.

    Service objects are returned when a getattr() is done on this object using
    the name of the service as the attr name.
    """

    def __getattr__(self, svc):
        log.debug("creating service object for %s", svc)
        return PebbleHelper([svc]).services.get(svc)
