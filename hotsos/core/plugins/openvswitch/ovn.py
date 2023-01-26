import abc

from hotsos.core.log import log
from hotsos.core.search import (
    SearchDef,
    SequenceSearchDef,
    FileSearcher,
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.utils import cached_property, mktemp_dump
from hotsos.core.host_helpers import SystemdHelper
from hotsos.core.plugins.openvswitch.common import OVS_SERVICES_EXPRS


class OVNSBDBPort(object):

    def __init__(self, name, type):
        self.name = name
        self.type = type


class OVNSBDBChassis(object):

    def __init__(self, name, content):
        self.name = name
        self.content = content or {}

    @cached_property
    def _ports(self):
        ports = []
        if not self.content or 'Port_Binding' not in self.content:
            return ports

        for p in self.content['Port_Binding']:
            if 'cr-lrp' in p:
                ports.append(OVNSBDBPort(p, 'cr-lrp'))
            else:
                ports.append(OVNSBDBPort(p, 'lsp'))

        return ports

    @cached_property
    def ports(self):
        return self._ports

    @cached_property
    def cr_ports(self):
        return [p for p in self._ports if p.type == 'cr-lrp']


class OVNDBBase(object):

    def __init__(self):
        contents = mktemp_dump(''.join(self.db_show))
        s = FileSearcher()
        s.add(self.resources_sd, contents)
        self.results = s.run()

    @abc.abstractproperty
    def db_show(self):
        """ e.g. ovn-sbctl show  """

    @cached_property
    def resources_sd(self):
        start = SearchDef([r"^(\S+)\s+(\S+)\s*.*"])
        body = SearchDef(r"^\s+(\S+)\s+(.+)")
        return SequenceSearchDef(start=start, body=body, tag='resources')

    @cached_property
    def resources(self):
        _resources = {}
        resource = None
        id = None
        sections = self.results.find_sequence_sections(self.resources_sd)
        for section in sections.values():
            for result in section:
                if result.tag == self.resources_sd.start_tag:
                    resource = result.get(1)
                    id = result.get(2)
                    if resource in _resources:
                        _resources[resource][id] = {}
                    else:
                        _resources[resource] = {id: {}}
                elif result.tag == self.resources_sd.body_tag:
                    rtype = result.get(1)
                    if rtype in _resources[resource][id]:
                        _resources[resource][id][rtype].append(result.get(2))
                    else:
                        _resources[resource][id][rtype] = [result.get(2)]

        return _resources


class OVNNBDB(OVNDBBase):
    """ Represents OVN Northbound DB. """

    @property
    def db_show(self):
        return CLIHelper().ovn_nbctl_show()

    @cached_property
    def routers(self):
        _routers = []
        for r, v in self.resources.items():
            if r == 'router':
                for id in v:
                    _routers.append(id)

        return _routers

    @cached_property
    def switches(self):
        _switches = []
        for r, v in self.resources.items():
            if r == 'switch':
                for id in v:
                    _switches.append(id)

        return _switches


class OVNSBDB(OVNDBBase):
    """ Represents OVN Southbound DB. """

    @property
    def db_show(self):
        return CLIHelper().ovn_sbctl_show()

    @cached_property
    def chassis(self):
        _chassis = []
        for r, v in self.resources.items():
            if r == 'Chassis':
                for id, contents in v.items():
                    _chassis.append(OVNSBDBChassis(id, contents))

        return _chassis


class OVNBase(object):
    """
    Base class for all OVN components.
    """
    def __init__(self):
        self.systemd = SystemdHelper(service_exprs=OVS_SERVICES_EXPRS)

    @cached_property
    def is_ovn_central(self):
        if HotSOSConfig.force_mode:
            return True

        ret = 'ovn-central' in self.systemd.services
        if ret:
            log.debug("this is an ovn-central")
        else:
            log.debug("this is not an ovn-central")

        return ret

    @cached_property
    def is_ovn_controller(self):
        if HotSOSConfig.force_mode:
            return True

        ret = 'ovn-controller' in self.systemd.services
        if ret:
            log.debug("this is an ovn-controller")
        else:
            log.debug("this is not an ovn-controller")

        return ret

    @cached_property
    def sbdb(self):
        if self.is_ovn_central:
            return OVNSBDB()

    @cached_property
    def nbdb(self):
        if self.is_ovn_central:
            return OVNNBDB()
