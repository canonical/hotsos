from functools import cached_property

from hotsos.core.plugins.openstack.openstack import OSTServiceBase

OCTAVIA_HM_PORT_NAME = 'o-hm0'


class OctaviaBase(OSTServiceBase):
    """ Base class for Octavia checks. """
    def __init__(self, *args, **kwargs):
        super().__init__('octavia', *args, **kwargs)

    @property
    def bind_interfaces(self):
        """
        Fetch interface o-hm0 used by Openstack Octavia. Returned dict is
        keyed by config key used to identify interface.
        """
        interfaces = {}
        port = self.nethelp.get_interface_with_name(OCTAVIA_HM_PORT_NAME)
        if port:
            interfaces.update({OCTAVIA_HM_PORT_NAME: port})

        return interfaces

    @property
    def hm_port_has_address(self):
        port = self.bind_interfaces.get(OCTAVIA_HM_PORT_NAME)
        if port is None or not port.addresses:
            return False

        return True

    @cached_property
    def hm_port_healthy(self):
        port = self.bind_interfaces.get(OCTAVIA_HM_PORT_NAME)
        if port is None:
            return True

        for counters in port.stats.values():
            total = sum(counters.values())
            if not total:
                continue

            pcent = int(100 / float(total) * float(counters.get('dropped', 0)))
            if pcent > 1:
                return False

            pcent = int(100 / float(total) * float(counters.get('errors', 0)))
            if pcent > 1:
                return False

        return True
